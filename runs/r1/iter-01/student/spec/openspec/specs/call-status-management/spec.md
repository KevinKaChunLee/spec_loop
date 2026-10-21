# call-status-management Specification

## Purpose
描述 `telephony_call_manager`（OpenHarmony v6.0 快照）中"上行呼叫状态处理与界面联动"能力的移植前现状：cellular_call 上报的呼叫事件经 `ReportCallInfoHandler` 进入 `CallStatusManager` 之后的全部分发、落位与周边联动。源码落点为 `services/call/src/` 下的 `call_status_manager.cpp`（含 `include/call_status_manager.h`，约 2500 行、94 个成员函数）、`call_status_policy.cpp`（`CallStatusPolicy` 状态分发规则）、`call_state_listener.cpp`（观察者总线 `CallStateListener` 与 `CallStateListenerBase`）、`call_request_event_handler_helper.cpp`（拨号期异步原语）、`call_connect_ability.cpp` / `call_ability_connect_callback.cpp`（通话界面 CallUIAbility 连接管理）、`call_broadcast_subscriber.cpp`（系统公共事件订阅分发），以及来电准入过滤链入口 `call_incoming_filter_manager.cpp`（`CallIncomingFilterManager::DoIncomingFilter`）。废单筛/亮屏/贴耳灭屏等来电话周边行为的观察者实现属于 `call-state-observer` 能力，本规格只定义其挂载的总线。

控制本能力行为的构建开关（逐宏 rg 核实）：
- `NOT_SUPPORT_MULTICALL`：由 `BUILD.gn` 的 `declare_args` 变量 `call_manager_feature_not_support_multicall` 定义；场点 `call_status_manager.h`（`AutoAnswerSecondCall` 声明）、`call_status_manager.cpp:1214/1243/2262`（`CallObjectManager::IsTwoCallBtCallAndESIM` / `IsTwoCallESIMCall` 判定与双 eSIM/BT 第二路自动接听）。
- `AUDIO_SUPPORT`：场点 `call_status_manager.cpp:880`（`ActiveHandle` 免提/音量）与 `1147`（`AlertHandle`）。本仓 `BUILD.gn`/`callmanager.gni` 未定义该宏，默认构建下两处分支恒不编译。
- `TELEPHONY_CUST_SUPPORT`：由 `callmanager.gni` 在部件 `telephony_telephony_enhanced` 存在时定义；场点 `call_status_manager.cpp:702`（`QueryCallerInfo` 长号码（≥`QUERY_CONTACT_LEN`=7）走 contacts 后缀匹配增强查询分支）。

异步任务原语的真实形态：模块内大量使用 `ffrt::submit` 做非阻塞 offload（联系人查询、归属地/黄页更新、防诈启动、通话记录入库）；拨号标志恢复则使用 `AppExecFwk::EventHandler`（`EventRunner` + `PostTask` 延时 3000ms），不是 ffrt。

## Requirements

### Requirement: 单笔呼叫状态上报分发
系统 SHALL 由 `CallStatusManager::HandleCallReportInfo` 按 `CallDetailInfo.state` 将单笔状态上报路由到对应处理函数：`CALL_STATUS_ACTIVE`→`ActiveHandle`、`CALL_STATUS_HOLDING`→`HoldingHandle`、`CALL_STATUS_DIALING`→`DialingHandle`、`CALL_STATUS_ALERTING`→`AlertHandle`、`CALL_STATUS_INCOMING`→`IncomingHandle`（前后包夹 `CallControlManager::AcquireIncomingLock`/`ReleaseIncomingLock`）、`CALL_STATUS_WAITING`/`CALL_STATUS_DISCONNECTED`/`CALL_STATUS_DISCONNECTING`→`HandleCallReportInfoEx`，非法状态仅记日志；`TYPE_VOIP` 走 `HandleVoipCallReportInfo`，`TYPE_BLUETOOTH` 先经 `HandleBluetoothCallReportInfo` 预处理；每次处理结束后 SHALL 统一执行 `HandleDsdaInfo` 与 `BluetoothCallService::GetCallState`。

#### Scenario: 拨号/来电维测计时
- **WHEN** 状态为 `CALL_STATUS_DIALING` 或 `CALL_STATUS_INCOMING` 的上报被处理完成
- **THEN** 分别触发 `FinishAsyncTrace`（"DialCall"/"InComingCall"）并调用 `CallManagerHisysevent::JudgingDialTimeOut`/`JudgingIncomingTimeOut` 记录超时判定

#### Scenario: WAITING 状态复用来电链
- **WHEN** `HandleCallReportInfoEx` 收到 `CALL_STATUS_WAITING`
- **THEN** 走 `WaitingHandle`，即包夹来电锁的 `IncomingHandle`

#### Scenario: 断链原因上报
- **WHEN** `HandleDisconnectedCause` 将 `DisconnectedDetails` 交给 `CallControlManager::NotifyCallDestroyed` 且返回失败
- **THEN** 返回 `CALL_ERR_PHONE_CALLSTATE_NOTIFY_FAILED`

### Requirement: 呼叫状态集合对账
系统 SHALL 由 `HandleCallsReportInfo` 将整呼叫列表（`CallDetailsInfo.callVec`）与按 slot 缓存的 `callDetailsInfo_` 对账，并只能为合法 slotId 分发。

#### Scenario: 非法 slotId
- **WHEN** `info.slotId` 未通过 `CallNumberUtils::IsValidSlotId`
- **THEN** 返回 `CALL_ERR_INVALID_SLOT_ID`，不做任何分发

#### Scenario: 同 index 状态变化分发
- **WHEN** 新列表中某条目与缓存里同 index 条目的 `state`/`mpty`/`callType`/`callMode` 任一发生变化，或新状态为 `CALL_STATUS_ALERTING`
- **THEN** 对该条目单发 `HandleCallReportInfo`

#### Scenario: 新增条目与 meetime 冲突降级
- **WHEN** 新列表条目未命中缓存（或该 slot 缓存为空），经 `HandleConnectingCallReportInfo` 处理
- **THEN** 若 `CallObjectManager::IsVoipCallExist(CALL_STATUS_ACTIVE)` 为真且新条目状态为 `CALL_STATUS_INCOMING`，先降级为 `CALL_STATUS_WAITING` 再 `HandleCallReportInfo`，否则直接分发

