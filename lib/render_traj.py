"""Turn a CLI stream-json trajectory into a readable trajectory.md and stats.json."""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

from .common import write_json
from .stream import bookends, content_text, parse_events, tool_call_key

PATH_KEYS = ("path", "file_path", "target_file", "targetFile", "filePath")
SHELL_READ_RE = re.compile(r"(?:^|[;&|(]\s*|\s)(cat|head|tail|sed|nl|less|more|awk|bat)\s")
SHELL_PATH_RE = re.compile(r"[\w./-]+\.(?:cpp|h|c|gn|gni|json)\b")


def _rel(path: str, ws: Path) -> str:
    if not path:
        return path
    p = str(path)
    prefix = str(ws).rstrip("/") + "/"
    if p.startswith(prefix):
        return p[len(prefix):]
    if p == str(ws):
        return "."
    return p


def _clip(text, n: int) -> str:
    text = "" if text is None else str(text)
    text = text.replace("\r", "")
    return text if len(text) <= n else text[:n] + f" ...[+{len(text) - n} chars]"


def _one_line(text, n: int) -> str:
    return _clip(" ".join(str(text or "").split()), n)


def _summarize_call(kind: str, args: dict, result: dict | None, ws: Path, preview: int):
    """Return (call description, result description, failed flag, extra facts)."""
    facts: dict = {}
    failed = False
    res_desc = ""
    success = None
    if isinstance(result, dict):
        success = result.get("success")
        if success is None and kind == "shell" and isinstance(result.get("failure"), dict):
            success = result["failure"]
        if success is None:
            failed = True
            other = {k: v for k, v in result.items() if k != "isBackground"}
            res_desc = "FAILED " + _one_line(json.dumps(other, ensure_ascii=False), preview)
    elif result is None:
        res_desc = "(no result)"

    if kind == "read":
        path = _rel(args.get("path", ""), ws)
        facts["read"] = path
        rng = ""
        if args.get("offset") or args.get("limit"):
            rng = f" offset={args.get('offset')} limit={args.get('limit')}"
        desc = f"read {path}{rng}"
        if isinstance(success, dict):
            res_desc = f"{success.get('totalLines', '?')} lines"
    elif kind == "shell":
        cmd = args.get("command", "")
        facts["command"] = cmd
        if SHELL_READ_RE.search(cmd):
            facts["shell_reads"] = [_rel(p, ws) for p in SHELL_PATH_RE.findall(cmd)]
        desc = f"shell `{_one_line(cmd, 300)}`"
        if isinstance(success, dict):
            code = success.get("exitCode")
            facts["exit_code"] = code
            out = (success.get("stdout") or "") + (success.get("stderr") or "")
            n_lines = out.count("\n")
            res_desc = f"exit {code}, {n_lines} lines"
            if code not in (0, None):
                failed = True
                res_desc += ": " + _one_line(out[-preview:], preview)
    elif kind in ("edit", "write"):
        path = _rel(args.get("path", ""), ws)
        facts["written"] = path
        desc = f"{kind} {path}"
        if isinstance(success, dict):
            res_desc = f"+{success.get('linesAdded', '?')} -{success.get('linesRemoved', '?')}"
    elif kind == "delete":
        path = _rel(args.get("path", ""), ws)
        facts["written"] = path
        desc = f"delete {path}"
    elif kind == "grep":
        path = _rel(args.get("path", "") or ".", ws)
        desc = f"grep /{_one_line(args.get('pattern', ''), 120)}/ in {path}"
        if isinstance(success, dict):
            files, hits = 0, 0
            for wr in (success.get("workspaceResults") or {}).values():
                content = (wr or {}).get("content") or (wr or {}).get("files") or {}
                for m in content.get("matches", []) if isinstance(content, dict) else []:
                    files += 1
                    hits += len(m.get("matches", [])) if isinstance(m, dict) else 0
                hits = content.get("totalMatchedLines", hits) if isinstance(content, dict) else hits
            res_desc = f"{hits} matches in {files} files" if files or hits else \
                _one_line(json.dumps(success, ensure_ascii=False)[:preview], preview)
    elif kind in ("glob", "ls"):
        target = args.get("globPattern") or args.get("glob_pattern") or args.get("pattern") or ""
        path = _rel(args.get("path") or args.get("targetDirectory") or "", ws)
        desc = f"{kind} {target} {path}".strip()
    elif kind == "task":
        facts["subagent"] = True
        desc = f"SUBAGENT {_one_line(args.get('description') or '', 80)}: " \
               f"{_one_line(args.get('prompt') or '', preview)}"
        if isinstance(success, dict):
            res_desc = _one_line(json.dumps(success, ensure_ascii=False), preview)
    else:
        desc = f"{kind} {_one_line(json.dumps(args, ensure_ascii=False), preview)}"
        if isinstance(success, dict):
            res_desc = _one_line(json.dumps(success, ensure_ascii=False), preview)
    if "web" in kind.lower():
        facts["web"] = True
    return desc, res_desc, failed, facts


