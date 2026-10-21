# spec_loop

**Teach a weaker model to write an OpenSpec.** A strong oracle model writes a reference OpenSpec that a human reviews and freezes. A weaker student model writes its own spec for the same task without ever seeing the reference. The oracle then scores the gap and writes a playbook, which the student receives on its next attempt. The loop repeats until the student's score stops improving.

The task: port the HMOS `telephony_call_manager` module (OpenHarmony v6.0) to the liteOS watch platform, under the constraints in `communication_mcu/AGENTS.md`. This stage produces planning artifacts only: baseline capability specs of the HMOS module plus one migration change, `migrate-call-manager-to-liteos`. No production code is written.

Every agent runs headless through the Cursor CLI (`agent -p`), each in its own throwaway snapshot of the repository. The tooling is standard-library Python.

---

## Architecture

![spec_loop architecture](architecture.svg)

1. **Shared inputs.** `AGENTS.md`, `openspec/config.yaml`, the HMOS module, the OpenSpec skills and `prompts/task.md` are fixed at `base_sha` and identical for every agent. `inputs.lock.json` records their hashes and the CLI versions.
2. **Isolated agent runs.** Each oracle, student, judge and synthesizer call gets a fresh snapshot with no git history, runs through `runner.py`, and is checked by `guards.py`. Its trajectory is rendered for reading and exported for TrajViz.
3. **Oracle.** The oracle writes the reference spec once. You review it, edit it directly or ask the oracle to revise, then freeze it.
4. **Teaching loop.** The student writes its spec blind. The judge scores it against the frozen reference with a fixed rubric, and the synthesizer turns the gaps and the student's trajectory into the next playbook, which a script checks for copied answers.
5. **Outputs and analysis.** Specs, scores, reports and playbooks land in `runs/<run>/`; trajectories can be opened in TrajViz.

---

## Requirements

- Linux or WSL with Python 3.10+ (no third-party packages)
- Cursor CLI `agent`, logged in (`agent status`)
- OpenSpec CLI 1.13+ (`openspec`)
- `git` and `tar`
- The target repository (`repo` in `config.json`) containing commit `base_sha`, and the OpenSpec skills under `<cursor_dir>/skills/openspec-*`
- Optional: a TrajViz checkout with its virtualenv (`trajviz.bin`), for analysis views and HTML reports

---

## Quick start: smoke test

The smoke test exercises the whole pipeline in about 10 minutes, using a tiny task (one capability) and the student model in every role:

```bash
cd spec_loop
python3 loop.py smoke --run smoke1
```

It runs oracle, freeze, student, judge and synthesizer, then prints a PASS/FAIL checklist. The checklist covers the model each run reported, transcript capture, guards, the freeze manifest, a valid score, an accepted playbook, and the playbook being inserted into the next student prompt.

---

## Running the loop

```bash
cd spec_loop
python3 loop.py prepare --run r1             # lock inputs, extract the base snapshot
python3 loop.py oracle  --run r1             # oracle writes the reference spec
python3 loop.py student --run r1 --iter 0    # optional: start the baseline student in parallel
```

Review `runs/r1/oracle/spec/openspec/`. Edit the files directly, ask the oracle to revise, or both. A revision resumes the oracle's session, and your direct edits are synced into its workspace first:

```bash
python3 loop.py oracle --run r1 --revise "Explain the VoIP decision in design.md and cite AGENTS.md"
python3 loop.py oracle --run r1 --revise-file review-notes.md
```

When you are satisfied, freeze the spec. After this it never changes, and every later stage verifies its hash:

```bash
python3 loop.py freeze  --run r1
python3 loop.py iterate --run r1 --iters 3   # student -> judge -> synthesizer, repeated
python3 loop.py status  --run r1
```

`iterate` skips stages that already completed, so it is safe to re-run after an interruption. It stops early when the score has not improved for `plateau` iterations; the best playbook is the one that produced the best score. With `--samples M` it runs M students in parallel per iteration: the iteration score is their mean, and the synthesizer learns from the median sample.

Stages are long. On the first run the oracle took about 45 minutes and the student about 30, so run them detached:

```bash
nohup python3 -u loop.py iterate --run r1 --iters 3 > runs/r1-iterate.log 2>&1 &
```

---

## What keeps the experiment fair

