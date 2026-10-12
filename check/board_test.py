#!/usr/bin/env python3
"""JPEG bytes and detection boxes become the page's ounces.

    python check/board_test.py
"""

import sys
import tempfile
import unittest
import urllib.request
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "page"))
sys.path.insert(0, str(ROOT / "check"))

import board
import ledger
import live
import sight

# 4-cup line, copied as a number so this test does not read volume.LINES.
FOUR_CUP_RATIO = 0.3831708317431226
LIQUID_Y0 = 1000 - FOUR_CUP_RATIO * 1000
CHICAGO = ZoneInfo("America/Chicago")


def four_cups():
    return (
        sight.Box("Reservoir", 0.9, 0.0, 0.0, 10.0, 1000.0),
        sight.Box("liquid-level", 0.8, 0.0, LIQUID_Y0, 10.0, LIQUID_Y0 + 10),
    )


def shot():
    return b"\xff\xd8\xff\x00\xff\xd9"


def one_decimal(gauge):
    tenths = round(gauge * 10)
    sign = "-" if tenths < 0 else ""
    whole, frac = divmod(abs(tenths), 10)
    return f"{sign}{whole}.{frac} fl oz"


def node(page, element_id):
    marker = f'id="{element_id}"'
    start = page.index(marker)
    start = page.index(">", start) + 1
    return page[start : page.index("<", start)]


class BoardTests(unittest.TestCase):
    def test_boxes_become_the_page_ounces(self):
        held = tempfile.TemporaryDirectory()
        self.addCleanup(held.cleanup)
        folder = Path(held.name)
        path = folder / "tank.sqlite"
        frames = folder / "frames"
        boxes = four_cups()
        seen = sight.seen(boxes)
        self.assertIsNotNone(seen.gauge_oz)
        self.assertIs(seen.person, False)
        self.assertNotEqual(seen.gauge_oz, 0)
        at = datetime(2026, 10, 12, 12, 0, 15, tzinfo=CHICAGO)
        db = ledger.connect(path)
        try:
            applied = board.tick(db, frames, shot(), boxes, at)
        finally:
            db.close()
        tenths = round(seen.gauge_oz * 10)
        self.assertEqual(applied.machine.booked_oz, tenths / 10)
        running = live.serve(path, frames, 0)
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{running.port}/", timeout=5) as resp:
                page = resp.read().decode()
        finally:
            running.close()
        self.assertEqual(node(page, "ounces"), one_decimal(seen.gauge_oz))
        self.assertEqual(node(page, "person-line"), "No")
        jpegs = [item for item in frames.iterdir() if item.suffix.lower() in {".jpg", ".jpeg"}]
        self.assertEqual(len(jpegs), 1)
        self.assertEqual(jpegs[0].read_bytes(), shot())

    def test_empty_jpeg_writes_nothing(self):
        held = tempfile.TemporaryDirectory()
        self.addCleanup(held.cleanup)
        folder = Path(held.name)
        path = folder / "tank.sqlite"
        frames = folder / "frames"
        at = datetime(2026, 10, 12, 12, 0, 15, tzinfo=CHICAGO)
        db = ledger.connect(path)
        try:
            with self.assertRaises(ValueError) as caught:
                board.tick(db, frames, b"", four_cups(), at)
            self.assertEqual(str(caught.exception), "JPEG bytes are empty.")
            count = db.execute("SELECT COUNT(*) FROM reading").fetchone()[0]
        finally:
            db.close()
        self.assertEqual(count, 0)
        self.assertFalse(frames.exists())


if __name__ == "__main__":
    unittest.main()
