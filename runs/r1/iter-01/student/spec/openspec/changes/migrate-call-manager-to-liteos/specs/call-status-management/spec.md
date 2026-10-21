# Spec Delta

## MODIFIED Requirements

### Requirement: 单笔呼叫状态上报分发
系统 SHALL 由 `CallStatusManager::HandleCallReportInfo` 按 `CallDetailInfo.state` 将单笔状态上报路由到对应处理函数：`CALL_STATUS_ACTIVE`→`ActiveHandle`、`CALL_STATUS_HOLDING`→`HoldingHandle`、`CALL_STATUS_DIALING`→`DialingHandle`、`CALL_STATUS_ALERTING`→`AlertHandle`、`CALL_STATUS_INCOMING`→`IncomingHandle`（前后包夹 `CallControlManager::AcquireIncomingLock`/`ReleaseIncomingLock`，专用锁调用点按 [powerLock] todo 桩化、逻辑保留）、`CALL_STATUS_WAITING`/`CALL_STATUS_DISCONNECTED`/`CALL_STATUS_DISCONNECTING`→`HandleCallReportInfoEx`，非法状态仅记日志；`TYPE_VOIP` 走 `HandleVoipCallReportInfo`。因 BLUETOOTH 类型通话不支持（AGENTS 功能范围），原 `TYPE_BLUETOOTH` 先经 `HandleBluetoothCallReportInfo` 预处理的分支移除；因 liteOS 不支持 DSDA（`CallManagerUtils::GetDsdsMode` 恒 0）且蓝牙通话不支持，原"每次处理结束后统一执行 `HandleDsdaInfo` 与 `BluetoothCallService::GetCallState`"的收尾分支移除。

#### Scenario: 拨号/来电维测计时
- **WHEN** 状态为 `CALL_STATUS_DIALING` 或 `CALL_STATUS_INCOMING` 的上报被处理完成
- **THEN** 超时判定 `CallManagerHisysevent::JudgingDialTimeOut`/`JudgingIncomingTimeOut` 照基线执行，HiSysEvent/hitrace 维测输出点改经 `stub/hisysevent_stub` 同名桩以日志打印（`FinishAsyncTrace` 计时终点同样以日志输出替代）

#### Scenario: WAITING 状态复用来电链
- **WHEN** `HandleCallReportInfoEx` 收到 `CALL_STATUS_WAITING`
- **THEN** 走 `WaitingHandle`，即包夹来电锁的 `IncomingHandle`

#### Scenario: 断链原因上报
- **WHEN** `HandleDisconnectedCause` 将 `DisconnectedDetails` 交给 `CallControlManager::NotifyCallDestroyed` 且返回失败
- **THEN** 返回 `CALL_ERR_PHONE_CALLSTATE_NOTIFY_FAILED`

### Requirement: 呼叫状态集合对账
系统 SHALL 由 `HandleCallsReportInfo` 将整呼叫列表（`CallDetailsInfo.callVec`）与按 slot 缓存的 `callDetailsInfo_` 对账，并只能为合法 slotId 分发（`slotId` 参数面保留，供双卡扩展）。因 liteOS 不支持 DSDA（`GetDsdsMode` 恒 0），对账结束后不再执行 `HandleDsdaInfo` 的保持能力收紧。

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
- **WHEN** 对账处理结束
- **THEN** 因 liteOS 不支持 DSDA（`CallManagerUtils::GetDsdsMode` 恒 0），原 `HandleDsdaInfo` 依 `DSDS_MODE_V5_DSDA`/`DSDS_MODE_V5_TDM` 与其它 slot 通话数对保持中通话执行 `SetCanUnHoldState(false)` 的收紧分支移除，不再发生任何 DSDA 收紧动作

### Requirement: 请求失败与事件上报
系统 SHALL 由 `HandleEventResultReportInfo` 将 cellular_call 的 `EVENT_REQUEST_RESULT_TYPE` 请求失败事件按 `mEventIdTransferMap_` 映射为 `CallAbilityEventId` 并经 `CallControlManager::NotifyCallEventUpdated` 上报。因 OTT 类型通话不支持（AGENTS 功能范围），原 `HandleOttEventReportInfo` 将 `OTT_CALL_EVENT_FUNCTION_UNSUPPORTED` 映射为 `EVENT_OTT_FUNCTION_UNSUPPORTED` 的处理分支移除。

#### Scenario: 拨号失败兜底
- **WHEN** 收到任一请求失败事件且存在 `CALL_RUNNING_STATE_DIALING` 的通话
- **THEN** 先对该通话执行 `DealFailDial`

#### Scenario: 无运营商拨号失败
- **WHEN** 事件为 `RESULT_DIAL_NO_CARRIER`（映射 `EVENT_DIAL_NO_CARRIER`）
- **THEN** 从 `CallControlManager::GetDialParaInfo` 取号码（校验 `kMaxNumberLen`）填入 `CallEventInfo.phoneNum` 后上报

#### Scenario: 合会议失败联动
- **WHEN** 事件为 `RESULT_COMBINE_SEND_FAILED`
- **THEN** 映射 `EVENT_COMBINE_CALL_FAILED`，并对活动通话执行 `HandleCombineConferenceFailEvent` 后上报（映射与处理链照基线保留；因会议通话不支持，该事件在 liteOS 上预期不发生）

#### Scenario: 保持失败复位
- **WHEN** 事件为 `RESULT_HOLD_SEND_FAILED`
- **THEN** 映射 `EVENT_HOLD_CALL_FAILED` 上报，并将 `needWaitHold_` 置 false

#### Scenario: 未知/OTT 事件
- **WHEN** 事件 id 不在映射表（仅记日志）
- **THEN** 映射表外的 cellular 事件不上报；因 OTT 通话不支持，原 `HandleOttEventReportInfo` 对携带 bundle 名的 OTT 事件（校验长度后拷入 `CallEventInfo.bundleName`）映射 `EVENT_OTT_FUNCTION_UNSUPPORTED` 上报的分支移除，OTT 事件不再被处理

### Requirement: 来电准入过滤
系统 SHALL 在 CS/IMS 类型来电建链前，由 `CallStatusManager::IncomingFilterPolicy` 调用 `CallIncomingFilterManager::DoIncomingFilter` 执行准入校验，非 `TELEPHONY_SUCCESS` 时来电直接终止。因 EDM 企业禁拨不支持（AGENTS 功能范围，`edm_call_policy` 不迁移），原 `CallControlManager::IsIncomingEnable`（EDM 禁拨策略）判定分支移除。

