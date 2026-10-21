# Task: score a student OpenSpec against the reference OpenSpec

You are the judge in an evaluation loop. Work alone; nobody will answer questions.

Two agents received the same task (`_inputs/task.md`): write the HMOS baseline specs and the liteOS migration change `migrate-call-manager-to-liteos` for the call manager module. The reference spec was written by a stronger model and reviewed by a human; it is frozen. The student spec was written by a weaker model.

## Inputs

- `_inputs/task.md`: the task both agents received.
- `_inputs/rubric.md`: the scoring dimensions and anchors. Use them exactly.
- `_inputs/reference/openspec/`: the reference spec.
- `_inputs/student/openspec/`: the student spec. In both, ignore `specs/pc-test-harness` and `changes/setup-pc-test-env`; they predate the task.
- `_inputs/metrics.md`: deterministic metrics computed by a script (counts, capability ids, macros mentioned, name grounding, validation and guard results).
- `_inputs/previous_gaps.json` (only after the first iteration): gap ids from the previous iteration. Reuse an id when the same gap recurs.
- `AGENTS.md` and `telephony_call_manager/`: the constraints and the HMOS source. Use them to settle disagreements.

## How to judge

1. Read the rubric and the metrics, then both proposals and designs, then the baseline specs and the delta specs.
2. Match capabilities by content, not by id: the student may split or name module groups differently.
3. For every substantive difference, decide who is right using AGENTS.md and the source:
   - `student_wrong`: the student contradicts AGENTS.md or the source, or misses something the reference covers correctly.
   - `student_defensible`: the student differs, but its reading is also supported. Do not penalize it.
   - `reference_questionable`: the reference itself looks wrong. Do not penalize the student; flag it for the human.
4. Score each rubric dimension from 0 to 5 with a short rationale. Do not compute a weighted total; the script does that.

## Outputs

Write exactly these two files and nothing else.

`_outputs/score.json`:

    {
      "dimensions": {
        "baseline_coverage":     {"score": 0, "rationale": "..."},
        "trim_scope":            {"score": 0, "rationale": "..."},
        "external_deps":         {"score": 0, "rationale": "..."},
        "code_level_design":     {"score": 0, "rationale": "..."},
        "testability_grounding": {"score": 0, "rationale": "..."},
        "readability_rules":     {"score": 0, "rationale": "..."}
      },
      "gaps": [
        {
          "id": "<dimension>/<short-kebab-topic>",
          "dimension": "<one of the six dimension keys>",
          "severity": "high | medium | low",
          "tag": "student_wrong | student_defensible | reference_questionable",
          "summary": "<one or two sentences>",
          "evidence": "<file:function, AGENTS.md section, or spec path>"
        }
      ]
    }

Scores are integers from 0 to 5.

`_outputs/report.md`, in zh-CN, for a human reader:
- a one-paragraph verdict;
- a table with one row per dimension: dimension, score, one-line reason;
- the gaps grouped by dimension, most severe first; each states what the reference does, what the student did, who is right and why, with evidence;
- a short list of `reference_questionable` items for the human reviewer, or "无".

Do not modify anything outside `_outputs/`. Before finishing, check that `_outputs/score.json` is valid JSON, for example with `python3 -m json.tool _outputs/score.json`.
