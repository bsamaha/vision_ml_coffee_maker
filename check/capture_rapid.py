#!/usr/bin/env python3
"""One press, one still, then upload it to the Roboflow project.

Open http://<pi>:8080. Pictures go to train/2026-10-10-clear-water-rapid/.
"""

import json
import os
import sys
import threading
import traceback
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import capture

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "train" / "2026-10-10-clear-water-rapid"
PROJECT = "rate-and-volume-of-coffee"
KEY_FILE = Path("/home/bs/tank-envs/roboflow.env")

saved = 0
next_n = 1
note = ""
state_lock = threading.Lock()


def set_note(text):
    global note
    with state_lock:
        note = text
    print(text, flush=True)


def next_index():
    nums = []
    if not OUT.is_dir():
        return 1
    for path in OUT.glob("*.jpg"):
        try:
            nums.append(int(path.stem))
        except ValueError:
            continue
    return max(nums, default=0) + 1


def api_key():
    found = os.environ.get("ROBOFLOW_API_KEY", "").strip()
    if found:
        return found
    for path in (KEY_FILE, ROOT / ".env"):
        try:
            text = path.read_text()
        except OSError:
            continue
        for line in text.splitlines():
            line = line.split("#", 1)[0].strip()
            if line.startswith("ROBOFLOW_API_KEY="):
                value = line.split("=", 1)[1].strip().strip('"').strip("'")
                if value:
                    return value
    return ""


def upload_image(path):
    key = api_key()
    if not key:
        return f"Saved {path.name}. No Roboflow key on this machine."
    boundary = "----tankboundary"
    payload = path.read_bytes()
    chunks = []

    def field(name, value):
        chunks.append(
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n\r\n{value}\r\n".encode()
        )

    field("name", path.name)
    field("split", "train")
    field("batch", "clear-water-rapid")
    field("tag", "clear-water-rapid")
    chunks.append(
        (
            f"--{boundary}\r\n"
            f"Content-Disposition: form-data; name=\"file\"; filename=\"{path.name}\"\r\n"
            "Content-Type: image/jpeg\r\n\r\n"
        ).encode()
        + payload
        + b"\r\n"
    )
    chunks.append(f"--{boundary}--\r\n".encode())
    body = b"".join(chunks)
    request = urllib.request.Request(
        f"https://api.roboflow.com/dataset/{PROJECT}/upload?api_key={key}",
        data=body,
        method="POST",
    )
    request.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            response.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:180]
        return f"Saved {path.name}. Upload failed ({exc.code}). {detail}"
    except OSError as exc:
        return f"Saved {path.name}. Upload failed. {exc}"
    return f"Saved {path.name} and uploaded it."


def take_one():
    global saved, next_n
    with capture.frame_lock:
        jpg = bytes(capture.latest)
    if not jpg:
        set_note("The camera has no frame yet.")
        return
    with state_lock:
        number = next_n
        next_n += 1
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"{number:04d}.jpg"
    path.write_bytes(jpg)
    if not capture.is_jpeg(path):
        path.unlink(missing_ok=True)
        with state_lock:
            next_n = number
        set_note("That frame was not a full picture. Press again.")
        return
    with state_lock:
        saved += 1
    set_note(upload_image(path))


def status():
    pair = capture.read_lock()
    with state_lock:
        count = saved
        shown = note
    return {
        "saved": count,
        "folder": "train/2026-10-10-clear-water-rapid",
        "focus": None if pair is None else pair[0],
        "exposure": None if pair is None else pair[1],
        "note": shown,
        "frameAge": capture.frame_age(),
    }


PAGE = """<!doctype html>
<meta name=viewport content="width=device-width,initial-scale=1,maximum-scale=1">
<title>rapid capture</title>
<style>
html,body{margin:0;height:100%}
body{background:#111;color:#fff;font:22px sans-serif;display:flex;flex-direction:column;height:100vh;height:100dvh}
#bar{padding:12px 16px;flex:0 0 auto}
#count{font:700 48px sans-serif;margin:0 0 8px}
button{font:28px sans-serif;padding:18px 22px;margin:0 8px 8px 0;touch-action:manipulation}
#stage{position:relative;flex:1 1 auto;min-height:50vh;background:#000}
#view{width:100%;height:100%;object-fit:contain;background:#000;display:block}
#stale{position:absolute;left:12px;top:12px;margin:0;background:#a30;color:#fff;font:700 28px sans-serif;padding:8px 12px}
</style>
<div id=bar>
<p id=count>0 saved</p>
<p id=line>One press saves one picture and uploads it.</p>
<p id=note></p>
<button id=save type=button>Capture Image</button>
<button id=darker type=button>Darker</button>
<button id=brighter type=button>Brighter</button>
</div>
<div id=stage>
<img id=view alt="camera">
<p id=stale hidden>no frame</p>
</div>
<script>
const view = document.getElementById("view");
const preload = new Image();
let imgBad = false;
let busy = false;
function frame(){ preload.src = "/frame.jpg?t=" + Date.now(); }
preload.onload = () => { imgBad = false; view.src = preload.src; setTimeout(frame, 1000); };
preload.onerror = () => { imgBad = true; document.getElementById("stale").hidden = false; setTimeout(frame, 1000); };
frame();
function show(body){
  const count = body.saved + " saved";
  const note = body.note || "";
  const countEl = document.getElementById("count");
  const noteEl = document.getElementById("note");
  if (countEl.textContent !== count) countEl.textContent = count;
  if (noteEl.textContent !== note) noteEl.textContent = note;
  const stale = imgBad || body.frameAge == null || body.frameAge > 2;
  document.getElementById("stale").hidden = !stale;
}
async function poll(){
  try { show(await fetch("/status.json", {cache:"no-store"}).then(r => r.json())); }
  catch (e) {}
}
async function press(path){
  if (busy) return;
  busy = true;
  try { show(await fetch(path, {method:"POST", cache:"no-store"}).then(r => r.json())); }
  catch (e) { document.getElementById("note").textContent = "That press did not finish."; }
  busy = false;
}
document.getElementById("save").onclick = () => press("/save");
document.getElementById("darker").onclick = () => press("/darker");
document.getElementById("brighter").onclick = () => press("/brighter");
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
            self._send(json.dumps(status()).encode(), "application/json")
            return
        if path == "/frame.jpg":
            with capture.frame_lock:
                jpg = bytes(capture.latest)
            if not jpg:
                self.send_error(503)
                return
            self._send(jpg, "image/jpeg")
            return
        if path in ("/", "/index.html"):
            self._send(PAGE, "text/html; charset=utf-8")
            return
        self.send_error(404)

    def do_POST(self):
        path = self.path.split("?", 1)[0]
        try:
            if path == "/save":
                take_one()
            elif path == "/darker":
                capture.nudge_exposure(2 / 3)
                set_note(capture.note)
            elif path == "/brighter":
                capture.nudge_exposure(3 / 2)
                set_note(capture.note)
            else:
                self.send_error(404)
                return
        except Exception:
            traceback.print_exc()
            set_note("That press failed. See /tmp/preview.log on the Pi.")
        self._send(json.dumps(status()).encode(), "application/json")

    def _send(self, body, content_type):
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        return


if __name__ == "__main__":
    next_n = next_index()
    saved = next_n - 1
    threading.Thread(target=capture.capture, daemon=True).start()
    print(f"rapid capture on :8080 writing {OUT}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", 8080), Handler).serve_forever()
