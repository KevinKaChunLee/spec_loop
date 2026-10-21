# Spec Delta

## MODIFIED Requirements

### Requirement: 通话对象入表与去重
系统 SHALL 由 `CallObjectManager::AddOneCallObject` 将通话对象（`std::shared_ptr<CallBase>`，替代基线 `sptr`）加入静态列表 `callObjectPtrList_`：入表前遍历比对 `GetCallID()`，callId 已存在时 MUST 返回 `CALL_ERR_PHONE_CALL_ALREADY_EXISTS` 且不修改列表；表为空（`NO_CALL_EXIST`）时入表前 MUST 触发 `CallConnectAbility::ConnectAbility` 拉起通话界面——`CallConnectAbility` 经本 change 引入的打桩实现（连接回调以桩承接，不再经 `AbilityManagerClient`，见 call-control 能力「拉起通话界面」）；入表后列表长度为 1（`ONE_CALL_EXIST`）时 MUST NOT 调用 `CallWiredHeadSet::Init`（有线耳机不支持，联动移除），且若该对象 `TelCallState` 为 `CALL_STATUS_DIALING` 则置 `isFirstDialCallAdded_` 并 `cv_.notify_all`。基线「无 VoIP 振铃（或新对象 isEcc 为真）」条件随 VoIP 通话对象移除自然恒真，isEcc 旁路语义不再有实际分支。

#### Scenario: callId 重复入表被拒绝
- **WHEN** 对一个 callId 已存在于 `callObjectPtrList_` 的通话对象再次调用 `AddOneCallObject`
- **THEN** 返回 `CALL_ERR_PHONE_CALL_ALREADY_EXISTS`，列表长度不变

#### Scenario: 空表首个通话拉起通话界面
- **WHEN** 表为空（基线 VoIP 振铃条件随 VoIP 对象移除恒不成立）时调用 `AddOneCallObject`
- **THEN** `CallConnectAbility::ConnectAbility`（打桩实现）被触发，对象入表后列表长度为 1，且 `CallWiredHeadSet::Init` 不被调用（有线耳机不支持）

#### Scenario: 首个拨号通话唤醒等待者
- **WHEN** 入表后列表长度为 1 且队首对象 `GetTelCallState()` 为 `CALL_STATUS_DIALING`
- **THEN** `isFirstDialCallAdded_` 置真并 `cv_.notify_all`，阻塞在条件变量上的等待者被唤醒

### Requirement: 六类通话对象按类型构造
系统 SHALL 由 `CallStatusManager::CreateNewCallByCallType` / `CreateNewCallByCallTypeEx` 按 `CallType` 构造通话对象，仅保留 `TYPE_CS`→`CSCall`、`TYPE_IMS`→`IMSCall` 两类：方向为 `CALL_DIRECTION_OUT` 时使用带 extras 的构造重载（基线 `AppExecFwk::PacMap` extras 以结构体替换）；`TYPE_OTT` / `TYPE_VOIP` / `TYPE_SATELLITE` / `TYPE_BLUETOOTH` 及未知类型 MUST NOT 构造对象，落入与基线未知类型一致的 default 分支返回 nullptr（基线无对应错误码，以空指针为实际返回值），不产生 `OTTCall` / `VoIPCall` / `SatelliteCall` / `BluetoothCall` 对象；IMS 对象构造后不再调用 `InitVideoCall`（视频通话不支持，见「IMS/OTT/VoIP 通话对象差异」）。

#### Scenario: 呼出使用 extras 构造
- **WHEN** `CallDetailInfo.callType` 为 `TYPE_CS` 且方向为 `CALL_DIRECTION_OUT`
- **THEN** 以 `(DialParaInfo, extras)` 构造 `CSCall`；方向为呼入时以 `(DialParaInfo)` 构造

