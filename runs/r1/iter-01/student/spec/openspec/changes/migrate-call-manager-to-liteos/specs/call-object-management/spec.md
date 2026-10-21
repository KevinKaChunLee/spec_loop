# Spec Delta

## REMOVED Requirements

### Requirement: 会议对象模型与 CS/IMS 会议联动

**Reason**: AGENTS「功能范围」明确 liteOS 不支持会议通话（"不支持：视频通话、会议通话……相关代码无需迁移"）；design D7 被删文件表列出 `conference_base.cpp`、`cs_conference.cpp`、`ims_conference.cpp`（`ott_conference.cpp` 随 OTT 一并删除）。
**Migration**: 删除源文件 `services/call/src/conference_base.cpp`、`cs_conference.cpp`、`ims_conference.cpp`（含对应头文件）并同步 `callmanager.gni` 的 `call_manager_sources`（design D7 表）；`cs_call.cpp`/`ims_call.cpp` 中 `CombineConference`/`LaunchConference`/`ExitConference`/`HoldConference`/`HandleCombineConferenceFailEvent`/`IsSupportConferenceable` 的会议联动分支随会议对象族移除；对象表谓词中的会议项（`IsConferenceCallExist`、载波计数的主叫去重分支）同步删除。恢复条件：手表平台支持会议通话后按基线重建会议对象族与 CS/IMS 联动分支。

### Requirement: OTT 通话与会议对象

**Reason**: AGENTS「功能范围」明确 liteOS 不支持 OTT 类型通话（暂无 OTT 依赖框架，且 OTT 属被裁剪清单）；design D7 被删文件表列出 `ott_call.cpp`、`ott_call_connection.cpp`、`ott_conference.cpp`。
**Migration**: 删除源文件 `services/call/src/ott_call.cpp`、`ott_call_connection.cpp`、`ott_conference.cpp`（含对应头文件）并同步 `callmanager.gni`（design D7 表）；`CallAbilityReportProxy::OttCallRequest` 的 OTT 上报分支与 `CallRequestProcess::OttDialProcess` 拨号分发分支随 OTT 对象消失而移除（见 call-control-management delta）。恢复条件：引入 OTT 通话框架后按基线重建对象与连接。

### Requirement: BluetoothCall 通话对象与蓝牙状态回调

**Reason**: AGENTS「功能范围」明确 liteOS 不支持 BLUETOOTH 类型通话，`ABILITY_BLUETOOTH_SUPPORT` 属不支持宏（AGENTS「特性宏支持范围」）；design D7 被删文件表列出 `bluetooth_call.cpp`、`bluetooth_call_state.cpp`（`bluetooth_call_connection.cpp` 随 telephony_interaction 删除）。
**Migration**: 删除源文件 `services/call/src/bluetooth_call.cpp`、`bluetooth_call_state.cpp`（含对应头文件）、`services/telephony_interaction/src/bluetooth_call_connection.cpp` 并同步 `callmanager.gni`（design D7 表）；`call_object_manager.{h,cpp}` 与 audio 路由中的蓝牙分支删除（design D7 宏处置行）。恢复条件：接入蓝牙 HFP 通话框架后重建对象、状态回调与连接。

### Requirement: SatelliteCall 通话对象

**Reason**: AGENTS「功能范围」明确 liteOS 不支持卫星通话；design D7 被删文件表列出 `satellite_call.cpp`（`satellite_call_control.cpp` 随 satellite_call 服务目录删除）。
**Migration**: 删除源文件 `services/call/src/satellite_call.cpp`、`services/satellite_call/src/satellite_call_control.cpp`（含对应头文件）并同步 `callmanager.gni`（design D7 表）；对象表谓词与检索中的 `TYPE_SATELLITE` 条件分支同步删除。恢复条件：支持卫星通话后按基线重建对象与多方/保持能力禁用面。

### Requirement: IMSCall 视频状态对象与 NetCallBase

**Reason**: AGENTS「功能范围」明确 liteOS 不支持视频通话，`ABILITY_CAMERA_SUPPORT` 恒关、`ABILITY_CAMERA_FRAMEWORK_SUPPORT` 属不支持宏（AGENTS「特性宏支持范围」）；design D7 被删文件表列出 `video_call_state.cpp`，`ims_call.cpp` 的 `ABILITY_CONFIG_SUPPORT`/`ABILIT_CONFIG_SUPPORT` 守卫块删除。
**Migration**: 删除源文件 `services/call/src/video_call_state.cpp` 与 `services/call/src/net_call_base.cpp`（含 `video_call_state.h`、`net_call_base.h`）并同步 `callmanager.gni`（design D7 表）——`net_call_base.cpp` 仅被 `OTTCall` 与 `VideoCallState` 派生（二者均已删除），成为无引用死代码，随本需求一并删除（design D7「services/call 删除」清单语义扩展，主线程已补记）；`ims_call.cpp` 中 `InitVideoCall`/`UpdateImsCallMode`/`SwitchVideoState`/`AssignVideoCallState` 及媒体模式收发分支移除（详见本 delta「IMSCall 通话对象」需求）。恢复条件：支持视频通话后重建 5 个视频状态子类、`NetCallBase` 派生体系与分发矩阵。

### Requirement: CallWiredHeadSet 有线耳机按键

