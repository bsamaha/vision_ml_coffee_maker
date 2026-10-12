#!/usr/bin/env python3
"""Phone page to compare one model reading with a known cup count.

Open http://<pi>:8080. Starts the camera thread from capture.py and does not
call capture.main(). One process owns /dev/video0. The tank weights load once,
at startup. That import stays inside accuracy.load_model so a machine without
torch can still import this file.

Class id is the line index in class_names.txt. This checkpoint's last logit is
liquid-level. predict() renames that logit to __background__, so the class
file is the source of the name. A read draws boxes on a copy of the displayed
JPEG and appends one line to /tmp/preview.log. It does not write a session.
"""

import json
import sys
import threading
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import accuracy
import capture
import volume

WEIGHTS = Path("/home/bs/.roboflow/models/rate-and-volume-of-coffee-1/weights.pth")
CLASSES = WEIGHTS.parent / "class_names.txt"
PREVIEW_LOG = Path("/tmp/preview.log")
RESERVOIR = "Reservoir"
LIQUID = "liquid-level"
THRESHOLD = 0.4

model = None
id_names = ()
known_cups = 0
reservoir_box = None
liquid_box = None
seen = False
reading = False
note = ""
painted_seq = -1
painted_jpeg = b""
script_lock = threading.Lock()
busy = threading.Lock()


def id_names_from(text):
    return accuracy.read_id_names(text)


def labels_for(predicted, names):
    # predict() renames the last logit to __background__. The class file wins.
    return accuracy.labels_for(predicted, names)


def pick_boxes(labels, scores, boxes):
    reservoir = accuracy.best_box(labels, scores, boxes, RESERVOIR)
    liquid = accuracy.best_box(labels, scores, boxes, LIQUID)
    return reservoir, liquid


def parse_cups(value):
    if isinstance(value, bool) or value is None:
        raise ValueError("Known cups are a whole number from 0 through 14.")
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError("Known cups are a whole number from 0 through 14.") from None
    if number < 0 or number > volume.FULL_CUPS or not number.is_integer():
        raise ValueError("Known cups are a whole number from 0 through 14.")
    return int(number)


def labeled_ratio(cups):
    for ratio, line_cups in volume.LINES:
        if line_cups == cups:
            return ratio
    return None


def comparison(cups, reservoir, liquid):
    """Model cups minus known cups. No liquid box is 0 cups. No reservoir is not a reading."""
    cups = int(cups)
    if cups < 0 or cups > volume.FULL_CUPS:
        raise ValueError("Known cups are a whole number from 0 through 14.")
    labeled = labeled_ratio(cups)
    if reservoir is None:
        return {
            "known_cups": cups,
            "reservoir": False,
            "box_ratio": None,
            "bottom_gap_px": None,
            "cups": None,
            "percent": None,
            "diff_cups": None,
            "diff_percent": None,
            "labeled_box_ratio": labeled,
            "ratio_gap": None,
            "has_labeled_line": labeled is not None,
        }
    if liquid is None:
        got = volume.reading(None)
        ratio = None
        gap = None
    else:
        ratio = volume.box_ratio(reservoir[1], reservoir[3], liquid[1])
        gap = abs(float(reservoir[3]) - float(liquid[3]))
        got = volume.reading(ratio)
    known_percent = cups / volume.FULL_CUPS * 100
    ratio_gap = None if ratio is None or labeled is None else ratio - labeled
    return {
        "known_cups": cups,
        "reservoir": True,
        "box_ratio": ratio,
        "bottom_gap_px": gap,
        "cups": got.cups,
        "percent": got.percent,
        "diff_cups": got.cups - cups,
        "diff_percent": got.percent - known_percent,
        "labeled_box_ratio": labeled,
        "ratio_gap": ratio_gap,
        "has_labeled_line": labeled is not None,
    }


def labeled_text(row):
    if not row["has_labeled_line"]:
        return f"No knot at {row['known_cups']} cups."
    text = f"knot box ratio {row['labeled_box_ratio']:.3f}"
    if row["ratio_gap"] is None:
        return text
    return f"{text}    ratio gap {row['ratio_gap']:+.3f}"