#### Scenario: IMS 对象构造后初始化视频状态
- **WHEN** `callType` 为 `TYPE_IMS` 的对象构造完成
- **THEN** `InitVideoCall` 不被调用（视频通话不支持），不建立 `videoStateMap_`，对象恒按语音通话处理

#### Scenario: OTT/VoIP/卫星/蓝牙类型不构造对象
- **WHEN** `callType` 为 `TYPE_OTT` / `TYPE_VOIP` / `TYPE_SATELLITE` / `TYPE_BLUETOOTH` 时调用 `CreateNewCallByCallType`
- **THEN** 返回 nullptr，不产生对应类型通话对象

#### Scenario: 未知类型返回空
- **WHEN** `callType` 不属于已知 `CallType`
- **THEN** `CreateNewCallByCallType` 返回 nullptr，不产生通话对象

### Requirement: CarrierCall 蜂窝通道行为
系统 SHALL 由 `CarrierCall` 执行蜂窝操作，通道调用由基线 `CellularCallConnection` 改为本 change 引入的 `CellularCallClient::GetInstance().Xxx()`（stub/ 打桩，方法名对齐 cellular_call 接口：Dial / Answer / Reject / HangUp / HoldCall / UnHoldCall / SwitchCall 等）：`CarrierDialingProcess`（失败时调 `CarrierHangUpCall`）、`CarrierAnswerCall`（先 `AnswerCallBase`）、`CarrierRejectCall`（经 `CallSupplementType::TYPE_DEFAULT` 挂断）、`CarrierHoldCall` / `CarrierUnHoldCall` / `CarrierSwitchCall`；`CarrierHangUpCall` 依据 `GetPolicyFlag()` 选择挂断补充类型（`POLICY_FLAG_HANG_UP_ACTIVE`→`TYPE_HANG_UP_ACTIVE`、`POLICY_FLAG_HANG_UP_HOLD_WAIT`→`TYPE_HANG_UP_HOLD_WAIT`、否则 `TYPE_DEFAULT`）并经 `CellularCallClient::GetInstance().HangUp` 下发；`GetEmergencyState` 返回 `isEcc_`；`GetCallAttributeCarrierInfo` 在 `GetCallAttributeBaseInfo` 基础上补充 isEcc/accountId/index。

#### Scenario: CSCall 全量委托 CarrierCall
- **WHEN** 对 `CSCall` 调用 `DialingProcess` / `AnswerCall` / `RejectCall` / `HangUpCall` / `HoldCall` / `UnHoldCall` / `SwitchCall`
- **THEN** 分别转发到 `CarrierDialingProcess` / `CarrierAnswerCall` / `CarrierRejectCall` / `CarrierHangUpCall` / `CarrierHoldCall` / `CarrierUnHoldCall` / `CarrierSwitchCall`

#### Scenario: 挂断补充类型按 policyFlag 选择
- **WHEN** `CarrierHangUpCall` 执行且 `GetPolicyFlag()` 含 `POLICY_FLAG_HANG_UP_ACTIVE`
- **THEN** 经 `CellularCallClient::GetInstance().HangUp` 以 `CallSupplementType::TYPE_HANG_UP_ACTIVE` 挂断；无任何 policyFlag 时用 `TYPE_DEFAULT`

#### Scenario: 紧急通话判定
- **WHEN** 以 `isEcc_` 为真构造的 `CarrierCall` 调用 `GetEmergencyState`
- **THEN** 返回 true，`GetCallAttributeCarrierInfo` 填充的 `CallAttributeInfo.isEcc` 为真

