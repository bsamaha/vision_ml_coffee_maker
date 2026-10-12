import math
import sqlite3
import time
from datetime import datetime, timedelta
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
    baseline: int | None
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


def connect(path: str | Path) -> sqlite3.Connection:
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    db.isolation_level = None
    db.execute("PRAGMA foreign_keys = ON")
    db.execute("PRAGMA journal_mode = WAL").fetchone()
    present = db.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'reading'"
    ).fetchone()
    if present is None:
        db.executescript(_SCHEMA.read_text(encoding="utf-8"))
    return db


def tick(db: sqlite3.Connection, one: Tick) -> Applied:
    _reject(one)
    db.execute("BEGIN IMMEDIATE")
    try:
        started = time.perf_counter()
        fold = _replay(db)
        gauge = None if one.gauge_oz is None else round(one.gauge_oz * 10)
        fold, events = _step(fold, one.at, gauge, one.person)
        ledger_ms = round((time.perf_counter() - started) * 1000)
        _write(db, one, fold, events, ledger_ms, gauge)
        db.execute("COMMIT")
    except BaseException:
        db.execute("ROLLBACK")
        raise
    return Applied(_machine(fold, one.person), events)


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
    baseline = fold.baseline
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
    steps = list(fold.steps)
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

    def book_change(new_baseline: int) -> int:
        nonlocal booked, baseline
        if booked is None or baseline is None:
            booked = new_baseline
            baseline = new_baseline
            return 0
        old = booked
        booked = old + (new_baseline - baseline)
        baseline = new_baseline
        if booked < old:
            steps.append((at, old - booked))
        return old - booked

    def place(level: int) -> None:
        nonlocal booked, baseline
        old = booked
        if old is not None and level < old:
            steps.append((at, old - level))
        booked = level
        baseline = level

    def idle_line() -> None:
        events.append(
            _event(
                "idle",
                f"Level {_oz(booked)} fl oz. No person. Bill stayed ${_money(today_cents())}.",
                gauge,
                booked,
            )
        )

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
            candidate = pending
            # Booked ounces and the baseline diverge after a fill. Add the candidate's
            # gauge change. Writing the candidate itself would replace 70 with the model.
            book_change(candidate)
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
        if person:
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
        if gauge == 0 and not person and not reservoir_out and (booked is None or booked < _CUP):
            booked = 0
            baseline = 0
            prev_gauge = None
    elif booked == 0 and _under_cup(gauge):
        pass
    elif reservoir_out:
        reservoir_out = False
        if gauge - taken >= _SHIFT:
            old = booked
            booked = _FULL
            if old is not None and booked < old:
                steps.append((at, old - booked))
            baseline = gauge
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
        # Quiet-jump size uses the previous liquid line, not the booking baseline.
        # A person tick moves only that line.
        if prev_gauge is not None and abs(gauge - prev_gauge) > _OVER:
            pending = gauge
            pending_count = 1
        elif baseline is None or booked is None:
            booked = gauge
            baseline = gauge
        else:
            old = booked
            drop = book_change(gauge)
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
            baseline,
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
) -> None:
    ts = one.at.isoformat()
    total_ms = one.capture_ms + one.tank_ms + one.person_ms + one.gauge_ms + ledger_ms
    db.execute(
        """
        INSERT INTO reading (
            ts, day, gauge_oz, booked_oz, person,
            capture_ms, tank_ms, person_ms, gauge_ms, ledger_ms, total_ms,
            rss_mb, temp_c
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
