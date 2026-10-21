# 模块交互（Telephony Interaction）Specification

## Purpose
描述 HMOS `telephony_call_manager` 模块当前与其他电话子系统的交互能力：`CellularCallConnection`（经 samgr 获取 cellular_call 系统服务代理并带重连语义，文件内引用宏 `RECONNECT_MAX_TRY_COUNT`）、`CoreServiceConnection`（core_service 的 FDN 查询）、`VoipCallConnection`（与 voip_call_manager 服务的代理交互）、`BluetoothCallConnection`（蓝牙 HFP 通话交互，外部依赖随 `ABILITY_BLUETOOTH_SUPPORT` 引入）、`CallStatusCallback`/`CallStatusCallbackStub`（接收 cellular_call 的 IPC 上报并分发）与 `ReportCallInfoHandler`（上行单队列 `report_call_info_queue` 串行处理）。源码落点：`telephony_call_manager/services/telephony_interaction/{include,src}` 的 cellular_call_connection.cpp、core_service_connection.cpp、voip_call_connection.cpp、bluetooth_call_connection.cpp、call_status_callback.cpp/.h、call_status_callback_stub.cpp、report_call_info_handler.cpp。控制开关：`callmanager.gni` 的 `ABILITY_CELLULAR_SUPPORT`（随 telephony_cellular_call 部件）控制 `CellularCallConnection::ReConnectService` 的重连逻辑；`ABILITY_BLUETOOTH_SUPPORT`（随 communication_bluetooth 部件）引入蓝牙框架依赖；本子模块无其他专属特性宏。

## Requirements

### Requirement: cellular_call 代理获取与回调注册
系统 SHALL 由 `CellularCallConnection`（延迟单例）在 `Init` 时经 `SystemAbilityManagerClient::GetSystemAbilityManager` 以 `TELEPHONY_CELLULAR_CALL_SYS_ABILITY_ID` 取 `IRemoteObject` 并 `iface_cast<CellularCallInterface>` 得到代理（ConnectService），随后 `RegisterCallBackFun` 创建 `CallStatusCallback` 实例并调用 `RegisterCallManagerCallBack` 向 cellular_call 注册回调；`Init` 同时经 `SubscribeSystemAbility` 注册内部类 `SystemAbilityListener` 监听该系统服务上下线；已连接（connectState_ 为 true）时 `Init` MUST 直接返回不再重连。

#### Scenario: 首次连接成功注册回调
- **WHEN** connectState_ 为 false 且 samgr 能返回有效代理时调用 Init(systemAbilityId)
- **THEN** 保存代理、创建 CallStatusCallback 并完成 RegisterCallManagerCallBack，connectState_ 置 true

#### Scenario: 重复初始化被忽略
- **WHEN** connectState_ 已为 true 时再次调用 Init
- **THEN** 直接返回，不重新获取代理

#### Scenario: 服务不存在时连接失败
- **WHEN** samgr 的 GetSystemAbility 返回空对象
- **THEN** ConnectService 返回 TELEPHONY_ERR_IPC_CONNECT_STUB_FAIL，connectState_ 保持 false

### Requirement: 重连与服务状态监听
系统 SHALL 由 `CellularCallConnection` 的每个业务方法在调用代理前先执行 `ReConnectService`（在 `ABILITY_CELLULAR_SUPPORT` 打开且代理为空时尝试 ConnectService），失败即返回 TELEPHONY_ERR_IPC_CONNECT_STUB_FAIL；`SystemAbilityListener::OnRemoveSystemAbility` 在已连接时调用 `Clean`（注销回调并清空代理、connectState_ 置 false）；`OnAddSystemAbility` MUST 先 Clean 再 ReConnectService，重连成功后调用 `ClearAllCalls`（仅当 CallObjectManager::HasCallExist，先延时 DELAY_TIME 再下发）向 cellular_call 同步残留通话清理；文件内 `#ifdef RECONNECT_MAX_TRY_COUNT` 下定义 CONNECT_MAX_TRY_COUNT = 5。

#### Scenario: 代理失效时业务自动重连
- **WHEN** cellularCallInterfacePtr_ 为空且 ABILITY_CELLULAR_SUPPORT 打开时调用 Dial
- **THEN** 先执行 ConnectService，成功后继续下发 Dial，失败则返回 TELEPHONY_ERR_IPC_CONNECT_STUB_FAIL

#### Scenario: cellular_call 服务下线
- **WHEN** OnRemoveSystemAbility 触发且当前已连接
- **THEN** Clean 清空代理与回调并置 connectState_ = false

#### Scenario: cellular_call 服务重新上线
- **WHEN** OnAddSystemAbility 触发且此前连接已断开、当前存在残留通话对象
- **THEN** 重连成功后 ClearAllCalls 将残留通话信息组装下发清理

