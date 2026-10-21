"""Clean, history-free snapshots of communication_mcu for each agent stage."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from .common import git, log, make_writable

GIT_ID = ["-c", "user.name=spec-loop", "-c", "user.email=spec-loop@localhost"]


def ws_path(cfg: dict, run_id: str, stage: str) -> Path:
    return Path(cfg["workspace_root"]) / run_id / stage


def extract(cfg: dict, dest: Path, paths: list[str] | None = None) -> None:
    """Extract the tree at base_sha (optionally limited to `paths`) into dest."""
    dest.mkdir(parents=True, exist_ok=True)
    archive = git(cfg["repo"], "archive", cfg["base_sha"], *(paths or []))
    subprocess.run(["tar", "-x", "-C", str(dest)], input=archive, check=True)


def build(cfg: dict, run_id: str, stage: str, inputs: dict[str, Path] | None = None) -> Path:
    """Create a fresh workspace for one stage.

    The snapshot has a single commit so that `git status` afterwards lists exactly
    what the agent wrote. When `inputs` is given (judge / synthesizer stages), the
    files are placed under `_inputs/` and `_outputs/` is created for the results.
    """
    ws = ws_path(cfg, run_id, stage)
    if ws.exists():
        make_writable(ws)
        shutil.rmtree(ws)
    extract(cfg, ws)

    cursor_src = Path(cfg["cursor_dir"])
    for sub, pattern in (("skills", "openspec-*"), ("commands", "opsx-*")):
        for src in sorted((cursor_src / sub).glob(pattern)):
            dst = ws / ".cursor" / sub / src.name
            dst.parent.mkdir(parents=True, exist_ok=True)
            if src.is_dir():
                shutil.copytree(src, dst)
            else:
                shutil.copy2(src, dst)

    if inputs is not None:
        for name, src in inputs.items():
            dst = ws / "_inputs" / name
            dst.parent.mkdir(parents=True, exist_ok=True)
            if src.is_dir():
                shutil.copytree(src, dst, symlinks=True)
            else:
                shutil.copy2(src, dst)
        (ws / "_outputs").mkdir(exist_ok=True)

    subprocess.run(["git", "init", "-q", str(ws)], check=True)
    git(ws, *GIT_ID, "add", "-A")
    git(ws, *GIT_ID, "commit", "-q", "-m", f"spec-loop base {cfg['base_sha'][:12]} ({stage})")
    log(f"workspace ready: {ws}")
    return ws


def changed_paths(ws: Path) -> list[str]:
    out = git(ws, "status", "--porcelain", "--untracked-files=all").decode("utf-8", "replace")
    paths = []
    for line in out.splitlines():
        if not line.strip():
            continue
        path = line[3:]
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        paths.append(path.strip('"'))
    return paths
