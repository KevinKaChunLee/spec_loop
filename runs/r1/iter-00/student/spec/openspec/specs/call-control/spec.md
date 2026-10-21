# Call Control Specification

## Purpose
描述 OpenHarmony v6.0-Release telephony_call_manager 呼叫控制层基线现状：`CallControlManager`（继承 `CallPolicy`，后者继承 `CallObjectManager`）作为 Dial / Answer / Reject / Hangup / Hold / UnHold / SwitchCall / 合并会议等操作的入口，`CallRequestHandler` 将请求 ffrt 异步化后交 `CallRequestProcess` 执行，`CallPolicy` 负责前置校验（参数合法性、紧急号码、SIM/网络状态、EDM、超级隐私），`CallConnectAbility` 负责拉起通话界面（`com.ohos.callui`），`CallBroadcastSubscriber` / `CallWiredHeadSet` / `CallIncomingFilterManager` / `CallSuperPrivacyControlManager` / `CallRequestEventHandlerHelper` 提供广播订阅、耳机按键、陌生来电过滤、超级隐私与拨号标志保护等辅助行为。源码落点：`telephony_call_manager/services/call/{include,src}` 的 `call_control_manager.cpp`、`call_request_handler.cpp`、`call_request_process.cpp`、`call_request_event_handler_helper.cpp`、`call_policy.cpp`、`call_connect_ability.cpp`、`call_ability_connect_callback.cpp`、`call_broadcast_subscriber.cpp`、`call_wired_headset.cpp`、`call_incoming_filter_manager.cpp`、`call_superprivacy_control_manager.cpp`。相关编译开关（`callmanager.gni` / `BUILD.gn`）：`HFP_ASYNC_ENABLE`（`BUILD.gn` 的 `call_manager_feature_hfp_async_enable`，默认 false，控制 `HfpBroadcastSubscriber` 的 HFP 广播订阅，出现在 `call_control_manager.cpp`）、`ABILITY_MEDIA_SUPPORT`（`callmanager.gni`，控制 `onButtonDealing` 媒体按键处理，出现在 `call_control_manager.cpp`）、`ABILITY_POWER_SUPPORT`（来电/断连 RunningLock）、`NOT_SUPPORT_MULTICALL`（应答前先挂断既有通话）、`ABILITY_BLUETOOTH_SUPPORT`、`TELEPHONY_CUST_SUPPORT` 等。本规格只描述基线现状，不含移植/裁剪决策。

## Requirements

### Requirement: 拨号入口分发
系统 SHALL 由 `CallControlManager::DialCall` 依次完成：`NumberLegalityCheck` 号码合法性、`CallNumberUtils::RemoveSeparatorsPhoneNumber` 去分隔符、`CallNumberUtils::CheckNumberIsEmergency` 紧急判定（命中则 extras 的 dialScene 置 `DialScene::CALL_EMERGENCY`）、`SatelliteCallControl::IsSatelliteSwitchEnable` 卫星开关检查（开启时校验 `IsAllowedSatelliteDialCall` 并置 `TYPE_SATELLITE`）、`CanDial`（`DialPolicy` + `CanDialMulityCall`）前置校验、`PackageDialInformation` 暂存拨号信息，最后转 `CallRequestHandler::DialCall` → `CallRequestProcess::DialRequest`（FDN 校验：`IsFdnEnabled` / `GetFdnNumberList` / `IsFdnNumber`；MMI 码判定：`CellularCallConnection::IsMmiCode`），再经 `HandleDialRequest` 按 dialType 分发至 `CarrierDialProcess` / `VoiceMailDialProcess` / `OttDialProcess` / `BluetoothDialProcess`，未知 dialType 返回 `CALL_ERR_UNKNOW_DIAL_TYPE`。
#### Scenario: FDN 禁拨名单拦截
- **WHEN** 非 ECC 的 `DIAL_CARRIER_TYPE` 拨号且 `IsFdnEnabled` 为真、号码不在 `GetFdnNumberList` 返回列表中
- **THEN** `DialRequest` 返回 `CALL_ERR_DIAL_FAILED`，`NotifyCallEventUpdated` 上报 `EVENT_INVALID_FDN_NUMBER`，并经 `CallDialog::DialogConnectExtension` 弹 "CALL_FAILED_DUE_TO_FDN"
#### Scenario: MMI 码走对话框不走通话
- **WHEN** 拨打的号码被 `CellularCallConnection::IsMmiCode` 判定为 MMI 码
- **THEN** 不创建通话对象、不上报 `CALL_STATUS_DIALING`，`CallDialog::DialogProcessMMICodeExtension` 被调用
#### Scenario: 语音信箱与 OTT 分发
- **WHEN** dialType 分别为 `DIAL_VOICE_MAIL_TYPE` / `DIAL_OTT_TYPE`
- **THEN** 分别由 `VoiceMailDialProcess`（内部转 `CarrierDialProcess`）与 `OttDialProcess`（经 `CallAbilityReportProxy::OttCallRequest`）处理

