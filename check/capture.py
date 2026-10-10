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
    pose: str
    cups: int
    action: str
    delta: int
    restore: str
    instruction: str
    filename: str


OZ_PER_CUP = Decimal(5)
FULL_OZ = Decimal(70)
ALARM_OZ = Decimal("17.5")
MIN_JPEG = 1024
EXPOSURE_MIN = 3
EXPOSURE_MAX = 2047
USABLE_BRIGHTNESS = 120


def _amount(number):
    if number == number.to_integral():
        return str(int(number))
    return f"{number:.1f}"


def _fill(cups):
    cups = Decimal(cups)
    oz = cups * OZ_PER_CUP
    pct = (oz / FULL_OZ * Decimal(100)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
    return cups, oz, pct


def _filename(pose, cups):
    mark = "empty" if int(cups) == 0 else str(int(cups))
    return f"{pose}_{mark}.jpg"


def _fill_words(cups):
    cups, oz, pct = _fill(cups)
    unit = "cup" if cups == 1 else "cups"
    alarm = ", alarm" if oz < ALARM_OZ else ""
    return f"{_amount(cups)} {unit}, {_amount(oz)} fl oz, {pct}%{alarm}"


def _cups_unit(count):
    return "cup" if count == 1 else "cups"


POSE_LABEL = {
    "square": "Squared tank",
    "right": "Rotated right",
    "left": "Rotated left",
    "face": "Face on",
}


def water_words(cups):
    cups = int(cups)
    if cups == 0:
        return "empty"
    if cups == 1:
        return "1 cup"
    return f"{cups} cups"


def _pose_sentence(pose):
    if pose == "square":
        return "Squared tank. Cup marks face the camera."
    if pose == "right":
        return "Rotated right. Buttons on the left, reservoir on the right."
    if pose == "left":
        return "Rotated left. Reservoir on the left, buttons on the right."
    if pose == "face":
        return "Face on. Buttons face the camera."
    raise ValueError(pose)


def _instruction(pose, cups, action, delta, restore):
    level = f"Water: {water_words(cups)}."
    save = "Stand out of the picture. Save."
    if action == "ADD":
        pour = f"Pour to {water_words(cups)}."
        if cups == 1:
            pour += " A Ninja cup is 5 fl oz, not a baking cup."
        if restore == "pose":
            return f"{_pose_sentence(pose)} {pour} {save}"
        return f"{pour} {save}"
    return f"{_pose_sentence(pose)} {level} {save}"


def step_header(step, number):
    return f"{number} of {len(STEPS)} · Water: {water_words(step.cups)} · {POSE_LABEL[step.pose]}"


def build_steps():
    # Squared tank up the cup lines. At empty, 8, and 14, also shoot the other three angles.
    # Rotated right matches train/2026-10-09-first-try. Rotated left is that turn the other way.
    # The carafe is not part of the picture. A Ninja cup is 5 fl oz. 14 is 70 fl oz.
    steps = []

    def add(pose, cups, action, delta=0, restore=""):
        steps.append(
            Step(
                pose,
                int(cups),
                action,
                int(delta),
                restore,
                _instruction(pose, cups, action, delta, restore),
                _filename(pose, cups),
            )
        )

    add("square", 0, "SET")
    add("right", 0, "TURN")
    add("left", 0, "TURN")
    add("face", 0, "TURN")
    add("square", 1, "ADD", 1, "pose")
    add("square", 2, "ADD", 1)
    for cups in (4, 6, 8):
        add("square", cups, "ADD", 2)
    add("right", 8, "TURN")
    add("left", 8, "TURN")
    add("face", 8, "TURN")
    for cups in (10, 12, 14):
        add("square", cups, "ADD", 2, "pose" if cups == 10 else "")
    add("right", 14, "TURN")
    add("left", 14, "TURN")
    add("face", 14, "TURN")
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
frame_at = 0.0
frame_lock = threading.Lock()
script_lock = threading.Lock()
locking = threading.Event()
busy = threading.Lock()
index = 0
note = ""
lock_warning = ""


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
        if target > 180 or target < 60:
            set_note(
                f"Automatic brightness is {target:.0f}. "
                "Looking for an exposure that keeps the tank visible."
            )
            target = USABLE_BRIGHTNESS
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


def write_lock(focus, exposure, accepted):
    text = f"focus_absolute={focus}\nexposure_time_absolute={exposure}\n"
    if accepted:
        text += "accepted=1\n"
    CONF.parent.mkdir(parents=True, exist_ok=True)
    CONF.write_text(text)


def nudge_exposure(factor):
    if not begin():
        return
    try:
        pair = read_lock()
        if pair is None:
            set_note("Lock the picture before changing exposure.")
            return
        focus, exposure = pair
        nxt = int(round(exposure * factor))
        nxt = max(EXPOSURE_MIN, min(EXPOSURE_MAX, nxt))
        if nxt == exposure:
            nxt = exposure + (1 if factor > 1 else -1)
            nxt = max(EXPOSURE_MIN, min(EXPOSURE_MAX, nxt))
        write_lock(focus, nxt, lock_accepted())
        set_note(f"Exposure {nxt}. Wait for the picture to settle, then leave it for the rest of the shoot.")
    finally:
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


def readback_warning(focus, exposure):
    got_focus = read_ctrl("focus_absolute")
    got_exposure = read_ctrl("exposure_time_absolute")
    if got_focus is None or got_exposure is None:
        return "Lock readback failed. The saved lock is still the one on screen."
    if got_focus != focus or got_exposure != exposure:
        return (
            f"Lock readback is focus {got_focus}, exposure {got_exposure}. "
            f"Saved lock is focus {focus}, exposure {exposure}."
        )
    return ""


def sync_lock(pair):
    global lock_warning
    if locking.is_set():
        return
    if pair is None:
        release_controls()
        warning = ""
    else:
        apply_controls(*pair)
        warning = readback_warning(*pair)
    with script_lock:
        lock_warning = warning


def is_jpeg(path):
    try:
        with path.open("rb") as handle:
            if handle.read(2) != b"\xff\xd8":
                return False
            handle.seek(0, 2)
            return handle.tell() >= MIN_JPEG
    except OSError:
        return False


def first_missing():
    for i, step in enumerate(STEPS):
        if not is_jpeg(TRAIN / step.filename):
            return i
    return len(STEPS)


def capture():
    global latest, frame_seq, frame_at
    while True:
        token = conf_text()
        proc = subprocess.Popen(FFMPEG, stdout=subprocess.PIPE)
        if not locking.is_set():
            sync_lock(read_lock())
        buf = b""
        try:
            while True:
                if not locking.is_set():
                    new = conf_text()
                    if new != token:
                        token = new
                        sync_lock(read_lock())
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
                        frame_at = time.monotonic()
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
                if is_jpeg(path):
                    message = f"{path.name} is already in train/. Press Replace to clear it."
                else:
                    TRAIN.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(jpg)
                    message = f"Saved {path.name}"
                    index = i + 1
        set_note(message)
    finally:
        busy.release()


def replace_current():
    if not begin():
        return
    try:
        if not lock_accepted():
            set_note("Keep the lock before replacing a picture.")
            return
        message = ""
        with script_lock:
            i = index
            if i >= len(STEPS):
                message = "The shoot is already done."
            else:
                path = TRAIN / STEPS[i].filename
                if path.is_file():
                    path.unlink()
                message = f"Cleared {path.name}. Save this picture again."
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


def frame_age():
    with frame_lock:
        seq = frame_seq
        at = frame_at
    if seq == 0 or at == 0:
        return None
    return round(time.monotonic() - at, 2)


def status():
    pair = read_lock()
    accepted = lock_accepted()
    with script_lock:
        i = index
        shown = note
        warning = lock_warning
    done = i >= len(STEPS)
    step = None if done else STEPS[i]
    if pair is None:
        phase = "lock"
        instruction = (
            "Empty the reservoir. Turn the machine off. "
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
        instruction = step.instruction
        count = step_header(step, i + 1)
    files = sum(1 for item in STEPS if is_jpeg(TRAIN / item.filename))
    current = None if step is None else TRAIN / step.filename
    return {
        "phase": phase,
        "locked": pair is not None,
        "accepted": accepted,
        "instruction": instruction,
        "focus": None if pair is None else pair[0],
        "exposure": None if pair is None else pair[1],
        "files": files,
        "done": done,
        "index": i,
        "action": None if step is None else step.action,
        "pose": None if step is None else step.pose,
        "cups": None if step is None else step.cups,
        "filename": None if step is None else step.filename,
        "canNudge": pair is not None,
        "canRetake": i > 0 and phase in ("pour", "done"),
        "canReplace": phase == "pour" and current is not None and is_jpeg(current),
        "count": count,
        "total": len(STEPS),
        "note": shown,
        "lockWarning": warning,
        "frameAge": frame_age(),
    }


PAGE = """<!doctype html>
<meta name=viewport content="width=device-width,initial-scale=1,maximum-scale=1">
<title>capture</title>
<style>
html,body{margin:0;height:100%}
body{background:#111;color:#fff;font:22px sans-serif;display:flex;flex-direction:column;height:100vh;height:100dvh}
#bar{padding:12px 16px;flex:0 0 auto;max-height:42vh;overflow:auto}
#bar p{margin:0 0 8px}
#count{font:700 40px sans-serif;line-height:1.15}
#lockline,#warn{font:18px sans-serif;color:#ddd}
#warn{color:#fc6}
button{font:22px sans-serif;padding:14px 18px;margin:0 8px 8px 0;touch-action:manipulation}
#retake,#replace{font:16px sans-serif;padding:8px 12px}
#stage{position:relative;flex:1 1 auto;min-height:50vh;background:#000}
#view{width:100%;height:100%;object-fit:contain;background:#000;display:block}
#caption{position:absolute;left:0;right:0;bottom:0;margin:0;padding:10px 12px;background:rgba(0,0,0,.72);font:700 28px sans-serif}
#stale{position:absolute;left:12px;top:12px;margin:0;background:#a30;color:#fff;font:700 28px sans-serif;padding:8px 12px}
</style>
<div id=bar>
<p id=count></p>
<p id=lockline></p>
<p id=warn></p>
<p id=line></p>
<p id=note></p>
<button id=lock type=button>Lock this picture</button>
<button id=keep type=button>Keep this lock</button>
<button id=retry type=button>Try again</button>
<button id=save type=button>Save this picture</button>
<button id=replace type=button>Replace this picture</button>
<button id=darker type=button>Darker</button>
<button id=brighter type=button>Brighter</button>
<button id=retake type=button>Retake last</button>
</div>
<div id=stage>
<img id=view alt="camera">
<p id=caption></p>
<p id=stale hidden>no frame</p>
</div>
<script>
const view = document.getElementById("view");
const buttons = ["lock","keep","retry","save","replace","darker","brighter","retake"].map(id => document.getElementById(id));
const labels = {
  lock: "Lock this picture",
  keep: "Keep this lock",
  retry: "Try again",
  save: "Save this picture",
  replace: "Replace this picture",
  darker: "Darker",
  brighter: "Brighter",
  retake: "Retake last"
};
const working = {lock: "Locking…", save: "Saving…", replace: "Replacing…", retake: "Removing…"};
let busy = false;
let epoch = 0;
let holdUntil = 0;
let retakeArmed = false;
let seenIndex = null;
let imgBad = false;
function frame(){ view.src = "/frame.jpg?t=" + Date.now(); }
view.onload = () => { imgBad = false; setTimeout(frame, 200); };
view.onerror = () => { imgBad = true; document.getElementById("stale").hidden = false; setTimeout(frame, 800); };
frame();
function show(body){
  if (body.index !== seenIndex) {
    seenIndex = body.index;
    retakeArmed = false;
  }
  document.getElementById("line").textContent = body.instruction;
  document.getElementById("count").textContent = body.count;
  document.getElementById("caption").textContent = body.count;
  document.getElementById("note").textContent = body.note || "";
  const focus = body.focus == null ? "" : "Focus " + body.focus + ", exposure " + body.exposure;
  document.getElementById("lockline").textContent = focus;
  document.getElementById("warn").textContent = body.lockWarning || "";
  const stale = imgBad || body.frameAge == null || body.frameAge > 2;
  document.getElementById("stale").hidden = !stale;
  document.getElementById("lock").hidden = body.phase !== "lock";
  document.getElementById("keep").hidden = body.phase !== "confirm";
  document.getElementById("retry").hidden = body.phase !== "confirm";
  document.getElementById("darker").hidden = !body.canNudge;
  document.getElementById("brighter").hidden = !body.canNudge;
  document.getElementById("save").hidden = body.phase !== "pour";
  document.getElementById("replace").hidden = !body.canReplace;
  document.getElementById("retake").hidden = !body.canRetake;
  document.getElementById("retake").textContent = retakeArmed ? "Retake?" : labels.retake;
  if (!busy) {
    buttons.forEach(button => {
      button.disabled = false;
      if (button.id !== "retake") button.textContent = labels[button.id];
    });
  }
}
async function poll(){
  const seen = epoch;
  try {
    const body = await fetch("/status.json", {cache:"no-store"}).then(r => r.json());
    if (seen !== epoch || Date.now() < holdUntil) return;
    show(body);
  } catch (e) {}
}
function sleep(ms){ return new Promise(resolve => setTimeout(resolve, ms)); }
async function press(id, path){
  if (busy || Date.now() < holdUntil) return;
  busy = true;
  epoch++;
  buttons.forEach(button => { button.disabled = true; });
  const button = document.getElementById(id);
  if (working[id]) button.textContent = working[id];
  let body = null;
  try {
    body = await fetch(path, {method:"POST", cache:"no-store"}).then(r => r.json());
    epoch++;
    show(body);
  } catch (e) {
    epoch++;
    document.getElementById("note").textContent = "That step did not finish.";
  }
  if (path === "/save" && body && (body.note || "").startsWith("Saved ")) {
    holdUntil = Date.now() + 400;
    await sleep(400);
  }
  busy = false;
  if (body) show(body);
  else buttons.forEach(button => { button.disabled = false; });
}
document.getElementById("lock").onclick = () => press("lock", "/lock");
document.getElementById("keep").onclick = () => press("keep", "/accept");
document.getElementById("retry").onclick = () => press("retry", "/retry");
document.getElementById("darker").onclick = () => press("darker", "/darker");
document.getElementById("brighter").onclick = () => press("brighter", "/brighter");
document.getElementById("save").onclick = () => press("save", "/save");
document.getElementById("replace").onclick = () => press("replace", "/replace");
document.getElementById("retake").onclick = () => {
  if (!retakeArmed) {
    retakeArmed = true;
    document.getElementById("retake").textContent = "Retake?";
    return;
  }
  retakeArmed = false;
  press("retake", "/retake");
};
if (navigator.wakeLock) {
  const ask = () => navigator.wakeLock.request("screen").catch(() => {});
  ask();
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible") ask();
  });
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
            elif path == "/replace":
                replace_current()
            elif path == "/darker":
                nudge_exposure(2 / 3)
            elif path == "/brighter":
                nudge_exposure(3 / 2)
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
