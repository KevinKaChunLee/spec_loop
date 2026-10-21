# Task: write the OpenSpec for porting call_manager from HMOS to liteOS

You are working alone and unattended in a snapshot of the `communication_mcu` repository; the workspace root is the repository root. Nobody will answer questions during this run.

## Goal

Produce the planning artifacts (an OpenSpec) for porting the HMOS call manager module to the liteOS watch platform. This stage is planning only: no production code is written. A human will review the result, so it must be accurate and easy to read.

## Inputs

- `AGENTS.md`: the project constraints (feature scope, supported and unsupported feature macros, how each external dependency is handled, architecture rules). Path mapping: `./HMOS/telephony_call_manager/` in AGENTS.md is `telephony_call_manager/` in this repository; `./liteOS/call_manager/` is `telephony_call_manager_mini/`, which does not exist yet.
- `openspec/config.yaml`: project context and per-artifact rules. `openspec instructions` returns them; apply them.
- `telephony_call_manager/`: the HMOS module (OpenHarmony v6.0 snapshot). It is read-only. Ground every statement in it.
- `test/`: the PC test harness, already described by `openspec/specs/pc-test-harness/spec.md`.
- `openspec/changes/setup-pc-test-env/`: an earlier, completed infrastructure change. Mentions of other changes inside it are historical; those changes do not exist.

## Deliverables

### 1. Baseline specs of the HMOS module

Write `openspec/specs/<capability-id>/spec.md` files that describe what the HMOS module does today, before any porting. Split the module into capabilities that follow its module groups, with kebab-case ids. Keep `pc-test-harness` as it is.

Each file uses this structure:

    # <capability name> Specification

    ## Purpose
    <what this capability covers; its source locations (directories, main files) and the build switches or macros that control it>

    ## Requirements

    ### Requirement: <name>
    The system SHALL ...

    #### Scenario: <name>
    - **WHEN** ...
    - **THEN** ...

Then run `openspec validate --specs --strict` and fix every error.

### 2. The migration change `{{change_name}}`

Create the change with the openspec-propose workflow (`.cursor/skills/openspec-propose/SKILL.md`): run `openspec new change "{{change_name}}"`, then for each artifact `openspec instructions <artifact> --change "{{change_name}}" --json`, until `proposal.md`, `design.md`, `specs/<capability-id>/spec.md` (deltas against the baseline specs from step 1) and `tasks.md` all exist.

The change describes how the liteOS port differs from the HMOS baseline: which capabilities are removed, kept or modified, and how, according to AGENTS.md.

## Hard rules

- Write only under `openspec/`. Do not create or modify source code, stubs, build files, tests, or `telephony_call_manager_mini/`. Do not modify `telephony_call_manager/` or `test/`.
- Stay inside this workspace. Do not read files outside it, and do not use git history.
- Do not ask questions. When something is ambiguous, choose the reading best supported by AGENTS.md and the HMOS source, and record it in a `## Open Questions` section at the end of `design.md`.
- Every file, function, class and macro name you cite must exist in `telephony_call_manager/`, unless it is new code that your design introduces (a stub, struct or todo label); say so where you introduce it.
- You are done only when `openspec validate --all --strict` passes and `openspec status --change "{{change_name}}"` shows every artifact as done.

## Readability (a human reviews this spec)

- Write in zh-CN. Keep the OpenSpec structural headings and keywords in English (`## Purpose`, `## Requirements`, `### Requirement:`, `#### Scenario:`, `## ADDED/MODIFIED/REMOVED Requirements`, SHALL/MUST, WHEN/THEN).
- `proposal.md`: the 裁剪范围 section is a table with one row per baseline capability (移除 / 保留 / 修改, with a one-line reason), followed by 非目标.
- `design.md` starts with a decision index, one line per decision. Each decision then has three parts: 决策 (what), 理由 (why, citing AGENTS.md or the source), 落点 (files, functions, macros, `callmanager.gni` entries).
- Use tables for enumerations (feature macros, external dependencies and their handling, removed files).
- Cite names instead of pasting source; no code block longer than 10 lines.
- One requirement describes one behaviour. Scenarios are concrete enough to become gtest cases in `test/`.

## Final answer

End with a short summary: the baseline capability ids, the change artifacts, the open questions, and the result of `openspec validate --all --strict`.
