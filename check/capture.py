#!/usr/bin/env python3
"""Guided still capture. Open http://<pi>:8080. Does not load a model."""

import json
import math
import subprocess
import threading
import time
from decimal import Decimal, ROUND_HALF_UP
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import NamedTuple

CONF = Path("/home/bs/tank-envs/camera.conf")
TRAIN = Path(__file__).resolve().parent.parent / "train"


class Step(NamedTuple):
    seconds: int
    instruction: str
    filename: str


def _amount(number):
    if number == number.to_integral():
        return str(int(number))
    return f"{number:.1f}"


def build_steps():
    steps = []
    # Empty, then every half cup through 14. Both ends are pictures, so this is 29.
    for i in range(29):
        cups = Decimal(i) / Decimal(2)
        oz = cups * Decimal(5)
        pct = (oz / Decimal(70) * Decimal(100)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
        filename = f"{_amount(cups)}cup_{oz:.1f}oz_{pct}pct.jpg"
        if i == 0:
            steps.append(
                Step(
                    60,
                    "WARM is 0. The machine is off. The carafe is seated and empty. "
                    "The reservoir is empty. Stand clear. The page saves this picture "
                    "when the count reaches zero. 0 fl oz, alarm.",
                    filename,
                )
            )
            continue
        unit = "cup" if cups == 1 else "cups"
        alarm = ", alarm" if oz < Decimal("17.5") else ""
        steps.append(
            Step(
                45,
                f"Add 1/2 cup. Stop at {_amount(cups)} {unit}. { _amount(oz)} fl oz, {pct}%{alarm}. "
                "Stand clear. The page saves this picture when the count reaches zero.",
                filename,
            )
        )
    return tuple(steps)


STEPS = build_steps()

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
    "-framerate",
    "15",
    "-i",
    "/dev/video0",
    "-vf",
    "hflip,vflip",
    "-f",
    "mjpeg",
    "-q:v",
    "5",
    "pipe:1",
]

latest = b""
frame_lock = threading.Lock()
script_lock = threading.Lock()
start_event = threading.Event()
index = 0
deadline = None
started = False


def read_lock():
    try:
        text = CONF.read_text()
    except OSError:
        return None
    vals = {}
    for line in text.splitlines():
        line = line.split("#", 1)[0].strip()
        if not line or "=" not in line:
            continue
        key, value = line.split("=", 1)
        vals[key.strip()] = value.strip()
    try:
        return int(vals["focus_absolute"]), int(vals["exposure_time_absolute"])
    except (KeyError, ValueError):
        return None


def conf_text():
    try:
        return CONF.read_text()
    except OSError:
        return None


def apply_controls(focus, exposure):
    # Manual exposure without the absolute value blacks the frame, so the absolute is last.
    pairs = (
        ("power_line_frequency", 2),
        ("focus_automatic_continuous", 0),
        ("focus_absolute", focus),
        ("auto_exposure", 1),
        ("exposure_time_absolute", exposure),
    )
    for name, value in pairs:
        subprocess.run(
            ["v4l2-ctl", "-d", "/dev/video0", "-c", f"{name}={value}"],
            check=False,
        )


def first_missing():
    for i, step in enumerate(STEPS):
        if not (TRAIN / step.filename).is_file():
            return i
    return len(STEPS)


def ensure_started():
    global started
    if read_lock() is None:
        return
    with script_lock:
        if started:
            return
        started = True
    start_event.set()


def capture():
    global latest
    applied = object()
    while True:
        lock = read_lock()
        token = conf_text()
        if lock is not None and token != applied:
            apply_controls(*lock)
            applied = token
        proc = subprocess.Popen(FFMPEG, stdout=subprocess.PIPE)
        buf = b""
        try:
            while True:
                if token != conf_text():
                    break
                chunk = proc.stdout.read(8192)
                if not chunk:
                    break
                buf += chunk
                if len(buf) > 8_000_000:
                    buf = buf[-4_000_000:]
                while True:
                    start = buf.find(b"\xff\xd8")
                    if start == -1:
                        break
                    end = buf.find(b"\xff\xd9", start + 2)
                    if end == -1:
                        break
                    jpg = buf[start : end + 2]
                    buf = buf[end + 2 :]
                    with frame_lock:
                        latest = jpg
        finally:
            proc.kill()
            proc.wait()
        time.sleep(0.2)