def tool_calls(events):
    """Yield (kind, args, result) for each completed (or dangling started) tool call."""
    started: dict[str, tuple[str, dict]] = {}
    order: list[str] = []
    done: dict[str, dict | None] = {}
    for ev in events:
        parsed = tool_call_key(ev) if ev.get("type") == "tool_call" else None
        if parsed is None:
            continue
        kind, body = parsed
        cid = ev.get("call_id") or f"anon-{len(order)}"
        if ev.get("subtype") == "started":
            started[cid] = (kind, body.get("args") or {})
            order.append(cid)
        elif ev.get("subtype") == "completed":
            if cid not in started:
                started[cid] = (kind, body.get("args") or {})
                order.append(cid)
            done[cid] = body.get("result")
    for cid in order:
        kind, args = started[cid]
        yield kind, args, done.get(cid)


def transcript_tool_uses(transcript_dir: Path | None):
    """Yield (agent, tool_name, input) from IDE-format transcripts, incl. subagents."""
    if not transcript_dir or not transcript_dir.exists():
        return
    files = [transcript_dir] if transcript_dir.is_file() else sorted(transcript_dir.rglob("*.jsonl"))
    for f in files:
        agent = "subagent" if "subagents" in f.parts else "main"
        for ev in parse_events(f):
            for block in (ev.get("message") or {}).get("content") or []:
                if isinstance(block, dict) and block.get("type") == "tool_use":
                    yield agent, block.get("name", ""), block.get("input") or {}


