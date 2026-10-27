"""Readers for `opencode run --format json` event streams: tool calls, text, errors, token usage,
and a readable trajectory.md with its stats.json."""

from __future__ import annotations

import json
import re
from pathlib import Path

# opencode tools that reach the internet; any use of them invalidates a solve.
WEB_TOOLS = {"webfetch", "websearch", "codesearch"}
NETWORK_RE = re.compile(r"\b(curl|wget|pip\s+(install|download)|git\s+(clone|fetch|pull|ls-remote)|"
                        r"apt(-get)?\s+install|conda\s+install)\b|https?://", re.I)


def parse(path: Path, offset: int = 0) -> list[dict]:
    """Events from byte `offset` on; lines that are not JSON objects are skipped."""
    if not path.exists():
        return []
    out = []
    with open(path, "rb") as f:
        f.seek(offset)
        for raw in f:
            try:
                ev = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if isinstance(ev, dict):
                out.append(ev)
    return out


def session_id(events: list[dict]) -> str | None:
    return next((e["sessionID"] for e in events if e.get("sessionID")), None)


def tool_calls(events: list[dict]) -> list[dict]:
    calls = []
    for e in events:
        if e.get("type") != "tool_use":
            continue
        part = e.get("part", {})
        state = part.get("state", {})
        meta = state.get("metadata") or {}
        times = state.get("time") or {}
        calls.append({"tool": part.get("tool", "?"), "status": state.get("status"),
                      "input": state.get("input") or {}, "title": state.get("title") or "",
                      "output": state.get("output") if state.get("output") is not None else state.get("error"),
                      "exit": meta.get("exit"), "seconds": round((times.get("end", 0) - times.get("start", 0)) / 1000, 1)
                      if times.get("end") else None})
    return calls


def texts(events: list[dict]) -> list[str]:
    return [e["part"].get("text", "") for e in events if e.get("type") == "text" and e.get("part")]


def errors(events: list[dict]) -> list[dict]:
    return [e.get("error") or {} for e in events if e.get("type") == "error"]


def finish_reason(events: list[dict]) -> str | None:
    """The reason of the last finished step: "stop" when the model ended its turn."""
    reasons = [e["part"].get("reason") for e in events if e.get("type") == "step_finish" and e.get("part")]
    return reasons[-1] if reasons else None


def usage(events: list[dict]) -> dict:
    total = {"steps": 0, "input": 0, "output": 0, "reasoning": 0, "cache_read": 0, "cache_write": 0, "cost": 0.0}
    for e in events:
        if e.get("type") != "step_finish":
            continue
        part = e.get("part", {})
        tok = part.get("tokens") or {}
        total["steps"] += 1
        for k in ("input", "output", "reasoning"):
            total[k] += tok.get(k) or 0
        total["cache_read"] += (tok.get("cache") or {}).get("read") or 0
        total["cache_write"] += (tok.get("cache") or {}).get("write") or 0
        total["cost"] += part.get("cost") or 0.0
    return total


def edited_files(calls: list[dict]) -> list[str]:
    return sorted({c["input"].get("filePath") or c["input"].get("path") or "" for c in calls
                   if c["tool"] in ("edit", "write", "patch", "multiedit")} - {""})


def network_attempts(calls: list[dict]) -> list[dict]:
    """Web tool calls, and shell commands that look like they reach the network, with whether
    they succeeded."""
    out = []
    for c in calls:
        if c["tool"] in WEB_TOOLS:
            out.append({"tool": c["tool"], "input": str(c["input"])[:300], "succeeded": c["status"] == "completed"})
        elif c["tool"] == "bash" and NETWORK_RE.search(str(c["input"].get("command", ""))):
            out.append({"tool": "bash", "input": str(c["input"].get("command"))[:300],
                        "succeeded": c["status"] == "completed" and c["exit"] == 0})
    return out


def stats(events: list[dict]) -> dict:
    calls = tool_calls(events)
    counts: dict[str, int] = {}
    for c in calls:
        counts[c["tool"]] = counts.get(c["tool"], 0) + 1
    times = [e.get("timestamp") for e in events if e.get("timestamp")]
    return {"session_id": session_id(events), "events": len(events), "tool_calls_total": len(calls),
            "tool_calls": counts, "tool_failures": sum(1 for c in calls if c["status"] == "error"
                                                       or (c["tool"] == "bash" and c["exit"] not in (0, None))),
            "files_edited": edited_files(calls), "web_calls": sum(1 for c in calls if c["tool"] in WEB_TOOLS),
            "errors": [str(e.get("data", {}).get("message") or e.get("name") or e)[:300] for e in errors(events)],
            "finish_reason": finish_reason(events), "usage": usage(events),
            "duration_s": round((max(times) - min(times)) / 1000, 1) if len(times) > 1 else 0.0}


def _short(value, limit: int) -> str:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    text = text.replace("\n", "\\n")
    return text if len(text) <= limit else text[:limit] + f" ...[+{len(text) - limit} chars]"


def digest(events: list[dict], limit: int = 80) -> list[str]:
    """One line per tool call, for the synthesizer: the call, its exit code and a little output."""
    lines = []
    for i, c in enumerate(tool_calls(events), 1):
        what = c["input"].get("command") or c["input"].get("filePath") or c["input"].get("pattern") or c["title"]
        status = c["status"] if c["exit"] is None else f"exit {c['exit']}"
        lines.append(f"{i}. {c['tool']} {_short(what, 160)} -> {status}: {_short(c['output'] or '', 120)}")
    if len(lines) > limit:
        lines = lines[: limit // 2] + [f"... {len(lines) - limit} calls omitted ..."] + lines[-limit // 2:]
    return lines


def render(events: list[dict], title: str) -> str:
    st = stats(events)
    u = st["usage"]
    out = [f"# {title}", "",
           f"- session {st['session_id']}, {st['tool_calls_total']} tool calls in {u['steps']} steps, "
           f"{st['duration_s'] / 60:.1f} min, finish: {st['finish_reason']}",
           f"- tokens: input {u['input']}, output {u['output']}, reasoning {u['reasoning']}, "
           f"cache read {u['cache_read']}",
           f"- tools: {', '.join(f'{k} {v}' for k, v in sorted(st['tool_calls'].items())) or 'none'}; "
           f"failures {st['tool_failures']}; web calls {st['web_calls']}",
           f"- edited: {', '.join(st['files_edited']) or 'nothing'}"]
    out += [f"- error: {e}" for e in st["errors"]]
    out.append("")
    n = 0
    for e in events:
        part = e.get("part", {})
        if e.get("type") == "tool_use":
            n += 1
            c = tool_calls([e])[0]
            what = c["input"].get("command") or c["input"].get("filePath") or c["input"].get("pattern") or c["input"]
            status = c["status"] if c["exit"] is None else f"exit {c['exit']}"
            out.append(f"[{n:04d}] {c['tool']} {_short(what, 300)} -> {status}, {len(str(c['output'] or ''))} chars")
        elif e.get("type") == "text" and part.get("text", "").strip():
            out.append(f"**SAY**: {_short(part['text'], 800)}")
        elif e.get("type") == "reasoning" and part.get("text", "").strip():
            out.append(f"**THINK** ({len(part['text'])} chars): {_short(part['text'], 300)}")
        elif e.get("type") == "error":
            out.append(f"**ERROR**: {_short(e.get('error'), 400)}")
    return "\n".join(out) + "\n"
