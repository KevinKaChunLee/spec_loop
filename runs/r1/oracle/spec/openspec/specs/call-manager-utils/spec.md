# 工具库（call-manager-utils）Specification

## Purpose
描述 `telephony_call_manager/utils/` 的工具库：`CallManagerUtils`（属性序列化）、`CallNumberUtils`（号码处理与归属地/黄页，`DelayedSingleton`）、`CallDialog`（系统对话框连接）、`CallAbilityConnection`/`CallSettingAbilityConnection`（对话框扩展连接）、`EdmCallPolicy`（企业禁拨/禁入名单）、`IncomingFlashReminder`（来电闪光）、`MotionRecogntion`（动作识别，类名原文缺 i）、`screen_sensor_plugin`（动作传感器 dlopen）、`SettingsDataShareHelper`/`NumberIdentityDataBaseHelper`（DataShare 封装）、`timer.h`（`Timer`）。编译开关：`CELLULAR_DATA_SUPPORT`（`call_number_utils.cpp` 的默认数据卡查询）、`OHOS_SUBSCRIBE_MOTION_ENABLE`（`motion_recognition` 整体）、`ABILITY_CAMERA_FRAMEWORK_SUPPORT`/`ABILITY_SCREENLOCKMGR_SUPPORT`（`incoming_flash_reminder` 的手电筒与锁屏条件）。

## Requirements

### Requirement: 通话属性序列化对称
系统 SHALL 由 `CallManagerUtils::WriteCallAttributeInfo(info, messageParcel)` 逐字段序列化 `CallAttributeInfo`（`TYPE_VOIP` 时附加 voipCallInfo 全字段 + userProfile，末尾 `phoneOrWatch`；来电状态下经 `IsForcedReportVoiceCall` 强制 videoState 为 `TYPE_VOICE`），由 `NativeCallManagerUtils::ReadCallAttributeInfo` 以完全对称的顺序反序列化；`CallManagerUtils::IsBundleInstalled(bundleName, userId)` 经 samgr `GetSystemAbility(BUNDLE_MGR_SERVICE_SYS_ABILITY_ID)`→`iface_cast<AppExecFwk::IBundleMgr>` 查询。
#### Scenario: IPC 序列化回读一致
- **WHEN** 服务端以 `WriteCallAttributeInfo` 写出 VoIP 通话属性
- **THEN** 客户端 `ReadCallAttributeInfo` 按相同字段序与 VOIP 附加字段回读一致

### Requirement: 号码格式化与紧急号码
系统 SHALL 由 `CallNumberUtils` 提供 `FormatPhoneNumber`（'#'/'*' 开头原样返回，否则 `ParseAndKeepRawInput`+`FormatInOriginalFormat`）、`FormatPhoneNumberToE164/National/International`（委托 `FormatNumberBase`）、`FormatPhoneNumberAsYouType`（逐字符 `InputDigit`）、`CheckNumberIsEmergency`（转发 `CellularCallConnection::IsEmergencyPhoneNumber`）、`RemoveSeparatorsPhoneNumber`、`RemovePostDialPhoneNumber`、`HasBCPhoneNumber`（11 位 "192" 前缀）、`IsValidSlotId`（按 `SIM_SLOT_COUNT` 与在位卡数校验）。
#### Scenario: 特殊号码不格式化
- **WHEN** 号码以 '*' 或 '#' 开头（MMI 码形态）
- **THEN** `FormatPhoneNumber` 原样返回不做 libphonenumber 解析

### Requirement: 默认卡选择与归属地/黄页更新
系统 SHALL 由 `CallNumberUtils::SelectAccountId` 在 accountId 无效时依次尝试 `CoreServiceClient::GetDefaultVoiceSlotId` 与（`CELLULAR_DATA_SUPPORT` 下）`CellularDataClient::GetDefaultCellularDataSlotId` 并以 `PutIntValue("accountId", ...)` 回写 extras；`NumberLocationUpdate`（DIALING 态重新取 `CallObjectManager::GetOneCallObject`，location 非空非 "default" 才 `ReportCallStateInfo`）；`YellowPageAndMarkUpdate`（`GetParameter("const.global.region", "CN")` 非 "CN" 直接返回；markType > `MARK_TYPE_NONE` 或 isEcc 才上报）；`QueryNumberLocationInfo`/`QueryYellowPageAndMarkInfo` 经 `NumberIdentityDataBaseHelper`（`NUMBER_IDENTITY_URI = "datashare:///numberlocationability"`、`NUMBER_MARK_INFO_URI = "datashare:///numbermarkability/number_mark_info"`，`SetMarkInfoValues` 读 markType/markContent/markCount/markSource/isCloud/markDetails），失败返回 `TELEPHONY_ERR_DATABASE_READ_FAIL`。
#### Scenario: 非中国区跳过黄页
- **WHEN** `const.global.region` 非 "CN"
- **THEN** `YellowPageAndMarkUpdate` 不查询黄页/标记库直接返回

