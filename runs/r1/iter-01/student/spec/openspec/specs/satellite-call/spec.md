# Satellite Call Specification

## Purpose
描述 HMOS `telephony_call_manager` 中卫星通话控制面（`services/satellite_call/src/satellite_call_control.cpp`，头文件 `services/satellite_call/include/satellite_call_control.h`）的移植前现状：`SatelliteCallControl` 提供卫星拨号准入（开关/连通性查询、温度限拨）、卫星通话状态联动（modem 参数映射、高温断链弹窗）、通话限时与倒计时任务。控制面由 `services/call/src/call_control_manager.cpp`（拨号前经 `IsSatelliteSwitchEnable`/`IsAllowedSatelliteDialCall` 判定并置 `CallType::TYPE_SATELLITE`）、`services/call/src/call_status_manager.cpp`（`HandleSatelliteCallStateUpdate`）与 `services/call/src/call_broadcast_subscriber.cpp`（`HighTempLevelChangedBroadcast` 转 `SetSatcommTempLevel`）接入。本模块无特性宏门控。

## Requirements

### Requirement: 卫星拨号准入
系统 SHALL 由 `IsSatelliteSwitchEnable` 经 `SettingsDataShareHelper::Query`（`QUERY_SATELLITE_MODE_KEY`）判断卫星模式开关，值为 1（`SATELLITE_MODE_ON`）时返回成功。`IsAllowedSatelliteDialCall` SHALL 经 `QUERY_SATELLITE_CONNECTED_KEY` 判断卫星业务连通（值为 1 即 `SATELLITE_CONNECTED`），连通时读取系统参数 `persist.thermal.log.satcomm` 更新温度等级，等级达到 `SatCommTempLevel::TEMP_LEVEL_MIDDLE` 及以上时经 `CallDialog::DialogConnectExtension("CANNOT_DIAL_SATELLITE_CALL")` 弹窗并返回 `TELEPHONY_ERROR`，否则 `SetUsedModem` 后返回成功；不连通时 `PublishSatelliteConnectEvent` 发布 action 为 `event.custom.satellite.ACTION_SATELLITE_CONNECT`（订阅权限 `Permission::SET_TELEPHONY_STATE`）的公共事件，并返回 `TELEPHONY_ERROR`。

#### Scenario: 卫星模式未开时拨号
- **WHEN** datashare 中卫星模式值不为 1 时发起卫星拨号前置判定
- **THEN** `IsSatelliteSwitchEnable` 返回失败，不进入连通性判定

#### Scenario: 卫星连通但温度中档
- **WHEN** 卫星连通值为 1 且 `persist.thermal.log.satcomm` 对应 `TEMP_LEVEL_MIDDLE`
- **THEN** 弹出 `CANNOT_DIAL_SATELLITE_CALL` 对话框，`IsAllowedSatelliteDialCall` 返回 `TELEPHONY_ERROR`

#### Scenario: 卫星未连通
- **WHEN** 卫星连通值不为 1 时执行 `IsAllowedSatelliteDialCall`
- **THEN** 发布 `event.custom.satellite.ACTION_SATELLITE_CONNECT` 公共事件并返回 `TELEPHONY_ERROR`

### Requirement: 温度等级管理
系统 SHALL 由 `SetSatcommTempLevel` 记录当前 `SatCommTempLevel_`：等级相同不动作；升到 `TEMP_LEVEL_HIGH` 且 `CallObjectManager::HasSatelliteCallExist` 为真时经 `CallDialog::DialogConnectExtension("SATELLITE_CALL_DISCONNECT")` 弹窗并 `SetShowDialog(true)`。`SetShowDialog(true)` SHALL 同时启动倒计时任务。

#### Scenario: 温度等级不变
- **WHEN** `SetSatcommTempLevel` 收到与当前等级相同的值
- **THEN** 状态不变、不弹窗、不启动倒计时

#### Scenario: 高温且有在网卫星通话
- **WHEN** 温度升到 `TEMP_LEVEL_HIGH` 且存在卫星通话
- **THEN** 弹出 `SATELLITE_CALL_DISCONNECT` 对话框并进入弹窗倒计时状态

