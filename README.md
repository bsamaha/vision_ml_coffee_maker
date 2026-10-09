# Publish a change

You edit this directory on the PC. The Pi runs the commit you push.

## Push the commit

1. Commit the change.
2. From this directory, run `git push pi main`.
3. Wait until that command returns. The Pi restarts the preview, and the command returns after port 8080 is open.
4. Open http://raspberrypi.local:8080.

If the push fails, read `/tmp/preview.log` on the Pi.

## What the Pi updates

`scripts/pi-receive` is the hook. A push checks that commit out into `/home/bs/tank` and starts `check/preview.py` with `/home/bs/nano-venv/bin/python`.

Git does not track the venv or the weights. The venv is `/home/bs/nano-venv`. The weights are `/home/bs/.roboflow/models/`.

## Leave the camera to that process

Do not start `/home/bs/preview.py`. That file is an old copy. Do not start a second preview. One process owns `/dev/video0`.

## Leave these files uncommitted

Do not commit the venv, the weights, `train/` stills, `learn/`, or the kitchen photos. `.gitignore` already excludes them.
