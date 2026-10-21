# Call Manager Service (SA 服务层) Specification

## Purpose
描述 OpenHarmony v6.0 基线中 call_manager 的 SystemAbility 服务层当前行为：`CallManagerService` 的注册、启动/初始化，`CallManagerServiceStub` 的 IPC 请求分发，`TelephonyCustWrapper` 动态库封装，以及服务侧对外接口面（含权限校验与查询类接口）。源码落点：`telephony_call_manager/services/call_manager_service/include/`（`call_manager_service.h`、`call_manager_service_stub.h`、`telephony_cust_wrapper.h`）与 `telephony_call_manager/services/call_manager_service/src/`（`call_manager_service.cpp`、`call_manager_service_stub.cpp`、`telephony_cust_wrapper.cpp`）；SA profile 落点：`telephony_call_manager/sa_profile/`（`4005.json`、`4005_auto_start_optimize.json`、`BUILD.gn`）。相关编译开关（来自 `telephony_call_manager/callmanager.gni` 的 global_parts_info 块）：`OHOS_BUILD_ENABLE_TELEPHONY_CUST`（telephony_telephony_cust 部件存在时定义）、`SUPPORT_MUTE_BY_DATABASE`（`target_platform == "watch"` 时定义）。

## Requirements

### Requirement: SA 注册与 profile 声明
系统 SHALL 在 `call_manager_service.cpp` 加载时通过 `SystemAbility::MakeAndRegisterAbility(DelayedSingleton<CallManagerService>::GetInstance().get())` 静态注册 SA，构造函数以 `SystemAbility(TELEPHONY_CALL_MANAGER_SYS_ABILITY_ID, true)` 声明；`sa_profile/4005.json` 声明 SA ID 4005、libpath `libtel_call_manager.z.so`、process `foundation`、`run-on-create: true`，`sa_profile/BUILD.gn` 在 `device_name == "rk3568"` 时改用 `4005_auto_start_optimize.json`（`run-on-create: false`）。

#### Scenario: 进程加载即注册 SA
- **WHEN** `libtel_call_manager.z.so` 在 foundation 进程内被加载
- **THEN** `g_registerResult` 完成静态注册，后续 samgr 可按 SA ID 4005 拉起 `CallManagerService`

#### Scenario: rk3568 设备选择自启动优化 profile
- **WHEN** 构建目标 `device_name` 为 `rk3568`
- **THEN** 安装的 SA profile 为 `4005_auto_start_optimize.json`，`run-on-create` 为 false；其他设备安装 `4005.json`，`run-on-create` 为 true

### Requirement: OnStart 幂等启动
系统 SHALL 在 `CallManagerService::OnStart()` 中持 `lock_` 检查 `state_`，若已为 `STATE_RUNNING` 则直接返回；否则先调用 `Init()`，失败时日志报错并返回（不发布服务）；`Init()` 成功后调用 `SystemAbility::Publish` 发布单例实例，成功后置 `state_` 为 `STATE_RUNNING` 并记录 `spendTime_`（`bindTime_` 由 `GetBindTime()` 查询时惰性设置）。

#### Scenario: 重复 OnStart 被幂等拦截
- **WHEN** 服务已处于 `STATE_RUNNING` 状态时再次触发 `OnStart`
- **THEN** 调用立即返回，不重复执行 `Init()` 与 `Publish`

#### Scenario: Init 失败不发布服务
- **WHEN** `CallControlManager::Init()` 返回 false 导致 `CallManagerService::Init()` 返回 false
- **THEN** `OnStart` 记录 init failed 日志后返回，`state_` 保持 `STATE_STOPPED`，SA 不被 Publish

### Requirement: Init 初始化管理器链
系统 SHALL 在 `CallManagerService::Init()` 中依次初始化：`OHOS_BUILD_ENABLE_TELEPHONY_CUST` 宏下先调用 `TELEPHONY_CUST_WRAPPER.InitTelephonyCustWrapper()`；然后 `DelayedSingleton<CallControlManager>::GetInstance()->Init()` 并保存 `callControlManagerPtr_`；再 `ReportCallInfoHandler::Init()`、`CellularCallConnection::Init(TELEPHONY_CELLULAR_CALL_SYS_ABILITY_ID)`、`CallRecordsManager::Init()`、`BluetoothConnection::Init()`、`DistributedCallManager::Init()`、`DistributedCommunicationManager::Init()`，并 `AddSystemAbilityListener` 订阅 `AUDIO_POLICY_SERVICE_ID` 与 `DISTRIBUTED_HARDWARE_DEVICEMANAGER_SA_ID`。

#### Scenario: 音频 SA 上线回调
- **WHEN** `OnAddSystemAbility` 收到 `AUDIO_POLICY_SERVICE_ID`
- **THEN** 通过 `AudioProxy` 单例依次设置 `SetAudioMicStateChangeCallback`、`SetAudioDeviceChangeCallback`、`SetAudioPreferDeviceChangeCallback`

#### Scenario: 未处理的 SA 上线
- **WHEN** `OnAddSystemAbility` 收到 switch 之外的 systemAbilityId
- **THEN** 记录 unhandle id 日志，不做任何初始化动作

