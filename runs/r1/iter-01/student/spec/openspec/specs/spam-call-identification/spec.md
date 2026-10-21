# Spam Call Identification Specification

## Purpose
描述目标仓中现有的骚扰来电识别（spam call shielding）能力：来电建立时连接外部骚扰防护服务 `com.spamshield` 的 `SpamShieldServiceExtAbility`（AA ServiceExtension 连接 + IPC，非 dlopen、非 DataShare），发起骚扰检测并在结果回调中解析拦截判定与号码标记；检测判定为拦截时走来电拦截/落账路径，判定为骚扰标记（未拦截）时再向服务发起"提醒"查询，结果经广播 `COMMON_EVENT_INCOMING_CALL_MISSED` 通知联系人应用；同时提供"响一声"来电检测与同步等待原语 `TimeWaitHelper`。落点：`services/spam_call/src/{spam_call_adapter,spam_call_connection,spam_call_proxy,spam_call_stub,callback_stub_helper,reminder_callback_stub_helper,time_wait_helper}.cpp`；检测触发/消费入口在 `CallStatusManager`（`ShouldBlockIncomingCall` / `IsRingOnceCall`）。本能力无专属编译宏（rg 核实：`services/spam_call/` 内无特性 `#ifdef`，七个源文件在 `callmanager.gni` 无条件编入）。

## Requirements

### Requirement: 来电时连接骚扰防护服务扩展
系统 SHALL 在 `SpamCallAdapter::DetectSpamCall(phoneNumber, slotId)` 中记录待检号码，构建 `AAFwk::Want` 指向 `com.spamshield` / `SpamShieldServiceExtAbility`，经 `SpamCallAdapter::ConnectSpamCallAbility` 创建携带号码与槽位的 `SpamCallConnection` 并调用 `AAFwk::ExtensionManagerClient::ConnectServiceExtensionAbility`（连接期间 `IPCSkeleton::ResetCallingIdentity` / `SetCallingIdentity`）；连接失败时返回 false 且不阻塞来电。该外部 AA 连接是独立的移植桩化出口。

#### Scenario: 连接成功
- **WHEN** `ConnectServiceExtensionAbility` 返回 0
- **THEN** `DetectSpamCall` 返回 true，后续由 `SpamCallConnection::OnAbilityConnectDone` 取得远端对象

#### Scenario: 连接失败不影响来电
- **WHEN** 返回码非 0 或 `connection_` 为空
- **THEN** `DetectSpamCall` 返回 false，`CallStatusManager::ShouldBlockIncomingCall` 直接返回 false，来电继续正常流程

### Requirement: 检测 IPC 携带结果回调桩
系统 SHALL 在 `SpamCallConnection::OnAbilityConnectDone` 中保存远端对象并通过 `SpamCallProxy::DetectSpamCall` 发送 IPC：code 为 `COMMAND_DETECT_SPAM_CALL`（值 1），接口描述符 `idl.ISpamShieldService`，parcel 内容依次为号码（`WriteString16`）、`slotId`（`WriteInt32`）与新建回调桩 `CallbackStubHelper` 的 `WriteRemoteObject`。回调桩继承 `SpamCallStub : IRemoteStub<SpamCallCallback>`（描述符 `idl.ISpamResultCallback`）；`SpamCallStub::OnRemoteRequest` 校验 descriptor 后按 `COMMAND_DETECT_SPAM_CALL_RESULT`（值 1）分发 `OnResult(errCode, result)`。

#### Scenario: 回调桩完成回环
- **WHEN** 骚扰防护服务向 `CallbackStubHelper` 发送 code=1 的请求
- **THEN** descriptor 校验通过后进入 `CallbackStubHelper::OnResult`，`errCode` 与 JSON `result` 字符串被送回 `SpamCallAdapter`

#### Scenario: descriptor 不匹配
- **WHEN** `SpamCallStub::OnRemoteRequest` 读到的接口 token 与 `SpamCallCallback` 描述符不一致
- **THEN** 返回 `TELEPHONY_ERR_DESCRIPTOR_MISMATCH`，不解析数据

