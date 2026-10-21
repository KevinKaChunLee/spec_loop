# call-state-observer Specification

## Purpose
描述 `telephony_call_manager`（OpenHarmony v6.0 快照）中 `services/call/call_state_observer/` 子模块的移植前现状：来电/通话结束后触发的周边行为（通知、通话记录入库、拒接短信、亮屏与防熄屏、贴耳灭屏、状态栏图标、有线耳机消息），全部实现为 `CallStateListenerBase` 的观察者并经 `CallStateListener` 总线接收回调（总线本身在 `call-status-management` 能力中定义）。源码落点（src/ 与 include/ 同名配对）：`incoming_call_notification.cpp`、`missed_call_notification.cpp`、`call_records_manager.cpp`、`call_records_handler.cpp`、`call_data_base_helper.cpp`、`call_data_base_helper.h` 中的 `CallDataRdbObserver`、`reject_call_sms.cpp`、`incoming_call_wake_up.cpp`、`proximity_sensor.cpp`、`status_bar.cpp`、`wired_headset.cpp`。每个文件都是外部系统接口消费者：DataShare（calllog/contacts/settings）、通知（`Notification::NotificationHelper`）、公共事件（`EventFwk::CommonEventManager`）、电源（`PowerMgr::PowerMgrClient`）、短信（`SmsServiceManagerClient`）、状态栏/媒体按键。

控制本能力行为的构建开关（逐宏 rg 核实）：
- `ABILITY_SMS_SUPPORT`：`callmanager.gni` 在部件 `telephony_sms_mms` 存在时定义；场点 `reject_call_sms.h:20`/`reject_call_sms.cpp:37`（`SendMessage` 调 `SmsServiceManagerClient::SendMessage`）。
- `ABILITY_POWER_SUPPORT`：`callmanager.gni` 在部件 `powermgr_power_manager` 存在时定义；场点 `incoming_call_wake_up.h`/`incoming_call_wake_up.cpp`（运行锁/亮屏 4 处）、`proximity_sensor.h/cpp`（`ShutDown`/`StartUp`）。
- `TELEPHONY_CUST_SUPPORT`：`callmanager.gni` 在部件 `telephony_telephony_enhanced` 存在时定义；场点 `call_data_base_helper.h:105`、`call_data_base_helper.cpp:451`（联系人增强查询 + `dlopen` cust so）。
- `SUPPORT_MUTE_BY_DATABASE`：`callmanager.gni` 仅在 `target_platform == "watch"` 时定义；场点 `call_records_manager.cpp:30`（include `interoperable_settings_handler.h`）与 `:469`（`COMMON_EVENT_DATA_SHARE_READY` 时 `InteroperableSettingsHandler::RegisterObserver()`）。
- `ABILITY_NOTIFICATION_SUPPORT`：场点 `incoming_call_notification.cpp:101`；本仓 gni/BUILD 未定义，默认构建下取消通知为空操作。
- `ABILITY_DISPLAY_SUPPORT`：场点 `incoming_call_notification.cpp:109`；本仓未定义，`IsFullScreen()` 恒返回 false，来电全屏通知在默认构建下从不发布。
- `ABILITY_STATUS_BAR_CONTROL_SUPPORT`：场点 `status_bar.cpp:31/46`；本仓未定义，图标操作分支默认不编译（且该分支引用本仓未定义的 `statusBarControl`/`isDisplaySpeakerphone` 符号）。
- `ABILITY_MEDIA_SUPPORT`：场点 `wired_headset.cpp:61`；本仓未定义，耳机按键处理分支默认不编译（且该分支引用本仓未定义的 `callsManager.onButtonDealing`）。

## Requirements

### Requirement: 来电全屏通知（incoming_call_notification）
系统 SHALL 由 `IncomingCallNotification` 在来电建立（`NewCallCreated`，状态 `CALL_STATUS_INCOMING` 且号码非空）时记录号码并尝试发布全屏通知；同一号码离开来电状态时撤销该通知。

#### Scenario: 发布被全屏判定门控
- **WHEN** `NewCallCreated` 触发，号码记入 `incomingCallNumber_` 后进入 `PublishIncomingCallNotification`
- **THEN** `IsFullScreen()`（`ABILITY_DISPLAY_SUPPORT` 下调 `DisplayManager::IsFullScreen`，默认构建恒 false）为假时直接返回、不发布；宏生效时以标题 `INCOMING_CALL_NOTIFICATION_TITLE`("Incoming Call")、正文为来电号码组装 `NotificationNormalContent`/`NotificationContent`，`NotificationRequest` 置 `INCOMING_CALL_NOTIFICATION_ID`(0) 后经 `Notification::NotificationHelper::PublishNotification` 发布

