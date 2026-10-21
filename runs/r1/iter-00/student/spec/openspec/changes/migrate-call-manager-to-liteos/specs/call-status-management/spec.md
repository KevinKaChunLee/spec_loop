# Spec Delta

## MODIFIED Requirements

### Requirement: 单条上报状态分发
系统 SHALL 在 `CallStatusManager::HandleCallReportInfo` 中按 `CallDetailInfo` 的 `state` 分发：CALL_STATUS_ACTIVE→`ActiveHandle`、CALL_STATUS_HOLDING→`HoldingHandle`、CALL_STATUS_DIALING→`DialingHandle`、CALL_STATUS_ALERTING→`AlertHandle`、CALL_STATUS_INCOMING→`IncomingHandle`、CALL_STATUS_WAITING/DISCONNECTED/DISCONNECTING→`HandleCallReportInfoEx`；TYPE_VOIP 走 `HandleVoipCallReportInfo` 的分流分支与 TYPE_BLUETOOTH 先经 `HandleBluetoothCallReportInfo` 的分支不迁移（liteOS 暂不支持 VoIP、不支持 BLUETOOTH 类型通话）；每次处理完成后调用 `HandleDsdaInfo` 及 `BluetoothCallService` 的 `GetCallState` 的 DSDA/蓝牙调用点不迁移（liteOS 上 `CallManagerUtils::GetDsdsMode()` 恒返回 0）。
#### Scenario: 来电状态分发
- **WHEN** 协议栈上报 `state` 为 CALL_STATUS_INCOMING 的蜂窝呼叫
- **THEN** 先经 `CallControlManager` 的 `AcquireIncomingLock` 再执行 `IncomingHandle`，随后 `ReleaseIncomingLock`，并以 `CallManagerHisysevent` 的 `JudgingIncomingTimeOut` 做维测计时（维测改日志打印）
#### Scenario: VoIP 上报分流
- **WHEN** `info.callType` 为 TYPE_VOIP
- **THEN** VoIP 分流链路不迁移（`HandleVoipCallReportInfo` 随 VoIP 暂不支持移除），TYPE_VOIP 上报不进入蜂窝状态 switch，也无 VoIP 专用处理分支
#### Scenario: 非法状态
- **WHEN** `info.state` 为 switch 未覆盖的取值
- **THEN** 仅记录 "Invalid call state!" 日志，不做状态处理

### Requirement: 通话列表增量比对
系统 SHALL 在 `CallStatusManager::HandleCallsReportInfo` 中按 `slotId` 将新 `CallDetailsInfo` 与已存 `callDetailsInfo_` 比对：同 `index` 且 state/mpty/callType/callMode 有变化（或 state 为 CALL_STATUS_ALERTING）时调用 `HandleCallReportInfo`；新出现的 `index` 走 `HandleConnectingCallReportInfo`（存在活跃 VoIP 通话时将该呼叫的 INCOMING 改写为 CALL_STATUS_WAITING 的分支不迁移，`IsVoipCallExist` 改写逻辑随 VoIP 裁剪移除）；旧列表中消失的 `index` 置 CALL_STATUS_DISCONNECTED 后上报；末尾经 `UpdateCallDetailsInfo` 刷新缓存并剔除已断开项；`slotId` 无效时返回 CALL_ERR_INVALID_SLOT_ID。
#### Scenario: 状态变化触发处理
- **WHEN** 上报列表中某 `index` 的状态由 CALL_STATUS_DIALING 变为 CALL_STATUS_ACTIVE
- **THEN** 对该呼叫触发一次 `HandleCallReportInfo`（进入 `ActiveHandle`）
#### Scenario: 列表消失项补挂断
- **WHEN** 旧 `callDetailsInfo_` 中某 `index` 不在新上报列表中
- **THEN** 该项状态被置为 CALL_STATUS_DISCONNECTED 并按挂断流程上报
#### Scenario: 活跃 VoIP 下的新来电
- **WHEN** 基线中存在 CALL_STATUS_ACTIVE 的 VoIP 通话且新上报呼叫 state 为 CALL_STATUS_INCOMING
- **THEN** liteOS 上 VoIP 通话对象不存在（`IsVoipCallExist` 恒为 false），该呼叫不经 INCOMING→CALL_STATUS_WAITING 改写，按上报原状态进入 `HandleCallReportInfo`

