# Smoke task: a minimal OpenSpec (tests the tooling only)

You are working alone and unattended in a snapshot of the `communication_mcu` repository. Nobody will answer questions. Keep this short; it only exercises the tooling. Aim to finish within about 10 minutes.

1. Read `AGENTS.md` and skim `telephony_call_manager/services/call_setting/`.
2. Write one baseline spec, `openspec/specs/call-setting/spec.md`, in zh-CN prose with the OpenSpec headings in English: a `## Purpose` section and a `## Requirements` section with 2 requirements, each with 1 scenario. Format:

       # Call Setting Specification

       ## Purpose
       ...

       ## Requirements

       ### Requirement: <name>
       The system SHALL ...

       #### Scenario: <name>
       - **WHEN** ...
       - **THEN** ...

3. Create the change `{{change_name}}` with `openspec new change "{{change_name}}"`. For each artifact, read `openspec instructions <artifact> --change "{{change_name}}" --json` and write a short version:
   - `proposal.md` (include `## 裁剪范围` and `## 非目标`, a few lines each);
   - `specs/call-setting/spec.md` with a `## MODIFIED Requirements` section containing one of the two requirements, adapted to liteOS according to AGENTS.md (copy the whole requirement block with its scenario, then change it);
   - `design.md` with a decision index and one decision (决策 / 理由 / 落点);
   - `tasks.md` with 2 checkbox tasks.
4. Run `openspec validate --all --strict` and fix errors until it passes.

Rules: write only under `openspec/`; stay inside this workspace; do not ask questions.

End with a one-paragraph summary.