#### Scenario: 消失的通话补断开
- **WHEN** 缓存中某条目的 index 在新列表中不存在
- **THEN** 该条目 `state` 被置为 `CALL_STATUS_DISCONNECTED` 后补发 `HandleCallReportInfo`

#### Scenario: 缓存更新
- **WHEN** 对账结束，`UpdateCallDetailsInfo` 以新列表整表替换该 slot 缓存
- **THEN** 从缓存剔除 `CALL_STATUS_DISCONNECTED` 行；若缓存因此为空则连带清空 `tmpCallDetailsInfo_` 同 slot 缓存

#### Scenario: DSDA 保持能力收紧
- **WHEN** 处理结束后 `HandleDsdaInfo` 查得 `CoreServiceClient::GetDsdsMode` 为 `DSDS_MODE_V5_DSDA`/`DSDS_MODE_V5_TDM`，且 `CallRequestProcess::IsExistCallOtherSlot` 显示其它 slot 仍有通话（noOtherCall=false），而其他 slot 通话数大于 `CALL_NUMBER`(2)
- **THEN** 对保持中通话执行 `SetCanUnHoldState(false)`

### Requirement: 请求失败与事件上报
系统 SHALL 由 `HandleEventResultReportInfo` 将 cellular_call 的 `EVENT_REQUEST_RESULT_TYPE` 请求失败事件按 `mEventIdTransferMap_` 映射为 `CallAbilityEventId` 并经 `CallControlManager::NotifyCallEventUpdated` 上报；`HandleOttEventReportInfo` 将 `OTT_CALL_EVENT_FUNCTION_UNSUPPORTED` 映射为 `EVENT_OTT_FUNCTION_UNSUPPORTED`。

#### Scenario: 拨号失败兜底
- **WHEN** 收到任一请求失败事件且存在 `CALL_RUNNING_STATE_DIALING` 的通话
- **THEN** 先对该通话执行 `DealFailDial`

#### Scenario: 无运营商拨号失败
- **WHEN** 事件为 `RESULT_DIAL_NO_CARRIER`（映射 `EVENT_DIAL_NO_CARRIER`）
- **THEN** 从 `CallControlManager::GetDialParaInfo` 取号码（校验 `kMaxNumberLen`）填入 `CallEventInfo.phoneNum` 后上报

#### Scenario: 合会议失败联动
- **WHEN** 事件为 `RESULT_COMBINE_SEND_FAILED`
- **THEN** 映射 `EVENT_COMBINE_CALL_FAILED`，并对活动通话执行 `HandleCombineConferenceFailEvent` 后上报

#### Scenario: 保持失败复位
- **WHEN** 事件为 `RESULT_HOLD_SEND_FAILED`
- **THEN** 映射 `EVENT_HOLD_CALL_FAILED` 上报，并将 `needWaitHold_` 置 false

#### Scenario: 未知/OTT 事件
- **WHEN** 事件 id 不在映射表（仅记日志），或 OTT 事件携带 bundle 名（校验长度后拷入 `CallEventInfo.bundleName`）
- **THEN** 映射表外的 cellular 事件不上报；OTT 的 `OTT_CALL_EVENT_FUNCTION_UNSUPPORTED` 正常上报

### Requirement: 来电准入过滤
系统 SHALL 在 CS/IMS/SATELLITE 类型来电建链前，由 `CallStatusManager::IncomingFilterPolicy` 调用 `CallIncomingFilterManager::DoIncomingFilter` 执行准入校验，非 `TELEPHONY_SUCCESS` 时来电直接终止。

#### Scenario: EDM 禁拨策略
- **WHEN** `CallControlManager::IsIncomingEnable`（EDM 禁拨策略）对来话号码返回 false
- **THEN** 返回 `TELEPHONY_ERR_POLICY_DISABLED`，不创建通话对象

#### Scenario: 紧急号码放行
- **WHEN** `CellularCallConnection::IsEmergencyPhoneNumber` 判定来话号码为紧急号码
- **THEN** 返回 `TELEPHONY_SUCCESS` 继续正常来电流程

### Requirement: 来电拒接判定链
系统 SHALL 在来电对象创建后、入表前，由 `CallStatusManager::IsRejectCall` 依次执行系统级拒接（`ShouldRejectIncomingCall`）、骚扰拦截（`ShouldBlockIncomingCall`）与免打扰静默标记（`IsFocusModeOpen`）三级判定；命中拒接时经 `HandleRejectCall` 完成状态落位与日志通知。

#### Scenario: 紧急通话在通时拒接
- **WHEN** `HasEmergencyCall` 报告存在紧急通话
- **THEN** 判定拒接，`block=false`，行为事件 `CALL_INCOMING_REJECT_BY_SYSTEM` 以 `REJECT_BY_OOBE` 记录

#### Scenario: 开机向导未完成拒接
- **WHEN** `GetDevProvisioned()` 非 `DEVICE_PROVISION_VALID`，或设置项 `user_setup_complete` 查询成功且取值为 "0"/空串
- **THEN** 判定拒接，`block=false`；若 `OsAccountManager::QueryActiveOsAccountIds` 为空则本分支不拒接

#### Scenario: VoIP 振铃冲突拒接
- **WHEN** `CallControlManager::GetVoIPCallState` 返回 `CALL_STATE_RINGING`
- **THEN** 判定拒接，`block=false`

#### Scenario: 骚扰拦截判定
- **WHEN** 非紧急号码，`SpamCallAdapter::DetectSpamCall` 启动检测且 `WaitForDetectResult` 在超时前返回
- **THEN** `GetParseResult` 解析结果写回通话对象（`SetNumberMarkInfo`/`SetBlockReason`/`SetDetectDetails` + extraParams "blockReason"）；`isBlock` 为真才判定拦截，`block=true` 以 `REJECT_BY_NUM_BLOCK` 记录；检测启动时间记入 `detectStartTime`

