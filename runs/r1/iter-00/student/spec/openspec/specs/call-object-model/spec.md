# Call Object Model Specification

## Purpose
描述 OpenHarmony v6.0-Release telephony_call_manager 的通话对象模型基线现状：`CallBase` 为抽象基类，`CarrierCall` 继承 `CallBase` 并进一步派生出 `CSCall` / `IMSCall` / `VoIPCall` / `SatelliteCall` / `BluetoothCall`，`OTTCall` 直接继承 `CallBase` 与 `NetCallBase`；会议对象由 `ConferenceBase` 派生出 `CsConference` / `ImsConference` / `OttConference`；全部通话对象由 `CallObjectManager` 的静态表（`callObjectPtrList_` / `voipCallObjectList_`）统一管理（入表 / 查找 / 删除 / callId 自增），对象构造入口为 `call_status_manager.cpp` 的 `CreateNewCallByCallType` / `CreateNewCallByCallTypeEx`。源码落点：`telephony_call_manager/services/call/{include,src}` 的 `call_base.cpp`、`carrier_call.cpp`、`net_call_base.cpp`、`cs_call.cpp`、`ims_call.cpp`、`ott_call.cpp`、`voip_call.cpp`、`satellite_call.cpp`、`bluetooth_call.cpp`、`bluetooth_call_state.cpp`、`video_call_state.cpp`、`conference_base.cpp`、`cs_conference.cpp`、`ims_conference.cpp`、`ott_conference.cpp`、`call_object_manager.cpp`。相关编译开关：`NOT_SUPPORT_MULTICALL`（`BUILD.gn` 的 `call_manager_feature_not_support_multicall`，默认 false，出现在 `call_object_manager.h` / `call_object_manager.cpp`，将新建通话的载波通话上限降为 1）、`ABILITY_CONFIG_SUPPORT`（`callmanager.gni`，`CsConference` / `ImsConference` 读取子通话数上限配置）、`ABILITY_BLUETOOTH_SUPPORT`（`callmanager.gni`）。本规格只描述基线现状，不含移植/裁剪决策。

## Requirements

### Requirement: 通话对象入表与去重
系统 SHALL 由 `CallObjectManager::AddOneCallObject` 将通话对象加入静态列表 `callObjectPtrList_`：入表前遍历比对 `GetCallID()`，callId 已存在时 MUST 返回 `CALL_ERR_PHONE_CALL_ALREADY_EXISTS` 且不修改列表；表为空（`NO_CALL_EXIST`）且不存在 VoIP 振铃（或新对象 `isEcc` 为真）时入表前 MUST 触发 `CallConnectAbility::ConnectAbility` 拉起通话界面；入表后列表长度为 1（`ONE_CALL_EXIST`）时 MUST 调用 `CallWiredHeadSet::Init`，且若该对象 `TelCallState` 为 `CALL_STATUS_DIALING` 则置 `isFirstDialCallAdded_` 并 `cv_.notify_all`。
#### Scenario: callId 重复入表被拒绝
- **WHEN** 对一个 callId 已存在于 `callObjectPtrList_` 的通话对象再次调用 `AddOneCallObject`
- **THEN** 返回 `CALL_ERR_PHONE_CALL_ALREADY_EXISTS`，列表长度不变
#### Scenario: 空表首个通话拉起通话界面
- **WHEN** 表为空、无 VoIP 通话处于 `CallStateToApp::CALL_STATE_RINGING` 时调用 `AddOneCallObject`
- **THEN** `CallConnectAbility::ConnectAbility` 被触发，对象入表后列表长度为 1 且 `CallWiredHeadSet::Init` 被调用
#### Scenario: 首个拨号通话唤醒等待者
- **WHEN** 入表后列表长度为 1 且队首对象 `GetTelCallState()` 为 `CALL_STATUS_DIALING`
- **THEN** `isFirstDialCallAdded_` 置真并 `cv_.notify_all`，阻塞在条件变量上的等待者被唤醒

