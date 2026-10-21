# Spec Delta

## MODIFIED Requirements

### Requirement: 来电时连接骚扰防护服务扩展
系统 SHALL 在 `SpamCallAdapter::DetectSpamCall(phoneNumber, slotId)` 中照抄记录待检号码与构建 `AAFwk::Want`（指向 `com.spamshield` / `SpamShieldServiceExtAbility`，携带号码与槽位）的逻辑；`SpamCallAdapter::ConnectSpamCallAbility` 对外部骚扰识别 Ability 的连接调用（`AAFwk::ExtensionManagerClient::ConnectServiceExtensionAbility`）经 `stub/` 打桩并标注 `// todo!!! [spamCall] ref to spam_call_adapter.cpp ConnectSpamCallAbility`（AGENTS：骚扰来电相关接口暂不调用、不用 dlopen，依赖外部查询接口适配；桩默认返回失败/不可用语义，与基线"连接失败"分支一致）；原 `IPCSkeleton::ResetCallingIdentity` / `SetCallingIdentity` 包夹随 IPC 层不迁移移除（design D3）；`connection_` 持有按 design D5 换 std 智能指针，`spam_call_adapter.cpp` 文件级全局 `connection_` 的覆盖隐患按 design D9 照抄并注明（单线程下无并发冲突，不修正）；`ffrt::mutex` 守卫随全仓去锁删除（design D6 锁行/D8）。连接失败时返回 false 且不阻塞来电（照抄）。

#### Scenario: 连接成功
- **WHEN** todo 桩注入使 `ConnectServiceExtensionAbility` 语义返回 0
- **THEN** `DetectSpamCall` 返回 true，后续由 `SpamCallConnection::OnAbilityConnectDone` 取得远端对象（保留形态，见「检测 IPC 携带结果回调桩」条）

#### Scenario: 连接失败不影响来电
- **WHEN** 桩默认态返回非 0 或 `connection_` 为空
- **THEN** `DetectSpamCall` 返回 false，`CallStatusManager::ShouldBlockIncomingCall` 直接返回 false，来电继续正常流程（照抄）

### Requirement: 检测 IPC 携带结果回调桩
系统 SHALL 保留回环形态：`SpamCallConnection::OnAbilityConnectDone` 保存远端对象、`SpamCallProxy::DetectSpamCall` 发送侧（code `COMMAND_DETECT_SPAM_CALL`（值 1）、接口描述符 `idl.ISpamShieldService`、parcel 依次号码（`WriteString16`）/`slotId`（`WriteInt32`）/新建回调桩 `CallbackStubHelper` 的 `WriteRemoteObject`）与 `SpamCallStub : IRemoteStub<SpamCallCallback>`（描述符 `idl.ISpamResultCallback`）的 `OnRemoteRequest` 按 `COMMAND_DETECT_SPAM_CALL_RESULT`（值 1）分发 `OnResult(errCode, result)` 的结构照抄；`spam_call_connection.cpp` / `spam_call_proxy.cpp` / `spam_call_stub.cpp` 按「逻辑保留」原则保留可编译最小形（design Open Question 6，登入复核），对外部骚扰识别服务的 IPC 发送与回调接收调用点标注 `// todo!!! [spamCall] ref to spam_call_proxy.cpp DetectSpamCall`（liteOS 无 IPC 通路，回环语义经桩注入驱动验证）。

#### Scenario: 回调桩完成回环
- **WHEN** 测试经桩注入向 `CallbackStubHelper` 送出 code=1 的结果（基线为骚扰防护服务发送该请求）
- **THEN** descriptor 校验通过后进入 `CallbackStubHelper::OnResult`，`errCode` 与 JSON `result` 字符串被送回 `SpamCallAdapter`（照抄）

