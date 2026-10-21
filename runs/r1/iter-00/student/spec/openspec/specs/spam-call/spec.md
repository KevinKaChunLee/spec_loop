# 骚扰来电（Spam Call） Specification

## Purpose
描述来电号码骚扰识别（骚扰拦截/号码标记）能力的基线行为：对来电路径上的号码发起骚扰识别查询、同步等待识别结果、解析标记信息并据此拦截来电。源码落点：`telephony_call_manager/services/spam_call/{include,src}`（`spam_call_adapter.cpp`、`spam_call_connection.cpp`、`spam_call_proxy.cpp`、`spam_call_stub.cpp`、`callback_stub_helper.cpp`、`reminder_callback_stub_helper.cpp`、`time_wait_helper.cpp`），调用方为 `telephony_call_manager/services/call/src/call_status_manager.cpp` 的 `ShouldBlockIncomingCall`。该能力无专属编译宏：源文件无条件列入 `callmanager.gni` 的 `call_manager_sources`。

## Requirements

### Requirement: 骚扰识别查询发起
系统 SHALL 在 `CallStatusManager::ShouldBlockIncomingCall` 判定非紧急号码来临时，创建 `SpamCallAdapter` 并调用其 `DetectSpamCall(phoneNumber, slotId)`：以 Want（bundle `com.spamshield`、ability `SpamShieldServiceExtAbility`）通过 `AAFwk::ExtensionManagerClient::ConnectServiceExtensionAbility` 连接骚扰拦截扩展；连接成功后经 `SpamCallConnection::OnAbilityConnectDone` 构造 `SpamCallProxy`，以 `COMMAND_DETECT_SPAM_CALL` 发起 IPC 请求并携带 `CallbackStubHelper` 回调对象。紧急号码来电 MUST NOT 发起骚扰识别（直接返回不拦截）。
#### Scenario: 连接成功发起查询
- **WHEN** 非紧急来电号码触发 `ShouldBlockIncomingCall` 且 `ConnectServiceExtensionAbility` 返回 0
- **THEN** `SpamCallProxy::DetectSpamCall` 写入接口描述符 `ISpamCall` 对应 token 后发送 `COMMAND_DETECT_SPAM_CALL` 请求
#### Scenario: 连接失败不拦截
- **WHEN** `ConnectServiceExtensionAbility` 返回非 0
- **THEN** `DetectSpamCall` 返回 false，`ShouldBlockIncomingCall` 返回 false（不拦截来电）
#### Scenario: 紧急号码跳过识别
- **WHEN** 来电号码经 `IsEmergencyPhoneNumber` 判定为紧急号码
- **THEN** 不创建 `SpamCallAdapter`，直接返回不拦截

### Requirement: 识别结果等待与超时
系统 SHALL 由 `SpamCallAdapter::WaitForDetectResult` 通过 `TimeWaitHelper`（等待时长 `WAIT_TIME_FIVE_SECOND`，即 5000ms）同步等待识别结果：`CallbackStubHelper::OnResult` 收到回调后写入结果并 `NotifyAll`；等待超时或未收到回调时 MUST 断开骚扰拦截扩展连接（`DisconnectAbility`）且不拦截来电。
#### Scenario: 回调按时到达
- **WHEN** 5000ms 内 `CallbackStubHelper::OnResult` 被调用且 `errCode == 0`
- **THEN** `WaitForDetectResult` 返回 true，随后断开扩展连接
#### Scenario: 等待超时
- **WHEN** 5000ms 内未收到回调
- **THEN** `WaitForDetectResult` 返回 false，断开扩展连接，`ShouldBlockIncomingCall` 返回 false

### Requirement: 识别结果解析与拦截判定
系统 SHALL 由 `SpamCallAdapter::ParseDetectResult` 用 cJSON 解析回调 JSON：`detectResult` 为 1 时 `isBlock` 为 true、`decisionReason` 映射为 `blockReason`，`markType`/`markCount`/`markSource`/`markContent`/`isCloud`/`markDetails` 填入 `NumberMarkInfo`；`ShouldBlockIncomingCall` 在 `isBlock` 为 true 时拦截来电，并把 `numberMarkInfo`/`blockReason`/`detectDetails` 写入通话对象（`SetNumberMarkInfo`、`SetBlockReason`、`SetDetectDetails` 及 extraParams 的 `blockReason`）。
#### Scenario: 判定拦截
- **WHEN** 回调 JSON 中 `detectResult == 1`
- **THEN** `ShouldBlockIncomingCall` 返回 true，来电被拦截，通话对象携带标记信息与 `blockReason`
#### Scenario: 判定放行但保留标记
- **WHEN** 回调 JSON 中 `detectResult != 1` 且解析成功
- **THEN** 不拦截来电，但 `NumberMarkInfo` 与 `blockReason` 已写入通话对象

### Requirement: 白名单转黄页查询与骚扰提醒
系统 SHALL 在 `blockReason == DECISION_REASON_TRUSTLIST`（值 2）时经 `CallNumberUtils::QueryYellowPageAndMarkInfo` 转查黄页标记；在未拦截且 `markType` 为 `MARK_TYPE_CRANK`/`MARK_TYPE_FRAUD`/`MARK_TYPE_PROMOTE_SALES`/`MARK_TYPE_HOUSE_AGENT` 之一时经 `SpamCallConnection::RequireCallReminder` 发送 `COMMAND_DETECT_NEED_NOTIFY` 请求；`ReminderCallbackStubHelper::OnResult` 解析出 `reminderResult` 为 true 时 MUST 发布 `COMMON_EVENT_INCOMING_CALL_MISSED` 公共事件（携带 `isHarassmentGuidance`、`slotId` 参数，订阅权限 `GET_TELEPHONY_STATE`）。
#### Scenario: 白名单转黄页
- **WHEN** `CallbackStubHelper::OnResult` 解析得 `blockReason == 2`
- **THEN** 经 `QueryYellowPageAndMarkInfo` 以被检测号码转查黄页标记
#### Scenario: 骚扰提醒回调
- **WHEN** `COMMAND_DETECT_NEED_NOTIFY` 回调 JSON 中 `reminderResult == true`
- **THEN** 发布 `COMMON_EVENT_INCOMING_CALL_MISSED` 公共事件并携带 `slotId`

### Requirement: 响铃一次来电判定
系统 SHALL 由 `CallStatusManager::IsRingOnceCall` 在号码为 `MARK_TYPE_YELLOW_PAGE` 或已有联系人名时跳过判定；否则查询设置项 `spamshield_sim{accountId+1}_phone_switch_ring_once`（经 `SettingsDataShareHelper`），为 1 时以骚扰识别后的剩余等待窗口（`WAIT_TIME_THREE_SECOND`）创建 `TimeWaitHelper` 等待：窗口内来电即断开（断开路径 `NotifyAll`）判定为响铃一次并走 `HandleRingOnceCall`，超时未断开 MUST 判定为普通来电。
#### Scenario: 窗口内来电消失
- **WHEN** 响铃一次设置项为 1 且等待窗口内来电进入断开状态
- **THEN** `IsRingOnceCall` 返回 true，来电按 `HandleRingOnceCall` 响铃一次未接处理
#### Scenario: 窗口超时
- **WHEN** 等待窗口超时且来电仍存在
- **THEN** `IsRingOnceCall` 返回 false，来电按正常来电路径继续
#### Scenario: 黄页或联系人号码跳过
- **WHEN** 来电号码标记为 `MARK_TYPE_YELLOW_PAGE` 或联系人名非空
- **THEN** 不进行响铃一次判定，直接返回 false
