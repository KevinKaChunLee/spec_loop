# Spec Delta

## MODIFIED Requirements

### Requirement: 来电全屏通知（incoming_call_notification）
系统 SHALL 由 `IncomingCallNotification` 在来电建立（`NewCallCreated`，状态 `CALL_STATUS_INCOMING` 且号码非空）时记录号码并尝试发布全屏通知；同一号码离开来电状态时撤销该通知。通知逻辑保留，`Notification::NotificationHelper` 发布/撤销调用点以 `// todo!!! [notification] ref to incoming_call_notification.cpp` 占位（发布不出去时的置位/记录行为照抄，桩返回失败/不可用语义）；因 `ABILITY_DISPLAY_SUPPORT`/`ABILITY_NOTIFICATION_SUPPORT` 均为不支持宏（AGENTS 特性宏支持范围），宏守卫去守卫处理：`DisplayManager::IsFullScreen` 调用不迁移、`IsFullScreen()` 恒返回 false（等价基线默认构建）。

#### Scenario: 发布被全屏判定门控
- **WHEN** `NewCallCreated` 触发，号码记入 `incomingCallNumber_` 后进入 `PublishIncomingCallNotification`
- **THEN** `IsFullScreen()` 在 liteOS 上恒返回 false（`ABILITY_DISPLAY_SUPPORT` 不支持，等价基线默认构建），发布分支不触发；通知组装逻辑（标题 `INCOMING_CALL_NOTIFICATION_TITLE`("Incoming Call")、正文为来电号码、`NotificationRequest` 置 `INCOMING_CALL_NOTIFICATION_ID`(0)）保留，`NotificationHelper::PublishNotification` 调用点 todo [notification]，发布失败时的记录/置位行为照抄基线

#### Scenario: 撤销通知
- **WHEN** `CallStateUpdated`（前态 INCOMING）、`IncomingCallActivated` 或 `IncomingCallHungUp` 中号码等于 `incomingCallNumber_`
- **THEN** `CancelIncomingCallNotification`：`NotificationHelper::CancelNotification(INCOMING_CALL_NOTIFICATION_ID)` 调用点 todo [notification]（`ABILITY_NOTIFICATION_SUPPORT` 去守卫，逻辑保留），不可用时按失败分支记录日志的行为照抄；非来电建链场景 `incomingCallNumber_` 被清空

### Requirement: 未接来电公共事件（missed_call_notification）
系统 SHALL 由 `MissedCallNotification` 在未接/拦截通话结束时发布 `COMMON_EVENT_INCOMING_CALL_MISSED` 有序公共事件，并为读侧提供未接提醒能力。发布逻辑保留，`EventFwk::CommonEventManager` 发布调用点以 `// todo!!! [broadcast] ref to missed_call_notification.cpp` 占位（发布失败返回 `TELEPHONY_ERR_PUBLISH_BROADCAST_FAIL` 的行为照抄，桩返回失败/不可用语义）；帐号校验按 liteOS 单主帐号精简为默认主帐号常量（分支结构保留）。

#### Scenario: 未接判定与发布门槛
- **WHEN** `CallStateUpdated` 且新态为 `CALL_STATUS_DISCONNECTED`、方向为 `CALL_DIRECTION_IN`、`answerType` 为 `CALL_ANSWER_MISSED` 或（`CALL_ANSWER_ACTIVED` 且 `IsAiAutoAnswer`），且帐号校验（默认主帐号常量）通过
- **THEN** VOIP 通话直接排除；满足条件时 `PublishMissedCallEvent` 发布两条有序事件（`SetOrdered(true)`，发布调用点 todo [broadcast]）：不带号码（callId + `notificationId`=`INCOMING_CALL_MISSED_ID`(0)，code=`INCOMING_CALL_MISSED_CODE`(0)）与带号码（`phoneNumber`/data 为号码，订阅权限限定 `Permission::GET_TELEPHONY_STATE` 参数照抄）

#### Scenario: 拦截通话事件
- **WHEN** `PublishBlockedCallEvent` 被 `CallControlManager::AddBlockLogAndNotification` 触发
- **THEN** 事件额外携带 `isBlocked=true` 与 `detectDetails`，订阅权限限定 `GET_TELEPHONY_STATE`（发布调用点 todo [broadcast]）

