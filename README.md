# Publish a change

You edit this directory on the Mac. The Pi runs the commit you push. Login and network details are in [hardware.md](hardware.md); how the board works is in [technical-solution.md](technical-solution.md).

## Test

The tests use only the standard library, so they run without the Pi's packages:

```sh
for t in check/*_test.py page/*_test.py; do uv run --no-project python "$t"; done
```

## Push the commit

1. Commit the change.
2. Push: `GIT_SSH_COMMAND="sshpass -e ssh -o PubkeyAuthentication=no -o PreferredAuthentications=password" git push pi main`, with the Pi's password in `SSHPASS`.
3. Wait until that command returns. The hook installs the lock if it changed, restarts `check/board.py`, and returns once port 8080 is open.
4. Open http://192.168.1.248:8080 and wait for the Raspberry Pi row to say Roboflow Workflow on local Inference.

If the install fails, the push fails and the board that was already running stays up. If the new board does not start, read `/tmp/preview.log` on the Pi.

Do not push during the demo. A restart takes over a minute while `inference` imports and both models load.

## Change a dependency

1. Edit the pin in `pyproject.toml`.
2. Run `uv lock --python-preference managed`. The project only allows a system Python, and the Mac's is not 3.12; the lock does not depend on which interpreter wrote it.
3. Commit `pyproject.toml` and `uv.lock` together, then push.

The Pi installs that lock into a slot under `/home/bs/tank-envs/slots/`, and an unchanged lock skips the install. `torch` and `torchvision` come from the CPU index named in `pyproject.toml`.

A large install downloads hundreds of megabytes over the Pi's Wi-Fi, and the push's SSH session can drop partway through, which stops the hook. The ref is already on the Pi by then. Run the hook there, detached from SSH, and watch its log:

```sh
echo "0 <commit sha> refs/heads/<branch>" > /tmp/deploy.stdin
setsid nohup sh -c 'sh /home/bs/tank.git/hooks/post-receive < /tmp/deploy.stdin > /tmp/deploy.log 2>&1; echo "hook exit $?" >> /tmp/deploy.log' >/dev/null 2>&1 </dev/null &
tail -f /tmp/deploy.log
```

The same command with an older commit is the rollback.

## Change the Workflow

`workflow/tank-gauge.json` is generated. After changing `check/tank_gauge.py`, `check/volume.py`, or `check/workflow.py`, run `python check/workflow.py --export workflow/tank-gauge.json`, commit the JSON, and paste it into the Roboflow Workflow editor so the app matches the Pi. A test fails if the committed JSON falls behind.

## What stays out of git

The slot, `train/` stills, `learn/`, the kitchen photos, the Workflow's model cache in `/home/bs/.inference/cache`, and the Roboflow API key. On the Pi the key is in `/home/bs/tank-envs/roboflow.env`; on the Mac it is in `.env`, which `.gitignore` excludes. One process owns `/dev/video0`, so do not start anything else that opens the camera while the board is up.
