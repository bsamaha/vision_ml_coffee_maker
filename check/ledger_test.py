#!/usr/bin/env python3
"""Ledger fold checks.

    python check/ledger_test.py
"""

import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import ledger


def at(clock, day="2026-10-12"):
    return datetime.fromisoformat(f"{day}T{clock}:00-05:00")


def tenths(value):
    if value is None:
        return None
    return round(value * 10)


class LedgerTests(unittest.TestCase):
    def db(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        path = Path(folder.name) / "tank.sqlite"
        db = ledger.connect(path)
        self.addCleanup(db.close)
        return folder.name, path, db

    def foreign(self, folder):
        other = ledger.connect(Path(folder) / "other.sqlite")
        self.addCleanup(other.close)
        applied = ledger.tick(other, ledger.Tick(at("12:00"), 50, False, 0, 0, 0, 0, None, None))
        self.assertEqual(tenths(applied.machine.booked_oz), 500)
        self.assertEqual(tenths(applied.machine.out_15m), 0)
        self.assertEqual(tenths(applied.machine.out_today), 0)
        self.assertFalse(applied.machine.alarm)
        self.assertEqual(applied.machine.activity, "idle")
        self.assertEqual(applied.events, ())

    def reconnect(self, path):
        db = ledger.connect(path)
        self.addCleanup(db.close)
        return db

    def row(self, db, clock, gauge, person, day="2026-10-12", **want):
        applied = ledger.tick(
            db, ledger.Tick(at(clock, day), gauge, person, 0, 0, 0, 0, None, None)
        )
        machine = applied.machine
        self.assertEqual(tenths(machine.booked_oz), want["booked"], clock)
        self.assertEqual(tenths(machine.out_15m), want["m15"], clock)
        self.assertEqual(tenths(machine.out_today), want["today"], clock)
        self.assertEqual(machine.alarm, want["alarm"], clock)
        self.assertEqual(machine.activity, want["activity"], clock)
        self.assertEqual(machine.person, person, clock)
        self.assert_events(applied, want.get("events", ()), clock)
        if "seen" in want:
            self.assertEqual(machine.seen_today, want["seen"], clock)
        if "open" in want:
            self.assertEqual(machine.person_open, want["open"], clock)
        if "out" in want:
            self.assertEqual(machine.reservoir_out, want["out"], clock)
        if "taken" in want:
            self.assertEqual(tenths(machine.taken_oz), want["taken"], clock)
        if "filled" in want:
            self.assertEqual(tenths(machine.filled_oz), want["filled"], clock)
        if "refills" in want:
            self.assertEqual(machine.refills_today, want["refills"], clock)
        if "month" in want:
            self.assertEqual(round(machine.coffee_month * 100), want["month"], clock)
        if any(key in want for key in ("gap", "gperson", "pending", "pcount")):
            got = db.execute(
                "SELECT gap_ticks, gap_person, pending_oz, pending_count FROM machine WHERE id = 1"
            ).fetchone()
            if "gap" in want:
                self.assertEqual(got["gap_ticks"], want["gap"], clock)
            if "gperson" in want:
                self.assertEqual(got["gap_person"], want["gperson"], clock)
            if "pending" in want:
                self.assertEqual(tenths(got["pending_oz"]), want["pending"], clock)
            if "pcount" in want:
                self.assertEqual(got["pending_count"], want["pcount"], clock)
        if "rgauge" in want or "rbooked" in want or "stored_day" in want:
            reading = db.execute(
                "SELECT gauge_oz, booked_oz, day FROM reading ORDER BY id DESC LIMIT 1"
            ).fetchone()
            if "rgauge" in want:
                self.assertEqual(tenths(reading["gauge_oz"]), want["rgauge"], clock)
            if "rbooked" in want:
                self.assertEqual(tenths(reading["booked_oz"]), want["rbooked"], clock)
            if "stored_day" in want:
                self.assertEqual(reading["day"], want["stored_day"], clock)
        return applied

    def assert_events(self, applied, expected, clock):
        self.assertEqual(len(applied.events), len(expected), clock)
        for got, exp in zip(applied.events, expected):
            kind, message, model, ounces, delta = exp
            self.assertEqual(got.kind, kind, clock)
            self.assertEqual(got.message, message, clock)
            self.assertEqual(tenths(got.model_oz), model, clock)
            self.assertEqual(tenths(got.ounces), ounces, clock)
            self.assertEqual(tenths(got.delta_oz), delta, clock)

    def take(self, db, saved=400):
        self.row(db, "12:00", saved / 10, False, booked=saved, m15=0, today=0, alarm=False, activity="idle")
        self.row(
            db,
            "12:01",
            None,
            True,
            booked=saved,
            m15=0,
            today=0,
            alarm=False,
            activity="idle",
            seen=1,
            gap=1,
            gperson=1,
            events=(("person", "Person seen.", None, saved, None),),
        )
        self.row(
            db,
            "12:02",
            None,
            False,
            booked=saved,
            m15=0,
            today=0,
            alarm=False,
            activity="out",
            taken=saved,
            out=True,
            gap=0,
            events=(("taken", f"Reservoir taken. Saved {saved // 10} fl oz.", None, saved, None),),
        )

    def test_connect_sets_the_file_up_once(self):
        _folder, path, db = self.db()
        self.assertIsNone(db.isolation_level)
        self.assertEqual(db.execute("PRAGMA foreign_keys").fetchone()[0], 1)
        self.assertEqual(db.execute("PRAGMA journal_mode").fetchone()[0], "wal")
        again = ledger.connect(path)
        self.addCleanup(again.close)
        self.assertEqual(
            again.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'reading'"
            ).fetchone()[0],
            "reading",
        )

    def test_connect_drops_the_indexes_nothing_reads(self):
        _folder, path, db = self.db()
        db.execute("CREATE INDEX reading_ts ON reading (ts)")
        db.execute("CREATE INDEX event_id_desc ON event (id DESC)")
        again = self.reconnect(path)
        names = {row[0] for row in again.execute("SELECT name FROM sqlite_master WHERE type = 'index'")}
        self.assertEqual(names, {"reading_day"})

    def test_connect_adds_the_device_columns_to_an_older_file(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        path = Path(folder.name) / "tank.sqlite"
        old = ledger.connect(path)
        old.execute("ALTER TABLE reading DROP COLUMN cpu_pct")
        old.execute("ALTER TABLE reading DROP COLUMN mem_free_pct")
        old.close()
        db = self.reconnect(path)
        columns = {row["name"] for row in db.execute("PRAGMA table_info(reading)")}
        self.assertLessEqual({"cpu_pct", "mem_free_pct"}, columns)
        ledger.tick(db, ledger.Tick(at("12:00"), 40, False, 0, 0, 0, 0, None, None, 30.0, 60.0))
        row = db.execute("SELECT cpu_pct, mem_free_pct FROM reading").fetchone()
        self.assertEqual(tuple(row), (30.0, 60.0))

    def test_total_ms_adds_the_fold_time(self):
        _folder, _path, db = self.db()
        ledger.tick(db, ledger.Tick(at("12:00"), 40, False, 3, 4, 5, 6, 12, 21.5))
        row = db.execute(
            """
            SELECT capture_ms, tank_ms, person_ms, gauge_ms, ledger_ms, total_ms,
                   rss_mb, temp_c, day
            FROM reading
            """
        ).fetchone()
        self.assertEqual(row["capture_ms"], 3)
        self.assertEqual(row["tank_ms"], 4)
        self.assertEqual(row["person_ms"], 5)
        self.assertEqual(row["gauge_ms"], 6)
        self.assertGreaterEqual(row["ledger_ms"], 0)
        self.assertEqual(row["total_ms"], 3 + 4 + 5 + 6 + row["ledger_ms"])
        self.assertEqual(row["rss_mb"], 12)
        self.assertEqual(row["temp_c"], 21.5)
        self.assertEqual(row["day"], "2026-10-12")
        self.assertEqual(db.execute("SELECT count(*) FROM machine").fetchone()[0], 1)

    def test_rejects_a_naive_datetime(self):
        _folder, _path, db = self.db()
        naive = datetime.fromisoformat("2026-10-12T12:00:00")
        with self.assertRaises(ValueError):
            ledger.tick(db, ledger.Tick(naive, 40, False, 0, 0, 0, 0, None, None))
        self.assertEqual(db.execute("SELECT count(*) FROM reading").fetchone()[0], 0)

    def test_rejects_a_non_finite_gauge(self):
        _folder, _path, db = self.db()
        for gauge in (float("nan"), float("inf"), float("-inf")):
            with self.assertRaises(ValueError):
                ledger.tick(db, ledger.Tick(at("12:00"), gauge, False, 0, 0, 0, 0, None, None))
        self.assertEqual(db.execute("SELECT count(*) FROM reading").fetchone()[0], 0)

    def test_rejects_a_person_that_is_not_a_bool(self):
        _folder, _path, db = self.db()
        with self.assertRaises(ValueError):
            ledger.tick(db, ledger.Tick(at("12:00"), 40, 1, 0, 0, 0, 0, None, None))
        self.assertEqual(db.execute("SELECT count(*) FROM reading").fetchone()[0], 0)

    def test_rejects_a_negative_duration(self):
        _folder, _path, db = self.db()
        with self.assertRaises(ValueError):
            ledger.tick(db, ledger.Tick(at("12:00"), 40, False, -1, 0, 0, 0, None, None))
        self.assertEqual(db.execute("SELECT count(*) FROM reading").fetchone()[0], 0)

    def test_seated_person_bills_the_next_line(self):
        _folder, _path, db = self.db()
        self.row(
            db, "12:00", 40, False, booked=400, m15=0, today=0, alarm=False, activity="idle", seen=0
        )
        self.row(
            db,
            "12:01",
            38,
            True,
            booked=400,
            m15=0,
            today=0,
            alarm=False,
            activity="idle",
            seen=1,
            open=True,
            events=(("person", "Person seen. Reservoir stayed.", 380, 400, None),),
        )
        self.row(
            db,
            "12:02",
            38,
            False,
            booked=380,
            m15=20,
            today=20,
            alarm=False,
            activity="idle",
            open=True,
            seen=1,
        )
        self.row(
            db,
            "12:03",
            38,
            False,
            booked=380,
            m15=20,
            today=20,
            alarm=False,
            activity="idle",
            open=False,
            seen=1,
        )

    def test_person_does_not_create_a_baseline(self):
        _folder, _path, db = self.db()
        self.row(
            db,
            "12:00",
            40,
            True,
            booked=None,
            m15=0,
            today=0,
            alarm=False,
            activity="idle",
            events=(("person", "Person seen. Reservoir stayed.", 400, None, None),),
        )
        self.row(db, "12:01", 38, False, booked=380, m15=0, today=0, alarm=False, activity="idle")

    def test_seen_today_does_not_increment_while_the_latch_stays_open(self):
        _folder, _path, db = self.db()
        self.row(db, "12:00", 40, False, booked=400, m15=0, today=0, alarm=False, activity="idle")
        self.row(
            db,
            "12:01",
            40,
            True,
            booked=400,
            m15=0,
            today=0,
            alarm=False,
            activity="idle",
            seen=1,
            open=True,
            events=(("person", "Person seen. Reservoir stayed.", 400, 400, None),),
        )
        self.row(
            db,
            "12:02",
            40,
            True,
            booked=400,
            m15=0,
            today=0,
            alarm=False,
            activity="idle",
            seen=1,
            open=True,
        )

    def test_take_confirms_on_the_second_miss(self):
        _folder, _path, db = self.db()
        self.row(db, "12:00", 40, False, booked=400, m15=0, today=0, alarm=False, activity="idle")
        self.row(
            db,
            "12:01",
            None,
            True,
            booked=400,
            m15=0,
            today=0,
            alarm=False,
            activity="idle",
            seen=1,
            gap=1,
            gperson=1,
            events=(("person", "Person seen.", None, 400, None),),
        )
        self.row(
            db,
            "12:02",
            None,
            False,
            booked=400,
            m15=0,
            today=0,
            alarm=False,
            activity="out",
            taken=400,
            out=True,
            gap=0,
            events=(("taken", "Reservoir taken. Saved 40 fl oz.", None, 400, None),),
        )

    def test_a_single_miss_that_comes_back_changes_nothing(self):
        _folder, _path, db = self.db()
        self.row(db, "12:00", 40, False, booked=400, m15=0, today=0, alarm=False, activity="idle")
        self.row(
            db,
            "12:01",
            None,
            False,
            booked=400,
            m15=0,
            today=0,
            alarm=False,
            activity="idle",
            gap=1,
            gperson=0,
            out=False,
        )
        self.row(
            db,
            "12:02",
            40,
            False,
            booked=400,
            m15=0,
            today=0,
            alarm=False,
            activity="idle",
            gap=0,
            out=False,
        )

    def test_a_person_on_the_fourth_miss_confirms_the_take(self):
        _folder, _path, db = self.db()
        self.row(db, "12:00", 40, False, booked=400, m15=0, today=0, alarm=False, activity="idle")
        self.row(
            db, "12:01", None, False, booked=400, m15=0, today=0, alarm=False, activity="idle", gap=1, gperson=0
        )
        self.row(
            db, "12:02", None, False, booked=400, m15=0, today=0, alarm=False, activity="idle", gap=2, gperson=0
        )
        self.row(
            db, "12:03", None, False, booked=400, m15=0, today=0, alarm=False, activity="idle", gap=3, gperson=0
        )
        self.row(
            db,
            "12:04",
            None,
            True,
            booked=400,
            m15=0,
            today=0,
            alarm=False,
            activity="out",
            taken=400,
            gap=0,
            seen=1,
            events=(
                ("person", "Person seen.", None, 400, None),
                ("taken", "Reservoir taken. Saved 40 fl oz.", None, 400, None),
            ),
        )

    def test_return_books_70_and_restart_keeps_the_fill_scale(self):
        folder, path, db = self.db()
        self.row(db, "12:00", 20, False, booked=200, m15=0, today=0, alarm=False, activity="idle")
        self.row(db, "12:01", 18, False, booked=180, m15=20, today=20, alarm=False, activity="idle")
        self.row(
            db,
            "12:02",
            16,
            False,
            booked=160,
            m15=40,
            today=40,
            alarm=True,
            activity="brewing",
            events=(
                ("brewing", "Brewing. Level falling from 20 fl oz.", 160, 160, None),
                ("alarm_on", "Alarm on. Level 16 fl oz. Still brewing.", 160, 160, None),
            ),
        )
        self.row(
            db,
            "12:03",
            None,
            True,
            booked=160,
            m15=40,
            today=40,
            alarm=True,
            activity="brewing",
            seen=1,
            gap=1,
            events=(("person", "Person seen.", None, 160, None),),
        )
        self.row(
            db,
            "12:04",
            None,
            False,
            booked=160,
            m15=40,
            today=40,
            alarm=True,
            activity="out",
            taken=160,
            out=True,
            events=(("taken", "Reservoir taken. Saved 16 fl oz.", None, 160, None),),
        )
        self.row(
            db,
            "12:05",
            47.3,
            False,
            booked=700,
            m15=40,
            today=40,
            alarm=False,
            activity="idle",
            filled=540,
            refills=1,
            month=16200,
            rgauge=473,
            rbooked=700,
            events=(
                ("alarm_off", "Alarm off. Level 70 fl oz.", 473, 700, None),
                (
                    "fill",
                    "Fill. Booked 70 fl oz. Model said 47.3. Coffee today $5.40.",
                    473,
                    700,
                    540,
                ),
            ),
        )
        self.foreign(folder)
        db = self.reconnect(path)
        # 45.3 of the 47.3 the fill read is 67.0 of 70.
        self.row(
            db,
            "12:06",
            45.3,
            False,
            booked=670,
            m15=70,
            today=70,
            alarm=False,
            activity="idle",
            filled=540,
            month=16200,
        )

    def test_accepted_jump_after_a_fill_stays_at_70(self):
        _folder, _path, db = self.db()
        self.row(db, "12:00", 20, False, booked=200, m15=0, today=0, alarm=False, activity="idle")
        self.row(db, "12:01", 18, False, booked=180, m15=20, today=20, alarm=False, activity="idle")
        self.row(
            db,
            "12:02",
            16,
            False,
            booked=160,
            m15=40,
            today=40,
            alarm=True,
            activity="brewing",
            events=(
                ("brewing", "Brewing. Level falling from 20 fl oz.", 160, 160, None),
                ("alarm_on", "Alarm on. Level 16 fl oz. Still brewing.", 160, 160, None),
            ),
        )
        self.row(
            db,
            "12:03",
            None,
            True,
            booked=160,
            m15=40,
            today=40,
            alarm=True,
            activity="brewing",
            seen=1,
            gap=1,
            events=(("person", "Person seen.", None, 160, None),),
        )
        self.row(
            db,
            "12:04",
            None,
            False,
            booked=160,
            m15=40,
            today=40,
            alarm=True,
            activity="out",
            taken=160,
            events=(("taken", "Reservoir taken. Saved 16 fl oz.", None, 160, None),),
        )
        self.row(
            db,
            "12:05",
            47.3,
            False,
            booked=700,
            m15=40,
            today=40,
            alarm=False,
            activity="idle",
            filled=540,
            refills=1,
            month=16200,
            events=(
                ("alarm_off", "Alarm off. Level 70 fl oz.", 473, 700, None),
                (
                    "fill",
                    "Fill. Booked 70 fl oz. Model said 47.3. Coffee today $5.40.",
                    473,
                    700,
                    540,
                ),
            ),
        )
        self.row(
            db,
            "12:06",
            60,
            False,
            booked=700,
            m15=40,
            today=40,
            alarm=False,
            activity="idle",
            pending=600,
            pcount=1,
        )
        self.row(
            db,
            "12:07",
            60.4,
            False,
            booked=700,
            m15=40,
            today=40,
            alarm=False,
            activity="idle",
            pcount=2,
        )
        self.row(
            db,
            "12:08",
            59.6,
            False,
            booked=700,
            m15=40,
            today=40,
            alarm=False,
            activity="idle",
            pcount=0,
        )

    def test_dump_books_the_model_gauge(self):
        _folder, _path, db = self.db()
        self.take(db)
        self.row(
            db,
            "12:03",
            30,
            False,
            booked=300,
            m15=100,
            today=100,
            alarm=False,
            activity="idle",
            events=(("dump", "Dump. Level 30 fl oz.", 300, 300, None),),
        )

    def test_box_back_while_a_person_remains_stays_out(self):
        _folder, _path, db = self.db()
        self.take(db)
        self.row(
            db,
            "12:03",
            30,
            True,
            booked=400,
            m15=0,
            today=0,
            alarm=False,
            activity="out",
            out=True,
            seen=1,
        )
        self.row(
            db,
            "12:04",
            30,
            False,
            booked=300,
            m15=100,
            today=100,
            alarm=False,
            activity="idle",
            events=(("dump", "Dump. Level 30 fl oz.", 300, 300, None),),
        )

    def test_return_with_no_line_keeps_the_saved_ounces(self):
        _folder, _path, db = self.db()
        self.take(db)
        self.row(
            db,
            "12:03",
            0,
            False,
            booked=400,
            m15=0,
            today=0,
            alarm=False,
            activity="out",
            out=True,
            gap=0,
        )

    def test_put_back_down_and_up(self):
        _folder, _path, db = self.db()
        self.take(db)
        self.row(
            db,
            "12:03",
            38,
            False,
            booked=380,
            m15=20,
            today=20,
            alarm=False,
            activity="idle",
            events=(("put_back", "Put back. Level 38 fl oz.", 380, 380, None),),
        )
        _folder, _path, fresh = self.db()
        self.take(fresh)
        self.row(
            fresh,
            "12:03",
            41,
            False,
            booked=410,
            m15=0,
            today=0,
            alarm=False,
            activity="idle",
            events=(("put_back", "Put back. Level 41 fl oz.", 410, 410, None),),
        )

    def test_fill_and_dump_edges_at_3_5(self):
        _folder, _path, fill = self.db()
        self.take(fill)
        self.row(
            fill,
            "12:03",
            43.5,
            False,
            booked=700,
            m15=0,
            today=0,
            alarm=False,
            activity="idle",
            filled=300,
            refills=1,
            month=9000,
            events=(
                (
                    "fill",
                    "Fill. Booked 70 fl oz. Model said 43.5. Coffee today $3.00.",
                    435,
                    700,
                    300,
                ),
            ),
        )
        _folder, _path, dump = self.db()
        self.take(dump)
        self.row(
            dump,
            "12:03",
            36.5,
            False,
            booked=365,
            m15=35,
            today=35,
            alarm=False,
            activity="idle",
            events=(("dump", "Dump. Level 36.5 fl oz.", 365, 365, None),),
        )
        _folder, _path, up = self.db()
        self.take(up)
        self.row(
            up,
            "12:03",
            43.4,
            False,
            booked=434,
            m15=0,
            today=0,
            alarm=False,
            activity="idle",
            events=(("put_back", "Put back. Level 43.4 fl oz.", 434, 434, None),),
        )
        _folder, _path, down = self.db()
        self.take(down)
        self.row(
            down,
            "12:03",
            36.6,
            False,
            booked=366,
            m15=34,
            today=34,
            alarm=False,
            activity="idle",
            events=(("put_back", "Put back. Level 36.6 fl oz.", 366, 366, None),),
        )

    def test_quiet_jump_accepts_the_candidate(self):
        _folder, _path, db = self.db()
        self.row(db, "12:00", 40, False, booked=400, m15=0, today=0, alarm=False, activity="idle")
        self.row(
            db,
            "12:01",
            48,
            False,
            booked=400,
            m15=0,
            today=0,
            alarm=False,
            activity="idle",
            pending=480,
            pcount=1,
        )
        self.row(
            db,
            "12:02",
            48.4,
            False,
            booked=400,
            m15=0,
            today=0,
            alarm=False,
            activity="idle",
            pending=480,
            pcount=2,
        )
        self.row(
            db,
            "12:03",
            47.6,
            False,
            booked=480,
            m15=0,
            today=0,
            alarm=False,
            activity="idle",
            pcount=0,
            rgauge=476,
            rbooked=480,
        )
        self.row(db, "12:04", 46, False, booked=460, m15=20, today=20, alarm=False, activity="idle")

    def test_quiet_jump_restart_uses_the_candidate(self):
        folder, path, db = self.db()
        self.row(db, "12:00", 40, False, booked=400, m15=0, today=0, alarm=False, activity="idle")
        self.row(db, "12:01", 48, False, booked=400, m15=0, today=0, alarm=False, activity="idle", pcount=1)
        self.row(db, "12:02", 48.4, False, booked=400, m15=0, today=0, alarm=False, activity="idle", pcount=2)
        self.row(db, "12:03", 47.6, False, booked=480, m15=0, today=0, alarm=False, activity="idle", pcount=0)
        self.foreign(folder)
        db = self.reconnect(path)
        self.row(db, "12:04", 46, False, booked=460, m15=20, today=20, alarm=False, activity="idle")

    def test_within_one_ounce_includes_one(self):
        _folder, _path, db = self.db()
        self.row(db, "12:00", 40, False, booked=400, m15=0, today=0, alarm=False, activity="idle")
        self.row(db, "12:01", 48, False, booked=400, m15=0, today=0, alarm=False, activity="idle", pcount=1)
        self.row(db, "12:02", 49, False, booked=400, m15=0, today=0, alarm=False, activity="idle", pcount=2)
        self.row(
            db,
            "12:03",
            47,
            False,
            booked=480,
            m15=0,
            today=0,
            alarm=False,
            activity="idle",
            rgauge=470,
            rbooked=480,
        )

    def test_a_step_past_one_ounce_cancels_the_hold(self):
        _folder, _path, db = self.db()
        self.row(db, "12:00", 40, False, booked=400, m15=0, today=0, alarm=False, activity="idle")
        self.row(db, "12:01", 48, False, booked=400, m15=0, today=0, alarm=False, activity="idle", pcount=1)
        self.row(
            db,
            "12:02",
            49.1,
            False,
            booked=491,
            m15=0,
            today=0,
            alarm=False,
            activity="idle",
            pcount=0,
        )

    def test_quiet_jump_uses_the_line_a_person_stored(self):
        _folder, _path, db = self.db()
        self.row(db, "12:00", 40, False, booked=400, m15=0, today=0, alarm=False, activity="idle")
        self.row(
            db,
            "12:01",
            38,
            True,
            booked=400,
            m15=0,
            today=0,
            alarm=False,
            activity="idle",
            seen=1,
            events=(("person", "Person seen. Reservoir stayed.", 380, 400, None),),
        )
        self.row(
            db,
            "12:02",
            44,
            False,
            booked=400,
            m15=0,
            today=0,
            alarm=False,
            activity="idle",
            pending=440,
            pcount=1,
        )

    def test_a_seated_person_clears_a_hold(self):
        _folder, _path, db = self.db()
        self.row(db, "12:00", 40, False, booked=400, m15=0, today=0, alarm=False, activity="idle")
        self.row(db, "12:01", 48, False, booked=400, m15=0, today=0, alarm=False, activity="idle", pcount=1)
        self.row(
            db,
            "12:02",
            48,
            True,
            booked=400,
            m15=0,
            today=0,
            alarm=False,
            activity="idle",
            pcount=0,
            seen=1,
            events=(("person", "Person seen. Reservoir stayed.", 480, 400, None),),
        )
        self.row(
            db,
            "12:03",
            48,
            False,
            booked=480,
            m15=0,
            today=0,
            alarm=False,
            activity="idle",
            open=True,
        )

    def test_an_accepted_rise_while_brewing_becomes_idle(self):
        _folder, _path, db = self.db()
        self.row(db, "12:00", 20, False, booked=200, m15=0, today=0, alarm=False, activity="idle")
        self.row(db, "12:01", 18, False, booked=180, m15=20, today=20, alarm=False, activity="idle")
        self.row(
            db,
            "12:02",
            16,
            False,
            booked=160,
            m15=40,
            today=40,
            alarm=True,
            activity="brewing",
            events=(
                ("brewing", "Brewing. Level falling from 20 fl oz.", 160, 160, None),
                ("alarm_on", "Alarm on. Level 16 fl oz. Still brewing.", 160, 160, None),
            ),
        )
        self.row(db, "12:03", 30, False, booked=160, m15=40, today=40, alarm=True, activity="brewing")
        self.row(db, "12:04", 30.4, False, booked=160, m15=40, today=40, alarm=True, activity="brewing")
        self.row(
            db,
            "12:05",
            29.6,
            False,
            booked=300,
            m15=40,
            today=40,
            alarm=False,
            activity="idle",
            events=(
                ("alarm_off", "Alarm off. Level 30 fl oz.", 296, 300, None),
                (
                    "idle",
                    "Level 30 fl oz. No person. Bill stayed $0.00.",
                    296,
                    300,
                    None,
                ),
            ),
        )

    def test_two_brew_samples_start_brewing(self):
        _folder, _path, db = self.db()
        self.row(db, "12:00", 40, False, booked=400, m15=0, today=0, alarm=False, activity="idle")
        self.row(db, "12:01", 38.5, False, booked=385, m15=15, today=15, alarm=False, activity="idle")
        self.row(
            db,
            "12:02",
            37,
            False,
            booked=370,
            m15=30,
            today=30,
            alarm=False,
            activity="brewing",
            events=(("brewing", "Brewing. Level falling from 40 fl oz.", 370, 370, None),),
        )

    def test_a_half_ounce_fall_does_not_extend_the_pair(self):
        _folder, _path, db = self.db()
        self.row(db, "12:00", 40, False, booked=400, m15=0, today=0, alarm=False, activity="idle")
        self.row(db, "12:01", 39, False, booked=390, m15=10, today=10, alarm=False, activity="idle")
        self.row(db, "12:02", 38.5, False, booked=385, m15=15, today=15, alarm=False, activity="idle")

    def test_a_five_ounce_fall_is_a_brew_sample(self):
        _folder, _path, db = self.db()
        self.row(db, "12:00", 40, False, booked=400, m15=0, today=0, alarm=False, activity="idle")
        self.row(db, "12:01", 35, False, booked=350, m15=50, today=50, alarm=False, activity="idle")
        self.row(
            db,
            "12:02",
            30,
            False,
            booked=300,
            m15=100,
            today=100,
            alarm=False,
            activity="brewing",
            events=(("brewing", "Brewing. Level falling from 40 fl oz.", 300, 300, None),),
        )

    def test_a_five_ounce_rise_is_not_a_hold(self):
        _folder, _path, db = self.db()
        self.row(db, "12:00", 40, False, booked=400, m15=0, today=0, alarm=False, activity="idle")
        self.row(
            db,
            "12:01",
            45,
            False,
            booked=450,
            m15=0,
            today=0,
            alarm=False,
            activity="idle",
            pcount=0,
        )

    def test_alarm_starts_under_17_5(self):
        _folder, _path, db = self.db()
        self.row(db, "12:00", 20, False, booked=200, m15=0, today=0, alarm=False, activity="idle")
        self.row(db, "12:01", 17.5, False, booked=175, m15=25, today=25, alarm=False, activity="idle")
        self.row(
            db,
            "12:02",
            17.4,
            False,
            booked=174,
            m15=26,
            today=26,
            alarm=True,
            activity="idle",
            events=(("alarm_on", "Alarm on. Level 17.4 fl oz.", 174, 174, None),),
        )

    def test_totals_at_zero_are_not_the_alarm(self):
        _folder, _path, full = self.db()
        self.row(full, "12:00", 40, False, booked=400, m15=0, today=0, alarm=False, activity="idle")
        _folder, _path, low = self.db()
        self.row(
            low,
            "12:00",
            10,
            False,
            booked=100,
            m15=0,
            today=0,
            alarm=True,
            activity="idle",
            events=(("alarm_on", "Alarm on. Level 10 fl oz.", 100, 100, None),),
        )

    def test_stale_gap_publishes_the_seated_snapshot(self):
        _folder, _path, db = self.db()
        self.row(db, "11:58", 40, False, booked=400, m15=0, today=0, alarm=False, activity="idle")
        self.row(db, "11:59", 37, False, booked=370, m15=30, today=30, alarm=False, activity="idle")
        self.row(
            db,
            "12:00",
            34,
            False,
            booked=340,
            m15=60,
            today=60,
            alarm=False,
            activity="brewing",
            events=(("brewing", "Brewing. Level falling from 40 fl oz.", 340, 340, None),),
        )
        self.row(
            db,
            "12:16",
            None,
            False,
            booked=340,
            m15=0,
            today=60,
            alarm=False,
            activity="brewing",
            gap=1,
            gperson=0,
        )
        self.row(
            db,
            "12:17",
            None,
            False,
            booked=340,
            m15=0,
            today=60,
            alarm=False,
            activity="brewing",
            gap=2,
        )
        self.row(
            db,
            "12:18",
            None,
            False,
            booked=340,
            m15=0,
            today=60,
            alarm=False,
            activity="brewing",
            gap=3,
        )
        self.row(
            db,
            "12:19",
            None,
            False,
            booked=340,
            m15=60,
            today=60,
            alarm=False,
            activity="brewing",
            gap=4,
            gperson=0,
        )
        self.row(
            db,
            "12:20",
            None,
            False,
            booked=340,
            m15=60,
            today=60,
            alarm=False,
            activity="brewing",
            gap=5,
        )
        self.row(
            db,
            "12:21",
            34,
            False,
            booked=340,
            m15=0,
            today=60,
            alarm=False,
            activity="idle",
            gap=0,
            events=(("idle", "Level 34 fl oz. No person. Bill stayed $0.00.", 340, 340, None),),
        )

    def test_fifteen_minute_window_drops_the_12_01_step_at_12_17(self):
        _folder, _path, db = self.db()
        self.row(db, "12:00", 40, False, booked=400, m15=0, today=0, alarm=False, activity="idle")
        self.row(db, "12:01", 38, False, booked=380, m15=20, today=20, alarm=False, activity="idle")
        self.row(db, "12:02", 40, False, booked=400, m15=20, today=20, alarm=False, activity="idle")
        self.row(db, "12:03", 37, False, booked=370, m15=50, today=50, alarm=False, activity="idle")
        self.row(
            db,
            "12:04",
            None,
            True,
            booked=370,
            m15=50,
            today=50,
            alarm=False,
            activity="idle",
            seen=1,
            events=(("person", "Person seen.", None, 370, None),),
        )
        self.row(
            db,
            "12:05",
            None,
            False,
            booked=370,
            m15=50,
            today=50,
            alarm=False,
            activity="out",
            taken=370,
            events=(("taken", "Reservoir taken. Saved 37 fl oz.", None, 370, None),),
        )
        self.row(
            db,
            "12:06",
            47.3,
            False,
            booked=700,
            m15=50,
            today=50,
            alarm=False,
            activity="idle",
            filled=330,
            refills=1,
            month=9900,
            events=(
                (
                    "fill",
                    "Fill. Booked 70 fl oz. Model said 47.3. Coffee today $3.30.",
                    473,
                    700,
                    330,
                ),
            ),
        )
        self.row(db, "12:16", 47.3, False, booked=700, m15=50, today=50, alarm=False, activity="idle")
        self.row(db, "12:17", 47.3, False, booked=700, m15=30, today=50, alarm=False, activity="idle")

    def test_midnight_resets_today_and_keeps_the_fifteen_minute_window(self):
        _folder, _path, db = self.db()
        self.row(
            db,
            "23:50",
            44,
            False,
            day="2026-10-11",
            booked=440,
            m15=0,
            today=0,
            alarm=False,
            activity="idle",
            stored_day="2026-10-11",
        )
        self.row(
            db,
            "23:51",
            40,
            False,
            day="2026-10-11",
            booked=400,
            m15=40,
            today=40,
            alarm=False,
            activity="idle",
        )
        self.row(
            db,
            "23:59",
            40,
            True,
            day="2026-10-11",
            booked=400,
            m15=40,
            today=40,
            alarm=False,
            activity="idle",
            seen=1,
            open=True,
            events=(("person", "Person seen. Reservoir stayed.", 400, 400, None),),
        )
        self.row(
            db,
            "00:00",
            40,
            True,
            day="2026-10-12",
            booked=400,
            m15=40,
            today=0,
            alarm=False,
            activity="idle",
            seen=0,
            open=True,
            filled=0,
            refills=0,
            month=0,
        )
        self.row(
            db,
            "00:01",
            36,
            False,
            day="2026-10-12",
            booked=360,
            m15=80,
            today=40,
            alarm=False,
            activity="brewing",
            open=True,
            seen=0,
            events=(("brewing", "Brewing. Level falling from 44 fl oz.", 360, 360, None),),
        )

    def test_a_miss_does_not_clear_the_previous_line(self):
        _folder, _path, db = self.db()
        self.row(db, "12:00", 40, False, booked=400, m15=0, today=0, alarm=False, activity="idle")
        self.row(db, "12:01", None, False, booked=400, m15=0, today=0, alarm=False, activity="idle", gap=1)
        self.row(
            db,
            "12:02",
            46,
            False,
            booked=400,
            m15=0,
            today=0,
            alarm=False,
            activity="idle",
            pending=460,
            pcount=1,
        )

    def test_a_bottom_flicker_stays_empty_after_zero(self):
        _folder, _path, db = self.db()
        self.row(
            db,
            "12:00",
            3.5,
            False,
            booked=35,
            m15=0,
            today=0,
            alarm=True,
            activity="idle",
            events=(("alarm_on", "Alarm on. Level 3.5 fl oz.", 35, 35, None),),
        )
        self.row(db, "12:01", 0, False, booked=0, m15=0, today=0, alarm=True, activity="idle")
        self.row(db, "12:02", 3.4, False, booked=0, m15=0, today=0, alarm=True, activity="idle")
        self.row(db, "12:03", 2.9, False, booked=0, m15=0, today=0, alarm=True, activity="idle")
        self.row(db, "12:04", 0, False, booked=0, m15=0, today=0, alarm=True, activity="idle")
        self.row(db, "12:05", 8, False, booked=80, m15=0, today=0, alarm=True, activity="idle")

    def test_an_empty_return_at_3_fl_oz_does_not_fill(self):
        _folder, _path, db = self.db()
        self.row(
            db,
            "12:00",
            0,
            False,
            booked=0,
            m15=0,
            today=0,
            alarm=True,
            activity="idle",
            events=(("alarm_on", "Alarm on. Level 0 fl oz.", 0, 0, None),),
        )
        self.row(
            db,
            "12:01",
            None,
            True,
            booked=0,
            m15=0,
            today=0,
            alarm=True,
            activity="idle",
            seen=1,
            gap=1,
            gperson=1,
            events=(("person", "Person seen.", None, 0, None),),
        )
        self.row(
            db,
            "12:02",
            None,
            False,
            booked=0,
            m15=0,
            today=0,
            alarm=True,
            activity="out",
            taken=0,
            out=True,
            gap=0,
            events=(("taken", "Reservoir taken. Saved 0 fl oz.", None, 0, None),),
        )
        self.row(
            db,
            "12:03",
            3.5,
            False,
            booked=0,
            m15=0,
            today=0,
            alarm=True,
            activity="out",
            out=True,
            taken=0,
        )

    def test_a_gauge_of_zero_does_not_clear_the_previous_line(self):
        _folder, _path, db = self.db()
        self.row(db, "12:00", 40, False, booked=400, m15=0, today=0, alarm=False, activity="idle")
        self.row(db, "12:01", 0, False, booked=400, m15=0, today=0, alarm=False, activity="idle", gap=0)
        self.row(
            db,
            "12:02",
            46,
            False,
            booked=400,
            m15=0,
            today=0,
            alarm=False,
            activity="idle",
            pending=460,
            pcount=1,
        )

    def ticks(self, db, start, gauges, person=False, day="2026-10-12"):
        when = at(start, day)
        applied = None
        for gauge in gauges:
            applied = ledger.tick(db, ledger.Tick(when, gauge, person, 0, 0, 0, 0, None, None))
            when += timedelta(seconds=10)
        return applied.machine

    def test_a_wobbling_still_tank_is_not_ounces_out(self):
        _folder, _path, db = self.db()
        wobble = (40.0, 39.7, 40.3, 39.8, 40.2, 39.7, 40.1, 39.9, 40.3, 39.7) * 9
        machine = self.ticks(db, "12:00", wobble)
        self.assertEqual(tenths(machine.out_15m), 3)
        self.assertEqual(tenths(machine.out_today), 3)
        self.assertEqual(machine.activity, "idle")

    def test_a_drop_after_a_wobble_counts_once(self):
        _folder, _path, db = self.db()
        machine = self.ticks(db, "12:00", (40.0, 39.7, 40.3, 39.7, 38.0, 38.4, 38.0))
        self.assertEqual(tenths(machine.booked_oz), 380)
        self.assertEqual(tenths(machine.out_today), 20)

    def take_at_16(self, db):
        self.ticks(db, "11:59", (16.0, 16.0))
        machine = self.ticks(db, "12:00", (None, None), person=True)
        self.assertEqual(machine.activity, "out")

    def test_a_fill_the_model_reads_low_still_empties_to_zero(self):
        _folder, _path, db = self.db()
        self.take_at_16(db)
        machine = self.ticks(db, "12:01", (60.0,))
        self.assertEqual(tenths(machine.booked_oz), 700)
        machine = self.ticks(db, "12:02", [float(gauge) for gauge in range(58, 29, -2)])
        self.assertEqual(tenths(machine.booked_oz), 350)
        machine = self.ticks(db, "12:05", [float(gauge) for gauge in range(28, 5, -2)])
        self.assertEqual(tenths(machine.booked_oz), 70)
        self.assertTrue(machine.alarm)
        self.assertEqual(machine.activity, "brewing")
        machine = self.ticks(db, "12:08", (0, 0))
        self.assertEqual(tenths(machine.booked_oz), 0)
        self.assertEqual(machine.activity, "idle")
        self.assertEqual(tenths(machine.out_today), 700)

    def test_booked_never_passes_70(self):
        _folder, _path, db = self.db()
        self.take_at_16(db)
        machine = self.ticks(db, "12:01", (50.0, 51.0, 52.0))
        self.assertEqual(tenths(machine.booked_oz), 700)

    def test_a_brew_that_loses_the_line_ends_idle_at_zero(self):
        _folder, _path, db = self.db()
        machine = self.ticks(db, "12:00", (20.0, 18.0, 16.0, 14.0, 12.0, 10.0, 8.0))
        self.assertEqual(machine.activity, "brewing")
        machine = self.ticks(db, "12:02", (0,))
        self.assertEqual(tenths(machine.booked_oz), 80)
        self.assertEqual(machine.activity, "brewing")
        machine = self.ticks(db, "12:03", (0,))
        self.assertEqual(tenths(machine.booked_oz), 0)
        self.assertEqual(machine.activity, "idle")
        self.assertEqual(tenths(machine.out_today), 200)
        kinds = [row["kind"] for row in db.execute("SELECT kind FROM event ORDER BY id")]
        self.assertEqual(kinds[-1], "idle")

    def test_one_zero_mid_brew_is_a_missed_line(self):
        _folder, _path, db = self.db()
        self.ticks(db, "12:00", (40.0, 38.0, 36.0))
        machine = self.ticks(db, "12:01", (0, 34.0, 32.0))
        self.assertEqual(tenths(machine.booked_oz), 320)
        self.assertEqual(machine.activity, "brewing")

    def test_lifting_it_and_walking_out_between_ticks_is_a_take(self):
        _folder, _path, db = self.db()
        self.ticks(db, "12:00", (40.0, 40.0))
        machine = self.ticks(db, "12:01", (40.0,), person=True)
        self.assertEqual(machine.activity, "idle")
        machine = self.ticks(db, "12:02", (None,))
        self.assertEqual(machine.activity, "idle")
        machine = self.ticks(db, "12:03", (None,))
        self.assertEqual(machine.activity, "out")
        self.assertTrue(machine.reservoir_out)
        self.assertEqual(tenths(machine.taken_oz), 400)
        machine = self.ticks(db, "12:05", (70.0,))
        self.assertEqual(tenths(machine.booked_oz), 700)
        self.assertEqual(machine.refills_today, 1)
        self.assertEqual(tenths(machine.filled_oz), 300)

    def test_a_person_gone_two_ticks_before_the_miss_is_not_a_take(self):
        _folder, _path, db = self.db()
        self.ticks(db, "12:00", (40.0,), person=True)
        self.ticks(db, "12:01", (40.0, 40.0))
        machine = self.ticks(db, "12:02", (None, None, None, None))
        self.assertEqual(machine.activity, "idle")
        self.assertFalse(machine.reservoir_out)
        got = db.execute("SELECT gap_ticks, gap_person FROM machine").fetchone()
        self.assertEqual(tuple(got), (4, 0))

    def test_the_kept_fold_matches_a_full_replay(self):
        _folder, path, db = self.db()
        self.ticks(db, "11:50", (40.0, 39.7, 40.3, 38.0, 36.0, 34.0, None, None), day="2026-10-11")
        self.ticks(db, "11:59", (None, None), person=True, day="2026-10-11")
        self.ticks(db, "12:00", (60.0, 59.6, 50.0, 48.0, 0, 0, 3.0))
        self.assertEqual(db.folded[1], ledger._replay(db))
        other = self.reconnect(path)
        self.assertIsNone(other.folded)
        self.ticks(other, "12:10", (3.0,))
        self.assertEqual(other.folded[1], ledger._replay(other))

    def test_a_tick_from_another_connection_forces_a_replay(self):
        _folder, path, db = self.db()
        self.ticks(db, "12:00", (40.0, 38.0))
        other = self.reconnect(path)
        self.ticks(other, "12:01", (36.0,))
        machine = self.ticks(db, "12:02", (34.0,))
        self.assertEqual(tenths(machine.out_today), 60)
        self.assertEqual(db.folded[1], ledger._replay(db))


if __name__ == "__main__":
    unittest.main()
