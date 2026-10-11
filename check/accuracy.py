#!/usr/bin/env python3
"""Phone page for the cup-line check. Open http://<pi>:8080.

Starts the camera thread from capture.py and serves this page. Does not call
capture.main(). One process owns /dev/video0. Start this when port 8080 is free.

The tank weights load once, at startup. That import stays inside load_model so
a machine without torch can still import this file.
"""

import json
import sys
import threading
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import NamedTuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
import capture
import volume

ROOT = Path(__file__).resolve().parent.parent
LOG = ROOT / "learn" / "accuracy.json"
WEIGHTS = Path("/home/bs/.roboflow/models/rate-and-volume-of-coffee-1/weights.pth")
CLASSES = WEIGHTS.parent / "class_names.txt"
RESERVOIR = "Reservoir"
LIQUID = "liquid-level"
THRESHOLD = 0.4
ROUNDS = 3
ACCURACY_CUPS = (4, 6, 8, 10, 14)


class Stop(NamedTuple):
    kind: str
    round: int | None
    cups: int
    title: str


def build_stops():
    # One camera angle. 4, 6, 8, 10, and 14 are each at or above 25% of 14 cups.
    # The 2-cup pour and the brew through 4 cups are the alarm check.
    # Those two rows stay out of the average.
    stops = []
    for round_n in range(1, ROUNDS + 1):
        for cups in ACCURACY_CUPS:
            stops.append(
                Stop(
                    "accuracy",
                    round_n,
                    cups,
                    f"Round {round_n} of {ROUNDS}. Pour to {cups} cups.",
                )
            )
    stops.append(Stop("alarm", None, 2, "Alarm. Pour to 2 cups."))
    stops.append(Stop("alarm", None, 4, "Alarm. One brew that falls through 4 cups."))
    return tuple(stops)


STOPS = build_stops()


def read_class_names(text):
    names = []
    for line in text.splitlines():
        name = line.strip()
        if not name or name.startswith("background_class"):
            continue
        names.append(name)
    return tuple(names)


def read_id_names(text):
    # The class id is the line index. background_class stays at 0.
    names = []
    for line in text.splitlines():
        name = line.strip()
        if name:
            names.append(name)
    return tuple(names)


def best_box(labels, scores, boxes, class_name):
    chosen = None
    chosen_score = -1.0
    for label, score, box in zip(labels, scores, boxes):
        label = str(label)
        if label.startswith("background_class") or label == "__background__":
            continue
        if label != class_name:
            continue
        score = float(score)
        if chosen is None or score > chosen_score:
            chosen = (float(box[0]), float(box[1]), float(box[2]), float(box[3]))
            chosen_score = score
    return chosen


def labels_for(predicted, names):
    # predict() renames the last logit to __background__. This checkpoint's last
    # logit is liquid-level, so the class file is the source of the name.
    class_ids = getattr(predicted, "class_id", None)
    if class_ids is not None:
        mapped = []
        for cid in class_ids:
            index = int(cid)
            if 0 <= index < len(names):
                mapped.append(names[index])
            else:
                mapped.append("__background__")
        return mapped
    data = getattr(predicted, "data", None)
    raw = data.get("class_name") if isinstance(data, dict) else None
    return [] if raw is None else [str(name) for name in raw]


def reading_for(known_cups, reservoir, liquid):
    """Image y grows downward. No liquid box is 0 cups. No reservoir is not a row."""
    if reservoir is None:
        return None
    if liquid is None:
        got = volume.reading(None)
        ratio = None
        gap = None
    else:
        ratio = volume.box_ratio(reservoir[1], reservoir[3], liquid[1])
        gap = abs(reservoir[3] - liquid[3])
        got = volume.reading(ratio)
    known = known_cups / volume.FULL_CUPS * 100
    return {
        "box_ratio": ratio,
        "bottom_gap_px": gap,
        "cups": got.cups,
        "percent": got.percent,
        "fluid_ounces": got.fluid_ounces,
        "diff_cups": got.cups - known_cups,
        "diff_percent": got.percent - known,
    }


