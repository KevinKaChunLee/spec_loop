# spec_loop

English | [简体中文](README_zh.md)

**Teach a weaker model to write an OpenSpec.** A strong oracle model writes a reference OpenSpec that a human reviews and freezes. A weaker student model writes its own spec for the same task without ever seeing the reference. The oracle then scores the gap and writes a playbook, which the student receives on its next attempt. The loop runs a fixed number of iterations, scores are judged against a measured noise threshold, and an ablation on fresh samples tests whether the best playbook really helps.

The task: port the HMOS `telephony_call_manager` module (OpenHarmony v6.0) to the liteOS watch platform, under the constraints in `communication_mcu/AGENTS.md`. This stage produces planning artifacts only: baseline capability specs of the HMOS module plus one migration change, `migrate-call-manager-to-liteos`. No production code is written.

Every agent runs headless through the Cursor CLI (`agent -p`), each in its own throwaway snapshot of the repository. The tooling is standard-library Python.

---

## Architecture

![spec_loop architecture](architecture.svg)

1. **Shared inputs.** `AGENTS.md`, `openspec/config.yaml`, the HMOS module, the OpenSpec skills and `prompts/task.md` are fixed at `base_sha` and identical for every agent. `inputs.lock.json` records their hashes and the CLI versions.
2. **Isolated agent runs.** Each oracle, student, extractor, judge and synthesizer call gets a fresh snapshot with no git history, runs through `runner.py`, and is checked by `guards.py`. Its trajectory is rendered for reading and exported for TrajViz.
3. **Oracle.** The oracle writes the reference spec once and the extractor proposes its decision table. You review both, edit them or ask the oracle to revise, then freeze them. Later runs reuse the frozen reference with `prepare --reference-from`.
4. **Baseline and noise.** Iteration 0 runs several students without a playbook, each scored against the frozen reference by two independent judge passes. The first playbook is written from all samples' gaps, recurring ones first, plus the median sample's full report and trajectory. The spread across samples, judges and extraction passes gives the noise estimates. From iteration 1 on, code uses them to mark score changes as within noise or significant, and to decide when the synthesizer takes back a playbook revision.
5. **Teaching loop.** Iterations 1 to N. The student writes its spec blind. Scoring compares its decision table with the reference in code, has a judge rule on disagreements and score four quality parts, and computes the total in code. The synthesizer turns the gaps and the student's trajectory into the next playbook. A script checks the playbook for copied text and leaked answers, and the loop runs a fixed number of iterations.
6. **Verification.** After the loop, the top playbook is re-tested on fresh students and compared with the iteration-0 baseline students, who had no playbook.
7. **Outputs and analysis.** Specs, scores, reports and playbooks land in `runs/<run>/`; trajectories can be opened in TrajViz.

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

When you are satisfied, extract the reference's decision table, check it, and freeze both. After this neither changes, and every later stage verifies their hashes:

```bash
python3 loop.py extract --run r1 --target oracle   # two extraction passes; writes oracle/decisions.review.md
# read oracle/decisions.review.md; correct values in oracle/decisions.proposed.json if needed
python3 loop.py freeze  --run r1
```

A later run can reuse a frozen reference instead of running the oracle again. Measure the noise once, then iterate and test the best playbook:

```bash
python3 loop.py prepare --run r2 --reference-from r1          # copies the frozen spec, manifest and decisions
python3 loop.py student --run r2 --iter 0 --samples 3         # three students without a playbook
python3 loop.py compare --run r2 --iter 0 --judges 2          # two independent judge passes per student
python3 loop.py noise   --run r2                              # spreads, extractor noise, thresholds
python3 loop.py iterate --run r2 --start 0 --iters 4          # playbooks from iterations 0-2, scored in 1-3
python3 loop.py ablate  --run r2 --playbook top --samples 3   # fresh students with the top playbook vs the baseline
python3 loop.py status  --run r2
```