#### Scenario: 免打扰静默不拒接
- **WHEN** 设置项 `focus_mode_enable` 为 "1" 且 `Notification::NotificationHelper::IsNeedSilentInDoNotDisturbMode` 返回 0
- **THEN** 不拒接，但向通话 extraParams 写入 `IsNeedSilentInDoNotDisturbMode=1`，行为事件以 `REJECT_IN_FOCUSMODE` 记录

#### Scenario: 拒接落位
- **WHEN** `IsRejectCall` 返回 true
- **THEN** `HandleRejectCall` 将状态置 `CALL_STATUS_INCOMING`、执行 `call->RejectCall`；`block=true` 走 `AddBlockLogAndNotification`（置 `CALL_ANSWER_BLOCKED`），否则走 `AddCallLogAndNotification`（置 `CALL_ANSWER_MISSED`）

### Requirement: 来话建链主链
系统 SHALL 由 `IncomingHandle` 按固定次序完成来话处理：重置 `detectStartTime` → `RefreshOldCall` 去重 → 准入过滤 → `CreateNewCall`（`CALL_DIRECTION_IN`）→ 同号同时来电判定 → `SetContactInfo` → 拒接判定 → 响一次判定 → 视频高级安全模式 → `AddOneCallObject` → `StartInComingCallMotionRecognition` → `NotifyNewCallCreated` → `UpdateCallState` → `FilterResultsDispose` → `StartFlashRemind`。

#### Scenario: 已存在旧来话去重
- **WHEN** `RefreshOldCall` 以 index/slotId/callType 命中既有来话
- **THEN** 仅按需 `RefreshCallIfNecessary`/`UpdateCallState` 刷新旧对象并置 `isExistedOldCall`，不重复建链；此前如存在 index-0 拨号占位通话，先对其 `DealFailDial`

#### Scenario: 正常来电入链
- **WHEN** 全部判定通过
- **THEN** 通话对象入全局表，状态经 `UpdateCallState` 落位 `CALL_STATUS_INCOMING`，随后交 `CallStatusPolicy::FilterResultsDispose` 处置并触发 `CallControlManager::StartFlashRemind`（来电闪光）

#### Scenario: 拒接/响一次分支短路
- **WHEN** `IsRejectCall` 或（非 VOIP/蓝牙且）`IsRingOnceCall` 判定命中
- **THEN** 分别转入 `HandleRejectCall`/`HandleRingOnceCall`，通话对象不入表、不触发后续通知链

### Requirement: CallStatusPolicy 状态分发规则
系统 SHALL 由 `CallStatusPolicy::FilterResultsDispose` 对已建链来话做终端处置；`DialingHandlePolicy` 对去电先行去重。

#### Scenario: 振铃/拨号数量超限挂断
- **WHEN** `CallObjectManager::HasRingingMaximum()` 或 `HasDialingMaximum()` 为真
- **THEN** 对该来话执行 `call->HangUpCall`，不进入来电通知链

#### Scenario: VoIP 振铃冲突拒绝
- **WHEN** `GetVoIPCallState` 为 `CALL_STATE_RINGING`
- **THEN** 对该来话执行 `call->RejectCall`

#### Scenario: 正常来电受理
- **WHEN** 无超限且无 VoIP 冲突
- **THEN** 执行 `call->IncomingCallBase`（进入振铃/音频链）并再次 `NotifyNewCallCreated`

#### Scenario: 去电重复校验
- **WHEN** `DialingHandlePolicy` 检出同号码通话已存在（`IsCallExist`）
- **THEN** 返回 `CALL_ERR_CALL_ALREADY_EXISTS`

### Requirement: 响一声拦截
系统 SHALL 由 `IsRingOnceCall` 在骚扰检测窗内等待一小段时间（`TimeWaitHelper`，窗口为 `WAIT_TIME_THREE_SECOND`(3000ms) 减去已耗检测时长），以识别"响一声即挂"的来电；命中时由 `HandleRingOnceCall` 直接记为未接。

#### Scenario: 免检场景
- **WHEN** 来电为黄页标记（`MARK_TYPE_YELLOW_PAGE`）或命中联系人（`contactInfo.name` 非空），或设置项 `spamshield_sim<N>_phone_switch_ring_once` 非 "1"
- **THEN** 判定非响一声，走正常来电流程

#### Scenario: 等待窗内对端挂断
- **WHEN** 开关开启且 `TimeWaitHelper::WaitForResult` 在等待窗内被 `DisconnectedHandle` 的 `NotifyAll` 唤醒返回 true
- **THEN** `HandleRingOnceCall` 将状态置 `CALL_STATUS_INCOMING` 并直接 `AddCallLogAndNotification`（记未接、不发通知）；等待窗结束 helper 释放

#### Scenario: 等待超时
- **WHEN** 等待窗内未发生挂断，`WaitForResult` 超时返回
- **THEN** 判定非响一声（"is not ring once"），helper 释放，通话走正常流程

### Requirement: 同号同时来电与 eSIM 归属修正
系统 SHALL 由 `IsFromTheSameNumberAtTheSameTime`（一号双终端场景）识别同号同瞬来电并触发 `ModifyEsimType` 修正 eSIM 类型设置。

#### Scenario: 判定条件全命中
- **WHEN** 新来话号码与既有通话（`GetOneCallObject(phoneNumber)`，号码比对前先剥离后拨段）相同、两 callId 差绝对值为 1、旧通话状态为 `CALL_STATUS_INCOMING`、两次 `callCreateTime` 差 ≤ 10000ms
- **THEN** 判定为同号同时来电

#### Scenario: eSIM 类型修正
- **WHEN** 判定命中且设置项 `key_esim_card_type` 查询成功、取值非 "1" 且非空
- **THEN** `SettingsDataShareHelper::Update` 将其更新为 "1"，并逐位检查 `key_manually_set_net`（不足 3 位不处理），未置位时补写 `key_smartoff_network_bluetooth_connection`/`key_smartoff_network_not_wear`/`key_smartoff_network_sleep_mode`

