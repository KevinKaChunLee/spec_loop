# 通话状态观察者（call-state-observer）Specification

## Purpose
描述 `telephony_call_manager/services/call/call_state_observer/` 的十个状态观察者：`CallDataBaseHelper`（DataShare 封装：联系人/通话记录/设置项查询）、`CallRecordsHandler`/`CallRecordsManager`（通话记录落库与未读未接提醒）、`IncomingCallNotification`/`MissedCallNotification`（来电/未接通知）、`IncomingCallWakeup`（来电亮屏与电源锁）、`ProximitySensor`（贴耳灭屏）、`RejectCallSms`（短信拒接）、`StatusBar`（静音/免提状态栏图标）、`WiredHeadset`（有线耳机事件骨架）。编译开关：`ABILITY_SMS_SUPPORT`（`reject_call_sms`，默认手机构建在位）、`ABILITY_POWER_SUPPORT`（`incoming_call_wake_up`/`proximity_sensor`）、`ABILITY_NOTIFICATION_SUPPORT`/`ABILITY_DISPLAY_SUPPORT`（`incoming_call_notification`）、`ABILITY_STATUS_BAR_CONTROL_SUPPORT`（`status_bar`）、`ABILITY_MEDIA_SUPPORT`（`wired_headset`）、`TELEPHONY_CUST_SUPPORT`（`call_data_base_helper` 的 dlopen 增强查询）。

## Requirements

### Requirement: DataShare 数据访问封装
系统 SHALL 由 `CallDataBaseHelper`（`DECLARE_DELAYED_SINGLETON`）经 `SystemAbilityManagerClient`→`GetSystemAbility(TELEPHONY_CALL_MANAGER_SYS_ABILITY_ID)` 取远端后以 `DataShare::DataShareHelper::Creator` 创建 helper，封装 `CALLLOG_URI = "datashare:///com.ohos.calllogability"`、`CONTACT_URI = "datashare:///com.ohos.contactsdataability"`、`CALL_BLOCK = ".../contacts/contact_blocklist"`、`SETTINGS_DATA_URI` 等 URI 的查询：`Query(ContactInfo&)`（读 `CALL_DISPLAY_NAME`/`PERSONAL_RINGTONE`/`PERSONAL_NOTIFICATION_RINGTONE`）、`QueryIsBlockPhoneNumber`（national/international 双匹配黑名单）、`GetAirplaneMode`、`RegisterObserver`（`CallDataRdbObserver` 监听 `CALL_BLOCK` 变化重查黑名单）。
#### Scenario: 未解锁时走静默代理 URI
- **WHEN** `GetHelperAndUrl` 时 `OsAccountManager::IsOsAccountVerified` 为假
- **THEN** 数据访问改走 `CALL_SUBSECTION_SILENCE`（`datashareproxy://...?Proxy=true&user=`）+ userId 形态的 URI

#### Scenario: TELEPHONY_CUST 增强来电归属查询
- **WHEN** `TELEPHONY_CUST_SUPPORT` 在位且来电号码长度不小于 `QUERY_CONTACT_LEN = 7`
- **THEN** `QueryContactInfoEnhanced` 经 `dlopen("libtelephony_cust_api.z.so")` + `dlsym("GetCallerNumIndex")` 执行后缀匹配增强查询并 `GetCallerIndex`

### Requirement: 通话记录落库与限量清理
系统 SHALL 由 `CallRecordsManager`（`CallStateListenerBase` 派生，`Init` 启动 `CallRecordsHandlerService`、订阅账号 SA 与 `COMMON_EVENT_DATA_SHARE_READY`）在 `CallStateUpdated` 且目标状态为 DISCONNECTED 时（`TYPE_VOIP` 跳过）经 `AddOneCallRecord`→`CopyCallInfoToRecord`（含 `GetCallFeatures(originalCallType)`、`GetCountryIso`（`GetParameter("telephony.operator.iso-country")` 默认 "CN"）、`CopyFormatNumberToRecord`（`FormatPhoneNumberAsYouType`/`FormatPhoneNumber`）、`CopyFormatNumberToE164ToRecord`（`FormatPhoneNumberToE164`））后由 `CallRecordsHandlerService::StoreCallRecord`（`ffrt::submit` 异步）执行 `AddCallLogInfo` 写通话记录；`Insert` 后 `DeleteCallLogForLimit` 以 `LOG_LIMIT_NUM = 5000` 分别清理被拦截与正常记录。
#### Scenario: 隐藏暴力/急救号码记录
- **WHEN** `TELEPHONY_CUST_WRAPPER.isHideViolenceOrEmcNumbersInCallLog_` 为真且来话号码属于暴力/急救号段
- **THEN** 该通话不写通话记录

