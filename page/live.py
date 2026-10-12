"""The live board.

One process reads the ledger database and the frame directory. It does not write either.
Import serve and Serving. Each request opens its own read-only SQLite connection.

Production, from the repo root:

    python page/live.py
"""

from __future__ import annotations

import functools
import html
import sqlite3
import threading
import urllib.parse
from datetime import date, datetime, timedelta
from email.utils import formatdate, parsedate_to_datetime
from enum import Enum
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import NamedTuple
from zoneinfo import ZoneInfo

__all__ = ["serve", "Serving", "error_path"]

_CHICAGO = ZoneInfo("America/Chicago")
_WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
_MONTHS = (
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)
_SHORT = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
_CAPTIONS = ("-1:45", "-1:30", "-1:15", "-1:00", "-0:45", "-0:30", "-0:15", "Now")
_STALE = "Stale. 4 ticks with no level."
_UNVERIFIED = "Unverified rise. Bill unchanged."
_REVIEW = "Earlier frame. The numbers stay live."
_DOT = "\u00b7"
_EVENTS = 50
# Seconds between polls, and the reading age past which the board says it is not updating.
_POLL_S = 3
_LAG_S = 30
_SCRIPT = f"""
"use strict";
(function () {{
  function age() {{
    const stamp = document.getElementById("age");
    if (!stamp || !stamp.dataset.tick) return;
    const seconds = Math.max(0, Math.round((Date.now() - Date.parse(stamp.dataset.tick)) / 1000));
    let text = seconds + " s ago";
    if (seconds >= 3600) text = Math.floor(seconds / 3600) + " h ago";
    else if (seconds >= 60) text = Math.floor(seconds / 60) + " min ago";
    stamp.textContent = "Updated " + text;
    const lagging = seconds > {_LAG_S};
    document.getElementById("board").classList.toggle("lagging", lagging);
    const mark = document.getElementById("live-mark");
    if (lagging) mark.textContent = "Not updating";
    else if (mark.textContent === "Not updating") mark.textContent = mark.dataset.mark;
  }}
  async function poll() {{
    try {{
      const response = await fetch(location.pathname + location.search, {{ cache: "no-store" }});
      if (!response.ok) return;
      const next = new DOMParser().parseFromString(await response.text(), "text/html");
      const fresh = next.getElementById("board");
      if (!fresh) return;
      const kept = {{}};
      for (const id of ["level", "status", "log-block"]) {{
        const old = document.getElementById(id);
        if (old) kept[id] = old.scrollTop;
      }}
      document.getElementById("board").replaceWith(fresh);
      for (const id in kept) {{
        const now = document.getElementById(id);
        if (now) now.scrollTop = kept[id];
      }}
    }} catch (error) {{
      return;
    }} finally {{
      age();
    }}
  }}
  age();
  setInterval(age, 1000);
  setInterval(poll, {_POLL_S * 1000});
}})();
"""
_ERROR_FILE = "board-error.txt"
_PHOTO = """
#frame {
  position: relative;
  height: 100%;
  width: auto;
  max-width: 100%;
  display: block;
  object-fit: contain;
}
#frame[hidden],
#hero[hidden] {
  display: none !important;
}
#strip a {
  flex: 1 1 0;
  min-width: 0;
  padding: 4px 4px 6px;
  border: 1px solid #333;
  background: #000;
  color: #fff;
  cursor: pointer;
  text-decoration: none;
}
#strip a[aria-current="page"] {
  border: 2px solid #fff;
  padding: 3px 3px 5px;
}
#strip img {
  display: block;
  width: 100%;
  height: 56px;
  object-fit: cover;
}
"""


class _Ounces(NamedTuple):
    """Fluid ounces as tenths. 473 is 47.3. Built only at the SQL boundary."""

    tenths: int


class _Activity(Enum):
    """Member name is the word stored on machine.activity. Value is the board label."""

    idle = "Idle"
    brewing = "Brewing"
    out = "Out"


class _Band(Enum):
    """Value is the board text. Chosen from booked tenths, never stored."""

    FULL = "Full"
    THREE_QUARTER = "3/4"
    HALF = "1/2"
    LOW = "Low"


# Higher band first. A shared edge belongs to the higher band.
# 525 is 52.5, 350 is 35, 175 is 17.5. Below 175 is Low.
_BAND_EDGES = (
    (525, _Band.FULL),
    (350, _Band.THREE_QUARTER),
    (175, _Band.HALF),
)