def summary_line(row):
    cups = row["known_cups"]
    if not row["reservoir"]:
        return f"compare known {cups} no reservoir box. {labeled_text(row)}"
    if row["box_ratio"] is None:
        ratio = "no liquid line"
        gap = "no liquid line"
    else:
        ratio = f"{row['box_ratio']:.3f}"
        gap = f"{row['bottom_gap_px']:.0f}px"
    return (
        f"compare known {cups} "
        f"box {ratio} model {row['percent']:.1f}% {row['cups']:.2f}cups "
        f"diff {row['diff_cups']:+.2f}cups {row['diff_percent']:+.1f}% "
        f"bottom {gap} {labeled_text(row)}"
    )


def blank_row(cups):
    labeled = labeled_ratio(cups)
    return {
        "known_cups": cups,
        "reservoir": False,
        "box_ratio": None,
        "bottom_gap_px": None,
        "cups": None,
        "percent": None,
        "diff_cups": None,
        "diff_percent": None,
        "labeled_box_ratio": labeled,
        "ratio_gap": None,
        "has_labeled_line": labeled is not None,
    }


def append_log(line):
    try:
        with PREVIEW_LOG.open("a", encoding="utf-8") as handle:
            handle.write(line.rstrip("\n") + "\n")
            handle.flush()
    except OSError:
        traceback.print_exc()


def set_note(text):
    global note
    with script_lock:
        note = text


def finish(line, page_note):
    set_note(page_note)
    append_log(line)


def status():
    with script_lock:
        cups = known_cups
        reservoir = reservoir_box
        liquid = liquid_box
        have = seen
        active = reading
        shown = note
    if have:
        row = comparison(cups, reservoir, liquid)
    else:
        row = blank_row(cups)
    row = dict(row)
    row["seen"] = have
    row["reading"] = active
    row["labeled_text"] = labeled_text(row)
    row["note"] = shown
    row["frameAge"] = capture.frame_age()
    pair = capture.read_lock()
    row["exposure"] = None if pair is None else pair[1]
    return row


def controls_from(data):
    with script_lock:
        cups = known_cups
    if "known_cups" in data and data["known_cups"] is not None:
        cups = parse_cups(data["known_cups"])
    return cups


def update_settings(cups):
    global known_cups
    if not busy.acquire(blocking=False):
        return
    try:
        with script_lock:
            known_cups = cups
    finally:
        busy.release()


def nudge(factor):
    if not busy.acquire(blocking=False):
        return
    try:
        capture.nudge_exposure(factor)
        set_note(capture.note)
    finally:
        busy.release()


def rgb_array(jpg):
    from io import BytesIO

    import numpy as np
    from PIL import Image

    image = Image.open(BytesIO(jpg)).convert("RGB")
    return np.asarray(image, dtype=np.uint8)


def infer_boxes(jpg):
    predicted = model.predict(rgb_array(jpg), threshold=THRESHOLD, include_source_image=False)
    if isinstance(predicted, list):
        predicted = predicted[0] if predicted else None
    if predicted is None:
        return None, None
    labels = labels_for(predicted, id_names)
    scores = [] if predicted.confidence is None else predicted.confidence
    boxes = [] if predicted.xyxy is None else predicted.xyxy
    return pick_boxes(labels, scores, boxes)


def read_frame(cups):
    global known_cups, reservoir_box, liquid_box, seen, reading, painted_seq
    if not busy.acquire(blocking=False):
        return
    try:
        with script_lock:
            reading = True
            known_cups = cups
        with capture.frame_lock:
            jpg = bytes(capture.latest)
        if not jpg:
            finish("compare no frame", "The camera has no frame yet.")
            return
        try:
            reservoir, liquid = infer_boxes(jpg)
        except Exception:
            traceback.print_exc()
            finish("compare read failed", "That reading failed.")
            return
        with script_lock:
            reservoir_box = reservoir
            liquid_box = liquid
            seen = True
            painted_seq = -1
            row = comparison(known_cups, reservoir, liquid)
        if row["reservoir"]:
            finish(summary_line(row), "")
        else:
            finish(summary_line(row), "No reservoir box.")
    finally:
        with script_lock:
            reading = False
        busy.release()


def _font():
    from PIL import ImageFont

    try:
        return ImageFont.load_default(size=32)
    except TypeError:
        return ImageFont.load_default()


def _mark(draw, box, color, label, font):
    x1, y1, x2, y2 = (
        int(round(box[0])),
        int(round(box[1])),
        int(round(box[2])),
        int(round(box[3])),
    )
    draw.rectangle((x1, y1, x2, y2), outline=color, width=5)
    text_y = y1 - 36
    if text_y < 0:
        text_y = y1 + 4
    draw.text((x1 + 6, text_y), label, fill=color, font=font)


