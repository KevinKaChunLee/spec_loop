# Spec Delta

## REMOVED Requirements

### Requirement: HFP通话状态上报
**Reason**: liteOS 不支持 BLUETOOTH 类型通话，`services/bluetooth/` 目录不迁移（AGENTS.md 功能范围）。
**Migration**: 无替代。

### Requirement: 蓝牙设备连接监听
**Reason**: liteOS 不支持 BLUETOOTH 类型通话，蓝牙 HFP 设备连接维护（`services/bluetooth/`）不迁移（AGENTS.md 功能范围）。
**Migration**: 无替代。

### Requirement: 蓝牙通话控制服务
**Reason**: liteOS 不支持 BLUETOOTH 类型通话，蓝牙侧通话控制 IPC 服务（`services/bluetooth/`）不迁移（AGENTS.md 功能范围）。
**Migration**: 无替代。
