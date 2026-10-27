"""Run with the Python that has swebench installed: write one repository's instances of a SWE-bench
dataset, all fields, to a JSON file. swe_loop.py itself needs only the standard library.

    python -m swe.dataset_dump SWE-bench/SWE-bench_Verified test django/django out.json
"""

import json
import sys

from swebench.harness.utils import load_swebench_dataset


def main() -> None:
    name, split, repo, out = sys.argv[1:5]
    rows = [dict(d) for d in load_swebench_dataset(name, split) if d["repo"] == repo]
    with open(out, "w", encoding="utf-8") as f:
        json.dump(rows, f, default=str)
    print(f"{len(rows)} {repo} instances of {name}/{split}")


if __name__ == "__main__":
    main()