def row_for_stop(stop, reservoir, liquid):
    measured = reading_for(stop.cups, reservoir, liquid)
    if measured is None:
        return None
    measured["kind"] = stop.kind
    measured["round"] = stop.round
    measured["known_cups"] = stop.cups
    measured["title"] = stop.title
    return measured


def abs_percent_average(saved):
    diffs = []
    for row in saved:
        if not isinstance(row, dict) or row.get("kind") != "accuracy":
            continue
        try:
            diffs.append(abs(float(row["diff_percent"])))
        except (KeyError, TypeError, ValueError):
            continue
    if not diffs:
        return None
    return sum(diffs) / len(diffs)


model = None
class_names = ()
id_names = ()
rows = []
note = ""
script_lock = threading.Lock()
busy = threading.Lock()


def load_rows():
    try:
        data = json.loads(LOG.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if isinstance(data, dict):
        data = data.get("rows", [])
    if not isinstance(data, list):
        return []
    return [row for row in data if isinstance(row, dict)]


def save_rows(saved):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    tmp = LOG.with_suffix(".json.tmp")
    tmp.write_text(json.dumps({"rows": saved}, indent=2) + "\n", encoding="utf-8")
    tmp.replace(LOG)


def set_note(text):
    global note
    with script_lock:
        note = text
    print(text, flush=True)


def begin():
    if busy.acquire(blocking=False):
        return True
    set_note("Wait for the current reading to finish.")
    return False


def summary(row):
    if row["box_ratio"] is None:
        ratio = "no liquid line"
    else:
        ratio = f"{row['box_ratio']:.3f}"
    if row["bottom_gap_px"] is None:
        gap = "no liquid line"
    else:
        gap = f"{row['bottom_gap_px']:.0f} px"
    return (
        f"{row['title']}  {row['percent']:.1f}%  {row['cups']:.2f} cups  "
        f"{row['fluid_ounces']:.1f} fl oz  {row['diff_cups']:+.2f} cups  "
        f"{row['diff_percent']:+.1f}% of full  box {ratio}  gap {gap}"
    )


def load_model(weights_path, names):
    from rfdetr import RFDETRNano

    tank = RFDETRNano(pretrain_weights=str(weights_path), device="cpu")
    tank.model.class_names = list(names)
    return tank


def rgb_array(jpg):
    from io import BytesIO

    import numpy as np
    from PIL import Image

    image = Image.open(BytesIO(jpg)).convert("RGB")
    return np.asarray(image, dtype=np.uint8)


def infer_row(jpg, stop):
    predicted = model.predict(rgb_array(jpg), threshold=THRESHOLD, include_source_image=False)
    if isinstance(predicted, list):
        predicted = predicted[0] if predicted else None
    if predicted is None:
        return row_for_stop(stop, None, None)
    labels = labels_for(predicted, id_names)
    scores = [] if predicted.confidence is None else predicted.confidence
    boxes = [] if predicted.xyxy is None else predicted.xyxy
    reservoir = best_box(labels, scores, boxes, RESERVOIR)
    liquid = best_box(labels, scores, boxes, LIQUID)
    return row_for_stop(stop, reservoir, liquid)


def record_reading():
    if not begin():
        return
    try:
        with script_lock:
            count = len(rows)
        if count >= len(STOPS):
            set_note("The check is already done.")
            return
        with capture.frame_lock:
            jpg = bytes(capture.latest)
        if not jpg:
            set_note("The camera has no frame yet.")
            return
        stop = STOPS[count]
        try:
            row = infer_row(jpg, stop)
        except Exception:
            traceback.print_exc()
            set_note("That reading failed.")
            return
        if row is None:
            set_note("No reservoir box. The reading was not saved.")
            return
        try:
            with script_lock:
                nxt = list(rows)
                nxt.append(row)
                save_rows(nxt)
                rows.append(row)
        except OSError:
            traceback.print_exc()
            set_note("That reading was not saved.")
            return
        set_note(summary(row))
    finally:
        busy.release()


def retake_last():
    if not begin():
        return
    try:
        message = ""
        with script_lock:
            if not rows:
                message = "There is no reading to retake."
            else:
                nxt = rows[:-1]
                try:
                    save_rows(nxt)
                except OSError:
                    traceback.print_exc()
                    message = "That retake was not saved."
                else:
                    rows.pop()
                    if len(rows) < len(STOPS):
                        message = f"Removed the last reading. {STOPS[len(rows)].title}"
                    else:
                        message = "Removed the last reading."
        set_note(message)
    finally:
        busy.release()


def status():
    with script_lock:
        saved = list(rows)
        shown = note
    done = len(saved) >= len(STOPS)
    stop = None if done else STOPS[len(saved)]
    return {
        "done": done,
        "index": len(saved),
        "total": len(STOPS),
        "title": "The check is done." if done else stop.title,
        "average": abs_percent_average(saved),
        "last": saved[-1] if saved else None,
        "rows": saved,
        "canRecord": not done,
        "canRetake": len(saved) > 0,
        "note": shown,
        "frameAge": capture.frame_age(),
    }


PAGE = """<!doctype html>
<meta name=viewport content="width=device-width,initial-scale=1,maximum-scale=1">
<title>accuracy</title>
<style>
html,body{margin:0;height:100%}
body{background:#111;color:#fff;font:22px sans-serif;display:flex;flex-direction:column;height:100vh;height:100dvh}
#bar{padding:12px 16px;flex:0 0 auto;max-height:46vh;overflow:auto}
#bar p{margin:0 0 8px}
#avg{font:700 48px sans-serif;line-height:1}
#avglabel,#raw,#lastlabel{font:16px sans-serif;color:#ddd}
#count{font:700 34px sans-serif;line-height:1.15}
#reading,#diff{font:700 30px sans-serif;line-height:1.2}
#record{display:block;width:100%;font:28px sans-serif;padding:18px;margin:0 0 10px;touch-action:manipulation}
#retake{font:16px sans-serif;padding:8px 12px;touch-action:manipulation}
#log p{margin:0 0 6px;font:16px sans-serif;color:#ddd}
#stage{position:relative;flex:1 1 auto;min-height:50vh;background:#000}
#view{width:100%;height:100%;object-fit:contain;background:#000;display:block}
#caption{position:absolute;left:0;right:0;bottom:0;margin:0;padding:10px 12px;background:rgba(0,0,0,.72);font:700 28px sans-serif}
#stale{position:absolute;left:12px;top:12px;margin:0;background:#a30;color:#fff;font:700 28px sans-serif;padding:8px 12px}
</style>
<div id=bar>
<p id=avg></p>
<p id=avglabel>average percent of full</p>
<p id=count></p>
<button id=record type=button>Record this reading</button>
<button id=retake type=button hidden>Retake last</button>
<p id=lastlabel></p>
<p id=reading></p>
<p id=diff></p>
<p id=raw></p>
<p id=note></p>
<div id=log></div>
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
function frame(){ view.src = "/frame.jpg?t=" + Date.now(); }
view.onload = () => { imgBad = false; setTimeout(frame, 200); };
view.onerror = () => { imgBad = true; document.getElementById("stale").hidden = false; setTimeout(frame, 800); };
frame();
function signed(n, digits){
  const value = Number(n);
  const text = value.toFixed(digits);
  if (value > 0) return "+" + text;
  return text;
}
function lineFor(row){
  const ratio = row.box_ratio == null ? "no liquid line" : Number(row.box_ratio).toFixed(3);
  const gap = row.bottom_gap_px == null ? "no liquid line" : Math.round(row.bottom_gap_px) + " px";
  return row.title + "  " + Number(row.percent).toFixed(1) + "%  "
    + Number(row.cups).toFixed(2) + " cups  "
    + signed(row.diff_cups, 2) + " cups  "
    + signed(row.diff_percent, 1) + "%  box " + ratio + "  gap " + gap;
}
function show(body){
  document.getElementById("avg").textContent = body.average == null ? "none yet" : Number(body.average).toFixed(1);
  document.getElementById("count").textContent = body.title || "";
  document.getElementById("caption").textContent = body.title || "";
  document.getElementById("note").textContent = body.note || "";
  const last = body.last;
  document.getElementById("lastlabel").textContent = last ? "Last reading" : "";
  if (!last) {
    document.getElementById("reading").textContent = "";
    document.getElementById("diff").textContent = "";
    document.getElementById("raw").textContent = "";
  } else {
    document.getElementById("reading").textContent =
      Number(last.percent).toFixed(1) + "%   "
      + Number(last.cups).toFixed(2) + " cups   "
      + Number(last.fluid_ounces).toFixed(1) + " fl oz";
    document.getElementById("diff").textContent =
      signed(last.diff_cups, 2) + " cups   "
      + signed(last.diff_percent, 1) + "% of full";
    const ratio = last.box_ratio == null ? "no liquid line" : Number(last.box_ratio).toFixed(3);
    const gap = last.bottom_gap_px == null ? "no liquid line" : Math.round(last.bottom_gap_px) + " px";
    document.getElementById("raw").textContent = "box ratio " + ratio + "    bottom gap " + gap;
  }
  const log = document.getElementById("log");
  log.replaceChildren();
  for (const row of body.rows || []) {
    const line = document.createElement("p");
    line.textContent = lineFor(row);
    log.appendChild(line);
  }
  const stale = imgBad || body.frameAge == null || body.frameAge > 2;
  document.getElementById("stale").hidden = !stale;
  document.getElementById("record").hidden = !body.canRecord;
  document.getElementById("retake").hidden = !body.canRetake;
}
async function poll(){
  const seen = epoch;
  try {
    const body = await fetch("/status.json", {cache:"no-store"}).then(r => r.json());
    if (seen !== epoch || busy) return;
    show(body);
  } catch (e) {}
}
async function press(id, path){
  if (busy) return;
  busy = true;
  epoch++;
  const record = document.getElementById("record");
  const retake = document.getElementById("retake");
  record.disabled = true;
  retake.disabled = true;
  if (id === "record") record.textContent = "Reading…";
  let body = null;
  try {
    body = await fetch(path, {method:"POST", cache:"no-store"}).then(r => r.json());
    epoch++;
    show(body);
  } catch (e) {
    epoch++;
    document.getElementById("note").textContent = "That step did not finish.";
  }
  if (id === "record") record.textContent = "Record this reading";
  record.disabled = false;
  retake.disabled = false;
  busy = false;
}
document.getElementById("record").onclick = () => press("record", "/record");
document.getElementById("retake").onclick = () => press("retake", "/retake");
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


def write_json(handler, payload):
    body = json.dumps(payload).encode()
    handler.send_response(200)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path == "/status.json":
            write_json(self, status())
            return
        if path == "/frame.jpg":
            with capture.frame_lock:
                jpg = bytes(capture.latest)
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
            if path == "/record":
                record_reading()
            elif path == "/retake":
                retake_last()
            else:
                self.send_error(404)
                return
        except Exception:
            traceback.print_exc()
            set_note("That press failed.")
        write_json(self, status())

    def log_message(self, fmt, *args):
        return


def main():
    global model, class_names, id_names, rows
    try:
        text = CLASSES.read_text(encoding="utf-8")
    except OSError as error:
        raise SystemExit(f"Missing class names at {CLASSES}: {error}") from error
    class_names = read_class_names(text)
    id_names = read_id_names(text)
    if RESERVOIR not in class_names or LIQUID not in class_names:
        raise SystemExit(f"{CLASSES} must list {RESERVOIR} and {LIQUID}.")
    print(f"loading RFDETRNano device=cpu weights={WEIGHTS}", flush=True)
    model = load_model(WEIGHTS, class_names)
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
    rows = load_rows()
    threading.Thread(target=capture.capture, daemon=True).start()
    print(f"accuracy on :8080  rows={len(rows)}  log={LOG}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", 8080), Handler).serve_forever()


if __name__ == "__main__":
    main()
