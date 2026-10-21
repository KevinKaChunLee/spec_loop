# Spec Delta

## MODIFIED Requirements

### Requirement: 号码格式化
系统 SHALL 由 `CallNumberUtils` 格式化号码，libphonenumber（`i18n::phonenumbers::PhoneNumberUtil`）经本 change 打桩（stub/ 同名桩）承接：`FormatPhoneNumber`（前缀为 `#`/`*` 的号码原样返回；`ParseAndKeepRawInput`+`FormatInOriginalFormat`，结果为空或 `0` 时置空）、`FormatPhoneNumberToE164`/`FormatPhoneNumberToNational`/`FormatPhoneNumberToInternational`（经 `FormatNumberBase`，仅 `IsValidNumber` 或 `HasBCPhoneNumber`（11 位且 `192` 开头）时格式化）、`FormatPhoneNumberAsYouType`（`AsYouTypeFormatter::InputDigit` 逐位格式化）；空号码入参 MUST 返回 `TELEPHONY_ERR_ARGUMENT_INVALID`。

#### Scenario: MMI 码原样返回
- **WHEN** 以 `*123#` 调用 `FormatPhoneNumber`（countryCode 任意）
- **THEN** 输出即 `*123#`，返回 `TELEPHONY_SUCCESS`

#### Scenario: 空号码
- **WHEN** 以空字符串调用 `FormatPhoneNumberToE164`
- **THEN** 返回 `TELEPHONY_ERR_ARGUMENT_INVALID`，输出保持不变

#### Scenario: BC 号码放行格式化
- **WHEN** 号码为 `192` 开头的 11 位号码（`HasBCPhoneNumber` 为 true）
- **THEN** `FormatNumberBase` 经桩的 `PhoneNumberUtil::Format` 执行并输出格式化结果

### Requirement: 号码校验与清洗
系统 SHALL 由 `CallNumberUtils::CheckNumberIsEmergency` 判断紧急号码（外部依赖经打桩承接：`CellularCallConnection::IsEmergencyPhoneNumber` 内部经 `CellularCallClient::GetInstance().Xxx()` 打桩转发，libphonenumber/国家码等外部查询经打桩）、`IsCarrierVtConfig` 查询运营商 VT 配置（查询通道经打桩）；`RemoveSeparatorsPhoneNumber` 仅保留数字、`+`、`N`、`,`、`;`、`*`、`#`；`RemovePostDialPhoneNumber` 遇 `,`/`;` 截断；`HasAlphabetInPhoneNum` 判定是否含字母；`IsValidSlotId` 按 `SIM_SLOT_COUNT`（1 或 2 时分别校验 `SIM_SLOT_0`/`SIM_SLOT_1`）校验卡槽号（单卡实现保留 slotId 供双卡扩展）。

#### Scenario: 紧急号码判断
- **WHEN** 以 (phoneNumber, slotId) 调用 `CheckNumberIsEmergency`
- **THEN** `enabled` 由桩的 `IsEmergencyPhoneNumber` 的结果填充

#### Scenario: 去后拨号码
- **WHEN** 以 `10086,123` 调用 `RemovePostDialPhoneNumber`
- **THEN** 输出为 `10086`（`,` 后内容被截断）

#### Scenario: 非法卡槽
- **WHEN** `SIM_SLOT_COUNT` 为 1 且 slotId 不为 `SIM_SLOT_0`
- **THEN** `IsValidSlotId` 返回 false

### Requirement: 卡状态查询与帐号选择
系统 SHALL 由 `CallNumberUtils::SelectAccountId` 在入参 slotId 无效时依次尝试 `CoreServiceClient::GetInstance().GetDefaultVoiceSlotId()`（stub/ 打桩）、（`CELLULAR_DATA_SUPPORT` 下）`CellularDataClient::GetInstance().GetDefaultCellularDataSlotId()`（stub/ 打桩），将首个有效值经 `extras.PutIntValue("accountId")` 写回（PacMap 以结构体替换，写回语义保留）；帐号维度精简为单主帐号（os_account 多帐号枚举逻辑不迁移，`IsBundleInstalled` 的 userId 固定为主帐号值）；由 `CallManagerUtils::IsBundleInstalled` 判定应用安装状态，BundleMgr 查询经打桩承接（基线经 `BUNDLE_MGR_SERVICE_SYS_ABILITY_ID` 查询 `AppExecFwk::IBundleMgr::IsBundleInstalled` 的语义由桩保留）。

