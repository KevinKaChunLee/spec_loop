# Telephony Interaction Specification

## Purpose
描述 HMOS `telephony_call_manager` 与其它 telephony 模块/系统服务交互能力的移植前现状：对 cellular_call 的下行远程调用与 SA 连接/重连，对 core_service 的 FDN 查询，cellular_call 回调的上行入口（IPC stub 分发）与单队列串行化处理（`ReportCallInfoHandler`），对 voip_call_manager 系统服务的连接与 UI 事件请求，对蓝牙通话框架（`Bluetooth::HandsFreeUnit`）的连接。源码落点：`telephony_call_manager/services/telephony_interaction/src/{cellular_call_connection, core_service_connection, call_status_callback, call_status_callback_stub, report_call_info_handler, voip_call_connection, bluetooth_call_connection}.cpp`。控制本能力的构建开关：`ABILITY_CELLULAR_SUPPORT`（`callmanager.gni` 在 `global_parts_info.telephony_cellular_call` 部件存在时定义，`#ifdef` 场点为 `cellular_call_connection.cpp` 的 `ReConnectService`）；`RECONNECT_MAX_TRY_COUNT`（`#ifdef` 场点为 `cellular_call_connection.cpp` 头部，仅包住常量 `CONNECT_MAX_TRY_COUNT = 5`，该常量仓内无使用点，不构成重试行为，重连实际语义见下）。本规格只描述现状，不涉及任何裁剪决策；本能力所有外部出口（cellular_call/core_service/voip SA 代理、蓝牙 profile、IPC stub）均为移植时的桩化对象。

## Requirements

### Requirement: cellular_call SA 连接、回调注册与重连
系统 SHALL 由 `CellularCallConnection`（`cellular_call_connection.cpp`，DelayedSingleton）以 `TELEPHONY_CELLULAR_CALL_SYS_ABILITY_ID` 连接 cellular_call SA：`ConnectService` 在 `ffrt::shared_mutex`（clientLock_）下经 `SystemAbilityManagerClient::GetInstance().GetSystemAbilityManager()` → `GetSystemAbility(systemAbilityId_)` → `iface_cast<CellularCallInterface>` 获取 `cellularCallInterfacePtr_`，随后 `RegisterCallBackFun` 创建 `CallStatusCallback`（`std::make_unique<...>().release()`）并调 `RegisterCallManagerCallBack(cellularCallCallbackPtr_)`，失败时 `Clean`（UnRegisterCallBack + 清空两个 sptr + `connectState_ = false`）。`Init` SHALL 另创建 `SystemAbilityListener` 并 `SubscribeSystemAbility`；`OnAddSystemAbility` 在未连接时 `Clean` → `ReConnectService` → `ClearAllCalls`，`OnRemoveSystemAbility` 在已连接时 `Clean`。`ReConnectService` SHALL 仅在 `#ifdef ABILITY_CELLULAR_SUPPORT` 下、且代理为空时执行一次 `ConnectService`（单次重连，宏未定义时直接返回成功）；`#ifdef RECONNECT_MAX_TRY_COUNT` 头部常量 `CONNECT_MAX_TRY_COUNT`（5）仓内无使用点，不构成任何重试计数行为。

#### Scenario: 服务未启动时下行调用
- **WHEN** cellular_call SA 尚未注册（`GetSystemAbility` 返回空）
- **THEN** `ConnectService` 返回 `TELEPHONY_ERR_IPC_CONNECT_STUB_FAIL`，代理为空、`connectState_` 为 false；后续每次业务调用经 `ReConnectService` 单次重试连接，失败返回 `TELEPHONY_ERR_IPC_CONNECT_STUB_FAIL`

#### Scenario: 服务上线监听重连
- **WHEN** cellular_call SA 后注册、`OnAddSystemAbility` 触发且 `IsConnect()` 为 false
- **THEN** `Clean` 后 `ReConnectService` 重连成功，并调 `ClearAllCalls` 向对端同步本端在途通话（组包后 sleep `DELAY_TIME` 100ms 再发）

#### Scenario: 服务下线清理
- **WHEN** `OnRemoveSystemAbility` 触发且当前已连接
- **THEN** `Clean` 注销回调并清空代理，`connectState_` 复位为 false

