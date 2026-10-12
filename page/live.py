"""The live board.

One process reads the ledger database and the frame directory. It does not write either.
Import serve and Serving. Each request opens its own read-only SQLite connection.

Production, from the repo root:

    python page/live.py
"""

from __future__ import annotations

import functools
import html
import json
import math
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
_STALE = "Reservoir not in view. Holding the last level."
_UNVERIFIED = "Level jumped without a refill. Not billed. Confirming."
_REVIEW = "Earlier frame. The numbers stay live."
_DOT = "\u00b7"
_EVENTS = 50
_DEVICE_WINDOW = timedelta(minutes=2)
_RATE_WINDOW = timedelta(minutes=2)
# The rate needs at least this much history, or two noisy readings would set it.
_RATE_MIN_SPAN = timedelta(seconds=60)
# Below this the tank is not draining. Model wobble alone moves the net fall a few tenths.
_DRAINING = 0.2
# Readings read for the device row. 2 minutes at the 7.5 s floor is 16, so this always covers it.
_DEVICE_ROWS = 40
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
      const diag = document.getElementById("diag");
      const open = diag ? diag.open : false;
      document.getElementById("board").replaceWith(fresh);
      for (const id in kept) {{
        const now = document.getElementById(id);
        if (now) now.scrollTop = kept[id];
      }}
      const nextDiag = document.getElementById("diag");
      if (nextDiag) nextDiag.open = open;
      boxes();
    }} catch (error) {{
      return;
    }} finally {{
      age();
    }}
  }}
  function boxes() {{
    const off = localStorage.getItem("detections") === "off";
    document.getElementById("board").classList.toggle("no-boxes", off);
    const button = document.getElementById("boxes-toggle");
    if (button) button.setAttribute("aria-pressed", off ? "false" : "true");
  }}
  document.addEventListener("click", function (event) {{
    if (!event.target.closest("#boxes-toggle")) return;
    const off = localStorage.getItem("detections") === "off";
    localStorage.setItem("detections", off ? "on" : "off");
    boxes();
  }});
  boxes();
  age();
  setInterval(age, 1000);
  setInterval(poll, {_POLL_S * 1000});
}})();
"""
_ERROR_FILE = "board-error.txt"
_PHOTO = """
#scene { container-type: size; }
.shot { position: relative; flex: none; }
.shot #frame {
  display: block;
  width: 100%;
  height: 100%;
  border-radius: 10px;
  box-shadow: 0 12px 40px rgba(0, 0, 0, .6);
}
.overlay {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  pointer-events: none;
  font: 700 30px ui-sans-serif, system-ui, sans-serif;
}
.overlay rect { fill: none; stroke-width: 2.5; vector-effect: non-scaling-stroke; }
.overlay text { paint-order: stroke; stroke: rgba(0, 0, 0, .85); stroke-width: 7px; stroke-linejoin: round; }
.overlay .reservoir rect { stroke: var(--info); fill: rgba(98, 172, 255, .06); }
.overlay .reservoir text { fill: var(--info); }
.overlay .liquid rect { stroke: var(--crema); fill: rgba(219, 168, 110, .16); }
.overlay .liquid text { fill: #ffe2bf; }
.overlay .surface { stroke: #fff1dc; stroke-width: 3; vector-effect: non-scaling-stroke; }
.overlay .person rect { stroke: var(--ok); fill: rgba(63, 208, 127, .07); }
.overlay .person text { fill: var(--ok); }
.overlay .spare rect { stroke-dasharray: 4 4; opacity: .55; }
.overlay .spare text { opacity: .55; }
#board.no-boxes .overlay { display: none; }
.boxes-toggle {
  position: absolute;
  z-index: 3;
  top: 24px;
  right: 24px;
  padding: 7px 12px;
  border: 1px solid rgba(98, 172, 255, .45);
  border-radius: 999px;
  background: rgba(10, 14, 20, .8);
  color: #cfe4ff;
  font: 700 11px/1 ui-sans-serif, system-ui, sans-serif;
  letter-spacing: .08em;
  text-transform: uppercase;
  cursor: pointer;
}
.boxes-toggle[aria-pressed="false"] { border-color: var(--line); color: var(--muted); }
#board-error { top: 64px; }
@media (max-width: 860px) {
  #scene { container-type: inline-size; }
  .shot { width: 100% !important; }
  .boxes-toggle { top: 16px; right: 16px; }
}
#frame[hidden],
#hero[hidden] {
  display: none !important;
}
#strip a {
  flex: 1 1 0;
  min-width: 0;
  padding: 4px 4px 6px;
  border: 1px solid var(--line);
  border-radius: 10px;
  background: var(--tile);
  color: var(--muted);
  cursor: pointer;
  text-decoration: none;
  transition: border-color .15s ease;
}
#strip a:hover { border-color: #3a414b; }
#strip a[aria-current="page"] {
  border-color: var(--crema);
  box-shadow: 0 0 0 1px var(--crema);
  color: var(--text);
}
#strip img {
  display: block;
  width: 100%;
  height: 56px;
  object-fit: cover;
  border-radius: 6px;
}
"""
_CUP_ICON = (
    '<svg class="brand-mark" viewBox="0 0 24 24" aria-hidden="true">'
    '<path d="M3.5 9h13v4.5a6 6 0 0 1-6 6h-1a6 6 0 0 1-6-6z" fill="currentColor"/>'
    '<path d="M16.5 10.5h1.25a2.75 2.75 0 0 1 0 5.5H16" fill="none" stroke="currentColor" stroke-width="2"/>'
    '<path d="M7.5 2.5c-.9 1.2.9 2.3 0 3.5M11 2.5c-.9 1.2.9 2.3 0 3.5" fill="none" '
    'stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg>'
)


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


class _Device(NamedTuple):
    """The Pi over the readings of the last `_DEVICE_WINDOW`. None where no reading had it."""

    cpu_pct: float | None
    temp_c: float | None
    mem_free_pct: float | None
    tank_ms: int | None
    person_ms: int | None
    every_s: float | None
    count: int


class _Rate(NamedTuple):
    """Net fall of booked ounces over the last `_RATE_WINDOW`, per minute. None without enough history."""

    oz_per_min: float | None
    empty_min: float | None


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
    device: _Device
    rate: _Rate


class _LogLine(NamedTuple):
    at: datetime
    kind: str
    message: str


class _Frame(NamedTuple):
    """Basename of a JPEG in the frames directory, and its mtime. No slash."""

    name: str
    mtime: float


class _Quiet(NamedTuple):
    """No machine row, or no reading. Frames may still be on disk. No ounces exist here."""

    frames: tuple[_Frame, ...]


class _Shown(NamedTuple):
    """One tick the ledger has finished writing. `log` is the newest `_EVENTS` lines."""

    live: _Live
    log: tuple[_LogLine, ...]
    logged_days: tuple[date, ...]
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
            boxes = None if selected is None else _detections(server.frames, board.frames[selected].name)
            body = _html(board, selected, _board_error(server.error), detections=boxes).encode("utf-8")
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
    return tuple(_Frame(name, mtime) for mtime, name in newest)


def _captions(frames: tuple[_Frame, ...]) -> tuple[str, ...]:
    """How much older each frame is than the newest. The newest is Now. `-53 s`, then `-1:05`."""
    if not frames:
        return ()
    newest = frames[-1].mtime
    captions = []
    for frame in frames[:-1]:
        seconds = max(0, round(newest - frame.mtime))
        if seconds < 60:
            captions.append(f"-{seconds} s")
        else:
            captions.append(f"-{seconds // 60}:{seconds % 60:02d}")
    return (*captions, "Now")


def _tenths(value: float | None) -> int | None:
    if value is None:
        return None
    return round(value * 10)


def _load(db: Path, frames: Path) -> _Quiet | _Shown:
    """Parse one committed tick into a board. Four bounded statements, one read transaction."""
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
            # SELECT * so a file the board has not migrated yet still loads without the new columns.
            recent = conn.execute(
                "SELECT * FROM reading ORDER BY id DESC LIMIT ?", (_DEVICE_ROWS,)
            ).fetchall()
            reading = recent[0] if recent else None
            if machine is None or reading is None:
                return _Quiet(shots)
            tick_at = datetime.fromisoformat(str(reading["ts"]))
            events = conn.execute(
                "SELECT ts, kind, message FROM event ORDER BY id DESC LIMIT ?", (_EVENTS,)
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
            device=_device(recent, tick_at),
            rate=_rate(recent, tick_at),
        )
        log = tuple(
            _LogLine(datetime.fromisoformat(str(row["ts"])), str(row["kind"]), str(row["message"]))
            for row in events
        )
        logged = tuple(date.fromisoformat(str(row[0])) for row in days)
        return _Shown(live, log, logged, shots)
    finally:
        conn.close()


def _column(row: sqlite3.Row, name: str) -> float | None:
    if name not in row.keys() or row[name] is None:
        return None
    return float(row[name])


def _device(rows: list[sqlite3.Row], tick_at: datetime) -> _Device:
    """CPU use and model times averaged over the last two minutes. Temperature and memory are the newest."""
    since = tick_at - _DEVICE_WINDOW
    window = [row for row in rows if datetime.fromisoformat(str(row["ts"])) >= since]

    def mean(name: str) -> float | None:
        values = [value for value in (_column(row, name) for row in window) if value is not None]
        return sum(values) / len(values) if values else None

    times = sorted(datetime.fromisoformat(str(row["ts"])) for row in window)
    every = None
    if len(times) > 1:
        every = (times[-1] - times[0]).total_seconds() / (len(times) - 1)
    tank = mean("tank_ms")
    person = mean("person_ms")
    return _Device(
        cpu_pct=mean("cpu_pct"),
        temp_c=_column(rows[0], "temp_c"),
        mem_free_pct=_column(rows[0], "mem_free_pct"),
        tank_ms=None if tank is None else round(tank),
        person_ms=None if person is None else round(person),
        every_s=every,
        count=len(window),
    )


def _rate(rows: list[sqlite3.Row], tick_at: datetime) -> _Rate:
    """Net, not summed, so tick-to-tick wobble cancels instead of adding up. A rise reads as 0."""
    since = tick_at - _RATE_WINDOW
    booked = [
        (datetime.fromisoformat(str(row["ts"])), float(row["booked_oz"]))
        for row in rows
        if row["booked_oz"] is not None and datetime.fromisoformat(str(row["ts"])) >= since
    ]
    if len(booked) < 2:
        return _Rate(None, None)
    booked.sort()
    (first_at, first), (last_at, last) = booked[0], booked[-1]
    span = last_at - first_at
    if span < _RATE_MIN_SPAN:
        return _Rate(None, None)
    per_min = max(0.0, (first - last) / (span.total_seconds() / 60))
    empty = last / per_min if per_min >= _DRAINING else None
    return _Rate(per_min, empty)


def _rate_text(rate: _Rate) -> tuple[str, str]:
    """(`4.6 fl oz/min`, `About 4 min`). Blank before there is enough history."""
    if rate.oz_per_min is None:
        return "", ""
    per_min = f"{rate.oz_per_min:.1f} fl oz/min"
    if rate.empty_min is None:
        return per_min, "Not draining"
    minutes = round(rate.empty_min)
    if minutes < 1:
        return per_min, "Under a minute"
    if minutes < 90:
        return per_min, f"About {minutes} min"
    return per_min, f"About {rate.empty_min / 60:.1f} h"


def _device_rows(device: _Device | None) -> tuple[tuple[str, str, str], ...]:
    """(id, label, value). Blank values on a quiet board."""

    def seconds(ms: int | None) -> str:
        return "" if ms is None else f"{ms / 1000:.2f} s"

    def percent(value: float | None) -> str:
        return "" if value is None else f"{value:.0f}%"

    if device is None:
        device = _Device(None, None, None, None, None, None, 0)
    temp = "" if device.temp_c is None else f"{device.temp_c:.1f}\u00b0C"
    every = "" if device.every_s is None else f"{device.every_s:.1f} s"
    return (
        ("device-cpu", "CPU use", percent(device.cpu_pct)),
        ("device-temp", "CPU temp", temp),
        ("device-memory", "Memory free", percent(device.mem_free_pct)),
        ("device-tank", "Tank model", seconds(device.tank_ms)),
        ("device-person", "Person model", seconds(device.person_ms)),
        ("device-every", "Reading every", every),
    )


def _band(booked: _Ounces) -> _Band:
    """Full at 52.5 and up, 3/4 from 35, 1/2 from 17.5, otherwise Low."""
    for edge, band in _BAND_EDGES:
        if booked.tenths >= edge:
            return band
    return _Band.LOW


def _model_line(gauge: _Ounces | None, booked: _Ounces | None) -> str | None:
    """`Camera reads 47.3 fl oz` when both exist and the tenths differ. Otherwise hidden."""
    if gauge is None or booked is None or gauge.tenths == booked.tenths:
        return None
    return "Camera reads " + _one_decimal(gauge)


def _elapsed(start: datetime, end: datetime) -> str:
    """Unpadded minutes and two-digit seconds. 15 seconds is `0:15`. 90 is `1:30`. 3725 is `1:02:05`."""
    seconds = max(0, int((end - start).total_seconds()))
    minutes, remain = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{remain:02d}"
    return f"{minutes}:{remain:02d}"


def _detail(activity: _Activity, started: datetime, tick: datetime) -> str:
    """Idle is `Steady for M:SS`. Brewing is `Falling for M:SS`. Out is `Out for M:SS`."""
    span = _elapsed(started, tick)
    if activity is _Activity.idle:
        return f"Steady for {span}"
    if activity is _Activity.brewing:
        return f"Falling for {span}"
    return f"Out for {span}"


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
    """Frame age, Tank, Person, Gauge, Ledger, Total, RSS, Temp, then Over 15 s."""
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
    labels = ("Frame age", "Tank", "Person", "Gauge", "Ledger", "Total", "RSS", "Temp", "Over 15 s")
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


def _detections(folder: Path, name: str) -> dict | None:
    """The boxes the board saved beside this frame, or None for a frame without them."""
    try:
        data = json.loads((folder / name).with_suffix(".json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _number(value: object, fallback: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return fallback
    return float(value)


def _overlay(data: dict) -> tuple[str, float, float]:
    """SVG in the frame's pixel space, plus that frame's width and height."""
    width = _number(data.get("width"), 1280) or 1280
    height = _number(data.get("height"), 720) or 720
    raw = data.get("boxes")
    boxes = [box for box in raw if isinstance(box, dict)] if isinstance(raw, list) else []
    gauge = data.get("gauge_oz")
    reservoir = None
    shapes: list[str] = []
    labels: list[str] = []
    # Only the classes the board reads. The person model's other COCO classes stay in the JSON.
    kinds = {"person": "person", "Reservoir": "reservoir", "liquid-level": "liquid"}
    order = list(kinds)
    boxes = [box for box in boxes if isinstance(box.get("name"), str) and box["name"] in kinds]
    boxes.sort(key=lambda box: order.index(box["name"]))
    for box in boxes:
        name = str(box["name"])
        x0 = _number(box.get("x0"), 0)
        y0 = _number(box.get("y0"), 0)
        x1 = _number(box.get("x1"), x0)
        y1 = _number(box.get("y1"), y0)
        score = _number(box.get("score"), 0)
        used = box.get("used") is True
        group = kinds[name]
        classes = group if used else f"{group} spare"
        if group == "reservoir" and used:
            reservoir = (x0, x1)
        text = f"{name} {score:.2f}"
        if group == "liquid" and used and isinstance(gauge, (int, float)):
            text = f"Water line {score:.2f} \u00b7 {gauge:.1f} fl oz \u00b7 {gauge / 70 * 100:.0f}%"
        label_y = max(y0 - 10, 28)
        if group == "liquid":
            label_y = y0 + 34
        shapes.append(
            f'<g class="{classes}"><rect x="{x0:.1f}" y="{y0:.1f}" '
            f'width="{max(x1 - x0, 0):.1f}" height="{max(y1 - y0, 0):.1f}" rx="4"/></g>'
        )
        if group == "liquid" and used:
            shapes.append(f'<line class="surface" x1="{x0:.1f}" x2="{x1:.1f}" y1="{y0:.1f}" y2="{y0:.1f}"/>')
        labels.append(
            f'<g class="{classes}"><text x="{x0 + 8:.1f}" y="{label_y:.1f}">{_esc(text)}</text></g>'
        )
    if reservoir is None:
        labels.append('<g class="reservoir"><text x="24" y="44">No reservoir found</text></g>')
    svg = (
        f'<svg class="overlay" id="overlay" viewBox="0 0 {width:.0f} {height:.0f}" '
        'preserveAspectRatio="none" aria-hidden="true">'
        f"{''.join(shapes)}{''.join(labels)}</svg>"
    )
    return svg, width, height


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
    detections: dict | None = None,
) -> str:
    """The document. Live text is written here. Preview chrome is sliced from the specimen."""
    frames = board.frames
    earlier = selected is not None and selected != len(frames) - 1
    if now is None:
        now = datetime.now(_CHICAGO)
    gauge_fill = 0.0
    gauge_low = False
    activity_class = ""
    if isinstance(board, _Quiet):
        age_html = '<p class="age" id="age"></p>'
        when = ""
        band_html = '<p class="band" id="band-name"></p>'
        ounces = ""
        model_html = '<p class="model" id="model-line" hidden></p>'
        out_15 = ""
        out_today = ""
        use_rate = ""
        empty_in = ""
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
            gauge_fill = max(0.0, min(100.0, live.booked.tenths / 7))
            gauge_low = band is _Band.LOW
            low = " low" if band is _Band.LOW else ""
            band_html = f'<p class="band{low}" id="band-name">{_esc(band.value)}</p>'
            ounces = _one_decimal(live.booked)
        model = _model_line(live.gauge, live.booked)
        if model is None:
            model_html = '<p class="model" id="model-line" hidden></p>'
        else:
            model_html = f'<p class="model" id="model-line">{_esc(model)}</p>'
        out_15 = _one_decimal(_Ounces(live.out_15m_tenths))
        out_today = _one_decimal(_Ounces(live.out_today_tenths))
        use_rate, empty_in = _rate_text(live.rate)
        seen = str(live.seen_today)
        refills = str(live.refills_today)
        volume = _one_decimal(_Ounces(live.filled_tenths))
        bill = _money(live.filled_tenths)
        count = len(board.logged_days)
        unit = "day" if count == 1 else "days"
        logged = f"Monthly estimate ({count} {unit} of data)"
        monthly = _money(live.coffee_month_cents)
        alarm_on = live.alarm_on
        alarm_text = "On" if live.alarm_on else "Off"
        alarm_age = "for " + _elapsed(live.alarm_started, live.tick_at)
        activity_text = live.activity.value
        activity_class = f" act-{live.activity.name}"
        activity_detail = _detail(live.activity, live.activity_started, live.tick_at)
        if live.person:
            person_html = '<p id="person-line" class="yes">Yes</p>'
        else:
            person_html = '<p id="person-line">No</p>'
        stale = live.stale
        unverified = live.unverified
        lines = []
        for line in board.log:
            lines.append(
                f'<li class="ev-{_esc(line.kind)}"><time>{_esc(_wall(line.at).clock)}</time>'
                f"{_esc(line.message)}</li>"
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
    tick_html = "".join(f"<li><span>{_esc(label)}</span><b>{_esc(value)}</b></li>" for label, value in timings)
    device = None if isinstance(board, _Quiet) else board.live.device
    heat = ""
    if device is not None and device.temp_c is not None:
        # The Pi 4 soft-throttles at 80 C.
        heat = "hot" if device.temp_c >= 80 else "warm" if device.temp_c >= 75 else ""
    stats = []
    for element_id, label, value in _device_rows(device):
        tone = f' class="{heat}"' if element_id == "device-temp" and heat else ""
        stats.append(f'<div><dt>{_esc(label)}</dt><dd id="{element_id}"{tone}>{_esc(value)}</dd></div>')
    device_html = "".join(stats)
    captions = _captions(frames)
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
        overlay, width, height = ("", 1280.0, 720.0)
        toggle = ""
        if detections is not None:
            overlay, width, height = _overlay(detections)
            toggle = (
                '<button type="button" class="boxes-toggle" id="boxes-toggle" aria-pressed="true">'
                "Detections</button>"
            )
        ratio = width / height
        photo = (
            f'<div class="shot" style="aspect-ratio: {width:.0f} / {height:.0f}; '
            f'width: min(100cqw, calc(100cqh * {ratio:.4f}))">'
            f'<img id="frame" src="{_esc(_src(name))}" alt="{_esc(name)}">'
            f"{overlay}</div>{toggle}"
        )
    gauge_class = "gauge low" if gauge_low else "gauge"
    gauge_html = (
        f'<div class="{gauge_class}" id="gauge" style="--fill: {gauge_fill:.1f}%" aria-hidden="true">'
        '<div class="gauge-fill"></div>'
        '<i style="bottom: 75%"></i><i style="bottom: 50%"></i>'
        '<i class="alarm-line" style="bottom: 25%"></i></div>'
    )
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
        '<div class="brand">\n'
        f"{_CUP_ICON}\n"
        '<div class="brand-text">\n'
        '<p class="brand-name">Coffee tank</p>\n'
        f'<p id="when">{when}</p>\n'
        "</div>\n"
        "</div>\n"
        '<div class="freshness">\n'
        f"{age_html}\n"
        f'<p class="live-mark" id="live-mark" data-mark="{_esc(mark)}">{_esc(mark)}</p>\n'
        "</div>\n"
        "</header>\n"
        '<section id="level" aria-label="Level">\n'
        '<div class="level-head">\n'
        "<div>\n"
        '<p class="k">Level</p>\n'
        f"{band_html}\n"
        f'<p class="oz" id="ounces">{_esc(ounces)}</p>\n'
        f"{model_html}\n"
        "</div>\n"
        f"{gauge_html}\n"
        "</div>\n"
        '<dl class="rows">\n'
        f'<div><dt>Used, last 15 min</dt><dd id="out-15">{_esc(out_15)}</dd></div>\n'
        f'<div><dt>Used today</dt><dd id="out-today">{_esc(out_today)}</dd></div>\n'
        f'<div><dt>Use rate, last 2 min</dt><dd id="use-rate">{_esc(use_rate)}</dd></div>\n'
        f'<div><dt>Empty in</dt><dd id="empty-in">{_esc(empty_in)}</dd></div>\n'
        f'<div><dt>People seen today</dt><dd id="seen-today">{_esc(seen)}</dd></div>\n'
        f'<div><dt>Refills today</dt><dd id="refill-today">{_esc(refills)}</dd></div>\n'
        f'<div><dt>Refilled today</dt><dd id="volume-today">{_esc(volume)}</dd></div>\n'
        f'<div><dt>Refill bill today</dt><dd id="bill-today">{_esc(bill)}</dd></div>\n'
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
        '<p class="k">Refill alarm</p>\n'
        f'<p class="big" id="alarm-value">{_esc(alarm_text)}</p>\n'
        f'<p class="sub" id="alarm-age">{_esc(alarm_age)}</p>\n'
        "</div>\n"
        "<div class=\"block\">\n"
        '<p class="k">Activity</p>\n'
        f'<p class="big{activity_class}" id="activity-value">{_esc(activity_text)}</p>\n'
        f'<p class="sub" id="activity-detail">{_esc(activity_detail)}</p>\n'
        "</div>\n"
        "<div class=\"block\">\n"
        '<p class="k">Person in view</p>\n'
        f"{person_html}\n"
        "</div>\n"
        '<div class="block log-block" id="log-block">\n'
        '<p class="k">Events</p>\n'
        f'<ol id="events">{log_html}</ol>\n'
        "</div>\n"
        "</section>\n"
        '<footer id="dock">\n'
        '<div class="dock-row">\n'
        '<section class="device" aria-label="Raspberry Pi">\n'
        '<p class="device-title">Raspberry Pi 4 <span>model times and CPU use averaged over 2 min</span></p>\n'
        f'<dl class="device-stats">{device_html}</dl>\n'
        "</section>\n"
        '<details class="diag" id="diag">\n'
        "<summary>Timing</summary>\n"
        f'<ul class="ticks" id="ticks">{tick_html}</ul>\n'
        "</details>\n"
        "</div>\n"
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