#### Scenario: descriptor 不匹配
- **WHEN** `SpamCallStub::OnRemoteRequest` 读到的接口 token 与 `SpamCallCallback` 描述符不一致（桩注入构造）
- **THEN** 返回 `TELEPHONY_ERR_DESCRIPTOR_MISMATCH`，不解析数据（保留形态照抄）

### Requirement: 同步等待检测结果（5 秒超时）
系统 SHALL 由 `SpamCallAdapter::WaitForDetectResult` 使用 `TimeWaitHelper(WAIT_TIME_FIVE_SECOND)`（5000ms，定义于 `interfaces/innerkits/call_manager_base.h`）阻塞等待，结果回调（`CallbackStubHelper::OnResult` 末尾 `NotifyAll`）或超时后都调用 `SpamCallAdapter::DisconnectSpamCallAbility`（`ExtensionManagerClient::DisconnectAbility` 断开调用点标注 `// todo!!! [spamCall] ref to spam_call_adapter.cpp DisconnectSpamCallAbility`）。`TimeWaitHelper` SHALL 保留形态：`NotifyAll` 与 `WaitForResult` 的语义照抄——未通知则 `cv_.wait_until` 等待至超时返回 false；预先已置位 `isNotified_` 时直接返回 false。`ffrt::mutex` 锁守卫随全仓去锁删除（design D6 锁行/D8 单线程）；等待与超时返回语义随 `ffrt` 依赖不迁移平移保留（基线 `ffrt::cv_status::timeout` 判定不承载真实 ffrt 调用）。

#### Scenario: 结果按时到达
- **WHEN** 回调在 5 秒内调用 `NotifyAll`
- **THEN** `WaitForDetectResult` 返回 true，随后主动断开服务连接（断开调用点 todo [spamCall]）

#### Scenario: 检测超时
- **WHEN** 5 秒内无回调
- **THEN** `WaitForResult` 等待超时返回 false，`WaitForDetectResult` 返回 false 并断开连接，来电不拦截（照抄）

### Requirement: 检测结果 JSON 解析与码表映射
系统 SHALL 照抄保留检测判定链与码表：`CallbackStubHelper::OnResult` 先行 `SpamCallAdapter::SetDetectResult` 保存原始结果；`errCode==0` 时调用 `SpamCallAdapter::ParseDetectResult` 解析（字段 `detectResult` 等于 1 映射为 `isBlock`、字段 `decisionReason` 映射为 `blockReason`）；`SpamCallAdapter::ParseMarkResults` 进一步把 `markType`（映射到 `MarkType` 枚举码表，`interfaces/innerkits/call_manager_base.h`）、`markCount`、`markSource`、`markContent`、`isCloud`、`markDetails` 装入 `NumberMarkInfo`（结构体定义于 `interfaces/innerkits/call_manager_info.h`），`detectDetails` 单独成串；解析完成后 `SetParseResult` 存回适配器。cJSON 解析调用经 `stub/cjson_stub` 同名桩承载（design D6 cJSON 行）；维测 `CallManagerHisysevent::WriteIncomingNumIdentityBehaviorEvent(markType, isBlock, blockReason)` 经 `stub/hisysevent_stub` 桩以日志打印替代 HiSysEvent（design D5，签名不变）。`DECISION_REASON_TRUSTLIST`（值 2，定义于 `callback_stub_helper.cpp`）回落 `CallNumberUtils::QueryYellowPageAndMarkInfo(numberMarkInfo, 待检号码)` 的本地黄页查询联动保留（该查询出口 todo [database]，处置见 call-utils delta「号码身份数据库助手」条）。

#### Scenario: 拦截判定
- **WHEN** `detectResult` 为数字 1
- **THEN** `isBlock` 为 true，`blockReason` 取 `decisionReason` 数值（照抄）

#### Scenario: 信任名单回落黄页查询
- **WHEN** `blockReason` 等于 `DECISION_REASON_TRUSTLIST`（值 2）
- **THEN** 调用 `CallNumberUtils::QueryYellowPageAndMarkInfo` 回落查询本地黄页标记（查询出口 todo [database]，逻辑保留照抄）

