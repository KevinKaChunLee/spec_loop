# 上行状态机（call-status-manager）Specification

## Purpose
描述 `telephony_call_manager/services/call/src` 中的上行状态机（协议栈→应用）：`CallStatusManager`（`HandleCallReportInfo`/`HandleCallsReportInfo` 状态分派与对象创建）、`CallStatusPolicy`（上行仲裁：`DialingHandlePolicy`/`FilterResultsDispose`）、`CallIncomingFilterManager`（来电前置过滤：MDM 禁入与 ECC 豁免）。编译开关：`NOT_SUPPORT_MULTICALL`（`AutoAnswerSecondCall`，默认 false）、`TELEPHONY_CUST_SUPPORT`（联系人增强查询，默认手机构建在位）、`AUDIO_SUPPORT`（`ActiveHandle`/`AlertHandle` 的扬声器/音量联动）。关联常量：`SLOT_NUM = 2`（`callDetailsInfo_[SLOT_NUM]` 按 slot 分桶缓存全量列表）。

## Requirements

### Requirement: 单条上报状态分派
系统 SHALL 由 `CallStatusManager::HandleCallReportInfo(CallDetailInfo)` 按 `info.callType`（`TYPE_VOIP`→`HandleVoipCallReportInfo`、`TYPE_BLUETOOTH`→`HandleBluetoothCallReportInfo`）与 `info.state`（ACTIVE→`ActiveHandle`、HOLDING→`HoldingHandle`、DIALING→`DialingHandle`、ALERTING→`AlertHandle`、INCOMING→`AcquireIncomingLock`+`IncomingHandle`+`ReleaseIncomingLock`、WAITING/DISCONNECTED/DISCONNECTING→`HandleCallReportInfoEx` 二次分派 `WaitingHandle`/`DisconnectedHandle`/`DisconnectingHandle`）处理，收尾统一 `HandleDsdaInfo(info.accountId)`。
#### Scenario: 来电上报持锁处理
- **WHEN** 协议栈上报 INCOMING 单条状态
- **THEN** 在 `IncomingCallWakeup` 的来电锁保护下执行 `IncomingHandle`，随后 `FinishAsyncTrace(HITRACE_TAG_OHOS, "InComingCall", getpid())` 与 `CallManagerHisysevent::JudgingIncomingTimeOut` 判超时

### Requirement: 全量列表比对
系统 SHALL 由 `HandleCallsReportInfo(CallDetailsInfo)` 将上报列表与 `callDetailsInfo_[slotId]` 逐条比对：index 相同且 state/mpty/callType/callMode 变化或 state 为 ALERTING 的项走 `HandleCallReportInfo`；新 call 走 `HandleConnectingCallReportInfo`（若 `CallObjectManager::IsVoipCallExist(CALL_STATUS_ACTIVE)` 且新 call 为 INCOMING，改 state 为 WAITING）；旧列表中消失的项置 DISCONNECTED 再上报；末尾 `UpdateCallDetailsInfo` 剔除断开项。
#### Scenario: 畅连通话在通话中新来话降级等待
- **WHEN** 已有 `TYPE_VOIP` 的 ACTIVE 通话且全量列表出现 INCOMING 新 call
- **THEN** 新 call 的 state 改写为 WAITING 后再进入状态处理

### Requirement: 状态迁移与观察者广播
系统 SHALL 由 `UpdateCallState(call, nextState)` 记录 `priorState` 后执行 `call->SetTelCallState(nextState)` + `CallObjectManager::UpdateOneCallObjectByCallId`，再经 `CallControlManager::NotifyCallStateUpdated(call, priorState, nextState)` 广播观察者；`TYPE_SATELLITE` 通话额外经 `SatelliteCallControl::HandleSatelliteCallStateUpdate`。
#### Scenario: 迁移广播失败记故障
- **WHEN** 观察者广播失败且 `nextState == CALL_STATUS_INCOMING`
- **THEN** 记录 `CallManagerHisysevent::WriteIncomingCallFaultEvent`

### Requirement: 来电处理链
系统 SHALL 由 `IncomingHandle` 依次执行：`RefreshOldCall`（index=0 的 pending 拨号先 `DealFailDial`）、CS/IMS/SATELLITE 的 `IncomingFilterPolicy(info)`、`CreateNewCall(info, CALL_DIRECTION_IN)`、一号双终端判定（`IsFromTheSameNumberAtTheSameTime` 命中则 `ModifyEsimType`）、`SetContactInfo`（`ffrt::submit` 异步 `QueryCallerInfo`，含 `AudioControlManager::NeedPlayVideoRing` 写入 "VideoRingPath" 与 `DistributedCommunicationManager::ProcessCallInfo(NAME)`）、`ShouldBlockIncomingCall`（spam 检测）→ `IsRejectCall`（OOBE/免打扰拒接）→ `IsRingOnceCall`（响一声）、`AddOneCallObject`、`StartInComingCallMotionRecognition`、`NotifyNewCallCreated`、`UpdateCallState`、`CallControlManager::StartFlashRemind()`。
#### Scenario: 一号双终端来电
- **WHEN** 同号、callId 差 1、旧 call 处于 INCOMING 且创建时间差不超过 10 秒的新来话
- **THEN** `ModifyEsimType` 将 settingsdata 的 `key_esim_card_type` 写为 "1" 并联动 smartoff 三项设置

