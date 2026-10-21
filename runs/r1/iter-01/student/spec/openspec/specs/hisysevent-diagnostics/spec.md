# Hisysevent Diagnostics Specification

## Purpose
描述 HMOS `telephony_call_manager` 的维测面（`services/hisysevent/src/{call_manager_dump_helper,call_manager_hisysevent}.cpp` + `include/` 两头文件，及 `frameworks/native/src/native_call_manager_hisysevent.cpp`）：`CallManagerDumpHelper` 承接 `CallManagerService::Dump` 的 hidumper 输出（服务自描述信息）；`CallManagerHisysevent`（继承 `TelephonyHiSysEvent`）集中封装行为事件（CALL_STATE/INCOMING_CALL/CALL_INCOMING_NUM_IDENTITY）、故障事件（CALL_DIAL_FAILED/CALL_INCOMING_FAILED/CALL_ANSWER_FAILED/CALL_HANGUP_FAILED）与 VOIP 统计事件的写入，并提供拨号/来电/应答的时延超时判定；`NativeCallManagerHisysevent::WriteVoipCallEvent` 为 VoIP NDK 侧事件写入口。写入门面（`call_manager_service.cpp`）与各管理者的调用点不展开，见对应能力。本规格为移植前现状基线，不涉及裁剪决策。本能力不涉及条件编译特性宏（基类 `TelephonyHiSysEvent` 的宏不属于本仓）。

## Requirements

### Requirement: hidumper 服务信息打印
系统 SHALL 由 `CallManagerService::Dump(fd, args)`（`call_manager_service.cpp`）校验 fd（<0 返回 `TELEPHONY_ERR_ARGUMENT_INVALID`）后委托栈上构造的 `CallManagerDumpHelper::Dump(argsInStr, result)`，成功则 `dprintf` 到 fd（失败返回 `CALL_ERR_SERVICE_DUMP_FAILED`）。`CallManagerDumpHelper::Dump` SHALL 先 `ShowHelp`（固定输出 -call_manager_info、-input_simulate/-output_simulate、-show_log_level/-set_log_level、-perf_dump 的 Usage 文本）再 `ShowCallManagerInfo`，恒返回 true。`ShowCallManagerInfo` SHALL 依次输出：`CurrentTime`（经 `CallManagerService::GetBindTime()`，该函数每次调用刷新为当前毫秒时间戳）、`SpendTime`（`GetStartServiceSpent()`，OnStart 耗时毫秒）、`ServiceRunningState`、按 `SIM_SLOT_COUNT` 循环经 `WhetherHasSimCard(i)`（`CoreServiceClient::HasSimCard`）逐槽输出 "SlotId = i"（仅有卡的槽）、`CallState`（`GetCallState()`）、`RingingCallState`（`IsRinging(enabled)` 出参）、`HasCall`。不解析 args、不区分子命令。

#### Scenario: 非法 fd
- **WHEN** hidumper 以 fd<0 调用 `CallManagerService::Dump`
- **THEN** 返回 `TELEPHONY_ERR_ARGUMENT_INVALID`

#### Scenario: 标准信息转储
- **WHEN** 以任意 args 调用 `Dump`
- **THEN** 输出 Usage 文本与 Ohos call_manager service 段（含时间/耗时/运行态/占卡槽列表/CallState/RingingCallState/HasCall），返回 `TELEPHONY_SUCCESS`

#### Scenario: 无卡槽位不打印
- **WHEN** slotId=1 槽位无 SIM 卡
- **THEN** 转储文本不含 "SlotId = 1" 行

### Requirement: 通话状态与来电行为事件
系统 SHALL 由 `CallManagerHisysevent` 写行为事件：`WriteCallStateBehaviorEvent(slotId, state, index)` 写事件 `CALL_STATE`，键 `SLOT_ID/STATE/INDEX_ID`（调用点 `services/telephony_interaction/src/call_status_callback.cpp`，即蜂窝通话状态回报到达时）；`WriteIncomingCallBehaviorEvent(slotId, callType, callMode)` 写事件 `INCOMING_CALL`，键 `SLOT_ID/CALL_TYPE`，类型映射为 IMS 语音→`IncomingCallType::IMS_VOICE_INCOMING`、IMS 视频→`IMS_VIDEO_INCOMING`、CS 或卫星语音→`CS_VOICE_INCOMING`，其余组合记 "args is out of range" 日志并不写事件；`WriteIncomingNumIdentityBehaviorEvent(markType, isBlock, blockReason)` 经模板 `HiWriteBehaviorEventPhoneUE` 以 PHONE_UE 域（`DOMAIN_PHONE_UE`）写事件 `CALL_INCOMING_NUM_IDENTITY`，固定键 PNAMEID="callmanager"、PVERSIONID=""、`MARK_TYPE/IS_BLOCK/BLOCK_REASON`（调用点 `services/spam_call/src/callback_stub_helper.cpp`，骚扰/黄页识别回调返回时）。

