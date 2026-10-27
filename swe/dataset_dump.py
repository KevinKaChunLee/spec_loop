"""Run with the Python that has swebench installed: write one repository's instances of a SWE-bench
dataset to a JSON file. swe_loop.py itself needs only the standard library.

    python -m swe.dataset_dump SWE-bench/SWE-bench_Verified test django/django out.json
"""

import json
import sys

from swebench.harness.utils import load_swebench_dataset

KEEP = ("instance_id", "repo", "base_commit", "version", "difficulty", "image", "problem_statement", "created_at",
        "patch", "test_patch", "FAIL_TO_PASS", "PASS_TO_PASS", "eval_script")


def main() -> None:
    name, split, repo, out = sys.argv[1:5]
    rows = [{k: d.get(k) for k in KEEP} for d in load_swebench_dataset(name, split) if d["repo"] == repo]
    with open(out, "w", encoding="utf-8") as f:
        json.dump(rows, f)
    print(f"{len(rows)} {repo} instances of {name}/{split}")


if __name__ == "__main__":
    main()
