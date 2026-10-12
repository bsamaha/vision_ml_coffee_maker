"""One tick of the coffee-tank board, and the Pi process that runs it.

Tests call tick with JPEG bytes and sight.Box values. The Pi runs main, which
is the only function that opens the camera and loads weights.
"""

from __future__ import annotations

import sqlite3
import sys
import threading
import time
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from typing import NamedTuple
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))

import ledger
import loop
import sight

__all__ = ["tick", "main", "Elapsed"]

CHICAGO = ZoneInfo("America/Chicago")


class Elapsed(NamedTuple):
    capture_ms: int
    tank_ms: int
    person_ms: int


def tick(
    db: sqlite3.Connection,
    frames: Path,
    jpeg: bytes,
    boxes: Sequence[sight.Box],
    at: datetime,
    elapsed: Elapsed = Elapsed(0, 0, 0),
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
        rss_mb=None,
        temp_c=None,
    )
    return loop.record(db, frames, jpeg, one)


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

    class Passes(NamedTuple):
        boxes: tuple[sight.Box, ...]
        tank_ms: int
        person_ms: int

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
            started = time.perf_counter()
            jpg = bytes(capture.latest)
            capture_ms = round((time.perf_counter() - started) * 1000)
        if not jpg:
            return None
        return Grab(jpg, capture_ms)

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

        return Passes(tank_boxes + person_boxes, tank_ms, person_ms)

    root = Path(__file__).resolve().parent.parent
    db_path = root / "learn" / "tank.sqlite"
    frames = root / "learn" / "frames"
    sys.path.insert(0, str(root / "page"))
    import live
    import capture

    serving = live.serve(db_path, frames, 8080)
    db = None
    try:
        threading.Thread(target=capture.capture, daemon=True).start()
        models = load()
        db = ledger.connect(db_path)
        while True:
            grab = copy_jpeg()
            if grab is None:
                # Same pause capture uses between ffmpeg restarts.
                time.sleep(0.2)
                continue
            passes = detect(models, grab.jpeg)
            tick(
                db,
                frames,
                grab.jpeg,
                passes.boxes,
                datetime.now(CHICAGO),
                Elapsed(
                    capture_ms=grab.capture_ms,
                    tank_ms=passes.tank_ms,
                    person_ms=passes.person_ms,
                ),
            )
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