### Requirement: 来电建立与拦截
系统 SHALL 在 `IncomingHandle` 中先经 `RefreshOldCall` 去重（已存在则直接返回）；对 TYPE_CS/TYPE_IMS 呼叫先执行 `IncomingFilterPolicy`（转 `CallIncomingFilterManager` 的 `DoIncomingFilter`，TYPE_SATELLITE 分支随卫星通话不支持移除）；随后 `CreateNewCall`（CALL_DIRECTION_IN）并 `SetContactInfo`（联系人查询经 `QueryCallerInfo` 的 DataShare 查询调用点以 `// todo!!! [database] ref to call_data_base_helper.cpp Query` 占位、查询未命中时保持默认 `ContactInfo`；`TELEPHONY_CUST_SUPPORT` 下对长度达 `QUERY_CONTACT_LEN` 的号码的后缀匹配增强查询调用点以 `// todo!!! [database] ref to call_data_base_helper.cpp QueryContactInfoEnhanced` 占位、不加载 libtelephony_cust_api.z.so）；`IsRejectCall` 判定拒绝时走 `HandleRejectCall`（`RejectCall`，拦截场景另经 `AddBlockLogAndNotification`），其中骚扰识别查询（`ShouldBlockIncomingCall` 的 `SpamCallAdapter::DetectSpamCall`）调用点占位、识别未就绪时返回 false 放行来电；`IsRingOnceCall` 时走 `HandleRingOnceCall`；否则 `AddOneCallObject`、`NotifyNewCallCreated`、`UpdateCallState`、`FilterResultsDispose`；过滤异步完成经 `CallFilterCompleteResult` 补建呼叫并依次执行 `NotifyNewCallCreated`、`UpdateCallState`、`FilterResultsDispose`。
#### Scenario: 命中拒绝策略
- **WHEN** 来电命中经桩注入的 `ShouldRejectIncomingCall`/`ShouldBlockIncomingCall` 等拒绝判定
- **THEN** 不进入正常来电通知流程，执行 `RejectCall`，拦截场景追加 `AddBlockLogAndNotification`
#### Scenario: 识别未就绪放行
- **WHEN** 骚扰识别与增强联系人查询调用点均为 todo 占位（外部查询未就绪）
- **THEN** `ShouldBlockIncomingCall` 返回 false 放行来电，`QueryCallerInfo` 返回未命中的默认联系人信息，来电进入正常通知流程
#### Scenario: 增强联系人查询
- **WHEN** 已定义 `TELEPHONY_CUST_SUPPORT` 且来电号码长度不小于 `QUERY_CONTACT_LEN`
- **THEN** 后缀匹配增强查询调用点以 `// todo!!! [database] ref to call_data_base_helper.cpp QueryContactInfoEnhanced` 占位、不实际执行 DataShare 查询，未命中时保持默认 `ContactInfo`
#### Scenario: 过滤完成回调
- **WHEN** 来电过滤管理器异步完成后回调 `CallFilterCompleteResult`
- **THEN** 创建来电对象并依次执行 `NotifyNewCallCreated`、`UpdateCallState`、`FilterResultsDispose`

### Requirement: 拨号与通话中状态处理
系统 SHALL 由 `DialingHandle` 处理去电：`index` 大于 0 且 `UpdateDialingHandle` 命中已有对象时经 `UpdateDialingCallInfo` 刷新；否则 `CreateNewCall`（CALL_DIRECTION_OUT）、`AddOneCallObject`、`DialingProcess`、`NotifyNewCallCreated` 后 `UpdateCallState` 置 CALL_STATUS_DIALING。`ActiveHandle` 在查不到对象时依次尝试 `CreateAndSaveNewCall` 与 `RefreshDialingStateByOtherState`；`mpty` 为 1 的会议归组处理（`SetConferenceCall`/`LaunchConference`/`ExitConference`/`HoldConference`）随会议通话不支持移除；随后 `UpdateCallState` 置 CALL_STATUS_ACTIVE 并允许保持通话恢复切换。`HoldingHandle` 对上报的 holding 呼叫直接经 `UpdateCallState` 置 CALL_STATUS_HOLDING（DSDS 模式分支 `UpdateCallStateAndHandleDsdsMode` 随 `CallManagerUtils::GetDsdsMode()` 恒返回 0 精简）。
#### Scenario: 首次拨号上报
- **WHEN** 上报 dialing 状态且 `info.index` 为 INIT_INDEX
- **THEN** 创建去电对象、置 pendingMo 标志（`SetPendingMo`），经 `DialingProcess` 与 `UpdateCallState` 进入 CALL_STATUS_DIALING
#### Scenario: 激活触发会议归组
- **WHEN** 上报 active 且 `info.mpty` 为 1、该 slotId 会议成员数大于 1
- **THEN** 会议归组链路（`SetConferenceCall`/`LaunchConference`）随会议通话不支持移除，不做会议归组，该呼叫直接经 `UpdateCallState` 置 CALL_STATUS_ACTIVE
#### Scenario: 保持状态处理
- **WHEN** 上报 holding 状态的蜂窝呼叫
- **THEN** 该呼叫状态经 `UpdateCallState` 更新为 CALL_STATUS_HOLDING，不进入 DSDS 模式分支

