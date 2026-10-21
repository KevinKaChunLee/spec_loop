# Spec Delta

## REMOVED Requirements

### Requirement: 检测启动条件判定

**Reason**: AGENTS 功能范围：不支持防诈 antifraud，相关代码无需迁移；`CallStatusManager::ActiveHandle` 的防诈启动判定与 `AntiFraudService::StartAntiFraudService` 异步启动链整体删除；design D7 被删文件表列出 `services/antifraud/src/antifraud_service.cpp`。
**Migration**: 删除 `services/antifraud/src/antifraud_service.cpp`（含 `antiinclude/` 外部头副本）并同步 `callmanager.gni` 的 `call_manager_sources` 与 `call_manager_include_dirs` 的 antifraud 目录条目（design D7 表）；`call_status_manager.cpp` 的 `SetupAntiFraudService`/`StartAntiFraudService` 启动入口与 `ActiveHandle` 启动判定分支删除（见 call-status-management delta「防诈检测状态管理」REMOVED 条）。恢复条件：目标平台引入防诈能力（外部防诈查询/云服务接口就绪）后按 baseline 需求整块恢复，或由后续 change 恢复。

### Requirement: 防诈算法库 dlopen 适配器

**Reason**: AGENTS 功能范围：不支持防诈 antifraud，相关代码无需迁移；`AntiFraudAdapter` 的 `dlopen("libanti_fraud_service_client.so")` 算法库加载通路随防诈能力整体删除（不做桩化保留）；design D7 被删文件表列出 `antifraud_adapter.cpp`。
**Migration**: 删除 `services/antifraud/src/antifraud_adapter.cpp`（含对应头文件）并同步 `callmanager.gni` 条目（design D7 表）；`CheckAntiFraud`/`DetectAntiFraud`/`StopAntiFraud` 的 dlsym 调用点随文件消失，不设 todo 占位（防诈属"不支持"而非"暂不调用"，AGENTS 外部依赖处理）。恢复条件：目标平台引入防诈算法库后按 baseline 需求整块恢复，或由后续 change 恢复。

### Requirement: 检测停止与迟到结果丢弃

**Reason**: AGENTS 功能范围：不支持防诈 antifraud，相关代码无需迁移；`StopAntiFraudDetect` 停止链与 `stoppedSlotId_`/`stoppedIndex_` 迟到结果丢弃机制随防诈能力整体删除（`HandleCeliaCall` 接管分支随新通话一并删除）；design D7 被删文件表列出 `antifraud_service.cpp`。
**Migration**: 删除 `services/antifraud/src/antifraud_service.cpp`（含对应头文件）并同步 `callmanager.gni` 条目（design D7 表）；`call_status_manager.cpp` 的 `StopAntiFraudDetect` 停止入口（HOLDING/DISCONNECTING/DISCONNECTED 善后链）删除（见 call-status-management delta）。恢复条件：目标平台引入防诈能力后按 baseline 需求整块恢复，或由后续 change 恢复。

### Requirement: 检测结果记录与状态回传

**Reason**: AGENTS 功能范围：不支持防诈 antifraud，相关代码无需迁移；`RecordDetectResult` 结果记录与 `TriggerAntiFraud`→`UpdateAntiFraudState`（extraParams `antiFraudState`）状态回传链整体删除；design D7 被删文件表列出 `antifraud_service.cpp`。
**Migration**: 删除 `services/antifraud/src/antifraud_service.cpp`（含对应头文件）并同步 `callmanager.gni` 条目（design D7 表）；`call_status_manager.cpp` 的 `TriggerAntiFraud`/`UpdateAntiFraudState` 实现删除（见 call-status-management delta）；`CallBase` 属性导出的 `antiFraudState` 解析及 `MARK_TYPE_FRAUD_RISK` 改写分支移除（见 call-object-management delta）。恢复条件：目标平台引入防诈能力后按 baseline 需求整块恢复，或由后续 change 恢复。

### Requirement: 防诈开关 DataShare 查询

**Reason**: AGENTS 功能范围：不支持防诈 antifraud，相关代码无需迁移；`IsSwitchOn` 的 DataShare 设置键查询随防诈能力整体删除（AGENTS"暂不调用+todo 桩化"仅适用于保留功能，防诈属"不支持"）；design D7 被删文件表列出 `antifraud_service.cpp`。
**Migration**: 删除 `services/antifraud/src/antifraud_service.cpp`（含对应头文件）并同步 `callmanager.gni` 条目（design D7 表）；其余保留功能的 DataShare 调用点仍按 `// todo!!! [database] ref to <文件> <函数>` 桩化（design D6 数据库行），与本需求无冲突。恢复条件：目标平台引入防诈能力后按 baseline 需求整块恢复，或由后续 change 恢复。

