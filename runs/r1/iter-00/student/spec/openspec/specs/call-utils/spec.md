# 公共工具（Call Utils） Specification

## Purpose
描述通话管理公共工具能力的基线行为：号码格式化/紧急号码判断/号码清洗、卡状态查询与帐号选择、通话属性序列化、设置库读写、EDM 企业禁拨、紧急号码对话框、运动识别传感器与来电闪灯提醒。源码落点：`telephony_call_manager/utils/{include,src}`（`call_manager_utils.cpp`、`call_number_utils.cpp`、`call_dialog.cpp`、`incoming_flash_reminder.cpp`、`motion_recognition.cpp`、`screen_sensor_plugin.cpp`、`settings_datashare_helper.cpp`、`edm_call_policy.cpp`、`call_ability_connection.cpp`、`call_setting_ability_connection.cpp`；`number_identity_data_base_helper.cpp` 划入 number-identity-proxy 规格，此处不覆盖）。相关编译开关来自 `callmanager.gni` 的 `call_manager_defines`：`OHOS_SUBSCRIBE_MOTION_ENABLE`（msdp_motion 部件）、`ABILITY_SCREENLOCKMGR_SUPPORT`（theme_screenlock_mgr 部件）、`CELLULAR_DATA_SUPPORT`（telephony_cellular_data 部件）；`ABILITY_CAMERA_FRAMEWORK_SUPPORT` 在源码中 `#ifdef` 引用、本仓 GN 仅在 multimedia_camera_framework 部件存在时追加 camera_framework 依赖而不显式定义该宏。

## Requirements

### Requirement: 号码格式化
系统 SHALL 由 `CallNumberUtils` 基于 libphonenumber（`i18n::phonenumbers::PhoneNumberUtil`）格式化号码：`FormatPhoneNumber`（前缀为 `#`/`*` 的号码原样返回；`ParseAndKeepRawInput`+`FormatInOriginalFormat`，结果为空或 `0` 时置空）、`FormatPhoneNumberToE164`/`FormatPhoneNumberToNational`/`FormatPhoneNumberToInternational`（经 `FormatNumberBase`，仅 `IsValidNumber` 或 `HasBCPhoneNumber`（11 位且 `192` 开头）时格式化）、`FormatPhoneNumberAsYouType`（`AsYouTypeFormatter::InputDigit` 逐位格式化）；空号码入参 MUST 返回 `TELEPHONY_ERR_ARGUMENT_INVALID`。
#### Scenario: MMI 码原样返回
- **WHEN** 以 `*123#` 调用 `FormatPhoneNumber`（countryCode 任意）
- **THEN** 输出即 `*123#`，返回 `TELEPHONY_SUCCESS`
#### Scenario: 空号码
- **WHEN** 以空字符串调用 `FormatPhoneNumberToE164`
- **THEN** 返回 `TELEPHONY_ERR_ARGUMENT_INVALID`，输出保持不变
#### Scenario: BC 号码放行格式化
- **WHEN** 号码为 `192` 开头的 11 位号码（`HasBCPhoneNumber` 为 true）
- **THEN** `FormatNumberBase` 执行 `PhoneNumberUtil::Format` 并输出格式化结果

### Requirement: 号码校验与清洗
系统 SHALL 由 `CallNumberUtils::CheckNumberIsEmergency` 经 `CellularCallConnection::IsEmergencyPhoneNumber(phoneNumber, slotId, enabled)` 判断紧急号码、`IsCarrierVtConfig` 查询运营商 VT 配置；`RemoveSeparatorsPhoneNumber` 仅保留数字、`+`、`N`、`,`、`;`、`*`、`#`；`RemovePostDialPhoneNumber` 遇 `,`/`;` 截断；`HasAlphabetInPhoneNum` 判定是否含字母；`IsValidSlotId` 按 `SIM_SLOT_COUNT`（1 或 2 时分别校验 `SIM_SLOT_0`/`SIM_SLOT_1`）校验卡槽号。
#### Scenario: 紧急号码判断
- **WHEN** 以 (phoneNumber, slotId) 调用 `CheckNumberIsEmergency`
- **THEN** `enabled` 由 `IsEmergencyPhoneNumber` 的结果填充
#### Scenario: 去后拨号码
- **WHEN** 以 `10086,123` 调用 `RemovePostDialPhoneNumber`
- **THEN** 输出为 `10086`（`,` 后内容被截断）
#### Scenario: 非法卡槽
- **WHEN** `SIM_SLOT_COUNT` 为 1 且 slotId 不为 `SIM_SLOT_0`
- **THEN** `IsValidSlotId` 返回 false

