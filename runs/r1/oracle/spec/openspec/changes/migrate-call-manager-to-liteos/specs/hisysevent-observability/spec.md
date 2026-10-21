# Spec Delta

## MODIFIED Requirements

### Requirement: 拨号/来铃/接听超时判定
系统 SHALL 由 `CallManagerHisysevent` 以 `SetDialStartTime/SetIncomingStartTime/SetAnswerStartTime` 记录起点，经 `JudgingDialTimeOut`（超 `NORMAL_DIAL_TIME = 500` 毫秒）、`JudgingIncomingTimeOut`（`NORMAL_INCOMING_TIME = 100` 毫秒）、`JudgingAnswerTimeOut`（`NORMAL_ANSWER_TIME = 300` 毫秒）判定超时（判定逻辑保留），超时落点由 HiSysEvent 事件改为日志打印（原 `CALL_DIAL_FAILED_EVENT`/`CALL_INCOMING_FAILED_EVENT`/`CALL_ANSWER_FAILED_EVENT` 信息进日志）。
#### Scenario: 拨号超时记故障
- **WHEN** `DialCall` 发起后 500 毫秒内未收到对应状态上报
- **THEN** `JudgingDialTimeOut` 判定超时并以日志记录原 `CALL_DIAL_FAILED` 故障事件信息

### Requirement: 故障事件错误码转换
系统 SHALL 由 `WriteIncomingCallFaultEvent/WriteDialCallFaultEvent/WriteAnswerCallFaultEvent/WriteHangUpFaultEvent`（MODULE = `CALL_MANAGER`）落参数前经 `ErrorCodeConversion`（= `CallDataErrorCodeConversion || CallInterfaceErrorCodeConversion || TelephonyErrorCodeConversion`）把内部错误码映射为 `CallErrorCode`，描述经 `GetErrorDescription`（如 `CALL_ERR_PHONE_NUMBER_EMPTY` → "NumberLegalityCheck failed"）——转换与描述逻辑保留，落点由 HiSysEvent 改为日志打印。
#### Scenario: 挂断失败落参
- **WHEN** `WriteHangUpFaultEvent(callId, errorCode, "HangUpCall")` 执行
- **THEN** 错误码先经 `ErrorCodeConversion` 归一后以日志记录原 `CALL_HANGUP_FAILED_EVENT` 事件信息

### Requirement: 行为与统计事件
系统 SHALL 由 `WriteCallStateBehaviorEvent`（SLOT_ID/STATE/INDEX_ID）、`WriteIncomingCallBehaviorEvent`（按 `IMS_CALL_TYPE/CS_CALL_TYPE` 与 voice/video 映射 `IncomingCallType`；`SATELLITE_CALL_TYPE` 分支不可达）、`WriteIncomingNumIdentityBehaviorEvent`（PHONE_UE 域）、`WriteVoipCallStatisticalEvent`（`VOIP_CALL_STATISTICS`，经打桩 `EventHandler` 异步；`GetAppIndexByBundleName` 经 bundleManager 桩补 APP_INDEX）上报——全部落点由 HiSysEvent 改为日志打印；PHONE_UE 域常量 `CALL_DIAL_IN_SUPER_PRIVACY`/`CALL_ANSWER_IN_SUPER_PRIVACY`/`CALL_REJECT_IN_SUPER_PRIVACY`/`CALL_DIAL_CLOSE_SUPER_PRIVACY`（超级隐私）不再触发；`CALL_INCOMING_REJECT_BY_SYSTEM` 与动作值 `REJECT_BY_OOBE = 0`/`REJECT_BY_NUM_BLOCK = 1`/`REJECT_IN_FOCUSMODE = 2`（键 `ACTION_TYPE`）保留（日志记录）。
#### Scenario: 拒接来源行为打点
- **WHEN** 来电因 OOBE 未配置被系统拒接
- **THEN** 以日志记录原 PHONE_UE 域 `CALL_INCOMING_REJECT_BY_SYSTEM` 信息，`ACTION_TYPE` 为 `REJECT_BY_OOBE`

### Requirement: Dump 输出
系统 SHALL 由 `CallManagerDumpHelper::Dump(args, result)`（`ShowHelp` + `ShowCallManagerInfo`，恒返回 true）保留用法（`-call_manager_info` 等）与运行信息输出（`CurrentTime`（`GetBindTime`）、`SpendTime`（`GetStartServiceSpent`）、`ServiceRunningState`、各卡 `SlotId`（`WhetherHasSimCard`→`CoreServiceClient::HasSimCard` 经桩，循环 `SIM_SLOT_COUNT`）、`CallState`、`RingingCallState`（`IsRinging`）、`HasCall`）；hidumper 平台侧入口不依赖，`Dump` 方法保留供测试直调。
#### Scenario: hidumper 查询运行状态
- **WHEN** 直调 `CallManagerService::Dump` 携带 `-call_manager_info` 参数
- **THEN** 输出服务绑定时间、启动耗时、运行状态、在位卡槽（经 `CoreServiceClient` 桩）与通话状态信息
