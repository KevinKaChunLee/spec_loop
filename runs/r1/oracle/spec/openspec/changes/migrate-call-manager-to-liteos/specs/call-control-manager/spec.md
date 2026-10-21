# Spec Delta

## MODIFIED Requirements

### Requirement: 初始化与观察者注册
系统 SHALL 由 `CallControlManager::Init()` 创建 `CallStateListener`、`CallRequestHandler`（并 `Init()`）、`CallSettingManager`，执行 `AudioControlManager::Init()` 与 `CallStateObserve()`（向 `CallStateListener` 注册 `CallAbilityReportProxy`、`CallStateReportProxy`、`AudioControlManager`、`RejectCallSms`、`CallRecordsManager`）；samgr `SubscribeSystemAbility(COMMON_EVENT_SERVICE_ID)` 与七组公共事件订阅（`CommonBroadcastSubscriber`/`ContactsBroadcastSubscriber`/`SatcommBroadcastSubscriber`/`SuperPrivacyModeBroadcastSubscriber`/`HSDRBroadcastSubscriber`/`HfpBroadcastSubscriber`/`MuteKeyBroadcastSubscriber`）调用点以 `// todo!!! [broadcast]` 占位（广播暂不调用，订阅逻辑保留骨架）；`IncomingCallWakeup`、`MissedCallNotification`、`DistributedCommunicationManager`、`InteroperableCommunicationManager`、`CallVoiceAssistantManager` 与 `CallSuperPrivacyControlManager::RegisterSuperPrivacyMode()` 不迁移。
#### Scenario: 公共事件 SA 就绪后订阅广播
- **WHEN** `Init()` 执行（无公共事件服务 SA 上线监听）
- **THEN** 七组广播订阅（`CommonBroadcastSubscriber` 等）调用点以 `// todo!!! [broadcast]` 占位，`subscriberPtrList_` 不产生订阅项，初始化照常完成

#### Scenario: 观察者注册表收敛
- **WHEN** `CallStateObserve()` 向 `CallStateListener` 注册观察者
- **THEN** 仅注册存活观察者（`CallAbilityReportProxy`、`CallStateReportProxy`、`AudioControlManager`、`RejectCallSms`、`CallRecordsManager`），已移除能力的观察者不出现

### Requirement: 拨号前置校验
系统 SHALL 由 `CallControlManager::DialCall(number, extras)` 依次执行 `NumberLegalityCheck`（空号返回 `CALL_ERR_PHONE_NUMBER_EMPTY`，超长返回 `CALL_ERR_NUMBER_OUT_OF_RANGE`）、`CallNumberUtils::RemoveSeparatorsPhoneNumber` + `CheckNumberIsEmergency`（经 `CellularCallClient` 桩，ECC 时置 `dialScene = CALL_EMERGENCY`）、`CanDial`（= `CallPolicy::DialPolicy` + `CallPolicy::CanDialMulityCall`；carrier config 查询（`IsSupportVideoCall`）不迁移走代码默认值）与 `PackageDialInformation`（暂存 `dialSrcInfo_`/`extras_`）后交 `CallRequestHandlerPtr_->DialCall()`；卫星开关判定（`SatelliteCallControl::IsSatelliteSwitchEnable`/`IsAllowedSatelliteDialCall`）与超级隐私拦截不迁移。
#### Scenario: 紧急呼叫豁免多通话限制
- **WHEN** ECC 号码拨号
- **THEN** `DialPolicy` 跳过 `HasNewCall`/`HasEmergencyCall` 等限制项，仅 `HasNormalCall`（无卡弹 `CALL_FAILED_NO_SIM_CARD`、飞行模式弹 `CALL_FAILED_IN_AIRPLANE_MODE`、无服务弹 `CALL_FAILED_NO_SERVICE`、电信卡未注册 IMS 弹 `CALL_FAILED_CTCARD_NO_IMS`）仍逐项校验（查卡状态经 `CoreServiceClient` 桩）

#### Scenario: 超级隐私拦截拨号
- **WHEN** 任一非 ECC 拨号请求发起
- **THEN** 无超级隐私判定与 `CallDialog::DialogConnectPrivpacyModeExtension` 弹窗拦截（超级隐私不迁移），拨号直接进入 `CanDial` 仲裁

