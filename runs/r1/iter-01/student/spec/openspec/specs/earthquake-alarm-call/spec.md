# Earthquake Alarm Call Specification

## Purpose
描述目标仓中现有的地震预警（earthquake alarm）能力：在预警开关打开（设置键 `auto_send_earthquake_alarm_switch`）且依赖系统服务（分布式 KV 数据 SA、定位 SA、免功耗定位 SA）就绪后，通过定位 SA 持续免功耗监听设备位置（10km 距离间隔、0 时间间隔），并把携带经纬度（want 参数 `latitude` / `longitude`，`callerName`=call_manager_earthquake_alarm）的 `AAFwk::AbilityManagerClient::ConnectAbility` 连接交给应急侧 Ability，由应急侧据位置决策是否拉起预警通话（预警来电的发起方在应急应用侧，不在本仓）；紧急呼叫（ECC）拨打时同样经该连接把 slotId / phoneNumber 提供给 `EccServiceExtAbility`。预警来电经应急侧发起后按普通/紧急电话走本仓常规来电路径。落点：`services/call_earthquake_alarm/src/{call_earthquake_alarm_locator,call_earthquake_alarm_subscriber}.cpp`；订阅入口 `CallManagerService`（`LocationSubscriber::Subscriber`）与 SA 守候入口 `CallRecordsManager`（`COMMON_EVENT_DATA_SHARE_READY` 后 `LocationSystemAbilityListener::SystemAbilitySubscriber`）；ECC 调用点在 `CallStatusManager`（`DialingHandle` / `DisconnectedHandle`）。本能力有独立 gtest 入口 `tel_call_earthquake_alarm_test`（`test/unittest/call_earthquake_alarm_test/`，汇入 `test/unittest/BUILD.gn`）。本能力无专属编译宏（rg 核实：该目录无特性 `#ifdef`，两个源文件在 `callmanager.gni` 无条件编入）。

## Requirements

### Requirement: 预警开关公共事件订阅
系统 SHALL 由 `LocationSubscriber::Subscriber`（`CallManagerService::OnStart` 调用）通过 `EventFwk::CommonEventSubscribeInfo`（`MatchingSkills` 添加 `LocationSubscriber::SWITCH_STATE_CHANGE_EVENTS`="usual.event.EMERGENCY_WARNINGS_SWITCH_STATE_CHANGE"，`SetPermission("ohos.permission.ATTEST_KEY")`，单例 `subscriber_` 防重复）经 `EventFwk::CommonEventManager::SubscribeCommonEvent` 注册订阅。`LocationSubscriber::OnReceiveEvent` SHALL 解析 want 参数 `switchState`：等于 `SWITCH_STATE_START`（"true"）时启动定位监听（`MyLocationEngine::SetValue` + `RegisterLocationChange` + `RegisterSwitchCallback`）；等于 `SWITCH_STATE_STOP`（"false"）时停止（`UnregisterLocationChange` + `UnRegisterSwitchCallback` + `OnInit` 复位）。该公共事件订阅是移植时的独立桩化出口（广播依赖）。

#### Scenario: 开关打开
- **WHEN** `usual.event.EMERGENCY_WARNINGS_SWITCH_STATE_CHANGE` 事件 `switchState`="true"
- **THEN** 定位引擎初始化并开始位置监听与开关回调注册

#### Scenario: 开关关闭
- **WHEN** `switchState`="false"
- **THEN** 注销位置监听与开关回调，引擎字段复位

#### Scenario: 重复订阅防护
- **WHEN** `LocationSubscriber::Subscriber` 被再次调用
- **THEN** 单例已存在时不重复注册

### Requirement: 依赖系统服务就绪守候
系统 SHALL 由 `LocationSystemAbilityListener::SystemAbilitySubscriber`（`CallRecordsManager` 在 `COMMON_EVENT_DATA_SHARE_READY` 广播后调用）经 `SystemAbilityManagerClient` 订阅三个系统服务：`OHOS::DISTRIBUTED_KV_DATA_SERVICE_ABILITY_ID`、`OHOS::LOCATION_LOCATOR_SA_ID`、`OHOS::LOCATION_NOPOWER_LOCATING_SA_ID`。`OnAddSystemAbility` SHALL 拒绝非目标 SA 且在 `startService` 已置位时直接返回；每收到目标 SA 就更新 `systemAbilityStatus` 并以 `GetSystemAbility` 探活，三者全部就绪后按设置值分叉（见 OOBE / Boot 两 Requirement），最后 `SystemAbilitySubscriber()` 对已就绪项反订阅并置空 `statusChangeListener_`。