#### Scenario: 撤销通知
- **WHEN** `CallStateUpdated`（前态 INCOMING）、`IncomingCallActivated` 或 `IncomingCallHungUp` 中号码等于 `incomingCallNumber_`
- **THEN** `CancelIncomingCallNotification`：`ABILITY_NOTIFICATION_SUPPORT` 下调 `NotificationHelper::CancelNotification(INCOMING_CALL_NOTIFICATION_ID)`，否则恒返回 `TELEPHONY_SUCCESS`；非来电建链场景 `incomingCallNumber_` 被清空

### Requirement: 未接来电公共事件（missed_call_notification）
系统 SHALL 由 `MissedCallNotification` 在未接/拦截通话结束时发布 `COMMON_EVENT_INCOMING_CALL_MISSED` 有序公共事件，并为读侧提供未接提醒能力。

#### Scenario: 未接判定与发布门槛
- **WHEN** `CallStateUpdated` 且新态为 `CALL_STATUS_DISCONNECTED`、方向为 `CALL_DIRECTION_IN`、`answerType` 为 `CALL_ANSWER_MISSED` 或（`CALL_ANSWER_ACTIVED` 且 `IsAiAutoAnswer`），且 `OsAccountManager::IsOsAccountVerified` 为真
- **THEN** VOIP 通话直接排除；满足条件时 `PublishMissedCallEvent` 发布两条有序事件（`SetOrdered(true)`）：不带号码（callId + `notificationId`=`INCOMING_CALL_MISSED_ID`(0)，code=`INCOMING_CALL_MISSED_CODE`(0)）与带号码（`phoneNumber`/data 为号码，订阅权限限定 `Permission::GET_TELEPHONY_STATE`）

#### Scenario: 拦截通话事件
- **WHEN** `PublishBlockedCallEvent` 被 `CallControlManager::AddBlockLogAndNotification` 触发
- **THEN** 事件额外携带 `isBlocked=true` 与 `detectDetails`，订阅权限限定 `GET_TELEPHONY_STATE`

#### Scenario: 未接提醒聚合
- **WHEN** `NotifyUnReadMissedCall` 收到号码-未接数映射 `phoneNumAndUnreadCountMap`
- **THEN** 以 `phoneNumberList`/`countList` 参数发布 `COMMON_EVENT_INCOMING_CALL_MISSED`；发布失败返回 `TELEPHONY_ERR_PUBLISH_BROADCAST_FAIL`

### Requirement: 通话记录入库（call_records_manager）
系统 SHALL 由 `CallRecordsManager` 在非 VOIP 通话结束时把 `CallAttributeInfo` 组装为 `CallRecordInfo` 并经 `CallRecordsHandlerService::StoreCallRecord` 异步入库（`ffrt::submit`）。

#### Scenario: 组装前的修正
- **WHEN** `CallStateUpdated` 收到 DISCONNECTED
- **THEN** 联系人名与设置名不一致时置 `namePresentation=1` 否则 0；`MARK_TYPE_DEFAULT` 归一为 `MARK_TYPE_NONE`；来电 + AI 自动接听改记 `CALL_ANSWER_MISSED`；`GetNewCallUseBox` 写 `newCallUseBox`

#### Scenario: cust 过滤
- **WHEN** `TELEPHONY_CUST_WRAPPER.isHideViolenceOrEmcNumbersInCallLog_` 非空且对该记录返回真
- **THEN** 记录被隐藏不入库

#### Scenario: 号码格式化与字段填充
- **WHEN** `AddOneCallRecord(CallAttributeInfo)` 组装记录
- **THEN** `GetCountryIso` 读系统参数 `telephony.operator.iso-country`（空则默认 "CN"）；号码含 ","/";" 时 `FormatPhoneNumberAsYouType` 否则 `FormatPhoneNumber` 填 `formattedNumber`；`FormatPhoneNumberToE164` 填 `formattedNumberToE164`；`CopyCallInfoToRecord` 填时长（`difftime` 计算 `callDuration`/`ringDuration`）、方向、answerType、`features`（`GetCallFeatures`：`TYPE_SEND_ONLY`/`TYPE_VIDEO` 置位）、标记信息、`blockReason`、`celiaCallType`；`markSource` 为反诈中心("5") 时经 `GetNumberMarkSource` 依反诈/身份识别设置开关与 `CallManagerUtils::IsBundleInstalled` 重判来源

