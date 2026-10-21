# Spec Delta

## REMOVED Requirements

### Requirement: 企业禁拨策略（EDM）
**Reason**: AGENTS 功能范围明确 EDM 企业禁拨不支持、相关代码无需迁移；design D7 删除 `utils/src/edm_call_policy.cpp`。
**Migration**: 删除 `utils/src/edm_call_policy.cpp`（及对应头文件）与拨入/拨出两张 `EdmCallPolicyList` 策略表（`EdmPolicyFlag`、`std::unordered_set` 号码集、`ffrt::shared_mutex` 读写锁随全仓去锁一并消失）；上层设置链 `CallManagerService::SetCallPolicyInfo`（call-manager-service delta）与消费判定点 `services/call/src/call_policy.cpp`（`IsDialingEnable`）、`call_incoming_filter_manager.cpp`（`IsIncomingEnable`）同步清理（call-status-management delta「来电准入过滤」条已移除 EDM 判定分支）。恢复条件：目标平台引入 EDM 企业管控能力后按本 baseline 需求整块恢复。

### Requirement: 来电闪光提醒
**Reason**: AGENTS 功能范围明确来电闪光（incoming flash）不支持、相关代码无需迁移；design D7 删除 `utils/src/incoming_flash_reminder.cpp`，`ABILITY_CAMERA_FRAMEWORK_SUPPORT` / `ABILITY_SCREENLOCKMGR_SUPPORT` 宏场点随文件删除，gni 部件块（`multimedia_camera_framework` / `theme_screenlock_mgr`）随删（design D7 宏清理）。
**Migration**: 删除 `utils/src/incoming_flash_reminder.cpp`（及对应头文件）与 `IncomingFlashReminder` 事件循环（`DELAY_SET_TORCH_EVENT`/`STOP_FLASH_REMIND_EVENT`/`START_FLASH_REMIND_EVENT`、`IsFlashReminderSwitchOn` 开关查询、`IsScreenStatusSatisfied`/`IsTorchReady` 就绪判定、`HandleSetTorchMode`/`HandleStopFlashRemind` 处理链）；上游触发/停止调用点（`CallControlManager::StartFlashRemind`/`StopFlashRemind` 及各联动分支）随 call-status-management / call-control-management delta 相应分支移除。恢复条件：平台具备 camera_framework/screenlock 部件并引入来电闪光需求后按本 baseline 需求恢复。

### Requirement: 运动识别与运动插件装载
**Reason**: AGENTS 特性宏支持范围明确 `OHOS_SUBSCRIBE_MOTION_ENABLE` 不支持（代码无需迁移）；design D7 删除 `utils/src/motion_recognition.cpp`、`utils/src/screen_sensor_plugin.cpp` 并清 gni `msdp_motion` 部件块。
**Migration**: 删除 `utils/src/motion_recognition.cpp`（及头文件）与 `utils/src/screen_sensor_plugin.cpp`（及头文件）：6 个订阅/退订接口（`SubscribePickupSensor`/`UnsubscribePickupSensor`/`SubscribeFlipSensor`/`UnsubscribeFlipSensor`/`SubscribeCloseToEarSensor`/`UnsubscribeCloseToEarSensor`）、`MOTION_TYPE_*` 常量与 `FilpDirection`、`Rosen::SubscribeCallback`/`UnsubscribeCallback` 转发与 `LoadMotionSensor` dlopen 插件装载（`PLUGIN_SO_PATH`、3 次重试）；消费点 `call_status_manager.cpp` 的 `IsCallMotionRecognitionEnable` 与订阅调用链随 call-status-management delta「动作识别订阅联动」REMOVED 条移除；`SettingsDataShareHelper` 运动键消费链见本 delta MODIFIED「设置项 DataShare 读写助手」条。恢复条件：平台引入 msdp_motion 传感插件后按本 baseline 需求恢复。

