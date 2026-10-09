# Tank proof

Edit this repo on the PC. `git push pi main` checks the same commit out on the Pi and restarts the preview.

Open http://raspberrypi.local:8080

The Pi keeps its own Python env at `/home/bs/nano-venv` and the Nano weights at `/home/bs/.roboflow/models/`. Those are not in git.

One process owns `/dev/video0`. Do not start a second preview.