### Requirement: 上报单队列串行处理
系统 SHALL 由 `ReportCallInfoHandler`（延迟单例）将 cellular_call 的上行报告统一提交到 ffrt 队列 `report_call_info_queue`（qos 为 user_interactive）串行处理：UpdateCallReportInfo/UpdateCallsReportInfo 转入 `CallStatusManager::HandleCallReportInfo`/`HandleCallsReportInfo`，UpdateDisconnectedCause 转入 HandleDisconnectedCause，UpdateEventResultInfo 转入 HandleEventResultReportInfo，UpdateOttEventInfo 转入 HandleOttEventReportInfo，UpdateVoipEventInfo 转入 HandleVoipEventReportInfo；任务以 weak_ptr 持有 CallStatusManager，失效时丢弃；`UpdateCallReportInfo` MUST 在 `CallStatusManager::GetDevProvisioned()` 不等于 DEVICE_PROVISION_VALID 且 callType 为 TYPE_BLUETOOTH 时直接返回 TELEPHONY_SUCCESS（OOBE 阶段不处理 BT 上报）。

#### Scenario: 单通上报入队串行执行
- **WHEN** UpdateCallReportInfo(info) 被调用且 handler 已 Init
- **THEN** 拷贝 info 后提交到 report_call_info_queue，由 HandleCallReportInfo 串行消费，函数本身立即返回 TELEPHONY_SUCCESS

#### Scenario: OOBE 阶段丢弃蓝牙通话上报
- **WHEN** GetDevProvisioned() != DEVICE_PROVISION_VALID 且 info.callType == TYPE_BLUETOOTH 时调用 UpdateCallReportInfo
- **THEN** 不入队，直接返回 TELEPHONY_SUCCESS

#### Scenario: 管理器已销毁时上报被丢弃
- **WHEN** 队列任务执行时 weak_ptr lock 得到空指针
- **THEN** 记录错误日志后返回，不调用任何 Handle* 处理

### Requirement: CallStatusCallback 上报分发
系统 SHALL 由 `CallStatusCallback`（继承 `CallStatusCallbackStub`）接收 cellular_call 的上报并分发：UpdateCallReportInfo 将 CallReportInfo 转换为 CallDetailInfo（TYPE_VOIP 时复制 voipCallInfo 字段）后交 ReportCallInfoHandler；UpdateRBTPlayInfo 在 info 为 `RBTPlayInfo::LOCAL_ALERTING` 时置 `AudioControlManager::SetLocalRingbackNeeded(true)` 并经 `CallAbilityReportProxy::CallEventUpdated` 上报 EVENT_LOCAL_ALERTING 事件，否则置 false；DTMF/USSD/CLIP/CLIR 等结果回调经 `CallAbilityReportProxy::ReportAsyncResults` 以对应 `CallResultReportId` 上报；`ReportPostDialChar` 取首字符转 `AudioControlManager::OnPostDialNextChar`。

#### Scenario: 本地回铃音激活
- **WHEN** cellular_call 上报 UpdateRBTPlayInfo(LOCAL_ALERTING)
- **THEN** SetLocalRingbackNeeded(true) 生效并向应用上报 EVENT_LOCAL_ALERTING 事件

#### Scenario: 非本地回铃音关闭本地回铃
- **WHEN** cellular_call 上报 UpdateRBTPlayInfo(非 LOCAL_ALERTING 取值)
- **THEN** SetLocalRingbackNeeded(false) 生效，不上报事件，返回 TELEPHONY_SUCCESS

#### Scenario: 后拨号码字符分发
- **WHEN** cellular_call 上报 ReportPostDialChar("5")
- **THEN** 取首字符 '5' 转发 AudioControlManager::OnPostDialNextChar('5')

### Requirement: 等待音定时停止
系统 SHALL 由 `CallStatusCallback::ReceiveUpdateCallMediaModeRequest` 在对端激活通话（CALL_STATUS_ACTIVE 且 callMode 为 CALL_MODE_SEND_RECEIVE）且 `PlayWaitingTone` 成功后，经 ffrt::submit_h 延迟 DELAY_STOP_PLAY_TIME 调度 `ShouldStopWaitingTone`；`ReceiveUpdateCallMediaModeResponse` 收到响应时若等待音任务仍在则 `ffrt::skip` 取消并立即执行 ShouldStopWaitingTone；`ShouldStopWaitingTone` MUST 仅在没有响铃通话或当前通话数小于 MIN_MULITY_CALL_COUNT 时调用 StopWaitingTone。

#### Scenario: 升级请求后 3 秒无响应自动停等待音
- **WHEN** 等待音已播放且 DELAY_STOP_PLAY_TIME 内未收到 ReceiveUpdateCallMediaModeResponse
- **THEN** 定时任务触发 ShouldStopWaitingTone 并停止等待音

#### Scenario: 收到响应取消定时任务
- **WHEN** waitingToneHandle_ 非空时调用 ReceiveUpdateCallMediaModeResponse
- **THEN** ffrt::skip 取消定时任务并立即执行 ShouldStopWaitingTone

#### Scenario: 多方响铃时不停等待音
- **WHEN** ShouldStopWaitingTone 执行时存在响铃通话且当前通话数 >= MIN_MULITY_CALL_COUNT(2)
- **THEN** 不调用 StopWaitingTone，仅清空 waitingToneHandle_

