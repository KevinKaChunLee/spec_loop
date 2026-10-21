# Spec Delta

## MODIFIED Requirements

### Requirement: SystemAbility 生命周期
系统 SHALL 由 `CallManagerService`（不再继承 `SystemAbility`，保留 `DelayedSingleton`；首次 `GetInstance()` 时执行 `Init()` 懒初始化，幂等防重入）承载服务入口：`Init()` 依次初始化 `CallControlManager`、`ReportCallInfoHandler`、`CellularCallConnection`（协议栈边界改经 `CellularCallClient` 桩）、`CallRecordsManager`；`BluetoothConnection`、`DistributedCallManager`、`DistributedCommunicationManager`、`LocationSubscriber::Subscriber()`（地震预警）与 `AddSystemAbilityListener` 系列监听不迁移；`sa_profile/` 不随库交付；外部接口不做权限校验。
#### Scenario: 音频策略服务上线
- **WHEN** `Init()` 执行（无 `AddSystemAbilityListener` SA 监听）
- **THEN** `AudioProxy` 音频回调注册（`SetAudioMicStateChangeCallback`/`SetAudioDeviceChangeCallback`/`SetAudioPreferDeviceChangeCallback`）调用点以 `// todo!!! [audio]` 占位，初始化照常完成

#### Scenario: 客户端首次调用触发懒初始化
- **WHEN** `CallManagerClient` 首次调用任一业务接口
- **THEN** `CallManagerService::Init()` 按序完成子管理器初始化后同步执行该调用并返回结果

### Requirement: 拨号后语音信箱计数清零
系统 SHALL 由 `CallManagerService::DialCall` 在拨号成功后比对号码与 `CoreServiceClient::GetInstance().GetVoiceMailNumber(...)`（core_service 交互改客户端桩），相等则 `SetVoiceMailCount(slotId, 0)` 清零语音信箱计数；失败路径以日志记录原 `WriteDialCallFaultEvent` 信息。
#### Scenario: 拨打语音信箱号码
- **WHEN** 拨号号码等于桩配置的该 slot 语音信箱号码
- **THEN** 拨号继续执行且语音信箱未读计数被清零

### Requirement: 特殊拨号盘指令
系统 SHALL 由 `InputDialerSpecialCode` 匹配 `supportSpecialCode_`（"*#2846#"、"*#*#2846579#*#*" 等 16 项）后以 `// todo!!! [broadcast]` 占位原 `EventFwk::CommonEventManager::PublishCommonEvent` 发布 `COMMON_EVENT_SPECIAL_CODE` 的调用点（匹配逻辑保留，不真正发布广播）。
#### Scenario: 输入工程模式指令
- **WHEN** 应用调用 `InputDialerSpecialCode` 且指令串命中 `supportSpecialCode_`
- **THEN** 匹配判定执行，发布调用点为 todo 占位并返回成功，不产生真实广播

### Requirement: UI 事件路由
系统 SHALL 由 `SendCallUiEvent(callId, eventName)` 按事件名路由：`EVENT_IS_CELIA_CALL`→`dealCeliaCallEvent`、`EVENT_SPEAKER_OFF`→`AudioProxy::SetSpeakerDevActive(false)`（音频调用点以 `// todo!!! [audio]` 占位）、`DISPLAY_SPECIFIED_CALL_PAGE_BY_CALL_ID`→`HandleDisplaySpecifiedCallPage`（界面经桩）、`EVENT_CELIA_AUTO_ANSWER_CALL_ON/OFF`→`HandleCeliaAutoAnswerCall`、`EVENT_VOIP_CALL_SUCCESS/FAILED`→`HandleVoIPCallEvent` 保留；蓝牙事件（`EVENT_BLUETOOTH_SCO_STATE_ON/OFF`、`EVENT_SUPPORT_BLUETOOTH_CALL`/`EVENT_NOT_SUPPORT_BLUETOOTH_CALL`）与 `EVENT_INVALID_VIDEO_FD`（视频彩振）路由不迁移。
#### Scenario: 蓝牙 SCO 开启事件
- **WHEN** UI 事件路由收到蓝牙事件名（`EVENT_BLUETOOTH_SCO_STATE_ON/OFF` 等）
- **THEN** 蓝牙路由分支已移除，事件按不支持处理，不产生 SCO 音频链路连接

#### Scenario: 指定通话页请求经桩记录
- **WHEN** 通话界面经 `SendCallUiEvent` 上报 `DISPLAY_SPECIFIED_CALL_PAGE_BY_CALL_ID`
- **THEN** `HandleDisplaySpecifiedCallPage` 执行指定页请求（界面连接经桩），不因蓝牙/彩振路由缺失而失败

### Requirement: 蓝牙与 VoIP 回调注册
系统 SHALL 保留 `RegisterVoipCallManagerCallback`（经 `VoipCallConnection` 桩完成注册，暂无 voip_call_manager SA 对接，依赖后续畅连通话适配）；蓝牙回调注册（`GetProxyObjectPtr(PROXY_BLUETOOTH_CALL)`、`BluetoothCallService`、`CallStatusCallback`/`BluetoothCallState` 的 `RegisterObserver`、`BluetoothCallConnection::SetMacAddress`）不迁移。
#### Scenario: 蓝牙框架索取代理
- **WHEN** 外部请求 `PROXY_BLUETOOTH_CALL` 代理对象
- **THEN** 蓝牙代理链已移除（`proxyObjectPtrMap_` 无蓝牙代理），仅 VoIP 回调注册经 `VoipCallConnection` 桩可用

#### Scenario: VoIP 回调注册经桩
- **WHEN** VoIP 侧调用 `RegisterVoipCallManagerCallback`
- **THEN** 注册经 `VoipCallConnection` 桩完成并返回成功，不发生真实 SA 连接

### Requirement: TelephonyCust dlopen 包装
系统 SHALL 由 `TelephonyCustWrapper` 改经 `TelephonyCustClient::GetInstance()` 桩提供 `IsHideViolenceOrEmcNumbersInCallLog`（隐藏暴力/急救号记录）与 `IsChangeDialNumberToTwEmc`（台湾紧急号码改写）两个判定（不再 dlopen/dlsym；桩可配置，默认均为假）。
#### Scenario: 台湾紧急号码改写
- **WHEN** 桩配置 `IsChangeDialNumberToTwEmc` 为真且拨号命中改写名单
- **THEN** 拨号号码被改写后再下发（经 `CellularCallClient` 桩可见改写结果）

## REMOVED Requirements

### Requirement: IPC 码表分发
**Reason**: AGENTS.md 架构约束：liteOS 不继承 SystemAbility、不实现 IPC 调用；外部接口不做权限校验。
**Migration**: `CallManagerServiceStub` 与 `InitCallBasicRequest` 等十一组建表不迁移；`CallManagerInterfaceCode` 等 IPC 码表头保留（枚举值 ABI 冻结，需人工复核）；接口行为由 `CallManagerClient` 直调 `CallManagerService` 承载。

### Requirement: EDM 策略下发
**Reason**: AGENTS.md 功能范围：EDM 企业禁拨不支持。
**Migration**: `SetCallPolicyInfo`/`SetEdmPolicy` 与 `EdmCallPolicy` 不迁移；uid 3057 的策略下发接口不存在。
