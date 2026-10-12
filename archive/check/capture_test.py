#!/usr/bin/env python3
"""Test-split stills. Same walk as capture.py, saved apart from the training set.

Open http://<pi>:8080. Upload this folder into the Roboflow project as the test split.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import capture

ROOT = Path(__file__).resolve().parent.parent
capture.TRAIN = ROOT / "train" / "2026-10-10-clear-water-test"
capture.SHOOT = "Test"
capture.PAGE = capture.PAGE.replace(
    b"<title>capture</title>",
    b"<title>test capture</title>",
)

if __name__ == "__main__":
    capture.main()
