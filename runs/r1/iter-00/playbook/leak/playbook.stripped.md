# call_manager → liteOS 移植规划（OpenSpec）编写指南

## 一、目标与产出物

本任务只做规划，不写产品代码。交付两样：

1. `openspec/specs/<能力id>/spec.md`：HMOS 基线能力（"移植前现状"），按模块组划分，kebab-case id；`pc-test-harness` 原样保留。
2. `openspec/changes/migrate-call-manager-to-liteos/`：proposal.md、design.md、tasks.md、specs/ 下的 delta（对基线的 MODIFIED/REMOVED/ADDED）。

硬边界：只写 `openspec/`；不读工作区外文件。完成标准：`openspec validate --all --strict` 全绿、`openspec status --change "migrate-call-manager-to-liteos"` 四个工件全 done、`git status --porcelain` 只出现 openspec/ 路径。评审是逐行对照 AGENTS 与源码核实行为，宁可少而准，不可多而虚。

## 二、工作顺序

**Phase 0 规则装配。** 通读 task、AGENTS.md（功能范围 / 外部依赖处理 / 特性宏支持范围 / 架构要求）、`openspec/config.yaml`（含"关键技术事实"）。立刻把 AGENTS 功能范围逐条抄成一张**裁剪清单工作表**（全程维护，建议放草稿里，不产出）：每项记`功能名 | 措辞类别(见§5.1) | 相关符号清单(稍后用 rg 填) | 处置预设`。proposal 的裁剪范围表、delta 的 REMOVED、design 的删除文件清单全部从这张表派生——它是唯一事实源，防止各文件各说各话。

**Phase 1 模块地图。** 只读 4 份小文件，其余只看目录：

```bash
ls telephony_call_manager/ && find telephony_call_manager -maxdepth 2 -type d | sort
cat telephony_call_manager/callmanager.gni          # 构建+宏的地形图
cat telephony_call_manager/BUILD.gn                 # declare_args 的两个 feature
```

对照 AGENTS 的两条宏清单，逐宏执行 §5.2 的核验命令，把"正向命中/零引用"写进工作表。gni 覆盖不了的要补扫 frameworks、sa_profile（见 5.2）。

**Phase 2 能力划分（定稿后才许派工）。** 划分推导，不要发明新词：
- `services/` 的模块组一对一成为能力，目录名即能力名的依据；
- `frameworks/`（native 客户端与 js/napi 绑定，拆或不拆均可，定一种口径）与 `utils/` 各成能力；
- 运行时共享约定（进程内直调、stub/ 桩目录、todo 格式、恒返 0）集中在 design 决策表里，delta 需要引用但不能各写各的变体。

**Phase 3 baseline 派工与质检。** 按能力组打包派给子代理（见§三、§四.1），自己逐项跑质检清单后才算完成。

**Phase 4 变更预处理（先决策，后派工）。**
- 按 openspec-propose 工作流 `openspec new change`，对每个工件先 `openspec instructions <artifact> --change ... --json`；
- 先写**适配决策表**（进 design 草稿）：(a) 每个跨模块交互 wrapper 类（如与 cellular_call、core_service 交互的连接类、客户端代理层）一次性定去留与形态；(b) 每类外部依赖的桩名/落点/todo 标签；(c) §5.1 的逐条措辞判定。AGENTS 只规定"调用形态用 XxxClient::GetInstance().Xxx() 的桩"，并没规定要删 wrapper——保留 wrapper 作适配器、内部改调桩是改动最小的读法，且各文件必须同一种说法。

**Phase 5 delta 派工与质检。** 派工单逐字附上决策表与裁剪清单工作表相关行；写完后必须逐项跑 §4.3 质检（涟漪清扫、一致性、去重）。

**Phase 6 design.md → tasks.md**（§4.5、§4.6）。

**Phase 7 收尾自检**（§六）。

## 三、上下文预算

