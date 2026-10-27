#!/usr/bin/env python3
"""SWE-bench playbook distillation: a student model (through opencode) solves GitHub issues in the
tasks' own containers, the official harness scores the patches, and a teacher model turns the
student's failures on training tasks into a playbook that is then tested on held-out tasks.

Typical flow (see README_swe.md):
  swe_loop.py check   [--run R]          # environment: opencode, swebench, Docker, SGLang, egress
  swe_loop.py prepare --run R            # pick tasks, pull images, check the gold patches resolve
  swe_loop.py oracle  --run R            # the stronger model solves the training tasks once
  swe_loop.py iterate --run R            # iteration 0 (noise), syntheses, iterations 1..N
  swe_loop.py test    --run R            # held-out tasks: no playbook vs the chosen playbook
  swe_loop.py status  --run R

  swe_loop.py smoke   --run swe-smoke    # the whole pipeline on a toy repo with a scripted model
"""

from __future__ import annotations

import argparse
import os
import signal
import sys

from lib.common import lock_run
from lib.runner import set_parallel_limit, stop_agents

from swe.ablation import cmd_test
from swe.core import CFG, require_swe_run
from swe.noise import cmd_noise
from swe.pipeline import cmd_check, cmd_iterate, cmd_oracle, cmd_prepare, cmd_status
from swe.smoke import cmd_smoke

ALLOW_DRIFT_HELP = ("continue although prompts, config, opencode or swebench versions, or the served models "
                    "changed since prepare (recorded in state.json)")
UNLOCKED_COMMANDS = ("check", "status")


def stop(signum: int, _frame) -> None:
    """Ctrl-C or kill: stop the agent sessions and their containers too."""
    os.write(2, f"\nswe_loop.py: {signal.Signals(signum).name}, stopping its agent sessions\n".encode())
    stop_agents()
    os._exit(128 + signum)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("check", help="check opencode, swebench, Docker, the model endpoint and container egress")
    p.add_argument("--run", help="a prepared run, to probe egress with one of its task images")
    p.add_argument("--image", help="a SWE-bench instance image to probe egress with")
    p.set_defaults(fn=cmd_check)

    p = sub.add_parser("prepare", help="select the tasks, write the run, pull images, check the gold patches")
    p.add_argument("--run", required=True)
    p.add_argument("--force", action="store_true", help="delete an existing run and prepare it again")
    p.add_argument("--no-pull", action="store_true", help="do not pull the task images now")
    p.add_argument("--skip-gold-check", action="store_true", help="do not evaluate the gold patches")
    p.set_defaults(fn=cmd_prepare)

    p = sub.add_parser("oracle", help="the oracle solves the training tasks once")
    p.add_argument("--run", required=True)
    p.add_argument("--allow-drift", action="store_true", help=ALLOW_DRIFT_HELP)
    p.set_defaults(fn=cmd_oracle)

    p = sub.add_parser("iterate", help="iteration 0, then synthesis and the next iteration, up to `iterations`")
    p.add_argument("--run", required=True)
    p.add_argument("--start", type=int, default=0, help="first iteration (completed work is reused)")
    p.add_argument("--allow-drift", action="store_true", help=ALLOW_DRIFT_HELP)
    p.set_defaults(fn=cmd_iterate)

    p = sub.add_parser("noise", help="the flip rate between iteration 0's samples")
    p.add_argument("--run", required=True)
    p.set_defaults(fn=lambda a: cmd_noise(a.run))

    p = sub.add_parser("test", help="the held-out tasks with no playbook and with the chosen playbook")
    p.add_argument("--run", required=True)
    p.add_argument("--samples", type=int, default=CFG["test_samples"], help="student samples per task and arm")
    p.add_argument("--playbook", help="the iteration whose playbook to test, e.g. iter-01 (default: the best)")
    p.add_argument("--allow-drift", action="store_true", help=ALLOW_DRIFT_HELP)
    p.set_defaults(fn=lambda a: cmd_test(a.run, a.samples, a.playbook, a.allow_drift))

    p = sub.add_parser("status", help="tasks, stages, playbooks, noise and the test result of a run")
    p.add_argument("--run", required=True)
    p.set_defaults(fn=cmd_status)

    p = sub.add_parser("smoke", help="the whole pipeline on a toy repository with a scripted fake model")
    p.add_argument("--run", default="swe-smoke")
    p.set_defaults(fn=cmd_smoke)

    args = ap.parse_args()
    if args.cmd not in ("prepare", "smoke") and getattr(args, "run", None):
        require_swe_run(args.run)
    if args.cmd not in UNLOCKED_COMMANDS and getattr(args, "run", None):
        lock_run(args.run, ("swe",), " ".join(sys.argv[1:]))
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, stop)
    set_parallel_limit(CFG["max_parallel_agents"])
    args.fn(args)


if __name__ == "__main__":
    main()
