# Spec Delta

## REMOVED Requirements

### Requirement: 视频接口前置校验
**Reason**: AGENTS.md 功能范围：视频通话不支持。
**Migration**: `VideoControlManager` 与 `CallPolicy::VideoCallPolicy` 的视频前置校验不迁移；`ControlCamera`/`SetPreviewWindow`/`SetDisplayWindow`/`SetPausePicture`/`SetDeviceDirection`/`CancelCallUpgrade`/`RequestCameraCapabilities` 接口不迁移。

### Requirement: 摄像头开关
**Reason**: AGENTS.md 功能范围：视频通话不支持（`ABILITY_CAMERA_SUPPORT` 为不支持宏）。
**Migration**: `ControlCamera`/`OpenCamera`/`CloseCamera`/`ContainCameraID` 与 `CameraManager` 枚举链路不迁移。

### Requirement: 参数范围校验
**Reason**: AGENTS.md 功能范围：视频通话不支持。
**Migration**: `SetCameraZoom`/`SetDeviceDirection`/`CheckWindow` 校验与 `CellularCallConnection::SetCameraZoom` 转发链路不迁移。

### Requirement: 视频模式上报与切换
**Reason**: AGENTS.md 功能范围：视频通话不支持。
**Migration**: `UpdateImsCallMode`/`ReportImsCallModeInfo` 与 `IMSCall::UpdateImsCallMode` 状态机链路不迁移（见 call-object-model delta 的 IMS 视频升级状态机移除）。