### Requirement: 拨号前置校验
系统 SHALL 由 `CallPolicy::DialPolicy` 校验 dialType（仅 `DIAL_CARRIER_TYPE` / `DIAL_VOICE_MAIL_TYPE` / `DIAL_OTT_TYPE` / `DIAL_BLUETOOTH_TYPE`）、callType、dialScene（`CALL_NORMAL` / `CALL_PRIVILEGED` / `CALL_EMERGENCY`）、videoState 合法性；非 ECC 时执行 `IsVoiceCallValid`（已有语音来电振铃则 `CALL_ERR_CALL_COUNTS_EXCEED_LIMIT`）、`HasNewCall`、`HasEmergencyCall`；末尾经 `SuperPrivacyMode` → `HasNormalCall`：无 SIM 卡返回 `TELEPHONY_ERR_NO_SIM_CARD` 并弹 "CALL_FAILED_NO_SIM_CARD"，飞行模式返回 `TELEPHONY_ERR_AIRPLANE_MODE_ON` 并弹 "CALL_FAILED_IN_AIRPLANE_MODE"，未驻留返回 `TELEPHONY_ERR_NETWORK_NOT_IN_SERVICE`；EDM 禁拨（`IsDialingEnable`）返回 `TELEPHONY_ERR_POLICY_DISABLED`；`CanDialMulityCall` 在视频通话等待未开启时对已有通话情况下再拨视频返回 `CALL_ERR_DIAL_IS_BUSY`。
#### Scenario: 非法 dialType 被拒
- **WHEN** extras 的 dialType 不属于四种合法 `DialType` 时调用 `DialPolicy`
- **THEN** 返回 `TELEPHONY_ERR_ARGUMENT_INVALID`
#### Scenario: 无 SIM 卡拨号被拦
- **WHEN** 非 ECC / 非卫星 / 非蓝牙拨号且 `CoreServiceClient::HasSimCard` 返回无卡
- **THEN** 返回 `TELEPHONY_ERR_NO_SIM_CARD` 并经 `CallDialog::DialogConnectExtension` 提示 "CALL_FAILED_NO_SIM_CARD"
#### Scenario: 紧急呼叫期间禁拨普通号码
- **WHEN** 表中已存在 `GetEmergencyState()` 为真的通话时拨打非 ECC 号码
- **THEN** `DialPolicy` 返回 `CALL_ERR_CALL_COUNTS_EXCEED_LIMIT`

