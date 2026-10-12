"""The webcam for the board: one `ffmpeg` process and the saved focus and exposure lock.

`run()` keeps the newest upright JPEG in memory on its own thread. `newest()` hands it out.
"""

import subprocess
import threading
import time
from pathlib import Path
from typing import NamedTuple

# Written once by the camera-lock step of the training shoot. Reapplied every time ffmpeg starts.
CONF = Path("/home/bs/tank-envs/camera.conf")
# The webcam only offers 1280x720 MJPEG at 60 fps. A tick takes one frame every 7.5 s, so
# `fps=2` ahead of the flip keeps ffmpeg from flipping and encoding all 60.
FFMPEG = [
    "ffmpeg",
    "-hide_banner",
    "-loglevel",
    "error",
    "-fflags",
    "nobuffer",
    "-f",
    "v4l2",
    "-input_format",
    "mjpeg",
    "-video_size",
    "1280x720",
    "-i",
    "/dev/video0",
    "-vf",
    "fps=2,hflip,vflip",
    "-f",
    "mjpeg",
    "-q:v",
    "5",
    "pipe:1",
]
_BUFFER_MAX = 8_000_000

_lock = threading.Lock()
_latest = b""
_seq = 0
_at = 0.0


class Frame(NamedTuple):
    jpeg: bytes
    seq: int
    age_s: float


def newest() -> Frame | None:
    with _lock:
        if not _latest:
            return None
        return Frame(_latest, _seq, max(0.0, time.monotonic() - _at))


def split_jpegs(buffer: bytes) -> tuple[list[bytes], bytes]:
    """Whole JPEGs in an ffmpeg byte stream, and the bytes left over for the next read."""
    found = []
    while True:
        start = buffer.find(b"\xff\xd8")
        if start == -1:
            return found, buffer
        end = buffer.find(b"\xff\xd9", start + 2)
        if end == -1:
            return found, buffer[start:]
        found.append(buffer[start : end + 2])
        buffer = buffer[end + 2 :]


def read_lock(conf: Path = CONF) -> tuple[int, int] | None:
    """(focus_absolute, exposure_time_absolute) from the lock file, or None."""
    try:
        lines = conf.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    values = {}
    for line in lines:
        key, _, value = line.split("#", 1)[0].partition("=")
        values[key.strip()] = value.strip()
    try:
        return int(values["focus_absolute"]), int(values["exposure_time_absolute"])
    except (KeyError, ValueError):
        return None


def _set(name: str, value: int) -> None:
    subprocess.run(["v4l2-ctl", "-d", "/dev/video0", "-c", f"{name}={value}"], check=False)


def _apply(pair: tuple[int, int] | None) -> None:
    """Manual focus and exposure at the lock, 60 Hz. No lock leaves the camera on automatic."""
    if pair is None:
        _set("focus_automatic_continuous", 1)
        _set("auto_exposure", 3)
        return
    focus, exposure = pair
    # Manual exposure without the absolute value blacks the frame, so the order matters.
    for name, value in (
        ("power_line_frequency", 2),
        ("focus_automatic_continuous", 0),
        ("focus_absolute", focus),
        ("auto_exposure", 1),
        ("exposure_time_absolute", exposure),
    ):
        _set(name, value)


def run() -> None:
    """Forever: start ffmpeg, apply the lock, keep the newest frame, restart if ffmpeg ends."""
    global _latest, _seq, _at
    while True:
        process = subprocess.Popen(FFMPEG, stdout=subprocess.PIPE)
        _apply(read_lock())
        buffer = b""
        try:
            while True:
                chunk = process.stdout.read(8192)
                if not chunk:
                    break
                frames, buffer = split_jpegs(buffer + chunk)
                if len(buffer) > _BUFFER_MAX:
                    buffer = b""
                if frames:
                    with _lock:
                        _latest = frames[-1]
                        _seq += len(frames)
                        _at = time.monotonic()
        finally:
            process.kill()
            process.wait()
        time.sleep(0.2)