#### Scenario: EDM 禁拨策略
- **WHEN** `DoIncomingFilter` 执行准入校验
- **THEN** 因 EDM 企业禁拨不支持，原 `CallControlManager::IsIncomingEnable`（EDM 禁拨策略）对来话号码返回 false 导致 `TELEPHONY_ERR_POLICY_DISABLED` 且不创建通话对象的分支移除，来电不再因 EDM 策略被终止

#### Scenario: 紧急号码放行
- **WHEN** `CellularCallConnection::IsEmergencyPhoneNumber`（适配器出口改调 `CellularCallClient::GetInstance()` 桩）判定来话号码为紧急号码
- **THEN** 返回 `TELEPHONY_SUCCESS` 继续正常来电流程

### Requirement: 来电拒接判定链
系统 SHALL 在来电对象创建后、入表前，由 `CallStatusManager::IsRejectCall` 依次执行系统级拒接（`ShouldRejectIncomingCall`）、骚扰拦截（`ShouldBlockIncomingCall`）与免打扰静默标记（`IsFocusModeOpen`）三级判定；命中拒接时经 `HandleRejectCall` 完成状态落位与日志通知。语义分支结构照基线保留；外部出口桩化：设置项查询（`user_setup_complete`/`focus_mode_enable` 等）出口以 `// todo!!! [database]` 占位，`Notification::NotificationHelper::IsNeedSilentInDoNotDisturbMode` 出口以 `// todo!!! [notification]` 占位，骚扰检测出口以 `// todo!!! [spamCall]` 占位；`OsAccountManager` 帐号查询按 liteOS 单主帐号精简为默认主帐号常量（分支结构保留）。

#### Scenario: 紧急通话在通时拒接
- **WHEN** `HasEmergencyCall` 报告存在紧急通话（需人工复核（ECC）：ECC 在通豁免判定链的裁剪面见 proposal BREAKING 项）
- **THEN** 判定拒接，`block=false`，行为事件 `CALL_INCOMING_REJECT_BY_SYSTEM` 以 `REJECT_BY_OOBE` 记录（维测输出经 `stub/hisysevent_stub` 桩以日志替代）

#### Scenario: 开机向导未完成拒接
- **WHEN** `GetDevProvisioned()` 非 `DEVICE_PROVISION_VALID`，或设置项 `user_setup_complete`（查询出口 todo [database]）查询成功且取值为 "0"/空串
- **THEN** 判定拒接，`block=false`；原 `OsAccountManager::QueryActiveOsAccountIds` 为空则本分支不拒接的判定，按 liteOS 单主帐号精简为默认主帐号常量（视为非空），分支结构照抄

#### Scenario: VoIP 振铃冲突拒接
- **WHEN** `CallControlManager::GetVoIPCallState` 返回 `CALL_STATE_RINGING`
- **THEN** 判定拒接，`block=false`

#### Scenario: 骚扰拦截判定
- **WHEN** 非紧急号码，`SpamCallAdapter::DetectSpamCall` 启动检测（外部查询出口 todo [spamCall]）且 `WaitForDetectResult` 在超时前返回
- **THEN** `GetParseResult` 解析结果写回通话对象（`SetNumberMarkInfo`/`SetBlockReason`/`SetDetectDetails` + extraParams "blockReason"）；`isBlock` 为真才判定拦截，`block=true` 以 `REJECT_BY_NUM_BLOCK` 记录（经桩以日志替代）；检测启动时间记入 `detectStartTime`

#### Scenario: 免打扰静默不拒接
- **WHEN** 设置项 `focus_mode_enable`（查询出口 todo [database]）为 "1" 且 `NotificationHelper::IsNeedSilentInDoNotDisturbMode`（出口 todo [notification]，桩返回失败/不可用语义）返回 0
- **THEN** 不拒接，但向通话 extraParams 写入 `IsNeedSilentInDoNotDisturbMode=1`，行为事件以 `REJECT_IN_FOCUSMODE` 记录（经桩以日志替代）

#### Scenario: 拒接落位
- **WHEN** `IsRejectCall` 返回 true
- **THEN** `HandleRejectCall` 将状态置 `CALL_STATUS_INCOMING`、执行 `call->RejectCall`；`block=true` 走 `AddBlockLogAndNotification`（置 `CALL_ANSWER_BLOCKED`），否则走 `AddCallLogAndNotification`（置 `CALL_ANSWER_MISSED`）

### Requirement: 来话建链主链
系统 SHALL 由 `IncomingHandle` 按固定次序完成来话处理：重置 `detectStartTime` → `RefreshOldCall` 去重 → 准入过滤 → `CreateNewCall`（`CALL_DIRECTION_IN`）→ 同号同时来电判定 → `SetContactInfo` → 拒接判定 → 响一声判定 → `AddOneCallObject` → `NotifyNewCallCreated` → `UpdateCallState` → `FilterResultsDispose`。因运动识别不支持（AGENTS 特性宏 OHOS_SUBSCRIBE_MOTION_ENABLE 不支持）、来电闪光不支持、视频通话不支持，原链路中的 `StartInComingCallMotionRecognition`、`StartFlashRemind`、视频高级安全模式（`HandleVideoCallInAdvsecMode`）节点移除。

#### Scenario: 已存在旧来话去重
- **WHEN** `RefreshOldCall` 以 index/slotId/callType 命中既有来话
- **THEN** 仅按需 `RefreshCallIfNecessary`/`UpdateCallState` 刷新旧对象并置 `isExistedOldCall`，不重复建链；此前如存在 index-0 拨号占位通话，先对其 `DealFailDial`

#### Scenario: 正常来电入链
- **WHEN** 全部判定通过
- **THEN** 通话对象入全局表，状态经 `UpdateCallState` 落位 `CALL_STATUS_INCOMING`，随后交 `CallStatusPolicy::FilterResultsDispose` 处置；因来电闪光不支持，原 `CallControlManager::StartFlashRemind`（`incoming_flash_reminder`）触发分支移除，不再触发闪光提醒

