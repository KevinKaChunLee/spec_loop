# Task: write the playbook for the student

You are improving a playbook in a teaching loop. Work alone; nobody will answer questions.

A weaker model (the student) receives the same task as the reference author (`_inputs/task.md`), with your playbook appended. The goal is that the student, following the playbook, writes an OpenSpec as close as possible in substance to the reference spec. You can see the reference; the student never will.

## Inputs

- `_inputs/task.md`: the task.
- `_inputs/reference/openspec/` and `_inputs/student/openspec/`: the reference spec and the student's spec (ignore `pc-test-harness` and `setup-pc-test-env`; they predate the task).
- `_inputs/trajectory.md`: what the student did, step by step (tool calls, excerpts of its thinking). `_inputs/stats.json`: totals (tokens, files read, share of HMOS files read, subagents, failed validations).
- `_inputs/report.md` and `_inputs/score.json`: the judge's gap analysis of this student spec.
- `_inputs/previous_playbook.md` (if present): the playbook the student had in this iteration. `_inputs/changelog_history.md` (if present): earlier changelogs.
- `_inputs/scores.csv`: the score history across iterations.
- `_inputs/playbook_rules.md`: what the playbook may and may not contain, and its size limit. A script enforces these rules and rejects a playbook that breaks them.
- `AGENTS.md` and `telephony_call_manager/`: the constraints and the HMOS source.

## Method

1. Read the report and the score, then the trajectory, to find the causes of each `student_wrong` gap: what the student never looked at, misread, lost to context pressure, or did not verify. Do not teach gaps tagged `student_defensible` or `reference_questionable`.
2. If a previous playbook exists, keep the rules whose gaps closed, fix the rules the student misapplied, and drop rules that did not help. The playbook should get better, not just longer.
3. Write rules the student can execute: concrete steps, commands and checks, in order. Prefer teaching how to find something out over stating the answer.
4. The student has a much smaller context window than you (about 200k tokens), and the HMOS module is far larger than that. Teach it to budget: what to read first, what to grep instead of reading, when to hand a module group to a subagent, and what the subagent must return.

## Outputs

Write exactly these files and nothing else:

- `_outputs/playbook.md`, in zh-CN and self-contained; the student sees nothing else from this loop. A suggested structure: 目标与产出 / 工作顺序 / 上下文预算 / 每个产出物前的检查清单 / 易错点 / 收尾自检.
- `_outputs/changelog.md`, in zh-CN: one line per rule added, changed or removed, each naming the gap id(s) it addresses.

Do not modify anything outside `_outputs/`.