模块有几百个源文件，你的窗口装不下全部，预算原则：**主线程广而浅，子代理窄而深**。

- 主线程只读：规则文件、构建面小文件、自己产出的 spec、抽检用的 2~3 份源文件；任何"某名字是否存在"的存在性问题一律用 rg，不做全文阅读；反复出现的判定结论随手固化进 design 表格/工作表（外化记忆，防窗口挤压后丢细节）。
- 派给子代理：按能力组打包，每组 3~5 个能力与其源文件（含大文件精读：服务门面 cpp、状态机 cpp、音频控制 cpp、状态上报 cpp 等）。
- 每份派工单必须包含：
  1. 工作区根、只读边界（telephony_call_manager/ 禁改）、AGENTS 相关节选（功能范围、外部依赖处理、宏判定原则）；
  2. spec 结构模板与语言要求（zh-CN 行文、英文结构关键字、SHALL/WHEN/THEN）；
  3. 硬性要求：规定的核心入口类/文件里每个非平凡函数（派工单里列名），要么出现在某条 Requirement/Scenario，要么在返回摘要里给出"不纳入+理由"；
  4. 返回格式：能力id → Requirement 数 → 覆盖的关键函数清单 → 宏命中 → 标出需要你裁定的模糊点。**子代理无权静默决定模糊问题**；
  5. delta 派工另附：对应 baseline spec 全文、决策表原文、REMOVED 需"理由+流向"说明、MODIFIED 需带全部基线场景名。
- 收尾时保留名字反查：对 delta/design 里 20~30 个关键名 `rg` 基线是否命中（新代码除外）。

## 四、每个产出物前的检查清单

### 4.1 baseline spec（每个能力完成后）

- [ ] **函数覆盖**：核心类的成员函数清单逐一核对。命令示例：
- [ ] **宏落地**：Purpose 声明的宏必须是源码真实 `#ifdef` 的（单宏 rg 核对）。
- [ ] **场景设计为移植着想**：每条场景=一个分支；预计 liteOS 上整组消失的分支，尽量在基线就集中进独立 Requirement，这样 delta 可以整条 REMOVED 而不用逐场景改写。

### 4.2 裁剪范围表 + delta（写前）

- [ ] 每条 AGENTS 功能范围条目按 §5.1 判定后填一行（能力 | 移除/保留/修改 | 一行理由）；表一式一份，全部文件从它派生。
- [ ] delta 格式（以 `openspec instructions specs` 输出为准）：REMOVED 给理由与流向（去哪/恢复条件）；MODIFIED 是整块替换——**必须携带基线该需求全部场景名**（strict 校验对丢场景报 ERROR），改行为就用原场景名改写 WHEN/THEN，不要另起新名。

### 4.3 delta 质检（写后必须跑，这是多代理协作的收口）

- [ ] **涟漪清扫**：裁剪清单工作表里每个"不迁移"功能，取其符号清单（类名/函数名/常量）sweep 全部输出物：
  `rg -n "符号1|符号2|符号3" openspec/changes/migrate-call-manager-to-liteos/`
- [ ] **被删消费方的上游**：对每个被删能力反向清上游——rg 该能力的入口函数（如 VoIP 事件转发、视频升级请求处理），保留侧的调用点要显式处置（转 REMOVED、标注不可达，或走桩），不许留"悬空转发"。
- [ ] **一致性 grep**：对每个 wrapper/代理类、架构决策（如"客户端代理层保留与否""直调后回调怎么走"）grep 全部 delta+proposal+design，必须只有一种说法；两种说法=硬伤，按决策表统一。
- [ ] **场景去重与规模**：同一需求下仅差一个参数值/落点的两条场景合并为一条 WHEN；统计 `grep -c "^#### Scenario"`，MODIFIED 后的场景数应与基线该需求持平（外加少量新增），总量爆炸说明你在堆近似变体（这是被评审扣分项，且稀释语义密度）。