### Requirement: 卫星通话状态联动
系统 SHALL 由 `HandleSatelliteCallStateUpdate` 在 `TYPE_SATELLITE` 通话状态变化时：来话/等待时 `SetUsedModem`；进入 `CALL_STATUS_ACTIVE` 且高温等级下存在卫星通话时弹 `SATELLITE_CALL_DISCONNECT` 并 `SetShowDialog(true)`；当系统参数 `const.build.product` 非空时 SHALL 直接返回（不启动限时任务），为空时 ACTIVE 且未在弹窗状态启动 `SetSatelliteCallDurationProcessing`，通话断开时 `RemoveCallDurationEventHandlerTask`，弹窗状态下的断开同时 `RemoveCallCountDownEventHandlerTask` 并清除弹窗标记。

#### Scenario: 活跃通话进入高温
- **WHEN** 卫星通话转为 `CALL_STATUS_ACTIVE` 且温度为 `TEMP_LEVEL_HIGH` 且仍有卫星通话存在
- **THEN** 弹出断链对话框并置弹窗标记

#### Scenario: 产线型号跳过限时
- **WHEN** `const.build.product` 非空且卫星通话转为 `CALL_STATUS_ACTIVE`
- **THEN** 不启动通话限时任务

### Requirement: 通话限时与倒计时任务
系统 SHALL 由 `SetSatelliteCallDurationProcessing` 在 `AppExecFwk::EventRunner::Create("start_satellite_call_duration_dialog")` 的 `CallDurationLimitHandler_` 上以 `DELAYED_TIME`(270000ms) 延时投递任务，触发时若未弹窗则经 `CallDialog::DialogConnectExtension("SATELLITE_CALL_DURATION_LIMIT")` 弹窗并 `SetShowDialog(true)`；任务名固定，重复启动前先 `RemoveTask`。`SetSatelliteCallCountDownProcessing` SHALL 在 `CallCountDownHandler_` 上以 `COUNT_DOWN_TIME`(30000ms) 投递倒计时任务：经 `CallObjectManager::GetSatelliteCallList` 遍历卫星通话，INCOMING/WAITING 状态执行 `CallControlManager::RejectCall(satelliteCallId, true, u"satellitecalldurationlimit")`，ACTIVE 状态执行 `CallControlManager::HangUpCall(satelliteCallId)`。

#### Scenario: 通话达到限时阈值
- **WHEN** 卫星通话 ACTIVE 且未弹窗持续 270 秒
- **THEN** 弹出 `SATELLITE_CALL_DURATION_LIMIT` 对话框

#### Scenario: 倒计时到期的来话
- **WHEN** 弹窗倒计时 30 秒结束时存在 `CALL_STATUS_INCOMING` 的卫星通话
- **THEN** 该通话被以短拒方式拒接（携带 `satellitecalldurationlimit` 消息）

#### Scenario: 倒计时到期的活跃通话
- **WHEN** 弹窗倒计时 30 秒结束时存在 `CALL_STATUS_ACTIVE` 的卫星通话
- **THEN** 该通话被挂断

### Requirement: modem 参数映射
系统 SHALL 由 `SetUsedModem` 读取系统参数 `const.telephony.satellite.support_type`（默认 "0"），当其位掩码含 0b00000100 或 0b00010000 时，经 `AudioStandard::AudioSystemManager::GetInstance()->SetExtraParameters("mmi", {{"USEDMODEM", "satemodem"}})` 设置音频侧 modem 选择参数。

#### Scenario: 支持类型命中位掩码
- **WHEN** `const.telephony.satellite.support_type` 值为 4（0b100）时来电触发 `SetUsedModem`
- **THEN** 音频系统收到 `USEDMODEM=satemodem` 的 mmi 扩展参数

#### Scenario: 支持类型未命中
- **WHEN** `const.telephony.satellite.support_type` 值为 1 时执行 `SetUsedModem`
- **THEN** 不调用 `SetExtraParameters`
