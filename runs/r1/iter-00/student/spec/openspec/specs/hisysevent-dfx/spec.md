# 维测（HiSysEvent DFX） Specification

## Purpose
描述通话管理维测能力的基线行为：HiSysEvent 行为/故障事件上报、VOIP 统计事件、事件隐私字段约束与 hidump 输出。源码落点：`telephony_call_manager/services/hisysevent/{include,src}`（`call_manager_hisysevent.cpp/.h`：`CallManagerHisysevent`；`call_manager_dump_helper.cpp/.h`：`CallManagerDumpHelper`）。该能力无专属编译宏：源文件无条件列入 `callmanager.gni` 的 `call_manager_sources`（外部依赖恒含 `hisysevent:libhisysevent`）。

## Requirements

### Requirement: 行为事件上报
系统 SHALL 由 `CallManagerHisysevent` 上报行为事件：`WriteCallStateBehaviorEvent` 上报 `CALL_STATE`（携带 `SLOT_ID`/`STATE`/`INDEX_ID`）；`WriteIncomingCallBehaviorEvent` 按 callType/callMode 组合映射 `INCOMING_CALL` 的 `IMS_VOICE_INCOMING`/`IMS_VIDEO_INCOMING`/`CS_VOICE_INCOMING`，组合非法时不上报；`WriteIncomingNumIdentityBehaviorEvent` 在 `PHONE_UE` 域上报 `CALL_INCOMING_NUM_IDENTITY`（携带 `PNAMEID`/`PVERSIONID`/`MARK_TYPE`/`IS_BLOCK`/`BLOCK_REASON`）。
#### Scenario: 来电类型映射上报
- **WHEN** 来电 callType 为 IMS 且 callMode 为语音
- **THEN** 上报 `INCOMING_CALL` 事件且 `CALL_TYPE` 为 `IMS_VOICE_INCOMING`（0）
#### Scenario: 组合非法不上报
- **WHEN** callType/callMode 组合不满足任何映射分支
- **THEN** 不上报 `INCOMING_CALL` 事件
#### Scenario: 号码身份事件
- **WHEN** 骚扰识别回调完成后调用 `WriteIncomingNumIdentityBehaviorEvent(markType, isBlock, blockReason)`
- **THEN** 在 `PHONE_UE` 域上报 `CALL_INCOMING_NUM_IDENTITY`，仅含 markType/isBlock/blockReason 字段

### Requirement: 故障事件上报与耗时超时判定
系统 SHALL 由 `WriteDialCallFaultEvent`/`WriteIncomingCallFaultEvent`/`WriteAnswerCallFaultEvent`/`WriteHangUpFaultEvent` 上报 `CALL_DIAL_FAILED`/`CALL_INCOMING_FAILED`/`CALL_ANSWER_FAILED`/`CALL_HANGUP_FAILED` 故障事件（携带 `MODULE`=`CALL_MANAGER`、`SLOT_ID`、`CALL_ID`、`CALL_TYPE`、`VIDEO_STATE`、`ERROR_TYPE`、`ERROR_MSG`）；errCode 经 `ErrorCodeConversion`（`CallDataErrorCodeConversion`/`CallInterfaceErrorCodeConversion`/`TelephonyErrorCodeConversion` 三级映射）转换为 `CallErrorCode` 事件值，未映射时 MUST 直接以原 errCode 作为 `ERROR_TYPE`；`JudgingDialTimeOut`/`JudgingIncomingTimeOut`/`JudgingAnswerTimeOut` 在耗时超过 `NORMAL_DIAL_TIME`（500ms）/`NORMAL_INCOMING_TIME`（100ms）/`NORMAL_ANSWER_TIME`（300ms）时分别上报含 `CALL_ERROR_DIAL_TIME_OUT`/`CALL_ERROR_INCOMING_TIME_OUT`/`CALL_ERROR_ANSWER_TIME_OUT` 的超时故障事件。
#### Scenario: 错误码命中映射
- **WHEN** 上报故障事件且 errCode 为 `CALL_ERR_INVALID_SLOT_ID`
- **THEN** `ERROR_TYPE` 为映射后的 `CALL_ERROR_INVALID_SLOT_ID` 事件值
#### Scenario: 错误码未命中映射
- **WHEN** errCode 不在任何转换表中
- **THEN** `ERROR_TYPE` 直接写原 errCode 值
#### Scenario: 拨号超时
- **WHEN** `SetDialStartTime` 后超过 500ms 才调用 `JudgingDialTimeOut`
- **THEN** 上报 `CALL_DIAL_FAILED` 事件且 `ERROR_TYPE` 为拨号超时错误码、`ERROR_MSG` 含实际耗时

### Requirement: 事件隐私字段约束
系统 SHALL 保证全部 HiSysEvent 事件（行为/故障/统计）仅携带 `SLOT_ID`/`CALL_ID`/`CALL_TYPE`/`VIDEO_STATE`/`STATE`/`INDEX_ID`/`MARK_TYPE`/`IS_BLOCK`/`BLOCK_REASON`/`ERROR_TYPE`/`ERROR_MSG`/`BUNDLE_NAME` 等非隐私字段，事件内容 MUST NOT 包含电话号码与联系人姓名。
#### Scenario: 故障事件不含号码
- **WHEN** 任一故障事件被上报
- **THEN** 事件负载中不存在电话号码或联系人姓名字段

### Requirement: VOIP 通话统计事件
系统 SHALL 由 `WriteVoipCallStatisticalEvent` 仅对 `CallType::TYPE_VOIP` 通话在 `STATISTIC` 类型上报 `VOIP_CALL_STATISTICS`（携带 `CALL_ID`/`BUNDLE_NAME`/`STATISTICAL_FIELD`/`APP_INDEX`）：经 ffrt 异步执行，`APP_INDEX` 由 `GetAppIndexByBundleName`（经 `BUNDLE_MGR_SERVICE_SYS_ABILITY_ID` 查询 `IBundleMgr`）解析；非 VOIP 通话 MUST NOT 上报。
#### Scenario: VOIP 通话统计
- **WHEN** VOIP 通话触发统计
- **THEN** 异步上报 `VOIP_CALL_STATISTICS` 事件并携带解析出的 `APP_INDEX`
#### Scenario: 非VOIP通话
- **WHEN** `GetOneCallObject` 返回非 VOIP 类型通话或空对象
- **THEN** 直接返回，不上报统计事件

### Requirement: hidump 输出
系统 SHALL 由 `CallManagerDumpHelper::Dump` 输出使用帮助（`ShowHelp`）与通话管理信息（`ShowCallManagerInfo`：`CurrentTime`=`GetBindTime`、`SpendTime`=`GetStartServiceSpent`、`ServiceRunningState`、各在卡槽位的 `SlotId`（经 `CoreServiceClient::HasSimCard` 判定，`WhetherHasSimCard`）、`CallState`、`RingingCallState`=`IsRinging`、`HasCall`）并恒返回 true。
#### Scenario: 执行 dump
- **WHEN** 以任意参数调用 `Dump(args, result)`
- **THEN** `result` 依次包含 Usage 帮助与当前通话管理信息，返回 true
#### Scenario: 无卡设备
- **WHEN** 所有槽位 `HasSimCard` 均为 false
- **THEN** 输出中不出现任何 `SlotId` 行
