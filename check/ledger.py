import math
import sqlite3
import time
from datetime import datetime, time as clock_time, timedelta
from pathlib import Path
from typing import NamedTuple
from zoneinfo import ZoneInfo

__all__ = ["connect", "tick", "Tick", "Machine", "Event", "Applied"]

_CHICAGO = ZoneInfo("America/Chicago")
_SCHEMA = Path(__file__).resolve().parent.parent / "page" / "schema.sql"
_KINDS = (
    "person",
    "taken",
    "brewing",
    "alarm_on",
    "alarm_off",
    "fill",
    "dump",
    "put_back",
    "idle",
)
_FULL = 700
_ALARM = 175
_OVER = 50
_NEAR = 10
_SHIFT = 35
_BREW_LO = 5
_BREW_HI = 50
# Under one cup. An empty tank flickers between no line and about 3 fl oz.
# A seated 0 locks that booking at 0. The flicker does not raise it.
_CUP = 50
# Model wobble on a still tank. A rise this small does not lift the outflow floor,
# so the same ounces are not counted out twice.
_NOISE = 10
_WINDOW = timedelta(minutes=15)


class Tick(NamedTuple):
    at: datetime
    gauge_oz: float | None
    person: bool
    capture_ms: int
    tank_ms: int
    person_ms: int
    gauge_ms: int
    rss_mb: int | None
    temp_c: float | None
    cpu_pct: float | None = None
    mem_free_pct: float | None = None


class Machine(NamedTuple):
    booked_oz: float | None
    activity: str
    activity_started: datetime
    alarm: bool
    alarm_started: datetime
    person: bool
    person_open: bool
    seen_today: int
    reservoir_out: bool
    taken_oz: float | None
    out_15m: float
    out_today: float
    filled_oz: float
    refills_today: int
    coffee_month: float


class Event(NamedTuple):
    kind: str
    message: str
    model_oz: float | None
    ounces: float | None
    delta_oz: float | None


class Applied(NamedTuple):
    machine: Machine
    events: tuple[Event, ...]


class _Fold(NamedTuple):
    # The gauge a fill booked as 70. Later gauges scale onto 0..70 from it. None is 1:1.
    anchor: int | None
    # Lowest booked level since the last real rise. Only a drop below it counts as out.
    floor: int | None
    empty_run: int
    prev_gauge: int | None
    booked: int | None
    activity: str
    activity_started: datetime | None
    alarm: bool
    alarm_started: datetime | None
    person_open: bool
    absent_run: int
    seen_today: int
    day: str | None
    reservoir_out: bool
    taken: int | None
    gap_ticks: int
    gap_person: bool
    pending: int | None
    pending_count: int
    brew_falls: int
    brew_from: int | None
    steps: tuple[tuple[datetime, int], ...]
    fills: tuple[tuple[str, int], ...]
    logged_days: tuple[str, ...]
    out_15m: int
    out_today: int
    filled: int
    refills_today: int
    coffee_cents: int
    seated_15m: int
    seated_today: int


class _Connection(sqlite3.Connection):
    # (newest reading id, fold after it). A tick replays only when another writer moved the table.
    folded: "tuple[int, _Fold] | None" = None


def connect(path: str | Path) -> sqlite3.Connection:
    db = sqlite3.connect(path, factory=_Connection)
    db.row_factory = sqlite3.Row
    db.isolation_level = None
    db.execute("PRAGMA foreign_keys = ON")
    db.execute("PRAGMA journal_mode = WAL").fetchone()
    present = db.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'reading'"
    ).fetchone()
    if present is None:
        db.executescript(_SCHEMA.read_text(encoding="utf-8"))
    # Files made before schema.sql dropped these. Nothing reads them, and each costs a page a tick.
    db.execute("DROP INDEX IF EXISTS reading_ts")
    db.execute("DROP INDEX IF EXISTS event_id_desc")
    columns = {row["name"] for row in db.execute("PRAGMA table_info(reading)")}
    for column in ("cpu_pct", "mem_free_pct"):
        if column not in columns:
            db.execute(f"ALTER TABLE reading ADD COLUMN {column} REAL")
    return db


