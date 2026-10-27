"""The reference decisions and coverage target from several independent oracle runs, in code.

Each oracle's spec is extracted twice; the oracle states a value where both passes agree and
abstains where they differ. The reference value of a key is the value a majority of the oracles
state; a key without a majority is contested and has no reference value (it is not scored). A key
AGENTS.md settles takes AGENTS.md's value whenever a majority of the oracles address it. The
coverage target is the set of HMOS names a majority of the oracle specs cite. The medoid, the
oracle closest to this consensus, provides the reference spec text.
"""

from __future__ import annotations

from collections import Counter

from .decisions import KIND_ID, KINDS, fmt_value, table_value, value_meaning, vocab_items


def majority(n: int) -> int:
    """Votes needed out of n oracles: more than half."""
    return n // 2 + 1


def agreed_table(a: dict, b: dict, vocab: dict) -> dict:
    """The values two extraction passes of one spec agree on (evidence from pass a); a key they
    read differently is abstained: value None."""
    out: dict = {kind: {} for kind in KINDS}
    for kind, key, _item, _allowed in vocab_items(vocab):
        va = table_value(a, kind, key)
        out[kind][key] = a[kind][key] if va is not None and va == table_value(b, kind, key) else {"value": None}
    return out


def agents_contradictions(table: dict, vocab: dict) -> list[dict]:
    """Keys AGENTS.md settles that the table states with another value."""
    out = []
    for kind, key, item, _allowed in vocab_items(vocab):
        av, v = item.get("agents_value"), table_value(table, kind, key)
        if av is not None and v is not None and v != av:
            out.append({"id": f"{KIND_ID[kind]}/{key}", "label": item["label"], "value": v,
                        "value_meaning": value_meaning(vocab, kind, v), "agents_value": av,
                        "agents_meaning": value_meaning(vocab, kind, av),
                        "quotes": [e["quote"] for e in table[kind][key].get("evidence", [])[:2]]})
    return out


def consensus_values(tables: list[dict], vocab: dict) -> dict:
    """{"values": {kind: {key: value or None}}, "votes": {id: [value per oracle]}, "contested":
    [ids some oracle states without a majority behind one value (or, for a settled key, without a
    majority addressing it)], "overrides": [settled ids whose majority value was not AGENTS.md's]}."""
    need = majority(len(tables))
    values: dict = {kind: {} for kind in KINDS}
    votes, contested, overrides = {}, [], []
    for kind, key, item, _allowed in vocab_items(vocab):
        kid = f"{KIND_ID[kind]}/{key}"
        vs = [table_value(t, kind, key) for t in tables]
        votes[kid] = vs
        counts = Counter(v for v in vs if v is not None)
        av = item.get("agents_value")
        if av is not None:
            value = av if sum(counts.values()) >= need else None
            if value is not None and counts.get(av, 0) < need:
                overrides.append(kid)
        else:
            top = counts.most_common(1)
            value = top[0][0] if top and top[0][1] >= need else None
        if value is None and counts:
            contested.append(kid)
        values[kind][key] = value
    return {"values": values, "votes": votes, "contested": contested, "overrides": overrides}


def dissent(table: dict, values: dict, vocab: dict) -> list[str]:
    """Ids of the keys with a reference value that `table` states otherwise, or not at all."""
    return [f"{KIND_ID[kind]}/{key}" for kind, key, _i, _a in vocab_items(vocab)
            if values[kind][key] is not None and table_value(table, kind, key) != values[kind][key]]


def agreement(table: dict, values: dict, vocab: dict) -> float:
    """Share of the keys with a reference value that `table` states with that value."""
    keyed = sum(1 for kind, key, _i, _a in vocab_items(vocab) if values[kind][key] is not None)
    return round(1 - len(dissent(table, values, vocab)) / keyed, 4) if keyed else 1.0


def consensus_names(name_sets: list[set[str]]) -> set[str]:
    """The names a majority of the sets contain."""
    need = majority(len(name_sets))
    counts = Counter(n for s in name_sets for n in s)
    return {n for n, c in counts.items() if c >= need}


def jaccard(a: set[str], b: set[str]) -> float:
    return round(len(a & b) / len(a | b), 4) if a | b else 1.0


def pick_medoid(scores: list[tuple[float, float]]) -> int:
    """Index of the oracle closest to the consensus, from its (decision agreement, Jaccard of its
    cited names with the consensus names); ties go to the lowest index."""
    return max(range(len(scores)), key=lambda i: (*scores[i], -i))


def consensus_table(tables: list[dict], values: dict, medoid: int, labels: list[str], vocab: dict) -> dict:
    """The reference decision table: each value with its evidence from the medoid when it holds
    that value, else from the first oracle that does (`source` names the oracle; "AGENTS.md" for
    a settled value no oracle states)."""
    out: dict = {kind: {} for kind in KINDS}
    for kind, key, _item, _allowed in vocab_items(vocab):
        v = values[kind][key]
        if v is None:
            out[kind][key] = {"value": None}
            continue
        holders = [i for i, t in enumerate(tables) if table_value(t, kind, key) == v]
        if not holders:
            out[kind][key] = {"value": v, "evidence": [], "files": [], "source": "AGENTS.md"}
            continue
        src = medoid if medoid in holders else holders[0]
        out[kind][key] = {**tables[src][kind][key], "source": labels[src]}
    return out


def render_md(report: dict) -> str:
    """consensus.md: how the reference was formed from the oracles."""
    labels = report["oracles"]
    out = ["# 参考决策（多 oracle 共识）", "",
           f"{len(labels)} 个独立 oracle，各抽取两次：两次一致的值才算该 oracle 的表态，否则弃权。"
           f"参考值取至少 {report['majority']} 个 oracle 一致的值；AGENTS.md 已定的项，只要多数 oracle 有表态，"
           "就取 AGENTS.md 的值；没有多数的项不计分。", "",
           f"- 参考 spec（与共识最接近的 oracle）：{report['medoid']}；其中与共识不一致或未表态的决策："
           f"{len(report['medoid_dissent'])}",
           f"- 有参考值的决策：{report['stated']}；无多数（不计分）：{len(report['contested'])}；"
           f"按 AGENTS.md 改正：{len(report['overrides'])}",
           f"- 覆盖目标：{len(report['names'])} 个 HMOS 名称（多数 oracle 的基线 spec 都引用）", "",
           "| oracle | 与共识决策一致率 | 与覆盖目标的 Jaccard |", "|---|---|---|"]
    out += [f"| {lab} | {o['agreement']:.1%} | {o['names_jaccard']:.1%} |" for lab, o in report["per_oracle"].items()]
    for title, ids in (("无多数的决策（不计分）", report["contested"]), ("按 AGENTS.md 改正的决策", report["overrides"]),
                       ("参考 spec 与共识不一致的决策（证据取自其他 oracle）", report["medoid_dissent"])):
        if ids:
            out += ["", f"## {title}", "", "| 决策 | " + " | ".join(labels) + " |",
                    "|---|" + "---|" * len(labels)]
            out += [f"| {i} | " + " | ".join(fmt_value(v) for v in report["votes"][i]) + " |" for i in ids]
    return "\n".join(out) + "\n"