### Requirement: 来电联系人信息与高级安全模式
系统 SHALL 在来电建链时以 `SetContactInfo` 异步（`ffrt::submit`）填充联系人信息：经 `QueryCallerInfo`→`CallDataBaseHelper::Query(ContactInfo…)` 用 predicates（`type_id=5`、`is_deleted=0`、`detail_info=号码`；`TELEPHONY_CUST_SUPPORT` 下号码长度 ≥ `QUERY_CONTACT_LEN`(7) 时改为对 `detail_info`/`format_phone_number` 的 ends-with 后缀匹配并调用 `QueryContactInfoEnhanced`）查询 contacts 数据库，随后 `SetCallerInfo`，并联动 `CallVoiceAssistantManager::UpdateContactInfo`、`DistributedCommunicationManager::ProcessCallInfo(NAME)` 与视频彩振路径（`NeedPlayVideoRing`→extraParams "VideoRingPath"）。

#### Scenario: 联系人命中与否
- **WHEN** `IsContactPhoneNum` 复用同查询，contacts 返回的 `detail_info/display_name` 非空（`contactInfo.name` 长度 ≥1）
- **THEN** 判定为联系人号码；查询失败仅记日志，`isQueryComplete` 保持初始 true

#### Scenario: 蓝牙来电联系人
- **WHEN** 来电为 `TYPE_BLUETOOTH` 且 `BluetoothCallConnection::GetHfpContactName` 返回非空
- **THEN** 直接以 HFP 联系人名填充 `SetCallerInfo` 与 extraParams "BtCallContactName"，不再查询数据库

#### Scenario: 视频来电高级安全模式
- **WHEN** IMS 视频来电在通话对象创建前后经 `HandleVideoCallInAdvsecMode` 判定：号码非受信（`IsTrustedNumber`：标记非黄页/企业且非联系人）且系统参数 `ohos.boot.advsecmode.state`（`ADVSECMODE_STATE`）为 true
- **THEN** 对通话执行 `SetForcedReportVoiceCall(true)`

### Requirement: 去电拨号与振铃处理
系统 SHALL 由 `DialingHandle` 完成去电状态落位、由 `AlertHandle` 完成对端振铃状态落位。

#### Scenario: 既有通话的拨号态更新
- **WHEN** 上报 index>0 且 `UpdateDialingHandle` 命中既有对象（蓝牙来话另走 `BtCallDialingHandle`；命中分卡 index 对象时依 `IsDistributeCallSourceStatus` 判分布式拨号）
- **THEN** `UpdateDialingCallInfo` 刷新既有通话（index-0 占位通话保留原拨号码 `oriNum`，刷新后 `ClearPendingState`），不新建对象

#### Scenario: 新建去电
- **WHEN** 无既有对象，`CreateNewCall(CALL_DIRECTION_OUT)` 成功
- **THEN** 依 `IsDistributeCallSourceStatus` 写入 extraParams "isDistributedDeviceDialing"；`IsDcCallConneceted` 为真时补 `SetContactInfo`；对象入表；index==`INIT_INDEX`(0) 时置 `SetPendingMo(true, callId)`、`SetPhoneOrWatchDial(WATCH_DIAL)`、`SetBtCallDialByPhone(false)` 并 `StartOutGoingCallMotionRecognition`；随后 `RestoreDialingFlag(false)`、`RemoveEventHandlerTask`、`call->DialingProcess`、`NotifyNewCallCreated`、`MyLocationEngine::StartEccService`、`UpdateCallState(CALL_STATUS_DIALING)`

#### Scenario: 振铃态落位
- **WHEN** `AlertHandle` 收到 `CALL_STATUS_ALERTING` 上报，对象缺失且 `IsDcCallConneceted` 为真时按 `CALL_DIRECTION_OUT` 补建，否则经 `RefreshDialingStateByOtherState`（以临时 DIALING 信息重跑 `DialingHandle`）补救
- **THEN** `UpdateCallState(CALL_STATUS_ALERTING)`；`AUDIO_SUPPORT` 分支（默认不编译）会执行免提/去静默/音量恢复

### Requirement: 激活态与会议合并
系统 SHALL 由 `ActiveHandle` 完成通话激活落位与多路会议合并判定。

#### Scenario: 对象缺失补救
- **WHEN** 以 index/slotId/callType 找不到对象
- **THEN** `IsDcCallConneceted` 为真时 `CreateAndSaveNewCall(CALL_DIRECTION_UNKNOW)` 补建（并 `ffrt::submit` 触发 `YellowPageAndMarkUpdate`），否则经 `RefreshDialingStateByOtherState` 补救；均失败返回 `TELEPHONY_ERR_LOCAL_PTR_NULL`

#### Scenario: 会议合并与退出
- **WHEN** 上报 `mpty==1` 且 `GetConferenceCallList`（按 `tmpCallDetailsInfo_` 中 mpty==1 的条目聚合）返回多于 1 个对象
- **THEN** `SetConferenceCall` 对每路非 `TEL_CONFERENCE_ACTIVE` 通话执行 `LaunchConference` + `UpdateCallState`；否则尝试 `call->ExitConference`

#### Scenario: 激活落位与音频恢复
- **WHEN** `UpdateCallState(CALL_STATUS_ACTIVE)` 成功
- **THEN** 保持中通话 `SetCanSwitchCallState(true)`；`AUDIO_SUPPORT` 分支（默认不编译）做免提/音量恢复；随后进入防诈启动判定（见防诈需求）

#### Scenario: 原始视频状态记录
- **WHEN** 前态为 ALERTING/INCOMING/WAITING 且 `GetOriginalCallType` 与当前视频状态不一致
- **THEN** `SetOriginalCallType` 改记当前视频状态；前态为 ACTIVE/HOLDING 时按位或合并记录（升级/降级场景）

### Requirement: 保持与断开处理
系统 SHALL 由 `HoldingHandle`/`DisconnectingHandle`/`DisconnectedHandle` 完成保持、断开中、已断开的状态落位及善后联动。

