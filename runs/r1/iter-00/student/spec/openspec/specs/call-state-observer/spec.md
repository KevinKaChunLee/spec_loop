# 通话状态观察者（Call State Observer）Specification

## Purpose
描述 HMOS `telephony_call_manager` 中由通话状态变化驱动的副作用处理：通话记录写入/查询、来电与未接通知、来电亮屏/功耗锁、贴耳灭屏、拒接回短信、状态栏静音图标与有线耳机联动。这些观察者实现 `CallStateListenerBase` 接口并经 `CallStateListener` 分发触发。源码落点：`telephony_call_manager/services/call/call_state_observer/{include,src}`：`call_data_base_helper.cpp/.h`（类 `CallDataBaseHelper`）、`call_records_handler.cpp/.h`（类 `CallRecordsHandler`/`CallRecordsHandlerService`）、`call_records_manager.cpp/.h`（类 `CallRecordsManager` 及 `AccountSystemAbilityListener`/`UserSwitchEventSubscriber`/`DataShareReadyEventSubscriber`）、`incoming_call_notification.cpp/.h`（类 `IncomingCallNotification`）、`missed_call_notification.cpp/.h`（类 `MissedCallNotification`）、`incoming_call_wake_up.cpp/.h`（类 `IncomingCallWakeup`）、`proximity_sensor.cpp/.h`（类 `ProximitySensor`）、`reject_call_sms.cpp/.h`（类 `RejectCallSms`）、`status_bar.cpp/.h`（类 `StatusBar`）、`wired_headset.cpp/.h`（类 `WiredHeadset`/`WiredHeadsetHandler`）。编译开关：`callmanager.gni` 定义 `TELEPHONY_CUST_SUPPORT`（telephony_telephony_enhanced 部件）、`SUPPORT_MUTE_BY_DATABASE`（`target_platform == "watch"` 时）、`ABILITY_POWER_SUPPORT`（powermgr_power_manager 部件）、`ABILITY_SMS_SUPPORT`（telephony_sms_mms 部件）；`ABILITY_NOTIFICATION_SUPPORT`、`ABILITY_DISPLAY_SUPPORT`、`ABILITY_STATUS_BAR_CONTROL_SUPPORT`、`ABILITY_MEDIA_SUPPORT` 仅出现在源码中，本仓 GN 未定义，由产品侧编译配置注入。

## Requirements

### Requirement: 断话触发通话记录写入
系统 SHALL 由 `CallRecordsManager::CallStateUpdated` 仅在 `nextState` 为 CALL_STATUS_DISCONNECTED 且通话类型非 TYPE_VOIP 时触发记录：来电为 AI 自动接听时 answerType 记为 CALL_ANSWER_MISSED；经 `AddOneCallRecord`/`CopyCallInfoToRecord` 组装后交 `CallRecordsHandlerService::StoreCallRecord` 以 `ffrt::submit` 异步落库；号码格式化使用系统参数 `telephony.operator.iso-country`（缺省 CN）经 `CopyFormatNumberToRecord`/`CopyFormatNumberToE164ToRecord` 完成；`TELEPHONY_CUST_WRAPPER` 的 `isHideViolenceOrEmcNumbersInCallLog_` 判定为真时丢弃该条记录。
#### Scenario: 蜂窝通话落库
- **WHEN** 一通蜂窝通话断开
- **THEN** 生成 `CallRecordInfo` 并异步插入通话记录库
#### Scenario: VoIP 不落库
- **WHEN** TYPE_VOIP 通话断开
- **THEN** `CallStateUpdated` 直接返回，不写通话记录
#### Scenario: 定制隐藏号码
- **WHEN** `isHideViolenceOrEmcNumbersInCallLog_` 钩子判定该号码需隐藏
- **THEN** 该条记录被丢弃，不调用 `StoreCallRecord`

### Requirement: 通话记录库维护
系统 SHALL 由 `CallRecordsHandler::AddCallLogInfo` 组装记录：黄页标记（MARK_TYPE_YELLOW_PAGE）且非云标记时 display_name 取 `markContent`，否则取联系人名；`CheckNumberLocationInfo` 对 "default" 归属地查询号码归属、空值记 "N"；`MakeCallLogInsertBucket` 组装字段后经 `CallDataBaseHelper::Insert` 插入。插入成功后 `DeleteCallLogForLimit` 按 CALL_CREATE_TIME 降序保留 `LOG_LIMIT_NUM`（5000）条（answerType 为 CALL_ANSWER_BLOCKED 的拦截记录单独统计），经 `QueryAndDeleteLimitedIds` 删除超额项。`CallRecordsHandlerService::RemoveMissedIncomingCallNotification` 将未读未接记录的 is_read 置为已读。
#### Scenario: 超限清理
- **WHEN** 插入成功且同类（拦截/非拦截）记录超过 5000 条
- **THEN** 按 create_time 降序删除超出部分
#### Scenario: 黄页显示名
- **WHEN** 号码为 MARK_TYPE_YELLOW_PAGE 且 `isCloud` 为 false
- **THEN** 记录 display_name 使用 `markContent`
#### Scenario: 未接已读回写
- **WHEN** 调用 `RemoveMissedIncomingCallNotification`
- **THEN** 满足（未读、呼入、CALL_ANSWER_MISSED）条件的记录 is_read 置为已读