#### Scenario: 就绪条件联动
- **WHEN** `Init` 启动 `CallRecordsHandlerService`、订阅账号管理 SA（`SUBSYS_ACCOUNT_SYS_ABILITY_ID_BEGIN`，`AccountSystemAbilityListener::OnAddSystemAbility`）与 `COMMON_EVENT_DATA_SHARE_READY`（`DataShareReadyEventSubscriber`）
- **THEN** DATA_SHARE_READY 置 `SetDataShareReady(true)` 并触发各观察者注册（`LocationSystemAbilityListener::SystemAbilitySubscriber`、`CallControlManager::RegisterObserver`、`CallStatusManager::RegisterObserver`；`SUPPORT_MUTE_BY_DATABASE` 下另有 `InteroperableSettingsHandler::RegisterObserver`）；活动用户为 `ACTIVE_USER_ID`(100) 时 `QueryUnReadMissedCallLog`，否则改订 `COMMON_EVENT_USER_SWITCHED` 后在新用户到达时查询；查询受 `isDataShareReady_`/`isSystemAbilityAdd_`/`isUnReadMissedCallLogQuery_` 三标志门控

### Requirement: 记录写库与限量清理（call_records_handler）
系统 SHALL 由 `CallRecordsHandler` 将 `CallRecordInfo` 转 DataShare 插入桶写入通话记录库，并做数量限清理；`CallRecordsHandlerService` 以 `ffrt::submit` 包裹执行。

#### Scenario: 插入
- **WHEN** `AddCallLogInfo` 组装 `MakeCallLogInsertBucket`（`CALL_PHONE_NUMBER`/`CALL_DISPLAY_NAME`/`CALL_DIRECTION`/`CALL_IS_READ`(0)/`CALL_RING_DURATION`/`CALL_TALK_DURATION`/`CALL_FORMAT_NUMBER`/`CALL_BEGIN_TIME`/`CALL_END_TIME`/`CALL_ANSWER_STATE`/`CALL_CREATE_TIME`/`CALL_NUMBER_LOCATION`/`CALL_SLOT_ID`/`CALL_FEATURES`/`CALL_IS_CNAP`/`CALL_USE_NEWCALLBOX` 等）并 `CallDataBaseHelper::Insert`
- **THEN** 显示名规则：黄页标记且非云端（`MARK_TYPE_YELLOW_PAGE` 且 `!isCloud`）用 `markContent` 否则用联系人名；归属地为 "default" 时经 `QueryNumberLocationInfo` 重查，空则填 "N"；插入失败返回 `TELEPHONY_ERR_DATABASE_WRITE_FAIL`

#### Scenario: 限量清理
- **WHEN** 插入成功后 `DeleteCallLogForLimit` 构造谓词（`CALL_ANSWER_BLOCKED` 记录单列，其余 `NotEqualTo` 分列）、按 `CALL_CREATE_TIME` 倒序 `Limit(-1, LOG_LIMIT_NUM)`(5000)
- **THEN** `CallDataBaseHelper::QueryAndDeleteLimitedIds` 查出超量记录并逐条 `Delete`

#### Scenario: 未接查询与广播
- **WHEN** `QueryAndNotifyUnReadMissedCall` 以 `CALL_IS_UNREAD` + `CALL_DIRECTION_IN` + `CALL_ANSWER_MISSED` 谓词 `QueryCallLog`
- **THEN** 得到号码-未接数映射后交 `MissedCallNotification::NotifyUnReadMissedCall` 广播；无未接记录或查询失败返回 `TELEPHONY_ERR_DATABASE_READ_FAIL`

#### Scenario: 未接记录置已读
- **WHEN** `CallRecordsHandlerService::RemoveMissedIncomingCallNotification` 被触发
- **THEN** 以 `CALL_IS_READ`=`CALL_LOG_READ_STATE::CALL_IS_READ` 为值、未读来电未接为条件执行 `CallDataBaseHelper::Update`；注意：该函数把 `Update` 返回 true 记为失败（`TELEPHONY_ERR_DATABASE_WRITE_FAIL`），与底层"true 表示成功"的语义相反，为上游现状疑点

