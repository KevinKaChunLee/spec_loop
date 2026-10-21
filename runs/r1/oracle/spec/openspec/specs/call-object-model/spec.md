# 通话对象模型（call-object-model）Specification

## Purpose
描述 `telephony_call_manager/services/call/src` 中的通话对象模型：`CallBase` 继承体系（`CarrierCall`/`CSCall`/`IMSCall`/`OTTCall`/`VoIPCall`/`SatelliteCall`/`BluetoothCall` 与 `NetCallBase`）、会议对象（`ConferenceBase`/`CsConference`/`ImsConference`/`OttConference`）、全局通话对象表 `CallObjectManager`、视频升级状态机 `VideoCallState` 与蓝牙 HFP 状态观察者 `BluetoothCallState`。主要落点：`services/call/src/{call_base,carrier_call,net_call_base,cs_call,ims_call,ott_call,ott_call_connection,voip_call,satellite_call,bluetooth_call,bluetooth_call_state,video_call_state,conference_base,cs_conference,ims_conference,ott_conference,call_object_manager}.cpp` 及 `services/call/include/` 对应头文件与 `common_type.h`（`DialParaInfo`/`PolicyFlag`/`ContactInfo` 与 `RINGING_CALL_NUMBER_LEN`/`DIALING_CALL_NUMBER_LEN`/`CALL_START_ID` 等常量）。编译开关：`NOT_SUPPORT_MULTICALL`（`call_object_manager.cpp` 单通话与双通话判定）、`ABILITY_CONFIG_SUPPORT` 与 `ABILIT_CONFIG_SUPPORT`（`cs_call.cpp`/`ims_call.cpp`/`ott_call.cpp` 原文拼写，会议子类的 carrier config 容量查询），默认手机构建下均未定义，容量取代码默认值。

## Requirements

### Requirement: 通话对象表管理
系统 SHALL 以全静态成员的 `CallObjectManager` 维护全局通话对象表 `callObjectPtrList_`（`std::list<sptr<CallBase>>`），并由 `GetNewCallId()`（`++callId_`，起始 `CALL_START_ID`）唯一分配 callId；VoIP 通话同时存在于主表与独立的属性缓存表 `voipCallObjectList_`（`std::map<int32_t, CallAttributeInfo>`）。
#### Scenario: 新增通话对象
- **WHEN** 上行状态机经 `AddOneCallObject(sptr<CallBase>)` 添加新通话对象
- **THEN** 同 callId 重复入表返回 `CALL_ERR_PHONE_CALL_ALREADY_EXISTS`；空表且（无 VoIP RINGING 通话或 `isEcc_` 为真）时调用 `CallConnectAbility::ConnectAbility()` 拉起通话界面，首个通话时调用 `CallWiredHeadSet::Init()`

#### Scenario: VoIP 属性缓存表
- **WHEN** `VoIPCall` 对象创建/更新/删除
- **THEN** 同步执行 `AddOneVoipCallObject`/`UpdateOneVoipCallObjectByCallId`/`DeleteOneVoipCallObject`；`IsVoipCallExist`、`GetVoipCallInfo`、`GetActiveVoipCallInfo`、`GetVoipCallInfoList`（依赖 `CallControlManager::GetMeetimeCallState`）基于该 map 提供查询

#### Scenario: 表清空后延时断开通话界面
- **WHEN** `DeleteOneCallObject` 后通话对象表为空且 `CallControlManager::ShouldDisconnectService()` 为真
- **THEN** `DelayedDisconnectCallConnectAbility` 以 `ffrt::submit_h` + `ffrt::task_attr().delay`（`DISCONNECT_DELAY_TIME = 2000000` 微秒）延时约 2 秒断开 `CallConnectAbility`

### Requirement: 通话状态迁移入口唯一
系统 SHALL 以 `CallBase::SetTelCallState(TelCallState nextState)` 作为通话状态迁移唯一入口，按 next 状态分发到 `StateChangesToDialing`/`StateChangesToIncoming`/`StateChangesToWaiting`/`StateChangesToActive`/`StateChangesToHolding`/`StateChangesToDisconnecting`/`StateChangesToDisconnected`/`StateChangesToAlerting` 八个私有方法，重复状态返回 `CALL_ERR_NOT_NEW_STATE`（`CALL_STATUS_DIALING` 除外）。
#### Scenario: 来电进入振铃
- **WHEN** `SetTelCallState(CALL_STATUS_INCOMING)` 或 `CALL_STATUS_WAITING`
- **THEN** 通话进入 `CALL_RUNNING_STATE_RINGING` 并记录 `ringBeginTime_`

