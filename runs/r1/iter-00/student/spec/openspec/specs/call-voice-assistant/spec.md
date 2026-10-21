# 通话语音助手（Call Voice Assistant） Specification

## Purpose
描述来电/去电场景语音助手能力的基线行为：在通话状态变化时按控制开关/播报开关连接 `CallVoiceControlAbility`，将主叫信息（号码、联系人名、归属地等）以 JSON 发给语音助手侧，根据其应答决定是否播报来电、是否由系统播放铃声，并对外发布状态公共事件。源码落点：`telephony_call_manager/services/call_voice_assistant/{include,src}`（`call_voice_assistant_manager.cpp/.h`：`CallVoiceAssistantManager`、`VoiceAssistantConnectCallback`、`VoiceAssistantSwitchObserver`、`VoiceAssistantRingSubscriber`）。该能力无专属编译宏：源文件无条件列入 `callmanager.gni` 的 `call_manager_sources`。

## Requirements

### Requirement: 语音助手开关判定
系统 SHALL 由 `CallVoiceAssistantManager::IsSwitchOn` 判定控制开关（`CONTROL_SWITCH` = `incoming_call_voice_control_switch`）与播报开关（`BROADCAST_SWITCH` = `incoming_call_voice_broadcast_switch`）：HiCar 车机在线（`DistributedCallManager::IsDistributedCarDeviceOnline`）时恒返回 true；前台用户未解锁返回 false；否则经 DataShare（`SETTINGS_DATASHARE_URI`，列 `KEYWORD`/`VALUE`）查询开关值，`0` 视为关。
#### Scenario: HiCar 在线
- **WHEN** 分布式车机设备在线
- **THEN** 控制开关与播报开关均视为开启
#### Scenario: 设置项关闭
- **WHEN** DataShare 查询 `incoming_call_voice_control_switch` 值为 `0`
- **THEN** 控制开关判定为关闭

### Requirement: 通话状态联动启停
系统 SHALL 由 `CallVoiceAssistantManager::CallStateUpdated` 在通话进入 INCOMING（免打扰静音场景除外）、DIALING、ACTIVE、DISCONNECTED 状态时联动：INCOMING/DIALING 触发 `OnStartService`（两开关均关闭时不启动），ACTIVE 时静音铃声音量并停止播报，DISCONNECTED 时经 `OnStopService` 断开能力、停止铃声（`StopRingtone`）并发布关断公共事件。
#### Scenario: 来电触发启动
- **WHEN** 新来电进入 CALL_STATUS_INCOMING 且非免打扰静音场景
- **THEN** 查询播报/控制开关并尝试连接 `CallVoiceControlAbility`
#### Scenario: 通话断开
- **WHEN** 通话进入 CALL_STATUS_DISCONNECTED 且无其他来电
- **THEN** 断开能力连接、`StopRingtone`、注销开关观察器并发布 `isConnectVoiceAssistant=0` 的公共事件
#### Scenario: 两开关均关闭
- **WHEN** `OnStartService` 时控制开关与播报开关均为 false
- **THEN** 不连接 `CallVoiceControlAbility`，直接返回

### Requirement: 主叫信息上报与应答解析
系统 SHALL 由 `CallVoiceAssistantManager::SendRequest` 在能力远端对象就绪且信息查询完成后，以 `GetSendString` 组装 JSON（`dialOrCome`/`callStatus`/`callId`/`phoneNumber`/`isContact`/`contactName`/`sim`/`stopBroadcasting`/`location` 字段）经 `SendRequest`（code `CHECK_CODE` = 1006）发送，并以 `UpdateReplyData` 解析应答中的 `incomingCallVoiceControlCheckResult`（`CONTROL_CHECK_RESULT`）与 `incomingCallVoiceBroadcastCheckResult`（`BROADCAST_CHECK_RESULT`）；`controlCheck` 为 `1` 且控制开关开启时置 `isConnectService` 并注册开关观察器（`RegisterListenSwitchState`）。信息查询未完成时 MUST NOT 发送。
#### Scenario: 应答允许播报
- **WHEN** 应答 JSON 中 `incomingCallVoiceBroadcastCheckResult` 为 `1` 且播报开关开启、来电非去电、未被要求停止播报
- **THEN** 初始化 `VoiceAssistantRingSubscriber`，`isplay` 置 `1`
#### Scenario: 信息未就绪
- **WHEN** 联系人信息 `isQueryComplete` 为 false 或归属地为 `default`
- **THEN** 放弃本次 `SendRequest` 上报

### Requirement: 系统铃声联动播放
系统 SHALL 由 `VoiceAssistantRingSubscriber`（订阅 `CONTROL_SWITCH_STATE_CHANGE_EVENT` = `usual.event.CALL_UI_REPORT_SWITCH_STATE_CHANGE`，订阅权限 `ohos.permission.GET_TELEPHONY_STATE`）在收到 publisher 为 `remote_object_send_request` 或 `connect_voice_assistant_ability_failed` 且 `call_manager_play_ring` 为 `1` 的事件时，经 `AudioControlManager` 先 `StopRingtone` 再按需 `PlayRingtone`（视频铃声时经 `NeedPlayVideoRing` 更新 `VideoRingPath` 并上报）。
#### Scenario: 需要播铃声
- **WHEN** `isplay` 为 `1` 且收到允许播放事件
- **THEN** 停止当前铃声后播放系统铃声（振铃中的通话）
#### Scenario: 能力连接失败兜底
- **WHEN** 连接 `CallVoiceControlAbility` 失败且播报开关开启
- **THEN** 初始化 `VoiceAssistantRingSubscriber`、`isplay` 置 `1` 并发布连接失败公共事件

### Requirement: 静音与停止播报
系统 SHALL 由 `CallVoiceAssistantManager::MuteRinger` 在静音请求时将铃声音量置 0（`SetRingToneVolume(0.0f)`）、注销 `VoiceAssistantRingSubscriber`、将当前通话的 `stopBroadcasting` 置 1，并向语音助手远端发送停止播报请求后发布状态公共事件；`CallStatusActive` MUST 在通话激活时同样将铃声音量置 0 并停止播报。
#### Scenario: 静音请求
- **WHEN** 通话振铃期间收到静音请求（`nowCallId` 有效）
- **THEN** 铃声音量为 0、播报订阅注销、该通话 `stopBroadcasting` 为 1
#### Scenario: 通话接通
- **WHEN** 通话进入 CALL_STATUS_ACTIVE
- **THEN** 铃声音量置 0 并发布 `isConnectVoiceAssistant=0` 的公共事件
