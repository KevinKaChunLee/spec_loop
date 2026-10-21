# Spec Delta

## REMOVED Requirements

### Requirement: 分布式音频设备接入
**Reason**: AGENTS.md 功能范围：分布式（distributed 及 interoperable）通话不支持（`SUPPORT_DSOFTBUS` 为不支持宏）。
**Migration**: `DistributedCallManager`/`DistributedCallProxy`（SA 9855 订阅与 `RegisterDeviceCallback`）、`AddDCallDevice/RemoveDCallDevice` 与 `DEVICE_DISTRIBUTED_PHONE/PAD/AUTOMOTIVE` 音频设备形态不迁移；`SwitchOn/SwitchOffDCallDevice` 入口不存在。

### Requirement: dcall 客户端 dlopen
**Reason**: AGENTS.md 功能范围：分布式通话不支持；liteOS 不用 dlopen。
**Migration**: `libdistributed_call_client.z.so` 的 dlopen/dlsym 包装不迁移。

### Requirement: softbus 会话通路
**Reason**: AGENTS.md 功能范围：分布式通话不支持（softbus/`SUPPORT_DSOFTBUS` 不迁移）。
**Migration**: `TransmissionManager`/`SessionAdapter`/`ServerSession`/`ClientSession`（`PACKET_NAME`/`SESSION_NAME` 会话）与 `SendMsg` 通路不迁移。

### Requirement: 角色化数据同步与远端静音
**Reason**: AGENTS.md 功能范围：分布式通话不支持。
**Migration**: `DistributedCommunicationManager`/`DistributedDeviceObserver`/`DistributedDataController` 系与 `libtelephony_ext_innerkits.z.so` dlopen 链路不迁移；对端 `MUTE`/`MUTE_RINGER` 消息处理与 `CallStateListener` 注册项移除。
