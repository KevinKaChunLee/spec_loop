# Spec Delta

## REMOVED Requirements

### Requirement: 折叠状态监听
**Reason**: AGENTS.md 功能范围：折叠屏不支持。
**Migration**: `FoldStatusManager`/`FoldStatusListener`（`Rosen::DisplayManager::IFoldStatusListener`）与 `DialogCallingPrivacyModeExtension(foldStatus)` 联动不迁移；超级隐私弹窗调用方已随超级隐私移除。

### Requirement: 小折叠形态判定
**Reason**: AGENTS.md 功能范围：折叠屏不支持。
**Migration**: `IsSmallFoldDevice()`（`FOLD_PRODUCT_TYPE_KEY = "const.window.foldscreen.type"`）判定与 `CallObjectManager::AddOneCallObject` 的折叠监听注册链路不迁移。