#### Scenario: 保持态落位
- **WHEN** `HoldingHandle` 收到 `CALL_STATUS_HOLDING`
- **THEN** `StopAntiFraudDetect`；`mpty==1` 时 `HoldConference`；`UpdateCallStateAndHandleDsdsMode` 落位 HOLDING 并仅在 `GetDsdsMode` 为 `DSDS_MODE_V5_DSDA`/`DSDS_MODE_V5_TDM` 时做后续自动处理（`needWaitHold_` 且无活动通话→`HandleDialWhenHolding`，否则 `AutoHandleForDsda`）

#### Scenario: 断开中落位
- **WHEN** `DisconnectingHandle` 收到 `CALL_STATUS_DISCONNECTING`
- **THEN** `StopAntiFraudDetect`、`SetOriginalCallTypeForDisconnectState`、`UpdateCallState(CALL_STATUS_DISCONNECTING)`、`StopFlashRemind`

#### Scenario: 已断开善后
- **WHEN** `DisconnectedHandle` 处理 `CALL_STATUS_DISCONNECTED`（若有 `TimeWaitHelper` 先 `NotifyAll`）
- **THEN** 前态非 DISCONNECTING 时先 `AcquireDisconnectedLock`；`StopAntiFraudDetect`、`RefreshCallDisconnectReason`、`ClearPendingState`；`call->ExitConference` 后 `UpdateCallState(DISCONNECTED)` 并 `MyLocationEngine::StopEccService`；再经 `HandleHoldCallOrAutoAnswerCall` 恢复保持通话或自动接听；会议仅剩一路时该路 `SetTelConferenceState(TEL_CONFERENCE_IDLE)` 并重发状态；通话总数归零时 `RestoreSuperPrivacyMode`；`NOT_SUPPORT_MULTICALL` 分支在双路 BT+eSIM 或双路 eSIM 场景 `AutoAnswerSecondCall`；最后 `StopCallMotionRecognition(DISCONNECTED)` 与 `StopFlashRemind`

#### Scenario: 断链原因归位
- **WHEN** `RefreshCallDisconnectReason` 依 `RilDisconnectedReason` 分类
- **THEN** CS 通话 `DISCONNECTED_REASON_CS_CALL_ANSWERED_ELSEWHER` 置 `CALL_ANSWERED_ELSEWHER`；`DISCONNECTED_REASON_ANSWERED_ELSEWHER` 在 sink 角色或 message 含 "elsewhere" 时同样置位；`DISCONNECTED_REASON_NORMAL` 时向 extraParams 写 `disconnectedReason=CALL_DISCONNECTED_BY_REMOTE`

### Requirement: 挂断后恢复保持与自动接听
系统 SHALL 由 `HandleHoldCallOrAutoAnswerCall` 在通话结束后按 DSDS 模式恢复保持通话或自动接听第二路；`IsCanUnHold` 描述可恢复条件（活动/等待/接听/去电/振铃数全为 0 且子通话数 ≤1）。

#### Scenario: 释放并恢复保持通话
- **WHEN** 通话结束时前态非 HOLD、非 ACTIVE、前状态为 DISCONNECTING，且存在保持通话、`canUnHold` 与 `GetCanUnHoldState` 均真、slot 相同
- **THEN** 对保持通话执行 `UnHoldCall`

#### Scenario: DSDS_MODE_V3 自动接听
- **WHEN** 通话结束后 `GetDsdsMode`==`DSDS_MODE_V3`，活动/等待/保持/拨号/振铃数全 0 且存在置了 `GetAutoAnswerState` 的振铃通话
- **THEN** 对其 `AnswerCall(GetAnswerVideoState)`

#### Scenario: DSDA/TDM 自动处理
- **WHEN** 模式为 `DSDS_MODE_V5_DSDA`/`DSDS_MODE_V5_TDM`
- **THEN** `AutoHandleForDsda`：视频振铃通话走 `AutoAnswerForVideoCall`；无去电/振铃/活动通话的语音振铃通话走 `AutoAnswerForVoiceCall`（音频状态已通报后 `AnswerCall`）；随后 `AutoUnHoldForDsda` 对其它 slot 满足条件（HOLDING、可恢复、前状态为 DISCONNECTING 或 `!canSwitchCallState && currentCallNum==2`）的通话 `UnHoldCall`，并在剩余两路时对保持通话 `SetCanUnHoldState(true)`

#### Scenario: NOT_SUPPORT_MULTICALL 二次自动接听
- **WHEN** 宏 `NOT_SUPPORT_MULTICALL` 生效且挂断前为 BT+eSIM 双路或双路 eSIM（`IsTwoCallBtCallAndESIM`/`IsTwoCallESIMCall`）
- **THEN** `AutoAnswerSecondCall` 对剩余 INCOMING/WAITING 且 `GetAutoAnswerState` 为真的第一路通话执行 `CallControlManager::AnswerCall`

### Requirement: 状态统一下发与对象刷新
系统 SHALL 由 `UpdateCallState` 统一完成状态落位与上报，`RefreshCallIfNecessary` 处理 callType 变化时的对象迁移，`SetVideoCallState` 联动视频状态缓存。

#### Scenario: 状态落位失败分支
- **WHEN** `call->SetTelCallState` 返回既非成功也非 `CALL_ERR_NOT_NEW_STATE`，或 `NotifyCallStateUpdated` 失败
- **THEN** 分别返回 `TELEPHONY_ERR_LOCAL_PTR_NULL`；上报失败且目标态为 INCOMING 时记 `WriteIncomingCallFaultEvent` 并返回 `CALL_ERR_PHONE_CALLSTATE_NOTIFY_FAILED`；satellite 通话另先经 `SatelliteCallControl::HandleSatelliteCallStateUpdate`、接听超时经 `JudgingAnswerTimeOut`

#### Scenario: callType 变化对象迁移
- **WHEN** `RefreshCallIfNecessary` 中上报 callType 与对象 callType 不一致（IMS 先同步视频状态并 `InitVideoCall`、crsType）
- **THEN** 以 `CreateNewCall` 新建对象并整体迁移属性（运行态、会议态、各时间戳、静音、号码归属地、黄页标记），删除旧对象并继承 callId 与前状态