### Requirement: 同步等待检测结果（5 秒超时）
系统 SHALL 由 `SpamCallAdapter::WaitForDetectResult` 使用 `TimeWaitHelper(WAIT_TIME_FIVE_SECOND)`（5000ms，定义于 `interfaces/innerkits/call_manager_base.h`）阻塞等待，结果回调（`CallbackStubHelper::OnResult` 末尾 `NotifyAll`）或超时后都调用 `SpamCallAdapter::DisconnectSpamCallAbility`（`ExtensionManagerClient::DisconnectAbility`）断开服务连接。`TimeWaitHelper` SHALL 提供 `NotifyAll` 与 `WaitForResult`：未通知则 `cv_.wait_until` 等待至超时返回 false；预先已置位 `isNotified_` 时直接返回 false。

#### Scenario: 结果按时到达
- **WHEN** 回调在 5 秒内调用 `NotifyAll`
- **THEN** `WaitForDetectResult` 返回 true，随后主动断开服务连接

#### Scenario: 检测超时
- **WHEN** 5 秒内无回调
- **THEN** `WaitForResult` 判定 `ffrt::cv_status::timeout` 返回 false，`WaitForDetectResult` 返回 false 并断开连接，来电不拦截

### Requirement: 检测结果 JSON 解析与码表映射
系统 SHALL 在 `CallbackStubHelper::OnResult` 中先行 `SpamCallAdapter::SetDetectResult` 保存原始结果；`errCode==0` 时调用 `SpamCallAdapter::ParseDetectResult`（cJSON 解析）：字段 `detectResult` 等于 1 映射为 `isBlock`，字段 `decisionReason` 映射为 `blockReason`；`SpamCallAdapter::ParseMarkResults` 进一步把 `markType`（映射到 `MarkType` 枚举码表）、`markCount`、`markSource`、`markContent`、`isCloud`、`markDetails` 装入 `NumberMarkInfo`（结构体定义于 `interfaces/innerkits/call_manager_info.h`），`detectDetails` 单独成串；解析完成后 `SetParseResult` 存回适配器。

#### Scenario: 拦截判定
- **WHEN** `detectResult` 为数字 1
- **THEN** `isBlock` 为 true，`blockReason` 取 `decisionReason` 数值

#### Scenario: 信任名单回落黄页查询
- **WHEN** `blockReason` 等于 `DECISION_REASON_TRUSTLIST`（值 2，定义于 `callback_stub_helper.cpp`）
- **THEN** 调用 `CallNumberUtils::QueryYellowPageAndMarkInfo(numberMarkInfo, 待检号码)` 回落查询本地黄页标记（该查询落点 `utils/src/call_number_utils.cpp` / `utils/src/number_identity_data_base_helper.cpp`，属号码标记数据库能力，不在本能力内）

#### Scenario: 识别行为维测
- **WHEN** 解析完成
- **THEN** `CallManagerHisysevent::WriteIncomingNumIdentityBehaviorEvent(markType, isBlock, blockReason)` 上报（HMOS 上为 HiSysEvent）

### Requirement: 骚扰标记触发提醒回调链路
系统 SHALL 在 `SpamCallAdapter::ParseMarkResults` 判定"未拦截且标记类型为骚扰类"（`MarkType::MARK_TYPE_CRANK` / `MARK_TYPE_FRAUD` / `MARK_TYPE_PROMOTE_SALES` / `MARK_TYPE_HOUSE_AGENT`，码表见 `interfaces/innerkits/call_manager_base.h` 的 `enum class MarkType`）时调用 `SpamCallConnection::RequireCallReminder`，经 `SpamCallProxy::RequireCallReminder` 发送 code `COMMAND_DETECT_NEED_NOTIFY`（值 3）的 IPC（parcel：`slotId` + `ReminderCallbackStubHelper` 回调桩）。回调 SHALL 由 `ReminderCallbackStubHelper::OnResult` 接收：`errCode==0` 时 `SpamCallAdapter::ParseNeedNotifyResult` 解析字段 `reminderResult` / `slotId`。

#### Scenario: 提醒查询 IPC
- **WHEN** 标记为骚扰类且未拦截
- **THEN** `SpamCallProxy::RequireCallReminder` 发送 code=3 请求并携带 `ReminderCallbackStubHelper`

#### Scenario: 非骚扰标记不打扰服务
- **WHEN** 标记类型不属于上述四种骚扰枚举或为拦截态
- **THEN** 不发起 `RequireCallReminder`

