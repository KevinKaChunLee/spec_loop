# Spec Delta

## MODIFIED Requirements

### Requirement: 上行单队列串行
系统 SHALL 由 `ReportCallInfoHandler` 以打桩 `EventHandler` 单队列（替代 `ffrt::queue reportCallInfoQueue`）串行处理全部上行：`UpdateCallReportInfo`→`HandleCallReportInfo`、`UpdateCallsReportInfo`→`HandleCallsReportInfo`、`UpdateDisconnectedCause`→`HandleDisconnectedCause`（`RilDisconnectedReason::DISCONNECTED_REASON_NORMAL` 转 `DisconnectedReason::NORMAL_CALL_CLEARING`）、`UpdateEventResultInfo`→`HandleEventResultReportInfo`、`UpdateVoipEventInfo`→`HandleVoipEventReportInfo`；`UpdateOttEventInfo`（OTT）与 `ReceiveImsCallModeRequest`/`ReceiveImsCallModeResponse`（视频升级）处理不迁移；`Init()` 创建 `CallStatusManager` 并注入 `CallManagerService::SetCallStatusManager`（`AntiFraudService::SetCallStatusManager` 注入不迁移）。
#### Scenario: 全量列表深拷贝入队
- **WHEN** 协议栈侧上报全量通话列表
- **THEN** `UpdateCallsReportInfo` 先 `BuildCallDetailsInfo` 深拷贝再入队，队列内按序转 `HandleCallsReportInfo`

#### Scenario: 上行队列串行
- **WHEN** 两次上行消息先后入队
- **THEN** 打桩 `EventHandler` 按提交顺序串行处理，不并发交错

### Requirement: 上行 IPC 入口与解包
系统 SHALL 由 `CallStatusCallback`（进程内直调对象，`CallStatusCallbackStub` 的 IPC 解包层不迁移）接收协议栈上行并把 `CallReportInfo` 转 `CallDetailInfo` 后交 `ReportCallInfoHandler`；`OnUpdateCallsReportInfo` 的 `0 < cnt <= MAX_CALL_NUM(10)` 上限校验与 voipCallInfo 全字段（含 `ReadUInt8Vector` 的 userProfile）解包逻辑保留（供桩测试注入）；`SendMmiCodeResult` 以打桩 `EventHandler` 延迟 `REPORT_SEND_USSD_DELAY_TIME` 上报。
#### Scenario: 视频升级请求触发等待音
- **WHEN** 上行视频升级请求（`ReceiveImsCallModeRequest` 路径）到达
- **THEN** 该处理不迁移（视频通话不支持），等待音触发与 `DELAY_STOP_PLAY_TIME` 延时停播链路不可达

#### Scenario: 超上限的全量列表拒绝
- **WHEN** 直调形态上报条数 cnt 超过 `MAX_CALL_NUM = 10`
- **THEN** 该次 `OnUpdateCallsReportInfo` 拒绝处理

#### Scenario: VoIP 附加字段解包保留
- **WHEN** 桩注入携带 voipCallInfo 全字段的 `TYPE_VOIP` 上报
- **THEN** 附加字段（userName/abilityName/voipCallState/userProfile 等）完整解包进 `CallDetailInfo`

### Requirement: cellular_call 客户端封装
系统 SHALL 由 `CellularCallConnection`（`DECLARE_DELAYED_SINGLETON`）保留同名接口面（`Dial/HangUp/Reject/Answer/HoldCall/UnHoldCall/SwitchCall/IsEmergencyPhoneNumber/CombineConference/SeparateConference/KickOutFromConference/StartDtmf/StopDtmf/PostDialProceed/SendDtmf/SendDtmfString/SetCallTransferInfo/CanSetCallTransferTime/GetCallTransferInfo/SetCallWaiting/GetCallWaiting/GetVideoCallWaiting/SetCallRestriction/GetCallRestriction/SetCallRestrictionPassword/SetCallPreferenceMode/StartRtt/StopRtt/SetImsSwitchStatus/GetImsSwitchStatus/SetImsConfig/GetImsConfig/SetImsFeatureValue/GetImsFeatureValue/InviteToConference/SetMute/CloseUnFinishedUssd/IsMmiCode/ClearAllCalls` 等），实现改经 `CellularCallClient::GetInstance()` 桩（接口名与参数语义同名）；samgr 连接、`SubscribeSystemAbility` 上下线监听与 `ReConnectService` 重连（`RECONNECT_MAX_TRY_COUNT`）不迁移；故障路径以日志记录原 `WriteDialCallFaultEvent`/`WriteHangUpFaultEvent` 信息。
#### Scenario: cellular_call 服务掉线清理
- **WHEN** `CellularCallClient` 桩配置接口返回错误（模拟协议栈失败/服务不可用）
- **THEN** 下行走失败路径并以日志记录原 `WriteDialCallFaultEvent`/`WriteHangUpFaultEvent` 故障信息（无真实服务掉线与重连）

#### Scenario: 拨号经 cellular_call 客户端桩
- **WHEN** 下行拨号到达协议栈边界
- **THEN** 以 `CellularCallClient::GetInstance().Dial(...)` 调用桩并按桩配置返回结果（成功或错误码）

### Requirement: core_service 客户端封装
系统 SHALL 由 `CoreServiceConnection` 的 FDN 查询改经 `CoreServiceClient::GetInstance()` 桩：`GetFdnNumberList(slotId)`→`QueryIccDiallingNumbers(slotId, DiallingNumbersInfo::SIM_FDN, diallingNumbers)`、`IsFdnEnabled(slotId)`→`GetLockState(slotId, LockType::FDN_LOCK, lockState) == LockState::LOCK_ON`（判定逻辑保留，查询经桩）。
#### Scenario: FDN 启用时段拨非 FDN 号码
- **WHEN** 桩配置 FDN 启用（`LockState::LOCK_ON`）且拨号号码不在 `GetFdnNumberList` 桩返回名单内
- **THEN** 拨号被拒并弹 `CALL_FAILED_DUE_TO_FDN` 提示（经 `CallDialog` 桩）

### Requirement: VoIP 客户端封装与清场
系统 SHALL 由 `VoipCallConnection`（暂无 voip_call_manager 真实对接，依赖后续畅连通话适配）经桩实现：`Answer/Reject/HangUp`（挂断前以日志记录原 `WriteVoipCallStatisticalEvent` 的 "HungupByCallmanager" 统计信息）、`SendCallUiEvent(voipCallId, CallAudioEvent)` 与 `SendCallUiEventForWindow`（`AppExecFwk::PacMap` 参数结构体化）；`ClearVoipCall()` 对残留 `TYPE_VOIP` 通话经 `BuildDisconnectedCallInfo` 组包后由 `voipCallCallbackPtr_->UpdateCallReportInfo` 补发 DISCONNECTED 再删对象（清场逻辑保留，触发经桩）。
#### Scenario: voip_call_manager 服务下线
- **WHEN** 桩模拟 voip 服务下线回调
- **THEN** `ClearVoipCall()` 对残留 `TYPE_VOIP` 通话补发 DISCONNECTED 上报并从对象表删除（清场逻辑保留，触发经桩）

## REMOVED Requirements

### Requirement: 蓝牙 HFP HF 侧连接
**Reason**: AGENTS.md 功能范围：BLUETOOTH 类型通话与蓝牙耳机设备连接不支持。
**Migration**: `BluetoothCallConnection` 与 HFP HF 侧接口（`StartDial`/`ConnectSco`/`SetHfpConnected` 等）不迁移；`SetHfpConnected(false)` 强制结束蓝牙通话的链路随 `TYPE_BLUETOOTH` 对象移除。