### Requirement: 呼叫控制下行出口
系统 SHALL 由 `CellularCallConnection` 的 `Dial/HangUp/Reject/Answer/HoldCall/UnHoldCall/SwitchCall` 提供呼叫控制远程调用：每个方法先过 `ReConnectService`（失败即返回 `TELEPHONY_ERR_IPC_CONNECT_STUB_FAIL`，Dial/HangUp/Reject/Answer 并经 `CallManagerHisysevent::WriteDialCallFaultEvent/WriteHangUpFaultEvent/WriteAnswerCallFaultEvent` 记故障事件），再调 `cellularCallInterfacePtr_` 的同名远程接口（`Dial(CellularCallInfo)`、`HangUp(callInfo, CallSupplementType)`、`Reject`、`Answer`、`HoldCall`、`UnHoldCall`、`SwitchCall`），非成功返回码原样透传。

#### Scenario: 拨号成功
- **WHEN** `Dial(callInfo)` 且代理已连
- **THEN** 远程 `Dial` 返回 0 时透传成功；非 0 时记录 errCode 日志并透传

#### Scenario: 挂断失败带故障事件
- **WHEN** `HangUp` 前的重连失败
- **THEN** `WriteHangUpFaultEvent` 以 `TELEPHONY_ERR_IPC_CONNECT_STUB_FAIL`/“HangUp ipc reconnect failed” 记录并返回该错误码

### Requirement: 补充业务与 MMI/USSD 下行出口
系统 SHALL 由 `CellularCallConnection` 提供补充业务（UT/USSI/USSD/MMI）远程调用：`SetCallTransferInfo/CanSetCallTransferTime/GetCallTransferInfo`、`SetCallWaiting/GetCallWaiting/GetVideoCallWaiting`、`SetCallRestriction/GetCallRestriction/SetCallRestrictionPassword`、`GetCallWaiting` 族、`SetCallPreferenceMode`、`SetImsSwitchStatus/GetImsSwitchStatus`、`GetCarrierVtConfig`、`SetVoNRState/GetVoNRState`、`SetImsConfig`（两重载）/`GetImsConfig`、`SetImsFeatureValue/GetImsFeatureValue`、`SendUssdResponse(slotId, content)`、`CloseUnFinishedUssd`、`IsMmiCode(slotId, number)`、`IsEmergencyPhoneNumber(slotId, phoneNum, enabled)`。各方法 SHALL 统一以 `ReConnectService` 前置，失败返回 `TELEPHONY_ERR_IPC_CONNECT_STUB_FAIL`，其余返回码透传。

#### Scenario: USSD 应答回发
- **WHEN** 用户在 USSD 会话中应答、`SendUssdResponse` 被调用
- **THEN** 重连成功后调远程 `SendUssdResponse(slotId, content)`，非 0 返回码透传

#### Scenario: MMI 码判定
- **WHEN** 拨号串需判定是否为功能码、`IsMmiCode(slotId, number)` 被调用
- **THEN** 由远程 `IsMmiCode` 的返回值决定（bool 透传；重连失败时返回错误码值）

### Requirement: 会议、视频与 RTT 下行出口
系统 SHALL 由 `CellularCallConnection` 集中提供会议与视频类远程调用（移植时预计整体裁剪/桩化）：`CombineConference/SeparateConference/KickOutFromConference/InviteToConference`、`ControlCamera/SetPreviewWindow/SetDisplayWindow/SetCameraZoom/SetPausePicture/SetDeviceDirection`、`SendUpdateCallMediaModeRequest/SendUpdateCallMediaModeResponse`、`CancelCallUpgrade/RequestCameraCapabilities`、`StartRtt/StopRtt`、`GetVideoCallWaiting`。各方法 SHALL 与其它下行出口共用 `ReConnectService` 前置与错误码透传约定。

#### Scenario: 合并会议
- **WHEN** `CombineConference(callInfo)` 被调用
- **THEN** 远程 `CombineConference` 被调用，结果码透传；重连失败返回 `TELEPHONY_ERR_IPC_CONNECT_STUB_FAIL`

#### Scenario: 视频模式升级请求
- **WHEN** `SendUpdateCallMediaModeRequest` 被调用
- **THEN** 远程同名接口被调用，对端响应经 `CallStatusCallback::ReceiveUpdateCallMediaModeResponse` 上行（见 CallStatusCallback 条）

### Requirement: DTMF 与其它杂项下行出口
系统 SHALL 由 `CellularCallConnection` 提供 DTMF 与杂项远程调用：`StartDtmf/StopDtmf/SendDtmf/SendDtmfString/PostDialProceed`、`SetMute`、`RegisterCallBack/UnRegisterCallBack`（本端回调注册生命周期）、`ClearAllCalls`（遍历本端在途通话组包 `callsInfo`，`std::this_thread::sleep_for(DELAY_TIME=100ms)` 后调远程 `ClearAllCalls(callsInfo)`；`callsInfo` 为空返回 `TELEPHONY_ERR_ARGUMENT_INVALID`）。所有方法 SHALL 保持统一的 `ReConnectService` 前置与返回码透传。