**Reason**: AGENTS「功能范围」明确 liteOS 不支持有线耳机；design D7 被删文件表列出 `services/call/src/call_wired_headset.cpp` 与 `services/call/call_state_observer/src/wired_headset.cpp`。
**Migration**: 删除上述两个源文件（含对应头文件）并同步 `callmanager.gni`（design D7 表）；`CallObjectManager::AddOneCallObject`/`DeleteOneCallObject` 中的 `CallWiredHeadSet::Init()`/`DeInit()` 联动调用移除（见本 delta「全局通话对象表的生命周期管理」需求）。恢复条件：接入有线耳机按键框架后重建订阅与短按/长按处理。

### Requirement: NOT_SUPPORT_MULTICALL 一号双终端对象判定

**Reason**: AGENTS「功能范围」明确 liteOS 不支持 BLUETOOTH 类型通话与 eSIM，判定链的两种触发形态（蓝牙对象、eSIM 双呼）在 liteOS 均不存在，一号双终端判定链删除（design D9 Open Question 1 同口径）。
**Migration**: 删除 `services/call/include/call_object_manager.h` 与 `services/call/src/call_object_manager.cpp` 中 `IsTwoCallBtCallAndESIM`/`IsTwoCallBtCall`/`IsTwoCallESIMCall`/`IsOneNumberDualTerminal` 判定族；`NOT_SUPPORT_MULTICALL` 宏按 design D7 支持宏表保留 declare_args 与 #ifdef 骨架（默认值仍 false），骨架内引用上述判定族的分支删除、其余骨架逻辑（含 `CALL_MAX_COUNT` 计数口径与 `IsNewCallAllowedCreate` 的 callNum 判定）照抄；引用该族的调用点（如 `call_control_manager.cpp` 的 `HangUpFirstCall` 判定链，见 call-control-management delta 同名需求）随判定族同步删除。恢复条件：手表出现蓝牙通话或 eSIM 双终端形态后在保留骨架内重建判定族。

## MODIFIED Requirements

### Requirement: 全局通话对象表的生命周期管理
系统 SHALL 以 `CallObjectManager` 的静态 `callObjectPtrList_` 作为全部通话对象的唯一全局表（移植后为 `std::list<std::shared_ptr<CallBase>>`，`sptr` 替换为 `std::shared_ptr`，design D5；`listMutex_` 互斥锁按 design D6"锁不调用（删除；不设替代）"处置删除，单线程假设见 design D8），通过 `AddOneCallObject`/`DeleteOneCallObject` 维护，并在表从空到非空、非空到空时联动通话界面连接；liteOS 上表内仅存在 CS/IMS/VoIP 三类通话对象。

#### Scenario: 新增对象唯一性
- **WHEN** `AddOneCallObject` 收到的通话对象 callId 与表内已有对象重复
- **THEN** 返回 `CALL_ERR_PHONE_CALL_ALREADY_EXISTS`，不修改对象表（行为照抄基线）

#### Scenario: 首个通话拉起通话界面
- **WHEN** 对象表从 `NO_CALL_EXIST`（0）添加第一个通话对象，且 CallControlManager 报告的 VoIP 状态不是 `CALL_STATE_RINGING`，或该对象 `isEcc` 为真
- **THEN** 调用 `CallConnectAbility::ConnectAbility()` 拉起通话界面；ConnectAbility 语义经 `stub/` 打桩实现，调用点标 `// todo!!! [callUi] ref to call_connect_ability.cpp ConnectAbility`（design D6「拉起通话界面」行）

#### Scenario: 首个通话触发有线耳机注册
- **WHEN** 添加后对象表大小为 `ONE_CALL_EXIST`（1）
- **THEN** 因有线耳机不支持（AGENTS 功能范围），`CallWiredHeadSet::Init()` 注册分支已移除，不产生耳机按键订阅；队头通话为 `CALL_STATUS_DIALING` 时置 `isFirstDialCallAdded_ = true` 并 `cv_.notify_all()` 唤醒拨号失败等待方的机制照抄保留（由 `HandleDialFail` 消费）

#### Scenario: 删除至空表延迟断开界面
- **WHEN** `DeleteOneCallObject`（callId 重载或对象指针重载）使对象表变空，且 `CallControlManager::ShouldDisconnectService()` 为真
- **THEN** 经 `DelayedDisconnectCallConnectAbility` 以打桩 EventHandler 延迟 `DISCONNECT_DELAY_TIME` 2000000 微秒投递（`ffrt::submit_h` 替换为 `stub/eventhandler_stub`，design D8），延迟到期复查对象表仍为空后调用 `CallConnectAbility::DisconnectAbility()`（经 callUi 桩，调用点标 `// todo!!! [callUi] ref to call_connect_ability.cpp DisconnectAbility`）；基线中的 `CallWiredHeadSet::DeInit()` 调用已随有线耳机移除

#### Scenario: 删除不存在的 callId
- **WHEN** `DeleteOneCallObject(int32_t)` 未找到对应 callId 的对象
- **THEN** 仍返回 `TELEPHONY_SUCCESS`（对象表不变，行为照抄基线）

#### Scenario: 折叠屏监听联动（移植关注点）
- **WHEN** 添加或删除通话使对象表跨越 0/1 边界
- **THEN** 因折叠屏不支持（AGENTS 功能范围），`FoldStatusManager::IsSmallFoldDevice()` 判定与折叠监听注册/注销分支整体移除，对象表边界变化不再触发任何折叠监听联动

测试落点：`call_manager_zero_gtest/src/zero_branch2_test.cpp`（`tel_call_manager_zero2_gtest` 套件）新增 `Telephony_CallObjectManager_01x` 系用例（重复 callId 拒入、空表延迟断开经桩 EventHandler 驱动、删除不存在 callId 返回成功等），经 `test/` PC 门禁驱动。

