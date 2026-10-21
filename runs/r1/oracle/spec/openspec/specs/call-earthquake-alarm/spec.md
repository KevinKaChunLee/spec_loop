# 地震预警来电（call-earthquake-alarm）Specification

## Purpose
描述 `telephony_call_manager/services/call_earthquake_alarm/` 的地震预警模块组：`MyLocationEngine`（无功耗定位与开关回调，`services/call_earthquake_alarm/src/call_earthquake_alarm_locator.cpp`）、`LocationSubscriber`/`DataShareSwitchState`/`LocationSystemAbilityListener`（广播与 SA 就绪编排，`src/call_earthquake_alarm_subscriber.cpp`）。落点：`include/call_earthquake_alarm_locator.h` 与 `include/call_earthquake_alarm_subscriber.h`。该模块组无独有编译开关；依赖 `Location::Locator`（`RequestConfig(SCENE_NO_POWER)`，`DISTANCE_INTERVAL = 10000` 米）与 devicemanager/softbus 外部能力。

## Requirements

### Requirement: 地震预警开关与定位编排
系统 SHALL 由 `LocationSubscriber::Subscriber()`（`CallManagerService::OnStart` 末尾调用）订阅广播 `usual.event.EMERGENCY_WARNINGS_SWITCH_STATE_CHANGE`（订阅权限 `ohos.permission.ATTEST_KEY`），`OnReceiveEvent` 解析 `SWITCH_STATE = "switchState"`：true→`SetValue`+`RegisterLocationChange`+`RegisterSwitchCallback`；false→`UnregisterLocationChange`+`UnRegisterSwitchCallback`+`OnInit`；开关项 `SWITCH_STATE_KEY = "auto_send_earthquake_alarm_switch"`。
#### Scenario: 预警开关打开
- **WHEN** 广播携带 `switchState = "true"`
- **THEN** 启动无功耗定位监听与开关回调注册

### Requirement: 三 SA 就绪判定与 OOBE 区分
系统 SHALL 由 `LocationSystemAbilityListener : SystemAbilityStatusChangeStub` 跟踪 `DISTRIBUTED_KV_DATA_SERVICE_ABILITY_ID`/`LOCATION_LOCATOR_SA_ID`/`LOCATION_NOPOWER_LOCATING_SA_ID` 三 SA 全就绪后按 `IsSwitchOn(SWITCH_STATE_KEY)` 结果为 `INITIAL_FIRST_VALUE = "invalid"` 区分：OOBE 路径走 `OOBEComplete()`（对 `device_provisioned`/`user_setup_complete`/`is_ota_finished` 未就绪项注册 `OOBESwitchObserver` 监听），否则 `BootComplete(alarmSwitchState)`（三连注册）；未就绪 SA 由 `SystemAbilitySubscriber()` 订阅等待。
#### Scenario: 开机但定位服务未就绪
- **WHEN** 三 SA 中任一未上线
- **THEN** 对该 SA `SubscribeSystemAbility` 挂起等待，全部就绪后再判定启动路径

### Requirement: 位置上报连接预警 ability
系统 SHALL 由 `MyLocationCallBack : ILocatorCallback` 的 `OnLocationReport` 把 `latitude/longitude` 写入 Want 后 `ConnectAbility(PARAMETERS_VALUE = "call_manager_earthquake_alarm")`（预警 ability），`MySwitchCallback : ISwitchCallback` 处理 `RECEIVE_SWITCH_STATE_EVENT`；`EmergencyCallConnectCallback` 记录 `nowCallId/isStartEccService`。
#### Scenario: 收到位置变化
- **WHEN** 无功耗定位回报新经纬度
- **THEN** 以 `call_manager_earthquake_alarm` 为 callerName 连接地震预警 ability 上报位置

### Requirement: 紧急呼叫位置扩展
系统 SHALL 由 `MyLocationEngine::StartEccService(call, info)`（`attributeInfo.isEcc` 为真且开关 `emergency_post_location_switch` 开）以 Want 带 `slotId/phoneNumber` 连接 `EMERGENCY_ABILITY_NAME_ECC = "EccServiceExtAbility"`（`PARAMETERS_VALUE_ECC = "call_status_manager"`）；`StopEccService(callId)` 仅 callId 匹配 `nowCallId` 时 `DisconnectAbility` 防误拆。
#### Scenario: ECC 主叫上报位置
- **WHEN** 紧急呼叫经协议栈上报 DIALING/ACTIVE
- **THEN** 紧急位置扩展按 slotId/号码连接，通话结束后按 callId 匹配断开
