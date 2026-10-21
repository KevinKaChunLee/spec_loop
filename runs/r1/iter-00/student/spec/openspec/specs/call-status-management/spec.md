# 上行通话状态管理（Call Status Management）Specification

## Purpose
描述 HMOS `telephony_call_manager` 中处理协议栈上行通话状态/事件并驱动后续副作用的核心能力：接收 cellular_call / OTT / VoIP 上报的 `CallDetailInfo` / `CallDetailsInfo` / `CellularCallEventInfo` / `OttCallEventInfo`，完成通话对象的创建、状态迁移、多通话仲裁与对观察者的分发。源码落点：`telephony_call_manager/services/call/{include,src}`，主要文件：`call_status_manager.cpp/.h`（类 `CallStatusManager`）、`call_status_policy.cpp/.h`（类 `CallStatusPolicy`，继承 `CallObjectManager`）、`call_state_listener.cpp/.h`（类 `CallStateListener`，观察者基类 `CallStateListenerBase` 见 `call_state_listener_base.h`）。相关编译开关：`NOT_SUPPORT_MULTICALL` 由 `BUILD.gn` 的 feature `call_manager_feature_not_support_multicall` 控制（`bundle.json` 声明，默认 false）；`TELEPHONY_CUST_SUPPORT` 由 `callmanager.gni` 在 `global_parts_info.telephony_telephony_enhanced` 使能时定义（控制 `QueryCallerInfo` 的增强联系人查询）；`call_status_manager.cpp` 中另有 `AUDIO_SUPPORT`（本仓 GN 未定义，由产品侧注入）。

## Requirements

### Requirement: 单条上报状态分发
系统 SHALL 在 `CallStatusManager::HandleCallReportInfo` 中按 `CallDetailInfo` 的 `state` 分发：CALL_STATUS_ACTIVE→`ActiveHandle`、CALL_STATUS_HOLDING→`HoldingHandle`、CALL_STATUS_DIALING→`DialingHandle`、CALL_STATUS_ALERTING→`AlertHandle`、CALL_STATUS_INCOMING→`IncomingHandle`、CALL_STATUS_WAITING/DISCONNECTED/DISCONNECTING→`HandleCallReportInfoEx`；`callType` 为 TYPE_VOIP 时改走 `HandleVoipCallReportInfo`，TYPE_BLUETOOTH 先经 `HandleBluetoothCallReportInfo`；每次处理完成后调用 `HandleDsdaInfo` 及 `BluetoothCallService` 的 `GetCallState`。
#### Scenario: 来电状态分发
- **WHEN** 协议栈上报 `state` 为 CALL_STATUS_INCOMING 的蜂窝呼叫
- **THEN** 先经 `CallControlManager` 的 `AcquireIncomingLock` 再执行 `IncomingHandle`，随后 `ReleaseIncomingLock`，并以 `CallManagerHisysevent` 的 `JudgingIncomingTimeOut` 做维测计时
#### Scenario: VoIP 上报分流
- **WHEN** `info.callType` 为 TYPE_VOIP
- **THEN** 不进入蜂窝状态 switch，直接转 `HandleVoipCallReportInfo` 处理
#### Scenario: 非法状态
- **WHEN** `info.state` 为 switch 未覆盖的取值
- **THEN** 仅记录 "Invalid call state!" 日志，不做状态处理

### Requirement: 通话列表增量比对
系统 SHALL 在 `CallStatusManager::HandleCallsReportInfo` 中按 `slotId` 将新 `CallDetailsInfo` 与已存 `callDetailsInfo_` 比对：同 `index` 且 state/mpty/callType/callMode 有变化（或 state 为 CALL_STATUS_ALERTING）时调用 `HandleCallReportInfo`；新出现的 `index` 走 `HandleConnectingCallReportInfo`（存在活跃 VoIP 通话时将该呼叫的 INCOMING 改写为 CALL_STATUS_WAITING）；旧列表中消失的 `index` 置 CALL_STATUS_DISCONNECTED 后上报；末尾经 `UpdateCallDetailsInfo` 刷新缓存并剔除已断开项；`slotId` 无效时返回 CALL_ERR_INVALID_SLOT_ID。
#### Scenario: 状态变化触发处理
- **WHEN** 上报列表中某 `index` 的状态由 CALL_STATUS_DIALING 变为 CALL_STATUS_ACTIVE
- **THEN** 对该呼叫触发一次 `HandleCallReportInfo`（进入 `ActiveHandle`）
#### Scenario: 列表消失项补挂断
- **WHEN** 旧 `callDetailsInfo_` 中某 `index` 不在新上报列表中
- **THEN** 该项状态被置为 CALL_STATUS_DISCONNECTED 并按挂断流程上报
#### Scenario: 活跃 VoIP 下的新来电
- **WHEN** 已存在 CALL_STATUS_ACTIVE 的 VoIP 通话且新上报呼叫 state 为 CALL_STATUS_INCOMING
- **THEN** 该呼叫以 CALL_STATUS_WAITING 状态进入 `HandleCallReportInfo`

