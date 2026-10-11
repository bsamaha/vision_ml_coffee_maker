#!/usr/bin/env python3
"""Known-cup comparison. No camera and no model.

    python check/compare_test.py
"""

import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import compare
import volume


RESERVOIR = (0.0, 100.0, 50.0, 300.0)
LIQUID = (0.0, 200.0, 40.0, 250.0)


def four_knot():
    return next(ratio for ratio, cups in volume.LINES if cups == 4)


class CompareTests(unittest.TestCase):
    def test_class_id_map(self):
        names = compare.id_names_from("background_class83422\nReservoir\nliquid-level\n")
        self.assertEqual(names[0].startswith("background_class"), True)
        self.assertEqual(names[1], "Reservoir")
        self.assertEqual(names[2], "liquid-level")

        class Predicted:
            class_id = [1, 2]
            data = {"class_name": ["liquid-level", "__background__"]}

        labels = compare.labels_for(Predicted(), names)
        self.assertEqual(labels, ["Reservoir", "liquid-level"])
        reservoir, liquid = compare.pick_boxes(
            labels,
            [0.9375, 0.8787],
            [(714.5, 308.1, 786.1, 529.2), (721.6, 443.3, 784.6, 528.0)],
        )
        self.assertEqual(reservoir, (714.5, 308.1, 786.1, 529.2))
        self.assertEqual(liquid, (721.6, 443.3, 784.6, 528.0))

    def test_difference_versus_known_cups(self):
        row = compare.comparison(4, RESERVOIR, LIQUID)
        ratio = volume.box_ratio(100.0, 300.0, 200.0)
        got = volume.reading(ratio)
        known_percent = 4 / volume.FULL_CUPS * 100
        self.assertAlmostEqual(row["box_ratio"], ratio)
        self.assertAlmostEqual(row["bottom_gap_px"], 50)
        self.assertEqual(row["cups"], got.cups)
        self.assertEqual(row["percent"], got.percent)
        self.assertEqual(row["diff_cups"], got.cups - 4)
        self.assertEqual(row["diff_percent"], got.percent - known_percent)
        self.assertAlmostEqual(known_percent, 4 / 14 * 100)

    def test_knot_ratio_gap_at_four_cups(self):
        labeled = four_knot()
        row = compare.comparison(4, RESERVOIR, LIQUID)
        self.assertNotIn("pose", row)
        self.assertEqual(row["labeled_box_ratio"], labeled)
        self.assertAlmostEqual(labeled, 0.3831708317431226)
        self.assertTrue(row["has_labeled_line"])
        self.assertAlmostEqual(row["box_ratio"], 0.5)
        self.assertAlmostEqual(row["ratio_gap"], row["box_ratio"] - labeled)
        self.assertGreater(row["ratio_gap"], 0)
        text = compare.labeled_text(row)
        self.assertIn("knot box ratio", text)
        self.assertIn("ratio gap +", text)
        line = compare.summary_line(row)
        self.assertNotIn("\n", line)
        self.assertIn("ratio gap +", line)

    def test_known_cups_without_a_knot_still_reports_the_model(self):
        row = compare.comparison(12, RESERVOIR, LIQUID)
        four = compare.comparison(4, RESERVOIR, LIQUID)
        got = volume.reading(row["box_ratio"])
        self.assertFalse(row["has_labeled_line"])
        self.assertIsNone(row["labeled_box_ratio"])
        self.assertIsNone(row["ratio_gap"])
        self.assertAlmostEqual(row["box_ratio"], four["box_ratio"])
        self.assertEqual(row["cups"], got.cups)
        self.assertIsNotNone(row["percent"])
        self.assertEqual(compare.labeled_text(row), "No knot at 12 cups.")

    def test_no_liquid_box_is_zero_cups(self):
        row = compare.comparison(4, RESERVOIR, None)
        self.assertTrue(row["reservoir"])
        self.assertEqual(row["cups"], 0)
        self.assertEqual(row["percent"], 0)
        self.assertIsNone(row["box_ratio"])
        self.assertIsNone(row["bottom_gap_px"])
        self.assertIsNone(row["ratio_gap"])
        self.assertEqual(row["diff_cups"], -4)
        self.assertEqual(row["labeled_box_ratio"], four_knot())

    def test_no_reservoir_box_draws_nothing(self):
        row = compare.comparison(4, None, LIQUID)
        self.assertFalse(row["reservoir"])
        self.assertIsNone(row["cups"])
        self.assertIsNone(row["percent"])
        self.assertIsNone(row["box_ratio"])
        raw = b"jpeg-bytes"
        self.assertIs(compare.draw_boxes(raw, None, LIQUID), raw)

    def test_known_cups_are_0_through_14(self):
        self.assertEqual(compare.parse_cups(0), 0)
        self.assertEqual(compare.parse_cups("14"), 14)
        self.assertEqual(compare.parse_cups(4.0), 4)
        with self.assertRaises(ValueError):
            compare.parse_cups(15)
        with self.assertRaises(ValueError):
            compare.parse_cups(-1)
        with self.assertRaises(ValueError):
            compare.parse_cups(1.5)

    def test_page_is_the_compare_page(self):
        page = compare.PAGE.decode()
        self.assertIn(">Read<", page)
        self.assertIn(">Darker<", page)
        self.assertIn(">Brighter<", page)
        self.assertIn("Known cups", page)
        self.assertIn("box ratio", page)
        self.assertIn("model ", page)
        self.assertIn("difference versus known cups", page)
        self.assertIn("bottom gap", page)
        self.assertIn("knot box ratio", page)
        self.assertIn("ratio gap", page)
        self.assertNotIn("data-pose", page)
        self.assertNotIn("id=poses", page)
        for name in ("square", "right", "left", "face"):
            self.assertIsNone(re.search(rf"(?<![A-Za-z]){name}(?![A-Za-z])", page), name)
        self.assertNotIn("Record this reading", page)
        self.assertNotIn("Capture Image", page)


if __name__ == "__main__":
    unittest.main()
