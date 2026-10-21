# 学生 OpenSpec 评分报告（对比 reference）

## 总体结论

本次学生提交的 OpenSpec 质量明显高于"较弱模型"的一般预期：24 个基线能力与 reference 按内容一一对应（仅命名不同，如 call-control-management 对应 reference 的 call-control-manager、liteos-stub-layer 对应 liteos-runtime），基线共 275 条需求、732 个场景，比 reference（127/143）更细；每个能力的 Purpose 均落到源码目录与宏清单，我抽查了约 35 处引用（如 `HandleCallWaitingNumTwo/One/Zero` 等待矩阵、`TELEPHONY_VOIP_CALL_MANAGER_SYS_ABILITY_ID=65968`、unittest 组成员资格、零引用宏清单等），绝大多数在 v6.0 源码中属实，个别"未解析名"是定位脚本的误报。裁剪范围、外部依赖处置、桩体系与 reference 实质一致，且部分裁剪判断（如 `HoldOrDisconnectedCall` 矩阵仅由 DSDA5 分支可达故可删）有源码级证据，比 reference 更精确。发现的真实缺陷主要是：一套 delta 之间存在一处内部矛盾（AppStateObserver 一删一留）、少量捏造/错名符号（如 `CallControlManager::InitEvents` 实为 `CallStateObserve()`）、个别语义笔误。另有三处学生与 reference 的分歧（通知观察者去留、支持宏 gni 块处置、Celia/新通话映射）中，通知观察者一处支持学生的读法，属 reference 值得人工复核的点。两端 `openspec validate --all --strict` 均通过。

## 维度得分

| 维度 | 得分 | 一句话理由 |
|---|---|---|
| baseline_coverage | 5 | 24 能力与 reference 一一对应且更深更准，Purpose/宏清单/场景矩阵接地充分，仅零星拼写笔误，无实质缺口 |
| trim_scope | 4 | 裁剪裁决与 reference 实质一致且若干处更精确，但 call-report 与 call-control-management 两个 delta 对 AppStateObserver 注册点一删一留，内部矛盾（1 处中等缺陷扣 1 分） |
| external_deps | 5 | AGENTS 全部外部依赖类别覆盖，todo 标签体系统一并带默认失败语义，客户端单例桩齐全，与 reference 相当且更系统 |
| code_level_design | 4 | 决策索引/逐宏表/删除文件清单/任务依赖具体，但存在 `report_call_info_queue_` 等符号误写，且设计未拦截跨 delta 矛盾 |
| testability_grounding | 4 | 测试落点全部指向真实套件、每组任务带门禁，但少数捏造/错名符号（`InitEvents`、`GetSimState` 等）违反"引用名必须存在"硬规则 |
| readability_rules | 5 | 提案/设计/任务/delta 结构齐备（含任务要求的非目标小节，reference 反而缺失），严格校验通过 |

## 分维度差距明细（同一维度内按严重度降序）

### baseline_coverage

无实质差距。学生基线规模与精度均不低于 reference；`USER_IMPROLAN_SWITCH`（实为 `USER_IMPROPLAN_SWITCH`）、`CallManagerManager::Init` 等笔误已计入 testability/code_level_design 维度，不构成本维度扣分。

### trim_scope

1. **AppStateObserver 注册点自相矛盾（medium，student_wrong）**
   - reference 做法：在 call-report delta 中明确删除 `AppStateObserver` 与 `CallControlManager::AppStateObserver()` 注册点，同时保留 `SetVoIPCallState((int32_t)CallStateToApp::CALL_STATE_IDLE)` 与 `ClearVoipList()` 复位函数供桩/畅连后续触发（`_inputs/reference/.../specs/call-report/spec.md:39`）。
   - 学生做法：call-report delta 的 REMOVED「系统应用进程死亡复位 VoIP 状态」删除 `app_state_observer.cpp/.h` 并声明"注册调用点不迁移"；但同一变更 call-control-management delta 的 SetVoIPCallState 场景仍要求"经 `AppStateObserver` 向 `AppMgr` 注册应用状态观察者（照抄保留）"（`.../specs/call-control-management/spec.md:422`）。
   - 谁对：reference 对。源码中注册链在 `call_control_manager.cpp:1392-1410`（SetVoIPCallState 内 `appMgrProxy->RegisterApplicationStateObserver`），观察者类与注册点要么都删要么都留；学生两个 delta 互相矛盾，实现者无法同时满足。学生自己的 design（D2/D6）与 call-report delta 立场一致，说明这是 call-control-management delta 的疏漏。

2. **通知/来电唤醒观察者的处置分歧（medium，reference_questionable，不扣学生分）**
   - reference 做法：整体不迁移 `IncomingCallWakeup`、`IncomingCallNotification`、`MissedCallNotification`（连源文件删除，见 `_inputs/reference/.../tasks.md:17`；call-control-manager/spec.md:6），理由是"无 power/AC 心跳通路"。
   - 学生做法：保留三个观察者类与注册形态，仅对 NotificationHelper/功耗锁等外部调用点打 `todo!!! [notification]/[powerLock]` 桩，由来电/未接/通知各 delta 承载。
   - 谁对：学生读法更有依据。AGENTS.md 将"通知 NotificationHelper"与"功耗锁 ABILITY_POWER_SUPPORT"列入"暂不调用、todo 占位"类而非"不迁移"类，并要求"不能因为无外部接口而丢弃功能"；HMOS 的 `callmanager.gni:52-54` 无条件编译这些文件，宏只守卫极少数行。此点属 reference 偏激进，留给人工复核。

