# Video Call Control Specification

## Purpose
描述 HMOS `telephony_call_manager` 中视频通话控制（`services/video/src/video_control_manager.cpp`）的移植前现状：`VideoControlManager` 封装摄像头开关/预览与显示窗口/窗口参数、缩放、媒体模式升级与取消等控制面，且除 `SetCameraZoom`、`ContainCameraID`、`CheckWindow` 外全部动作仅对 `CallType::TYPE_IMS` 通话生效（经 `CallPolicy::VideoCallPolicy` 前置校验后转调 `IMSCall` 对应方法）。相机枚举能力由 `ABILITY_CAMERA_SUPPORT` 宏门控：该宏在 `callmanager.gni` 中不定义（gni 仅在 `global_parts_info.multimedia_camera_framework` 部件存在时追加 `camera_framework:camera_framework` 外部依赖），`#ifdef ABILITY_CAMERA_SUPPORT` 场点仅存在于 `services/video/src/video_control_manager.cpp`（引入 `input/camera_manager.h` 与 `ContainCameraID` 实现体）。

## Requirements

### Requirement: 摄像头开关控制
系统 SHALL 由 `VideoControlManager::ControlCamera` 按 cameraId 分发：空串转 `CloseCamera`，非空转 `OpenCamera`。`OpenCamera` SHALL 经 `CallPolicy::VideoCallPolicy` 校验、取 `CallObjectManager::GetOneCallObject` 通话对象后，对 `TYPE_IMS` 通话调用 `IMSCall::ControlCamera`，成功时置 `isOpenCamera_` 为 true 并追加 `IMSCall::RequestCameraCapabilities`。`CloseCamera` SHALL 在 `isOpenCamera_` 为 false 时直接返回 `CALL_ERR_CAMERA_NOT_TURNED_ON`，为 true 时对 `TYPE_IMS` 通话转调 `IMSCall::ControlCamera`。

#### Scenario: 未开相机时关闭
- **WHEN** `ControlCamera` 收到空 cameraId 且此前未成功 `OpenCamera`
- **THEN** 返回 `CALL_ERR_CAMERA_NOT_TURNED_ON`，不触碰 `IMSCall`

#### Scenario: 打开相机
- **WHEN** `OpenCamera` 在 `TYPE_IMS` 通话上且 `IMSCall::ControlCamera` 返回成功
- **THEN** `isOpenCamera_` 置 true，并继续发起 `RequestCameraCapabilities`

### Requirement: 预览与显示窗口及窗口参数设置
系统 SHALL 由 `SetPreviewWindow`/`SetDisplayWindow` 在 `VideoCallPolicy` 校验通过且通话为 `TYPE_IMS` 时转调 `IMSCall::SetPreviewWindow`/`SetDisplayWindow`，非 IMS 通话直接返回成功。`SetDeviceDirection` SHALL 仅接受 0/90/180/270 四个旋转值，否则返回 `CALL_ERR_VIDEO_INVALID_ROTATION`；`SetPausePicture` SHALL 经 `Str16ToStr8` 转换后对 IMS 通话转调 `IMSCall::SetPausePicture`。`CheckWindow` SHALL 校验 `VideoWindow` 的 width/height 大于 0 且 z 取值仅允许 `VIDEO_WINDOWS_Z_BOTTOM`(0) 或 `VIDEO_WINDOWS_Z_TOP`(1)。

#### Scenario: 非法旋转角
- **WHEN** `SetDeviceDirection(callId, 45)` 在有效 IMS 通话上调用
- **THEN** 返回 `CALL_ERR_VIDEO_INVALID_ROTATION`，不调用 `IMSCall::SetDeviceDirection`

#### Scenario: 非法窗口参数
- **WHEN** `CheckWindow` 收到 width=0 或 z=2 的 `VideoWindow`
- **THEN** 返回 false

### Requirement: 相机缩放
系统 SHALL 由 `SetCameraZoom` 校验 zoomRatio 在 `MIN_CAMERA_ZOOM`(0.1) 与 `MAX_CAMERA_ZOOM`(10.0) 区间内，越界返回 `CALL_ERR_VIDEO_INVALID_ZOOM`；合法值经 `CellularCallConnection` 的 `SetCameraZoom` 下发给 cellular_call，不做通话类型限制。

#### Scenario: 缩放越界
- **WHEN** `SetCameraZoom(0.05)` 或 `SetCameraZoom(11.0)`
- **THEN** 返回 `CALL_ERR_VIDEO_INVALID_ZOOM`，不调用 CellularCallConnection

#### Scenario: 合法缩放透传
- **WHEN** `SetCameraZoom(2.0)`
- **THEN** 转调 `CellularCallConnection::SetCameraZoom(2.0)` 并透传其返回值

### Requirement: 媒体模式升级与取消
系统 SHALL 由 `UpdateImsCallMode` 优先取 `CallObjectManager::GetForegroundLiveCallByCallId`，取不到再取 `GetOneCallObject`，对 `TYPE_IMS` 通话转调 `IMSCall::UpdateImsCallMode(callMode)` 发起音频/视频升级请求；`CancelCallUpgrade` 与 `RequestCameraCapabilities`（带 callId 版本）SHALL 同样经 `VideoCallPolicy` 校验后对 IMS 通话转调 `IMSCall` 对应方法。`ReportImsCallModeInfo` SHALL 经 `CallAbilityReportProxy::ReportImsCallModeChange` 向通话界面回调媒体模式变化。

#### Scenario: 发起视频升级
- **WHEN** `UpdateImsCallMode(callId, ImsCallMode::TYPE_VIDEO)` 在前台活跃 IMS 通话上调用
- **THEN** 转调 `IMSCall::UpdateImsCallMode(TYPE_VIDEO)` 并透传结果

#### Scenario: 取消升级
- **WHEN** `CancelCallUpgrade` 在 `TYPE_IMS` 通话上调用且 `IMSCall::CancelCallUpgrade` 成功
- **THEN** 返回 `TELEPHONY_SUCCESS`

### Requirement: 相机能力枚举的宏门控
系统 SHALL 由 `ContainCameraID` 判断 cameraId 是否为设备真实相机：在 `ABILITY_CAMERA_SUPPORT` 打开时经 `CameraStandard::CameraManager::GetInstance()->GetSupportedCameras()` 枚举并逐个比对 `GetID`，命中返回 true；宏关闭时 SHALL 恒返回 false，不引入相机框架。

#### Scenario: 宏关闭时恒不包含
- **WHEN** `ABILITY_CAMERA_SUPPORT` 未定义且 `ContainCameraID("CAMERA_0")` 调用
- **THEN** 返回 false，不触碰 CameraManager

#### Scenario: 宏打开时命中设备相机
- **WHEN** `ABILITY_CAMERA_SUPPORT` 定义且传入的 id 与 `GetSupportedCameras` 列表中某设备 `GetID` 相同
- **THEN** 返回 true
