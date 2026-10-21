# call-utils Specification

## Purpose
描述 `telephony_call_manager/utils/` 下的公共实用层在 OpenHarmony v6.0 快照中的现状：号码格式化与号码识别链（`call_number_utils.cpp` + `number_identity_data_base_helper.cpp`，依赖三方库 libphonenumber 与 DataShare）、MessageParcel 序列化助手（`call_manager_utils.cpp`）、设置项 DataShare 读写（`settings_datashare_helper.cpp`）、系统对话框拉起与 Ability 连接回调（`call_dialog.cpp`、`call_ability_connection.cpp`、`call_setting_ability_connection.cpp`）、企业禁拨策略（`edm_call_policy.cpp`）、来电闪光提醒（`incoming_flash_reminder.cpp`）、运动识别（`motion_recognition.cpp` + `screen_sensor_plugin.cpp`）。本能力为移植前基线，不涉及裁剪决策。本能力声明以下编译宏（均需在移植时裁决）：`CELLULAR_DATA_SUPPORT`（场点：`utils/src/call_number_utils.cpp` 中 `SelectAccountId` 的 `#ifdef`，由 `callmanager.gni` 的 `telephony_cellular_data` 部件开启）、`OHOS_SUBSCRIBE_MOTION_ENABLE`（场点：`utils/src/motion_recognition.cpp` 与 `utils/include/motion_recognition.h` 的多处 `#ifdef`，由 `callmanager.gni` 的 `msdp_motion` 部件开启）、`ABILITY_CAMERA_FRAMEWORK_SUPPORT` 与 `ABILITY_SCREENLOCKMGR_SUPPORT`（场点：`utils/src/incoming_flash_reminder.cpp` 的 `#ifdef`，后者由 `callmanager.gni` 的 `theme_screenlock_mgr` 部件开启，前者在本仓 gni 中仅添加 `camera_framework` 依赖、无同名 define 块）。`utils/include/timer.h` 为头文件，不在本能力展开。

## Requirements

### Requirement: 号码格式化链
系统 SHALL 由 `CallNumberUtils`（`DECLARE_DELAYED_SINGLETON` 声明，`utils/src/call_number_utils.cpp`）基于 libphonenumber（`i18n::phonenumbers::PhoneNumberUtil`）提供 4 种格式化出口：`FormatPhoneNumber`（`ParseAndKeepRawInput` + `FormatInOriginalFormat`）、`FormatPhoneNumberToE164` / `FormatPhoneNumberToNational` / `FormatPhoneNumberToInternational`（统一经 `FormatNumberBase` 以 `Parse` + `IsValidNumber`（或 `HasBCPhoneNumber` 放行）后按 `PhoneNumberUtil::E164` / `NATIONAL` / `INTERNATIONAL` 格式化）、以及 `FormatPhoneNumberAsYouType`（`AsYouTypeFormatter::InputDigit` 逐字符输入）。National/International 输出经私有函数 `ProcessSpace` 去除全部空白字符。

#### Scenario: # 或 * 前缀直通
- **WHEN** `FormatPhoneNumber` / `FormatPhoneNumberAsYouType` 收到以 '#' 或 '*' 开头的号码（如 MMI/USSD 补充业务码）
- **THEN** 不走 libphonenumber，直接原样返回该字符串并返回 `TELEPHONY_SUCCESS`

#### Scenario: 空号码或解析失败
- **WHEN** 入参号码为空、或 `PhoneNumberUtil` 单例为空、或格式化结果为空串或 "0"
- **THEN** 分别返回 `TELEPHONY_ERR_ARGUMENT_INVALID` / `TELEPHONY_ERR_LOCAL_PTR_NULL`，或把 formatNumber 置空串

#### Scenario: E164 规范化
- **WHEN** 调用 `FormatPhoneNumberToE164` 且 countries code 大写化后 `IsValidNumber` 通过
- **THEN** 输出 E164 格式号码（真实号码示例以 unknown 占位），返回 `TELEPHONY_SUCCESS`

