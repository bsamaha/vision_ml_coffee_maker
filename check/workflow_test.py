#!/usr/bin/env python3
"""The Workflow definition and the TankGauge block, without the `inference` package.

    python check/workflow_test.py
"""

import json
import random
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import ledger
import sight
import tank_gauge
import volume
import workflow


def box(name, score, y0=0.0, y1=10.0):
    return sight.Box(name, score, 0.0, y0, 10.0, y1)


def gauge(boxes):
    tank = tank_gauge.Detections([b for b in boxes if b.name != "person"])
    people = tank_gauge.Detections([b for b in boxes if b.name == "person"])
    return tank_gauge.run(tank, people)


class TankGaugeTests(unittest.TestCase):
    def assert_matches_sight(self, boxes):
        got = gauge(boxes)
        want = sight.seen(boxes)
        if want.gauge_oz is None:
            self.assertIsNone(got["gauge_oz"], boxes)
        else:
            self.assertAlmostEqual(got["gauge_oz"], want.gauge_oz, places=9, msg=boxes)
        self.assertIs(got["person"], want.person, boxes)

    def test_no_reservoir_is_no_gauge(self):
        self.assert_matches_sight(())
        self.assert_matches_sight((box("liquid-level", 0.9, 400, 1000),))

    def test_a_reservoir_without_a_line_is_empty(self):
        self.assertEqual(gauge((box("Reservoir", 0.9, 0, 1000),))["gauge_oz"], 0.0)

    def test_every_cup_line_reads_its_ounces(self):
        for ratio, cups in volume.LINES:
            got = gauge((box("Reservoir", 0.9, 0, 1000), box("liquid-level", 0.8, 1000 - ratio * 1000, 1000)))
            self.assertAlmostEqual(got["gauge_oz"], cups * volume.OZ_PER_CUP, places=6)

    def test_the_best_box_wins_and_low_scores_drop(self):
        self.assert_matches_sight(
            (
                box("Reservoir", 0.5, 0, 900),
                box("Reservoir", 0.9, 0, 1000),
                box("liquid-level", 0.39, 100, 1000),
                box("liquid-level", 0.7, 600, 1000),
                box("person", 0.3),
            )
        )

    def test_random_boxes_match_sight(self):
        rng = random.Random(7)
        for _ in range(500):
            boxes = []
            for name in ("Reservoir", "liquid-level", "person", "chair"):
                for _ in range(rng.randint(0, 2)):
                    top = rng.uniform(0, 600)
                    boxes.append(box(name, rng.uniform(0.2, 1.0), top, top + rng.uniform(1, 600)))
            self.assert_matches_sight(tuple(boxes))

    def test_the_block_carries_the_current_cup_table(self):
        self.assertIn(repr(volume.LINES), tank_gauge.code())


