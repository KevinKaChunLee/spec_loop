# Spec Delta

## MODIFIED Requirements

### Requirement: 骚扰识别查询发起
系统 SHALL 在 `CallStatusManager::ShouldBlockIncomingCall` 判定非紧急号码来临时，创建 `SpamCallAdapter` 并调用其 `DetectSpamCall(phoneNumber, slotId)`；liteOS 上骚扰来电相关外部接口暂不调用，`spam_call_connection.cpp` 的 com.spamshield 扩展连接调用点 MUST 写 `// todo!!! [spamCall] ref to spam_call_connection.cpp OnAbilityConnectDone` 占位（不用 dlopen、不发起查询、不构造 SpamCallProxy），`DisconnectAbility` 断开调用点写 `// todo!!! [spamCall] ref to spam_call_connection.cpp OnAbilityDisconnectDone` 占位；紧急号码来电 MUST NOT 发起骚扰识别（直接返回不拦截）的判定逻辑保留。

#### Scenario: 任何来电都不发起识别查询
- **WHEN** 非紧急来电号码触发 `ShouldBlockIncomingCall` 且查询调用点为 `// todo!!! [spamCall] ref to spam_call_connection.cpp OnAbilityConnectDone` 占位
- **THEN** 不发起任何识别查询（无扩展连接、无 IPC 请求），`ShouldBlockIncomingCall` 返回 false（不拦截来电）

#### Scenario: 连接成功发起查询
- **WHEN** 非紧急来电号码触发 `ShouldBlockIncomingCall` 且桩注入扩展连接成功路径（基线 ConnectServiceExtensionAbility 返回 0）
- **THEN** 连接调用点为 `// todo!!! [spamCall] ref to spam_call_connection.cpp OnAbilityConnectDone` 占位，不构造 `SpamCallProxy`、不发送 `COMMAND_DETECT_SPAM_CALL` 请求，`ShouldBlockIncomingCall` 返回 false（不拦截来电）

#### Scenario: 连接失败不拦截
- **WHEN** 桩注入扩展连接失败（基线 ConnectServiceExtensionAbility 返回非 0）
- **THEN** 不创建 `SpamCallProxy`，`DetectSpamCall` 返回 false，`ShouldBlockIncomingCall` 返回 false（不拦截来电）

#### Scenario: 紧急号码跳过识别
- **WHEN** 来电号码经 `IsEmergencyPhoneNumber` 判定为紧急号码
- **THEN** 不创建 `SpamCallAdapter`，直接返回不拦截

### Requirement: 识别结果等待与超时
系统 SHALL 由 `SpamCallAdapter::WaitForDetectResult` 通过 `TimeWaitHelper`（等待时长 `WAIT_TIME_FIVE_SECOND`，即 5000ms）同步等待识别结果的等待/超时逻辑保留：`CallbackStubHelper::OnResult` 收到回调后写入结果并 `NotifyAll`；查询占位期间无真实回调到达时 MUST 恒走等待超时路径放行来电；断开骚扰拦截扩展连接的调用点为 todo 占位，不真实断开。

#### Scenario: 回调按时到达
- **WHEN** 5000ms 内经 `SpamCallAdapter::SetDetectResult`/`SetParseResult` 注入结果并 `NotifyAll`（进程内模拟 `CallbackStubHelper::OnResult` 且 errCode == 0）
- **THEN** `WaitForDetectResult` 返回 true，等待/唤醒逻辑与基线一致，断开扩展连接调用点为 `// todo!!! [spamCall] ref to spam_call_connection.cpp OnAbilityDisconnectDone` 占位、不真实断开

#### Scenario: 等待超时
- **WHEN** `DetectSpamCall` 查询调用点占位后进入 `WaitForDetectResult`，5000ms（`WAIT_TIME_FIVE_SECOND`）内无回调到达（无真实查询时恒走该路径）
- **THEN** `WaitForDetectResult` 返回 false，断开调用点为 todo 占位不真实断开，`ShouldBlockIncomingCall` 返回 false，来电放行

### Requirement: 识别结果解析与拦截判定
系统 SHALL 由 `SpamCallAdapter::ParseDetectResult` 用 cJSON 解析回调 JSON 的判定逻辑保留：`detectResult` 为 1 时 `isBlock` 为 true、`decisionReason` 映射为 `blockReason`，`markType`/`markCount`/`markSource`/`markContent`/`isCloud`/`markDetails` 填入 `NumberMarkInfo`；cJSON MUST 经本 change 引入的 stub/ 同名打桩桩实现提供（不依赖真实 cJSON 库）；查询占位期间无识别结果到达时 MUST 默认放行来电；`ShouldBlockIncomingCall` 在 `isBlock` 为 true 时拦截来电，并把 `numberMarkInfo`/`blockReason`/`detectDetails` 写入通话对象（`SetNumberMarkInfo`、`SetBlockReason`、`SetDetectDetails` 及 extraParams 的 `blockReason`）的写入链路保留。