### Requirement: 号码字符串清洗与合法性判定
系统 SHALL 由 `CallNumberUtils` 提供三个纯字符串函数：`RemoveSeparatorsPhoneNumber`（仅保留数字与 '*','#','+','N',',',';'）、`RemovePostDialPhoneNumber`（同符集但在遇到 ',' 或 ';' 时截断后拨串）、`HasAlphabetInPhoneNum`（空串视为含字母返回 true；任一 a-z/A-Z 字符即返回 true）。

#### Scenario: 分隔符剥离
- **WHEN** 号码串含空格、'-' 等分隔符
- **THEN** `RemoveSeparatorsPhoneNumber` 输出仅保留合法拨号字符的字符串

#### Scenario: 后拨截断
- **WHEN** 号码串形如 unknown 占位的 主号,分机格式（',' 之后为后拨段）
- **THEN** `RemovePostDialPhoneNumber` 返回 ',' 之前的主号部分

#### Scenario: 含字母拒绝
- **WHEN** `HasAlphabetInPhoneNum` 入参为空或含英文字母
- **THEN** 返回 true，调用方（拨号链路）拒绝该号码

### Requirement: 紧急号码、运营商配置与卡槽有效性判定
系统 SHALL 由 `CallNumberUtils` 将三类判定代理到 cellular_call 连接层：`CheckNumberIsEmergency` 经 `DelayedSingleton<CellularCallConnection>::GetInstance()->IsEmergencyPhoneNumber(phoneNumber, slotId, enabled)`；`IsCarrierVtConfig` 经 `GetCarrierVtConfig(slotId, enabled)`；`IsValidSlotId` 按 `SIM_SLOT_COUNT`（==1 判 `SIM_SLOT_0`，==2 判 `SIM_SLOT_0`/`SIM_SLOT_1`）本仓内判定。

#### Scenario: 紧急号码判定委托
- **WHEN** 呼叫链路（`call_request_process.cpp`、`call_control_manager.cpp`）调用 `CheckNumberIsEmergency`
- **THEN** 结果完全由 cellular_call 侧 `IsEmergencyPhoneNumber` 决定，本层仅透传

#### Scenario: 非法 slotId
- **WHEN** `SIM_SLOT_COUNT` 为 1 时传入非 `SIM_SLOT_0` 的 slotId
- **THEN** `IsValidSlotId` 返回 false

### Requirement: 拨号账号选择（默认语音卡与默认数据卡回退）
系统 SHALL 由 `CallNumberUtils::SelectAccountId(slotId, extras)` 实现两级账号选择：slotId 本身有效直接放行；否则经 `DelayedRefSingleton<CoreServiceClient>::GetInstance()->GetDefaultVoiceSlotId()` 取默认语音卡写入 extras 键 "accountId"；仍失败且开启 `CELLULAR_DATA_SUPPORT` 时（`utils/src/call_number_utils.cpp` 的 `#ifdef` 场点），经 `DelayedRefSingleton<CellularDataClient>::GetInstance()->GetDefaultCellularDataSlotId()` 取默认数据卡作为最后回退。该函数被 `services/call/src/call_policy.cpp` 的拨号策略调用。

#### Scenario: 传入 slotId 有效
- **WHEN** `IsValidSlotId(slotId)` 为 true
- **THEN** 直接返回 true，不写 extras

#### Scenario: 默认数据卡回退
- **WHEN** slotId 无效且默认语音卡不可用，且编译期定义了 `CELLULAR_DATA_SUPPORT`
- **THEN** 查询 cellular_data 的默认数据卡 slotId，有效时写 extras "accountId" 并返回 true；否则返回 false

### Requirement: 号码归属地查询与上报
系统 SHALL 由 `CallNumberUtils` 通过 `QueryNumberLocationInfo(numberLocation, accountNumber)`（经 `NumberIdentityDataBaseHelper::Query`）查询号码归属地，并由 `NumberLocationUpdate(callObjectPtr)` 落盘到通话对象：`call->SetNumberLocation(numberLocation)`、同步通知 `CallVoiceAssistantManager::GetInstance()->UpdateNumberLocation`，归属地非空且非 "default" 时经 `DelayedSingleton<CallAbilityReportProxy>::ReportCallStateInfo` 上报。拨打态（`CALL_STATUS_DIALING`）时先经 `CallObjectManager::GetOneCallObject(info.callId)` 换取受控对象。调用方为 `services/call/src/call_status_manager.cpp`。

