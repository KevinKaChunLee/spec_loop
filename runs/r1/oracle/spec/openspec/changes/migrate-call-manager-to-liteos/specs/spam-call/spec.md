# Spec Delta

## MODIFIED Requirements

### Requirement: 骚扰检测编排
系统 SHALL 由 `SpamCallAdapter::DetectSpamCall(phoneNumber, slotId)` 保留检测编排逻辑；`AAFwk::ExtensionManagerClient::ConnectServiceExtensionAbility` 扩展连接调用点以 `// todo!!! [spam]` 占位（不真正连接 `com.spamshield` 扩展）；`WaitForDetectResult()` 经 `TimeWaitHelper(WAIT_TIME_FIVE_SECOND)` 限时 5000 毫秒等待逻辑保留，占位形态下按超时路径收尾（默认不拦截）并执行 `DisconnectSpamCallAbility()`（占位）。
#### Scenario: 检测超时
- **WHEN** `TimeWaitHelper::WaitForResult()` 5000 毫秒内未收到 `NotifyAll()`（占位形态恒如此）
- **THEN** 检测按超时处理并断开扩展连接（占位），拦截判定取默认不拦截

### Requirement: 检测结果解析与黄页回退
系统 SHALL 由 `CallbackStubHelper::OnResult`（errCode == 0）执行 `ParseDetectResult`（cJSON 解析逻辑保留，cJSON 经桩）解析 `DETECT_RESULT`（== 1 判拦截）、`DECISION_REASON`、`MARK_TYPE/MARK_COUNT/MARK_SOURCE/MARK_CONTENT/IS_CLOUD/MARK_DETAILS/DETECT_DETAILS` 后 `SetParseResult(isBlock, numberMarkInfo, blockReason, detectDetails)`；黄页回退 `CallNumberUtils::QueryYellowPageAndMarkInfo` 的 DataShare 查询调用点以 `// todo!!! [database]` 占位（返回默认未命中）；随后以日志记录原 `CallManagerHisysevent::WriteIncomingNumIdentityBehaviorEvent` 信息并 `NotifyAll()`；`RequireCallReminder` 提醒请求调用点占位。
#### Scenario: 标记为骚扰且不拦截
- **WHEN** 桩注入检测结果 `markType` 为 `MARK_TYPE_CRANK/MARK_TYPE_FRAUD/MARK_TYPE_PROMOTE_SALES/MARK_TYPE_HOUSE_AGENT` 且 `isBlock` 为假
- **THEN** 提醒请求调用点为 todo 占位，解析结果（含 `NumberMarkInfo` 字段）与黄页回退判定逻辑照常执行

### Requirement: 骚扰引导广播
系统 SHALL 由 `ParseNeedNotifyResult` 保留需要引导的判定逻辑；`EventFwk::CommonEventSupport::COMMON_EVENT_INCOMING_CALL_MISSED` 公共事件发布调用点以 `// todo!!! [broadcast]` 占位（不真正发布广播）。
#### Scenario: 提醒结果回调
- **WHEN** 提醒结果回调（errCode == 0）触发 `ParseNeedNotifyResult`
- **THEN** 判定逻辑执行，发布调用点为 todo 占位并返回成功，不产生真实广播

## REMOVED Requirements

### Requirement: 检测命令 IPC
**Reason**: AGENTS.md 外部依赖处理：骚扰来电相关接口在 liteOS 暂不调用、不用 dlopen；`com.spamshield` 扩展 IPC 通路不迁移。
**Migration**: `SpamCallProxy`/`SpamCallStub`（descriptor `u"idl.ISpamShieldService"`/`u"idl.ISpamResultCallback"`）不迁移；检测结果改由桩/默认值供给 `SetParseResult`，检测请求调用点以 `// todo!!! [spam]` 占位。