### Requirement: callId 自增分配与对象删除
系统 SHALL 由 `CallObjectManager::GetNewCallId` 对静态计数 `callId_` 自增（`++callId_`）并返回新值供 `call_status_manager.cpp` 填入 `DialParaInfo.callId`，通话删除后 callId MUST NOT 回退复用；`DeleteOneCallObject` 按 callId 从列表移除对象，表清空时 MUST 调用 `CallWiredHeadSet::DeInit`，且在 `CallControlManager::ShouldDisconnectService` 为真时经 `DelayedDisconnectCallConnectAbility`（ffrt 延时 `DISCONNECT_DELAY_TIME` = 2000000 微秒）断开通话界面。
#### Scenario: callId 单调递增
- **WHEN** 连续两次调用 `GetNewCallId`，中间执行一次 `DeleteOneCallObject`
- **THEN** 第二次返回值仍比第一次大 1，被删除通话的 callId 不被复用
#### Scenario: 最后一个通话删除后延时断连
- **WHEN** `DeleteOneCallObject` 使 `callObjectPtrList_` 清空且 `ShouldDisconnectService()` 为真
- **THEN** `CallWiredHeadSet::DeInit` 被调用，并在约 2 秒延时后对通话界面执行 `DisconnectAbility`

### Requirement: 并发呼叫数上限
系统 SHALL 用 `CallObjectManager::HasNewCall` 在已存在 `CALL_RUNNING_STATE_CREATE` / `CALL_RUNNING_STATE_CONNECTING` / `CALL_RUNNING_STATE_DIALING` 状态通话（或卫星通话）时拒绝新呼叫（`CALL_ERR_CALL_COUNTS_EXCEED_LIMIT`）；用 `IsNewCallAllowedCreate` 判定可否新建：存在上述状态或 `CALL_RUNNING_STATE_RINGING` 的非 VoIP 通话时 enabled 为 false，且载波通话数（会议计 1）达到上限时 enabled 为 false——未定义 `NOT_SUPPORT_MULTICALL` 时上限为 2，定义时为 1；`HasRingingMaximum` 以 `RINGING_CALL_NUMBER_LEN`（30）为振铃上限，`HasDialingMaximum` 实际统计 ACTIVE 状态通话数、以 `DIALING_CALL_NUMBER_LEN`（30）为上限。
#### Scenario: 已有拨号中通话时再拨被拒
- **WHEN** 存在一个 `CallRunningState` 为 `CALL_RUNNING_STATE_DIALING` 的通话时调用 `HasNewCall`
- **THEN** 返回 `CALL_ERR_CALL_COUNTS_EXCEED_LIMIT`
#### Scenario: NOT_SUPPORT_MULTICALL 下单载波通话即满
- **WHEN** 定义 `NOT_SUPPORT_MULTICALL`、已存在 1 个非会议的 CS/IMS/卫星/蓝牙通话时调用 `IsNewCallAllowedCreate`
- **THEN** enabled 为 false；未定义该宏且仅有 1 个载波通话时 enabled 为 true
#### Scenario: 振铃数达上限
- **WHEN** `CALL_RUNNING_STATE_RINGING` 状态的通话数达到 30
- **THEN** `HasRingingMaximum` 返回 true

