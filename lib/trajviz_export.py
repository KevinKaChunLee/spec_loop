"""Convert a Cursor CLI stream-json trajectory into a TrajViz-loadable Cursor export.

TrajViz's own Cursor collector (`agent-trajviz-collect cursor`) needs the IDE's
state.vscdb for tool results, which CLI sessions never write. The CLI stream has
them (plus tool clocks and reasoning), so this builds the same
`cursor_composer` schema directly. Subagent sessions come from the copied IDE-format
transcripts, which carry tool inputs only.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from .common import timestamp, write_text_atomic
from .stream import bookends, content_text, parse_events, tool_call_key, usage_total

TOOL_NAMES = {
    "read": "Read", "shell": "Shell", "edit": "StrReplace", "write": "Write", "delete": "Delete",
    "grep": "Grep", "glob": "Glob", "ls": "LS", "task": "Task", "updateTodos": "TodoWrite",
    "todo": "TodoWrite", "webSearch": "WebSearch", "webFetch": "WebFetch", "readLints": "ReadLints",
}
SHELL_INPUT_KEYS = ("command", "workingDirectory", "timeout", "isBackground")
NOISE_KEYS = {"toolCallId", "parsingResult", "simpleCommands", "hasInputRedirect", "hasOutputRedirect"}


def _clip(text: str, n: int) -> str:
    return text if len(text) <= n else text[:n] + f"\n...[truncated {len(text) - n} chars]"


def _dump(value) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False)


def _ms(value) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _tokens(role: str, parts: list[dict]) -> dict:
    text = sum(len(p.get("text", "")) for p in parts if p.get("type") in ("text", "reasoning"))
    tin = sum(len(_dump(p["state"].get("input"))) for p in parts if p.get("type") == "tool")
    tout = sum(len(_dump(p["state"].get("output"))) for p in parts if p.get("type") == "tool")
    tok = lambda c: max(1, (c + 3) // 4) if c > 0 else 0
    if role == "user":
        return {"input": tok(text), "output": 0, "total": tok(text)} if text else {}
    out = tok(text) + tok(tin)
    total = out + tok(tout)
    return {"input": tok(tout), "output": out, "total": total} if total else {}


def _tool_input(name: str, args: dict, cap: int) -> dict:
    if name == "Shell":
        return {k: args[k] for k in SHELL_INPUT_KEYS if k in args}
    clean = {}
    for k, v in (args or {}).items():
        if k in NOISE_KEYS:
            continue
        clean[k] = _clip(v, cap) if isinstance(v, str) else v
    return clean


def _fill_result(part: dict, kind: str, result, cap: int) -> None:
    state = part["state"]
    if not isinstance(result, dict):
        state["status"] = "unknown"
        return
    body = result.get("success")
    if body is None and kind == "shell" and isinstance(result.get("failure"), dict):
        body = result["failure"]
    if body is None:
        other = {k: v for k, v in result.items() if k != "isBackground"}
        state["status"] = "error"
        state["output"] = _clip(_dump(other), cap)
        err = other.get("error")
        state["error"] = _dump(err.get("error") if isinstance(err, dict) else err)[:2000]
        return
    state["status"] = "completed"
    meta = state["metadata"]
    if kind == "shell":
        out = body.get("interleavedOutput") or ((body.get("stdout") or "") + (body.get("stderr") or ""))
        state["output"] = _clip(out, cap)
        meta["exit"] = body.get("exitCode")
        if body.get("executionTime") is not None:
            meta["executionTimeMs"] = body.get("executionTime")
    elif kind == "read":
        state["output"] = _clip(_dump(body.get("content")), cap)
        meta["totalLines"] = body.get("totalLines")
    elif kind in ("edit", "write"):
        state["output"] = _clip(_dump(body.get("diffString") or body.get("message")), cap)
        meta["linesAdded"] = body.get("linesAdded")
        meta["linesRemoved"] = body.get("linesRemoved")
    else:
        state["output"] = _clip(_dump(body), cap)


def _subagent_sessions(transcripts: Path | None) -> list[tuple[str, list[dict]]]:
    if not transcripts or not transcripts.exists():
        return []
    return [(f.stem, list(parse_events(f))) for f in sorted(transcripts.rglob("subagents/*.jsonl"))]


def _first_user_text(events: list[dict]) -> str:
    return next((content_text(ev, "text") for ev in events if ev.get("role") == "user"), "")


def _subagent_messages(child: str, parent: str, events: list[dict], model: str) -> list[dict]:
    messages = []
    for i, ev in enumerate(events):
        role = ev.get("role")
        if role not in ("user", "assistant"):
            continue
        mid = f"{child}:{role}:{i}"
        parts = []
        for block in (ev.get("message") or {}).get("content") or []:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "text" and block.get("text"):
                parts.append({"type": "text", "text": block["text"], "id": f"{mid}:text:{len(parts)}",
                              "sessionID": child, "messageID": mid})
            elif block.get("type") in ("tool_use", "tool_call"):
                cid = block.get("id") or f"{child}:tool:{i}:{len(parts)}"
                parts.append({"type": "tool", "tool": block.get("name") or "?", "callID": cid, "id": cid,
                              "sessionID": child, "messageID": mid,
                              "state": {"status": "unknown", "input": block.get("input") or {},
                                        "output": "", "metadata": {}}})
        info = {"role": role, "id": mid, "sessionID": child, "agent": "cursor", "isSubAgent": True,
                "sessionDepth": 1, "parentSessionID": parent, "modelID": model}
        tokens = _tokens(role, parts)
        if tokens:
            info["tokens"] = tokens
        messages.append({"info": info, "parts": parts})
    return messages


def convert(traj: Path, ws: Path, transcripts: Path | None, title: str, output_cap: int = 20000) -> dict:
    events = list(parse_events(traj))
    init, result = bookends(events)
    sid = init.get("session_id") or result.get("session_id") or traj.stem
    model = init.get("model") or ""

    messages: list[dict] = []
    pending: dict[str, dict] = {}
    cur: dict | None = None
    last_ts = 0
    first_ts = 0

    def new_message(role: str) -> dict:
        mid = f"{sid}:{role}:{len(messages)}"
        msg = {"info": {"role": role, "id": mid, "sessionID": sid, "agent": "cursor",
                        "isSubAgent": False, "sessionDepth": 0, "modelID": model},
               "parts": [], "_ts": [], "_mcid": None}
        messages.append(msg)
        return msg

    def stamp(msg: dict, ts: int) -> None:
        if ts:
            msg["_ts"].append(ts)

    for ev in events:
        t = ev.get("type")
        ts = _ms(ev.get("timestamp_ms")) or last_ts
        if ts:
            first_ts = first_ts or ts
            last_ts = max(last_ts, ts)
        if t == "user":
            msg = new_message("user")
            msg["parts"].append({"type": "text", "text": content_text(ev),
                                 "id": f"{msg['info']['id']}:text:0",
                                 "sessionID": sid, "messageID": msg["info"]["id"]})
            stamp(msg, ts)
            cur = None
        elif t == "thinking" and ev.get("subtype") == "delta":
            if cur is None or (cur["parts"] and cur["parts"][-1]["type"] != "reasoning"):
                cur = new_message("assistant")
            if cur["parts"] and cur["parts"][-1]["type"] == "reasoning":
                part = cur["parts"][-1]
                part["text"] += ev.get("text", "")
                part["time"]["end"] = ts
            else:
                cur["parts"].append({"type": "reasoning", "text": ev.get("text", ""),
                                     "time": {"start": ts, "end": ts},
                                     "id": f"{cur['info']['id']}:reasoning:{len(cur['parts'])}",
                                     "sessionID": sid, "messageID": cur["info"]["id"]})
            stamp(cur, ts)
        elif t == "tool_call":
            parsed = tool_call_key(ev)
            if parsed is None:
                continue
            kind, body = parsed
            name = TOOL_NAMES.get(kind, kind[:1].upper() + kind[1:])
            cid = ev.get("call_id") or body.get("toolCallId") or f"{sid}:tool:{len(pending)}"
            mcid = ev.get("model_call_id")
            part = pending.get(cid)
            if part is None:
                if cur is None or (mcid and cur["_mcid"] and cur["_mcid"] != mcid):
                    cur = new_message("assistant")
                cur["_mcid"] = cur["_mcid"] or mcid
                part = {"type": "tool", "tool": name, "callID": cid, "id": cid, "sessionID": sid,
                        "messageID": cur["info"]["id"],
                        "state": {"status": "running", "input": _tool_input(name, body.get("args") or {},
                                                                            output_cap),
                                  "output": "", "metadata": {}, "time": {}}}
                cur["parts"].append(part)
                pending[cid] = part
                part["_kind"] = kind
            start = _ms(body.get("startedAtMs")) or (ts if ev.get("subtype") == "started" else 0)
            if start and not part["state"]["time"].get("start"):
                part["state"]["time"]["start"] = start
            if ev.get("subtype") == "completed":
                _fill_result(part, kind, body.get("result"), output_cap)
                end = _ms(body.get("completedAtMs")) or ts
                if end:
                    part["state"]["time"]["end"] = end
                tm = part["state"]["time"]
                if tm.get("start") and tm.get("end") and tm["end"] >= tm["start"]:
                    part["state"]["metadata"]["totalDurationMs"] = tm["end"] - tm["start"]
            if cur is not None:
                stamp(cur, ts)
        elif t == "assistant":
            text = content_text(ev, "text")
            if not text:
                continue
            if cur is None:
                cur = new_message("assistant")
            cur["parts"].append({"type": "text", "text": text,
                                 "id": f"{cur['info']['id']}:text:{len(cur['parts'])}",
                                 "sessionID": sid, "messageID": cur["info"]["id"]})
            stamp(cur, ts)
        elif t == "result" and cur is not None:
            cur["info"]["finish"] = "error" if ev.get("is_error") else "success"

    children = _subagent_sessions(transcripts)
    first_prompts = {child: _first_user_text(evs) for child, evs in children}
    linked: set[str] = set()
    for msg in messages:
        for part in msg["parts"]:
            if part.get("type") != "tool" or part["tool"] != "Task":
                continue
            prompt = str(part["state"]["input"].get("prompt", ""))[:200]
            for child, first_prompt in first_prompts.items():
                if child not in linked and prompt and prompt in first_prompt:
                    linked.add(child)
                    part["state"]["metadata"]["sessionId"] = child
                    part["state"]["metadata"]["parentSessionId"] = sid
                    break

    additions = deletions = 0
    files: set[str] = set()
    for msg in messages:
        info = msg["info"]
        ts_list = msg.pop("_ts")
        msg.pop("_mcid", None)
        for part in msg["parts"]:
            if part.get("type") == "tool":
                kind = part.pop("_kind", "")
                if kind in ("edit", "write"):
                    additions += part["state"]["metadata"].get("linesAdded") or 0
                    deletions += part["state"]["metadata"].get("linesRemoved") or 0
                    if part["state"]["input"].get("path"):
                        files.add(part["state"]["input"]["path"])
                for k in ("start", "end"):
                    if part["state"]["time"].get(k):
                        ts_list.append(part["state"]["time"][k])
                if not part["state"]["time"]:
                    del part["state"]["time"]
        if ts_list:
            info["time"] = {"created": min(ts_list), "completed": max(ts_list)}
        tokens = _tokens(info["role"], msg["parts"])
        if tokens:
            info["tokens"] = tokens

    all_messages = list(messages)
    sessions = [{"id": sid, "parent_id": None, "depth": 0, "title": title,
                 "transcript_path": str(traj), "message_count": len(messages)}]
    for child, evs in children:
        sub = _subagent_messages(child, sid, evs, model)
        all_messages.extend(sub)
        sessions.append({"id": child, "parent_id": sid, "depth": 1, "title": "",
                         "transcript_path": str(transcripts), "message_count": len(sub)})

    tool_parts = [p for m in all_messages for p in m["parts"] if p.get("type") == "tool"]
    warnings = []
    if not result:
        warnings.append("stream has no result event (run did not finish)")
    if children:
        warnings.append("subagent sessions come from IDE-format transcripts: tool inputs only, no outputs")
    info = {
        "id": sid, "title": title, "directory": str(ws), "status": "completed" if result else "aborted",
        "model": model, "modelConfig": {"modelName": model},
        "time": {"created": first_ts, "updated": last_ts},
        "summary": {"additions": additions, "deletions": deletions, "files": len(files)},
        "usageData": usage_total(events),
        "subagentComposerIds": [c for c, _ in children],
    }
    return {
        "info": info,
        "messages": all_messages,
        "sessions": sessions,
        "statistics": {
            "sessions": len(sessions), "subagent_sessions": len(children),
            "total_messages": len(all_messages),
            "user_messages": sum(1 for m in all_messages if m["info"]["role"] == "user"),
            "assistant_messages": sum(1 for m in all_messages if m["info"]["role"] == "assistant"),
            "tool_parts": len(tool_parts),
            "tool_parts_with_output": sum(1 for p in tool_parts if p["state"].get("output")),
        },
        "export_metadata": {
            "schema_version": 1, "source_format": "cursor_composer",
            "generator_name": "spec_loop_cli_stream",
            "generated_at": timestamp(),
            "chat_id": sid, "transcript_path": str(traj), "database_path": "",
            "token_semantics": "estimated_log_tokens; real CLI run totals in info.usageData",
            "complete": bool(result), "warnings": warnings,
        },
    }


def export(cfg: dict, traj: Path, ws: Path, transcripts: Path | None, out_dir: Path, name: str,
           title: str) -> dict:
    """Write <out_dir>/<name>.trajviz.json and, if TrajViz is installed, its views and HTML report."""
    tv = cfg.get("trajviz", {})
    out_dir.mkdir(parents=True, exist_ok=True)
    data = convert(traj, ws, transcripts, title, tv.get("output_chars", 20000))
    path = out_dir / f"{name}.trajviz.json"
    write_text_atomic(path, json.dumps(data, ensure_ascii=False))
    status = {"export": str(path), "views": None, "report": None, "errors": []}
    binary = Path(tv.get("bin", ""))
    if not tv.get("bin") or not binary.exists():
        return status
    for flag, target, key in (("--json", out_dir / f"{name}.views", "views"),
                              ("--report", out_dir / f"{name}.html", "report")):
        if key == "report" and not tv.get("html_report", True):
            continue
        proc = subprocess.run([str(binary), flag, str(path), "-o", str(target)],
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=600)
        if proc.returncode == 0:
            status[key] = str(target)
        else:
            status["errors"].append(f"{flag}: {(proc.stderr or proc.stdout)[-500:]}")
    return status
