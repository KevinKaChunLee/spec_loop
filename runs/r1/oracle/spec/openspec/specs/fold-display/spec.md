# 折叠屏状态（fold-display）Specification

## Purpose
描述 `telephony_call_manager/services/display/` 的折叠屏状态模块组：`FoldStatusManager`（折叠状态监听与隐私模式联动、小折叠形态判定）。落点：`services/display/src/fold_status_manager.cpp` 与 `services/display/include/fold_status_manager.h`。该模块组无独有编译开关；依赖 `Rosen::DisplayManager` 与系统参数。

## Requirements

### Requirement: 折叠状态监听
系统 SHALL 由 `FoldStatusManager`（`DECLARE_DELAYED_SINGLETON`）经 `RegisterFoldableListener()` 注册内部类 `FoldStatusListener : Rosen::DisplayManager::IFoldStatusListener`（`DMError::DM_OK` 判定成功）并缓存 `mOldFoldStatus`，`UnregisterFoldableListener()` 反向注销并复位 `Rosen::FoldStatus::UNKNOWN`；`OnFoldStatusChanged` 仅在与 `mOldFoldStatus` 不同时 `CallDialog::DialogCallingPrivacyModeExtension(foldStatus)` 并更新旧值。
#### Scenario: 通话中折叠形态变化
- **WHEN** 注册监听后设备折叠状态发生变化
- **THEN** 以新 foldStatus 调用 `CallDialog::DialogCallingPrivacyModeExtension`，同状态重复回调不触发

### Requirement: 小折叠形态判定
系统 SHALL 由 `FoldStatusManager::IsSmallFoldDevice()` 读系统参数 `FOLD_PRODUCT_TYPE_KEY = "const.window.foldscreen.type"`（默认 `"0,0,0,0"`），`FOLD_TYPE_INDEX = 0` 处字符等于 `SMALL_FOLD_PRODUCT_TYPE = '2'` 判定小折叠；`CallObjectManager::AddOneCallObject` 在小折叠设备上 `RegisterFoldableListener()`，表空时 `UnregisterFoldableListener()`。
#### Scenario: 非小折叠设备
- **WHEN** `const.window.foldscreen.type` 首字符非 '2'
- **THEN** 通话对象创建不注册折叠监听