#### Scenario: 三服务相继就绪
- **WHEN** 1301 / 2802 / 2805 三个 SA 全部探活成功
- **THEN** 执行一次启动分叉并反订阅、清空监听器

#### Scenario: 非目标 SA
- **WHEN** `OnAddSystemAbility` 收到其他 SA id
- **THEN** 记日志返回，不改变就绪状态

### Requirement: OOBE 完成守候与预警启动
系统 SHALL 在 `LocationSystemAbilityListener::OnAddSystemAbility` 全就绪后查 `auto_send_earthquake_alarm_switch`（`MyLocationEngine::IsSwitchOn(LocationSubscriber::SWITCH_STATE_KEY, ...)`）：查询值仍为 `INITIAL_FIRST_VALUE`（"invalid"）视为 OOBE 未完成，走 `MyLocationEngine::OOBEComplete`——对键 `device_provisioned` / `user_setup_complete` / `is_ota_finished`（`OOBESwitchObserver::keyStatus`）逐个 `IsSwitchOn`，未开启的键以 `OOBESwitchObserver` 观察者经 `DataShareSwitchState::RegisterListenSettingsKey(key, true, observer)` 监听；`OOBESwitchObserver::OnChange` SHALL 待三键全部开启且 `auto_send_earthquake_alarm_switch` 开启时，以空 want + `callerName`=`PARAMETERS_VALUE_OOBE`（call_manager_oobe_earthquake_warning_switch_on）调用 `ConnectAbility`，随后经 `ffrt::submit` 批量 `RegisterListenSettingsKey(key, false, ...)` 注销观察者。否则（有值）走 `MyLocationEngine::BootComplete(alarmSwitchState)`：开关开则启动定位监听。

#### Scenario: OOBE 后自动开启
- **WHEN** 三键先后全部变为开且预警开关为开
- **THEN** 以 OOBE 标识连接应急 Ability，并注销全部设置观察者

#### Scenario: 未完成则仅守候
- **WHEN** 任一 OOBE 键未开启
- **THEN** 保持 DataShare 观察者监听，不启动预警上报

#### Scenario: 已完成 OOBE 的开机流程
- **WHEN** 就绪时设置值非 "invalid" 且为开
- **THEN** `BootComplete` 启动定位监听；开关关则直接返回

### Requirement: 定位监听与位置开关联动
系统 SHALL 由 `MyLocationEngine::SetValue` 初始化：`Location::Locator::GetInstance()`、记录 `IsLocationEnabled()` 初值到 `locationEnabled_`，`RequestConfig` 取 `Location::SCENE_NO_POWER` 且 `SetTimeInterval(TIMER_INTERVAL=0)`、`SetDistanceInterval(DISTANCE_INTERVAL=10000)`（10km）。`RegisterLocationChange` SHALL 在 `IsLocationEnabledV9` 为开时以 `MyLocationCallBack`（`sptr` 转 `ILocatorCallback`）调 `StartLocatingV9`，`UnregisterLocationChange` 调 `StopLocatingV9`。`RegisterSwitchCallback` 以 `MySwitchCallback` 调 `RegisterSwitchCallbackV9`，`MySwitchCallback::OnRemoteRequest`（校验 descriptor，code `RECEIVE_SWITCH_STATE_EVENT`）→ `OnSwitchChange` → `LocationSwitchChange` 按开关边沿翻转注册/注销。`MyLocationCallBack::OnRemoteRequest` SHALL 校验 descriptor 后分发三种 code：`RECEIVE_LOCATION_INFO_EVENT`（`Location::Location::UnmarshallingMakeUnique` 后进 `OnLocationReport`）、`RECEIVE_ERROR_INFO_EVENT`（`OnErrorReport`）、`RECEIVE_LOCATION_STATUS_EVENT`（`OnLocatingStatusChange`）。定位 SA 是移植时的独立桩化出口。

#### Scenario: 位置上报触发
- **WHEN** 定位 SA 推送 `RECEIVE_LOCATION_INFO_EVENT`
- **THEN** 反序列化位置对象并进入 `OnLocationReport`

#### Scenario: 定位开关打开的边沿
- **WHEN** `LocationSwitchChange` 检测到 false→true
- **THEN** 重新 `RegisterLocationChange`

#### Scenario: 定位开关关闭的边沿
- **WHEN** true→false
- **THEN** `UnregisterLocationChange`

