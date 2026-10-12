#!/usr/bin/env python3
"""JPEG bytes and detection boxes become the page's ounces.

    python check/board_test.py
"""

import json
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

    def test_the_frame_keeps_its_boxes_beside_it(self):
        held = tempfile.TemporaryDirectory()
        self.addCleanup(held.cleanup)
        folder = Path(held.name)
        frames = folder / "frames"
        boxes = four_cups() + (
            sight.Box("Reservoir", 0.5, 0.0, 0.0, 10.0, 990.0),
            sight.Box("chair", 0.7, 1.0, 2.0, 3.0, 4.0),
        )
        db = ledger.connect(folder / "tank.sqlite")
        try:
            board.tick(db, frames, shot(), boxes, datetime(2026, 10, 12, 12, 0, tzinfo=CHICAGO), size=(1280, 720))
        finally:
            db.close()
        saved = json.loads((frames / "00000001.json").read_text(encoding="utf-8"))
        self.assertEqual((saved["width"], saved["height"]), (1280, 720))
        self.assertEqual(saved["gauge_oz"], sight.seen(boxes).gauge_oz)
        used = {(box["name"], box["score"]): box["used"] for box in saved["boxes"]}
        self.assertEqual(
            used,
            {("Reservoir", 0.9): True, ("liquid-level", 0.8): True, ("Reservoir", 0.5): False, ("chair", 0.7): False},
        )

    def test_the_board_thins_ffmpeg_ahead_of_the_flip(self):
        command = ["ffmpeg", "-i", "/dev/video0", "-vf", "hflip,vflip", "-f", "mjpeg", "pipe:1"]
        self.assertEqual(
            board.thinned(command, 2),
            ["ffmpeg", "-i", "/dev/video0", "-vf", "fps=2,hflip,vflip", "-f", "mjpeg", "pipe:1"],
        )
        self.assertEqual(command[4], "hflip,vflip")

    def test_memory_and_temperature_come_from_proc_and_sys(self):
        held = tempfile.TemporaryDirectory()
        self.addCleanup(held.cleanup)
        folder = Path(held.name)
        status = folder / "status"
        status.write_text("Name:\tpython\nVmRSS:\t  812032 kB\nThreads:\t9\n", encoding="utf-8")
        zone = folder / "temp"
        zone.write_text("78880\n", encoding="utf-8")
        self.assertEqual(board.rss_mb(status), 793)
        self.assertEqual(board.temp_c(zone), 78.9)
        self.assertIsNone(board.rss_mb(folder / "missing"))
        self.assertIsNone(board.temp_c(folder / "missing"))
        zone.write_text("warm\n", encoding="utf-8")
        self.assertIsNone(board.temp_c(zone))

    def test_the_reading_keeps_memory_temperature_and_frame_age(self):
        held = tempfile.TemporaryDirectory()
        self.addCleanup(held.cleanup)
        folder = Path(held.name)
        db = ledger.connect(folder / "tank.sqlite")
        try:
            board.tick(
                db,
                folder / "frames",
                shot(),
                four_cups(),
                datetime(2026, 10, 12, 12, 0, tzinfo=CHICAGO),
                board.Elapsed(capture_ms=180, tank_ms=3700, person_ms=3690),
                memory_mb=793,
                cpu_c=78.9,
            )
            row = db.execute("SELECT ts, capture_ms, rss_mb, temp_c FROM reading").fetchone()
        finally:
            db.close()
        self.assertEqual(tuple(row), ("2026-10-12T12:00:00-05:00", 180, 793, 78.9))

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