class WorkflowTests(unittest.TestCase):
    def test_the_definition_wires_both_models_into_the_gauge(self):
        spec = workflow.definition()
        steps = {step["name"]: step for step in spec["steps"]}
        self.assertEqual(steps["tank"]["model_id"], workflow.TANK_MODEL)
        self.assertEqual(steps["people"]["model_id"], "rfdetr-nano")
        self.assertEqual(steps["people"]["class_filter"], ["person"])
        self.assertEqual(steps["gauge"]["type"], "TankGauge")
        self.assertEqual(steps["gauge"]["tank"], "$steps.tank.predictions")
        self.assertEqual(steps["gauge"]["people"], "$steps.people.predictions")
        block = spec["dynamic_blocks_definitions"][0]
        self.assertEqual(block["manifest"]["block_type"], "TankGauge")
        self.assertEqual(block["code"]["run_function_code"], tank_gauge.code())
        self.assertEqual({o["name"] for o in spec["outputs"]}, {"tank", "people", "gauge_oz", "person"})
        json.dumps(spec)

    def test_the_export_is_the_definition(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        path = Path(folder.name) / "workflow" / "tank-gauge.json"
        workflow.main(["workflow.py", "--export", str(path)])
        self.assertEqual(json.loads(path.read_text(encoding="utf-8")), workflow.definition())

    def test_the_committed_export_is_current(self):
        committed = Path(__file__).resolve().parent.parent / "workflow" / "tank-gauge.json"
        self.assertEqual(json.loads(committed.read_text(encoding="utf-8")), workflow.definition())

    def test_the_alert_workflow_is_the_board_workflow_plus_an_email(self):
        board = workflow.definition()
        alert = workflow.alert_definition()
        self.assertEqual(alert["steps"][: len(board["steps"])], board["steps"])
        self.assertEqual(alert["dynamic_blocks_definitions"], board["dynamic_blocks_definitions"])
        added = {step["name"]: step for step in alert["steps"][len(board["steps"]) :]}
        self.assertEqual(set(added), {"low", "photo", "refill_email"})
        condition = added["low"]["condition_statement"]["statements"][0]
        self.assertEqual(condition["comparator"]["type"], "(Number) <")
        self.assertEqual(condition["right_operand"]["value"], ledger._ALARM / 10)
        self.assertEqual(added["low"]["evaluation_parameters"], {"level": "$steps.gauge.gauge_oz"})
        self.assertEqual(added["low"]["next_steps"], ["$steps.photo"])
        email = added["refill_email"]
        self.assertEqual(email["type"], "roboflow_core/email_notification@v2")
        self.assertEqual(email["receiver_email"], "$inputs.alert_email")
        self.assertEqual(email["attachments"], {"tank.jpg": "$steps.photo.image"})
        self.assertIn({"type": "WorkflowParameter", "name": "alert_email"}, alert["inputs"])

    def test_the_board_workflow_sends_nothing(self):
        text = json.dumps(workflow.definition())
        self.assertNotIn("email", text)
        self.assertNotIn("continue_if", text)

    def test_no_email_address_is_stored(self):
        text = json.dumps(workflow.alert_definition())
        self.assertNotRegex(text, r"[\w.+-]+@[\w-]+\.[\w.]+")

    def test_the_committed_alert_export_is_current(self):
        committed = Path(__file__).resolve().parent.parent / "workflow" / "tank-gauge-alert.json"
        self.assertEqual(json.loads(committed.read_text(encoding="utf-8")), workflow.alert_definition())

    def test_detections_become_boxes(self):
        detections = tank_gauge.Detections((box("Reservoir", 0.9, 5, 50), box("liquid-level", 0.8, 20, 50)))
        self.assertEqual(
            workflow.boxes_from(detections),
            (sight.Box("Reservoir", 0.9, 0.0, 5.0, 10.0, 50.0), sight.Box("liquid-level", 0.8, 0.0, 20.0, 10.0, 50.0)),
        )

    def test_step_times_come_from_the_newest_run(self):
        trace = [
            {"name": "step_code_execution", "args": {"step": "$steps.tank"}, "dur": 9_000_000},
            {"name": "step_code_execution", "args": {"step": "$steps.tank"}, "dur": 1_861_400},
            {"name": "step_code_execution", "args": {"step": "$steps.people"}, "dur": 1_830_600},
            {"name": "step_execution", "dur": 5},
            {"name": "step_code_execution", "args": {"step": "$steps.gauge"}},
        ]
        self.assertEqual(workflow.step_ms(trace), {"tank": 1861, "people": 1831})

    def test_the_api_key_comes_from_the_environment_or_a_file(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        env_file = Path(folder.name) / "roboflow.env"
        saved = workflow.os.environ.pop("ROBOFLOW_API_KEY", None)
        try:
            self.assertIsNone(workflow.api_key(env_file))
            env_file.write_text('# key\nROBOFLOW_API_KEY="abc123"\n', encoding="utf-8")
            self.assertEqual(workflow.api_key(env_file), "abc123")
            workflow.os.environ["ROBOFLOW_API_KEY"] = "from-env"
            self.assertEqual(workflow.api_key(env_file), "from-env")
        finally:
            workflow.os.environ.pop("ROBOFLOW_API_KEY", None)
            if saved is not None:
                workflow.os.environ["ROBOFLOW_API_KEY"] = saved


if __name__ == "__main__":
    unittest.main()