### Requirement: callId 分配与多维度对象检索
系统 SHALL 由 `GetNewCallId` 从静态 `callId_`（初始 `CALL_START_ID` = 0）自增分配新 callId，并提供按 callId、号码、运行态、index、slotId、callType、VoIP callId 的检索函数族；`slotId` 参数保留供双卡扩展（AGENTS：只支持单卡，预留双卡扩展能力）。

#### Scenario: callId 单调自增
- **WHEN** 连续调用 `GetNewCallId`
- **THEN** 每次返回 `++callId_`，先后分配的 callId 严格递增且不复用（行为照抄基线）

#### Scenario: 按号码检索剥离后拨段
- **WHEN** 调用 `GetOneCallObject(std::string &phoneNumber)` 或 `IsCallExist(phoneNumber)` 检索
- **THEN** 对表内每个对象的 `GetAccountNumber()` 先经 `CallNumberUtils::RemovePostDialPhoneNumber` 剥离后拨号段再与目标号码比较；命中返回对象/true，全部未命中返回 nullptr/false（号码为空直接返回 nullptr/false）；`CallNumberUtils` 的 libphonenumber 依赖经 `stub/phonenumber_stub` 打桩（design D5），剥离逻辑照抄

#### Scenario: 按 index+slotId+callType 检索的蓝牙特例
- **WHEN** 调用 `GetOneCallObjectByIndexSlotIdAndCallType` 以任意 callType 检索
- **THEN** 因 BLUETOOTH 类型通话不支持（AGENTS），原 `TYPE_BLUETOOTH` 特例匹配分支（含 `GetPhoneOrWatchDial()` 等于 `PhoneOrWatchDial::WATCH_DIAL` 时豁免 slotId 相等条件）移除；统一按 callIndex 相等、slotId 相等且 callType 非 VoIP 的对象匹配

#### Scenario: 按运行态检索
- **WHEN** 调用 `GetOneCallObject(CallRunningState)` 或 `GetOneCarrierCallObject(CallRunningState)`
- **THEN** 均从表尾反向扫描取最近一个运行态匹配的对象；后者额外要求对象 `GetCallType() != TYPE_VOIP`（行为照抄基线）

#### Scenario: 按 VoIP 三元组检索
- **WHEN** 调用 `GetOneCallObjectByVoipCallId(voipCallId, bundleName, uid)`
- **THEN** 仅在 `TYPE_VOIP` 对象中按 `VoIPCall::GetVoipCallId`/`GetVoipBundleName`/`GetVoipUid` 三元组精确匹配（行为照抄基线）

测试落点：`call_manager_zero_gtest/src/zero_branch2_test.cpp` 新增 `Telephony_CallObjectManager_02x` 系用例（callId 自增、号码检索、index+slotId 匹配）。

### Requirement: VoIP 通话信息表
系统 SHALL 为 VoIP（畅连/meetime）维护独立于对象表的 `voipCallObjectList_`（`std::map<int32_t, CallAttributeInfo>`，callId→属性），由 `AddOneVoipCallObject`/`DeleteOneVoipCallObject`/`UpdateOneVoipCallObjectByCallId` 维护；VoIP 暂不支持真实对端，但信息表与冲突判定逻辑保留（AGENTS「暂不支持 VOIP……解决畅连通话和蜂窝通话冲突场景」；design D8 Risks：用例以桩注入对端事件驱动）。

#### Scenario: 增删改
- **WHEN** 向 map 添加已存在 callId / 删除或更新不存在 callId
- **THEN** 分别返回 `CALL_ERR_PHONE_CALL_ALREADY_EXISTS` / `TELEPHONY_ERROR`；新 callId 添加成功、已存在 callId 的状态更新返回 `TELEPHONY_SUCCESS`（行为照抄基线）

#### Scenario: 状态存在性查询
- **WHEN** 调用无参 `IsVoipCallExist`，或带状态的 `IsVoipCallExist(TelCallState, int32_t &callId)`
- **THEN** 前者返回 map 是否非空；后者在 map 中找到首个指定状态的条目时输出其 callId 并返回 true（行为照抄基线）

#### Scenario: 属性读取与清理
- **WHEN** 调用 `GetVoipCallInfo`/`GetActiveVoipCallInfo`/`ClearVoipList`
- **THEN** 前两者分别返回 map 首个条目与首个 `CALL_STATUS_ACTIVE` 条目（无命中返回零值结构）；`ClearVoipList` 清空 map 并调用 `CallControlManager::SetVirtualCall(true)`（行为照抄基线）

#### Scenario: 信息列表导出受 meetee 状态门控
- **WHEN** `GetVoipCallInfoList` 被 `GetCallInfoList`/`GetAllCallInfoList` 调用
- **THEN** 仅当 `CallControlManager::GetMeetimeCallState()` 为 `CALL_STATUS_INCOMING`、`CALL_STATUS_IDLE` 或 `CALL_STATUS_ALERTING` 时才把 map 条目追加进导出结果（行为照抄基线）

测试落点：`call_manager_zero_gtest/src/zero_branch2_test.cpp` 新增 `Telephony_CallObjectManager_03x` 系用例（map 增删改查、meetime 门控），VoIP 对端状态以桩注入驱动。

