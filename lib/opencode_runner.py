"""Run one opencode agent session (`opencode run --format json`) and capture its event stream.

The caller says how to launch opencode (directly, or inside a container through `docker exec`), so
the same runner serves the solve and synthesis stages. A run that fails for reasons outside the
model's control (the endpoint unreachable, server errors) is resumed in the same session; a run in
which the model itself fails is a result, not an error."""

from __future__ import annotations

import contextlib
import json
import os
import signal
import subprocess
import time
from pathlib import Path
from typing import Callable

from . import opencode_stream as ocs
from . import runner
from .common import log, write_json, write_text_atomic
from .runner import CONTINUE_PROMPT

# Switches for a reproducible run that needs no network besides the model endpoint: no model
# catalogue fetch, no self-update, no LSP downloads, no Claude Code configuration from the host, no
# default plugins and no external skills.
OPENCODE_ENV = {"OPENCODE_DISABLE_MODELS_FETCH": "1", "OPENCODE_DISABLE_AUTOUPDATE": "1",
                "OPENCODE_DISABLE_LSP_DOWNLOAD": "1", "OPENCODE_DISABLE_CLAUDE_CODE": "1",
                "OPENCODE_DISABLE_DEFAULT_PLUGINS": "1", "OPENCODE_DISABLE_EXTERNAL_SKILLS": "1"}
PROVIDER = "sglang"
STARTUP_ATTEMPTS = 3
CONTINUE_ATTEMPTS = 2
RETRY_S = 30
NUDGE_PROMPT = """Your turn ended, but the task is not finished:

{problems}

Continue now. Use your tools to make the change, follow all of the original instructions, and stop
only when the task is done."""


def opencode_config(base_url: str, model: dict, api_key: str) -> dict:
    """An opencode.json with one OpenAI-compatible provider (an SGLang server) serving `model`, which
    also writes session titles, and only the tools a solve needs: no web access, no reading outside
    the working directory."""
    return {"$schema": "https://opencode.ai/config.json", "autoupdate": False, "share": "disabled",
            "small_model": model_ref(model["id"]),
            "provider": {PROVIDER: {"npm": "@ai-sdk/openai-compatible", "name": "SGLang",
                                    "options": {"baseURL": base_url, "apiKey": api_key},
                                    "models": {model["id"]: {"name": model["id"], "tool_call": True,
                                                             "limit": {"context": model["context"],
                                                                       "output": model["output"]}}}}},
            "permission": {"webfetch": "deny", "bash": "allow", "edit": "allow", "external_directory": "deny"}}


def model_ref(model_id: str) -> str:
    return f"{PROVIDER}/{model_id}"


def opencode_version(binary: str) -> str:
    try:
        return subprocess.run([binary, "--version"], capture_output=True, text=True, timeout=60).stdout.strip() \
            or "unknown"
    except (OSError, subprocess.TimeoutExpired):
        return "unknown"


def infra_error(events: list[dict], rc: int) -> str | None:
    """Why a segment failed outside the model's control, or None."""
    if not events:
        return f"no events (exit {rc})"
    for err in reversed(ocs.errors(events)):
        data = err.get("data") or {}
        if err.get("name") in ("APIError", "ProviderInitError", "ProviderAuthError") or data.get("isRetryable"):
            return f"{err.get('name')}: {str(data.get('message') or err)[:300]}"
    return None


Launcher = Callable[[list[str]], tuple[list[str], dict | None]]


def _stop(proc: subprocess.Popen, kill_agent: Callable[[], None]) -> None:
    """Stop the agent (inside its container too) and the process group; either may be gone already."""
    with contextlib.suppress(OSError, subprocess.TimeoutExpired):
        kill_agent()
    with contextlib.suppress(ProcessLookupError):
        os.killpg(proc.pid, signal.SIGTERM)


def _segment(argv: list[str], env: dict | None, traj: Path, errf: Path, label: str, started: float,
             timeout_min: float, kill_agent: Callable[[], None]) -> tuple[int, bool]:
    offset = traj.stat().st_size
    with open(traj, "a", encoding="utf-8") as fout, open(errf, "a", encoding="utf-8") as ferr:
        proc = subprocess.Popen(argv, stdout=fout, stderr=ferr, env=env, start_new_session=True)
        runner.track_process(proc.pid)
        try:
            while True:
                try:
                    return proc.wait(timeout=60), False
                except subprocess.TimeoutExpired:
                    elapsed = time.time() - started
                    calls = ocs.tool_calls(ocs.parse(traj, offset))
                    last = f"{calls[-1]['tool']} {str(calls[-1]['title'])[:70]}" if calls else "-"
                    log(f"  {label}: {elapsed / 60:.0f}m, {len(calls)} tool calls, last: {last}")
                    if elapsed > timeout_min * 60:
                        log(f"  {label}: timeout after {timeout_min}m, stopping the agent")
                        _stop(proc, kill_agent)
                        try:
                            return proc.wait(timeout=30), True
                        except subprocess.TimeoutExpired:
                            with contextlib.suppress(ProcessLookupError):
                                os.killpg(proc.pid, signal.SIGKILL)
                            return proc.wait(), True
        except BaseException:
            _stop(proc, kill_agent)
            raise
        finally:
            runner.untrack_process(proc.pid)