### Requirement: 未读未接提醒
系统 SHALL 由 `QueryAndNotifyUnReadMissedCall`（`CALL_IS_READ = CALL_IS_UNREAD` + `CALL_DIRECTION_IN` + `CALL_ANSWER_MISSED` 聚合号码）经 `MissedCallNotification::NotifyUnReadMissedCall` 发布 `CommonEventSupport::COMMON_EVENT_INCOMING_CALL_MISSED`（ordered 公共事件，订阅权限 `Permission::GET_TELEPHONY_STATE`，blocked 版带 `isBlocked/detectDetails`），触发条件为 DISCONNECTED、入呼方向、未接（或 `IsAiAutoAnswer()` 智能接听标记未读）且账号已解锁；`RemoveMissedIncomingCallNotification` 将未读置 `CALL_IS_READ`。
#### Scenario: 数据库就绪后补查未读未接
- **WHEN** `COMMON_EVENT_DATA_SHARE_READY` 广播到达或账号 SA 上线
- **THEN** `QueryUnReadMissedCallLog` 执行并聚合未读未接数后发布未接提醒公共事件

### Requirement: 来电亮屏与电源锁
系统 SHALL 由 `IncomingCallWakeup`（`CallStateListenerBase` + `CallObjectManager`）在 `NewCallCreated`（INCOMING）时经 `PowerMgr::PowerMgrClient::CreateRunningLock` 持 "phonerunninglock"（`RUNNINGLOCK_BACKGROUND_PHONE`）与 "screenonrunninglock"（`RUNNINGLOCK_SCREEN`）双锁并仅对 `TYPE_VOIP` 执行 `WakeupDevice(WAKEUP_DEVICE_APPLICATION, "incoming call")`；无振铃通话时解锁；`AcquireIncomingLock` 使用 "incomingrunninglock"（`INCOMING_LOCK_TIMEOUT = 6000` 毫秒）。
#### Scenario: 来电持锁亮屏
- **WHEN** VoIP 来电创建
- **THEN** 持后台通话锁与亮屏锁并执行 `WakeupDevice`

### Requirement: 贴耳灭屏
系统 SHALL 由 `ProximitySensor` 在 `CallDestroyed` 且 `CallObjectManager::HasCallExist()` 为假时执行 `ShutDown(SUSPEND_DEVICE_REASON_APPLICATION, true)` 灭屏（`ABILITY_POWER_SUPPORT` 下走 `PowerMgr`，否则空实现）。
#### Scenario: 最后一通通话销毁
- **WHEN** 耳边通话结束且全局无存活通话
- **THEN** 设备被灭屏挂起

### Requirement: 短信拒接
系统 SHALL 由 `RejectCallSms`（`CallStateListenerBase`）在 `IncomingCallHungUp(call, isSendSms, content)` 时经 `SendMessage(slotId, u16号码, u16内容)` 以 `Singleton<SmsServiceManagerClient>::GetInstance().SendMessage(slotId, desAddr, ConvertToUtf16(""), text, nullptr, nullptr)` 发送拒接短信（`ABILITY_SMS_SUPPORT` 下，否则空实现）。
#### Scenario: 拒接时附带短信
- **WHEN** 用户拒接来电并填写拒接短信内容
- **THEN** 经 sms_mms 客户端按 slotId 发送该短信

### Requirement: 状态栏静音/免提图标
系统 SHALL 由 `StatusBar` 经 `UpdateMuteIcon(bool)`/`UpdateSpeakerphoneIcon(bool)` 以 `statusBarControl.setIcon("Mute")/removeIcon("Mute")`、`setIcon("Speakerphone")/removeIcon("Speakerphone")` 维护状态栏图标（`ABILITY_STATUS_BAR_CONTROL_SUPPORT` 下，否则空实现），`CallDestroyed` 时双图标清除。
#### Scenario: 静音图标显示
- **WHEN** 通话麦克风静音开启且 `ABILITY_STATUS_BAR_CONTROL_SUPPORT` 在位
- **THEN** 状态栏显示 "Mute" 图标；解除静音后移除

### Requirement: 来电全屏通知
系统 SHALL 由 `IncomingCallNotification` 在 `NewCallCreated`（INCOMING）且 `IsFullScreen()`（`ABILITY_DISPLAY_SUPPORT` 下 `DisplayManager::IsFullScreen()`，默认 false）为真时以 `Notification::NotificationHelper::PublishNotification`（id `INCOMING_CALL_NOTIFICATION_ID = 0`）发布 "Incoming Call" 标题的通知，通话离开该状态后 `CancelIncomingCallNotification`（`ABILITY_NOTIFICATION_SUPPORT` 下）。
#### Scenario: 非全屏形态不发布
- **WHEN** 设备非全屏形态（`IsFullScreen()` 为假）
- **THEN** 不发布来电通知
