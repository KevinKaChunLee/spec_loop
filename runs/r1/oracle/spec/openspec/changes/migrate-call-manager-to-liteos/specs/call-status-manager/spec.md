# Spec Delta

## MODIFIED Requirements

### Requirement: 单条上报状态分派
系统 SHALL 由 `CallStatusManager::HandleCallReportInfo(CallDetailInfo)` 按 `info.callType`（`TYPE_VOIP`→`HandleVoipCallReportInfo`；`TYPE_BLUETOOTH` 分派不迁移）与 `info.state`（ACTIVE→`ActiveHandle`、HOLDING→`HoldingHandle`、DIALING→`DialingHandle`、ALERTING→`AlertHandle`、INCOMING→`AcquireIncomingLock`+`IncomingHandle`+`ReleaseIncomingLock`（持锁调用点为空操作占位，功耗锁暂不调用）、WAITING/DISCONNECTED/DISCONNECTING→`HandleCallReportInfoEx` 二次分派 `WaitingHandle`/`DisconnectedHandle`/`DisconnectingHandle`）处理，收尾统一 `HandleDsdaInfo(info.accountId)`（`CoreServiceClient::GetInstance().GetDsdsMode()` 桩恒返回 0，仅走默认路径）；超时判定与 `FinishAsyncTrace` 维测改日志打印。
#### Scenario: 来电上报持锁处理
- **WHEN** 协议栈上报 INCOMING 单条状态
- **THEN** `IncomingHandle` 直接执行（`AcquireIncomingLock`/`ReleaseIncomingLock` 为空操作占位，功耗锁暂不调用），超时判定（`JudgingIncomingTimeOut` 语义）以日志记录

### Requirement: 状态迁移与观察者广播
系统 SHALL 由 `UpdateCallState(call, nextState)` 记录 `priorState` 后执行 `call->SetTelCallState(nextState)` + `CallObjectManager::UpdateOneCallObjectByCallId`，再经 `CallControlManager::NotifyCallStateUpdated(call, priorState, nextState)` 广播观察者；`TYPE_SATELLITE` 通话的 `SatelliteCallControl::HandleSatelliteCallStateUpdate` 联动不迁移。
#### Scenario: 迁移广播失败记故障
- **WHEN** 观察者广播失败且 `nextState == CALL_STATUS_INCOMING`
- **THEN** 以日志记录原 `CallManagerHisysevent::WriteIncomingCallFaultEvent` 的故障信息

### Requirement: 来电处理链
系统 SHALL 由 `IncomingHandle` 依次执行：`RefreshOldCall`（index=0 的 pending 拨号先 `DealFailDial`）、CS/IMS 的 `IncomingFilterPolicy(info)`、`CreateNewCall(info, CALL_DIRECTION_IN)`、`SetContactInfo`（打桩 `EventHandler` 异步 `QueryCallerInfo`，联系人 DataShare 查询调用点以 `// todo!!! [database]` 占位返回默认）、`ShouldBlockIncomingCall`（spam 检测编排保留，外部检测调用点占位，默认不拦截）→ `IsRejectCall`（OOBE 判定改经打桩系统参数；免打扰 DataShare 查询调用点占位，默认不拒接）→ `IsRingOnceCall`（响一声）、`AddOneCallObject`、`NotifyNewCallCreated`、`UpdateCallState`；一号双终端判定（`IsFromTheSameNumberAtTheSameTime`/`ModifyEsimType`，ESIM 不支持）、`NeedPlayVideoRing`/`DistributedCommunicationManager::ProcessCallInfo`（视频彩振/分布式）、`StartInComingCallMotionRecognition`（动作识别）、`StartFlashRemind()`（来电闪光）不迁移。
#### Scenario: 联系人查询占位返回默认
- **WHEN** 来电触发异步 `QueryCallerInfo`
- **THEN** DataShare 查询调用点为 todo 占位，`ContactInfo` 取默认值（显示名缺省为号码），来电创建流程不受阻

#### Scenario: 一号双终端来电
- **WHEN** 同号、callId 差 1、旧 call 处于 INCOMING 且创建时间差不超过 10 秒的新来话
- **THEN** 不执行 `ModifyEsimType` 的 settingsdata 联动（ESIM 不支持），按普通来话分别处理

