# Spec Delta

## REMOVED Requirements

### Requirement: 管理器生命周期与系统能力订阅

**Reason**: AGENTS 功能范围：不支持分布式（distributed 及 interoperable）通话，相关代码无需迁移；`DistributedCallManager` 依赖 samgr 订阅与 `dlopen("libdistributed_call_client.z.so")` 代理加载，liteOS 无系统服务生态与 dlopen 通路；design D7 被删文件表列出 `distributed_call_manager.cpp`、`distributed_call_proxy.cpp`。
**Migration**: 删除 `services/distributed_call/` 下 `distributed_call_manager.cpp`、`distributed_call_proxy.cpp`（含对应头文件）并同步 `callmanager.gni` 的 `call_manager_sources` 与 `call_manager_include_dirs` 的 distributed_call 目录条目（design D7 表）；`CallManagerService::Init` 的 `DistributedCallManager::Init()` 装配调用删除（见 call-manager-service delta）。恢复条件：支持分布式通话后重建管理器与代理并恢复 gni 条目，或由后续 change 恢复。

### Requirement: 分布式设备发现与设备对象构造

**Reason**: AGENTS 功能范围：不支持分布式（distributed 及 interoperable）通话，相关代码无需迁移；设备发现与 JSON 地址映射依赖 dcall 代理与设备回调，liteOS 不可达；design D7 被删文件表列出 `distributed_call_manager.cpp`；其 `ABILITY_BLUETOOTH_SUPPORT` 门控的 HFP 监听场点（`AddDCallDevice`/`OnDCallDeviceOffline`）随 gni 宏块一并删除（design D7 宏处置行）。
**Migration**: 删除 `services/distributed_call/src/distributed_call_manager.cpp`（含对应头文件）并同步 `callmanager.gni` 条目（design D7 表）；`callmanager.gni` 的 `ABILITY_BLUETOOTH_SUPPORT` 部件块删除、分布式侧 HFP 监听场点随之消失（design D7 宏处置行）；音频设备表中 `DEVICE_DISTRIBUTED_PHONE/PAD/AUTOMOTIVE` 类型与 `CheckAndSwitchDistributedAudioDevice` 路由族删除（见 audio-device-management delta）。恢复条件：支持分布式通话后重建设备发现链并恢复 gni 条目与宏块，或由后续 change 恢复。

### Requirement: 设备切换与音频输出路由

**Reason**: AGENTS 功能范围：不支持分布式（distributed 及 interoperable）通话，相关代码无需迁移；`SwitchOnDCallDeviceSync` 切换与 `ReportDistributedDeviceInfo` 音频路由依赖 dcall 代理与 audio_framework 分布式设备枚举，均不可达；design D7 被删文件表列出 `distributed_call_manager.cpp`。
**Migration**: 删除 `services/distributed_call/src/distributed_call_manager.cpp`（含对应头文件）并同步 `callmanager.gni` 条目（design D7 表）；`dCallDeviceSwitchedOn_` 的消费方（`dealCeliaCallEvent` 分布式关断联动）随新通话删除（见 call-manager-service delta）；音频输出路由侧的分布式分支删除见 audio-device-management delta。恢复条件：支持分布式通话后重建切换与路由链并恢复 gni 条目，或由后续 change 恢复。

### Requirement: 分布式通信管理与数据控制器

**Reason**: AGENTS 功能范围：不支持分布式（distributed 及 interoperable）通话，相关代码无需迁移；`DistributedCommunicationManager` 依赖软总线会话与 `dlopen("libtelephony_ext_innerkits.z.so")` 包装，liteOS 无 dsoftbus（`SUPPORT_DSOFTBUS` 属不支持宏）；design D7 被删文件表列出 `distributed_communication/` 6 个 cpp；source/sink 开关控制器中 `ABILITY_BLUETOOTH_SUPPORT` 门控的 HFP 联动场点随 gni 宏块一并删除（design D7 宏处置行）。
**Migration**: 删除 `services/distributed_call/src/distributed_communication/` 下 6 个 cpp（含对应头文件）并同步 `callmanager.gni` 条目与 dsoftbus 外部依赖（design D7 表）；`CallManagerService::Init` 的 `DistributedCommunicationManager::Init()` 装配与 `SetMuted`/`MuteRinger` 的分布式联动删除（见 call-manager-service delta）；`SUPPORT_DSOFTBUS` 零引用、无迁移动作（design D7 不支持宏表）。恢复条件：接入 dsoftbus 后重建通信管理与数据控制器并恢复 gni 条目，或由后续 change 恢复。

### Requirement: 软总线会话传输

**Reason**: AGENTS 功能范围：不支持分布式（distributed 及 interoperable）通话，相关代码无需迁移；`TransmissionManager`/`ServerSession`/`ClientSession` 全部基于软总线 `Socket` 会话与 cJSON 消息，liteOS 无 dsoftbus；design D7 被删文件表列出 `transmission/` 5 个 cpp。
**Migration**: 删除 `services/distributed_call/src/transmission/` 下 5 个 cpp（含对应头文件）并同步 `callmanager.gni` 条目与 dsoftbus 外部依赖（design D7 表）；cJSON 桩（`stub/cjson_stub`）仅服务于保留的解析面（spam_call/json 数据面、voip 解析），本需求的会话收发面整体消失。恢复条件：接入 dsoftbus 后重建会话传输族并恢复 gni 条目，或由后续 change 恢复。
