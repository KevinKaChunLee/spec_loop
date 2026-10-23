# 评分报告

总分 **75.0**（满分 100）。其中代码判定 49.8 分、模型判定 25.2 分（代码占比 66%）。

| 维度 | 权重 | 得分(0-5) | 组成 |
|---|---|---|---|
| agents_compliance | 10 | 5.0 | agents_compliance 1.00 |
| open_decisions | 15 | 3.33 | open_decisions 0.67 |
| baseline_coverage | 35 | 3.23 | module_coverage 1.00，behaviour_coverage 0.61，requirements_correctness 0.60 |
| code_level_design | 15 | 3.45 | build_coverage 0.90，design_quality 0.60 |
| testability_grounding | 15 | 4.21 | grounding_rate 0.95，task_rules 0.93，scenario_quality 0.60 |
| readability_rules | 10 | 4.68 | rule_checklist 0.99，readability 0.80 |

## 决策对照

settled = AGENTS.md 已定（参考取 AGENTS.md 的值、模块裁剪、无引用的宏），只检验是否遵守 AGENTS.md；open = AGENTS.md 未定或参考另作决定。

| 分组 / 类别 | 条目 | 代码一致 | 裁定计为一致 | 一致率 |
|---|---|---|---|---|
| open | 6 | 1 | 3 | 0.67 |
| settled | 101 | 101 | 0 | 1.00 |
| modules | 22 | 22 | 0 | 1.00 |
| features | 24 | 23 | 0 | 0.96 |
| macros | 34 | 31 | 2 | 0.97 |
| dependencies | 22 | 22 | 0 | 1.00 |
| architecture | 5 | 4 | 1 | 1.00 |

### 不一致项与裁定

| id | 分组 | 参考 | 学生 | 裁定 | 严重度 | 理由 |
|---|---|---|---|---|---|---|
| `feature/voip` | open | stub | remove | student_wrong | high | AGENTS.md 将 VOIP 单列为「暂不支持，依赖后续跟 meetime 畅连通话解决畅连与蜂窝通话冲突场景」，与不支持清单「相关代码无需迁移」刻意区分，且总约束明确「代码按功能实现，不能因为无外部接口而丢弃功能」。reference 保留 VoIPCall、voipCallObjectList_ 与 CarrierAndVoipConflictProcess/HangUpVoipCall/HandleVoipCallReportInfo 并仅桩化 VoipCallConnection，符合该口径；student 整通路删除（voip_call.cpp、voip_call_connection.cpp 及织入 CS/IMS 主流程的冲突分支），丢弃了 AGENTS.md 为畅连明确预留的冲突处理能力。 |
| `macro/NOT_SUPPORT_MULTICALL` | open | keep | unguard | reference_questionable | medium | AGENTS.md 将该宏列入「支持宏（无需显示定义宏）」，且说明 2 仅对 CONFIG_FACTORY_VERSION 要求「这个宏需要保留」，即其余支持宏应按已定义生效；student 固定 feature 为 true、按已定义处理符合此口径。reference 保留 declare_args 且默认 false 不定义，使 liteOS 默认构建放开通话上限 2 的多通话行为，与支持宏定位相悖，也与其自身 D12「支持宏恒定义」规则矛盾。 |
| `macro/ABILITY_POWER_SUPPORT` | open | remove | unguard | reference_questionable | high | AGENTS.md 将 ABILITY_POWER_SUPPORT 列为支持宏，外部依赖处理只要求功耗锁「调用点用 todo 注释占位」而非删功能，并有「不能因为无外部接口而丢弃功能」的总约束；student 宏生效保留 incoming_call_wake_up.cpp 代码路径、RunningLock 调用点 todo，符合口径。reference 将其并入 gni 不支持块删除并整文件不迁移 IncomingCallWakeup（来电亮屏需求被 REMOVED），与其对 ABILITY_SMS_SUPPORT 等支持宏「代码迁移+桩化」的同类处理不一致。 |
| `macro/ABILIT_CONFIG_SUPPORT` | open | remove | - | student_wrong | low | 源码在保留文件 cs_call.cpp:177、ims_call.cpp:282 存在拼写变体 ABILIT_CONFIG_SUPPORT 守卫的 carrier config 查询（IsSupportConferenceable）；AGENTS.md 规定「宏定义按实际代码实现来判断」，ABILITY_CONFIG_SUPPORT 为不支持宏，reference 将该变体一并删守卫（查询走默认值）是正确决策。student 全部规格对该变体只字未提，漏掉了这一处置点；因所守卫的是本就不支持的会议容量查询，实际影响很小。 |
| `architecture/locks` | open | remove | keep | student_defensible | low | AGENTS.md 只说单线程环境「不需要加锁」，并未要求删除既有锁；student 原样保留 std::mutex（单线程无争用、行为一致，契合「架构尽量与 HMOS 保持一致」）并将 ffrt::mutex 换空实现桩（符合 ffrt 打桩规则）。reference 删除全部锁成员与加锁调用是同一前提下的另一种合理处置，两种做法运行时行为一致，属可辩护的架构取舍。 |

