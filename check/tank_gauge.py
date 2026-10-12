"""The TankGauge custom block that the Roboflow Workflow runs.

The Workflow carries this code as text, so it cannot import `sight` or `volume`. `code()` writes
the cup table from `volume.LINES` into it, and `run()` executes the same text here, which is how
the tests hold it to `sight.seen`.
"""

from collections.abc import Sequence
from typing import Any

import sight
import volume

_TEMPLATE = '''
LINES = {lines!r}
OZ_PER_CUP = {oz_per_cup!r}
THRESHOLD = {threshold!r}


def _best(detections, name):
    names = detections.data.get("class_name", [])
    best = None
    for index in range(len(detections)):
        if names[index] != name or detections.confidence[index] < THRESHOLD:
            continue
        if best is None or detections.confidence[index] > detections.confidence[best]:
            best = index
    return best


def _cups(ratio):
    if ratio <= LINES[0][0]:
        return float(LINES[0][1])
    if ratio >= LINES[-1][0]:
        return float(LINES[-1][1])
    for (low_ratio, low_cups), (high_ratio, high_cups) in zip(LINES, LINES[1:]):
        if low_ratio <= ratio <= high_ratio:
            return low_cups + (ratio - low_ratio) / (high_ratio - low_ratio) * (high_cups - low_cups)
    return float(LINES[-1][1])


def run(self, tank, people):
    reservoir = _best(tank, "Reservoir")
    liquid = _best(tank, "liquid-level")
    gauge_oz = None
    if reservoir is not None:
        top, bottom = float(tank.xyxy[reservoir][1]), float(tank.xyxy[reservoir][3])
        if bottom > top:
            if liquid is None:
                gauge_oz = 0.0
            else:
                ratio = (bottom - float(tank.xyxy[liquid][1])) / (bottom - top)
                gauge_oz = _cups(ratio) * OZ_PER_CUP
    return {{"gauge_oz": gauge_oz, "person": _best(people, "person") is not None}}
'''


def code() -> str:
    return _TEMPLATE.format(lines=volume.LINES, oz_per_cup=volume.OZ_PER_CUP, threshold=sight.THRESHOLD)


class Detections:
    """The parts of `sv.Detections` the block reads, built from `sight.Box` values."""

    def __init__(self, boxes: Sequence[sight.Box]) -> None:
        self.data = {"class_name": [box.name for box in boxes]}
        self.confidence = [box.score for box in boxes]
        self.xyxy = [(box.x0, box.y0, box.x1, box.y1) for box in boxes]

    def __len__(self) -> int:
        return len(self.confidence)


def run(tank: Any, people: Any) -> dict:
    namespace: dict = {}
    exec(code(), namespace)
    return namespace["run"](None, tank, people)