def clock():
    global index, deadline
    start_event.wait()
    while True:
        with script_lock:
            i = index
        if i >= len(STEPS):
            with script_lock:
                deadline = None
            return
        step = STEPS[i]
        path = TRAIN / step.filename
        if path.is_file():
            with script_lock:
                if index == i:
                    index = i + 1
                    deadline = None
            continue
        end = time.monotonic() + step.seconds
        with script_lock:
            deadline = end
        while time.monotonic() < end:
            time.sleep(0.05)
        jpg = b""
        while not jpg:
            with frame_lock:
                jpg = bytes(latest)
            if not jpg:
                time.sleep(0.2)
        TRAIN.mkdir(parents=True, exist_ok=True)
        if not path.is_file():
            path.write_bytes(jpg)
        with script_lock:
            if index == i:
                index = i + 1
                deadline = None


def status():
    locked = read_lock() is not None
    if locked:
        ensure_started()
    with script_lock:
        i = index
        when = deadline
    done = i >= len(STEPS)
    if not locked:
        instruction = (
            "The camera is not locked. There is no capture button. "
            "After the lock file is in place, this page counts down and saves each picture by itself."
        )
        left = None
    elif done:
        instruction = "The shoot is done."
        left = None
    else:
        instruction = STEPS[i].instruction
        left = None if when is None else max(0, math.ceil(when - time.monotonic()))
    files = sum(1 for step in STEPS if (TRAIN / step.filename).is_file())
    return {
        "locked": locked,
        "instruction": instruction,
        "secondsLeft": left,
        "files": files,
        "done": done,
        "total": len(STEPS),
    }


PAGE = """<!doctype html>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>capture</title>
<style>
html,body{margin:0;height:100%}
body{background:#111;color:#fff;font:22px sans-serif;display:flex;flex-direction:column;height:100vh}
#bar{padding:12px 16px;flex:0 0 auto}
#bar p{margin:0 0 8px}
#sec{font-size:56px;line-height:1}
img{width:100vw;flex:1 1 auto;min-height:0;object-fit:contain;background:#000;display:block}
</style>
<div id=bar>
<p id=line></p>
<p id=sec></p>
<p id=count></p>
</div>
<img src="/stream.mjpg" alt="camera">
<script>
async function poll(){
  try {
    const body = await fetch("/status.json", {cache:"no-store"}).then(r => r.json());
    document.getElementById("line").textContent = body.instruction;
    document.getElementById("sec").textContent = body.secondsLeft == null ? "" : body.secondsLeft;
    document.getElementById("count").textContent = body.files + " of " + body.total + " pictures";
  } catch (e) {}
}
setInterval(poll, 250);
poll();
</script>
""".encode()


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path == "/status.json":
            body = json.dumps(status()).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if path == "/frame.jpg":
            with frame_lock:
                jpg = bytes(latest)
            if not jpg:
                self.send_error(503)
                return
            self.send_response(200)
            self.send_header("Content-Type", "image/jpeg")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(jpg)))
            self.end_headers()
            self.wfile.write(jpg)
            return
        if path == "/stream.mjpg":
            self.send_response(200)
            self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            try:
                while True:
                    with frame_lock:
                        jpg = bytes(latest)
                    if jpg:
                        self.wfile.write(b"--frame\r\nContent-Type: image/jpeg\r\n\r\n")
                        self.wfile.write(jpg)
                        self.wfile.write(b"\r\n")
                        self.wfile.flush()
                    time.sleep(1 / 15)
            except (BrokenPipeError, ConnectionError):
                return
            return
        if path in ("/", "/index.html"):
            ensure_started()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(PAGE)))
            self.end_headers()
            self.wfile.write(PAGE)
            return
        self.send_error(404)

    def log_message(self, fmt, *args):
        return


if __name__ == "__main__":
    index = first_missing()
    threading.Thread(target=capture, daemon=True).start()
    threading.Thread(target=clock, daemon=True).start()
    print("capture on :8080", flush=True)
    ThreadingHTTPServer(("0.0.0.0", 8080), Handler).serve_forever()