### Requirement: 紧急呼叫放行
系统 SHALL 对 `CheckNumberIsEmergency` 判定为紧急的号码执行 `CallRequestProcess::EccDialPolicy`：挂断现有 `CALL_RUNNING_STATE_CREATE` / `CALL_RUNNING_STATE_CONNECTING` / `CALL_RUNNING_STATE_DIALING` / `CALL_RUNNING_STATE_ACTIVE` / `CALL_RUNNING_STATE_HOLD` 的通话及卫星通话、拒接 `CALL_RUNNING_STATE_RINGING` 的来电为紧急呼叫让路；若已存在紧急拨号中通话则返回 `CALL_ERR_CALL_COUNTS_EXCEED_LIMIT`；`CallPolicy::HasNormalCall` 在 `isEcc` 为真（或卫星/蓝牙类型、`DialScene::CALL_EMERGENCY`）时跳过 SIM/飞行模式/驻留检查直接放行；`CallControlManager::DialCall` 对 ECC 号码将 dialScene 置 `CALL_EMERGENCY`。
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
系统 SHALL 由 `CallControlManager::AnswerCall` 先 `StopFlashRemind`，取 `CALL_RUNNING_STATE_RINGING` 通话（callId 为 `INVALID_CALLID` 时用振铃通话的 callId），经 `CurrentIsSuperPrivacyMode`（超级隐私下静音并弹对话框）与 `AnswerHandlerForSatelliteOrVideoCall`（IMS 视频态变化重调 `InitVideoCall`、卫星应答先挂断前台卫星通话）后，`NotifyCallStateUpdated` 上报 ANSWERED 并 `CarrierAndVoipConflictProcess`；VoIP 活跃（`VoIPCallState_` 非 `CALL_STATE_IDLE`）且应答为非 VoIP 通话时 MUST 将请求暂存 `AnsweredCallQueue_` 等待 VoIP 断开；`AnswerCallPolicy` 校验 callId 存在且状态为 `CALL_STATUS_INCOMING` / `CALL_STATUS_WAITING`；`CallRequestProcess::AnswerRequest` 对 VoIP 直接应答并 `NotifyIncomingCallAnswered`，其余按 `IsDsdsMode3` / `IsDsdsMode5`（DSDA 场景 `NeedAnswerVTAndEndActiveVO` / `NeedAnswerVOAndEndActiveVT` / `HoldOrDisconnectedCall` / `HandleCallWaitingNum*`）或直接 `call->AnswerCall` 处理。
#### Scenario: 非来电状态应答被拒
- **WHEN** 对一个 `TelCallState` 为 `CALL_STATUS_ACTIVE` 的通话调用 `AnswerCall`
- **THEN** `AnswerCallPolicy` 返回 `CALL_ERR_ILLEGAL_CALL_OPERATION`，不下发应答
#### Scenario: VoIP 活跃时载波应答排队
- **WHEN** `VoIPCallState_` 为 `CALL_STATE_RINGING`（非 IDLE）时应答一个 IMS 来电
- **THEN** 请求暂存 `AnsweredCallQueue_`（hasCall/callId/videoState），`HandlerAnswerCall` 未被立即调用
#### Scenario: 单卡模式直接应答
- **WHEN** `GetDsdsMode` 返回非 DSDA 模式（非 `IsDsdsMode3` / `IsDsdsMode5`）时应答来电
- **THEN** `AnswerRequest` 直接调用 `call->AnswerCall(videoState)`，成功后 `NotifyIncomingCallAnswered` 被调用