### Requirement: 手表移植预计移除面（utils 层）
**Reason**: 该需求是基线侧移植前的预登记占位（各场景均注明"具体由裁剪 delta 决定"），本 delta 已对各登记面给出实际裁决：EDM 禁拨、来电闪光、运动识别+传感插件按预测移除（见上三条 REMOVED）；`call_setting_ability_connection.cpp` 的卫星对话框分支、`call_dialog.cpp` 的 "SATELLITE" 分流与 `SettingsDataShareHelper` 卫星键按已定裁决保留（卫星功能已删但连接/分流/查询逻辑保留 todo 形态照抄，见 MODIFIED 条），预登记使命完成。
**Migration**: 内容由本 delta 实际 REMOVED/MODIFIED 条目承载（`edm_call_policy.cpp`、`incoming_flash_reminder.cpp`、`motion_recognition.cpp`、`screen_sensor_plugin.cpp` 四文件删除；卫星分支/键保留 todo 形态）；native 侧预计移除文件（bluetooth_call_client、nearlink_call_client、super_privacy_manager_client 等）由 native-client-api delta 承载（基线指引照抄）。恢复条件：不适用（该需求为规划占位，不描述运行时行为）。

## MODIFIED Requirements

### Requirement: 号码格式化链
系统 SHALL 由 `CallNumberUtils`（`DECLARE_DELAYED_SINGLETON` 声明，`utils/src/call_number_utils.cpp`）照抄保留 4 种格式化出口与 `FormatNumberBase` / `ProcessSpace` 私有链全部逻辑：`FormatPhoneNumber`（`ParseAndKeepRawInput` + `FormatInOriginalFormat`）、`FormatPhoneNumberToE164` / `FormatPhoneNumberToNational` / `FormatPhoneNumberToInternational`（`Parse` + `IsValidNumber`（或 `HasBCPhoneNumber` 放行）后按 `PhoneNumberUtil::E164` / `NATIONAL` / `INTERNATIONAL` 格式化）、`FormatPhoneNumberAsYouType`（`AsYouTypeFormatter::InputDigit` 逐字符输入）；National/International 输出经 `ProcessSpace` 去除全部空白字符照抄。libphonenumber（`i18n::phonenumbers::PhoneNumberUtil`）调用经 `stub/phonenumber_stub` 同名桩承载（design D6，签名相同的空实现）；`#`/`*` 前缀直通与错误码分支照抄。

#### Scenario: # 或 * 前缀直通
- **WHEN** `FormatPhoneNumber` / `FormatPhoneNumberAsYouType` 收到以 '#' 或 '*' 开头的号码（如 MMI/USSD 补充业务码）
- **THEN** 不走 libphonenumber 桩，直接原样返回该字符串并返回 `TELEPHONY_SUCCESS`（照抄）

#### Scenario: 空号码或解析失败
- **WHEN** 入参号码为空、或 `PhoneNumberUtil` 单例为空、或格式化结果为空串或 "0"
- **THEN** 分别返回 `TELEPHONY_ERR_ARGUMENT_INVALID` / `TELEPHONY_ERR_LOCAL_PTR_NULL`，或把 formatNumber 置空串（照抄）

#### Scenario: E164 规范化
- **WHEN** 调用 `FormatPhoneNumberToE164` 且 countries code 大写化后 `IsValidNumber` 通过（经桩注入）
- **THEN** 输出 E164 格式号码（真实号码示例以 unknown 占位），返回 `TELEPHONY_SUCCESS`（照抄）

### Requirement: 紧急号码、运营商配置与卡槽有效性判定
系统 SHALL 照抄保留三类判定：`CheckNumberIsEmergency` 经 `DelayedSingleton<CellularCallConnection>::GetInstance()->IsEmergencyPhoneNumber(phoneNumber, slotId, enabled)`——连接类按 design D4 保留为适配器、内部改调 `CellularCallClient::GetInstance()` 桩（见 telephony-interaction delta），本层仅透传照抄；`IsCarrierVtConfig` 经 `GetCarrierVtConfig(slotId, enabled)` 同经适配器/桩（视频通话不支持、调用方随视频能力裁剪减少，函数本体与委托照抄保留）；`IsValidSlotId` 按 `SIM_SLOT_COUNT`（==1 判 `SIM_SLOT_0`，==2 判 `SIM_SLOT_0`/`SIM_SLOT_1`）本仓内判定照抄（liteOS 单卡、预留双卡扩展能力，AGENTS）。

#### Scenario: 紧急号码判定委托
- **WHEN** 呼叫链路（`call_request_process.cpp`、`call_control_manager.cpp`）调用 `CheckNumberIsEmergency`
- **THEN** 结果完全由 cellular_call 侧（经 `CellularCallClient::GetInstance()` 桩）决定，本层仅透传（照抄）

#### Scenario: 非法 slotId
- **WHEN** `SIM_SLOT_COUNT` 为 1 时传入非 `SIM_SLOT_0` 的 slotId
- **THEN** `IsValidSlotId` 返回 false（照抄）

