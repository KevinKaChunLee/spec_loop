# Spec Delta

## MODIFIED Requirements

### Requirement: 通话属性序列化对称
系统 SHALL 由 `CallManagerUtils::WriteCallAttributeInfo(info, messageParcel)` 逐字段序列化 `CallAttributeInfo`（`TYPE_VOIP` 时附加 voipCallInfo 全字段 + userProfile，末尾 `phoneOrWatch`；来电状态下经 `IsForcedReportVoiceCall` 强制 videoState 为 `TYPE_VOICE`），由 `NativeCallManagerUtils::ReadCallAttributeInfo` 以完全对称的顺序反序列化——序列化函数保留（不再承载 IPC，供结构与测试对拍）；`CallManagerUtils::IsBundleInstalled(bundleName, userId)` 改经 bundleManager 桩查询（逻辑保留）。
#### Scenario: IPC 序列化回读一致
- **WHEN** 以 `WriteCallAttributeInfo` 写出 VoIP 通话属性后经 `ReadCallAttributeInfo` 回读
- **THEN** 按相同字段序与 VOIP 附加字段回读一致（序列化保留供结构与测试对拍，不再承载 IPC）

### Requirement: 号码格式化与紧急号码
系统 SHALL 由 `CallNumberUtils` 提供 `FormatPhoneNumber`（'#'/'*' 开头原样返回，否则 `ParseAndKeepRawInput`+`FormatInOriginalFormat`）、`FormatPhoneNumberToE164/National/International`（委托 `FormatNumberBase`）、`FormatPhoneNumberAsYouType`（逐字符 `InputDigit`）——libphonenumber 解析经桩（接口形态同名）；`CheckNumberIsEmergency`（转发 `CellularCallConnection::IsEmergencyPhoneNumber`，经 `CellularCallClient` 桩）、`RemoveSeparatorsPhoneNumber`、`RemovePostDialPhoneNumber`、`HasBCPhoneNumber`（11 位 "192" 前缀）、`IsValidSlotId`（按 `SIM_SLOT_COUNT` 与在位卡数校验，桩配置单卡在位）保留。
#### Scenario: 特殊号码不格式化
- **WHEN** 号码以 '*' 或 '#' 开头（MMI 码形态）
- **THEN** `FormatPhoneNumber` 原样返回不做 libphonenumber 解析

### Requirement: 默认卡选择与归属地/黄页更新
系统 SHALL 由 `CallNumberUtils::SelectAccountId` 在 accountId 无效时依次尝试 `CoreServiceClient::GetInstance().GetDefaultVoiceSlotId`（桩）与 `CellularDataClient::GetInstance().GetDefaultCellularDataSlotId`（桩，`CELLULAR_DATA_SUPPORT` 支持宏）并以 `PutIntValue("accountId", ...)` 回写 extras；`NumberLocationUpdate`（DIALING 态重新取 `CallObjectManager::GetOneCallObject`，location 非空非 "default" 才 `ReportCallStateInfo`）与 `YellowPageAndMarkUpdate`（`GetParameter("const.global.region", "CN")` 经系统参数桩，非 "CN" 直接返回；markType > `MARK_TYPE_NONE` 或 isEcc 才上报）逻辑保留；`QueryNumberLocationInfo`/`QueryYellowPageAndMarkInfo` 的 DataShare 查询调用点以 `// todo!!! [database]` 占位（返回默认未命中，原 `TELEPHONY_ERR_DATABASE_READ_FAIL` 失败路径保留）。
#### Scenario: 非中国区跳过黄页
- **WHEN** 桩参数表配置 `const.global.region` 非 "CN"
- **THEN** `YellowPageAndMarkUpdate` 不查询黄页/标记库直接返回

#### Scenario: 归属地查询占位
- **WHEN** DIALING 态触发 `NumberLocationUpdate` 需查询归属地
- **THEN** DataShare 查询调用点为 todo 占位，location 取默认值，状态上报逻辑照常判定

### Requirement: 系统对话框连接
系统 SHALL 由 `CallDialog` 系列调用点保留：`DialogConnectExtension(dialogReason[, slotId])`、`DialogConnectPrivpacyModeExtension`、`DialogConnectAnswerPrivpacyModeExtension`、`DialogCallingPrivacyModeExtension`、`DialogProcessMMICodeExtension`（reason "PROCESS_MMI_CODE"）——连接实现经 `stub/` 桩空执行（`com.ohos.sceneboard`/`com.ohos.sceneboard.systemdialog` 系统对话框不真正弹出，返回成功）；卫星对话框（`CallSettingAbilityConnection`/`com.callsetting`）与超级隐私弹窗的触发场景随上游能力移除。
#### Scenario: 拨号失败弹对话框
- **WHEN** `DialogConnectExtension("CALL_FAILED_...")` 触发
- **THEN** 连接经桩空执行返回成功，业务流程不受阻，不真正弹出系统对话框

### Requirement: 设置项 DataShare 封装
系统 SHALL 由 `SettingsDataShareHelper`（`DelayedSingleton`）保留 `SETTINGS_DATASHARE_URI` 与列 KEYWORD/VALUE 定义及 `Query/Insert/Update`（Update 先 Query 不存在转 Insert 并 `NotifyChange`）与 `RegisterToDataShare/UnRegisterToDataShare` 骨架；DataShare 操作调用点以 `// todo!!! [database]` 占位（返回默认值）；key 常量保留，`QUERY_SATELLITE_MODE_KEY = "satellite_mode_switch"`/`QUERY_SATELLITE_CONNECTED_KEY = "satellite_connected"` 的调用方随卫星通话移除。
#### Scenario: 查询卫星开关
- **WHEN** 保留代码经 `SettingsDataShareHelper::Query(key)` 查询设置项（`QUERY_SATELLITE_MODE_KEY` 等卫星 key 的调用方已随卫星通话移除）
- **THEN** DataShare 查询调用点为 `// todo!!! [database]` 占位并返回默认值，调用方按默认分支处理

## REMOVED Requirements

### Requirement: EDM 企业策略名单
**Reason**: AGENTS.md 功能范围：EDM 企业禁拨不支持。
**Migration**: `EdmCallPolicy`（`EdmPolicyFlag`/`MAX_COUNT = 1000`）不迁移；`persist.edm.telephony_call_disable` 参数与 `IsDialingEnable`/`IsIncomingEnable` 判定调用点移除。

### Requirement: 来电闪光
**Reason**: AGENTS.md 功能范围：来电闪光（incoming flash）不支持（`ABILITY_CAMERA_FRAMEWORK_SUPPORT`/`ABILITY_SCREENLOCKMGR_SUPPORT` 为不支持宏）。
**Migration**: `IncomingFlashReminder` 不迁移；`CallControlManager::StartFlashRemind()` 调用点移除。

### Requirement: 动作识别
**Reason**: AGENTS.md 功能范围：动作识别（`OHOS_SUBSCRIBE_MOTION_ENABLE` 为不支持宏）不迁移。
**Migration**: `MotionRecogntion` 与 `screen_sensor_plugin`（`PLUGIN_SO_PATH` dlopen 加载）不迁移；`StartInComingCallMotionRecognition` 与 FLIP/PICKUP/CLOSE_TO_EAR 联动调用点移除。