### Requirement: 新建通话约束判定
系统 SHALL 由 `HasNewCall` 与 `IsNewCallAllowedCreate` 判定当前是否允许发起新建通话；`IsNewCallAllowed` 判定与"新通话/CeliaCall"无关，保留（design D9 已证明）。

#### Scenario: 拨号中存在未完成新通话
- **WHEN** 对象表中存在 `GetCallType() != TYPE_VOIP` 且运行态为 `CALL_RUNNING_STATE_CREATE`/`CALL_RUNNING_STATE_CONNECTING`/`CALL_RUNNING_STATE_DIALING` 的对象
- **THEN** `HasNewCall` 返回 `CALL_ERR_CALL_COUNTS_EXCEED_LIMIT`；因卫星通话不支持（AGENTS），基线"或任意 `TYPE_SATELLITE` 对象"分支移除

#### Scenario: 已有振铃通话时禁止再建
- **WHEN** `IsNewCallAllowedCreate` 扫描到非 VoIP 的 CREATE/CONNECTING/DIALING/RINGING 通话
- **THEN** 输出 enabled=false 并返回 `TELEPHONY_ERR_SUCCESS`（行为照抄基线）

#### Scenario: 载波通话数量上限
- **WHEN** 扫描通过后统计载波通话数，每个载波通话对象计 1，统计值达到上限
- **THEN** enabled=false；上限默认为 2，定义 `NOT_SUPPORT_MULTICALL` 时为 1（宏按 design D7 支持宏表保留，declare_args 默认值仍 false）；因会议通话不支持，基线"会议成员按主叫去重（会议非 `TEL_CONFERENCE_IDLE` 且 callId 等于 `ImsConference::GetMainCall()` 计 1）"分支随会议对象族移除

测试落点：`call_manager_zero_gtest/src/zero_branch2_test.cpp` 新增 `Telephony_CallObjectManager_04x` 系用例（新建约束、上限判定含 `NOT_SUPPORT_MULTICALL` 两档）。

### Requirement: 通话存在性与计数谓词族
系统 SHALL 提供统一的存在性/计数/属性导出谓词：`HasCallExist`、`HasCellularCallExist`、`HasVoipCallExist`、`HasEmergencyCall`、`HasRingingCall`/`HasHoldCall`、`HasRingingMaximum`/`HasDialingMaximum`、`IsCallExist` 重载族、`HasActivedCallExist`、`GetCallNum`/`GetCallNumber`、`GetCarrierCallList`/`GetVoipCallList`/`GetCurrentCallNum`、`GetCallInfoList`/`GetAllCallInfoList`；因卫星/蓝牙/会议不支持，基线谓词族中的 `HasSatelliteCallExist`/`GetSatelliteCallList` 与 `IsConferenceCallExist` 移除。

#### Scenario: 蜂窝通话存在判定
- **WHEN** 调用 `HasCellularCallExist`
- **THEN** 仅当存在 callType 为 `TYPE_CS`/`TYPE_IMS` 且 `TelCallState` 既非 `CALL_STATUS_DISCONNECTED` 也非 `CALL_STATUS_DISCONNECTING` 的对象时返回 true；因卫星与蓝牙通话不支持，基线 `TYPE_SATELLITE`/`TYPE_BLUETOOTH` 条件移除

#### Scenario: 振铃/拨号数量上限判定
- **WHEN** 调用 `HasRingingMaximum`/`HasDialingMaximum`
- **THEN** 分别统计 `CALL_RUNNING_STATE_RINGING`/`CALL_RUNNING_STATE_ACTIVE` 数量（注释语义为拨号路数），达到 `RINGING_CALL_NUMBER_LEN`/`DIALING_CALL_NUMBER_LEN`（均=30）返回 true（行为照抄基线）

#### Scenario: 活动通话查找的 VoIP 兜底
- **WHEN** 调用 `HasActivedCallExist(callId, isIncludeCallServiceKitCall)` 且对象表中无匹配
- **THEN** 继续从 `voipCallObjectList_` 取活动 VoIP 条目，其 callId >= `VOIP_CALL_MINIMUM`（10000）时输出该 callId 并返回 true（行为照抄基线）

#### Scenario: 按状态统计与号码/列表导出
- **WHEN** 调用 `GetCallNum(callState, isIncludeVoipCall)`/`GetCallNumber`/`GetCarrierCallList`/`GetVoipCallList`
- **THEN** 统计/取号时按 isIncludeVoipCall 决定是否跳过 `TYPE_VOIP` 对象（照抄）；`GetCarrierCallList` 仅导出 CS/IMS 的 callId，基线含 SATELLITE/BLUETOOTH 的导出条件随卫星/蓝牙移除；`GetVoipCallList` 导出 VOIP callId 照抄

#### Scenario: 其余单项谓词
- **WHEN** 调用 `GetCallState(callId)`（未命中返回 `CALL_STATUS_IDLE`）、`GetCallNumByRunningState(callState)`、`GetVoipCallNum`、`UpdateOneCallObjectByCallId(callId, nextState)`（对匹配对象逐个 `SetTelCallState`）
- **THEN** 分别返回该通话的 `TelCallState`、指定运行态计数、对象表内 VOIP 计数、无返回值的就地状态更新（行为照抄基线）

#### Scenario: 按 slot 导出属性列表
- **WHEN** 调用 `GetCallInfoList(slotId, isIncludeVoipCall)`
- **THEN** 导出 accountId==slotId 且（isIncludeVoipCall 或 callType != TYPE_VOIP）的对象属性，并追加 `GetVoipCallInfoList` 结果；因 OTT 类型通话不支持，基线 `callType != TYPE_OTT` 条件随 OTT 对象消失而移除；`GetAllCallInfoList` 不限 slotId 导出全表（照抄）