### Requirement: 挂断与通话中控制
系统 SHALL 由 `CallControlManager::HangUpCall` 在 callId 为 `INVALID_CALLID` 时按 ACTIVE→DIALING→CONNECTING→HOLD 顺序选取通话；`HangUpPolicy` 要求通话状态非 `CALL_STATUS_IDLE` / `CALL_STATUS_DISCONNECTING` / `CALL_STATUS_DISCONNECTED`；挂断前若 `HasPendingMo` 为真（拨号尚未回报）则 `SetPendingHangup` 挂起等待 CLCC 回报；`HoldCallPolicy` 要求通话 `CALL_RUNNING_STATE_ACTIVE`（否则 `CALL_ERR_CALL_IS_NOT_ACTIVATED`）、`UnHoldCallPolicy` 要求 `CALL_RUNNING_STATE_HOLD`（否则 `CALL_ERR_CALL_IS_NOT_ON_HOLDING`）、`SwitchCallPolicy` 要求载波通话数不小于 2（`onlyTwoCall_`，否则 `CALL_ERR_PHONE_CALLS_TOO_FEW`）且被切换通话为 `CALL_STATUS_HOLDING`；`CombineConference` 要求主通话 `CALL_STATUS_ACTIVE`、存在同类型 `CALL_STATUS_HOLDING` 通话（否则 `CALL_ERR_CALL_STATE_MISMATCH_OPERATION`）且 `CanCombineConference` 通过。
#### Scenario: 默认 callId 按状态优先级选取
- **WHEN** 以 `INVALID_CALLID` 调用 `HangUpCall` 且同时存在 ACTIVE 与 HOLD 通话
- **THEN** 选中 ACTIVE 通话的 callId 执行挂断；无任何 ACTIVE/DIALING/CONNECTING/HOLD 通话时返回 `TELEPHONY_ERR_ARGUMENT_INVALID`
#### Scenario: 拨号未回报时挂断被挂起
- **WHEN** 对一个 `HasPendingMo(callId)` 为真的通话调用 `HangUpCall`
- **THEN** `SetPendingHangup(true, callId)` 被设置，本次不立即下发 `HangUpRequest`，等待拨号回报后再处理
#### Scenario: 无保持通话时合并会议被拒
- **WHEN** 主通话为 ACTIVE 但不存在同 callType 的 `CALL_STATUS_HOLDING` 通话时调用 `CombineConference(mainCallId)`
- **THEN** 返回 `CALL_ERR_CALL_STATE_MISMATCH_OPERATION`

### Requirement: 控制请求异步化
系统 SHALL 由 `CallRequestHandler` 将 Answer / Reject / HangUp / Hold / UnHold / SwitchCall / CombineConference / SeparateConference / KickOutFromConference / StartRtt / StopRtt / JoinConference 各请求经 `ffrt::submit` 异步转 `CallRequestProcess` 对应 *Request 方法（`DialCall` 为同步直达）；`CallRequestEventHandlerHelper` 在拨号处理中置 dialing 标志（`SetDialingCallProcessing` / `IsDialingCallProcessing`），并以 `PostTask` 延时 `DELAY_TIME`（3000 毫秒）任务 `RestoreDialingFlag(false)` 恢复，任务名 `TASK_ID`（"handler_restore_dialing_flag"）；同时以 `SetPendingMo` / `HasPendingMo` / `SetPendingHangup` / `HasPendingHangup` 记录拨号回报前的挂起状态。
#### Scenario: 应答请求异步下发
- **WHEN** 调用 `CallRequestHandler::AnswerCall(callId, videoState)`
- **THEN** 立即返回 `TELEPHONY_SUCCESS`，`AnswerRequest` 在 ffrt 任务中执行
#### Scenario: 拨号标志 3 秒自动恢复
- **WHEN** `CarrierDialProcess` 置 dialing 标志后 3000 毫秒内无新的拨号触发
- **THEN** 延时任务执行 `RestoreDialingFlag(false)`，`IsDialingCallProcessing()` 变为 false
#### Scenario: 拨号处理中再拨被拒
- **WHEN** `IsDialingCallProcessing()` 为 true 时再次进入 `CarrierDialProcess`
- **THEN** 返回 `CALL_ERR_CALL_COUNTS_EXCEED_LIMIT`