def tick(db: sqlite3.Connection, one: Tick) -> Applied:
    _reject(one)
    db.execute("BEGIN IMMEDIATE")
    try:
        started = time.perf_counter()
        fold = _current(db)
        gauge = None if one.gauge_oz is None else round(one.gauge_oz * 10)
        fold, events = _step(fold, one.at, gauge, one.person)
        ledger_ms = round((time.perf_counter() - started) * 1000)
        reading_id = _write(db, one, fold, events, ledger_ms, gauge)
        db.execute("COMMIT")
    except BaseException:
        db.execute("ROLLBACK")
        raise
    if isinstance(db, _Connection):
        db.folded = (reading_id, fold)
    return Applied(_machine(fold, one.person), events)


def _current(db: sqlite3.Connection) -> "_Fold":
    folded = getattr(db, "folded", None)
    if folded is not None:
        newest = db.execute("SELECT max(id) FROM reading").fetchone()[0]
        if newest == folded[0]:
            return folded[1]
    return _replay(db)


def _reject(one: Tick) -> None:
    if one.at.tzinfo is None or one.at.tzinfo.utcoffset(one.at) is None:
        raise ValueError("Tick time must carry a timezone.")
    if one.gauge_oz is not None and not math.isfinite(one.gauge_oz):
        raise ValueError("Gauge must be finite.")
    if type(one.person) is not bool:
        raise ValueError("Person must be a bool.")
    if one.capture_ms < 0 or one.tank_ms < 0 or one.person_ms < 0 or one.gauge_ms < 0:
        raise ValueError("A duration must not be negative.")


def _empty() -> _Fold:
    return _Fold(
        None,
        None,
        0,
        None,
        None,
        "idle",
        None,
        False,
        None,
        False,
        0,
        0,
        None,
        False,
        None,
        0,
        False,
        None,
        0,
        0,
        None,
        (),
        (),
        (),
        0,
        0,
        0,
        0,
        0,
        0,
        0,
    )


def _under_cup(gauge: int | None) -> bool:
    return gauge is not None and gauge < _CUP


def _scaled(gauge: int, anchor: int | None) -> int:
    if anchor is None:
        level = gauge
    else:
        level = round(gauge * _FULL / anchor)
    return max(0, min(_FULL, level))


def _replay(db: sqlite3.Connection) -> _Fold:
    fold = _empty()
    rows = db.execute("SELECT ts, gauge_oz, person FROM reading ORDER BY id")
    for row in rows:
        gauge = None if row["gauge_oz"] is None else round(row["gauge_oz"] * 10)
        fold, _events = _step(
            fold,
            datetime.fromisoformat(row["ts"]),
            gauge,
            row["person"] == 1,
        )
    return fold


