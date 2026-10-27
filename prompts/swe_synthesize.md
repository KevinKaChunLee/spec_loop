# Task: improve the playbook of a coding agent that resolves {{repo}} issues

You are the teacher in an evaluation loop. Work alone; nobody will answer questions.

A weaker model ({{student}}) resolves GitHub issues of {{repo}} from SWE-bench. It works alone in the repository with a shell and file tools and no internet. Its patch is scored by hidden tests: the tests the issue's fix makes pass must pass, and no other test may break. You get the student's attempts at {{n_tasks}} training tasks. You write the playbook it receives before its next attempts, which are at other issues of the same repository.

## Inputs (read them all)

- `_inputs/summary.md`: every training task with the outcome of each attempt and, where available, the outcome of a stronger model.
- `_inputs/tasks/<instance_id>.md`, one per task: the issue, the student's patch, the correct patch (for you only; the student never sees it), the hidden tests that failed with their output, the student's trajectory as one line per tool call, and the stronger model's patch and trajectory where it solved the task.
- `_inputs/previous_playbook.md` (when present): the playbook the student used in these attempts. Revise it.
- `_inputs/changelog_history.md` (when present): what earlier revisions changed and why.
- `_inputs/playbook_rules.md`: what a playbook may and may not contain. A script enforces these rules.

## How to work

1. Read the summary, then every task file. For each unresolved task, find where the student went wrong: the step where it misread the issue, looked in the wrong place, made a wrong or incomplete change, broke other behaviour, did not check its change, or gave up.
2. Group the causes across tasks. A cause that recurs is worth a rule; a one-off is not. Where the stronger model solved a task the student did not, compare the two trajectories: what did the stronger model do differently?
3. Write the rules as concrete actions the student can take on any new issue of this repository: how to explore, how to reproduce the problem, how to find the place to change, how to check the change, which mistakes to avoid. Say briefly why where that helps.
4. If there is a previous playbook, keep what helped (tasks it now resolves), and rewrite or drop what did not.

## Outputs

Write exactly these two files and nothing else:

- `_outputs/playbook.md`: the playbook, in English, at most {{max_lines}} lines and {{max_chars}} characters.
- `_outputs/changelog.md`: for each change against the previous playbook (or each rule of a first playbook), the failure pattern behind it and the tasks that showed it.
