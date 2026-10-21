# Spec Delta

## MODIFIED Requirements

### Requirement: 拨号入口分发
系统 SHALL 由 `CallControlManager::DialCall` 依次完成：`NumberLegalityCheck` 号码合法性、`CallNumberUtils::RemoveSeparatorsPhoneNumber` 去分隔符、`CallNumberUtils::CheckNumberIsEmergency` 紧急判定（命中则 extras 的 dialScene 置 `DialScene::CALL_EMERGENCY`）、`CanDial`（`DialPolicy` + `CanDialMulityCall`）前置校验、`PackageDialInformation` 暂存拨号信息（`AppExecFwk::PacMap` extras 以结构体替换），最后转 `CallRequestHandler::DialCall` → `CallRequestProcess::DialRequest`（FDN 校验：`IsFdnEnabled` / `GetFdnNumberList` / `IsFdnNumber`，经本 change 引入的 `CoreServiceClient::GetInstance().Xxx()` 打桩执行；MMI 码判定：经 `CellularCallClient::GetInstance()` 打桩执行 `IsMmiCode`），再经 `HandleDialRequest` 按 dialType 分发至 `CarrierDialProcess` / `VoiceMailDialProcess`，未知 dialType 返回 `CALL_ERR_UNKNOW_DIAL_TYPE`。基线卫星开关检查（`SatelliteCallControl::IsSatelliteSwitchEnable` / `IsAllowedSatelliteDialCall` 及置 `TYPE_SATELLITE`）与 OTT/蓝牙分发（`OttDialProcess` / `BluetoothDialProcess`）MUST 移除；`CallDialog` 对话框经本 change 引入的打桩实现（`DialogConnectExtension` / `DialogProcessMMICodeExtension` 调用点保留但走桩）。

#### Scenario: FDN 禁拨名单拦截
- **WHEN** 非 ECC 的 `DIAL_CARRIER_TYPE` 拨号且经 `CoreServiceClient::GetInstance()` 打桩 `IsFdnEnabled` 为真、号码不在 `GetFdnNumberList` 返回列表中
- **THEN** `DialRequest` 返回 `CALL_ERR_DIAL_FAILED`，`NotifyCallEventUpdated` 上报 `EVENT_INVALID_FDN_NUMBER`，并经 `CallDialog` 桩弹 "CALL_FAILED_DUE_TO_FDN"

#### Scenario: MMI 码走对话框不走通话
- **WHEN** 拨打的号码被 `IsMmiCode`（经 `CellularCallClient::GetInstance()` 打桩）判定为 MMI 码
- **THEN** 不创建通话对象、不上报 `CALL_STATUS_DIALING`，`CallDialog::DialogProcessMMICodeExtension` 被调用（打桩实现）

#### Scenario: 语音信箱与 OTT 分发
- **WHEN** dialType 分别为 `DIAL_VOICE_MAIL_TYPE` / `DIAL_OTT_TYPE`
- **THEN** 语音信箱由 `VoiceMailDialProcess` 处理（内部转 `CarrierDialProcess`）；OTT 分支移除，`DIAL_OTT_TYPE` 落入 default 分支返回 `CALL_ERR_UNKNOW_DIAL_TYPE`

#### Scenario: 非法 dialType 仍被拒
- **WHEN** dialType 为 `DIAL_OTT_TYPE` / `DIAL_BLUETOOTH_TYPE`（分发分支已移除）或未知类型时进入 `HandleDialRequest`
- **THEN** 落入 default 分支返回 `CALL_ERR_UNKNOW_DIAL_TYPE`