### Requirement: 拉起通话界面
系统 SHALL 由 `CallConnectAbility::ConnectAbility` 经 `AbilityManagerClient::ConnectAbility` 以 Want（bundle "com.ohos.callui"、ability "com.ohos.callui.ServiceAbility"）连接通话界面，回调为 `CallAbilityConnectCallback`；`isConnecting_` / `isDisconnecting_` 标志 MUST 防止连接与断开竞态（断开中收到连接请求被丢弃并记日志，反之亦然）；`DisconnectAbility` 先经 `WaitForConnectResult`（`cv_.wait_for` 至多 `WAIT_TIME_ONE_SECOND` = 1 秒）确认已连接才执行断开；首个通话入表时由 `CallObjectManager::AddOneCallObject` 触发连接，表清空且 `ShouldDisconnectService` 为真时延时断开。
#### Scenario: 首个通话拉起通话界面
- **WHEN** `AddOneCallObject` 将首个通话对象入表（无 VoIP 振铃冲突）
- **THEN** `CallConnectAbility::ConnectAbility` 以 "com.ohos.callui" 的 ServiceAbility 发起连接
#### Scenario: 未连接完成时断开被跳过
- **WHEN** `isConnected_` 为 false 时调用 `DisconnectAbility` 且 1 秒内连接未完成
- **THEN** `WaitForConnectResult` 超时返回 false，本次不调用 `DisconnectAbility`
#### Scenario: 断开中收到连接请求
- **WHEN** `isDisconnecting_` 为 true 时调用 `ConnectAbility`
- **THEN** 该请求被丢弃，不发起 `AbilityManagerClient::ConnectAbility`

### Requirement: 广播订阅
系统 SHALL 由 `CallControlManager::Init` 经 `SubscriberSaStateChange` 订阅 `COMMON_EVENT_SERVICE_ID` 系统能力状态；`SystemAbilityListener::OnAddSystemAbility` 在 `COMMON_EVENT_SERVICE_ID` 上线时依次注册 `CommonBroadcastSubscriber`（`COMMON_EVENT_SIM_STATE_CHANGED` / `COMMON_EVENT_SCREEN_UNLOCKED` / `COMMON_EVENT_BLUETOOTH_REMOTEDEVICE_NAME_UPDATE` / `COMMON_EVENT_USER_SWITCHED` / `COMMON_EVENT_SHUTDOWN`）、`ContactsBroadcastSubscriber`、`SatcommBroadcastSubscriber`、`SuperPrivacyModeBroadcastSubscriber`（"usual.event.SUPER_PRIVACY_MODE"）、`HSDRBroadcastSubscriber`（"usual.event.HSDR_EVENT"）、`HfpBroadcastSubscriber`（"usual.event.bluetooth.CONNECT_HFP_HF"，仅 `HFP_ASYNC_ENABLE` 宏开启时）、`MuteKeyBroadcastSubscriber`（"multimodal.event.MUTE_KEY_PRESS"）；`OnRemoveSystemAbility` 对全部订阅 `UnSubscribeCommonEvent` 并清空；`CallBroadcastSubscriber::OnReceiveEvent` 按事件类型分发到 `SimStateBroadcast` / `HighTempLevelChangedBroadcast` / `ConnectCallUiSuperPrivacyModeBroadcast` / `UpdateBluetoothDeviceName` / `ConnectCallUiUserSwitchedBroadcast` / `ShutdownBroadcast` / `HsdrEventBroadcast` / `HfpConnectBroadcast` / `ScreenUnlockedBroadcast` / `MuteKeyBroadcast` 等处理函数。
#### Scenario: 公共事件服务上线触发注册
- **WHEN** `OnAddSystemAbility` 收到 `COMMON_EVENT_SERVICE_ID`
- **THEN** 七类 `CallBroadcastSubscriber` 订阅被注册并加入 `subscriberPtrList_`
#### Scenario: HFP 广播订阅受宏控制
- **WHEN** 未定义 `HFP_ASYNC_ENABLE` 时 `HfpBroadcastSubscriber` 执行
- **THEN** "usual.event.bluetooth.CONNECT_HFP_HF" 不被订阅；定义该宏时被订阅
#### Scenario: 未知事件走默认分支
- **WHEN** `OnReceiveEvent` 收到不匹配任何已登记事件的广播
- **THEN** 分发到 `UnknownBroadcast`，不做业务处理

