# Task: extract the migration decisions of an OpenSpec into a fixed table

You are an extractor in an evaluation loop. Work alone; nobody will answer questions. You do not judge whether a decision is right: you record what the spec decides, so that a script can compare two specs key by key.

## Inputs

- `_inputs/spec/openspec/`: the spec. Its decisions live in `changes/{{change_name}}/`: `proposal.md`, `design.md`, `tasks.md` and the delta specs `specs/*/spec.md`. Ignore `specs/pc-test-harness` and `changes/setup-pc-test-env`; they predate the task.
- `_inputs/decision_vocab.json`: the decision keys, grouped by kind (`features`, `macros`, `dependencies`, `architecture`). Each kind lists its allowed values and their meaning; an item may narrow them with its own `values` list. `agents_value` is background only: never copy it into the table.

Read nothing else. Do not open `AGENTS.md` or `telephony_call_manager/`: the table records what the spec says, not what the source or the constraints say.

## Method

1. Read `proposal.md` and `design.md` completely, then `tasks.md`. Use the delta specs to settle a key that those three leave unclear (for example a capability whose delta removes every requirement of a feature).
2. For every key in the vocabulary choose the one value that best describes what the spec decides for the liteOS port:
   - Decide from explicit statements: 裁剪范围 rows, decision text and tables, task steps, REMOVED/MODIFIED requirements.
   - A statement about the key itself beats a general rule. "VoIP 代码全保留" beats "不支持的功能代码删除".
   - When the spec contradicts itself, take design.md's decision on that topic, then proposal.md, then tasks.md, then the delta specs, and describe the contradiction in `note`.
   - Use `unstated` only when no file decides the key. A key that is mentioned but not decided is `unstated`.
3. Reading the values:
   - features: `remove` when the feature's code is not migrated (files, objects or branches deleted, requirements REMOVED); `stub` when code and logic are kept but the external side is stubbed or left as a todo, so the feature is inactive for now; `keep` when it is kept and works; `simplify` when it is kept with branches trimmed (only the single-SIM or single-account path remains).
   - macros: `remove` when the macro is treated as undefined and its guarded code or build block is deleted; `unguard` when the guarded code is migrated and enabled (guard removed, or always defined); `keep` when the macro stays a switch with both branches migrated; `no_code` when the spec says the macro has no reference in the v6.0 source and nothing needs doing. If the spec says both "no reference" and "delete its build block", record what it says to do: `remove`.
   - dependencies: `todo` when call sites stay with a `// todo!!!` placeholder; `stub` for a stub implementation (client singleton or same-name stub); `replace` for a replacement (smart pointer, log, struct, EventHandler); `remove` when the calling code, file or observer is deleted; `keep` when it is called unchanged. If one dependency is handled two ways (call sites kept with todo, but the files around them deleted), record the treatment of the call sites the port keeps, and describe the split in `note`.
   - architecture: each item's label says what `remove`/`keep` or `yes`/`no` mean for it.
4. Evidence: for every value other than `unstated`, give 1 to 3 quotes, each a single line of at most 200 characters, copied verbatim from the spec, with the file path relative to `_inputs/spec/openspec/` (for example `changes/{{change_name}}/design.md`). Copy the characters exactly; you may leave out backticks and `*`, nothing else. A script checks every quote and rejects the value if no quote is found.
5. `files` (optional, at most 5): HMOS paths relative to `telephony_call_manager/` that the spec names as where the decision lands.

## Output

Write `_outputs/decisions.json` and nothing else:

    {
      "features": {
        "<key>": {"value": "<allowed value>",
                  "evidence": [{"file": "changes/{{change_name}}/design.md", "quote": "..."}],
                  "files": ["services/..."],
                  "note": "optional"}
      },
      "macros": {},
      "dependencies": {},
      "architecture": {}
    }

Every key of the vocabulary appears under its kind, including the `unstated` ones (`{"value": "unstated"}`). Before finishing, check the file with `python3 -m json.tool _outputs/decisions.json`.