### Requirement: 拨号前置校验
系统 SHALL 由 `CallPolicy::DialPolicy` 校验 dialType、callType、dialScene（`CALL_NORMAL` / `CALL_PRIVILEGED` / `CALL_EMERGENCY`）、videoState 合法性（非法 dialType 返回 `TELEPHONY_ERR_ARGUMENT_INVALID` 不变）；非 ECC 时执行 `IsVoiceCallValid`（已有语音来电振铃则 `CALL_ERR_CALL_COUNTS_EXCEED_LIMIT`）、`HasNewCall`、`HasEmergencyCall`；末尾经 `HasNormalCall`：无 SIM 卡返回 `TELEPHONY_ERR_NO_SIM_CARD` 并弹 "CALL_FAILED_NO_SIM_CARD"，飞行模式返回 `TELEPHONY_ERR_AIRPLANE_MODE_ON` 并弹 "CALL_FAILED_IN_AIRPLANE_MODE"，未驻留返回 `TELEPHONY_ERR_NETWORK_NOT_IN_SERVICE`——上述无 SIM/飞行模式/未驻留检查经本 change 引入的 `CoreServiceClient::GetInstance().Xxx()`（打桩）保留语义，失败对话框经 `CallDialog` 桩弹出；`CanDialMulityCall` 校验保留。EDM 禁拨（`IsDialingEnable` / `TELEPHONY_ERR_POLICY_DISABLED`）与超级隐私拦截（`SuperPrivacyMode`）MUST 移除。

#### Scenario: 非法 dialType 被拒
- **WHEN** extras 的 dialType 不属于合法 `DialType` 时调用 `DialPolicy`
- **THEN** 返回 `TELEPHONY_ERR_ARGUMENT_INVALID`

#### Scenario: 无 SIM 卡拨号被拦
- **WHEN** 非 ECC 拨号且 `CoreServiceClient::GetInstance().HasSimCard`（打桩）返回无卡
- **THEN** 返回 `TELEPHONY_ERR_NO_SIM_CARD` 并经 `CallDialog` 桩提示 "CALL_FAILED_NO_SIM_CARD"

#### Scenario: 紧急呼叫期间禁拨普通号码
- **WHEN** 表中已存在 `GetEmergencyState()` 为真的通话时拨打非 ECC 号码
- **THEN** `DialPolicy` 返回 `CALL_ERR_CALL_COUNTS_EXCEED_LIMIT`

### Requirement: 紧急呼叫放行
系统 SHALL 对 `CheckNumberIsEmergency` 判定为紧急的号码执行 `CallRequestProcess::EccDialPolicy`：挂断现有 `CALL_RUNNING_STATE_CREATE` / `CALL_RUNNING_STATE_CONNECTING` / `CALL_RUNNING_STATE_DIALING` / `CALL_RUNNING_STATE_ACTIVE` / `CALL_RUNNING_STATE_HOLD` 的通话、拒接 `CALL_RUNNING_STATE_RINGING` 的来电为紧急呼叫让路（卫星通话清理分支 MUST 移除——卫星对象不构造，分支无实际输入）；若已存在紧急拨号中通话则返回 `CALL_ERR_CALL_COUNTS_EXCEED_LIMIT`；`CallPolicy::HasNormalCall` 在 `isEcc` 为真（或 `DialScene::CALL_EMERGENCY`）时跳过 SIM/飞行模式/驻留检查直接放行，旁路逻辑原样保留（卫星/蓝牙旁路随对象移除失效）；`CallControlManager::DialCall` 对 ECC 号码将 dialScene 置 `CALL_EMERGENCY` 保留。

需人工复核（ECC）：卫星清理分支移除与旁路条件收敛对紧急呼叫放行语义的影响。

#### Scenario: ECC 拨号前清理既有通话
- **WHEN** 已有一个 ACTIVE 通话与一个 RINGING 来电时拨打 ECC 号码
- **THEN** `EccDialPolicy` 对 ACTIVE 通话调用 `HangUpCall`、对 RINGING 通话调用 `RejectCall`，随后返回 `TELEPHONY_SUCCESS` 放行拨号

#### Scenario: 已有 ECC 拨号中再拨 ECC 被拒
- **WHEN** 已存在一个 `GetEmergencyState()` 为真的 DIALING 状态通话时再拨 ECC
- **THEN** `EccDialPolicy` 返回 `CALL_ERR_CALL_COUNTS_EXCEED_LIMIT`