### Requirement: 六类通话对象按类型构造
系统 SHALL 由 `CallStatusManager::CreateNewCallByCallType` / `CreateNewCallByCallTypeEx` 按 `CallType` 构造通话对象：`TYPE_CS`→`CSCall`、`TYPE_IMS`→`IMSCall`（构造后调用 `InitVideoCall`）、`TYPE_OTT`→`OTTCall`、`TYPE_VOIP`→`VoIPCall`、`TYPE_SATELLITE`→`SatelliteCall`、`TYPE_BLUETOOTH`→`BluetoothCall`（macAddress 取自 `BluetoothCallConnection::GetMacAddress`）；方向为 `CALL_DIRECTION_OUT` 时使用带 `AppExecFwk::PacMap` extras 的构造重载；未知类型 MUST 返回 nullptr。
#### Scenario: 呼出使用 extras 构造
- **WHEN** `CallDetailInfo.callType` 为 `TYPE_CS` 且方向为 `CALL_DIRECTION_OUT`
- **THEN** 以 `(DialParaInfo, AppExecFwk::PacMap)` 构造 `CSCall`；方向为呼入时以 `(DialParaInfo)` 构造
#### Scenario: IMS 对象构造后初始化视频状态
- **WHEN** `callType` 为 `TYPE_IMS` 的对象构造完成
- **THEN** `InitVideoCall` 被调用，建立 `videoStateMap_` 中各 `ImsCallMode` 对应的 `VideoCallState`
#### Scenario: 未知类型返回空
- **WHEN** `callType` 不属于六种已知 `CallType`
- **THEN** `CreateNewCallByCallType` 返回 nullptr，不产生通话对象

### Requirement: CallBase 控制接口与状态迁移
系统 SHALL 在 `CallBase` 声明纯虚控制接口 `DialingProcess` / `AnswerCall` / `RejectCall` / `HangUpCall` / `HoldCall` / `UnHoldCall` / `SwitchCall` / `CombineConference` / `SeparateConference` / `KickOutFromConference` / `CanCombineConference` / `CanSeparateConference` / `CanKickOutFromConference` / `LaunchConference` / `ExitConference` / `HoldConference` / `StartDtmf` / `StopDtmf` / `PostDialProceed`，由六类子类实现；公共实现 `DialCallBase` 将 `callRunningState_` 置为 `CALL_RUNNING_STATE_CONNECTING` 并经 ffrt 异步执行 `HangUpVoipCall`；`SetTelCallState` 按目标状态经 `StateChangesToActive` / `StateChangesToHolding` / `StateChangesToDialing` 等私有函数完成状态迁移；`GetCallID` / `GetCallType` / `GetTelCallState` / `GetCallRunningState` 提供状态查询。
#### Scenario: 拨号基线置连接态
- **WHEN** 子类 `DialingProcess` 内部调用 `DialCallBase`
- **THEN** `GetCallRunningState()` 返回 `CALL_RUNNING_STATE_CONNECTING`，且已有 VoIP 通话被异步挂断（`HangUpVoipCall`）
#### Scenario: 状态迁移走内部迁移函数
- **WHEN** 对通话对象调用 `SetTelCallState(TelCallState::CALL_STATUS_ACTIVE)`
- **THEN** 内部经 `StateChangesToActive` 完成迁移，`GetTelCallState()` 返回 `CALL_STATUS_ACTIVE` 且运行态同步更新
#### Scenario: 状态查询返回构造填充值
- **WHEN** 对象以 `DialParaInfo`（含 callId/callType/videoState/number）构造后调用 `GetCallID` / `GetCallType`
- **THEN** 分别返回构造时填充的 callId 与 callType