### Requirement: 来电建立与拦截
系统 SHALL 在 `IncomingHandle` 中先经 `RefreshOldCall` 去重（已存在则直接返回）；对 TYPE_CS/TYPE_IMS/TYPE_SATELLITE 呼叫先执行 `IncomingFilterPolicy`（转 `CallIncomingFilterManager` 的 `DoIncomingFilter`）；随后 `CreateNewCall`（CALL_DIRECTION_IN）并 `SetContactInfo`（含 `QueryCallerInfo` 联系人查询，`TELEPHONY_CUST_SUPPORT` 下对长度达 `QUERY_CONTACT_LEN` 的号码用后缀匹配增强查询）；`IsRejectCall` 判定拒绝时走 `HandleRejectCall`（`RejectCall`，拦截场景另经 `AddBlockLogAndNotification`）；`IsRingOnceCall` 时走 `HandleRingOnceCall`；否则 `AddOneCallObject`、`NotifyNewCallCreated`、`UpdateCallState`、`FilterResultsDispose`；过滤异步完成经 `CallFilterCompleteResult` 补建呼叫。
#### Scenario: 命中拒绝策略
- **WHEN** 来电命中 `ShouldRejectIncomingCall`/`ShouldBlockIncomingCall` 等拒绝判定
- **THEN** 不进入正常来电通知流程，执行 `RejectCall`，拦截场景追加 `AddBlockLogAndNotification`
#### Scenario: 增强联系人查询
- **WHEN** 已定义 `TELEPHONY_CUST_SUPPORT` 且来电号码长度不小于 `QUERY_CONTACT_LEN`
- **THEN** `QueryCallerInfo` 以号码后缀匹配 detail_info/format_phone_number 字段做增强联系人查询
#### Scenario: 过滤完成回调
- **WHEN** 来电过滤管理器异步完成后回调 `CallFilterCompleteResult`
- **THEN** 创建来电对象并依次执行 `NotifyNewCallCreated`、`UpdateCallState`、`FilterResultsDispose`

### Requirement: 拨号与通话中状态处理
系统 SHALL 由 `DialingHandle` 处理去电：`index` 大于 0 且 `UpdateDialingHandle` 命中已有对象时经 `UpdateDialingCallInfo` 刷新；否则 `CreateNewCall`（CALL_DIRECTION_OUT）、`AddOneCallObject`、`DialingProcess`、`NotifyNewCallCreated` 后 `UpdateCallState` 置 CALL_STATUS_DIALING。`ActiveHandle` 在查不到对象时依次尝试 `CreateAndSaveNewCall` 与 `RefreshDialingStateByOtherState`；`mpty` 为 1 且会议成员大于 1 时 `SetConferenceCall`（成员 `LaunchConference`），否则 `ExitConference`；随后 `UpdateCallState` 置 CALL_STATUS_ACTIVE 并允许保持通话恢复切换。`HoldingHandle` 对 `mpty` 为 1 的呼叫先 `HoldConference`，再经 `UpdateCallStateAndHandleDsdsMode` 更新。
#### Scenario: 首次拨号上报
- **WHEN** 上报 dialing 状态且 `info.index` 为 INIT_INDEX
- **THEN** 创建去电对象、置 pendingMo 标志（`SetPendingMo`），经 `DialingProcess` 与 `UpdateCallState` 进入 CALL_STATUS_DIALING
#### Scenario: 激活触发会议归组
- **WHEN** 上报 active 且 `info.mpty` 为 1、该 slotId 会议成员数大于 1
- **THEN** `SetConferenceCall` 对成员执行 `LaunchConference` 并逐个更新状态
#### Scenario: 保持状态处理
- **WHEN** 上报 holding 且呼叫 `mpty` 为 1
- **THEN** 先 `HoldConference` 再按 DSDS 模式经 `UpdateCallStateAndHandleDsdsMode` 更新状态

### Requirement: 挂断处理与自动恢复
系统 SHALL 在 `DisconnectedHandle` 中先唤醒 `timeWaitHelper_`（响一声场景）；未经 DISCONNECTING 的远端挂断先 `AcquireDisconnectedLock`；经 `RefreshCallDisconnectReason` 保存原因后 `UpdateCallState` 置 CALL_STATUS_DISCONNECTED，随后 `HandleHoldCallOrAutoAnswerCall`：`IsCanUnHold` 判定可恢复时对同 slotId 保持通话执行 `UnHoldCall`，DSDS_MODE_V3 下 `AutoAnswer`、DSDA/TDM 下 `AutoHandleForDsda`；最后 `DeleteOneCallObject` 删除对象，会议仅剩一人时置 TEL_CONFERENCE_IDLE。定义 `NOT_SUPPORT_MULTICALL` 时，`IsTwoCallBtCallAndESIM` 或 `IsTwoCallESIMCall` 场景断开后执行 `AutoAnswerSecondCall` 自动接听。`HandleDisconnectedCause` 经 `NotifyCallDestroyed` 通知观察者。
#### Scenario: 恢复保持通话
- **WHEN** 通话断开且无其它活跃/等待/拨号呼叫、存在可恢复的同 slotId 保持通话
- **THEN** 对该保持通话执行 `UnHoldCall`
#### Scenario: 不支持多通话自动接听
- **WHEN** 已定义 `NOT_SUPPORT_MULTICALL` 且 `IsTwoCallBtCallAndESIM` 或 `IsTwoCallESIMCall` 成立
- **THEN** 断开后 `AutoAnswerSecondCall` 对 `GetAutoAnswerState` 为真的来电/等待呼叫自动 `AnswerCall`
#### Scenario: 会议仅剩一人
- **WHEN** 断开后该 slotId 会议列表仅剩 1 个成员
- **THEN** 其会议状态置 TEL_CONFERENCE_IDLE 并重新上报该通话状态

