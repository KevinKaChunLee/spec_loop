"""Deterministic facts about an OpenSpec tree, used by the judge and the score log."""

from __future__ import annotations

import json
import re
from pathlib import Path

from .common import write_text_atomic

SRC_EXT = (".cpp", ".h", ".c", ".gn", ".gni", ".json", ".idl")
PATH_EXT = (".cpp", ".h", ".c", ".gn", ".gni", ".json", ".idl", ".ts", ".js", ".cfg", ".xml")
IDENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]{2,}")
UPPER_RE = re.compile(r"\b[A-Z][A-Z0-9_]{3,}\b")
BACKTICK_RE = re.compile(r"`([^`\n]{2,160})`")
REQ_RE = re.compile(r"^### Requirement:", re.M)
SCEN_RE = re.compile(r"^#### Scenario:", re.M)
DELTA_RE = re.compile(r"^## (ADDED|MODIFIED|REMOVED|RENAMED) Requirements\s*$", re.M)
DECISION_RE = re.compile(r"^#{2,4} .*(Decision|决策)", re.M)
TASK_RE = re.compile(r"^\s*- \[[ xX]\]", re.M)


def build_hmos_index(base: Path, hmos_dir: str, cache: Path | None = None) -> dict:
    """Identifier, macro and path sets for the HMOS tree under base/hmos_dir."""
    if cache and cache.exists():
        data = json.loads(cache.read_text(encoding="utf-8"))
        return {k: set(v) if isinstance(v, list) else v for k, v in data.items()}
    root = base / hmos_dir
    idents: set[str] = set()
    macros: set[str] = set()
    paths: set[str] = set()
    dirs: set[str] = set()
    for p in root.rglob("*"):
        rel = p.relative_to(root).as_posix()
        if p.is_dir():
            dirs.add(rel)
            continue
        paths.add(rel)
        if p.suffix not in SRC_EXT:
            continue
        text = p.read_text(encoding="utf-8", errors="replace")
        idents.update(IDENT_RE.findall(text))
        if p.suffix in (".cpp", ".h", ".c"):
            for line in text.splitlines():
                s = line.lstrip()
                if s.startswith("#") and re.match(r"#\s*(if|ifdef|ifndef|elif)\b", s):
                    macros.update(t for t in UPPER_RE.findall(s)
                                  if t != "DEFINED" and not re.search(r"_H_?$", t))
        else:
            macros.update(re.findall(r'"([A-Z][A-Z0-9_]{3,})(?:=[^"]*)?"', text))
    agents = base / "AGENTS.md"
    agents_idents: set[str] = set()
    if agents.exists():
        agents_text = agents.read_text(encoding="utf-8")
        macros.update(re.findall(r"\b[A-Z][A-Z0-9]*_[A-Z0-9_]+\b", agents_text))
        agents_idents = set(IDENT_RE.findall(agents_text))
    index = {"idents": idents, "agents_idents": agents_idents, "macros": macros,
             "paths": paths, "dirs": dirs}
    if cache:
        write_text_atomic(cache, json.dumps({k: sorted(v) for k, v in index.items()}))
    return index


IDENT_FULL = re.compile(r"~?[A-Za-z_][A-Za-z0-9_]*(::~?[A-Za-z_][A-Za-z0-9_]*)*")


def _code_like(t: str) -> bool:
    return "::" in t or "_" in t or bool(re.search(r"[a-z][A-Z]", t))


def _classify(token: str):
    t = token.strip()
    t = re.sub(r"\(.*\)$", "", t).strip()
    if not t or " " in t or len(t) < 4 or t.startswith("."):
        return None
    parts = t.split("/")
    if len(parts) > 1 and all(IDENT_FULL.fullmatch(p) for p in parts) and "." not in t:
        if any(_code_like(p) for p in parts):
            return "ident", t
        if not t.startswith("//") and not any(p[:1].islower() for p in parts if p):
            return None
    if "/" in t or t.endswith(PATH_EXT):
        return "path", t
    if IDENT_FULL.fullmatch(t) and _code_like(t):
        return "ident", t
    return None


def _expand_braces(t: str) -> list[str]:
    m = re.search(r"\{([^{}]*)\}", t)
    if not m:
        return [t]
    return [x for alt in m.group(1).split(",")
            for x in _expand_braces(t[:m.start()] + alt.strip() + t[m.end():])]


