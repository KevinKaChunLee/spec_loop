"""check, prepare, oracle, iterate and status of the SWE-bench loop."""

from __future__ import annotations

import json
import random
import subprocess
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

from lib.common import ROOT, die, load_state, log, read_json, run_dir, save_state, timestamp, write_json
from lib.opencode_runner import opencode_version

from .core import (CFG, ROLES, api_key, base_url, iteration_stage, model_for, opencode_bin, served_models,
                   swebench_version, tasks, write_lock)
from .env import EGRESS_BLOCKED, OC_IN_CONTAINER, docker, docker_available, egress_probe, ensure_image
from .evaluate import as_list, evaluate_stage, gold_check
from .noise import cmd_noise
from .solve import solve_stage
from .synthesis import playbook_text, synthesize


def task_record(row: dict) -> dict:
    """What a solving agent may know about a task: no patch, no tests."""
    return {k: row.get(k) for k in ("instance_id", "repo", "base_commit", "version", "difficulty", "image",
                                    "problem_statement", "created_at")} | \
        {"reinstall": "python setup.py install" in (row.get("eval_script") or "")}


def gold_record(row: dict) -> dict:
    return {"patch": row.get("patch") or "", "test_patch": row.get("test_patch") or "",
            "FAIL_TO_PASS": as_list(row.get("FAIL_TO_PASS")), "PASS_TO_PASS": as_list(row.get("PASS_TO_PASS"))}


def select_tasks(rows: list[dict]) -> tuple[list[dict], list[dict]]:
    ds = CFG["dataset"]
    pool = sorted((r for r in rows if not ds["difficulties"] or r.get("difficulty") in ds["difficulties"]),
                  key=lambda r: r["instance_id"])
    need = ds["train"] + ds["test"]
    if len(pool) < need:
        die(f"only {len(pool)} {ds['repo']} tasks match the difficulty filter; {need} are needed")
    picked = random.Random(ds["seed"]).sample(pool, need)
    return picked[: ds["train"]], picked[ds["train"]:]


def write_run(run_id: str, train: list[dict], test: list[dict], backend: str, extra: dict | None = None) -> None:
    """tasks.json (what agents may see), gold/<id>.json (only for the harness, the synthesizer and
    the leak check), the input lock and a fresh state."""
    rd = run_dir(run_id)
    (rd / "gold").mkdir(parents=True, exist_ok=True)
    add = extra or {}
    write_json(rd / "tasks.json", {"train": [task_record(r) | add.get(r["instance_id"], {}) for r in train],
                                    "test": [task_record(r) | add.get(r["instance_id"], {}) for r in test]})
    for r in train + test:
        write_json(rd / "gold" / f"{r['instance_id']}.json", gold_record(r))
    write_lock(run_id, served_models())
    save_state(run_id, {"run": run_id, "backend": backend, "created": timestamp(), "stages": {}, "playbooks": {}})


def ensure_network() -> None:
    name = CFG["docker"]["network"]
    if subprocess.run(["docker", "network", "inspect", name], capture_output=True).returncode != 0:
        docker("network", "create", name)
        log(f"created the Docker network {name}; restrict its outbound traffic with swe/setup/egress.sh")


def cmd_prepare(args) -> None:
    rd = run_dir(args.run)
    if (rd / "state.json").exists() and not args.force:
        die(f"run '{args.run}' already exists (use --force to prepare it again)")
    ds = CFG["dataset"]
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "rows.json"
        r = subprocess.run([CFG["python"], "-m", "swe.dataset_dump", ds["name"], ds["split"], ds["repo"], str(out)],
                           cwd=ROOT, capture_output=True, text=True)
        if r.returncode != 0:
            die(f"loading {ds['name']} with {CFG['python']} failed (is swebench installed there?):\n{r.stderr[-1500:]}")
        rows = json.loads(out.read_text(encoding="utf-8"))
    train, test = select_tasks(rows)
    write_run(args.run, train, test, "docker")
    log(f"prepared run '{args.run}': {len(train)} training and {len(test)} test tasks from {ds['repo']} "
        f"({', '.join(ds['difficulties']) or 'any difficulty'}, seed {ds['seed']})")
    for split, rows_ in (("train", train), ("test", test)):
        log(f"  {split}: {', '.join(r['instance_id'] for r in rows_)}")
    why = docker_available()
    if why:
        log(f"warning: Docker is not available ({why}); images are not pulled and the gold check is skipped")
        return
    ensure_network()
    if not args.no_pull:
        for t in tasks(args.run, "train") + tasks(args.run, "test"):
            ensure_image(t["image"])
    if args.skip_gold_check:
        return
    ids = [t["instance_id"] for t in tasks(args.run, "train") + tasks(args.run, "test")]
    result = gold_check(args.run, ids)
    state = load_state(args.run)
    state["gold_check"] = result
    save_state(args.run, state)
    bad = [i for i, ok in result.items() if not ok]
    if bad:
        die(f"the gold patch does not resolve {', '.join(bad)} in this environment; check the harness logs under "
            f"{rd / 'harness'}, or prepare again with another dataset.seed")
    log(f"gold check: all {len(ids)} gold patches resolve")


