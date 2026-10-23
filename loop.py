#!/usr/bin/env python3
"""Oracle / student OpenSpec loop driven by the Cursor CLI.

Typical flow:
  loop.py prepare --run r1
  loop.py oracle  --run r1                   # oracle writes the reference spec
  # review runs/r1/oracle/spec/openspec/: edit it directly, and/or
  loop.py oracle  --run r1 --revise "..."    # resume the oracle session with feedback
  loop.py extract --run r1 --target oracle   # propose the reference decision table
  # review runs/r1/oracle/decisions.review.md, edit decisions.proposed.json if needed
  loop.py freeze  --run r1                   # hash spec + decisions, read-only; never change again
  loop.py iterate --run r1 --iters 3         # student -> compare -> synthesize, repeated
  loop.py status  --run r1

Single stages: `student`, `compare`, `synthesize` (all take --iter K).
`student --iter 0` may run before the freeze, since it needs nothing from the oracle.
Offline checks that touch neither state.json nor scores.csv: `rescore` (score an existing
student spec again), `leak-check` (run the playbook checks on a playbook), `extract`.

Plumbing test with a tiny task and the smoke model for every role:
  loop.py smoke --run smoke1

Every agent run is also exported for TrajViz under <stage>/trajviz/ (`<label>.trajviz.json`
to upload into the dashboard, `<label>.views/` and `<label>.html`); `loop.py trajviz --run r1`
re-exports existing runs.
"""

from __future__ import annotations

import argparse
import os
import signal
import sys

from lib.common import lock_run
from lib.runner import set_parallel_limit, stop_agents

from stages.core import CFG
from stages.oracle import cmd_extract, cmd_freeze, cmd_oracle, cmd_prepare
from stages.student import cmd_student
from stages.scoring import cmd_compare, cmd_rescore
from stages.synthesis import cmd_leak_check, cmd_synthesize
from stages.noise import cmd_noise
from stages.ablation import MIN_ARM_SAMPLES, cmd_ablate
from stages.pipeline import cmd_iterate, cmd_reset, cmd_smoke, cmd_status, cmd_trajviz


ALLOW_DRIFT_HELP = ("continue although prompts, rubric, vocabulary, config, skills, models or CLI versions "
                    "changed since prepare (recorded in state.json)")
# The run locks a command holds while it runs. Commands in different scopes may run side by side,
# such as the baseline student while the oracle writes the reference; state.json updates are
# serialised separately. status, trajviz, rescore, leak-check and extract of anything but the
# oracle hold none: they write only their own outputs.
LOCK_SCOPES = {"prepare": ("oracle", "loop"), "smoke": ("oracle", "loop"), "oracle": ("oracle",),
               "freeze": ("oracle",), "student": ("loop",), "compare": ("loop",), "noise": ("loop",),
               "synthesize": ("loop",), "ablate": ("loop",), "iterate": ("loop",), "reset": ("loop",)}


