"""Paths, config, run state and small file helpers shared by all stages."""

from __future__ import annotations

import contextlib
import fcntl
import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "runs"
PROMPTS = ROOT / "prompts"
_log_lock = threading.Lock()
_run_locks: list = []


def log(msg: str) -> None:
    # One write per line under a lock: print() writes the text and the newline separately, which
    # lets lines from parallel threads run into each other.
    line = f"[{time.strftime('%H:%M:%S')}] {msg}\n"
    with _log_lock:
        sys.stdout.write(line)
        sys.stdout.flush()


def timestamp() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def die(msg: str) -> None:
    print(f"error: {msg}", file=sys.stderr, flush=True)
    sys.exit(1)


def load_config() -> dict:
    return json.loads((ROOT / "config.json").read_text(encoding="utf-8"))


def read_json(path: Path, default=None):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_text_atomic(path: Path, text: str) -> None:
    """Write and fsync a sibling temporary file, then rename it over `path`, so neither a reader
    nor a crash of the process or the machine ever sees a truncated file. The rename would replace
    a read-only `path` regardless of its mode, so that is refused here, as a plain write would."""
    if path.exists() and not os.access(path, os.W_OK):
        raise PermissionError(f"{path} is read-only")
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def write_json(path: Path, data) -> None:
    write_text_atomic(path, json.dumps(data, ensure_ascii=False, indent=2) + "\n")


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


def lock_run(run_id: str, scopes: tuple[str, ...], command: str) -> None:
    """Hold runs/.<run>.<scope>.lock for every scope until this process exits; die when another
    loop.py process holds one of them. The lock files sit beside the run directory, so a run that
    is still being created is locked as well."""
    RUNS.mkdir(exist_ok=True)
    for scope in scopes:
        f = open(RUNS / f".{run_id}.{scope}.lock", "a+", encoding="utf-8")
        try:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            f.seek(0)
            holder = f.read().strip() or "unknown"
            f.close()
            die(f"run '{run_id}' is in use by another loop.py process ({holder}); wait for it to finish or stop it")
        f.seek(0)
        f.truncate()
        f.write(f"pid {os.getpid()}, started {timestamp()}: loop.py {command}\n")
        f.flush()
        _run_locks.append(f)


@contextlib.contextmanager
def state_update(run_id: str):
    """Load state.json for the caller to change, and save it when the block ends, holding
    runs/.<run>.state.lock throughout: commands of different lock scopes may run side by side and
    must not lose each other's updates. Other processes wait for the block, so keep it short."""
    RUNS.mkdir(exist_ok=True)
    with open(RUNS / f".{run_id}.state.lock", "a+", encoding="utf-8") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        state = load_state(run_id)
        yield state
        save_state(run_id, state)


def remove_tree(path: Path) -> None:
    """Delete a directory tree, including read-only files such as a frozen spec copy."""
    if path.exists():
        make_writable(path)
        shutil.rmtree(path)


def keep_attempt(out_dir: Path) -> None:
    """Move a superseded run aside as <out_dir>.attemptN (not read as a sample)."""
    n = 1
    while out_dir.with_name(f"{out_dir.name}.attempt{n}").exists():
        n += 1
    out_dir.rename(out_dir.with_name(f"{out_dir.name}.attempt{n}"))


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