- **One task.** `prompts/task.md` goes unchanged to the oracle and the student. A student run differs only in the model and the playbook appended after the task.
- **Locked inputs.** `prepare` records `base_sha`, the hashes of AGENTS.md, config.yaml, the skills, every prompt and the rubric, and the CLI versions. The student, judge and synthesizer stages warn if a prompt has changed since then.
- **Blind workspaces.** Each agent works in a fresh `git archive` snapshot with a single commit and no history; the original repository's history and branches contain earlier specs. Oracle outputs live outside the student's workspace. The leak check scans every tool call, including subagent transcripts, plus tool outputs for exposed paths. It fails a run that touches `spec_loop/`, another stage's workspace, the original workspace, other projects' agent transcripts, or earlier GLM exports.
- **Frozen reference.** `freeze` writes `MANIFEST.sha256` and makes the spec read-only; every later stage re-verifies it.
- **Planning only.** The no-code guard reads `git status` in the workspace. Anything written outside `openspec/` fails an oracle run and is excluded from a student's score.
- **Scoring is separate from teaching.** The judge scores in a fresh session against a fixed rubric, and the script computes the weighted total. Each gap is tagged `student_wrong`, `student_defensible` or `reference_questionable`; only `student_wrong` gaps are taught.
- **The playbook may not leak the answer.** A script rejects a playbook that shares long passages with the reference (beyond text that also appears in AGENTS.md, config.yaml, the task or the HMOS source), names most of the reference's capability ids, or exceeds the line limit. The synthesizer gets up to two rewrites.
- **The model is the one you asked for.** Every run compares the model reported in the stream's `system/init` event against `models.<role>.expect` and fails on a mismatch.

---

## Stages

| Stage | Model (config role) | Reads | Writes (under `runs/<run>/`) |
|---|---|---|---|
| `oracle` | `oracle` | task.md and the shared inputs | `oracle/spec/`, trajectory, guards, metrics |
| `freeze` | none | `oracle/spec/` | `oracle/MANIFEST.sha256` |
| `student --iter k` | `student` | task.md and the playbook from iteration k-1 | `iter-k/student[-sN]/` |
| `compare --iter k` | `judge` | task, rubric, reference, student spec, `metrics.md`, previous gap ids | `iter-k/compare[-sN]/score.json`, `report.md`; a row in `scores.csv` |
| `synthesize --iter k` | `synthesizer` | task, reference, student spec, trajectory, stats, TrajViz views, report, score, previous playbook and changelogs, scores, playbook rules | `iter-k/playbook/playbook.md`, `changelog.md`, `overlap_report.json` |

The judge and synthesizer work in their own snapshots, with their inputs under `_inputs/` and their results written to `_outputs/`. The judge's `score.json` is schema-checked, with one fix attempt in the same session. The total is the sum of score/5 times weight, normalized to 100. Reports and playbooks are written in zh-CN to match the project; the prompts are in English.

---

## Run directory

```
runs/<run>/
  inputs.lock.json  state.json  scores.csv
  base/                      # snapshot at base_sha, used for metrics (local only)
  oracle/
    spec/openspec/           # the reference; edit here during review
    MANIFEST.sha256          # after freeze
    trajectory.md  stats.json  guards.json  metrics.json  *.run.json  *.prompt.md
    trajectory.jsonl  transcripts/  trajviz/            # local only
  iter-00/
    student/    spec/  trajectory.md  stats.json  guards.json  metrics.json ...
    compare/    score.json  report.md  metrics.md  metrics_diff.json ...
    playbook/   playbook.md  changelog.md  overlap_report.json ...
  iter-01/ ...
```

Scratch workspaces stay in `<workspace_root>/<run>/<stage>/` for inspection and are wiped whenever that stage is rebuilt. Git tracks the prompts, rubric, config, specs, scores, reports and playbooks. It ignores raw `*.jsonl`, stderr logs, copied transcripts, `base/`, TrajViz output and `runs/smoke*/`.

---

## Trajectory analysis and TrajViz

Every agent run produces:

- `trajectory.md`: one line per tool call (path, command, exit code, result size), plus thinking excerpts and assistant text. A header gives tokens, duration, HMOS files read, subagents and failed validations.
- `stats.json`: the same totals as JSON, including the real token usage reported by the CLI.
- `trajviz/<label>.trajviz.json`: an export TrajViz can load (Cursor format). Upload it into the TrajViz dashboard (`uv run agent-trajviz` in the TrajViz checkout). When `trajviz.bin` is set, the analysis views (`trajviz/<label>.views/`) and a standalone report (`trajviz/<label>.html`) are written alongside.

TrajViz's own collector (`agent-trajviz-collect cursor`) reads tool results from the Cursor IDE's `state.vscdb`, which CLI runs never write. `lib/trajviz_export.py` builds the same `cursor_composer` schema from the CLI's stream-json instead, which carries full tool outputs, exit codes, tool timings and reasoning. Subagent sessions are linked to the Task calls that started them.

```bash
python3 loop.py trajviz --run r1                  # every stage
python3 loop.py trajviz --run r1 --stage oracle
```

Two caveats:
- TrajViz token counts for Cursor exports are estimates, so its "Cache Efficiency" health check is meaningless. Real totals are in `stats.json` and the export's `info.usageData`.
- Subagent tool calls carry inputs but no outputs, which inflates TrajViz's tool success rate when subagents were used.

