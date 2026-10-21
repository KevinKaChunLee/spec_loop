# Spec Delta

## MODIFIED Requirements

### Requirement: DataShare 数据访问封装
系统 SHALL 由 `CallDataBaseHelper`（`DECLARE_DELAYED_SINGLETON`）保留 URI 常量与查询接口骨架：`Query(ContactInfo&)`（读 `CALL_DISPLAY_NAME`/`PERSONAL_RINGTONE`/`PERSONAL_NOTIFICATION_RINGTONE`）、`QueryIsBlockPhoneNumber`（national/international 双匹配黑名单）、`GetAirplaneMode`、`RegisterObserver`；DataShare helper 创建与查询调用点以 `// todo!!! [database]` 占位（返回默认：联系人未命中、黑名单不拦截、飞行模式关）；TELEPHONY_CUST 增强查询 `QueryContactInfoEnhanced` 不再 dlopen，改经 `TelephonyCustClient::GetInstance()` 桩（后缀匹配逻辑保留）。
#### Scenario: 未解锁时走静默代理 URI
- **WHEN** DataShare 访问执行（单主帐号恒已解锁形态）
- **THEN** 未解锁静默代理 URI 分支不迁移，查询调用点为 `// todo!!! [database]` 占位并返回默认值

#### Scenario: TELEPHONY_CUST 增强来电归属查询
- **WHEN** `TELEPHONY_CUST_SUPPORT` 在位且来电号码长度不小于 `QUERY_CONTACT_LEN = 7`
- **THEN** `QueryContactInfoEnhanced` 经 `TelephonyCustClient::GetInstance()` 桩执行后缀匹配并回填 `GetCallerIndex`

### Requirement: 通话记录落库与限量清理
系统 SHALL 由 `CallRecordsManager`（`CallStateListenerBase` 派生，`Init` 的账号 SA 与 `COMMON_EVENT_DATA_SHARE_READY` 订阅调用点以 `// todo!!! [broadcast]` 占位）在 `CallStateUpdated` 且目标状态为 DISCONNECTED 时（`TYPE_VOIP` 跳过）经 `AddOneCallRecord`→`CopyCallInfoToRecord`（含 `GetCallFeatures(originalCallType)`、`GetCountryIso`（`GetParameter("telephony.operator.iso-country")` 经系统参数桩，默认 "CN"）、`CopyFormatNumberToRecord`（`FormatPhoneNumberAsYouType`/`FormatPhoneNumber` 经 libphonenumber 桩）、`CopyFormatNumberToE164ToRecord`（`FormatPhoneNumberToE164` 经桩））后由 `CallRecordsHandlerService::StoreCallRecord`（打桩 `EventHandler` 异步）执行 `AddCallLogInfo`（DataShare 写库调用点以 `// todo!!! [database]` 占位）；`Insert` 后 `DeleteCallLogForLimit` 以 `LOG_LIMIT_NUM = 5000` 的限量清理逻辑保留（查询/删除调用点占位）；隐藏暴力/急救号记录改经 `TelephonyCustClient::GetInstance()` 桩判定（默认不隐藏）。
#### Scenario: 断开通话触发记录组装
- **WHEN** CS/IMS 通话进入 DISCONNECTED
- **THEN** 通话记录组装链完整执行（号码格式化经桩、写库调用点占位），记录对象内容与组装逻辑一致

#### Scenario: 隐藏暴力/急救号码记录
- **WHEN** `TelephonyCustClient` 桩配置隐藏开关为真且来话号码属于暴力/急救号段
- **THEN** 该通话不进入记录组装链（判定逻辑经桩生效）

### Requirement: 短信拒接
系统 SHALL 由 `RejectCallSms`（`CallStateListenerBase`）在 `IncomingCallHungUp(call, isSendSms, content)` 时经 `SendMessage(slotId, u16号码, u16内容)` 以 `SmsClient::GetInstance().SendMessage(slotId, desAddr, ConvertToUtf16(""), text, nullptr, nullptr)` 桩发送拒接短信（`ABILITY_SMS_SUPPORT` 为支持宏，代码迁移）。
#### Scenario: 拒接时附带短信
- **WHEN** 用户拒接来电并填写拒接短信内容
- **THEN** 经 `SmsClient::GetInstance()` 桩按 slotId 发送该短信，桩可校验收到的号码与内容

## REMOVED Requirements

### Requirement: 未读未接提醒
**Reason**: 通知（`ABILITY_NOTIFICATION_SUPPORT`）与公共事件发布暂不调用；未接提醒依赖通知与 DataShare 查询。
**Migration**: `MissedCallNotification` 不迁移；`CallRecordsManager` 内 `QueryAndNotifyUnReadMissedCall` 与未接提醒调用点以 `// todo!!! [notification]` 占位保留骨架，待通知接口适配后恢复。

### Requirement: 来电亮屏与电源锁
**Reason**: 功耗锁接口（`ABILITY_POWER_SUPPORT` 域）在 liteOS 暂不调用，亮屏/灭屏不在 liteOS 范围。
**Migration**: `IncomingCallWakeup` 不迁移；`IncomingHandle` 前后的 `AcquireIncomingLock`/`ReleaseIncomingLock` 调用点保留为空操作占位（单线程无需持锁）。

### Requirement: 贴耳灭屏
**Reason**: AGENTS.md 功能范围：贴耳灭屏（proximity_sensor）不支持。
**Migration**: `ProximitySensor` 不迁移；`CallDestroyed` 链路中的灭屏调用点移除。

### Requirement: 状态栏静音/免提图标
**Reason**: AGENTS.md 功能范围：状态栏静音图标（StatusBar）不支持（`ABILITY_STATUS_BAR_CONTROL_SUPPORT` 为不支持宏）。
**Migration**: `StatusBar` 不迁移；静音/免提状态仅经回调上报，无状态栏图标维护。

### Requirement: 来电全屏通知
**Reason**: 通知（`ABILITY_NOTIFICATION_SUPPORT`）与 Display（`ABILITY_DISPLAY_SUPPORT`）均为不支持宏，通知接口暂不调用。
**Migration**: `IncomingCallNotification` 不迁移；`NewCallCreated` 链路中的来电通知调用点移除（不做全屏通知判定）。
