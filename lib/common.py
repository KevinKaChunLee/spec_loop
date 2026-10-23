"""Paths, config, run state and small file helpers shared by all stages."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "runs"
PROMPTS = ROOT / "prompts"


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def die(msg: str) -> None:
    print(f"error: {msg}", file=sys.stderr, flush=True)
    sys.exit(1)


def load_config() -> dict:
    return json.loads((ROOT / "config.json").read_text(encoding="utf-8"))


def read_json(path: Path, default=None):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def git(repo: Path | str, *args: str, input: bytes | None = None) -> bytes:
    return subprocess.run(["git", "-C", str(repo), *args], input=input,
                          stdout=subprocess.PIPE, check=True).stdout


def run_dir(run_id: str) -> Path:
    return RUNS / run_id


def iter_dir(run_id: str, k: int) -> Path:
    return run_dir(run_id) / f"iter-{k:02d}"


def load_state(run_id: str) -> dict:
    state = read_json(run_dir(run_id) / "state.json")
    if state is None:
        die(f"run '{run_id}' is not prepared; run `loop.py prepare --run {run_id}` first")
    return state


def save_state(run_id: str, state: dict) -> None:
    write_json(run_dir(run_id) / "state.json", state)


def remove_tree(path: Path) -> None:
    """Delete a directory tree, including read-only files such as a frozen spec copy."""
    if path.exists():
        make_writable(path)
        shutil.rmtree(path)


def copy_tree(src: Path, dst: Path) -> None:
    remove_tree(dst)
    shutil.copytree(src, dst, symlinks=True)


def make_writable(path: Path) -> None:
    for p in [path, *path.rglob("*")] if path.is_dir() else [path]:
        try:
            mode = p.lstat().st_mode
            if not stat.S_ISLNK(mode):
                os.chmod(p, mode | stat.S_IWUSR)
        except FileNotFoundError:
            pass


def make_readonly(path: Path) -> None:
    for p in [path, *path.rglob("*")]:
        mode = p.lstat().st_mode
        if not stat.S_ISLNK(mode):
            os.chmod(p, mode & ~(stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH))


def prompt(name: str, **values: str) -> str:
    """Read prompts/<name> and substitute {{key}} placeholders."""
    text = (PROMPTS / name).read_text(encoding="utf-8")
    for key, value in values.items():
        text = text.replace("{{" + key + "}}", value)
    return text