### Requirement: 有线耳机与媒体按键
系统 SHALL 由 `CallWiredHeadSet::Init`（首个通话入表时调用）经 `MMI::InputManager::SubscribeKeyEvent` 注册 `MMI::KeyEvent::KEYCODE_HEADSETHOOK` 按下/抬起订阅（表清空时 `DeInit` 注销）：短按（按压时长小于 `FINAL_KEY_DOWN_DURATION_TWO` = 2000 毫秒，且 `AudioDeviceManager::IsWiredHeadsetConnected`）在振铃时 `AnswerCall`、有 HOLD+ACTIVE 通话时 `UnHoldCall` 保持通话、否则经 `AudioProxy::IsMicrophoneMute` 翻转 `SetMuted`；长按（≥2000 毫秒）触发 `DealKeyMuteLongPressed`；定义 `ABILITY_MEDIA_SUPPORT` 时 `CallControlManager::onButtonDealing` 处理 `HeadsetButtonService` 按键：SHORT_PRESS（振铃挂断/非振铃应答）、LONG_PRESS（振铃 `RejectCall`/非振铃静音）。
#### Scenario: 短按应答来电
- **WHEN** 有线耳机已连接且存在 RINGING 通话时耳机键短按
- **THEN** `DealKeyMuteShortPressed` 对振铃通话调用 `AnswerCall`（按其 `GetVideoStateType` 或 `GetOriginalCallType` 取视频态）
#### Scenario: 短按激活保持通话
- **WHEN** 无振铃通话、同时存在 HOLD 与 ACTIVE 通话时耳机键短按
- **THEN** 对 HOLD 通话调用 `UnHoldCall`
#### Scenario: 媒体按键长按拒接
- **WHEN** 定义 `ABILITY_MEDIA_SUPPORT`、存在 RINGING 通话时收到 `HeadsetButtonService::LONG_PRESS_EVENT`
- **THEN** `onButtonDealing` 对该通话调用 `RejectCall`；非振铃时长按则 `SetMute(true)`

### Requirement: 陌生来电过滤与超级隐私
系统 SHALL 由 `CallIncomingFilterManager::DoIncomingFilter` 对上报的来电先做 EDM 校验（`CallControlManager::IsIncomingEnable`，失败返回 `TELEPHONY_ERR_POLICY_DISABLED`），紧急号码（`CellularCallConnection::IsEmergencyPhoneNumber`）直接放行；`CallSuperPrivacyControlManager` 经 `WatchParameter` 监听 "persist.super_privacy.mode"（`ParamChangeCallback`），值变为 "2"（开启）时 `CloseAllCall` 对非 ECC/非 ECC 联系人通话：INCOMING/WAITING 状态 `RejectCall`、其余 `HangUpCall`，并经 `SuperPrivacyModeChangeEvent` 上报 `EVENT_IS_SUPER_PRIVACY_MODE_ON` / `EVENT_IS_SUPER_PRIVACY_MODE_OFF`；超级隐私模式中拨号被 `CallPolicy::SuperPrivacyMode` 拦截（`DialogConnectPrivpacyModeExtension` 并返回 `CALL_ERR_DIAL_FAILED`）、应答被 `CurrentIsSuperPrivacyMode` 拦截（`MuteRinger` + `DialogConnectAnswerPrivpacyModeExtension`）。
#### Scenario: EDM 禁入名单拦截来电
- **WHEN** 来电号码未通过 `IsIncomingEnable` 校验时执行 `DoIncomingFilter`
- **THEN** 返回 `TELEPHONY_ERR_POLICY_DISABLED`；号码为紧急号码时返回 `TELEPHONY_SUCCESS` 放行
#### Scenario: 超级隐私开启清理通话
- **WHEN** "persist.super_privacy.mode" 参数值变为 "2"
- **THEN** 非紧急的 INCOMING/WAITING 通话被 `RejectCall`，其余非紧急通话被 `HangUpCall`
#### Scenario: 超级隐私中拨号被拦
- **WHEN** `GetCurrentIsSuperPrivacyMode()` 为 true 时拨打非 ECC 号码
- **THEN** `SuperPrivacyMode` 经 `CallDialog::DialogConnectPrivpacyModeExtension` 弹出超级隐私对话框并返回 `CALL_ERR_DIAL_FAILED`