### Requirement: 拨号账号选择（默认语音卡与默认数据卡回退）
系统 SHALL 由 `CallNumberUtils::SelectAccountId(slotId, extras)` 照抄保留两级回退判定：slotId 本身有效直接放行；否则经 `DelayedRefSingleton<CoreServiceClient>::GetInstance()->GetDefaultVoiceSlotId()` 取默认语音卡写入 extras 键 "accountId"——`CoreServiceClient` 经 `stub/core_service_client` 桩（design D4）；仍失败且保留的 `CELLULAR_DATA_SUPPORT` 宏块开启时（design D7 支持宏表，gni `telephony_cellular_data` 部件块保留），经 `DelayedRefSingleton<CellularDataClient>::GetInstance()->GetDefaultCellularDataSlotId()` 取默认数据卡作为最后回退——`CellularDataClient` 经 `stub/cellular_data_client` 桩（design D4）；extras 载体按基线 `AppExecFwk::PacMap` 参数依 design D5 换普通结构体（"accountId" 键写入语义照抄）；调用方 `services/call/src/call_policy.cpp` 的拨号策略保留。

#### Scenario: 传入 slotId 有效
- **WHEN** `IsValidSlotId(slotId)` 为 true
- **THEN** 直接返回 true，不写 extras（照抄）

#### Scenario: 默认数据卡回退
- **WHEN** slotId 无效且默认语音卡不可用（经桩注入），且 `CELLULAR_DATA_SUPPORT` 宏块保留开启
- **THEN** 经 `CellularDataClient::GetInstance()` 桩查询默认数据卡 slotId，有效时写 extras "accountId" 并返回 true；否则返回 false（照抄）

### Requirement: 号码归属地查询与上报
系统 SHALL 照抄保留 `QueryNumberLocationInfo(numberLocation, accountNumber)` / `NumberLocationUpdate(callObjectPtr)` 链：归属地查询经 `NumberIdentityDataBaseHelper::Query`（调用点标注 `// todo!!! [database]`，AGENTS：数据库 DataShare 暂不调用，逻辑保留）；`call->SetNumberLocation(numberLocation)` 照抄；因语音播报不支持（AGENTS 功能范围；`call_voice_assistant_manager.cpp` 删除，design D7），原同步通知 `CallVoiceAssistantManager::GetInstance()->UpdateNumberLocation` 分支移除；归属地非空且非 "default" 时经 `DelayedSingleton<CallAbilityReportProxy>::ReportCallStateInfo` 上报——回报直调形态（design D3，见 call-report delta）；拨打态（`CALL_STATUS_DIALING`）先经 `CallObjectManager::GetOneCallObject(info.callId)` 换取受控对象照抄；调用方 `services/call/src/call_status_manager.cpp` 保留。

#### Scenario: 空号拦截
- **WHEN** accountNumber 为空串
- **THEN** `QueryNumberLocationInfo` 返回 `TELEPHONY_ERR_ARGUMENT_INVALID`（照抄）

#### Scenario: 查询失败静默
- **WHEN** 数据库查询（todo [database] 桩）返回 `TELEPHONY_ERR_DATABASE_READ_FAIL`
- **THEN** `NumberLocationUpdate` 直接返回，不修改通话对象、不上报（照抄）

#### Scenario: 查询成功上报
- **WHEN** 归属地为非空且非 "default" 的值且 callId 仍存在
- **THEN** 经 `CallAbilityReportProxy::ReportCallStateInfo` 直调上报最新 `CallAttributeInfo`（照抄；语音播报通知分支已移除）

### Requirement: 黄页标记查询与上报
系统 SHALL 照抄保留 `CallNumberUtils::YellowPageAndMarkUpdate(callObjectPtr)` 链：系统参数 `const.global.region` 判定 "CN"（`OHOS::system::GetParameter` 经 `stub/parameter_stub` 桩，design D6 系统参数行）时执行 `QueryYellowPageAndMarkInfo`（经 `NumberIdentityDataBaseHelper::QueryYellowPageAndMark`，调用点标注 `// todo!!! [database]`）；成功后 `call->SetNumberMarkInfo(numberMarkInfo)` 照抄；当 `numberMarkInfo.markType > MarkType::MARK_TYPE_NONE` 或 `info.isEcc` 时经 `CallAbilityReportProxy::ReportCallStateInfo` 上报（直调形态，见 call-report delta）；非中国区版本直接跳过照抄。