#### Scenario: 默认语音卡兜底
- **WHEN** slotId 无效且桩的 `GetDefaultVoiceSlotId` 返回有效卡槽
- **THEN** extras 中 `accountId` 被置为默认语音卡槽，返回 true

#### Scenario: 全部兜底失败
- **WHEN** slotId 与两个默认卡槽（桩返回值）均无效
- **THEN** `SelectAccountId` 返回 false，extras 不写入 `accountId`

#### Scenario: 查询应用安装状态
- **WHEN** 以 (bundleName, userId) 调用 `IsBundleInstalled` 且桩返回已安装
- **THEN** 返回 true

### Requirement: 设置库读写
系统 SHALL 由 `SettingsDataShareHelper` 保留设置项读写的判定逻辑，DataShare 读写调用点以 todo 占位（`// todo!!! [database] ref to settings_datashare_helper.cpp Query`、Insert、Update、RegisterToDataShare、UnRegisterToDataShare 各函数对应占位）：`Query` 按 key 查询 VALUE（无结果返回 `TELEPHONY_ERR_UNINIT`）、`Insert` 写入并 `NotifyChange`、`Update` 在旧值不存在时转 `Insert`、`RegisterToDataShare`/`UnRegisterToDataShare` 注册与注销 observer；预置 key 集合按裁剪结果收敛（卫星模式与运动识别相关 key 随特性移除）。

#### Scenario: 查询存在项
- **WHEN** 以 key 调用 `Query` 且（占位后端/桩侧）存在该 KEYWORD 行
- **THEN** DataShare 调用点为 `// todo!!! [database] ref to settings_datashare_helper.cpp Query` 占位，value 为该行 VALUE 列值，返回 `TELEPHONY_SUCCESS`

#### Scenario: 查询不存在项
- **WHEN** 按 key 查询且（占位后端/桩侧）无该 KEYWORD 行
- **THEN** 返回 `TELEPHONY_ERR_UNINIT`

#### Scenario: 更新不存在项
- **WHEN** `Update` 时 `Query` 失败
- **THEN** 转为 `Insert` 写入该 key/value

### Requirement: 紧急号码对话框
系统 SHALL 由 `CallDialog::DialogConnectExtension(dialogReason, slotId)` 构建 JSON 命令（`ability.want.params.uiExtensionType`=`sysDialog/common`、`sysDialogZOrder`、`dialogReason`、`slotId`），对话框/AlertDialog 拉起经本 change 打桩的外部 UI 依赖桩连接 `com.ohos.sceneboard.systemdialog` 扩展；卫星对话框分支随卫星通话移除（`CallSettingAbilityConnection` 不迁移），统一经外部 UI 依赖桩（对应基线 `CallAbilityConnection` 路径）转发；`CallAbilityConnection::OnAbilityConnectDone` MUST 以 `ON_ABILITY_CONNECT_DONE` 请求把 `com.ohos.callui.CallFailedDialogAbility` 与命令串转发给远端（经桩承接）。

#### Scenario: 普通紧急对话框
- **WHEN** 以不含 `SATELLITE` 的 dialogReason 调用 `DialogConnectExtension`
- **THEN** 经外部 UI 依赖桩连接 systemdialog 并转发命令串

#### Scenario: 卫星对话框
- **WHEN** dialogReason 含 `SATELLITE`（触发卫星紧急对话框条件）
- **THEN** 卫星对话框链路（`CallSettingAbilityConnection`）不迁移、该分支不连接转发；仅普通紧急对话框（经外部 UI 依赖桩）可用

## REMOVED Requirements

### Requirement: EDM 企业禁拨
**Reason**: EDM 企业禁拨特性不支持，`edm_call_policy.cpp` 不迁移。
**Migration**: 无。

### Requirement: 运动识别与闪灯提醒
**Reason**: `OHOS_SUBSCRIBE_MOTION_ENABLE` 为不支持宏，来电闪光、贴耳灭屏、运动识别（翻转静音/拿起减弱铃声）均不支持，`motion_recognition.cpp`、`incoming_flash_reminder.cpp`、`screen_sensor_plugin.cpp` 不迁移。
**Migration**: 无。
