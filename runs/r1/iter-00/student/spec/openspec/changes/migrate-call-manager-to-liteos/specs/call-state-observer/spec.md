# Spec Delta

## MODIFIED Requirements

### Requirement: 断话触发通话记录写入
系统 SHALL 由 `CallRecordsManager::CallStateUpdated` 仅在 `nextState` 为 CALL_STATUS_DISCONNECTED 时触发记录（非 TYPE_VOIP 的类型判断随 VoIP 暂不支持移除）：来电为 AI 自动接听时 answerType 记为 CALL_ANSWER_MISSED；经 `AddOneCallRecord`/`CopyCallInfoToRecord` 组装后交 `CallRecordsHandlerService::StoreCallRecord` 以打桩的 EventHandler 异步处理（替代 ffrt）；号码格式化使用系统参数 `telephony.operator.iso-country`（经打桩的参数接口，缺省 CN）经 `CopyFormatNumberToRecord`/`CopyFormatNumberToE164ToRecord` 完成；`TELEPHONY_CUST_WRAPPER` 的 `isHideViolenceOrEmcNumbersInCallLog_` 判定为真时丢弃该条记录（判定经 `TelephonyCustClient::GetInstance().Xxx()` 桩注入）；`call_data_base_helper.cpp` 的 DataShare 写入调用点以 `// todo!!! [database] ref to call_data_base_helper.cpp Insert` 占位、不实际落库。
#### Scenario: 断话触发组包不落库
- **WHEN** 一通蜂窝通话断开
- **THEN** 生成 `CallRecordInfo` 并经打桩的 EventHandler 异步进入 `CallRecordsHandler::AddCallLogInfo`，DataShare 写入调用点为 todo 占位、不实际插入通话记录库
#### Scenario: 蜂窝通话落库
- **WHEN** 一通蜂窝通话断开
- **THEN** 生成 `CallRecordInfo` 并经打桩的 EventHandler 异步进入 `CallRecordsHandler::AddCallLogInfo`，DataShare 写入调用点为 `// todo!!! [database] ref to call_data_base_helper.cpp Insert` 占位、不实际插入通话记录库
#### Scenario: VoIP 不落库
- **WHEN** 基线中 TYPE_VOIP 通话断开
- **THEN** liteOS 上 VoIP 通话对象不存在（VoIP 暂不支持），无通话记录写入触发，非 TYPE_VOIP 的类型判断分支不迁移
#### Scenario: 定制隐藏号码
- **WHEN** 经桩注入的 `isHideViolenceOrEmcNumbersInCallLog_` 钩子判定该号码需隐藏
- **THEN** 该条记录被丢弃，不调用 `StoreCallRecord`

### Requirement: 通话记录库维护
系统 SHALL 由 `CallRecordsHandler::AddCallLogInfo` 组装记录：黄页标记（MARK_TYPE_YELLOW_PAGE）且非云标记时 display_name 取 `markContent`，否则取联系人名；`CheckNumberLocationInfo` 对 "default" 归属地查询号码归属、空值记 "N"；`MakeCallLogInsertBucket` 组装字段后经 `CallDataBaseHelper::Insert` 插入（调用点以 `// todo!!! [database] ref to call_data_base_helper.cpp Insert` 占位、不实际插入）。插入成功后 `DeleteCallLogForLimit` 按 CALL_CREATE_TIME 降序保留 `LOG_LIMIT_NUM`（5000）条（answerType 为 CALL_ANSWER_BLOCKED 的拦截记录单独统计），经 `QueryAndDeleteLimitedIds` 删除超额项（调用点以 `// todo!!! [database] ref to call_data_base_helper.cpp QueryAndDeleteLimitedIds` 占位）。`CallRecordsHandlerService::RemoveMissedIncomingCallNotification` 将未读未接记录的 is_read 置为已读（写回调用点以 `// todo!!! [database] ref to call_data_base_helper.cpp Update` 占位）。
#### Scenario: 超限清理
- **WHEN** 插入成功且同类（拦截/非拦截）记录超过 5000 条
- **THEN** 按 CALL_CREATE_TIME 降序计算超额项，实际删除调用点以 `// todo!!! [database] ref to call_data_base_helper.cpp QueryAndDeleteLimitedIds` 占位、不实际删除
#### Scenario: 超限清理判定
- **WHEN** 插入成功且同类（拦截/非拦截）记录超过 5000 条
- **THEN** 按 create_time 降序计算超额项，实际删除调用点为 todo 占位、不实际删除
#### Scenario: 黄页显示名
- **WHEN** 号码为 MARK_TYPE_YELLOW_PAGE 且 `isCloud` 为 false
- **THEN** 记录 display_name 使用 `markContent`
#### Scenario: 未接已读回写判定
- **WHEN** 调用 `RemoveMissedIncomingCallNotification`
- **THEN** 满足（未读、呼入、CALL_ANSWER_MISSED）条件的记录 is_read 置为已读，写回调用点为 todo 占位、不实际更新
#### Scenario: 未接已读回写
- **WHEN** 调用 `RemoveMissedIncomingCallNotification`
- **THEN** 满足（未读、呼入、CALL_ANSWER_MISSED）条件的记录 is_read 置为已读，写回调用点以 `// todo!!! [database] ref to call_data_base_helper.cpp Update` 占位、不实际更新