#### Scenario: 识别行为维测
- **WHEN** 解析完成
- **THEN** `WriteIncomingNumIdentityBehaviorEvent` 维测点经 `stub/hisysevent_stub` 桩以日志输出（design D5）

### Requirement: 骚扰标记触发提醒回调链路
系统 SHALL 照抄保留判定链：`SpamCallAdapter::ParseMarkResults` 判定"未拦截且标记类型为骚扰类"（`MarkType::MARK_TYPE_CRANK` / `MARK_TYPE_FRAUD` / `MARK_TYPE_PROMOTE_SALES` / `MARK_TYPE_HOUSE_AGENT`，码表见 `interfaces/innerkits/call_manager_base.h` 的 `enum class MarkType`）时调用 `SpamCallConnection::RequireCallReminder`，经 `SpamCallProxy::RequireCallReminder` 发送 code `COMMAND_DETECT_NEED_NOTIFY`（值 3）请求（parcel：`slotId` + `ReminderCallbackStubHelper` 回调桩）的对外部骚扰识别 Ability 调用点标注 `// todo!!! [spamCall] ref to spam_call_proxy.cpp RequireCallReminder`；回调 SHALL 由 `ReminderCallbackStubHelper::OnResult` 接收：`errCode==0` 时 `SpamCallAdapter::ParseNeedNotifyResult` 解析字段 `reminderResult` / `slotId`（回环形态保留，经桩注入驱动验证）。

#### Scenario: 提醒查询 IPC
- **WHEN** 标记为骚扰类且未拦截
- **THEN** `SpamCallProxy::RequireCallReminder` 发送 code=3 请求并携带 `ReminderCallbackStubHelper`（调用点 todo [spamCall]，回环经桩注入验证）

#### Scenario: 非骚扰标记不打扰服务
- **WHEN** 标记类型不属于上述四种骚扰枚举或为拦截态
- **THEN** 不发起 `RequireCallReminder`（照抄）

### Requirement: 骚扰引导广播发布
系统 SHALL 照抄保留 `ParseNeedNotifyResult` 判定 `reminderResult` 为 true 时构建 `AAFwk::Want`（action 为 `EventFwk::CommonEventSupport::COMMON_EVENT_INCOMING_CALL_MISSED`，参数 `isHarassmentGuidance=true`、`slotId`）的组装逻辑与内容完整性判定；`EventFwk::CommonEventManager::PublishCommonEvent` 发布调用点标注 `// todo!!! [broadcast] ref to spam_call_adapter.cpp ParseNeedNotifyResult`（AGENTS：广播 EventFwk::CommonEventManager 相关接口暂不调用，逻辑保留）；订阅者权限 `Permission::GET_TELEPHONY_STATE` 参数面照抄保留（liteOS 不做权限校验、不调用校验接口）。

#### Scenario: 发布成功
- **WHEN** `reminderResult` 为 true
- **THEN** 组装并发布携带骚扰引导参数的未接来电广播（发布调用点 todo [broadcast]，组包经桩注入断言）

#### Scenario: 广播内容不完整即停止
- **WHEN** JSON 缺 `slotId`/`reminderResult` 或解析失败
- **THEN** 直接返回，不发布广播（照抄）