#### Scenario: 拒接/响一次分支短路
- **WHEN** `IsRejectCall` 或（非 VOIP 且）`IsRingOnceCall` 判定命中
- **THEN** 分别转入 `HandleRejectCall`/`HandleRingOnceCall`，通话对象不入表、不触发后续通知链；原"非蓝牙"排除条件因 BLUETOOTH 类型通话不支持随蓝牙链路整体移除

### Requirement: 响一声拦截
系统 SHALL 由 `IsRingOnceCall` 在骚扰检测窗内等待一小段时间（`TimeWaitHelper`，窗口为 `WAIT_TIME_THREE_SECOND`(3000ms) 减去已耗检测时长），以识别"响一声即挂"的来电；命中时由 `HandleRingOnceCall` 直接记为未接。`spamshield_sim<N>_phone_switch_ring_once` 类设置键的查询出口以 `// todo!!! [database]` 占位（逻辑保留）。

#### Scenario: 免检场景
- **WHEN** 来电为黄页标记（`MARK_TYPE_YELLOW_PAGE`）或命中联系人（`contactInfo.name` 非空，联系人查询出口 todo [database]），或设置项 `spamshield_sim<N>_phone_switch_ring_once`（查询出口 todo [database]）非 "1"
- **THEN** 判定非响一声，走正常来电流程

#### Scenario: 等待窗内对端挂断
- **WHEN** 开关开启且 `TimeWaitHelper::WaitForResult` 在等待窗内被 `DisconnectedHandle` 的 `NotifyAll` 唤醒返回 true
- **THEN** `HandleRingOnceCall` 将状态置 `CALL_STATUS_INCOMING` 并直接 `AddCallLogAndNotification`（记未接、通知出口按 call-state-observer 能力桩化）；等待窗结束 helper 释放

#### Scenario: 等待超时
- **WHEN** 等待窗内未发生挂断，`WaitForResult` 超时返回
- **THEN** 判定非响一声（"is not ring once"），helper 释放，通话走正常流程

### Requirement: 同号同时来电与 eSIM 归属修正
系统 SHALL 由 `IsFromTheSameNumberAtTheSameTime`（一号双终端场景）识别同号同瞬来电；判定与处理链保留。因 eSIM 不支持（AGENTS 功能范围），原判定命中后的 `ModifyEsimType` eSIM 类型修正分支移除。

#### Scenario: 判定条件全命中
- **WHEN** 新来话号码与既有通话（`GetOneCallObject(phoneNumber)`，号码比对前先剥离后拨段）相同、两 callId 差绝对值为 1、旧通话状态为 `CALL_STATUS_INCOMING`、两次 `callCreateTime` 差 ≤ 10000ms
- **THEN** 判定为同号同时来电（判定逻辑保留，判定结果不再驱动 eSIM 修正）

#### Scenario: eSIM 类型修正
- **WHEN** 判定命中
- **THEN** 因 eSIM 不支持，原 `SettingsDataShareHelper::Update` 将 `key_esim_card_type` 更新为 "1" 并逐位补写 `key_manually_set_net`（`key_smartoff_network_bluetooth_connection`/`key_smartoff_network_not_wear`/`key_smartoff_network_sleep_mode`）的 `ModifyEsimType` 分支移除，不发生任何 eSIM 设置项更新

### Requirement: 来电联系人信息与高级安全模式
系统 SHALL 在来电建链时以 `SetContactInfo` 异步（原 `ffrt::submit` 改经打桩 EventHandler 提交，`stub/eventhandler_stub`）填充联系人信息：经 `QueryCallerInfo`→`CallDataBaseHelper::Query(ContactInfo…)`（DataShare 调用点 todo [database]）用 predicates（`type_id=5`、`is_deleted=0`、`detail_info=号码`；`TELEPHONY_CUST_SUPPORT` 下号码长度 ≥ `QUERY_CONTACT_LEN`(7) 时改为对 `detail_info`/`format_phone_number` 的 ends-with 后缀匹配并调用 `QueryContactInfoEnhanced`，增强查询出口经 TelephonyCustClient 桩/ todo [database]）查询 contacts 数据库，随后 `SetCallerInfo`。因语音播报、分布式通话、视频彩振、BLUETOOTH 类型通话、视频通话均不支持（AGENTS 功能范围），原联动的 `CallVoiceAssistantManager::UpdateContactInfo`、`DistributedCommunicationManager::ProcessCallInfo(NAME)`、视频彩振路径（`NeedPlayVideoRing`→extraParams "VideoRingPath"）与蓝牙派生分支移除。

#### Scenario: 联系人命中与否
- **WHEN** `IsContactPhoneNum` 复用同查询（查询出口 todo [database]），contacts 返回的 `detail_info/display_name` 非空（`contactInfo.name` 长度 ≥1）
- **THEN** 判定为联系人号码；查询失败仅记日志，`isQueryComplete` 保持初始 true

#### Scenario: 蓝牙来电联系人
- **WHEN** 来电为 `TYPE_BLUETOOTH`
- **THEN** 因 BLUETOOTH 类型通话不支持，原 `SetContactInfo` 中经 `BluetoothCallConnection::GetHfpContactName`/`GetBtCallContactInfo` 直接以 HFP 联系人名填充 `SetCallerInfo` 与 extraParams "BtCallContactName" 的蓝牙派生分支移除；liteOS 上不存在 `TYPE_BLUETOOTH` 来电进入本链

#### Scenario: 视频来电高级安全模式
- **WHEN** IMS 视频来电进入建链
- **THEN** 因视频通话不支持，原 `HandleVideoCallInAdvsecMode` 判定（`IsTrustedNumber`：标记非黄页/企业且非联系人；系统参数 `ohos.boot.advsecmode.state`）与对通话执行 `SetForcedReportVoiceCall(true)` 的分支移除，不发生高级安全模式判定

### Requirement: 去电拨号与振铃处理
系统 SHALL 由 `DialingHandle` 完成去电状态落位、由 `AlertHandle` 完成对端振铃状态落位。因分布式通话、BLUETOOTH 类型通话、运动识别、地震预警均不支持（AGENTS 功能范围），链路中原 `IsDistributeCallSourceStatus`/`IsDcCallConneceted` 分布式判定、`BtCallDialingHandle`/`SetBtCallDialByPhone` 蓝牙标识、`StartOutGoingCallMotionRecognition`、`MyLocationEngine::StartEccService` 分支移除；拨号标志恢复经打桩 EventHandler（见 CallRequestEventHandlerHelper 需求）。

