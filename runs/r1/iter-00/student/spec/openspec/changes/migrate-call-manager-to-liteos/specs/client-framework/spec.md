# Spec Delta

## MODIFIED Requirements

### Requirement: 客户端单例与未初始化防护
系统 SHALL 以 `DECLARE_DELAYED_SINGLETON`（`DelayedSingleton`）提供 `CallManagerClient` 全局单例：`Init` 惰性创建/复用进程内 `CallManagerService`（`DelayedSingleton<CallManagerService>`，本 change 引入的直连架构，不再经 samgr 连接 SA 4005，`systemAbilityId` 参数仅保留接口形态占位）；`UnInit` 释放对服务的引用；所有业务方法（如 `DialCall`、`AnswerCall`、`GetCallState`）在未初始化（未持有进程内服务）时记录 init first 日志并返回 `TELEPHONY_ERR_UNINIT`，否则直接透传给进程内 `CallManagerService` 同名方法。

#### Scenario: 未初始化即调用拨号
- **WHEN** 未调用 `CallManagerClient::Init` 直接调用 `DialCall("10086", extras)`
- **THEN** 返回 `TELEPHONY_ERR_UNINIT`，不触碰进程内 `CallManagerService`

#### Scenario: 初始化后透传
- **WHEN** 先 `CallManagerClient::Init` 成功再调用 `GetCallState()`
- **THEN** 请求直接透传给进程内 `CallManagerService::GetCallState()`，返回服务侧结果，无任何 samgr/IPC 参与

### Requirement: 回调注册与注销
系统 SHALL 由 `CallManagerProxy::RegisterCallBack(std::unique_ptr<CallManagerCallback>)` 完成注册：若 `registerStatus_` 已为 true 直接返回 `TELEPHONY_ERR_REGISTER_CALLBACK_FAIL`；否则创建 `CallAbilityCallback` 并以进程内指针直接交给 `CallManagerService::RegisterCallBack(callAbilityCallbackPtr_)`（无 IPC 序列化，不再有 `TELEPHONY_ERR_PERMISSION_ERR`、`TELEPHONY_ERR_ILLEGAL_USE_OF_SYSTEM_API` 的错误映射分支），失败返回 `TELEPHONY_ERR_REGISTER_CALLBACK_FAIL`；成功则 `SetProcessCallback(std::move(callback))` 并置 `registerStatus_` 为 true；`UnRegisterCallBack` 在未注册时同样返回 `TELEPHONY_ERR_REGISTER_CALLBACK_FAIL`，成功后清空 `callAbilityCallbackPtr_` 并复位 `registerStatus_`。

#### Scenario: 重复注册被拒
- **WHEN** `registerStatus_` 为 true 时再次调用 `RegisterCallBack`
- **THEN** 返回 `TELEPHONY_ERR_REGISTER_CALLBACK_FAIL`，原有回调保持不变

#### Scenario: 注册成功接管回调
- **WHEN** 进程内 `CallManagerService::RegisterCallBack` 返回 `TELEPHONY_SUCCESS`
- **THEN** 客户端回调经 `SetProcessCallback` 注入 `CallAbilityCallback`，后续服务侧事件沿进程内指针通路直接下发

## REMOVED Requirements

### Requirement: 连接服务与死亡通知注册
**Reason**: liteOS 单进程无 samgr/IPC，不存在经 `SystemAbilityManagerClient::GetSystemAbilityManager`、`GetSystemAbility` 的服务连接与 `AddDeathRecipient` 死亡通知注册。
**Migration**: `CallManagerClient` 直接连通进程内 `CallManagerService` 单例，无连接与死亡通知概念。

### Requirement: 按 IPC 码发送请求
**Reason**: 无 IPC 请求序列化，`CallManagerServiceProxy`（`IRemoteProxy<ICallManagerService>`）的 `SendRequest`/`WriteInterfaceToken` 路径不迁移。
**Migration**: 客户端方法级直调 `CallManagerService` 同名方法；`CallManagerInterfaceCode` 枚举保留在 `call_manager_service_ipc_interface_code.h` 接口头中且不动值，供后续恢复 IPC 对照（需人工复核项）。

### Requirement: 死亡通知与重连
**Reason**: 单进程无服务死亡，`CallManagerServiceDeathRecipient::OnRemoteDied`、`ReConnectService`、`ReRegisterCallBack` 无存在基础。
**Migration**: 无，进程内直连服务始终可达。

### Requirement: 外部 SA 代理类
**Reason**: `CellularCallProxy`、`CallStatusCallbackProxy`、`BluetoothCallProxy`、`CallManagerDeathRecipient` 等面向外部 SA 的 IPC 代理类在 liteOS 上无 IPC 通道。
**Migration**: cellular_call 交互经本 change 引入的 stub/ 桩 `CellularCallClient::GetInstance().Xxx()`；cellular_call 上行状态直接进程内调用 `CallStatusCallback`。