### Requirement: IMS/OTT/VoIP 通话对象差异
系统 SHALL 仅保留 IMS 通话对象行为：`IMSCall` 多重继承 `NetCallBase`，视频相关能力 MUST 移除——`InitVideoCall` / `videoCallState_` 状态机与 `DispatchUpdateVideoRequest` / `DispatchUpdateVideoResponse` / `DispatchReportVideoCallInfo` 媒体模式协商分发、`UpdateImsCallMode` / `SwitchVideoState` / `IsSupportVideoCall` 均不再提供，IMS 通话对象恒为语音（`GetVideoStateType()` 恒为 `TYPE_VOICE`）；`StartRtt` / `StopRtt` 接口保留，RTT 文件节点通路调用点以 todo 占位（依赖通路接口适配）。`OTTCall` 连接转发（`ottCallConnectionPtr_` / `OTTCallConnection` / `PackOttCallRequestInfo`）与 VoIP 双轨管理（`voipCallObjectList_` / `AddOneVoipCallObject` / `DeleteOneVoipCallObject` / `UpdateOneVoipCallObjectByCallId` / `GetOneCallObjectByVoipCallId`、`HangUpCall(const ErrorReason&)` 重载与 `GetVoipCallId` / `GetVoipBundleName` / `GetVoipUid` / `UpdateCallAttributeInfo`）MUST NOT 迁移。

#### Scenario: IMS 通话恒为语音
- **WHEN** `CreateNewCallByCallType` 构造 `TYPE_IMS` 对象后查询其视频态
- **THEN** `InitVideoCall` 未被调用，`GetVideoStateType()` 返回 `TYPE_VOICE`，媒体模式协商分发接口不存在

#### Scenario: OTT 控制请求经连接转发
- **WHEN** 以 `TYPE_OTT` 的 `CallDetailInfo` 请求构造通话对象并对其发起 `AnswerCall` 等控制请求
- **THEN** OTT 对象不构造（`CreateNewCallByCallType` 返回 nullptr），`ottCallConnectionPtr_` / `OTTCallConnection` / `PackOttCallRequestInfo` 转发链路不存在，控制请求无处转发、不产生 `CALL_ERR_ANSWER_FAILED` 返回路径

#### Scenario: VoIP 属性表按 callId 键管理
- **WHEN** 以同一 `CallAttributeInfo.callId` 两次发起 VoIP 对象入表请求
- **THEN** `AddOneVoipCallObject` 与 `voipCallObjectList_` 不存在（VoIP 双轨管理移除），无按 callId 键重复入表返回 `CALL_ERR_PHONE_CALL_ALREADY_EXISTS` 的 VoIP 路径；通话对象仅由 `callObjectPtrList_` 管理，重复 callId 由 `AddOneCallObject` 返回 `CALL_ERR_PHONE_CALL_ALREADY_EXISTS`

#### Scenario: IMS 媒体模式协商分发
- **WHEN** 对 `IMSCall` 请求 `SendUpdateCallMediaModeRequest(mode)`（ImsCallMode 媒体模式协商）
- **THEN** 协商不触发：`videoCallState_` 状态机与 `DispatchUpdateVideoRequest` / `DispatchUpdateVideoResponse` / `DispatchReportVideoCallInfo` 分发接口不再提供，IMS 通话恒为语音（`GetVideoStateType()` 恒为 `TYPE_VOICE`）

#### Scenario: OTT/VoIP 对象与双轨表不再存在
- **WHEN** 以 `TYPE_OTT` / `TYPE_VOIP` 的 `CallDetailInfo` 走 `CreateNewCallByCallType`，随后查询 `voipCallObjectList_`
- **THEN** 返回 nullptr 不构造对象，`voipCallObjectList_` 无任何条目（双轨管理随特性移除）

## REMOVED Requirements

### Requirement: 卫星与蓝牙通话差异
**Reason**: 卫星通话与 BLUETOOTH 类型通话不支持，satellite_call.cpp、bluetooth_call.cpp、bluetooth_call_state.cpp 不迁移。
**Migration**: 无替代；对应 callType 不构造对象（见「六类通话对象按类型构造」）。

### Requirement: 会议对象管理
**Reason**: 会议通话不支持，conference_base.cpp、cs_conference.cpp、ims_conference.cpp、ott_conference.cpp 不迁移。
**Migration**: 无替代；会议入口（CombineConference 等）不再提供，见 call-control delta。