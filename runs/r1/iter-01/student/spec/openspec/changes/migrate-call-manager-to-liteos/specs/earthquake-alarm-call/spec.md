# Spec Delta

## REMOVED Requirements

### Requirement: 预警开关公共事件订阅

**Reason**: AGENTS 功能范围：不支持地震预警，相关代码无需迁移；`LocationSubscriber` 对 `usual.event.EMERGENCY_WARNINGS_SWITCH_STATE_CHANGE` 的公共事件订阅与定位监听启停链整体删除（广播属"暂不调用+todo 桩化"仅适用于保留功能，地震预警属"不支持"）；design D7 被删文件表列出 `services/call_earthquake_alarm/src/call_earthquake_alarm_subscriber.cpp`。
**Migration**: 删除 `services/call_earthquake_alarm/src/call_earthquake_alarm_subscriber.cpp`（含对应头文件）并同步 `callmanager.gni` 的 `call_manager_sources` 与 `call_manager_include_dirs` 的 call_earthquake_alarm 目录条目（design D7 表）；订阅入口 `CallManagerService::OnStart` 的 `LocationSubscriber::Subscriber` 调用删除（见 call-manager-service delta）；PC 门禁套件 `tel_call_earthquake_alarm_test` 移除见 pc-test-harness delta（design D11）。恢复条件：支持地震预警后重建订阅链并恢复 gni 条目与测试套件，或由后续 change 恢复。

### Requirement: 依赖系统服务就绪守候

**Reason**: AGENTS 功能范围：不支持地震预警，相关代码无需迁移；`LocationSystemAbilityListener` 对分布式 KV/定位/免功耗定位三个 SA 的 samgr 守候在 liteOS 无系统服务生态（design D2）；design D7 被删文件表列出 `call_earthquake_alarm_subscriber.cpp`。
**Migration**: 删除 `services/call_earthquake_alarm/src/call_earthquake_alarm_subscriber.cpp`（含对应头文件）并同步 `callmanager.gni` 条目（design D7 表）；SA 守候入口 `CallRecordsManager` 在 `COMMON_EVENT_DATA_SHARE_READY` 后的 `SystemAbilitySubscriber` 调用删除（见 call-state-observer delta）；PC 门禁套件 `tel_call_earthquake_alarm_test` 移除见 pc-test-harness delta（design D11）。恢复条件：支持地震预警后重建 SA 守候链并恢复 gni 条目与测试套件，或由后续 change 恢复。

### Requirement: OOBE 完成守候与预警启动

**Reason**: AGENTS 功能范围：不支持地震预警，相关代码无需迁移；OOBE 三键守候（`device_provisioned`/`user_setup_complete`/`is_ota_finished`）与预警启动分叉随地震预警能力整体删除；design D7 被删文件表列出 `call_earthquake_alarm_subscriber.cpp`。
**Migration**: 删除 `services/call_earthquake_alarm/src/call_earthquake_alarm_subscriber.cpp`（含对应头文件，`OOBESwitchObserver`/`MyLocationEngine::OOBEComplete`/`BootComplete` 随文件消失）并同步 `callmanager.gni` 条目（design D7 表）；PC 门禁套件 `tel_call_earthquake_alarm_test` 移除见 pc-test-harness delta（design D11）。恢复条件：支持地震预警后重建 OOBE 守候与启动链并恢复 gni 条目与测试套件，或由后续 change 恢复。

### Requirement: 定位监听与位置开关联动

**Reason**: AGENTS 功能范围：不支持地震预警，相关代码无需迁移；`MyLocationEngine` 的定位 SA 免功耗监听（10km 距离间隔）与开关边沿联动依赖定位服务，liteOS 无定位 SA（design D2）；design D7 被删文件表列出 `services/call_earthquake_alarm/src/call_earthquake_alarm_locator.cpp`。
**Migration**: 删除 `services/call_earthquake_alarm/src/call_earthquake_alarm_locator.cpp`（含对应头文件，`MyLocationCallBack`/`MySwitchCallback` 回调桩随文件消失）并同步 `callmanager.gni` 条目（design D7 表）；gni 的 `location` 外部依赖随裁剪移除（design D10）；PC 门禁套件 `tel_call_earthquake_alarm_test` 移除见 pc-test-harness delta（design D11）。恢复条件：接入定位服务后重建监听联动并恢复 gni 条目与测试套件，或由后续 change 恢复。

### Requirement: 位置上报应急 Ability 连接

**Reason**: AGENTS 功能范围：不支持地震预警，相关代码无需迁移；`OnLocationReport` 携带经纬度连接应急侧 Ability 的上报链随地震预警能力整体删除（预警通话发起方在应急应用侧，本仓仅提供连接通路）；design D7 被删文件表列出 `call_earthquake_alarm_locator.cpp`。
**Migration**: 删除 `services/call_earthquake_alarm/src/call_earthquake_alarm_locator.cpp`（含对应头文件，`EmergencyCallConnectCallback` 随文件消失）并同步 `callmanager.gni` 条目（design D7 表）；其余保留功能的 Ability 连接出口仍按 `[callUi]` todo 桩化（design D6 拉起通话界面行），与本需求无冲突；PC 门禁套件 `tel_call_earthquake_alarm_test` 移除见 pc-test-harness delta（design D11）。恢复条件：接入应急侧 Ability 后重建位置上报连接并恢复 gni 条目与测试套件，或由后续 change 恢复。

### Requirement: ECC 拨打的位置上报生命周期

**Reason**: AGENTS 功能范围：不支持地震预警，相关代码无需迁移；`StartEccService`/`StopEccService` 的 ECC 拨打位置上报生命周期随地震预警能力整体删除；ECC 紧急呼叫判定/豁免主线本身保留（见 call-control-management delta，不随本需求删除）；design D7 被删文件表列出 `call_earthquake_alarm_locator.cpp`。
**Migration**: 删除 `services/call_earthquake_alarm/src/call_earthquake_alarm_locator.cpp`（含对应头文件）并同步 `callmanager.gni` 条目（design D7 表）；`CallStatusManager` 的 `DialingHandle`/`DisconnectedHandle` 中 `MyLocationEngine::StartEccService`/`StopEccService` 调用分支删除（见 call-status-management delta）；PC 门禁套件 `tel_call_earthquake_alarm_test` 移除见 pc-test-harness delta（design D11）。恢复条件：支持地震预警后重建 ECC 位置上报链并恢复 gni 条目与测试套件，或由后续 change 恢复。

### Requirement: DataShare 设置键查询与观察

**Reason**: AGENTS 功能范围：不支持地震预警，相关代码无需迁移；`DataShareSwitchState` 的设置键查询与键值观察仅服务地震预警 OOBE/开关链，随能力整体删除（AGENTS"暂不调用+todo 桩化"仅适用于保留功能）；design D7 被删文件表列出 `call_earthquake_alarm_subscriber.cpp`。
**Migration**: 删除 `services/call_earthquake_alarm/src/call_earthquake_alarm_subscriber.cpp`（含对应头文件，`DataShareSwitchState` 随文件消失）并同步 `callmanager.gni` 条目（design D7 表）；其余保留功能的 DataShare 调用点仍按 `// todo!!! [database] ref to <文件> <函数>` 桩化（design D6 数据库行），与本需求无冲突；PC 门禁套件 `tel_call_earthquake_alarm_test` 移除见 pc-test-harness delta（design D11）。恢复条件：支持地震预警后重建设置键查询与观察并恢复 gni 条目与测试套件，或由后续 change 恢复。