#### Scenario: ECC 绕过 SIM 与网络检查
- **WHEN** 无 SIM 卡（或未驻留网络）时拨打 ECC 号码
- **THEN** `HasNormalCall` 直接返回 `TELEPHONY_SUCCESS`，拨号不被 SIM/驻留检查拦截

### Requirement: 应答入口
系统 SHALL 由 `CallControlManager::AnswerCall` 取 `CALL_RUNNING_STATE_RINGING` 通话（callId 为 `INVALID_CALLID` 时用振铃通话的 callId）后 `NotifyCallStateUpdated` 上报 ANSWERED；`AnswerCallPolicy` 校验 callId 存在且状态为 `CALL_STATUS_INCOMING` / `CALL_STATUS_WAITING` 保留；`CallRequestProcess::AnswerRequest` MUST 直接调用 `call->AnswerCall(videoState)`（基线 DSDA 分支 `IsDsdsMode3` / `IsDsdsMode5` 及 `NeedAnswerVTAndEndActiveVO` / `NeedAnswerVOAndEndActiveVT` / `HoldOrDisconnectedCall` / `HandleCallWaitingNum*` 移除——`GetDsdsMode` 在 liteOS 恒返回 0，经 `CoreServiceClient::GetInstance()` 打桩获取），成功后 `NotifyIncomingCallAnswered` 保留。来电闪光联动（`StopFlashRemind`）、超级隐私应答拦截（`CurrentIsSuperPrivacyMode`）、卫星/视频分支（`AnswerHandlerForSatelliteOrVideoCall`，含 IMS 视频态重调 `InitVideoCall`）与 VoIP 冲突排队（`AnsweredCallQueue_` / `CarrierAndVoipConflictProcess`）MUST 移除。

#### Scenario: 非来电状态应答被拒
- **WHEN** 对一个 `TelCallState` 为 `CALL_STATUS_ACTIVE` 的通话调用 `AnswerCall`
- **THEN** `AnswerCallPolicy` 返回 `CALL_ERR_ILLEGAL_CALL_OPERATION`，不下发应答

#### Scenario: VoIP 活跃时载波应答排队
- **WHEN** 经桩注入使 VoIP 类型通话存在（基线 `VoIPCallState_` 非 `CALL_STATE_IDLE` 的等价条件）时应答载波来电
- **THEN** 无排队逻辑：`AnsweredCallQueue_` / `CarrierAndVoipConflictProcess` 不存在（VoIP 冲突排队移除），应答不暂存，按正常链路直接进入 `AnswerRequest` 下发应答

#### Scenario: 单卡模式直接应答
- **WHEN** `GetDsdsMode`（经 `CoreServiceClient::GetInstance()` 打桩）返回 0（非 DSDA 模式）时应答来电
- **THEN** `AnswerRequest` 直接调用 `call->AnswerCall(videoState)`，成功后 `NotifyIncomingCallAnswered` 被调用

### Requirement: 挂断与通话中控制
系统 SHALL 由 `CallControlManager::HangUpCall` 在 callId 为 `INVALID_CALLID` 时按 ACTIVE→DIALING→CONNECTING→HOLD 顺序选取通话；`HangUpPolicy` 要求通话状态非 `CALL_STATUS_IDLE` / `CALL_STATUS_DISCONNECTING` / `CALL_STATUS_DISCONNECTED`；挂断前若 `HasPendingMo` 为真（拨号尚未回报）则 `SetPendingHangup` 挂起等待 CLCC 回报；`HoldCallPolicy` 要求通话 `CALL_RUNNING_STATE_ACTIVE`（否则 `CALL_ERR_CALL_IS_NOT_ACTIVATED`）、`UnHoldCallPolicy` 要求 `CALL_RUNNING_STATE_HOLD`（否则 `CALL_ERR_CALL_IS_NOT_ON_HOLDING`）、`SwitchCallPolicy` 要求载波通话数不小于 2（`onlyTwoCall_`，否则 `CALL_ERR_PHONE_CALLS_TOO_FEW`）且被切换通话为 `CALL_STATUS_HOLDING`。`CombineConference` 相关校验与错误码场景（会议不支持）MUST 移除。

