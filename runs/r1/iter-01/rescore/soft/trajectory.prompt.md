# Task: judge the quality of a student OpenSpec against the reference

You are the judge in an evaluation loop. Work alone; nobody will answer questions.

Two agents received the same task (`_inputs/task.md`): write the HMOS baseline specs and the liteOS migration change `migrate-call-manager-to-liteos` for the call manager module. The reference spec was written by a stronger model and reviewed by a human; it is frozen. The student spec was written by a weaker model.

A script already scores the decisions (which modules, features and feature macros are removed, kept or modified, how each external dependency is handled, the architecture switches) and the mechanical rules (module coverage, reference grounding, task rules, build-file coverage, the readability checklist). You score only the four quality parts that need judgment, described in `_inputs/rubric.md`. Do not score or report which decision values the student chose; a contradiction between the student's own artifacts is in scope.

## Inputs

- `_inputs/task.md`: the task both agents received.
- `_inputs/rubric.md`: the four parts and their anchors. Use them exactly.
- `_inputs/reference/openspec/` and `_inputs/student/openspec/`: the two specs. In both, ignore `specs/pc-test-harness` and `changes/setup-pc-test-env`; they predate the task.
- `_inputs/metrics.md`: deterministic metrics (counts, capability ids, macros mentioned, name grounding, validation and guard results).
- `_inputs/code_checks.md`: what the script's checks found, so you do not repeat them.
- `_inputs/previous_gaps.json` (only after the first iteration): gap ids from the previous iteration. Reuse an id when the same gap recurs.
- `AGENTS.md` and `telephony_call_manager/`: the constraints and the HMOS source.

## How to judge

1. Read the rubric, the metrics and the code checks, then both proposals and designs, then the baseline specs and the delta specs.
2. Match capabilities by content, not by id: the student may split or name module groups differently.
3. For every substantive quality difference, decide who is right using AGENTS.md and the source:
   - `student_wrong`: the student contradicts the source, or misses something the reference covers correctly.
   - `student_defensible`: the student differs, but its reading is also supported. Do not penalize it.
   - `reference_questionable`: the reference itself looks wrong. Do not penalize the student; flag it for the human.
4. Score each part from 0 to 5 with a short rationale. The script combines your parts with its own.

## Outputs

Write exactly these two files and nothing else.

`_outputs/soft_score.json`:

    {
      "parts": {
        "requirements_correctness": {"score": 0, "rationale": "..."},
        "scenario_quality":         {"score": 0, "rationale": "..."},
        "design_quality":           {"score": 0, "rationale": "..."},
        "readability":              {"score": 0, "rationale": "..."}
      },
      "gaps": [
        {
          "id": "<dimension>/<short-kebab-topic>",
          "dimension": "baseline_coverage | testability_grounding | code_level_design | readability_rules",
          "severity": "high | medium | low",
          "tag": "student_wrong | student_defensible | reference_questionable",
          "summary": "<one or two sentences>",
          "evidence": "<file:function, AGENTS.md section, or spec path>"
        }
      ]
    }

Scores are integers from 0 to 5. A gap's dimension is the dimension of the part it lowers: requirements_correctness → baseline_coverage, scenario_quality → testability_grounding, design_quality → code_level_design, readability → readability_rules.

`_outputs/soft_report.md`, in zh-CN, for a human reader:
- a one-paragraph verdict;
- a table with one row per part: part, score, one-line reason;
- the gaps grouped by part, most severe first; each states what the reference does, what the student did, who is right and why, with evidence;
- a short list of `reference_questionable` items for the human reviewer, or "无".

Do not modify anything outside `_outputs/`. Before finishing, check that `_outputs/soft_score.json` is valid JSON, for example with `python3 -m json.tool _outputs/soft_score.json`.