#### Scenario: 非中国区跳过
- **WHEN** `const.global.region`（经 parameter 桩）不为 "CN"
- **THEN** 不发起任何数据库查询与上报（照抄）

#### Scenario: 标记有效上报
- **WHEN** 查询成功且 `markType` 高于 `MARK_TYPE_NONE` 或该通话为紧急呼叫
- **THEN** 上报含 `NumberMarkInfo` 的通话属性（直调，照抄）

### Requirement: 号码身份数据库助手
系统 SHALL 照抄保留 `NumberIdentityDataBaseHelper`（`utils/src/number_identity_data_base_helper.cpp`，DelayedSingleton）两查询的判定与资源释放逻辑：`Query`（URI `datashare:///numberlocationability`，列 `number_location`，查询列含精确匹配标志 "true"）与 `QueryYellowPageAndMark`（URI `datashare:///numbermarkability/number_mark_info`，经 `SetMarkInfoValues` 读出 `markType`/`markContent`/`markCount`/`markSource`/`isCloud`/`markDetails` 六列，字符串经 `memcpy_s` 拷贝至 `kMaxNumberLen` 定长缓冲——`memcpy_s` 经 `stub/securec_stub` 同名桩，design D5）；行数为 0 时归属地查询直接成功返回、黄页查询把 `markType` 置 `MARK_TYPE_NONE`（照抄）；`helper->Release()` 释放照抄。`DataShare::DataShareHelper::Creator`（remoteObj 取自 `TELEPHONY_CALL_MANAGER_SYS_ABILITY_ID` SA 的取远端对象面随无 SA 形态不迁移）与全部 DataShare 调用点标注 `// todo!!! [database] ref to number_identity_data_base_helper.cpp Query/QueryYellowPageAndMark`（AGENTS：号码识别/黄页相关接口暂不调用，依赖数据库接口适配，逻辑保留）。

#### Scenario: 归属地行数为零
- **WHEN** `Query` 结果 rowCount 为 0（经桩注入）
- **THEN** 返回 true 且不修改 numberLocation（照抄）

#### Scenario: 列读取越界防护
- **WHEN** `SetMarkInfoValues` 中任一 `memcpy_s` 失败
- **THEN** 返回 false，上层映射为 `TELEPHONY_ERR_DATABASE_READ_FAIL`（照抄）

### Requirement: CallManagerUtils 序列化与包安装查询
系统 SHALL 由 `CallManagerUtils`（纯静态，`utils/src/call_manager_utils.cpp`）三函数照抄保留：`IsForcedReportVoiceCall`（来电态且 `CallBase::IsForcedReportVoiceCall()` 为真把 videoState 强制写成 `VideoStateType::TYPE_VOICE` 的判定）；`WriteCallAttributeInfo(info, messageParcel)` 把 `CallAttributeInfo` 逐字段序列化（accountNumber/bundleName/speakerphoneOn/accountId/videoState/startTime/isEcc/callType/callId/callState/conferenceState/各时间戳/index/crsType/originalCallType/numberLocation/numberMarkInfo/contactName/extraParamsString，`TYPE_VOIP` 时追加 voipCallInfo 全字段与 `WriteUInt8Vector(userProfile)`，末尾写 `phoneOrWatch`）——函数本体照抄保留（liteOS 直调回报不再经其组包，见 call-report delta「应用回报 IPC 封装」条；序列化字段面保留供测试与后续恢复使用）；`IsBundleInstalled(bundleName, userId)`——原经 samgr 取 `BUNDLE_MGR_SERVICE_SYS_ABILITY_ID` 的 `AppExecFwk::IBundleMgr` 代理查询的 ability 查询出口经 `stub/` 打桩并标注 `// todo!!! [callUi] ref to call_manager_utils.cpp IsBundleInstalled`（桩默认返回不可用、`IsBundleInstalled` 走返回 false 分支，与基线"samgr 或代理为空"语义一致）。

#### Scenario: 强制语音上报
- **WHEN** 通话为来电态且该 `CallBase` 要求强制语音上报
- **THEN** 序列化的 videoState 字段写 `TYPE_VOICE` 而非真实视频态（照抄）