测试落点：`call_manager_zero_gtest/src/zero_branch2_test.cpp` 新增 `Telephony_CallObjectManager_05x` 系用例（存在性/计数/列表导出，含卫星/蓝牙条件移除后的负向断言）。

### Requirement: 前台通话选择
系统 SHALL 提供 `GetForegroundCall`/`GetForegroundLiveCall`/`GetIncomingCall`/`GetForegroundLiveCallByCallId`/`GetAudioLiveCall` 的前台通话选择逻辑，供音频、UI 与控制路径取"当前通话"（纯状态扫描，无裁剪点，行为照抄基线）。

#### Scenario: 前台通话优先级
- **WHEN** 调用 `GetForegroundCall(isIncludeVoipCall)`
- **THEN** 顺序扫描：命中 `CALL_STATUS_WAITING`/`CALL_STATUS_INCOMING` 立即返回；`CALL_STATUS_ALERTING`/`CALL_STATUS_DIALING`/`CALL_STATUS_ACTIVE`/`CALL_STATUS_HOLDING` 则记录并继续（后者覆盖前者）；扫描结束返回最后记录者

#### Scenario: 前台活动通话
- **WHEN** 调用 `GetForegroundLiveCall(isIncludeVoipCall)`
- **THEN** 顺序扫描，命中 `CALL_STATUS_ACTIVE` 或 `CALL_STATUS_ALERTING`/`CALL_STATUS_DIALING` 立即返回该对象；`GetForegroundLiveCallByCallId` 在此基础上要求 callId 匹配

#### Scenario: 来电对象与音频活动通话回退链
- **WHEN** 调用 `GetIncomingCall(isIncludeVoipCall)` 或 `GetAudioLiveCall`
- **THEN** 前者返回首个 `CALL_STATUS_INCOMING`/`CALL_STATUS_WAITING` 对象；后者依次尝试 `GetForegroundLiveCall(false)` → `GetForegroundLiveCall(true)` → `GetIncomingCall(false)`，取第一个非空结果

测试落点：`call_manager_zero_gtest/src/zero_branch2_test.cpp` 新增 `Telephony_CallObjectManager_06x` 系用例（前台优先级矩阵、回退链）。

### Requirement: 来电铃声形态与免打扰静默判定
系统 SHALL 由 `HasIncomingCallVideoRingType`+`IsVideoRing` 与 `IsNeedSilentInDoNotDisturbMode` 判定当前来电的视频铃声形态与免打扰静默需求；因视频彩振（crsType==CRS_TYPE）与视频通话不支持（AGENTS 功能范围），基线 `HasIncomingCallCrsType` 彩振判定与 `HasVideoCall` 判定的可达分支移除。

#### Scenario: 视频彩振来电
- **WHEN** 来电场景需要判定铃声形态
- **THEN** 因视频彩振（crsType==CRS_TYPE）不支持（AGENTS），`HasIncomingCallCrsType` 判定及 `CRS_TYPE` 命中分支随彩振移除，liteOS 上不存在彩振形态来电，该判定不再提供

#### Scenario: 视频铃声来电
- **WHEN** 调用 `HasIncomingCallVideoRingType`，某非 VoIP 振铃对象的联系人 `personalNotificationRingtone` 以 `.mp4` 结尾或 `ringtonePath` 等于 `"system_video_ring"`
- **THEN** `IsVideoRing` 返回 true，该函数返回 true（判定逻辑照抄保留；铃声播放出口属 audio 能力，经 `[audio]` todo 桩化，design D6）

#### Scenario: 存在视频通话
- **WHEN** 调用 `HasVideoCall`
- **THEN** 因视频通话不支持（AGENTS），liteOS 对象表中不存在 `GetVideoStateType() == TYPE_VIDEO` 且非 `TYPE_VOIP` 的对象，判定恒返回 false；函数体照抄保留（行为保持默认，design D14），下游消费该判定的视频拨号约束已随视频裁剪（见 call-control-management delta）

#### Scenario: 免打扰静默
- **WHEN** 调用 `IsNeedSilentInDoNotDisturbMode`，前台通话（不含 VoIP）处于 `CALL_STATUS_INCOMING` 且其 `GetExtraParams()` 中 `"IsNeedSilentInDoNotDisturbMode"` 整型参数为 1
- **THEN** 返回 true；前台通话为空或非来电状态返回 false（行为照抄基线）

测试落点：`call_manager_zero_gtest/src/zero_branch2_test.cpp` 新增 `Telephony_CallObjectManager_07x` 系用例（IsVideoRing 字符串判定、免打扰静默、HasVideoCall 恒 false 断言）。

### Requirement: 拨号暂态共享与失败拨号处理
系统 SHALL 在 `CallObjectManager` 上保存跨模块共享的拨号暂态（`dialCallInfo_`、`needWaitHold_`、`isFirstDialCallAdded_`），并由 `GetDialCallInfo`/`DealFailDial` 提供读取与失败上报；`isFirstDialCallAdded_` 与 `DealFailDial` 失败补报为单卡活路径、照抄保留；`dialCallInfo_`/`needWaitHold_` 的置位、暂存与消费均属非零 DSDS 模式流程、不迁移（双卡扩展以参数面保留 `slotId` 为准，AGENTS），字段与读取接口作为骨架照抄。