### Requirement: CarrierCall 蜂窝通道行为
系统 SHALL 由 `CarrierCall` 通过 `CellularCallConnection` 执行蜂窝操作：`CarrierDialingProcess`（失败时调 `CarrierHangUpCall`）、`CarrierAnswerCall`（先 `AnswerCallBase`）、`CarrierRejectCall`（经 `CallSupplementType::TYPE_DEFAULT` 挂断）、`CarrierHoldCall` / `CarrierUnHoldCall` / `CarrierSwitchCall`；`CarrierHangUpCall` 依据 `GetPolicyFlag()` 选择挂断补充类型（`POLICY_FLAG_HANG_UP_ACTIVE`→`TYPE_HANG_UP_ACTIVE`、`POLICY_FLAG_HANG_UP_HOLD_WAIT`→`TYPE_HANG_UP_HOLD_WAIT`、否则 `TYPE_DEFAULT`）；`GetEmergencyState` 返回 `isEcc_`；`GetCallAttributeCarrierInfo` 在 `GetCallAttributeBaseInfo` 基础上补充 isEcc/accountId/index。
#### Scenario: CSCall 全量委托 CarrierCall
- **WHEN** 对 `CSCall` 调用 `DialingProcess` / `AnswerCall` / `RejectCall` / `HangUpCall` / `HoldCall` / `UnHoldCall` / `SwitchCall`
- **THEN** 分别转发到 `CarrierDialingProcess` / `CarrierAnswerCall` / `CarrierRejectCall` / `CarrierHangUpCall` / `CarrierHoldCall` / `CarrierUnHoldCall` / `CarrierSwitchCall`
#### Scenario: 挂断补充类型按 policyFlag 选择
- **WHEN** `CarrierHangUpCall` 执行且 `GetPolicyFlag()` 含 `POLICY_FLAG_HANG_UP_ACTIVE`
- **THEN** 经 `CellularCallConnection` 以 `CallSupplementType::TYPE_HANG_UP_ACTIVE` 挂断；无任何 policyFlag 时用 `TYPE_DEFAULT`
#### Scenario: 紧急通话判定
- **WHEN** 以 `isEcc_` 为真构造的 `CarrierCall` 调用 `GetEmergencyState`
- **THEN** 返回 true，`GetCallAttributeCarrierInfo` 填充的 `CallAttributeInfo.isEcc` 为真

### Requirement: IMS/OTT/VoIP 通话对象差异
系统 SHALL：`IMSCall` 多重继承 `NetCallBase`，持有 `videoCallState_`（`VideoCallState` 状态机，媒体模式协商经 `DispatchUpdateVideoRequest` / `DispatchUpdateVideoResponse` / `DispatchReportVideoCallInfo` 分发），提供 `StartRtt` / `StopRtt` / `UpdateImsCallMode` / `SwitchVideoState` / `IsSupportVideoCall`；`OTTCall` 经 `ottCallConnectionPtr_`（`OTTCallConnection`）以 `PackOttCallRequestInfo` 打包后转发 Answer/Reject/HangUp/Hold/UnHold；`VoIPCall` 除 `callObjectPtrList_` 外还由 `voipCallObjectList_`（`std::map<int32_t, CallAttributeInfo>`）经 `AddOneVoipCallObject` / `DeleteOneVoipCallObject` / `UpdateOneVoipCallObjectByCallId` / `GetOneCallObjectByVoipCallId` 管理，提供 `HangUpCall(const ErrorReason&)` 重载与 `GetVoipCallId` / `GetVoipBundleName` / `GetVoipUid` / `UpdateCallAttributeInfo`。
#### Scenario: OTT 控制请求经连接转发
- **WHEN** 对 `OTTCall` 调用 `AnswerCall`（`AnswerCallBase` 成功后）
- **THEN** 经 `PackOttCallRequestInfo` 打包并由 `ottCallConnectionPtr_->Answer` 转发，失败返回 `CALL_ERR_ANSWER_FAILED`
#### Scenario: VoIP 属性表按 callId 键管理
- **WHEN** 以同一 `CallAttributeInfo.callId` 两次调用 `AddOneVoipCallObject`
- **THEN** 第一次返回 `TELEPHONY_SUCCESS` 并写入 `voipCallObjectList_`，第二次返回 `CALL_ERR_PHONE_CALL_ALREADY_EXISTS`
#### Scenario: IMS 媒体模式协商分发
- **WHEN** 对 `IMSCall` 调用 `SendUpdateCallMediaModeRequest(mode)`
- **THEN** 经当前 `videoCallState_` 的 `DispatchUpdateVideoRequest` 完成请求分发

