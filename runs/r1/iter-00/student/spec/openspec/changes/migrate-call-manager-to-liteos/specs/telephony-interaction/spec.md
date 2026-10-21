# Spec Delta

## MODIFIED Requirements

### Requirement: cellular_call 代理获取与回调注册
系统 SHALL 由 `CellularCallConnection`（延迟单例）在 `Init` 时经本 change 引入的 `CellularCallClient::GetInstance()`（stub/ 打桩，方法名与基线 ICellularCall 一致）完成服务接口获取（ConnectService），随后 `RegisterCallBackFun` 创建 `CallStatusCallback` 实例并调用 `RegisterCallManagerCallBack` 向 cellular_call 桩注册回调（回调注册经打桩实现：cellular_call 桩侧直接在进程内调用 `CallStatusCallback` 接口完成上报）；已连接（connectState_ 为 true）时 `Init` MUST 直接返回不再重连。

#### Scenario: 首次连接成功注册回调
- **WHEN** connectState_ 为 false 且 `CellularCallClient::GetInstance()` 桩接口可用时调用 Init(systemAbilityId)
- **THEN** 完成桩接口获取、创建 CallStatusCallback 并完成 RegisterCallManagerCallBack，connectState_ 置 true

#### Scenario: 重复初始化被忽略
- **WHEN** connectState_ 已为 true 时再次调用 Init
- **THEN** 直接返回，不重新获取桩接口

#### Scenario: 服务不存在时连接失败
- **WHEN** liteOS 无 samgr 状态监听，打桩客户端 `CellularCallClient::GetInstance()` 桩接口不可用（初始化失败，对应基线 GetSystemAbility 返回空对象的场景）
- **THEN** ConnectService 返回 TELEPHONY_ERR_IPC_CONNECT_STUB_FAIL，connectState_ 保持 false

### Requirement: 上报单队列串行处理
系统 SHALL 由 `ReportCallInfoHandler`（延迟单例）将 cellular_call 桩的上行报告统一提交到单队列 `report_call_info_queue` 串行处理，队列原语由基线的 ffrt 换成本 change 打桩的 EventHandler（单线程顺序派发，串行语义保留）：UpdateCallReportInfo/UpdateCallsReportInfo 转入 `CallStatusManager::HandleCallReportInfo`/`HandleCallsReportInfo`，UpdateDisconnectedCause 转入 HandleDisconnectedCause，UpdateEventResultInfo 转入 HandleEventResultReportInfo，UpdateOttEventInfo 转入 HandleOttEventReportInfo，UpdateVoipEventInfo 转入 HandleVoipEventReportInfo；任务以 weak_ptr 持有 CallStatusManager，失效时丢弃；callType 为 `TYPE_BLUETOOTH` 的上报因蓝牙 HFP 链路不迁移被判为不支持的 callType，MUST 不入队直接返回 TELEPHONY_SUCCESS。

#### Scenario: 单通上报入队串行执行
- **WHEN** UpdateCallReportInfo(info) 被调用且 handler 已 Init
- **THEN** 拷贝 info 后经打桩 EventHandler 提交到 report_call_info_queue，由 HandleCallReportInfo 串行消费，函数本身立即返回 TELEPHONY_SUCCESS

#### Scenario: OOBE 阶段丢弃蓝牙通话上报
- **WHEN** 上报 callType 为 `TYPE_BLUETOOTH` 的通话信息（蓝牙类型通话不迁移，无论 OOBE 配置状态）
- **THEN** 该上报被判为不支持的 callType 后不入队直接丢弃，返回 TELEPHONY_SUCCESS

#### Scenario: 管理器已销毁时上报被丢弃
- **WHEN** 队列任务执行时 weak_ptr lock 得到空指针
- **THEN** 记录错误日志后返回，不调用任何 Handle* 处理

### Requirement: CallStatusCallback 上报分发
系统 SHALL 由 `CallStatusCallback` 接收 cellular_call 桩的上报并分发，上报入口从 IPC stub 改为进程内直调 `CallStatusCallback` 的同名方法：UpdateCallReportInfo 将 CallReportInfo 转换为 CallDetailInfo 后交 ReportCallInfoHandler；UpdateRBTPlayInfo 在 info 为 `RBTPlayInfo::LOCAL_ALERTING` 时置 `AudioControlManager::SetLocalRingbackNeeded(true)` 并经 `CallAbilityReportProxy::CallEventUpdated` 上报 EVENT_LOCAL_ALERTING 事件，否则置 false；DTMF/USSD/CLIP/CLIR 等结果回调经 `CallAbilityReportProxy::ReportAsyncResults` 以对应 `CallResultReportId` 上报；`ReportPostDialChar` 取首字符转 `AudioControlManager::OnPostDialNextChar`。