#### Scenario: 后拨字符上报
- **WHEN** 对端通知后拨序列、`PostDialProceed` 被调用
- **THEN** 远程 `PostDialProceed` 被调用，结果码透传

#### Scenario: 服务上线后的通话同步
- **WHEN** SA 重连成功后 `ClearAllCalls` 被调用且本端有在途通话
- **THEN** 逐通组包（slotId/accountId/callType/videoState/index/phoneNum）后延迟 100ms 调远程 `ClearAllCalls`；无通话时返回参数错误

### Requirement: 与 core_service 的 FDN 交互
系统 SHALL 由 `CoreServiceConnection`（`core_service_connection.cpp`）经 `DelayedRefSingleton<CoreServiceClient>` 与 core_service 交互：`GetFdnNumberList(slotId)` 调 `QueryIccDiallingNumbers(slotId, DiallingNumbersInfo::SIM_FDN, diallingNumbers)`，空表返回空 vector，否则逐条收集 `GetNumber()`；`IsFdnEnabled(slotId)` 调 `GetLockState(slotId, LockType::FDN_LOCK, lockState)`，仅当返回成功且 `lockState == LOCK_ON` 时为 true。注：`HasSimCard`/`GetSimState` 等 core_service 查询的调用点不在本目录（`call_policy.cpp`、`call_manager_service.cpp`、`call_manager_dump_helper.cpp` 等），不纳入本能力。

#### Scenario: FDN 号码白名单查询
- **WHEN** 拨号前需校验受限拨号、`GetFdnNumberList` 被调用
- **THEN** SIM FDN 记录的号码列表被返回；查询为空时返回空列表

#### Scenario: FDN 开关判定
- **WHEN** `IsFdnEnabled` 被调用且 `GetLockState` 失败或状态非 LOCK_ON
- **THEN** 返回 false（FDN 未启用，不阻断拨号）

### Requirement: 上行单队列串行化（ReportCallInfoHandler）
系统 SHALL 由 `ReportCallInfoHandler`（`report_call_info_handler.cpp`）以命名空间级 ffrt 队列 `report_call_info_queue`（`ffrt::queue_attr().qos(ffrt_qos_user_interactive)`）串行处理全部上行通话报告：`UpdateCallReportInfo`（OOBE 期 `CallStatusManager::GetDevProvisioned() != DEVICE_PROVISION_VALID` 且 `TYPE_BLUETOOTH` 的来电直接丢弃返回成功）、`UpdateCallsReportInfo`（含 `BuildCallDetailsInfo` 逐条字段拷贝；incoming 列表额外 `WriteIncomingCallFaultEvent` 记账）、`UpdateDisconnectedCause`（`RilDisconnectedReason::DISCONNECTED_REASON_NORMAL` 归一为 `DisconnectedReason::NORMAL_CALL_CLEARING`）、`UpdateEventResultInfo`、`UpdateOttEventInfo`、`UpdateVoipEventInfo`（各自以 `std::weak_ptr<CallStatusManager>` 捕获后 submit，队列内 `HandleCallReportInfo/HandleCallsReportInfo/HandleDisconnectedCause/HandleEventResultReportInfo/HandleOttEventReportInfo/HandleVoipEventReportInfo`）。`ReceiveImsCallModeRequest/ReceiveImsCallModeResponse` SHALL 在队列内按 `response.callIndex`（Response 先按 slotId 再按 index）取 `CallObjectManager` 通话对象，`TYPE_IMS` 时 `reinterpret_cast<IMSCall *>` 后转 `RecieveUpdateCallMediaModeRequest/ReceiveUpdateCallMediaModeResponse`。`Init` SHALL 构造 `CallStatusManager` 并注入 `AntiFraudService` 与 `CallManagerService`（`SetCallStatusManager`）。

#### Scenario: 单通话状态上报
- **WHEN** cellular_call 上行 `UPDATE_CALL_INFO` 经 `CallStatusCallback::UpdateCallReportInfo` 转为 `CallDetailInfo`
- **THEN** `ReportCallInfoHandler::UpdateCallReportInfo` 立即返回成功，`HandleCallReportInfo` 在队列内串行执行，失败仅记日志不回传