### Requirement: DataShare 数据通道
系统 SHALL 保留 `CallDataBaseHelper` 的接口面与判定逻辑，DataShare 数据通道调用点全部 todo 占位、不实际调用 `DataShare::DataShareHelper`：`CreateDataShareHelper`（以 TELEPHONY_CALL_MANAGER_SYS_ABILITY_ID 为 caller）不创建；Insert/Query/Update/Delete/QueryCallLog 调用点以 `// todo!!! [database] ref to call_data_base_helper.cpp <对应函数>` 占位、查询返回未命中/失败；拦截名单（CALL_BLOCK，`datashare:///com.ohos.contactsdataability/contacts/contact_blocklist`）查询返回空 phone_number 列表；`QueryIsBlockPhoneNumber` 的国内/国际两种格式匹配判定保留、查询占位返回未命中；定义 `TELEPHONY_CUST_SUPPORT` 时 `QueryContactInfoEnhanced` 调用点以 `// todo!!! [database] ref to call_data_base_helper.cpp QueryContactInfoEnhanced` 占位、不加载 `TELEPHONY_CUST_SO_PATH`（libtelephony_cust_api.z.so）；`RegisterObserver` 以 `CallDataRdbObserver` 监听 CALL_BLOCK 变化的订阅不注册（调用点以 `// todo!!! [database] ref to call_data_base_helper.cpp RegisterObserver` 占位）。
#### Scenario: 拦截名单查询未命中
- **WHEN** 以 CALL_BLOCK URI 执行 `Query`
- **THEN** DataShare 查询调用点为 todo 占位，返回空号码列表，`QueryIsBlockPhoneNumber` 判定为不拦截
#### Scenario: 拦截名单查询
- **WHEN** 以 CALL_BLOCK URI 执行 `Query`
- **THEN** DataShare 查询调用点以 `// todo!!! [database] ref to call_data_base_helper.cpp Query` 占位、不实际调用 DataShare，返回空 phone_number 列表，国内/国际两种格式匹配判定均不命中
#### Scenario: 增强联系人查询占位
- **WHEN** 已定义 `TELEPHONY_CUST_SUPPORT` 且调用 `QueryContactInfoEnhanced`
- **THEN** 调用点为 todo 占位、不加载 libtelephony_cust_api.z.so，返回查询失败并回退普通查询路径
#### Scenario: 增强联系人查询
- **WHEN** 已定义 `TELEPHONY_CUST_SUPPORT` 且调用 `QueryContactInfoEnhanced`
- **THEN** 调用点以 `// todo!!! [database] ref to call_data_base_helper.cpp QueryContactInfoEnhanced` 占位、不加载 `TELEPHONY_CUST_SO_PATH`（libtelephony_cust_api.z.so），返回查询失败并回退普通查询路径
#### Scenario: 拦截名单变更刷新
- **WHEN** 基线中 CALL_BLOCK 数据变化触发 `CallDataRdbObserver::OnChange`
- **THEN** 订阅不注册（`RegisterObserver` 调用点以 `// todo!!! [database] ref to call_data_base_helper.cpp RegisterObserver` 占位），无 OnChange 链路，缓存号码列表不因此清空重查

