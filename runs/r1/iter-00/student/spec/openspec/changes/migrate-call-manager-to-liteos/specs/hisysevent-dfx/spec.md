# Spec Delta

## MODIFIED Requirements

### Requirement: 行为事件上报
系统 SHALL 由 `CallManagerHisysevent` 组织行为事件（事件名与来电类型映射保留）：`WriteCallStateBehaviorEvent` 上报 `CALL_STATE`（携带 `SLOT_ID`/`STATE`/`INDEX_ID`）；`WriteIncomingCallBehaviorEvent` 按 callType/callMode 组合映射 `INCOMING_CALL` 的 `IMS_VOICE_INCOMING`/`IMS_VIDEO_INCOMING`/`CS_VOICE_INCOMING`，组合非法时不上报；`WriteIncomingNumIdentityBehaviorEvent` 在 `PHONE_UE` 域上报 `CALL_INCOMING_NUM_IDENTITY`（携带 `PNAMEID`/`PVERSIONID`/`MARK_TYPE`/`IS_BLOCK`/`BLOCK_REASON`）；HiSysEvent 上报改日志打印（本 change 引入的日志替代，保留 `TELEPHONY_LOG_TAG` 前缀），事件名与字段随日志输出。

#### Scenario: 来电类型映射上报
- **WHEN** 来电 callType 为 IMS 且 callMode 为语音
- **THEN** 以日志打印 `INCOMING_CALL` 事件且 `CALL_TYPE` 为 `IMS_VOICE_INCOMING`（0）

#### Scenario: 组合非法不上报
- **WHEN** callType/callMode 组合不满足任何映射分支
- **THEN** 不输出 `INCOMING_CALL` 事件日志

#### Scenario: 号码身份事件
- **WHEN** 骚扰识别回调完成后调用 `WriteIncomingNumIdentityBehaviorEvent(markType, isBlock, blockReason)`
- **THEN** 以日志输出 `PHONE_UE` 域的 `CALL_INCOMING_NUM_IDENTITY`，仅含 markType/isBlock/blockReason 字段

### Requirement: 故障事件上报与耗时超时判定
系统 SHALL 由 `WriteDialCallFaultEvent`/`WriteIncomingCallFaultEvent`/`WriteAnswerCallFaultEvent`/`WriteHangUpFaultEvent` 组织 `CALL_DIAL_FAILED`/`CALL_INCOMING_FAILED`/`CALL_ANSWER_FAILED`/`CALL_HANGUP_FAILED` 故障事件（携带 `MODULE`=`CALL_MANAGER`、`SLOT_ID`、`CALL_ID`、`CALL_TYPE`、`VIDEO_STATE`、`ERROR_TYPE`、`ERROR_MSG`），HiSysEvent 上报改日志打印（本 change 引入的日志替代，保留 `TELEPHONY_LOG_TAG` 前缀）；errCode 经 `ErrorCodeConversion`（`CallDataErrorCodeConversion`/`CallInterfaceErrorCodeConversion`/`TelephonyErrorCodeConversion` 三级映射）转换为 `CallErrorCode` 事件值，未映射时 MUST 直接以原 errCode 作为 `ERROR_TYPE`；`JudgingDialTimeOut`/`JudgingIncomingTimeOut`/`JudgingAnswerTimeOut` 在耗时超过 `NORMAL_DIAL_TIME`（500ms）/`NORMAL_INCOMING_TIME`（100ms）/`NORMAL_ANSWER_TIME`（300ms）时分别组织含 `CALL_ERROR_DIAL_TIME_OUT`/`CALL_ERROR_INCOMING_TIME_OUT`/`CALL_ERROR_ANSWER_TIME_OUT` 的超时故障事件并以日志输出。

#### Scenario: 错误码命中映射
- **WHEN** 上报故障事件且 errCode 为 `CALL_ERR_INVALID_SLOT_ID`
- **THEN** 日志中 `ERROR_TYPE` 为映射后的 `CALL_ERROR_INVALID_SLOT_ID` 事件值

#### Scenario: 错误码未命中映射
- **WHEN** errCode 不在任何转换表中
- **THEN** 日志中 `ERROR_TYPE` 直接写原 errCode 值

#### Scenario: 拨号超时
- **WHEN** `SetDialStartTime` 后超过 500ms 才调用 `JudgingDialTimeOut`
- **THEN** 以日志输出 `CALL_DIAL_FAILED` 事件且 `ERROR_TYPE` 为拨号超时错误码、`ERROR_MSG` 含实际耗时

### Requirement: hidump 输出
系统 SHALL 由 `CallManagerDumpHelper::Dump` 输出使用帮助（`ShowHelp`）与通话管理信息（`ShowCallManagerInfo`：`CurrentTime`=`GetBindTime`、`SpendTime`=`GetStartServiceSpent`、`ServiceRunningState`、各在卡槽位的 `SlotId`（经 `CoreServiceClient::GetInstance().HasSimCard(slotId, hasSimCard)`（stub/ 打桩）判定，`WhetherHasSimCard`）、`CallState`、`RingingCallState`=`IsRinging`、`HasCall`）并恒返回 true；hidumper IPC 入口改为日志输出（`Dump` 直接打日志）。

#### Scenario: 执行 dump
- **WHEN** 以任意参数调用 `Dump(args, result)`
- **THEN** `result` 依次包含 Usage 帮助与当前通话管理信息并以日志输出，返回 true

#### Scenario: 无卡设备
- **WHEN** 所有槽位桩的 `HasSimCard` 均为 false
- **THEN** 输出中不出现任何 `SlotId` 行

## REMOVED Requirements

### Requirement: VOIP 通话统计事件
**Reason**: VoIP 类型通话暂不支持（依赖后续 meetime 畅连适配）。
**Migration**: 后续畅连适配 change 如需要再立项。
