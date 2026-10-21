# 协议栈交互层（telephony-interaction）Specification

## Purpose
描述 `telephony_call_manager/services/telephony_interaction/` 的协议栈交互层：`ReportCallInfoHandler`（上行单队列）、`CallStatusCallback`/`CallStatusCallbackStub`（cellular_call/voip/蓝牙共用的上行 IPC 入口）、`CellularCallConnection`（cellular_call 客户端）、`CoreServiceConnection`（core_service 客户端）、`BluetoothCallConnection`（蓝牙 HFP HF 侧）、`VoipCallConnection`（voip_call_manager 客户端）。编译开关：`ABILITY_CELLULAR_SUPPORT`（`ReConnectService` 重连，默认手机构建在位）、`RECONNECT_MAX_TRY_COUNT`（重试上限，默认未定义走无限重连）。

## Requirements

### Requirement: 上行单队列串行
系统 SHALL 由 `ReportCallInfoHandler` 以文件级 `ffrt::queue reportCallInfoQueue{"report_call_info_queue", ffrt::queue_attr().qos(ffrt_qos_user_interactive)}` 串行处理全部上行：`UpdateCallReportInfo`→`HandleCallReportInfo`、`UpdateCallsReportInfo`→`HandleCallsReportInfo`、`UpdateDisconnectedCause`→`HandleDisconnectedCause`（`RilDisconnectedReason::DISCONNECTED_REASON_NORMAL` 转 `DisconnectedReason::NORMAL_CALL_CLEARING`）、`UpdateEventResultInfo`→`HandleEventResultReportInfo`、`UpdateOttEventInfo`→`HandleOttEventReportInfo`、`UpdateVoipEventInfo`→`HandleVoipEventReportInfo`、`ReceiveImsCallModeRequest`/`ReceiveImsCallModeResponse`（取 `GetOneCallObjectByIndex(AndSlotId)` 后 `reinterpret_cast<IMSCall*>` 调 `RecieveUpdateCallMediaModeRequest/ReceiveUpdateCallMediaModeResponse`）；`Init()` 创建 `CallStatusManager` 并注入 `CallManagerService::SetCallStatusManager` 与 `AntiFraudService::SetCallStatusManager`。
#### Scenario: 全量列表深拷贝入队
- **WHEN** cellular_call 上报全量通话列表
- **THEN** `UpdateCallsReportInfo` 先 `BuildCallDetailsInfo` 深拷贝再入队，队列内转 `HandleCallsReportInfo`

### Requirement: 上行 IPC 入口与解包
系统 SHALL 由 `CallStatusCallbackStub : public IRemoteStub<ICallStatusCallback>` 以 `InitBasicFuncMap/InitSupplementFuncMap/InitImsFuncMap` 三组建表按 `CallStatusInterfaceCode` 分发（descriptor 失配返回 `TELEPHONY_ERR_DESCRIPTOR_MISMATCH`）；`OnUpdateCallsReportInfo` 校验 `0 < cnt <= MAX_CALL_NUM(10)` 后逐条 `BuildCallReportInfo` 解包（`TYPE_VOIP` 时追加 voipCallInfo 全字段与 `ReadUInt8Vector` 的 userProfile）；`CallStatusCallback`（`: public CallStatusCallbackStub, public std::enable_shared_from_this<CallStatusCallback>`）把 `CallReportInfo` 转 `CallDetailInfo` 后交 `ReportCallInfoHandler`，`SendMmiCodeResult` 以 `ffrt::submit_h` 延迟 `REPORT_SEND_USSD_DELAY_TIME` 上报。
#### Scenario: 超上限的全量列表拒绝
- **WHEN** 上报条数 cnt 超过 `MAX_CALL_NUM = 10`
- **THEN** 该次 `OnUpdateCallsReportInfo` 拒绝处理

#### Scenario: 视频升级请求触发等待音
- **WHEN** `ReceiveUpdateCallMediaModeRequest` 在 ACTIVE 且 `ImsCallMode::CALL_MODE_SEND_RECEIVE` 时到达
- **THEN** `AudioControlManager::PlayWaitingTone()` 播放等待音并以 `ffrt::submit_h` 延迟 `DELAY_STOP_PLAY_TIME = 3000000` 微秒后按 `ShouldStopWaitingTone()`（`HasRingingCall` 且 `GetCurrentCallNum() >= MIN_MULITY_CALL_COUNT(2)` 才保留）决定是否 `StopWaitingTone`

