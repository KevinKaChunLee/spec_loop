# Spec Delta

## MODIFIED Requirements

### Requirement: HSDR 事件的订阅注册
系统 SHALL 保留 `CallControlManager::SystemAbilityListener::HSDRBroadcastSubscriber` 通过 `EventFwk::MatchingSkills` 订阅公共事件 `usual.event.HSDR_EVENT`（`subscriberInfos.SetPublisherBundleName("com.hsdr")`、`SetPermission("ohos.permission.securityguard.REPORT_SECURITY_INFO")`、`COMMON` 线程模式）与事件经 `CallBroadcastSubscriber::OnReceiveEvent` 按 code `HSDR_EVENT` 分发到 `HsdrEventBroadcast` 的逻辑，口径与 call-status-management delta「HSDR 号码识别数据更新」场景保持一致：订阅建立逻辑保留（原 samgr `SystemAbilityListener` 宿主随无 samgr 形态不迁移，design D2；`MatchingSkills` 构造照抄），`EventFwk::CommonEventManager` 订阅调用点标注 `// todo!!! [broadcast]` 占位（AGENTS：广播相关接口暂不调用，逻辑保留）。

#### Scenario: 订阅成功
- **WHEN** call manager 服务初始化并注册 HSDR 事件订阅（订阅调用点 todo [broadcast]）
- **THEN** 后续 `usual.event.HSDR_EVENT` 事件（经桩注入）按 code `HSDR_EVENT` 进入 `HsdrEventBroadcast` 处理（照抄）

### Requirement: HSDR 事件触发标记数据更新通知
系统 SHALL 照抄保留 `CallBroadcastSubscriber::HsdrEventBroadcast` 对事件 data 字符串的检查：命中子串 `com.numberidentity.devicenumber` 时调用 `DelayedRefSingleton<NumberIdentityServiceHelper>::GetInstance().NotifyNumberMarkDataUpdate()`，否则不做处理仅记日志。

#### Scenario: 命中号码识别数据事件
- **WHEN** HSDR 事件 data 含 `com.numberidentity.devicenumber`
- **THEN** 触发一次 `NotifyNumberMarkDataUpdate` 流程（照抄）

#### Scenario: 其他 HSDR 事件
- **WHEN** data 不含该子串
- **THEN** 仅记日志，不触发通知（照抄）

### Requirement: 号码识别服务连接管理
系统 SHALL 保留 `NumberIdentityServiceHelper::Connect(onConnected, onDisconnected)` / `Disconnect` 的连接管理逻辑与 `NumberIdentityConnection` 的 `IsAlive` / `OnAbilityConnectDone` / `OnAbilityDisconnectDone` 回调形态照抄：`AAFwk::Want`（`NUMBER_IDENTITY_BUNDLE_NAME`="com.numberidentity"、`NUMBER_IDENTITY_SERVICE_EXT_ABILITY`="NumberIdentityServiceExtAbility"、`USER_ID`=100）构建照抄；`AAFwk::ExtensionManagerClient::ConnectServiceExtensionAbility` / `DisconnectAbility` 连接与断开调用点经 `stub/` 打桩并标注 `// todo!!! [numberIdentity] ref to number_identity_service.cpp Connect`（AGENTS：号码识别/黄页标记相关接口暂不调用，依赖数据库接口适配；桩默认返回失败/不可用，与基线连接失败分支语义一致）；已有存活连接（`IsAlive`：远端对象存在且未死）以旧代理异步回调复用的路径保留；基线 `ffrt::submit`（`qos_background`）异步回调改经 `stub/eventhandler_stub` 打桩 EventHandler 提交（design D6 ffrt 行/D8，不新增线程）；`remoteObject_` 持有按 design D5 换 std 智能指针，`connection_` 断开清空照抄。

#### Scenario: 首次连接
- **WHEN** 无存活连接且连接语义（todo [numberIdentity] 桩注入）成功
- **THEN** 连接建立后远端对象经回调交给上层执行通知（照抄）

#### Scenario: 复用已有连接
- **WHEN** `Connect` 时 `connection_->IsAlive()`
- **THEN** 不再发起新连接，直接以旧代理异步回调（经桩 EventHandler 提交，照抄）

#### Scenario: 连接失败
- **WHEN** 连接 todo 桩默认态返回非 `ERR_OK`
- **THEN** 返回 `TELEPHONY_ERR_IPC_CONNECT_STUB_FAIL`，`NotifyNumberMarkDataUpdate` 记日志终止（照抄）

### Requirement: 更新通知的一次执行防重入
系统 SHALL 照抄保留 `NumberIdentityServiceHelper::NotifyNumberMarkDataUpdate` 的原子位 `working_` 防重入链：`working_` 已为 true 的后续连接回调直接跳过并记日志；连接成功的 `onConnected` 内完成通知后即 `Disconnect`，断开回调 `onDisconnected` 中复位 `working_=false`（异步回调经桩 EventHandler 提交）。liteOS 单线程下无并发冲突，防重入语义按 design D9 行为保持默认照抄。

#### Scenario: 任务进行中重复触发
- **WHEN** `working_` 为 true 时又一次更新通知到达连接回调
- **THEN** 跳过本次通知（照抄）

#### Scenario: 任务后清理
- **WHEN** 服务断开回调到来
- **THEN** `working_` 复位 false，允许下一轮通知（照抄）

### Requirement: 标记数据更新 IPC
系统 SHALL 保留 `NumberIdentityServiceProxy::NotifyNumberMarkDataUpdate` 的判定与日志逻辑照抄（design D6 号码识别行：IPC 新建删除、留桩）：`Remote()` 为空或 `IsObjectDead()` 时记日志（空指针直接返回）；`SendRequest` 失败或 `reply` 读得非 `ERR_OK` 记错误日志；请求 parcel 仅含接口 token（`INumberIdentityService` 描述符 `com.numberidentity:NumberIdentityService`、`NumberIdentityServiceMessageCode::IMPORT_NUMBER_MARK_DATA_FILE`=0）无业务参数照抄（更新范围由服务侧按自身数据文件决定）。IPC 发送调用点标注 `// todo!!! [numberIdentity] ref to number_identity_service.cpp NotifyNumberMarkDataUpdate`（liteOS 无 IPC 通路，回环经桩注入驱动验证）。本地号码标记/黄页数据库查询链（`utils/src/number_identity_data_base_helper.cpp`）查询出口 todo [database]，处置见 call-utils delta「号码身份数据库助手」条。

#### Scenario: 通知成功
- **WHEN** 桩注入远端返回 `ERR_OK`
- **THEN** 记 "notify done" 日志，流程结束（照抄）

#### Scenario: 远端失效
- **WHEN** `Remote()` 为空
- **THEN** 函数直接返回，不再发送请求（照抄）
