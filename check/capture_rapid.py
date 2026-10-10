#!/usr/bin/env python3
"""Rapid stills. One button saves a new frame about twice a second.

Open http://<pi>:8080. Pictures go to train/2026-10-10-clear-water-rapid/.
"""

import json
import sys
import threading
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import capture

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "train" / "2026-10-10-clear-water-rapid"
INTERVAL = 0.5

firing = False
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


def rapid_loop():
    global saved, next_n
    last_seq = -1
    while True:
        with state_lock:
            go = firing
        if not go:
            time.sleep(0.05)
            continue
        with capture.frame_lock:
            seq = capture.frame_seq
            jpg = bytes(capture.latest)
        if not jpg or seq == last_seq:
            time.sleep(0.05)
            continue
        last_seq = seq
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
            time.sleep(0.05)
            continue
        with state_lock:
            saved += 1
        set_note(f"Saved {path.name}")
        time.sleep(INTERVAL)


def status():
    pair = capture.read_lock()
    with state_lock:
        count = saved
        on = firing
        shown = note
    return {
        "firing": on,
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
#fire.on{background:#c33;color:#fff}
#stage{position:relative;flex:1 1 auto;min-height:50vh;background:#000}
#view{width:100%;height:100%;object-fit:contain;background:#000;display:block}
#stale{position:absolute;left:12px;top:12px;margin:0;background:#a30;color:#fff;font:700 28px sans-serif;padding:8px 12px}
</style>
<div id=bar>
<p id=count>0 saved</p>
<p id=line>Move the coffee maker. Press Rapid fire. Press it again to stop.</p>
<p id=note></p>
<button id=fire type=button>Rapid fire</button>
<button id=darker type=button>Darker</button>
<button id=brighter type=button>Brighter</button>
</div>
<div id=stage>
<img id=view alt="camera">
<p id=stale hidden>no frame</p>
</div>
<script>
const view = document.getElementById("view");
let imgBad = false;
function frame(){ view.src = "/frame.jpg?t=" + Date.now(); }
view.onload = () => { imgBad = false; setTimeout(frame, 200); };
view.onerror = () => { imgBad = true; document.getElementById("stale").hidden = false; setTimeout(frame, 800); };
frame();
function show(body){
  document.getElementById("count").textContent = body.saved + " saved";
  document.getElementById("note").textContent = body.note || "";
  const fire = document.getElementById("fire");
  fire.textContent = body.firing ? "Stop" : "Rapid fire";
  fire.classList.toggle("on", body.firing);
  const stale = imgBad || body.frameAge == null || body.frameAge > 2;
  document.getElementById("stale").hidden = !stale;
}
async function poll(){
  try { show(await fetch("/status.json", {cache:"no-store"}).then(r => r.json())); }
  catch (e) {}
}
async function press(path){
  try { show(await fetch(path, {method:"POST", cache:"no-store"}).then(r => r.json())); }
  catch (e) { document.getElementById("note").textContent = "That press did not finish."; }
}
document.getElementById("fire").onclick = () => press("/fire");
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
            body = json.dumps(status()).encode()
            self._send(body, "application/json")
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
        global firing
        path = self.path.split("?", 1)[0]
        try:
            if path == "/fire":
                with state_lock:
                    firing = not firing
                set_note("Rapid fire on." if firing else "Rapid fire off.")
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
    threading.Thread(target=capture.capture, daemon=True).start()
    threading.Thread(target=rapid_loop, daemon=True).start()
    print(f"rapid capture on :8080 writing {OUT}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", 8080), Handler).serve_forever()