#### Scenario: 通话列表上报
- **WHEN** `UpdateCallsReportInfo` 收到多通通话列表
- **THEN** 逐条字段拷贝后队列内 `HandleCallsReportInfo`；若列表中有 incoming 状态通话，额外 `WriteIncomingCallFaultEvent` 记录

#### Scenario: IMS 视频模式请求
- **WHEN** `ReceiveImsCallModeRequest` 被调用且 index 对应通话为 `TYPE_IMS`
- **THEN** 队列内转 `IMSCall::RecieveUpdateCallMediaModeRequest`；无对应通话对象时记日志返回

### Requirement: CallStatusCallback 上行转换与 app 上报
系统 SHALL 由 `CallStatusCallback`（`call_status_callback.cpp`）作为 cellular_call 上行回调（`ICallStatusCallback`）的本地实现：`UpdateCallReportInfo` 把 `CallReportInfo` 转 `CallDetailInfo`（VOIP 字段逐项拷贝；存在 index 0 的蓝牙拨号通话且本条为蓝牙 disconnected 时把 `detailInfo.index` 归零）后交 `ReportCallInfoHandler`；`UpdateCallsReportInfo` 记 `WriteCallStateBehaviorEvent`、incoming 时记 `WriteIncomingCallBehaviorEvent` + `SetIncomingStartTime` + `StartAsyncTrace(HITRACE_TAG_OHOS, "InComingCall", getpid())`；`UpdateRBTPlayInfo` 在 `LOCAL_ALERTING` 时置 `isLocalRingbackNeeded = true` 并经 `CallAbilityReportProxy::CallEventUpdated` 发 `EVENT_LOCAL_ALERTING`，否则置 false，随后调 `AudioControlManager::SetLocalRingbackNeeded`；`StartDtmfResult/StopDtmfResult/SendUssdResult/GetImsCallDataResult/UpdateGetWaitingResult` 等全部补充业务结果 SHALL 以 `AppExecFwk::PacMap` + `CallResultReportId` 经 `CallAbilityReportProxy::ReportAsyncResults` 上报 app；`SendMmiCodeResult` SHALL 以 `ffrt::submit_h` 延迟 1s（`REPORT_SEND_USSD_DELAY_TIME`）上报 `ReportMmiCodeResult`；`ReceiveUpdateCallMediaModeRequest` 在转发 `ReportCallInfoHandler::ReceiveImsCallModeRequest` 后，对 active 且 `CALL_MODE_SEND_RECEIVE` 的通话 `PlayWaitingTone` 并以 `ffrt::submit_h` 延迟 3s（`DELAY_STOP_PLAY_TIME`）调 `ShouldStopWaitingTone`；`ReceiveUpdateCallMediaModeResponse` SHALL `ffrt::skip` 该延迟句柄并立即 `ShouldStopWaitingTone`（`HasRingingCall` 且通话数 ≥ `MIN_MULITY_CALL_COUNT`(2) 时不停等待音）；`ReportPostDialChar` SHALL 取首字符转 `AudioControlManager::OnPostDialNextChar`；`HandleCallSessionEventChanged/HandlePeerDimensionsChanged/HandleCameraCapabilitiesChanged` SHALL 以 `CallObjectManager::GetOneCallObjectByIndex` 解析 callId（无通话用 `ERR_CALL_ID`=0）后经 `CallAbilityReportProxy` 对应 `Report*` 接口上报。

#### Scenario: 网络侧回铃音提示
- **WHEN** 对端开始振铃、`UpdateRBTPlayInfo(LOCAL_ALERTING)` 上行
- **THEN** 本地回铃音需求置 true 并向 app 发 `EVENT_LOCAL_ALERTING` 事件

#### Scenario: 等待音超时停止
- **WHEN** 对端请求升级为视频（active + SEND_RECEIVE）且 3s 内未收到 Response
- **THEN** 延迟任务触发 `ShouldStopWaitingTone`，无振铃通话或多于 1 通时不停止，否则 `StopWaitingTone`

#### Scenario: 视频模式响应取消等待音
- **WHEN** `ReceiveUpdateCallMediaModeResponse` 在 3s 内到达
- **THEN** `ffrt::skip` 取消延迟停止并立即判定是否停等待音

#### Scenario: MMI 结果延迟上报
- **WHEN** `SendMmiCodeResult(info)` 被调用
- **THEN** 1s 后经 `CallAbilityReportProxy::ReportMmiCodeResult` 上报，本函数立即返回成功