## 代码检查

- 模块目录覆盖：1.00；未覆盖：无
- 行为覆盖：0.61（参考 baseline 引用的 1295 个 HMOS 名称中覆盖 61%；学生共引用 1399 个，折算系数 1.0）
- 引用接地率：0.954
- tasks 规则：0.93（{"gate": 1.0, "gtest": 0.778, "gni_sync": 1.0}）
- callmanager.gni / bundle.json 覆盖：0.90（design 点名 1.0，构建词覆盖 0.79）
- 规则清单：0.99
  - design_decision_structure = 0.933 14/15 decisions have 决策/理由/落点

## 软性评审（模型）

# 学生 OpenSpec 软评分报告（iter-00）

## 总体结论

学生的规划工件整体质量较高：24 个基线能力覆盖全部模块目录，需求与场景普遍具体（错误码、函数名、注入值、时序值），design 的删除清单、宏处置表、桩命名与 todo 标签表都能落到代码级，且多处比参考更细（如 `HasDialingMaximum` 实际统计 ACTIVE 的怪癖、`HandleEventResultReportInfo` 事件链、`ProximitySensor` 灭屏条件——后者学生写对了而参考写反了）。但相对参考存在三类需要扣分的差距：其一，基线在"大文件服务级行为"上有成簇遗漏（`call_manager_service.cpp` 的 `InputDialerSpecialCode`/`SendCallUiEvent` 路由/`SetCallPolicyInfo`/语音信箱计数清零、上行状态机的 OOBE 与 ESIM 分支、音频 CRS 视频彩振与语音↔视频切设备链）；其二，delta 场景存在系统性的近重复充数（同一 WHEN/THEN 换两个标题各写一遍，374 个场景对参考的 143 个），且 ECC 有场景却无 gtest 任务；其三，design 与 delta 之间存在自相矛盾（`call_manager_proxy.cpp` 已列入删除清单、delta 却仍以 `CallManagerProxy::RegisterCallBack` 为注册类；状态注册双路上报被收敛为单路却无 proposal/design 痕迹），CRS 裁剪在 proposal 宣称后未落到代码级。锁的处置（保留 `std::mutex`、`ffrt::mutex` 打空桩）与参考（全删）不同，但同样可由 AGENTS.md「不需要加锁」的表述支撑，不扣分。

## 分项得分

| 分项 | 得分 | 一句话理由 |
| --- | --- | --- |
| requirements_correctness | 3 | 基线广泛且准确，但漏掉三簇参考已覆盖的行为（服务层服务级行为、OOBE/ESIM 分支、音频 CRS/视频切设备链） |
| scenario_quality | 3 | 场景具体可测，但 delta 近重复场景系统性充数（约 11 对/文件），且 ECC 缺 gtest 任务 |
| design_quality | 3 | 设计落点很具体，但 CRS 裁剪未落地、工件自相矛盾两处、移除的连带链只处理一半 |
| readability | 4 | 结构、表格、决策索引与开放问题都好；扣在重复内容与个别 delta 标题与 THEN 相反 |

## 差距明细（按严重度排序）

### requirements_correctness（baseline_coverage）

