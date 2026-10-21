# Spec Delta

## REMOVED Requirements

### Requirement: 防诈检测编排
**Reason**: AGENTS.md 功能范围：防诈 antifraud 不支持；liteOS 不用 dlopen。
**Migration**: `AntiFraudService`/`AntiFraudAdapter`（`libanti_fraud_service_client.so`）与 `ANTIFRAUD_SWITCH` 开关链路不迁移；`ActiveHandle` 中的防诈启动调用点移除。

### Requirement: 检测结果状态联动
**Reason**: AGENTS.md 功能范围：防诈不支持。
**Migration**: `RecordDetectResult`/`TriggerAntiFraud`/`UpdateAntiFraudState`（extraParams "antiFraudState"）与 `MarkType::MARK_TYPE_FRAUD_RISK` 联动不迁移。

### Requirement: 防诈库与脱敏库 dlopen
**Reason**: AGENTS.md 功能范围：防诈不支持；liteOS 不用 dlopen。
**Migration**: `libanti_fraud_service_client.so`/`libdia_sdk.z.so` 的 dlopen/dlsym 绑定与 `services/antifraud/antiinclude/` 外部头不迁移。

### Requirement: HSDR 加密上云
**Reason**: AGENTS.md 功能范围：防诈不支持。
**Migration**: `HsdrHelper`/`AntiFraudCloudService`/`HSDRService` 连接与 `EncryptSync`/`GetAuthSync`/`ConnectCloudAsync` 上云链路不迁移；`CallBroadcastSubscriber` 的 HSDR 广播订阅点随广播占位处置。
