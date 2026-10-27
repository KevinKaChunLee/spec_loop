"""Decision tables: parse and validate them, compare reference against student, aggregate the score.

A decision table maps fixed keys (decision_vocab.json) to values. Four kinds come from the
extractor model (features, macros, dependencies, architecture); the fifth, modules, is parsed
here from the proposal's 裁剪范围 table and the HMOS directories each baseline `## Purpose` names.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

from .common import ROOT
from .spec_metrics import (BACKTICK_RE, DELTA_RE, PATH_EXT, REQ_RE, TASK_RE, _classify, _expand_braces,
                           _path_resolves)

VOCAB_PATH = ROOT / "decision_vocab.json"
KINDS = ("features", "macros", "dependencies", "architecture")
ALL_KINDS = ("modules", *KINDS)
KIND_ID = {"modules": "module", "features": "feature", "macros": "macro",
           "dependencies": "dependency", "architecture": "architecture"}
# "settled" decisions only test whether a spec follows AGENTS.md (the reference takes AGENTS.md's
# value, the module trims follow its feature list, unreferenced macros have nothing to decide);
# "open" decisions are the ones AGENTS.md leaves open or the reference decides differently.
GROUPS = ("open", "settled")
GROUP_PART = {"open": "open_decisions", "settled": "agents_compliance"}
RULINGS = ("student_wrong", "student_defensible", "reference_questionable")
COUNTS_AS_AGREEMENT = {"student_defensible", "reference_questionable"}
SEVERITIES = ("high", "medium", "low")
TRIM_WORDS = {"移除": "remove", "保留": "keep", "修改": "modify", "新增": "add"}
MODULE_VALUES = {"remove": "移除", "keep": "保留", "modify": "修改"}
ROOT_BUILD_FILES = {"callmanager.gni", "BUILD.gn", "bundle.json"}
MIN_QUOTE_CHARS = 4
MAX_QUOTE_CHARS = 400

HEADING_RE = re.compile(r"^(#{1,6})[ \t]+(.+?)[ \t]*$", re.M)
FENCE_RE = re.compile(r"^```.*?^```[ \t]*$", re.M | re.S)
ASCII_RUN_RE = re.compile(r"[A-Za-z0-9_.{}*,/:\-~]+")
CAMEL_RE = re.compile(r"^[A-Z][a-z0-9]+(?:[A-Z]+[a-z0-9]*)+$|^[A-Z]{2,}[a-z]+[A-Za-z0-9]*$")
IDENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
FILE_RE = re.compile(r"[A-Za-z0-9_.\-]+\.(?:cpp|h|c|gn|gni|json|idl|ts|js|cfg|xml)\b")
CJK_RE = re.compile(r"[\u4e00-\u9fff]")


# ---------------------------------------------------------------- vocabulary

def load_vocab(path: Path = VOCAB_PATH) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def vocab_items(vocab: dict):
    """Yield (kind, key, item, allowed values) for every decision key."""
    for kind in KINDS:
        spec = vocab["kinds"][kind]
        for key, item in spec["items"].items():
            yield kind, key, item, item.get("values") or list(spec["values"])


def value_meaning(vocab: dict, kind: str, value: str | None) -> str:
    if kind == "modules":
        return MODULE_VALUES.get(value or "", "")
    return vocab["kinds"][kind]["values"].get(value or "", "")


def agents_settled(vocab: dict, kind: str, key: str, value: str | None) -> bool:
    """True when AGENTS.md itself settles `key` to `value` (a playbook may repeat it)."""
    if kind not in vocab["kinds"]:
        return False
    item = vocab["kinds"][kind]["items"].get(key, {})
    return item.get("agents_value") is not None and item.get("agents_value") == value


# ---------------------------------------------------------------- markdown helpers

def md_section(text: str, pattern: str) -> str:
    """Body of the first heading whose title matches `pattern`, up to the next heading of the
    same or a higher level."""
    for m in HEADING_RE.finditer(text):
        if re.search(pattern, m.group(2), re.I):
            level = len(m.group(1))
            for n in HEADING_RE.finditer(text, m.end()):
                if len(n.group(1)) <= level:
                    return text[m.end():n.start()]
            return text[m.end():]
    return ""


def md_tables(text: str) -> list[list[list[str]]]:
    tables, cur = [], []
    for line in text.splitlines() + [""]:
        s = line.strip()
        if s.startswith("|") and s.count("|") >= 2:
            cells = [c.strip() for c in s.strip("|").split("|")]
            if not all(re.fullmatch(r":?-{2,}:?", c) for c in cells if c):
                cur.append(cells)
        elif cur:
            tables.append(cur)
            cur = []
    return tables


def _strip_md(cell: str) -> str:
    return re.sub(r"[`*]", "", cell).strip()


# ---------------------------------------------------------------- 裁剪范围 table

def parse_trim_table(proposal: str) -> dict:
    """{capability id: {"value": remove|keep|modify|add, "raw", "reason"}} from the 裁剪范围 table."""
    body = md_section(proposal, r"裁剪范围")
    for table in md_tables(body):
        if len(table) < 2:
            continue
        header = [_strip_md(c) for c in table[0]]
        rows = table[1:]

        def has_word(cell: str) -> bool:
            return any(w in cell for w in TRIM_WORDS)

        val_col = next((i for i, h in enumerate(header) if "处置" in h), None)
        if val_col is None:
            scores = [sum(has_word(r[i]) for r in rows if i < len(r)) for i in range(len(header))]
            val_col = max(range(len(header)), key=lambda i: scores[i]) if scores and max(scores) else None
        if val_col is None:
            continue
        cap_col = next((i for i, h in enumerate(header) if "能力" in h and i != val_col),
                       0 if val_col != 0 else 1)
        reason_col = next((i for i, h in enumerate(header) if "理由" in h), len(header) - 1)
        out = {}
        for r in rows:
            if max(cap_col, val_col) >= len(r):
                continue
            m = re.search(r"[a-z0-9][a-z0-9-]*[a-z0-9]", _strip_md(r[cap_col]))
            word = next((w for w in TRIM_WORDS if w in r[val_col]), None)
            if m and word:
                out[m.group(0)] = {"value": TRIM_WORDS[word], "raw": _strip_md(r[val_col]),
                                   "reason": _strip_md(r[reason_col]) if reason_col < len(r) else ""}
        if out:
            return out
    return {}


# ---------------------------------------------------------------- modules from ## Purpose

def module_key(rel: str) -> str | None:
    """Module group of a path relative to the HMOS module root."""
    parts = [p for p in rel.split("/") if p]
    if not parts:
        return None
    if rel in ROOT_BUILD_FILES or parts[0] == "sa_profile":
        return "build"
    if parts[0] == "services" and len(parts) >= 2:
        if parts[1] == "call" and len(parts) >= 3 and parts[2] == "call_state_observer":
            return "services/call/call_state_observer"
        return f"services/{parts[1]}"
    if parts[0] in ("frameworks", "interfaces"):
        return "frameworks"
    if parts[0] == "utils":
        return "utils"
    return None


def all_modules(index: dict) -> list[str]:
    keys = {module_key(d) for d in index["dirs"]} | {module_key(p) for p in index["paths"]}
    keys.add("build")
    return sorted(k for k in keys if k)


def _stem_key(name: str) -> str:
    return name.rsplit(".", 1)[0].replace("_", "").lower()


def _lookup(index: dict) -> dict:
    """Lookup tables over the HMOS index (cached on the index dict)."""
    if "_lookup" not in index:
        by_base: dict[str, set[str]] = {}
        by_stem: dict[str, set[str]] = {}
        for p in index["paths"]:
            base = p.rsplit("/", 1)[-1]
            by_base.setdefault(base, set()).add(p)
            if base.endswith((".cpp", ".h", ".c")):
                by_stem.setdefault(_stem_key(base), set()).add(p)
        index["_lookup"] = {"by_base": by_base, "by_stem": by_stem, "basenames": set(by_base),
                            "dir_names": {d.rsplit("/", 1)[-1] for d in index["dirs"]}}
    return index["_lookup"]


def _path_id(rel: str, is_dir: bool) -> tuple[str, str] | None:
    mod = module_key(rel)
    if mod is None:
        return None
    return mod, ("d:" if is_dir else "p:") + rel.rstrip("/")


def _resolve_token(tok: str, index: dict, hmos_dir: str) -> set[tuple[str, str]]:
    """Path ids (module, item) that one Purpose token refers to."""
    lk = _lookup(index)
    tok = tok.strip().strip(".,;:()（）、")
    if not tok or len(tok) < 3:
        return set()
    if "::" in tok:
        tok = tok.split("::", 1)[0]
    m = re.fullmatch(r"(.+)\.(\w+)/\.(\w+)", tok)
    cands = [f"{m.group(1)}.{m.group(2)}", f"{m.group(1)}.{m.group(3)}"] if m else _expand_braces(tok)
    out: set[tuple[str, str]] = set()
    for c in cands:
        c = c.strip()
        for prefix in ("./", "//base/telephony/call_manager/", f"{hmos_dir}/", "/"):
            if c.startswith(prefix):
                c = c[len(prefix):]
        if "*" in c:
            c = c.split("*", 1)[0].rsplit("/", 1)[0] if "/" in c.split("*", 1)[0] else ""
        c = c.rstrip("/")
        if not c:
            continue
        if c in index["paths"]:
            pid = _path_id(c, False)
        elif c in index["dirs"]:
            pid = _path_id(c, True) if "/" in c or tok.endswith("/") else None
        elif c in ROOT_BUILD_FILES:
            pid = ("build", "p:" + c)
        elif "/" in c:
            hits = [(p, False) for p in index["paths"] if p.endswith("/" + c)] + \
                   [(d, True) for d in index["dirs"] if d.endswith("/" + c)]
            ids = {_path_id(p, d) for p, d in hits} - {None}
            pid = sorted(ids)[0] if len({i[0] for i in ids}) == 1 else None
        elif c.endswith(PATH_EXT):
            paths = lk["by_base"].get(c, set())
            ids = {_path_id(p, False) for p in paths} - {None}
            pid = sorted(ids)[0] if ids and len({i[0] for i in ids}) == 1 else None
        elif CAMEL_RE.match(c):
            mods = {module_key(p) for p in lk["by_stem"].get(c.lower(), set())} - {None}
            pid = (mods.pop(), "s:" + c.lower()) if len(mods) == 1 else None
        else:
            pid = None
        if pid:
            out.add(pid)
    return out


def purpose_modules(purpose: str, index: dict, hmos_dir: str) -> Counter:
    """Weighted mentions of each module group in a Purpose: 2 per distinct path or directory,
    1 per class (a class whose file is also named is not counted again)."""
    purpose = re.sub(r"\{[^{}\n]*\}", lambda m: re.sub(r"\s+", "", m.group(0)), purpose)
    ids: set[tuple[str, str]] = set()
    tokens = set(re.findall(r"`([^`\n]+)`", purpose))
    tokens |= set(ASCII_RUN_RE.findall(purpose))
    for t in tokens:
        for part in t.split():
            ids |= _resolve_token(part, index, hmos_dir)
    named = {(mod, _stem_key(i.rsplit("/", 1)[-1])) for mod, i in ids if i.startswith("p:")}
    ids = {(mod, i) for mod, i in ids if not (i.startswith("s:") and (mod, i[2:]) in named)}
    out: Counter = Counter()
    for mod, i in ids:
        out[mod] += 1 if i.startswith("s:") else 2
    return out


def baseline_caps(spec_root: Path, cfg: dict) -> dict[str, str]:
    pre = set(cfg.get("preexisting_specs", []))
    return {p.parent.name: p.read_text(encoding="utf-8", errors="replace")
            for p in sorted((spec_root / "openspec" / "specs").glob("*/spec.md"))
            if p.parent.name not in pre}


def delta_ops(spec_root: Path, cfg: dict) -> dict[str, dict]:
    ch = spec_root / "openspec" / "changes" / cfg["change_name"] / "specs"
    out = {}
    for spec in sorted(ch.glob("*/spec.md")):
        text = spec.read_text(encoding="utf-8", errors="replace")
        counts = {"ADDED": 0, "MODIFIED": 0, "REMOVED": 0, "RENAMED": 0}
        marks = [(m.start(), m.group(1)) for m in DELTA_RE.finditer(text)] + [(len(text), None)]
        for (start, op), (end, _) in zip(marks, marks[1:]):
            counts[op] += len(REQ_RE.findall(text[start:end]))
        out[spec.parent.name] = counts
    return out


OWNER_SHARE = 0.25


def _claims(counts: Counter) -> list[str]:
    """Module groups holding at least OWNER_SHARE of a Purpose's mentions. Root build files are
    named in passing by most Purposes, so they do not dilute claims on other groups."""
    total = sum(counts.values())
    rest = total - counts.get("build", 0)
    return sorted(m for m, c in counts.items()
                  if c / (total if m == "build" else rest or 1) >= OWNER_SHARE)


def module_table(spec_root: Path, index: dict, cfg: dict) -> dict:
    """Module decisions of one spec.

    A capability claims a module group when at least a quarter of the weighted mentions in its
    `## Purpose` lie in that group (Purposes also name the hook points they share with other
    groups). The owners of a group are its claimants with at least half the top count;
    a group nobody claims falls back to every capability naming it. A group takes its owners'
    trim value; owners that disagree make it `modify` (partly removed, partly kept). A group is
    covered when some capability claims it.
    """
    hmos_dir = cfg["hmos_dir"]
    caps = baseline_caps(spec_root, cfg)
    change = spec_root / "openspec" / "changes" / cfg["change_name"]
    proposal = (change / "proposal.md").read_text(encoding="utf-8", errors="replace") \
        if (change / "proposal.md").exists() else ""
    trim = parse_trim_table(proposal)
    deltas = delta_ops(spec_root, cfg)
    pre = set(cfg.get("preexisting_specs", []))

    cap_info = {}
    for cap, text in caps.items():
        counts = purpose_modules(md_section(text, r"^Purpose$"), index, hmos_dir)
        row = trim.get(cap)
        if row and row["value"] in MODULE_VALUES:
            value, source = row["value"], "table"
        else:
            ops = deltas.get(cap)
            if not ops:
                value = "keep"
            elif ops["REMOVED"] and not (ops["MODIFIED"] or ops["ADDED"] or ops["RENAMED"]):
                value = "remove"
            else:
                value = "modify"
            source = "inferred"
        cap_info[cap] = {"value": value, "source": source, "modules": dict(counts),
                         "claims": _claims(counts)}

    modules = {}
    for mod in sorted({m for c in cap_info.values() for m in c["modules"]}):
        counts = {cap: c["modules"][mod] for cap, c in cap_info.items() if mod in c["modules"]}
        strong = {cap: n for cap, n in counts.items() if mod in cap_info[cap]["claims"]} or counts
        top = max(strong.values())
        owners = sorted(cap for cap, n in strong.items() if n >= top / 2)
        values = {cap_info[cap]["value"] for cap in owners}
        modules[mod] = {"value": values.pop() if len(values) == 1 else "modify",
                        "owners": owners, "counts": counts}
    problems = []
    if not trim:
        problems.append("proposal.md has no parsable 裁剪范围 table")
    problems += [f"capability `{c}` has no 裁剪范围 row; value inferred from its delta"
                 for c, i in cap_info.items() if i["source"] == "inferred"]
    problems += [f"capability `{c}` names no HMOS path in its Purpose"
                 for c, i in cap_info.items() if not i["modules"]]
    return {"modules": modules, "capabilities": cap_info,
            "covered": sorted({m for c in cap_info.values() for m in c["claims"]}),
            "trim_rows": trim, "unknown_rows": sorted(r for r in trim if r not in caps and r not in pre),
            "deltas": deltas, "problems": problems}


# ---------------------------------------------------------------- extraction validation

def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[`*]", "", text)).strip()


def spec_corpus(spec_root: Path, cfg: dict) -> dict[str, str]:
    """Markdown files of a spec, keyed by path relative to openspec/."""
    os_root = spec_root / "openspec"
    skip = set(cfg.get("preexisting_specs", [])) | set(cfg.get("preexisting_changes", []))
    return {p.relative_to(os_root).as_posix(): p.read_text(encoding="utf-8", errors="replace")
            for p in sorted(os_root.rglob("*.md")) if not skip & set(p.relative_to(os_root).parts)}


def _find_quote(quote: str, file: str, corpus_norm: dict[str, str]) -> str | None:
    q = _norm(quote)
    if len(q) < MIN_QUOTE_CHARS:
        return None
    if file in corpus_norm and q in corpus_norm[file]:
        return file
    return next((f for f, t in corpus_norm.items() if q in t), None)


def validate_extraction(data, vocab: dict, corpus: dict[str, str], index: dict, base: Path,
                        hmos_dir: str, require_all: bool = True) -> tuple[dict, dict]:
    """Check an extractor output; return (clean table, report).

    The clean table holds every vocabulary key; a key whose entry is invalid or `unstated`
    gets value None. `report["errors"]` lists what the extractor must fix.
    """
    corpus_norm = {f: _norm(t) for f, t in corpus.items()}
    errors, warnings, dropped = [], [], []
    clean: dict = {kind: {} for kind in KINDS}
    if not isinstance(data, dict):
        return clean, {"errors": ["top level must be an object with keys " + ", ".join(KINDS)],
                       "warnings": [], "dropped": []}
    for kind in KINDS:
        if not isinstance(data.get(kind), dict):
            if require_all:
                errors.append(f"missing object '{kind}'")
            data[kind] = {}
        known = vocab["kinds"][kind]["items"]
        for key in data[kind]:
            if key not in known:
                warnings.append(f"{kind}.{key}: not a vocabulary key (ignored)")
    for kind, key, _item, allowed in vocab_items(vocab):
        entry = data.get(kind, {}).get(key)
        where = f"{kind}.{key}"
        if entry is None:
            if require_all:
                errors.append(f"{where}: missing (use \"unstated\" when the spec does not decide it)")
            clean[kind][key] = {"value": None}
            continue
        if not isinstance(entry, dict):
            errors.append(f"{where}: must be an object")
            clean[kind][key] = {"value": None}
            dropped.append(where)
            continue
        value = entry.get("value")
        if value not in allowed:
            errors.append(f"{where}: value {value!r} is not one of {allowed}")
            clean[kind][key] = {"value": None}
            dropped.append(where)
            continue
        if value == "unstated":
            clean[kind][key] = {"value": None}
            continue
        quotes, bad = [], []
        for ev in entry.get("evidence") or []:
            if not isinstance(ev, dict) or not isinstance(ev.get("quote"), str):
                bad.append(str(ev)[:80])
                continue
            if len(ev["quote"]) > MAX_QUOTE_CHARS:
                bad.append(ev["quote"][:80] + f"... (longer than {MAX_QUOTE_CHARS} characters)")
                continue
            found = _find_quote(ev["quote"], str(ev.get("file", "")), corpus_norm)
            if found:
                quotes.append({"file": found, "quote": ev["quote"]})
            else:
                bad.append(ev["quote"][:120])
        if bad:
            warnings.append(f"{where}: quotes not found verbatim: " + " | ".join(bad[:3]))
        if not quotes:
            errors.append(f"{where}: value {value!r} needs at least one evidence quote copied verbatim "
                          f"from the spec" + (f" (not found: {bad[0]})" if bad else ""))
            clean[kind][key] = {"value": None}
            dropped.append(where)
            continue
        files, bad_files = [], []
        for f in entry.get("files") or []:
            if isinstance(f, str) and f.strip():
                (files if _path_resolves(f.strip(), base, hmos_dir, index) else bad_files).append(f.strip())
        if bad_files:
            warnings.append(f"{where}: cited files not in the HMOS tree: {', '.join(bad_files[:5])}")
        clean[kind][key] = {"value": value, "evidence": quotes, "files": files}
        if entry.get("note"):
            clean[kind][key]["note"] = str(entry["note"])[:400]
    if isinstance(data.get("baseline_facts"), list):
        facts = []
        for f in data["baseline_facts"]:
            if isinstance(f, dict) and isinstance(f.get("quote"), str) and \
                    _find_quote(f["quote"], "", corpus_norm):
                facts.append({"quote": f["quote"], "fact": str(f.get("fact", ""))[:200]})
            else:
                warnings.append(f"baseline_facts: quote not found verbatim: {str(f)[:120]}")
        clean["baseline_facts"] = facts
    return clean, {"errors": errors[:60], "warnings": warnings[:80], "dropped": dropped}


def table_value(table: dict, kind: str, key: str):
    return table.get(kind, {}).get(key, {}).get("value")


def stated_count(table: dict) -> int:
    return sum(1 for k in KINDS for e in table[k].values() if e.get("value"))


def extraction_agreement(a: dict, b: dict, vocab: dict) -> dict:
    """How often two extractions of the same document give the same value per key."""
    same = stated = stated_same = 0
    diffs = []
    items = list(vocab_items(vocab))
    for kind, key, _item, _allowed in items:
        va, vb = table_value(a, kind, key), table_value(b, kind, key)
        same += va == vb
        if va is not None or vb is not None:
            stated += 1
            stated_same += va == vb
        if va != vb:
            diffs.append({"id": f"{KIND_ID[kind]}/{key}", "a": va, "b": vb})
    return {"items": len(items), "same": same, "agreement": round(same / len(items), 4),
            "stated_items": stated, "stated_same": stated_same,
            "stated_agreement": round(stated_same / stated, 4) if stated else 1.0, "diffs": diffs}


# ---------------------------------------------------------------- compare

def compare(ref: dict, stu: dict, ref_mod: dict, stu_mod: dict, vocab: dict, index: dict) -> list[dict]:
    """One item per reference decision: agree, differ, or missing in the student table; each item
    is in group "settled" or "open"."""
    items = []
    for mod, r in ref_mod["modules"].items():
        s = stu_mod["modules"].get(mod, {}).get("value")
        items.append({"id": f"module/{mod}", "kind": "modules", "key": mod, "group": "settled",
                      "ref": r["value"], "stu": s,
                      "status": "agree" if s == r["value"] else "missing" if s is None else "differ"})
    for kind, key, item, _allowed in vocab_items(vocab):
        rv = table_value(ref, kind, key)
        if rv is None:
            continue
        sv = table_value(stu, kind, key)
        no_code = kind == "macros" and key not in index["idents"]
        if sv == rv or (no_code and sv is not None):
            status = "agree"
        else:
            status = "missing" if sv is None else "differ"
        settled = no_code or item.get("agents_value") == rv
        items.append({"id": f"{KIND_ID[kind]}/{key}", "kind": kind, "key": key,
                      "group": "settled" if settled else "open", "ref": rv, "stu": sv, "status": status,
                      **({"no_code": True} if no_code else {})})
    return items


def dispute_inputs(items: list[dict], ref: dict, stu: dict, ref_mod: dict, stu_mod: dict,
                   vocab: dict) -> list[dict]:
    """What the dispute judge sees for every item that is not an agreement."""
    out = []
    for it in items:
        if it["status"] == "agree":
            continue
        kind, key = it["kind"], it["key"]
        entry = {"id": it["id"], "kind": KIND_ID[kind], "status": it["status"]}
        if kind == "modules":
            def side(mt):
                m = mt["modules"].get(key)
                if not m:
                    return None
                return {"value": m["value"], "meaning": MODULE_VALUES[m["value"]],
                        "capabilities": [{"id": c, "trim_value": mt["capabilities"][c]["value"],
                                          "reason": mt["trim_rows"].get(c, {}).get("reason", "")}
                                         for c in m["owners"]]}
            entry.update(question=f"HMOS 模块目录 `{key}` 在 liteOS 版本中移除、保留还是修改",
                         reference=side(ref_mod), student=side(stu_mod))
        else:
            item = vocab["kinds"][kind]["items"][key]

            def side(table):
                e = table.get(kind, {}).get(key, {})
                if e.get("value") is None:
                    return None
                return {"value": e["value"], "meaning": value_meaning(vocab, kind, e["value"]),
                        "evidence": e.get("evidence", [])[:4], "files": e.get("files", [])[:8]}
            entry.update(question=f"{item['label']}：{vocab['kinds'][kind]['question']}",
                         agents_value=item.get("agents_value"),
                         reference=side(ref), student=side(stu))
            if it.get("no_code"):
                entry["note"] = "该宏在 HMOS 树中没有任何引用"
        out.append(entry)
    return out


def validate_rulings(data, ids: list[str]) -> tuple[dict, list[str]]:
    errors = []
    rulings = {}
    items = data.get("rulings") if isinstance(data, dict) else None
    if not isinstance(items, list):
        return {}, ["top level must be an object with a list 'rulings'"]
    for i, r in enumerate(items):
        if not isinstance(r, dict) or r.get("id") not in ids:
            errors.append(f"rulings[{i}]: id must be one of the dispute ids (got {r.get('id') if isinstance(r, dict) else r!r})")
            continue
        if r.get("ruling") not in RULINGS:
            errors.append(f"{r['id']}: ruling must be one of {list(RULINGS)}")
            continue
        if r.get("severity") not in SEVERITIES:
            errors.append(f"{r['id']}: severity must be one of {list(SEVERITIES)}")
            continue
        if not str(r.get("evidence", "")).strip() or not str(r.get("reason", "")).strip():
            errors.append(f"{r['id']}: reason and evidence are required")
            continue
        rulings[r["id"]] = {k: r[k] for k in ("ruling", "severity", "reason", "evidence")}
    errors += [f"{i}: no ruling" for i in ids if i not in rulings]
    return rulings, errors[:40]


def majority_rulings(rulings_list: list[dict]) -> dict:
    """One ruling per item from several judge passes: the most common ruling; a tie goes to
    student_wrong when it is among the tied rulings. Records the votes."""
    out = {}
    for i in sorted({i for r in rulings_list for i in r}):
        votes = [r[i] for r in rulings_list if i in r]
        counts = Counter(v["ruling"] for v in votes)
        top = max(counts.values())
        tied = [x for x in RULINGS if counts.get(x) == top]
        pick = "student_wrong" if "student_wrong" in tied else tied[0]
        first = next(v for v in votes if v["ruling"] == pick)
        out[i] = {**first, "votes": [v["ruling"] for v in votes]}
    return out


def agreement(items: list[dict], rulings: dict) -> dict[str, dict]:
    """Agreement per group ("open", "settled") and per kind (for the report)."""
    def summary(sel):
        code = sum(it["status"] == "agree" for it in sel)
        ruled = sum(it["status"] != "agree" and rulings.get(it["id"], {}).get("ruling")
                    in COUNTS_AS_AGREEMENT for it in sel)
        return {"items": len(sel), "agree_code": code, "agree_ruling": ruled,
                "value": round((code + ruled) / len(sel), 4) if sel else 1.0,
                "code_value": round(code / len(sel), 4) if sel else 1.0}
    return {**{g: summary([it for it in items if it["group"] == g]) for g in GROUPS},
            **{k: summary([it for it in items if it["kind"] == k]) for k in ALL_KINDS}}


# ---------------------------------------------------------------- code-only checks

def change_texts(spec_root: Path, cfg: dict) -> dict[str, str]:
    ch = spec_root / "openspec" / "changes" / cfg["change_name"]
    return {p.relative_to(ch).as_posix(): p.read_text(encoding="utf-8", errors="replace")
            for p in sorted(ch.rglob("*.md"))} if ch.exists() else {}


def task_rules(spec_root: Path, cfg: dict) -> dict:
    """config.yaml task rules: gate per group, gni sync with deletions, gtest per group."""
    text = change_texts(spec_root, cfg).get("tasks.md", "")
    heads = [(m.start(), m.group(2)) for m in HEADING_RE.finditer(text) if len(m.group(1)) == 2]
    groups = []
    for (start, title), (end, _) in zip(heads, heads[1:] + [(len(text), "")]):
        body = text[start:end]
        if TASK_RE.search(body):
            groups.append((title, body))
    if not groups:
        return {"value": 0.0, "groups": 0, "detail": "tasks.md has no task groups"}
    gate = [t for t, b in groups if re.search(r"must-pass|门禁", b, re.I)]
    gtest = [t for t, b in groups if re.search(r"gtest|用例|\bTEST\b|\b[A-Z][A-Za-z0-9]+_[A-Z][A-Za-z0-9_]+\b", b)]
    deletions, synced = 0, 0
    for _t, b in groups:
        for line in b.splitlines():
            if TASK_RE.match(line) and re.search(r"删除|删去|移除", line) and \
                    re.search(r"\.(cpp|h)\b|源文件|文件|目录|[\w-]+/`", line):
                deletions += 1
                synced += bool(re.search(r"gni", line) or re.search(r"callmanager\.gni", b))
    parts = {"gate": len(gate) / len(groups), "gtest": len(gtest) / len(groups),
             "gni_sync": synced / deletions if deletions else 1.0}
    return {"value": round(sum(parts.values()) / 3, 4), "groups": len(groups),
            "parts": {k: round(v, 3) for k, v in parts.items()},
            "groups_without_gate": [t for t, _ in groups if t not in gate],
            "groups_without_gtest": [t for t, _ in groups if t not in gtest],
            "deletion_tasks": deletions, "deletion_tasks_with_gni": synced}


def cited_names(spec_root: Path, cfg: dict, index: dict, shared: set[str]) -> set[str]:
    """HMOS identifiers (functions, classes, members, macros) a spec's baseline specs cite in
    backticks, leaving out names the shared documents already give."""
    out = set()
    for text in baseline_caps(spec_root, cfg).values():
        for tok in BACKTICK_RE.findall(text):
            c = _classify(tok)
            if not c or c[0] != "ident":
                continue
            for part in c[1].replace("/", "::").split("::"):
                p = part.lstrip("~")
                if len(p) >= 4 and p in index["idents"] and p not in shared and \
                        p not in STD_IDENTS and not STD_TYPE_RE.match(p):
                    out.add(p)
    return out


def behaviour_coverage(ref_names: set[str], stu_names: set[str], padding_ratio: float) -> dict:
    """Share of the HMOS names the reference's baseline cites that the student's baseline also
    cites. Citing more than `padding_ratio` times as many names as the reference scales the value
    down, so listing names cannot buy coverage."""
    recall = len(ref_names & stu_names) / len(ref_names) if ref_names else 1.0
    factor = min(1.0, padding_ratio * len(ref_names) / len(stu_names)) if stu_names else 1.0
    return {"value": round(recall * factor, 4), "recall": round(recall, 4),
            "padding_factor": round(factor, 4), "reference_names": len(ref_names),
            "student_names": len(stu_names), "missing": sorted(ref_names - stu_names)}


def build_tokens(base: Path, hmos_dir: str) -> set[str]:
    """Build-system vocabulary of the HMOS module: gni variables, feature names, defines,
    dependency labels and bundle.json keys (source paths excluded)."""
    root = base / hmos_dir
    out: set[str] = set()
    for name in ("callmanager.gni", "BUILD.gn", "bundle.json"):
        p = root / name
        if not p.exists():
            continue
        text = p.read_text(encoding="utf-8", errors="replace")
        for s in re.findall(r'"([^"\n]*)"', text):
            if "/" in s or s.endswith(PATH_EXT) or len(s) < 5:
                continue
            if ":" in s or "_" in s:
                out.add(s.split("=", 1)[0].strip())
        bare = re.sub(r'"[^"\n]*"', " ", text)
        out |= {t for t in IDENT_RE.findall(bare) if "_" in t and len(t) >= 6}
    return out


def build_coverage(ref_root: Path, stu_root: Path, base: Path, cfg: dict,
                   tokens: set[str] | None = None) -> dict:
    tokens = tokens if tokens is not None else build_tokens(base, cfg["hmos_dir"])

    def hits(root):
        text = "\n".join(change_texts(root, cfg).values())
        return {t for t in tokens if re.search(rf"(?<![\w:]){re.escape(t)}(?![\w:])", text)}
    ref_hits, stu_hits = hits(ref_root), hits(stu_root)
    design = change_texts(stu_root, cfg).get("design.md", "")
    named = (("callmanager.gni" in design) + ("bundle.json" in design)) / 2
    cov = len(ref_hits & stu_hits) / len(ref_hits) if ref_hits else 1.0
    return {"value": round(0.5 * named + 0.5 * cov, 4), "design_names_gni_and_bundle": named,
            "token_coverage": round(cov, 4), "reference_tokens": len(ref_hits),
            "missing_tokens": sorted(ref_hits - stu_hits)[:60]}


def rule_checklist(spec_root: Path, cfg: dict, validate_ok: bool | None, mod: dict) -> dict:
    """Mechanical config.yaml / task.md readability rules."""
    texts = change_texts(spec_root, cfg)
    proposal, design = texts.get("proposal.md", ""), texts.get("design.md", "")
    caps = list(mod["capabilities"])
    trim, deltas = mod["trim_rows"], mod["deltas"]
    checks = {}
    checks["trim_table"] = (1.0 if trim else 0.0, f"{len(trim)} rows parsed")
    covered = [c for c in caps if c in trim]
    checks["trim_covers_capabilities"] = (len(covered) / len(caps) if caps else 0.0,
                                          "missing: " + ", ".join(c for c in caps if c not in trim))
    consistent = []
    for c in covered:
        v, d = trim[c]["value"], deltas.get(c)
        consistent.append(bool(d) if v in ("remove", "modify") else not d or not (d["REMOVED"] or d["MODIFIED"]))
    bad = [c for c, ok in zip(covered, consistent) if not ok]
    checks["trim_matches_deltas"] = (sum(consistent) / len(consistent) if consistent else 0.0,
                                     "inconsistent: " + ", ".join(bad))
    checks["proposal_non_goals"] = (1.0 if re.search(r"^#{2,4}\s.*(非目标|Non-Goals)", proposal, re.M | re.I)
                                    else 0.0, "")
    checks["proposal_review_markers"] = (1.0 if "需人工复核" in proposal else 0.0, "")
    idx = re.search(r"^#{2,4}\s.*(索引|index)", design, re.M | re.I)
    first_dec = re.search(r"^#{3,4}\s+(D\d+|决策\s*\d+)", design, re.M)
    checks["design_decision_index"] = (1.0 if idx and (not first_dec or idx.start() < first_dec.start())
                                       else 0.0, "")
    heads = list(re.finditer(r"^(#{3,4})\s+(D\d+|决策\s*\d+).*$", design, re.M))
    full = []
    for i, h in enumerate(heads):
        end = heads[i + 1].start() if i + 1 < len(heads) else len(design)
        nxt = re.search(r"^#{1,2}\s", design[h.end():end], re.M)
        body = design[h.end():h.end() + nxt.start()] if nxt else design[h.end():end]
        full.append(all(w in body for w in ("决策", "理由", "落点")))
    checks["design_decision_structure"] = (sum(full) / len(full) if full else 0.0,
                                           f"{sum(full)}/{len(full)} decisions have 决策/理由/落点")
    checks["design_open_questions"] = (1.0 if re.search(r"^#{2,4}\s.*(Open Questions|开放问题|待决问题)",
                                                        design, re.M | re.I) else 0.0, "")
    prose = FENCE_RE.sub(" ", proposal + design)
    prose = re.sub(r"`[^`\n]*`", " ", prose)
    cjk, latin = len(CJK_RE.findall(prose)), len(re.findall(r"[A-Za-z]", prose))
    checks["zh_cn_prose"] = (1.0 if cjk / max(1, cjk + latin) >= 0.35 else 0.0,
                             f"CJK share {cjk / max(1, cjk + latin):.2f}")
    long_blocks = [n for t in texts.values() for b in FENCE_RE.findall(t)
                   if (n := b.count("\n") - 1) > 10]
    checks["no_long_code_blocks"] = (1.0 if not long_blocks else 0.0,
                                     f"{len(long_blocks)} block(s) over 10 lines")
    checks["openspec_validate"] = (1.0 if validate_ok else 0.0, "")
    value = sum(v for v, _ in checks.values()) / len(checks)
    return {"value": round(value, 4),
            "checks": {k: {"value": round(v, 3), "detail": d} for k, (v, d) in checks.items()}}


# ---------------------------------------------------------------- aggregate

def aggregate(scoring: dict, parts: dict[str, float]) -> tuple[dict, float]:
    dims, total = {}, 0.0
    for dim, weight in scoring["weights"].items():
        pw = scoring["parts"][dim]
        value = sum(parts[p] * w for p, w in pw.items()) / sum(pw.values())
        dims[dim] = {"value": round(value, 4), "score": round(value * 5, 2),
                     "parts": {p: round(parts[p], 4) for p in pw}}
        total += weight * value
    return dims, round(total / sum(scoring["weights"].values()) * 100, 1)


def part_points(scoring: dict) -> dict[str, float]:
    """Points of the total each part is worth at value 1."""
    wsum = sum(scoring["weights"].values())
    points = {}
    for dim, weight in scoring["weights"].items():
        pw = scoring["parts"][dim]
        for p, w in pw.items():
            points[p] = weight * w / sum(pw.values()) / wsum * 100
    return points


def code_share(scoring: dict, parts: dict[str, float], agree: dict[str, dict]) -> dict:
    """Split the earned total into points decided by code and points decided by a model.

    Agreement parts are code-decided for items that agree in the tables and model-decided
    for items a dispute ruling counted as agreement."""
    llm = set(scoring["llm_parts"])
    part_kind = {p: g for g, p in GROUP_PART.items()}
    code_pts = llm_pts = code_max = 0.0
    for p, scale in part_points(scoring).items():
        if p in llm:
            llm_pts += scale * parts[p]
        elif p in part_kind:
            a = agree[part_kind[p]]
            if a["items"]:
                code_pts += scale * a["agree_code"] / a["items"]
                llm_pts += scale * a["agree_ruling"] / a["items"]
            else:
                code_pts += scale
            code_max += scale
        else:
            code_pts += scale * parts[p]
            code_max += scale
    total = code_pts + llm_pts
    return {"code_points": round(code_pts, 1), "llm_points": round(llm_pts, 1),
            "code_share_of_total": round(code_pts / total, 3) if total else 0.0,
            "code_share_of_weights": round(code_max / 100, 3)}


def decision_gaps(items: list[dict], rulings: dict, vocab: dict) -> list[dict]:
    gaps = []
    for it in items:
        if it["status"] == "agree":
            continue
        r = rulings.get(it["id"], {})
        kind = it["kind"]
        label = it["key"] if kind == "modules" else vocab["kinds"][kind]["items"][it["key"]]["label"]
        ref_m = value_meaning(vocab, kind, it["ref"])
        stu_m = value_meaning(vocab, kind, it["stu"]) if it["stu"] else "未作决定"
        gaps.append({"id": it["id"], "dimension": GROUP_PART[it["group"]],
                     "severity": r.get("severity", "medium"),
                     "tag": r.get("ruling", "student_wrong"),
                     "summary": f"{label}：参考 {it['ref']}（{ref_m}），学生 {it['stu'] or '-'}（{stu_m}）。"
                                + (r.get("reason") or "（无裁定）"),
                     "evidence": r.get("evidence", ""), "source": "decision"})
    return gaps


def check_gaps(coverage_missing: list[str], behaviour: dict, rules: dict, tasks: dict) -> list[dict]:
    gaps = [{"id": f"coverage/{m}", "dimension": "baseline_coverage", "severity": "medium",
             "tag": "student_wrong", "summary": f"没有以 HMOS 模块目录 `{m}` 为主体的 baseline 能力",
             "evidence": "baseline specs 的 ## Purpose", "source": "code"} for m in coverage_missing]
    if behaviour["recall"] < 1:
        gaps.append({"id": "coverage/behaviour", "dimension": "baseline_coverage",
                     "severity": "high" if behaviour["recall"] < 0.7 else "medium", "tag": "student_wrong",
                     "summary": f"参考 baseline 引用的 {behaviour['reference_names']} 个 HMOS 名称中，学生覆盖 "
                                f"{behaviour['recall']:.0%}；缺失示例："
                                + "、".join(f"`{n}`" for n in behaviour["missing"][:12]),
                     "evidence": "baseline specs 中反引号引用的 HMOS 名称", "source": "code"})
    if behaviour["padding_factor"] < 1:
        gaps.append({"id": "coverage/padding", "dimension": "baseline_coverage", "severity": "medium",
                     "tag": "student_wrong",
                     "summary": f"学生引用 {behaviour['student_names']} 个 HMOS 名称，超过参考的 "
                                f"{behaviour['reference_names']} 个太多，覆盖分按 {behaviour['padding_factor']} 折算",
                     "evidence": "baseline specs", "source": "code"})
    for k, c in rules["checks"].items():
        if c["value"] < 1:
            gaps.append({"id": f"rule/{k}", "dimension": "readability_rules", "severity": "low",
                         "tag": "student_wrong", "summary": f"规则检查 {k} = {c['value']}"
                         + (f"（{c['detail']}）" if c["detail"] else ""),
                         "evidence": "config.yaml / task.md", "source": "code"})
    for k, v in tasks.get("parts", {}).items():
        if v < 1:
            gaps.append({"id": f"rule/tasks-{k}", "dimension": "testability_grounding",
                         "severity": "low", "tag": "student_wrong",
                         "summary": f"tasks.md 规则 {k} 满足率 {v}", "evidence": "config.yaml rules.tasks",
                         "source": "code"})
    return gaps


# ---------------------------------------------------------------- reports

def fmt_value(v) -> str:
    return "-" if v is None else str(v)


def render_report(score: dict, items: list[dict], rulings: dict, mod_cov: dict, behaviour: dict,
                  rules: dict, tasks: dict, build: dict, soft_report: str, vocab: dict) -> str:
    out = ["# 评分报告", "",
           f"总分 **{score['total']}**（满分 100）。其中代码判定 {score['code_share']['code_points']} 分、"
           f"模型判定 {score['code_share']['llm_points']} 分（代码占比 "
           f"{score['code_share']['code_share_of_total']:.0%}）。", "",
           "| 维度 | 权重 | 得分(0-5) | 组成 |", "|---|---|---|---|"]
    for dim, d in score["dimensions"].items():
        parts = "，".join(f"{p} {v:.2f}" for p, v in d["parts"].items())
        out.append(f"| {dim} | {score['weights'][dim]} | {d['score']} | {parts} |")
    out += ["", "## 决策对照", "",
            "settled = AGENTS.md 已定（参考取 AGENTS.md 的值、模块裁剪、无引用的宏），只检验是否遵守 AGENTS.md；"
            "open = AGENTS.md 未定或参考另作决定。", "",
            "| 分组 / 类别 | 条目 | 代码一致 | 裁定计为一致 | 一致率 |", "|---|---|---|---|---|"]
    for name, a in score["agreement"].items():
        out.append(f"| {name} | {a['items']} | {a['agree_code']} | {a['agree_ruling']} | {a['value']:.2f} |")
    diff = [it for it in items if it["status"] != "agree"]
    out += ["", "### 不一致项与裁定", ""]
    if not diff:
        out.append("无。")
    else:
        out += ["| id | 分组 | 参考 | 学生 | 裁定 | 严重度 | 理由 |", "|---|---|---|---|---|---|---|"]
        for it in diff:
            r = rulings.get(it["id"], {})
            reason = str(r.get("reason", "")).replace("|", "\\|").replace("\n", " ")
            out.append(f"| `{it['id']}` | {it['group']} | {fmt_value(it['ref'])} | {fmt_value(it['stu'])} | "
                       f"{r.get('ruling', '-')} | {r.get('severity', '-')} | {reason} |")
    out += ["", "## 代码检查", "",
            f"- 模块目录覆盖：{mod_cov['value']:.2f}；未覆盖：{', '.join(mod_cov['missing']) or '无'}",
            f"- 行为覆盖：{behaviour['value']:.2f}（参考 baseline 引用的 {behaviour['reference_names']} 个 HMOS 名称中"
            f"覆盖 {behaviour['recall']:.0%}；学生共引用 {behaviour['student_names']} 个，折算系数 "
            f"{behaviour['padding_factor']}）",
            f"- 引用接地率：{score['code_checks']['grounding_rate']:.3f}",
            f"- tasks 规则：{tasks['value']:.2f}（{json.dumps(tasks.get('parts', {}), ensure_ascii=False)}）",
            f"- callmanager.gni / bundle.json 覆盖：{build['value']:.2f}（design 点名 "
            f"{build['design_names_gni_and_bundle']:.1f}，构建词覆盖 {build['token_coverage']:.2f}）",
            f"- 规则清单：{rules['value']:.2f}"]
    for k, c in rules["checks"].items():
        if c["value"] < 1:
            out.append(f"  - {k} = {c['value']} {c['detail']}")
    out += ["", "## 软性评审（模型）", "", soft_report.strip() or "（无）"]
    return "\n".join(out) + "\n"


# ---------------------------------------------------------------- playbook leak checks

STD_IDENTS = {"lock_guard", "unique_lock", "shared_lock", "shared_mutex", "recursive_mutex",
              "condition_variable", "make_shared", "make_unique", "unique_ptr", "shared_ptr",
              "weak_ptr", "enable_shared_from_this", "static_cast", "reinterpret_cast",
              "const_cast", "dynamic_cast", "string_view", "nullptr_t"}
STD_TYPE_RE = re.compile(r"^(u?int(8|16|32|64)_t|u?intptr_t|s?size_t|char(16|32)_t|wchar_t)$")
PATHLIKE_RE = re.compile(r"[A-Za-z0-9_.\-{}*~]*(?:/[A-Za-z0-9_.\-{}*~]*)+")


def _code_like(t: str) -> bool:
    return "_" in t or bool(re.search(r"[a-z][A-Z]", t))


def allowed_symbols(texts: list[str]) -> tuple[set[str], set[str]]:
    joined = "\n".join(texts)
    return set(IDENT_RE.findall(joined)), {m.rsplit("/", 1)[-1] for m in FILE_RE.findall(joined)}


def symbol_leaks(text: str, index: dict, allowed_idents: set[str], allowed_files: set[str]) -> list[dict]:
    """Lines naming HMOS identifiers or file names that the shared documents do not name.
    Directory paths and directory names are always allowed."""
    lk = _lookup(index)
    out = []
    for no, line in enumerate(text.splitlines(), 1):
        found = []
        for f in FILE_RE.findall(line):
            base = f.rsplit("/", 1)[-1]
            if base in lk["basenames"] and base not in allowed_files:
                found.append(("file", base))
        masked = PATHLIKE_RE.sub(lambda m: " " if "/" in m.group(0) else m.group(0), line)
        masked = FILE_RE.sub(" ", masked)
        masked = re.sub(r"\bstd::[A-Za-z_][A-Za-z0-9_:]*", " ", masked)
        for tok in IDENT_RE.findall(masked):
            if len(tok) < 4 or not _code_like(tok) or tok in STD_IDENTS or STD_TYPE_RE.match(tok) \
                    or tok in lk["dir_names"]:
                continue
            if tok in index["idents"] and tok not in allowed_idents:
                found.append(("ident", tok))
        if found:
            seen = sorted(set(found))
            out.append({"line": no, "text": line.strip()[:200],
                        "reasons": [f"HMOS {k} `{t}`" for k, t in seen]})
    return out


def quote_lines(quote: str, lines: list[str]) -> list[int]:
    """1-based line numbers a (normalized) quote spans in a document."""
    q = _norm(quote)
    if len(q) < MIN_QUOTE_CHARS:
        return []
    joined, owner = "", []
    for no, line in enumerate(lines, 1):
        n = _norm(line)
        if not n:
            continue
        if joined:
            joined += " "
            owner.append(no)
        joined += n
        owner += [no] * len(n)
    hits, start = set(), joined.find(q)
    while start >= 0:
        hits |= set(owner[start:start + len(q)])
        start = joined.find(q, start + 1)
    return sorted(hits)


def decision_leaks(pb_table: dict, ref_table: dict, vocab: dict, lines: list[str],
                   strict: bool = False) -> list[dict]:
    """Playbook lines stating the reference's value for a key AGENTS.md does not settle, and lines
    stating findings about the HMOS code (baseline facts). `strict` flags every stated decision
    value, settled or not."""
    out: dict[int, list[str]] = {}
    for f in pb_table.get("baseline_facts", []):
        for no in quote_lines(f["quote"], lines):
            out.setdefault(no, []).append(f"baseline fact: {f['fact']}" if f.get("fact") else "baseline fact")
    for kind in KINDS:
        for key, e in pb_table.get(kind, {}).items():
            v = e.get("value")
            if v is None:
                continue
            ref_v = table_value(ref_table, kind, key)
            if not strict and (v != ref_v or agents_settled(vocab, kind, key, v)):
                continue
            for ev in e.get("evidence", []):
                for no in quote_lines(ev["quote"], lines):
                    out.setdefault(no, []).append(f"decision {KIND_ID[kind]}/{key} = {v}"
                                                  + ("" if v == ref_v else " (not the reference value)"))
    return [{"line": no, "text": lines[no - 1].strip()[:200], "reasons": sorted(set(r))}
            for no, r in sorted(out.items())]


def merge_leaks(*groups: list[dict]) -> list[dict]:
    merged: dict[int, dict] = {}
    for g in groups:
        for e in g:
            m = merged.setdefault(e["line"], {"line": e["line"], "text": e["text"], "reasons": []})
            m["reasons"] = sorted(set(m["reasons"]) | set(e["reasons"]))
    return [merged[k] for k in sorted(merged)]


def strip_lines(text: str, line_numbers) -> str:
    drop = set(line_numbers)
    kept = [line for no, line in enumerate(text.splitlines(), 1) if no not in drop]
    return "\n".join(kept) + ("\n" if text.endswith("\n") else "")