#### Scenario: 空号拦截
- **WHEN** accountNumber 为空串
- **THEN** `QueryNumberLocationInfo` 返回 `TELEPHONY_ERR_ARGUMENT_INVALID`

#### Scenario: 查询失败静默
- **WHEN** 数据库查询返回 `TELEPHONY_ERR_DATABASE_READ_FAIL`
- **THEN** `NumberLocationUpdate` 直接返回，不修改通话对象、不上报

#### Scenario: 查询成功上报
- **WHEN** 归属地为非空且非 "default" 的值且 callId 仍存在
- **THEN** 调用 `ReportCallStateInfo` 上报最新 `CallAttributeInfo`

### Requirement: 黄页标记查询与上报
系统 SHALL 由 `CallNumberUtils::YellowPageAndMarkUpdate(callObjectPtr)` 在系统参数 `const.global.region` 为 "CN"（`OHOS::system::GetParameter`）时执行 `QueryYellowPageAndMarkInfo`（经 `NumberIdentityDataBaseHelper::QueryYellowPageAndMark`），成功后 `call->SetNumberMarkInfo(numberMarkInfo)`；当 `numberMarkInfo.markType > MarkType::MARK_TYPE_NONE` 或 `info.isEcc` 时经 `CallAbilityReportProxy::ReportCallStateInfo` 上报。非中国区版本直接跳过。

#### Scenario: 非中国区跳过
- **WHEN** `const.global.region` 不为 "CN"
- **THEN** 不发起任何数据库查询与上报

#### Scenario: 标记有效上报
- **WHEN** 查询成功且 `markType` 高于 `MARK_TYPE_NONE` 或该通话为紧急呼叫
- **THEN** 上报含 `NumberMarkInfo` 的通话属性

### Requirement: 号码身份数据库助手
系统 SHALL 由 `NumberIdentityDataBaseHelper`（`utils/src/number_identity_data_base_helper.cpp`，DelayedSingleton）经 `DataShare::DataShareHelper::Creator(remoteObj, uri)`（remoteObj 取自 `TELEPHONY_CALL_MANAGER_SYS_ABILITY_ID` SA）提供两个查询：`Query`（URI `datashare:///numberlocationability`，列 `number_location`，查询列含精确匹配标志 "true"）与 `QueryYellowPageAndMark`（URI `datashare:///numbermarkability/number_mark_info`，经 `SetMarkInfoValues` 读出 `markType`/`markContent`/`markCount`/`markSource`/`isCloud`/`markDetails` 六列，字符串经 `memcpy_s` 拷贝至 `kMaxNumberLen` 定长缓冲）。行数为 0 时归属地查询直接成功返回、黄页查询把 `markType` 置 `MARK_TYPE_NONE`。两查询均负责 `helper->Release()` 资源释放。

#### Scenario: 归属地行数为零
- **WHEN** `Query` 结果 rowCount 为 0
- **THEN** 返回 true 且不修改 numberLocation

#### Scenario: 列读取越界防护
- **WHEN** `SetMarkInfoValues` 中任一 `memcpy_s` 失败
- **THEN** 返回 false，上层映射为 `TELEPHONY_ERR_DATABASE_READ_FAIL`

### Requirement: CallManagerUtils 序列化与包安装查询
系统 SHALL 由 `CallManagerUtils`（纯静态，`utils/src/call_manager_utils.cpp`）提供两个函数：`WriteCallAttributeInfo(info, messageParcel)` 把 `CallAttributeInfo` 逐字段序列化进 `MessageParcel`（accountNumber/bundleName/speakerphoneOn/accountId/videoState/startTime/isEcc/callType/callId/callState/conferenceState/各时间戳/index/crsType/originalCallType/numberLocation/numberMarkInfo/contactName/extraParamsString，`TYPE_VOIP` 时追加 voipCallInfo 全字段与 `WriteUInt8Vector(userProfile)`，末尾写 `phoneOrWatch`）；`IsBundleInstalled(bundleName, userId)` 经 samgr 取 `BUNDLE_MGR_SERVICE_SYS_ABILITY_ID` 的 `AppExecFwk::IBundleMgr` 代理查询。序列化时私有 `IsForcedReportVoiceCall`（来电态且 `CallBase::IsForcedReportVoiceCall()` 为真）把 videoState 强制写成 `VideoStateType::TYPE_VOICE`。