### Requirement: 系统对话框连接
系统 SHALL 由 `CallDialog::DialogConnectExtension(dialogReason[, slotId])`：reason 含 "SATELLITE" 走 `CallSettingAbilityConnection`（`com.callsetting`/`com.callsetting.SatelliteCallDialogAbility`），否则走 `CallAbilityConnection`（`com.ohos.callui`/`com.ohos.callui.CallFailedDialogAbility`）；两者均连接 `com.ohos.sceneboard`/`com.ohos.sceneboard.systemdialog`，命令以 `nlohmann::json` 组 `uiExtensionType = "sysDialog/common"`、`sysDialogZOrder`、dialogReason；另有 `DialogConnectPrivpacyModeExtension`、`DialogConnectAnswerPrivpacyModeExtension`、`DialogCallingPrivacyModeExtension`（仅 `Rosen::FoldStatus::FOLDED` 且超级隐私且前台非 INCOMING）、`DialogProcessMMICodeExtension`（reason "PROCESS_MMI_CODE"）。
#### Scenario: 拨号失败弹对话框
- **WHEN** `DialogConnectExtension("CALL_FAILED_...")` 触发
- **THEN** 经 sceneboard 系统对话框以 JSON 命令弹出对应提示

### Requirement: EDM 企业策略名单
系统 SHALL 由 `EdmCallPolicy`（`EdmPolicyFlag`：`POLICY_FLAG_NONE = -1`/`BLOCK = 0`/`TRUST = 1`，名单上限 `MAX_COUNT = 1000`，`ffrt::shared_mutex` 保护）以 `SetCallPolicy` 接收策略；`IsDialingEnable`/`IsIncomingEnable`→`IsCallEnable`：系统参数 `persist.edm.telephony_call_disable` 为 true 全禁；NONE 放行；BLOCK/TRUST 名单为空放行，否则按命中判断。
#### Scenario: EDM 全局禁拨
- **WHEN** `persist.edm.telephony_call_disable` 为 true
- **THEN** `IsDialingEnable` 拒绝全部拨号

### Requirement: 来电闪光
系统 SHALL 由 `IncomingFlashReminder : AppExecFwk::EventHandler`（事件 `DELAY_SET_TORCH_EVENT = 1000000`/`STOP_FLASH_REMIND_EVENT = 1000001`/`START_FLASH_REMIND_EVENT = 1000002`）以 `IsFlashRemindNecessary`（开关含 "INCOMING_CALL"、`IsScreenStatusSatisfied`（`ABILITY_SCREENLOCKMGR_SUPPORT` 下锁屏）、`IsTorchReady`（`ABILITY_CAMERA_FRAMEWORK_SUPPORT` 下手电筒可用未占用））判定后 `HandleSetTorchMode` 以 300 毫秒间隔翻转手电筒。
#### Scenario: 宏缺失时不闪光
- **WHEN** `ABILITY_CAMERA_FRAMEWORK_SUPPORT` 或 `ABILITY_SCREENLOCKMGR_SUPPORT` 未定义
- **THEN** `IsFlashRemindNecessary` 恒为假，来电闪光不触发

### Requirement: 动作识别
系统 SHALL 由 `MotionRecogntion`（整体 `OHOS_SUBSCRIBE_MOTION_ENABLE` 宏内）提供 `SubscribePickupSensor/SubscribeFlipSensor/SubscribeCloseToEarSensor` 与反向退订（`MOTION_TYPE_PICKUP = 100`/`FLIP = 200`/`CLOSE_TO_EAR = 300`，三个 Subscriber 类静态标志防重）：`FlipMotionEventCallback`（FLIP_UP 且有振铃通话→`CallControlManager::MuteRinger`）、PICKUP status == 0（退订 + `StopFlashRemind` + `ffrt::submit` `ReduceRingToneVolume`，总时长 `REDUCE_RING_TOTAL_LENGTH = 1500000` 微秒逐级降铃）、`CloseToEarMotionEventCallback`（仅振铃时 `AnswerCall`；通话中从 `DEVICE_SPEAKER/DEVICE_BLUETOOTH_SCO/DEVICE_NEARLINK` 切 `DEVICE_EARPIECE`）；传感器库由 `screen_sensor_plugin`（`PLUGIN_SO_PATH = "/system/lib64/platformsdk/libmotion_agent.z.so"`）`LoadMotionSensor`（dlopen 重试 3 次，间隔 10 毫秒）+ dlsym `MotionSubscribeCallback/MotionUnsubscribeCallback`（`no_sanitize("cfi")`）加载。
#### Scenario: 翻转静音
- **WHEN** 振铃中设备收到 FLIP_UP 动作事件
- **THEN** 执行 `CallControlManager::MuteRinger` 静音铃响

### Requirement: 设置项 DataShare 封装
系统 SHALL 由 `SettingsDataShareHelper`（`DelayedSingleton`，`SETTINGS_DATASHARE_URI = "datashare:///com.ohos.settingsdata/entry/settingsdata/SETTINGSDATA?Proxy=true"`，列 KEYWORD/VALUE）提供 `Query/Insert/Update`（Update 先 Query 不存在转 Insert 并 `NotifyChange`）与 `RegisterToDataShare/UnRegisterToDataShare`；key 常量 `QUERY_SATELLITE_MODE_KEY = "satellite_mode_switch"`、`QUERY_SATELLITE_CONNECTED_KEY = "satellite_connected"`、`QUERY_MOTION_FLIP_MUTE_KEY = "motion_flip_mute_call"`、`QUERY_MOTION_CLOSE_TO_EAR_KEY = "motion_quick_answer"`、`QUERY_MOTION_PICKUP_REDUCE_KEY = "motion_pickup_reduce_call"`。
#### Scenario: 查询卫星开关
- **WHEN** `SatelliteCallControl::IsSatelliteSwitchEnable` 查询卫星模式
- **THEN** 经 `SettingsDataShareHelper::Query(QUERY_SATELLITE_MODE_KEY)` 读 VALUE 列比对 `SATELLITE_MODE_ON`
