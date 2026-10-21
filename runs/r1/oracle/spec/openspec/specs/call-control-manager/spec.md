# 下行控制（call-control-manager）Specification

## Purpose
描述 `telephony_call_manager/services/call/src` 中的下行控制链路（应用→协议栈）：`CallControlManager`（拨号/接听/拒接/挂断/保持/切换/会议/DTMF/RTT/音频设置与补充业务入口，`DECLARE_DELAYED_SINGLETON`，继承 `CallPolicy`）、`CallRequestHandler`/`CallRequestProcess`/`CallRequestEventHandlerHelper`（请求转发与拨号互斥）、`CallPolicy`（拨号前置仲裁）、`CallConnectAbility`/`CallAbilityConnectCallback`（通话界面拉起）、`CallBroadcastSubscriber`（公共事件订阅）、`CallStateListener`/`CallStateListenerBase`（状态观察者注册表）、`CallWiredHeadSet`（有线耳机按键）、`CallSuperPrivacyControlManager`（超级隐私）。编译开关：`HFP_ASYNC_ENABLE`（HFP 广播订阅，`declare_args` 默认 false）、`NOT_SUPPORT_MULTICALL`（`HangUpFirstCall` 系列与单通话上限，默认 false）、`ABILITY_POWER_SUPPORT`（断开保持 `RunningLock`）、`ABILITY_MEDIA_SUPPORT`（耳机按键分发）、`ABILITY_CONFIG_SUPPORT`（`CallPolicy::IsSupportVideoCall` 查询 carrier config，默认手机构建下前三者在位）。

## Requirements

### Requirement: 初始化与观察者注册
系统 SHALL 由 `CallControlManager::Init()` 创建 `CallStateListener`、`CallRequestHandler`（并 `Init()`）、`IncomingCallWakeup`、`MissedCallNotification`、`CallSettingManager`，执行 `SubscriberSaStateChange()`（经 samgr `SubscribeSystemAbility(COMMON_EVENT_SERVICE_ID, statusChangeListener_)`）、`AudioControlManager::Init()`、`CallStateObserve()`（向 `CallStateListener` 注册 `CallAbilityReportProxy`、`CallStateReportProxy`、`AudioControlManager`、`RejectCallSms`、`MissedCallNotification`、`IncomingCallWakeup`、`CallRecordsManager`、`DistributedCommunicationManager`、`InteroperableCommunicationManager`、`CallVoiceAssistantManager`）与 `CallSuperPrivacyControlManager::RegisterSuperPrivacyMode()`。
#### Scenario: 公共事件 SA 就绪后订阅广播
- **WHEN** `SystemAbilityListener::OnAddSystemAbility` 收到公共事件服务上线
- **THEN** 依次订阅 `CommonBroadcastSubscriber`、`ContactsBroadcastSubscriber`、`SatcommBroadcastSubscriber`、`SuperPrivacyModeBroadcastSubscriber`、`HSDRBroadcastSubscriber`、`HfpBroadcastSubscriber`（`HFP_ASYNC_ENABLE` 内）、`MuteKeyBroadcastSubscriber` 七组广播并存入 `subscriberPtrList_`

### Requirement: 拨号前置校验
系统 SHALL 由 `CallControlManager::DialCall(number, extras)` 依次执行 `NumberLegalityCheck`（空号返回 `CALL_ERR_PHONE_NUMBER_EMPTY`，超长返回 `CALL_ERR_NUMBER_OUT_OF_RANGE`）、`CallNumberUtils::RemoveSeparatorsPhoneNumber` + `CheckNumberIsEmergency`（ECC 时置 `dialScene = CALL_EMERGENCY`）、卫星开关判定（`SatelliteCallControl::IsSatelliteSwitchEnable`/`IsAllowedSatelliteDialCall` 可改写 `TYPE_SATELLITE`）、`CanDial`（= `CallPolicy::DialPolicy` + `CallPolicy::CanDialMulityCall`）与 `PackageDialInformation`（暂存 `dialSrcInfo_`/`extras_`）后交 `CallRequestHandlerPtr_->DialCall()`。
#### Scenario: 紧急呼叫豁免多通话限制
- **WHEN** ECC 号码拨号
- **THEN** `DialPolicy` 跳过 `HasNewCall`/`HasEmergencyCall` 等限制项，仅 `HasNormalCall`（无卡弹 `CALL_FAILED_NO_SIM_CARD`、飞行模式弹 `CALL_FAILED_IN_AIRPLANE_MODE`、无服务弹 `CALL_FAILED_NO_SERVICE`、电信卡未注册 IMS 弹 `CALL_FAILED_CTCARD_NO_IMS`）仍逐项校验