#### Scenario: VOIP 扩展字段
- **WHEN** info.callType 为 `TYPE_VOIP`
- **THEN** 序列化追加 voipCallInfo 段（voipCallId、userName、abilityName、extensionId、voipBundleName 等 11 项）（照抄；VoIP 冲突链保留，AGENTS「暂不支持 VOIP……解决畅连通话和蜂窝通话冲突场景」）

#### Scenario: BundleMgr 不可用
- **WHEN** [callUi] 桩默认不可用（基线为 samgr 或 BUNDLE_MGR 代理为空）
- **THEN** `IsBundleInstalled` 返回 false（照抄；基线调用方 `call_records_manager.cpp` 的 ANTIFRAUD_CENTER_BUNDLE_NAME/BEST_MIND_BUNDLE_NAME 安装检测分支随防诈能力删除，见 call-status-management delta REMOVED 条）

### Requirement: 设置项 DataShare 读写助手
系统 SHALL 照抄保留 `SettingsDataShareHelper`（DelayedSingleton，`utils/src/settings_datashare_helper.cpp`）对 URI `datashare:///com.ohos.settingsdata/entry/settingsdata/SETTINGSDATA?Proxy=true`（扩展 URI `datashare:///com.ohos.settingsdata.DataAbility`，列 `KEYWORD`/`VALUE`）的读写逻辑：`Query`（EqualTo KEYWORD 过滤，rowCount 为 0 返回 `TELEPHONY_ERR_UNINIT`）、`Insert`（成功后 `NotifyChange`）、`Update`（先 Query 判存在，不存在转 Insert 的 upsert）与 `RegisterToDataShare`/`UnRegisterToDataShare`（注册/注销 `AAFwk::IDataAbilityObserver`）全部照抄；`DataShare::DataShareHelper::Creator` / `Release` / `NotifyChange` / 注册注销调用点标注 `// todo!!! [database] ref to settings_datashare_helper.cpp Query/Insert/Update/RegisterToDataShare/UnRegisterToDataShare`（AGENTS：数据库暂不调用，逻辑保留）。预置键常量处置：卫星键 `QUERY_SATELLITE_MODE_KEY`("satellite_mode_switch")、`QUERY_SATELLITE_CONNECTED_KEY`("satellite_connected") 保留（卫星通话功能已删但查询逻辑保留 todo 形态照抄，已定裁决）；`wear_status` 消费键保留（佩戴判定链保留，design D9）；运动键 `QUERY_MOTION_FLIP_MUTE_KEY`("motion_flip_mute_call")、`QUERY_MOTION_CLOSE_TO_EAR_KEY`("motion_quick_answer")、`QUERY_MOTION_PICKUP_REDUCE_KEY`("motion_pickup_reduce_call") 及其消费判定链随运动识别能力移除（见本 delta REMOVED「运动识别与运动插件装载」条与 call-status-management delta「动作识别订阅联动」条）。

#### Scenario: 键不存在
- **WHEN** `Query` 命中 0 行（经桩注入）
- **THEN** 返回 `TELEPHONY_ERR_UNINIT` 而非成功（照抄）

#### Scenario: 更新转为插入
- **WHEN** `Update` 前置 `Query` 返回非 0（键不存在）
- **THEN** 内部转调 `Insert` 完成 upsert 语义（照抄）

#### Scenario: 卫星模式消费方
- **WHEN** 查询方（基线消费方 `services/satellite_call/src/satellite_call_control.cpp` 已随卫星通话能力删除；经桩注入查询）查询 `QUERY_SATELLITE_MODE_KEY` / `QUERY_SATELLITE_CONNECTED_KEY`
- **THEN** 经本助手逻辑从 settingsdata 读取布尔值（查询出口 todo [database]；键常量与查询逻辑保留照抄）

