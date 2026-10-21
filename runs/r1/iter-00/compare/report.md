# 学生 OpenSpec 评分报告：migrate-call-manager-to-liteos（对比参考）

## 总评

学生提案的整体质量明显高于"较弱模型"的一般预期：24 个基线能力覆盖面与参考对齐，命名接地率 95.4% 略高于参考，多数场景能直接落 gtest，`openspec validate --all --strict` 通过，0 ADDED/79 MODIFIED/61 REMOVED 的 delta 结构完整、裁剪范围表与 delta 基本一一对应；在骚扰来电、号码识别、ECC 拨号策略等能力上学生甚至写得比参考更细。主要失分集中在两处：一是 **VoIP 整通路被删除**而非按 AGENTS "暂不支持（待畅连）"保留+桩化——rubric 明确规定此类歧义以参考为准，这一高严重度缺口连带产生悬空转发链；二是**裁剪执行与自身声明不自洽**及**删除涟漪处理不闭环**（视频彩振链与 ESIM/BT 死分支保留、CellularCallConnection 去留自相矛盾、CALL_MANAGER_AUTO_START_OPTIMIZE 误判零引用）。此外学生缺少构建面（gni/bundle.json/declare_args）的基线能力与 delta 承载，且 CallManagerService 服务层入口行为（拨号特殊码、SendCallUiEvent、语音信箱计数清零）与 OOBE/免打扰拒接语义在基线和 delta 中双双缺失。外部依赖处置是学生最扎实的维度，与参考实质一致；锁与通知观察者"保留+todo"的读法与参考的"删除"读法均可辩护，未扣分。

## 维度得分

| 维度 | 得分 | 一句话理由 |
|---|---|---|
| baseline_coverage | 3 | 覆盖广且接地好（还发现了参考漏掉的 AUDIO_SUPPORT），但缺构建面能力，服务层入口行为与 OOBE/免打扰/一号双终端拒接语义成组缺失 |
| trim_scope | 3 | 整目录删除/宏分类/DSDS=0/单卡单帐号均正确，但 VoIP 整通路删除（高）+ 彩振链/ESIM 死分支保留 + 状态上报双路收敛无依据 |
| external_deps | 5 | AGENTS 各依赖类全覆盖并落到文件/函数级 todo 与 stub/ 桩清单，与参考实质一致；锁与通知文件保留属可辩护读法 |
| code_level_design | 3 | 删除清单/并发替换/gni 重排详尽贴源，但 VoIP/视频删除后留悬空转发与死链、CellularCallConnection 自相矛盾、AUTO_START_OPTIMIZE 误判零引用 |
| testability_grounding | 4 | 场景具体可落 gtest、门禁/gni 同步/具名用例齐备，唯 ECC 变更无任何专属 gtest（仅列复核标记） |
| readability_rules | 4 | 行文与规则格式合规、validate 通过，但成对重复场景撑到 374 个（参考 143），个别标题混英、段落过长 |

## 缺口明细（按维度分组，组内严重度降序）

### trim_scope

1. **[高｜student_wrong] VoIP 整通路被删除而非保留+桩化**
   - 参考：按 AGENTS "liteOS 暂不支持 VOIP，依赖后续跟 meetime 畅连"保留整条 VoIP 通路并桩化（`voip_call.cpp`、`voip_call_connection.cpp`、`voipCallObjectList_` 双轨、来电冲突处理、`HangUpVoipCall`、VoIP 统计事件），见 reference design D15。
   - 学生：design D10 与 delta 直接删除 VoIP 对象、连接类、双轨表、分流与统计事件，仅留枚举。rubric 明确规定 VoIP 歧义以参考为准，且 AGENTS 约束"不能因为无外部接口而丢弃功能"支持保留读法。学生错误。
   - 证据：AGENTS.md 功能范围 VoIP 条目；student design D10 / changes/specs/call-object-model REMOVED；源码 `services/call/src/voip_call.cpp`、`call_control_manager.cpp HangUpVoipCall`。

2. **[中｜student_wrong] 视频彩振（CRS）裁剪不自洽**
   - 参考：显式 REMOVED 彩振链，并在铃声播放需求中删除 CRS 分支与 `MuteNetWorkRingTone`/`NeedPlayVideoRing` 联动。
   - 学生：proposal 宣称视频彩振不迁移，但 audio-management delta 仍保留 Sound/`PlaySoundtone` 彩振播放链（仅打 [audio] todo、只删分布式 sink 条件），保留的链路与裁剪声明矛盾。参考正确。
   - 证据：student changes/specs/audio-management `Sound 播放`；源码 `audio_control_manager.cpp:172/268/492/834/1396`。

