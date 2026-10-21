# Rubric

Six dimensions, each scored with an integer from 0 to 5. The script applies the weights (`rubric_weights` in config.json).

Anchors for every dimension:
- 5: matches the reference in substance; no material gaps.
- 4: minor gaps only.
- 3: several medium gaps, or one high-severity gap.
- 2: multiple high-severity gaps.
- 1: mostly missing or wrong.
- 0: absent.

Differences tagged `student_defensible` or `reference_questionable` do not lower the score.

## baseline_coverage

How completely and correctly the student's baseline specs describe the HMOS module as it is today.
- Module groups covered, matched to the reference by content rather than by id.
- `## Purpose` names source locations and the build switches or macros involved.
- Requirements describe behaviour that exists in the HMOS source, not the liteOS target.

## trim_scope

Whether the change removes, keeps and modifies the right things.
- Features AGENTS.md lists as unsupported are removed; supported features are kept, including VoIP being deferred rather than kept.
- Feature macros are classified as AGENTS.md says (unsupported: code not migrated; supported: no explicit define needed), and decisions follow actual code usage, not macro descriptions.
- The explanatory notes in AGENTS.md are respected (for example the meaning of CALL_MANAGER_CALL_TRANSFER versus UT supplementary services, both branches of CONFIG_FACTORY_VERSION, DSDS mode fixed to 0, single SIM with room for dual SIM, single primary account).
- The proposal's 裁剪范围 matches the delta specs (every removed or modified capability has a matching delta).

## external_deps

Handling of each external dependency category in AGENTS.md, and where it lands in the code:
- not called for now, with a `// todo!!! [label] ref to <file> <function>` placeholder;
- `XxxClient::GetInstance().Xxx()` calls with stubs;
- replacements (smart pointers, logs instead of HiSysEvent and hitrace, a stubbed EventHandler instead of ffrt, structs instead of PacMap);
- not called at all (permission checks, locks, SystemAbility and IPC).

## code_level_design

How the design turns decisions into code-level actions.
- Removed functionality: delete source files, clean up retired macros, remove guards of supported macros, or stub, each with a reason.
- Affected `callmanager.gni` entries and `bundle.json` features are listed.
- Concurrency: where ffrt queues and locks are, and what replaces them on liteOS (single thread, no locks).
- Architecture: CallManagerClient calls CallManagerService directly; stubs live in `stub/` at the port root; directory structure and file names mirror HMOS.

## testability_grounding

- Scenarios are concrete enough to become gtest cases in `test/`.
- Cited names exist in the HMOS source or are declared as new code (see the grounding rate and unresolved names in the metrics).
- Tasks: each task group ends with the must-pass gate still passing; deleting source files includes syncing `callmanager.gni`; every change has at least one gtest case.

## readability_rules

- zh-CN prose with English OpenSpec keywords.
- Proposal: a 裁剪范围 table per capability, a 非目标 section, and 「需人工复核」 markers on changes touching ECC, permission checks, IPC enums or cross-component structs.
- Design: a decision index; 决策 / 理由 / 落点 for each decision; tables for enumerations; no long code blocks; open questions recorded.
- `openspec validate --all --strict` passes (see the metrics).
