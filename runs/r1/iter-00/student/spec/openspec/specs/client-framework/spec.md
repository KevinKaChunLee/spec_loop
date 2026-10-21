# Client Framework (原生客户端框架) Specification

## Purpose
描述 OpenHarmony v6.0 基线中 call_manager 原生客户端框架的当前行为：`CallManagerClient` 的单例与代理获取、`CallManagerProxy` 连接 SA 4005、`CallManagerServiceProxy` 按 IPC 码发请求、错误码体系、回调注册与死亡通知/重连，以及面向 cellular_call 的 `CellularCallProxy` 与 `CallStatusCallbackProxy` 等代理类。源码落点：`telephony_call_manager/frameworks/native/include/`（`call_manager_proxy.h`、`call_manager_service_proxy.h`、`call_ability_callback.h`、`i_call_manager_service.h` 等）与 `telephony_call_manager/frameworks/native/src/`（`call_manager_client.cpp`、`call_manager_proxy.cpp`、`call_manager_service_proxy.cpp`、`cellular_call_proxy.cpp`、`call_status_callback_proxy.cpp` 等）；公共接口落点：`telephony_call_manager/interfaces/innerkits/`（`call_manager_client.h`、`call_manager_errors.h`、`call_manager_service_ipc_interface_code.h`、`i_call_status_callback.h`、`cellular_call_proxy.h`、`call_status_callback_proxy.h` 等）。本能力无专属 declare_args 开关；`frameworks/native/BUILD.gn` 在 `device_name == "rk3568"` 时定义 `CALL_MANAGER_AUTO_START_OPTIMIZE`。

## Requirements

### Requirement: 客户端单例与未初始化防护
系统 SHALL 以 `DECLARE_DELAYED_SINGLETON(CallManagerClient)` 提供全局单例：`Init(systemAbilityId)` 惰性创建/复用全局 `g_callManagerProxy`（`DelayedSingleton<CallManagerProxy>`）并转发 `Init`；`UnInit` 转发 `UnInit`；所有业务方法（如 `DialCall`、`AnswerCall`、`GetCallState`）在 `g_callManagerProxy` 为空时记录 init first 日志并返回 `TELEPHONY_ERR_UNINIT`，否则透传给代理。

#### Scenario: 未初始化即调用拨号
- **WHEN** 未调用 `CallManagerClient::Init` 直接调用 `DialCall("10086", extras)`
- **THEN** 返回 `TELEPHONY_ERR_UNINIT`，不发起任何 IPC

#### Scenario: 初始化后透传
- **WHEN** 先 `Init(TELEPHONY_CALL_MANAGER_SYS_ABILITY_ID)` 成功再调用 `GetCallState()`
- **THEN** 请求透传至 `CallManagerProxy::GetCallState()`，返回代理侧结果

### Requirement: 连接服务与死亡通知注册
系统 SHALL 由 `CallManagerProxy::ConnectService()` 完成连接：经 `SystemAbilityManagerClient::GetInstance().GetSystemAbilityManager()` 取 `ISystemAbilityManager`，再 `GetSystemAbility(systemAbilityId_)` 取 `IRemoteObject`（空则返回 `TELEPHONY_ERR_IPC_CONNECT_STUB_FAIL`）；对代理对象 `AddDeathRecipient` 挂接内部类 `CallManagerServiceDeathRecipient`，`iface_cast<ICallManagerService>` 得到服务代理；`Init` 成功后置 `initStatus_` 为 true，重复 `Init` 时记录 already initialized 日志并跳过。

#### Scenario: SA 不在线连接失败
- **WHEN** `GetSystemAbility` 返回 nullptr
- **THEN** `ConnectService` 返回 `TELEPHONY_ERR_IPC_CONNECT_STUB_FAIL`，`initStatus_` 保持 false

#### Scenario: 重复初始化
- **WHEN** `initStatus_` 已为 true 时再次调用 `CallManagerProxy::Init`
- **THEN** 记录 already initialized 日志后直接返回，不重复连接

### Requirement: 按 IPC 码发送请求
系统 SHALL 由 `CallManagerServiceProxy`（`IRemoteProxy<ICallManagerService>`）将每个客户端方法编码为一次 `SendRequest`：先 `WriteInterfaceToken(GetDescriptor())`（失败返回 `TELEPHONY_ERR_WRITE_DESCRIPTOR_TOKEN_FAIL`），再按方法写入参数并以 `CallManagerInterfaceCode` 枚举值（如 `INTERFACE_DIAL_CALL`、`INTERFACE_ANSWER_CALL`、`INTERFACE_DISCONNECT_CALL`、`INTERFACE_GET_CALL_STATE`、`INTERFACE_REGISTER_CALLBACK`）作为 code；发送失败返回 `TELEPHONY_ERR_IPC_CONNECT_STUB_FAIL`，成功时返回 `replyParcel.ReadInt32()` 的业务结果。

#### Scenario: 挂断使用 DISCONNECT 码
- **WHEN** 客户端调用 `CallManagerServiceProxy::HangUpCall(callId)`
- **THEN** 以 `INTERFACE_DISCONNECT_CALL` 为 code 携带 callId 发送 IPC，返回 reply 中的业务码

#### Scenario: 无参查询直发
- **WHEN** 客户端调用 `GetCallState()`
- **THEN** 仅携带接口令牌以 `INTERFACE_GET_CALL_STATE` 发送，返回 reply 中的通话状态值

