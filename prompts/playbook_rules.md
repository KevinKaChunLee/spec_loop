# Playbook rules (enforced by a script)

The playbook teaches how to find something out, not what the answer is.

## Allowed

- Process: the order of exploration (for example `callmanager.gni` first, then the `services/` tree, then the usage sites of each feature macro), what to grep instead of reading, how to split the work across subagents and what each must return, a checklist before each artifact, and self-verification commands.
- Lessons specific to call_manager, phrased as how to check something in the source or in AGENTS.md (for example: "decide each macro by its #ifdef sites, not by its name", "for every AGENTS.md item worded 暂不支持 / 暂不调用, look at its call sites and its external exits before choosing between deleting and stubbing").
- Directory paths (`telephony_call_manager/services`, `frameworks/native`), and any name that AGENTS.md, `openspec/config.yaml` or the task already contains.
- Decision values that AGENTS.md itself settles (for example "video calls are not migrated").

## Forbidden

- Stating a decision AGENTS.md leaves open, directly or through an instruction that leaves only one answer: whether a feature is removed or kept and stubbed, how a macro is handled, how a dependency's call sites are treated, whether locks are deleted. A script extracts every decision the playbook states and rejects the lines that give one of the reference's answers on an open question.
- Stating findings about what the HMOS code does: which branches a decision function has, what a call chain does, which behaviours a service class contains. Teach the search that would find them ("read every predicate down to its external-dependency leaves; each branch becomes a scenario") instead. Directory layout is fine. The same extraction flags such lines.
- Naming identifiers (functions, classes, variables, macros) or file names from the HMOS source that AGENTS.md, config.yaml and the task do not contain. Teach the search instead ("find the special-code handling in the service facade with rg") of naming what it finds. A script rejects every such line.
- Copying requirement or scenario text, or any other passage, from the reference spec. The playbook is rejected if it shares a passage of {{max_span}} or more characters with the reference (not counting text that also appears in AGENTS.md, config.yaml, the task or the HMOS source), or more than {{max_total}} shared characters in total.
- Listing the reference's capability ids. Naming more than {{cap_share_pct}}% of them causes rejection; describe how to derive the capability split instead.
- Per-requirement enumerations ("write requirement R1 ..., R2 ...").

Lines that still state an open decision or an HMOS finding, or name an HMOS symbol, after the rewrites are deleted automatically, so write rules that stand without them.

## Limits

- At most {{max_lines}} lines.
- Written in zh-CN.
