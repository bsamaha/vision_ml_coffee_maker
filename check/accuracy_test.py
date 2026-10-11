#!/usr/bin/env python3
"""Stop list and percent average for the cup-line check. No camera and no model.

    python check/accuracy_test.py
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import accuracy
import volume


class AccuracyTests(unittest.TestCase):
    def test_stop_list(self):
        stops = accuracy.build_stops()
        expected = []
        for round_n in (1, 2, 3):
            for cups in (4, 6, 8, 10, 14):
                expected.append(
                    ("accuracy", round_n, cups, f"Round {round_n} of 3. Pour to {cups} cups.")
                )
        expected.append(("alarm", None, 2, "Alarm. Pour to 2 cups."))
        expected.append(("alarm", None, 4, "Alarm. One brew that falls through 4 cups."))
        self.assertEqual([(stop.kind, stop.round, stop.cups, stop.title) for stop in stops], expected)
        self.assertEqual(sum(1 for stop in stops if stop.kind == "accuracy"), 15)

    def test_two_cup_row_stays_out_of_the_average(self):
        two = [stop for stop in accuracy.build_stops() if stop.cups == 2]
        self.assertEqual(len(two), 1)
        self.assertEqual(two[0].kind, "alarm")
        row = accuracy.row_for_stop(two[0], (0, 100, 10, 300), None)
        self.assertEqual(row["kind"], "alarm")
        self.assertEqual(row["known_cups"], 2)
        self.assertEqual(row["cups"], 0)
        saved = [
            {"kind": "accuracy", "diff_percent": 2},
            {"kind": "accuracy", "diff_percent": -4},
            row,
        ]
        self.assertEqual(accuracy.abs_percent_average(saved), 3)

    def test_average_is_the_mean_of_absolute_percent_differences(self):
        saved = [
            {"kind": "accuracy", "diff_percent": 1},
            {"kind": "accuracy", "diff_percent": -2},
            {"kind": "accuracy", "diff_percent": 3},
            {"kind": "alarm", "known_cups": 4, "diff_percent": 9},
        ]
        self.assertEqual(accuracy.abs_percent_average(saved), 2)
        self.assertIsNone(accuracy.abs_percent_average([]))
        self.assertIsNone(
            accuracy.abs_percent_average([{"kind": "alarm", "known_cups": 2, "diff_percent": 10}])
        )

    def test_background_class_is_ignored(self):
        names = accuracy.read_class_names("background_class83422\nReservoir\nliquid-level\n")
        self.assertEqual(names, ("Reservoir", "liquid-level"))
        box = accuracy.best_box(
            ["background_class83422", "Reservoir", "Reservoir"],
            [0.99, 0.4, 0.8],
            [(0, 0, 1, 1), (2, 3, 4, 5), (6, 7, 8, 9)],
            "Reservoir",
        )
        self.assertEqual(box, (6.0, 7.0, 8.0, 9.0))

    def test_class_id_is_the_file_line(self):
        names = accuracy.read_id_names("background_class83422\nReservoir\nliquid-level\n")
        self.assertEqual(names, ("background_class83422", "Reservoir", "liquid-level"))

        class Predicted:
            class_id = [1, 2, 3]
            data = {"class_name": ["liquid-level", "__background__", "person"]}

        labels = accuracy.labels_for(Predicted(), names)
        self.assertEqual(labels, ["Reservoir", "liquid-level", "__background__"])
        boxes = [(714.5, 308.1, 786.1, 529.2), (721.6, 443.3, 784.6, 528.0), (0, 0, 1, 1)]
        scores = [0.9375, 0.8787, 0.5]
        self.assertEqual(
            accuracy.best_box(labels, scores, boxes, "Reservoir"),
            (714.5, 308.1, 786.1, 529.2),
        )
        self.assertEqual(
            accuracy.best_box(labels, scores, boxes, "liquid-level"),
            (721.6, 443.3, 784.6, 528.0),
        )

    def test_box_ratio_and_bottom_gap(self):
        reservoir = (0.0, 100.0, 50.0, 300.0)
        liquid = (0.0, 200.0, 40.0, 250.0)
        row = accuracy.reading_for(4, reservoir, liquid)
        self.assertAlmostEqual(row["box_ratio"], (300 - 200) / (300 - 100))
        self.assertAlmostEqual(row["bottom_gap_px"], 50)
        self.assertFalse(hasattr(accuracy, "POSE"))
        self.assertEqual(volume.LINES, (
            (0.0, 0),
            (0.22273079838880622, 2),
            (0.3831708317431226, 4),
            (0.5264066757481384, 6),
            (0.6760998404779525, 8),
            (0.7640879285619365, 10),
            (0.9951559305027505, 14),
        ))
        got = volume.reading(row["box_ratio"])
        self.assertEqual(row["cups"], got.cups)
        self.assertEqual(row["percent"], got.percent)
        self.assertEqual(row["fluid_ounces"], got.fluid_ounces)
        self.assertEqual(row["diff_cups"], got.cups - 4)
        self.assertEqual(row["diff_percent"], got.percent - 4 / volume.FULL_CUPS * 100)

    def test_no_liquid_box_is_zero_cups(self):
        row = accuracy.reading_for(4, (0, 100, 10, 300), None)
        self.assertEqual(row["cups"], 0)
        self.assertEqual(row["percent"], 0)
        self.assertEqual(row["fluid_ounces"], 0)
        self.assertIsNone(row["box_ratio"])
        self.assertIsNone(row["bottom_gap_px"])

    def test_no_reservoir_box_is_not_saved(self):
        self.assertIsNone(accuracy.reading_for(4, None, (0, 200, 10, 250)))


if __name__ == "__main__":
    unittest.main()
