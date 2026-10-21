# spec_loop

[English](README.md) | 简体中文

**教一个较弱的模型写 OpenSpec。** 由强模型 oracle 写出参考 OpenSpec，经人工审阅后冻结。较弱的 student 模型针对同一任务写出自己的 spec，全程看不到参考答案。随后 oracle 对两者的差距打分，并写出一份 playbook（执行手册），student 在下一次尝试时会拿到这份手册。循环往复，直到 student 的分数不再提升。

任务内容：把 HMOS 的 `telephony_call_manager` 模块（OpenHarmony v6.0）移植到 liteOS 手表平台，约束见 `communication_mcu/AGENTS.md`。本阶段只产出规划文档：HMOS 模块的 baseline 能力规格，以及一个迁移 change `migrate-call-manager-to-liteos`，不写任何产品代码。

所有 agent 都通过 Cursor CLI（`agent -p`）无界面运行，每个 agent 使用一份独立的、用完即弃的仓库快照。工具本身只依赖 Python 标准库。

---

## 架构

![spec_loop 架构](architecture.svg)

1. **共享输入。** `AGENTS.md`、`openspec/config.yaml`、HMOS 模块、OpenSpec skills 和 `prompts/task.md` 固定在 `base_sha`，对每个 agent 完全相同。`inputs.lock.json` 记录它们的哈希和 CLI 版本。
2. **隔离的 agent 运行。** 每一次 oracle、student、judge（评审）和 synthesizer（手册生成）调用都使用一份没有 git 历史的新快照，经 `runner.py` 运行，再由 `guards.py` 检查。其执行轨迹会被渲染成便于阅读的文本，并导出给 TrajViz。
3. **Oracle。** oracle 只写一次参考 spec。你审阅它，可以直接编辑，也可以让 oracle 修改，然后冻结。
4. **教学循环。** student 在看不到参考答案的情况下写 spec。judge 按固定评分标准把它与冻结的参考 spec 对比打分；synthesizer 根据差距和 student 的执行轨迹写出下一版 playbook，再由脚本检查其中是否抄了答案。
5. **产出与分析。** spec、分数、评审报告和 playbook 都存放在 `runs/<run>/`；执行轨迹可以在 TrajViz 中打开。

---

## 环境要求

- Linux 或 WSL，Python 3.10+（无需第三方包）
- Cursor CLI `agent`，且已登录（`agent status`）
- OpenSpec CLI 1.13+（`openspec`）
- `git` 和 `tar`
- 目标仓库（`config.json` 中的 `repo`）包含提交 `base_sha`，且 OpenSpec skills 位于 `<cursor_dir>/skills/openspec-*`
- 可选：带虚拟环境的 TrajViz 检出目录（`trajviz.bin`），用于生成分析视图和 HTML 报告

---

## 快速上手：冒烟测试

冒烟测试用一个极小的任务（只写一个能力）在约 10 分钟内跑通整条流水线，所有角色都使用 student 模型：

```bash
cd spec_loop
python3 loop.py smoke --run smoke1
```

它依次运行 oracle、冻结、student、judge 和 synthesizer，最后打印 PASS/FAIL 检查清单，内容包括：每次运行实际报告的模型、对话记录是否已复制、各项检查、冻结清单、合法的分数、被接受的 playbook，以及 playbook 是否已插入下一轮 student 的提示词。

---

## 运行循环

```bash
cd spec_loop
python3 loop.py prepare --run r1             # 锁定输入，解出 base 快照
python3 loop.py oracle  --run r1             # oracle 写参考 spec
python3 loop.py student --run r1 --iter 0    # 可选：并行启动基线 student
```

审阅 `runs/r1/oracle/spec/openspec/`。可以直接编辑文件，也可以让 oracle 修改，或两者结合。修改会恢复 oracle 原来的会话，并先把你的直接编辑同步进它的工作区：

```bash
python3 loop.py oracle --run r1 --revise "在 design.md 中说明 VoIP 决策并引用 AGENTS.md"
python3 loop.py oracle --run r1 --revise-file review-notes.md
```

满意后冻结 spec。冻结后它不再改变，之后每个阶段都会校验其哈希：

```bash
python3 loop.py freeze  --run r1
python3 loop.py iterate --run r1 --iters 3   # 反复执行 student -> judge -> synthesizer
python3 loop.py status  --run r1
```