#### Scenario: 读取暂存的拨号信息
- **WHEN** 调用 `GetDialCallInfo`
- **THEN** 返回静态 `dialCallInfo_`（暂态字段与读取接口作为骨架照抄）；因非零 DSDS 模式流程不迁移（AGENTS：`GetDsdsMode()` 恒 0），基线"等待保持"的置位点（`IsDialCallForDsda` 内 `needWaitHold_ = true`）、`HandleStartDial` 的 `needWaitHold_` 门控暂存段与 `CallStatusManager::HandleDialWhenHolding` 消费分支均删除，liteOS 上该暂态恒为零值、不可达

#### Scenario: 失败拨号补报断开
- **WHEN** 调用 `DealFailDial(call)`
- **THEN** 以该对象的 callType/slotId/videoState/号码构造 `CALL_STATUS_DISCONNECTED` 的 `CallDetailInfo` 并经 `ReportCallInfoHandler::UpdateCallReportInfo` 上报；号码长度超过 `kMaxNumberLen` 返回 `CALL_ERR_NUMBER_OUT_OF_RANGE`（行为照抄基线；上报队列语义经桩 EventHandler 保持，design D8）

测试落点：`call_manager_zero_gtest/src/zero_branch2_test.cpp` 新增 `Telephony_CallObjectManager_08x` 系用例（GetDialCallInfo/DealFailDial 超长号码错误码）。

### Requirement: CallBase 呼叫状态机
系统 SHALL 由 `CallBase::SetTelCallState` 驱动外部上报的 `TelCallState` 到本地 `CallRunningState`/时间戳字段的转移（`StateChangesToDialing` 等私有函数），重复状态返回 `CALL_ERR_NOT_NEW_STATE`；状态机整体照抄保留（会议对象族删除不影响对象本地 `conferenceState` 字段的转移语义，行为保持默认，design D14）。

#### Scenario: 状态重复上报
- **WHEN** 对象运行态已非 `CALL_RUNNING_STATE_CREATE` 且 `SetTelCallState` 收到与当前 `callState_` 相同的目标状态（`CALL_STATUS_DIALING` 例外）
- **THEN** 记录状态重复并返回 `CALL_ERR_NOT_NEW_STATE`（行为照抄基线）

#### Scenario: 拨号/回铃态
- **WHEN** 状态置为 `CALL_STATUS_DIALING` 或 `CALL_STATUS_ALERTING`
- **THEN** 运行态均转为 `CALL_RUNNING_STATE_DIALING`；ALERTING 时记录 `ringBeginTime_`，DIALING 时不记（行为照抄基线）

#### Scenario: 来电/等待态
- **WHEN** 状态置为 `CALL_STATUS_INCOMING` 或 `CALL_STATUS_WAITING`
- **THEN** 运行态转为 `CALL_RUNNING_STATE_RINGING` 并记录 `ringBeginTime_`（行为照抄基线）

#### Scenario: 激活态与计时
- **WHEN** 状态置为 `CALL_STATUS_ACTIVE` 且 `callBeginTime_` 尚为 0
- **THEN** 运行态转 `CALL_RUNNING_STATE_ACTIVE`，`callBeginTime_` 与 `ringEndTime_` 同取当前时间，`answerType_` 置 `CALL_ANSWER_ACTIVED`；`startTime_` 对 VoIP 通话取 gettimeofday 毫秒值、其他通话取 `callBeginTime_`（行为照抄基线）

#### Scenario: 保持/断开态与会议联动
- **WHEN** 状态置为 `CALL_STATUS_HOLDING`/`CALL_STATUS_DISCONNECTING`/`CALL_STATUS_DISCONNECTED`
- **THEN** 运行态分别转 HOLD/ENDING/ENDED；对象本地会议态字段的改写照抄保留：HOLDING 时从 `TEL_CONFERENCE_ACTIVE` 改写为 `TEL_CONFERENCE_DISCONNECTED`，DISCONNECTING 时 ACTIVE 改写为 DISCONNECTING，DISCONNECTED 时 DISCONNECTING/ACTIVE 改写为 DISCONNECTED 并记录 `callEndTime_`（`ringEndTime_` 为 0 时补记）；会议对象族删除后该字段在 liteOS 恒为 `TEL_CONFERENCE_IDLE`，改写逻辑不可达但照抄（design D14）

测试落点：`call_manager_zero_gtest/src/zero_branch2_test.cpp` 新增 `Telephony_CallBase_01x` 系用例（重复状态错误码、各态时间戳记录矩阵）。

### Requirement: CallBase 基础生命周期钩子与属性导出
系统 SHALL 提供 `DialCallBase`/`IncomingCallBase`/`AnswerCallBase`/`RejectCallBase` 四个基础钩子与 `GetCallAttributeBaseInfo` 属性导出；钩子在派生类流程前置调用，`HangUpVoipCall` VoIP 抢占链保留。

#### Scenario: 拨号前置与 VoIP 抢占
- **WHEN** 调用 `DialCallBase`
- **THEN** 运行态转 `CALL_RUNNING_STATE_CONNECTING`，并经打桩 EventHandler 异步执行 `HangUpVoipCall`（`ffrt::submit` 替换为 `stub/eventhandler_stub` 提交，design D8）：遍历全表 VoIP 对象，ACTIVE 的跳过、INCOMING 的 `RejectCall`、其余以 `ErrorReason::CELLULAR_CALL_EXISTS` 挂断（`HangUpVoipCall` 逻辑照抄保留）

