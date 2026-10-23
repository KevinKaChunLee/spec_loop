# Rubric

The total is out of 100. Six dimensions carry the weights in `config.json` (`scoring.weights`); each dimension is a weighted mix of parts (`scoring.parts`), every part a value from 0 to 1. Most parts are computed by the script. You score the four parts marked **judge**, each with an integer from 0 to 5.

| dimension | weight | parts |
|---|---|---|
| agents_compliance | 10 | agreement on the decisions AGENTS.md settles: module trims, features, macros, dependencies and architecture switches where the reference takes AGENTS.md's value (script and dispute rulings) |
| open_decisions | 15 | agreement on the decisions AGENTS.md leaves open or the reference decides differently (script and dispute rulings) |
| baseline_coverage | 35 | 0.1 share of HMOS module directories covered, 0.6 behaviour coverage: share of the HMOS names the reference's baseline cites that the student's baseline also cites, scaled down when the student cites more than twice as many (script), 0.3 **requirements_correctness** (judge) |
| code_level_design | 15 | 0.3 callmanager.gni / bundle.json coverage (script), 0.7 **design_quality** (judge) |
| testability_grounding | 15 | 0.5 reference grounding rate, 0.2 config.yaml task rules (script), 0.3 **scenario_quality** (judge) |
| readability_rules | 10 | 0.7 config.yaml / task.md checklist (script), 0.3 **readability** (judge) |

Anchors for every judge part:
- 5: matches the reference in substance; no material gaps.
- 4: minor gaps only.
- 3: several medium gaps, or one high-severity gap.
- 2: multiple high-severity gaps.
- 1: mostly missing or wrong.
- 0: absent.

Differences tagged `student_defensible` or `reference_questionable` do not lower a part.

## requirements_correctness

Whether the baseline requirements describe the HMOS module as it is today, within the module groups the student covers (the script measures which groups are covered and which of the reference's cited names the student cites).
- Requirements describe behaviour that exists in the HMOS source, not the liteOS target. Naming a function is not describing it: a requirement that only lists names is a gap here.
- Behaviour that matters is not missing: decision chains are expanded branch by branch, and service-level behaviours of large files are present.
- `## Purpose` names the real source locations and the build switches or macros that actually guard code.

## scenario_quality

- Scenarios are concrete enough to become gtest cases in `test/`: a trigger, an observable result, the function or state involved.
- One requirement describes one behaviour; no padding with near-duplicate scenarios.
- Safety-relevant behaviour the change touches (emergency calls, call rejection) has scenarios and gtest tasks.

## design_quality

How the design turns the decisions into code-level actions, and whether the artifacts agree with each other.
- Removed functionality: what is deleted, which retired macros are cleaned up, which guards of supported macros are removed, what is stubbed, each with a reason; the knock-on effects on kept code (dangling calls, dead branches) are handled.
- Concurrency: where the ffrt queues and locks are, and what replaces them on liteOS.
- Architecture: CallManagerClient calls CallManagerService directly; stubs live in `stub/` at the port root; directory structure and file names mirror HMOS.
- Proposal, design, delta specs and tasks say the same thing about every decision; a decision stated two ways is a gap here.

## readability

- zh-CN prose with English OpenSpec keywords; easy for a human reviewer to scan.
- Tables for enumerations; decisions are short and cite names instead of pasting source; open questions are real questions.
- No padding: long paragraphs, repeated content and near-duplicate requirements lower this part.