1. **服务层服务级行为遗漏（medium，student_wrong）**
   - 参考：`call-manager-service` 基线覆盖 `InputDialerSpecialCode`（工程模式指令发广播）、`SendCallUiEvent` UI 事件路由、`SetCallPolicyInfo`（EDM uid 3057）、拨语音信箱后 `SetVoiceMailCount` 清零及 `GetProxyObjectPtr`。
   - 学生：`call-manager-service` 基线全篇未提这四类行为，delta 也无从裁剪。
   - 谁对：参考对。源码 `call_manager_service.cpp:331/1466/1694/1829` 均存在这些服务级行为，属于"大文件服务级行为必须在场"的评审要求。
   - 证据：`student/openspec/specs/call-manager-service/spec.md`；`telephony_call_manager/services/call_manager_service/src/call_manager_service.cpp`。

2. **OOBE/ESIM 分支链未展开（medium，student_wrong）**
   - 参考：逐分支展开 `ShouldRejectIncomingCall`（`device_provisioned`/`user_setup_complete`、`OOBEStatusObserver`）与一号双终端 `IsFromTheSameNumberAtTheSameTime → ModifyEsimType`。
   - 学生：`call-status-management` 只以 `IsRejectCall` 一句带过，两条判定链均未展开。
   - 谁对：参考对。均为 `call_status_manager.cpp` 中真实存在且影响来电放行的行为。
   - 证据：`reference/openspec/specs/call-status-manager/spec.md:27-56` vs `student/openspec/specs/call-status-management/spec.md:33-36`。

3. **音频 CRS/视频切设备链遗漏（medium，student_wrong）**
   - 参考：基线含 CRS 视频彩振（`dealCrsScene`/`MuteNetWorkRingTone`/`NeedPlayVideoRing`/`AdjustVolumesForCrs`）与 `VideoStateUpdated → CheckTypeAndSetAudioDevice` 语音↔视频切设备，并在 delta 中显式移除。
   - 学生：`audio-management` 基线对 CRS 与 `VideoStateUpdated` 零覆盖，delta 也未处理。
   - 谁对：参考对。源码 `audio_control_manager.cpp` 中这些分支真实存在，且 AGENTS.md 明确视频彩振不支持（裁剪需要先写基线再写移除）。
   - 证据：`student/openspec/specs/audio-management/spec.md`（rg "CRS|NeedPlayVideoRing|VideoStateUpdated" 零命中）。

### scenario_quality（testability_grounding）

4. **近重复场景充数（high，student_wrong）**
   - 参考：143 个场景，每个场景一个行为点。
   - 学生：374 个场景，delta 中同一 WHEN/THEN 以两个标题重复出现：仅 `call-state-observer` delta 就有约 11 对（"断话触发组包不落库/蜂窝通话落库"、"超限清理/超限清理判定"、"拦截名单查询未命中/拦截名单查询"、"主用户一次性查询判定/主用户一次性查询"、"来电持锁占位/来电持锁亮屏"等），`call-report` delta 亦有（"双路上报/单路直调上报"）。
   - 谁对：参考对。评审规则明确"不得用近重复场景充数"；重复对实施无增量信息。
   - 证据：`student/changes/migrate-call-manager-to-liteos/specs/call-state-observer/spec.md`、`.../call-report/spec.md`。

5. **ECC 缺 gtest 任务（medium，student_wrong）**
   - 参考：tasks 7.1 定义 `DialEmergencyNumber_BypassesMulticallLimitButChecksSimState`、`SetMute_ForcedOffDuringEmergencyCall` 等 ECC gtest。
   - 学生：call-control delta 有完整的 ECC 场景（清理既有通话、ECC 豁免 SIM/驻留检查），但 tasks.md 中 ECC 仅出现在 9.2 复核项，无任何紧急呼叫 gtest。
   - 谁对：参考对。评审规则要求安全相关行为（紧急呼叫、拒接）既有场景又有 gtest 任务；学生的场景无法被门禁锁定。
   - 证据：`student/.../tasks.md`（rg "ECC|Emergency" 仅命中 9.2）vs `reference/.../tasks.md` 7.1。

### design_quality（code_level_design）

6. **CRS 裁剪未落到代码级（medium，student_wrong）**
   - 参考：audio delta 逐条写明 CRS 分支与振动链路的 Migration（`MuteNetWorkRingTone` 停播链、`UNMUTE_SOUNDTONE_DELAY_TIME` 恢复音量、`NeedPlayVideoRing`/`StartVibrator` 等）。
   - 学生：proposal 宣称"视频彩振不迁移"，但 design 无对应决策，audio-management delta 亦无 CRS 移除条目——决策与代码动作之间断链。
   - 谁对：参考对。"design 如何把决策转成代码级动作"正是本分项评审内容。
   - 证据：`student/proposal.md`（What Changes）与 `student/design.md`（无 CRS 决策）；`reference/.../specs/audio-control-manager/spec.md:16-23,66-71`。

