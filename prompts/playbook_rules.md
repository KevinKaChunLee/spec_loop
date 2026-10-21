# Playbook rules (enforced by a script)

## Allowed

- Process: the order of exploration (for example `callmanager.gni` first, then the `services/` tree, then the usage sites of each feature macro), what to grep instead of reading, how to split the work across subagents and what each must return, a checklist before each artifact, and self-verification commands.
- Lessons specific to call_manager: where the student misjudged a feature, macro or dependency, phrased as how to check it in the source or in AGENTS.md (for example: "decide macro X by its #ifdef sites in A and B, not by its name").

## Forbidden

- Copying requirement or scenario text, or any other passage, from the reference spec. The playbook is rejected if it shares a passage of {{max_span}} or more characters with the reference (not counting text that also appears in AGENTS.md, config.yaml, the task or the HMOS source), or more than {{max_total}} shared characters in total.
- Listing the reference's capability ids. Naming more than {{cap_share_pct}}% of them causes rejection; describe how to derive the capability split instead.
- Per-requirement enumerations ("write requirement R1 ..., R2 ...").

## Limits

- At most {{max_lines}} lines.
- Written in zh-CN.