### Requirement: 来电拦截判定与落账路径
系统 SHALL 照抄保留 `CallStatusManager::IsRejectCall` 对 `ShouldBlockIncomingCall` 的调用链（基线"非 `TYPE_VOIP` / 非 `TYPE_BLUETOOTH`"排除条件照抄；`TYPE_BLUETOOTH` 通话对象已随 BLUETOOTH 类型通话删除不可达，见 call-object-management delta）：先用 `DelayedSingleton<CellularCallConnection>::GetInstance()->IsEmergencyPhoneNumber` 排除紧急号码——连接类按 design D4 保留为适配器、内部改调 `CellularCallClient::GetInstance()` 桩（见 telephony-interaction delta）；再执行 `DetectSpamCall` + `WaitForDetectResult`，成功取回 `GetParseResult` 后将 `NumberMarkInfo` / `blockReason` / `detectDetails` 写回电话对象（`call->SetNumberMarkInfo` / `SetBlockReason` / `SetDetectDetails`）并写入 extraParams `blockReason`；`isBlock` 为 true 时返回拦截。`IsRejectCall` 判定拦截后 SHALL 走 `CallStatusManager::HandleRejectCall(call, isBlock=true)`：设置 `TelCallState::CALL_STATUS_INCOMING`、`call->RejectCall()` 拒接、`CallControlManager::AddBlockLogAndNotification` 记拦截日志与通知；非拦截时同名函数走 `AddCallLogAndNotification`（通知出口按 call-state-observer 能力桩化）；维测 `CallManagerHisysevent::HiWriteBehaviorEventPhoneUE(CALL_INCOMING_REJECT_BY_SYSTEM, ..., REJECT_BY_NUM_BLOCK)` 经 `stub/hisysevent_stub` 桩以日志输出。

#### Scenario: 骚扰拦截
- **WHEN** 检测返回 `isBlock=true`
- **THEN** 来电被 `RejectCall` 拒接，标记信息与 `blockReason` 已写入 call 对象，落账走 `AddBlockLogAndNotification`（照抄）

#### Scenario: 紧急号码旁路
- **WHEN** 来电号码为紧急号码（经 `CellularCallClient::GetInstance()` 桩的适配器判定）
- **THEN** `ShouldBlockIncomingCall` 返回 false，不发起骚扰检测（照抄）

### Requirement: 响一声来电检测
系统 SHALL 照抄保留 `CallStatusManager::IsRingOnceCall` 判定链（与 call-status-management delta「响一声拦截」条同口径）：`IncomingHandle` 中非 `TYPE_VOIP`、标记非 `MARK_TYPE_YELLOW_PAGE`、非联系人的场景判定；经 `SettingsDataShareHelper::Query`（DataShare URI `datashare:///com.ohos.settingsdata/entry/settingsdata/SETTINGSDATA?Proxy=true&key=...`）读设置键 `spamshield_sim{N}_phone_switch_ring_once`（N 为 `info.accountId + 1`）的查询出口标注 `// todo!!! [database]`（逻辑保留）；开关关闭返回 false；开启时构造等待时长 = `WAIT_TIME_THREE_SECOND`（3000ms）减去骚扰检测已耗时长（`detectStartTime` 与当前时间差），用 `CallStatusManager` 自持的 `TimeWaitHelper` 等待 `DisconnectedHandle` 中的 `timeWaitHelper_->NotifyAll`（保留形态，见「同步等待检测结果」条）。命中后 `CallStatusManager::HandleRingOnceCall` SHALL 设置 `TelCallState::CALL_STATUS_INCOMING` 并直接 `CallControlManager::AddCallLogAndNotification`，不进入正常来电对象/响铃路径（照抄）。基线"非 `TYPE_BLUETOOTH`"排除条件随 BLUETOOTH 类型通话删除不可达（判定链本体照抄）。

#### Scenario: 响一声命中
- **WHEN** 开关（查询出口 todo [database]，经桩注入开启）开启且来电在剩余等待窗口内断开
- **THEN** `IsRingOnceCall` 返回 true，`HandleRingOnceCall` 直接记未接日志与通知（照抄）

#### Scenario: 非响一声
- **WHEN** 等待窗口超时或来电持续存在
- **THEN** `IsRingOnceCall` 返回 false，来电继续正常流程（照抄）

#### Scenario: 黄页/联系人跳过
- **WHEN** 号码标记为 `MARK_TYPE_YELLOW_PAGE` 或命中联系人（联系人查询出口 todo [database]）
- **THEN** 不做响一声检测（照抄）