class _Timings(NamedTuple):
    """The newest reading. Over 15 s is not a column and not a field."""

    capture_ms: int
    tank_ms: int
    person_ms: int
    gauge_ms: int
    ledger_ms: int
    total_ms: int
    rss_mb: int | None
    temp_tenths: int | None


class _Live(NamedTuple):
    """Facts from the machine row plus the newest reading."""

    tick_at: datetime
    booked: _Ounces | None
    gauge: _Ounces | None
    alarm_on: bool
    alarm_started: datetime
    activity: _Activity
    activity_started: datetime
    person: bool
    seen_today: int
    refills_today: int
    out_15m_tenths: int
    out_today_tenths: int
    filled_tenths: int
    coffee_month_cents: int
    stale: bool
    unverified: bool
    timings: _Timings


class _LogLine(NamedTuple):
    at: datetime
    message: str


class _Fill(NamedTuple):
    """One fill event's coffee, in cents. Prior days only."""

    day: date
    cents: int


class _Frame(NamedTuple):
    """Basename of a JPEG in the frames directory. No slash."""

    name: str


class _Quiet(NamedTuple):
    """No machine row, or no reading. Frames may still be on disk. No ounces exist here."""

    frames: tuple[_Frame, ...]


class _Shown(NamedTuple):
    """One tick the ledger has finished writing. `log` is the newest `_EVENTS` lines."""

    live: _Live
    log: tuple[_LogLine, ...]
    logged_days: tuple[date, ...]
    fills: tuple[_Fill, ...]
    frames: tuple[_Frame, ...]


class _Wall(NamedTuple):
    """One Chicago instant, formatted twice so the attribute and the visible text share it."""

    attribute: str
    date_line: str
    clock: str


class _Server(ThreadingHTTPServer):
    """One listener. Holds the paths for its own requests. Does not hold a board."""

    db: Path
    frames: Path
    error: Path

    def __init__(self, db: Path, frames: Path, port: int) -> None:
        super().__init__(("0.0.0.0", port), _Handler)
        self.db = db
        self.frames = frames
        self.error = error_path(db)


class _Handler(BaseHTTPRequestHandler):
    """Writes bytes. Does not format ounces, clocks, or bands."""

    def do_GET(self) -> None:
        server = self.server
        assert isinstance(server, _Server)
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/":
            board = _load(server.db, server.frames)
            raw = urllib.parse.parse_qs(parsed.query, keep_blank_values=True).get("frame", [None])[0]
            selected = _choice(board.frames, raw)
            body = _html(board, selected, _board_error(server.error)).encode("utf-8")
            self._send(200, body, "text/html; charset=utf-8", {"Cache-Control": "no-store"})
            return
        if parsed.path.startswith("/frame/"):
            self._jpeg(server, parsed.path[len("/frame/") :])
            return
        self._send(404, b"Not found", "text/plain; charset=utf-8")

    def _jpeg(self, server: _Server, segment: str) -> None:
        name = urllib.parse.unquote(segment)
        if not _one_name(name):
            self._send(404, b"Not found", "text/plain; charset=utf-8")
            return
        allowed = {frame.name for frame in _frames(server.frames)}
        path = server.frames / name
        if name not in allowed or not path.is_file():
            self._send(404, b"Not found", "text/plain; charset=utf-8")
            return
        if path.resolve().parent != server.frames.resolve():
            self._send(404, b"Not found", "text/plain; charset=utf-8")
            return
        # A wiped run reuses file names, so the browser revalidates by mtime instead of caching blind.
        modified = int(path.stat().st_mtime)
        headers = {"Cache-Control": "no-cache", "Last-Modified": formatdate(modified, usegmt=True)}
        since = self.headers.get("If-Modified-Since")
        if since is not None:
            try:
                unchanged = int(parsedate_to_datetime(since).timestamp()) >= modified
            except (TypeError, ValueError):
                unchanged = False
            if unchanged:
                self.send_response(304)
                for key, value in headers.items():
                    self.send_header(key, value)
                self.end_headers()
                return
        self._send(200, path.read_bytes(), "image/jpeg", headers)

    def _send(
        self, status: int, body: bytes, content_type: str, headers: dict[str, str] | None = None
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt: str, *args: object) -> None:
        return


