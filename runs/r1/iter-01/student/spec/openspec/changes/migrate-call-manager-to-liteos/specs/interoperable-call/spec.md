# Spec Delta

## REMOVED Requirements

### Requirement: 设备发现与角色判定

**Reason**: AGENTS 功能范围：不支持分布式（distributed 及 interoperable）通话，相关代码无需迁移；互信互联角色判定依赖 `DistributedHardware::DeviceManager` 设备发现与 devType 组合，liteOS 无分布式硬件生态；design D7 被删文件表列出 `interoperable_communication_manager.cpp`、`interoperable_device_observer.cpp`。
**Migration**: 删除 `services/interoperable_call/src/interoperable_communication_manager.cpp`、`interoperable_device_observer.cpp`（含对应头文件）并同步 `callmanager.gni` 的 `call_manager_sources` 与 `call_manager_include_dirs` 的 interoperable_call 目录条目（design D7 表）；`call_control_manager.cpp` 的 `AddOneObserver(InteroperableCommunicationManager)` 注册分支删除（见 call-control-management delta）。恢复条件：支持互信互联通话后重建角色判定链并恢复 gni 条目，或由后续 change 恢复。

### Requirement: 协同通话状态联动

**Reason**: AGENTS 功能范围：不支持分布式（distributed 及 interoperable）通话，相关代码无需迁移；`CallStateUpdated` 的来话建会话、断开拆会话与静音转发联动仅在协同对端存在时生效，liteOS 无对端；design D7 被删文件表列出 `interoperable_communication_manager.cpp`。
**Migration**: 删除 `services/interoperable_call/src/interoperable_communication_manager.cpp`（含对应头文件）并同步 `callmanager.gni` 条目（design D7 表）；`CallManagerService::SetMuted`/`MuteRinger` 的 `InteroperableCommunicationManager` 两处联动删除（见 call-manager-service delta）。恢复条件：支持互信互联通话后重建状态联动并恢复 gni 条目，或由后续 change 恢复。

### Requirement: 客户端会话管理

**Reason**: AGENTS 功能范围：不支持分布式（distributed 及 interoperable）通话，相关代码无需迁移；`InteroperableClientManager` 的会话创建与 requisite 数据收发基于软总线会话（`SOFTNET_SESSION_NAME`、`QOS_BW_BT`），liteOS 无 dsoftbus；design D7 被删文件表列出 `interoperable_client_manager.cpp`。
**Migration**: 删除 `services/interoperable_call/src/interoperable_client_manager.cpp`（含对应头文件）并同步 `callmanager.gni` 条目（design D7 表）；`PhoneOrWatchDial::WATCH_DIAL` 相关的蓝牙豁免判定族已随蓝牙/eSIM 删除（见 call-object-management delta「NOT_SUPPORT_MULTICALL 一号双终端对象判定」条）。恢复条件：接入 dsoftbus 后重建客户端会话管理并恢复 gni 条目，或由后续 change 恢复。

### Requirement: 服务端会话管理

**Reason**: AGENTS 功能范围：不支持分布式（distributed 及 interoperable）通话，相关代码无需迁移；`InteroperableServerManager` 的服务端会话监听与卡槽查询应答基于软总线会话，liteOS 无 dsoftbus；design D7 被删文件表列出 `interoperable_server_manager.cpp`。
**Migration**: 删除 `services/interoperable_call/src/interoperable_server_manager.cpp`（含对应头文件）并同步 `callmanager.gni` 条目（design D7 表）；`CallManagerService` 的 `GetBtCallSlotId`/`BtCallWaitSlotId` 拨号卡槽补写分支删除（见 call-manager-service delta）。恢复条件：接入 dsoftbus 后重建服务端会话管理并恢复 gni 条目，或由后续 change 恢复。

### Requirement: 卡槽数据控制与一次性查询语义

**Reason**: AGENTS 功能范围：不支持分布式（distributed 及 interoperable）通话，相关代码无需迁移；`InteroperableDataController` 的 cJSON requisite 收发、`GetBtCallSlotId` 查询-等待-删除语义与 mute 消息组包全部依赖软总线会话，liteOS 无对端；design D7 被删文件表列出 `interoperable_data_controller.cpp`。
**Migration**: 删除 `services/interoperable_call/src/interoperable_data_controller.cpp`（含对应头文件）并同步 `callmanager.gni` 条目（design D7 表）；`call_manager_service.cpp` 的 `GetBtCallSlotId`/`SetMuted`/`MuteRinger` 互通分支与 extras `btSlotIdUnknown`→`BtCallWaitSlotId` 补写链删除（见 call-manager-service delta）。恢复条件：支持互信互联通话后重建数据控制器并恢复 gni 条目，或由后续 change 恢复。

### Requirement: watch 平台数据库静音联动

**Reason**: AGENTS 功能范围：不支持分布式（distributed 及 interoperable）通话，相关代码无需迁移；`SUPPORT_MUTE_BY_DATABASE` 属不支持宏（AGENTS 特性宏支持范围），watch 特设静音联动整链删除；design D7 被删文件表列出 gni watch 块编入的 `interoperable_settings_handler.cpp`。
**Migration**: 删除 `interoperable_settings_handler.cpp`（含对应头文件）并同步 `callmanager.gni` 条目；gni `target_platform=="watch"` 特设块整体删除（design D7 宏清理）；`SUPPORT_MUTE_BY_DATABASE` 在 `call_manager_service.cpp`/`call_records_manager.cpp` 的两处 `#ifdef` 守卫块删除、全库走默认静音路径（见 call-manager-service/call-state-observer delta；design D7 不支持宏表）。恢复条件：支持互信互联通话并启用数据库静音联动后重建本文件并恢复 gni watch 块与守卫，或由后续 change 恢复。