def probe_tool_call(role: str) -> str | None:
    """None when `role`'s model returns a tool call for a prompt that needs one, else why not (the
    SGLang server needs --tool-call-parser, qwen25 for Qwen3)."""
    body = {"model": model_for(role)["id"], "max_tokens": 4096, "messages": [{"role": "user", "content":
            "What time is it? Answer only by calling the get_time tool."}],
            "tools": [{"type": "function", "function": {"name": "get_time", "description": "Current time",
                                                        "parameters": {"type": "object", "properties": {}}}}],
            "tool_choice": "auto"}
    req = urllib.request.Request(base_url(role) + "/chat/completions", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key()}"})
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            msg = json.loads(r.read())["choices"][0]["message"]
    except (urllib.error.URLError, OSError, ValueError, KeyError) as e:
        return f"request failed: {e}"
    return None if msg.get("tool_calls") else f"no tool call in the reply: {str(msg.get('content'))[:160]}"


def cmd_check(args) -> None:
    """The environment checks of the plan's phase 0, runnable on the server."""
    results: list[tuple[str, bool, str]] = []

    def add(name: str, ok: bool, hint: str = "") -> None:
        results.append((name, ok, hint))

    oc = opencode_bin()
    v = opencode_version(oc)
    add(f"opencode {v} ({oc})", v == CFG["opencode"]["version"], f"config expects {CFG['opencode']['version']}")
    with open(oc, "rb") as f:
        elf = f.read(4) == b"\x7fELF"
    add("opencode is a standalone binary", elf, "containers cannot run a wrapper script (such as the npm package's): "
        "install with the opencode.ai install script, or point opencode.bin at the binary itself")
    sv = swebench_version()
    add(f"swebench {sv} with {CFG['python']}", sv != "unknown", "install it: pip install swebench")
    why = docker_available()
    add("Docker daemon", why is None, why or "")
    served = served_models()
    for base, s in served.items():
        add(f"model endpoint {base}" + (f": {', '.join(s['models'])} on SGLang {s['server']['version']}, tool-call "
                                        f"parser {s['server']['tool_call_parser']}, reasoning parser "
                                        f"{s['server']['reasoning_parser']}" if s else ""),
            s is not None, "cannot be reached")
    for role in ROLES:
        mid, s = model_for(role)["id"], served[base_url(role)]
        if s is None:
            continue
        add(f"{role} model {mid} served", mid in s["models"], f"{base_url(role)} serves {', '.join(s['models'])}")
        if mid in s["models"]:
            err = probe_tool_call(role)
            add(f"{role} model {mid} makes tool calls", err is None, err or "")
    image = args.image or (next((t["image"] for t in tasks(args.run, "train")), None) if args.run else None)
    if why is None:
        net = subprocess.run(["docker", "network", "inspect", CFG["docker"]["network"]], capture_output=True).returncode == 0
        add(f"Docker network {CFG['docker']['network']}", net, "create it with swe/setup/egress.sh")
        if image:
            ensure_image(image)
            r = subprocess.run(["docker", "run", "--rm", "-v", f"{oc}:{OC_IN_CONTAINER}:ro", "--entrypoint",
                                OC_IN_CONTAINER, image, "--version"], capture_output=True, text=True, timeout=300)
            add(f"opencode runs inside {image}", r.returncode == 0 and r.stdout.strip() == v,
                (r.stdout + r.stderr).strip()[-300:])
        if net and image:
            probe = egress_probe(image, CFG["docker"], [f"{b}/models" for b in served])
            if "error" in probe:
                add("egress probe", False, probe["error"])
            else:
                for url, ok in probe["reachable"].items():
                    blocked = url in EGRESS_BLOCKED
                    add(f"containers {'cannot' if blocked else 'can'} reach {url}", ok != blocked,
                        "restrict the network with swe/setup/egress.sh" if blocked else
                        "allow it in swe/setup/egress.sh; if SGLang runs on this host, use the network's gateway address")
        elif not image:
            add("egress probe", False, "pass --run (a prepared run) or --image to test a task image")
    print("\nchecks:")
    for name, ok, hint in results:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f"  ({hint})" if hint and not ok else ""))
    if not all(ok for _n, ok, _h in results):
        raise SystemExit(2)