def render(traj_path: Path, ws: Path, out_md: Path, out_stats: Path, cfg: dict,
           transcripts: Path | None = None, title: str = "") -> dict:
    rc = cfg.get("render", {})
    think_n = rc.get("thinking_chars", 600)
    prev_n = rc.get("result_preview_chars", 240)
    say_n = rc.get("assistant_chars", 4000)
    hmos_dir = cfg["hmos_dir"]

    events = list(parse_events(traj_path))
    types = Counter((e.get("type"), e.get("subtype")) for e in events)
    known = {"system", "user", "thinking", "assistant", "tool_call", "result"}
    unknown = sorted({str(e.get("type")) for e in events if e.get("type") not in known})

    init, result = bookends(events)

    lines: list[str] = []
    step = 0
    think_buf: list[str] = []
    thinking_chars = 0
    assistant_chars = 0
    kinds = Counter()
    failures = 0
    files_read: set[str] = set()
    files_written: set[str] = set()
    validate_runs = validate_fail = 0
    subagents = 0
    web_calls = 0

    def flush_think():
        nonlocal step, think_buf
        if think_buf:
            text = "".join(think_buf)
            step += 1
            lines.append(f"**[{step:04d}] THINK** ({len(text)} chars): {_one_line(text, think_n)}")
            lines.append("")
            think_buf = []

    pending: dict[str, tuple[str, dict]] = {}
    users_seen = 0
    for ev in events:
        t = ev.get("type")
        if t == "user":
            users_seen += 1
            if users_seen > 1:
                flush_think()
                text = content_text(ev)
                step += 1
                lines.append(f"**[{step:04d}] USER (resumed session)**: {_one_line(text, prev_n)}")
                lines.append("")
            continue
        if t == "thinking":
            if ev.get("subtype") == "delta":
                think_buf.append(ev.get("text", ""))
                thinking_chars += len(ev.get("text", ""))
            continue
        if t == "assistant":
            flush_think()
            text = content_text(ev, "text")
            if text.strip():
                assistant_chars += len(text)
                step += 1
                lines.append(f"**[{step:04d}] SAY**: {_clip(text.strip(), say_n)}")
                lines.append("")
            continue
        if t == "tool_call":
            flush_think()
            parsed = tool_call_key(ev)
            if parsed is None:
                continue
            kind, body = parsed
            cid = ev.get("call_id") or ""
            if ev.get("subtype") == "started":
                pending[cid] = (kind, body.get("args") or {})
                continue
            kind, args = pending.pop(cid, (kind, body.get("args") or {}))
            res = body.get("result")
            desc, res_desc, failed, facts = _summarize_call(kind, args, res, ws, prev_n)
            kinds[kind] += 1
            failures += int(failed)
            if "read" in facts:
                files_read.add(facts["read"])
            files_read.update(facts.get("shell_reads", []))
            if "written" in facts:
                files_written.add(facts["written"])
            if facts.get("subagent"):
                subagents += 1
            if facts.get("web"):
                web_calls += 1
            if "openspec validate" in facts.get("command", ""):
                validate_runs += 1
                validate_fail += int(facts.get("exit_code") not in (0, None))
            step += 1
            mark = " **FAILED**" if failed else ""
            lines.append(f"[{step:04d}] {desc} -> {res_desc}{mark}")
            continue
        if t not in known:
            flush_think()
            step += 1
            lines.append(f"[{step:04d}] EVENT {t}/{ev.get('subtype')}: "
                         f"{_one_line(json.dumps(ev, ensure_ascii=False), prev_n)}")
    flush_think()
    for cid, (kind, args) in pending.items():
        desc, _, _, _ = _summarize_call(kind, args, None, ws, prev_n)
        kinds[kind] += 1
        lines.append(f"[----] {desc} -> (never completed)")

    sub_reads: set[str] = set()
    sub_tool_uses = 0
    for agent, name, inp in transcript_tool_uses(transcripts):
        if agent != "subagent":
            continue
        sub_tool_uses += 1
        if name.lower() in ("read", "readfile", "read_file"):
            for k in PATH_KEYS:
                if inp.get(k):
                    sub_reads.add(_rel(inp[k], ws))
        elif name.lower() == "shell" and SHELL_READ_RE.search(inp.get("command", "")):
            sub_reads.update(_rel(p, ws) for p in SHELL_PATH_RE.findall(inp["command"]))

    hmos_prefix = hmos_dir.rstrip("/") + "/"
    hmos_root = ws / hmos_dir
    hmos_total = sum(1 for p in hmos_root.rglob("*") if p.suffix in (".cpp", ".h")) \
        if hmos_root.exists() else 0
    main_hmos = {p for p in files_read if p.startswith(hmos_prefix) and p.endswith((".cpp", ".h"))}
    all_hmos = main_hmos | {p for p in sub_reads if p.startswith(hmos_prefix)
                            and p.endswith((".cpp", ".h"))}

    usage = result.get("usage", {})
    stats = {
        "model_reported": init.get("model"),
        "session_id": init.get("session_id"),
        "has_result": bool(result),
        "duration_ms": result.get("duration_ms"),
        "usage": usage,
        "events": len(events),
        "event_types": {f"{a}/{b}": n for (a, b), n in sorted(types.items(), key=str)},
        "unknown_event_types": unknown,
        "tool_calls_total": sum(kinds.values()),
        "tool_calls": dict(kinds.most_common()),
        "tool_failures": failures,
        "files_read": len(files_read),
        "files_written": sorted(files_written),
        "hmos_files_total": hmos_total,
        "hmos_files_read_main": len(main_hmos),
        "hmos_files_read_incl_subagents": len(all_hmos),
        "hmos_coverage": round(len(all_hmos) / hmos_total, 3) if hmos_total else 0.0,
        "outside_workspace_reads": sorted(p for p in files_read if p.startswith("/")),
        "openspec_validate_runs": validate_runs,
        "openspec_validate_failures": validate_fail,
        "subagents": subagents,
        "subagent_tool_uses": sub_tool_uses,
        "web_calls": web_calls,
        "thinking_chars": thinking_chars,
        "assistant_chars": assistant_chars,
    }

    header = [
        f"# Trajectory{': ' + title if title else ''}",
        "",
        f"- model: {stats['model_reported']}  session: {stats['session_id']}",
        f"- finished: {stats['has_result']}  duration: "
        f"{(stats['duration_ms'] or 0) / 60000:.1f} min",
        f"- tokens: input {usage.get('inputTokens', '?')}, output {usage.get('outputTokens', '?')}, "
        f"cache read {usage.get('cacheReadTokens', '?')}",
        f"- tool calls: {stats['tool_calls_total']} ({', '.join(f'{k} {v}' for k, v in kinds.most_common())}), "
        f"failures {failures}",
        f"- HMOS .cpp/.h files read: {stats['hmos_files_read_incl_subagents']} / {hmos_total} "
        f"(main agent {stats['hmos_files_read_main']})",
        f"- subagents: {subagents}  openspec validate runs: {validate_runs} (failed {validate_fail})",
        f"- thinking: {thinking_chars} chars  assistant text: {assistant_chars} chars",
        "",
        "## Steps",
        "",
    ]
    out_md.write_text("\n".join(header + lines) + "\n", encoding="utf-8")
    write_json(out_stats, stats)
    return stats