`iterate` runs a fixed number of iterations and never stops early: with one sample per iteration, most score changes are within noise, and an early stop would end the loop on noise. It skips stages that already completed, so it is safe to re-run after an interruption; the last iteration writes no playbook. A completed stage counts only if its record matches: student runs made with another prompt stop the loop (reset the iteration), and a score produced from another student spec is scored again. With `--samples M` it runs M students in parallel per iteration: the iteration score is the mean of the valid ones, and the synthesizer learns from the median sample. With `--judges N` (default `judges` in config.json) every sample gets N independent judge passes; its score is their mean.

Stages are long: an oracle about 45 minutes, a student 30 to 70, a compare with two judges about 25, a synthesis 15 to 35 including its leak checks. Run them detached:

```bash
nohup python3 -u loop.py iterate --run r2 --start 0 --iters 4 > runs/r2-iterate.log 2>&1 &
```

### Reading noise and ablation results

- **Noise** (`noise.md`, `noise.json`, and `state.json` under `noise`). From the valid iteration-0 samples, all scored with the same number J of judge passes: σ_judge = sqrt(mean within-sample variance of the judge totals), and σ²_student = var(sample means). The latter is not reduced by σ²_judge / J: with a handful of samples that difference is often clamped to 0, which would leave only judge noise in the threshold, so the estimate errs on the high side instead. An iteration score is the mean of n valid samples with J judge passes each, with variance σ²_student / n + σ²_judge / (n J). Two iteration scores differ significantly only when they differ by more than 2 × sqrt(var_a + var_b); for two one-sample iterations that is 2 × √2 × σ, the `threshold` shown by `status`. A baseline measured before σ²_student was defined this way marks nothing until `noise` runs again (`--extract-passes 1` needs no agent runs). By default `noise` also runs a second extraction of every sample (`--extract-passes 1` skips it): each sample has one extraction shared by all its judge passes, so extractor noise sits inside σ_student. `noise.md` reports per sample which decisions the two extractions read differently and how many points that could move (an upper bound, `σ_extract ≤`), and it marks the decision items that flip between samples and between judges, separating the flips the extractor itself causes. Measure it once per run: re-judge the existing specs after changing the rubric, a judge prompt, the judge model or the scoring code; prepare a new run after changing the student model, the task or the reference.
- **Iteration marks.** `status`, `scores.csv` (`vs_best`) and the iterate log mark each iteration's score against the best earlier one as "within noise" or "significant", using that pair's threshold. `gaps_closed` and `gaps_reopened` count the code-derived gap ids (decisions, coverage, rules) that disappeared since the previous iteration, or came back after an earlier one had closed them.
- **Revert.** The synthesizer revises the latest playbook unless the latest iteration scored clearly below its parent, the iteration that used the playbook the latest one was revised from (iteration 0 for a playbook written from scratch). Then it revises the parent playbook instead and gets the worse one as evidence. It compares with the parent, not with the best earlier iteration, because the best of several noisy scores is biased upward and would trigger reverts more often as iterations accumulate. `state.json` records `based_on` (and `reverted_from`) for each playbook. Without a noise baseline there are no marks and no reverts; `iterate` and `synthesize` warn about it.
- **Ablation** (`ablation/report.md`, `ablation/ablation.json`). The "highest-scoring playbook" is the one with the highest raw iteration score, which overstates it, because it was picked from noisy scores; fresh samples correct that. By default two arms are judged the same way: none, the valid iteration-0 baseline students (no new runs), and full, at least three fresh students with the playbook as it passed the leak check. full − none is the playbook's effect and the only primary comparison. `--arms full,process_only` adds a third arm with the same playbook minus every line a strict leak pass flags (any decision value, including those AGENTS.md settles; any HMOS symbol; any finding about the HMOS code; saved as `ablation/playbook.process_only.md`). full − process-only then estimates residual answer content; it and process-only − none are exploratory. Because every playbook already passed the normal leak check, the two playbooks differ little, and with a few samples per arm that difference is rarely measurable. Every comparison is a two-sided Welch t test at α = 0.05, with Welch–Satterthwaite degrees of freedom from each arm's own spread: with three samples per arm the critical value is about 2.8, not 2. `ablate` stops when an arm has fewer than three valid scored samples, when the none arm was judged with another number of judge passes, or when its scores carry a provenance stamp from other inputs (`--allow-drift` overrides the last). The report lists each sample's student attempts and flags arms that ran under different CLI versions or judge inputs. It also breaks the differences down by dimension, by decision group and kind, and by gap id.