3. **[低｜student_wrong] 状态上报双路被收敛为单路**
   - 参考：保留 `UpdateCallState`（全局）+ `UpdateCallStateForSlotId`（带卡槽）双路，以 `TelephonyStateRegistryClient` 同名桩承载。
   - 学生：仅保留带 slotId 一路，"全局状态仅用于去重判定、不再单独上报"——AGENTS 要求逻辑与 HMOS 保持一致，收敛缺乏依据。参考正确。
   - 证据：`call_state_report_proxy.cpp:52-138`；student changes/specs/call-report:45-54。

4. **[低｜student_wrong] ESIM/BT 死分支保留与声明矛盾**
   - 参考：一号双终端判定链（`IsFromTheSameNumberAtTheSameTime`→`ModifyEsimType`）与 ESIM 相关分支随 ESIM 不支持显式处置。
   - 学生：proposal 称 ESIM 不迁移，但 delta 仍保留 `IsTwoCallBtCallAndESIM`/`IsTwoCallESIMCall`（BT/ESIM 均不支持）死条件及 `AutoAnswerSecondCall` 分支，而一号双终端判定链又整体缺席而非显式 REMOVED。参考更自洽。
   - 证据：student changes/specs/call-status-management:57-62 + proposal.md:11。

### baseline_coverage

5. **[中｜student_wrong] CallManagerService 服务层入口行为缺失**
   - 参考：`InputDialerSpecialCode`（`supportSpecialCode_` 匹配 + `COMMON_EVENT_SPECIAL_CODE` 广播 todo 占位）、`SendCallUiEvent` 服务级事件路由（含 `HandleDisplaySpecifiedCallPage`/`dealCeliaCallEvent`）、拨号成功后语音信箱计数清零（`GetVoiceMailNumber`/`SetVoiceMailCount`）均有基线需求与 delta 处置，并配 gtest。
   - 学生：基线与 delta 全目录检索均无这三组行为（call-report 中仅有 VoipConnection 的同名接口转发，属另一链路）。参考正确，学生遗漏。
   - 证据：`call_manager_service.cpp:329-331/1466-1483/1694+`；reference changes/specs/call-manager-service。

6. **[中｜student_wrong] 来电拒接语义（OOBE/免打扰）与一号双终端缺失**
   - 参考：`ShouldRejectIncomingCall` 的 OOBE 语义（`GetDevProvisioned`/`user_setup_complete` 改打桩参数表）、免打扰拒接（不调用、默认不拒接）、一号双终端判定均有专门需求、场景与 liteOS 落点。
   - 学生：仅在场景 WHEN 里点名 `ShouldRejectIncomingCall`，需求文本不描述其行为与处置。参考正确。
   - 证据：`call_status_manager.cpp:1801-1826/2019-2026`；reference specs/call-status-manager:27-30。

7. **[中｜student_wrong] 构建面无能力承载**
   - 参考：`build-and-feature-flags` 能力 6 需求基线 + 5 需求 delta，覆盖 callmanager.gni 结构、bundle.json components/inner_kits、declare_args、sa_profile、测试 target 重组（如 `NOT_SUPPORT_MULTICALL` 固化、宏注入集）。
   - 学生：无对应能力，构建决策只散落在 design D9/D13 与 tasks（无 spec 需求可校验、可回归）。参考正确。
   - 证据：reference specs/build-and-feature-flags；metrics 能力清单学生侧无对应项。

### code_level_design

8. **[中｜student_wrong] 删除功能后的涟漪处理不闭环**
   - 参考：删除/保留边界统一收口——Ott 转发链 REMOVED、VoIP 保留+桩化、等待音触发链在视频升级不可达时显式标注不可达。
   - 学生：telephony-interaction delta 仍保留 `HandleVoipEventReportInfo` 转发（消费方已删）、依赖视频升级的等待音链（`ReceiveUpdateCallMediaModeRequest`/`ShouldStopWaitingTone`），形成悬空转发与死链。参考正确。
   - 证据：student changes/specs/telephony-interaction vs 其 call-object-model/call-status-management REMOVED。