def cmd_oracle(args) -> None:
    """The oracle solves the training tasks once; its trajectories are contrastive evidence for the
    synthesizer and an upper bound."""
    solve_stage(args.run, "oracle", "oracle", tasks(args.run, "train"), 1, None, args.allow_drift)
    evaluate_stage(args.run, "oracle")


def cmd_iterate(args) -> None:
    """Iteration 0: the student, no playbook, iteration0_samples per task (the noise baseline), then
    the first synthesis. Iterations 1..N: the student with the previous iteration's playbook, then a
    synthesis except after the last. With iterations = 2 that is two syntheses."""
    last = CFG["iterations"]
    train = tasks(args.run, "train")
    for k in range(args.start, last + 1):
        stage = iteration_stage(k)
        playbook = src = None
        if k > 0:
            src = iteration_stage(k - 1)
            if not load_state(args.run).get("playbooks", {}).get(src, {}).get("ok"):
                synthesize(args.run, k - 1, args.allow_drift)
            playbook = playbook_text(args.run, src)
            if not playbook:
                die(f"no acceptable playbook from {src}; inspect {run_dir(args.run) / src / 'playbook'}")
        samples = CFG["iteration0_samples"] if k == 0 else 1
        solve_stage(args.run, stage, "student", train, samples, playbook, args.allow_drift, playbook_source=src)
        evaluate_stage(args.run, stage)
        if k == 0 and samples >= 2:
            cmd_noise(args.run)
        if k < last and not load_state(args.run).get("playbooks", {}).get(stage, {}).get("ok"):
            synthesize(args.run, k, args.allow_drift)


def cmd_status(args) -> None:
    state = load_state(args.run)
    print(f"run {args.run} ({state.get('backend')} backend, created {state.get('created')})")
    for split in ("train", "test"):
        print(f"  {split}: {', '.join(t['instance_id'] for t in tasks(args.run, split))}")
    for d in state.get("drift", []):
        print(f"  accepted input drift ({d['at']}): {'; '.join(d['changed'])}")
    if state.get("gold_check"):
        bad = [i for i, ok in state["gold_check"].items() if not ok]
        print(f"  gold check: {'all resolve' if not bad else 'FAILS for ' + ', '.join(bad)}")
    for stage, s in sorted(state.get("stages", {}).items()):
        rate = s.get("resolve_rate")
        pb = s.get("playbook") or {}
        print(f"  {stage:10s} {s.get('role', '?'):8s} {s.get('valid', 0)}/{s.get('attempts', 0)} valid"
              + (f", resolved {s.get('resolved')}/{s.get('scored')} ({rate:.0%})" if rate is not None else ", not scored")
              + (f", playbook of {pb.get('source')}" if pb else "")
              + (f", unscored: {', '.join(s['unscored'])}" if s.get("unscored") else ""))
    for stage, p in sorted(state.get("playbooks", {}).items()):
        print(f"  playbook {stage}: {'ok' if p.get('ok') else 'REJECTED'}, {p.get('lines')} lines, "
              f"{p.get('stripped', 0)} line(s) stripped" + (f", revises {p['based_on']}" if p.get("based_on") else ""))
    if state.get("noise"):
        n = state["noise"]
        print(f"  noise: {n['flip_rate']:.0%} of {n['tasks']} tasks flip between samples; resolve rate per sample "
              f"{', '.join(f'{r:.0%}' for r in n['resolve_rate_per_sample'])}")
    if state.get("test"):
        t = state["test"]
        print(f"  test ({t['paired']} tasks, playbook {t['playbook']}): no playbook {t['resolve_rate']['none']}, "
              f"playbook {t['resolve_rate']['full']}, p = {t['p']}")
    report = read_json(run_dir(args.run) / "test" / "ablation.json")
    if report:
        print(f"  report: {run_dir(args.run) / 'test' / 'report.md'}")
