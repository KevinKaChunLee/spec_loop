# Spec Delta

## REMOVED Requirements

### Requirement: 卫星开关与拨号准入
**Reason**: AGENTS.md 功能范围：卫星通话不支持。
**Migration**: `SatelliteCallControl::IsSatelliteSwitchEnable`/`IsAllowedSatelliteDialCall` 与 `QUERY_SATELLITE_MODE_KEY`/`QUERY_SATELLITE_CONNECTED_KEY` 查询链路不迁移；`CallControlManager::DialCall` 不再执行卫星开关判定，`TYPE_SATELLITE` 改写不可达。

### Requirement: modem 使用标记
**Reason**: AGENTS.md 功能范围：卫星通话不支持。
**Migration**: `SetUsedModem`/`HandleSatelliteCallStateUpdate` 的 modem 标记与 `USEDMODEM` 音频参数下发链路不迁移。

### Requirement: 通话时长限制与倒计时挂断
**Reason**: AGENTS.md 功能范围：卫星通话不支持。
**Migration**: `SetSatelliteCallDurationProcessing`/`SetSatelliteCallCountDownProcessing` 与 `GetSatelliteCallList` 强制挂断链路不迁移；`SATELLITE_CALL_DURATION_LIMIT`/`SATELLITE_CALL_DISCONNECT` 对话框触发移除。