### Requirement: 就绪与多用户初始化
系统 SHALL 由 `CallRecordsManager::Init` 启动 `CallRecordsHandlerService`；liteOS 只支持单主帐号：os_account 多用户逻辑精简为默认主帐号（以基线 `call_records_manager.cpp` 的默认用户 ID 常量 `ACTIVE_USER_ID`（100）为准，恒为活跃主用户，非主用户分支 `UserSwitchEventSubscriber`/COMMON_EVENT_USER_SWITCHED 移除）；`QueryUnReadMissedCallLog` 仅在 `isDataShareReady_`/`isSystemAbilityAdd_` 均为真且 userId 为 `ACTIVE_USER_ID`（100）时执行一次（DATA_SHARE_READY 公共事件订阅调用点以 `// todo!!! [broadcast] ref to call_records_manager.cpp Init` 占位、不实际注册，就绪标志判定语义保留）；DATA_SHARE_READY 时同时触发 `CallControlManager::RegisterObserver`、`CallStatusManager::RegisterObserver`；`SUPPORT_MUTE_BY_DATABASE` 为不支持宏，`InteroperableSettingsHandler::RegisterObserver` 的手表静音数据库订阅不迁移。
#### Scenario: 主用户一次性查询判定
- **WHEN** 账号判定取默认主帐号且 userId 为 `ACTIVE_USER_ID`（100）、就绪标志均为真
- **THEN** 执行一次 `QueryUnReadMissedCallLog`，成功后不重复执行
#### Scenario: 数据库就绪
- **WHEN** 基线中收到 COMMON_EVENT_DATA_SHARE_READY
- **THEN** 公共事件订阅调用点以 `// todo!!! [broadcast] ref to call_records_manager.cpp Init` 占位、不实际订阅，事件不会实际到达；就绪标志判定语义保留，标志置真时执行一次未接查询
#### Scenario: 主用户一次性查询
- **WHEN** 就绪标志 `isDataShareReady_`/`isSystemAbilityAdd_` 均为真且 userId 为 `ACTIVE_USER_ID`（100）
- **THEN** 执行一次 `QueryUnReadMissedCallLog`，成功后不重复执行
#### Scenario: 手表静音数据库订阅
- **WHEN** 基线中已定义 `SUPPORT_MUTE_BY_DATABASE` 且收到 COMMON_EVENT_DATA_SHARE_READY
- **THEN** `SUPPORT_MUTE_BY_DATABASE` 为不支持宏，`InteroperableSettingsHandler::RegisterObserver` 的手表静音数据库订阅不迁移、无该订阅链路
#### Scenario: 就绪订阅占位
- **WHEN** `Init` 执行
- **THEN** DATA_SHARE_READY 公共事件订阅调用点为 todo 占位、不实际注册，`SUPPORT_MUTE_BY_DATABASE` 静音数据库订阅不存在

### Requirement: 来电通知发布
系统 SHALL 由 `IncomingCallNotification` 在 INCOMING 状态新呼建时记录 `incomingCallNumber_` 并 `PublishIncomingCallNotification`：通知发布调用点以 `// todo!!! [notification] ref to incoming_call_notification.cpp PublishIncomingCallNotification` 占位、不实际发布通知（INCOMING_CALL_NOTIFICATION_TITLE 与号码的组包逻辑保留）；该来电接通/挂断/状态迁移且号码与 `incomingCallNumber_` 一致时 `CancelIncomingCallNotification`，取消调用点以 `// todo!!! [notification] ref to incoming_call_notification.cpp CancelIncomingCallNotification` 占位、不实际取消；`IsFullScreen()`（`ABILITY_DISPLAY_SUPPORT`）与 `NotificationHelper::PublishNotification`/`CancelNotification`（`ABILITY_NOTIFICATION_SUPPORT`）的差异分支随宏退役统一（均为不支持宏，`#ifdef` 分支移除）。
#### Scenario: 来电通知发布占位
- **WHEN** 来电创建
- **THEN** `incomingCallNumber_` 记录来电号码，通知发布调用点为 todo 占位、不实际发布通知
#### Scenario: 全屏下来电发布
- **WHEN** 来电创建且基线中 `IsFullScreen()` 为 true
- **THEN** INCOMING_CALL_NOTIFICATION_TITLE 与号码的组包逻辑保留，`NotificationHelper::PublishNotification` 调用点以 `// todo!!! [notification] ref to incoming_call_notification.cpp PublishIncomingCallNotification` 占位、不实际发布通知
#### Scenario: 无显示宏不发布
- **WHEN** 未定义 `ABILITY_DISPLAY_SUPPORT`（不支持宏）
- **THEN** `IsFullScreen()` 差异分支随宏退役移除，不产生亮屏态通知发布判定，无通知发布链路
#### Scenario: 来电结束取消占位
- **WHEN** `IncomingCallActivated`/`IncomingCallHungUp` 且号码与 `incomingCallNumber_` 一致
- **THEN** 取消通知调用点为 todo 占位、不实际取消该来电通知
#### Scenario: 来电结束取消
- **WHEN** `IncomingCallActivated`/`IncomingCallHungUp` 且号码与 `incomingCallNumber_` 一致
- **THEN** `NotificationHelper::CancelNotification` 调用点以 `// todo!!! [notification] ref to incoming_call_notification.cpp CancelIncomingCallNotification` 占位、不实际取消该来电通知