#### Scenario: 既有通话的拨号态更新
- **WHEN** 上报 index>0 且 `UpdateDialingHandle` 命中既有对象
- **THEN** `UpdateDialingCallInfo` 刷新既有通话（index-0 占位通话保留原拨号码 `oriNum`，刷新后 `ClearPendingState`），不新建对象；原蓝牙来话另走 `BtCallDialingHandle` 与命中分卡 index 对象时依 `IsDistributeCallSourceStatus` 判分布式拨号的分支移除

#### Scenario: 新建去电
- **WHEN** 无既有对象，`CreateNewCall(CALL_DIRECTION_OUT)` 成功
- **THEN** 对象入表；index==`INIT_INDEX`(0) 时置 `SetPendingMo(true, callId)`、`SetPhoneOrWatchDial(WATCH_DIAL)`；随后 `RestoreDialingFlag(false)`、`RemoveEventHandlerTask`、`call->DialingProcess`、`NotifyNewCallCreated`、`UpdateCallState(CALL_STATUS_DIALING)`；原 `IsDistributeCallSourceStatus` 写 extraParams "isDistributedDeviceDialing"、`IsDcCallConneceted` 为真时补 `SetContactInfo`、`SetBtCallDialByPhone(false)`、`StartOutGoingCallMotionRecognition`、`MyLocationEngine::StartEccService` 分支均移除

#### Scenario: 振铃态落位
- **WHEN** `AlertHandle` 收到 `CALL_STATUS_ALERTING` 上报，对象缺失
- **THEN** 经 `RefreshDialingStateByOtherState`（以临时 DIALING 信息重跑 `DialingHandle`）补救后 `UpdateCallState(CALL_STATUS_ALERTING)`；原 `IsDcCallConneceted` 为真时按 `CALL_DIRECTION_OUT` 补建的分布式分支移除；`AUDIO_SUPPORT` 分支因基线仓未定义（默认构建恒不编译）不迁移

### Requirement: 激活态与会议合并
系统 SHALL 由 `ActiveHandle` 完成通话激活落位。因会议通话不支持（AGENTS 功能范围），原多路会议合并判定（`GetConferenceCallList`/`SetConferenceCall`/`LaunchConference`/`ExitConference`）分支移除；因分布式通话、视频通话、防诈不支持，原 `IsDcCallConneceted` 补建、原始视频状态记录与防诈启动判定分支移除。

#### Scenario: 对象缺失补救
- **WHEN** 以 index/slotId/callType 找不到对象
- **THEN** 经 `RefreshDialingStateByOtherState` 补救；失败返回 `TELEPHONY_ERR_LOCAL_PTR_NULL`；原 `IsDcCallConneceted` 为真时 `CreateAndSaveNewCall(CALL_DIRECTION_UNKNOW)` 补建（并 `ffrt::submit` 触发 `YellowPageAndMarkUpdate`）的分布式分支移除

#### Scenario: 会议合并与退出
- **WHEN** 上报 `mpty==1`
- **THEN** 因会议通话不支持，原 `GetConferenceCallList` 聚合多于 1 个对象时 `SetConferenceCall` 对每路非 `TEL_CONFERENCE_ACTIVE` 通话执行 `LaunchConference` + `UpdateCallState`、否则尝试 `call->ExitConference` 的会议合并与退出分支移除，仅完成激活落位

#### Scenario: 激活落位与音频恢复
- **WHEN** `UpdateCallState(CALL_STATUS_ACTIVE)` 成功
- **THEN** 保持中通话 `SetCanSwitchCallState(true)`；`AUDIO_SUPPORT` 分支因基线仓未定义不迁移；原随后进入的防诈启动判定分支移除（防诈能力整删，见 REMOVED 防诈检测状态管理需求）

#### Scenario: 原始视频状态记录
- **WHEN** 前态为 ALERTING/INCOMING/WAITING/ACTIVE/HOLDING
- **THEN** 因视频通话不支持，原 `GetOriginalCallType`/`SetOriginalCallType` 记录与按位或合并（升级/降级场景）分支移除，不发生原始视频状态记录

### Requirement: 保持与断开处理
系统 SHALL 由 `HoldingHandle`/`DisconnectingHandle`/`DisconnectedHandle` 完成保持、断开中、已断开的状态落位及善后联动。因防诈、会议通话、DSDA、地震预警、超级隐私、运动识别、来电闪光均不支持（AGENTS 功能范围），善后链中 `StopAntiFraudDetect`、`ExitConference` 与会议收尾、`MyLocationEngine::StopEccService`、`RestoreSuperPrivacyMode`、`StopCallMotionRecognition`、`StopFlashRemind` 分支移除；`UpdateCallStateAndHandleDsdsMode` 非零分支删除、其余照抄。

#### Scenario: 保持态落位
- **WHEN** `HoldingHandle` 收到 `CALL_STATUS_HOLDING`
- **THEN** `UpdateCallStateAndHandleDsdsMode` 落位 HOLDING；原 `mpty==1` 时 `HoldConference` 分支与仅当 `GetDsdsMode` 为 `DSDS_MODE_V5_DSDA`/`DSDS_MODE_V5_TDM` 时的后续自动处理（`needWaitHold_` 且无活动通话→`HandleDialWhenHolding`，否则 `AutoHandleForDsda`）分支移除；`needWaitHold_` 字段与复位写点按 NOT_SUPPORT_MULTICALL 宏骨架照抄保留

#### Scenario: 断开中落位
- **WHEN** `DisconnectingHandle` 收到 `CALL_STATUS_DISCONNECTING`
- **THEN** `SetOriginalCallTypeForDisconnectState`（视频通话不支持，视频记录分支移除后为空操作语义照抄）、`UpdateCallState(CALL_STATUS_DISCONNECTING)`；原 `StopAntiFraudDetect` 与 `StopFlashRemind` 分支移除