#### Scenario: 强制语音上报
- **WHEN** 通话为来电态且该 `CallBase` 要求强制语音上报
- **THEN** 序列化的 videoState 字段写 `TYPE_VOICE` 而非真实视频态

#### Scenario: VOIP 扩展字段
- **WHEN** info.callType 为 `TYPE_VOIP`
- **THEN** MessageParcel 追加 voipCallInfo 段（voipCallId、userName、abilityName、extensionId、voipBundleName 等 11 项）

#### Scenario: BundleMgr 不可用
- **WHEN** samgr 或 BUNDLE_MGR 代理为空
- **THEN** `IsBundleInstalled` 返回 false（如调用方 `call_records_manager.cpp` 对骚扰拦截应用安装检测 ANTIFRAUD_CENTER_BUNDLE_NAME/BEST_MIND_BUNDLE_NAME 的分支）

### Requirement: 设置项 DataShare 读写助手
系统 SHALL 由 `SettingsDataShareHelper`（DelayedSingleton，`utils/src/settings_datashare_helper.cpp`）对 URI `datashare:///com.ohos.settingsdata/entry/settingsdata/SETTINGSDATA?Proxy=true`（扩展 URI `datashare:///com.ohos.settingsdata.DataAbility`，列 `KEYWORD`/`VALUE`）提供 `Query`（EqualTo KEYWORD 过滤，rowCount 为 0 返回 `TELEPHONY_ERR_UNINIT`）、`Insert`（成功后 `NotifyChange`）、`Update`（先 Query 判存在，不存在转 Insert）与 `RegisterToDataShare`/`UnRegisterToDataShare`（注册/注销 `AAFwk::IDataAbilityObserver`）。预置键常量：`QUERY_SATELLITE_MODE_KEY`("satellite_mode_switch")、`QUERY_SATELLITE_CONNECTED_KEY`("satellite_connected")、`QUERY_MOTION_FLIP_MUTE_KEY`("motion_flip_mute_call")、`QUERY_MOTION_CLOSE_TO_EAR_KEY`("motion_quick_answer")、`QUERY_MOTION_PICKUP_REDUCE_KEY`("motion_pickup_reduce_call")。

#### Scenario: 键不存在
- **WHEN** `Query` 命中 0 行
- **THEN** 返回 `TELEPHONY_ERR_UNINIT` 而非成功

#### Scenario: 更新转为插入
- **WHEN** `Update` 前置 `Query` 返回非 0（键不存在）
- **THEN** 内部转调 `Insert` 完成 upsert 语义

#### Scenario: 卫星模式消费方
- **WHEN** `services/satellite_call/src/satellite_call_control.cpp` 查询 `QUERY_SATELLITE_MODE_KEY` / `QUERY_SATELLITE_CONNECTED_KEY`
- **THEN** 经本助手从 settingsdata DataShare 读取布尔值

