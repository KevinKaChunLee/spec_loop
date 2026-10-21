# 骚扰来电检测（spam-call）Specification

## Purpose
描述 `telephony_call_manager/services/spam_call/` 的骚扰来电检测模块组：`SpamCallAdapter`（检测编排：连接扩展、限时等待、结果解析）、`SpamCallConnection`（扩展连接回调）、`SpamCallProxy`/`SpamCallStub`（与 `com.spamshield` 扩展的 IPC）、`CallbackStubHelper`/`ReminderCallbackStubHelper`（检测/提醒结果回调）、`TimeWaitHelper`（限时等待）。该模块组无独有编译开关，连接方式为 `AAFwk::ExtensionManagerClient::ConnectServiceExtensionAbility`（非 dlopen）。

## Requirements

### Requirement: 骚扰检测编排
系统 SHALL 由 `SpamCallAdapter::DetectSpamCall(phoneNumber, slotId)` 构造 `AAFwk::Want`（bundle `"com.spamshield"`、ability `"SpamShieldServiceExtAbility"`）经 `ConnectSpamCallAbility`（`AAFwk::ExtensionManagerClient::ConnectServiceExtensionAbility(want, connection_, nullptr, DEFAULT_USER_ID = -1)`）连接；`WaitForDetectResult()` 经 `TimeWaitHelper(WAIT_TIME_FIVE_SECOND)` 限时 5000 毫秒等待，超时或完成后 `DisconnectSpamCallAbility()`。
#### Scenario: 检测超时
- **WHEN** `TimeWaitHelper::WaitForResult()` 5000 毫秒内未收到 `NotifyAll()`
- **THEN** 检测按超时处理并断开扩展连接

### Requirement: 检测结果解析与黄页回退
系统 SHALL 由 `CallbackStubHelper::OnResult`（errCode == 0）执行 `ParseDetectResult`（cJSON 解析 `DETECT_RESULT`（== 1 判拦截）、`DECISION_REASON`、`MARK_TYPE/MARK_COUNT/MARK_SOURCE/MARK_CONTENT/IS_CLOUD/MARK_DETAILS/DETECT_DETAILS`）后 `SetParseResult(isBlock, numberMarkInfo, blockReason, detectDetails)`；`blockReason == DECISION_REASON_TRUSTLIST(2)` 时转 `CallNumberUtils::QueryYellowPageAndMarkInfo(numberMarkInfo, GetDetectPhoneNum())` 查黄页；随后 `CallManagerHisysevent::WriteIncomingNumIdentityBehaviorEvent(markType, isBlock, blockReason)` 并 `NotifyAll()`。
#### Scenario: 标记为骚扰且不拦截
- **WHEN** `markType` 为 `MARK_TYPE_CRANK/MARK_TYPE_FRAUD/MARK_TYPE_PROMOTE_SALES/MARK_TYPE_HOUSE_AGENT` 且 `isBlock` 为假
- **THEN** `SpamCallConnection::RequireCallReminder()` 经 `SpamCallProxy::RequireCallReminder` 请求提醒（`COMMAND_DETECT_NEED_NOTIFY = 3`）

### Requirement: 检测命令 IPC
系统 SHALL 由 `SpamCallProxy : public IRemoteProxy<ISpamCall>`（descriptor `u"idl.ISpamShieldService"`）以 `DetectSpamCall` 写 phoneNumber/slotId + 回调（`CallbackStubHelper`）后 `SendRequest(COMMAND_DETECT_SPAM_CALL = 1)`；`SpamCallStub : public IRemoteStub<SpamCallCallback>`（descriptor `u"idl.ISpamResultCallback"`）仅处理 `COMMAND_DETECT_SPAM_CALL_RESULT = 1` → `OnResult(errCode, result)`。
#### Scenario: 连接成功即发起检测
- **WHEN** `SpamCallConnection::OnAbilityConnectDone` 拿到 `remoteObject_`
- **THEN** 立即以暂存的号码与 slotId 经 `SpamCallProxy::DetectSpamCall` 发起检测

### Requirement: 骚扰引导广播
系统 SHALL 由 `ParseNeedNotifyResult` 在需要引导时发布 `EventFwk::CommonEventSupport::COMMON_EVENT_INCOMING_CALL_MISSED` 公共事件（参数 `isHarassmentGuidance`，订阅权限 `Permission::GET_TELEPHONY_STATE`）。
#### Scenario: 提醒结果回调
- **WHEN** `ReminderCallbackStubHelper::OnResult` 收到 errCode == 0 的提醒结果
- **THEN** `ParseNeedNotifyResult` 判定后决定是否发布骚扰引导广播