`iterate` 会跳过已完成的阶段，因此中断后重新运行是安全的。如果分数连续 `plateau` 轮没有提升，它会提前停止；最好的 playbook 就是产生最高分的那一份。使用 `--samples M` 时，每一轮并行运行 M 个 student：该轮分数取它们的平均值，synthesizer 从中位数那个样本中学习。

各阶段耗时较长。第一次运行时 oracle 约 45 分钟，student 约 30 分钟，建议后台运行：

```bash
nohup python3 -u loop.py iterate --run r1 --iters 3 > runs/r1-iterate.log 2>&1 &
```

---

## 如何保证实验公平

- **同一个任务。** `prompts/task.md` 原样发给 oracle 和 student。student 的运行只在模型和附加在任务后面的 playbook 上有所不同。
- **锁定输入。** `prepare` 记录 `base_sha`、AGENTS.md、config.yaml、skills、每个提示词和评分标准的哈希，以及 CLI 版本。之后如果有提示词被改动，student、judge 和 synthesizer 阶段会发出警告。
- **盲测工作区。** 每个 agent 都在一份全新的 `git archive` 快照中工作，只有一个提交、没有历史；原仓库的历史和分支里保存着早期的 spec。oracle 的产出存放在 student 工作区之外。泄漏检查会扫描每一次工具调用（包括子 agent 的对话记录），以及工具输出中暴露的路径。只要运行触碰了 `spec_loop/`、其他阶段的工作区、原始工作区、其他项目的 agent 对话记录或早期的 GLM 导出，该次运行即判为失败。
- **冻结的参考答案。** `freeze` 写出 `MANIFEST.sha256` 并把 spec 设为只读；之后每个阶段都会重新校验。
- **只做规划。** 无代码检查读取工作区中的 `git status`。凡写到 `openspec/` 之外的内容，oracle 运行判为失败，student 运行则不计入评分。
- **评分与教学分开。** judge 在全新会话中按固定评分标准打分，加权总分由脚本计算。每个差距都会被标记为 `student_wrong`、`student_defensible` 或 `reference_questionable`；只有 `student_wrong` 的差距会被写进 playbook。
- **playbook 不得泄漏答案。** 如果 playbook 与参考 spec 有较长的相同段落（AGENTS.md、config.yaml、任务说明或 HMOS 源码中本来就有的文字除外）、列出了参考 spec 大部分的能力 id，或超过行数上限，脚本会拒绝它。synthesizer 最多有两次重写机会。
- **模型就是你指定的那个。** 每次运行都会把流中 `system/init` 事件报告的模型与 `models.<role>.expect` 比对，不一致即判为失败。

---

## 各阶段

| 阶段 | 模型（配置中的角色） | 读取 | 写入（位于 `runs/<run>/` 下） |
|---|---|---|---|
| `oracle` | `oracle` | task.md 和共享输入 | `oracle/spec/`、执行轨迹、检查结果、指标 |
| `freeze` | 无 | `oracle/spec/` | `oracle/MANIFEST.sha256` |
| `student --iter k` | `student` | task.md 和第 k-1 轮的 playbook | `iter-k/student[-sN]/` |
| `compare --iter k` | `judge` | 任务、评分标准、参考 spec、student 的 spec、`metrics.md`、上一轮的差距 id | `iter-k/compare[-sN]/score.json`、`report.md`；`scores.csv` 中的一行 |
| `synthesize --iter k` | `synthesizer` | 任务、参考 spec、student 的 spec、执行轨迹、统计、TrajViz 视图、评审报告、分数、上一版 playbook 和变更记录、历史分数、playbook 规则 | `iter-k/playbook/playbook.md`、`changelog.md`、`overlap_report.json` |

judge 和 synthesizer 也各自在独立快照中工作，输入放在 `_inputs/`，结果写到 `_outputs/`。judge 的 `score.json` 会做格式校验，不合格时在同一会话中给一次修正机会。总分为各维度"分数/5 × 权重"之和，归一化到 100 分。评审报告和 playbook 使用中文以与项目保持一致；提示词本身是英文。

---

## 运行目录

```
runs/<run>/
  inputs.lock.json  state.json  scores.csv
  base/                      # base_sha 快照，用于计算指标（仅本地）
  oracle/
    spec/openspec/           # 参考 spec；审阅时在这里编辑
    MANIFEST.sha256          # 冻结后生成
    trajectory.md  stats.json  guards.json  metrics.json  *.run.json  *.prompt.md
    trajectory.jsonl  transcripts/  trajviz/            # 仅本地
  iter-00/
    student/    spec/  trajectory.md  stats.json  guards.json  metrics.json ...
    compare/    score.json  report.md  metrics.md  metrics_diff.json ...
    playbook/   playbook.md  changelog.md  overlap_report.json ...
  iter-01/ ...
```

