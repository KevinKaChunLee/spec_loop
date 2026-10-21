# Spec Delta

## REMOVED Requirements

### Requirement: HFP AG 状态上报
**Reason**: AGENTS.md 功能范围：BLUETOOTH 类型通话不支持。
**Migration**: `BluetoothCallManager`/`BluetoothConnection` 的 HFP AG 状态上报链路不迁移；`CallAbilityReportProxy` 上报后不再联动蓝牙侧。

### Requirement: 对外接口与权限
**Reason**: AGENTS.md 功能范围与架构约束：BLUETOOTH 类型通话不支持；liteOS 外部接口不做权限校验。
**Migration**: `BluetoothCallStub`/`BluetoothCallService`/`BluetoothCallPolicy` 与 `BluetoothCallInterfaceCode` IPC 面不迁移；蓝牙侧入口不存在，接听/挂断等经 `CallManagerClient` 直调承载。

### Requirement: 通话状态聚合
**Reason**: AGENTS.md 功能范围：BLUETOOTH 类型通话不支持，HFP 状态聚合无消费方。
**Migration**: `getCarrierCallInfoNum` 聚合与 HFP 上报链路不迁移。

### Requirement: HFP AG 连接与音频设备联动
**Reason**: AGENTS.md 功能范围：蓝牙耳机设备连接不支持。
**Migration**: `BluetoothConnection` 的 SA 订阅、`AddBtDevice`、`AudioDeviceManager::AddAudioDeviceList(macAddress, DEVICE_BLUETOOTH_SCO, deviceName)` 与掉线清理链路不迁移；音频设备列表无蓝牙设备形态。

### Requirement: 可穿戴蓝牙耳机地址
**Reason**: AGENTS.md 功能范围：蓝牙耳机设备连接不支持（分布式 sink 切换链路整体移除）。
**Migration**: `GetWearBtHeadsetAddress()` 与 `DistributedSinkSwitchController::TrySwitchToBtHeadset` 调用链不迁移。