---

## Configuration (`config.json`)

| Key | Meaning |
|---|---|
| `repo`, `base_sha` | Target repository, and the commit every snapshot is cut from |
| `cursor_dir` | Directory whose `skills/openspec-*` and `commands/opsx-*` are copied into each workspace |
| `workspace_root` | Where scratch workspaces go; keep it outside `repo` and `spec_loop` |
| `change_name`, `hmos_dir` | The change id both agents must create; the HMOS module's path in the repo |
| `preexisting_specs`, `preexisting_changes` | Specs and changes in the base that are not part of the task (ignored by metrics) |
| `models.{oracle,judge,synthesizer,student}` | `id` is passed to `agent --model`; `expect` is the model name the CLI must report |
| `smoke_model` | Model used for every role in smoke runs |
| `timeouts_min` | Wall-clock limit per role |
| `iterations`, `plateau` | Default iteration count; stop after this many iterations without improvement |
| `student_retries`, `judge_fix_retries`, `synth_fix_retries` | Retries for an invalid student run, an invalid score.json, a rejected playbook |
| `rubric_weights` | Weight per rubric dimension; keys must match `rubric.md` |
| `playbook_limits` | Line cap, n-gram size, copied-passage limits, maximum share of reference capability ids |
| `trajviz` | `bin` (path to agent-trajviz), `html_report`, `output_chars` (cap per tool output), `synth_views` (views given to the synthesizer) |
| `render` | Truncation limits for `trajectory.md` |

To change the task, the rubric or the base commit, edit the file and `prepare` a new run, so that scores within a run stay comparable.

---

## Command reference

| Command | Purpose |
|---|---|
| `prepare --run R [--smoke] [--force]` | Create a run: lock the inputs, extract the base snapshot |
| `oracle --run R` | Run the oracle in a fresh workspace |
| `oracle --run R --revise TEXT` (or `--revise-file F`) | Resume the oracle session with reviewer feedback |
| `freeze --run R [--force]` | Validate, hash and make the reference read-only |
| `student --run R --iter K [--samples M] [--dry-run]` | Run the student; `--dry-run` prints its prompt |
| `compare --run R --iter K` | Judge the student spec(s) of an iteration |
| `synthesize --run R --iter K` | Write the playbook for iteration K+1 |
| `iterate --run R [--iters N] [--start K] [--samples M]` | Repeat student, compare and synthesize |
| `status --run R` | Oracle state, validity of each student run, scores |
| `trajviz --run R [--stage S]` | (Re-)export runs for TrajViz |
| `smoke --run R` | End-to-end plumbing test |

---

## Common issues

**`Cannot use this model` or `HTTP 502` at startup.** The GLM 5.3 ids (`glm-5p3-max`, `glm-5p3-high`) work but are not listed by `agent models`, and the CLI sometimes rejects them at startup. The runner retries startup failures (4 attempts, 30 s apart) and resumes a run that drops mid-way (up to 3 times, in the same session). A run that never reports the expected model fails.

**The 1M / 200k context split is not enforced.** The CLI rejects bracket overrides such as `[context=1m]` for GLM, so oracle and student differ in reasoning effort only. Token usage is recorded per run.

**Glob fails for GLM 5.3.** The CLI's Glob tool rejects the arguments GLM sends, and agents fall back to `ls` and `rg`. This affects every role equally.

**`zsh: == not found` in a trajectory.** Agents' shell commands run in zsh, where a bare `echo ===` fails. It is harmless.

**`warning: prompts changed since prepare`.** A prompt or the rubric differs from what the run was prepared with, so later scores may not be comparable with earlier ones. Prepare a new run for deliberate changes.

**`the frozen oracle spec changed since freeze`.** Something modified `runs/<run>/oracle/spec/`. Restore it (for example with `git checkout`); the manifest is the source of truth.

**Removing workspaces.** Judge and synthesizer workspaces contain read-only copies of the frozen spec; run `chmod -R u+w <dir>` before `rm -rf`.

---

## Layout

```
loop.py                 CLI and stage orchestration
config.json             paths, models, limits
rubric.md               the judge's scoring dimensions
architecture.svg        the diagram above
prompts/
  task.md               the task (oracle and student)
  smoke_task.md         reduced task for smoke runs
  compare.md            judge prompt
  synthesize.md         synthesizer prompt
  playbook_rules.md     what a playbook may contain (enforced)
lib/
  workspace.py          history-free snapshots
  runner.py             agent -p wrapper: stream capture, retries, resume, model check, transcripts
  guards.py             no-code guard, validation, leak check, playbook checker
  render_traj.py        trajectory.md and stats.json
  spec_metrics.py       deterministic spec metrics and the reference/student diff
  trajviz_export.py     stream-json to TrajViz export, views and HTML report
  common.py             paths, run state, file helpers
```