#### Scenario: 超级隐私拦截拨号
- **WHEN** `CallSuperPrivacyControlManager::GetCurrentIsSuperPrivacyMode()` 为真且非 ECC 拨号
- **THEN** `CallPolicy::SuperPrivacyMode` 经 `CallDialog::DialogConnectPrivpacyModeExtension("SUPER_PRIVACY_MODE", ...)` 弹窗拦截并返回 `CALL_ERR_DIAL_FAILED`

### Requirement: 下行请求异步化
系统 SHALL 使 `CallRequestHandler` 除 `DialCall()` 同步直调 `CallRequestProcess::DialRequest()` 外，`AnswerCall/RejectCall/HangUpCall/HoldCall/UnHoldCall/SwitchCall/CombineConference/SeparateConference/KickOutFromConference/StartRtt/StopRtt/JoinConference` 全部经 `ffrt::submit` 投递后立即返回 `TELEPHONY_SUCCESS`，错误仅经 `CallManagerHisysevent` 记录。
#### Scenario: 同步拨号带回执
- **WHEN** 应用调用 `DialCall`
- **THEN** 拨号请求同步走 `DialRequest()` 并返回实际错误码（如 FDN 校验失败发 `EVENT_INVALID_FDN_NUMBER` 并弹 `CALL_FAILED_DUE_TO_FDN`）

#### Scenario: 接听请求异步
- **WHEN** 应用调用 `AnswerCall(callId, videoState)` 且 `AnswerCallPolicy` 校验通过（状态须 INCOMING/WAITING）
- **THEN** 请求异步下发 `AnswerRequest`，方法立即返回 `TELEPHONY_SUCCESS`

### Requirement: 无效 callId 的自动定位
系统 SHALL 在 `AnswerCall`/`RejectCall` 传 `INVALID_CALLID` 时自动取振铃通话，`HangUpCall` 传 `INVALID_CALLID` 时按 ACTIVE→DIALING→CONNECTING→HOLD 顺序取首个通话。
#### Scenario: 挂断未指定 callId
- **WHEN** 应用以 `INVALID_CALLID` 调用 `HangUpCall`
- **THEN** 按活动→拨号→连接中→保持的顺序选择目标通话执行挂断

### Requirement: VoIP 冲突处理
系统 SHALL 在接听载体通话前经 `CarrierAndVoipConflictProcess` 拒接/挂断冲突 VoIP；`VoIPCallState_` 非 IDLE 且非 VoIP 通话时接听请求入 `AnsweredCallQueue_` 延迟执行。
#### Scenario: 接听载体通话撞上 VoIP 振铃
- **WHEN** 载体通话接听时存在 INCOMING 的 VoIP 通话
- **THEN** 冲突 VoIP 被 `RejectCall` 拒接后载体接听继续

### Requirement: MO 未上报 CLCC 的挂断挂起
系统 SHALL 由 `CallRequestEventHandlerHelper`（内置 `AppExecFwk::EventHandler`，`DELAY_TIME = 3000` 毫秒延时恢复拨号互斥位）维护 `SetPendingMo`/`HasPendingMo`、`SetPendingHangup`/`HasPendingHangup` 状态位；`HangUpCall` 遇 `HasPendingMo(callId)` 时不立即下发，改 `SetPendingHangup(true, callId)` 记录待补挂断。
#### Scenario: CLCC 到达后补挂断
- **WHEN** MO 拨号已下发但协议栈 CLCC 尚未上报时应用挂断
- **THEN** 挂断请求转为挂起，待上行状态机处理该 callId 的 CLCC 时补执行挂断

