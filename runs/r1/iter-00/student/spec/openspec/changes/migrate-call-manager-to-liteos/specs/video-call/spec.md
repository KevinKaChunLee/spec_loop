# Spec Delta

## REMOVED Requirements

### Requirement: 摄像头打开与关闭
**Reason**: liteOS 不支持视频通话（含视频彩振 crsType==CRS_TYPE），`services/video/` 目录不迁移（AGENTS.md 功能范围）。
**Migration**: 无替代。

### Requirement: 变焦与设备朝向参数校验
**Reason**: liteOS 不支持视频通话，摄像头变焦与朝向控制（`services/video/`）不迁移（AGENTS.md 功能范围）。
**Migration**: 无替代。

### Requirement: 窗口与暂停画面设置
**Reason**: liteOS 不支持视频通话，预览/显示窗口与暂停画面设置（`services/video/`）不迁移（AGENTS.md 功能范围）。
**Migration**: 无替代。

### Requirement: 媒体模式升级与能力协商
**Reason**: liteOS 不支持视频通话（含视频彩振 crsType==CRS_TYPE），媒体模式升级与摄像头能力协商（`services/video/`）不迁移（AGENTS.md 功能范围）。
**Migration**: 无替代。
