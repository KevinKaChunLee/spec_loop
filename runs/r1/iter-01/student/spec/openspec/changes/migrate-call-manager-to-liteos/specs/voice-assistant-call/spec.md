# Spec Delta

## REMOVED Requirements

### Requirement: 播报与控制开关查询

**Reason**: AGENTS 功能范围：不支持语音播报，相关代码无需迁移；`IsStartVoiceBroadcast`/`IsSwitchOn` 的开关查询链（含 HiCar 车机在线判定）随语音助手能力整体删除，HiCar 依赖的分布式车机亦不支持；design D7 被删文件表列出 `services/call_voice_assistant/src/call_voice_assistant_manager.cpp`。
**Migration**: 删除 `services/call_voice_assistant/src/call_voice_assistant_manager.cpp`（含 `services/call_voice_assistant/include/call_voice_assistant_manager.h`）并同步 `callmanager.gni` 的 `call_manager_sources` 与 `call_manager_include_dirs` 的 call_voice_assistant 目录条目（design D7 表）；`call_status_manager.cpp` 的 `IsStartVoiceBroadcast` 消费分支删除（见 call-status-management delta）。恢复条件：接入语音助手框架后重建开关查询链并恢复 gni 条目，或由后续 change 恢复。

### Requirement: 语音助手 ability 连接管理

**Reason**: AGENTS 功能范围：不支持语音播报，相关代码无需迁移；`ConnectAbility` 拉起语音助手与失败回退铃音订阅均依赖 AbilityManagerClient/公共事件框架，liteOS 不接入；design D7 被删文件表列出 `call_voice_assistant_manager.cpp`。
**Migration**: 删除 `services/call_voice_assistant/src/call_voice_assistant_manager.cpp`（含对应头文件）并同步 `callmanager.gni` 条目（design D7 表）；`call_control_manager.cpp` 的 `AddOneObserver(CallVoiceAssistantManager)` 注册分支删除（见 call-control-management delta）。恢复条件：接入语音助手框架后重建 ability 连接管理并恢复 gni 条目，或由后续 change 恢复。

### Requirement: 来去电状态触发

**Reason**: AGENTS 功能范围：不支持语音播报，相关代码无需迁移；`CallStateUpdated` 的来去电播报触发链（含免打扰过滤、VOIP off_hook 抢占、铃音量置零）随语音助手能力整体删除；design D7 被删文件表列出 `call_voice_assistant_manager.cpp`。
**Migration**: 删除 `services/call_voice_assistant/src/call_voice_assistant_manager.cpp`（含对应头文件）并同步 `callmanager.gni` 条目（design D7 表）；`call_status_manager.cpp` 的 `UpdateContactInfo`→`CallVoiceAssistantManager::UpdateContactInfo` 联动分支删除（见 call-status-management delta）。恢复条件：接入语音助手框架后重建状态触发链并恢复 gni 条目，或由后续 change 恢复。

### Requirement: 来话信息 IPC 同步

**Reason**: AGENTS 功能范围：不支持语音播报，相关代码无需迁移；且 liteOS 不实现 IPC 调用（AGENTS 架构要求），`mRemoteObject->SendRequest` 的来话信息同步通路无承载对象（design D2/D3）；design D7 被删文件表列出 `call_voice_assistant_manager.cpp`。
**Migration**: 删除 `services/call_voice_assistant/src/call_voice_assistant_manager.cpp`（含对应头文件）并同步 `callmanager.gni` 条目（design D7 表）；`call_control_manager.cpp` 的 `UpdateVoipCallState`→`nowVoipCallState` 消费分支删除（见 call-control-management delta）。恢复条件：支持语音播报且恢复系统形态后重建信息同步链并恢复 gni 条目，或由后续 change 恢复。

### Requirement: 铃音让位与静默控制

**Reason**: AGENTS 功能范围：不支持语音播报，相关代码无需迁移；`MuteRinger` 的播报让位与 `VoiceAssistantRingSubscriber` 的铃音接管均服务语音助手场景，liteOS 无该场景；design D7 被删文件表列出 `call_voice_assistant_manager.cpp`。
**Migration**: 删除 `services/call_voice_assistant/src/call_voice_assistant_manager.cpp`（含对应头文件）并同步 `callmanager.gni` 条目（design D7 表）；audio 侧 `AudioControlManager` 的"语音播报判定"分支删除（见 audio-device-management delta）；蜂窝侧 `MuteRinger` 主线与免打扰静默判定保留（见 call-control-management/call-object-management delta）。恢复条件：接入语音助手框架后重建铃音让位链并恢复 gni 条目，或由后续 change 恢复。