#### Scenario: 已断开善后
- **WHEN** `DisconnectedHandle` 处理 `CALL_STATUS_DISCONNECTED`（若有 `TimeWaitHelper` 先 `NotifyAll`，响一声链保留）
- **THEN** 前态非 DISCONNECTING 时先 `AcquireDisconnectedLock`（[powerLock] todo 桩化、逻辑保留）；`RefreshCallDisconnectReason`、`ClearPendingState`；`UpdateCallState(DISCONNECTED)`；再经 `HandleHoldCallOrAutoAnswerCall` 恢复保持通话（自动接听路径移除，见挂断后恢复保持与自动接听需求）；原 `call->ExitConference`、会议仅剩一路时 `SetTelConferenceState(TEL_CONFERENCE_IDLE)` 并重发状态、通话总数归零时 `RestoreSuperPrivacyMode`、`NOT_SUPPORT_MULTICALL` 下双路 BT+eSIM/双路 eSIM 场景 `AutoAnswerSecondCall`、`StopCallMotionRecognition(DISCONNECTED)`、`StopFlashRemind` 分支均移除；原 `MyLocationEngine::StopEccService` 分支移除

#### Scenario: 断链原因归位
- **WHEN** `RefreshCallDisconnectReason` 依 `RilDisconnectedReason` 分类
- **THEN** CS 通话 `DISCONNECTED_REASON_CS_CALL_ANSWERED_ELSEWHER` 置 `CALL_ANSWERED_ELSEWHER`；`DISCONNECTED_REASON_ANSWERED_ELSEWHER` 在 message 含 "elsewhere" 时同样置位（原 `DistributedCommunicationManager::IsSinkRole` 的 sink 角色判定因分布式通话不支持移除）；`DISCONNECTED_REASON_NORMAL` 时向 extraParams 写 `disconnectedReason=CALL_DISCONNECTED_BY_REMOTE`

### Requirement: 挂断后恢复保持与自动接听
系统 SHALL 由 `HandleHoldCallOrAutoAnswerCall` 在通话结束后恢复保持通话；`IsCanUnHold` 描述可恢复条件（活动/等待/接听/去电/振铃数全为 0 且子通话数 ≤1）。因 liteOS 不支持 DSDA（`CallManagerUtils::GetDsdsMode` 恒 0，非 0 流程不迁移），DSDS_MODE_V3 自动接听与 DSDA/TDM 自动处理路径移除；因 BLUETOOTH 类型通话与 eSIM 不支持，NOT_SUPPORT_MULTICALL 二次自动接听判定族移除（宏骨架本身保留，见 build-config）。

#### Scenario: 释放并恢复保持通话
- **WHEN** 通话结束时前态非 HOLD、非 ACTIVE、前状态为 DISCONNECTING，且存在保持通话、`canUnHold` 与 `GetCanUnHoldState` 均真、slot 相同
- **THEN** 对保持通话执行 `UnHoldCall`

#### Scenario: DSDS_MODE_V3 自动接听
- **WHEN** 通话结束后查询 DSDS 模式
- **THEN** 因 liteOS 不支持 DSDA（`GetDsdsMode` 恒 0），原 `DSDS_MODE_V3` 下活动/等待/保持/拨号/振铃数全 0 且存在置了 `GetAutoAnswerState` 的振铃通话时对其 `AnswerCall(GetAnswerVideoState)` 的分支移除，不发生 DSDS_MODE_V3 自动接听

#### Scenario: DSDA/TDM 自动处理
- **WHEN** 通话结束后查询 DSDS 模式
- **THEN** 因 liteOS 不支持 DSDA（`GetDsdsMode` 恒 0），原 `DSDS_MODE_V5_DSDA`/`DSDS_MODE_V5_TDM` 下 `AutoHandleForDsda`（视频振铃通话走 `AutoAnswerForVideoCall`、语音振铃通话走 `AutoAnswerForVoiceCall`、`AutoUnHoldForDsda` 恢复其它 slot 保持通话并对保持通话 `SetCanUnHoldState(true)`）的整链分支移除，不发生任何 DSDA/TDM 自动处理

#### Scenario: NOT_SUPPORT_MULTICALL 二次自动接听
- **WHEN** 通话挂断后进入收尾
- **THEN** 因 BLUETOOTH 类型通话与 eSIM 不支持，原 `NOT_SUPPORT_MULTICALL` 下 `IsTwoCallBtCallAndESIM`/`IsTwoCallESIMCall` 判定双路 BT+eSIM/双路 eSIM 后 `AutoAnswerSecondCall` 对剩余 INCOMING/WAITING 通话执行 `CallControlManager::AnswerCall` 的分支移除；`NOT_SUPPORT_MULTICALL` 宏骨架（`needWaitHold_`/`dialCallInfo_` 字段与读取接口）保留

### Requirement: 状态统一下发与对象刷新
系统 SHALL 由 `UpdateCallState` 统一完成状态落位与上报，`RefreshCallIfNecessary` 处理 callType 变化时的对象迁移。因视频通话与视频彩振（crsType==CRS_TYPE）不支持（AGENTS 功能范围），原 `SetVideoCallState` 视频对象态联动分支移除。

#### Scenario: 状态落位失败分支
- **WHEN** `call->SetTelCallState` 返回既非成功也非 `CALL_ERR_NOT_NEW_STATE`，或 `NotifyCallStateUpdated` 失败
- **THEN** 分别返回 `TELEPHONY_ERR_LOCAL_PTR_NULL`；上报失败且目标态为 INCOMING 时记 `WriteIncomingCallFaultEvent`（经 `stub/hisysevent_stub` 桩以日志输出）并返回 `CALL_ERR_PHONE_CALLSTATE_NOTIFY_FAILED`；接听超时经 `JudgingAnswerTimeOut` 照抄；原 satellite 通话先经 `SatelliteCallControl::HandleSatelliteCallStateUpdate` 的分支因卫星通话不支持移除

#### Scenario: callType 变化对象迁移
- **WHEN** `RefreshCallIfNecessary` 中上报 callType 与对象 callType 不一致
- **THEN** 以 `CreateNewCall` 新建对象并整体迁移属性（运行态、会议态、各时间戳、静音、号码归属地、黄页标记），删除旧对象并继承 callId 与前状态；原 IMS 先同步视频状态并 `InitVideoCall`、crsType（视频彩振）判定的分支因视频通话/视频彩振不支持移除

