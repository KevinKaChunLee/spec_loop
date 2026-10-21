# 视频通话控制（video-call）Specification

## Purpose
描述 `telephony_call_manager/services/video/` 的视频通话控制：`VideoControlManager`（摄像头、预览/显示窗口、变焦、暂停画面、设备方向、视频模式上报与升级取消）。落点：`services/video/src/video_control_manager.cpp` 与 `services/video/include/video_control_manager.h`。编译开关：`ABILITY_CAMERA_SUPPORT`（`ContainCameraID` 经 `OHOS::CameraStandard::CameraManager` 枚举 cameraId，multimedia_camera_framework 部件在位时开）。

## Requirements

### Requirement: 视频接口前置校验
系统 SHALL 由 `VideoControlManager`（`DECLARE_DELAYED_SINGLETON`）在 `ControlCamera/SetPreviewWindow/SetDisplayWindow/SetPausePicture/SetDeviceDirection/CancelCallUpgrade/RequestCameraCapabilities` 前经 `CallPolicy::VideoCallPolicy(callId)` 校验，且仅 `CallType::TYPE_IMS` 通话（`reinterpret_cast<IMSCall*>`）实际执行，其余类型不生效。
#### Scenario: 非 IMS 通话请求摄像头
- **WHEN** 非 `TYPE_IMS` 通话调用 `ControlCamera`
- **THEN** 请求不转发，功能不生效

### Requirement: 摄像头开关
系统 SHALL 由 `ControlCamera(callId, cameraId, callingUid, callingPid)`：cameraId 为空走 `CloseCamera`（未开返回 `CALL_ERR_CAMERA_NOT_TURNED_ON`），否则 `OpenCamera`（成功置 `isOpenCamera_` 并自动追加 `RequestCameraCapabilities`）；`ContainCameraID` 在 `ABILITY_CAMERA_SUPPORT` 下经 `CameraManager::GetInstance()->GetSupportedCameras()` 遍历 `GetID()` 校验。
#### Scenario: 传入不存在的摄像头 ID
- **WHEN** cameraId 不在 `ContainCameraID` 枚举结果内
- **THEN** 摄像头不打开

### Requirement: 参数范围校验
系统 SHALL 由 `SetCameraZoom` 校验 `[MIN_CAMERA_ZOOM = 0.1, MAX_CAMERA_ZOOM = 10.0]`（越界返回 `CALL_ERR_VIDEO_INVALID_ZOOM`）后转发 `CellularCallConnection::SetCameraZoom`；`SetDeviceDirection` 仅允许 `CAMERA_ROTATION_0/90/180/270`（否则返回 `CALL_ERR_VIDEO_INVALID_ROTATION`）；`CheckWindow` 校验宽高大于 0 与 z 值（`VIDEO_WINDOWS_Z_BOTTOM = 0`/`VIDEO_WINDOWS_Z_TOP = 1`）。
#### Scenario: 越界变焦请求
- **WHEN** `SetCameraZoom(20.0)`
- **THEN** 返回 `CALL_ERR_VIDEO_INVALID_ZOOM` 拒绝下发

### Requirement: 视频模式上报与切换
系统 SHALL 由 `UpdateImsCallMode(callId, ImsCallMode)` 优先取 `CallObjectManager::GetForegroundLiveCallByCallId`，回退 `GetOneCallObject`，再转 `IMSCall::UpdateImsCallMode`；`ReportImsCallModeInfo(CallMediaModeInfo&)` 转发 `CallAbilityReportProxy::ReportImsCallModeChange`。
#### Scenario: 前台通话切换视频模式
- **WHEN** 前台存活通话请求 `UpdateImsCallMode`
- **THEN** 经 `IMSCall::UpdateImsCallMode` 走视频升级状态机并最终上报 `ReportImsCallModeChange`
