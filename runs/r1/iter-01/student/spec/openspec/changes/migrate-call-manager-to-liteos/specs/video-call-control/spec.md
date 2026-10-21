# Spec Delta

## REMOVED Requirements

### Requirement: 摄像头开关控制

**Reason**: AGENTS 功能范围：不支持视频通话，相关代码无需迁移；`ABILITY_CAMERA_SUPPORT` 属不支持宏（AGENTS 特性宏支持范围）、恒关，摄像头开关链路在 liteOS 不可达；design D7 被删文件表列出 `services/video/src/video_control_manager.cpp`。
**Migration**: 删除 `services/video/src/video_control_manager.cpp`（含对应头文件）并同步 `callmanager.gni` 的 `call_manager_sources` 条目与 `call_manager_include_dirs` 的 video 目录条目（design D7 表）；`ABILITY_CAMERA_SUPPORT` 宏场点仅在该文件、随文件删除，gni `global_parts_info.multimedia_camera_framework` 部件块与 `camera_framework` 外部依赖删除（design D7 宏清理）。恢复条件：支持视频通话后重建本文件并恢复 gni 条目与宏块，或由后续 change 恢复。

### Requirement: 预览与显示窗口及窗口参数设置

**Reason**: AGENTS 功能范围：不支持视频通话，相关代码无需迁移；预览/显示窗口与窗口参数设置仅对 `TYPE_IMS` 视频通话生效，该形态在 liteOS 不存在；design D7 被删文件表列出 `video_control_manager.cpp`。
**Migration**: 删除 `services/video/src/video_control_manager.cpp`（含对应头文件）并同步 `callmanager.gni` 条目（design D7 表）；`IMSCall` 侧 `SetPreviewWindow`/`SetDisplayWindow`/`SetPausePicture`/`SetDeviceDirection` 视频扩展指令转发族随 `video_call_state.cpp` 删除移除（见 call-object-management delta「IMSCall 通话对象」条）；`ABILITY_CAMERA_SUPPORT` gni 宏块处置同上（design D7 宏清理）。恢复条件：支持视频通话后重建窗口参数链并恢复 gni 条目，或由后续 change 恢复。

### Requirement: 相机缩放

**Reason**: AGENTS 功能范围：不支持视频通话，相关代码无需迁移；`SetCameraZoom` 是视频通话控制面的入口函数，随 `video_control_manager.cpp` 整体删除，缩放值经 `CellularCallConnection` 的下发链不再有调用方；design D7 被删文件表列出 `video_control_manager.cpp`。
**Migration**: 删除 `services/video/src/video_control_manager.cpp`（含对应头文件）并同步 `callmanager.gni` 条目（design D7 表）；`CellularCallConnection::SetCameraZoom` 适配器出口随视频控制面消失无调用方，不做单独保留（适配器本体属 telephony-interaction 能力）；`ABILITY_CAMERA_SUPPORT` gni 宏块处置同上（design D7 宏清理）。恢复条件：支持视频通话后重建缩放控制链并恢复 gni 条目，或由后续 change 恢复。

### Requirement: 媒体模式升级与取消

**Reason**: AGENTS 功能范围：不支持视频通话，相关代码无需迁移；音频/视频升级请求、取消升级与相机能力请求仅对 `TYPE_IMS` 视频通话生效，liteOS 无该形态；design D7 被删文件表列出 `video_control_manager.cpp`。
**Migration**: 删除 `services/video/src/video_control_manager.cpp`（含对应头文件）并同步 `callmanager.gni` 条目（design D7 表）；`IMSCall::UpdateImsCallMode` 与媒体模式协商收发族（`SendUpdateCallMediaModeRequest` 系）、`CallAbilityReportProxy::ReportImsCallModeChange` 媒体模式上报消费随 `video_call_state.cpp` 删除移除（见 call-object-management delta）；`ABILITY_CAMERA_SUPPORT` gni 宏块处置同上（design D7 宏清理）。恢复条件：支持视频通话后重建升级/取消链并恢复 gni 条目，或由后续 change 恢复。

### Requirement: 相机能力枚举的宏门控

**Reason**: AGENTS 功能范围：不支持视频通话，相关代码无需迁移；`ABILITY_CAMERA_SUPPORT` 属不支持宏（AGENTS 特性宏支持范围）、恒关，`ContainCameraID` 宏关闭分支恒返回 false，无迁移价值；design D7 宏处置表明确该宏场点仅 `video_control_manager.cpp`、随文件删除。
**Migration**: 删除 `services/video/src/video_control_manager.cpp`（含对应头文件，含 `ContainCameraID` 实现与 `input/camera_manager.h` 引入）并同步 `callmanager.gni` 条目（design D7 表）；gni `global_parts_info.multimedia_camera_framework` 部件块删除（design D7 宏清理）。恢复条件：接入相机框架后重建枚举判定并恢复 gni 部件块与宏，或由后续 change 恢复。