### Requirement: CallStatusCallbackStub IPC 分发表
系统 SHALL 由 `CallStatusCallbackStub`（`call_status_callback_stub.cpp`）承接 cellular_call 的 IPC 上行入口：构造函数经 `InitBasicFuncMap/InitSupplementFuncMap/InitImsFuncMap` 建立共 37 个命令码（`UPDATE_CALL_INFO`、`UPDATE_CALLS_INFO`、`UPDATE_DISCONNECTED_CAUSE`、`UPDATE_EVENT_RESULT_INFO`、`UPDATE_RBT_PLAY_INFO`、`START_DTMF/STOP_DTMF`、`RECEIVE_UPDATE_MEDIA_MODE_REQUEST/RESPONSE`、`UPDATE_STARTRTT_STATUS/UPDATE_STOPRTT_STATUS`、`INVITE_TO_CONFERENCE`、`MMI_CODE_INFO_RESPONSE`、`CLOSE_UNFINISHED_USSD`、`POST_DIAL_CHAR/POST_DIAL_DELAY`、`CALL_SESSION_EVENT/PEER_DIMENSION_CHANGE/CALL_DATA_USAGE`、`SEND_USSD`、`UPDATE_GET/SET_WAITING`、`UPDATE_GET/SET_RESTRICTION`、`UPDATE_SET_RESTRICTION_PWD`、`UPDATE_GET/SET_TRANSFER`、`UPDATE_GET_CALL_CLIP/CLIR`、`UPDATE_SET_CALL_CLIR`、`GET_IMS_CALL_DATA`、`GET/SET_IMS_CONFIG`、`GET/SET_IMS_FEATURE_VALUE`、`CAMERA_CAPBILITIES_CHANGE`、`UPDATE_VOIP_EVENT_INFO`）到 On* 处理器的 `memberFuncMap_`。`OnRemoteRequest` SHALL 先比对 `CallStatusCallbackStub::GetDescriptor()` 与 `data.ReadInterfaceToken()`（不符返回 `TELEPHONY_ERR_DESCRIPTOR_MISMATCH`），再查表分发，未命中回落 `IPCObjectStub::OnRemoteRequest`。各 On* 处理器 SHALL 完成 parcel 解包（结构体类用 `ReadRawData(len)`，`len` 越界（≥`MAX_LEN`=100000）或 `cnt` 越界（≤0 或 >`MAX_CALL_NUM`=10）返回 `TELEPHONY_ERR_ARGUMENT_INVALID`）、调 `CallStatusCallback` 对应实现、`reply.WriteInt32` 回写（失败返回 `TELEPHONY_ERR_WRITE_REPLY_FAIL`）。`BuildCallReportInfo` SHALL 按约定序列（index/accountNum/accountId/callType/callMode/state/voiceDomain/mpty/crsType/originalCallType/VOIP 扩展字段/name/namePresentation/reason/message/newCallUseBox）解包 `CallReportInfo`。

#### Scenario: 描述符校验失败
- **WHEN** IPC 请求的 InterfaceToken 与 stub 描述符不一致
- **THEN** 返回 `TELEPHONY_ERR_DESCRIPTOR_MISMATCH`，不进入任何分发

#### Scenario: 通话列表参数越界
- **WHEN** `UPDATE_CALLS_INFO` 的通话数 cnt 不在 (0, 10] 区间
- **THEN** 返回 `TELEPHONY_ERR_ARGUMENT_INVALID`，不做处理

#### Scenario: VOIP 事件上行
- **WHEN** `UPDATE_VOIP_EVENT_INFO` 分发
- **THEN** 解出 voipCallId/bundleName/uid/voipCallEvent/errorReason 后交 `CallStatusCallback::UpdateVoipEventInfo`，结果码回写 reply