### Requirement: 卫星与蓝牙通话差异
系统 SHALL：`SatelliteCall` 的 `DialingProcess` / `AnswerCall` / `RejectCall` / `HangUpCall` 委托 `CarrierCall` 对应 `Carrier*` 方法，而 `HoldCall` / `UnHoldCall` / `SwitchCall` / `SetMute` 及全部会议接口（`CombineConference` / `SeparateConference` / `KickOutFromConference` / `CanCombineConference` / `CanSeparateConference` / `CanKickOutFromConference` / `LaunchConference` / `ExitConference` / `HoldConference` / `GetMainCallId` / `GetSubCallIdList` / `GetCallIdListForConference` / `IsSupportConferenceable`）MUST 恒返回 `TELEPHONY_ERROR`；`BluetoothCall` 经 `Bluetooth::HandsFreeUnit::GetProfile` 对 `macAddress_` 设备执行 `AcceptIncomingCall` / `RejectIncomingCall` / `FinishActiveCall`，`DialingProcess` 直接返回 `TELEPHONY_SUCCESS` 不下发拨号；`BluetoothCallState` 以 `OnConnectionStateChanged` / `OnScoStateChanged` 更新 `BluetoothCallConnection` 的 HFP / Sco 连接标志。
#### Scenario: 卫星通话不支持保持与会议
- **WHEN** 对 `SatelliteCall` 调用 `HoldCall` 或 `CombineConference`
- **THEN** 均返回 `TELEPHONY_ERROR`
#### Scenario: 蓝牙应答走 HFP profile
- **WHEN** 对 `BluetoothCall` 调用 `AnswerCall(videoState)`
- **THEN** 经 `Bluetooth::HandsFreeUnit::GetProfile` 对 `macAddress_` 设备 `AcceptIncomingCall` 并返回 `TELEPHONY_SUCCESS`
#### Scenario: 蓝牙连接状态同步
- **WHEN** HFP SCO 状态变为 `SCO_CONNECTED` 触发 `BluetoothCallState::OnScoStateChanged`
- **THEN** `BluetoothCallConnection::SetBtCallScoConnected(true)` 被调用并上报音频设备信息

### Requirement: 会议对象管理
系统 SHALL 由 `ConferenceBase` 维护 `mainCallId_` 与 `subCallIdSet_`（`GetMainCall` / `SetMainCall` / `GetSubCallIdList` / `GetCallIdListForConference`），由 `CsConference` / `ImsConference` / `OttConference` 分别实现 `JoinToConference` / `LeaveFromConference` / `HoldConference` / `CanCombineConference` / `CanSeparateConference` / `CanKickOutFromConference`；`ImsConference::JoinToConference` 仅在 `state_` 为 `CONFERENCE_STATE_CREATING` / `CONFERENCE_STATE_ACTIVE` / `CONFERENCE_STATE_LEAVING` / `CONFERENCE_STATE_HOLDING` 时允许并把 `state_` 置 `CONFERENCE_STATE_ACTIVE`；`LeaveFromConference` 在子集清空时将 `mainCallId_` 置 `ERR_ID`、`state_` 置 `CONFERENCE_STATE_IDLE`；子通话上限 `maxSubCallLimits_` 默认 `CS_CONFERENCE_MAX_CALLS_CNT`（5），定义 `ABILITY_CONFIG_SUPPORT` 时从配置读取。
#### Scenario: IMS 并入会议需状态合法
- **WHEN** `ImsConference` 的 `state_` 为 `CONFERENCE_STATE_IDLE` 时调用 `JoinToConference(callId)`
- **THEN** 返回 `CALL_ERR_ILLEGAL_CALL_OPERATION`；`state_` 为 ACTIVE 时调用则 callId 插入 `subCallIdSet_` 且返回 `TELEPHONY_SUCCESS`
#### Scenario: 会议成员清空即解散
- **WHEN** `LeaveFromConference` 移除后 `subCallIdSet_` 为空
- **THEN** `GetMainCall()` 返回 `ERR_ID`，`GetConferenceState()` 返回 `CONFERENCE_STATE_IDLE`，`beginTime_` 清零
#### Scenario: 子通话数达上限拒绝并入
- **WHEN** `CsConference` 的 `subCallIdSet_.size()` 达到 `maxSubCallLimits_`（默认 5）
- **THEN** 再并入通话被拒绝
