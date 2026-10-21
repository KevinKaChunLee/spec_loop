"""Readers for Cursor CLI stream-json trajectories and IDE-format transcript JSONL."""

from __future__ import annotations

import json
from pathlib import Path


def parse_events(path: Path, offset: int = 0):
    """Yield the JSON objects of a JSONL file from byte `offset`, skipping blank or malformed lines."""
    with open(path, encoding="utf-8", errors="replace") as f:
        f.seek(offset)
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def tool_call_key(ev: dict) -> tuple[str, dict] | None:
    """(kind, body) of a tool_call event, e.g. ("read", {...}) for `readToolCall`."""
    tc = ev.get("tool_call") or {}
    if not tc:
        return None
    key = next(iter(tc))
    kind = key[:-len("ToolCall")] if key.endswith("ToolCall") else key
    return kind, tc[key] or {}


def content_text(ev: dict, block_type: str | None = None) -> str:
    """Concatenated text of a message's content blocks, optionally only blocks of `block_type`."""
    blocks = (ev.get("message") or {}).get("content") or []
    return "".join(b.get("text", "") for b in blocks
                   if isinstance(b, dict) and (block_type is None or b.get("type") == block_type))


def usage_total(events) -> dict:
    """Token usage summed over every `result` event; a resumed run has one result per segment."""
    total: dict = {}
    for e in events:
        if e.get("type") == "result":
            for k, v in (e.get("usage") or {}).items():
                if isinstance(v, (int, float)):
                    total[k] = total.get(k, 0) + v
    return total


def bookends(events: list[dict]) -> tuple[dict, dict]:
    """The first system event and the last result event of a stream."""
    init = next((e for e in events if e.get("type") == "system"), {})
    result = next((e for e in reversed(events) if e.get("type") == "result"), {})
    return init, result