#### Scenario: 状态回报触发 CALL_STATE
- **WHEN** 蜂窝通话状态变化经 `call_status_callback.cpp` 回调
- **THEN** `CALL_STATE` 行为事件携带 slotId、state、index 写入

#### Scenario: CS 来电事件
- **WHEN** callType 为 CS_CALL_TYPE(0)/SATELLITE_CALL_TYPE(5) 且 callMode 为语音
- **THEN** `INCOMING_CALL` 事件 CALL_TYPE 值为 `CS_VOICE_INCOMING`

#### Scenario: 参数组合超界丢弃
- **WHEN** callType=IMS 且 callMode 既非语音也非视频
- **THEN** 仅记错误日志，不产生 `INCOMING_CALL` 事件

#### Scenario: 号码识别结果上报
- **WHEN** 骚扰识别回调获得 markType/isBlock/blockReason
- **THEN** PHONE_UE 域 `CALL_INCOMING_NUM_IDENTITY` 事件写入（不含号码字段）

### Requirement: 四类故障事件与错误码映射
系统 SHALL 由 `CallManagerHisysevent` 以 `HiWriteFaultEvent` 写故障事件，公共键 `MODULE="CALL_MANAGER"` 与 `SLOT_ID`：`WriteDialCallFaultEvent(slotId, callType, videoState, errCode, desc)`→`CALL_DIAL_FAILED`（附 `CALL_TYPE/VIDEO_STATE/ERROR_TYPE/ERROR_MSG`，拨号失败或权限拒绝时由 `call_manager_service.cpp` 调用）；`WriteIncomingCallFaultEvent`→`CALL_INCOMING_FAILED`；`WriteAnswerCallFaultEvent(slotId, callId, videoState, errCode, desc)`→`CALL_ANSWER_FAILED`（附 `CALL_ID`）；`WriteHangUpFaultEvent(slotId, callId, errCode, desc)`→`CALL_HANGUP_FAILED`（附 `CALL_ID`）。写入前 SHALL 尝试 `ErrorCodeConversion`（依次 `CallDataErrorCodeConversion`/`CallInterfaceErrorCodeConversion`/`TelephonyErrorCodeConversion` 把仓内错误码映射为 `CallErrorCode` 枚举填 ERROR_TYPE；映射失败原样写入 errCode）。`GetErrorDescription(errCode, desc)` SHALL 按错误类别生成固定描述（"NumberLegalityCheck failed"、"DialPolicy failed"、"CallRequestHandlerPtr_ or handler_ is nullptr"、"Send HANDLER_DIAL_CALL_REQUEST event failed" 等）。

#### Scenario: 拨号失败写故障
- **WHEN** `DialCall` 返回非 0 且 `GetErrorDescription` 命中
- **THEN** `CALL_DIAL_FAILED` 事件 ERROR_TYPE 为映射后 CallErrorCode，ERROR_MSG 为该描述

#### Scenario: 未知错误码透传
- **WHEN** errCode 无法被三级映射命中
- **THEN** 事件 ERROR_TYPE 字段直接写入原始 errCode 数值

### Requirement: 拨号/来电/应答时延超时判定
系统 SHALL 由 `CallManagerHisysevent` 实例（`DelayedSingleton` 持有）维护三个起点：`SetDialStartTime()`（`DialCall` 入口调用）、`SetIncomingStartTime()`、`SetAnswerStartTime()`（`AnswerCall` 入口调用）；对应终点判定 `JudgingDialTimeOut(slotId, callType, videoState)` 超过 `NORMAL_DIAL_TIME=500ms`、`JudgingIncomingTimeOut` 超过 `NORMAL_INCOMING_TIME=100ms`、`JudgingAnswerTimeOut(slotId, callId, videoState)` 超过 `NORMAL_ANSWER_TIME=300ms` 时，分别以 `CALL_ERROR_DIAL_TIME_OUT`、`CALL_ERROR_INCOMING_TIME_OUT`、`CALL_ERROR_ANSWER_TIME_OUT` 写调用对应的故障事件（描述附实际耗时，调用点 `services/call/src/call_status_manager.cpp` 等）。

