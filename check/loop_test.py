#!/usr/bin/env python3
"""One tick and the eight newest frames.

    python check/loop_test.py
"""

import os
import re
import sys
import tempfile
import unittest
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import unquote
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "page"))
sys.path.insert(0, str(ROOT / "check"))

import ledger
import live
import loop

CHICAGO = ZoneInfo("America/Chicago")
_CAPTIONS = ("-1:45", "-1:30", "-1:15", "-1:00", "-0:45", "-0:30", "-0:15", "Now")


def shot(index):
    return b"\xff\xd8\xff" + bytes([index]) + b"\xff\xd9"


def at(clock):
    hour, minute, second = (int(part) for part in clock.split(":"))
    return datetime(2026, 10, 12, hour, minute, second, tzinfo=CHICAGO)


def tick(when, gauge):
    return ledger.Tick(when, gauge, False, 0, 0, 0, 0, None, None)


def node(page, element_id):
    marker = f'id="{element_id}"'
    start = page.index(marker)
    start = page.index(">", start) + 1
    return page[start : page.index("<", start)]


def block(page, element_id, close):
    start = page.index(f'id="{element_id}"')
    return page[start : page.index(close, start)]


def opening(page, element_id):
    marker = f'id="{element_id}"'
    at_id = page.index(marker)
    start = page.rfind("<", 0, at_id)
    end = page.index(">", at_id)
    return page[start : end + 1]


def jpegs(folder):
    return [
        path
        for path in folder.iterdir()
        if path.is_file() and path.suffix.lower() in {".jpg", ".jpeg"}
    ]


def strip_srcs(page):
    strip = block(page, "strip", 'id="preview"')
    return [unquote(src) for src in re.findall(r'<img src="([^"]*)"', strip)]