#### Scenario: 视频状态联动
- **WHEN** 通话状态变化
- **THEN** 因视频通话不支持，原 slot 级 `priorVideoState_` 视频状态缓存与 `SetVideoCallState`/`AudioControlManager::VideoStateUpdated` 通报、断开时该 slot 缓存复位 `TYPE_VOICE` 的联动分支移除，不发生视频状态联动

### Requirement: 开机向导状态缓存与观察
系统 SHALL 以静态 `deviceProvisioned_` 缓存 `device_provisioned` 设置项（`DEVICE_PROVISION_UNDEF`/-1、`DEVICE_PROVISION_INVALID`/0、`DEVICE_PROVISION_VALID`/1），并由静态 `OOBEStatusObserver` 监听变更。设置项查询与观察注册出口桩化：`SettingsDataShareHelper::Query` 调用点 todo [database]，数据观察注册调用点 todo [database]，`COMMON_EVENT_DATA_SHARE_READY` 的 EventFwk 订阅调用点 todo [broadcast]（逻辑保留）。

#### Scenario: 懒加载首读
- **WHEN** `GetDevProvisioned` 首次调用（缓存为 UNDEF）
- **THEN** `UpdateDevProvisioned` 经 `SettingsDataShareHelper::Query`（调用点 todo [database]）读取：值为 "0" 或空→INVALID，"1"→VALID，其余保持未决

#### Scenario: 变更监听
- **WHEN** `RegisterObserver` 以 `SETTINGS_DATASHARE_URI + "&key=device_provisioned"` 注册 `OOBEStatusObserver`（注册调用点 todo [database]）成功后设置项变化
- **THEN** `OOBEStatusObserver::OnChange` 触发 `UpdateDevProvisioned` 刷新缓存（注册失败仅记日志；`UpdateDevProvisioned` 在 `COMMON_EVENT_DATA_SHARE_READY` 之后由 `CallStatusManager::RegisterObserver` 挂载，该公共事件的订阅调用点 todo [broadcast]）

### Requirement: CallStateListener 观察者总线
系统 SHALL 以 `CallStateListener`（`std::set<std::shared_ptr<CallStateListenerBase>>`）作为状态变化广播总线，将 8 类回调（`NewCallCreated`/`CallDestroyed`/`CallStateUpdated`/`MeeTimeStateUpdated`/`IncomingCallHungUp`/`IncomingCallActivated`/`CallEventUpdated`）逐一转发给全部已注册观察者；liteOS 单线程不加锁，原 `std::mutex` 保护随全仓去锁移除。

#### Scenario: 注册与去重
- **WHEN** `AddOneObserver` 收到已注册观察者或 `RemoveOneObserver`/`RemoveAllObserver` 操作
- **THEN** 重复注册幂等返回 true；null 观察者拒绝返回 false；移除即时生效

#### Scenario: 固定观察者阵容
- **WHEN** `CallControlManager` 初始化总线
- **THEN** 依次注册 `CallAbilityReportProxy`（回调直调）、`CallStateReportProxy`（对 core_service 的 TelephonyStateRegistry 上报出口经 `stub/state_registry_client` 桩）、`AudioControlManager`、`RejectCallSms`（hangUpSmsPtr）、`MissedCallNotification`、`IncomingCallWakeup`、`CallRecordsManager`；原 `DistributedCommunicationManager`、`InteroperableCommunicationManager`、`CallVoiceAssistantManager` 三个观察者因分布式/互信互联/语音播报不支持移除（观察者实现分属其他能力规格）

### Requirement: CallRequestEventHandlerHelper 拨号异步原语
系统 SHALL 由 `CallRequestEventHandlerHelper` 提供拨号标志的延时恢复与挂起状态对（`pendingMo_`/`pendingMoCallId_`、`pendingHangup_`/`pendingHangupCallId_`）。基线中该原语已是 `AppExecFwk::EventRunner`("handler_restore_dialing_flag") + `AppExecFwk::EventHandler` 的 `PostTask`/`RemoveTask` 形态（延时 3000ms，非 ffrt）；liteOS 上 EventRunner/EventHandler 改用 `stub/eventhandler_stub` 打桩（不新增线程，桩内串行语义）。`SetDialingCallProcessing` 的返回值反判按 HMOS 现状照抄（见正文注明）。

#### Scenario: 拨号标志延时恢复
- **WHEN** `SetDialingCallProcessing` 在 `IsDialingCallProcessing()` 为真时被调用
- **THEN** 先 `RemoveTask(TASK_ID)` 再经桩 EventHandler `PostTask` 3000ms（`DELAY_TIME`）后执行 `RestoreDialingFlag(false)`；`isDialingCallProcessing_` 不变时静默。注明：与 HMOS 现状一致，`PostTask` 返回 true（任务提交成功）被反判为失败——记 "restore dialing flag task failed" 日志并返回 `TELEPHONY_ERROR`，仅返回 false 才返回 `TELEPHONY_SUCCESS`；该反判为上游现状疑点，按 AGENTS「代码逻辑与 HMOS 保持一致」照抄不改

#### Scenario: 任务撤销
- **WHEN** 拨号状态上报到达后调用 `RemoveEventHandlerTask`
- **THEN** 经桩 EventHandler 撤销挂起的恢复任务

#### Scenario: 挂起状态对消费
- **WHEN** `CallStatusManager::ClearPendingState` 检查某 callId 的 `HasPendingMo`/`HasPendingHangup`
- **THEN** 挂起 MO 清标志；挂起挂断且通话未结束时执行 `call->HangUpCall` 再清标志；`IsPendingHangup` 仅在 `pendingHangupCallId_ != -1` 时返回 `pendingHangup_`

### Requirement: CallConnectAbility 通话界面连接管理
系统 SHALL 由 `CallConnectAbility` 维持 CallUIAbility 连接：以 `AAFwk::Want`（ElementName "com.ohos.callui"/"com.ohos.callui.ServiceAbility"）发起连接，回调为 `CallAbilityConnectCallback`；`isConnected_`/`isConnecting_`/`isDisconnecting_` 三标志互斥推进。`AAFwk::AbilityManagerClient::ConnectAbility`/`DisconnectAbility` 连接调用点经 `stub/` 打桩并标注 `// todo!!! [callUi] ref to call_connect_ability.cpp ConnectAbility`，失连降级行为照抄基线（桩返回失败/不可用语义）；原 `IPCSkeleton::ResetCallingIdentity` 包夹随 IPC 层不迁移移除。