### Requirement: 挂断处理与自动恢复
系统 SHALL 在 `DisconnectedHandle` 中先唤醒 `timeWaitHelper_`（响一声场景）；未经 DISCONNECTING 的远端挂断先 `AcquireDisconnectedLock`；经 `RefreshCallDisconnectReason` 保存原因后 `UpdateCallState` 置 CALL_STATUS_DISCONNECTED，随后 `HandleHoldCallOrAutoAnswerCall`：`IsCanUnHold` 判定可恢复时对同 slotId 保持通话执行 `UnHoldCall`（DSDS_MODE_V3 的 `AutoAnswer` 与 DSDA/TDM 的 `AutoHandleForDsda` 分支随 `CallManagerUtils::GetDsdsMode()` 恒返回 0 移除）；最后 `DeleteOneCallObject` 删除对象（会议仅剩一人置 TEL_CONFERENCE_IDLE 的处理随会议通话不支持移除）。liteOS 按 `NOT_SUPPORT_MULTICALL` 已定义处理：`IsTwoCallBtCallAndESIM` 或 `IsTwoCallESIMCall` 场景断开后执行 `AutoAnswerSecondCall` 自动接听。`HandleDisconnectedCause` 经 `NotifyCallDestroyed` 通知观察者。
#### Scenario: 恢复保持通话
- **WHEN** 通话断开且无其它活跃/等待/拨号呼叫、存在可恢复的同 slotId 保持通话
- **THEN** 对该保持通话执行 `UnHoldCall`
#### Scenario: 不支持多通话自动接听
- **WHEN** 按已定义的 `NOT_SUPPORT_MULTICALL` 且 `IsTwoCallBtCallAndESIM` 或 `IsTwoCallESIMCall` 成立
- **THEN** 断开后 `AutoAnswerSecondCall` 对 `GetAutoAnswerState` 为真的来电/等待呼叫自动 `AnswerCall`
#### Scenario: 会议仅剩一人
- **WHEN** 断开后该 slotId 会议列表仅剩 1 个成员
- **THEN** 会议仅剩一人置 TEL_CONFERENCE_IDLE 的处理随会议通话不支持移除，不做会议状态重置与重新上报

### Requirement: 协议栈事件与错误处理
系统 SHALL 在 `HandleEventResultReportInfo` 中仅接受 `EVENT_REQUEST_RESULT_TYPE` 类型事件（否则返回 CALL_ERR_PHONE_TYPE_UNEXPECTED）；对处于 CALL_RUNNING_STATE_DIALING 的呼叫执行 `DealFailDial`；经 `mEventIdTransferMap_` 将 `RequestResultEventId` 映射为 `CallAbilityEventId` 后 `NotifyCallEventUpdated`：EVENT_DIAL_NO_CARRIER 附带拨号号码、EVENT_HOLD_CALL_FAILED 复位 `needWaitHold_`（EVENT_COMBINE_CALL_FAILED 触发的 `HandleCombineConferenceFailEvent` 随会议通话不支持移除）。`HandleOttEventReportInfo` 及 `mOttEventIdTransferMap_` 随 OTT 类型通话不支持不迁移。
#### Scenario: 无运营商拨号失败
- **WHEN** 收到 RESULT_DIAL_NO_CARRIER 事件
- **THEN** 对拨号中呼叫执行 `DealFailDial`，并以 EVENT_DIAL_NO_CARRIER 携带号码 `NotifyCallEventUpdated`
#### Scenario: 合并会议失败
- **WHEN** 收到 RESULT_COMBINE_SEND_FAILED 事件
- **THEN** `HandleCombineConferenceFailEvent` 触发链路随会议通话不支持移除，活跃通话对象不做合并会议失败处理
#### Scenario: 非请求结果类型
- **WHEN** `info.eventType` 不为 EVENT_REQUEST_RESULT_TYPE
- **THEN** 返回 CALL_ERR_PHONE_TYPE_UNEXPECTED

### Requirement: 多通话仲裁策略
系统 SHALL 由 `CallStatusPolicy::DialingHandlePolicy` 在同号码呼叫已存在（`IsCallExist`）时返回 CALL_ERR_CALL_ALREADY_EXISTS；由 `FilterResultsDispose` 仲裁新来电：`HasRingingMaximum` 或 `HasDialingMaximum` 超限时对该呼叫 `HangUpCall`；否则执行 `IncomingCallBase` 并 `NotifyNewCallCreated`（VoIP 全局状态为 CALL_STATE_RINGING 时 `RejectCall` 的分支随 VoIP 暂不支持移除）。
#### Scenario: 重复号码去电
- **WHEN** 同号码呼叫对象已存在时进入 `DialingHandlePolicy`
- **THEN** 返回 CALL_ERR_CALL_ALREADY_EXISTS
#### Scenario: 通话数超限
- **WHEN** 振铃或拨号通话数达到上限且新来电进入 `FilterResultsDispose`
- **THEN** 对该来电执行 `HangUpCall`，不再进入来电通知流程
#### Scenario: 与 VoIP 振铃冲突
- **WHEN** 基线中 VoIP 呼叫处于 CALL_STATE_RINGING 且蜂窝来电进入 `FilterResultsDispose`
- **THEN** VoIP 全局振铃判定分支随 VoIP 暂不支持移除（无 VoIP 通话对象与 VoIP 全局状态），蜂窝来电按普通仲裁继续 `IncomingCallBase` 与 `NotifyNewCallCreated`