### Requirement: 检测文本脱敏（anonymize 适配器）

**Reason**: AGENTS 功能范围：不支持防诈 antifraud，相关代码无需迁移；`AnonymizeAdapter` 的 `dlopen("libdia_sdk.z.so")` 与 DIA 规则脱敏链仅服务防诈云上报，随防诈能力整体删除；design D7 被删文件表列出 `anonymize_adapter.cpp`。
**Migration**: 删除 `services/antifraud/src/anonymize_adapter.cpp`（含对应头文件与 `antiinclude/dia_interface_c.h` 等外部头副本）并同步 `callmanager.gni` 条目（design D7 表）。恢复条件：目标平台引入防诈能力与 DIA SDK 后按 baseline 需求整块恢复，或由后续 change 恢复。

### Requirement: 云上报条件与负载生成

**Reason**: AGENTS 功能范围：不支持防诈 antifraud，相关代码无需迁移；`spamshield_call_live_report` 改进计划开关判定与 cJSON 上报负载组装随防诈能力整体删除；design D7 被删文件表列出 `antifraud_cloud_service.cpp`。
**Migration**: 删除 `services/antifraud/src/antifraud_cloud_service.cpp`（含对应头文件）并同步 `callmanager.gni` 条目（design D7 表）；系统参数读取（`const.product.software.version`）与 cJSON 的桩约定（`stub/parameter_stub`、`stub/cjson_stub`）不变，仅本负载生成调用点消失。恢复条件：目标平台引入防诈云上报后按 baseline 需求整块恢复，或由后续 change 恢复。

### Requirement: HSDR 服务的连接管理

**Reason**: AGENTS 功能范围：不支持防诈 antifraud，相关代码无需迁移；`HsdrHelper` 到 `com.hmos.hsdr` 的 ServiceExtension 连接仅服务防诈加密/签名与云上传，随防诈能力整体删除；design D7 被删文件表列出 `antifraud_hsdr_helper.cpp`。
**Migration**: 删除 `services/antifraud/src/antifraud_hsdr_helper.cpp`（含对应头文件）并同步 `callmanager.gni` 条目（design D7 表）；HSDR 广播订阅分发保留于 call-status-management 能力（订阅侧见 call-control-management delta；其数据亦供号码识别链使用），仅防诈侧消费分支随本能力删除——与 call-status-management/call-control-management delta 同口径，避免矛盾。恢复条件：目标平台引入防诈能力后按 baseline 需求整块恢复，或由后续 change 恢复。

### Requirement: UCS 同步请求（加密与签名）

**Reason**: AGENTS 功能范围：不支持防诈 antifraud，相关代码无需迁移；`HsdrProxy::RequestHsdrServiceSync` 的 UCS 加密/签名同步等待链（`mutex_`/`cv_` 同步原语随全仓去锁一并消失，design D6/D8）随防诈能力整体删除；design D7 被删文件表列出 `antifraud_cloud_service.cpp`、`antifraud_hsdr_helper.cpp`。
**Migration**: 删除 `services/antifraud/src/antifraud_cloud_service.cpp`、`antifraud_hsdr_helper.cpp`（含对应头文件）并同步 `callmanager.gni` 条目（design D7 表）；`EncryptSync`/`GetAuthSync` 的 UCS 请求构造与 `EXT-CLOUDSOA-HMAC-SHA256` auth 头拼装调用点随文件消失。恢复条件：目标平台引入防诈能力与 HSDR UCS 通路后按 baseline 需求整块恢复，或由后续 change 恢复。

### Requirement: 云侧异步上传

**Reason**: AGENTS 功能范围：不支持防诈 antifraud，相关代码无需迁移；`ConnectCloudAsync` 经 HSDR 通道向 `com.cloud.afs.ROOT` 的 multipart 异步上传（含 SHA256/Base64/系统参数桩化出口）随防诈能力整体删除；design D7 被删文件表列出 `antifraud_cloud_service.cpp`。
**Migration**: 删除 `services/antifraud/src/antifraud_cloud_service.cpp`（含对应头文件）并同步 `callmanager.gni` 条目（design D7 表）；`HsdrCallbackStub` 回调分发与 OpenSSL SHA256/Base64 调用点随文件消失，不为防诈保留桩出口。恢复条件：目标平台引入防诈云上报链路后按 baseline 需求整块恢复，或由后续 change 恢复。