def stop(signum: int, _frame) -> None:
    """Ctrl-C or kill: stop the agent sessions too, which would otherwise keep running (and billing)
    in their own process groups after this process is gone. No log(): it takes a lock that the
    interrupted code may hold."""
    os.write(2, f"\nloop.py: {signal.Signals(signum).name}, stopping its agent sessions\n".encode())
    stop_agents()
    os._exit(128 + signum)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("prepare", help="create runs/<run>/ with inputs.lock.json and the base snapshot")
    p.add_argument("--run", required=True)
    p.add_argument("--force", action="store_true")
    p.add_argument("--smoke", action="store_true", help="use the small smoke task and smoke model")
    p.add_argument("--reference-from", metavar="RUN",
                   help="reuse RUN's frozen reference spec, manifest and reference decisions (no oracle run)")
    p.add_argument("--allow-drift", action="store_true",
                   help="reuse the reference even if the vocabulary, extraction prompt or task changed since "
                        "it was extracted")
    p.set_defaults(fn=cmd_prepare)

    p = sub.add_parser("oracle", help="run the oracle, or revise its spec with --revise")
    p.add_argument("--run", required=True)
    g = p.add_mutually_exclusive_group()
    g.add_argument("--revise", help="reviewer feedback; resumes the oracle session")
    g.add_argument("--revise-file", help="file containing reviewer feedback")
    p.set_defaults(fn=cmd_oracle)

    p = sub.add_parser("freeze", help="hash the reviewed oracle spec and reference decisions, make them "
                                      "read-only (an already frozen spec gets its decisions frozen)")
    p.add_argument("--run", required=True)
    p.add_argument("--force", action="store_true", help="freeze even if validation fails")
    p.set_defaults(fn=cmd_freeze)

    p = sub.add_parser("extract", help="extract a decision table from a spec or a playbook")
    p.add_argument("--run", required=True)
    p.add_argument("--target", required=True,
                   help="run-relative directory holding spec/ (oracle, iter-00/student) or playbook .md")
    p.add_argument("--passes", type=int, default=2, help="independent passes, run in parallel (default 2)")
    p.add_argument("--out", help="run-relative output directory (default <target>/decisions)")
    p.set_defaults(fn=cmd_extract)

    p = sub.add_parser("student", help="run the student for one iteration")
    p.add_argument("--run", required=True)
    p.add_argument("--iter", type=int, required=True)
    p.add_argument("--samples", type=int, default=1)
    p.add_argument("--dry-run", action="store_true", help="print the prompt and exit")
    p.add_argument("--allow-drift", action="store_true", help=ALLOW_DRIFT_HELP)
    p.set_defaults(fn=cmd_student)

    p = sub.add_parser("compare", help="score the student spec(s) of one iteration")
    p.add_argument("--run", required=True)
    p.add_argument("--iter", type=int, required=True)
    p.add_argument("--judges", type=int, help="independent judge passes per sample (default: config judges)")
    p.add_argument("--fresh", action="store_true",
                   help="judge again even samples whose score.json matches the current inputs")
    p.add_argument("--allow-drift", action="store_true", help=ALLOW_DRIFT_HELP)
    p.set_defaults(fn=cmd_compare)

    p = sub.add_parser("noise", help="student, judge and extractor spread of one iteration; sets the thresholds")
    p.add_argument("--run", required=True)
    p.add_argument("--iter", type=int, default=0)
    p.add_argument("--judges", type=int, help="judge passes per later iteration score (default: config judges)")
    p.add_argument("--extract-passes", type=int, default=2,
                   help="2 (default) runs a second extraction of every sample to measure extractor noise; "
                        "1 skips it")
    p.add_argument("--allow-drift", action="store_true", help=ALLOW_DRIFT_HELP)
    p.set_defaults(fn=cmd_noise)

    p = sub.add_parser("ablate", help="none / full / process-only playbook arms on fresh samples")
    p.add_argument("--run", required=True)
    p.add_argument("--playbook", default="top", help="`top` (highest raw score) or iter-NN")
    p.add_argument("--samples", type=int, default=3,
                   help=f"fresh students per new arm (at least {MIN_ARM_SAMPLES})")
    p.add_argument("--judges", type=int, help="judge passes per sample (default: config judges)")
    p.add_argument("--arms", default="full",
                   help="new arms besides none, comma-separated: full (default), process_only")
    p.add_argument("--force", action="store_true", help="replace an ablation of another playbook")
    p.add_argument("--allow-drift", action="store_true", help=ALLOW_DRIFT_HELP)
    p.set_defaults(fn=cmd_ablate)

    p = sub.add_parser("rescore", help="score an existing student spec again into iter-KK/<out>/ "
                                       "(state.json and scores.csv untouched)")
    p.add_argument("--run", required=True)
    p.add_argument("--iter", type=int, required=True)
    p.add_argument("--out", default="rescore", help="output directory name under iter-KK/ (default rescore)")
    p.add_argument("--student", help="run-relative student directory (default iter-KK/student)")
    p.add_argument("--student-decisions", help="run-relative decisions.json to reuse instead of extracting")
    p.add_argument("--reuse", action="store_true",
                   help="reuse the extraction, rulings and soft score already in iter-KK/<out>/ "
                        "(for changes to the scoring code only)")
    p.add_argument("--judges", type=int, default=1, help="independent judge passes (default 1)")
    p.set_defaults(fn=cmd_rescore)

    p = sub.add_parser("synthesize", help="write the playbook for the next iteration")
    p.add_argument("--run", required=True)
    p.add_argument("--iter", type=int, required=True)
    p.add_argument("--allow-drift", action="store_true", help=ALLOW_DRIFT_HELP)
    p.set_defaults(fn=cmd_synthesize)

    p = sub.add_parser("leak-check", help="run the playbook checks on an existing playbook")
    p.add_argument("--run", required=True)
    p.add_argument("--iter", type=int, default=0, help="checks iter-KK/playbook/playbook.md")
    p.add_argument("--playbook", help="run-relative playbook path instead")
    p.add_argument("--strict", action="store_true",
                   help="flag every stated decision value, settled by AGENTS.md or not")
    p.add_argument("--decisions", help="run-relative playbook decisions.json to reuse instead of extracting")
    p.add_argument("--write-stripped", action="store_true", help="also write the playbook without flagged lines")
    p.set_defaults(fn=cmd_leak_check)

    p = sub.add_parser("iterate", help="student -> compare -> synthesize for a fixed number of iterations")
    p.add_argument("--run", required=True)
    p.add_argument("--iters", type=int, default=None, help="default: config.json iterations")
    p.add_argument("--start", type=int, default=0)
    p.add_argument("--samples", type=int, default=1)
    p.add_argument("--judges", type=int, help="judge passes per sample (default: config judges)")
    p.add_argument("--allow-drift", action="store_true", help=ALLOW_DRIFT_HELP)
    p.set_defaults(fn=cmd_iterate)

    p = sub.add_parser("reset", help="discard iterations K and later (outputs, state, score rows)")
    p.add_argument("--run", required=True)
    p.add_argument("--from-iter", type=int, required=True)
    p.set_defaults(fn=cmd_reset)

    p = sub.add_parser("status", help="show the state and score history of a run")
    p.add_argument("--run", required=True)
    p.set_defaults(fn=cmd_status)

    p = sub.add_parser("trajviz", help="(re)export agent runs for TrajViz: JSON, views, HTML report")
    p.add_argument("--run", required=True)
    p.add_argument("--stage", help="e.g. oracle or iter-00/student (default: every stage)")
    p.set_defaults(fn=cmd_trajviz)

    p = sub.add_parser("smoke", help="end-to-end plumbing test with the smoke task")
    p.add_argument("--run", required=True)
    p.set_defaults(fn=cmd_smoke)

    args = ap.parse_args()
    scopes = ("oracle",) if args.cmd == "extract" and args.target == "oracle" else LOCK_SCOPES.get(args.cmd, ())
    lock_run(args.run, scopes, " ".join(sys.argv[1:]))
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, stop)
    set_parallel_limit(CFG.get("max_parallel_agents", 8))
    args.fn(args)


if __name__ == "__main__":
    main()