### 4.4 design.md（写前）

- [ ] **先证明后落笔**：每个宏单条 rg（§5.2），"零引用"结论二次复核后方可写进宏处置表；正向命中的逐处记录（文件:行级即可）。
- [ ] 依赖处置表覆盖 AGENTS 外部依赖处理清单每一行（todo 占位 / 客户端单例桩 / 同名桩 / 替代）+ stub/ 目录清单。
- [ ] 每个编辑决策三段：决策 / 理由（引 AGENTS 或源码）/ 落点（文件、函数、宏、gni 条目）。
- [ ] 构建面：gni 受影响条目、bundle.json features、declare_args、sa_profile、测试 target 一表列齐。

### 4.5 tasks.md（写前）

- [ ] 每个改动至少一条自解释 gtest 用例；删源文件任务伴随 gni 同步子任务；每任务组以 must-pass 门禁收尾。

### 4.6 proposal.md

- [ ] 裁剪范围表（每行=baseline 能力必现，包括 pc-test-harness）、非目标、复核标记与 design 决策索引一致；自定能力拆分 id 与 specs/ 目录一致。

## 五、易错点（每条给"怎么核实"）

### 5.1 AGENTS 措辞分级（裁剪判定第一依据）

- 「不支持……相关代码无需迁移」→ 整目录/整链删除 + delta REMOVED（如视频、会议、卫星、彩振、ESIM、防诈等）。
- 「暂不支持/暂不调用……依赖后续……适配」→ **保留代码与逻辑，仅把外部依赖调用点换成 todo/桩**。判据链：AGENTS「代码按功能实现，不能因为无外部接口而丢弃功能」+ config.yaml「代码按功能实现，不能因为没有外部接口而丢弃功能：暂不可用的外部接口只换掉调用（todo 占位），逻辑保留」+ 外部依赖处理节对 audio/database/broadcast 等全是"暂不调用、todo 占位"的同款句式。
- 「不支持宏」逐宏按真实 #ifdef 场点判定，不按名字直觉。

### 5.2 宏"零引用"最易翻车

- 逐宏单独 rg，**不要几十个宏拼一条大正则**（一个笔误=整串静默空匹配）：
  `rg -n -w "CALL_MANAGER_AUTO_START_OPTIMIZE" telephony_call_manager`
  必须覆盖构建文件（BUILD.gn/.gni）、frameworks/、sa_profile/；声明在 gni/declare_args 的宏不在源文件里 rg 得到。本仓`test/`下的命中单列（测试代码不等于业务引用，但也是命中）。
- 负结论必须换一种命令复验（去掉 `-w`、或 `git grep -n`）后才能写进设计表。
- rg 退出码 1=无匹配，不是命令失败。

### 5.3 深链与大文件

- 判定链函数（拒接/拦截/路由类）每环独立成场景；服务门面类散行为按 4.1 函数清单法过。

### 5.4 多代理一致性

- 决策表先行；没有决策表就派工，不同 delta 会就同一 wrapper 给出相反说法（一处"不得保留"、另一处"保留打桩"），这是结构性硬伤，一律以决策表+一致性 grep 收口。

## 六、收尾自检（提交前全部通过）

1. `openspec validate --specs --strict`（基线单独过）、`openspec validate "migrate-call-manager-to-liteos" --strict`（每写完一批 delta 就跑，早抓 MODIFIED 丢场景）。
2. `openspec validate --all --strict` 全绿；`openspec status --change "migrate-call-manager-to-liteos"` 四工件 done。
3. `git status --porcelain` 仅 openspec/ 路径。
4. 名字反查：delta+design 中关键名 rg 基线命中（或属设计新代码并已声明）。
5. 涟漪清扫终跑一遍（4.3），逐条对照裁剪清单工作表核销。
6. 终答按 task 要求：能力 id 清单、四工件、Open Questions、校验结果摘要。