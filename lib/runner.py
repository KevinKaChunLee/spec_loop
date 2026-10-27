"""Run one headless Cursor CLI agent and capture its trajectory."""

from __future__ import annotations

import contextlib
import functools
import json
import os
import shutil
import signal
import subprocess
import threading
import time
from pathlib import Path

from .common import log, write_json
from .stream import parse_events, tool_call_key, usage_total

MAX_PROMPT_BYTES = 100_000
# The CLI does not list the GLM 5.3 ids and intermittently rejects them (or returns HTTP 5xx)
# at startup; long runs can also drop mid-way and are resumed in the same session.
STARTUP_ATTEMPTS = 4
STARTUP_RETRY_S = 30
CONTINUE_ATTEMPTS = 3
CONTINUE_PROMPT = ("Your previous turn was interrupted by a connection error. Continue the task from "
                   "where you stopped, following all of the original instructions.")
# Headless runs end as soon as the model replies without a tool call, which a model can do
# while still mid-task (for example after writing a plan as text).
NUDGE_PROMPT = """Your turn ended, but the task is not finished. Still missing:

{problems}

Continue now. Use your tools to create the missing files (do not only describe a plan or draft
instructions as text), follow all of the original instructions, and stop only when the task's
completion criteria are met."""
TRANSCRIPTS_ROOT = Path.home() / ".cursor" / "projects"
_slots = threading.BoundedSemaphore(8)
# Process groups of the agent sessions running now; each session runs in its own group, so it
# outlives this process unless it is stopped explicitly.
_live: set[int] = set()
# Callables that stop agents this process cannot signal itself, such as one running in a container.
_stop_hooks: set = set()


def stop_agents() -> None:
    """Terminate every agent session this process is running."""
    for pgid in list(_live):
        with contextlib.suppress(ProcessLookupError):
            os.killpg(pgid, signal.SIGTERM)
    for hook in list(_stop_hooks):
        with contextlib.suppress(Exception):
            hook()


def track_process(pgid: int) -> None:
    _live.add(pgid)


def untrack_process(pgid: int) -> None:
    _live.discard(pgid)


def add_stop_hook(hook) -> None:
    _stop_hooks.add(hook)


def remove_stop_hook(hook) -> None:
    _stop_hooks.discard(hook)


def agent_slot() -> threading.BoundedSemaphore:
    """The semaphore that caps agent sessions across all threads (and runners) of this process."""
    return _slots


def tool_version(cmd: list[str]) -> str:
    try:
        return subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                              text=True, timeout=60).stdout.strip() or "unknown"
    except (OSError, subprocess.TimeoutExpired):
        return "unknown"


@functools.cache
def _binary_version(path: str, _mtime_ns: int) -> str:
    return tool_version([path, "--version"])


def cli_version() -> str:
    """Version of the `agent` CLI on PATH. The CLI updates itself, so this is read per run: the
    installed binary lives in .../versions/<version>/; another layout is asked once per binary
    file (path and modification time)."""
    exe = shutil.which("agent")
    if not exe:
        return "unknown"
    real = Path(exe).resolve()
    if real.parent.parent.name == "versions":
        return real.parent.name
    return _binary_version(str(real), real.stat().st_mtime_ns)


def set_parallel_limit(n: int) -> None:
    """At most `n` agent sessions run at once across all threads of this process."""
    global _slots
    _slots = threading.BoundedSemaphore(max(1, n))


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
        _live.add(proc.pid)
        try:
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
        except BaseException:
            with contextlib.suppress(ProcessLookupError):
                os.killpg(proc.pid, signal.SIGTERM)
            raise
        finally:
            _live.discard(proc.pid)


def find_transcript(session_id: str) -> Path | None:
    if not session_id or not TRANSCRIPTS_ROOT.exists():
        return None
    for candidate in TRANSCRIPTS_ROOT.glob(f"*/agent-transcripts/{session_id}*"):
        return candidate
    return None


def run_agent(**kwargs) -> dict:
    with _slots:
        return _run_agent(**kwargs)


def _run_agent(*, model: dict, ws: Path, prompt: str, out_dir: Path, label: str,
               timeout_min: float, resume_session: str | None = None,
               completion_check=None, max_nudges: int = 0) -> dict:
    """Run `agent -p` in `ws`; write <label>.jsonl, <label>.stderr.log, <label>.run.json.

    Returns the run metadata. `ok` is True only if the stream ended with a
    non-error `result` event and the init event reported the expected model.
    `completion_check()` returns the deliverables still missing; while it reports
    any after a finished turn, the session is resumed with a nudge (at most
    `max_nudges` times). Whatever is still missing at the end is in `incomplete`.
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
    cli_start = cli_version()
    started = time.time()
    traj.write_text("", encoding="utf-8")
    errf.write_text("", encoding="utf-8")
    session, segment_prompt = resume_session, prompt
    startup_failures = continuations = nudges = 0
    inits: list[dict] = []
    results: list[dict] = []
    problems: list[str] = []
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
        seg_results = [e for e in segment if e.get("type") == "result"]
        results += seg_results
        session = session or (inits[0].get("session_id") if inits else None)
        if timed_out:
            break
        if seg_results:
            problems = completion_check() if completion_check else []
            if not problems or nudges >= max_nudges or not session:
                break
            nudges += 1
            log(f"  {label}: turn ended with deliverables missing ({'; '.join(problems)[:200]}); "
                f"nudging ({nudges}/{max_nudges})")
            segment_prompt = NUDGE_PROMPT.format(problems="\n".join(f"- {p}" for p in problems))
            continue
        if continuations >= CONTINUE_ATTEMPTS or not session:
            break
        continuations += 1
        log(f"  {label}: run stopped without a result ({_last_line(errf)}); resuming session "
            f"({continuations}/{CONTINUE_ATTEMPTS}) in {STARTUP_RETRY_S}s")
        time.sleep(STARTUP_RETRY_S)
        segment_prompt = CONTINUE_PROMPT

    init = inits[0] if inits else {}
    result = results[-1] if results else {}
    if completion_check:
        problems = completion_check()

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
    cli_end = cli_version()
    meta = {
        "label": label,
        "agent_cli": cli_start,
        **({"agent_cli_end": cli_end} if cli_end != cli_start else {}),
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
        "nudges": nudges,
        "incomplete": problems,
        "has_result": bool(result),
        "is_error": bool(result.get("is_error", not result)),
        "duration_s": round(time.time() - started, 1),
        "usage": usage_total(results),
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