#### Scenario: 默认 callId 按状态优先级选取
- **WHEN** 以 `INVALID_CALLID` 调用 `HangUpCall` 且同时存在 ACTIVE 与 HOLD 通话
- **THEN** 选中 ACTIVE 通话的 callId 执行挂断；无任何 ACTIVE/DIALING/CONNECTING/HOLD 通话时返回 `TELEPHONY_ERR_ARGUMENT_INVALID`

#### Scenario: 拨号未回报时挂断被挂起
- **WHEN** 对一个 `HasPendingMo(callId)` 为真的通话调用 `HangUpCall`
- **THEN** `SetPendingHangup(true, callId)` 被设置，本次不立即下发 `HangUpRequest`，等待拨号回报后再处理

#### Scenario: 无保持通话时合并会议被拒
- **WHEN** 主通话为 ACTIVE 且不存在同 callType 的 `CALL_STATUS_HOLDING` 通话时调用合并会议入口（`CombineConference(mainCallId)`）
- **THEN** 接口不提供：会议通话不支持，`CombineConference` 及其 `CALL_ERR_CALL_STATE_MISMATCH_OPERATION` 校验链路不迁移、入口不编译，请求无处受理（会议对象管理见 call-object-model delta REMOVED）

### Requirement: 控制请求异步化
系统 SHALL 由 `CallRequestHandler` 将 Answer / Reject / HangUp / Hold / UnHold / SwitchCall / StartRtt / StopRtt 各请求经本 change 引入的打桩 EventHandler 异步提交（替代基线 `ffrt::submit`）转 `CallRequestProcess` 对应 *Request 方法，语义不变（`DialCall` 为同步直达）；会议类请求（CombineConference / SeparateConference / KickOutFromConference / JoinConference）随会议不支持移除；`CallRequestEventHandlerHelper` 在拨号处理中置 dialing 标志（`SetDialingCallProcessing` / `IsDialingCallProcessing`），并以打桩 EventHandler `PostTask` 延时 `DELAY_TIME`（3000 毫秒）任务 `RestoreDialingFlag(false)` 恢复，任务名 `TASK_ID`（"handler_restore_dialing_flag"），语义不变；同时以 `SetPendingMo` / `HasPendingMo` / `SetPendingHangup` / `HasPendingHangup` 记录拨号回报前的挂起状态。

#### Scenario: 应答请求异步下发
- **WHEN** 调用 `CallRequestHandler::AnswerCall(callId, videoState)`
- **THEN** 立即返回 `TELEPHONY_SUCCESS`，`AnswerRequest` 在打桩 EventHandler 任务中执行

#### Scenario: 拨号标志 3 秒自动恢复
- **WHEN** `CarrierDialProcess` 置 dialing 标志后 3000 毫秒内无新的拨号触发
- **THEN** 延时任务执行 `RestoreDialingFlag(false)`，`IsDialingCallProcessing()` 变为 false

#### Scenario: 拨号处理中再拨被拒
- **WHEN** `IsDialingCallProcessing()` 为 true 时再次进入 `CarrierDialProcess`
- **THEN** 返回 `CALL_ERR_CALL_COUNTS_EXCEED_LIMIT`

### Requirement: 拉起通话界面
系统 SHALL 由 `CallConnectAbility::ConnectAbility` 经本 change 引入的打桩发起对通话界面（Want：bundle "com.ohos.callui"、ability "com.ohos.callui.ServiceAbility"）的连接，替代基线 `AbilityManagerClient::ConnectAbility`，连接回调以桩实现承接（基线回调类 `CallAbilityConnectCallback` 的语义由桩保留：连接成功置位 `isConnected_`）；`isConnecting_` / `isDisconnecting_` 标志 MUST 防止连接与断开竞态（断开中收到连接请求被丢弃并记日志，反之亦然）；`DisconnectAbility` 先经 `WaitForConnectResult`（`cv_.wait_for` 至多 `WAIT_TIME_ONE_SECOND` = 1 秒）确认已连接才执行断开（断开调用同样走桩）；首个通话入表时由 `CallObjectManager::AddOneCallObject` 触发连接，表清空且 `ShouldDisconnectService` 为真时延时断开。