3. **Celia/新通话映射分歧（low，student_defensible，不扣分）**
   - reference 做法：保留 `isCeliaCall`/`dealCeliaCallEvent`/`HandleCeliaAutoAnswerCall` 路由（distributed-call delta 注明"celia 事件保留"）。
   - 学生做法：按 AGENTS"不支持新通话"删除 Celia 事件路由，并在 design 中记录理由。
   - 谁对：两可。源码中 Celia 符号实存（`distributed_communication_manager.cpp`），但"Celia=新通话"的映射无直接证据（Celia 更可能是小艺语音场景）；两端的解读都有依据，学生另有 `WearStatusObserver` 等无关裁剪处理正确的旁证，不扣分。

### external_deps

- **SpamCall IPC 三件套空壳保留（low，student_defensible，不扣分）**
  - reference：删除 `SpamCallProxy`/`SpamCallStub` IPC 类（spam-call delta REMOVED「检测命令 IPC」），检测请求调用点 todo 占位。
  - 学生：保留 `spam_call_connection/proxy/stub` 为"可编译最小形"，用 todo 桩驱动回环语义做测试，并在 Open Question 6 登记待复核。
  - 谁对：两可。AGENTS 只要求骚扰接口暂不调用、不用 dlopen，未规定 IPC 传输类的去留；同类差异还有 `voip_call_manager_proxy.cpp` 保留桩化（学生）vs 删除（reference）。学生的保守保留符合其统一的"逻辑保留"原则，不扣分。

### code_level_design

1. **`report_call_info_queue_` 成员名误写（low，student_wrong）**
   - reference：正确描述落地为全局 `reportCallInfoQueue`（`report_call_info_handler.cpp:31`，`ffrt::queue`），替换为打桩 Executor。
   - 学生：把该对象当成员/写作 `report_call_info_queue_`，在 design 决策 8 与 call-report、liteos-stub-layer delta 中以此符号描述 EventHandler 替换形态。功能语义不受影响，但符号级落点错误。
   - 谁对：reference 对，源码可证。属轻微命名接地缺陷。

2. **支持宏 gni 部件块处置差异（low，student_defensible，不扣分）**
   - reference：支持宏（ABILITY_SMS_SUPPORT 等）改为构建恒定义，去掉 `global_parts_info` 条件。
   - 学生：按基线形态照抄保留条件块，依赖测试兼容层/部件信息注入宏。
   - 谁对：两可。AGENTS"支持宏（无需显式定义宏）"允许两种读法；两者在 PC 门禁层均注入手表宏集且 must-pass 语义一致。学生对 bool 型/数值型宏赋值语义的区分处理合理，不扣分。

### testability_grounding

- **捏造/错名符号（medium，student_wrong）**
  - reference：符号引用全部核实为真实存在（如 `CallStateObserve()`、`reportCallInfoQueue`、`USER_IMPROPLAN_SWITCH`）。
  - 学生：出现约 5-6 处违反"引用名必须在源码中存在"硬规则的符号——`CallControlManager::InitEvents`（真实为 `CallStateObserve()`，且位于 delta 场景 WHEN 内，会误导测试编写）、`GetSimState`（树中不存在）、`CallManagerManager::Init()`（拼写）、`USER_IMPROLAN_SWITCH`（实为 `USER_IMPROPLAN_SWITCH`）、`PublishCallManagerService`（实为 OnStart/AddSystemAbility 链路）。
  - 谁对：reference 对。考虑到学生已核实引用达 3405 个、这些仅占极小比例且多为叙述性笔误，扣 1 分即可。

### readability_rules

无学生缺陷。学生的 proposal/design/tasks/delta 结构完整满足任务要求（含非目标小节、评审关注点标记、Open Questions），严格校验通过；反而 reference 存在结构缺失（见下）。

## reference_questionable 清单（供人工复核）

1. **通知/未接/来电唤醒观察者整体删除**：`IncomingCallWakeup`/`IncomingCallNotification`/`MissedCallNotification` 连源文件删除（reference tasks 2.4/2.5），与 AGENTS"通知/功耗锁接口为 todo 占位类"和"不能因无外部接口丢弃功能"的约束存在张力；学生保留类、桩化外部调用点的读法更贴合 AGENTS。
2. **Celia 事件路由保留**：若"Celia=新通话"（AGENTS 不支持）成立，reference 的保留反而漏裁；若 Celia 属小艺语音场景，则学生误删。建议人工根据产品定义裁决。
3. **proposal.md 缺少任务规定的"非目标"小节**：任务 Readability 节明确要求裁剪范围表后接非目标，reference 提案没有该小节（学生提案有）。属文档规范缺陷，建议补充。

## 附：客观指标（脚本产出）

两份 spec 的基线能力数均为 24；学生基线 275 需求/732 场景，reference 127/143；学生 delta ADDED/MODIFIED/REMOVED 为 5/161/104，reference 为 7/63/59；`openspec validate --all --strict` 双方均通过；双方都只写入 `openspec/`。学生引用名未在 HMOS 树中命中的比例略高，但其中大多数是新桩文件名或定位脚本误报（本次抽查已逐一甄别）。