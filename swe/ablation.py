"""test: the held-out tasks with no playbook and with the chosen playbook, compared task by task.

With one sample per task and arm the test is McNemar's exact test on the tasks only one arm
resolves; with more samples, the sign-flip test on the per-task difference in resolve rate. With n
tasks neither can go below p = 2 / 2^n (0.0625 for 5 tasks), so a small test set is a sanity check."""

from __future__ import annotations

from lib.common import die, load_state, log, run_dir, state_update, timestamp, write_json, write_text_atomic
from lib.stats import mcnemar_exact, sign_flip

from .core import CFG, iteration_stage, playbook_path, tasks
from .evaluate import evaluate_stage
from .noise import outcomes
from .solve import solve_stage
from .synthesis import playbook_text

ARMS = ("test-none", "test-full")


def choose_playbook(run_id: str, wanted: str | None) -> str:
    """The playbook to test: `wanted` (an iteration such as iter-01), or the one whose iteration
    resolved the most training attempts (ties go to the later playbook)."""
    state = load_state(run_id)
    if wanted:
        if not playbook_path(run_id, wanted).exists():
            die(f"no playbook at {playbook_path(run_id, wanted)}")
        return wanted
    candidates = []
    for k in range(CFG["iterations"]):
        src, used_in = iteration_stage(k), state.get("stages", {}).get(iteration_stage(k + 1), {})
        if playbook_path(run_id, src).exists() and used_in.get("resolve_rate") is not None:
            candidates.append((used_in["resolve_rate"], k, src))
    if not candidates:
        die("no playbook has been tried on the training tasks yet; run `iterate` first, or pass --playbook iter-NN")
    rate, _k, src = max(candidates)
    log(f"testing the playbook of {src}: its iteration resolved {rate:.0%} of the training attempts")
    return src


def cmd_test(run_id: str, samples: int, wanted: str | None, allow_drift: bool) -> dict:
    src = choose_playbook(run_id, wanted)
    test_tasks = tasks(run_id, "test")
    playbook = playbook_text(run_id, src)
    solve_stage(run_id, "test-none", "student", test_tasks, samples, None, allow_drift)
    solve_stage(run_id, "test-full", "student", test_tasks, samples, playbook, allow_drift, playbook_source=src)
    for arm in ARMS:
        evaluate_stage(run_id, arm)
    none, full = outcomes(run_id, "test-none"), outcomes(run_id, "test-full")
    rows = []
    for t in test_tasks:
        a, b = list(none.get(t["instance_id"], {}).values()), list(full.get(t["instance_id"], {}).values())
        rows.append({"instance_id": t["instance_id"], "difficulty": t.get("difficulty"),
                     "none": round(sum(a) / len(a), 4) if a else None, "full": round(sum(b) / len(b), 4) if b else None,
                     "none_samples": len(a), "full_samples": len(b)})
    paired = [r for r in rows if r["none"] is not None and r["full"] is not None]
    if samples == 1:
        b = sum(1 for r in paired if r["full"] > r["none"])
        c = sum(1 for r in paired if r["none"] > r["full"])
        test = {"name": "McNemar exact", "full_only": b, "none_only": c, "p": round(mcnemar_exact(b, c), 4)}
    else:
        test = {"name": "sign-flip on per-task resolve rates",
                "p": round(sign_flip([r["full"] - r["none"] for r in paired]), 4)}
    test["min_p"] = round(min(1.0, 2 / 2 ** len(paired)), 4) if paired else None
    result = {"playbook": src, "samples": samples, "tasks": rows, "paired": len(paired), "test": test,
              "resolve_rate": {arm: round(sum(r[arm] for r in paired) / len(paired), 4) if paired else None
                               for arm in ("none", "full")},
              "measured_at": timestamp()}
    write_json(run_dir(run_id) / "test" / "ablation.json", result)
    write_text_atomic(run_dir(run_id) / "test" / "report.md", render(result))
    with state_update(run_id) as st:
        st["test"] = {k: result[k] for k in ("playbook", "samples", "paired", "resolve_rate")} | {"p": test["p"]}
    log(f"test ({len(paired)} tasks): no playbook {result['resolve_rate']['none']}, playbook {src} "
        f"{result['resolve_rate']['full']}; {test['name']} p = {test['p']} (smallest possible {test['min_p']})")
    return result


def render(r: dict) -> str:
    t = r["test"]
    out = ["# Held-out test", "",
           f"Playbook `{r['playbook']}` against no playbook, {r['samples']} student sample(s) per task and arm, "
           f"{r['paired']} task(s) scored in both arms.", "",
           "| task | difficulty | no playbook | playbook | change |", "|---|---|---|---|---|"]
    for row in r["tasks"]:
        change = "-" if row["none"] is None or row["full"] is None else \
            ("better" if row["full"] > row["none"] else "worse" if row["full"] < row["none"] else "same")
        out.append(f"| {row['instance_id']} | {row['difficulty'] or ''} | {row['none']} | {row['full']} | {change} |")
    out += ["", f"- resolve rate: no playbook {r['resolve_rate']['none']}, playbook {r['resolve_rate']['full']}",
            f"- {t['name']}: p = {t['p']}" + (f" ({t['full_only']} task(s) only the playbook arm resolves, "
                                               f"{t['none_only']} only the other)" if "full_only" in t else ""),
            f"- with {r['paired']} tasks the smallest possible p is {t['min_p']}; treat this as a sanity check "
            f"until the test set is larger."]
    return "\n".join(out) + "\n"
