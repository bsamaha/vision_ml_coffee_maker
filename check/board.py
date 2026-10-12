"""One tick of the coffee-tank board, and the Pi process that runs it.

Tests call tick with JPEG bytes and sight.Box values. The Pi runs main, which
is the only function that opens the camera and loads the Workflow.
"""

from __future__ import annotations

import sqlite3
import sys
import threading
import time
import traceback
from collections.abc import Sequence
from datetime import datetime, timedelta
from pathlib import Path
from typing import NamedTuple
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))

import ledger
import loop
import sight

__all__ = ["tick", "main", "Elapsed", "rss_mb", "temp_c", "cpu_times", "cpu_pct", "mem_free_pct"]

CHICAGO = ZoneInfo("America/Chicago")
# This long with no new frame means the camera stopped.
CAMERA_QUIET_S = 10
# Shortest gap between tick starts. The brew rule needs two ticks in a row that each fall
# more than 0.5 fl oz, and a Classic brew falls about 3 to 5 fl oz a minute. At the ~3.5 s the
# Workflow takes on its own, a brew falls under 0.5 a tick and seldom reads as Brewing.
MIN_TICK_S = 7.5
_WORKFLOW_MODE = "Roboflow Workflow on local Inference"


class Elapsed(NamedTuple):
    # How old the frame was when the tick took it.
    capture_ms: int
    tank_ms: int
    person_ms: int


def rss_mb(status: Path = Path("/proc/self/status")) -> int | None:
    try:
        for line in status.read_text(encoding="utf-8").splitlines():
            if line.startswith("VmRSS:"):
                return round(int(line.split()[1]) / 1024)
    except (OSError, ValueError, IndexError):
        return None
    return None


def temp_c(zone: Path = Path("/sys/class/thermal/thermal_zone0/temp")) -> float | None:
    try:
        return round(int(zone.read_text(encoding="utf-8").strip()) / 1000, 1)
    except (OSError, ValueError):
        return None


def cpu_times(stat: Path = Path("/proc/stat")) -> tuple[int, int] | None:
    """(idle, total) jiffies across all cores. Idle includes iowait."""
    try:
        fields = stat.read_text(encoding="utf-8").splitlines()[0].split()
        if fields[0] != "cpu":
            return None
        counts = [int(value) for value in fields[1:9]]
    except (OSError, ValueError, IndexError):
        return None
    return counts[3] + counts[4], sum(counts)


def cpu_pct(before: tuple[int, int] | None, after: tuple[int, int] | None) -> float | None:
    """Whole-Pi CPU use between two `cpu_times` samples."""
    if before is None or after is None:
        return None
    total = after[1] - before[1]
    if total <= 0:
        return None
    return round(100 * (1 - (after[0] - before[0]) / total), 1)


def mem_free_pct(meminfo: Path = Path("/proc/meminfo")) -> float | None:
    values: dict[str, int] = {}
    try:
        for line in meminfo.read_text(encoding="utf-8").splitlines():
            key, _, rest = line.partition(":")
            if key in ("MemTotal", "MemAvailable"):
                values[key] = int(rest.split()[0])
    except (OSError, ValueError, IndexError):
        return None
    if values.get("MemTotal", 0) <= 0 or "MemAvailable" not in values:
        return None
    return round(100 * values["MemAvailable"] / values["MemTotal"], 1)


def detections(
    boxes: Sequence[sight.Box], seen: sight.Seen, size: tuple[int, int]
) -> dict:
    """What the page draws over this frame. Coordinates are pixels of the saved JPEG."""
    used = set(sight.chosen(boxes))
    return {
        "width": size[0],
        "height": size[1],
        "gauge_oz": seen.gauge_oz,
        "boxes": [
            {
                "name": box.name,
                "score": round(box.score, 3),
                "x0": round(box.x0, 1),
                "y0": round(box.y0, 1),
                "x1": round(box.x1, 1),
                "y1": round(box.y1, 1),
                "used": box in used,
            }
            for box in boxes
        ],
    }


