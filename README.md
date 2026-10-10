# Publish a change

You edit this directory on the PC. The Pi runs the commit you push.

## Push the commit

1. Commit the change.
2. From this directory, run `git push pi main`.
3. Wait until that command returns. The Pi restarts the capture page, and the command returns after port 8080 is open.
4. Open http://raspberrypi.local:8080.

If the install fails, the push fails and the preview that was already running stays up. If the new preview fails to listen, read `/tmp/preview.log` on the Pi.

## Change a dependency

1. Edit the pin in `pyproject.toml`.
2. From this directory, run `uv lock`.
3. Commit `pyproject.toml` and `uv.lock` together.
4. Push with the steps above.

The Pi installs that lock into a slot under `/home/bs/tank-envs/slots/`. An unchanged lock skips the install. `torch` and `torchvision` come from the CPU index named in `pyproject.toml`.

## What the Pi updates

`scripts/pi-receive` is the hook. A push checks that commit out into `/home/bs/tank`, installs the lock when the lock changed, and starts `check/capture_test.py` with that slot's Python. That page writes the test split. `check/capture.py` is the training-set page. `check/preview.py` is the boxed person page. The hook does not start preview during this shoot.

uv on the Pi is `/home/bs/.local/bin/uv`. Git does not track the slot or the weights. The weights are `/home/bs/.roboflow/models/`.

## Leave the camera to that process

Do not start `/home/bs/preview.py`. That file is an old copy. Do not start a second preview. One process owns `/dev/video0`.

## Leave these files uncommitted

Do not commit the slot, the weights, `train/` stills, `learn/`, or the kitchen photos. `.gitignore` already excludes a venv in this directory.