#### Scenario: 未接提醒聚合
- **WHEN** `NotifyUnReadMissedCall` 收到号码-未接数映射 `phoneNumAndUnreadCountMap`
- **THEN** 以 `phoneNumberList`/`countList` 参数发布 `COMMON_EVENT_INCOMING_CALL_MISSED`（发布调用点 todo [broadcast]）；发布失败返回 `TELEPHONY_ERR_PUBLISH_BROADCAST_FAIL`

### Requirement: 通话记录入库（call_records_manager）
系统 SHALL 由 `CallRecordsManager` 在非 VOIP 通话结束时把 `CallAttributeInfo` 组装为 `CallRecordInfo` 并经 `CallRecordsHandlerService::StoreCallRecord` 异步入库（原 `ffrt::submit` 改经打桩 EventHandler 提交，`stub/eventhandler_stub`）。因 `SUPPORT_MUTE_BY_DATABASE` 为不支持宏（AGENTS 特性宏支持范围），其守卫分支删除（`InteroperableSettingsHandler::RegisterObserver` 不迁移），全库走默认静音路径；`TELEPHONY_CUST_WRAPPER` cust 过滤出口改经 `TelephonyCustClient::GetInstance()` 桩（不再 dlopen）；samgr 宿主订阅不迁移、按默认主帐号就位处理。

#### Scenario: 组装前的修正
- **WHEN** `CallStateUpdated` 收到 DISCONNECTED
- **THEN** 联系人名与设置名不一致时置 `namePresentation=1` 否则 0；`MARK_TYPE_DEFAULT` 归一为 `MARK_TYPE_NONE`；来电 + AI 自动接听改记 `CALL_ANSWER_MISSED`；`GetNewCallUseBox` 写 `newCallUseBox`

#### Scenario: cust 过滤
- **WHEN** `TELEPHONY_CUST_WRAPPER.isHideViolenceOrEmcNumbersInCallLog_` 非空且对该记录返回真（`TELEPHONY_CUST_SUPPORT` 增强查询分支保留，出口经 TelephonyCustClient 桩）
- **THEN** 记录被隐藏不入库

#### Scenario: 号码格式化与字段填充
- **WHEN** `AddOneCallRecord(CallAttributeInfo)` 组装记录
- **THEN** `GetCountryIso` 读系统参数 `telephony.operator.iso-country`（系统参数桩，空则默认 "CN"）；号码含 ","/";" 时 `FormatPhoneNumberAsYouType` 否则 `FormatPhoneNumber`（libphonenumber 桩）填 `formattedNumber`；`FormatPhoneNumberToE164` 填 `formattedNumberToE164`；`CopyCallInfoToRecord` 填时长（`difftime` 计算 `callDuration`/`ringDuration`）、方向、answerType、`features`（`GetCallFeatures`：`TYPE_SEND_ONLY`/`TYPE_VIDEO` 置位）、标记信息、`blockReason`、`celiaCallType`；`markSource` 为 "5" 时的 `GetNumberMarkSource` 重判分支照抄保留（该标记值的产出来自已移除的防诈检测链，防诈能力不迁移后不再产生；分支主体为设置开关查询与 `CallManagerUtils::IsBundleInstalled` 判定，查询出口 todo [database]）

#### Scenario: 就绪条件联动
- **WHEN** `Init` 启动 `CallRecordsHandlerService` 并建立就绪联动（原 samgr 订阅账号管理 SA 的调用点不迁移，按 liteOS 单主帐号默认主帐号就位处理，`AccountSystemAbilityListener` 到达分支结构保留；`COMMON_EVENT_DATA_SHARE_READY` 订阅调用点 todo [broadcast]）
- **THEN** DATA_SHARE_READY 置 `SetDataShareReady(true)` 并触发各观察者注册（`LocationSystemAbilityListener::SystemAbilitySubscriber`、`CallControlManager::RegisterObserver`、`CallStatusManager::RegisterObserver`）；因 `SUPPORT_MUTE_BY_DATABASE` 不支持，原 `InteroperableSettingsHandler::RegisterObserver()` 守卫分支删除，全库走默认静音路径；活动用户为 `ACTIVE_USER_ID`(100) 时 `QueryUnReadMissedCallLog`，否则改订 `COMMON_EVENT_USER_SWITCHED`（订阅调用点 todo [broadcast]）后在新用户到达时查询；查询受 `isDataShareReady_`/`isSystemAbilityAdd_`/`isUnReadMissedCallLogQuery_` 三标志门控（`CallDataBaseHelper` 查询出口 todo [database]）