class Serving:
    """A bound board.

    `port` is the port the OS bound. Passing 0 to `serve` stores the ephemeral port here.
    Scripts call `serve`, then `wait` or `close`. They do not construct `Serving`.
    """

    port: int

    def __init__(self, port: int, server: _Server, thread: threading.Thread) -> None:
        self.port = port
        self._server = server
        self._thread = thread
        self._closed = False
        self._lock = threading.Lock()

    def wait(self) -> None:
        try:
            self._thread.join()
        except KeyboardInterrupt:
            self.close()

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
        self._server.shutdown()
        self._server.server_close()
        self._thread.join()


def serve(db: Path, frames: Path, port: int = 8080) -> Serving:
    """Bind a board and return. The caller waits or closes.

    Each request opens its own read-only connection. This function does not connect.
    """
    httpd = _Server(db, frames, port)
    thread = threading.Thread(target=httpd.serve_forever, daemon=False)
    thread.start()
    return Serving(int(httpd.server_address[1]), httpd, thread)


def error_path(db: Path) -> Path:
    """Where the board process writes the one line that explains why it is not ticking."""
    return db.with_name(_ERROR_FILE)


def _board_error(path: Path) -> str | None:
    try:
        text = path.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return text or None


def _one_name(name: str) -> bool:
    if name in ("", ".", ".."):
        return False
    if "/" in name or "\\" in name or "\x00" in name:
        return False
    return Path(name).name == name


def _choice(frames: tuple[_Frame, ...], raw: str | None) -> int | None:
    """The frame named in the query. A name that aged out falls back to the newest."""
    if not frames:
        return None
    for index, frame in enumerate(frames):
        if frame.name == raw:
            return index
    return len(frames) - 1


def _frames(folder: Path) -> tuple[_Frame, ...]:
    """At most eight JPEGs, oldest of that window first. The last one is the newest mtime."""
    if not folder.is_dir():
        return ()
    root = folder.resolve()
    found: list[tuple[float, str]] = []
    for path in folder.iterdir():
        if not path.is_file():
            continue
        if path.suffix.lower() not in {".jpg", ".jpeg"}:
            continue
        name = path.name
        if not _one_name(name):
            continue
        if (folder / name).resolve().parent != root:
            continue
        found.append((path.stat().st_mtime, name))
    found.sort(key=lambda item: (item[0], item[1]))
    newest = found[-8:]
    return tuple(_Frame(name) for _mtime, name in newest)


def _captions(count: int) -> tuple[str, ...]:
    """Tail of `_CAPTIONS`. The last caption is Now. Zero files is ()."""
    if count == 0:
        return ()
    return _CAPTIONS[-count:]


def _tenths(value: float | None) -> int | None:
    if value is None:
        return None
    return round(value * 10)