#### Scenario: 拉起
- **WHEN** `ConnectAbility` 且未连接、未在断开中
- **THEN** 置 connecting 标志经桩发起连接；已连接仅复位标志；断开过程中拒绝并发起

#### Scenario: 断开
- **WHEN** `DisconnectAbility` 且 `WaitForConnectResult`（等待，最长 `WAIT_TIME_ONE_SECOND`(1s)）确认已连接
- **THEN** 经桩对 `connectCallback_` 断开并置回调为空；未连接（等待超时）则跳过断开并复位断开标志

#### Scenario: 连接/断开竞态
- **WHEN** `SetConnectingFlag(false)` 时仍在断开中，或 `SetDisconnectingFlag(false)` 时仍在连接中
- **THEN** 前者：若 `CallObjectManager::HasCallExist()` 为真则中止断开复原标志，否则继续断开；后者：重新发起连接（reconnect）

### Requirement: CallAbilityConnectCallback 连接结果处理
系统 SHALL 由 `CallAbilityConnectCallback` 在连接/断开回调中驱动标志复位与降级恢复（回调经 [callUi] 桩驱动，桩返回失败/不可用语义时降级行为照抄）。因超级隐私与语音播报不支持（AGENTS 功能范围），原超级隐私模式事件组装与 `CallVoiceAssistantManager::PublishCommonEvent` 分支移除。

#### Scenario: 连接成功
- **WHEN** `OnAbilityConnectDone` 的 resultCode==0（`CONNECT_ABILITY_SUCCESS`）
- **THEN** 置 `SetConnectFlag(true)`、`SetConnectingFlag(false)`、`NotifyAll` 唤醒等待方；原按 `CallSuperPrivacyControlManager::GetCurrentIsSuperPrivacyMode` 组装 `EVENT_IS_SUPER_PRIVACY_MODE_ON/OFF` 事件经 `CallAbilityReportProxy::CallEventUpdated` 上报的超级隐私分支移除；`AudioDeviceManager::UpdateEarpieceDevice` 恢复听筒保留；原 `CallVoiceAssistantManager::PublishCommonEvent(true, "call_ui_connect_done")` 分支移除

#### Scenario: 断开与意外重连
- **WHEN** `OnAbilityDisconnectDone` 返回，resultCode 为 `UNEXPECT_DISCONNECT_CODE`(-1)
- **THEN** 两个标志复位后执行 `ReConnectAbility`：仅当仍存在非 DISCONNECTING/DISCONNECTED/UNKNOWN/IDLE 通话时重新 `ConnectAbility`（经 [callUi] 桩）

### Requirement: CallBroadcastSubscriber 系统公共事件分发
系统 SHALL 由 `CallBroadcastSubscriber::OnReceiveEvent` 将 action 字符串映射到内部事件码（`UNKNOWN_BROADCAST_EVENT`…`MUTE_KEY_PRESS`）并经 `memberFuncMap_` 分发。订阅建立逻辑保留（原 samgr `SystemAbilityListener` 宿主不迁移，`MatchingSkills` 构造照抄），`EventFwk::CommonEventManager` 订阅/发布调用点统一以 `// todo!!! [broadcast]` 占位（逻辑保留）。因卫星通话、超级隐私、BLUETOOTH/HFP、来电闪光不支持（AGENTS 功能范围），卫星高温、超级隐私、蓝牙远端设备名、HFP 来电信息与闪光提醒联动分支移除；MUTE_KEY_PRESS 映射保留。

#### Scenario: SIM 状态变化
- **WHEN** 收到 `COMMON_EVENT_SIM_STATE_CHANGED`（订阅调用点 todo [broadcast]）
- **THEN** `SimStateBroadcast` 仅记录 code 日志

#### Scenario: 通讯录界面联动
- **WHEN** 收到 "event.custom.contacts.PAGE_STATE_CHANGE"，want 参数 `isShouldConnect` 为真
- **THEN** `CallControlManager::ConnectCallUiService(true)` 拉起通话界面服务（[callUi] 桩出口）

#### Scenario: 卫星高温等级
- **WHEN** 收到 "usual.event.thermal.satcomm.HIGH_TEMP_LEVEL"（发布者 UID 门控，订阅调用点 todo [broadcast]）
- **THEN** 因卫星通话不支持，原以 `satcomm_high_temp_level` 调 `SatelliteCallControl::SetSatcommTempLevel` 的分支移除，该事件仅记日志不作处理

#### Scenario: 超级隐私模式
- **WHEN** 收到 "usual.event.SUPER_PRIVACY_MODE"（发布者限 com.settings，订阅调用点 todo [broadcast]）
- **THEN** 因超级隐私不支持，原 `isInCall&&isHangup` 时 `CloseAllCall`、记旧模式并置变更标志后按 `isInCall`/`isAnswer`/dial 参数分别走 `CloseSuperPrivacyMode`/`CloseAnswerSuperPrivacyMode`/`CloseCallSuperPrivacyMode` 的分支移除，该事件仅记日志不作处理

#### Scenario: 蓝牙远端设备名更新
- **WHEN** 收到 `COMMON_EVENT_BLUETOOTH_REMOTEDEVICE_NAME_UPDATE`（订阅调用点 todo [broadcast]）
- **THEN** 因 BLUETOOTH 类型通话不支持，原以 `deviceAddr`/`remoteName` 调 `AudioDeviceManager::UpdateBluetoothDeviceName` 的分支移除，该事件仅记日志不作处理

#### Scenario: 用户切换
- **WHEN** 收到 `COMMON_EVENT_USER_SWITCHED`（订阅调用点 todo [broadcast]）且通话界面已连接
- **THEN** `DisconnectAbility` 后由新回调 `ReConnectAbility` 重连（[callUi] 桩出口）；原 `OsAccountManager::IsOsAccountVerified` 判定按 liteOS 单主帐号精简为默认主帐号常量；原 `StopFlashRemind` 联动因来电闪光不支持移除

#### Scenario: 系统关机
- **WHEN** 收到 `COMMON_EVENT_SHUTDOWN`（订阅调用点 todo [broadcast]）
- **THEN** `CallControlManager::DisconnectAllCalls`；原 `StopFlashRemind` 联动因来电闪光不支持移除

