# Spec Delta

## REMOVED Requirements

### Requirement: 开关与数据面
**Reason**: AGENTS.md 功能范围：语音播报（来电语音助手）不支持。
**Migration**: `CallVoiceAssistantManager` 与 `CONTROL_SWITCH`/`BROADCAST_SWITCH` DataShare 查询面不迁移；`CallStateListener` 注册项移除。

### Requirement: 助手 ability 连接与检测请求
**Reason**: AGENTS.md 功能范围：语音播报/号码助手不支持。
**Migration**: `OnStartService`/`ConnectAbility`（`CallVoiceControlAbility`）与 `CHECK_CODE = 1006` 检测请求链路不迁移；`VoiceAssistantRingSubscriber` 与铃声控制事件订阅移除。

### Requirement: 状态联动
**Reason**: AGENTS.md 功能范围：语音播报不支持。
**Migration**: `ffrt::queue callVoiceAssistantQueue` 串行处理与 `SetRingToneVolume(0.0f)`/`OnStopService` 联动不迁移；免打扰判定（`IsNeedSilentInDoNotDisturbMode`）的调用方移除（免打扰查询本身见 call-status-manager delta 的占位处置）。
