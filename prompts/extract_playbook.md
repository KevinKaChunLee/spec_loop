# Task: find the migration decisions a playbook states

You are an extractor in an evaluation loop. Work alone; nobody will answer questions.

`_inputs/playbook.md` is guidance for an agent that will plan a port of the HMOS call manager to liteOS. It may teach process, but it must not hand over answers. A script needs to know which of the fixed decisions in `_inputs/decision_vocab.json` the playbook answers for the reader, and which lines state findings about the HMOS code. You do not judge whether the playbook is right.

## What counts as stating a value

A line states a value for a key when it tells the reader what the decision is:
- directly: "VoIP 保留代码并桩化", "锁全部删除", "宏 X 按未定义清理";
- or through an instruction that leaves only one answer: "暂不支持的条目一律保留代码+桩化" followed by "VoIP 即此句式".

A line does not state a value when it only says how to find the answer ("先 rg VoIP 的调用点再定处置", "逐宏核对 #ifdef 场点"), or when it lists a key without saying what to do with it.

## Baseline behaviour facts

Separately, list the lines that assert what the HMOS code does: which branches a decision function has, what a call chain does, which behaviours a service class contains, which two paths coexist. For example "来电拒接判定至少含四个分支（ECC、开机向导未完成、免打扰、其余放行）" or "状态上报的全局与带卡槽两路并存". Such a line hands the reader a finding instead of teaching the search.

Not facts in this sense:
- process and how-to-check instructions ("把谓词读到外部依赖叶子为止", "用 rg 找门面函数清单");
- directory layout ("services/ 下每个子目录是一个模块组"), which `ls` reveals anyway;
- facts that `AGENTS.md`, `openspec/config.yaml` or `_inputs/task.md` already state (read those three to check).

Read nothing else: not the HMOS source, not other files.

## Output

Write `_outputs/decisions.json` with only the keys the playbook states, in the vocabulary's format, plus the facts:

    {
      "features": {"<key>": {"value": "<allowed value>",
                             "evidence": [{"file": "playbook.md", "quote": "..."}]}},
      "macros": {},
      "dependencies": {},
      "architecture": {},
      "baseline_facts": [{"quote": "...", "fact": "<what it asserts, zh-CN, one short phrase>"}]
    }

Give one quote per playbook line: a single line of at most 200 characters, copied verbatim (backticks and `*` may be left out, nothing else). A script maps every quote back to its line. Values must come from the vocabulary (an item's own `values` list, else its kind's). Check the file with `python3 -m json.tool _outputs/decisions.json` before finishing.
