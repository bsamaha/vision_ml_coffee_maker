import sqlite3
from pathlib import Path

import ledger

_KEEP = 8


def record(db: sqlite3.Connection, frames: Path, jpeg: bytes, one: ledger.Tick) -> ledger.Applied:
    if not jpeg:
        raise ValueError("JPEG bytes are empty.")
    applied = ledger.tick(db, one)
    frames.mkdir(parents=True, exist_ok=True)
    name = _next_name(frames)
    (frames / name).write_bytes(jpeg)
    _prune(frames)
    return applied


def _ordered(frames: Path) -> list[tuple[float, str]]:
    root = frames.resolve()
    found: list[tuple[float, str]] = []
    for path in frames.iterdir():
        if not path.is_file():
            continue
        name = path.name
        if path.suffix.lower() not in {".jpg", ".jpeg"}:
            continue
        if name in ("", ".", "..") or "/" in name or "\\" in name or "\x00" in name:
            continue
        if Path(name).name != name:
            continue
        if (frames / name).resolve().parent != root:
            continue
        found.append((path.stat().st_mtime, name))
    # Match page.live._frames: top-level .jpg/.jpeg, then (mtime, name).
    found.sort(key=lambda item: (item[0], item[1]))
    return found


def _next_name(frames: Path) -> str:
    highest = 0
    for _mtime, name in _ordered(frames):
        stem = Path(name).stem
        if len(stem) == 8 and stem.isdigit():
            highest = max(highest, int(stem))
    n = highest + 1
    while True:
        candidate = f"{n:08d}.jpg"
        if not (frames / candidate).exists():
            return candidate
        n += 1


def _prune(frames: Path) -> None:
    found = _ordered(frames)
    for _mtime, name in found[:-_KEEP]:
        (frames / name).unlink()