def _load(db: Path, frames: Path) -> _Quiet | _Shown:
    """Parse one committed tick into a board. Five bounded statements, one read transaction."""
    shots = _frames(frames)
    if not db.is_file():
        return _Quiet(shots)
    uri = f"{db.resolve().as_uri()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    conn.isolation_level = None
    try:
        present = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'machine'"
        ).fetchone()
        if present is None:
            return _Quiet(shots)
        conn.execute("BEGIN")
        try:
            machine = conn.execute(
                """
                SELECT booked_oz, activity, activity_started, alarm, alarm_started,
                       person, seen_today, gap_ticks, gap_person, pending_count,
                       out_15m, out_today, filled_oz, refills_today, coffee_month
                FROM machine WHERE id = 1
                """
            ).fetchone()
            reading = conn.execute(
                """
                SELECT ts, gauge_oz, capture_ms, tank_ms, person_ms, gauge_ms,
                       ledger_ms, total_ms, rss_mb, temp_c
                FROM reading ORDER BY id DESC LIMIT 1
                """
            ).fetchone()
            if machine is None or reading is None:
                return _Quiet(shots)
            tick_at = datetime.fromisoformat(str(reading["ts"]))
            since = (tick_at.astimezone(_CHICAGO).date() - timedelta(days=3)).isoformat()
            events = conn.execute(
                "SELECT ts, message FROM event ORDER BY id DESC LIMIT ?", (_EVENTS,)
            ).fetchall()
            fill_rows = conn.execute(
                "SELECT day, delta_oz FROM event WHERE kind = 'fill' AND day >= ?", (since,)
            ).fetchall()
            # One index seek per logged day, so the page never walks every reading.
            days = conn.execute(
                """
                WITH RECURSIVE logged(day) AS (
                  SELECT min(day) FROM reading
                  UNION ALL
                  SELECT (SELECT min(day) FROM reading WHERE day > logged.day)
                  FROM logged WHERE logged.day IS NOT NULL
                )
                SELECT day FROM logged WHERE day IS NOT NULL
                """
            ).fetchall()
        finally:
            conn.execute("ROLLBACK")
        booked = _tenths(machine["booked_oz"])
        gauge = _tenths(reading["gauge_oz"])
        temp = reading["temp_c"]
        rss = reading["rss_mb"]
        # filled_oz / 5 * $0.50 is filled_oz * 10 cents, so these tenths are already coffee cents.
        filled_tenths = round(float(machine["filled_oz"]) * 10)
        live = _Live(
            tick_at=tick_at,
            booked=None if booked is None else _Ounces(booked),
            gauge=None if gauge is None else _Ounces(gauge),
            alarm_on=bool(machine["alarm"]),
            alarm_started=datetime.fromisoformat(str(machine["alarm_started"])),
            activity=_Activity[str(machine["activity"])],
            activity_started=datetime.fromisoformat(str(machine["activity_started"])),
            person=bool(machine["person"]),
            seen_today=int(machine["seen_today"]),
            refills_today=int(machine["refills_today"]),
            out_15m_tenths=round(float(machine["out_15m"]) * 10),
            out_today_tenths=round(float(machine["out_today"]) * 10),
            filled_tenths=filled_tenths,
            coffee_month_cents=round(float(machine["coffee_month"]) * 100),
            stale=int(machine["gap_ticks"]) >= 4 and int(machine["gap_person"]) == 0,
            unverified=int(machine["pending_count"]) > 0,
            timings=_Timings(
                capture_ms=int(reading["capture_ms"]),
                tank_ms=int(reading["tank_ms"]),
                person_ms=int(reading["person_ms"]),
                gauge_ms=int(reading["gauge_ms"]),
                ledger_ms=int(reading["ledger_ms"]),
                total_ms=int(reading["total_ms"]),
                rss_mb=None if rss is None else int(rss),
                temp_tenths=None if temp is None else round(float(temp) * 10),
            ),
        )
        log = tuple(
            _LogLine(datetime.fromisoformat(str(row["ts"])), str(row["message"])) for row in events
        )
        fills = tuple(
            _Fill(date.fromisoformat(str(row["day"])), round(float(row["delta_oz"]) * 10))
            for row in fill_rows
            if row["delta_oz"] is not None
        )
        logged = tuple(date.fromisoformat(str(row[0])) for row in days)
        return _Shown(live, log, logged, fills, shots)
    finally:
        conn.close()


def _band(booked: _Ounces) -> _Band:
    """Full at 52.5 and up, 3/4 from 35, 1/2 from 17.5, otherwise Low."""
    for edge, band in _BAND_EDGES:
        if booked.tenths >= edge:
            return band
    return _Band.LOW


def _model_line(gauge: _Ounces | None, booked: _Ounces | None) -> str | None:
    """`Model 47.3 fl oz` when both exist and the tenths differ. Otherwise hidden."""
    if gauge is None or booked is None or gauge.tenths == booked.tenths:
        return None
    return "Model " + _one_decimal(gauge)


def _elapsed(start: datetime, end: datetime) -> str:
    """Unpadded minutes and two-digit seconds. 15 seconds is `0:15`. 90 is `1:30`. 3725 is `1:02:05`."""
    seconds = max(0, int((end - start).total_seconds()))
    minutes, remain = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{remain:02d}"
    return f"{minutes}:{remain:02d}"


def _detail(activity: _Activity, started: datetime, tick: datetime) -> str:
    """Idle is `level still M:SS`. Brewing is `drop running M:SS`. Out is the elapsed time alone."""
    span = _elapsed(started, tick)
    if activity is _Activity.idle:
        return f"level still {span}"
    if activity is _Activity.brewing:
        return f"drop running {span}"
    return span


def _wall(at: datetime) -> _Wall:
    """Chicago wall time in English. Weekday and month come from the tuples above."""
    local = at.astimezone(_CHICAGO)
    hour = local.hour
    suffix = "AM" if hour < 12 else "PM"
    hour12 = hour % 12
    if hour12 == 0:
        hour12 = 12
    clock = f"{hour12}:{local.minute:02d}:{local.second:02d} {suffix}"
    date_line = f"{_WEEKDAYS[local.weekday()]} {local.day} {_MONTHS[local.month - 1]} {local.year}"
    return _Wall(local.isoformat(timespec="seconds"), date_line, clock)