### Requirement: 骚扰引导广播发布
系统 SHALL 在 `ParseNeedNotifyResult` 判定 `reminderResult` 为 true 时构建 `AAFwk::Want`（action 为 `EventFwk::CommonEventSupport::COMMON_EVENT_INCOMING_CALL_MISSED`，参数 `isHarassmentGuidance=true`、`slotId`），以订阅者权限 `Permission::GET_TELEPHONY_STATE` 通过 `EventFwk::CommonEventManager::PublishCommonEvent` 发布。该广播出口在移植时为独立桩化点。

#### Scenario: 发布成功
- **WHEN** `reminderResult` 为 true
- **THEN** 发布携带骚扰引导参数的未接来电广播

#### Scenario: 广播内容不完整即停止
- **WHEN** JSON 缺 `slotId`/`reminderResult` 或解析失败
- **THEN** 直接返回，不发布广播

### Requirement: 来电拦截判定与落账路径
系统 SHALL 由 `CallStatusManager::IsRejectCall`（对非 `TYPE_VOIP` / 非 `TYPE_BLUETOOTH` 来电）调用 `ShouldBlockIncomingCall`：先用 `DelayedSingleton<CellularCallConnection>::GetInstance()->IsEmergencyPhoneNumber` 排除紧急号码，再执行 `DetectSpamCall` + `WaitForDetectResult`，成功取回 `GetParseResult` 后将 `NumberMarkInfo` / `blockReason` / `detectDetails` 写回电话对象（`call->SetNumberMarkInfo` / `SetBlockReason` / `SetDetectDetails`）并写入 extraParams `blockReason`；`isBlock` 为 true 时返回拦截。`IsRejectCall` 判定拦截后 SHALL 走 `CallStatusManager::HandleRejectCall(call, isBlock=true)`：设置 `TelCallState::CALL_STATUS_INCOMING`、`call->RejectCall()` 拒接、`CallControlManager::AddBlockLogAndNotification` 记拦截日志与通知；非拦截时同名函数走 `AddCallLogAndNotification`。维测 SHALL 上报 `CallManagerHisysevent::HiWriteBehaviorEventPhoneUE(CALL_INCOMING_REJECT_BY_SYSTEM, ..., REJECT_BY_NUM_BLOCK)`。

#### Scenario: 骚扰拦截
- **WHEN** 检测返回 `isBlock=true`
- **THEN** 来电被 `RejectCall` 拒接，标记信息与 `blockReason` 已写入 call 对象，落账走 `AddBlockLogAndNotification`

#### Scenario: 紧急号码旁路
- **WHEN** 来电号码为紧急号码
- **THEN** `ShouldBlockIncomingCall` 返回 false，不发起骚扰检测

### Requirement: 响一声来电检测
系统 SHALL 由 `CallStatusManager::IsRingOnceCall`（`IncomingHandle` 中对非 `TYPE_VOIP` / 非 `TYPE_BLUETOOTH` 来电、且标记非 `MARK_TYPE_YELLOW_PAGE`、非联系人的场景）实现响一声检测：经 `SettingsDataShareHelper::Query`（DataShare URI `datashare:///com.ohos.settingsdata/entry/settingsdata/SETTINGSDATA?Proxy=true&key=...`）读设置键 `spamshield_sim{N}_phone_switch_ring_once`（N 为 `info.accountId + 1`），开关关闭返回 false；开启时构造等待时长 = `WAIT_TIME_THREE_SECOND`（3000ms）减去骚扰检测已耗时长（`detectStartTime` 与当前时间差），用 `CallStatusManager` 自持的 `TimeWaitHelper` 等待 `DisconnectedHandle` 中的 `timeWaitHelper_->NotifyAll`。命中后 `CallStatusManager::HandleRingOnceCall` SHALL 设置 `TelCallState::CALL_STATUS_INCOMING` 并直接 `CallControlManager::AddCallLogAndNotification`，不进入正常来电对象/响铃路径。

#### Scenario: 响一声命中
- **WHEN** 开关开启且来电在剩余等待窗口内断开
- **THEN** `IsRingOnceCall` 返回 true，`HandleRingOnceCall` 直接记未接日志与通知

#### Scenario: 非响一声
- **WHEN** 等待窗口超时或来电持续存在
- **THEN** `IsRingOnceCall` 返回 false，来电继续正常流程

#### Scenario: 黄页/联系人跳过
- **WHEN** 号码标记为 `MARK_TYPE_YELLOW_PAGE` 或命中联系人
- **THEN** 不做响一声检测