临时工作区保留在 `<workspace_root>/<run>/<stage>/` 以便查看，每当该阶段重建时会被清空。git 跟踪提示词、评分标准、配置、spec、分数、评审报告和 playbook；忽略原始 `*.jsonl`、stderr 日志、复制来的对话记录、`base/`、TrajViz 输出以及 `runs/smoke*/`。

---

## 执行轨迹分析与 TrajViz

每次 agent 运行都会产出：

- `trajectory.md`：每次工具调用一行（路径、命令、退出码、结果大小），外加思考摘录和 agent 的回复文字。开头的汇总给出 token 用量、耗时、读过的 HMOS 文件数、子 agent 数量和校验失败次数。
- `stats.json`：同样的汇总数据，JSON 格式，包含 CLI 报告的真实 token 用量。
- `trajviz/<label>.trajviz.json`：TrajViz 可以加载的导出文件（Cursor 格式）。把它上传到 TrajViz 仪表盘即可（在 TrajViz 检出目录中运行 `uv run agent-trajviz`）。设置了 `trajviz.bin` 时，还会同时写出分析视图（`trajviz/<label>.views/`）和独立报告（`trajviz/<label>.html`）。

TrajViz 自带的采集器（`agent-trajviz-collect cursor`）从 Cursor IDE 的 `state.vscdb` 读取工具结果，而 CLI 运行从不写入这个数据库。因此 `lib/trajviz_export.py` 改为从 CLI 的 stream-json 构建同样的 `cursor_composer` 格式；stream-json 包含完整的工具输出、退出码、工具耗时和推理内容。子 agent 会话会关联到启动它们的 Task 调用。

```bash
python3 loop.py trajviz --run r1                  # 所有阶段
python3 loop.py trajviz --run r1 --stage oracle
```

两点注意：
- 对于 Cursor 导出，TrajViz 的 token 数是估算值，因此它的 "Cache Efficiency" 健康检查没有意义。真实总量见 `stats.json` 和导出文件中的 `info.usageData`。
- 子 agent 的工具调用只有输入、没有输出，所以用到子 agent 时，TrajViz 统计的工具成功率会偏高。

---

## 配置（`config.json`）

| 键 | 含义 |
|---|---|
| `repo`、`base_sha` | 目标仓库，以及所有快照所基于的提交 |
| `cursor_dir` | 该目录下的 `skills/openspec-*` 和 `commands/opsx-*` 会被复制进每个工作区 |
| `workspace_root` | 临时工作区的存放位置；请放在 `repo` 和 `spec_loop` 之外 |
| `change_name`、`hmos_dir` | 两个 agent 都必须创建的 change id；HMOS 模块在仓库中的路径 |
| `preexisting_specs`、`preexisting_changes` | base 中已有、但不属于本任务的 spec 和 change（指标计算时忽略） |
| `models.{oracle,judge,synthesizer,student}` | `id` 传给 `agent --model`；`expect` 是 CLI 必须报告的模型名 |
| `smoke_model` | 冒烟运行中所有角色使用的模型 |
| `timeouts_min` | 每个角色的运行时间上限 |
| `iterations`、`plateau` | 默认轮数；连续多少轮无提升即停止 |
| `student_retries`、`judge_fix_retries`、`synth_fix_retries` | 无效 student 运行、无效 score.json、被拒 playbook 的重试次数 |
| `completion_nudges` | oracle 或 student 的一轮在交付物尚未写完或校验未通过时就结束，会话最多被恢复的次数 |
| `rubric_weights` | 各评分维度的权重；键名必须与 `rubric.md` 一致 |
| `playbook_limits` | 行数上限、n-gram 长度、抄袭段落限制、参考能力 id 的最大占比 |
| `trajviz` | `bin`（agent-trajviz 路径）、`html_report`、`output_chars`（每次工具输出的截断长度）、`synth_views`（提供给 synthesizer 的视图） |
| `render` | `trajectory.md` 的截断长度 |

如需修改任务、评分标准或 base 提交，请编辑文件后 `prepare` 一个新的 run，这样同一个 run 内的分数才具有可比性。