### Requirement: 记录写库与限量清理（call_records_handler）
系统 SHALL 由 `CallRecordsHandler` 将 `CallRecordInfo` 转 DataShare 插入桶写入通话记录库，并做数量限清理；`CallRecordsHandlerService` 以打桩 EventHandler（`stub/eventhandler_stub`）包裹执行（原 `ffrt::submit` 替换）。插入/限删 5000/已读置位逻辑保留，`CallDataBaseHelper` 全部 DataShare 调用点以 `// todo!!! [database] ref to call_records_handler.cpp` 占位。

#### Scenario: 插入
- **WHEN** `AddCallLogInfo` 组装 `MakeCallLogInsertBucket`（`CALL_PHONE_NUMBER`/`CALL_DISPLAY_NAME`/`CALL_DIRECTION`/`CALL_IS_READ`(0)/`CALL_RING_DURATION`/`CALL_TALK_DURATION`/`CALL_FORMAT_NUMBER`/`CALL_BEGIN_TIME`/`CALL_END_TIME`/`CALL_ANSWER_STATE`/`CALL_CREATE_TIME`/`CALL_NUMBER_LOCATION`/`CALL_SLOT_ID`/`CALL_FEATURES`/`CALL_IS_CNAP`/`CALL_USE_NEWCALLBOX` 等）并 `CallDataBaseHelper::Insert`（调用点 todo [database]）
- **THEN** 显示名规则：黄页标记且非云端（`MARK_TYPE_YELLOW_PAGE` 且 `!isCloud`）用 `markContent` 否则用联系人名；归属地为 "default" 时经 `QueryNumberLocationInfo` 重查（查询出口 todo [database]），空则填 "N"；插入失败返回 `TELEPHONY_ERR_DATABASE_WRITE_FAIL`

#### Scenario: 限量清理
- **WHEN** 插入成功后 `DeleteCallLogForLimit` 构造谓词（`CALL_ANSWER_BLOCKED` 记录单列，其余 `NotEqualTo` 分列）、按 `CALL_CREATE_TIME` 倒序 `Limit(-1, LOG_LIMIT_NUM)`(5000)
- **THEN** `CallDataBaseHelper::QueryAndDeleteLimitedIds` 查出超量记录并逐条 `Delete`（调用点 todo [database]），限删 5000 语义保留

#### Scenario: 未接查询与广播
- **WHEN** `QueryAndNotifyUnReadMissedCall` 以 `CALL_IS_UNREAD` + `CALL_DIRECTION_IN` + `CALL_ANSWER_MISSED` 谓词 `QueryCallLog`（调用点 todo [database]）
- **THEN** 得到号码-未接数映射后交 `MissedCallNotification::NotifyUnReadMissedCall` 广播（发布出口 todo [broadcast]）；无未接记录或查询失败返回 `TELEPHONY_ERR_DATABASE_READ_FAIL`

#### Scenario: 未接记录置已读
- **WHEN** `CallRecordsHandlerService::RemoveMissedIncomingCallNotification` 被触发
- **THEN** 以 `CALL_IS_READ`=`CALL_LOG_READ_STATE::CALL_IS_READ` 为值、未读来电未接为条件执行 `CallDataBaseHelper::Update`（调用点 todo [database]）；注明：与 HMOS 现状一致，该函数把 `Update` 返回 true 记为失败（`TELEPHONY_ERR_DATABASE_WRITE_FAIL`），与底层"true 表示成功"的语义相反，为上游现状疑点，按 AGENTS「代码逻辑与 HMOS 保持一致」照抄不改

### Requirement: DataShare 数据库助手（call_data_base_helper）
系统 SHALL 由 `CallDataBaseHelper` 统一包装通话记录/联系人/设置项的 DataShare 访问：经 samgr 取 `TELEPHONY_CALL_MANAGER_SYS_ABILITY_ID` token 后 `DataShareHelper::Creator` 的调用点以 `// todo!!! [database] ref to call_data_base_helper.cpp` 占位（逻辑保留，settings URI 附 `SETTINGS_DATA_EXT_URI` 扩展，其余带 `MAX_WAITIME_TIME`(10s) 照抄）；通话记录随用户解锁状态在 `CALLLOG_URI`("datashare:///com.ohos.calllogability") + `CALL_SUBSECTION` 与 `CALL_SUBSECTION_SILENCE`（未解锁代理通道，追加 userId）之间切换（`GetHelperAndUrl`）逻辑保留。`TELEPHONY_CUST_SUPPORT` 为支持宏，增强查询分支保留：原 `dlopen("libtelephony_cust_api.z.so")` 解析 `GetCallerNumIndex` 改经 `stub/telephony_cust_client.h/.cpp` 的 `TelephonyCustClient::GetInstance()` 桩（不再 dlopen）。