#### Scenario: 视频状态联动
- **WHEN** slot 级 `priorVideoState_` 与当前视频状态不一致
- **THEN** `AudioControlManager::VideoStateUpdated` 通报并更新缓存；通话断开时该 slot 缓存复位 `TYPE_VOICE`；VOIP 通话不参与

### Requirement: 防诈检测状态管理
系统 SHALL 由 `SetupAntiFraudService`/`StopAntiFraudDetect`/`TriggerAntiFraud`/`HandleCeliaCall`/`UpdateAntiFraudState` 管理 active 防诈检测实例（`antiFraudSlotId_`/`antiFraudIndex_`，`ffrt::mutex` 保护）。

#### Scenario: 启动判定
- **WHEN** `ActiveHandle` 中系统参数 `const.telephony.antifraud.supported`（`ANTIFRAUD_FEATURE`）为 true，且处于主用户空间（活动账号首项 `MAIN_USER_SPACE`=100）、号码标记非 `MARK_TYPE_FRAUD`/`MARK_TYPE_YELLOW_PAGE`/`MARK_TYPE_ENTERPRISE`、非联系人、`AntiFraudService::IsAntiFraudSwitchOn` 为真、slotId 非 -1 且无进行中的检测
- **THEN** 记录 slot/index 并 `ffrt::submit` 执行 `AntiFraudService::StartAntiFraudService`；失败则复位 -1

#### Scenario: 挂断停止
- **WHEN** HOLDING/DISCONNECTING/DISCONNECTED 处理中 `StopAntiFraudDetect` 命中当前 slot/index
- **THEN** `StopAntiFraudService`、复位记录、extraParams 写 `antiFraudState=ANTIFRAUD_STATE_FINISHED`

#### Scenario: 检测结果触发
- **WHEN** `TriggerAntiFraud` 收到 `ANTIFRAUD_STATE_RISK`/`ANTIFRAUD_STATE_FINISHED`
- **THEN** 从 `callDetailsInfo_` 定位通话、复位 slot/index 记录、extraParams 更新 antiFraudState；活动通话随后重发 `UpdateCallState(ACTIVE)`

#### Scenario: Celia 通话抢占
- **WHEN** `HandleCeliaCall` 命中防诈 slot/index
- **THEN** 停止防诈并复位，通话若为 ACTIVE 则重发状态

### Requirement: VoIP 上行处理族
系统 SHALL 由 `HandleVoipCallReportInfo` 按 VOIP 状态路由：ACTIVE→`ActiveVoipCallHandle`、INCOMING→`IncomingVoipCallHandle`、DISCONNECTED→`DisconnectedVoipCallHandle`、DIALING→`OutgoingVoipCallHandle`、ANSWERED→`AnsweredVoipCallHandle`、DISCONNECTING→`DisconnectingVoipCallHandle`。

#### Scenario: 来电
- **WHEN** voipCallId/bundleName/uid 三元组已存在对应对象
- **THEN** 返回成功不重复建链；否则 `CreateNewCall`（入向）、入表、`NotifyNewCallCreated`、`UpdateCallState`

#### Scenario: 去电与属性同步
- **WHEN** 三元组命中既有对象
- **THEN** 差异时 `SetVideoStateType`（callMode）并 `VoIPCall::UpdateCallAttributeInfo`，再 `UpdateCallState`；未命中则按出向新建并落位 DIALING

#### Scenario: 已接/断开中/已断开
- **WHEN** 状态分别为 ANSWERED/DISCONNECTING/DISCONNECTED
- **THEN** ANSWERED 经 `NotifyCallStateUpdated(INCOMING→ANSWERED)` 上报；DISCONNECTING 落位状态；DISCONNECTED 落位后 `DeleteOneCallObject`

#### Scenario: VoIP 静音事件
- **WHEN** `HandleVoipEventReportInfo` 收到 `VOIP_CALL_EVENT_MUTED`/`VOIP_CALL_EVENT_UNMUTED`
- **THEN** 分别 `SetMicPhoneState(true)`/`(false)`；UNMUTED 且 `AudioProxy::GetPreferredOutputAudioDevice` 命中听筒时 `SetCurrentAudioDevice`；随后 `AudioDeviceManager::ReportAudioDeviceInfo`；仅 ACTIVE/DIALING 通话接受事件

### Requirement: 蓝牙通话上行预处理
系统 SHALL 由 `HandleBluetoothCallReportInfo` 在常规分发前预处理 BT 状态上报：WAITING/INCOMING 不处理；index>0 时按 index+slotId+callType 查找（先查 index-0 的 WATCH_DIAL 对象执行 `BtCallDialingHandleFirst`），找不到才 `CreateNewCall(CALL_DIRECTION_OUT)` 并 `NotifyNewCallCreated`。

#### Scenario: 手表侧首报
- **WHEN** BT 通话 DIALING/ALERTING 上报且无既有对象
- **THEN** 新建出向 BT 通话对象（携带 `BluetoothCallConnection::GetMacAddress`）并入表、通报

#### Scenario: 手表侧对象回退
- **WHEN** 命中 index-0 的 WATCH_DIAL 对象后再次收到 ALERTING
- **THEN** `UpdateDialingCallInfo` 刷新，且对象状态为 ALERTING 时回退为 DIALING

#### Scenario: 手机侧拨号标识
- **WHEN** `BtCallDialingHandle` 找不到 index-0 对象但命中分卡 index 对象
- **THEN** 标记 `PHONE_DIAL` 且 `SetBtCallDialByPhone(true)`（extraParams "isBtCallDialByPhone"）

### Requirement: 分布式协同判定
系统 SHALL 以设置项 `distributed_modem_state`（`SettingsDataShareHelper::SETTINGS_DATASHARE_URI`）为准提供两个分布式协同谓词，并在 Active/Alert/Holding 对象缺失时按 `CALL_DIRECTION_UNKNOW` 补建对象。

#### Scenario: 通路在连判定
- **WHEN** `IsDcCallConneceted` 查询到该值为 "1_sink" 或 "1_source"
- **THEN** 视为分布式调制解调通路在连，允许补建未知方向通话对象、去电补联系人