### Requirement: 来电/通话系统对话框拉起
系统 SHALL 照抄保留 `CallDialog`（`utils/src/call_dialog.cpp`，DelayedSingleton 使用方）的对话框组装与连接拉起逻辑：命令体由 nlohmann::json 构造（`ability.want.params.uiExtensionType`="sysDialog/common"、`sysDialogZOrder`、`dialogReason`、`slotId` 等字段）照抄；`DialogConnectExtension(dialogReason[, slotId])` 入口面保留——dialogReason 含 "SATELLITE" 时走 `CallSettingAbilityConnection`、否则走 `CallAbilityConnection` 的分流保留（已定裁决：卫星对话框消费方 `satellite_call_control.cpp` 已随卫星通话删除，分流与连接逻辑保留照抄；保留消费方如 `call_policy.cpp` 的 "CALL_FAILED_NO_SIM_CARD"/"CALL_FAILED_IN_AIRPLANE_MODE"/"CALL_FAILED_NO_SERVICE"/"CALL_FAILED_CTCARD_NO_IMS"、`call_request_process.cpp` 的 "CALL_FAILED_DUE_TO_FDN"）；`DialogProcessMMICodeExtension`（"PROCESS_MMI_CODE"，`sysDialogZOrder` 用 `SCB_SYS_DIALOG_ZORDER_UNDER_LOCK`=1，`call_request_process.cpp` 消费）保留（补充业务 MMI 支持，AGENTS 特性宏说明 1）；`AAFwk::ExtensionManagerClient::ConnectServiceExtensionAbility` 连接调用点经 `stub/` 打桩并标注 `// todo!!! [callUi] ref to call_dialog.cpp DialogConnectExtension`（AGENTS：拉起通话界面对应外部依赖接口通过打桩实现）；原 `IPCSkeleton::ResetCallingIdentity`/`SetCallingIdentity` 包夹随 IPC 层不迁移移除。因超级隐私与折叠屏不支持（AGENTS 功能范围；`call_superprivacy_control_manager.cpp`、`fold_status_manager.cpp` 删除，design D7），`DialogConnectPrivpacyModeExtension` / `DialogConnectAnswerPrivpacyModeExtension`（"SUPER_PRIVACY_MODE"）与 `DialogCallingPrivacyModeExtension`（`FoldStatusManager::IsSmallFoldDevice()` / `Rosen::DisplayManager::GetFoldStatus()==FOLDED` 判定）三入口删除。

#### Scenario: 普通失败原因对话框
- **WHEN** `DialogConnectExtension` 的 reason 不含 "SATELLITE"
- **THEN** 经 `CallAbilityConnection` 连接 sceneboard systemdialog（[callUi] 桩出口），连接结果非 0 时返回 false（照抄）

#### Scenario: 卫星对话框分流
- **WHEN** reason 含 "SATELLITE"
- **THEN** 改经 `CallSettingAbilityConnection` 发起连接（分流与连接逻辑保留照抄；基线卫星侧消费方已随卫星通话删除，liteOS 上该分流无真实触发方）

#### Scenario: 超级隐私折叠来电
- **WHEN** 基线折叠态为 `FOLDED` 且当前处于超级隐私模式且存在非来电态前台通话
- **THEN** 因超级隐私与折叠屏不支持，"SUPER_PRIVACY_MODE" 对话框三入口已删除，liteOS 上无该对话框拉起路径

### Requirement: Ability 连接回调发参
系统 SHALL 照抄保留 `CallAbilityConnection` 与 `CallSettingAbilityConnection`（`utils/src/call_ability_connection.cpp`、`utils/src/call_setting_ability_connection.cpp`）的回调形态：`OnAbilityConnectDone` 中把构造时保存的 commandStr 通过 `remoteObject->SendRequest(AAFwk::IAbilityConnection::ON_ABILITY_CONNECT_DONE, ...)` 回发给被连 uiAbility 的交互调用点经 `stub/` 打桩并标注 `// todo!!! [callUi] ref to call_ability_connection.cpp OnAbilityConnectDone`（CallUIAbility/对话框 ability 交互出口打桩，AGENTS：拉起通话界面通过打桩实现）；`CallAbilityConnection` 固定携带 bundleName "com.ohos.callui"、abilityName "com.ohos.callui.CallFailedDialogAbility"，`CallSettingAbilityConnection` 携带 bundleName "com.callsetting"、abilityName "com.callsetting.SatelliteCallDialogAbility"，参数计数 `PARAM_NUM`=3（bundleName/abilityName/parameters 三键值对）照抄；remoteObject 为空时仅打日志、`OnAbilityDisconnectDone` 仅记日志照抄。

#### Scenario: 连接成功回发命令
- **WHEN** sceneboard 连接成功回调 `OnAbilityConnectDone`（经 [callUi] 桩注入驱动）
- **THEN** 以 MessageParcel 写入 3 组键值（含 commandStr）并回发 `SendRequest(ON_ABILITY_CONNECT_DONE)`（桩出口，语义照抄）

#### Scenario: 远端对象缺失
- **WHEN** 回调的 remoteObject 为空
- **THEN** 不发送任何 `SendRequest`，仅记录日志（照抄）