def _prior(
    tick_at: datetime,
    logged_days: tuple[date, ...],
    fills: tuple[_Fill, ...],
) -> tuple[tuple[str, str], ...]:
    """The three Chicago dates before the tick, newest first."""
    day = tick_at.astimezone(_CHICAGO).date()
    rows: list[tuple[str, str]] = []
    for offset in (1, 2, 3):
        earlier = day - timedelta(days=offset)
        label = f"{_SHORT[earlier.weekday()]} {earlier.day}"
        if earlier not in logged_days:
            rows.append((label, "no rows"))
            continue
        cents = sum(fill.cents for fill in fills if fill.day == earlier)
        rows.append((label, _money(cents)))
    return tuple(rows)


def _money(cents: int) -> str:
    """540 is `$5.40`. 0 is `$0.00`."""
    sign = "-" if cents < 0 else ""
    amount = abs(cents)
    return f"{sign}${amount // 100}.{amount % 100:02d}"


def _one_decimal(ounces: _Ounces) -> str:
    """400 tenths is `40.0 fl oz`. Always one decimal."""
    sign = "-" if ounces.tenths < 0 else ""
    whole, frac = divmod(abs(ounces.tenths), 10)
    return f"{sign}{whole}.{frac} fl oz"


def _amount(tenths: int) -> str:
    """0 is `0`. 100 is `10`. 25 is `2.5`. No suffix."""
    sign = "-" if tenths < 0 else ""
    whole, frac = divmod(abs(tenths), 10)
    if frac == 0:
        return f"{sign}{whole}"
    return f"{sign}{whole}.{frac}"


def _temp(tenths: int) -> str:
    sign = "-" if tenths < 0 else ""
    whole, frac = divmod(abs(tenths), 10)
    return f"{sign}{whole}.{frac}\u00b0C"


def _timing_rows(timings: _Timings | None) -> tuple[tuple[str, str], ...]:
    """Capture, Tank, Person, Gauge, Ledger, Total, RSS, Temp, then Over 15 s."""
    if timings is None:
        values = ("", "", "", "", "", "", "", "")
    else:
        values = (
            f"{timings.capture_ms} ms",
            f"{timings.tank_ms} ms",
            f"{timings.person_ms} ms",
            f"{timings.gauge_ms} ms",
            f"{timings.ledger_ms} ms",
            f"{timings.total_ms} ms",
            "" if timings.rss_mb is None else f"{timings.rss_mb} MB",
            "" if timings.temp_tenths is None else _temp(timings.temp_tenths),
        )
    # Over 15 s is the literal 0. It is not total_ms and it is not a count of old rows.
    labels = ("Capture", "Tank", "Person", "Gauge", "Ledger", "Total", "RSS", "Temp", "Over 15 s")
    return tuple(zip(labels, (*values, "0")))


def _between(text: str, start: str, end: str, missing: str) -> str:
    at = text.find(start)
    if at < 0:
        raise RuntimeError(missing)
    stop = text.find(end, at + len(start))
    if stop < 0:
        raise RuntimeError(missing)
    return text[at : stop + len(end)]


@functools.cache
def _specimen() -> str:
    """CSS from `page/live.html` beside this file. The preview footer stays in that file."""
    text = Path(__file__).with_name("live.html").read_text(encoding="utf-8")
    return _between(text, "<style>", "</style>", "style block missing")


@functools.cache
def _hero() -> str:
    text = Path(__file__).with_name("live.html").read_text(encoding="utf-8")
    svg = _between(text, '<svg id="hero"', "</svg>", "hero svg missing")
    svg = svg.replace(
        'aria-label="Latest frame, 40.0 fluid ounces"',
        'aria-label="Latest frame"',
        1,
    )
    return svg.replace('<svg id="hero"', '<svg id="hero" hidden', 1)


def _esc(value: str) -> str:
    return html.escape(value, quote=True)


def _src(name: str) -> str:
    return "/frame/" + urllib.parse.quote(name, safe="")


def _flag(element_id: str, text: str, show: bool) -> str:
    hidden = "" if show else " hidden"
    return f'<p id="{element_id}" class="flag"{hidden}>{_esc(text)}</p>'


