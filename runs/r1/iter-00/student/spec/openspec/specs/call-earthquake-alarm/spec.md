# 地震预警来电（Call Earthquake Alarm） Specification

## Purpose
描述地震预警来电定位能力的基线行为：订阅地震预警开关公共事件、依赖系统服务就绪与 DataShare 设置项判定开关状态、经定位引擎上报位置、以及在紧急呼叫期间向后报位置。源码落点：`telephony_call_manager/services/call_earthquake_alarm/{include,src}`（`call_earthquake_alarm_subscriber.cpp`：`LocationSubscriber`/`DataShareSwitchState`/`LocationSystemAbilityListener`；`call_earthquake_alarm_locator.cpp`：`MyLocationEngine`/`OOBESwitchObserver`/`EmergencyCallConnectCallback`）。该能力无专属编译宏：源文件无条件列入 `callmanager.gni` 的 `call_manager_sources`。

## Requirements

### Requirement: 系统服务就绪与OOBE判定
系统 SHALL 由 `LocationSystemAbilityListener::OnAddSystemAbility` 在 `DISTRIBUTED_KV_DATA_SERVICE_ABILITY_ID`、`LOCATION_LOCATOR_SA_ID`、`LOCATION_NOPOWER_LOCATING_SA_ID` 全部就绪后启动服务：查询 `auto_send_earthquake_alarm_switch`（`SWITCH_STATE_KEY`）时若值仍为 `INITIAL_FIRST_VALUE`（`invalid`）则走 `MyLocationEngine::OOBEComplete`（注册 `device_provisioned`/`user_setup_complete`/`is_ota_finished` 的 DataShare 观察器 `OOBESwitchObserver`）；否则走 `MyLocationEngine::BootComplete` 按开关状态决定是否启动定位。
#### Scenario: OOBE 未完成
- **WHEN** 三个系统服务就绪且开关查询值为 `invalid`
- **THEN** 注册 `OOBESwitchObserver` 的三个 DataShare key 观察器，暂不启动定位
#### Scenario: OOBE 完成且开关开启
- **WHEN** 三个 DataShare key 均为开启且 `auto_send_earthquake_alarm_switch` 为开
- **THEN** `OOBESwitchObserver::OnChange` 触发 `OOBEComplete` 连接地震预警扩展并注销观察器

### Requirement: 开关公共事件订阅
系统 SHALL 由 `LocationSubscriber::Subscriber`（`call_manager_service.cpp` 初始化时调用）订阅 `usual.event.EMERGENCY_WARNINGS_SWITCH_STATE_CHANGE`（`SWITCH_STATE_CHANGE_EVENTS`，订阅权限 `ohos.permission.ATTEST_KEY`）：`OnReceiveEvent` 收到 `switchState` 为 `true` 时启动定位监听（`RegisterLocationChange`/`RegisterSwitchCallback`），为 `false` 时停止并复位（`UnregisterLocationChange`/`UnRegisterSwitchCallback`/`OnInit`）。
#### Scenario: 开关打开事件
- **WHEN** 事件 Want 的 `switchState` 参数为 `true`
- **THEN** `MyLocationEngine` 注册位置变化回调与定位开关回调
#### Scenario: 开关关闭事件
- **WHEN** 事件 Want 的 `switchState` 参数为 `false`
- **THEN** 注销位置变化与开关回调并复位引擎成员

### Requirement: 位置变化触发上报
系统 SHALL 由 `MyLocationEngine::RegisterLocationChange` 经 `Location::Locator`（`RequestConfig` 使用 `SCENE_NO_POWER` 场景并设置时间/距离间隔）启动定位；`MyLocationCallBack::OnLocationReport` 收到位置后 MUST 把 `latitude`/`longitude` 写入 Want，经 `MyLocationEngine::ConnectAbility`（`PARAMETERS_VALUE` 为 `call_manager_earthquake_alarm`）连接地震预警扩展（`EccServiceExtAbility`）转发位置；定位开关变化由 `MySwitchCallback::OnSwitchChange` 联动启停定位。
#### Scenario: 收到位置上报
- **WHEN** 定位回调携带非空 `Location` 对象
- **THEN** 以 `latitude`/`longitude` 参数连接 `EccServiceExtAbility` 扩展
#### Scenario: 定位开关从开到关
- **WHEN** `LocationSwitchChange` 检测到 `IsLocationEnabled` 由 true 变为 false
- **THEN** 注销位置变化回调（`UnregisterLocationChange`）

### Requirement: 紧急呼叫位置后报
系统 SHALL 由 `MyLocationEngine::StartEccService` 在通话为紧急呼叫（`attributeInfo.isEcc`）且设置项 `emergency_post_location_switch` 开启时，以 `slotId`/`phoneNumber` 参数（`PARAMETERS_VALUE_ECC` 为 `call_status_manager`）连接 `EccServiceExtAbility` 并记录 `nowCallId`；`StopEccService` MUST 仅在传入 `callId` 与 `nowCallId` 一致时断开该扩展连接并复位。
#### Scenario: 紧急呼叫启动后报
- **WHEN** 紧急来电接通且 `emergency_post_location_switch` 为开、无进行中的后报服务
- **THEN** 连接 `EccServiceExtAbility`，`nowCallId` 记录该呼叫，`isStartEccService` 置 true
#### Scenario: 呼叫结束停止后报
- **WHEN** `StopEccService` 收到的 `callId` 等于 `nowCallId`
- **THEN** 断开扩展连接并复位 `nowCallId`/`isStartEccService`

### Requirement: 开关状态数据查询
系统 SHALL 由 `DataShareSwitchState::QueryData` 通过 DataShare（URI 前缀 `datashare:///com.ohos.settingsdata/entry/settingsdata/SETTINGSDATA?Proxy=true&key=`，列 `KEYWORD`/`VALUE`）按 key 查询设置项值；`MyLocationEngine::IsSwitchOn` 在查询失败或值为 `ALARM_SWITCH_OFF`（`0`）时返回 false；`RegisterListenSettingsKey` 支持按 key 注册/注销 `IDataAbilityObserver` 观察器。
#### Scenario: 查询开关为开
- **WHEN** `QueryData` 返回 `TELEPHONY_SUCCESS` 且 VALUE 非 `0`
- **THEN** `IsSwitchOn` 返回 true
#### Scenario: 查询失败
- **WHEN** DataShare 查询结果为空或行数为 0
- **THEN** `QueryData` 返回 `INVALID_VALUE`，`IsSwitchOn` 返回 false