### Requirement: 来电/通话系统对话框拉起
系统 SHALL 由 `CallDialog`（`utils/src/call_dialog.cpp`，DelayedSingleton 使用方）经 `AAFwk::ExtensionManagerClient::ConnectServiceExtensionAbility` 连接 `com.ohos.sceneboard` / `com.ohos.sceneboard.systemdialog`，命令体由 nlohmann::json 构造（`ability.want.params.uiExtensionType`="sysDialog/common"、`sysDialogZOrder`、`dialogReason`、`slotId` 等字段）。入口面：`DialogConnectExtension(dialogReason[, slotId])`（dialogReason 含 "SATELLITE" 时走 `CallSettingAbilityConnection`，否则走 `CallAbilityConnection`；消费方如 `call_policy.cpp` 的 "CALL_FAILED_NO_SIM_CARD"/"CALL_FAILED_IN_AIRPLANE_MODE"/"CALL_FAILED_NO_SERVICE"/"CALL_FAILED_CTCARD_NO_IMS"、`call_request_process.cpp` 的 "CALL_FAILED_DUE_TO_FDN"、`satellite_call_control.cpp` 的 "SATELLITE_CALL_DISCONNECT" 等）；`DialogConnectPrivpacyModeExtension` 与 `DialogConnectAnswerPrivpacyModeExtension`（"SUPER_PRIVACY_MODE"，含 number/accountId/videoState/dialType/dialScene/callType/isAnswer/isVideo/isFold，isFold 取 `FoldStatusManager::IsSmallFoldDevice()` 与 `Rosen::DisplayManager::GetFoldStatus()==FOLDED`）；`DialogCallingPrivacyModeExtension(foldStatus)`（仅 `FOLDED` 且 `CallSuperPrivacyControlManager::GetCurrentIsSuperPrivacyMode()` 时）；`DialogProcessMMICodeExtension`（"PROCESS_MMI_CODE"，`sysDialogZOrder` 用 `SCB_SYS_DIALOG_ZORDER_UNDER_LOCK`=1，`call_request_process.cpp` 消费）。连接期间用 `IPCSkeleton::ResetCallingIdentity`/`SetCallingIdentity` 切换身份。

#### Scenario: 普通失败原因对话框
- **WHEN** `DialogConnectExtension` 的 reason 不含 "SATELLITE"
- **THEN** 经 `CallAbilityConnection` 连接 sceneboard systemdialog，连接结果非 0 时返回 false

#### Scenario: 卫星对话框分流
- **WHEN** reason 含 "SATELLITE"
- **THEN** 改经 `CallSettingAbilityConnection` 发起连接

#### Scenario: 超级隐私折叠来电
- **WHEN** 折叠态为 `FOLDED` 且当前处于超级隐私模式且存在非来电态前台通话
- **THEN** 拉起 "SUPER_PRIVACY_MODE" 对话框并携带前台通话的 videoState

### Requirement: Ability 连接回调发参
系统 SHALL 由 `CallAbilityConnection` 与 `CallSettingAbilityConnection`（`utils/src/call_ability_connection.cpp`、`utils/src/call_setting_ability_connection.cpp`）在 `OnAbilityConnectDone` 中把构造时保存的 commandStr 通过 `remoteObject->SendRequest(AAFwk::IAbilityConnection::ON_ABILITY_CONNECT_DONE, ...)` 回发给被连 uiAbility：`CallAbilityConnection` 固定携带 bundleName "com.ohos.callui"、abilityName "com.ohos.callui.CallFailedDialogAbility"；`CallSettingAbilityConnection` 携带 bundleName "com.callsetting"、abilityName "com.callsetting.SatelliteCallDialogAbility"；参数计数 `PARAM_NUM`=3（bundleName/abilityName/parameters 三键值对），remoteObject 为空时仅打日志。`OnAbilityDisconnectDone` 仅记日志。

#### Scenario: 连接成功回发命令
- **WHEN** sceneboard 连接成功回调 `OnAbilityConnectDone`
- **THEN** 以 MessageParcel 写入 3 组键值（含 commandStr）并 `SendRequest(ON_ABILITY_CONNECT_DONE)`

#### Scenario: 远端对象缺失
- **WHEN** 回调的 remoteObject 为空
- **THEN** 不发送任何 `SendRequest`，仅记录日志

### Requirement: 企业禁拨策略（EDM）
系统 SHALL 由 `EdmCallPolicy`（`utils/src/edm_call_policy.cpp`）维护拨入/拨出两张策略表 `EdmCallPolicyList`（`EdmPolicyFlag`：`POLICY_FLAG_NONE`/`POLICY_FLAG_BLOCK` 黑名单/`POLICY_FLAG_TRUST` 白名单，`std::unordered_set` 号码集，`ffrt::shared_mutex` 读写锁）：`SetCallPolicy(isDialingTrustlist, dialingList, isIncomingTrustlist, incomingList)`（任一清单超 `MAX_COUNT`=1000 返回 `TELEPHONY_ERR_ARGUMENT_INVALID`）；`IsCallEnable` 先查系统参数 `persist.edm.telephony_call_disable`（`system::GetBoolParameter`，true 则全禁），再按 flag 语义判定（空名单放行；BLOCK=不在黑名单放行；TRUST=在白名单放行）；`IsDialingEnable`/`IsIncomingEnable` 分别供 `services/call/src/call_policy.cpp` 与 `call_incoming_filter_manager.cpp` 调用。设置链路为 `CallManagerService::SetCallPolicyInfo`（见 call-manager-service 能力）。