#### Scenario: 首个通话拉起通话界面
- **WHEN** `AddOneCallObject` 将首个通话对象入表（基线 VoIP 振铃冲突条件随 VoIP 对象移除恒不成立）
- **THEN** `CallConnectAbility::ConnectAbility` 以 "com.ohos.callui" 的 ServiceAbility 发起连接，连接调用走打桩实现（不再经 `AbilityManagerClient::ConnectAbility`）

#### Scenario: 未连接完成时断开被跳过
- **WHEN** `isConnected_` 为 false 时调用 `DisconnectAbility` 且 1 秒内连接未完成
- **THEN** `WaitForConnectResult` 超时返回 false，本次不执行断开

#### Scenario: 断开中收到连接请求
- **WHEN** `isDisconnecting_` 为 true 时调用 `ConnectAbility`
- **THEN** 该请求被丢弃，不发起桩侧连接调用

### Requirement: 广播订阅
系统 SHALL 在 liteOS 上暂不调用 `EventFwk::CommonEventManager` 相关接口（依赖广播接口适配）：`CallControlManager::Init` 的订阅链（`SubscriberSaStateChange` → `SystemAbilityListener::OnAddSystemAbility` 的 `CommonBroadcastSubscriber` / `ContactsBroadcastSubscriber` / `MuteKeyBroadcastSubscriber` 等订阅注册）MUST 不注册任何公共事件订阅，各订阅调用点写 `// todo!!! [broadcast] ref to call_broadcast_subscriber.cpp OnReceiveEvent`（及 `SimStateBroadcast` 等对应处理函数）占位；SIM 状态等原经广播获取的输入改经打桩查询接口（如 `CoreServiceClient::GetInstance().Xxx()`）获取；HFP（`HfpBroadcastSubscriber`）、超级隐私（`SuperPrivacyModeBroadcastSubscriber`）、HSDR（`HSDRBroadcastSubscriber`）与卫星（`SatcommBroadcastSubscriber`）订阅随特性移除；`CallBroadcastSubscriber::OnReceiveEvent` 的事件分发不再被触发，未知事件默认分支场景移除。

#### Scenario: 初始化不注册任何公共事件订阅
- **WHEN** `CallControlManager::Init` 执行
- **THEN** 无任何 `CommonEventManager` 订阅注册，订阅调用点存在 `// todo!!! [broadcast] ref to call_broadcast_subscriber.cpp OnReceiveEvent` 占位注释

#### Scenario: SIM 状态经打桩查询获取
- **WHEN** 业务逻辑需要 SIM 状态等原广播输入
- **THEN** 经 `CoreServiceClient::GetInstance().Xxx()` 打桩查询接口获取，不依赖公共事件广播

#### Scenario: 公共事件服务上线触发注册
- **WHEN** 公共事件服务上线事件到达（基线 `OnAddSystemAbility` 收到 `COMMON_EVENT_SERVICE_ID` 的等价触发；广播链路 todo 占位未接通）
- **THEN** 无任何订阅注册：各 `CallBroadcastSubscriber` 注册调用点以 `// todo!!! [broadcast]` 占位，`subscriberPtrList_` 不产生任何条目

#### Scenario: HFP 广播订阅受宏控制
- **WHEN** HFP 广播订阅时机到来（基线 `HFP_ASYNC_ENABLE` 宏随 BLUETOOTH 特性退役）
- **THEN** 任何宏配置下 "usual.event.bluetooth.CONNECT_HFP_HF" 均不被订阅，`HfpBroadcastSubscriber` 不存在

#### Scenario: 未知事件走默认分支
- **WHEN** 广播链路（todo 占位未接通）无任何事件到达 `CallBroadcastSubscriber::OnReceiveEvent`
- **THEN** 无分发处理：`OnReceiveEvent` 不被触发，不存在 `UnknownBroadcast` 默认分支调用

