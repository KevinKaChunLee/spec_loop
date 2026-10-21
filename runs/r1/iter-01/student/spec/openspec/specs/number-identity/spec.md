# Number Identity Specification

## Purpose
描述目标仓中现有的号码识别（number identity）外部服务同步能力：当收到 HSDR 分发的号码标记数据更新公共事件（`usual.event.HSDR_EVENT`，data 含 `com.numberidentity.devicenumber`）时，连接号码识别服务 `com.numberidentity` 的 `NumberIdentityServiceExtAbility`（AA ServiceExtension 连接 + IPC；rg 核实：本能力的外部依赖不是 DataShare），并通过 IPC（code `IMPORT_NUMBER_MARK_DATA_FILE`，描述符 `com.numberidentity:NumberIdentityService`）通知其对标记数据文件执行更新。本地号码标记/黄页数据库查询能力（`utils/src/number_identity_data_base_helper.cpp`、`utils/src/call_number_utils.cpp` 的 `QueryYellowPageAndMarkInfo` 上报链）落点在 utils，属号码标记数据库能力，不在本规格范围内。落点：`services/number_identity_proxy/src/number_identity_service.cpp`。本能力无专属编译宏（rg 核实：该目录无特性 `#ifdef`，源文件在 `callmanager.gni` 无条件编入）。

## Requirements

### Requirement: HSDR 事件的订阅注册
系统 SHALL 由 `CallControlManager::SystemAbilityListener::HSDRBroadcastSubscriber` 通过 `EventFwk::MatchingSkills` 订阅公共事件 `usual.event.HSDR_EVENT`（`subscriberInfos.SetPublisherBundleName("com.hsdr")`、`SetPermission("ohos.permission.securityguard.REPORT_SECURITY_INFO")`、`COMMON` 线程模式），事件经 `CallBroadcastSubscriber::OnReceiveEvent` 分发到 `HsdrEventBroadcast`。该公共事件订阅是移植时的独立桩化出口（广播依赖）。

#### Scenario: 订阅成功
- **WHEN** call manager 服务初始化并注册 HSDR 事件订阅
- **THEN** 后续 `usual.event.HSDR_EVENT` 事件按 code `HSDR_EVENT` 进入 `HsdrEventBroadcast` 处理

### Requirement: HSDR 事件触发标记数据更新通知
系统 SHALL 在 `CallBroadcastSubscriber::HsdrEventBroadcast` 中检查事件的 data 字符串：命中子串 `com.numberidentity.devicenumber` 时调用 `DelayedRefSingleton<NumberIdentityServiceHelper>::GetInstance().NotifyNumberMarkDataUpdate()`，否则不做处理。

#### Scenario: 命中号码识别数据事件
- **WHEN** HSDR 事件 data 含 `com.numberidentity.devicenumber`
- **THEN** 触发一次 `NotifyNumberMarkDataUpdate` 流程

#### Scenario: 其他 HSDR 事件
- **WHEN** data 不含该子串
- **THEN** 仅记日志，不触发通知

### Requirement: 号码识别服务连接管理
系统 SHALL 由 `NumberIdentityServiceHelper::Connect(onConnected, onDisconnected)` 管理服务连接：构建 `AAFwk::Want`（`NUMBER_IDENTITY_BUNDLE_NAME`="com.numberidentity"，`NUMBER_IDENTITY_SERVICE_EXT_ABILITY`="NumberIdentityServiceExtAbility"，`USER_ID`=100）经 `AAFwk::ExtensionManagerClient::ConnectServiceExtensionAbility` 连接；已有存活连接（`NumberIdentityConnection::IsAlive`：远端对象存在且未死）SHALL 以 `ffrt::submit`（`qos_background`）回调旧代理复用；连接失败返回 `TELEPHONY_ERR_IPC_CONNECT_STUB_FAIL`。`Disconnect` SHALL 调 `DisconnectAbility` 并清空 `connection_`。`NumberIdentityConnection` SHALL 在 `OnAbilityConnectDone` 中校验远端非空后存入 `remoteObject_` 并异步（`ffrt::submit`、`qos_background`）分发 `connectedCallback_`，在 `OnAbilityDisconnectDone` 中清空远端并异步分发 `disconnectedCallback_`。该 AA 连接是移植时的独立桩化出口。

#### Scenario: 首次连接
- **WHEN** 无存活连接且 `ConnectServiceExtensionAbility` 成功
- **THEN** 连接建立后远端对象经回调交给上层执行通知

#### Scenario: 复用已有连接
- **WHEN** `Connect` 时 `connection_->IsAlive()`
- **THEN** 不再发起新连接，直接以旧代理异步回调

#### Scenario: 连接失败
- **WHEN** `ConnectServiceExtensionAbility` 返回非 `ERR_OK`
- **THEN** 返回 `TELEPHONY_ERR_IPC_CONNECT_STUB_FAIL`，`NotifyNumberMarkDataUpdate` 记日志终止

### Requirement: 更新通知的一次执行防重入
系统 SHALL 在 `NumberIdentityServiceHelper::NotifyNumberMarkDataUpdate` 中用原子位 `working_` 保证同一时刻只有一个更新任务在跑（`working_` 已为 true 的后续连接回调直接跳过并记日志）；连接成功的 `onConnected` 内完成 IPC 后即 `Disconnect`，断开回调 `onDisconnected` 中复位 `working_=false`。

#### Scenario: 任务进行中重复触发
- **WHEN** `working_` 为 true 时又一次更新通知到达连接回调
- **THEN** 跳过本次通知

#### Scenario: 任务后清理
- **WHEN** 服务断开回调到来
- **THEN** `working_` 复位 false，允许下一轮通知

### Requirement: 标记数据更新 IPC
系统 SHALL 由 `NumberIdentityServiceProxy::NotifyNumberMarkDataUpdate` （`INumberIdentityService` 描述符 `com.numberidentity:NumberIdentityService`，`NumberIdentityServiceMessageCode::IMPORT_NUMBER_MARK_DATA_FILE`=0）发送 IPC：`Remote()` 为空或 `IsObjectDead()` 时记日志（空指针直接返回）；`SendRequest` 失败或 `reply` 读得非 `ERR_OK` 记错误日志。请求 parcel 仅含接口 token，无业务参数（更新范围由服务侧按自身数据文件决定）。

#### Scenario: 通知成功
- **WHEN** 远端返回 `ERR_OK`
- **THEN** 记 "notify done" 日志，流程结束

#### Scenario: 远端失效
- **WHEN** `Remote()` 为空
- **THEN** 函数直接返回，不再发送请求