def draw_boxes(jpg, reservoir, liquid):
    """Draw on a new image. No reservoir box draws nothing."""
    if reservoir is None:
        return jpg
    from io import BytesIO

    from PIL import Image, ImageDraw

    image = Image.open(BytesIO(jpg)).convert("RGB")
    draw = ImageDraw.Draw(image)
    font = _font()
    _mark(draw, reservoir, (0, 220, 0), RESERVOIR, font)
    if liquid is not None:
        _mark(draw, liquid, (64, 170, 255), LIQUID, font)
    out = BytesIO()
    image.save(out, format="JPEG", quality=80)
    return out.getvalue()


def displayed_jpeg():
    global painted_seq, painted_jpeg
    with capture.frame_lock:
        jpg = bytes(capture.latest)
        seq = capture.frame_seq
    if not jpg:
        return b""
    with script_lock:
        reservoir = reservoir_box
        liquid = liquid_box
        cached_seq = painted_seq
        cached = painted_jpeg
    if reservoir is None:
        return jpg
    if cached_seq == seq and cached:
        return cached
    try:
        rendered = draw_boxes(jpg, reservoir, liquid)
    except Exception:
        traceback.print_exc()
        return jpg
    with script_lock:
        painted_seq = seq
        painted_jpeg = rendered
    return rendered