### Requirement: IPC stub 命令分发
系统 SHALL 由 `CallStatusCallbackStub` 在构造时经 `InitBasicFuncMap`/`InitSupplementFuncMap`/`InitImsFuncMap` 将 UPDATE_CALL_INFO、UPDATE_CALLS_INFO、START_DTMF、MMI_CODE_INFO_RESPONSE、CLOSE_UNFINISHED_USSD 等 IPC 命令码注册进 `memberFuncMap_`，命令到达时派发到对应 OnXxx 处理函数（如 OnUpdateCallReportInfo、OnSendMmiCodeResult、OnCloseUnFinishedUssdResult），解出的结果再调用 `CallStatusCallback` 同名虚函数完成分发。

#### Scenario: MMI 结果命令分发
- **WHEN** IPC 收到 MMI_CODE_INFO_RESPONSE 命令
- **THEN** 经 memberFuncMap_ 派发到 OnSendMmiCodeResult，解出 MmiCodeInfo 后调用 SendMmiCodeResult

#### Scenario: 构造时完成三组命令注册
- **WHEN** CallStatusCallbackStub 实例化
- **THEN** 基础/补充业务/IMS 三组命令码全部注册进 memberFuncMap_

### Requirement: core_service FDN 查询
系统 SHALL 由 `CoreServiceConnection::GetFdnNumberList(slotId)` 经 `CoreServiceClient::QueryIccDiallingNumbers(slotId, DiallingNumbersInfo::SIM_FDN, ...)` 查询 FDN 号码列表并返回 u16string 向量（空列表时返回空向量）；`IsFdnEnabled(slotId)` 经 `GetLockState(slotId, LockType::FDN_LOCK, lockState)` 判断，仅当返回 TELEPHONY_ERR_SUCCESS 且 lockState 为 `LockState::LOCK_ON` 时返回 true。

#### Scenario: FDN 启用判断
- **WHEN** GetLockState 返回成功且 lockState == LOCK_ON
- **THEN** IsFdnEnabled 返回 true

#### Scenario: FDN 号码列表为空
- **WHEN** QueryIccDiallingNumbers 返回空列表
- **THEN** GetFdnNumberList 返回空向量

### Requirement: VoIP 服务代理交互
系统 SHALL 由 `VoipCallConnection`（延迟单例）经 `GetCallManagerProxy` 以 `TELEPHONY_VOIP_CALL_MANAGER_SYS_ABILITY_ID` 从 samgr 取 `IVoipCallManagerService` 代理；AnswerCall/RejectCall/HangUpCall/SendCallUiEvent/SendCallUiEventForWindow 在代理为空时先尝试 GetCallManagerProxy，仍为空返回 TELEPHONY_ERROR；`UnRegisterCallManagerCallBack` 注销后调用 `UnInit` 清理；服务下线（OnRemoveSystemAbility）时 `ClearVoipCall` MUST 对每个 TYPE_VOIP 通话经 `BuildDisconnectedCallInfo` 构造 DISCONNECTED 报告再次经回调 UpdateCallReportInfo 上报以防界面残留，回调为空则直接 DeleteOneCallObject。

#### Scenario: VoIP 服务不可用时接听失败
- **WHEN** voipCallManagerInterfacePtr_ 为空且 GetCallManagerProxy 失败时调用 AnswerCall
- **THEN** 返回 TELEPHONY_ERROR

#### Scenario: VoIP 服务下线补报断开
- **WHEN** OnRemoveSystemAbility 触发且存在 TYPE_VOIP 通话对象
- **THEN** 对每个 VoIP 通话构造 CALL_STATUS_DISCONNECTED 报告经回调再次上报

### Requirement: 蓝牙 HFP 通话交互
系统 SHALL 由 `BluetoothCallConnection::Dial` 在 `GetSupportBtCall()`（经 `BluetoothRemoteDevice::IsAclConnected` 判断手表蓝牙通话支持）通过且 macAddress_、号码非空时经 `Bluetooth::HandsFreeUnit::GetProfile()->StartDial` 发起蓝牙拨号；`ConnectBtSco`/`DisConnectBtSco` 经 profile 的 ConnectSco/DisconnectSco 操作 SCO 链路；`GetBtScoIsConnected` 以 SCO_CONNECTED 判断链路状态；`SetHfpConnected(false)` MUST 触发 `HfpDisConnectedEndBtCall` 将所有 TYPE_BLUETOOTH 通话构造为 DISCONNECTED 报告经 `ReportCallInfoHandler::UpdateCallReportInfo` 上报结束。

#### Scenario: ACL 未连接时蓝牙拨号失败
- **WHEN** GetSupportBtCall() 返回 false 时调用 Dial
- **THEN** 返回 CALL_ERR_BLUETOOTH_CONNECTION_FAILED，不调用 StartDial

#### Scenario: HFP 断开结束蓝牙通话
- **WHEN** SetHfpConnected(false) 且存在 TYPE_BLUETOOTH 通话
- **THEN** HfpDisConnectedEndBtCall 将每个蓝牙通话以 CALL_STATUS_DISCONNECTED 上报

#### Scenario: SCO 连接状态查询
- **WHEN** GetScoState 返回 SCO_CONNECTED 时调用 GetBtScoIsConnected
- **THEN** 返回 true