### Requirement: DataShare 数据通道
系统 SHALL 由 `CallDataBaseHelper` 经 `CreateDataShareHelper`（以 TELEPHONY_CALL_MANAGER_SYS_ABILITY_ID 为 caller）创建 `DataShare::DataShareHelper`，提供 Insert/Query/Update/Delete/QueryCallLog/QueryAndDeleteLimitedIds：联系人查询走 CONTACT_DATA，拦截名单（CALL_BLOCK，`datashare:///com.ohos.contactsdataability/contacts/contact_blocklist`）查询返回 phone_number 列表；`QueryIsBlockPhoneNumber` 以国内/国际两种格式匹配判定拦截；定义 `TELEPHONY_CUST_SUPPORT` 时提供 `QueryContactInfoEnhanced`（加载 `TELEPHONY_CUST_SO_PATH` 即 libtelephony_cust_api.z.so）；`RegisterObserver` 以 `CallDataRdbObserver` 监听 CALL_BLOCK 变化，`OnChange` 时清空并重查号码列表。
#### Scenario: 拦截名单查询
- **WHEN** 以 CALL_BLOCK URI 执行 `Query`
- **THEN** 返回的号码列表来自 phone_number 列
#### Scenario: 增强联系人查询
- **WHEN** 已定义 `TELEPHONY_CUST_SUPPORT` 且调用 `QueryContactInfoEnhanced`
- **THEN** 经 libtelephony_cust_api.z.so 扩展查询联系人信息
#### Scenario: 拦截名单变更刷新
- **WHEN** CALL_BLOCK 数据变化触发 `CallDataRdbObserver::OnChange`
- **THEN** 缓存号码列表被清空并重新查询

### Requirement: 就绪与多用户初始化
系统 SHALL 由 `CallRecordsManager::Init` 启动 `CallRecordsHandlerService`、订阅账号系统能力（SUBSYS_ACCOUNT_SYS_ABILITY_ID_BEGIN，`AccountSystemAbilityListener`）与 COMMON_EVENT_DATA_SHARE_READY（`DataShareReadyEventSubscriber`）；`QueryUnReadMissedCallLog` 仅在 `isDataShareReady_`/`isSystemAbilityAdd_` 均为真且 userId 为 `ACTIVE_USER_ID`（100）时执行一次；非主用户时改订阅 COMMON_EVENT_USER_SWITCHED（`UserSwitchEventSubscriber`）；DATA_SHARE_READY 时同时触发 `CallControlManager::RegisterObserver`、`CallStatusManager::RegisterObserver`，定义 `SUPPORT_MUTE_BY_DATABASE` 时另触发 `InteroperableSettingsHandler::RegisterObserver`。
#### Scenario: 数据库就绪
- **WHEN** 收到 COMMON_EVENT_DATA_SHARE_READY
- **THEN** 置 `isDataShareReady_` 为真并对当前活跃用户执行未接查询
#### Scenario: 主用户一次性查询
- **WHEN** 账号 SA 就绪且活跃用户为 100
- **THEN** 执行一次 `QueryUnReadMissedCallLog`，成功后不重复执行
#### Scenario: 手表静音数据库订阅
- **WHEN** 已定义 `SUPPORT_MUTE_BY_DATABASE` 且收到 COMMON_EVENT_DATA_SHARE_READY
- **THEN** `InteroperableSettingsHandler::RegisterObserver` 被调用

### Requirement: 来电通知发布
系统 SHALL 由 `IncomingCallNotification` 在 INCOMING 状态新呼建时记录 `incomingCallNumber_` 并 `PublishIncomingCallNotification`：仅 `IsFullScreen()`（`ABILITY_DISPLAY_SUPPORT`，未定义时恒 false）时以 INCOMING_CALL_NOTIFICATION_TITLE 与号码构建 NotificationNormalContent、SetNotificationId(INCOMING_CALL_NOTIFICATION_ID=0) 后经 `Notification::NotificationHelper::PublishNotification` 发布；该来电接通/挂断/状态迁移且号码与 `incomingCallNumber_` 一致时 `CancelIncomingCallNotification`（`ABILITY_NOTIFICATION_SUPPORT` 下经 `NotificationHelper::CancelNotification` 取消）。
#### Scenario: 全屏下来电发布
- **WHEN** 来电创建且 `IsFullScreen()` 为 true
- **THEN** 发布 id 为 0、标题为 "Incoming Call"、内容为来电号码的通知
#### Scenario: 无显示宏不发布
- **WHEN** 未定义 `ABILITY_DISPLAY_SUPPORT`
- **THEN** `IsFullScreen()` 恒为 false，不发布来电通知
#### Scenario: 来电结束取消
- **WHEN** `IncomingCallActivated`/`IncomingCallHungUp` 且号码与 `incomingCallNumber_` 一致
- **THEN** 取消该来电通知