#### Scenario: 总开关禁拨
- **WHEN** `persist.edm.telephony_call_disable` 为 true
- **THEN** `IsDialingEnable`/`IsIncomingEnable` 对任意号码（示例 unknown）均返回 false

#### Scenario: 白名单命中
- **WHEN** 策略 flag 为 `POLICY_FLAG_TRUST` 且名单非空、号码在名单中
- **THEN** 返回 true 允许呼叫

#### Scenario: 清单超限
- **WHEN** 任一号码清单大小超过 1000
- **THEN** `SetCallPolicy` 返回 `TELEPHONY_ERR_ARGUMENT_INVALID`，策略表保持不变

### Requirement: 来电闪光提醒
系统 SHALL 由 `IncomingFlashReminder`（`utils/src/incoming_flash_reminder.cpp`，`AppExecFwk::EventHandler` 子类）在事件分派（`ProcessEvent`：`DELAY_SET_TORCH_EVENT`=1000000、`STOP_FLASH_REMIND_EVENT`=1000001、`START_FLASH_REMIND_EVENT`=1000002）基础上实现：开关查询 `IsFlashReminderSwitchOn`（`OsAccountManager::QueryActiveOsAccountIds` 取 userId，对 `USER_SETTINGSDATA_SECURE_<userId>` DataShare URI 查询，值为 "1" 且含子串 `FLASH_REMINDER_SWITCH_SUBSTRING`("INCOMING_CALL") 才开）；就绪判定 `IsScreenStatusSatisfied`（仅 `ABILITY_SCREENLOCKMGR_SUPPORT` 定义时经 `ScreenLock::ScreenLockManager::IsScreenLocked()` 判断锁屏，未定义恒 false）与 `IsTorchReady`（仅 `ABILITY_CAMERA_FRAMEWORK_SUPPORT` 定义时经 `CameraStandard::CameraManager` 的 `IsTorchSupported`/`GetTorchMode`，未定义恒 false）；`HandleSetTorchMode` 翻转 `TORCH_MODE_ON`/`TORCH_MODE_OFF` 并按 `DELAY_SET_TORCH_MODE_TIME`=300ms 自循环；`HandleStopFlashRemind` 移除循环事件并强制 `TORCH_MODE_OFF` 后回调 stopFlashRemindDone_。

#### Scenario: 宏未开启时禁用
- **WHEN** 编译期未定义 `ABILITY_CAMERA_FRAMEWORK_SUPPORT` 或 `ABILITY_SCREENLOCKMGR_SUPPORT`
- **THEN** `IsTorchReady`/`IsScreenStatusSatisfied` 恒 false，`IsFlashRemindNecessary` 为 false，闪光提醒不可用

#### Scenario: 手电占用中
- **WHEN** 当前 `TorchMode` 已是 `TORCH_MODE_ON`
- **THEN** `IsTorchReady` 返回 false，不来电闪烁

#### Scenario: 停止时清理
- **WHEN** `StopFlashRemind` 触发且曾启动过闪光
- **THEN** 移除 `DELAY_SET_TORCH_EVENT`、强制关 torch、回调完成通知