#### Scenario: 判定拦截
- **WHEN** 进程内注入的回调 JSON 中 `detectResult == 1`（经打桩 cJSON 解析）
- **THEN** `ShouldBlockIncomingCall` 返回 true，来电被拦截，通话对象携带标记信息与 `blockReason`

#### Scenario: 判定放行但保留标记
- **WHEN** 进程内注入的回调 JSON 中 `detectResult != 1` 且解析成功
- **THEN** 不拦截来电，但 `NumberMarkInfo` 与 `blockReason` 已写入通话对象

### Requirement: 白名单转黄页查询与骚扰提醒
系统 SHALL 在 `blockReason == DECISION_REASON_TRUSTLIST`（值 2）时经 `CallNumberUtils::QueryYellowPageAndMarkInfo` 转查黄页标记，黄页查询（DataShare/号码识别）调用点 MUST 写 `// todo!!! [numberIdentity] ref to call_number_utils.cpp QueryYellowPageAndMarkInfo` 占位；在未拦截且 `markType` 为 `MARK_TYPE_CRANK`/`MARK_TYPE_FRAUD`/`MARK_TYPE_PROMOTE_SALES`/`MARK_TYPE_HOUSE_AGENT` 之一时经 `SpamCallConnection::RequireCallReminder` 发送 `COMMAND_DETECT_NEED_NOTIFY` 请求的链路判定保留；`ReminderCallbackStubHelper::OnResult` 解析出 `reminderResult` 为 true 时发布 `COMMON_EVENT_INCOMING_CALL_MISSED` 公共事件（携带 `isHarassmentGuidance`、`slotId` 参数）的调用点 MUST 写 `// todo!!! [broadcast] ref to spam_call_adapter.cpp ParseNeedNotifyResult` 占位，提醒回调链路保留占位、不真实发布。

#### Scenario: 白名单转黄页
- **WHEN** `CallbackStubHelper::OnResult` 解析得 `blockReason == 2`
- **THEN** 进入经 `QueryYellowPageAndMarkInfo` 转查黄页标记的分支，调用点写 `// todo!!! [numberIdentity] ref to call_number_utils.cpp QueryYellowPageAndMarkInfo` 占位，不发起真实查询

#### Scenario: 骚扰提醒回调
- **WHEN** `COMMAND_DETECT_NEED_NOTIFY` 回调 JSON 中 `reminderResult == true`
- **THEN** 进入发布 `COMMON_EVENT_INCOMING_CALL_MISSED` 公共事件的分支，发布调用点写 `// todo!!! [broadcast] ref to spam_call_adapter.cpp ParseNeedNotifyResult` 占位，链路判定逻辑保留

### Requirement: 响铃一次来电判定
系统 SHALL 由 `CallStatusManager::IsRingOnceCall` 在号码为 `MARK_TYPE_YELLOW_PAGE` 或已有联系人名时跳过判定的逻辑保留；否则查询设置项 `spamshield_sim{accountId+1}_phone_switch_ring_once`（经 `SettingsDataShareHelper`）的调用点 MUST 写 `// todo!!! [database] ref to call_status_manager.cpp IsRingOnceCall` 占位，为 1 时以骚扰识别后的剩余等待窗口（`WAIT_TIME_THREE_SECOND`）创建 `TimeWaitHelper` 等待：窗口内来电即断开（断开路径 `NotifyAll`）判定为响铃一次并走 `HandleRingOnceCall`，超时未断开 MUST 判定为普通来电；识别结果恒放行场景下设置项查询占位按默认值处理时 MUST 默认判定为非响铃一次。

#### Scenario: 窗口内来电消失
- **WHEN** 响铃一次设置项查询调用点为 `// todo!!! [database] ref to call_status_manager.cpp IsRingOnceCall` 占位且进程内注入设置值为 1，`WAIT_TIME_THREE_SECOND` 窗口内来电进入断开状态（断开路径 `NotifyAll`）
- **THEN** `IsRingOnceCall` 返回 true，来电按 `HandleRingOnceCall` 走响铃一次未接处理，判定逻辑与基线一致

#### Scenario: 窗口超时
- **WHEN** 等待窗口超时且来电仍存在
- **THEN** `IsRingOnceCall` 返回 false，来电按正常来电路径继续

#### Scenario: 占位默认非响铃一次
- **WHEN** 响铃一次设置项查询调用点为 `// todo!!! [database] ref to call_status_manager.cpp IsRingOnceCall` 占位且按默认值（非 1）返回
- **THEN** `IsRingOnceCall` 返回 false，来电按正常来电路径继续

#### Scenario: 黄页或联系人号码跳过
- **WHEN** 来电号码标记为 `MARK_TYPE_YELLOW_PAGE` 或联系人名非空
- **THEN** 不进行响铃一次判定，直接返回 false