def _step(
    fold: _Fold, at: datetime, gauge: int | None, person: bool
) -> tuple[_Fold, tuple[Event, ...]]:
    anchor = fold.anchor
    floor = fold.floor
    empty_run = fold.empty_run
    prev_gauge = fold.prev_gauge
    booked = fold.booked
    activity = fold.activity
    activity_started = fold.activity_started
    alarm = fold.alarm
    alarm_started = fold.alarm_started
    person_open = fold.person_open
    absent_run = fold.absent_run
    seen_today = fold.seen_today
    reservoir_out = fold.reservoir_out
    taken = fold.taken
    gap_ticks = fold.gap_ticks
    gap_person = fold.gap_person
    pending = fold.pending
    pending_count = fold.pending_count
    brew_falls = fold.brew_falls
    brew_from = fold.brew_from
    midnight = datetime.combine(at.astimezone(_CHICAGO).date(), clock_time(), _CHICAGO)
    keep_from = min(at - _WINDOW, midnight)
    steps = [step for step in fold.steps if step[0] >= keep_from]
    fills = list(fold.fills)
    logged_days = list(fold.logged_days)
    seated_15m = fold.seated_15m
    seated_today = fold.seated_today
    events: list[Event] = []

    day = _chicago_day(at)
    if fold.day is not None and fold.day != day:
        seen_today = 0
    if day not in logged_days:
        logged_days.append(day)
    if gauge is not None:
        gap_ticks = 0
        gap_person = False

    def become(word: str) -> None:
        nonlocal activity, activity_started
        if activity != word:
            activity = word
            activity_started = at

    def today_cents() -> int:
        return sum(delta for filled_day, delta in fills if filled_day == day)

    def move(level: int) -> int:
        """Book a level. Return how far it fell this tick."""
        nonlocal booked, floor
        old = booked
        booked = level
        if floor is None or level - floor > _NOISE:
            floor = level
        elif level < floor:
            steps.append((at, floor - level))
            floor = level
        return 0 if old is None else old - level

    def book(new_gauge: int) -> int:
        return move(_scaled(new_gauge, anchor))

    def place(level: int) -> None:
        nonlocal anchor
        anchor = None
        move(level)

    def idle_line() -> None:
        events.append(
            _event(
                "idle",
                f"Level {_oz(booked)} fl oz. No person. Bill stayed ${_money(today_cents())}.",
                gauge,
                booked,
            )
        )

    seated_empty = gauge == 0 and not person and not reservoir_out
    empty_run = empty_run + 1 if seated_empty else 0

    held = False
    if (
        pending is not None
        and gauge is not None
        and gauge != 0
        and not person
        and not reservoir_out
        and abs(gauge - pending) <= _NEAR
    ):
        pending_count += 1
        if pending_count >= 3:
            book(pending)
            pending = None
            pending_count = 0
            if activity == "brewing":
                become("idle")
                idle_line()
            brew_falls = 0
            brew_from = None
        held = True
    else:
        pending = None
        pending_count = 0

    if person:
        absent_run = 0
        if not person_open:
            person_open = True
            seen_today += 1
            if gauge is None:
                message = "Person seen."
            else:
                message = "Person seen. Reservoir stayed."
            events.append(_event("person", message, gauge, booked))
    elif person_open:
        absent_run += 1
        if absent_run >= 2:
            person_open = False
            absent_run = 0

    if held:
        pass
    elif gauge is None and not reservoir_out:
        gap_ticks += 1
        # A person seen just before the reservoir vanished counts. Someone who lifts it and
        # walks out between two ticks is never in a frame without it.
        if person or person_open:
            gap_person = True
        if gap_ticks >= 2 and gap_person and booked is not None:
            taken = booked
            reservoir_out = True
            gap_ticks = 0
            gap_person = False
            brew_falls = 0
            brew_from = None
            become("out")
            events.append(
                _event(
                    "taken",
                    f"Reservoir taken. Saved {_oz(booked)} fl oz.",
                    None,
                    booked,
                )
            )
    elif gauge is None or (reservoir_out and (person or _under_cup(gauge))) or person or gauge == 0:
        # A seated 0 leaves a real level alone. It clears a booking still under one cup.
        # During a brew, two seated 0s in a row are the tank running out below the last
        # line the model can see.
        if seated_empty and (
            booked is None or booked < _CUP or (activity == "brewing" and empty_run >= 2)
        ):
            if activity == "brewing":
                place(0)
                become("idle")
                idle_line()
            else:
                # Clearing an idle flicker is not ounces out.
                anchor = None
                booked = 0
                floor = 0
            prev_gauge = None
            brew_falls = 0
            brew_from = None
    elif booked == 0 and _under_cup(gauge):
        pass
    elif reservoir_out:
        reservoir_out = False
        if gauge - taken >= _SHIFT:
            anchor = gauge
            move(_FULL)
            delta = _FULL - taken
            fills.append((day, delta))
            events.append(
                _event(
                    "fill",
                    (
                        f"Fill. Booked {_oz(booked)} fl oz. Model said {_oz(gauge)}. "
                        f"Coffee today ${_money(today_cents())}."
                    ),
                    gauge,
                    booked,
                    delta,
                )
            )
        elif taken - gauge >= _SHIFT:
            place(gauge)
            events.append(_event("dump", f"Dump. Level {_oz(booked)} fl oz.", gauge, booked))
        else:
            place(gauge)
            events.append(_event("put_back", f"Put back. Level {_oz(booked)} fl oz.", gauge, booked))
        become("idle")
    else:
        # Quiet-jump size uses the previous liquid line, not the booked level.
        # A person tick moves only that line.
        if prev_gauge is not None and abs(gauge - prev_gauge) > _OVER:
            pending = gauge
            pending_count = 1
        elif booked is None:
            book(gauge)
        else:
            old = booked
            drop = book(gauge)
            if _BREW_LO < drop <= _BREW_HI:
                if brew_falls == 0:
                    brew_from = old
                brew_falls = min(brew_falls + 1, 2)
                if brew_falls == 2 and activity == "idle":
                    become("brewing")
                    events.append(
                        _event(
                            "brewing",
                            f"Brewing. Level falling from {_oz(brew_from)} fl oz.",
                            gauge,
                            booked,
                        )
                    )
            else:
                if activity == "brewing":
                    become("idle")
                    idle_line()
                brew_falls = 0
                brew_from = None

    new_alarm = booked is not None and booked < _ALARM
    if new_alarm != alarm:
        alarm = new_alarm
        alarm_started = at
        if new_alarm:
            text = f"Alarm on. Level {_oz(booked)} fl oz."
            if activity == "brewing":
                text = f"Alarm on. Level {_oz(booked)} fl oz. Still brewing."
            events.append(_event("alarm_on", text, gauge, booked))
        else:
            events.append(
                _event("alarm_off", f"Alarm off. Level {_oz(booked)} fl oz.", gauge, booked)
            )
    if alarm_started is None:
        alarm_started = at
    if activity_started is None:
        activity_started = at

    out_15m = sum(down for ts, down in steps if ts >= at - _WINDOW)
    out_today = sum(down for ts, down in steps if _chicago_day(ts) == day)
    filled = sum(delta for filled_day, delta in fills if filled_day == day)
    refills_today = sum(1 for filled_day, _delta in fills if filled_day == day)
    coffee_cents = _coffee_cents(fills, logged_days)
    if gap_ticks >= 4 and not gap_person:
        # Misses 1 through 3 recompute the window. The fourth person-free miss
        # publishes the last seated totals, which replay keeps on the fold.
        out_15m = seated_15m
        out_today = seated_today
    elif gap_ticks == 0:
        seated_15m = out_15m
        seated_today = out_today

    if gauge is not None and gauge != 0 and not (booked == 0 and _under_cup(gauge)):
        prev_gauge = gauge

    events.sort(key=lambda event: _KINDS.index(event.kind))
    return (
        _Fold(
            anchor,
            floor,
            empty_run,
            prev_gauge,
            booked,
            activity,
            activity_started,
            alarm,
            alarm_started,
            person_open,
            absent_run,
            seen_today,
            day,
            reservoir_out,
            taken,
            gap_ticks,
            gap_person,
            pending,
            pending_count,
            brew_falls,
            brew_from,
            tuple(steps),
            tuple(fills),
            tuple(logged_days),
            out_15m,
            out_today,
            filled,
            refills_today,
            coffee_cents,
            seated_15m,
            seated_today,
        ),
        tuple(events),
    )