### Requirement: 卡状态查询与帐号选择
系统 SHALL 由 `CallNumberUtils::SelectAccountId` 在入参 slotId 无效时依次尝试 `CoreServiceClient::GetDefaultVoiceSlotId`、（`CELLULAR_DATA_SUPPORT` 下）`CellularDataClient::GetDefaultCellularDataSlotId`，将首个有效值经 `extras.PutIntValue("accountId")` 写回；由 `CallManagerUtils::IsBundleInstalled` 经 `BUNDLE_MGR_SERVICE_SYS_ABILITY_ID` 查询 `IBundleMgr::IsBundleInstalled` 判定应用安装状态。
#### Scenario: 默认语音卡兜底
- **WHEN** slotId 无效且 `GetDefaultVoiceSlotId` 返回有效卡槽
- **THEN** extras 中 `accountId` 被置为默认语音卡槽，返回 true
#### Scenario: 全部兜底失败
- **WHEN** slotId 与两个默认卡槽均无效
- **THEN** `SelectAccountId` 返回 false，extras 不写入 `accountId`
#### Scenario: 查询应用安装状态
- **WHEN** 以 (bundleName, userId) 调用 `IsBundleInstalled` 且 BundleMgr 返回已安装
- **THEN** 返回 true

### Requirement: 通话属性序列化
系统 SHALL 由 `CallManagerUtils::WriteCallAttributeInfo` 将 `CallAttributeInfo` 序列化到 MessageParcel（依次 accountNumber/bundleName/speakerphoneOn/accountId/videoState/startTime/isEcc/callType/callId/callState/conferenceState/各时间戳/callDirection/answerType/index/crsType/originalCallType/numberLocation/numberMarkInfo 各字段/contactName/extraParamsString，`CallType::TYPE_VOIP` 时附加 `voipCallInfo` 各字段，尾部 `phoneOrWatch`）；来电状态下 `IsForcedReportVoiceCall` 为 true 时 videoState MUST 以 `VideoStateType::TYPE_VOICE` 写出。
#### Scenario: 强制语音上报
- **WHEN** 通话为 INCOMING 且 `call->IsForcedReportVoiceCall()` 为 true
- **THEN** 序列化的 videoState 为 `TYPE_VOICE` 而非原始 videoState
#### Scenario: VOIP 附加字段
- **WHEN** `info.callType` 为 `TYPE_VOIP`
- **THEN** 额外序列化 `voipCallId`/`userName`/`abilityName` 等 voipCallInfo 字段

### Requirement: 设置库读写
系统 SHALL 由 `SettingsDataShareHelper`（URI `datashare:///com.ohos.settingsdata/entry/settingsdata/SETTINGSDATA?Proxy=true`，列 `KEYWORD`/`VALUE`）读写设置项：`Query` 按 key 查询 VALUE（无结果返回 `TELEPHONY_ERR_UNINIT`）、`Insert` 写入并 `NotifyChange`、`Update` 在旧值不存在时转 `Insert`、`RegisterToDataShare`/`UnRegisterToDataShare` 注册与注销 `IDataAbilityObserver`；预置 key 包括 `QUERY_SATELLITE_MODE_KEY`、`QUERY_MOTION_FLIP_MUTE_KEY`、`QUERY_MOTION_CLOSE_TO_EAR_KEY`、`QUERY_MOTION_PICKUP_REDUCE_KEY` 等。
#### Scenario: 查询存在项
- **WHEN** 以 key `motion_flip_mute_call` 调用 `Query` 且库中存在该行
- **THEN** value 为该行 VALUE 列值，返回 `TELEPHONY_SUCCESS`
#### Scenario: 查询不存在项
- **WHEN** 库中无该 KEYWORD 行
- **THEN** 返回 `TELEPHONY_ERR_UNINIT`
#### Scenario: 更新不存在项
- **WHEN** `Update` 时 `Query` 失败
- **THEN** 转为 `Insert` 写入该 key/value

