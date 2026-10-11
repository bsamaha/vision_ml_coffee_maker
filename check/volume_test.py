#!/usr/bin/env python3
"""Defined cup-line checks for the box-ratio conversion.

    python check/volume_test.py
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import volume

# box ratio, cups. One camera angle. Empty is 0. 4, 6, 8, and 10 are the
# mean of the three settled rounds. 2 is the alarm pour. 14 is round 3 only.
KNOTS = (
    (0.0, 0),
    (0.22273079838880622, 2),
    (0.3831708317431226, 4),
    (0.5264066757481384, 6),
    (0.6760998404779525, 8),
    (0.7640879285619365, 10),
    (0.9951559305027505, 14),
)

TWO = 0.22273079838880622
FOUR = 0.3831708317431226


class VolumeTests(unittest.TestCase):
    def test_one_table(self):
        self.assertEqual(volume.LINES, KNOTS)
        self.assertFalse(hasattr(volume, "POSE"))

    def test_labeled_lines_come_back_as_those_cups(self):
        for ratio, cups in KNOTS:
            with self.subTest(cups=cups):
                got = volume.reading(ratio)
                self.assertEqual(got.cups, cups)
                self.assertEqual(got.percent, cups / volume.FULL_CUPS * 100)
                self.assertEqual(got.fluid_ounces, cups * volume.OZ_PER_CUP)
                self.assertEqual(got.fluid_ounces / volume.OZ_PER_CUP, got.cups)

    def test_two_cups_is_one_seventh_of_the_tank(self):
        got = volume.reading(TWO)
        self.assertEqual(got.cups, 2)
        self.assertEqual(got.percent, 2 / 14 * 100)
        self.assertAlmostEqual(got.percent, 14.285714, places=5)
        self.assertEqual(got.fluid_ounces, 10)

    def test_halfway_between_two_and_four_cups_is_three(self):
        midpoint = (TWO + FOUR) / 2
        got = volume.reading(midpoint)
        self.assertAlmostEqual(got.cups, 3)
        self.assertAlmostEqual(got.percent, 3 / 14 * 100)
        self.assertAlmostEqual(got.fluid_ounces, 15)

    def test_live_four_cup_ratio_is_near_four(self):
        six = 0.5264066757481384
        for ratio in (0.391, 0.395):
            with self.subTest(ratio=ratio):
                expected = 4 + (ratio - FOUR) / (six - FOUR) * 2
                got = volume.reading(ratio)
                self.assertAlmostEqual(got.cups, expected)
                self.assertGreater(got.cups, 4.0)
                self.assertLess(got.cups, 4.2)

    def test_no_liquid_line_is_empty(self):
        got = volume.reading(None)
        self.assertEqual(got.cups, 0)
        self.assertEqual(got.percent, 0)
        self.assertEqual(got.fluid_ounces, 0)

    def test_a_line_above_the_14_cup_mark_is_full(self):
        got = volume.reading(1.2)
        self.assertEqual(got.cups, 14)
        self.assertEqual(got.percent, 100)
        self.assertEqual(got.fluid_ounces, 70)

    def test_a_line_below_the_floor_is_empty(self):
        got = volume.reading(-0.2)
        self.assertEqual(got.cups, 0)
        self.assertEqual(got.percent, 0)

    def test_box_ratio_is_the_filled_share_of_the_reservoir(self):
        ratio = volume.box_ratio(100.0, 300.0, 200.0)
        self.assertAlmostEqual(ratio, 0.5)
        got = volume.reading(TWO)
        self.assertEqual(got.cups, 2)
        with self.assertRaises(ValueError):
            volume.box_ratio(300.0, 100.0, 200.0)

    def test_reading_does_not_take_a_pose(self):
        with self.assertRaises(TypeError):
            volume.reading("square", FOUR)


if __name__ == "__main__":
    unittest.main()
