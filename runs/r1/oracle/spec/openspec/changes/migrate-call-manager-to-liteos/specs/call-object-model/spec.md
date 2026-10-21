# Spec Delta

## MODIFIED Requirements

### Requirement: 通话对象表管理
系统 SHALL 以全静态成员的 `CallObjectManager` 维护全局通话对象表 `callObjectPtrList_`（`std::list<std::shared_ptr<CallBase>>`，替代 `sptr`），并由 `GetNewCallId()`（`++callId_`，起始 `CALL_START_ID`）唯一分配 callId；VoIP 通话同时存在于主表与独立的属性缓存表 `voipCallObjectList_`（`std::map<int32_t, CallAttributeInfo>`）。
#### Scenario: 新增通话对象
- **WHEN** 上行状态机经 `AddOneCallObject(std::shared_ptr<CallBase>)` 添加新通话对象
- **THEN** 同 callId 重复入表返回 `CALL_ERR_PHONE_CALL_ALREADY_EXISTS`；空表且（无 VoIP RINGING 通话或 `isEcc_` 为真）时调用 `CallConnectAbility::ConnectAbility()`（界面拉起经 `stub/` 桩，不真正连接 `com.ohos.callui`）

#### Scenario: VoIP 属性缓存表
- **WHEN** `VoIPCall` 对象创建/更新/删除
- **THEN** 同步执行 `AddOneVoipCallObject`/`UpdateOneVoipCallObjectByCallId`/`DeleteOneVoipCallObject`；`IsVoipCallExist`、`GetVoipCallInfo`、`GetActiveVoipCallInfo`、`GetVoipCallInfoList`（依赖 `CallControlManager::GetMeetimeCallState`）基于该 map 提供查询

#### Scenario: 表清空后延时断开通话界面
- **WHEN** `DeleteOneCallObject` 后通话对象表为空且 `CallControlManager::ShouldDisconnectService()` 为真
- **THEN** `DelayedDisconnectCallConnectAbility` 以打桩 `EventHandler` 延时任务（`DISCONNECT_DELAY_TIME = 2000000` 微秒）约 2 秒后执行断开（断开动作经桩）

### Requirement: 蜂窝拨号基流程清理冲突 VoIP
系统 SHALL 在 `CallBase::DialCallBase()` 置 `CALL_RUNNING_STATE_CONNECTING` 后以打桩 `EventHandler` 异步执行 `HangUpVoipCall()`：遍历 `CallObjectManager::GetAllCallInfoList()`，`TYPE_VOIP` 且 INCOMING 的通话走 `RejectCall()`，其余 VoIP 通话走 `HangUpCall(ErrorReason::CELLULAR_CALL_EXISTS)`。
#### Scenario: 载体拨号撞上 VoIP 振铃
- **WHEN** 已存在 `TYPE_VOIP` 的 INCOMING 通话时发起蜂窝拨号
- **THEN** 冲突 VoIP 通话被 `RejectCall()` 拒接，蜂窝拨号继续

### Requirement: VoIP 通话对象行为
系统 SHALL 由 `VoIPCall`（构造自 `DialParaInfo.voipCallInfo`，携带 `voipCallId_/userName_/abilityName_/extensionId_/voipBundleName_/uid_` 等）把 `AnswerCall`/`RejectCall`/`HangUpCall` 经 `PackVoipCallInfo` 后交 `VoipCallConnection` 同名接口（`VoipCallConnection` 经 `stub/` 桩实现，暂无 voip_call_manager 真实对接，依赖后续畅连通话适配）；`HoldCall`/`UnHoldCall`/`SwitchCall` 与会议族空实现返回 `TELEPHONY_SUCCESS`；`GetOneCallObjectByVoipCallId(voipCallId, bundleName, uid)` 以三元组定位。
#### Scenario: VoIP 静音事件
- **WHEN** 对 `VoIPCall` 调用 `SetMute`
- **THEN** 以 `voipBundleName:uid:voipCallId` 组串经 `VoipCallConnection::SendCallUiEvent(voipCallId, CallAudioEvent::AUDIO_EVENT_MUTED/AUDIO_EVENT_UNMUTED)` 发送 UI 事件（经桩）

## REMOVED Requirements

### Requirement: 会议对象与容量上限
**Reason**: AGENTS.md 功能范围：liteOS 不支持会议通话，会议对象族不迁移。
**Migration**: `ConferenceBase`/`CsConference`/`ImsConference`/`OttConference` 与 `JoinToConference`/`CombineConference` 调用链不迁移；`CarrierCall::IsSupportConferenceable()` 恒返回不支持错误码，会议相关入口（`CombineConference` 等）返回 `CALL_ERR_FUNCTION_NOT_SUPPORTED`。

### Requirement: IMS 视频升级状态机
**Reason**: AGENTS.md 功能范围：liteOS 不支持视频通话，视频升级状态机不迁移。
**Migration**: `videoStateMap_`/`VideoCallState` 状态类与 `UpdateImsCallMode`/`SendUpdateCallMediaModeRequest`/`SendUpdateCallMediaModeResponse` 调用链不迁移；`IMSCall` 仅保留语音行为，视频接口返回 `CALL_ERR_FUNCTION_NOT_SUPPORTED`。

### Requirement: OTT 命令经回调代理转发
**Reason**: AGENTS.md 功能范围：OTT 类型通话不支持。
**Migration**: `OTTCall`/`OTTCallConnection` 对象与 `OttCallRequest` 回传链不迁移；`CallType::TYPE_OTT` 分支不可达，上行该类型按未知类型拒绝。

### Requirement: 卫星与蓝牙通话对象差异
**Reason**: AGENTS.md 功能范围：卫星通话与 BLUETOOTH 类型通话不支持。
**Migration**: `SatelliteCall`/`BluetoothCall`/`BluetoothCallState` 对象不迁移；`CreateNewCallByCallTypeEx` 不再有 `TYPE_SATELLITE`/`TYPE_BLUETOOTH` 分支，`GetSlotId()` 等差异行为随对象移除。