#### Scenario: 源端判定
- **WHEN** `IsDistributeCallSourceStatus` 查询到 "1_source"
- **THEN** 视为本端为分布式拨号源，`SetDistributedDeviceDialing` 写入 extraParams "isDistributedDeviceDialing"="true"

### Requirement: 动作识别订阅联动
系统 SHALL 由 `IsCallMotionRecognitionEnable` 读设置项（`USER_SETTINGSDATA_<userId>?Proxy=true` 下 `QUERY_MOTION_PICKUP_REDUCE_KEY`/`QUERY_MOTION_FLIP_MUTE_KEY`/`QUERY_MOTION_CLOSE_TO_EAR_KEY` 为 "1"），并在来电时订阅、状态切换时退订动作传感器。

#### Scenario: 来电订阅前提
- **WHEN** `StartInComingCallMotionRecognition` 且已存在拨号/活动/保持的载波通话
- **THEN** 不订阅；否则任一开关开启时 `Rosen::LoadMotionSensor` 成功后按开关分别 `MotionRecogntion::SubscribePickupSensor`/`SubscribeFlipSensor`/`SubscribeCloseToEarSensor`

#### Scenario: 去电订阅
- **WHEN** index==0 的手表侧新去电且贴耳速接开关开启
- **THEN** `StartOutGoingCallMotionRecognition` 仅订阅贴耳传感器

#### Scenario: 状态切换退订
- **WHEN** 通话转 ACTIVE（退订 pickup/flip）或转 DISCONNECTED 且已无蜂窝通话（退订 pickup/flip/贴耳并 `Rosen::UnloadMotionSensor`）
- **THEN** 对应传感器退订；其余状态不动

### Requirement: 开机向导状态缓存与观察
系统 SHALL 以静态 `deviceProvisioned_` 缓存 `device_provisioned` 设置项（`DEVICE_PROVISION_UNDEF`/-1、`DEVICE_PROVISION_INVALID`/0、`DEVICE_PROVISION_VALID`/1），并由静态 `OOBEStatusObserver` 监听变更。

#### Scenario: 懒加载首读
- **WHEN** `GetDevProvisioned` 首次调用（缓存为 UNDEF）
- **THEN** `UpdateDevProvisioned` 经 `SettingsDataShareHelper::Query` 读取：值为 "0" 或空→INVALID，"1"→VALID，其余保持未决

#### Scenario: 变更监听
- **WHEN** `RegisterObserver` 以 `SETTINGS_DATASHARE_URI + "&key=device_provisioned"` 注册 `OOBEStatusObserver` 成功后设置项变化
- **THEN** `OOBEStatusObserver::OnChange` 触发 `UpdateDevProvisioned` 刷新缓存（注册失败仅记日志；`UpdateDevProvisioned` 在 `COMMON_EVENT_DATA_SHARE_READY` 之后由 `CallStatusManager::RegisterObserver` 挂载）

### Requirement: CallStateListener 观察者总线
系统 SHALL 以 `CallStateListener`（`std::set<std::shared_ptr<CallStateListenerBase>>` + `std::mutex`）作为状态变化广播总线，将 8 类回调（`NewCallCreated`/`CallDestroyed`/`CallStateUpdated`/`MeeTimeStateUpdated`/`IncomingCallHungUp`/`IncomingCallActivated`/`CallEventUpdated`）逐一转发给全部已注册观察者。

#### Scenario: 注册与去重
- **WHEN** `AddOneObserver` 收到已注册观察者或 `RemoveOneObserver`/`RemoveAllObserver` 操作
- **THEN** 重复注册幂等返回 true；null 观察者拒绝返回 false；移除即时生效

#### Scenario: 固定观察者阵容
- **WHEN** `CallControlManager` 初始化总线
- **THEN** 依次注册 `CallAbilityReportProxy`、`CallStateReportProxy`、`AudioControlManager`、`RejectCallSms`（hangUpSmsPtr）、`MissedCallNotification`、`IncomingCallWakeup`、`CallRecordsManager`、`DistributedCommunicationManager`、`InteroperableCommunicationManager`、`CallVoiceAssistantManager`（观察者实现分属其他能力规格）

### Requirement: CallRequestEventHandlerHelper 拨号异步原语
系统 SHALL 由 `CallRequestEventHandlerHelper`（`AppExecFwk::EventRunner`("handler_restore_dialing_flag") + `AppExecFwk::EventHandler` 的 `PostTask`/`RemoveTask`，非 ffrt）提供拨号标志的延时恢复与挂起状态对（`pendingMo_`/`pendingMoCallId_`、`pendingHangup_`/`pendingHangupCallId_`）。

#### Scenario: 拨号标志延时恢复
- **WHEN** `SetDialingCallProcessing` 在 `IsDialingCallProcessing()` 为真时被调用
- **THEN** 先 `RemoveTask(TASK_ID)` 再 `PostTask` 3000ms（`DELAY_TIME`）后执行 `RestoreDialingFlag(false)`；`isDialingCallProcessing_` 不变时静默

#### Scenario: 任务撤销
- **WHEN** 拨号状态上报到达后调用 `RemoveEventHandlerTask`
- **THEN** 撤销挂起的恢复任务

#### Scenario: 挂起状态对消费
- **WHEN** `CallStatusManager::ClearPendingState` 检查某 callId 的 `HasPendingMo`/`HasPendingHangup`
- **THEN** 挂起 MO 清标志；挂起挂断且通话未结束时执行 `call->HangUpCall` 再清标志；`IsPendingHangup` 仅在 `pendingHangupCallId_ != -1` 时返回 `pendingHangup_`

### Requirement: CallConnectAbility 通话界面连接管理
系统 SHALL 由 `CallConnectAbility` 维持 CallUIAbility 连接：以 `AAFwk::Want`（ElementName "com.ohos.callui"/"com.ohos.callui.ServiceAbility"）经 `AAFwk::AbilityManagerClient::ConnectAbility` 连接，回调为 `CallAbilityConnectCallback`；`isConnected_`/`isConnecting_`/`isDisconnecting_` 三标志互斥推进，`IPCSkeleton::ResetCallingIdentity` 包夹调用。

