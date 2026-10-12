#!/usr/bin/env python3
"""Detection boxes to one gauge reading and one person flag.

    python check/sight_test.py
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import sight

# 4-cup line from volume.LINES. Stated here so this file does not read that table.
FOUR_CUP_RATIO = 0.3831708317431226
LIQUID_Y0 = 1000 - FOUR_CUP_RATIO * 1000


def box(name, score, y0=0.0, y1=10.0):
    return sight.Box(name, score, 0.0, y0, 10.0, y1)


def four_cups():
    return (
        box("Reservoir", 0.9, 0, 1000),
        box("liquid-level", 0.8, LIQUID_Y0, LIQUID_Y0 + 10),
    )


class SightTests(unittest.TestCase):
    def test_chosen_is_the_best_box_of_each_class_seen_reads(self):
        boxes = four_cups() + (box("Reservoir", 0.5), box("person", 0.6), box("chair", 0.9), box("person", 0.3))
        self.assertEqual(sight.chosen(boxes), (four_cups()[0], four_cups()[1], box("person", 0.6)))

    def test_no_boxes(self):
        got = sight.seen(())
        self.assertEqual(got.gauge_oz, None)
        self.assertEqual(got.person, False)

    def test_reservoir_and_no_line_is_empty(self):
        got = sight.seen((box("Reservoir", 0.9, 0, 1000),))
        self.assertEqual(got.gauge_oz, 0)
        self.assertEqual(got.person, False)

    def test_four_cup_line_is_twenty_ounces(self):
        got = sight.seen(four_cups())
        # A 1000px reservoir cannot hold that ratio exactly, so the ounces sit one ulp under 20.
        self.assertAlmostEqual(got.gauge_oz, 20)
        self.assertEqual(got.person, False)

    def test_person_does_not_change_the_gauge(self):
        got = sight.seen(four_cups() + (box("person", 0.5),))
        self.assertAlmostEqual(got.gauge_oz, 20)
        self.assertEqual(got.person, True)

    def test_person_below_the_cutoff_is_absent(self):
        got = sight.seen((box("person", 0.39),))
        self.assertEqual(got.person, False)
        self.assertEqual(got.gauge_oz, None)

    def test_line_without_a_reservoir_has_no_gauge(self):
        got = sight.seen((box("liquid-level", 0.9, LIQUID_Y0, LIQUID_Y0 + 10),))
        self.assertEqual(got.gauge_oz, None)
        self.assertEqual(got.person, False)

    def test_higher_reservoir_score_wins(self):
        low = box("Reservoir", 0.5, 0, 100)
        high = box("Reservoir", 0.9, 0, 1000)
        line = box("liquid-level", 0.8, LIQUID_Y0, LIQUID_Y0 + 10)
        got = sight.seen((low, high, line))
        self.assertAlmostEqual(got.gauge_oz, 20)
        self.assertEqual(got.person, False)

    def test_background_is_ignored(self):
        got = sight.seen((box("__background__", 0.99, 0, 1000),))
        self.assertEqual(got.gauge_oz, None)
        self.assertEqual(got.person, False)

    def test_person_at_the_cutoff_counts(self):
        got = sight.seen((box("person", 0.4),))
        self.assertEqual(got.person, True)
        self.assertEqual(got.gauge_oz, None)

    def test_line_below_the_cutoff_is_empty(self):
        got = sight.seen(
            (
                box("Reservoir", 0.9, 0, 1000),
                box("liquid-level", 0.39, LIQUID_Y0, LIQUID_Y0 + 10),
            )
        )
        self.assertEqual(got.gauge_oz, 0)
        self.assertEqual(got.person, False)

    def test_a_chair_is_not_a_person(self):
        got = sight.seen(four_cups() + (box("chair", 0.99),))
        self.assertEqual(got.person, False)
        self.assertAlmostEqual(got.gauge_oz, 20)


if __name__ == "__main__":
    unittest.main()