### Requirement: cellular_call 客户端封装
系统 SHALL 由 `CellularCallConnection`（`DECLARE_DELAYED_SINGLETON`，`ffrt::shared_mutex clientLock_`）经 samgr `GetSystemAbility(TELEPHONY_CELLULAR_CALL_SYS_ABILITY_ID)`→`iface_cast<CellularCallInterface>` 建代理并以 `SubscribeSystemAbility` 监听其上下线（`OnAddSystemAbility`→`Clean()+ReConnectService()+ClearAllCalls()`，`OnRemoveSystemAbility`→`Clean()`），封装 `Dial/HangUp/Reject/Answer/HoldCall/UnHoldCall/SwitchCall/IsEmergencyPhoneNumber/CombineConference/SeparateConference/KickOutFromConference/StartDtmf/StopDtmf/PostDialProceed/SendDtmf/SendDtmfString/SetCallTransferInfo/CanSetCallTransferTime/GetCallTransferInfo/SetCallWaiting/GetCallWaiting/GetVideoCallWaiting/SetCallRestriction/GetCallRestriction/SetCallRestrictionPassword/SetCallPreferenceMode/StartRtt/StopRtt/ControlCamera/SetPreviewWindow/SetDisplayWindow/SetCameraZoom/SetPausePicture/SetDeviceDirection/SetImsSwitchStatus/GetImsSwitchStatus/GetCarrierVtConfig/SetVoNRState/GetVoNRState/SendUpdateCallMediaModeRequest/SendUpdateCallMediaModeResponse/SetImsConfig/GetImsConfig/SetImsFeatureValue/GetImsFeatureValue/InviteToConference/SetMute/CloseUnFinishedUssd/CancelCallUpgrade/RequestCameraCapabilities/SendUssdResponse/IsMmiCode/ClearAllCalls` 等接口。
#### Scenario: cellular_call 服务掉线清理
- **WHEN** `TELEPHONY_CELLULAR_CALL_SYS_ABILITY_ID` 服务下线
- **THEN** `Clean()` 清空代理引用，通话业务下行走失败路径并记 `CallManagerHisysevent::WriteDialCallFaultEvent/WriteHangUpFaultEvent`

### Requirement: core_service 客户端封装
系统 SHALL 由 `CoreServiceConnection` 直接经 `DelayedRefSingleton<CoreServiceClient>::GetInstance()` 封装 FDN 查询：`GetFdnNumberList(slotId)`→`QueryIccDiallingNumbers(slotId, DiallingNumbersInfo::SIM_FDN, diallingNumbers)`、`IsFdnEnabled(slotId)`→`GetLockState(slotId, LockType::FDN_LOCK, lockState) == LockState::LOCK_ON`。
#### Scenario: FDN 启用时段拨非 FDN 号码
- **WHEN** `IsFdnEnabled` 为真且拨号号码不在 `GetFdnNumberList` 返回名单内
- **THEN** 拨号被拒并弹 `CALL_FAILED_DUE_TO_FDN` 提示

### Requirement: 蓝牙 HFP HF 侧连接
系统 SHALL 由 `BluetoothCallConnection`（`DECLARE_DELAYED_SINGLETON`，`bluetooth_hfp_hf.h`）封装 HF 侧接口：`Dial(DialParaInfo&)`→`Bluetooth::HandsFreeUnit::GetProfile()->StartDial(device, number)`、`ConnectBtSco/DisConnectBtSco`→`ConnectSco/DisconnectSco`、`GetBtScoIsConnected`、`GetSupportBtCall`（`BluetoothRemoteDevice::IsAclConnected()`）、`SetHfpConnected(false)`→`HfpDisConnectedEndBtCall()`（为每个 `TYPE_BLUETOOTH` 通话构造 DISCONNECTED 的 `CallDetailInfo` 交 `ReportCallInfoHandler::UpdateCallReportInfo` 强制结束）、`SetMacAddress/GetMacAddress`、`SetHfpContactName/GetHfpContactName`。
#### Scenario: HFP 断连强制结束蓝牙通话
- **WHEN** 蓝牙 HFP 链路断开（`SetHfpConnected(false)`）
- **THEN** 全部 `TYPE_BLUETOOTH` 通话被构造为 DISCONNECTED 上报后结束

### Requirement: VoIP 客户端封装与清场
系统 SHALL 由 `VoipCallConnection`（`systemAbilityId_ = TELEPHONY_VOIP_CALL_MANAGER_SYS_ABILITY_ID`）经 samgr 建代理并监听其上下线：`Answer/Reject/HangUp`（挂断前记 `CallManagerHisysevent::WriteVoipCallStatisticalEvent(..., "HungupByCallmanager")`）、`SendCallUiEvent(voipCallId, CallAudioEvent)` 与 `SendCallUiEventForWindow(AppExecFwk::PacMap&)`；SA 下线时 `ClearVoipCall()` 对残留 `TYPE_VOIP` 通话经 `BuildDisconnectedCallInfo` 组包后由 `voipCallCallbackPtr_->UpdateCallReportInfo` 补发 DISCONNECTED 再删对象。
#### Scenario: voip_call_manager 服务下线
- **WHEN** `TELEPHONY_VOIP_CALL_MANAGER_SYS_ABILITY_ID` 服务下线
- **THEN** 残留 VoIP 通话被补发 DISCONNECTED 上报并从对象表删除
