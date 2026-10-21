"""Run one headless Cursor CLI agent and capture its trajectory."""

from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import time
from pathlib import Path

from .common import log, write_json

MAX_PROMPT_BYTES = 100_000
TRANSCRIPTS_ROOT = Path.home() / ".cursor" / "projects"


def _parse_events(path: Path):
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


class _Progress:
    """Tails the stream file to print a liveness line once a minute."""

    def __init__(self, path: Path):
        self.path = path
        self.offset = 0
        self.tool_calls = 0
        self.last_tool = ""
        self.buf = b""

    def poll(self) -> str:
        try:
            with open(self.path, "rb") as f:
                f.seek(self.offset)
                data = f.read()
                self.offset = f.tell()
        except FileNotFoundError:
            return "no output yet"
        self.buf += data
        *lines, self.buf = self.buf.split(b"\n")
        for raw in lines:
            try:
                ev = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if ev.get("type") == "tool_call" and ev.get("subtype") == "started":
                self.tool_calls += 1
                tc = ev.get("tool_call") or {}
                kind = next(iter(tc), "?")
                args = (tc.get(kind) or {}).get("args") or {}
                detail = args.get("path") or args.get("command") or args.get("pattern") or ""
                self.last_tool = f"{kind.replace('ToolCall', '')} {str(detail)[:80]}"
        return f"{self.tool_calls} tool calls, last: {self.last_tool or '-'}"


def find_transcript(session_id: str) -> Path | None:
    if not session_id or not TRANSCRIPTS_ROOT.exists():
        return None
    for candidate in TRANSCRIPTS_ROOT.glob(f"*/agent-transcripts/{session_id}*"):
        return candidate
    return None


def run_agent(*, model: dict, ws: Path, prompt: str, out_dir: Path, label: str,
              timeout_min: float, resume_session: str | None = None) -> dict:
    """Run `agent -p` in `ws`; write <label>.jsonl, <label>.stderr.log, <label>.run.json.

    Returns the run metadata. `ok` is True only if the stream ended with a
    non-error `result` event and the init event reported the expected model.
    """
    if len(prompt.encode("utf-8")) > MAX_PROMPT_BYTES:
        raise ValueError(f"prompt is {len(prompt.encode('utf-8'))} bytes; the limit is "
                         f"{MAX_PROMPT_BYTES} (Linux caps one argv string at 128 KiB)")
    out_dir.mkdir(parents=True, exist_ok=True)
    traj = out_dir / f"{label}.jsonl"
    errf = out_dir / f"{label}.stderr.log"
    (out_dir / f"{label}.prompt.md").write_text(prompt, encoding="utf-8")

    cmd = ["agent", "-p", "--output-format", "stream-json", "--model", model["id"],
           "--force", "--trust", "--sandbox", "enabled", "--workspace", str(ws)]
    if resume_session:
        cmd += ["--resume", resume_session]
    cmd.append(prompt)

    log(f"agent start: model={model['id']} ws={ws} label={label} timeout={timeout_min}m")
    started = time.time()
    timed_out = False
    progress = _Progress(traj)
    with open(traj, "w", encoding="utf-8") as fout, open(errf, "w", encoding="utf-8") as ferr:
        proc = subprocess.Popen(cmd, cwd=ws, stdout=fout, stderr=ferr, start_new_session=True)
        while True:
            try:
                rc = proc.wait(timeout=60)
                break
            except subprocess.TimeoutExpired:
                elapsed = time.time() - started
                log(f"  {label}: {elapsed / 60:.0f}m, {progress.poll()}")
                if elapsed > timeout_min * 60:
                    timed_out = True
                    log(f"  {label}: timeout after {timeout_min}m, terminating")
                    os.killpg(proc.pid, signal.SIGTERM)
                    try:
                        rc = proc.wait(timeout=30)
                    except subprocess.TimeoutExpired:
                        os.killpg(proc.pid, signal.SIGKILL)
                        rc = proc.wait()
                    break

    init, result = {}, {}
    for ev in _parse_events(traj):
        if ev.get("type") == "system" and ev.get("subtype") == "init" and not init:
            init = ev
        elif ev.get("type") == "result":
            result = ev

    session_id = init.get("session_id") or result.get("session_id") or resume_session or ""
    transcript_src = find_transcript(session_id)
    transcript_dst = None
    if transcript_src is not None:
        transcript_dst = out_dir / "transcripts" / label / transcript_src.name
        transcript_dst.parent.mkdir(parents=True, exist_ok=True)
        if transcript_dst.exists():
            shutil.rmtree(transcript_dst) if transcript_dst.is_dir() else transcript_dst.unlink()
        if transcript_src.is_dir():
            shutil.copytree(transcript_src, transcript_dst)
        else:
            shutil.copy2(transcript_src, transcript_dst)

    model_reported = init.get("model", "")
    meta = {
        "label": label,
        "model_id": model["id"],
        "model_expected": model["expect"],
        "model_reported": model_reported,
        "model_ok": model_reported == model["expect"],
        "session_id": session_id,
        "resumed_from": resume_session,
        "workspace": str(ws),
        "exit_code": rc,
        "timed_out": timed_out,
        "has_result": bool(result),
        "is_error": bool(result.get("is_error", not result)),
        "duration_s": round(time.time() - started, 1),
        "usage": result.get("usage", {}),
        "final_text": (result.get("result") or "")[:4000],
        "transcript_project": transcript_src.parent.parent.name if transcript_src else None,
        "transcript_copy": str(transcript_dst) if transcript_dst else None,
    }
    meta["ok"] = meta["has_result"] and not meta["is_error"] and meta["model_ok"] and not timed_out
    write_json(out_dir / f"{label}.run.json", meta)
    status = "ok" if meta["ok"] else "FAILED"
    log(f"agent done: {label} {status} in {meta['duration_s'] / 60:.1f}m "
        f"(model reported '{model_reported}', exit {rc})")
    if not meta["model_ok"]:
        log(f"  model mismatch: expected '{model['expect']}', got '{model_reported}'")
    return meta
