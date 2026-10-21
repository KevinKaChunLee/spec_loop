# 来电语音助手（call-voice-assistant）Specification

## Purpose
描述 `telephony_call_manager/services/call_voice_assistant/` 的来电语音助手模块组（语音播报与语音控制）：`CallVoiceAssistantManager`（开关查询、助手 ability 连接、检测请求与播报联动）与内部订阅类 `VoiceAssistantRingSubscriber`。落点：`services/call_voice_assistant/src/call_voice_assistant_manager.cpp` 与 `include/call_voice_assistant_manager.h`。该模块组无独有编译开关；HiCar 场景经 `DistributedCallManager::IsDistributedCarDeviceOnline` 运行时判定。

## Requirements

### Requirement: 开关与数据面
系统 SHALL 由 `CallVoiceAssistantManager`（继承 `CallStateListenerBase`，`Initial()` 经 `DataShare::DataShareHelper::Creator(remote, SETTINGS_DATASHARE_URI, SETTINGS_DATASHARE_EXT_URI)`）查询 `CONTROL_SWITCH = "incoming_call_voice_control_switch"` 与 `BROADCAST_SWITCH = "incoming_call_voice_broadcast_switch"`；`IsSwitchOn`：HiCar 在线恒 true，`OsAccountManager::IsOsAccountVerified` 未解锁恒 false。
#### Scenario: 未解锁时不开播报
- **WHEN** 当前账号未通过 `IsOsAccountVerified`
- **THEN** 语音播报开关判为关闭，来电不启动播报

### Requirement: 助手 ability 连接与检测请求
系统 SHALL 由 `OnStartService(isDial, callId)`：meetime（VoIP）off_hook 时先 `OnStopService`；两开关全关不启动；`ConnectAbility`（ElementName 指向 `ABILITY_NAME = "CallVoiceControlAbility"`）；`SendRequest` 以 `CHECK_CODE = 1006` 发送 `GetSendString` 组装的 JSON（dialOrCome/callStatus/callId/phoneNumber/isContact/contactName/sim/stopBroadcasting/location），回包 `UpdateReplyData` 解析 `CONTROL_CHECK_RESULT = "incomingCallVoiceControlCheckResult"` 与 `BROADCAST_CHECK_RESULT = "incomingCallVoiceBroadcastCheckResult"`；连接失败且播报开关开时 `VoiceAssistantRingSubscriber::Initial` + `PublishCommonEvent(false, "connect_voice_assistant_ability_failed")`。
#### Scenario: 播报允许时订阅铃声控制事件
- **WHEN** 检测回包允许播报且播报开关开
- **THEN** 订阅 `CONTROL_SWITCH_STATE_CHANGE_EVENT = "usual.event.CALL_UI_REPORT_SWITCH_STATE_CHANGE"`，收到 `IS_PLAY_RING = "call_manager_play_ring"` 为 "1" 时 `StopRingtone` + `PlayRingtone`

### Requirement: 状态联动
系统 SHALL 由 `CallStateUpdated` 全部经 `ffrt::queue callVoiceAssistantQueue`（`ffrt_qos_user_interactive`）串行处理；免打扰（`CallObjectManager::IsNeedSilentInDoNotDisturbMode`）且无来电时不启动；接通（`CallStatusActive`）`SetRingToneVolume(0.0f)` 停播报；断开清 `accountIds` 且无其他来话时 `OnStopService`（`DisconnectAbility` + `AudioControlManager::StopRingtone` + `RingSubscriber::Release`）。
#### Scenario: 接通停播报
- **WHEN** 语音播报中的来电被接通
- **THEN** 铃声音量置 0 并释放播报订阅
