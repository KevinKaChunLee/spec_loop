# 维测与 Dump（hisysevent-observability）Specification

## Purpose
描述 `telephony_call_manager/services/hisysevent/` 的维测模块组：`CallManagerHisysevent`（行为/故障/统计事件与超时判定，继承公共基类 `TelephonyHiSysEvent` 的 `HiWriteBehaviorEvent`/`HiWriteFaultEvent`）、`CallManagerDumpHelper`（hidumper 输出）。落点：`services/hisysevent/src/call_manager_hisysevent.cpp` 与 `src/call_manager_dump_helper.cpp` 及对应头文件。该模块组无独有编译开关；隐私红线：号码、联系人名不进事件，用 callId/slotId/index 定位。

## Requirements

### Requirement: 拨号/来铃/接听超时判定
系统 SHALL 由 `CallManagerHisysevent` 以 `SetDialStartTime/SetIncomingStartTime/SetAnswerStartTime` 记录起点，经 `JudgingDialTimeOut`（超 `NORMAL_DIAL_TIME = 500` 毫秒）、`JudgingIncomingTimeOut`（`NORMAL_INCOMING_TIME = 100` 毫秒）、`JudgingAnswerTimeOut`（`NORMAL_ANSWER_TIME = 300` 毫秒）判定超时并落对应 FAULT 事件（`CALL_DIAL_FAILED_EVENT`/`CALL_INCOMING_FAILED_EVENT`/`CALL_ANSWER_FAILED_EVENT`）。
#### Scenario: 拨号超时记故障
- **WHEN** `DialCall` 发起后 500 毫秒内未收到对应状态上报
- **THEN** `JudgingDialTimeOut` 判定超时并上报 `CALL_DIAL_FAILED` 故障事件

### Requirement: 故障事件错误码转换
系统 SHALL 由 `WriteIncomingCallFaultEvent/WriteDialCallFaultEvent/WriteAnswerCallFaultEvent/WriteHangUpFaultEvent`（MODULE = `CALL_MANAGER`）落参数前经 `ErrorCodeConversion`（= `CallDataErrorCodeConversion || CallInterfaceErrorCodeConversion || TelephonyErrorCodeConversion`）把内部错误码映射为 `CallErrorCode`，描述经 `GetErrorDescription`（如 `CALL_ERR_PHONE_NUMBER_EMPTY` → "NumberLegalityCheck failed"）。
#### Scenario: 挂断失败落参
- **WHEN** `WriteHangUpFaultEvent(callId, errorCode, "HangUpCall")` 执行
- **THEN** 错误码先经 `ErrorCodeConversion` 归一后再写入 `CALL_HANGUP_FAILED_EVENT` 事件

### Requirement: 行为与统计事件
系统 SHALL 由 `WriteCallStateBehaviorEvent`（SLOT_ID/STATE/INDEX_ID）、`WriteIncomingCallBehaviorEvent`（按 `IMS_CALL_TYPE/CS_CALL_TYPE/SATELLITE_CALL_TYPE` 与 voice/video 映射 `IncomingCallType`）、`WriteIncomingNumIdentityBehaviorEvent`（PHONE_UE 域）、`WriteVoipCallStatisticalEvent`（`VOIP_CALL_STATISTICS`，经 ffrt 异步；`GetAppIndexByBundleName` 经 `IBundleMgr::GetNameAndIndexForUid` 补 APP_INDEX）上报；PHONE_UE 域常量 `CALL_DIAL_IN_SUPER_PRIVACY`/`CALL_ANSWER_IN_SUPER_PRIVACY`/`CALL_REJECT_IN_SUPER_PRIVACY`/`CALL_DIAL_CLOSE_SUPER_PRIVACY`/`CALL_INCOMING_REJECT_BY_SYSTEM`（动作值 `REJECT_BY_OOBE = 0`/`REJECT_BY_NUM_BLOCK = 1`/`REJECT_IN_FOCUSMODE = 2`，键 `ACTION_TYPE`）。
#### Scenario: 拒接来源行为打点
- **WHEN** 来电因 OOBE 未配置被系统拒接
- **THEN** PHONE_UE 域记 `CALL_INCOMING_REJECT_BY_SYSTEM`，`ACTION_TYPE` 为 `REJECT_BY_OOBE`

### Requirement: Dump 输出
系统 SHALL 由 `CallManagerDumpHelper::Dump(args, result)`（`ShowHelp` + `ShowCallManagerInfo`，恒返回 true）输出：用法（`-call_manager_info`、`-input_simulate <event>`、`-output_simulate <event>`、`-show_log_level`、`-set_log_level <level>`、`-perf_dump`）与运行信息（`CurrentTime`（`GetBindTime`）、`SpendTime`（`GetStartServiceSpent`）、`ServiceRunningState`、各卡 `SlotId`（`WhetherHasSimCard`→`CoreServiceClient::HasSimCard`，循环 `SIM_SLOT_COUNT`）、`CallState`、`RingingCallState`（`IsRinging`）、`HasCall`）。
#### Scenario: hidumper 查询运行状态
- **WHEN** `CallManagerService::Dump` 收到 `-call_manager_info` 参数
- **THEN** 输出服务绑定时间、启动耗时、运行状态、在位卡槽与通话状态信息