### Requirement: 通话界面按需连接与延时断开
系统 SHALL 由 `CallConnectAbility`（`DECLARE_DELAYED_SINGLETON`）经 `AAFwk::AbilityManagerClient::GetInstance()->ConnectAbility(want, connectCallback_, userId = -1)` 连接 `com.ohos.callui` / `com.ohos.callui.ServiceAbility`；`CallControlManager::ConnectCallUiService(false)` 以 `ffrt::submit_h` + `ffrt::task_attr().delay`（`DISCONNECT_DELAY_TIME = 1000000` 微秒）提交延时断开任务，静态 `alarmSeted` 去重，连接分支以 `ffrt::skip` 取消未决断开任务。
#### Scenario: 界面异常断开自动重连
- **WHEN** `CallAbilityConnectCallback::OnAbilityDisconnectDone` 收到 `UNEXPECT_DISCONNECT_CODE(-1)`
- **THEN** `ReConnectAbility()` 遍历 `GetAllCallInfoList`，只要存在非空闲通话即重新 `ConnectAbility`

### Requirement: 超级隐私参数驱动
系统 SHALL 由 `CallSuperPrivacyControlManager` 以系统参数 `SUPER_PRIVACY_MODE_PARAM_KEYS = "persist.super_privacy.mode"`（`WatchParameter` 注册 `ParamChangeCallback`）与超级隐私广播双路驱动：值为 "2"（`ALWAYS_ON`）或 `ON_WHEN_FOLDED` 且折叠态时生效；`CloseAllCall` 清除全部非 ECC 通话（INCOMING/WAITING 走 `RejectCall(callId, false, u"superPrivacyModeOn")`，其余走 `HangUpCall`）；`CloseSuperPrivacyMode` 经 `SuperPrivacyManagerClient::GetInstance().SetSuperPrivacyMode(OFF, SOURCE_CALL)` 关闭后恢复拨号。
#### Scenario: 超级隐私开启时来话
- **WHEN** 超级隐私模式下收到来电并触发接听
- **THEN** `CurrentIsSuperPrivacyMode` 先 `MuteRinger` 并经 `CallDialog::DialogConnectAnswerPrivpacyModeExtension("SUPER_PRIVACY_MODE", ...)` 弹窗拦截

### Requirement: 有线耳机按键处理
系统 SHALL 由 `CallWiredHeadSet`（`DECLARE_DELAYED_SINGLETON`，`CallObjectManager::AddOneCallObject` 首个通话时 `Init()`、表空时 `DeInit()`）经 `MMI::InputManager::SubscribeKeyEvent` 订阅 `MMI::KeyEvent::KEYCODE_HEADSETHOOK` 按下/抬起：短按（< `FINAL_KEY_DOWN_DURATION_TWO = 2000` 毫秒）`DealKeyMuteShortPressed`（振铃接听；活动+保持并存时恢复保持；否则翻转静音），长按 `DealKeyMuteLongPressed`（振铃拒接；会议中挂断 `ImsConference::GetMainCall()`；否则挂断前台通话）。
#### Scenario: 短按接听振铃通话
- **WHEN** 已连有线耳机且存在 INCOMING 通话时短按耳机键
- **THEN** 以该通话的 `GetOriginalCallType` 对应 videoState 执行 `AnswerCall`

### Requirement: 状态观察者注册表
系统 SHALL 由 `CallStateListener`（`std::set<std::shared_ptr<CallStateListenerBase>> listenerSet_`）经 `NewCallCreated/CallDestroyed/CallStateUpdated/MeeTimeStateUpdated/IncomingCallHungUp/IncomingCallActivated/CallEventUpdated` 分发状态变化，观察者经 `AddOneObserver/RemoveOneObserver` 注册；`CallControlManager::NotifyCallStateUpdated` 在分发失败且目标状态为 INCOMING 时记 `CallManagerHisysevent::WriteIncomingCallFaultEvent`。
#### Scenario: 新建通话通知观察者
- **WHEN** `NotifyNewCallCreated(callObjectPtr)` 触发
- **THEN** 全部注册观察者的 `NewCallCreated` 被依次调用，任一返回失败即记故障事件
