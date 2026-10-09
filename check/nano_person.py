"""Run RF-DETR Nano once on the Pi and print what it sees.

Same `predict` call as desk_supervisor.detect.detect_frame. That project
refuses to load the model unless CUDA is available. This script loads it
on CPU and reads a JPEG from the preview at http://127.0.0.1:8080/frame.jpg.
"""

import time
import urllib.request
from io import BytesIO

import numpy as np
import numpy.typing as npt
from PIL import Image
from rfdetr import RFDETRNano

PREVIEW_URL = "http://127.0.0.1:8080/frame.jpg"
THRESHOLD = 0.4
PERSON_CLASS_NAMES = ("person",)


def class_names(detections: object) -> npt.NDArray[np.object_]:
    data = getattr(detections, "data", {})
    raw = data.get("class_name") if isinstance(data, dict) else None
    if raw is None:
        return np.empty(0, dtype=object)
    return np.asarray(raw, dtype=object)


def grab_rgb() -> npt.NDArray[np.uint8]:
    with urllib.request.urlopen(PREVIEW_URL, timeout=5) as response:
        image = Image.open(BytesIO(response.read())).convert("RGB")
    return np.asarray(image, dtype=np.uint8)


def main() -> None:
    print("loading RFDETRNano device=cpu", flush=True)
    started = time.perf_counter()
    model = RFDETRNano(device="cpu")
    print(f"loaded_s={time.perf_counter() - started:.1f}", flush=True)

    frame = grab_rgb()
    print(f"warmup {frame.shape[1]}x{frame.shape[0]}", flush=True)
    _ = model.predict(frame, threshold=THRESHOLD, include_source_image=False)

    for index in range(3):
        frame = grab_rgb()
        tick = time.perf_counter()
        predicted = model.predict(frame, threshold=THRESHOLD, include_source_image=False)
        elapsed_ms = (time.perf_counter() - tick) * 1000
        names = class_names(predicted)
        confidence = getattr(predicted, "confidence", None)
        scores = [] if confidence is None else [float(score) for score in confidence]
        person_scores = [
            f"{score:.2f}"
            for name, score in zip(names, scores)
            if name in PERSON_CLASS_NAMES
        ]
        seen = ",".join(f"{name}:{score:.2f}" for name, score in zip(names, scores))
        print(
            f"frame={index} ms={elapsed_ms:.0f} n={len(names)} "
            f"person={len(person_scores)} person_conf={','.join(person_scores) or '-'} "
            f"seen={seen or '-'}",
            flush=True,
        )


if __name__ == "__main__":
    main()
