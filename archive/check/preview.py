#!/usr/bin/env python3
"""Live webcam preview with RF-DETR Nano boxes. Open http://<pi>:8080."""

import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO

import numpy as np
from PIL import Image, ImageDraw

latest = b""
shown = b""
lock = threading.Lock()
THRESHOLD = 0.4

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
    "10",
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


def capture():
    global latest
    while True:
        proc = subprocess.Popen(FFMPEG, stdout=subprocess.PIPE)
        buf = b""
        try:
            while True:
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
                    with lock:
                        latest = jpg
        finally:
            proc.kill()
            proc.wait()
        time.sleep(1)


def draw_boxes(jpg: bytes, model: object) -> tuple[bytes, str]:
    image = Image.open(BytesIO(jpg)).convert("RGB")
    rgb = np.asarray(image, dtype=np.uint8)
    predicted = model.predict(rgb, threshold=THRESHOLD, include_source_image=False)
    names = predicted.data.get("class_name") if isinstance(predicted.data, dict) else None
    if names is None:
        labels = []
    else:
        labels = [str(name) for name in names]
    scores = [] if predicted.confidence is None else [float(score) for score in predicted.confidence]
    boxes = [] if predicted.xyxy is None else predicted.xyxy
    draw = ImageDraw.Draw(image)
    parts: list[str] = []
    for label, score, box in zip(labels, scores, boxes):
        color = (0, 220, 0) if label == "person" else (255, 170, 0)
        width = 5 if label == "person" else 2
        x1, y1, x2, y2 = (int(box[0]), int(box[1]), int(box[2]), int(box[3]))
        draw.rectangle((x1, y1, x2, y2), outline=color, width=width)
        draw.text((x1 + 4, max(0, y1 - 14)), f"{label} {score:.2f}", fill=color)
        parts.append(f"{label}:{score:.2f}")
    out = BytesIO()
    image.save(out, format="JPEG", quality=80)
    return out.getvalue(), ",".join(parts) or "-"


def infer() -> None:
    global shown
    from rfdetr import RFDETRNano

    print("loading RFDETRNano device=cpu", flush=True)
    started = time.perf_counter()
    model = RFDETRNano(device="cpu")
    print(f"loaded_s={time.perf_counter() - started:.1f}", flush=True)
    while True:
        with lock:
            raw = latest
        if not raw:
            time.sleep(0.1)
            continue
        tick = time.perf_counter()
        try:
            annotated, summary = draw_boxes(raw, model)
        except Exception as error:
            print(f"infer error {error}", flush=True)
            time.sleep(1)
            continue
        elapsed_ms = (time.perf_counter() - tick) * 1000
        with lock:
            shown = annotated
        print(f"ms={elapsed_ms:.0f} {summary}", flush=True)


PAGE = b"""<!doctype html>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>camera</title>
<style>
body{margin:0;background:#111}
img{width:100vw;height:100vh;object-fit:contain;background:#000}
</style>
<img id=f alt="camera">
<script>
const img = document.getElementById("f");
function tick(){ img.src = "/frame.jpg?t=" + Date.now(); }
img.onload = () => setTimeout(tick, 400);
img.onerror = () => setTimeout(tick, 800);
tick();
</script>
"""


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith("/frame.jpg"):
            with lock:
                jpg = shown or latest
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
        if self.path in ("/", "/index.html"):
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
    threading.Thread(target=capture, daemon=True).start()
    threading.Thread(target=infer, daemon=True).start()
    print("preview on :8080", flush=True)
    ThreadingHTTPServer(("0.0.0.0", 8080), Handler).serve_forever()