def tick(
    db: sqlite3.Connection,
    frames: Path,
    jpeg: bytes,
    boxes: Sequence[sight.Box],
    at: datetime,
    elapsed: Elapsed = Elapsed(0, 0, 0),
    size: tuple[int, int] = (1280, 720),
    memory_mb: int | None = None,
    cpu_c: float | None = None,
    cpu_use: float | None = None,
    memory_free: float | None = None,
    seen: sight.Seen | None = None,
) -> ledger.Applied:
    """`seen` is the Workflow's TankGauge output. Without it the gauge is read from `boxes` here."""
    started = time.perf_counter()
    if seen is None:
        seen = sight.seen(boxes)
    gauge_ms = round((time.perf_counter() - started) * 1000)
    one = ledger.Tick(
        at=at,
        gauge_oz=seen.gauge_oz,
        person=seen.person,
        capture_ms=elapsed.capture_ms,
        tank_ms=elapsed.tank_ms,
        person_ms=elapsed.person_ms,
        gauge_ms=gauge_ms,
        rss_mb=memory_mb,
        temp_c=cpu_c,
        cpu_pct=cpu_use,
        mem_free_pct=memory_free,
    )
    return loop.record(db, frames, jpeg, one, detections(boxes, seen, size))


def main() -> None:
    import cv2
    import numpy as np

    import camera
    import workflow

    root = Path(__file__).resolve().parent.parent
    db_path = root / "learn" / "tank.sqlite"
    frames = root / "learn" / "frames"
    sys.path.insert(0, str(root / "page"))
    import live

    error_file = live.error_path(db_path)
    mode_file = live.mode_path(db_path)
    shown: str | None = "unknown"

    def report(text: str | None) -> None:
        """One line on the board saying why it is not ticking. None clears it."""
        nonlocal shown
        if text == shown:
            return
        shown = text
        if text is None:
            error_file.unlink(missing_ok=True)
            return
        print(text, file=sys.stderr, flush=True)
        error_file.parent.mkdir(parents=True, exist_ok=True)
        error_file.write_text(text + "\n", encoding="utf-8")

    def announce(text: str) -> None:
        """What the board is running, shown under the photo."""
        print(text, file=sys.stderr, flush=True)
        mode_file.parent.mkdir(parents=True, exist_ok=True)
        mode_file.write_text(text + "\n", encoding="utf-8")

    report(None)
    mode_file.unlink(missing_ok=True)
    serving = live.serve(db_path, frames, 8080)
    db = None
    try:
        threading.Thread(target=camera.run, daemon=True).start()
        try:
            announce("Loading the Roboflow Workflow")
            key = workflow.api_key()
            if key is None:
                raise RuntimeError("no ROBOFLOW_API_KEY in the environment or ~/tank-envs/roboflow.env")
            runner = workflow.Runner(key)
            # The first run downloads and loads both models. Do it before the first tick.
            runner.run(np.zeros((720, 1280, 3), dtype=np.uint8))
            announce(_WORKFLOW_MODE)
            db = ledger.connect(db_path)
        except Exception as error:
            traceback.print_exc()
            mode_file.unlink(missing_ok=True)
            report(f"The board did not start: {error}. See /tmp/preview.log.")
            serving.wait()
            return
        last_seq = -1
        waiting_since = time.monotonic()
        next_tick = 0.0
        last_cpu = cpu_times()
        while True:
            early = next_tick - time.monotonic()
            if early > 0:
                time.sleep(min(early, 0.2))
                continue
            frame = camera.newest()
            if frame is None or frame.seq == last_seq:
                quiet = time.monotonic() - waiting_since
                if quiet > CAMERA_QUIET_S:
                    report(f"No new camera picture for {int(quiet)} s. Check the webcam on /dev/video0.")
                time.sleep(0.2)
                continue
            last_seq = frame.seq
            waiting_since = time.monotonic()
            next_tick = waiting_since + MIN_TICK_S
            taken = datetime.now(CHICAGO) - timedelta(seconds=frame.age_s)
            try:
                image = cv2.imdecode(np.frombuffer(frame.jpeg, dtype=np.uint8), cv2.IMREAD_COLOR)
                if image is None:
                    raise ValueError("The camera frame is not a readable JPEG.")
                result = runner.run(image)
                now_cpu = cpu_times()
                use = cpu_pct(last_cpu, now_cpu)
                last_cpu = now_cpu
                height, width = image.shape[:2]
                tick(
                    db,
                    frames,
                    frame.jpeg,
                    result.boxes,
                    taken,
                    Elapsed(round(frame.age_s * 1000), result.tank_ms, result.person_ms),
                    (int(width), int(height)),
                    rss_mb(),
                    temp_c(),
                    use,
                    mem_free_pct(),
                    sight.Seen(result.gauge_oz, result.person),
                )
            except Exception as error:
                traceback.print_exc()
                report(f"The last tick failed: {type(error).__name__}: {error}")
                time.sleep(1)
                continue
            report(None)
    except KeyboardInterrupt:
        pass
    finally:
        try:
            if db is not None:
                db.close()
        finally:
            serving.close()


if __name__ == "__main__":
    main()