### Requirement: VoipCallConnection 与 voip_call_manager 服务交互
系统 SHALL 由 `VoipCallConnection`（`voip_call_connection.cpp`，DelayedSingleton，`std::mutex` 保护）以 `TELEPHONY_VOIP_CALL_MANAGER_SYS_ABILITY_ID` 连接 voip_call_manager：`GetCallManagerProxy` 经 samgr `GetSystemAbility` + `iface_cast<IVoipCallManagerService>` 取 `voipCallManagerInterfacePtr_`；`Init` 成功后 `SubscribeSystemAbility` 挂 `SystemAbilityListener`（OnAdd → 重新 `Init`；OnRemove → `ClearVoipCall` + `UnInit`）。`AnswerCall/RejectCall/HangUpCall` SHALL 先 `GetCallManagerProxy` 再调远程 `Answer(events, videoState)/Reject(events)/HangUp(events)`（代理为空返回 `TELEPHONY_ERROR`；HangUp 前经 `CallManagerHisysevent::WriteVoipCallStatisticalEvent(..., "HungupByCallmanager")` 记统计）；`RegisterCallManagerCallBack` SHALL 保存 `voipCallCallbackPtr_` 并调远程同名接口，`UnRegisterCallManagerCallBack` SHALL 调远程注销后 `UnInit`。`SendCallUiEvent(voipCallId, callAudioEvent)` 与 `SendCallUiEventForWindow(extras: AppExecFwk::PacMap)` SHALL 把通话 UI 事件（对端请求 UI 展示）转发给 voip 服务。`ClearVoipCall` SHALL 对每通 `TYPE_VOIP` 通话经 `BuildDisconnectedCallInfo` 组 `CALL_STATUS_DISCONNECTED` 报文，`voipCallCallbackPtr_` 存在时补报一次 `UpdateCallReportInfo`（防止界面未销毁），否则直接 `DeleteOneCallObject`。

#### Scenario: VOIP 来电接听
- **WHEN** 蜂窝侧判定 VOIP 来电被用户接听、`AnswerCall(events, videoState)` 被调用
- **THEN** 代理在位时远程 `Answer` 被调用并透传结果；代理为空返回 `TELEPHONY_ERROR`

#### Scenario: voip 服务下线清理
- **WHEN** `OnRemoveSystemAbility` 触发且本端存在 VOIP 通话对象
- **THEN** 逐通补报 DISCONNECTED（回调仍可用）或直接删除通话对象，随后 `UnInit` 清空代理与连接标志

#### Scenario: 通话 UI 事件转发
- **WHEN** 界面事件需请求 voip 侧 UI（`SendCallUiEvent/SendCallUiEventForWindow`）
- **THEN** 代理在位时转发给 voip 服务；代理为空返回 `TELEPHONY_ERROR`

### Requirement: BluetoothCallConnection 与蓝牙通话框架交互
系统 SHALL 由 `BluetoothCallConnection`（`bluetooth_call_connection.cpp`，DelayedSingleton）集中承接对 `Bluetooth::HandsFreeUnit` profile 的调用（移植时预计整体移除）：`Dial` 要求 `GetSupportBtCall()`（`BluetoothRemoteDevice(macAddress_).IsAclConnected()`，手表佩戴判定）与非空号码、非空 `macAddress_`，随后 `HandsFreeUnit::GetProfile()->StartDial(device, number)`；`ConnectBtSco/DisConnectBtSco` 以 `BluetoothRemoteDevice(macAddress_, 1)` 调 `ConnectSco/DisconnectSco`；`GetBtScoIsConnected` 以 `GetScoState == SCO_CONNECTED` 判定；`SetMacAddress/GetMacAddress` 维护蓝牙地址；`SetHfpConnected(false)` SHALL 触发 `HfpDisConnectedEndBtCall`（遍历 `TYPE_BLUETOOTH` 通话，逐通组 `CallDetailInfo` 经 `ReportCallInfoHandler::UpdateCallReportInfo` 报 DISCONNECTED）；`SetBtCallScoConnected/GetBtCallScoConnected` 维护 SCO 连接标志（供 `AudioDeviceManager::ReportAudioDeviceInfo` 的显示映射使用）；`SetHfpContactName/GetHfpContactName` 缓存 HFP 侧联系人姓名。

#### Scenario: 蓝牙通道拨号
- **WHEN** `GetSupportBtCall()` 为 true、号码与 macAddress 均非空、`Dial` 被调用
- **THEN** `HandsFreeUnit::StartDial` 发起蓝牙侧拨号并返回成功；任一前置不满足返回 `CALL_ERR_BLUETOOTH_CONNECTION_FAILED/CALL_ERR_DIAL_FAILED`

#### Scenario: HFP 断开结束蓝牙通话
- **WHEN** `SetHfpConnected(false)` 被调用且存在 `TYPE_BLUETOOTH` 通话
- **THEN** 每通蓝牙通话以 DISCONNECTED 状态上报（含 index、号码），由 `ReportCallInfoHandler` 队列内删除通话对象

#### Scenario: SCO 连接状态查询
- **WHEN** `GetBtScoIsConnected` 被调用
- **THEN** `GetScoState` 为 SCO_CONNECTED 时返回 true；profile 为空时返回 false