def _coffee_cents(fills: list[tuple[str, int]], days: list[str]) -> int:
    count = len(days)
    if count == 0:
        return 0
    by_day = {one: 0 for one in days}
    for filled_day, delta in fills:
        by_day[filled_day] += delta
    total = sum(by_day.values())
    return (total * 30 + count // 2) // count


def _write(
    db: sqlite3.Connection,
    one: Tick,
    fold: _Fold,
    events: tuple[Event, ...],
    ledger_ms: int,
    gauge: int | None,
) -> int:
    ts = one.at.isoformat()
    total_ms = one.capture_ms + one.tank_ms + one.person_ms + one.gauge_ms + ledger_ms
    inserted = db.execute(
        """
        INSERT INTO reading (
            ts, day, gauge_oz, booked_oz, person,
            capture_ms, tank_ms, person_ms, gauge_ms, ledger_ms, total_ms,
            rss_mb, temp_c, cpu_pct, mem_free_pct
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            ts,
            fold.day,
            _ounces(gauge),
            _ounces(fold.booked),
            int(one.person),
            one.capture_ms,
            one.tank_ms,
            one.person_ms,
            one.gauge_ms,
            ledger_ms,
            total_ms,
            one.rss_mb,
            one.temp_c,
            one.cpu_pct,
            one.mem_free_pct,
        ),
    )
    started = fold.activity_started.isoformat()
    alarm_at = fold.alarm_started.isoformat()
    db.execute(
        """
        INSERT OR REPLACE INTO machine (
            id, booked_oz, activity, activity_started, alarm, alarm_started,
            person, person_open, seen_today, reservoir_out, taken_oz,
            gap_ticks, gap_person, pending_oz, pending_count,
            out_15m, out_today, filled_oz, refills_today, coffee_month
        ) VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            _ounces(fold.booked),
            fold.activity,
            started,
            int(fold.alarm),
            alarm_at,
            int(one.person),
            int(fold.person_open),
            fold.seen_today,
            int(fold.reservoir_out),
            _ounces(fold.taken),
            fold.gap_ticks,
            int(fold.gap_person),
            _ounces(fold.pending),
            fold.pending_count,
            fold.out_15m / 10,
            fold.out_today / 10,
            fold.filled / 10,
            fold.refills_today,
            fold.coffee_cents / 100,
        ),
    )
    for event in events:
        db.execute(
            """
            INSERT INTO event (ts, day, kind, message, model_oz, ounces, delta_oz)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                ts,
                fold.day,
                event.kind,
                event.message,
                event.model_oz,
                event.ounces,
                event.delta_oz,
            ),
        )
    return int(inserted.lastrowid)


def _machine(fold: _Fold, person: bool) -> Machine:
    return Machine(
        _ounces(fold.booked),
        fold.activity,
        fold.activity_started,
        fold.alarm,
        fold.alarm_started,
        person,
        fold.person_open,
        fold.seen_today,
        fold.reservoir_out,
        _ounces(fold.taken),
        fold.out_15m / 10,
        fold.out_today / 10,
        fold.filled / 10,
        fold.refills_today,
        fold.coffee_cents / 100,
    )


def _event(
    kind: str,
    message: str,
    gauge: int | None,
    booked: int | None,
    delta: int | None = None,
) -> Event:
    return Event(
        kind,
        message,
        None if gauge is None else gauge / 10,
        None if booked is None else booked / 10,
        None if delta is None else delta / 10,
    )


def _ounces(tenths: int | None) -> float | None:
    if tenths is None:
        return None
    return tenths / 10


def _oz(tenths: int) -> str:
    whole, frac = divmod(tenths, 10)
    if frac == 0:
        return str(whole)
    return f"{whole}.{frac}"


def _money(cents: int) -> str:
    sign = "-" if cents < 0 else ""
    cents = abs(cents)
    return f"{sign}{cents // 100}.{cents % 100:02d}"


def _chicago_day(at: datetime) -> str:
    return at.astimezone(_CHICAGO).date().isoformat()