### Requirement: 来电过滤仅含 MDM 与 ECC 豁免
系统 SHALL 由 `CallIncomingFilterManager::DoIncomingFilter` 仅执行 ECC 豁免（`CellularCallConnection::IsEmergencyPhoneNumber`，经 `CellularCallClient` 桩）：紧急号码直接放行，非紧急号码按放行处理；MDM 禁入（`EdmCallPolicy`，EDM 不支持）不迁移；骚扰拦截在建 call 后由 `ShouldBlockIncomingCall` 执行（外部检测调用点占位，默认不拦截），异步过滤完成由 `CallFilterCompleteResult(info)` 收尾；`CallStatusPolicy::FilterResultsDispose` 判定 `HasRingingMaximum()`（30 通）或 `HasDialingMaximum()`（30 通）时直接挂断的逻辑保留。
#### Scenario: MDM 禁入名单拦截
- **WHEN** 非紧急号码来电进入 `DoIncomingFilter`
- **THEN** 仅执行 ECC 豁免判定后放行，无 MDM 名单拦截（`EdmCallPolicy` 不迁移）

#### Scenario: 振铃/拨号满则挂断
- **WHEN** `FilterResultsDispose` 判定 `HasRingingMaximum()`（30 通）或 `HasDialingMaximum()`（30 通）
- **THEN** 直接 `call->HangUpCall()`；存在 `CALL_STATE_RINGING` 的 VoIP 时改 `call->RejectCall()`

### Requirement: 断开处理与自动恢复
系统 SHALL 由 `DisconnectedHandle` 执行 `timeWaitHelper_->NotifyAll()`（响一声等待唤醒）、`RefreshCallDisconnectReason`（`DISCONNECTED_REASON_CS_CALL_ANSWERED_ELSEWHER` 等 → `SetAnswerType(CALL_ANSWERED_ELSEWHER)`）、`UpdateCallState(DISCONNECTED)`、`HandleHoldCallOrAutoAnswerCall` 仅保留默认路径（`CoreServiceClient::GetInstance().GetDsdsMode()` 桩恒 0：同 slot 存在满足 `GetCanUnHoldState()` 的保持通话时自动 `UnHoldCall()`；`DSDS_MODE_V3` 自动接听与 `DSDS_MODE_V5_DSDA`/`DSDS_MODE_V5_TDM` 跨卡分支不迁移）；会议退出处理随会议对象移除。
#### Scenario: 活动通话断开后自动恢复保持
- **WHEN** 前一活动通话断开且同 slot 存在满足 `GetCanUnHoldState()` 的保持通话
- **THEN** `HandleHoldCallOrAutoAnswerCall` 自动执行 `UnHoldCall()` 恢复保持通话

#### Scenario: DSDA 双卡自动接听
- **WHEN** 断开处理查询 DSDS 模式
- **THEN** `GetDsdsMode()` 恒返回 0，`AutoAnswerForVoiceCall`/`AutoAnswerForVideoCall` 与 `AutoUnHoldForDsda` 跨卡分支不可达

### Requirement: OOBE 未配置时拒接来电
系统 SHALL 由 `ShouldRejectIncomingCall` 判定：存在紧急呼叫、`GetDevProvisioned() != DEVICE_PROVISION_VALID` 或 `user_setup_complete` 为 "0"/空时拒接（OOBE 判定改读打桩系统参数表，settingsdata DataShare 查询不调用；拒接事件以日志记录原 `REJECT_BY_OOBE` 动作）；`OOBEStatusObserver` 的 settingsdata 监听不迁移（参数变化经桩表配置）。
#### Scenario: 开箱未完成时来电
- **WHEN** 桩参数表配置设备未完成开箱（`device_provisioned` 未就绪）时收到来电
- **THEN** 来电被系统拒接并以日志记录原 `CALL_INCOMING_REJECT_BY_SYSTEM` 事件信息

### Requirement: 通话对象创建按类型分派
系统 SHALL 由 `CreateNewCallByCallType`（`TYPE_CS`→`CSCall`、`TYPE_IMS`→`IMSCall`，不再初始化视频升级状态机）与 `CreateNewCallByCallTypeEx`（`TYPE_VOIP`→`VoIPCall`）创建对象；`TYPE_OTT`/`TYPE_SATELLITE`/`TYPE_BLUETOOTH` 分派不迁移；`DialScene::CALL_EMERGENCY` 置 `SetIsEccContact(true)` 保留。
#### Scenario: IMS 去电对象创建
- **WHEN** 全量/单条上报的 DIALING 且 `callType == TYPE_IMS`
- **THEN** 创建 `IMSCall` 仅承载语音通话行为，不初始化视频升级状态机

## REMOVED Requirements

### Requirement: 防诈检测联动
**Reason**: AGENTS.md 功能范围：防诈 antifraud 不支持。
**Migration**: `AntiFraudService` 及 antifraud 模块组不迁移；`ActiveHandle` 中的防诈启动/停检调用点与 extraParams "antiFraudState" 联动移除。
