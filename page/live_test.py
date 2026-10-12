#!/usr/bin/env python3
"""Live board checks.

    python page/live_test.py
"""

import json
import os
import re
import sys
import tempfile
import unittest
import urllib.error
import urllib.request
from datetime import datetime, timedelta
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
        self.assertEqual(prior.count("No data"), 3)
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

    def test_eight_frames_link_to_an_earlier_frame_by_name(self):
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
                [f"/?frame={name}" for name in names],
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
            earlier = self.read(running, "/?frame=shot-0.jpg")
            self.assertEqual(node(earlier, "live-mark"), "Earlier frame")
            self.assertNotIn("hidden", opening(earlier, "review"))
            self.assertEqual(node(earlier, "review"), "Earlier frame. The numbers stay live.")
            self.assertIn("review", classes(opening(earlier, "board")))
            self.assertEqual(node(earlier, "ounces"), "40.0 fl oz")
            self.assertIn("shot-0.jpg", opening(earlier, "frame"))
            fallback = self.read(running, "/?frame=shot-gone.jpg")
            self.assertEqual(node(fallback, "live-mark"), "Live")
            self.assertIn("hidden", opening(fallback, "review"))
            self.assertIn("shot-7.jpg", opening(fallback, "frame"))
            status, kind, body = self.body(running, "/frame/shot-0.jpg")
            self.assertEqual(status, 200)
            self.assertEqual(kind, "image/jpeg")
            self.assertEqual(body, (frames / "shot-0.jpg").read_bytes())
            request = urllib.request.Request(
                f"http://127.0.0.1:{running.port}/frame/shot-0.jpg",
                headers={"If-Modified-Since": "Tue, 14 Nov 2023 22:13:20 GMT"},
            )
            with self.assertRaises(urllib.error.HTTPError) as cached:
                urllib.request.urlopen(request, timeout=5)
            self.assertEqual(cached.exception.code, 304)
            cached.exception.close()
            os.utime(frames / "shot-0.jpg", (base + 100, base + 100))
            with urllib.request.urlopen(request, timeout=5) as resp:
                self.assertEqual(resp.status, 200)
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

    def test_saved_boxes_draw_over_the_photo(self):
        folder = self.folder()
        path, frames = self.database(folder)
        self.fill(path, [("12:00", 40, False)])
        (frames / "00000001.jpg").write_bytes(b"\xff\xd8\xff\xd9")
        detections = {
            "width": 1280,
            "height": 720,
            "gauge_oz": 40.2,
            "boxes": [
                {"name": "Reservoir", "score": 0.93, "x0": 600, "y0": 200, "x1": 700, "y1": 500, "used": True},
                {"name": "liquid-level", "score": 0.88, "x0": 602, "y0": 330, "x1": 698, "y1": 500, "used": True},
                {"name": "person", "score": 0.71, "x0": 10, "y0": 20, "x1": 300, "y1": 700, "used": True},
                {"name": "chair", "score": 0.6, "x0": 900, "y0": 400, "x1": 1000, "y1": 600, "used": False},
                {"name": "<b>", "score": "bad", "x0": None, "used": False},
            ],
        }
        (frames / "00000001.json").write_text(json.dumps(detections), encoding="utf-8")
        page = self.page(path, frames)
        overlay = block(page, "overlay", "</svg>")
        self.assertIn('viewBox="0 0 1280 720"', overlay)
        self.assertIn("Reservoir 0.93", overlay)
        self.assertIn("Water line 0.88 \u00b7 40.2 fl oz \u00b7 57%", overlay)
        self.assertIn('class="surface" x1="602.0" x2="698.0" y1="330.0" y2="330.0"', overlay)
        self.assertIn("person 0.71", overlay)
        self.assertNotIn("chair", overlay)
        self.assertNotIn("900.0", overlay)
        self.assertNotIn("&lt;b&gt;", overlay)
        self.assertIn('aria-pressed="true"', opening(page, "boxes-toggle"))
        self.assertIn("aspect-ratio: 1280 / 720", block(page, "scene", 'id="frame"'))

    def test_a_frame_without_boxes_has_no_overlay(self):
        folder = self.folder()
        path, frames = self.database(folder)
        self.fill(path, [("12:00", 40, False)])
        (frames / "00000001.jpg").write_bytes(b"\xff\xd8\xff\xd9")
        page = self.page(path, frames)
        self.assertNotIn('id="overlay"', page)
        self.assertNotIn('id="boxes-toggle"', page)
        (frames / "00000001.json").write_text("not json", encoding="utf-8")
        page = self.page(path, frames)
        self.assertNotIn('id="overlay"', page)

    def test_board_error_file_shows_a_flag(self):
        folder = self.folder()
        path, frames = self.database(folder)
        page = self.page(path, frames)
        self.assertIn("hidden", opening(page, "board-error"))
        live.error_path(path).write_text("Tank model did not load: missing weights\n", encoding="utf-8")
        page = self.page(path, frames)
        self.assertNotIn("hidden", opening(page, "board-error"))
        self.assertEqual(node(page, "board-error"), "Tank model did not load: missing weights")

    def test_the_page_polls_and_stamps_the_tick_age(self):
        folder = self.folder()
        path, frames = self.database(folder)
        self.fill(path, [("12:00", 40, False)])
        page = self.page(path, frames)
        self.assertIn('data-tick="2026-10-12T12:00:00-05:00"', opening(page, "age"))
        self.assertTrue(node(page, "age").startswith("Updated "))
        self.assertIn("setInterval(poll, 3000)", page)
        self.assertIn('data-mark="Live"', opening(page, "live-mark"))

    def test_the_log_keeps_the_newest_fifty_lines(self):
        folder = self.folder()
        path, frames = self.database(folder)
        self.fill(path, [("12:00", 40, False)])
        db = ledger.connect(path)
        try:
            for index in range(60):
                db.execute(
                    "INSERT INTO event (ts, day, kind, message) VALUES (?, ?, 'person', ?)",
                    ("2026-10-12T11:00:00-05:00", "2026-10-12", f"Line {index}."),
                )
        finally:
            db.close()
        page = self.page(path, frames)
        events = block(page, "events", "</ol>")
        self.assertEqual(events.count("<li "), 50)
        self.assertIn('<li class="ev-person">', events)
        self.assertIn("Line 59.", events)
        self.assertNotIn("Line 9.", events)

    def test_elapsed_shows_hours(self):
        start = at("09:00")
        self.assertEqual(live._elapsed(start, start + timedelta(seconds=90)), "1:30")
        self.assertEqual(live._elapsed(start, start + timedelta(seconds=3725)), "1:02:05")

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