9. **[中｜student_wrong] CellularCallConnection 去留自相矛盾**
   - 参考：统一保留 `CellularCallConnection` 作为适配器，内部改走 `CellularCallClient::GetInstance()` 桩，客户端/服务端边界清晰。
   - 学生：call-object-model、call-setting delta 称调用点直连 `CellularCallClient` 且"CellularCallConnection MUST NOT 保留"，call-manager-service、telephony-interaction delta 又保留它（含 `Init`）；client-framework delta 还在 D2 删除 `call_manager_proxy.cpp` 后仍以 `CallManagerProxy::RegisterCallBack` 为主语。参考正确。
   - 证据：student changes/specs/call-object-model、call-setting vs call-manager-service、telephony-interaction；client-framework/spec.md:17。

10. **[低｜student_wrong] CALL_MANAGER_AUTO_START_OPTIMIZE 误判"基线未出现"**
    - 参考：正确归入"不支持宏→删除"，并点名 rk3568 分支与 `call_manager_proxy.*`。
    - 学生：D9 宏表称该宏 "v6.0 零引用、基线未出现"，实测 frameworks/native/BUILD.gn、call_manager_proxy.h/.cpp、zero_branch6_test、sa_profile 共 12 处引用。结果殊途同归（proxy 随 D2 删除），但事实判定错误，违反"宏定义按实际代码实现判断"。参考正确。
    - 证据：`frameworks/native/BUILD.gn:97`、`call_manager_proxy.h/.cpp`、`sa_profile/BUILD.gn:17`。

### testability_grounding

11. **[低｜student_wrong] ECC 变更无专属 gtest**
    - 参考：tasks 有 `DialEmergencyNumber_BypassesMulticallLimitButChecksSimState`、`SetMute_ForcedOffDuringEmergencyCall` 等成组 ECC 用例。
    - 学生：ECC 需求与 delta 质量不差（EccDialPolicy 场景齐全），tasks 9.2 也标了需人工复核，但没有任何 ECC 用例，紧急呼叫这类安全相关行为缺回归保护。参考正确。
    - 证据：student tasks.md 9.2 vs reference tasks 7.x。

### readability_rules

12. **[低｜student_wrong] 成对重复场景撑大 delta**
    - 参考：143 个 delta 场景，一场景一语义。
    - 学生：374 个场景中有大量近似重复对（如"断话触发组包不落库/蜂窝通话落库"、"超限清理/超限清理判定"、未接来电广播的双组包场景），语义密度被稀释。参考更好。
    - 证据：student changes/specs/call-state-observer、call-object-model；metrics 场景数 374 vs 143。

### 可辩护差异（不扣分，供参考）

- **[低｜student_defensible] 锁与通知文件保留 vs 删除**：学生保留 `std::mutex`、`ffrt::mutex` 空桩与通知观察者文件（调用点 todo）；参考全删锁、删通知文件留空操作骨架。两种读法分别对应 AGENTS "单线程不需要加锁"与"暂不调用 todo 占位、逻辑保留"的字面要求，学生读法同样有据。
- **[低｜student_defensible] 能力组织方式**：学生单列 js-ets-cj-binding、不新增 liteos-runtime 能力（运行时约定散布在各 delta Process/Outcome）；参考合并客户端框架、新增集中式 liteos-runtime。内容等价，组织选择可辩护。

## 需人工复核的参考侧问题（reference_questionable，不影响学生得分）

1. **参考宏表漏掉 `AUDIO_SUPPORT`**：`call_status_manager.cpp:880/1147` 存在真实 `#ifdef AUDIO_SUPPORT` 守卫，参考宏退役扫描只处理了 tone.cpp 的 `ABILITY_AUDIO_SUPPORT`；学生正确列出并按未定义清理（学生在此处更完整）。
2. **免打扰机制标注有误**：参考 call-status-manager delta 把免打扰拒接写成"免打扰 DataShare 查询调用点占位"，实际调用 `NotificationHelper::IsNeedSilentInDoNotDisturbMode`（通知框架而非 DataShare）；处置结论正确、机制标注错误，建议更正。
3. **通知/功耗文件删除尺度偏激进**：参考直接删除 `incoming_call_wake_up.cpp/.h`、`incoming_call_notification.cpp/.h` 等文件，但 AGENTS 将 ABILITY_POWER_SUPPORT 列为支持宏、通知/功耗按"暂不调用 todo 占位"处理，与"不支持宏 ABILITY_NOTIFICATION_SUPPORT 代码不迁移"存在规则张力；学生的"保留文件+todo"读法同样有据，建议人工定夺文件级保留与删除的统一尺度。