### Requirement: 陌生来电过滤与超级隐私
系统 SHALL 由 `CallIncomingFilterManager::DoIncomingFilter` 保留过滤调用链：EDM 校验（`CallControlManager::IsIncomingEnable`）随 EDM 企业策略不支持 MUST 移除；紧急号码判定（基线 `CellularCallConnection::IsEmergencyPhoneNumber`）经本 change 引入的 `CellularCallClient::GetInstance().Xxx()`（打桩）保留，命中时直接放行返回 `TELEPHONY_SUCCESS`；骚扰识别（`SpamCallAdapter` 相关调用，基线 `DetectSpamCall` / `WaitForDetectResult` / `GetParseResult`）经 spam-call 的 todo 占位（`// todo!!! [spam] ref to spam_call_adapter.cpp DetectSpamCall`）放行——不发起识别连接、不拦截来电；过滤完成后 MUST 保留过滤完成回调链（`CallFilterCompleteResult`：创建通话对象并继续来电上报流程）。`CallSuperPrivacyControlManager`（超级隐私整体，含 `WatchParameter` 监听 "persist.super_privacy.mode" 与 `CloseAllCall`）MUST 不迁移，`CallPolicy::SuperPrivacyMode` 拨号拦截与 `CurrentIsSuperPrivacyMode` 应答拦截随之移除。

#### Scenario: 紧急号码直接放行
- **WHEN** 来电号码被 `IsEmergencyPhoneNumber`（经 `CellularCallClient::GetInstance()` 打桩）判定为紧急时执行 `DoIncomingFilter`
- **THEN** 返回 `TELEPHONY_SUCCESS` 放行，进入过滤完成回调

#### Scenario: 非紧急号码经骚扰识别占位链放行并保留过滤完成回调
- **WHEN** 非紧急来电执行 `DoIncomingFilter`
- **THEN** 骚扰识别调用点以 `// todo!!! [spam]` 占位、不发起识别、不拦截，`DoIncomingFilter` 返回 `TELEPHONY_SUCCESS`，`CallFilterCompleteResult` 过滤完成回调被调用（通话对象创建与来电上报流程继续）

#### Scenario: EDM 禁入名单拦截来电
- **WHEN** 来电过滤链路执行 `DoIncomingFilter`（EDM 企业禁拨不迁移）
- **THEN** 无 `IsIncomingEnable` 校验链路：非紧急来电不被 `TELEPHONY_ERR_POLICY_DISABLED` 拦截、按正常链路继续处理；号码为紧急号码时仍返回 `TELEPHONY_SUCCESS` 直接放行

#### Scenario: 超级隐私开启清理通话
- **WHEN** "persist.super_privacy.mode" 参数值变化（超级隐私不迁移，无 `WatchParameter` 监听）
- **THEN** 无 `CloseAllCall` 清理链路：既有通话不被 `RejectCall` / `HangUpCall` 清理，也不上报 `EVENT_IS_SUPER_PRIVACY_MODE_ON` / `EVENT_IS_SUPER_PRIVACY_MODE_OFF`，通话按正常链路处理

#### Scenario: 超级隐私中拨号被拦
- **WHEN** 超级隐私模式开启的等价条件成立时拨打非 ECC 号码（`CallPolicy::SuperPrivacyMode` 校验移除）
- **THEN** 无超级隐私拦截：不弹超级隐私对话框、不返回 `CALL_ERR_DIAL_FAILED`，拨号按正常 `DialPolicy` / `HasNormalCall` 链路校验

## REMOVED Requirements

### Requirement: 有线耳机与媒体按键
**Reason**: 有线耳机不支持，call_wired_headset.cpp、MMI::InputManager 按键订阅与 ABILITY_MEDIA_SUPPORT 媒体按键（onButtonDealing）不迁移。
**Migration**: 无替代；按键接听由整机按键方案另行适配。