#### Scenario: 联系人查询
- **WHEN** `Query(ContactInfo, predicates)` 以 `CONTACT_DATA` URI 查询（调用点 todo [database]）
- **THEN** `CheckResultSet` 判非空后读取 `CALL_DISPLAY_NAME`、`PERSONAL_RINGTONE`、`PERSONAL_NOTIFICATION_RINGTONE`（按 `FILE_PATH_MAX_LEN` 截断拷贝）；行集为空/失败返回 false

#### Scenario: 增强的联系人查询（cust）
- **WHEN** 宏 `TELEPHONY_CUST_SUPPORT` 生效且走 `QueryContactInfoEnhanced`
- **THEN** `GetCallerIndex` 改经 `TelephonyCustClient::GetInstance()` 桩选出目标行再读同名列；调用失败返回 -1（首行）的语义照抄基线桩失败/不可用分支

#### Scenario: 通话记录查询/增删改
- **WHEN** 调用 `Insert`/`Update`/`Delete`/`QueryCallLog`（按号码聚合 `CALL_LOG_DEFAULT_COUNT`(1)）/`QueryAndDeleteLimitedIds`/`QueryIsBlockPhoneNumber`（调用点 todo [database]）
- **THEN** 全部按上述 URI 族与 `CALL_BLOCK`("…contacts/contact_blocklist")、`CONTACT_URI` 完成；`QueryIsBlockPhoneNumber` 以国家/国际两种格式（`FormatPhoneNumberToNational`/`FormatPhoneNumberToInternational`（libphonenumber 桩），失败回退原号）双匹配黑名单

#### Scenario: 屏蔽名单观察
- **WHEN** `RegisterObserver(phones)` 在 `CALL_BLOCK` 上挂 `CallDataRdbObserver`（DataShare 观察注册调用点 todo [database]）
- **THEN** `OnChange` 重新 `Query(phones)`（`phone_number` 非空谓词）刷新屏蔽号码列表；`UnRegisterObserver` 反注册（调用点 todo [database]）

#### Scenario: 飞行模式查询
- **WHEN** `GetAirplaneMode` 查 `SETTINGS_AIRPLANE_MODE_URI`（调用点 todo [database]）
- **THEN** 以列 `SETTING_KEY`("KEYWORD") 等于 `SETTINGS_AIRPLANE_MODE`（"settings.telephony.airplanemode"）为谓词读取 `SETTING_VALUE`("VALUE") 列，"1" 即飞行模式开

### Requirement: 拒接短信（reject_call_sms）
系统 SHALL 由 `RejectCallSms` 在带短信拒接（`IncomingCallHungUp`）时向对方发送用户配置的拒接短信。`ABILITY_SMS_SUPPORT` 为支持宏、守卫保留；发送出口改经 `stub/sms_client.h/.cpp` 的 `SmsClient::GetInstance()` 桩（design D4），发送语义照抄。

#### Scenario: 发送条件
- **WHEN** `IncomingCallHungUp` 的 `isSendSms` 为真、`content` 与通话号码 `GetAccountNumber` 均非空
- **THEN** `SendMessage`（`ConvertToUtf16` 转码）经 `SmsClient::GetInstance().SendMessage(slotId, desAddr, "", text, nullptr, nullptr)` 桩发送（发送结果处理照抄桩失败/成功语义）；条件不满足直接返回

### Requirement: 来电亮屏与运行锁（incoming_call_wake_up）
系统 SHALL 由 `IncomingCallWakeup` 在来电时持运行锁防休眠，并在通话结束后释放。运行锁逻辑保留，`PowerMgr::PowerMgrClient::CreateRunningLock`/`Lock`/`UnLock` 及 `WakeupDevice` 调用点以 `// todo!!! [powerLock] ref to incoming_call_wake_up.cpp` 占位；`IsPowerAbilityExist` 的 samgr `POWER_MANAGER_SERVICE_ID` 可用性检查调用点不迁移，在桩语义下按电源服务可用处理。