### Requirement: DataShare 数据库助手（call_data_base_helper）
系统 SHALL 由 `CallDataBaseHelper` 统一包装通话记录/联系人/设置项的 DataShare 访问：经 samgr 取 `TELEPHONY_CALL_MANAGER_SYS_ABILITY_ID` token 后 `DataShareHelper::Creator`（settings URI 附 `SETTINGS_DATA_EXT_URI` 扩展，其余带 `MAX_WAITIME_TIME`(10s)）；通话记录随用户解锁状态在 `CALLLOG_URI`("datashare:///com.ohos.calllogability") + `CALL_SUBSECTION` 与 `CALL_SUBSECTION_SILENCE`（未解锁代理通道，追加 userId）之间切换（`GetHelperAndUrl`）。

#### Scenario: 联系人查询
- **WHEN** `Query(ContactInfo, predicates)` 以 `CONTACT_DATA` URI 查询
- **THEN** `CheckResultSet` 判非空后读取 `CALL_DISPLAY_NAME`、`PERSONAL_RINGTONE`、`PERSONAL_NOTIFICATION_RINGTONE`（按 `FILE_PATH_MAX_LEN` 截断拷贝）；行集为空/失败返回 false

#### Scenario: 增强的联系人查询（cust）
- **WHEN** 宏 `TELEPHONY_CUST_SUPPORT` 生效且走 `QueryContactInfoEnhanced`
- **THEN** `GetCallerIndex` 经 `dlopen("libtelephony_cust_api.z.so")`（`TELEPHONY_CUST_SO_PATH`）解析符号 `GetCallerNumIndex` 选出目标行再读同名列；so 加载或符号解析失败返回 -1（首行）

#### Scenario: 通话记录查询/增删改
- **WHEN** 调用 `Insert`/`Update`/`Delete`/`QueryCallLog`（按号码聚合 `CALL_LOG_DEFAULT_COUNT`(1)）/`QueryAndDeleteLimitedIds`/`QueryIsBlockPhoneNumber`
- **THEN** 全部按上述 URI 族与 `CALL_BLOCK`("…contacts/contact_blocklist")、`CONTACT_URI` 完成；`QueryIsBlockPhoneNumber` 以国家/国际两种格式（`FormatPhoneNumberToNational`/`FormatPhoneNumberToInternational`，失败回退原号）双匹配黑名单

#### Scenario: 屏蔽名单观察
- **WHEN** `RegisterObserver(phones)` 在 `CALL_BLOCK` 上挂 `CallDataRdbObserver`
- **THEN** `OnChange` 重新 `Query(phones)`（`phone_number` 非空谓词）刷新屏蔽号码列表；`UnRegisterObserver` 反注册

#### Scenario: 飞行模式查询
- **WHEN** `GetAirplaneMode` 查 `SETTINGS_AIRPLANE_MODE_URI`
- **THEN** 以列 `SETTING_KEY`("KEYWORD") 等于 `SETTINGS_AIRPLANE_MODE`（"settings.telephony.airplanemode"）为谓词读取 `SETTING_VALUE`("VALUE") 列，"1" 即飞行模式开

### Requirement: 拒接短信（reject_call_sms）
系统 SHALL 由 `RejectCallSms` 在带短信拒接（`IncomingCallHungUp`）时向对方发送用户配置的拒接短信。

#### Scenario: 发送条件
- **WHEN** `IncomingCallHungUp` 的 `isSendSms` 为真、`content` 与通话号码 `GetAccountNumber` 均非空
- **THEN** `SendMessage`（`ConvertToUtf16` 转码）经 `Singleton<SmsServiceManagerClient>::SendMessage(slotId, desAddr, "", text, nullptr, nullptr)` 发送；`ABILITY_SMS_SUPPORT` 未定义时不发送仅记录；条件不满足直接返回

### Requirement: 来电亮屏与运行锁（incoming_call_wake_up）
系统 SHALL 由 `IncomingCallWakeup` 在来电时持运行锁防休眠（`ABILITY_POWER_SUPPORT` 下经 `PowerMgr::PowerMgrClient::CreateRunningLock`），并在通话结束后释放。