#### Scenario: 接通与挂断计时
- **WHEN** 通话首次进入 `CALL_STATUS_ACTIVE`（记录 `callBeginTime_`/`ringEndTime_`，VoIP 通话用毫秒级 `startTime_`）或进入 `CALL_STATUS_DISCONNECTED`（记录 `callEndTime_`）
- **THEN** 计费/展示用的起止时间戳分别落盘到通话属性并经 `GetCallAttributeBaseInfo()` 输出

### Requirement: 蜂窝拨号基流程清理冲突 VoIP
系统 SHALL 在 `CallBase::DialCallBase()` 置 `CALL_RUNNING_STATE_CONNECTING` 后以 `ffrt::submit` 异步执行 `HangUpVoipCall()`：遍历 `CallObjectManager::GetAllCallInfoList()`，`TYPE_VOIP` 且 INCOMING 的通话走 `RejectCall()`，其余 VoIP 通话走 `HangUpCall(ErrorReason::CELLULAR_CALL_EXISTS)`。
#### Scenario: 载体拨号撞上 VoIP 振铃
- **WHEN** 已存在 `TYPE_VOIP` 的 INCOMING 通话时发起蜂窝拨号
- **THEN** 冲突 VoIP 通话被 `RejectCall()` 拒接，蜂窝拨号继续

### Requirement: 挂断补充类型按策略位选择
系统 SHALL 由 `CarrierHangUpCall` 依据 `PolicyFlag` 位（`POLICY_FLAG_HANG_UP_ACTIVE`/`POLICY_FLAG_HANG_UP_HOLD_WAIT` 等）选择 `CallSupplementType::TYPE_HANG_UP_ACTIVE`/`TYPE_HANG_UP_HOLD_WAIT`/`TYPE_DEFAULT` 下发 `CellularCallConnection::HangUp`。
#### Scenario: 挂断活动通话恢复保持通话
- **WHEN** 通话对象携带 `POLICY_FLAG_HANG_UP_ACTIVE`
- **THEN** 以 `TYPE_HANG_UP_ACTIVE` 挂断活动通话，协议栈侧释放后恢复保持通话

### Requirement: 紧急呼叫禁止入会
系统 SHALL 对 `isEcc` 紧急呼叫执行 `CarrierCall::IsSupportConferenceable()` 返回 `CALL_ERR_EMERGENCY_UNSUPPORT_CONFERENCEABLE`，且 `IMSCall::IsSupportVideoCall()` 禁止紧急呼叫升级视频。
#### Scenario: 紧急呼叫尝试并入会议
- **WHEN** ECC 通话对象调用会议合并路径
- **THEN** 返回 `CALL_ERR_EMERGENCY_UNSUPPORT_CONFERENCEABLE` 拒绝入会

### Requirement: 会议对象与容量上限
系统 SHALL 以 `ConferenceBase`（`mainCallId_`、`subCallIdSet_`、`state_/oldState_`）派生 `CsConference`/`ImsConference`/`OttConference` 三个延迟单例，`JoinToConference` 后置 `CONFERENCE_STATE_ACTIVE` 并记 `beginTime_`；`CanCombineConference` 以 `maxSubCallLimits_`（默认 `CS_CONFERENCE_MAX_CALLS_CNT = 5`，`ABILITY_CONFIG_SUPPORT` 下改取 carrier config）校验容量，超限返回 `CALL_ERR_CONFERENCE_CALL_EXCEED_LIMIT`。
#### Scenario: 会议主叫漂移
- **WHEN** `LeaveFromConference` 删除的恰是 `mainCallId_`
- **THEN** `mainCallId_` 改取 `*subCallIdSet_.begin()`；集合清空时 `mainCallId_ = ERR_ID`、`state_ = CONFERENCE_STATE_IDLE`、`beginTime_ = 0`

#### Scenario: 会议合并与失败回滚
- **WHEN** `CombineConference` 成功回调 `LaunchConference`（`JoinToConference` + `SetTelConferenceState(TEL_CONFERENCE_ACTIVE)`）或失败回调 `HandleCombineConferenceFailEvent`
- **THEN** 成功时会议进入 `TEL_CONFERENCE_ACTIVE`；失败时恢复 `GetOldConferenceState` 并以 `*subCallIdList.begin()` 重设主叫

