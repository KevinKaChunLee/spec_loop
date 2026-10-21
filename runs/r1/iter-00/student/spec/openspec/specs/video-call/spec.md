# 视频通话控制（Video Call Control）Specification

## Purpose
描述 HMOS call_manager 当前的视频通话控制能力：对 IMS 视频通话执行摄像头控制（打开/关闭、变焦、设备朝向、暂停画面）、预览/显示窗口设置、通话媒体模式升级/取消与摄像头能力协商。源码落点：`telephony_call_manager/services/video/{include,src}`：`video_control_manager.cpp`（类 `VideoControlManager`，`DECLARE_DELAYED_SINGLETON`）。编译开关：`ABILITY_CAMERA_SUPPORT` 仅在 `video_control_manager.cpp` 中守护 `ContainCameraID` 对 camera framework（`input/camera_manager.h`、`OHOS::CameraStandard::CameraManager`）的访问；`callmanager.gni` 在 `global_parts_info.multimedia_camera_framework` 存在时添加外部依赖 `camera_framework:camera_framework`（但不在仓内定义该宏，该宏由仓外编译配置提供）。

## Requirements

### Requirement: 摄像头打开与关闭
系统 SHALL 由 `VideoControlManager::ControlCamera` 依据 cameraId 是否为空分发：非空调用 `OpenCamera`（`CallPolicy::VideoCallPolicy` 校验通过且 callId 对应 `TYPE_IMS` 通话时经 `IMSCall::ControlCamera` 打开摄像头，成功后置 `isOpenCamera_` 为 true 并调用 `RequestCameraCapabilities`）；空 cameraId 调用 `CloseCamera`；摄像头未打开时 `CloseCamera` MUST 返回 `CALL_ERR_CAMERA_NOT_TURNED_ON`。

#### Scenario: 打开摄像头
- **WHEN** cameraId 非空、`VideoCallPolicy` 校验通过且 callId 对应 `TYPE_IMS` 通话
- **THEN** 经 `IMSCall::ControlCamera` 打开摄像头，`isOpenCamera_` 置 true，并请求摄像头能力，返回 `TELEPHONY_SUCCESS`

#### Scenario: 关闭未打开的摄像头
- **WHEN** `isOpenCamera_` 为 false 时以空 cameraId 调用 `ControlCamera`
- **THEN** `CloseCamera` 返回 `CALL_ERR_CAMERA_NOT_TURNED_ON`

#### Scenario: 通话对象不存在
- **WHEN** `CallObjectManager::GetOneCallObject(callId)` 返回 nullptr
- **THEN** 摄像头/窗口/朝向类接口均返回 `TELEPHONY_ERR_LOCAL_PTR_NULL`

### Requirement: 变焦与设备朝向参数校验
系统 SHALL 由 `SetCameraZoom` 校验 zoomRatio 位于 `MIN_CAMERA_ZOOM`(0.1)~`MAX_CAMERA_ZOOM`(10.0)，越界 MUST 返回 `CALL_ERR_VIDEO_INVALID_ZOOM`，合法时转发 `CellularCallConnection::SetCameraZoom`；由 `SetDeviceDirection` 校验 rotation 为 0/90/180/270，越界 MUST 返回 `CALL_ERR_VIDEO_INVALID_ROTATION`，合法时经 `IMSCall::SetDeviceDirection` 下发。

#### Scenario: 变焦越界
- **WHEN** `SetCameraZoom(0.05)` 或 `SetCameraZoom(11.0)`
- **THEN** 返回 `CALL_ERR_VIDEO_INVALID_ZOOM`，不向 cellular_call 侧转发

#### Scenario: 合法朝向下发
- **WHEN** TYPE_IMS 通话存在且 `SetDeviceDirection(callId, 90)`
- **THEN** 校验通过并经 `IMSCall::SetDeviceDirection(90)` 下发，返回 `TELEPHONY_SUCCESS`

### Requirement: 窗口与暂停画面设置
系统 SHALL 由 `SetPreviewWindow`/`SetDisplayWindow` 在 `VideoCallPolicy` 校验通过且 callId 对应 `TYPE_IMS` 通话时，将 surfaceId 与 Surface 经 `IMSCall::SetPreviewWindow`/`SetDisplayWindow` 设置；由 `SetPausePicture` 将暂停画面路径转 UTF-8 后经 `IMSCall::SetPausePicture` 设置；非 IMS 通话时 MUST 不调用 IMSCall 接口、直接返回 `TELEPHONY_SUCCESS`。

#### Scenario: 设置预览窗口
- **WHEN** TYPE_IMS 通话存在，调用 `SetPreviewWindow(callId, surfaceId, surface)`
- **THEN** Surface 经 `IMSCall::SetPreviewWindow` 设置，返回 `TELEPHONY_SUCCESS`

#### Scenario: 非IMS通话设置暂停画面
- **WHEN** callId 对应非 `TYPE_IMS` 通话，调用 `SetPausePicture(callId, path)`
- **THEN** 不调用 IMSCall 接口，直接返回 `TELEPHONY_SUCCESS`

### Requirement: 媒体模式升级与能力协商
系统 SHALL 由 `UpdateImsCallMode` 优先 `GetForegroundLiveCallByCallId`、回退 `GetOneCallObject` 取通话，TYPE_IMS 时经 `IMSCall::UpdateImsCallMode` 发起媒体模式升级；由 `CancelCallUpgrade` 取消升级；由 `RequestCameraCapabilities` 发起摄像头能力协商；`ReportImsCallModeInfo` 经 `CallAbilityReportProxy::ReportImsCallModeChange` 向应用上报媒体模式变化。

#### Scenario: 请求升级到视频
- **WHEN** 存在 TYPE_IMS 前台活跃通话且 `UpdateImsCallMode(callId, ImsCallMode::CALL_MODE_SEND_RECEIVE)`
- **THEN** 经 `IMSCall::UpdateImsCallMode` 请求模式切换

#### Scenario: 上报媒体模式
- **WHEN** 底层上报 `CallMediaModeInfo` 触发 `ReportImsCallModeInfo`
- **THEN** 经 `CallAbilityReportProxy::ReportImsCallModeChange` 通知已注册应用
