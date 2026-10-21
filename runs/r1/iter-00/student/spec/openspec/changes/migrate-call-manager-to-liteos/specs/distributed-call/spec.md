# Spec Delta

## REMOVED Requirements

### Requirement: 分布式设备在线管理
**Reason**: liteOS 不支持分布式通话（dsoftbus 依赖不迁移），`services/distributed_call/` 目录不迁移（AGENTS.md 功能范围）。
**Migration**: 无替代。

### Requirement: 分布式设备开关切换
**Reason**: liteOS 不支持分布式通话，分布式设备开关切换（`services/distributed_call/`）不迁移（AGENTS.md 功能范围）。
**Migration**: 无替代。

### Requirement: source/sink角色协商与数据同步
**Reason**: liteOS 不支持分布式通话（dsoftbus 依赖不迁移），source/sink 角色协商与数据同步（`services/distributed_call/`）不迁移（AGENTS.md 功能范围）。
**Migration**: 无替代。

### Requirement: softbus会话传输
**Reason**: liteOS 不支持分布式通话（dsoftbus 依赖不迁移），softbus 会话传输（`services/distributed_call/`）不迁移（AGENTS.md 功能范围）。
**Migration**: 无替代。
