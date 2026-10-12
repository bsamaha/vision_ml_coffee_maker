"""One tick of the coffee-tank board, and the Pi process that runs it.

Tests call tick with JPEG bytes and sight.Box values. The Pi runs main, which
is the only function that opens the camera and loads weights.
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

__all__ = ["tick", "main", "Elapsed", "thinned", "rss_mb", "temp_c"]

CHICAGO = ZoneInfo("America/Chicago")
# The webcam only offers 1280x720 MJPEG at 60 fps, whatever -framerate asks for.
# A tick takes one frame every ~7 s, so ffmpeg flips and encodes only this many a second.
BOARD_FPS = 2
# This long with no new frame means the camera stopped.
CAMERA_QUIET_S = 10


class Elapsed(NamedTuple):
    # How old the frame was when the tick took it.
    capture_ms: int
    tank_ms: int
    person_ms: int


def thinned(command: Sequence[str], fps: int) -> list[str]:
    """The capture ffmpeg command with an fps filter ahead of the flip."""
    out = list(command)
    at = out.index("-vf")
    out[at + 1] = f"fps={fps}," + out[at + 1]
    return out


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
            if box.name != "__background__"
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
) -> ledger.Applied:
    started = time.perf_counter()
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
    )
    return loop.record(db, frames, jpeg, one, detections(boxes, seen, size))


def main() -> None:
    class Models(NamedTuple):
        tank: object
        person: object
        # predict renames the last logit to __background__. labels_for indexes
        # this table, which still has the background line. load_model does not.
        id_names: tuple[str, ...]

    class Grab(NamedTuple):
        jpeg: bytes
        capture_ms: int
        seq: int
        taken: datetime

    class Passes(NamedTuple):
        boxes: tuple[sight.Box, ...]
        tank_ms: int
        person_ms: int
        size: tuple[int, int]

    def load() -> Models:
        import accuracy

        try:
            text = accuracy.CLASSES.read_text(encoding="utf-8")
        except OSError as error:
            raise SystemExit(f"Missing class names at {accuracy.CLASSES}: {error}") from error
        shown = accuracy.read_class_names(text)
        ids = accuracy.read_id_names(text)
        if accuracy.RESERVOIR not in shown or accuracy.LIQUID not in shown:
            raise SystemExit(
                f"{accuracy.CLASSES} must list {accuracy.RESERVOIR} and {accuracy.LIQUID}."
            )
        tank = accuracy.load_model(accuracy.WEIGHTS, shown)
        found = int(tank.model.args.num_classes)
        if found != len(shown):
            raise SystemExit(
                f"{accuracy.CLASSES.name} has {len(shown)} classes after the background line. "
                f"The checkpoint has {found}."
            )
        if len(ids) != found + 1:
            raise SystemExit(
                f"{accuracy.CLASSES.name} has {len(ids)} lines. "
                f"The checkpoint has {found + 1} class slots."
            )
        from rfdetr import RFDETRNano

        person = RFDETRNano(device="cpu")
        return Models(tank, person, ids)

    def copy_jpeg() -> Grab | None:
        with capture.frame_lock:
            jpg = bytes(capture.latest)
            seq = capture.frame_seq
            age_s = max(0.0, time.monotonic() - capture.frame_at)
        if not jpg:
            return None
        taken = datetime.now(CHICAGO) - timedelta(seconds=age_s)
        return Grab(jpg, round(age_s * 1000), seq, taken)

    def detect(models: Models, jpeg: bytes) -> Passes:
        import accuracy

        def head(predicted: object) -> object | None:
            if isinstance(predicted, list):
                return predicted[0] if predicted else None
            return predicted

        def boxes_from(predicted: object, labels: object) -> tuple[sight.Box, ...]:
            confidence = getattr(predicted, "confidence", None)
            xyxy = getattr(predicted, "xyxy", None)
            if confidence is None or xyxy is None:
                return ()
            built: list[sight.Box] = []
            for label, score, box in zip(labels, confidence, xyxy):
                built.append(
                    sight.Box(
                        str(label),
                        float(score),
                        float(box[0]),
                        float(box[1]),
                        float(box[2]),
                        float(box[3]),
                    )
                )
            return tuple(built)

        # The ledger has no decode column, so the shared decode stays on the tank pass.
        started = time.perf_counter()
        frame = accuracy.rgb_array(jpeg)
        tank_raw = models.tank.predict(
            frame, threshold=sight.THRESHOLD, include_source_image=False
        )
        tank_ms = round((time.perf_counter() - started) * 1000)
        started = time.perf_counter()
        person_raw = models.person.predict(
            frame, threshold=sight.THRESHOLD, include_source_image=False
        )
        person_ms = round((time.perf_counter() - started) * 1000)

        tank_out = head(tank_raw)
        if tank_out is None:
            tank_boxes: tuple[sight.Box, ...] = ()
        else:
            tank_boxes = boxes_from(tank_out, accuracy.labels_for(tank_out, models.id_names))

        person_boxes: tuple[sight.Box, ...] = ()
        person_out = head(person_raw)
        if person_out is not None:
            data = getattr(person_out, "data", None)
            if isinstance(data, dict):
                raw = data.get("class_name")
                if raw is not None:
                    person_boxes = boxes_from(person_out, raw)

        height, width = frame.shape[:2]
        return Passes(tank_boxes + person_boxes, tank_ms, person_ms, (int(width), int(height)))

    root = Path(__file__).resolve().parent.parent
    db_path = root / "learn" / "tank.sqlite"
    frames = root / "learn" / "frames"
    sys.path.insert(0, str(root / "page"))
    import live
    import capture

    error_file = live.error_path(db_path)
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

    report(None)
    serving = live.serve(db_path, frames, 8080)
    db = None
    try:
        capture.FFMPEG = thinned(capture.FFMPEG, BOARD_FPS)
        threading.Thread(target=capture.capture, daemon=True).start()
        try:
            models = load()
            db = ledger.connect(db_path)
        except (Exception, SystemExit) as error:
            traceback.print_exc()
            report(f"The board did not start: {error}. See /tmp/preview.log.")
            serving.wait()
            return
        last_seq = -1
        waiting_since = time.monotonic()
        while True:
            grab = copy_jpeg()
            if grab is None or grab.seq == last_seq:
                quiet = time.monotonic() - waiting_since
                if quiet > CAMERA_QUIET_S:
                    report(f"No new camera picture for {int(quiet)} s. Check the webcam on /dev/video0.")
                # Same pause capture uses between ffmpeg restarts.
                time.sleep(0.2)
                continue
            last_seq = grab.seq
            waiting_since = time.monotonic()
            try:
                passes = detect(models, grab.jpeg)
                tick(
                    db,
                    frames,
                    grab.jpeg,
                    passes.boxes,
                    grab.taken,
                    Elapsed(
                        capture_ms=grab.capture_ms,
                        tank_ms=passes.tank_ms,
                        person_ms=passes.person_ms,
                    ),
                    passes.size,
                    rss_mb(),
                    temp_c(),
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