---

## What keeps the experiment fair

- **One task.** `prompts/task.md` goes unchanged to the oracle and the student. A student run differs only in the model and the playbook appended after the task.
- **Locked inputs.** `prepare` records `base_sha`, the hashes of AGENTS.md, config.yaml, the skills, every prompt, the rubric and the decision vocabulary, a fingerprint of config.json (all keys except `iterations`, `judges`, `max_parallel_agents`, `model_notes` and `workspace_root`), the models and the CLI versions. Every stage that runs agents stops when any of these changed since, unless you pass `--allow-drift`; accepted drift is recorded in `state.json` and shown by `status`. The agent CLI updates itself, so every run also records the CLI version it ran with (`agent_cli` in its `.run.json`). `prepare --reference-from` also stops when the vocabulary, the extraction prompt or the task changed since the reference decisions were extracted (recorded at freeze, followed back through runs that copied them).
- **Provenance.** Every `score.json` carries the inputs, the student spec hash, the reference manifest, the judge count and the scoring code it came from. `compare` and `ablate` reuse a score only when all of these match (`compare --fresh` judges again anyway); when only the scoring code changed, they recompute the total from the saved model outputs. Every student run writes `provenance.json` with its prompt hash and attempts.
- **Only valid student runs count.** A student run that failed, still missed deliverables after the nudges, or leaked is retried from scratch (`student_retries`); the earlier attempt is kept as `student-sN.attemptN`, and the attempt count goes to `scores.csv` and the ablation report. A run that stays invalid is not scored and is left out of the iteration mean, the gap table, the noise baseline and the ablation; `status` lists it. When a valid sample fails to score, the iteration gets no score until `compare` succeeds for every valid sample. A dispute run that leaves a ruling out after its fix attempt fails the same way, instead of charging the student.
- **Same judging everywhere.** The judge gets the same inputs in every iteration, in the noise baseline and in the ablation; in particular it never sees the previous iteration's gaps.
- **Blind workspaces.** Each agent works in a fresh `git archive` snapshot with a single commit and no history; the original repository's history and branches contain earlier specs. Oracle outputs live outside the student's workspace. The leak check scans every tool call, including subagent transcripts, plus tool outputs for exposed paths. It fails a run that touches `spec_loop/`, another stage's workspace, the original workspace, other projects' agent transcripts, or earlier GLM exports.
- **Frozen reference.** `freeze` writes `MANIFEST.sha256` and makes the spec and the human-checked reference decisions read-only; every later stage re-verifies them.
- **Planning only.** The no-code guard reads `git status` in the workspace. Anything written outside `openspec/` fails an oracle run and is excluded from a student's score.
- **Scoring is mostly code, and separate from teaching.** Decisions are compared as tables in code, and only disagreements go to a model for a ruling; a model scores just four quality parts (see [How scoring works](#how-scoring-works)). Each gap is tagged `student_wrong`, `student_defensible` or `reference_questionable`; only `student_wrong` gaps are taught.
- **The playbook may not leak the answer.** A script rejects a playbook that shares long passages with the reference (beyond text that also appears in AGENTS.md, config.yaml, the task or the HMOS source), names most of the reference's capability ids, or exceeds the line limit. It also flags lines that leak answers: the extractor runs on the playbook and flags lines stating the reference's value for a decision AGENTS.md leaves open, or stating findings about what the HMOS code does; code flags lines naming HMOS identifiers or file names that AGENTS.md, config.yaml and the task do not (directories are allowed). The synthesizer gets up to two rewrites with the flagged lines; flagged lines left after that are stripped and recorded as `auto_stripped` in `state.json` and in the changelog. Other rejections still stop the loop.
- **The model is the one you asked for.** Every run compares the model reported in the stream's `system/init` event against `models.<role>.expect` and fails on a mismatch.

---

## Stages

| Stage | Model (config role) | Reads | Writes (under `runs/<run>/`) |
|---|---|---|---|
| `oracle` | `oracle` | task.md and the shared inputs | `oracle/spec/`, trajectory, guards, metrics |
| `extract --target oracle` | `extractor` | reference spec, `decision_vocab.json` | `oracle/decisions/pass-N/`, `decisions.proposed.json`, `decisions.review.md` |
| `freeze` | none | `oracle/spec/`, `oracle/decisions.proposed.json` | `oracle/MANIFEST.sha256`, `oracle/decisions.json` |
| `student --iter k` | `student` | task.md and the playbook from iteration k-1 | `iter-k/student[-sN]/` |
| `compare --iter k` | `extractor`, then `judge` (disputes, soft parts) | task, rubric, reference spec and decisions, student spec, `metrics.md`, script checks | `iter-k/compare[-sN]/score.json`, `report.md`, `decisions_compare.json`; a row in `scores.csv` |
| `noise` | `extractor` (second extraction pass) | the iteration-0 samples' scores and specs | `noise.json`, `noise.md`, `iter-00/compare-sN/decisions-pass2/`; `noise` in `state.json` |
| `ablate` | `student`, `extractor` and `judge` (scoring); `extractor` (strict leak pass, process_only arm only) | the selected playbook, the iteration-0 samples | `ablation/full/student-sN`, `compare-sN`; `ablation/report.md`, `ablation.json` |
| `synthesize --iter k` | `synthesizer`, `extractor` (leak check) | task, reference, student spec, trajectory, stats, TrajViz views, report, score, previous playbook and changelogs, scores, playbook rules | `iter-k/playbook/playbook.md`, `changelog.md`, `overlap_report.json` |

The extractor, judge and synthesizer work in their own snapshots, with their inputs under `_inputs/` and their results written to `_outputs/`. Every JSON they write is checked by code, with one fix attempt in the same session. Reports and playbooks are written in zh-CN to match the project; the prompts are in English.

### How scoring works

1. **Decision tables.** `decision_vocab.json` fixes the keys, taken from AGENTS.md: the 功能范围 features plus VoIP, DSDA, single SIM, single account and the JS/ETS/仓颉 bindings; the supported and unsupported macros plus the macros found in the source; the 外部依赖处理 categories; and five architecture switches (SystemAbility/IPC, permission checks, locks, DSDS fixed to 0, `slotId` kept). The `extractor` maps a spec onto these keys. Every value must come from the vocabulary and carry a quote that code finds verbatim in the spec. A fifth kind, modules, is parsed by code from the proposal's 裁剪范围 table and the HMOS directories each baseline `## Purpose` names, so capabilities are matched by directory, not by id.
2. **Compare in code.** Each reference decision is `agree`, `differ` or `missing` in the student table. Macros with no reference anywhere in the HMOS tree have nothing to migrate, so any stated value agrees.
3. **Disputes.** Each disagreement goes to `prompts/disputes.md` for one ruling: `student_wrong`, `student_defensible` or `reference_questionable`, with evidence. The last two count as agreement.
4. **Soft parts.** In parallel, the judge (`prompts/compare.md`) scores four parts from 0 to 5: requirements correctness, scenario quality, design quality and readability.
5. **Total in code.** Each dimension is a weighted mix of parts (`scoring.parts`); see `rubric.md` for the table. Decisions are split in two groups. *Settled* decisions only test whether a spec follows AGENTS.md: the reference takes AGENTS.md's value, module trims follow its feature list, and unreferenced macros have nothing to decide. They form `agents_compliance` (10 points). *Open* decisions are the few that AGENTS.md leaves open or the reference decides differently, such as VoIP and locks; they form `open_decisions` (15 points). Most of the weight sits in `baseline_coverage` (35), led by behaviour coverage: the share of the HMOS function, class and macro names cited in the reference's baseline specs that the student's baseline specs also cite. It is scaled down when the student cites more than `scoring.coverage_padding_ratio` times as many names, so listing names cannot buy coverage. Other code-only parts are module coverage, reference grounding, the config.yaml task rules, callmanager.gni / bundle.json coverage and a readability checklist. The total is the weighted sum out of 100. Gap ids are stable: `feature/voip`, `macro/X`, `module/services/video`, `coverage/<module>`, `rule/<check>`. `score.json` also records `code_share`, the part of the total decided by code; disputed items and soft parts count as model-decided.

---

## Run directory

```
runs/<run>/
  inputs.lock.json  state.json  scores.csv
  base/                      # snapshot at base_sha, used for metrics (local only)
  oracle/
    spec/openspec/           # the reference; edit here during review
    decisions/pass-N/        # extraction passes; agreement.json compares them
    decisions.proposed.json  decisions.review.md        # for the human check
    decisions.json  MANIFEST.sha256                     # after freeze
    trajectory.md  stats.json  guards.json  metrics.json  *.run.json  *.prompt.md
    trajectory.jsonl  transcripts/  trajviz/            # local only
  iter-00/
    student-s1/    spec/  provenance.json  trajectory.md  stats.json  guards.json  metrics.json ...
    student-s1.attempt1/                                # an earlier, invalid attempt (if any)
    compare-s1/    score.json  report.md  decisions_compare.json  code_checks.md  metrics.md
                   decisions/                           # the extractor's table of this student
                   decisions-pass2/                     # the second extraction of `noise`
                   judge-1/ judge-2/                    # disputes/, soft/, score.json per judge pass
    playbook/      playbook.md  changelog.md  overlap_report.json  leak-N/ ...
  iter-01/ ...
  noise.json  noise.md
  ablation/      playbook.full.md  report.md  ablation.json
                 full/                                  # student-sN/, compare-sN/ (process_only/ with --arms)
```

Runs prepared before the `-sN` naming (r1) use plain `student/` and `compare/` for a single sample, with `disputes/` and `soft/` directly in `compare/`; they read as sample s1.

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
| `models.{oracle,judge,synthesizer,extractor,student}` | `id` is passed to `agent --model`; `expect` is the model name the CLI must report |
| `smoke_model` | Model used for every role in smoke runs |
| `timeouts_min` | Wall-clock limit per role |
| `iterations` | Default iteration count of `iterate` |
| `judges` | Independent judge passes per sample (disputes and soft parts) |
| `max_parallel_agents` | Agent sessions that may run at once across samples, judges and arms |
| `student_retries`, `judge_fix_retries`, `extract_fix_retries`, `synth_fix_retries` | Retries for an invalid student run, an invalid judge or dispute JSON, an invalid extraction, a rejected playbook |
| `completion_nudges` | How many times an oracle or student session is resumed when its turn ends before the deliverables exist and validate |
| `scoring` | `weights` per dimension (sum 100), `parts` (each dimension's mix of parts) and `llm_parts` (the parts the judge scores) |
| `playbook_limits` | Line cap, n-gram size, copied-passage limits, maximum share of reference capability ids |
| `trajviz` | `bin` (path to agent-trajviz), `html_report`, `output_chars` (cap per tool output), `synth_views` (views given to the synthesizer) |
| `render` | Truncation limits for `trajectory.md` |

To change the task, the rubric or the base commit, edit the file and `prepare` a new run, so that scores within a run stay comparable.

---

## Command reference

| Command | Purpose |
|---|---|
| `prepare --run R [--smoke] [--force] [--reference-from R0 [--allow-drift]]` | Create a run: lock the inputs, extract the base snapshot; with `--reference-from`, copy R0's frozen reference and decisions |
| `oracle --run R` | Run the oracle in a fresh workspace |
| `oracle --run R --revise TEXT` (or `--revise-file F`) | Resume the oracle session with reviewer feedback |
| `extract --run R --target T [--passes N]` | Extract a decision table from `T` (a run-relative directory holding `spec/`, or a playbook `.md`); `--target oracle` proposes the reference decisions |
| `freeze --run R [--force]` | Validate, hash and make the reference read-only; on a frozen spec, freezes the reviewed reference decisions |
| `student --run R --iter K [--samples M] [--dry-run]` | Run the student; `--dry-run` prints its prompt |
| `compare --run R --iter K [--judges N] [--fresh]` | Score the valid student spec(s) of an iteration, N judge passes each; reuses scores with matching provenance unless `--fresh` |
| `noise --run R [--iter K] [--extract-passes 1\|2]` | Spread between samples, judges and (default) extraction passes; writes `noise.md` and the thresholds |
| `ablate --run R [--playbook top\|iter-NN] [--samples M] [--judges N] [--arms full,process_only]` | At least three fresh students with the playbook against the iteration-0 baseline, Welch t test; resumable |
| `rescore --run R --iter K [--out NAME] [--student-decisions F] [--reuse] [--judges N]` | Score an existing student spec again into `iter-K/NAME/` without touching `state.json` or `scores.csv` |
| `synthesize --run R --iter K` | Write the playbook for iteration K+1 |
| `leak-check --run R --iter K [--strict] [--write-stripped]` | Run the playbook checks on an existing playbook and list the flagged lines |
| `iterate --run R [--iters N] [--start K] [--samples M] [--judges J]` | Repeat student, compare and synthesize for exactly N iterations |
| `reset --run R --from-iter K` | Discard iterations K and later (outputs, state, score rows) so `iterate` redoes them |
| `status --run R` | Oracle state, validity of each student run, scores |
| `trajviz --run R [--stage S]` | (Re-)export runs for TrajViz |
| `smoke --run R` | End-to-end plumbing test |

`student`, `compare`, `noise`, `synthesize`, `ablate` and `iterate` take `--allow-drift` to continue although the locked inputs changed.

Commands hold run locks (`runs/.<run>.<scope>.lock`) while they run, so two `loop.py` processes cannot work on the same part of a run at once. `oracle`, `freeze` and `extract --target oracle` hold the oracle scope; `student`, `compare`, `noise`, `synthesize`, `ablate`, `iterate` and `reset` hold the loop scope; `prepare` and `smoke` hold both. A command whose scope is taken stops at once and names the process holding it. The baseline student can therefore still run while the oracle writes the reference, and `status`, `trajviz`, `rescore`, `leak-check` and other `extract` targets, which write only their own outputs, take no lock. Every change to `state.json` is a short locked read-modify-write, so commands of the two scopes never lose each other's updates. JSON and CSV records are fsynced to a temporary file and renamed into place, so neither a reader nor a crash ever sees a half-written file. Ctrl-C or `kill` stops a command's agent sessions as well, so no orphaned agent keeps running after its lock is gone.

---

## Common issues

**`Cannot use this model` or `HTTP 502` at startup.** The GLM 5.3 ids (`glm-5p3-max`, `glm-5p3-high`) work but are not listed by `agent models`, and the CLI sometimes rejects them at startup. The runner retries startup failures (4 attempts, 30 s apart) and resumes a run that drops mid-way (up to 3 times, in the same session). A run that never reports the expected model fails.

**An agent ends its turn before writing anything.** A headless run ends as soon as the model replies without a tool call, for example after writing a plan or subagent instructions as text. For oracle and student runs, the runner then checks the deliverables (baseline specs, the four change artifacts, `openspec validate --strict`) and resumes the same session with a short "not finished, still missing: ..." message, up to `completion_nudges` times. The count is recorded as `nudges` in the run metadata and `scores.csv`. A student run that is still incomplete counts as invalid and is retried from scratch.

**The 1M / 200k context split is not enforced.** The CLI rejects bracket overrides such as `[context=1m]` for GLM, so oracle and student differ in reasoning effort only. Token usage is recorded per run.

**Glob fails for GLM 5.3.** The CLI's Glob tool rejects the arguments GLM sends, and agents fall back to `ls` and `rg`. This affects every role equally.

**`zsh: == not found` in a trajectory.** Agents' shell commands run in zsh, where a bare `echo ===` fails. It is harmless.

**`inputs changed since prepare`.** A prompt, the rubric, the vocabulary, config.json, a skill, a model or a CLI version differs from what the run was prepared with, so later scores would not be comparable with earlier ones. The agent CLI updating itself between stages is the most common cause. Prepare a new run for deliberate changes, or pass `--allow-drift` when you accept the difference.

**`run 'R' is in use by another loop.py process`.** Another command of the same lock scope is still running on that run; the message names its pid and command line. Wait for it, or stop it with Ctrl-C or `kill <pid>`, which also stops its agent sessions; the lock goes away with the process.

**`the frozen oracle spec changed since freeze`.** Something modified `runs/<run>/oracle/spec/`. Restore it (for example with `git checkout`); the manifest is the source of truth.

**Removing workspaces.** Judge and synthesizer workspaces contain read-only copies of the frozen spec; run `chmod -R u+w <dir>` before `rm -rf`.

---

## Layout

```
loop.py                 the command line: argument parsing, dispatch to the stages
stages/
  core.py               config, run paths, models, sample directories, shared helpers
  provenance.py         locked inputs, drift checks, provenance stamps of scores
  agents.py             running agents and finishing their stages (guards, trajectories, TrajViz)
  extraction.py         decision tables from a spec or a playbook
  oracle.py             prepare, oracle, extract, freeze
  student.py            student prompts, runs, attempts and validity
  marks.py              which samples count, iteration variance and thresholds, marks, gap ids
  scoring.py            compare, rescore: disputes, soft judge, the total of a sample
  synthesis.py          synthesize, leak-check, revert rule
  noise.py              noise: spread between samples, judges and extraction passes
  ablation.py           ablate and its report
  pipeline.py           iterate, reset, status, trajviz, smoke
config.json             paths, models, limits, scoring weights
rubric.md               scoring dimensions and the judge's soft parts
decision_vocab.json     fixed decision keys and values, from AGENTS.md
architecture.svg        the diagram above
prompts/
  task.md               the task (oracle and student)
  smoke_task.md         reduced task for smoke runs
  extract.md            extractor prompt: spec to decision table
  extract_playbook.md   extractor prompt: decisions and HMOS findings a playbook states
  disputes.md           judge prompt: one ruling per disagreement
  compare.md            judge prompt: the four soft parts
  synthesize.md         synthesizer prompt
  playbook_rules.md     what a playbook may contain (enforced)
lib/
  decisions.py          decision tables: parsing, validation, compare, code checks, totals, leak checks
  workspace.py          history-free snapshots
  runner.py             agent -p wrapper: stream capture, retries, resume, model check, transcripts
  stream.py             stream-json / transcript readers shared by the modules below
  guards.py             no-code guard, validation, leak check, playbook checker
  render_traj.py        trajectory.md and stats.json
  spec_metrics.py       deterministic spec metrics and the reference/student diff
  stats.py              Student's t distribution and Welch's test (no SciPy)
  trajviz_export.py     stream-json to TrajViz export, views and HTML report
  common.py             paths, run state, file helpers
```