### Requirement: IPC 请求分发
系统 SHALL 由 `CallManagerServiceStub::OnRemoteRequest` 统一分发 IPC：先比对 `GetDescriptor()` 与 `data.ReadInterfaceToken()`，不一致返回 `TELEPHONY_ERR_DESCRIPTOR_MISMATCH`；再以 code 查 `memberFuncMap_`（构造函数中由 `InitCallBasicRequest` 等 11 个 Init 函数按 `CallManagerInterfaceCode` 枚举值注册 `OnXxx` 处理器），命中则执行并回写 reply，未命中则透传 `IPCObjectStub::OnRemoteRequest`。

#### Scenario: 接口令牌不匹配
- **WHEN** 客户端 MessageParcel 的 InterfaceToken 与 `CallManagerServiceStub::GetDescriptor()` 不一致
- **THEN** `OnRemoteRequest` 返回 `TELEPHONY_ERR_DESCRIPTOR_MISMATCH`，不进入任何业务处理器

#### Scenario: 拨号请求分发
- **WHEN** 客户端以 `CallManagerInterfaceCode::INTERFACE_DIAL_CALL` 发起 IPC
- **THEN** `memberFuncMap_` 命中 `OnDialCall`，反序列化后调用 `CallManagerService::DialCall`，结果写入 reply

#### Scenario: 未知 code 透传
- **WHEN** 收到未注册进 `memberFuncMap_` 的 code
- **THEN** 走 `IPCObjectStub::OnRemoteRequest` 默认路径

### Requirement: TelephonyCustWrapper 动态库封装
系统 SHALL 仅在定义 `OHOS_BUILD_ENABLE_TELEPHONY_CUST` 时启用 `TelephonyCustWrapper`：`InitTelephonyCustWrapper()` 以 `dlopen("libtelephony_cust_api.z.so")` 打开动态库，再以 `dlsym` 解析 `IsHideViolenceOrEmcNumbersInCallLog` 与 `IsChangeDialNumberToTwEmc` 两个符号；任一步失败仅记录日志，不阻断服务启动。

#### Scenario: 动态库缺失容忍
- **WHEN** `libtelephony_cust_api.z.so` 不存在导致 `dlopen` 返回空
- **THEN** 记录 dlerror 日志后返回，两个函数指针保持 nullptr，`Init()` 与 `OnStart` 不受影响

#### Scenario: 宏关闭时封装不参与
- **WHEN** 构建未定义 `OHOS_BUILD_ENABLE_TELEPHONY_CUST`
- **THEN** `Init()` 不调用 `TELEPHONY_CUST_WRAPPER.InitTelephonyCustWrapper()`，wrapper 代码不参与编译

### Requirement: MUTE_BY_DATABASE 平台差异
系统 SHALL 仅在 `target_platform == "watch"`（定义 `SUPPORT_MUTE_BY_DATABASE`）时：`callmanager.gni` 将 `interoperable_settings_handler.cpp` 加入源码，`MuteRinger()` 成功后额外调用 `InteroperableSettingsHandler::SendMuteRinger()`；其他平台该调用不存在。

#### Scenario: watch 平台静音写数据库
- **WHEN** watch 平台 `MuteRinger()` 返回 `TELEPHONY_SUCCESS`
- **THEN** 在分布式/互通静音之后执行 `InteroperableSettingsHandler::SendMuteRinger()`

#### Scenario: 非 watch 平台静音不写数据库
- **WHEN** 非 watch 平台 `MuteRinger()` 成功
- **THEN** 只执行 `DistributedCommunicationManager` 与 `InteroperableCommunicationManager` 的 `MuteRinger()`，无 `SendMuteRinger()` 调用

### Requirement: 服务侧接口权限校验与查询面
系统 SHALL 对控制类接口（如 `SetMuted`、`IsRinging`、`RegisterCallBack`）先执行 `TelephonyPermission::CheckCallerIsSystemApp` 与 `CheckPermission`（对应 `ohos.permission.SET_TELEPHONY_STATE` 等权限），失败分别返回 `TELEPHONY_ERR_ILLEGAL_USE_OF_SYSTEM_API`、`TELEPHONY_ERR_PERMISSION_ERR`；查询类 `GetCallState()`/`HasCall()` 不做权限校验直接转发 `callControlManagerPtr_`；`callControlManagerPtr_` 为空时控制与查询均返回 `TELEPHONY_ERR_LOCAL_PTR_NULL`（`HasCall` 返回 false）。

#### Scenario: 非系统应用调用设置类接口
- **WHEN** 非系统应用经 IPC 调用 `SetMuted`
- **THEN** 返回 `TELEPHONY_ERR_ILLEGAL_USE_OF_SYSTEM_API`，不触碰 `CallControlManager`

#### Scenario: GetCallState 无权限直查
- **WHEN** 任意已连接客户端调用 `GetCallState()` 且服务已初始化
- **THEN** 直接返回 `callControlManagerPtr_->GetCallState()`，不做系统应用与权限检查

#### Scenario: 未初始化时查询
- **WHEN** `callControlManagerPtr_` 为 nullptr 时调用 `GetCallState()`
- **THEN** 返回 `TELEPHONY_ERR_LOCAL_PTR_NULL`；调用 `HasCall()` 返回 false