#### Scenario: 令牌写入失败
- **WHEN** `WriteInterfaceToken` 返回 false
- **THEN** 方法立即返回 `TELEPHONY_ERR_WRITE_DESCRIPTOR_TOKEN_FAIL`，不发送请求

### Requirement: 错误码体系
系统 SHALL 在 `interfaces/innerkits/call_manager_errors.h` 以 `CALL_ERR_OFFSET` 为基定义 `CallManagerErrorCode` 枚举（如 `CALL_ERR_INVALID_CALLID`、`CALL_ERR_PHONE_NUMBER_EMPTY`、`CALL_ERR_UNKNOW_CALL_TYPE`、`CALL_ERR_FUNCTION_NOT_SUPPORTED`），以 `PROTOCOL_ERR_OFFSET` 为基定义 `PROTOCOL_ERROR_TYPE`；客户端各方法把服务端写入 reply 的错误码原样返回给调用者。

#### Scenario: 业务错误码透传
- **WHEN** 服务端 `DialCall` 因无效 callId 相关校验在 reply 写入 `CALL_ERR_*` 值
- **THEN** `CallManagerServiceProxy::DialCall` 将该值作为返回值交给 `CallManagerClient`，不重新包装

### Requirement: 回调注册与注销
系统 SHALL 由 `CallManagerProxy::RegisterCallBack(std::unique_ptr<CallManagerCallback>)` 完成：若 `registerStatus_` 已为 true 直接返回 `TELEPHONY_ERR_REGISTER_CALLBACK_FAIL`；否则 new 一个 `CallAbilityCallback`（sptr），调用 `callManagerServicePtr_->RegisterCallBack(callAbilityCallbackPtr_)`，失败按服务端返回值映射（`TELEPHONY_ERR_PERMISSION_ERR`、`TELEPHONY_ERR_ILLEGAL_USE_OF_SYSTEM_API` 或 `TELEPHONY_ERR_REGISTER_CALLBACK_FAIL`），成功则 `SetProcessCallback(std::move(callback))` 并置 `registerStatus_` 为 true；`UnRegisterCallBack` 在未注册时同样返回 `TELEPHONY_ERR_REGISTER_CALLBACK_FAIL`，成功后清空 `callAbilityCallbackPtr_` 并复位 `registerStatus_`。

#### Scenario: 重复注册被拒
- **WHEN** `registerStatus_` 为 true 时再次调用 `RegisterCallBack`
- **THEN** 返回 `TELEPHONY_ERR_REGISTER_CALLBACK_FAIL`，原有回调保持不变

#### Scenario: 注册成功接管回调
- **WHEN** 服务端 `RegisterCallBack` 返回 `TELEPHONY_SUCCESS`
- **THEN** 客户端回调经 `SetProcessCallback` 注入 `CallAbilityCallback`，后续服务侧事件沿该通路下发

### Requirement: 死亡通知与重连
系统 SHALL 在服务死亡时由 `CallManagerServiceDeathRecipient::OnRemoteDied` 转入 `CallManagerProxy::OnRemoteDied`：比对 `callManagerServicePtr_->AsObject()` 与死亡对象一致后 `RemoveDeathRecipient`、清空 `callManagerServicePtr_`、置 `initStatus_` 为 false；后续业务调用经 `ReConnectService()` 重建连接（失败返回 `TELEPHONY_ERR_IPC_CONNECT_STUB_FAIL`），且若此前 `registerStatus_` 为 true 则 `ReRegisterCallBack()` 重新注册 `callAbilityCallbackPtr_`。

#### Scenario: 服务死亡后置为未连接
- **WHEN** SA 4005 死亡触发 `OnRemoteDied` 且对象匹配
- **THEN** `callManagerServicePtr_` 为 nullptr、`initStatus_` 为 false，旧死亡通知被移除

#### Scenario: 业务触发重连并补注册
- **WHEN** 死亡后调用任一走 `ReConnectService` 的方法且重连成功、此前已注册回调
- **THEN** `ConnectService` 重建代理后自动执行 `ReRegisterCallBack`，方法返回 `TELEPHONY_SUCCESS`

### Requirement: 外部 SA 代理类
系统 SHALL 在 `frameworks/native` 内提供面向其他 SA 的代理类：`CellularCallProxy`（`IRemoteProxy<CellularCallInterface>`，基于 `cellular_call_ipc_interface_code.h` 的 IPC 码，提供 `Dial`、`HangUp`、`Answer`、`HoldCall`、`UnHoldCall` 等方法）；`CallStatusCallbackProxy`（`IRemoteProxy<ICallStatusCallback>`，提供 `UpdateCallReportInfo`、`UpdateCallsReportInfo`、`UpdateDisconnectedCause`、`UpdateEventResultInfo`、`UpdateGetWaitingResult` 等上报方法）；另有 `BluetoothCallProxy`、`CallManagerDeathRecipient`（通用死亡通知封装）等。

#### Scenario: 蜂窝通话代理走专用 IPC 码
- **WHEN** 持有 cellular_call 的 `IRemoteObject` 构造 `CellularCallProxy` 并调用 `Dial(callInfo)`
- **THEN** 请求按 `cellular_call_ipc_interface_code.h` 定义的码经 `SendRequest` 发往 cellular_call 服务

#### Scenario: 通话状态回调上报
- **WHEN** 以 `CallStatusCallbackProxy::UpdateCallReportInfo(info)` 上报 `CallReportInfo`
- **THEN** 序列化 info 后按 `call_status_callback_ipc_interface_code.h` 的码发送 IPC，目标端为注册方
