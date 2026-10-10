#!/usr/bin/env python3
"""Guided still capture. Open http://<pi>:8080. Does not load a model."""

import json
import subprocess
import threading
import time
import traceback
from decimal import Decimal, ROUND_HALF_UP
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
from pathlib import Path
from typing import NamedTuple

CONF = Path("/home/bs/tank-envs/camera.conf")
TRAIN = Path(__file__).resolve().parent.parent / "train"


class Step(NamedTuple):
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
                    "WARM is 0. The machine is off. The carafe is seated and empty. "
                    "The reservoir is empty. Stand clear, then press Save picture. 0 fl oz, alarm.",
                    filename,
                )
            )
            continue
        unit = "cup" if cups == 1 else "cups"
        alarm = ", alarm" if oz < Decimal("17.5") else ""
        steps.append(
            Step(
                f"Add 1/2 cup. Stop at {_amount(cups)} {unit}. {_amount(oz)} fl oz, {pct}%{alarm}. "
                "Stand clear, then press Save picture.",
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
frame_seq = 0
frame_lock = threading.Lock()
script_lock = threading.Lock()
locking = threading.Event()
busy = threading.Lock()
index = 0
note = ""


def conf_vals():
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
    return vals


def read_lock():
    vals = conf_vals()
    if not vals:
        return None
    try:
        return int(vals["focus_absolute"]), int(vals["exposure_time_absolute"])
    except (KeyError, ValueError):
        return None


def lock_accepted():
    vals = conf_vals()
    return bool(vals) and vals.get("accepted") == "1"


def begin():
    if busy.acquire(blocking=False):
        return True
    set_note("Wait for the current step to finish.")
    return False


def conf_text():
    try:
        return CONF.read_text()
    except OSError:
        return None


def set_note(text):
    global note
    with script_lock:
        note = text
    print(text, flush=True)


def read_ctrl(name):
    result = subprocess.run(
        ["v4l2-ctl", "-d", "/dev/video0", "-C", name],
        check=False,
        capture_output=True,
        text=True,
    )
    line = result.stdout.strip()
    if result.returncode != 0 or ":" not in line:
        return None
    try:
        return int(line.split(":", 1)[1].strip())
    except ValueError:
        return None


def set_ctrl(name, value):
    subprocess.run(
        ["v4l2-ctl", "-d", "/dev/video0", "-c", f"{name}={value}"],
        check=False,
    )


def jpeg_brightness(jpg):
    from PIL import Image

    image = Image.open(BytesIO(jpg)).convert("L").resize((64, 36))
    hist = image.histogram()
    count = sum(hist)
    if count == 0:
        return None
    return sum(i * n for i, n in enumerate(hist)) / count


def sample_brightness():
    with frame_lock:
        seq = frame_seq
    time.sleep(0.5)
    deadline = time.monotonic() + 1.0
    jpg = b""
    while time.monotonic() < deadline:
        with frame_lock:
            if frame_seq > seq and latest:
                jpg = bytes(latest)
                break
        time.sleep(0.05)
    if not jpg:
        with frame_lock:
            jpg = bytes(latest)
    if not jpg:
        return None
    return jpeg_brightness(jpg)


def match_exposure(target):
    # The control's idle reading is 166, and writing that number makes the picture dark.
    # Search for the manual value that keeps the automatic picture's brightness.
    low, high = 3, 2047
    best = None
    best_err = 10**9
    for _ in range(8):
        if low > high:
            break
        guess = (low + high) // 2
        set_ctrl("auto_exposure", 1)
        set_ctrl("exposure_time_absolute", guess)
        level = sample_brightness()
        if level is None:
            break
        err = abs(level - target)
        set_note(f"Trying exposure {guess}. Brightness {level:.0f}, target {target:.0f}.")
        if err < best_err:
            best, best_err = guess, err
        if err <= 12:
            break
        if level < target:
            low = guess + 1
        else:
            high = guess - 1
    if best is None or best_err > 12:
        return None
    set_ctrl("auto_exposure", 1)
    set_ctrl("exposure_time_absolute", best)
    checked = sample_brightness()
    if checked is None or abs(checked - target) > 20:
        set_note("That exposure did not stay as bright as the automatic picture.")
        return None
    return best


def release_controls():
    set_ctrl("focus_automatic_continuous", 1)
    set_ctrl("auto_exposure", 3)


def lock_current():
    if not begin():
        return False
    locking.set()
    try:
        focus = read_ctrl("focus_absolute")
        if focus is None:
            set_note("Lock failed. The camera did not report focus.")
            return False
        set_ctrl("power_line_frequency", 2)
        set_ctrl("focus_automatic_continuous", 0)
        set_ctrl("focus_absolute", focus)
        set_ctrl("auto_exposure", 3)
        set_note("Locking. Matching the bright picture.")
        target = sample_brightness()
        if target is None:
            release_controls()
            set_note("Lock failed. The camera has no frame yet.")
            return False
        exposure = match_exposure(target)
        if exposure is None:
            release_controls()
            set_note("Lock failed. Exposure was left on automatic.")
            return False
        CONF.parent.mkdir(parents=True, exist_ok=True)
        CONF.write_text(f"focus_absolute={focus}\nexposure_time_absolute={exposure}\n")
        set_note(f"Locked. Focus {focus}, exposure {exposure}. Look again before you keep it.")
        return True
    finally:
        locking.clear()
        busy.release()


def accept_lock():
    if not begin():
        return
    try:
        pair = read_lock()
        if pair is None:
            set_note("There is no lock to keep.")
            return
        focus, exposure = pair
        CONF.write_text(f"focus_absolute={focus}\nexposure_time_absolute={exposure}\naccepted=1\n")
        set_note("Lock kept.")
    finally:
        busy.release()


def retry_lock():
    if not begin():
        return
    locking.set()
    try:
        CONF.unlink(missing_ok=True)
        release_controls()
        set_note("Lock cleared. Look again, then press Lock this picture.")
    finally:
        locking.clear()
        busy.release()


def apply_controls(focus, exposure):
    pairs = (
        ("power_line_frequency", 2),
        ("focus_automatic_continuous", 0),
        ("focus_absolute", focus),
        ("auto_exposure", 1),
        ("exposure_time_absolute", exposure),
    )
    for name, value in pairs:
        set_ctrl(name, value)


def first_missing():
    for i, step in enumerate(STEPS):
        if not (TRAIN / step.filename).is_file():
            return i
    return len(STEPS)


def capture():
    global latest, frame_seq
    applied = object()
    while True:
        lock = read_lock()
        token = conf_text()
        proc = subprocess.Popen(FFMPEG, stdout=subprocess.PIPE)
        if not locking.is_set():
            if lock is None:
                release_controls()
                applied = object()
            elif token != applied:
                apply_controls(*lock)
                applied = token
        buf = b""
        try:
            while True:
                if not locking.is_set():
                    new = conf_text()
                    if new != token:
                        token = new
                        lock = read_lock()
                        if lock is None:
                            release_controls()
                            applied = object()
                        else:
                            apply_controls(*lock)
                            applied = token
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
                        frame_seq += 1
        finally:
            proc.kill()
            proc.wait()
        time.sleep(0.2)


def save_current():
    global index
    if not begin():
        return
    try:
        if not lock_accepted():
            set_note("Keep the lock before saving a picture.")
            return
        with frame_lock:
            jpg = bytes(latest)
        if not jpg:
            set_note("Save picture wrote nothing. The camera has no frame yet.")
            return
        message = ""
        with script_lock:
            i = index
            if i >= len(STEPS):
                message = "The shoot is already done."
            else:
                path = TRAIN / STEPS[i].filename
                if not path.is_file():
                    TRAIN.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(jpg)
                    message = f"Saved {path.name}"
                else:
                    message = f"{path.name} was already there."
                index = i + 1
        set_note(message)
    finally:
        busy.release()


def retake_last():
    global index
    if not begin():
        return
    try:
        if not lock_accepted():
            set_note("Keep the lock before retaking a picture.")
            return
        message = ""
        with script_lock:
            if index <= 0:
                message = "There is no picture to retake."
            else:
                index -= 1
                path = TRAIN / STEPS[index].filename
                if path.is_file():
                    path.unlink()
                message = f"Removed {path.name}. Take that picture again."
        set_note(message)
    finally:
        busy.release()


def status():
    pair = read_lock()
    accepted = lock_accepted()
    with script_lock:
        i = index
        shown = note
    done = i >= len(STEPS)
    if pair is None:
        phase = "lock"
        instruction = (
            "Empty the reservoir. Seat the carafe. Turn the machine off. "
            "Stand where the camera cannot see you. When the reservoir looks sharp and bright, "
            "press Lock this picture."
        )
        count = "Step 1. Lock the camera."
    elif not accepted:
        phase = "confirm"
        instruction = (
            "Look at the reservoir again. It should still be sharp and bright. "
            "Keep this lock, or try again."
        )
        count = f"Step 2. Check the picture. Focus {pair[0]}, exposure {pair[1]}."
    elif done:
        phase = "done"
        instruction = "The shoot is done. The pictures are in train/."
        count = f"{len(STEPS)} of {len(STEPS)} pictures."
    else:
        phase = "pour"
        instruction = STEPS[i].instruction
        count = f"Picture {i + 1} of {len(STEPS)}."
    files = sum(1 for step in STEPS if (TRAIN / step.filename).is_file())
    return {
        "phase": phase,
        "locked": pair is not None,
        "accepted": accepted,
        "instruction": instruction,
        "focus": None if pair is None else pair[0],
        "exposure": None if pair is None else pair[1],
        "files": files,
        "done": done,
        "canRetake": phase == "pour" and i > 0,
        "count": count,
        "total": len(STEPS),
        "note": shown,
    }


PAGE = """<!doctype html>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>capture</title>
<style>
html,body{margin:0;height:100%}
body{background:#111;color:#fff;font:22px sans-serif;display:flex;flex-direction:column;height:100vh}
#bar{padding:12px 16px;flex:0 0 auto}
#bar p{margin:0 0 8px}
button{font:22px sans-serif;padding:14px 18px}
img{width:100vw;flex:1 1 auto;min-height:0;object-fit:contain;background:#000;display:block}
</style>
<div id=bar>
<p id=count></p>
<p id=line></p>
<p id=note></p>
<button id=lock type=button>Lock this picture</button>
<button id=keep type=button>Keep this lock</button>
<button id=retry type=button>Try again</button>
<button id=save type=button>Save this picture</button>
<button id=retake type=button>Retake the last picture</button>
</div>
<img id=view alt="camera">
<script>
const view = document.getElementById("view");
function frame(){ view.src = "/frame.jpg?t=" + Date.now(); }
view.onload = () => setTimeout(frame, 200);
view.onerror = () => setTimeout(frame, 800);
frame();
let busy = false;
function show(body){
  document.getElementById("line").textContent = body.instruction;
  document.getElementById("count").textContent = body.count;
  document.getElementById("note").textContent = body.note || "";
  document.getElementById("lock").hidden = body.phase !== "lock";
  document.getElementById("keep").hidden = body.phase !== "confirm";
  document.getElementById("retry").hidden = body.phase !== "confirm";
  document.getElementById("save").hidden = body.phase !== "pour";
  document.getElementById("retake").hidden = !body.canRetake;
  if (!busy) {
    document.getElementById("lock").disabled = false;
    document.getElementById("keep").disabled = false;
    document.getElementById("retry").disabled = false;
    document.getElementById("save").disabled = false;
    document.getElementById("retake").disabled = false;
  }
}
async function poll(){
  try { show(await fetch("/status.json", {cache:"no-store"}).then(r => r.json())); }
  catch (e) {}
}
async function press(id, path){
  if (busy) return;
  busy = true;
  document.getElementById(id).disabled = true;
  try { show(await fetch(path, {method:"POST", cache:"no-store"}).then(r => r.json())); }
  catch (e) { document.getElementById("note").textContent = "That step did not finish."; }
  busy = false;
  poll();
}
document.getElementById("lock").onclick = () => press("lock", "/lock");
document.getElementById("keep").onclick = () => press("keep", "/accept");
document.getElementById("retry").onclick = () => press("retry", "/retry");
document.getElementById("save").onclick = () => press("save", "/save");
document.getElementById("retake").onclick = () => press("retake", "/retake");
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
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(PAGE)))
            self.end_headers()
            self.wfile.write(PAGE)
            return
        self.send_error(404)

    def do_POST(self):
        path = self.path.split("?", 1)[0]
        try:
            if path == "/lock":
                lock_current()
            elif path == "/accept":
                accept_lock()
            elif path == "/retry":
                retry_lock()
            elif path == "/save":
                save_current()
            elif path == "/retake":
                retake_last()
            else:
                self.send_error(404)
                return
        except Exception:
            traceback.print_exc()
            set_note("That press failed. See /tmp/preview.log on the Pi.")
        body = json.dumps(status()).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        return


if __name__ == "__main__":
    index = first_missing()
    threading.Thread(target=capture, daemon=True).start()
    print("capture on :8080", flush=True)
    ThreadingHTTPServer(("0.0.0.0", 8080), Handler).serve_forever()