def _age(tick_at: datetime, now: datetime) -> str:
    """`Updated 7 s ago`, then minutes, then hours. The page script keeps it counting."""
    seconds = max(0, int((now - tick_at).total_seconds()))
    if seconds >= 3600:
        return f"Updated {seconds // 3600} h ago"
    if seconds >= 60:
        return f"Updated {seconds // 60} min ago"
    return f"Updated {seconds} s ago"


def _html(
    board: _Quiet | _Shown,
    selected: int | None,
    error: str | None = None,
    now: datetime | None = None,
) -> str:
    """The document. Live text is written here. Preview chrome is sliced from the specimen."""
    frames = board.frames
    earlier = selected is not None and selected != len(frames) - 1
    if now is None:
        now = datetime.now(_CHICAGO)
    if isinstance(board, _Quiet):
        age_html = '<p class="age" id="age"></p>'
        when = ""
        band_html = '<p class="band" id="band-name"></p>'
        ounces = ""
        model_html = '<p class="model" id="model-line" hidden></p>'
        out_15 = ""
        out_today = ""
        seen = ""
        refills = ""
        volume = ""
        bill = ""
        logged = ""
        monthly = ""
        alarm_on = False
        alarm_text = ""
        alarm_age = ""
        activity_text = ""
        activity_detail = ""
        person_html = '<p id="person-line"></p>'
        stale = False
        unverified = False
        prior = ()
        log_html = ""
        timings = _timing_rows(None)
    else:
        live = board.live
        wall = _wall(live.tick_at)
        age_html = (
            f'<p class="age" id="age" data-tick="{_esc(live.tick_at.isoformat())}">'
            f"{_esc(_age(live.tick_at, now))}</p>"
        )
        when = (
            f'<time datetime="{_esc(wall.attribute)}">'
            f"{_esc(wall.date_line)} {_DOT} {_esc(wall.clock)}</time>"
        )
        if live.booked is None:
            band_html = '<p class="band" id="band-name"></p>'
            ounces = ""
        else:
            band = _band(live.booked)
            low = " low" if band is _Band.LOW else ""
            band_html = f'<p class="band{low}" id="band-name">{_esc(band.value)}</p>'
            ounces = _one_decimal(live.booked)
        model = _model_line(live.gauge, live.booked)
        if model is None:
            model_html = '<p class="model" id="model-line" hidden></p>'
        else:
            model_html = f'<p class="model" id="model-line">{_esc(model)}</p>'
        out_15 = _amount(live.out_15m_tenths)
        out_today = _amount(live.out_today_tenths)
        seen = str(live.seen_today)
        refills = str(live.refills_today)
        volume = _amount(live.filled_tenths) + " fl oz"
        bill = _money(live.filled_tenths)
        count = len(board.logged_days)
        unit = "day" if count == 1 else "days"
        logged = f"Month {_DOT} {count} {unit}"
        monthly = _money(live.coffee_month_cents)
        alarm_on = live.alarm_on
        alarm_text = "On" if live.alarm_on else "Off"
        alarm_age = "for " + _elapsed(live.alarm_started, live.tick_at)
        activity_text = live.activity.value
        activity_detail = _detail(live.activity, live.activity_started, live.tick_at)
        if live.person:
            person_html = '<p id="person-line" class="yes">Yes</p>'
        else:
            person_html = '<p id="person-line">No</p>'
        stale = live.stale
        unverified = live.unverified
        prior = _prior(live.tick_at, board.logged_days, board.fills)
        lines = []
        for line in board.log:
            lines.append(
                f"<li><time>{_esc(_wall(line.at).clock)}</time>{_esc(line.message)}</li>"
            )
        log_html = "".join(lines)
        timings = _timing_rows(live.timings)

    classes: list[str] = []
    if alarm_on:
        classes.append("alarm")
    if earlier:
        classes.append("review")
    board_class = f' class="{" ".join(classes)}"' if classes else ""
    mark = "Earlier frame" if earlier else "Live"
    prior_html = "".join(f"<div><span>{_esc(label)}</span><b>{_esc(text)}</b></div>" for label, text in prior)
    tick_html = "".join(f"<li><span>{_esc(label)}</span><b>{_esc(value)}</b></li>" for label, value in timings)
    captions = _captions(len(frames))
    strip = []
    for index, (frame, caption) in enumerate(zip(frames, captions)):
        current = ' aria-current="page"' if index == selected else ""
        src = _esc(_src(frame.name))
        href = "/?frame=" + urllib.parse.quote(frame.name, safe="")
        strip.append(
            f'<a href="{_esc(href)}"{current}>'
            f'<img src="{src}" alt="{_esc(frame.name)}">'
            f'<span class="cap">{_esc(caption)}</span></a>'
        )
    photo = ""
    if selected is not None:
        name = frames[selected].name
        photo = f'<img id="frame" src="{_esc(_src(name))}" alt="{_esc(name)}">'
    style = _specimen()
    return (
        "<!doctype html>\n"
        '<html lang="en">\n'
        "<head>\n"
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        "<title>Coffee tank</title>\n"
        "<link rel=\"icon\" href=\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 16'%3E%3Crect width='16' height='16' fill='%23000'/%3E%3C/svg%3E\">\n"
        f"{style}\n"
        f"<style>{_PHOTO}</style>\n"
        "</head>\n"
        "<body>\n"
        f'<main id="board"{board_class}>\n'
        '<header id="top">\n'
        f'<p id="when">{when}</p>\n'
        '<div class="freshness">\n'
        f"{age_html}\n"
        f'<p class="live-mark" id="live-mark" data-mark="{_esc(mark)}">{_esc(mark)}</p>\n'
        "</div>\n"
        "</header>\n"
        '<section id="level" aria-label="Level">\n'
        '<p class="k">Level</p>\n'
        f"{band_html}\n"
        f'<p class="oz" id="ounces">{_esc(ounces)}</p>\n'
        f"{model_html}\n"
        '<dl class="rows">\n'
        f'<div><dt>15 min out</dt><dd id="out-15">{_esc(out_15)}</dd></div>\n'
        f'<div><dt>Today out</dt><dd id="out-today">{_esc(out_today)}</dd></div>\n'
        f'<div><dt>Seen today</dt><dd id="seen-today">{_esc(seen)}</dd></div>\n'
        f'<div><dt>Refills</dt><dd id="refill-today">{_esc(refills)}</dd></div>\n'
        f'<div><dt>Volume</dt><dd id="volume-today">{_esc(volume)}</dd></div>\n'
        f'<div><dt>Coffee today</dt><dd id="bill-today">{_esc(bill)}</dd></div>\n'
        f'<div><dt id="logged-days">{_esc(logged)}</dt><dd id="monthly">{_esc(monthly)}</dd></div>\n'
        "</dl>\n"
        "</section>\n"
        '<div id="scene">\n'
        f"{_hero()}\n"
        f"{photo}\n"
        f"{_flag('unverified', _UNVERIFIED, unverified)}\n"
        f"{_flag('stale-banner', _STALE, stale)}\n"
        f"{_flag('review', _REVIEW, earlier)}\n"
        f"{_flag('board-error', error or '', error is not None)}\n"
        "</div>\n"
        '<section id="status" aria-label="Alarm and activity">\n'
        '<div class="block" id="alarm-block">\n'
        '<p class="k">Alarm</p>\n'
        f'<p class="big" id="alarm-value">{_esc(alarm_text)}</p>\n'
        f'<p class="sub" id="alarm-age">{_esc(alarm_age)}</p>\n'
        "</div>\n"
        "<div class=\"block\">\n"
        '<p class="k">Activity</p>\n'
        f'<p class="big" id="activity-value">{_esc(activity_text)}</p>\n'
        f'<p class="sub" id="activity-detail">{_esc(activity_detail)}</p>\n'
        "</div>\n"
        "<div class=\"block\">\n"
        '<p class="k">Person right now</p>\n'
        f"{person_html}\n"
        "</div>\n"
        '<div class="block log-block" id="log-block">\n'
        '<p class="k">Events</p>\n'
        f'<ol id="events">{log_html}</ol>\n'
        "</div>\n"
        "</section>\n"
        '<footer id="dock">\n'
        f'<div class="prior" id="prior">{prior_html}</div>\n'
        f'<ul class="ticks" id="ticks">{tick_html}</ul>\n'
        '<div id="strip" role="listbox" aria-label="Last 8 frames. The last one is the most recent.">'
        f"{''.join(strip)}</div>\n"
        "</footer>\n"
        "</main>\n"
        f"<script>{_SCRIPT}</script>\n"
        "</body>\n"
        "</html>\n"
    )


if __name__ == "__main__":
    root = Path(__file__).resolve().parent.parent
    serve(root / "learn" / "tank.sqlite", root / "learn" / "frames", 8080).wait()