### Requirement: 协议栈事件与错误处理
系统 SHALL 在 `HandleEventResultReportInfo` 中仅接受 `EVENT_REQUEST_RESULT_TYPE` 类型事件（否则返回 CALL_ERR_PHONE_TYPE_UNEXPECTED）；对处于 CALL_RUNNING_STATE_DIALING 的呼叫执行 `DealFailDial`；经 `mEventIdTransferMap_` 将 `RequestResultEventId` 映射为 `CallAbilityEventId` 后 `NotifyCallEventUpdated`：EVENT_DIAL_NO_CARRIER 附带拨号号码、EVENT_COMBINE_CALL_FAILED 触发活跃呼叫的 `HandleCombineConferenceFailEvent`、EVENT_HOLD_CALL_FAILED 复位 `needWaitHold_`。`HandleOttEventReportInfo` 经 `mOttEventIdTransferMap_` 映射 `OttCallEventId`。
#### Scenario: 无运营商拨号失败
- **WHEN** 收到 RESULT_DIAL_NO_CARRIER 事件
- **THEN** 对拨号中呼叫执行 `DealFailDial`，并以 EVENT_DIAL_NO_CARRIER 携带号码 `NotifyCallEventUpdated`
#### Scenario: 合并会议失败
- **WHEN** 收到 RESULT_COMBINE_SEND_FAILED 事件
- **THEN** 活跃通话对象执行 `HandleCombineConferenceFailEvent`
#### Scenario: 非请求结果类型
- **WHEN** `info.eventType` 不为 EVENT_REQUEST_RESULT_TYPE
- **THEN** 返回 CALL_ERR_PHONE_TYPE_UNEXPECTED

### Requirement: 多通话仲裁策略
系统 SHALL 由 `CallStatusPolicy::DialingHandlePolicy` 在同号码呼叫已存在（`IsCallExist`）时返回 CALL_ERR_CALL_ALREADY_EXISTS；由 `FilterResultsDispose` 仲裁新来电：`HasRingingMaximum` 或 `HasDialingMaximum` 超限时对该呼叫 `HangUpCall`；VoIP 全局状态为 CALL_STATE_RINGING 时 `RejectCall`；否则执行 `IncomingCallBase` 并 `NotifyNewCallCreated`。
#### Scenario: 重复号码去电
- **WHEN** 同号码呼叫对象已存在时进入 `DialingHandlePolicy`
- **THEN** 返回 CALL_ERR_CALL_ALREADY_EXISTS
#### Scenario: 通话数超限
- **WHEN** 振铃或拨号通话数达到上限且新来电进入 `FilterResultsDispose`
- **THEN** 对该来电执行 `HangUpCall`，不再进入来电通知流程
#### Scenario: 与 VoIP 振铃冲突
- **WHEN** VoIP 呼叫处于 CALL_STATE_RINGING 且蜂窝来电进入 `FilterResultsDispose`
- **THEN** 对该蜂窝来电执行 `RejectCall`

### Requirement: 状态变化监听分发
系统 SHALL 由 `CallStateListener` 维护 `CallStateListenerBase` 观察者集合 `listenerSet_`：`AddOneObserver` 幂等（已存在返回 true 不重复插入）、`RemoveOneObserver`/`RemoveAllObserver` 移除；`NewCallCreated`/`CallDestroyed`/`CallStateUpdated`/`MeeTimeStateUpdated`/`IncomingCallHungUp`/`IncomingCallActivated`/`CallEventUpdated` 在互斥锁保护下遍历集合向全部观察者分发，`callObjectPtr` 为空的入参仅记日志返回。
#### Scenario: 重复注册幂等
- **WHEN** 同一 observer 对象再次调用 `AddOneObserver`
- **THEN** 集合不重复插入且返回 true
#### Scenario: 状态变化广播
- **WHEN** `CallStateUpdated` 收到非空 `callObjectPtr` 及变化的 priorState/nextState
- **THEN** 集合内每个观察者的 `CallStateUpdated` 均被调用一次
#### Scenario: 空对象保护
- **WHEN** `NewCallCreated` 收到 nullptr
- **THEN** 仅记录错误日志，不通知任何观察者