#### Scenario: 本地回铃音激活
- **WHEN** cellular_call 桩进程内直调 UpdateRBTPlayInfo(LOCAL_ALERTING)
- **THEN** SetLocalRingbackNeeded(true) 生效并向应用上报 EVENT_LOCAL_ALERTING 事件

#### Scenario: 非本地回铃音关闭本地回铃
- **WHEN** cellular_call 桩上报 UpdateRBTPlayInfo(非 LOCAL_ALERTING 取值)
- **THEN** SetLocalRingbackNeeded(false) 生效，不上报事件，返回 TELEPHONY_SUCCESS

#### Scenario: 后拨号码字符分发
- **WHEN** cellular_call 桩上报 ReportPostDialChar("5")
- **THEN** 取首字符 '5' 转发 AudioControlManager::OnPostDialNextChar('5')

### Requirement: 等待音定时停止
系统 SHALL 由 `CallStatusCallback::ReceiveUpdateCallMediaModeRequest` 在对端激活通话（CALL_STATUS_ACTIVE 且 callMode 为 CALL_MODE_SEND_RECEIVE）且 `PlayWaitingTone` 成功后，经本 change 打桩的 EventHandler 延迟 DELAY_STOP_PLAY_TIME 调度 `ShouldStopWaitingTone`；`ReceiveUpdateCallMediaModeResponse` 收到响应时若等待音任务仍在则取消该定时任务并立即执行 ShouldStopWaitingTone；`ShouldStopWaitingTone` MUST 仅在没有响铃通话或当前通话数小于 MIN_MULITY_CALL_COUNT 时调用 StopWaitingTone（等待音的实际播放/停止在 audio-management 能力中经 audio todo 占位承接）。

#### Scenario: 升级请求后 3 秒无响应自动停等待音
- **WHEN** 等待音已播放且 DELAY_STOP_PLAY_TIME 内未收到 ReceiveUpdateCallMediaModeResponse
- **THEN** 打桩 EventHandler 的定时任务触发 ShouldStopWaitingTone 并停止等待音

#### Scenario: 收到响应取消定时任务
- **WHEN** waitingToneHandle_ 非空时调用 ReceiveUpdateCallMediaModeResponse
- **THEN** 打桩 EventHandler 取消定时任务并立即执行 ShouldStopWaitingTone

#### Scenario: 多方响铃时不停等待音
- **WHEN** ShouldStopWaitingTone 执行时存在响铃通话且当前通话数 >= MIN_MULITY_CALL_COUNT(2)
- **THEN** 不调用 StopWaitingTone，仅清空 waitingToneHandle_

### Requirement: core_service FDN 查询
系统 SHALL 由 `CoreServiceConnection::GetFdnNumberList(slotId)` 经 `CoreServiceClient::GetInstance().QueryIccDiallingNumbers(slotId, DiallingNumbersInfo::SIM_FDN, ...)`（stub/ 打桩）查询 FDN 号码列表并返回 u16string 向量（空列表时返回空向量）；`IsFdnEnabled(slotId)` 经 `CoreServiceClient::GetInstance().GetLockState(slotId, LockType::FDN_LOCK, lockState)`（stub/ 打桩）判断，仅当返回 TELEPHONY_ERR_SUCCESS 且 lockState 为 `LockState::LOCK_ON` 时返回 true。

#### Scenario: FDN 启用判断
- **WHEN** 桩的 GetLockState 返回成功且 lockState == LOCK_ON
- **THEN** IsFdnEnabled 返回 true

#### Scenario: FDN 号码列表为空
- **WHEN** 桩的 QueryIccDiallingNumbers 返回空列表
- **THEN** GetFdnNumberList 返回空向量

## REMOVED Requirements

### Requirement: 重连与服务状态监听
**Reason**: liteOS 无 samgr 服务状态监听与 IPC 重连机制，`RECONNECT_MAX_TRY_COUNT` 为不支持宏。
**Migration**: 客户端单例直连（`CellularCallClient::GetInstance().Xxx()` 打桩），连接失败即返回错误码。

### Requirement: IPC stub 命令分发
**Reason**: `call_status_callback_stub.cpp` 的 IPC OnRemoteRequest/memberFuncMap_ 命令分发机制不迁移。
**Migration**: cellular_call 桩直接调用 `CallStatusCallback` 进程内方法完成上报分发。

### Requirement: VoIP 服务代理交互
**Reason**: VoIP 类型通话暂不支持（依赖后续 meetime 畅连适配），`voip_call_connection.cpp` 不迁移。
**Migration**: 后续 change 适配畅连通话与蜂窝通话冲突场景。

### Requirement: 蓝牙 HFP 通话交互
**Reason**: BLUETOOTH 类型通话与 HFP 音频链路不支持，`bluetooth_call_connection.cpp` 不迁移。
**Migration**: 无。
