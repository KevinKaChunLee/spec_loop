# Spec Delta

## MODIFIED Requirements

### Requirement: OnStart 幂等启动
`CallManagerService` SHALL 不再继承 `SystemAbility`、不再提供 `OnStart()`/`SystemAbility::Publish` 语义，改为普通单例类的首次初始化：初始化入口检查 `state_`（`ServiceRunningState`），若已为 `STATE_RUNNING` 则直接返回（幂等）；否则调用 `Init()`，失败时记录 init failed 日志并返回，`state_` 保持 `STATE_STOPPED`，不对外提供服务；`Init()` 成功后置 `state_` 为 `STATE_RUNNING` 并记录 `spendTime_`。初始化入口由 `CallManagerClient` 直连触发（本 change 引入的进程内直连架构），单线程模型下不再依赖 `lock_` 加锁。

#### Scenario: 重复 OnStart 被幂等拦截
- **WHEN** 服务已处于 `STATE_RUNNING`（已完成首次初始化）时再次进入初始化入口（liteOS 上该入口由 `CallManagerClient` 直连触发，替代原 `OnStart`）
- **THEN** 幂等拦截直接返回，不重复执行 `Init()`，`GetServiceRunningState()` 仍返回 `STATE_RUNNING`

#### Scenario: Init 失败不发布服务
- **WHEN** `CallControlManager::Init()` 返回 false 导致 `CallManagerService::Init()` 返回 false
- **THEN** 记录 init failed 日志后返回，`state_` 保持 `STATE_STOPPED`，不置为运行态，服务不对外可用（liteOS 上无 `SystemAbility::Publish` 语义，进程内服务入口保持不可用）；此时 `GetCallState()` 返回 `TELEPHONY_ERR_LOCAL_PTR_NULL`（`callControlManagerPtr_` 为空），`HasCall()` 返回 false

### Requirement: Init 初始化管理器链
系统 SHALL 在 `CallManagerService::Init()` 中按基线实际链路保留可迁移项：`OHOS_BUILD_ENABLE_TELEPHONY_CUST` 宏下先调用 `TELEPHONY_CUST_WRAPPER.InitTelephonyCustWrapper()`；然后 `DelayedSingleton<CallControlManager>::GetInstance()->Init()` 并保存 `callControlManagerPtr_`；再 `DelayedSingleton<ReportCallInfoHandler>::GetInstance()->Init()`、`DelayedSingleton<CellularCallConnection>::GetInstance()->Init()`（改经本 change 引入的 `CellularCallClient::GetInstance()` 打桩，见 stub/）、`DelayedSingleton<CallRecordsManager>::GetInstance()->Init()`（DataShare 调用点 todo 占位）。`BluetoothConnection::Init()`、`DistributedCallManager::Init()`、`DistributedCommunicationManager::Init()` 与 `LocationSubscriber::Subscriber()`（地震预警，随 `call_earthquake_alarm` 移除）SHALL NOT 执行。基线 `OnAddSystemAbility` 的 SA 上线分发机制移除：原 `AUDIO_POLICY_SERVICE_ID` 分支的 `AudioProxy` 回调注册（`SetAudioMicStateChangeCallback`、`SetAudioDeviceChangeCallback`、`SetAudioPreferDeviceChangeCallback`）改为 `Init()` 中直接执行（其系统音频调用点按 audio-management 能力的 todo 占位承接）；`DISTRIBUTED_HARDWARE_DEVICEMANAGER_SA_ID` 分支随互通通话移除。

#### Scenario: 音频 SA 上线回调
- **WHEN** `CallManagerService::Init()` 执行完成管理器链初始化（原 `AUDIO_POLICY_SERVICE_ID` SA 上线触发点已移除）
- **THEN** 直接依次调用 `AudioProxy` 单例的 `SetAudioMicStateChangeCallback`、`SetAudioDeviceChangeCallback`、`SetAudioPreferDeviceChangeCallback`，不再等待任何 SA 上线回调

#### Scenario: 裁剪模块不参与初始化
- **WHEN** `CallManagerService::Init()` 执行
- **THEN** 不调用 `BluetoothConnection::Init()`、`DistributedCallManager::Init()`、`DistributedCommunicationManager::Init()`，也不存在 `OnAddSystemAbility` 的 SA 上线订阅与未处理 id 日志分支

#### Scenario: 未处理的 SA 上线
- **WHEN** liteOS 单进程直连架构下执行初始化（无 samgr，任何 SA 上线事件均无法到达服务）
- **THEN** 不存在 `AddSystemAbilityListener` 订阅与 `OnAddSystemAbility` 分发入口，原 switch 之外 systemAbilityId 的处理路径不可触达，`Init()` 只完成管理器链与音频回调注册