def _path_resolves(t: str, base: Path, hmos_dir: str, index: dict) -> bool:
    if "{" in t:
        return all(_path_resolves(x, base, hmos_dir, index) for x in _expand_braces(t))
    if "*" in t:
        head = t.split("*", 1)[0]
        t = head.rsplit("/", 1)[0] if "/" in head else ""
        if not t:
            return False
    t = re.sub(r"(/\*\*?|/)$", "", t.lstrip("./")) if not t.startswith("//") else t
    if t.startswith("//base/telephony/call_manager"):
        t = t[len("//base/telephony/call_manager"):].lstrip("/").split(":")[0]
    if t.startswith(hmos_dir + "/"):
        t = t[len(hmos_dir) + 1:]
    if not t:
        return True
    if t in index["paths"] or t in index["dirs"]:
        return True
    if (base / t).exists():
        return True
    suffix = "/" + t
    return any(p.endswith(suffix) for p in index["paths"]) or \
        any(d.endswith(suffix) for d in index["dirs"])


def _ident_resolves(t: str, index: dict) -> bool:
    agents = index.get("agents_idents", set())
    return all(part.lstrip("~") in index["idents"] or part.lstrip("~") in agents
               for part in t.replace("/", "::").split("::") if part)


def _md_files(root: Path):
    return sorted(root.rglob("*.md")) if root.exists() else []


def collect(spec_root: Path, base: Path, cfg: dict, index: dict) -> dict:
    """spec_root is a directory that contains openspec/."""
    hmos_dir = cfg["hmos_dir"]
    change = cfg["change_name"]
    pre_specs = set(cfg.get("preexisting_specs", []))
    os_root = spec_root / "openspec"

    baseline = {}
    for spec in sorted((os_root / "specs").glob("*/spec.md")):
        cid = spec.parent.name
        if cid in pre_specs:
            continue
        text = spec.read_text(encoding="utf-8", errors="replace")
        baseline[cid] = {"requirements": len(REQ_RE.findall(text)),
                         "scenarios": len(SCEN_RE.findall(text)),
                         "lines": text.count("\n") + 1}

    ch_root = os_root / "changes" / change
    artifacts = {}
    for name in ("proposal.md", "design.md", "tasks.md"):
        p = ch_root / name
        artifacts[name] = (p.read_text(encoding="utf-8", errors="replace").count("\n") + 1) \
            if p.exists() else 0
    design_text = (ch_root / "design.md").read_text(encoding="utf-8", errors="replace") \
        if (ch_root / "design.md").exists() else ""
    tasks_text = (ch_root / "tasks.md").read_text(encoding="utf-8", errors="replace") \
        if (ch_root / "tasks.md").exists() else ""

    deltas = {}
    for spec in sorted((ch_root / "specs").glob("*/spec.md")):
        text = spec.read_text(encoding="utf-8", errors="replace")
        counts = {"ADDED": 0, "MODIFIED": 0, "REMOVED": 0, "RENAMED": 0}
        marks = [(m.start(), m.group(1)) for m in DELTA_RE.finditer(text)] + [(len(text), None)]
        for (start, op), (end, _) in zip(marks, marks[1:]):
            counts[op] += len(REQ_RE.findall(text[start:end]))
        counts["scenarios"] = len(SCEN_RE.findall(text))
        deltas[spec.parent.name] = counts

    change_text = "\n".join(p.read_text(encoding="utf-8", errors="replace")
                            for p in _md_files(ch_root))
    macros_mentioned = sorted(set(UPPER_RE.findall(change_text)) & index["macros"])

    checked = resolved = 0
    unresolved: list[str] = []
    seen: set[str] = set()
    md = [p for p in _md_files(os_root / "specs") if p.parent.name not in pre_specs] + \
        _md_files(ch_root)
    for p in md:
        for tok in BACKTICK_RE.findall(p.read_text(encoding="utf-8", errors="replace")):
            c = _classify(tok)
            if not c or c[1] in seen:
                continue
            seen.add(c[1])
            kind, t = c
            ok = _path_resolves(t, base, hmos_dir, index) if kind == "path" \
                else _ident_resolves(t, index)
            checked += 1
            resolved += int(ok)
            if not ok:
                unresolved.append(t)

    return {
        "baseline_capabilities": baseline,
        "baseline_totals": {
            "capabilities": len(baseline),
            "requirements": sum(v["requirements"] for v in baseline.values()),
            "scenarios": sum(v["scenarios"] for v in baseline.values()),
        },
        "change_exists": ch_root.exists(),
        "change_artifact_lines": artifacts,
        "design_decisions": len(DECISION_RE.findall(design_text)),
        "tasks": len(TASK_RE.findall(tasks_text)),
        "delta_specs": deltas,
        "delta_totals": {op: sum(v[op] for v in deltas.values())
                         for op in ("ADDED", "MODIFIED", "REMOVED", "RENAMED", "scenarios")},
        "macros_mentioned_in_change": macros_mentioned,
        "references_checked": checked,
        "references_resolved": resolved,
        "reference_grounding": round(resolved / checked, 3) if checked else None,
        "unresolved_references": unresolved[:200],
        "other_changes": sorted(p.name for p in (os_root / "changes").iterdir()
                                if p.is_dir() and p.name not in ("archive", change)
                                and p.name not in cfg.get("preexisting_changes", []))
        if (os_root / "changes").exists() else [],
    }