#### Scenario: 亮屏与防熄屏
- **WHEN** `NewCallCreated` 收到 INCOMING 通话并进入 `WakeupDevice`
- **THEN** 先后创建并 Lock "phonerunninglock"（`RUNNINGLOCK_BACKGROUND_PHONE`）与 "screenonrunninglock"（`RUNNINGLOCK_SCREEN`）（调用点 todo [powerLock]），各自以 `isPhoneLocked`/`isScreenOnLocked` 去重；VOIP 通话额外 `WakeupDevice(WAKEUP_DEVICE_APPLICATION, wakeupReason_="incoming call")`（调用点 todo [powerLock]，VOIP 冲突链保留）

#### Scenario: 来电期专用锁
- **WHEN** `CallControlManager::AcquireIncomingLock`/`ReleaseIncomingLock` 包夹 `CallStatusManager::IncomingHandle`
- **THEN** 分别以 `INCOMING_LOCK_TIMEOUT`(6000ms) 时长 Lock / 检查 `IsUsed` 后 UnLock "incomingrunninglock"（调用点 todo [powerLock]）

#### Scenario: 解锁释放
- **WHEN** `CallStateUpdated` 时 `CallObjectManager::HasRingingCall(hasRingCall)` 为假且两个锁标志在位
- **THEN** 依次 UnLock screenRunningLock_ 与 phoneRunningLock_ 并清标志（调用点 todo [powerLock]）；`IsPowerAbilityExist` 可用性前置门检在桩语义下按可用处理

## REMOVED Requirements

### Requirement: 贴耳灭屏（proximity_sensor）
**Reason**: AGENTS 功能范围明确不支持"贴耳灭屏（proximity_sensor）"；design D7 特性宏处置表中 proximity_sensor 相关 `ABILITY_POWER_SUPPORT` 场点（`ShutDown`/`StartUp` 的电源灭屏/亮屏行为）随 `services/call/call_state_observer/` 下 `proximity_sensor.cpp` 整文件删除。
**Migration**: 删除 `proximity_sensor.cpp`/`proximity_sensor.h`（`ProximitySensor` 观察者）及其在 `CallControlManager` 固定观察者阵容中的注册点；`PowerMgr` 灭屏/亮屏联动调用不再发生。注意：`ABILITY_POWER_SUPPORT` 本身为支持宏，`incoming_call_wake_up` 的运行锁场点保留（仅 todo 桩化）。恢复条件：平台引入接近传感与电源灭屏通路后按本 baseline 需求恢复。

### Requirement: 状态栏静音图标（status_bar）
**Reason**: AGENTS 功能范围明确不支持"状态栏静音图标（StatusBar）"，且特性宏 `ABILITY_STATUS_BAR_CONTROL_SUPPORT` 为不支持宏（design D7：`status_bar.cpp` 场点，开启分支还引用本仓未定义符号，属上游死分支）。
**Migration**: 删除 `status_bar.cpp`/`status_bar.h`（`StatusBar` 观察者）及其注册点；`isDisplayMute_`/`isDisplayIcon_` 状态去重与 "Mute"/"Speakerphone" 图标 `setIcon`/`removeIcon` 调用链删除（其 `ABILITY_STATUS_BAR_CONTROL_SUPPORT`、`ABILITY_MEDIA_SUPPORT` 场点描述的图标操作分支随文件消亡）。恢复条件：平台引入状态栏控制服务后按本 baseline 需求恢复。

### Requirement: 有线耳机消息处理（wired_headset）
**Reason**: AGENTS 功能范围明确不支持有线耳机；特性宏 `ABILITY_MEDIA_SUPPORT` 为不支持宏（design D7：`wired_headset.cpp` 与 `call_control_manager.cpp` onButtonDealing 两处守卫块随文件/块删除）。
**Migration**: 删除 `wired_headset.cpp`/`wired_headset.h`（`WiredHeadsetHandler` 与 `WiredHeadset` 媒体事件常量 `MEDIA_INITIALIZE_MSG`/`MEDIA_SET_ACTIVE_MSG`/`MEDIA_SET_LEAVE_MSG` 投递链）及其注册点；`ButtonEventhandling` 耳机按键死分支（引用本仓未定义的 `callsManager.onButtonDealing`）随文件消亡。恢复条件：平台引入有线耳机媒体事件通路后按本 baseline 需求恢复。