### Requirement: 未接与拦截广播
系统 SHALL 由 `MissedCallNotification::CallStateUpdated` 对呼入断话在 answerType 为 CALL_ANSWER_MISSED（或激活但 `IsAiAutoAnswer`）且账号已验证（`IsOsAccountVerified`，单主帐号下按默认主帐号判定）时 `PublishMissedCallEvent`：以 COMMON_EVENT_INCOMING_CALL_MISSED、code 为 INCOMING_CALL_MISSED_CODE(0) 有序组包两条（含号码版本，权限校验随免权限直通不调用）；广播发布调用点以 `// todo!!! [broadcast] ref to missed_call_notification.cpp PublishMissedCallEvent` 占位、不实际发布；`PublishBlockedCallEvent` 额外携带 isBlocked 与 detectDetails 的组包判定保留（发布调用点同样 todo 占位）；`NotifyUnReadMissedCall` 以 phoneNumberList/countList 组装未接汇总，发布失败返回 TELEPHONY_ERR_PUBLISH_BROADCAST_FAIL；`CallRecordsHandler::QueryAndNotifyUnReadMissedCall` 以（未读、呼入、CALL_ANSWER_MISSED）条件查询后调用之（查询调用点以 `// todo!!! [database] ref to call_records_handler.cpp QueryAndNotifyUnReadMissedCall` 占位）。
#### Scenario: 未接来电广播组包占位
- **WHEN** 呼入通话未接断开且用户已解锁
- **THEN** 组包两条 COMMON_EVENT_INCOMING_CALL_MISSED 广播数据，发布调用点为 todo 占位、不实际发布
#### Scenario: 未接来电广播
- **WHEN** 呼入通话未接断开且用户已解锁
- **THEN** 组包两条 COMMON_EVENT_INCOMING_CALL_MISSED 广播数据（含号码版本，权限校验随免权限直通不调用），发布调用点以 `// todo!!! [broadcast] ref to missed_call_notification.cpp PublishMissedCallEvent` 占位、不实际发布
#### Scenario: 拦截来电广播组包
- **WHEN** 被拦截的来电断开触发 `PublishBlockedCallEvent`
- **THEN** 组包携带 isBlocked=true 与 detectDetails 的广播数据，发布调用点为 todo 占位、不实际发布
#### Scenario: 拦截来电广播
- **WHEN** 被拦截的来电断开触发 `PublishBlockedCallEvent`
- **THEN** 组包携带 isBlocked=true 与 detectDetails 的广播数据，发布调用点以 `// todo!!! [broadcast] ref to missed_call_notification.cpp PublishBlockedCallEvent` 占位、不实际发布
#### Scenario: 未接汇总失败
- **WHEN** `NotifyUnReadMissedCall` 广播发布（占位路径）失败
- **THEN** 返回 TELEPHONY_ERR_PUBLISH_BROADCAST_FAIL