#### Scenario: HSDR 号码识别数据更新
- **WHEN** 收到 "usual.event.HSDR_EVENT"（发布者限 com.hsdr，订阅调用点 todo [broadcast]）且 data 含 "com.numberidentity.devicenumber"
- **THEN** `NumberIdentityServiceHelper::NotifyNumberMarkDataUpdate` 分发保留（数据供号码识别链使用，发布方调用点 todo [broadcast]）；仅防诈侧消费分支（`antifraud_hsdr_helper`）随防诈能力整删移除

#### Scenario: HFP 连接来电信息
- **WHEN** 收到 "usual.event.bluetooth.CONNECT_HFP_HF"
- **THEN** 因 BLUETOOTH 类型通话不支持且 `HFP_ASYNC_ENABLE` 为不支持宏，原先 `ConnectAbility` 再 `DelayedDisconnectCallConnectAbility`(3000000µs)、前台通话号码一致时直接更新 `SetCallerInfo`、否则 `BluetoothCallConnection::SetHfpContactName` 缓存名的订阅与处理分支移除，不订阅该事件

#### Scenario: 屏幕解锁
- **WHEN** 收到 `COMMON_EVENT_SCREEN_UNLOCKED`（订阅调用点 todo [broadcast]）且帐号校验（按 liteOS 单主帐号精简为默认主帐号常量）为未验证
- **THEN** 延迟 2000ms（经桩 EventHandler）后发布有序公共事件 `COMMON_EVENT_INCOMING_CALL_MISSED`（code 0，EventFwk 发布调用点 todo [broadcast]）；已验证则不作发布；原 `StopFlashRemind` 联动因来电闪光不支持移除

#### Scenario: 静音键
- **WHEN** 收到 "multimodal.event.MUTE_KEY_PRESS"（订阅调用点 todo [broadcast]）
- **THEN** `MUTE_KEY_PRESS` 映射与分发保留；原 `StopFlashRemind` 联动因来电闪光不支持移除，分发后仅记日志

#### Scenario: 未知事件
- **WHEN** action 不在任何已知映射
- **THEN** 走 `UnknownBroadcast` 仅记日志

## REMOVED Requirements

### Requirement: 防诈检测状态管理
**Reason**: AGENTS 功能范围明确"防诈 antifraud 相关代码无需迁移"，防诈能力整体删除（proposal 裁剪范围表 antifraud-call 移除项；design D7 删除 `services/antifraud` 全部源文件）。
**Migration**: 删除 `services/antifraud/` 下 `anonymize_adapter.cpp`、`antifraud_adapter.cpp`、`antifraud_cloud_service.cpp`、`antifraud_hsdr_helper.cpp`、`antifraud_service.cpp`，及 `call_status_manager.cpp` 中 `SetupAntiFraudService`/`StopAntiFraudDetect`/`TriggerAntiFraud`/`UpdateAntiFraudState` 实现与全部消费分支（`ActiveHandle` 启动判定、HOLDING/DISCONNECTING/DISCONNECTED 中的 `StopAntiFraudDetect`、检测结果触发与状态更新）；`ffrt::mutex` 保护随防诈实例与全仓去锁一并消失。恢复条件：目标平台引入防诈能力（外部防诈查询/云服务接口就绪）后按本 baseline 需求整块恢复。

### Requirement: 蓝牙通话上行预处理
**Reason**: AGENTS 功能范围明确不支持 BLUETOOTH 类型通话（特性宏 ABILITY_BLUETOOTH_SUPPORT 不支持，代码无需迁移；proposal 裁剪范围表 bluetooth-call 移除项）。
**Migration**: 删除 `HandleBluetoothCallReportInfo`/`BtCallDialingHandle`/`BtCallDialingHandleFirst`/`SetBtCallDialByPhone` 整链及 `call_status_manager` 主分发中的 `TYPE_BLUETOOTH` 预处理分支；`GetBtCallContactInfo` 蓝牙联系人派生分支在 `SetContactInfo` 中并删；`BluetoothCallService::GetCallState` 收尾调用点删除；相关源文件随 `services/bluetooth/`、`bluetooth_call.cpp`、`bluetooth_call_state.cpp` 删除（design D7 删除清单）。恢复条件：平台引入 BLUETOOTH 通话能力（HFP 通路）后按本 baseline 需求恢复。

### Requirement: 分布式协同判定
**Reason**: AGENTS 功能范围明确不支持分布式（distributed 及 interoperable）通话（SUPPORT_DSOFTBUS 不支持；proposal 裁剪范围表 distributed-call/interoperable-call 移除项；design D7 删除 `services/distributed_call/`、`services/interoperable_call/` 全部源文件）。
**Migration**: 删除 `IsDcCallConneceted`/`IsDistributeCallSourceStatus` 谓词与 `SetDistributedDeviceDialing` 分支（`DialingHandle`/`AlertHandle`/`ActiveHandle` 对象缺失补建与 extraParams "isDistributedDeviceDialing" 写点）；`distributed_modem_state` 设置项查询链与 `DistributedCommunicationManager::IsSinkRole` sink 判定一并删除；对账与断开善后中对分布式管理器的观察者/联动调用点删除。恢复条件：平台具备 dsoftbus 分布式调制解调通路后按本 baseline 需求恢复。

### Requirement: 动作识别订阅联动
**Reason**: AGENTS 特性宏支持范围明确 OHOS_SUBSCRIBE_MOTION_ENABLE 不支持（代码无需迁移；design D7 删除 `utils` 下 `motion_recognition.cpp`、`screen_sensor_plugin.cpp` 并清 gni 部件块 `msdp_motion`）。
**Migration**: 删除 `StartInComingCallMotionRecognition`/`StartOutGoingCallMotionRecognition`/`StopCallMotionRecognition`/`IsCallMotionRecognitionEnable` 及 `IncomingHandle`/`DialingHandle`/`DisconnectedHandle` 中的订阅/退订调用点；`QUERY_MOTION_PICKUP_REDUCE_KEY`/`QUERY_MOTION_FLIP_MUTE_KEY`/`QUERY_MOTION_CLOSE_TO_EAR_KEY` 设置项查询与 `Rosen::LoadMotionSensor`/`MotionRecogntion::Subscribe*Sensor` 调用链删除。恢复条件：平台引入动作传感插件（msdp_motion）后按本 baseline 需求恢复。
