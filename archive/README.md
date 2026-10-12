These pages are the earlier shoots. The hook does not start them.

`check/board.py` is the process on port 8080. It still uses `check/capture.py` for the camera and `check/accuracy.py` for the tank model. Those two files stayed in `check/` because of that. Their own page entry points are not what a push starts.

Each file here imports `capture` from the directory it lives in. To run one again, move it back beside `check/capture.py` and stop the board first. One process owns `/dev/video0`.
