#!/usr/bin/env python3
"""Live board checks.

    python page/live_test.py
"""

import os
import re
import sys
import tempfile
import unittest
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "page"))
sys.path.insert(0, str(ROOT / "check"))

import ledger
import live


def at(clock, day="2026-10-12"):
    return datetime.fromisoformat(f"{day}T{clock}:00-05:00")


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


def classes(tag):
    match = re.search(r'class="([^"]*)"', tag)
    if match is None:
        return set()
    return set(match.group(1).split())


def without_scripts(page):
    return re.sub(r"<script\b[^>]*>.*?</script>", "", page, flags=re.DOTALL | re.IGNORECASE)


class LiveTests(unittest.TestCase):
    def folder(self):
        held = tempfile.TemporaryDirectory()
        self.addCleanup(held.cleanup)
        return Path(held.name)

    def database(self, folder):
        path = folder / "tank.sqlite"
        frames = folder / "frames"
        frames.mkdir()
        return path, frames

    def fill(self, path, rows):
        db = ledger.connect(path)
        try:
            for clock, gauge, person in rows:
                ledger.tick(
                    db, ledger.Tick(at(clock), gauge, person, 0, 0, 0, 0, None, None)
                )
        finally:
            db.close()

    def page(self, db, frames, path="/"):
        running = live.serve(db, frames, 0)
        try:
            self.assertNotEqual(running.port, 0)
            return self.read(running, path)
        finally:
            running.close()
            running.close()

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

    def test_booked_40_is_three_quarters_and_idle(self):
        folder = self.folder()
        path, frames = self.database(folder)
        when = datetime.fromisoformat("2026-10-12T12:00:15-05:00")
        db = ledger.connect(path)
        try:
            ledger.tick(db, ledger.Tick(when, 40.0, False, 0, 0, 0, 0, None, None))
        finally:
            db.close()
        page = self.page(path, frames)
        self.assertEqual(node(page, "band-name"), "3/4")
        self.assertEqual(node(page, "ounces"), "40.0 fl oz")
        self.assertEqual(node(page, "alarm-value"), "Off")
        self.assertEqual(node(page, "activity-value"), "Idle")
        self.assertEqual(node(page, "activity-detail"), "level still 0:00")
        self.assertEqual(node(page, "out-15"), "0")
        self.assertEqual(node(page, "out-today"), "0")
        self.assertEqual(node(page, "logged-days"), "Month \u00b7 1 day")
        self.assertIn("Monday 12 October 2026 \u00b7 12:00:15 PM", block(page, "when", "</p>"))
        prior = block(page, "prior", 'id="ticks"')
        self.assertIn("Sun 11", prior)
        self.assertIn("Sat 10", prior)
        self.assertIn("Fri 9", prior)
        self.assertEqual(prior.count("no rows"), 3)
        self.assertNotIn("120 ms", block(page, "ticks", "</ul>"))
        self.assertNotIn("Preview, not on the Pi", page)
        self.assertNotIn("data-state=", page)
        self.assertNotIn("alarm", classes(opening(page, "board")))
        self.assertEqual(node(page, "live-mark"), "Live")
        self.assertIn("hidden", opening(page, "review"))
        self.assertIn("hidden", opening(page, "stale-banner"))
        self.assertIn("hidden", opening(page, "unverified"))
        self.assertNotIn('show("open")', page)
        self.assertNotIn("const STATES", page)

    def test_booked_17_5_stays_half_and_alarm_off(self):
        folder = self.folder()
        path, frames = self.database(folder)
        self.fill(path, [("12:00", 20, False), ("12:01", 17.5, False)])
        page = self.page(path, frames)
        self.assertEqual(node(page, "band-name"), "1/2")
        self.assertEqual(node(page, "ounces"), "17.5 fl oz")
        self.assertEqual(node(page, "alarm-value"), "Off")
        self.assertNotIn("alarm", classes(opening(page, "board")))

    def test_booked_17_4_is_low_and_alarm_on(self):
        folder = self.folder()
        path, frames = self.database(folder)
        self.fill(
            path,
            [("12:00", 20, False), ("12:01", 17.5, False), ("12:02", 17.4, False)],
        )
        page = self.page(path, frames)
        self.assertEqual(node(page, "band-name"), "Low")
        self.assertEqual(node(page, "ounces"), "17.4 fl oz")
        self.assertEqual(node(page, "alarm-value"), "On")
        self.assertIn("alarm", classes(opening(page, "board")))
        self.assertIn("low", classes(opening(page, "band-name")))

    def test_fill_books_70_and_keeps_the_brew_drop(self):
        folder = self.folder()
        path, frames = self.database(folder)
        self.fill(
            path,
            [
                ("12:00", 20, False),
                ("12:01", 18, False),
                ("12:02", 16, False),
                ("12:03", None, True),
                ("12:04", None, False),
                ("12:05", 47.3, False),
            ],
        )
        page = self.page(path, frames)
        events = block(page, "events", "</ol>")
        self.assertIn(
            "Fill. Booked 70 fl oz. Model said 47.3. Coffee today $5.40.",
            events,
        )
        self.assertEqual(node(page, "ounces"), "70.0 fl oz")
        self.assertNotIn("hidden", opening(page, "model-line"))
        self.assertEqual(node(page, "model-line"), "Model 47.3 fl oz")
        self.assertEqual(node(page, "out-15"), "4")
        self.assertEqual(node(page, "out-today"), "4")
        self.assertEqual(node(page, "bill-today"), "$5.40")
        self.assertEqual(node(page, "volume-today"), "54 fl oz")

    def test_stale_banner_after_four_misses(self):
        folder = self.folder()
        path, frames = self.database(folder)
        self.fill(
            path,
            [
                ("11:58", 40, False),
                ("11:59", 37, False),
                ("12:00", 34, False),
                ("12:16", None, False),
                ("12:17", None, False),
                ("12:18", None, False),
                ("12:19", None, False),
            ],
        )
        page = self.page(path, frames)
        self.assertNotIn("hidden", opening(page, "stale-banner"))
        self.assertEqual(node(page, "stale-banner"), "Stale. 4 ticks with no level.")
        self.assertEqual(node(page, "ounces"), "34.0 fl oz")
        self.assertEqual(node(page, "out-15"), "6")
        self.assertEqual(node(page, "out-today"), "6")
        self.assertNotIn("Stale", block(page, "events", "</ol>"))

    def test_quiet_jump_holds_the_booked_ounces(self):
        folder = self.folder()
        path, frames = self.database(folder)
        self.fill(path, [("12:00", 40, False), ("12:01", 48, False)])
        page = self.page(path, frames)
        self.assertNotIn("hidden", opening(page, "unverified"))
        self.assertEqual(node(page, "unverified"), "Unverified rise. Bill unchanged.")
        self.assertEqual(node(page, "ounces"), "40.0 fl oz")

    def test_eight_frames_link_to_an_earlier_index(self):
        folder = self.folder()
        path, frames = self.database(folder)
        when = datetime.fromisoformat("2026-10-12T12:00:15-05:00")
        db = ledger.connect(path)
        try:
            ledger.tick(db, ledger.Tick(when, 40, False, 0, 0, 0, 0, None, None))
        finally:
            db.close()
        names = [f"shot-{index}.jpg" for index in range(8)]
        base = 1_700_000_000
        for index, name in enumerate(names):
            shot = frames / name
            shot.write_bytes(bytes([0xFF, 0xD8, 0xFF, 0xD9, index]))
            os.utime(shot, (base + index, base + index))
        (frames / "notes.txt").write_text("no", encoding="utf-8")
        nested = frames / "nested"
        nested.mkdir()
        (nested / "inside.jpg").write_bytes(b"\xff\xd8\xff\xd9")
        running = live.serve(path, frames, 0)
        try:
            page = self.read(running, "/")
            strip = block(page, "strip", "</footer>")
            captions = re.findall(r'class="cap">([^<]*)', strip)
            self.assertEqual(
                captions,
                ["-1:45", "-1:30", "-1:15", "-1:00", "-0:45", "-0:30", "-0:15", "Now"],
            )
            self.assertEqual(captions[-1], "Now")
            self.assertEqual(
                re.findall(r'href="([^"]*)"', strip),
                [f"/?frame={index}" for index in range(8)],
            )
            self.assertLess(strip.index("shot-0.jpg"), strip.index("shot-7.jpg"))
            self.assertNotIn("notes.txt", strip)
            self.assertNotIn("inside.jpg", strip)
            self.assertIn(
                'aria-label="Last 8 frames. The last one is the most recent."',
                opening(page, "strip"),
            )
            self.assertEqual(node(page, "live-mark"), "Live")
            self.assertNotIn("review", classes(opening(page, "board")))
            self.assertIn("hidden", opening(page, "review"))
            self.assertIn("shot-7.jpg", opening(page, "frame"))
            self.assertEqual(node(page, "ounces"), "40.0 fl oz")
            earlier = self.read(running, "/?frame=0")
            self.assertEqual(node(earlier, "live-mark"), "Earlier frame")
            self.assertNotIn("hidden", opening(earlier, "review"))
            self.assertEqual(node(earlier, "review"), "Earlier frame. The numbers stay live.")
            self.assertIn("review", classes(opening(earlier, "board")))
            self.assertEqual(node(earlier, "ounces"), "40.0 fl oz")
            self.assertIn("shot-0.jpg", opening(earlier, "frame"))
            fallback = self.read(running, "/?frame=99")
            self.assertEqual(node(fallback, "live-mark"), "Live")
            self.assertIn("hidden", opening(fallback, "review"))
            self.assertIn("shot-7.jpg", opening(fallback, "frame"))
            status, kind, body = self.body(running, "/frame/shot-0.jpg")
            self.assertEqual(status, 200)
            self.assertEqual(kind, "image/jpeg")
            self.assertEqual(body, (frames / "shot-0.jpg").read_bytes())
            status, _kind, _body = self.body(running, "/frame/notes.txt")
            self.assertEqual(status, 404)
            status, _kind, _body = self.body(running, "/frame/%2e%2e%2fshot-0.jpg")
            self.assertEqual(status, 404)
            status, _kind, _body = self.body(running, "/frame/shot-0.jpg%2fextra")
            self.assertEqual(status, 404)
        finally:
            running.close()
            running.close()

    def test_empty_database_leaves_the_ounces_blank(self):
        folder = self.folder()
        path, frames = self.database(folder)
        db = ledger.connect(path)
        db.close()
        page = self.page(path, frames)
        self.assertEqual(node(page, "ounces"), "")
        self.assertEqual(node(page, "band-name"), "")
        self.assertNotIn("40.0 fl oz", without_scripts(page))
        self.assertIn("<span>Over 15 s</span><b>0</b>", block(page, "ticks", "</ul>"))
        self.assertNotIn("<li", block(page, "events", "</ol>"))
        self.assertNotIn("Sun 11", block(page, "prior", 'id="ticks"'))
        self.assertNotIn("Monday", block(page, "when", "</p>"))
        self.assertNotIn("Preview, not on the Pi", page)
        self.assertNotIn("data-state=", page)
        self.assertNotIn("120 ms", block(page, "ticks", "</ul>"))

    def test_missing_file_stays_missing(self):
        folder = self.folder()
        missing = folder / "missing.sqlite"
        frames = folder / "frames"
        page = self.page(missing, frames)
        self.assertFalse(missing.exists())
        self.assertFalse(frames.exists())
        self.assertEqual(node(page, "ounces"), "")
        self.assertEqual(node(page, "band-name"), "")
        self.assertNotIn("40.0 fl oz", page)
        self.assertNotIn("Preview, not on the Pi", page)
        self.assertNotIn("data-state=", page)


if __name__ == "__main__":
    unittest.main()
