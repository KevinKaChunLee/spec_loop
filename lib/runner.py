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
from .stream import parse_events, tool_call_key

MAX_PROMPT_BYTES = 100_000
# The CLI does not list the GLM 5.3 ids and intermittently rejects them (or returns HTTP 5xx)
# at startup; long runs can also drop mid-way and are resumed in the same session.
STARTUP_ATTEMPTS = 4
STARTUP_RETRY_S = 30
CONTINUE_ATTEMPTS = 3
CONTINUE_PROMPT = ("Your previous turn was interrupted by a connection error. Continue the task from "
                   "where you stopped, following all of the original instructions.")
TRANSCRIPTS_ROOT = Path.home() / ".cursor" / "projects"


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
                kind, body = tool_call_key(ev) or ("?", {})
                args = body.get("args") or {}
                detail = args.get("path") or args.get("command") or args.get("pattern") or ""
                self.last_tool = f"{kind} {str(detail)[:80]}"
        return f"{self.tool_calls} tool calls, last: {self.last_tool or '-'}"


def _last_line(path: Path) -> str:
    lines = path.read_text(encoding="utf-8", errors="replace").strip().splitlines()
    return lines[-1][:160] if lines else "no stderr"


def _run_once(cmd: list[str], ws: Path, traj: Path, errf: Path, label: str, started: float,
              timeout_min: float) -> tuple[int, bool]:
    progress = _Progress(traj)
    progress.offset = traj.stat().st_size
    with open(traj, "a", encoding="utf-8") as fout, open(errf, "a", encoding="utf-8") as ferr:
        proc = subprocess.Popen(cmd, cwd=ws, stdout=fout, stderr=ferr, start_new_session=True)
        while True:
            try:
                return proc.wait(timeout=60), False
            except subprocess.TimeoutExpired:
                elapsed = time.time() - started
                log(f"  {label}: {elapsed / 60:.0f}m, {progress.poll()}")
                if elapsed > timeout_min * 60:
                    log(f"  {label}: timeout after {timeout_min}m, terminating")
                    os.killpg(proc.pid, signal.SIGTERM)
                    try:
                        return proc.wait(timeout=30), True
                    except subprocess.TimeoutExpired:
                        os.killpg(proc.pid, signal.SIGKILL)
                        return proc.wait(), True


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
    prompt_bytes = len(prompt.encode("utf-8"))
    if prompt_bytes > MAX_PROMPT_BYTES:
        raise ValueError(f"prompt is {prompt_bytes} bytes; the limit is "
                         f"{MAX_PROMPT_BYTES} (Linux caps one argv string at 128 KiB)")
    out_dir.mkdir(parents=True, exist_ok=True)
    traj = out_dir / f"{label}.jsonl"
    errf = out_dir / f"{label}.stderr.log"
    (out_dir / f"{label}.prompt.md").write_text(prompt, encoding="utf-8")

    base = ["agent", "-p", "--output-format", "stream-json", "--model", model["id"],
            "--force", "--trust", "--sandbox", "enabled", "--workspace", str(ws)]

    log(f"agent start: model={model['id']} ws={ws} label={label} timeout={timeout_min}m")
    started = time.time()
    traj.write_text("", encoding="utf-8")
    errf.write_text("", encoding="utf-8")
    session, segment_prompt = resume_session, prompt
    startup_failures = continuations = 0
    inits: list[dict] = []
    result: dict = {}
    while True:
        cmd = base + (["--resume", session] if session else []) + [segment_prompt]
        offset = traj.stat().st_size
        rc, timed_out = _run_once(cmd, ws, traj, errf, label, started, timeout_min)
        segment = list(parse_events(traj, offset))
        if not segment:
            startup_failures += 1
            if startup_failures >= STARTUP_ATTEMPTS:
                break
            log(f"  {label}: CLI failed before starting ({_last_line(errf)}); "
                f"retry {startup_failures}/{STARTUP_ATTEMPTS - 1} in {STARTUP_RETRY_S}s")
            time.sleep(STARTUP_RETRY_S)
            continue
        inits += [e for e in segment if e.get("type") == "system" and e.get("subtype") == "init"]
        result = next((e for e in reversed(segment) if e.get("type") == "result"), result)
        session = session or (inits[0].get("session_id") if inits else None)
        if timed_out or result:
            break
        if continuations >= CONTINUE_ATTEMPTS or not session:
            break
        continuations += 1
        log(f"  {label}: run stopped without a result ({_last_line(errf)}); resuming session "
            f"({continuations}/{CONTINUE_ATTEMPTS}) in {STARTUP_RETRY_S}s")
        time.sleep(STARTUP_RETRY_S)
        segment_prompt = CONTINUE_PROMPT

    init = inits[0] if inits else {}

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
        "model_ok": bool(inits) and all(e.get("model") == model["expect"] for e in inits),
        "session_id": session_id,
        "resumed_from": resume_session,
        "workspace": str(ws),
        "exit_code": rc,
        "timed_out": timed_out,
        "startup_retries": startup_failures,
        "continuations": continuations,
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