---

## 命令参考

| 命令 | 用途 |
|---|---|
| `prepare --run R [--smoke] [--force]` | 创建 run：锁定输入，解出 base 快照 |
| `oracle --run R` | 在全新工作区中运行 oracle |
| `oracle --run R --revise TEXT`（或 `--revise-file F`） | 带着审阅意见恢复 oracle 会话 |
| `freeze --run R [--force]` | 校验、计算哈希，并把参考 spec 设为只读 |
| `student --run R --iter K [--samples M] [--dry-run]` | 运行 student；`--dry-run` 只打印提示词 |
| `compare --run R --iter K` | 评审某一轮 student 的 spec |
| `synthesize --run R --iter K` | 为第 K+1 轮写 playbook |
| `iterate --run R [--iters N] [--start K] [--samples M]` | 反复执行 student、compare 和 synthesize |
| `reset --run R --from-iter K` | 丢弃第 K 轮及之后的轮次（产出、状态、分数行），之后 `iterate` 会重做 |
| `status --run R` | oracle 状态、每次 student 运行是否有效、分数 |
| `trajviz --run R [--stage S]` | （重新）为 TrajViz 导出运行记录 |
| `smoke --run R` | 端到端冒烟测试 |

---

## 常见问题

**启动时报 `Cannot use this model` 或 `HTTP 502`。** GLM 5.3 的 id（`glm-5p3-max`、`glm-5p3-high`）可以使用，但 `agent models` 不会列出它们，CLI 有时会在启动时拒绝。runner 会重试启动失败（最多 4 次，间隔 30 秒），并在运行中途断开时恢复同一会话继续（最多 3 次）。始终没有报告预期模型的运行判为失败。

**agent 还没写任何东西就结束了这一轮。** 无界面运行时，只要模型的回复里没有工具调用，这一轮就会结束，例如模型把计划或给子 agent 的指令写成了文字。对于 oracle 和 student 的运行，runner 会随即检查交付物（baseline 规格、change 的四个产出物、`openspec validate --strict`），并用一句简短的"尚未完成，仍缺少：……"恢复同一会话，最多 `completion_nudges` 次。次数记录在运行元数据和 `scores.csv` 的 `nudges` 中。仍未完成的 student 运行判为无效，并从头重试。

**1M / 200k 上下文的区分并未生效。** 对 GLM，CLI 拒绝 `[context=1m]` 这类方括号参数，所以 oracle 和 student 只在推理强度上有区别。每次运行都会记录 token 用量。

**GLM 5.3 的 Glob 工具调用失败。** CLI 的 Glob 工具不接受 GLM 发送的参数，agent 会改用 `ls` 和 `rg`。这对所有角色影响相同。

**执行轨迹中出现 `zsh: == not found`。** agent 的 shell 命令在 zsh 中运行，单独的 `echo ===` 会报错，无害。

**`warning: prompts changed since prepare`。** 某个提示词或评分标准与准备 run 时不同，之后的分数可能无法与之前比较。有意修改时请 prepare 一个新的 run。

**`the frozen oracle spec changed since freeze`。** 有东西修改了 `runs/<run>/oracle/spec/`。请恢复它（例如用 `git checkout`）；以清单为准。

**删除工作区。** judge 和 synthesizer 的工作区中有冻结 spec 的只读副本；先执行 `chmod -R u+w <dir>`，再 `rm -rf`。

---

## 目录结构

```
loop.py                 命令行入口与阶段编排
config.json             路径、模型、各项限制
rubric.md               judge 的评分维度
architecture.svg        上方的架构图
prompts/
  task.md               任务说明（oracle 和 student 共用）
  smoke_task.md         冒烟运行用的精简任务
  compare.md            judge 提示词
  synthesize.md         synthesizer 提示词
  playbook_rules.md     playbook 允许包含的内容（由脚本强制执行）
lib/
  workspace.py          无历史的仓库快照
  runner.py             agent -p 封装：流捕获、重试、恢复、模型校验、对话记录
  stream.py             下列模块共用的 stream-json / 对话记录读取函数
  guards.py             无代码检查、校验、泄漏检查、playbook 检查
  render_traj.py        trajectory.md 和 stats.json
  spec_metrics.py       确定性的 spec 指标，以及参考与 student 的差异
  trajviz_export.py     stream-json 转 TrajViz 导出、视图和 HTML 报告
  common.py             路径、run 状态、文件工具函数
```
