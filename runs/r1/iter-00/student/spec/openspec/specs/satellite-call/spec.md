# 卫星通话控制（Satellite Call Control）Specification

## Purpose
描述 HMOS call_manager 当前的卫星通话控制能力：独立控制入口 `SatelliteCallControl`（`DECLARE_DELAYED_SINGLETON`）对卫星拨号执行连接/开关/温控门禁，对卫星通话状态执行时长限制与倒计时挂断处理，并通过系统参数与音频侧协同占用 modem。源码落点：`telephony_call_manager/services/satellite_call/{include,src}`：`satellite_call_control.cpp`。无专属编译开关：该文件无条件列入 `callmanager.gni` 的 `call_manager_sources`。

## Requirements

### Requirement: 卫星拨号门禁
系统 SHALL 由 `IsAllowedSatelliteDialCall` 经 `SettingsDataShareHelper` 查询 `QUERY_SATELLITE_CONNECTED_KEY`：卫星已连接时读取系统参数 `persist.thermal.log.satcomm` 更新温控档位，温控达到 `TEMP_LEVEL_MIDDLE` 及以上时弹出 `CANNOT_DIAL_SATELLITE_CALL` 对话框并返回 `TELEPHONY_ERROR`，否则 `SetUsedModem` 后返回 `TELEPHONY_SUCCESS`；卫星未连接时 MUST 发布卫星连接引导事件并返回 `TELEPHONY_ERROR`。

#### Scenario: 卫星未连接拨号
- **WHEN** 数据库查询 satellite_connected 结果非 1 时调用 `IsAllowedSatelliteDialCall`
- **THEN** `PublishSatelliteConnectEvent` 发布 action 为 `event.custom.satellite.ACTION_SATELLITE_CONNECT` 的公共事件（订阅需 SET_TELEPHONY_STATE 权限），返回 `TELEPHONY_ERROR`

#### Scenario: 温控门禁拦截
- **WHEN** 卫星已连接且 `GetSatcommTempLevel()` 返回 `TEMP_LEVEL_MIDDLE`
- **THEN** 经 `CallDialog` 弹出 `CANNOT_DIAL_SATELLITE_CALL` 对话框，返回 `TELEPHONY_ERROR`

#### Scenario: 门禁放行
- **WHEN** 卫星已连接且温控档位低于 `TEMP_LEVEL_MIDDLE`
- **THEN** `SetUsedModem` 后返回 `TELEPHONY_SUCCESS`

### Requirement: 卫星模式开关查询
系统 SHALL 由 `IsSatelliteSwitchEnable` 经 `SettingsDataShareHelper` 查询 `QUERY_SATELLITE_MODE_KEY`，值为 1（SATELLITE_MODE_ON）返回 `TELEPHONY_SUCCESS`，查询失败或非 1 MUST 返回 `TELEPHONY_ERROR`。

#### Scenario: 模式开启
- **WHEN** 查询 satellite mode 结果为 "1"
- **THEN** 返回 `TELEPHONY_SUCCESS`

#### Scenario: 模式关闭
- **WHEN** 查询失败或结果为 "0"
- **THEN** 返回 `TELEPHONY_ERROR`

### Requirement: 温控档位与高热断话
系统 SHALL 由 `SetSatcommTempLevel` 更新 `SatCommTempLevel_`；档位升到 `TEMP_LEVEL_HIGH` 且 `CallObjectManager::HasSatelliteCallExist()` 为真时，经 `CallDialog` 弹出 `SATELLITE_CALL_DISCONNECT` 对话框并 `SetShowDialog(true)`；档位未变化时 MUST 不做任何处理。

#### Scenario: 高热告警断话
- **WHEN** `SetSatcommTempLevel(TEMP_LEVEL_HIGH)` 且存在卫星通话
- **THEN** 弹出 `SATELLITE_CALL_DISCONNECT` 对话框，`IsShowDialog()` 返回 true

#### Scenario: 档位未变化
- **WHEN** `SetSatcommTempLevel` 传入与当前相同档位
- **THEN** 不做任何处理直接返回

### Requirement: 通话状态处理与时长限制
系统 SHALL 由 `HandleSatelliteCallStateUpdate` 处理状态迁移：进入/等待来电时 `SetUsedModem` 协同音频侧占用 modem（依据 `const.telephony.satellite.support_type` 参数位设置 USEDMODEM）；进入 ACTIVE 且未弹窗时启动 270000ms 延时任务弹出 `SATELLITE_CALL_DURATION_LIMIT` 对话框；弹窗时启动 30000ms 倒计时任务，到期对 INCOMING/WAITING 卫星通话 `RejectCall(callId, true, "satellitecalldurationlimit")`、对 ACTIVE 卫星通话 `HangUpCall`；通话断开或弹窗取消时 MUST 移除对应任务。

#### Scenario: 激活启动时长限制
- **WHEN** `const.build.product` 参数为空、卫星通话进入 `CALL_STATUS_ACTIVE` 且 `IsShowDialog()` 为 false
- **THEN** 以 `DELAYED_TIME`(270000ms) 延时弹出 `SATELLITE_CALL_DURATION_LIMIT` 对话框（`SetSatelliteCallDurationProcessing`）

#### Scenario: 倒计时到期强挂
- **WHEN** `SetShowDialog(true)` 启动的 30000ms 倒计时到期且存在 ACTIVE 卫星通话
- **THEN** 经 `CallControlManager::HangUpCall` 挂断该卫星通话（`SetSatelliteCallCountDownProcessing` 任务）

#### Scenario: 通话断开清任务
- **WHEN** 卫星通话迁移到 `CALL_STATUS_DISCONNECTED`/`CALL_STATUS_DISCONNECTING`
- **THEN** `RemoveCallDurationEventHandlerTask` 移除时长限制任务；若此前已弹窗则同时移除倒计时任务并复位弹窗标志