def run_opencode(*, launch: Launcher, model: str, workdir: str, prompt: str, out_dir: Path, label: str,
                 timeout_min: float, completion_check: Callable[[], list[str]], max_nudges: int,
                 kill_agent: Callable[[], None], resume_session: str | None = None) -> dict:
    """Run one session in `workdir`; write <label>.jsonl, .stderr.log, .run.json, .transcript.json,
    <label>.md and <label>.stats.json. While `completion_check()` reports problems after a finished
    turn, the session is resumed with a nudge (at most `max_nudges` times)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    traj, errf = out_dir / f"{label}.jsonl", out_dir / f"{label}.stderr.log"
    (out_dir / f"{label}.prompt.md").write_text(prompt, encoding="utf-8")
    traj.write_text("", encoding="utf-8")
    errf.write_text("", encoding="utf-8")
    session, text = resume_session, prompt
    startup = continuations = nudges = 0
    rc, timed_out, infra, problems = 0, False, None, []
    with runner.agent_slot():
        log(f"opencode start: model={model} dir={workdir} label={label} timeout={timeout_min}m")
        started = time.time()
        while True:
            args = ["run", "--format", "json", "-m", model_ref(model), "--dir", workdir, "--auto",
                    *(["--session", session] if session else []), text]
            argv, env = launch(args)
            offset = traj.stat().st_size
            rc, timed_out = _segment(argv, env, traj, errf, label, started, timeout_min, kill_agent)
            segment = ocs.parse(traj, offset)
            session = session or ocs.session_id(segment)
            infra = None if timed_out else infra_error(segment, rc)
            if timed_out:
                break
            if not segment:
                startup += 1
                if startup >= STARTUP_ATTEMPTS:
                    break
                log(f"  {label}: opencode produced no events (exit {rc}); retry {startup}/{STARTUP_ATTEMPTS - 1} "
                    f"in {RETRY_S}s")
                time.sleep(RETRY_S)
                continue
            if infra:
                if continuations >= CONTINUE_ATTEMPTS or not session:
                    break
                continuations += 1
                log(f"  {label}: {infra}; resuming the session ({continuations}/{CONTINUE_ATTEMPTS}) in {RETRY_S}s")
                time.sleep(RETRY_S)
                text = CONTINUE_PROMPT
                continue
            problems = completion_check()
            if not problems or nudges >= max_nudges or not session:
                break
            nudges += 1
            log(f"  {label}: turn ended unfinished ({'; '.join(problems)[:200]}); nudging ({nudges}/{max_nudges})")
            text = NUDGE_PROMPT.format(problems="\n".join(f"- {p}" for p in problems))
        if session:
            argv, env = launch(["export", session])
            try:
                exported = subprocess.run(argv, env=env, capture_output=True, text=True, timeout=120).stdout
                json.loads(exported)
                write_text_atomic(out_dir / f"{label}.transcript.json", exported)
            except (subprocess.TimeoutExpired, json.JSONDecodeError, OSError) as e:
                log(f"  {label}: could not export the session transcript: {e}")

    events = ocs.parse(traj)
    st = ocs.stats(events)
    finish = st["finish_reason"]
    meta = {"label": label, "model": model, "session_id": session, "resumed_from": resume_session,
            "workdir": workdir, "exit_code": rc, "timed_out": timed_out, "startup_retries": startup,
            "continuations": continuations, "nudges": nudges, "incomplete": problems,
            "finish_reason": finish, "infra_error": infra if infra else (None if events else "no events"),
            "duration_s": round(time.time() - started, 1), "usage": st["usage"],
            "tool_calls": st["tool_calls_total"]}
    meta["ok"] = not timed_out and not meta["infra_error"] and finish == "stop"
    write_json(out_dir / f"{label}.run.json", meta)
    write_json(out_dir / f"{label}.stats.json", st)
    write_text_atomic(out_dir / f"{label}.md", ocs.render(events, f"{label} ({model})", st))
    log(f"opencode done: {label} {'ok' if meta['ok'] else 'NOT OK'} in {meta['duration_s'] / 60:.1f}m "
        f"({st['tool_calls_total']} tool calls, finish {finish}"
        + (f", {meta['infra_error']}" if meta["infra_error"] else "") + ")")
    return meta