### Requirement: 来电亮屏与功耗控制
系统 SHALL 由 `IncomingCallWakeup` 在来电创建时 `WakeupDevice`：持锁/亮屏的 RunningLock 调用点以 `// todo!!! [powerLock] ref to incoming_call_wake_up.cpp WakeupDevice` 占位、不实际持锁亮屏（TYPE_VOIP 呼叫以 WAKEUP_DEVICE_APPLICATION 亮屏的分支随 VoIP 暂不支持移除；`ABILITY_POWER_SUPPORT` 为支持宏但接口暂不调用）；`AcquireIncomingLock`/`ReleaseIncomingLock` 以 `INCOMING_LOCK_TIMEOUT`（6000ms）管理 incomingRunningLock_ 的调用点以 `// todo!!! [powerLock] ref to incoming_call_wake_up.cpp AcquireIncomingLock` / `ReleaseIncomingLock` 占位；`CallStateUpdated` 检测无振铃呼叫（`HasRingingCall`）时释放两锁的判定保留（解锁调用点为 todo 占位）。贴耳灭屏（`ProximitySensor`，proximity_sensor.cpp 的 sensor 依赖）不支持、不迁移。
#### Scenario: 来电持锁占位
- **WHEN** INCOMING 状态新呼建触发 `WakeupDevice`
- **THEN** phoneRunningLock_ 与 screenRunningLock_ 的持锁/亮屏调用点为 todo 占位、不实际持锁亮屏
#### Scenario: 振铃结束释放判定
- **WHEN** 状态更新且已无振铃呼叫（`HasRingingCall` 为 false）
- **THEN** 释放 screenRunningLock_/phoneRunningLock_ 的判定成立，解锁调用点为 todo 占位、不实际解锁
#### Scenario: 来电持锁亮屏
- **WHEN** INCOMING 状态新呼建触发 `WakeupDevice`
- **THEN** phoneRunningLock_ 与 screenRunningLock_ 的持锁/亮屏调用点以 `// todo!!! [powerLock] ref to incoming_call_wake_up.cpp WakeupDevice` 占位、不实际持锁亮屏，VoIP 呼叫亮屏分支随 VoIP 暂不支持移除
#### Scenario: 振铃结束释放
- **WHEN** 状态更新且已无振铃呼叫（`HasRingingCall` 为 false）
- **THEN** 释放 screenRunningLock_/phoneRunningLock_ 的判定成立，解锁调用点以 `// todo!!! [powerLock] ref to incoming_call_wake_up.cpp ReleaseIncomingLock` 占位、不实际解锁
#### Scenario: 贴耳灭屏
- **WHEN** 通话销毁且仍存在其它通话（基线贴耳传感器条件满足）
- **THEN** 贴耳灭屏链路不迁移（proximity_sensor.cpp 不迁移），无传感器订阅与 `ShutDown` 处理、不灭屏

### Requirement: 拒接短信与外设联动
系统 SHALL 由 `RejectCallSms::IncomingCallHungUp` 在 isSendSms 且内容与号码非空时经本 change 引入的 `SmsClient::GetInstance().SendMessage`（stub/ 打桩，替代 `SmsServiceManagerClient::SendMessage`）回复拒接短信（`ABILITY_SMS_SUPPORT` 为支持宏）；状态栏静音图标（`StatusBar`，status_bar.cpp，`ABILITY_STATUS_BAR_CONTROL_SUPPORT` 为不支持宏）与有线耳机联动（`WiredHeadset`/`WiredHeadsetHandler`，wired_headset.cpp）不支持、不迁移。
#### Scenario: 拒接回短信
- **WHEN** 来电被拒且 isSendSms 为真、短信内容非空
- **THEN** 以该呼叫 slotId 与号码经 `SmsClient::GetInstance().SendMessage` 发送拒接短信
#### Scenario: 静音图标去重
- **WHEN** 基线中 `UpdateMuteIcon(true)` 且图标此前未显示
- **THEN** 状态栏静音图标链路不迁移（status_bar.cpp 不迁移），无 setIcon 去重与图标显示
#### Scenario: 通话结束隐藏图标
- **WHEN** 基线中 `CallDestroyed` 触发
- **THEN** 状态栏图标隐藏与有线耳机 MEDIA_SET_LEAVE_MSG 联动均不迁移（status_bar.cpp、wired_headset.cpp 不迁移），无对应处理链路