### Requirement: 未接与拦截广播
系统 SHALL 由 `MissedCallNotification::CallStateUpdated` 对非 VoIP 的呼入断话在 answerType 为 CALL_ANSWER_MISSED（或激活但 `IsAiAutoAnswer`）且账号已验证（`IsOsAccountVerified`）时 `PublishMissedCallEvent`：以 COMMON_EVENT_INCOMING_CALL_MISSED、code 为 INCOMING_CALL_MISSED_CODE(0) 有序发布两条（含号码版本要求 `Permission::GET_TELEPHONY_STATE`）；`PublishBlockedCallEvent` 额外携带 isBlocked 与 detectDetails；`NotifyUnReadMissedCall` 以 phoneNumberList/countList 发布未接汇总，失败返回 TELEPHONY_ERR_PUBLISH_BROADCAST_FAIL；`CallRecordsHandler::QueryAndNotifyUnReadMissedCall` 以（未读、呼入、CALL_ANSWER_MISSED）条件查询后调用之。
#### Scenario: 未接来电广播
- **WHEN** 呼入通话未接断开且用户已解锁
- **THEN** 发布两条 COMMON_EVENT_INCOMING_CALL_MISSED 广播（不含号码与含号码版本）
#### Scenario: 拦截来电广播
- **WHEN** 被拦截的来电断开触发 `PublishBlockedCallEvent`
- **THEN** 广播携带 isBlocked=true 与 detectDetails
#### Scenario: 未接汇总失败
- **WHEN** `NotifyUnReadMissedCall` 广播发布失败
- **THEN** 返回 TELEPHONY_ERR_PUBLISH_BROADCAST_FAIL

### Requirement: 来电亮屏与功耗控制
系统 SHALL 由 `IncomingCallWakeup` 在来电创建时 `WakeupDevice`：创建并持有 phoneRunningLock_（RUNNINGLOCK_BACKGROUND_PHONE）与 screenRunningLock_（RUNNINGLOCK_SCREEN），TYPE_VOIP 呼叫另以 WAKEUP_DEVICE_APPLICATION 亮屏（`ABILITY_POWER_SUPPORT`）；`AcquireIncomingLock`/`ReleaseIncomingLock` 以 `INCOMING_LOCK_TIMEOUT`（6000ms）管理 incomingRunningLock_；`CallStateUpdated` 检测无振铃呼叫（`HasRingingCall`）时释放两锁。`ProximitySensor::CallDestroyed` 在仍有通话（`HasCallExist`）时经 `ShutDown`（SUSPEND_DEVICE_REASON_APPLICATION）贴耳灭屏。
#### Scenario: 来电持锁亮屏
- **WHEN** INCOMING 状态新呼建触发 `WakeupDevice`
- **THEN** phoneRunningLock_ 与 screenRunningLock_ 被持有，VoIP 呼叫额外触发亮屏
#### Scenario: 振铃结束释放
- **WHEN** 状态更新且已无振铃呼叫
- **THEN** screenRunningLock_ 与 phoneRunningLock_ 依次释放
#### Scenario: 贴耳灭屏
- **WHEN** 通话销毁且仍存在其它通话
- **THEN** 以 SUSPEND_DEVICE_REASON_APPLICATION 执行 `ShutDown`

### Requirement: 拒接短信与外设联动
系统 SHALL 由 `RejectCallSms::IncomingCallHungUp` 在 isSendSms 且内容与号码非空时经 `SmsServiceManagerClient::SendMessage`（`ABILITY_SMS_SUPPORT`）回复拒接短信；由 `StatusBar::UpdateMuteIcon`/`UpdateSpeakerphoneIcon` 去重后经 statusBarControl 的 setIcon/removeIcon（`ABILITY_STATUS_BAR_CONTROL_SUPPORT`）控制 "Mute"/"Speakerphone" 图标，`CallDestroyed` 时全部隐藏；由 `WiredHeadset` 在呼建/通话销毁时经 `WiredHeadsetHandler` 发送 MEDIA_SET_ACTIVE_MSG/MEDIA_SET_LEAVE_MSG，`ButtonEventhandling`（`ABILITY_MEDIA_SUPPORT`）按短/长按转交 callsManager 的 onButtonDealing。
#### Scenario: 拒接回短信
- **WHEN** 来电被拒且 isSendSms 为真、短信内容非空
- **THEN** 以该呼叫 slotId 与号码发送拒接短信
#### Scenario: 静音图标去重
- **WHEN** `UpdateMuteIcon(true)` 且图标此前未显示
- **THEN** statusBarControl 执行 setIcon("Mute") 并记录状态
#### Scenario: 通话结束隐藏图标
- **WHEN** `CallDestroyed` 触发
- **THEN** Mute 与 Speakerphone 图标均被移除，且有线耳机侧收到 MEDIA_SET_LEAVE_MSG