class LoopTests(unittest.TestCase):
    def folder(self):
        held = tempfile.TemporaryDirectory()
        self.addCleanup(held.cleanup)
        return Path(held.name)

    def read(self, running, path):
        with urllib.request.urlopen(f"http://127.0.0.1:{running.port}{path}", timeout=5) as resp:
            self.assertEqual(resp.status, 200)
            return resp.read().decode()

    def body(self, running, path):
        try:
            with urllib.request.urlopen(
                f"http://127.0.0.1:{running.port}{path}", timeout=5
            ) as resp:
                return resp.status, resp.headers.get_content_type(), resp.read()
        except urllib.error.HTTPError as err:
            return err.code, err.headers.get_content_type(), err.read()

    def page(self, db, frames):
        running = live.serve(db, frames, 0)
        try:
            self.assertNotEqual(running.port, 0)
            self.assertNotEqual(running.port, 8080)
            return self.read(running, "/"), running
        except Exception:
            running.close()
            running.close()
            raise

    def test_one_tick_shows_forty_ounces_and_one_frame(self):
        folder = self.folder()
        path = folder / "tank.sqlite"
        frames = folder / "frames"
        db = ledger.connect(path)
        try:
            applied = loop.record(db, frames, shot(0), tick(at("12:00:15"), 40.0))
        finally:
            db.close()
        self.assertEqual(applied.machine.booked_oz, 40.0)
        files = jpegs(frames)
        self.assertEqual(len(files), 1)
        self.assertEqual(files[0].read_bytes(), shot(0))
        page, running = self.page(path, frames)
        try:
            self.assertEqual(node(page, "ounces"), "40.0 fl oz")
            self.assertEqual(node(page, "band-name"), "3/4")
            strip = block(page, "strip", 'id="preview"')
            captions = re.findall(r'class="cap">([^<]*)', strip)
            self.assertEqual(captions, ["Now"])
            srcs = strip_srcs(page)
            self.assertEqual(srcs, [f"/frame/{files[0].name}"])
            self.assertIn(files[0].name, opening(page, "frame"))
            status, kind, body = self.body(running, srcs[0])
            self.assertEqual(status, 200)
            self.assertEqual(kind, "image/jpeg")
            self.assertEqual(body, shot(0))
        finally:
            running.close()
            running.close()

    def test_nine_records_keep_the_newest_eight(self):
        folder = self.folder()
        path = folder / "tank.sqlite"
        frames = folder / "frames"
        frames.mkdir()
        (frames / "notes.txt").write_text("keep", encoding="utf-8")
        nested = frames / "nested"
        nested.mkdir()
        nested_bytes = b"\xff\xd8nested\xff\xd9"
        (nested / "inside.jpg").write_bytes(nested_bytes)
        start = at("12:00:00")
        db = ledger.connect(path)
        try:
            for index, gauge in enumerate(range(40, 31, -1)):
                when = start + timedelta(minutes=index)
                loop.record(db, frames, shot(index), tick(when, float(gauge)))
            count = db.execute("SELECT COUNT(*) FROM reading").fetchone()[0]
        finally:
            db.close()
        self.assertEqual(count, 9)
        files = jpegs(frames)
        self.assertEqual(len(files), 8)
        remaining = {item.read_bytes() for item in files}
        self.assertNotIn(shot(0), remaining)
        for index in range(1, 9):
            self.assertIn(shot(index), remaining)
        self.assertEqual((frames / "notes.txt").read_text(encoding="utf-8"), "keep")
        self.assertEqual((nested / "inside.jpg").read_bytes(), nested_bytes)
        self.assertTrue(frames.is_dir())
        page, running = self.page(path, frames)
        try:
            self.assertEqual(node(page, "ounces"), "32.0 fl oz")
            strip = block(page, "strip", 'id="preview"')
            captions = re.findall(r'class="cap">([^<]*)', strip)
            self.assertEqual(captions, list(_CAPTIONS))
            self.assertEqual(len(captions), 8)
            self.assertEqual(captions[-1], "Now")
            srcs = strip_srcs(page)
            self.assertEqual(len(srcs), 8)
            ninth = next(item.name for item in files if item.read_bytes() == shot(8))
            self.assertEqual(srcs[-1], f"/frame/{ninth}")
            self.assertIn(ninth, opening(page, "frame"))
            self.assertNotIn("notes.txt", strip)
            self.assertNotIn("inside.jpg", strip)
            status, kind, body = self.body(running, srcs[-1])
            self.assertEqual(status, 200)
            self.assertEqual(kind, "image/jpeg")
            self.assertEqual(body, shot(8))
        finally:
            running.close()
            running.close()

    def test_crash_leftover_nine_ends_at_eight(self):
        folder = self.folder()
        path = folder / "tank.sqlite"
        frames = folder / "frames"
        frames.mkdir()
        base = 1_700_000_000
        for index in range(9):
            planted = frames / f"old-{index}.jpg"
            planted.write_bytes(shot(index))
            os.utime(planted, (base + index, base + index))
        db = ledger.connect(path)
        try:
            loop.record(db, frames, shot(9), tick(at("12:00:15"), 40.0))
        finally:
            db.close()
        files = jpegs(frames)
        self.assertEqual(len(files), 8)
        remaining = {item.read_bytes() for item in files}
        self.assertNotIn(shot(0), remaining)
        self.assertNotIn(shot(1), remaining)
        self.assertIn(shot(2), remaining)
        self.assertIn(shot(9), remaining)
        page, running = self.page(path, frames)
        try:
            self.assertEqual(node(page, "ounces"), "40.0 fl oz")
            captions = re.findall(r'class="cap">([^<]*)', block(page, "strip", 'id="preview"'))
            self.assertEqual(captions[-1], "Now")
            self.assertEqual(len(captions), 8)
            srcs = strip_srcs(page)
            newest = next(item.name for item in files if item.read_bytes() == shot(9))
            self.assertEqual(srcs[-1], f"/frame/{newest}")
            status, _kind, body = self.body(running, srcs[-1])
            self.assertEqual(status, 200)
            self.assertEqual(body, shot(9))
        finally:
            running.close()
            running.close()

    def test_tied_mtime_puts_the_later_write_last(self):
        folder = self.folder()
        path = folder / "tank.sqlite"
        frames = folder / "frames"
        db = ledger.connect(path)
        try:
            loop.record(db, frames, shot(1), tick(at("12:00:00"), 40.0))
            loop.record(db, frames, shot(2), tick(at("12:01:00"), 39.0))
        finally:
            db.close()
        files = jpegs(frames)
        self.assertEqual(len(files), 2)
        stamp = 1_700_000_000
        for item in files:
            os.utime(item, (stamp, stamp))
        page, running = self.page(path, frames)
        try:
            srcs = strip_srcs(page)
            self.assertEqual(len(srcs), 2)
            captions = re.findall(r'class="cap">([^<]*)', block(page, "strip", 'id="preview"'))
            self.assertEqual(captions, ["-0:15", "Now"])
            first = frames / srcs[0].removeprefix("/frame/")
            last = frames / srcs[-1].removeprefix("/frame/")
            self.assertEqual(first.read_bytes(), shot(1))
            self.assertEqual(last.read_bytes(), shot(2))
            self.assertLess(first.name, last.name)
        finally:
            running.close()
            running.close()

    def test_an_older_write_still_leaves_eight(self):
        folder = self.folder()
        path = folder / "tank.sqlite"
        frames = folder / "frames"
        frames.mkdir()
        future = 2_000_000_000
        for index in range(8):
            planted = frames / f"later-{index}.jpg"
            planted.write_bytes(shot(index))
            os.utime(planted, (future + index, future + index))
        db = ledger.connect(path)
        try:
            loop.record(db, frames, shot(9), tick(at("12:00:15"), 40.0))
        finally:
            db.close()
        files = jpegs(frames)
        self.assertEqual(len(files), 8)
        remaining = {item.read_bytes() for item in files}
        self.assertNotIn(shot(9), remaining)
        for index in range(8):
            self.assertIn(shot(index), remaining)
        page, running = self.page(path, frames)
        try:
            self.assertEqual(node(page, "ounces"), "40.0 fl oz")
            srcs = strip_srcs(page)
            self.assertEqual(len(srcs), 8)
            self.assertNotIn(shot(9), [(frames / src.removeprefix("/frame/")).read_bytes() for src in srcs])
        finally:
            running.close()
            running.close()

    def test_empty_jpeg_does_not_tick_or_write(self):
        folder = self.folder()
        path = folder / "tank.sqlite"
        frames = folder / "frames"
        db = ledger.connect(path)
        try:
            with self.assertRaises(ValueError):
                loop.record(db, frames, b"", tick(at("12:00:15"), 40.0))
            count = db.execute("SELECT COUNT(*) FROM reading").fetchone()[0]
        finally:
            db.close()
        self.assertEqual(count, 0)
        self.assertFalse(frames.exists())
        self.assertEqual(list(folder.rglob("*.jpg")), [])
        self.assertEqual(list(folder.rglob("*.jpeg")), [])


if __name__ == "__main__":
    unittest.main()