### Requirement: TelephonyCustWrapper 动态库封装
系统 SHALL 仅在定义 `OHOS_BUILD_ENABLE_TELEPHONY_CUST`（`TELEPHONY_CUST_SUPPORT`，均为支持宏）时启用 `TelephonyCustWrapper` 联动：`InitTelephonyCustWrapper()` 不再执行 `dlopen("libtelephony_cust_api.z.so")` 与 `dlsym` 解析 `IsHideViolenceOrEmcNumbersInCallLog`、`IsChangeDialNumberToTwEmc` 符号的动态库加载逻辑，改为调用本 change 引入的 `TelephonyCustClient::GetInstance().Xxx()`（stub/ 打桩，承接上述两个符号对应的查询能力）；桩接口初始化或调用失败时仅记录日志并返回错误，不阻断 `Init()` 与服务启动。

#### Scenario: 动态库缺失容忍
- **WHEN** `TelephonyCustClient::GetInstance()` 桩接口初始化失败或不可用（替代原 `libtelephony_cust_api.z.so` 缺失导致 `dlopen` 返回空的场景）
- **THEN** 仅记录错误日志后返回失败结果，对应查询能力保持不可用，`CallManagerService::Init()` 与首次初始化流程不受阻断，继续执行后续管理器链初始化

#### Scenario: 宏关闭时封装不参与
- **WHEN** 构建未定义 `OHOS_BUILD_ENABLE_TELEPHONY_CUST`
- **THEN** `Init()` 不调用 `TELEPHONY_CUST_WRAPPER.InitTelephonyCustWrapper()`，wrapper 代码不参与编译

### Requirement: 服务侧接口权限校验与查询面
系统 SHALL 对全部外部接口免权限校验直通：`TelephonyPermission::CheckCallerIsSystemApp` 与 `TelephonyPermission::CheckPermission`（对应 `OHOS_PERMISSION_SET_TELEPHONY_STATE`、`OHOS_PERMISSION_PLACE_CALL`、`OHOS_PERMISSION_ANSWER_CALL` 等）不调用，控制类接口（如 `SetMuted`）不再返回 `TELEPHONY_ERR_ILLEGAL_USE_OF_SYSTEM_API`、`TELEPHONY_ERR_PERMISSION_ERR`，直接转发 `callControlManagerPtr_`；查询类 `GetCallState()`/`HasCall()` 保留，直接转发 `callControlManagerPtr_`；`callControlManagerPtr_` 为空时控制与查询均返回 `TELEPHONY_ERR_LOCAL_PTR_NULL`（`HasCall` 返回 false）。

**需人工复核**：免权限校验直通为安全语义变更（对应 proposal.md「需人工复核」权限校验项）。

#### Scenario: 非系统应用调用设置类接口
- **WHEN** 非系统应用调用方（liteOS 上不再区分调用方身份）直接调用 `SetMuted` 且服务已完成初始化
- **THEN** 不执行 `TelephonyPermission::CheckCallerIsSystemApp` 与 `CheckPermission`，不再返回 `TELEPHONY_ERR_ILLEGAL_USE_OF_SYSTEM_API`，直接转发 `callControlManagerPtr_->SetMuted()`，返回业务结果

#### Scenario: GetCallState 无权限直查
- **WHEN** 任意调用方调用 `GetCallState()` 且服务已完成初始化（`callControlManagerPtr_` 非空）
- **THEN** 直接返回 `callControlManagerPtr_->GetCallState()`，不做任何系统应用与权限检查

#### Scenario: 未初始化时查询
- **WHEN** `callControlManagerPtr_` 为 nullptr 时调用 `GetCallState()`
- **THEN** 返回 `TELEPHONY_ERR_LOCAL_PTR_NULL`；调用 `HasCall()` 返回 false

## REMOVED Requirements

### Requirement: SA 注册与 profile 声明
**Reason**: liteOS 上 callmanager 不继承 `SystemAbility`、不做 SA 注册，`SystemAbility::MakeAndRegisterAbility` 静态注册与 `sa_profile/`（`4005.json`、`4005_auto_start_optimize.json`）不迁移。
**Migration**: `CallManagerService` 改为普通单例类（`DelayedSingleton`），由 `CallManagerClient` 进程内直连连通，无 samgr 参与。

### Requirement: IPC 请求分发
**Reason**: liteOS 上 callmanager 不实现 IPC，`CallManagerServiceStub::OnRemoteRequest`、接口令牌比对（`TELEPHONY_ERR_DESCRIPTOR_MISMATCH`）与 `memberFuncMap_` 分发不迁移。
**Migration**: `CallManagerClient` 直接调用 `CallManagerService` 同名方法；`CallManagerInterfaceCode` 枚举保留在接口头且不动值，供后续恢复 IPC 对照（需人工复核项）。

### Requirement: MUTE_BY_DATABASE 平台差异
**Reason**: `SUPPORT_MUTE_BY_DATABASE` 为不支持宏，watch 静音写数据库链路（`InteroperableSettingsHandler::SendMuteRinger`）随互通通话整体移除。
**Migration**: 静音只保留 audio-management 的调用点（音频接口以 `// todo!!! [audio] ref to ...` 占位）。