### Requirement: 下行请求异步化
系统 SHALL 使 `CallRequestHandler` 除 `DialCall()` 同步直调 `CallRequestProcess::DialRequest()` 外，`AnswerCall/RejectCall/HangUpCall/HoldCall/UnHoldCall/SwitchCall/CombineConference/SeparateConference/KickOutFromConference/StartRtt/StopRtt/JoinConference` 全部经打桩 `EventHandler` 投递后立即返回 `TELEPHONY_SUCCESS`，错误仅经日志记录（`CallManagerHisysevent` 维测改日志打印）。
#### Scenario: 同步拨号带回执
- **WHEN** 应用调用 `DialCall`
- **THEN** 拨号请求同步走 `DialRequest()` 并返回实际错误码（如 FDN 校验失败发 `EVENT_INVALID_FDN_NUMBER` 并弹 `CALL_FAILED_DUE_TO_FDN` 提示，提示经 `CallDialog` 桩）

#### Scenario: 接听请求异步
- **WHEN** 应用调用 `AnswerCall(callId, videoState)` 且 `AnswerCallPolicy` 校验通过（状态须 INCOMING/WAITING）
- **THEN** 请求经打桩 `EventHandler` 异步下发 `AnswerRequest`，方法立即返回 `TELEPHONY_SUCCESS`

### Requirement: 通话界面按需连接与延时断开
系统 SHALL 由 `CallConnectAbility`（`DECLARE_DELAYED_SINGLETON`）经桩化的 `AAFwk::AbilityManagerClient::GetInstance()->ConnectAbility(want, connectCallback_, userId = -1)` 连接 `com.ohos.callui` / `com.ohos.callui.ServiceAbility`（桩不真正拉起界面，回调按桩语义触发）；`CallControlManager::ConnectCallUiService(false)` 以打桩 `EventHandler` 延时任务（`DISCONNECT_DELAY_TIME = 1000000` 微秒）提交延时断开，静态 `alarmSeted` 去重，连接分支取消未决断开任务。
#### Scenario: 界面连接经桩执行
- **WHEN** 首个通话对象入表触发 `CallConnectAbility::ConnectAbility()`
- **THEN** 连接请求经桩执行并按桩配置回调，不真正拉起通话界面，业务流程不受阻

#### Scenario: 界面异常断开自动重连
- **WHEN** 桩触发 `CallAbilityConnectCallback::OnAbilityDisconnectDone` 收到 `UNEXPECT_DISCONNECT_CODE(-1)`
- **THEN** `ReConnectAbility()` 遍历 `GetAllCallInfoList`，只要存在非空闲通话即重新经桩发起连接

### Requirement: 状态观察者注册表
系统 SHALL 由 `CallStateListener`（`std::set<std::shared_ptr<CallStateListenerBase>> listenerSet_`）经 `NewCallCreated/CallDestroyed/CallStateUpdated/MeeTimeStateUpdated/IncomingCallHungUp/IncomingCallActivated/CallEventUpdated` 分发状态变化，观察者经 `AddOneObserver/RemoveOneObserver` 注册；`CallControlManager::NotifyCallStateUpdated` 在分发失败且目标状态为 INCOMING 时记日志（原 `CallManagerHisysevent::WriteIncomingCallFaultEvent` 改日志打印）。
#### Scenario: 新建通话通知观察者
- **WHEN** `NotifyNewCallCreated(callObjectPtr)` 触发
- **THEN** 全部注册观察者的 `NewCallCreated` 被依次调用，任一返回失败即记日志

## REMOVED Requirements

### Requirement: 超级隐私参数驱动
**Reason**: AGENTS.md 功能范围：超级隐私不支持。
**Migration**: `CallSuperPrivacyControlManager` 与 `CallPolicy::SuperPrivacyMode` 分支不迁移；拨号/接听/挂断链路中的超级隐私判定、`CloseAllCall` 与 `SUPER_PRIVACY_MODE_PARAM_KEYS` 参数监听调用点移除。

### Requirement: 有线耳机按键处理
**Reason**: AGENTS.md 功能范围：有线耳机不支持（`ABILITY_MEDIA_SUPPORT` 为不支持宏）。
**Migration**: `CallWiredHeadSet` 不迁移；`CallObjectManager::AddOneCallObject` 首通话时的 `CallWiredHeadSet::Init()` 与表空时的 `DeInit()` 调用点移除。