### Requirement: 来电过滤仅含 MDM 与 ECC 豁免
系统 SHALL 由 `CallIncomingFilterManager::DoIncomingFilter` 执行且仅执行两步：`CallControlManager::IsIncomingEnable(phoneNum)`（`EdmCallPolicy` MDM 禁入，失败返回 `TELEPHONY_ERR_POLICY_DISABLED`）与 `CellularCallConnection::IsEmergencyPhoneNumber`（ECC 直接放行）；骚扰拦截在建 call 后由 `ShouldBlockIncomingCall`（`SpamCallAdapter::DetectSpamCall` + `WaitForDetectResult` + `GetParseResult`）执行，异步过滤完成由 `CallFilterCompleteResult(info)` 收尾（重建 call→`UpdateCallState`→`FilterResultsDispose`）。
#### Scenario: MDM 禁入名单拦截
- **WHEN** 来电号码命中 `EdmCallPolicy` 的 BLOCK 名单
- **THEN** `DoIncomingFilter` 返回 `TELEPHONY_ERR_POLICY_DISABLED`，不创建通话对象

#### Scenario: 振铃/拨号满则挂断
- **WHEN** `CallStatusPolicy::FilterResultsDispose` 判定 `HasRingingMaximum()`（30 通）或 `HasDialingMaximum()`（30 通）
- **THEN** 直接 `call->HangUpCall()`；存在 `CALL_STATE_RINGING` 的 VoIP 时改 `call->RejectCall()`

### Requirement: 断开处理与自动恢复
系统 SHALL 由 `DisconnectedHandle` 执行 `timeWaitHelper_->NotifyAll()`（响一声等待唤醒）、`RefreshCallDisconnectReason`（`DISCONNECTED_REASON_CS_CALL_ANSWERED_ELSEWHER` 等 → `SetAnswerType(CALL_ANSWERED_ELSEWHER)`）、`ExitConference`、`UpdateCallState(DISCONNECTED)`、`HandleHoldCallOrAutoAnswerCall`（按 `CoreServiceClient::GetDsdsMode()` 分档：`DSDS_MODE_V3`→`AutoAnswer`，`DSDS_MODE_V5_DSDA`/`DSDS_MODE_V5_TDM`→`AutoHandleForDsda` + `AutoUnHoldForDsda`）。
#### Scenario: 活动通话断开后自动恢复保持
- **WHEN** 前一活动通话断开且同 slot 存在满足 `GetCanUnHoldState()` 的保持通话
- **THEN** `HandleHoldCallOrAutoAnswerCall` 自动执行 `UnHoldCall()` 恢复保持通话

#### Scenario: DSDA 双卡自动接听
- **WHEN** `GetDsdsMode()` 返回 `DSDS_MODE_V5_DSDA` 且另一卡通话存在时来话进入振铃
- **THEN** `AutoAnswerForVoiceCall`（或视频来话 `AutoAnswerForVideoCall`）自动接听，随后 `AutoUnHoldForDsda` 恢复他卡保持通话

### Requirement: OOBE 未配置时拒接来电
系统 SHALL 由 `ShouldRejectIncomingCall` 判定：存在紧急呼叫、`GetDevProvisioned() != DEVICE_PROVISION_VALID` 或 `user_setup_complete` 为 "0"/空时拒接（HiSysEvent 动作 `REJECT_BY_OOBE`）；`OOBEStatusObserver` 经 `RegisterObserver` 监听 settingsdata 的 `device_provisioned` 变化并 `UpdateDevProvisioned`。
#### Scenario: 开箱未完成时来电
- **WHEN** 设备 `device_provisioned` 未就绪时收到来电
- **THEN** 来电被系统拒接并记录 `CALL_INCOMING_REJECT_BY_SYSTEM` 事件（动作 `REJECT_BY_OOBE`）

### Requirement: 通话对象创建按类型分派
系统 SHALL 由 `CreateNewCallByCallType`（`TYPE_CS`→`CSCall`、`TYPE_IMS`→`IMSCall` 并 `InitVideoCall()`、`TYPE_OTT`→`OTTCall`）与 `CreateNewCallByCallTypeEx`（`TYPE_VOIP`→`VoIPCall`、`TYPE_SATELLITE`→`SatelliteCall`、`TYPE_BLUETOOTH`→`BluetoothCall` 且取 `BluetoothCallConnection::GetMacAddress()`）创建对象；`DialScene::CALL_EMERGENCY` 置 `SetIsEccContact(true)`。
#### Scenario: IMS 去电对象创建
- **WHEN** 全量/单条上报的 DIALING 且 `callType == TYPE_IMS`
- **THEN** 创建 `IMSCall` 并完成 `InitVideoCall()` 的视频升级状态机初始化

### Requirement: 防诈检测联动
系统 SHALL 在 `ActiveHandle` 依系统参数 `ANTIFRAUD_FEATURE = "const.telephony.antifraud.supported"` 为真时调 `SetupAntiFraudService`（仅主用户 `MAIN_USER_SPACE(100)`、非联系人/非标记号、`AntiFraudService::IsAntiFraudSwitchOn()` 且 slotId/index 未占用）；检测结果经 `TriggerAntiFraud`/`UpdateAntiFraudState`（extraParams 写 "antiFraudState"）刷新；`HandleCeliaCall`/`StopAntiFraudDetect` 停检并复位 `SetAntiFraudSlotId`/`SetAntiFraudIndex`。
#### Scenario: 接通后启动防诈检测
- **WHEN** 来电接通进入 ACTIVE 且防诈总开关为真
- **THEN** `SetupAntiFraudService` 占用 slotId/index 并经 `ffrt::submit` 调 `StartAntiFraudService`
