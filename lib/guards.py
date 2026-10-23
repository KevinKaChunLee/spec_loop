"""Checks that make a run valid: no code written, spec validates, no leaks, no copied answers."""

from __future__ import annotations

import functools
import json
import os
import re
import subprocess
from pathlib import Path

from . import decisions
from .render_traj import tool_calls, transcript_tool_uses
from .stream import parse_events
from .workspace import changed_paths

_PATH_CHARS = r"[^\s'\"`<>|;&(){}*?,\u3000-\u303f\u4e00-\u9fff\uff00-\uffef]"
ABS_PATH_RE = re.compile(rf"(?:~|/){_PATH_CHARS}+")
REL_UP_RE = re.compile(rf"(?:^|[\s'\"=:(])(\.\.(?:/{_PATH_CHARS}*)?)(?=$|[\s'\"`;|&)]|[\u3000-\u303f\uff00-\uffef])")


def no_code(ws: Path, allowed_prefixes: tuple[str, ...]) -> dict:
    changed = changed_paths(ws)
    ignored = [p for p in changed if p.startswith(".cursor/")]
    violations = [p for p in changed if p not in ignored and not p.startswith(allowed_prefixes)]
    return {"ok": not violations, "allowed": list(allowed_prefixes),
            "changed": len(changed), "violations": violations, "ignored": ignored}


