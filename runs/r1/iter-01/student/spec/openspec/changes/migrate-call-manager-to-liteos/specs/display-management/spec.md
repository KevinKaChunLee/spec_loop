# Spec Delta

## REMOVED Requirements

### Requirement: 折叠监听注册与注销

**Reason**: AGENTS 功能范围：不支持折叠屏，相关代码无需迁移；`FoldStatusListener` 依赖 `Rosen::DisplayManager` 折叠状态订阅，liteOS 无显示服务生态；design D7 被删文件表列出 `services/display/src/fold_status_manager.cpp`。
**Migration**: 删除 `services/display/src/fold_status_manager.cpp`（含 `services/display/include/fold_status_manager.h`）并同步 `callmanager.gni` 的 `call_manager_sources` 与 `call_manager_include_dirs` 的 display 目录条目（design D7 表）；`call_object_manager.cpp` 的 `AddOneCallObject`/`DeleteOneCallObject` 折叠监听注册/注销联动删除（见 call-object-management delta）。恢复条件：支持折叠屏后重建监听注册链并恢复 gni 条目，或由后续 change 恢复。

### Requirement: 折叠状态变化联动通话隐私弹窗

**Reason**: AGENTS 功能范围：不支持折叠屏，相关代码无需迁移；折叠状态变化触发的 `DialogCallingPrivacyModeExtension` 隐私弹窗联动随监听链整体消失；design D7 被删文件表列出 `fold_status_manager.cpp`。
**Migration**: 删除 `services/display/src/fold_status_manager.cpp`（含对应头文件）并同步 `callmanager.gni` 条目（design D7 表）；`CallDialog` 对话框连接出口本体按 `[callUi]` todo 桩化保留（design D6 拉起通话界面行），仅折叠弹窗调用点随本需求删除。恢复条件：支持折叠屏后重建隐私弹窗联动并恢复 gni 条目，或由后续 change 恢复。

### Requirement: 小折叠机型判定

**Reason**: AGENTS 功能范围：不支持折叠屏，相关代码无需迁移；`IsSmallFoldDevice` 按系统参数 `const.window.foldscreen.type` 判定小折叠机型，liteOS 平台无折叠形态、判定恒无意义；design D7 被删文件表列出 `fold_status_manager.cpp`。
**Migration**: 删除 `services/display/src/fold_status_manager.cpp`（含对应头文件，`IsSmallFoldDevice` 随文件消失）并同步 `callmanager.gni` 条目（design D7 表）；系统参数读取经 `stub/parameter_stub` 桩的约定不变（design D5），本判定无迁移调用点。恢复条件：支持折叠屏后重建机型判定并恢复 gni 条目，或由后续 change 恢复。