7. **工件自相矛盾两处（medium，student_wrong）**
   - (a) design D2/D3 把 `call_manager_proxy.cpp` 列入删除并称"删除全部 stub/proxy/death-recipient"，但 client-framework delta 的 MODIFIED 需求仍以 `CallManagerProxy::RegisterCallBack` 为注册类并描述其内部流程。
   - (b) call-report delta 把基线 `UpdateCallState` + `UpdateCallStateForSlotId` 双路上报收敛为"仅带 slotId 一路"，这是超出依赖替换的功能裁剪，proposal/design 均无此决策，也无 AGENTS.md 依据；参考经 `TelephonyStateRegistryClient` 桩保留双路。
   - 谁对：参考对（工件间口径一致；功能裁剪需有约束依据）。
   - 证据：`student/design.md` D2/D3 vs `student/.../specs/client-framework/spec.md`；`student/.../specs/call-report/spec.md`（系统状态注册上报）。

8. **移除连带链只处理一半（low，student_wrong）**
   - 参考：整链删除等待音触发（`ReceiveImsCallModeRequest/Response` 随视频升级一并移除）；`AddOneCallObject` 的 `FoldStatusManager` 折叠监听清理在 fold-display delta 点名。
   - 学生：保留等待音链但静默丢掉其第一步（`ReportCallInfoHandler::ReceiveImsCallModeRequest` 指向已删除的 IMSCall 视频状态机）；design D10 称被移除 callType 的上报在 `report_call_info_handler` 判不支持后丢弃，delta 却保留 `UpdateOttEventInfo` 分发；`FoldStatusManager::IsSmallFoldDevice() → RegisterFoldableListener()` 的清理点未列出。
   - 谁对：参考对。悬空调用/死分支属于"knock-on effects 已处理"的评审要求；学生仅部分处理。
   - 证据：`telephony_call_manager/services/telephony_interaction/src/call_status_callback.cpp:398-433`；`call_object_manager.cpp:96-98`；`student/.../specs/telephony-interaction/spec.md`。

### readability（readability_rules）

9. **重复内容与误导性标题（构成 readability 4 分的扣分项，low，student_wrong）**
   - 参考：场景一题一事，delta 标题与行为一致。
   - 学生：除上文的场景成对重复外，个别 delta 沿用基线标题但 THEN 已反转（"IMS 对象构造后初始化视频状态"实际断言 `InitVideoCall` 不被调用、"蜂窝通话落库"实际断言不落库），需求标题"六类通话对象按类型构造"在 delta 中实际只剩两类，个别 WHEN 从句内嵌裁剪理由（如"蓝牙链路已随 BLUETOOTH 类型通话不支持移除"），降低扫读效率。
   - 谁对：参考的表达更清晰；但学生整体结构（裁剪表、决策索引、开放问题）达标，故仅小扣。
   - 证据：`student/.../specs/call-object-model/spec.md`、`.../call-state-observer/spec.md`。

## 供人工复核的 reference_questionable 项

1. **`ProximitySensor` 灭屏条件写反（medium）**：参考基线称"`CallDestroyed` 且 `HasCallExist()` 为假时执行 `ShutDown`"，源码实为"仍有通话（`HasCallExist()` 为真）才灭屏"（`proximity_sensor.cpp:37-44`）。学生写对了，不扣分。
2. **通知/亮屏观察者过度裁剪（low）**：AGENTS.md 把通知（NotificationHelper）与功耗锁（ABILITY_POWER_SUPPORT）归为"暂不调用 → todo 占位"，功能范围未将来电全屏通知/未接提醒/来电亮屏列为不支持；参考却整体删除 `incoming_call_notification.cpp`、`missed_call_notification.cpp`、`incoming_call_wake_up.cpp` 及 `ABILITY_POWER_SUPPORT` gni 块。学生按 todo 占位保留，更贴合约束原文。该项属依赖处置判定（脚本评分），提请复核脚本裁定的口径。