def validate(spec_root: Path) -> dict:
    """Run `openspec validate --all --strict` in a directory that contains openspec/."""
    proc = subprocess.run(["openspec", "validate", "--all", "--strict", "--json", "--no-interactive"],
                          cwd=spec_root, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {"ok": False, "exit_code": proc.returncode,
                "error": (proc.stdout + proc.stderr)[-2000:]}
    items = data.get("items", [])
    failed = [{"id": i.get("id"), "type": i.get("type"),
               "issues": [f"{x.get('level')} {x.get('path')}: {x.get('message')}"
                          for x in i.get("issues", []) if x.get("level") == "ERROR"][:20]}
              for i in items if not i.get("valid")]
    totals = data.get("summary", {}).get("totals", {})
    return {"ok": proc.returncode == 0 and not failed, "exit_code": proc.returncode,
            "totals": totals, "failed": failed}


CONTENT_KEYS = {"streamContent", "content", "contents", "new_string", "old_string",
                "newString", "oldString", "fileText", "text", "todos", "parsingResult"}


def _strings(obj, skip=CONTENT_KEYS):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for k, v in obj.items():
            if k not in skip:
                yield from _strings(v, skip)
    elif isinstance(obj, list):
        for v in obj:
            yield from _strings(v, skip)


# Parts of a stage workspace that differ between stages: other agents' specs, inputs (the
# reference) and outputs. Everything else is the same base snapshot in every workspace.
PRIVATE_WS_DIRS = {"_inputs", "_outputs", "openspec", ".git", ".cursor"}


def _forbidden_reason(path: str, ws: Path, cfg: dict, own_project: str | None,
                      spec_loop_root: Path) -> tuple[str, str] | None:
    """Return (severity, reason) for a path the agent must not touch, else None. Reading another
    stage's copy of a shared snapshot file (one that also exists in this workspace, outside the
    private directories) is only a warning: its content is the same as this workspace's copy."""
    p = os.path.normpath(os.path.expanduser(path))
    wsr = str(ws)
    if p == wsr or p.startswith(wsr + "/"):
        return None

    def shared(parts: tuple[str, ...]) -> bool:
        return bool(parts) and parts[0] not in PRIVATE_WS_DIRS and (ws / Path(*parts)).exists()

    if p.startswith(str(spec_loop_root)):
        rel = Path(p).relative_to(spec_loop_root).parts
        if len(rel) > 3 and rel[0] == "runs" and rel[2] == "base" and shared(rel[3:]):
            return "warning", f"shared snapshot file in the base copy of run {rel[1]}"
        return "violation", "spec_loop tooling or run outputs"
    if p.startswith(str(Path(cfg["repo"]).parent)):
        repo = Path(cfg["repo"])
        if p.startswith(str(repo) + "/") and shared(Path(p).relative_to(repo).parts):
            return "warning", "shared snapshot file in the original repository's working tree"
        return "violation", "original workspace (repo with history, branches, tooling)"
    if "/.cursor/projects/" in p + "/":
        if own_project and f"/.cursor/projects/{own_project}" in p:
            return None
        return "violation", "another workspace's agent transcripts"
    if "glm-exports" in p or "glm-runs" in p:
        return "violation", "earlier GLM run exports"
    wroot = cfg["workspace_root"].rstrip("/")
    if p.startswith(wroot + "/"):
        rel = Path(p).relative_to(wroot).parts
        if len(rel) >= 2 and (Path(wroot) / rel[0] / rel[1]).is_dir():
            inner = rel[2:]
            if inner and inner[0] not in PRIVATE_WS_DIRS and (ws / Path(*inner)).exists():
                return "warning", f"shared snapshot file in another stage's workspace ({rel[0]}/{rel[1]})"
            return "violation", f"another stage's workspace ({rel[0]}/{rel[1]})"
        return "warning", "parent of the stage workspaces"
    if p == wroot:
        return "warning", "parent of the stage workspaces"
    return None


def leak_check(cfg: dict, ws: Path, traj: Path, transcripts: Path | None,
               own_project: str | None, spec_loop_root: Path) -> dict:
    violations, warnings = [], []
    seen = set()
    markers = (str(spec_loop_root / "runs"), str(Path(cfg["repo"]).parent))

    def scan(where: str, tool: str, args, result=None, cwd: str = ""):
        for text in _strings(args):
            cands = ABS_PATH_RE.findall(text)
            base = Path(cwd) if cwd.startswith("/") else ws
            cands += [str(base / m) for m in REL_UP_RE.findall(text)]
            for c in cands:
                r = _forbidden_reason(c, ws, cfg, own_project, spec_loop_root)
                if r and (r[1], c, tool) not in seen:
                    seen.add((r[1], c, tool))
                    entry = {"where": where, "tool": tool, "path": c[:300], "reason": r[1]}
                    (violations if r[0] == "violation" else warnings).append(entry)
        if result is not None:
            for s in _strings(result, skip=frozenset()):
                if not any(marker in s for marker in markers):
                    continue
                for c in ABS_PATH_RE.findall(s):
                    if not c.startswith(markers):
                        continue
                    r = _forbidden_reason(c, ws, cfg, own_project, spec_loop_root)
                    key = ("tool output exposed a forbidden path", c, tool)
                    if r and r[0] == "violation" and key not in seen:
                        seen.add(key)
                        violations.append({"where": where, "tool": tool, "path": c[:300],
                                           "reason": f"tool output exposed a forbidden path ({r[1]})"})
        if "web" in tool.lower():
            warnings.append({"where": where, "tool": tool, "path": "", "reason": "web tool used"})

    for kind, args, result in tool_calls(parse_events(traj)):
        cwd = args.get("workingDirectory", "") if isinstance(args, dict) else ""
        scan("stream", kind, args, result, cwd)
    for agent, name, inp in transcript_tool_uses(transcripts):
        scan(f"transcript:{agent}", name, inp)
    return {"ok": not violations, "violations": violations[:100], "warnings": warnings[:100]}


_NORM_RE = re.compile(r"[\s`*_#>|\-=~\[\]]+")


def _norm(text: str) -> str:
    return _NORM_RE.sub("", text)


def overlap(playbook: str, reference: str, allowed_norm: str, n: int) -> list[str]:
    """Spans of the playbook (normalized) that also occur in the reference spec and are
    not explained by the shared inputs (`allowed_norm`, already normalized)."""
    pb, ref = _norm(playbook), _norm(reference)
    if len(pb) < n or len(ref) < n:
        return []
    grams = {ref[i:i + n] for i in range(len(ref) - n + 1)}
    covered = [False] * len(pb)
    for i in range(len(pb) - n + 1):
        if pb[i:i + n] in grams:
            for j in range(i, i + n):
                covered[j] = True
    spans, start = [], None
    for i, c in enumerate(covered + [False]):
        if c and start is None:
            start = i
        elif not c and start is not None:
            spans.append(pb[start:i])
            start = None
    return [s for s in spans if s not in allowed_norm]


@functools.lru_cache(maxsize=4)
def _allowed_corpus(base: Path, hmos_dir: str, task_text: str) -> str:
    """Normalized text of the shared inputs; a playbook may repeat anything found here."""
    parts = [(base / rel).read_text(encoding="utf-8", errors="replace")
             for rel in ("AGENTS.md", "openspec/config.yaml") if (base / rel).exists()]
    entries = list((base / hmos_dir).rglob("*"))
    parts.append("\n".join(p.relative_to(base).as_posix() for p in entries))
    parts += [p.read_text(encoding="utf-8", errors="replace") for p in entries
              if p.is_file() and p.suffix in (".cpp", ".h", ".gn", ".gni", ".json")]
    parts.append(task_text)
    return _norm("\n".join(parts))


def check_playbook(cfg: dict, playbook_path: Path, reference_root: Path, base: Path,
                   reference_caps: list[str], task_text: str, index: dict) -> dict:
    """Code-only playbook checks. `problems` reject the playbook; `symbol_leaks` are lines that
    name HMOS identifiers or file names the shared documents do not name (strippable)."""
    lim = cfg["playbook_limits"]
    problems = []
    if not playbook_path.exists():
        return {"ok": False, "problems": ["playbook.md was not written"], "symbol_leaks": []}
    text = playbook_path.read_text(encoding="utf-8", errors="replace")
    shared = [(base / rel).read_text(encoding="utf-8", errors="replace")
              for rel in ("AGENTS.md", "openspec/config.yaml") if (base / rel).exists()]
    idents, files = decisions.allowed_symbols([*shared, task_text])
    symbol_leaks = decisions.symbol_leaks(text, index, idents, files)
    n_lines = text.count("\n") + 1
    if n_lines > lim["max_lines"]:
        problems.append(f"playbook has {n_lines} lines; the limit is {lim['max_lines']}")

    ref_text = "\n".join(p.read_text(encoding="utf-8", errors="replace")
                         for p in sorted((reference_root / "openspec").rglob("*.md"))
                         if "pc-test-harness" not in p.parts and "setup-pc-test-env" not in p.parts)
    allowed = _allowed_corpus(base.resolve(), cfg["hmos_dir"], task_text)
    spans = overlap(text, ref_text, allowed, lim["ngram_chars"])
    total = sum(len(s) for s in spans)
    long_spans = [s for s in spans if len(s) >= lim["max_span_chars"]]
    if long_spans:
        problems.append(f"{len(long_spans)} passage(s) of >= {lim['max_span_chars']} characters "
                        f"are copied from the reference spec")
    if total > lim["max_total_copied_chars"]:
        problems.append(f"{total} characters in total overlap with the reference spec; "
                        f"the limit is {lim['max_total_copied_chars']}")

    caps = [c for c in reference_caps if c not in cfg.get("preexisting_specs", [])]
    named = [c for c in caps if re.search(rf"(?<![\w-]){re.escape(c)}(?![\w-])", text)]
    share = round(len(named) / len(caps), 3) if caps else 0.0
    if caps and share > lim["max_capability_id_share"]:
        problems.append(f"playbook names {len(named)} of the reference's {len(caps)} capability ids "
                        f"(share {share} > {lim['max_capability_id_share']}); describe how to derive "
                        f"capabilities instead of listing them")
    return {"ok": not problems and not symbol_leaks, "problems": problems, "lines": n_lines,
            "copied_chars": total, "spans": [s[:200] for s in sorted(spans, key=len, reverse=True)[:15]],
            "capability_ids_named": named, "capability_id_share": share,
            "symbol_leaks": symbol_leaks}
