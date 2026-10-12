#!/usr/bin/env python3
"""The Roboflow Workflow the board runs in process with the `inference` package.

Steps: the fine-tuned tank model, the COCO RF-DETR Nano kept to `person`, and the TankGauge
custom block, which turns the two sets of boxes into fluid ounces and a person flag.

    python check/workflow.py --export workflow/tank-gauge.json
"""

from __future__ import annotations

import json
import os
import sys
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any, NamedTuple

sys.path.insert(0, str(Path(__file__).resolve().parent))

import sight
import tank_gauge

TANK_MODEL = "rate-and-volume-of-coffee/1"
PERSON_MODEL = "rfdetr-nano"
_DETECTOR = "roboflow_core/roboflow_object_detection_model@v2"
# Read by `inference` when it is first imported, so `Runner` sets them before that import.
_ENVIRONMENT = {
    "ALLOW_CUSTOM_PYTHON_EXECUTION_IN_WORKFLOWS": "True",
    "MODEL_CACHE_DIR": str(Path.home() / ".inference" / "cache"),
    "CORE_MODEL_SAM_ENABLED": "False",
    "CORE_MODEL_SAM3_ENABLED": "False",
    "CORE_MODEL_YOLO_WORLD_ENABLED": "False",
    "CORE_MODEL_GAZE_ENABLED": "False",
}


def definition(tank_model: str = TANK_MODEL) -> dict:
    return {
        "version": "1.0",
        "inputs": [{"type": "WorkflowImage", "name": "image"}],
        "dynamic_blocks_definitions": [
            {
                "type": "DynamicBlockDefinition",
                "manifest": {
                    "type": "ManifestDescription",
                    "block_type": "TankGauge",
                    "inputs": {
                        "tank": {"type": "DynamicInputDefinition", "selector_types": ["step_output"]},
                        "people": {"type": "DynamicInputDefinition", "selector_types": ["step_output"]},
                    },
                    "outputs": {
                        "gauge_oz": {"type": "DynamicOutputDefinition", "kind": []},
                        "person": {"type": "DynamicOutputDefinition", "kind": []},
                    },
                },
                "code": {"type": "PythonCode", "run_function_code": tank_gauge.code()},
            }
        ],
        "steps": [
            {
                "type": _DETECTOR,
                "name": "tank",
                "image": "$inputs.image",
                "model_id": tank_model,
                "confidence": sight.THRESHOLD,
            },
            {
                "type": _DETECTOR,
                "name": "people",
                "image": "$inputs.image",
                "model_id": PERSON_MODEL,
                "confidence": sight.THRESHOLD,
                "class_filter": ["person"],
            },
            {
                "type": "TankGauge",
                "name": "gauge",
                "tank": "$steps.tank.predictions",
                "people": "$steps.people.predictions",
            },
        ],
        "outputs": [
            {"type": "JsonField", "name": "tank", "selector": "$steps.tank.predictions"},
            {"type": "JsonField", "name": "people", "selector": "$steps.people.predictions"},
            {"type": "JsonField", "name": "gauge_oz", "selector": "$steps.gauge.gauge_oz"},
            {"type": "JsonField", "name": "person", "selector": "$steps.gauge.person"},
        ],
    }


def api_key(env_file: Path = Path.home() / "tank-envs" / "roboflow.env") -> str | None:
    """`ROBOFLOW_API_KEY` from the environment, else from a KEY=value file kept outside the repo."""
    key = os.environ.get("ROBOFLOW_API_KEY")
    if key:
        return key
    try:
        lines = env_file.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    for line in lines:
        name, _, value = line.partition("=")
        if name.strip() == "ROBOFLOW_API_KEY":
            return value.strip().strip('"').strip("'") or None
    return None


def boxes_from(detections: Any) -> tuple[sight.Box, ...]:
    """`sv.Detections` to `sight.Box` values, in the model's order."""
    names = detections.data.get("class_name", [])
    return tuple(
        sight.Box(str(name), float(score), float(xyxy[0]), float(xyxy[1]), float(xyxy[2]), float(xyxy[3]))
        for name, score, xyxy in zip(names, detections.confidence, detections.xyxy)
    )


def step_ms(trace: list[Mapping[str, Any]]) -> dict[str, int]:
    """Milliseconds of the newest run of each step, from the Workflows profiler's trace."""
    found: dict[str, int] = {}
    for event in trace:
        if event.get("name") != "step_code_execution" or "dur" not in event:
            continue
        step = str(event.get("args", {}).get("step", ""))
        found[step.removeprefix("$steps.")] = round(float(event["dur"]) / 1000)
    return found


class Result(NamedTuple):
    boxes: tuple[sight.Box, ...]
    gauge_oz: float | None
    person: bool
    tank_ms: int
    person_ms: int
    total_ms: int


class Runner:
    """One compiled Workflow and its loaded models, kept for the life of the board process."""

    def __init__(self, key: str, tank_model: str = TANK_MODEL) -> None:
        for name, value in _ENVIRONMENT.items():
            os.environ.setdefault(name, value)
        from inference.core.env import MAX_ACTIVE_MODELS
        from inference.core.managers.base import ModelManager
        from inference.core.managers.decorators.fixed_size_cache import WithFixedSizeCache
        from inference.core.registries.roboflow import RoboflowModelRegistry
        from inference.core.workflows.core_steps.common.entities import StepExecutionMode
        from inference.core.workflows.execution_engine.core import ExecutionEngine
        from inference.models.utils import ROBOFLOW_MODEL_TYPES
        from roboflow_workflows.execution_engine.profiling.core import BaseWorkflowsProfiler

        manager = WithFixedSizeCache(
            ModelManager(model_registry=RoboflowModelRegistry(ROBOFLOW_MODEL_TYPES)),
            max_size=MAX_ACTIVE_MODELS,
        )
        self._profiler = BaseWorkflowsProfiler.init(max_runs_in_buffer=1)
        self._engine = ExecutionEngine.init(
            workflow_definition=definition(tank_model),
            init_parameters={
                "workflows_core.model_manager": manager,
                "workflows_core.api_key": key,
                "workflows_core.step_execution_mode": StepExecutionMode.LOCAL,
            },
            max_concurrent_steps=1,
            profiler=self._profiler,
        )

    def run(self, image: Any) -> Result:
        """One BGR frame through the Workflow. The first call downloads and loads both models."""
        started = time.perf_counter()
        output = self._engine.run(runtime_parameters={"image": [image]})[0]
        total_ms = round((time.perf_counter() - started) * 1000)
        steps = step_ms(self._profiler.export_trace())
        gauge = output["gauge_oz"]
        return Result(
            boxes=boxes_from(output["tank"]) + boxes_from(output["people"]),
            gauge_oz=None if gauge is None else float(gauge),
            person=bool(output["person"]),
            tank_ms=steps.get("tank", total_ms),
            person_ms=steps.get("people", 0),
            total_ms=total_ms,
        )


def main(argv: list[str]) -> None:
    if len(argv) == 3 and argv[1] == "--export":
        Path(argv[2]).parent.mkdir(parents=True, exist_ok=True)
        Path(argv[2]).write_text(json.dumps(definition(), indent=2) + "\n", encoding="utf-8")
        return
    raise SystemExit("usage: python check/workflow.py --export <path>")


if __name__ == "__main__":
    main(sys.argv)