#### Scenario: 拨号超时
- **WHEN** 自 `SetDialStartTime` 起超过 500ms 才到达判定点
- **THEN** 写 `CALL_DIAL_FAILED`，ERROR_TYPE 为 CALL_ERROR_DIAL_TIME_OUT

#### Scenario: 未超时静默
- **WHEN** 应答在 300ms 内完成
- **THEN** `JudgingAnswerTimeOut` 不写任何事件

### Requirement: VoIP 通话统计事件
系统 SHALL 由 `CallManagerHisysevent::WriteVoipCallStatisticalEvent(voipCallId, bundleName, uid, statisticalField)` 经 `ffrt::submit` 异步写 STATISTIC 事件 `VOIP_CALL_STATISTICS`（域为外部依赖头提供的 `DOMAIN_NAME` 常量）：先 `GetAppIndexByBundleName`（经 `SystemAbilityManager` 取 `BUNDLE_MGR_SERVICE_SYS_ABILITY_ID` 的 `IBundleMgr`，调 `GetNameAndIndexForUid` 反查 appIndex，SA 缺失时 appIndex 保持 -1），再携带 `CALL_ID/BUNDLE_NAME/STATISTICAL_FIELD/APP_INDEX` 写入。callId 重载 SHALL 先经 `CallControlManager::GetOneCallObject` 判空且 callType 必须为 TYPE_VOIP，再以 `reinterpret_cast<VoIPCall*>` 取 voipCallId/bundleName/uid 转调字符串版本（调用点 `services/telephony_interaction/src/voip_call_connection.cpp` 与 `services/call/src/call_control_manager.cpp` 的 "MtBannerAnswer" 等统计字段）。

#### Scenario: 非 VoIP 通话不统计
- **WHEN** callId 对应对象为空或 callType 非 TYPE_VOIP
- **THEN** 直接返回，不写事件

#### Scenario: 异步补齐 appIndex
- **WHEN** 写入时 BundleMgr 可用
- **THEN** 事件 APP_INDEX 为 uid 反查结果；不可用时 APP_INDEX 为 -1

### Requirement: VoIP NDK 侧事件写入口
系统 SHALL 提供 `NativeCallManagerHisysevent::WriteVoipCallEvent(callId, bundleName, scenario, errCode, errorMsg, callType, callState, callDirection)`（`frameworks/native/src/native_call_manager_hisysevent.cpp`，由 `voip_call_manager_proxy.cpp` 在 VoIP IPC 连接失败路径以 `Scenario::VOIP_PROXY_IPC_CONNECTTING` 上报），事件经基类 `TelephonyHiSysEvent` 写入。

#### Scenario: NDK VoIP 调用结果上报
- **WHEN** VoIP 代理经 NDK 层完成一次请求
- **THEN** `WriteVoipCallEvent` 以 callId/bundleName/scenario/err/callType/callState/callDirection 组装事件

### Requirement: 事件隐私约束
系统 SHALL 保证本能力写入的全部事件不携带明文电话号码：故障/行为事件的字段集合仅有 `MODULE/SLOT_ID/INDEX_ID/STATE/CALL_ID/CALL_TYPE/VIDEO_STATE/ERROR_TYPE/ERROR_MSG/MARK_TYPE/IS_BLOCK/BLOCK_REASON/PNAMEID/PVERSIONID/BUNDLE_NAME/STATISTICAL_FIELD/APP_INDEX` 等标识与枚举值；`CALL_INCOMING_NUM_IDENTITY` 只携带识别结果不携带号码本身；`CallManagerDumpHelper` 的文本输出同样不含任何号码或联系人字段；话单/号码展示由 `core_service` 域的 CALL_STATE 系事件处理，不在本仓面。

#### Scenario: 故障事件字段巡检
- **WHEN** 任一 fault/behavior 事件按声明的键集合打包
- **THEN** 键集合内不存在 phone number 类字段

#### Scenario: dump 文本巡检
- **WHEN** `ShowCallManagerInfo` 生成转储文本
- **THEN** 文本只含服务/状态布尔与枚举数值，无号码（示例号码 unknown 不出现于任何事件场景）