#### Scenario: 来电前置
- **WHEN** 调用 `IncomingCallBase`
- **THEN** 运行态转 `CALL_RUNNING_STATE_RINGING`，返回 `TELEPHONY_SUCCESS`（行为照抄基线）

#### Scenario: 应答/拒接前置校验
- **WHEN** 调用 `AnswerCallBase` 时对象非 `CALL_RUNNING_STATE_RINGING`，或调用 `RejectCallBase`
- **THEN** 前者返回 `CALL_ERR_PHONE_ANSWER_IS_BUSY`；后者恒成功并把 `answerType_` 置 `CALL_ANSWER_REJECT`（行为照抄基线）

#### Scenario: 属性导出
- **WHEN** 调用 `GetCallAttributeBaseInfo(info)`
- **THEN** 填充 accountNumber/videoState/startTime/callType/callId/callState/conferenceState/各时间戳/callDirection/answerType/accountId/crsType/originalCallType/isEccContact/numberLocation/contactName/numberMarkInfo/blockReason/bundleName/detectDetails/phoneOrWatch（`CallAttributeInfo` 结构体字段按 design D5 平移，`PackParaInfo` 的 PacMap 出口改结构体出口），并把 `extraParams_` 序列化后解析出 name/namePresentation；因防诈 antifraud 不支持（AGENTS），基线 `antiFraudState` 解析及 `ANTIFRAUD_STATE_RISK`→`numberMarkInfo.markType` 改写为 `MARK_TYPE_FRAUD_RISK` 的分支移除；因新通话（CeliaCall）不支持，基线 `celiaCallType` 判定链移除、字段填充恒为默认值（design D9 新通话族处置）；号码超 `kMaxNumberLen` 时不填充直接返回（照抄）

测试落点：`call_manager_zero_gtest/src/zero_branch5_test.cpp` 新增 `Telephony_CallBase_02x` 系用例（钩子前置校验、属性导出字段矩阵、超长号码拒填）。

### Requirement: CarrierCall 载波通话公共行为
系统 SHALL 由 `CarrierCall`（`slotId_` 取 `info.accountId`，`index_` 取 `info.index`，`isEcc_` 取 `info.isEcc`，持有 `CellularCallConnection` 单例——移植后保留为适配器，内部改调 `CellularCallClient::GetInstance().Xxx()` 桩，design D4）承载 CS/IMS 共用的拨号、应答、拒接、挂断、保持、恢复、切换、静音、DTMF 与后拨转发；因会议/卫星/蓝牙通话不支持，基线会议族转发接口（`CarrierCombineConference`/`CarrierSeparateConference`/`CarrierKickOutFromConference`）移除，卫星/蓝牙对象不再派生自 `CarrierCall`。

#### Scenario: 控制指令经 CellularCallConnection 转发
- **WHEN** 调用 `CarrierAnswerCall`/`CarrierRejectCall`/`CarrierHangUpCall`/`CarrierHoldCall`/`CarrierUnHoldCall`/`CarrierSwitchCall`/`CarrierSetMute`/`StartDtmf`/`StopDtmf`/`PostDialProceed`
- **THEN** 均先 `PackCellularCallInfo`（callId/callType/videoState/index/slotId=accountId/号码，超长返回 `CALL_ERR_NUMBER_OUT_OF_RANGE`）再转发到 `cellularCallConnectionPtr_` 适配器、经 `CellularCallClient::GetInstance()` 桩下发（与 cellular_call 交换的 `CellularCallInfo` 结构体在桩面的兼容性需人工复核，design D4）；`CarrierHangUpCall` 按 `GetPolicyFlag()` 选择 `POLICY_FLAG_HANG_UP_ACTIVE`→`TYPE_HANG_UP_ACTIVE`、`POLICY_FLAG_HANG_UP_HOLD_WAIT`→`TYPE_HANG_UP_HOLD_WAIT`、否则 `TYPE_DEFAULT` 的挂断补充类型（照抄）；因会议不支持，基线会议族三项转发接口随会议移除

#### Scenario: 拨号流程失败回滚
- **WHEN** 调用 `CarrierDialingProcess` 且 `DialCallBase` 失败
- **THEN** 调用 `CarrierHangUpCall` 回滚后返回原错误码（行为照抄基线）

#### Scenario: 属性与紧急状态
- **WHEN** 调用 `GetCallAttributeCarrierInfo`/`GetEmergencyState`
- **THEN** 前者在 `GetCallAttributeBaseInfo` 基础上补充 isEcc/slotId/index；后者返回 `isEcc_`（行为照抄基线；ECC 判定链需人工复核（ECC），见 call-control-management delta）

#### Scenario: 紧急呼叫禁入会议
- **WHEN** 评估紧急呼叫的会议可入性
- **THEN** 因会议通话不支持（AGENTS），`CarrierCall::IsSupportConferenceable` 判定及紧急呼叫返回 `CALL_ERR_EMERGENCY_UNSUPPORT_CONFERENCEABLE` 的分支随会议族移除，liteOS 不再提供该判定

测试落点：`special_branch2_test.cpp`（`tel_call_manager_special2_test` 套件）扩展 `Telephony_CSCall`/`Telephony_CellularCallConnection` 系用例（转发矩阵、失败回滚、PackCellularCallInfo 超长错误码、桩出口断言）。

