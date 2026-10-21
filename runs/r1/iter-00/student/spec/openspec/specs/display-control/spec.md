# 显示控制（Display Control） Specification

## Purpose
描述折叠屏折叠状态监听及其对通话显示（超级隐私模式对话框）影响的基线行为。源码落点：`telephony_call_manager/services/display/{include,src}`（`fold_status_manager.cpp/.h`：`FoldStatusManager`/`FoldStatusListener`），联动 `telephony_call_manager/utils/src/call_dialog.cpp` 的 `DialogCallingPrivacyModeExtension`；监听注册方为 `telephony_call_manager/services/call/src/call_object_manager.cpp` 的 `AddOneCallObject`。该能力无专属编译宏：源文件无条件列入 `callmanager.gni` 的 `call_manager_sources`。

## Requirements

### Requirement: 小折叠设备判定
系统 SHALL 由 `FoldStatusManager::IsSmallFoldDevice` 通过系统参数 `const.window.foldscreen.type`（默认 `0,0,0,0`）判定设备是否为小折叠形态：仅当参数非空且首字符（`FOLD_TYPE_INDEX` = 0）为 `2`（`SMALL_FOLD_PRODUCT_TYPE`）时返回 true。
#### Scenario: 小折叠设备
- **WHEN** `const.window.foldscreen.type` 值为以 `2` 开头的非空字符串
- **THEN** `IsSmallFoldDevice` 返回 true
#### Scenario: 非小折叠设备
- **WHEN** 参数为默认值 `0,0,0,0` 或为空
- **THEN** `IsSmallFoldDevice` 返回 false

### Requirement: 折叠状态监听注册
系统 SHALL 由 `FoldStatusManager::RegisterFoldableListener` 在小折叠设备上首次添加通话对象时（`CallObjectManager::AddOneCallObject` 判定 `IsSmallFoldDevice` 后调用）经 `Rosen::DisplayManager::RegisterFoldStatusListener` 注册 `FoldStatusListener` 并记录当前 `GetFoldStatus` 到 `mOldFoldStatus`；`UnregisterFoldableListener` 注销监听并将 `mOldFoldStatus` 复位为 `Rosen::FoldStatus::UNKNOWN`。重复注册 MUST 被忽略。
#### Scenario: 注册成功
- **WHEN** 小折叠设备上添加首个通话对象且注册返回 `Rosen::DMError::DM_OK`
- **THEN** 监听器生效，`mOldFoldStatus` 记录当前折叠状态
#### Scenario: 重复注册
- **WHEN** `foldStatusListener_` 已非空时再次调用 `RegisterFoldableListener`
- **THEN** 直接返回，不重复注册

### Requirement: 折叠状态变化联动通话显示
系统 SHALL 由 `FoldStatusListener::OnFoldStatusChanged` 在折叠状态与 `mOldFoldStatus` 不同时调用 `CallDialog::DialogCallingPrivacyModeExtension(foldStatus)` 并更新 `mOldFoldStatus`；`DialogCallingPrivacyModeExtension` MUST 仅在新状态为 `Rosen::FoldStatus::FOLDED`、超级隐私模式开启（`CallSuperPrivacyControlManager::GetCurrentIsSuperPrivacyMode`）且前台通话存在且非来电状态时，经 `CallSettingAbilityConnection` 连接 `com.ohos.sceneboard.systemdialog`（dialogReason `SUPER_PRIVACY_MODE`）弹出隐私模式对话框。
#### Scenario: 折叠进入超级隐私
- **WHEN** 折叠状态变为 `FOLDED`、超级隐私模式开启且前台通话处于非 INCOMING 状态
- **THEN** 连接 systemdialog 扩展弹出隐私模式对话框
#### Scenario: 状态未变化
- **WHEN** 新回调的 `foldStatus` 与 `mOldFoldStatus` 相同
- **THEN** 不触发对话框联动，仅记录日志
#### Scenario: 展开状态
- **WHEN** 折叠状态变为非 `FOLDED` 的其他值
- **THEN** 不触发隐私模式对话框