### Requirement: 运动识别与运动插件装载
系统 SHALL 由 `MotionRecogntion`（`utils/src/motion_recognition.cpp`，全部订阅/退订函数体在 `#ifdef OHOS_SUBSCRIBE_MOTION_ENABLE` 内）提供 6 个订阅接口（`SubscribePickupSensor`/`UnsubscribePickupSensor`/`SubscribeFlipSensor`/`UnsubscribeFlipSensor`/`SubscribeCloseToEarSensor`/`UnsubscribeCloseToEarSensor`），经 `screen_sensor_plugin.cpp` 的 `Rosen::SubscribeCallback`/`UnsubscribeCallback` 转发到 dlopen 插件。运动类型常量：`MOTION_TYPE_PICKUP`=100、`MOTION_TYPE_FLIP`=200、`MOTION_TYPE_CLOSE_TO_EAR`=300，翻转方向 `FilpDirection`：`FLIP_DOWN`=3 / `FLIP_UP`=4。回调行为：翻转 `FLIP_UP` 且存在振铃通话时 `CallControlManager::MuteRinger` 并 `StopFlashRemind`；拿起动作先退订 pickup，经 ffrt::submit 异步执行 `ReduceRingToneVolume`（按 `REDUCE_RING_TOTAL_LENGTH`=1500000us 分级把 `AudioProxy` 铃声音量从当前级降到 1）；贴近耳朵时仅振铃态 `AnswerCall` 语音接听，拨打/激活态且当前音频设备为 `DEVICE_SPEAKER`/`DEVICE_BLUETOOTH_SCO`/`DEVICE_NEARLINK` 时 `SetAudioDevice` 切到 `DEVICE_EARPIECE`。`screen_sensor_plugin.cpp` 的 `LoadMotionSensor`（按 `PLUGIN_SO_PATH` = 平台 SDK 下 libmotion_agent.z.so，重试至多 3 次，命名空间 `OHOS::Rosen`）由 `call_status_manager.cpp` 在设置开关开启时调用。订阅防重入由静态标志 isMotionXxxSubscribed_ 保证。

#### Scenario: 宏未开启空实现
- **WHEN** 编译期未定义 `OHOS_SUBSCRIBE_MOTION_ENABLE`
- **THEN** 6 个订阅/退订函数为空实现，且无任何静态标志与回调编译

#### Scenario: 翻转静音
- **WHEN** 运动回调 `MOTION_TYPE_FLIP` 且 status 为 `FLIP_UP` 且存在振铃通话
- **THEN** 执行 `MuteRinger` 与 `StopFlashRemind`

#### Scenario: 插件缺失
- **WHEN** libmotion_agent.z.so 三次 dlopen 均失败
- **THEN** `LoadMotionSensor` 返回 false，`SubscribeCallback` 收到空句柄返回 false

### Requirement: 手表移植预计移除面（utils 层）
系统 SHALL 把以下预计在手表目标上整体移除的文件集中登记（基线中它们当前编译且行为如上）：企业禁拨 `utils/src/edm_call_policy.cpp`（含 EDM 设置链）、来电闪光 `utils/src/incoming_flash_reminder.cpp`、运动识别 `utils/src/motion_recognition.cpp` + 插件装载 `utils/src/screen_sensor_plugin.cpp`，以及 `call_setting_ability_connection.cpp` 中面向卫星对话框的分支。`utils` 目录下的 `settings_datashare_helper.cpp` 卫星键（`QUERY_SATELLITE_MODE_KEY`/`QUERY_SATELLITE_CONNECTED_KEY`）与 `call_dialog.cpp` 中 "SATELLITE" 对话框分支预计随卫星通话裁剪一并移除。native 侧预计移除文件（bluetooth_call_client、nearlink_call_client、super_privacy_manager_client 等）见 native-client-api 规格同名 Requirement。

#### Scenario: EDM 移除后的设置链
- **WHEN** 手表基线移除 edm_call_policy 后调用 `SetCallPolicyInfo`
- **THEN** 上层（call-manager-service 能力）的该入口与 `call_policy.cpp`/`call_incoming_filter_manager.cpp` 判定点需同步清理（具体由裁剪 delta 决定）

#### Scenario: 运动宏整体跳过
- **WHEN** 手表基线移除 motion_recognition / screen_sensor_plugin
- **THEN** `call_status_manager.cpp` 的 `IsCallMotionRecognitionEnable` 相关订阅点与 `CallDialog`/`SettingsDataShareHelper` 的 motion 键消费方需同步处理（具体由裁剪 delta 决定）