### Requirement: 位置上报应急 Ability 连接
系统 SHALL 在 `MyLocationCallBack::OnLocationReport` 中以位置构造 `AAFwk::Want`（参数 `latitude` / `longitude` 为字符串化的 `GetLatitude()` / `GetLongitude()`），经 `MyLocationEngine::ConnectAbility(PARAMETERS_VALUE, EmergencyCallConnectCallback::connectCallback_, want)` 连接应急侧 Ability：`ConnectAbility` SHALL 设置参数 `callerName=PARAMETERS_VALUE`（"call_manager_earthquake_alarm"；ECC 场景为 `PARAMETERS_VALUE_ECC`="call_status_manager"），选择 abilityName（默认 `EMERGENCY_ABILITY_NAME`，值为 `PARAMETERS_VALUE_ECC` 时取 `EMERGENCY_ABILITY_NAME_ECC`="EccServiceExtAbility"），经 `AAFwk::AbilityManagerClient::GetInstance()->ConnectAbility(want, callback, userId=-1)` 建立 `IAbilityConnection`（回调桩 `EmergencyCallConnectCallback`，连接/断开仅记日志）。该 AA 连接是移植时的独立桩化出口；预警通话是否拨出由应急侧 Ability 决策。

#### Scenario: 携带经纬度连接
- **WHEN** 定位回调给出有效位置
- **THEN** 以经纬度参数与 call_manager_earthquake_alarm 标识连接应急 Ability

#### Scenario: 空位置丢弃
- **WHEN** `OnLocationReport` 收到空指针位置
- **THEN** 记日志返回，不发起连接

### Requirement: ECC 拨打的位置上报生命周期
系统 SHALL 在 `CallStatusManager::DialingHandle` 中 `NotifyNewCallCreated` 之后调用 `MyLocationEngine::StartEccService(call, info)`：以 `EmergencyCallConnectCallback::mutex_` 串行化，校验 `EmergencyCallConnectCallback::isStartEccService` 未占用、`call->GetCallAttributeInfo(attributeInfo)` 的 `isEcc` 为真、设置键 `emergency_post_location_switch`（`IsSwitchOn`）开启，随后以 want 参数 `slotId` / `phoneNumber` 调 `ConnectAbility(PARAMETERS_VALUE_ECC, connectCallbackEcc, want)`，记录 `nowCallId`（`call->GetCallID()`）并置 `isStartEccService=true`。`CallStatusManager::DisconnectedHandle` SHALL 调用 `MyLocationEngine::StopEccService(call->GetCallID())`：`connectCallbackEcc` 非空且 `nowCallId` 匹配时 `AAFwk::AbilityManagerClient::GetInstance()->DisconnectAbility` 并复位占用与 `nowCallId=-1`。

#### Scenario: ECC 拨打启动位置上报
- **WHEN** 拨打的 call 为 ECC 且上报开关开
- **THEN** 连接 `EccServiceExtAbility` 并携带槽位与号码（号码示例以 unknown 表示）

#### Scenario: 非 ECC 或开关关
- **WHEN** `isEcc` 为 false 或 `emergency_post_location_switch` 为关
- **THEN** 不启动，直接返回

#### Scenario: 呼叫结束停止上报
- **WHEN** 断开调用的 callId 与 `nowCallId` 一致
- **THEN** 断开 Ability 连接并复位占用标记

### Requirement: DataShare 设置键查询与观察
系统 SHALL 由 `DataShareSwitchState` 提供设置数据面访问：构造时 `CreateDataShareHelper(OHOS::TELEPHONY_CALL_MANAGER_SYS_ABILITY_ID)`（`DataShare::DataShareHelper::Creator(remote, SETTINGS_DATASHARE_URI, SETTINGS_DATASHARE_EXT_URI)`）；`QueryData(uri, key, value)` 以 `DataSharePredicates` 的 `KEYWORD` 等值查询，取 `VALUE` 列，行数为 0 或遍历失败返回 `INVALID_VALUE`(-1)；`RegisterListenSettingsKey(key, isReg, callback)` 以 `DEFAULT_URI`+key 经 `RegisterObserver` / `UnregisterObserver`（`sptr<AAFwk::IDataAbilityObserver>`）注册/注销键监听。该 DataShare 出口是移植时的独立桩化点。

#### Scenario: 查询开关值
- **WHEN** `QueryData` 以 `auto_send_earthquake_alarm_switch` 查询
- **THEN** 返回值列的字符串值与 0 状态码

#### Scenario: 键值监听回调
- **WHEN** 被监听键的值发生设置数据变更
- **THEN** `OOBESwitchObserver::OnChange` 被数据观察者触发