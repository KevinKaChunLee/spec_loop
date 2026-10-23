# Task: write the playbook for the student

You are improving a playbook in a teaching loop. Work alone; nobody will answer questions.

A weaker model (the student) receives the same task as the reference author (`_inputs/task.md`), with your playbook appended. The goal is that the student, following the playbook, writes an OpenSpec as close as possible in substance to the reference spec. You can see the reference; the student never will.

## Inputs

- `_inputs/task.md`: the task.
- `_inputs/reference/openspec/` and `_inputs/student/openspec/`: the reference spec and the student's spec (ignore `pc-test-harness` and `setup-pc-test-env`; they predate the task).
- `_inputs/trajectory.md`: what the student did, step by step (tool calls, excerpts of its thinking). `_inputs/stats.json`: totals (tokens, files read, share of HMOS files read, subagents, failed validations).
- `_inputs/trajviz/` (if present): TrajViz analysis views of the student trajectory as JSON (health checks, issues, failure patterns and chains, fruitless search streaks, tool-selection anti-patterns, repeated searches, edit thrash, bottlenecks, workflow phases). Its token numbers are estimates; use `stats.json` for real totals.
- `_inputs/report.md` and `_inputs/score.json`: the judge's gap analysis of this student spec.
- `_inputs/sample_gaps.md` (only when several students ran this iteration): every gap of every student, with how many students share it. The report, trajectory and spec above belong to the median student.
- `_inputs/previous_playbook.md` (if present): the playbook to revise. Normally it is the playbook the student had in this iteration. `_inputs/changelog_history.md` (if present): earlier changelogs.
- `_inputs/reverted_playbook.md` (only after a clearly worse iteration): the playbook the student actually had in this iteration. It scored clearly below the best iteration, so revise `previous_playbook.md` (the best iteration's playbook, or none: then write a new one) instead, and use this iteration's report and trajectory as evidence of what the reverted playbook got wrong.
- `_inputs/scores.csv`: the score history across iterations.
- `_inputs/playbook_rules.md`: what the playbook may and may not contain, and its size limit. A script enforces these rules and rejects a playbook that breaks them.
- `AGENTS.md` and `telephony_call_manager/`: the constraints and the HMOS source.

## Method

1. Read the report and the score, then the trajectory, to find the causes of each `student_wrong` gap: what the student never looked at, misread, lost to context pressure, or did not verify. Do not teach gaps tagged `student_defensible` or `reference_questionable`. If `_inputs/sample_gaps.md` exists, prioritize the gaps most students share: they are systematic. A gap only one student has may be chance; teach it only if the fix is cheap and general.
2. If a previous playbook exists, keep the rules whose gaps closed, fix the rules the student misapplied, and drop rules that did not help. The playbook should get better, not just longer.
3. Write rules the student can execute: concrete steps, commands and checks, in order. Teach how to find something out, never the answer: do not state a decision AGENTS.md leaves open (a feature's, macro's or dependency's treatment, the handling of locks), do not state findings about what the HMOS code does (the branches of a function, the paths of a call chain), and do not name functions, classes, variables, macros or files from the HMOS source that AGENTS.md, config.yaml and the task do not already name; directory paths are fine. `_inputs/playbook_rules.md` explains how both are enforced.
4. The student has a much smaller context window than you (about 200k tokens), and the HMOS module is far larger than that. Teach it to budget: what to read first, what to grep instead of reading, when to hand a module group to a subagent, and what the subagent must return.

## Outputs

Write exactly these files and nothing else:

- `_outputs/playbook.md`, in zh-CN and self-contained; the student sees nothing else from this loop. A suggested structure: 目标与产出 / 工作顺序 / 上下文预算 / 每个产出物前的检查清单 / 易错点 / 收尾自检.
- `_outputs/changelog.md`, in zh-CN: one line per rule added, changed or removed, each naming the gap id(s) it addresses.

Do not modify anything outside `_outputs/`.
