# Task: rule on the decisions where the student spec and the reference spec disagree

You are a judge in an evaluation loop. Work alone; nobody will answer questions.

Two agents received the same task (`_inputs/task.md`): write the HMOS baseline specs and the liteOS migration change `{{change_name}}` for the call manager module. The reference spec was written by a stronger model and reviewed by a human. A script extracted a fixed table of decisions from both specs (modules removed, kept or modified; features; feature macros; external dependencies; architecture switches) and compared them. Agreements are already scored. You rule on each disagreement.

## Inputs

- `_inputs/disputes.json`: one entry per disagreement:
  - `id`, `kind` and `question`;
  - `reference` and `student`: the value, its meaning, verbatim evidence quotes from that spec and the files it cites. `student` is null when the student spec does not decide the key (`status: missing`);
  - `agents_value`: the value AGENTS.md itself settles, or null when AGENTS.md leaves it open;
  - for modules, the capabilities that own the directory in each spec, with their 裁剪范围 rows.
- `_inputs/reference/openspec/` and `_inputs/student/openspec/`: both specs, for the context around the quotes.
- `AGENTS.md`, `openspec/config.yaml` and `telephony_call_manager/` (the HMOS source): use them to settle each disagreement.

## How to rule

For every entry choose one ruling:
- `student_wrong`: the student's value, or its silence, contradicts AGENTS.md or the source, or misses a decision the reference makes correctly.
- `student_defensible`: AGENTS.md and the source support the student's value as well as the reference's. This covers genuinely ambiguous rules and the same outcome expressed differently, for example a module the reference trims inside a modified capability while the student removes it as a capability of its own.
- `reference_questionable`: the reference's value itself looks wrong.

If both specs in fact decide the same thing and only the extracted values differ, rule `student_defensible` and say so in the reason. Check the source when the disagreement is about facts (whether a macro is referenced, whether a file or call site exists). Rule only on the listed entries.

Severity: `high` when the difference changes what is migrated for a whole feature or module, or breaks an AGENTS.md rule; `medium` for a partial or local difference; `low` for differences with little practical effect.

## Output

Write `_outputs/rulings.json` and nothing else:

    {
      "rulings": [
        {"id": "<entry id>", "ruling": "student_wrong | student_defensible | reference_questionable",
         "severity": "high | medium | low",
         "reason": "<zh-CN, one to three sentences>",
         "evidence": "<AGENTS.md section, file:line in telephony_call_manager/, or spec path>"}
      ]
    }

Give exactly one ruling per entry. Before finishing, check the file with `python3 -m json.tool _outputs/rulings.json`.