#### Scenario: 亮屏与防熄屏
- **WHEN** `NewCallCreated` 收到 INCOMING 通话并进入 `WakeupDevice`
- **THEN** 先后创建并 Lock "phonerunninglock"（`RUNNINGLOCK_BACKGROUND_PHONE`）与 "screenonrunninglock"（`RUNNINGLOCK_SCREEN`），各自以 `isPhoneLocked`/`isScreenOnLocked` 去重；VOIP 通话额外 `WakeupDevice(WAKEUP_DEVICE_APPLICATION, wakeupReason_="incoming call")` 点亮屏幕

#### Scenario: 来电期专用锁
- **WHEN** `CallControlManager::AcquireIncomingLock`/`ReleaseIncomingLock` 包夹 `CallStatusManager::IncomingHandle`
- **THEN** 分别以 `INCOMING_LOCK_TIMEOUT`(6000ms) 时长 Lock / 检查 `IsUsed` 后 UnLock "incomingrunninglock"

#### Scenario: 解锁释放
- **WHEN** `CallStateUpdated` 时 `CallObjectManager::HasRingingCall(hasRingCall)` 为假且两个锁标志在位
- **THEN** 依次 UnLock screenRunningLock_ 与 phoneRunningLock_ 并清标志；`IsPowerAbilityExist` 经 samgr 检查 `POWER_MANAGER_SERVICE_ID` 可用性作为前置门检

### Requirement: 贴耳灭屏（proximity_sensor）
系统 SHALL 由 `ProximitySensor` 在通话对象销毁时联动电源管理（`ABILITY_POWER_SUPPORT`）。

#### Scenario: 剩余通话时灭屏
- **WHEN** `CallDestroyed` 且 `CallObjectManager::HasCallExist()` 为真
- **THEN** `ShutDown(SUSPEND_DEVICE_REASON_APPLICATION, true)` 立即熄屏；`HasCallExist()` 为假时不做电源操作（为上游现状语义，疑与常规预期相反）；`StartUp`（`WakeupDevice`）仅在宏生效时可被调用

### Requirement: 状态栏静音图标（status_bar）
系统 SHALL 由 `StatusBar` 以 `isDisplayMute_`/`isDisplayIcon_` 状态去重地展示/隐藏静音与扬声器图标，并在通话销毁时复位。

#### Scenario: 图标切换
- **WHEN** `UpdateMuteIcon`/`UpdateSpeakerphoneIcon` 的目标值不同
- **THEN** 宏 `ABILITY_STATUS_BAR_CONTROL_SUPPORT` 生效时对 "Mute"/"Speakerphone" 图标执行 `setIcon`/`removeIcon`；默认构建（宏未定义）仅更新内部状态不触碰状态栏

#### Scenario: 通话销毁复位
- **WHEN** `CallDestroyed`
- **THEN** `UpdateMuteIcon(false)` 与 `UpdateSpeakerphoneIcon(false)` 复位

#### Scenario: 默认构建的边界
- **WHEN** 默认构建编译本文件
- **THEN** 图标分支不编译才能通过编译：宏开启分支引用本仓未定义的 `statusBarControl` 与 `isDisplaySpeakerphone` 符号，属于上游死分支现状

### Requirement: 有线耳机消息处理（wired_headset）
系统 SHALL 由 `WiredHeadsetHandler`（`AppExecFwk::EventHandler`）接收 `WiredHeadset` 的媒体事件常量（`MEDIA_INITIALIZE_MSG`/`MEDIA_SET_ACTIVE_MSG`/`MEDIA_SET_LEAVE_MSG`），在通话建立/销毁时向 handler 投递激活/离开发送事件。

#### Scenario: 通话联动投递
- **WHEN** `NewCallCreated` 或 `CallDestroyed`
- **THEN** handler_ 非空时分别 `SendEvent(MEDIA_SET_ACTIVE_MSG)` / `SendEvent(MEDIA_SET_LEAVE_MSG)`；`ProcessEvent` 对三类事件的处理体均为空占位

#### Scenario: 耳机按键分支为死分支
- **WHEN** 默认构建（`ABILITY_MEDIA_SUPPORT` 未定义）
- **THEN** `ButtonEventhandling`（短/长按键分发 `callsManager.onButtonDealing`）不参与编译；该分支引用的 `callsManager`/`ButtonEvent::SHORT_PRESS` 等均不在本仓定义