def diff(ref: dict, stu: dict) -> dict:
    rc, sc = set(ref["baseline_capabilities"]), set(stu["baseline_capabilities"])
    rm, sm = set(ref["macros_mentioned_in_change"]), set(stu["macros_mentioned_in_change"])
    rd, sd = set(ref["delta_specs"]), set(stu["delta_specs"])
    jac = lambda a, b: round(len(a & b) / len(a | b), 3) if a | b else 1.0
    return {
        "capabilities_shared": sorted(rc & sc),
        "capabilities_only_reference": sorted(rc - sc),
        "capabilities_only_student": sorted(sc - rc),
        "capability_id_jaccard": jac(rc, sc),
        "delta_capabilities_jaccard": jac(rd, sd),
        "macros_shared": sorted(rm & sm),
        "macros_only_reference": sorted(rm - sm),
        "macros_only_student": sorted(sm - rm),
        "macro_jaccard": jac(rm, sm),
    }


def _row(label, a, b):
    return f"| {label} | {a} | {b} |"


def render_md(ref: dict, stu: dict, d: dict, ref_guards: dict | None = None,
              stu_guards: dict | None = None) -> str:
    out = ["# Deterministic metrics: reference vs student", "",
           "Computed by script, not by a model. Capability ids are compared literally; a",
           "student may use different ids for the same module group, so read them as hints.", "",
           "| metric | reference | student |", "|---|---|---|"]
    for key in ("capabilities", "requirements", "scenarios"):
        out.append(_row(f"baseline {key}", ref["baseline_totals"][key], stu["baseline_totals"][key]))
    out.append(_row("change exists", ref["change_exists"], stu["change_exists"]))
    for name in ("proposal.md", "design.md", "tasks.md"):
        out.append(_row(f"{name} lines", ref["change_artifact_lines"][name],
                        stu["change_artifact_lines"][name]))
    out.append(_row("design decisions (headings)", ref["design_decisions"], stu["design_decisions"]))
    out.append(_row("tasks (checkboxes)", ref["tasks"], stu["tasks"]))
    for op in ("ADDED", "MODIFIED", "REMOVED", "RENAMED"):
        out.append(_row(f"delta {op} requirements", ref["delta_totals"][op], stu["delta_totals"][op]))
    out.append(_row("reference grounding (backticked names found in HMOS)",
                    f"{ref['references_resolved']}/{ref['references_checked']}",
                    f"{stu['references_resolved']}/{stu['references_checked']}"))
    if ref_guards is not None and stu_guards is not None:
        out.append(_row("openspec validate --all --strict",
                        ref_guards.get("validate", {}).get("ok"),
                        stu_guards.get("validate", {}).get("ok")))
        out.append(_row("only openspec/ written", ref_guards.get("no_code", {}).get("ok"),
                        stu_guards.get("no_code", {}).get("ok")))
    out += ["", "## Baseline capability ids", "",
            f"- shared: {', '.join(d['capabilities_shared']) or '-'}",
            f"- only reference: {', '.join(d['capabilities_only_reference']) or '-'}",
            f"- only student: {', '.join(d['capabilities_only_student']) or '-'}",
            "", "## Feature macros mentioned in the change", "",
            f"- shared: {', '.join(d['macros_shared']) or '-'}",
            f"- only reference: {', '.join(d['macros_only_reference']) or '-'}",
            f"- only student: {', '.join(d['macros_only_student']) or '-'}",
            "", "## Student names that were not found in the HMOS tree", "",
            "These are either new code introduced by the student's design (stubs, structs,",
            "todo labels) or hallucinated references. Check before penalizing.", ""]
    out += [f"- `{t}`" for t in stu["unresolved_references"][:80]] or ["- none"]
    if stu_guards and stu_guards.get("no_code", {}).get("violations"):
        out += ["", "## Files the student wrote outside openspec/ (excluded from scoring)", ""]
        out += [f"- {p}" for p in stu_guards["no_code"]["violations"][:50]]
    return "\n".join(out) + "\n"
