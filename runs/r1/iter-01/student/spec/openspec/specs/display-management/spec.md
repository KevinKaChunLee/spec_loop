# Display Management Specification

## Purpose
描述 HMOS `telephony_call_manager` 中折叠屏显示状态管理（`services/display/src/fold_status_manager.cpp`，头文件 `services/display/include/fold_status_manager.h`）的移植前现状：`FoldStatusManager` 通过 `Rosen::DisplayManager` 订阅折叠状态（`FoldStatusListener`），仅在折叠状态实际变化时联动通话侧隐私模式弹窗（`CallDialog::DialogCallingPrivacyModeExtension`）；`IsSmallFoldDevice` 以系统参数 `const.window.foldscreen.type` 判定小折叠机型，决定是否启用折叠监听（由 `services/call/src/call_object_manager.cpp` 的 `AddOneCallObject`/`DeleteOneCallObject` 在首通电话建立时注册、通话清空时注销）。本模块无特性宏门控。

## Requirements

### Requirement: 折叠监听注册与注销
系统 SHALL 由 `RegisterFoldableListener` 创建 `FoldStatusListener` 并经 `Rosen::DisplayManager::RegisterFoldStatusListener` 注册，成功时以 `GetFoldStatus` 记录初始 `mOldFoldStatus`（构造时为 `Rosen::FoldStatus::UNKNOWN`），重复注册 SHALL 直接忽略；`UnregisterFoldableListener` SHALL 反注册并复位 `mOldFoldStatus` 为 UNKNOWN。注册时机 SHALL 由通话对象管理驱动：`IsSmallFoldDevice()` 为真时首通电话加入通话列表触发注册，通话列表清空时注销。

#### Scenario: 首通电话建立时注册
- **WHEN** 小折叠机型上通话列表从空变为非空
- **THEN** `RegisterFoldableListener` 执行，`mOldFoldStatus` 记录当前折叠状态

#### Scenario: 通话清空时注销
- **WHEN** 小折叠机型上最后一个通话对象被删除
- **THEN** `UnregisterFoldableListener` 执行，监听器与折叠状态复位

#### Scenario: 重复注册
- **WHEN** `foldStatusListener_` 已存在时再次调用 `RegisterFoldableListener`
- **THEN** 直接返回，不重复向 DisplayManager 注册

### Requirement: 折叠状态变化联动通话隐私弹窗
系统 SHALL 由 `FoldStatusListener::OnFoldStatusChanged` 与 `mOldFoldStatus` 比较：相同则直接返回；不同则调用 `CallDialog::DialogCallingPrivacyModeExtension(foldStatus)` 联动通话隐私模式界面，并更新 `mOldFoldStatus`。

#### Scenario: 折叠状态未变化
- **WHEN** 回调收到的 foldStatus 与 `mOldFoldStatus` 相同
- **THEN** 不触发隐私模式弹窗

#### Scenario: 折叠状态变化
- **WHEN** 回调收到的 foldStatus 与 `mOldFoldStatus` 不同
- **THEN** 以新状态调用 `DialogCallingPrivacyModeExtension` 并更新 `mOldFoldStatus`

### Requirement: 小折叠机型判定
系统 SHALL 由 `IsSmallFoldDevice` 读取系统参数 `const.window.foldscreen.type`（默认 "0,0,0,0"），参数为空返回 false，否则以首字符（`FOLD_TYPE_INDEX`=0）等于 '2'（`SMALL_FOLD_PRODUCT_TYPE`）判定为小折叠机型。

#### Scenario: 小折叠机型
- **WHEN** `const.window.foldscreen.type` 取值为 "2,..."（首字符 '2'）
- **THEN** `IsSmallFoldDevice` 返回 true，通话生命周期内启用折叠监听

#### Scenario: 非小折叠或未配置
- **WHEN** 参数首字符非 '2' 或参数为空串
- **THEN** `IsSmallFoldDevice` 返回 false，不注册折叠监听
