# Spec Delta

## REMOVED Requirements

### Requirement: 设备发现与角色判定
**Reason**: AGENTS.md 功能范围：分布式（distributed 及 interoperable）通话不支持。
**Migration**: `InteroperableDeviceObserver`/`InteroperableClientManager`/`InteroperableServerManager` 与 devicemanager 订阅链路不迁移。

### Requirement: 蓝牙通话 slotId 同步
**Reason**: AGENTS.md 功能范围：互通通话与 BLUETOOTH 类型通话均不支持。
**Migration**: `GetBtCallSlotId`/`WaitForBtSlotId`/`SaveBtSlotId` 与 `PhoneOrWatchDial::WATCH_DIAL` 拨号链路不迁移；`BtCallWaitSlotId` 流程不可达。

### Requirement: 互通静音联动
**Reason**: AGENTS.md 功能范围：互通通话不支持；`SUPPORT_MUTE_BY_DATABASE` 的 watch 专属源随之移除。
**Migration**: `InteroperableSettingsHandler`（`synergy_incoming_mute`/`call_mute_ringer` key 与 `SYNERGY_INCOMING_MUTE_URI`/`CALL_MUTE_RINGER_URI`）不迁移；`MuteRinger` 不再联动 settingsdata 静音开关，`InteroperableRecvObserver` 移除。
