"""smoke: the whole pipeline (prepare, oracle, iterate with noise and two syntheses, test, status) on
a tiny synthetic repository with the scripted fake model, on the host. Needs opencode, but not
Docker, a GPU or the SWE-bench harness; checks the plumbing, not learning."""

from __future__ import annotations

import argparse
import difflib
import socket

from lib.common import die, load_state, read_json, remove_tree, run_dir

from . import fake_llm
from .ablation import cmd_test
from .core import CFG, RUN_KIND, run_kind
from .evaluate import read_results, stage_attempts
from .pipeline import cmd_iterate, cmd_oracle, cmd_status, write_run
from .synthesis import playbook_text

CALC = """def add(a, b):
    return a - b  # add


def mul(a, b):
    return a + b  # mul


def sub(a, b):
    return a * b  # sub


def div(a, b):
    return a + b  # div


def neg(a):
    return a  # neg
"""
FIXES = {"add": ("a - b  # add", "a + b  # add"), "mul": ("a + b  # mul", "a * b  # mul"),
         "sub": ("a * b  # sub", "a - b  # sub"), "div": ("a + b  # div", "a / b  # div"),
         "neg": ("return a  # neg", "return -a  # neg")}
CHECKS = {"add": "calc.add(2, 3) == 5", "mul": "calc.mul(2, 3) == 6", "sub": "calc.sub(5, 3) == 2",
          "div": "calc.div(6, 3) == 2", "neg": "calc.neg(2) == -2"}
TRAIN, TEST = ("add", "mul", "sub"), ("div", "neg")
LEAKY_PLAYBOOK = ("mkdir -p _outputs && printf '%s\\n' '# Playbook' "
                  "'- Reproduce the issue with a short python -c script before you change any code.' "
                  "'- Run the same script again after the change, and keep the change small.' "
                  "'- The bugs are usually in calc.py.' > _outputs/playbook.md && "
                  "printf '%s\\n' '# Changelog' '- First rules from the training failures.' > _outputs/changelog.md")


def gold_patch(func: str) -> str:
    old, new = FIXES[func]
    fixed = CALC.replace(old, new)
    diff = difflib.unified_diff(CALC.splitlines(True), fixed.splitlines(True), "a/calc.py", "b/calc.py")
    return "diff --git a/calc.py b/calc.py\n" + "".join(diff)


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def configure(port: int) -> None:
    """Point this process's configuration at the fake model and keep the run small."""
    CFG["server"]["base_url"] = f"http://127.0.0.1:{port}/v1"
    CFG["models"] = {"oracle": {"id": "fake/oracle", "context": 32768, "output": 4096},
                     "synthesizer": {"id": "fake/teacher", "context": 32768, "output": 4096},
                     "student": {"id": "fake/student", "context": 32768, "output": 4096}}
    CFG["dataset"].update(repo="smoke/calc", train=len(TRAIN), test=len(TEST))
    CFG["repo_hints"]["smoke/calc"] = "Check a function with `python -c 'import calc; print(calc.add(2, 3))'`."
    CFG["timeouts_min"] = {"oracle": 5, "student": 5, "synthesizer": 5}
    CFG["iterations"] = 2
    CFG["iteration0_samples"] = 2


def row(func: str) -> dict:
    return {"instance_id": f"smoke__calc-{func}", "repo": "smoke/calc", "base_commit": "fixture", "version": "0",
            "difficulty": "<15 min fix", "image": None, "created_at": "",
            "problem_statement": f"`calc.{func}` returns the wrong result: `{CHECKS[func]}` does not hold.",
            "patch": gold_patch(func), "test_patch": "", "FAIL_TO_PASS": [f"test_{func}_result (tests.CalcTests)"],
            "PASS_TO_PASS": [], "eval_script": ""}


def cmd_smoke(args) -> None:
    run_id = args.run
    if not run_id.startswith("swe-smoke"):
        die(f"smoke runs start over by deleting their run directory, so their names must start with swe-smoke "
            f"(got '{run_id}')")
    if run_kind(run_id) not in (None, RUN_KIND):
        die(f"run '{run_id}' belongs to {run_kind(run_id)}; use another run name")
    remove_tree(run_dir(run_id))
    fixture = run_dir(run_id) / "fixture" / "calc"
    fixture.mkdir(parents=True)
    (fixture / "calc.py").write_text(CALC, encoding="utf-8")
    port = free_port()
    old, new = FIXES["add"]
    oracle_fix = " ".join(f"-e 's/{FIXES[f][0].replace('*', chr(92) + '*')}/{FIXES[f][1]}/'" for f in TRAIN)
    server = fake_llm.serve(port, {"fake/student": ["ls", f"sed -i 's/{old}/{new}/' calc.py"],
                                   "fake/oracle": [f"sed -i {oracle_fix} calc.py"],
                                   "fake/teacher": [LEAKY_PLAYBOOK, LEAKY_PLAYBOOK]})
    configure(port)
    try:
        extra = {f"smoke__calc-{f}": {"local_repo": str(fixture), "check": f"python3 -c 'import calc; assert {CHECKS[f]}'"}
                 for f in TRAIN + TEST}
        write_run(run_id, [row(f) for f in TRAIN], [row(f) for f in TEST], "local", extra)
        ns = argparse.Namespace(run=run_id, allow_drift=False, start=0)
        cmd_oracle(ns)
        cmd_iterate(ns)
        cmd_test(run_id, 1, None, False)
        cmd_status(ns)
    finally:
        server.shutdown()
    report(run_id)


def report(run_id: str) -> None:
    state = load_state(run_id)
    stages, pbs = state["stages"], state["playbooks"]
    checks = [
        ("oracle resolves all 3 training tasks", stages.get("oracle", {}).get("resolved") == 3),
        ("iteration 0: 2 samples x 3 tasks, the add task resolved in both", stages.get("iter-00", {}).get("scored") == 6
         and stages.get("iter-00", {}).get("resolved") == 2),
        ("noise baseline written, no flips", (read_json(run_dir(run_id) / "noise.json") or {}).get("flip_rate") == 0),
        ("two playbooks written", pbs.get("iter-00", {}).get("ok") and pbs.get("iter-01", {}).get("ok")),
        ("the leaky line was stripped from both", all(pbs.get(s, {}).get("stripped", 0) >= 1 for s in ("iter-00", "iter-01"))),
        ("no stripped line left in a playbook", all("calc.py" not in playbook_text(run_id, s)
                                                     for s in ("iter-00", "iter-01"))),
        ("iterations 1 and 2 used the previous playbook", all((stages.get(s, {}).get("playbook") or {}).get("source") == p
                                                              for s, p in (("iter-01", "iter-00"), ("iter-02", "iter-01")))),
        ("the second synthesis revised the first", pbs.get("iter-01", {}).get("based_on") == "iter-00"),
        ("held-out test: both arms scored on 2 tasks", (state.get("test") or {}).get("paired") == 2),
        ("transcripts exported", all((d / "trajectory.transcript.json").exists()
                                     for _rec, d in stage_attempts(run_id, "iter-00"))),
        ("results.csv has every attempt", len(read_results(run_id)) == 3 + 6 + 3 + 3 + 2 + 2),
    ]
    print("\nsmoke checks:")
    for name, ok in checks:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}")
    if not all(ok for _n, ok in checks):
        raise SystemExit(2)