def json_body(handler):
    try:
        length = int(handler.headers.get("Content-Length", "0") or 0)
    except ValueError:
        length = 0
    if length < 0 or length > 100_000:
        raise ValueError("That request was too large.")
    raw = handler.rfile.read(length) if length else b""
    if not raw:
        return {}
    data = json.loads(raw.decode("utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Expected a JSON object.")
    return data


def write_json(handler, payload):
    body = json.dumps(payload).encode()
    handler.send_response(200)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


PAGE = """<!doctype html>
<meta name=viewport content="width=device-width,initial-scale=1,maximum-scale=1">
<title>compare</title>
<style>
html,body{margin:0;height:100%}
body{background:#111;color:#fff;font:22px sans-serif;display:flex;flex-direction:column;height:100vh;height:100dvh}
#bar{padding:12px 16px 8px;flex:0 0 auto;max-height:62vh;overflow:auto}
#bar p{margin:0 0 8px}
#known{font:16px sans-serif;color:#ddd}
#cupsrow{display:flex;align-items:center;gap:8px;margin:0 0 10px}
#cupsrow button{font:36px sans-serif;padding:8px 18px;touch-action:manipulation}
#cups{font:700 48px sans-serif;width:4.2ch;text-align:center;padding:4px}
#exposure{display:flex;gap:8px;margin:0 0 10px}
#exposure button{flex:1 1 0;font:22px sans-serif;padding:16px 8px;touch-action:manipulation}
#ratio,#diff,#gap,#labeled{font:700 30px sans-serif;line-height:1.2}
#model,#rgap{font:700 36px sans-serif;line-height:1.15}
#difflabel,#note{font:16px sans-serif;color:#ddd}
body.locked #cupsrow button,body.locked #cups,body.locked #exposure button{pointer-events:none;opacity:.72}
#stage{position:relative;flex:1 1 auto;min-height:38vh;background:#000}
#view{width:100%;height:100%;object-fit:contain;background:#000;display:block}
#caption{position:absolute;inset:auto 0 0 0;margin:0;padding:10px 12px;background:rgba(0,0,0,.72);font:700 28px sans-serif}
#stale{position:absolute;inset:12px auto auto 12px;margin:0;background:#a30;color:#fff;font:700 28px sans-serif;padding:8px 12px}
</style>
<div id=bar>
<p id=known>Known cups</p>
<div id=cupsrow>
<button id=minus type=button>-</button>
<input id=cups type=number min=0 max=14 step=1 value=0 inputmode=numeric autocomplete=off>
<button id=plus type=button>+</button>
</div>
<div id=exposure>
<button id=darker type=button>Darker</button>
<button id=read type=button>Read</button>
<button id=brighter type=button>Brighter</button>
</div>
<p id=ratio></p>
<p id=model></p>
<p id=diff></p>
<p id=difflabel></p>
<p id=gap></p>
<p id=labeled></p>
<p id=rgap></p>
<p id=note></p>
</div>
<div id=stage>
<img id=view alt="camera">
<p id=caption></p>
<p id=stale hidden>no frame</p>
</div>
<script>
const view = document.getElementById("view");
let busy = false;
let epoch = 0;
let imgBad = false;
let tail = Promise.resolve();
function frame(){ view.src = "/frame.jpg?t=" + Date.now(); }
view.onload = () => { imgBad = false; setTimeout(frame, 200); };
view.onerror = () => { imgBad = true; document.getElementById("stale").hidden = false; setTimeout(frame, 800); };
frame();
function enqueue(work) {
  tail = tail.then(work, work).then(() => {}, () => {});
}
function currentCups() {
  const raw = document.getElementById("cups").value.trim();
  if (raw === "") return null;
  const n = Number(raw);
  if (!Number.isInteger(n) || n < 0 || n > 14) return null;
  return n;
}
function signed(n, digits) {
  const value = Number(n);
  const text = value.toFixed(digits);
  if (value > 0) return "+" + text;
  return text;
}
function statusLine(body) {
  const note = body.note || "";
  if (body.exposure == null) return note;
  if (/^exposure\b/i.test(note)) return note;
  const tracked = "exposure " + body.exposure;
  return note ? tracked + "  " + note : tracked;
}
function setPressButtons(reading) {
  const read = document.getElementById("read");
  read.textContent = reading ? "Reading" : "Read";
  const held = !!reading;
  read.disabled = held;
  document.getElementById("darker").disabled = held;
  document.getElementById("brighter").disabled = held;
}
function beginPress() {
  if (busy) return false;
  busy = true;
  epoch++;
  lock(true);
  document.getElementById("darker").disabled = true;
  document.getElementById("brighter").disabled = true;
  document.getElementById("read").disabled = true;
  return true;
}
function render(body) {
  const ratio = document.getElementById("ratio");
  const model = document.getElementById("model");
  const diff = document.getElementById("diff");
  const gap = document.getElementById("gap");
  const labeled = document.getElementById("labeled");
  const rgap = document.getElementById("rgap");
  const difflabel = document.getElementById("difflabel");
  document.getElementById("note").textContent = statusLine(body);
  const unit = body.known_cups === 1 ? "cup" : "cups";
  document.getElementById("caption").textContent = body.reading
    ? "Reading"
    : body.known_cups + " " + unit;
  if (!body.seen) {
    ratio.textContent = "";
    model.textContent = "";
    diff.textContent = "";
    difflabel.textContent = "";
    gap.textContent = "";
    rgap.textContent = "";
    labeled.textContent = body.labeled_text || "";
  } else if (!body.reservoir) {
    ratio.textContent = "No reservoir box.";
    model.textContent = "";
    diff.textContent = "";
    difflabel.textContent = "";
    gap.textContent = "";
    rgap.textContent = "";
    labeled.textContent = body.labeled_text || "";
  } else {
    ratio.textContent = body.box_ratio == null
      ? "box ratio no liquid line"
      : "box ratio " + Number(body.box_ratio).toFixed(3);
    model.textContent = "model " + Number(body.percent).toFixed(1) + "%    "
      + Number(body.cups).toFixed(2) + " cups";
    diff.textContent = signed(body.diff_cups, 2) + " cups    " + signed(body.diff_percent, 1) + "%";
    difflabel.textContent = "difference versus known cups";
    gap.textContent = body.bottom_gap_px == null
      ? "bottom gap no liquid line"
      : "bottom gap " + Math.round(body.bottom_gap_px) + " px";
    if (!body.has_labeled_line) {
      labeled.textContent = body.labeled_text || "";
      rgap.textContent = "";
    } else {
      labeled.textContent = "knot box ratio " + Number(body.labeled_box_ratio).toFixed(3);
      rgap.textContent = body.ratio_gap == null
        ? "ratio gap no liquid line"
        : "ratio gap " + signed(body.ratio_gap, 3);
    }
  }
  const stale = imgBad || body.frameAge == null || body.frameAge > 2;
  document.getElementById("stale").hidden = !stale;
  if (!busy) setPressButtons(body.reading);
}
function lock(on) {
  document.body.classList.toggle("locked", on);
}
async function post(path) {
  const cups = currentCups();
  if (cups == null) {
    document.getElementById("note").textContent = "Known cups are a whole number from 0 through 14.";
    return null;
  }
  return fetch(path, {
    method: "POST",
    cache: "no-store",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({known_cups: cups}),
  }).then(r => r.json());
}
function sendSettings() {
  if (busy) return;
  epoch++;
  enqueue(async () => {
    if (busy) return;
    const seen = epoch;
    try {
      const body = await post("/settings");
      if (body && seen === epoch && !busy) render(body);
    } catch (e) {
      if (seen === epoch) document.getElementById("note").textContent = "That setting did not save.";
    }
  });
}
async function doRead() {
  const seen = epoch;
  try {
    const body = await post("/read");
    if (body && seen === epoch) render(body);
  } catch (e) {
    if (seen === epoch) document.getElementById("note").textContent = "That reading did not finish.";
  } finally {
    busy = false;
    lock(false);
    setPressButtons(false);
  }
}
async function doExposure(path) {
  const seen = epoch;
  try {
    const body = await fetch(path, {method: "POST", cache: "no-store"}).then(r => r.json());
    if (body && seen === epoch) render(body);
  } catch (e) {
    if (seen === epoch) document.getElementById("note").textContent = "That exposure did not change.";
  } finally {
    busy = false;
    lock(false);
    setPressButtons(false);
  }
}
document.getElementById("read").onclick = () => {
  if (!beginPress()) return;
  document.getElementById("read").textContent = "Reading";
  enqueue(doRead);
};
document.getElementById("darker").onclick = () => {
  if (!beginPress()) return;
  enqueue(() => doExposure("/darker"));
};
document.getElementById("brighter").onclick = () => {
  if (!beginPress()) return;
  enqueue(() => doExposure("/brighter"));
};
document.getElementById("minus").onclick = () => {
  if (busy) return;
  const n = currentCups();
  const next = Math.max(0, (n == null ? 0 : n) - 1);
  document.getElementById("cups").value = String(next);
  sendSettings();
};
document.getElementById("plus").onclick = () => {
  if (busy) return;
  const n = currentCups();
  const next = Math.min(14, (n == null ? -1 : n) + 1);
  document.getElementById("cups").value = String(next);
  sendSettings();
};
document.getElementById("cups").addEventListener("change", () => {
  if (!busy) sendSettings();
});
if (navigator.wakeLock) {
  const ask = () => navigator.wakeLock.request("screen").catch(() => {});
  ask();
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible") ask();
  });
}
async function poll() {
  const seen = epoch;
  try {
    const body = await fetch("/status.json", {cache: "no-store"}).then(r => r.json());
    if (seen !== epoch || busy) return;
    render(body);
  } catch (e) {}
}
async function init() {
  try {
    const body = await fetch("/status.json", {cache: "no-store"}).then(r => r.json());
    document.getElementById("cups").value = body.known_cups;
    render(body);
  } catch (e) {}
  setInterval(poll, 250);
}
init();
</script>
""".encode()


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path == "/status.json":
            write_json(self, status())
            return
        if path == "/frame.jpg":
            jpg = displayed_jpeg()
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
            data = json_body(self)
            if path == "/read":
                read_frame(controls_from(data))
            elif path == "/settings":
                update_settings(controls_from(data))
            elif path == "/darker":
                nudge(2 / 3)
            elif path == "/brighter":
                nudge(3 / 2)
            else:
                self.send_error(404)
                return
        except (ValueError, json.JSONDecodeError) as error:
            set_note(str(error) or "That request was not understood.")
        except Exception:
            traceback.print_exc()
            set_note("That press failed.")
        write_json(self, status())

    def log_message(self, fmt, *args):
        return


def main():
    global model, id_names
    try:
        text = CLASSES.read_text(encoding="utf-8")
    except OSError as error:
        raise SystemExit(f"Missing class names at {CLASSES}: {error}") from error
    class_names = accuracy.read_class_names(text)
    id_names = id_names_from(text)
    if RESERVOIR not in class_names or LIQUID not in class_names:
        raise SystemExit(f"{CLASSES} must list {RESERVOIR} and {LIQUID}.")
    print(f"loading RFDETRNano device=cpu weights={WEIGHTS}", flush=True)
    model = accuracy.load_model(WEIGHTS, class_names)
    found = int(model.model.args.num_classes)
    if found != len(class_names):
        raise SystemExit(
            f"{CLASSES.name} has {len(class_names)} classes after the background line. "
            f"The checkpoint has {found}."
        )
    if len(id_names) != found + 1:
        raise SystemExit(
            f"{CLASSES.name} has {len(id_names)} lines. "
            f"The checkpoint has {found + 1} class slots."
        )
    threading.Thread(target=capture.capture, daemon=True).start()
    print("compare on :8080", flush=True)
    ThreadingHTTPServer(("0.0.0.0", 8080), Handler).serve_forever()


if __name__ == "__main__":
    main()