### Requirement: IMS 视频升级状态机
系统 SHALL 在 `IMSCall::InitVideoCall()` 构建 `videoStateMap_`（`CALL_MODE_AUDIO_ONLY`/`SEND_ONLY`/`RECEIVE_ONLY`/`SEND_RECEIVE`/`VIDEO_PAUSED` 对应 `AudioOnlyState`/`VideoSendState`/`VideoReceiveState`/`VideoSendReceiveState`/`VideoPauseState`）；`UpdateImsCallMode` 仅 `CALL_STATUS_ACTIVE` 可执行，按 `GetVideoUpdateStatus()`（`STATUS_NONE`/`STATUS_RECV_REQUEST`）分发 `SendUpdateCallMediaModeRequest`/`SendUpdateCallMediaModeResponse` 到 `CellularCallConnection`。
#### Scenario: 视频升级请求被拒
- **WHEN** 非活动状态调用 `UpdateImsCallMode` 或对端响应升级失败
- **THEN** 升级被拒绝；响应失败时强制回落 `CALL_MODE_AUDIO_ONLY`

### Requirement: OTT 命令经回调代理转发
系统 SHALL 由 `OTTCall` 把接听/拒接/挂断/保持/切换/会议等命令经 `PackOttCallRequestInfo` 打包后由 `OTTCallConnection` 转交 `DelayedSingleton<CallAbilityReportProxy>::GetInstance()->OttCallRequest(OttCallRequestId::*, info)`；`GetSlotId()` 返回 `CALL_ERR_ILLEGAL_CALL_OPERATION`，`StartDtmf`/`StopDtmf`/`PostDialProceed`/`SetMute` 与全部视频接口返回 `CALL_ERR_FUNCTION_NOT_SUPPORTED`。
#### Scenario: OTT 接听命令下发
- **WHEN** 应用对 `OTTCall` 执行 `AnswerCall`
- **THEN** 以 `OTT_REQUEST_ANSWER` 经 `OttCallRequest` 回传 `com.ohos.callservice` 侧回调

### Requirement: VoIP 通话对象行为
系统 SHALL 由 `VoIPCall`（构造自 `DialParaInfo.voipCallInfo`，携带 `voipCallId_/userName_/abilityName_/extensionId_/voipBundleName_/uid_` 等）把 `AnswerCall`/`RejectCall`/`HangUpCall` 经 `PackVoipCallInfo` 后交 `VoipCallConnection` 同名接口；`HoldCall`/`UnHoldCall`/`SwitchCall` 与会议族空实现返回 `TELEPHONY_SUCCESS`；`GetOneCallObjectByVoipCallId(voipCallId, bundleName, uid)` 以三元组定位。
#### Scenario: VoIP 静音事件
- **WHEN** 对 `VoIPCall` 调用 `SetMute`
- **THEN** 以 `voipBundleName:uid:voipCallId` 组串经 `VoipCallConnection::SendCallUiEvent(voipCallId, CallAudioEvent::AUDIO_EVENT_MUTED/AUDIO_EVENT_UNMUTED)` 发送 UI 事件

### Requirement: 卫星与蓝牙通话对象差异
系统 SHALL 使 `SatelliteCall` 的 `HoldCall`/`UnHoldCall`/`SwitchCall`/`SetMute` 与会议族直接返回 `TELEPHONY_ERROR`；`BluetoothCall` 的 `AnswerCall`/`RejectCall`/`HangUpCall`/`StartDtmf` 直调 `Bluetooth::HandsFreeUnit::GetProfile()` 的 `AcceptIncomingCall/RejectIncomingCall/FinishActiveCall/SendDTMFTone`，Hold/Switch/会议族空返回 `TELEPHONY_SUCCESS`。
#### Scenario: 蓝牙 SCO 状态联动
- **WHEN** `BluetoothCallState::OnScoStateChanged` 收到 `HfpScoConnectState::SCO_CONNECTED/DISCONNECTED`
- **THEN** 经 `BluetoothCallConnection::SetBtCallScoConnected` 同步状态并由 `AudioDeviceManager::ReportAudioDeviceInfo` 上报音频设备变化
