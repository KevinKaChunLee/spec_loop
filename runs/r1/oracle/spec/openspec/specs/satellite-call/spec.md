# 卫星通话（satellite-call）Specification

## Purpose
描述 `telephony_call_manager/services/satellite_call/` 的卫星通话控制：`SatelliteCallControl`（卫星开关与允许拨号判定、温控等级、通话时长限制与倒计时强制挂断）。落点：`services/satellite_call/src/satellite_call_control.cpp` 与 `services/satellite_call/include/satellite_call_control.h`。该模块组无独有编译开关；设置项查询依赖 `SettingsDataShareHelper`（见 call-manager-utils 能力）。

## Requirements

### Requirement: 卫星开关与拨号准入
系统 SHALL 由 `SatelliteCallControl::IsSatelliteSwitchEnable()`（`SettingsDataShareHelper::Query(QUERY_SATELLITE_MODE_KEY) == SATELLITE_MODE_ON`）与 `IsAllowedSatelliteDialCall()`（`Query(QUERY_SATELLITE_CONNECTED_KEY) == SATELLITE_CONNECTED` 时读系统参数 `persist.thermal.log.satcomm` 刷新温控等级，`TEMP_LEVEL_MIDDLE` 及以上经 `CallDialog::DialogConnectExtension("CANNOT_DIAL_SATELLITE_CALL")` 弹窗并拒绝；未连卫星时 `PublishSatelliteConnectEvent()` 发布 `event.custom.satellite.ACTION_SATELLITE_CONNECT`）共同决定卫星拨号准入。
#### Scenario: 温控中档禁止卫星拨号
- **WHEN** 卫星已连接且温控等级达到 `TEMP_LEVEL_MIDDLE`
- **THEN** 拨号被拒绝并弹出 `CANNOT_DIAL_SATELLITE_CALL` 对话框

### Requirement: modem 使用标记
系统 SHALL 由 `SetUsedModem()` 读系统参数 `const.telephony.satellite.support_type`，含 bit `0b00000100`/`0b00010000` 时经 `AudioStandard::AudioSystemManager::SetExtraParameters("mmi", {("USEDMODEM","satemodem")})` 下发卫星 modem 标记；`HandleSatelliteCallStateUpdate` 在 INCOMING/WAITING 时执行 `SetUsedModem`。
#### Scenario: 卫星来话设置 modem 标记
- **WHEN** 卫星通话进入 INCOMING/WAITING
- **THEN** 按支持类型位图决定是否下发 `USEDMODEM` 音频参数

### Requirement: 通话时长限制与倒计时挂断
系统 SHALL 由 `HandleSatelliteCallStateUpdate`：ACTIVE 且 `SetSatelliteCallDurationProcessing()`（`DELAYED_TIME = 270000` 毫秒后弹 `SATELLITE_CALL_DURATION_LIMIT`）；`SetShowDialog(true)` 后 `SetSatelliteCallCountDownProcessing()`（`COUNT_DOWN_TIME = 30000` 毫秒后遍历 `CallObjectManager::GetSatelliteCallList`：INCOMING/WAITING 走 `CallControlManager::RejectCall(callId, true, u"satellitecalldurationlimit")`，ACTIVE 走 `HangUpCall`）；`const.build.product` 非空的产品不做时长限制；`TEMP_LEVEL_HIGH` 升温且有卫星通话时弹 `SATELLITE_CALL_DISCONNECT`。
#### Scenario: 卫星通话 270 秒到时
- **WHEN** 非 `const.build.product` 空产品的卫星通话 ACTIVE 达到时长限制
- **THEN** 弹出时长限制对话框并启动 30 秒倒计时，倒计时结束强制拒绝/挂断全部卫星通话
