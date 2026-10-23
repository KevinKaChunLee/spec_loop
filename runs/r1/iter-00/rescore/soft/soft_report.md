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
