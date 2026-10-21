# Spec Delta

## REMOVED Requirements

### Requirement: 地震预警开关与定位编排
**Reason**: AGENTS.md 功能范围：地震预警不支持。
**Migration**: `MyLocationEngine`/`LocationSubscriber`/`DataShareSwitchState` 与 `usual.event.EMERGENCY_WARNINGS_SWITCH_STATE_CHANGE` 广播订阅、`SWITCH_STATE_KEY` 开关查询链路不迁移；`CallManagerService::OnStart`/`Init` 末尾的 `LocationSubscriber::Subscriber()` 调用点移除。

### Requirement: 三 SA 就绪判定与 OOBE 区分
**Reason**: AGENTS.md 功能范围：地震预警不支持。
**Migration**: `LocationSystemAbilityListener`/`OOBESwitchObserver`/`SystemAbilitySubscriber` 与三 SA（`DISTRIBUTED_KV_DATA_SERVICE_ABILITY_ID`/`LOCATION_LOCATOR_SA_ID`/`LOCATION_NOPOWER_LOCATING_SA_ID`）就绪判定链路不迁移。

### Requirement: 位置上报连接预警 ability
**Reason**: AGENTS.md 功能范围：地震预警不支持。
**Migration**: `MyLocationCallBack`/`MySwitchCallback`/`EmergencyCallConnectCallback` 与 `call_manager_earthquake_alarm` 连接链路不迁移。

### Requirement: 紧急呼叫位置扩展
**Reason**: AGENTS.md 功能范围：地震预警不支持。
**Migration**: `StartEccService`/`StopEccService`（`EccServiceExtAbility` 连接与 `emergency_post_location_switch` 查询）不迁移；ECC 拨号/通话不再触发紧急位置扩展。