#### Scenario: 拉起
- **WHEN** `ConnectAbility` 且未连接、未在断开中
- **THEN** 置 connecting 标志发起连接；已连接仅复位标志；断开过程中拒绝并发起

#### Scenario: 断开
- **WHEN** `DisconnectAbility` 且 `WaitForConnectResult`（`cv_` 等待，最长 `WAIT_TIME_ONE_SECOND`(1s)）确认已连接
- **THEN** `DisconnectAbility(connectCallback_)` 并置回调为空；未连接（等待超时）则跳过断开并复位断开标志

#### Scenario: 连接/断开竞态
- **WHEN** `SetConnectingFlag(false)` 时仍在断开中，或 `SetDisconnectingFlag(false)` 时仍在连接中
- **THEN** 前者：若 `CallObjectManager::HasCallExist()` 为真则中止断开复原标志，否则继续断开；后者：重新发起连接（reconnect）

### Requirement: CallAbilityConnectCallback 连接结果处理
系统 SHALL 由 `CallAbilityConnectCallback` 在连接/断开回调中驱动标志复位与降级恢复。

#### Scenario: 连接成功
- **WHEN** `OnAbilityConnectDone` 的 resultCode==0（`CONNECT_ABILITY_SUCCESS`）
- **THEN** 置 `SetConnectFlag(true)`、`SetConnectingFlag(false)`、`NotifyAll` 唤醒等待方；按 `CallSuperPrivacyControlManager::GetCurrentIsSuperPrivacyMode` 组装 `EVENT_IS_SUPER_PRIVACY_MODE_ON/OFF` 事件经 `CallAbilityReportProxy::CallEventUpdated` 上报；`AudioDeviceManager::UpdateEarpieceDevice` 恢复听筒；`CallVoiceAssistantManager::PublishCommonEvent(true, "call_ui_connect_done")`

#### Scenario: 断开与意外重连
- **WHEN** `OnAbilityDisconnectDone` 返回，resultCode 为 `UNEXPECT_DISCONNECT_CODE`(-1)
- **THEN** 两个标志复位后执行 `ReConnectAbility`：仅当仍存在非 DISCONNECTING/DISCONNECTED/UNKNOWN/IDLE 通话时重新 `ConnectAbility`

### Requirement: CallBroadcastSubscriber 系统公共事件分发
系统 SHALL 由 `CallBroadcastSubscriber::OnReceiveEvent` 将 action 字符串映射到内部事件码（`UNKNOWN_BROADCAST_EVENT`…`MUTE_KEY_PRESS`）并经 `memberFuncMap_` 分发；订阅由 `CallControlManager::SystemAbilityListener` 以多组 `MatchingSkills` 建立。

#### Scenario: SIM 状态变化
- **WHEN** 收到 `COMMON_EVENT_SIM_STATE_CHANGED`
- **THEN** `SimStateBroadcast` 仅记录 code 日志

#### Scenario: 通讯录界面联动
- **WHEN** 收到 "event.custom.contacts.PAGE_STATE_CHANGE"，want 参数 `isShouldConnect` 为真
- **THEN** `CallControlManager::ConnectCallUiService(true)` 拉起通话界面服务

#### Scenario: 卫星高温等级
- **WHEN** 收到 "usual.event.thermal.satcomm.HIGH_TEMP_LEVEL"（发布者 UID 门控）
- **THEN** 以 `satcomm_high_temp_level` 调 `SatelliteCallControl::SetSatcommTempLevel`

#### Scenario: 超级隐私模式
- **WHEN** 收到 "usual.event.SUPER_PRIVACY_MODE"（发布者限 com.settings）
- **THEN** `isInCall&&isHangup` 时 `CloseAllCall`；否则记旧模式并置变更标志，按 `isInCall`/`isAnswer`/dial 参数分别走 `CloseSuperPrivacyMode`/`CloseAnswerSuperPrivacyMode`/`CloseCallSuperPrivacyMode`

#### Scenario: 蓝牙远端设备名更新
- **WHEN** 收到 `COMMON_EVENT_BLUETOOTH_REMOTEDEVICE_NAME_UPDATE`
- **THEN** 以 `deviceAddr`/`remoteName` 调 `AudioDeviceManager::UpdateBluetoothDeviceName`

#### Scenario: 用户切换
- **WHEN** 收到 `COMMON_EVENT_USER_SWITCHED` 且通话界面已连接
- **THEN** `DisconnectAbility` 后由新回调 `ReConnectAbility` 重连，并 `StopFlashRemind`

#### Scenario: 系统关机
- **WHEN** 收到 `COMMON_EVENT_SHUTDOWN`
- **THEN** `CallControlManager::DisconnectAllCalls` 并 `StopFlashRemind`

#### Scenario: HSDR 号码识别数据更新
- **WHEN** 收到 "usual.event.HSDR_EVENT"（发布者限 com.hsdr）且 data 含 "com.numberidentity.devicenumber"
- **THEN** `NumberIdentityServiceHelper::NotifyNumberMarkDataUpdate`

#### Scenario: HFP 连接来电信息
- **WHEN** 收到 "usual.event.bluetooth.CONNECT_HFP_HF"（订阅受 `HFP_ASYNC_ENABLE` 门控）
- **THEN** 先 `ConnectAbility` 再 `DelayedDisconnectCallConnectAbility`(3000000µs)；前台通话号码一致时直接更新其 `SetCallerInfo`，否则 `BluetoothCallConnection::SetHfpContactName` 缓存名

#### Scenario: 屏幕解锁
- **WHEN** 收到 `COMMON_EVENT_SCREEN_UNLOCKED` 且 `OsAccountManager::IsOsAccountVerified` 为假
- **THEN** 延迟 2000ms 后发布有序公共事件 `COMMON_EVENT_INCOMING_CALL_MISSED`（code 0）；已验证则仅 `StopFlashRemind`

#### Scenario: 静音键
- **WHEN** 收到 "multimodal.event.MUTE_KEY_PRESS"
- **THEN** `StopFlashRemind`

#### Scenario: 未知事件
- **WHEN** action 不在任何已知映射
- **THEN** 走 `UnknownBroadcast` 仅记日志