### Requirement: IMSCall 通话对象
系统 SHALL 由 `IMSCall` 在 `CarrierCall` 之上提供 RTT 发起/停止（API 链路保留，出口经适配器桩化）；因视频通话不支持（AGENTS），基线视频升级判定（`IsSupportVideoCall`）、`InitVideoCall` 分支与媒体模式协商/视频扩展指令族移除（design D7：`video_call_state.cpp` 删除、`ims_call.cpp` 的 `ABILITY_CONFIG_SUPPORT`/`ABILIT_CONFIG_SUPPORT` 守卫块删除）。

#### Scenario: RTT 发起与停止
- **WHEN** 调用 `StartRtt(msg)`/`StopRtt`
- **THEN** `PackCellularCallInfo` 后转发 `CellularCallConnection::StartRtt`/`StopRtt`（适配器内部经 `CellularCallClient::GetInstance().StartRtt/StopRtt` 桩）；按 AGENTS「RTT 业务不再使用文件节点的方式，相关调用暂不实现」，适配器出口标 `// todo!!! [rtt] ref to cellular_call_connection.cpp StartRtt/StopRtt`（design D6 RTT 行），API 链路保留；失败分别返回 `CALL_ERR_STARTRTT_FAILED`/`CALL_ERR_STOPRTT_FAILED`（照抄）

#### Scenario: 视频升级支持判定
- **WHEN** 评估 IMS 通话的视频升级能力
- **THEN** 因视频通话不支持（AGENTS），`IsSupportVideoCall` 判定（含 `CALL_STATUS_INCOMING`/紧急呼叫强制 false 分支与 config 读取分支）移除，liteOS 不提供视频升级判定

#### Scenario: 媒体模式协商收发
- **WHEN** 评估 IMS 媒体模式协商收发
- **THEN** 因视频通话不支持，`SendUpdateCallMediaModeRequest`/`SendUpdateCallMediaModeResponse`/`RecieveUpdateCallMediaModeRequest`/`ReceiveUpdateCallMediaModeResponse` 及 `videoCallState_` 分发分支随 `video_call_state.cpp` 删除而移除

#### Scenario: 视频扩展指令转发
- **WHEN** 评估 IMS 视频扩展指令
- **THEN** 因视频通话不支持，`ControlCamera`/`SetPreviewWindow`/`SetDisplayWindow`/`SetPausePicture`/`SetDeviceDirection`/`RequestCameraCapabilities`/`CancelCallUpgrade` 转发接口移除

测试落点：`special_branch2_test.cpp` 新增 `Telephony_IMSCall_01x` 系用例（StartRtt/StopRtt 错误码与 todo 桩出口断言）。

### Requirement: VoIPCall 通话对象
系统 SHALL 由 `VoIPCall`（继承 `CarrierCall`，构造时从 `info.voipCallInfo` 提取 voipCallId/userName/userProfile/abilityName/extensionId/voipBundleName/uid 等畅连字段）承载 VoIP 通话的对象行为，控制指令经 `VoipCallConnection` 出口——移植后保留为适配器，内部改调 `VoipCallClient::GetInstance().Xxx()` 桩（design D4 新增桩）；VoIP 真实对端暂不支持，对象逻辑保留（AGENTS「暂不支持 VOIP……解决畅连通话和蜂窝通话冲突场景」）。

#### Scenario: 拨号/保持/切换空实现
- **WHEN** 调用 `DialingProcess`/`HoldCall`/`UnHoldCall`/`SwitchCall`
- **THEN** 直接返回 `TELEPHONY_SUCCESS`，不产生任何外部调用（照抄）；因会议通话不支持，基线全部会议族空实现接口（`CombineConference` 等 14 个）随 CallBase 会议面移除

#### Scenario: 应答/拒接/挂断经 VoipCallConnection
- **WHEN** 调用 `AnswerCall`/`RejectCall`/`HangUpCall()`
- **THEN** `PackVoipCallInfo`（voipCallId/bundleName/uid）后转发 `VoipCallConnection::AnswerCall`/`RejectCall`/`HangUpCall`（适配器内经 `VoipCallClient::GetInstance()` 桩）；无参 `HangUpCall` 固定携带 `ErrorReason::USER_ANSWER_CELLULAR_FIRST`（照抄）

#### Scenario: 带原因挂断
- **WHEN** 调用 `HangUpCall(const ErrorReason &status)`（由 `CallBase::HangUpVoipCall` 抢占场景使用）
- **THEN** 携带传入原因转发 `VoipCallConnection::HangUpCall`（适配器内经桩，照抄）

#### Scenario: VoIP 静音
- **WHEN** 调用 `SetMute(mute, slotId)`
- **THEN** 以 "bundleName:uid:voipCallId" 拼接 voipCallId，按 mute 取 `CallAudioEvent::AUDIO_EVENT_MUTED`/`AUDIO_EVENT_UNMUTED` 经 `VoipCallConnection::SendCallUiEvent` 上报（适配器内经桩，照抄）

#### Scenario: 属性导出与麦克风权限更新
- **WHEN** 调用 `GetCallAttributeInfo` 或 `UpdateCallAttributeInfo`
- **THEN** 前者在载波属性之上回填 `voipCallInfo` 全部畅连字段；后者仅在 `hasMicPermission` 变化时更新本地值（行为照抄基线）

测试落点：`call_manager_zero_gtest/src/zero_branch5_test.cpp` 新增 `Telephony_VoIPCall_01x` 系用例（空实现返回值、`VoipCallClient` 桩出口断言、畅连字段回填），对端事件以桩注入驱动。