### Requirement: EDM 企业禁拨
系统 SHALL 由 `EdmCallPolicy::SetCallPolicy` 分别设置拨号/来电名单（trust 或 block 语义、各自上限 `MAX_COUNT` 1000 条，超限返回 `TELEPHONY_ERR_ARGUMENT_INVALID`），由 `IsDialingEnable`/`IsIncomingEnable` 判定号码可拨/可接：系统参数 `persist.edm.telephony_call_disable` 为 true 时 MUST NOT 允许；黑名单语义下名单为空允许全部、命中名单拒绝；白名单语义下名单为空允许全部、未命中名单拒绝。
#### Scenario: 企业禁拨总开关
- **WHEN** `persist.edm.telephony_call_disable` 为 true
- **THEN** `IsDialingEnable` 与 `IsIncomingEnable` 均返回 false
#### Scenario: 黑名单命中
- **WHEN** 拨号策略为黑名单（isDialingTrustlist=false）且号码在名单中
- **THEN** `IsDialingEnable` 返回 false
#### Scenario: 名单超限
- **WHEN** `SetCallPolicy` 收到超过 1000 条的名单
- **THEN** 返回 `TELEPHONY_ERR_ARGUMENT_INVALID`，原名单保持不变

### Requirement: 紧急号码对话框
系统 SHALL 由 `CallDialog::DialogConnectExtension(dialogReason, slotId)` 构建 JSON 命令（`ability.want.params.uiExtensionType`=`sysDialog/common`、`sysDialogZOrder`、`dialogReason`、`slotId`）并连接 `com.ohos.sceneboard.systemdialog` 扩展：dialogReason 含 `SATELLITE` 时经 `CallSettingAbilityConnection`、否则经 `CallAbilityConnection`；`CallAbilityConnection::OnAbilityConnectDone` MUST 以 `ON_ABILITY_CONNECT_DONE` 请求把 `com.ohos.callui.CallFailedDialogAbility` 与命令串转发给远端。
#### Scenario: 普通紧急对话框
- **WHEN** 以不含 `SATELLITE` 的 dialogReason 调用 `DialogConnectExtension`
- **THEN** 经 `CallAbilityConnection` 连接 systemdialog 并转发命令串
#### Scenario: 卫星对话框
- **WHEN** dialogReason 含 `SATELLITE`
- **THEN** 改经 `CallSettingAbilityConnection` 连接转发

### Requirement: 运动识别与闪灯提醒
系统 SHALL 由 `MotionRecogntion`（`OHOS_SUBSCRIBE_MOTION_ENABLE` 下）经 `screen_sensor_plugin.cpp`（`dlopen` `libmotion_agent.z.so`（`PLUGIN_SO_PATH`，重试 3 次）后 `dlsym` `MotionSubscribeCallback`/`MotionUnsubscribeCallback`）订阅运动事件并联动通话控制：翻转（`MOTION_TYPE_FLIP`，状态 `FLIP_UP`）静音响铃通话并停止闪灯、拿起（`MOTION_TYPE_PICKUP`，状态 0）停止闪灯并 `ReduceRingToneVolume` 渐弱铃声、贴耳（`MOTION_TYPE_CLOSE_TO_EAR`，状态 0）响铃中接听或通话中切听筒（`SetAudioDevice` 置 `DEVICE_EARPIECE`）；来电时 `CallControlManager::StartFlashRemind` 在闪灯开关（设置值含 `INCOMING_CALL`）、锁屏（`ABILITY_SCREENLOCKMGR_SUPPORT`）且手电筒可用（`ABILITY_CAMERA_FRAMEWORK_SUPPORT`）时经 `IncomingFlashReminder` 周期翻转 `SetTorchMode` 闪烁提醒。
#### Scenario: 翻转静音
- **WHEN** 收到 `MOTION_TYPE_FLIP` 且状态为 `FLIP_UP` 且存在响铃通话
- **THEN** 调用 `MuteRinger` 并 `StopFlashRemind`
#### Scenario: 拿起减弱铃声
- **WHEN** 收到状态为 0 的 `MOTION_TYPE_PICKUP`
- **THEN** 注销拿起订阅、`StopFlashRemind` 并按 `REDUCE_RING_TOTAL_LENGTH` 渐弱铃声音量
#### Scenario: 贴耳接听
- **WHEN** 收到状态为 0 的 `MOTION_TYPE_CLOSE_TO_EAR` 且仅有响铃通话
- **THEN** 以 `VideoStateType::TYPE_VOICE` 接听该通话
#### Scenario: 来电闪灯
- **WHEN** 来电时闪灯开关开启、屏幕已锁且手电筒支持且未开启
- **THEN** `IncomingFlashReminder` 启动手电筒周期闪烁（每 `DELAY_SET_TORCH_MODE_TIME` 300ms 翻转一次 `TorchMode`）
