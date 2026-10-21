# call-object-management Specification

## Purpose
描述 `telephony_call_manager`（OpenHarmony v6.0 快照）中通话对象模型的"移植前现状"：全局通话对象表 `CallObjectManager`（`services/call/src/call_object_manager.cpp` + `include/call_object_manager.h`）、基类 `CallBase` 的属性与状态机（`call_base.cpp`）、载波通话对象 `CarrierCall`/`CSCall`/`IMSCall`（`carrier_call.cpp`/`cs_call.cpp`/`ims_call.cpp`）、VoIP 通话对象 `VoIPCall`（`voip_call.cpp`）、OTT 通话对象 `OTTCall`/`OTTCallConnection`（`ott_call.cpp`/`ott_call_connection.cpp`）、会议对象 `ConferenceBase`/`CsConference`/`ImsConference`/`OttConference`（`conference_base.cpp`/`cs_conference.cpp`/`ims_conference.cpp`/`ott_conference.cpp`）、视频状态对象 `VideoCallState` 及 `NetCallBase`（`video_call_state.cpp`/`net_call_base.cpp`）、蓝牙通话对象 `BluetoothCall`/`BluetoothCallState`（`bluetooth_call.cpp`/`bluetooth_call_state.cpp`）、卫星通话对象 `SatelliteCall`（`satellite_call.cpp`）、有线耳机按键 `CallWiredHeadSet`（`call_wired_headset.cpp`）。本规格只覆盖对象层；蓝牙/卫星的管理链路（`bluetooth_call_manager`、`satellite_call_control` 等）不在本能力范围内。

控制本能力行为的构建开关（均已逐点 rg 核实场点）：
- `NOT_SUPPORT_MULTICALL`：由 `BUILD.gn` 的 `declare_args` 变量 `call_manager_feature_not_support_multicall` 控制；场点为 `call_object_manager.h`（声明 `IsTwoCallBtCallAndESIM`/`IsTwoCallBtCall`/`IsTwoCallESIMCall`/`IsOneNumberDualTerminal`）与 `call_object_manager.cpp`（`CALL_MAX_COUNT=2`、`IsNewCallAllowedCreate` 内 callNum=1、上述判定族实现）。
- `ABILITY_CONFIG_SUPPORT`：场点 `ims_call.cpp`（`IsSupportVideoCall`）、`cs_conference.cpp`/`ims_conference.cpp`/`ott_conference.cpp`（会议成员上限改读配置项）。本仓 `BUILD.gn`/`callmanager.gni` 未定义该宏，相关分支恒关闭，会议上限恒为常量 `CS_CONFERENCE_MAX_CALLS_CNT`。
- `ABILIT_CONFIG_SUPPORT`（上游拼写变体宏）：场点 `cs_call.cpp`/`ims_call.cpp`（`IsSupportConferenceable`）、`ott_call.cpp`；本仓同样未定义，恒关闭。

## Requirements

### Requirement: 全局通话对象表的生命周期管理
系统 SHALL 以 `CallObjectManager` 的静态 `callObjectPtrList_`（`std::list<sptr<CallBase>>`，`listMutex_` 互斥）作为全部通话对象的唯一全局表，通过 `AddOneCallObject`/`DeleteOneCallObject` 维护，并在表从空到非空、非空到空时联动通话界面连接与有线耳机初始化。

#### Scenario: 新增对象唯一性
- **WHEN** `AddOneCallObject` 收到的通话对象 callId 与表内已有对象重复
- **THEN** 返回 `CALL_ERR_PHONE_CALL_ALREADY_EXISTS`，不修改对象表

#### Scenario: 首个通话拉起通话界面
- **WHEN** 对象表从 `NO_CALL_EXIST`（0）添加第一个通话对象，且 CallControlManager 报告的 VoIP 状态不是 `CALL_STATE_RINGING`，或该对象 `isEcc` 为真
- **THEN** 调用 `CallConnectAbility::ConnectAbility()` 拉起通话界面

#### Scenario: 首个通话触发有线耳机注册
- **WHEN** 添加后对象表大小为 `ONE_CALL_EXIST`（1）
- **THEN** 调用 `CallWiredHeadSet::Init()` 注册耳机按键；若队头通话为 `CALL_STATUS_DIALING` 则置 `isFirstDialCallAdded_ = true` 并 `cv_.notify_all()` 唤醒拨号失败等待方

#### Scenario: 删除至空表延迟断开界面
- **WHEN** `DeleteOneCallObject`（callId 重载或对象指针重载）使对象表变空，且 `CallControlManager::ShouldDisconnectService()` 为真
- **THEN** 先调用 `CallWiredHeadSet::DeInit()` 注销耳机按键，再经 `DelayedDisconnectCallConnectAbility`（`ffrt::submit_h` 延迟 `DISCONNECT_DELAY_TIME` 2000000 微秒）在延迟到期时复查对象表仍为空后调用 `CallConnectAbility::DisconnectAbility()`

#### Scenario: 删除不存在的 callId
- **WHEN** `DeleteOneCallObject(int32_t)` 未找到对应 callId 的对象
- **THEN** 仍返回 `TELEPHONY_SUCCESS`（对象表不变）

#### Scenario: 折叠屏监听联动（移植关注点）
- **WHEN** 添加或删除通话使对象表跨越 0/1 边界，且 `FoldStatusManager::IsSmallFoldDevice()` 判定为小折叠设备
- **THEN** 对应注册/注销 `FoldStatusManager` 的折叠监听（非折叠设备不触发）

### Requirement: callId 分配与多维度对象检索
系统 SHALL 由 `GetNewCallId` 从静态 `callId_`（初始 `CALL_START_ID` = 0）自增分配新 callId，并提供按 callId、号码、运行态、index、slotId、callType、VoIP callId 的检索函数族。

#### Scenario: callId 单调自增
- **WHEN** 连续调用 `GetNewCallId`
- **THEN** 每次返回 `++callId_`，先后分配的 callId 严格递增且不复用

#### Scenario: 按号码检索剥离后拨段
- **WHEN** 调用 `GetOneCallObject(std::string &phoneNumber)` 或 `IsCallExist(phoneNumber)` 检索
- **THEN** 对表内每个对象的 `GetAccountNumber()` 先经 `CallNumberUtils::RemovePostDialPhoneNumber` 剥离后拨号段再与目标号码比较；命中返回对象/true，全部未命中返回 nullptr/false（号码为空直接返回 nullptr/false）

#### Scenario: 按 index+slotId+callType 检索的蓝牙特例
- **WHEN** `GetOneCallObjectByIndexSlotIdAndCallType` 的 callType 为 `TYPE_BLUETOOTH`
- **THEN** 匹配条件为 callType==TYPE_BLUETOOTH 且 callIndex 相等且（slotId 相等 或 `GetPhoneOrWatchDial()` 等于 `PhoneOrWatchDial::WATCH_DIAL`）；为其他 callType 时匹配非蓝牙、非 VoIP、callIndex 与 slotId 均相等的对象

#### Scenario: 按运行态检索
- **WHEN** 调用 `GetOneCallObject(CallRunningState)` 或 `GetOneCarrierCallObject(CallRunningState)`
- **THEN** 均从表尾反向扫描取最近一个运行态匹配的对象；后者额外要求对象 `GetCallType() != TYPE_VOIP`

#### Scenario: 按 VoIP 三元组检索
- **WHEN** 调用 `GetOneCallObjectByVoipCallId(voipCallId, bundleName, uid)`
- **THEN** 仅在 `TYPE_VOIP` 对象中按 `VoIPCall::GetVoipCallId`/`GetVoipBundleName`/`GetVoipUid` 三元组精确匹配

### Requirement: VoIP 通话信息表
系统 SHALL 为 VoIP（畅连/meetime）维护独立于对象表的 `voipCallObjectList_`（`std::map<int32_t, CallAttributeInfo>`，callId→属性），由 `AddOneVoipCallObject`/`DeleteOneVoipCallObject`/`UpdateOneVoipCallObjectByCallId` 维护。

#### Scenario: 增删改
- **WHEN** 向 map 添加已存在 callId / 删除或更新不存在 callId
- **THEN** 分别返回 `CALL_ERR_PHONE_CALL_ALREADY_EXISTS` / `TELEPHONY_ERROR`；新 callId 添加成功、已存在 callId 的状态更新返回 `TELEPHONY_SUCCESS`

#### Scenario: 状态存在性查询
- **WHEN** 调用无参 `IsVoipCallExist`，或带状态的 `IsVoipCallExist(TelCallState, int32_t &callId)`
- **THEN** 前者返回 map 是否非空；后者在 map 中找到首个指定状态的条目时输出其 callId 并返回 true

#### Scenario: 属性读取与清理
- **WHEN** 调用 `GetVoipCallInfo`/`GetActiveVoipCallInfo`/`ClearVoipList`
- **THEN** 前两者分别返回 map 首个条目与首个 `CALL_STATUS_ACTIVE` 条目（无命中返回零值结构）；`ClearVoipList` 清空 map 并调用 `CallControlManager::SetVirtualCall(true)`

#### Scenario: 信息列表导出受 meetee 状态门控
- **WHEN** `GetVoipCallInfoList` 被 `GetCallInfoList`/`GetAllCallInfoList` 调用
- **THEN** 仅当 `CallControlManager::GetMeetimeCallState()` 为 `CALL_STATUS_INCOMING`、`CALL_STATUS_IDLE` 或 `CALL_STATUS_ALERTING` 时才把 map 条目追加进导出结果

### Requirement: 新建通话约束判定
系统 SHALL 由 `HasNewCall` 与 `IsNewCallAllowedCreate` 判定当前是否允许发起新建通话。

#### Scenario: 拨号中存在未完成新通话
- **WHEN** 对象表中存在 `GetCallType() != TYPE_VOIP` 且运行态为 `CALL_RUNNING_STATE_CREATE`/`CALL_RUNNING_STATE_CONNECTING`/`CALL_RUNNING_STATE_DIALING` 的对象，或任意 `TYPE_SATELLITE` 对象
- **THEN** `HasNewCall` 返回 `CALL_ERR_CALL_COUNTS_EXCEED_LIMIT`

#### Scenario: 已有振铃通话时禁止再建
- **WHEN** `IsNewCallAllowedCreate` 扫描到非 VoIP 的 CREATE/CONNECTING/DIALING/RINGING 通话
- **THEN** 输出 enabled=false 并返回 `TELEPHONY_ERR_SUCCESS`

#### Scenario: 载波通话数量上限
- **WHEN** 扫描通过后统计载波通话数（会议成员按主叫去重：会议非 `TEL_CONFERENCE_IDLE` 且 callId 等于 `ImsConference::GetMainCall()` 计 1，非会议通话计 1），统计值达到上限
- **THEN** enabled=false；上限默认为 2，定义 `NOT_SUPPORT_MULTICALL` 时为 1

### Requirement: 通话存在性与计数谓词族
系统 SHALL 提供统一的存在性/计数/属性导出谓词：`HasCallExist`、`HasCellularCallExist`、`HasVoipCallExist`、`HasSatelliteCallExist`/`GetSatelliteCallList`、`HasEmergencyCall`、`HasRingingCall`/`HasHoldCall`、`HasRingingMaximum`/`HasDialingMaximum`、`IsCallExist` 重载族、`IsConferenceCallExist`、`HasActivedCallExist`、`GetCallNum`/`GetCallNumber`、`GetCarrierCallList`/`GetVoipCallList`/`GetCurrentCallNum`、`GetCallInfoList`/`GetAllCallInfoList`。

#### Scenario: 蜂窝通话存在判定
- **WHEN** 调用 `HasCellularCallExist`
- **THEN** 仅当存在 callType 为 `TYPE_CS`/`TYPE_IMS`/`TYPE_SATELLITE`/`TYPE_BLUETOOTH` 且 `TelCallState` 既非 `CALL_STATUS_DISCONNECTED` 也非 `CALL_STATUS_DISCONNECTING` 的对象时返回 true

#### Scenario: 振铃/拨号数量上限判定
- **WHEN** 调用 `HasRingingMaximum`/`HasDialingMaximum`
- **THEN** 分别统计 `CALL_RUNNING_STATE_RINGING`/`CALL_RUNNING_STATE_ACTIVE` 数量（注释语义为拨号路数），达到 `RINGING_CALL_NUMBER_LEN`/`DIALING_CALL_NUMBER_LEN`（均=30）返回 true

#### Scenario: 活动通话查找的 VoIP 兜底
- **WHEN** 调用 `HasActivedCallExist(callId, isIncludeCallServiceKitCall)` 且对象表中无匹配
- **THEN** 继续从 `voipCallObjectList_` 取活动 VoIP 条目，其 callId >= `VOIP_CALL_MINIMUM`（10000）时输出该 callId 并返回 true

#### Scenario: 按状态统计与号码/列表导出
- **WHEN** 调用 `GetCallNum(callState, isIncludeVoipCall)`/`GetCallNumber`/`GetCarrierCallList`/`GetVoipCallList`
- **THEN** 统计/取号时按 isIncludeVoipCall 决定是否跳过 `TYPE_VOIP` 对象；列表函数分别导出 CS/IMS/SATELLITE/BLUETOOTH 的 callId 与 VOIP 的 callId

#### Scenario: 其余单项谓词
- **WHEN** 调用 `GetCallState(callId)`（未命中返回 `CALL_STATUS_IDLE`）、`GetCallNumByRunningState(callState)`、`GetVoipCallNum`、`UpdateOneCallObjectByCallId(callId, nextState)`（对匹配对象逐个 `SetTelCallState`）
- **THEN** 分别返回该通话的 `TelCallState`、指定运行态计数、对象表内 VOIP 计数、无返回值的就地状态更新

#### Scenario: 按 slot 导出属性列表
- **WHEN** 调用 `GetCallInfoList(slotId, isIncludeVoipCall)`
- **THEN** 导出 accountId==slotId 且 callType != TYPE_OTT 且（isIncludeVoipCall 或 callType != TYPE_VOIP）的对象属性，并追加 `GetVoipCallInfoList` 结果；`GetAllCallInfoList` 不限 slotId 导出全表

### Requirement: 前台通话选择
系统 SHALL 提供 `GetForegroundCall`/`GetForegroundLiveCall`/`GetIncomingCall`/`GetForegroundLiveCallByCallId`/`GetAudioLiveCall` 的前台通话选择逻辑，供音频、UI 与控制路径取"当前通话"。

#### Scenario: 前台通话优先级
- **WHEN** 调用 `GetForegroundCall(isIncludeVoipCall)`
- **THEN** 顺序扫描：命中 `CALL_STATUS_WAITING`/`CALL_STATUS_INCOMING` 立即返回；`CALL_STATUS_ALERTING`/`CALL_STATUS_DIALING`/`CALL_STATUS_ACTIVE`/`CALL_STATUS_HOLDING` 则记录并继续（后者覆盖前者）；扫描结束返回最后记录者

#### Scenario: 前台活动通话
- **WHEN** 调用 `GetForegroundLiveCall(isIncludeVoipCall)`
- **THEN** 顺序扫描，命中 `CALL_STATUS_ACTIVE` 或 `CALL_STATUS_ALERTING`/`CALL_STATUS_DIALING` 立即返回该对象；`GetForegroundLiveCallByCallId` 在此基础上要求 callId 匹配

#### Scenario: 来电对象与音频活动通话回退链
- **WHEN** 调用 `GetIncomingCall(isIncludeVoipCall)` 或 `GetAudioLiveCall`
- **THEN** 前者返回首个 `CALL_STATUS_INCOMING`/`CALL_STATUS_WAITING` 对象；后者依次尝试 `GetForegroundLiveCall(false)` → `GetForegroundLiveCall(true)` → `GetIncomingCall(false)`，取第一个非空结果

### Requirement: 来电铃声形态与免打扰静默判定
系统 SHALL 由 `HasIncomingCallCrsType`、`HasIncomingCallVideoRingType`+`IsVideoRing`、`HasVideoCall`、`IsNeedSilentInDoNotDisturbMode` 判定当前来电的铃声/彩振/视频形态与静默需求。

#### Scenario: 视频彩振来电
- **WHEN** 调用 `HasIncomingCallCrsType`
- **THEN** 存在 `CALL_RUNNING_STATE_RINGING` 且 `GetCrsType() == CRS_TYPE`（2）的对象时返回 true

#### Scenario: 视频铃声来电
- **WHEN** 调用 `HasIncomingCallVideoRingType`，某非 VoIP 振铃对象的联系人 `personalNotificationRingtone` 以 `.mp4` 结尾或 `ringtonePath` 等于 `"system_video_ring"`
- **THEN** `IsVideoRing` 返回 true，该函数返回 true

#### Scenario: 存在视频通话
- **WHEN** 调用 `HasVideoCall`
- **THEN** 存在 `GetVideoStateType() == TYPE_VIDEO` 且非 `TYPE_VOIP` 的对象时返回 true

#### Scenario: 免打扰静默
- **WHEN** 调用 `IsNeedSilentInDoNotDisturbMode`，前台通话（不含 VoIP）处于 `CALL_STATUS_INCOMING` 且其 `GetExtraParams()` 中 `"IsNeedSilentInDoNotDisturbMode"` 整型参数为 1
- **THEN** 返回 true；前台通话为空或非来电状态返回 false

### Requirement: 拨号暂态共享与失败拨号处理
系统 SHALL 在 `CallObjectManager` 上保存跨模块共享的拨号暂态（`dialCallInfo_`、`needWaitHold_`、`isFirstDialCallAdded_`，供 `CallRequestProcess`/`CallStatusManager` 消费），并由 `GetDialCallInfo`/`DealFailDial` 提供读取与失败上报。

#### Scenario: 读取暂存的拨号信息
- **WHEN** 调用 `GetDialCallInfo`
- **THEN** 返回静态 `dialCallInfo_`（由 `CallRequestProcess::HandleStartDial` 在 DSDA 等待保持场景暂存的 `CellularCallInfo`）

#### Scenario: 失败拨号补报断开
- **WHEN** 调用 `DealFailDial(call)`
- **THEN** 以该对象的 callType/slotId/videoState/号码构造 `CALL_STATUS_DISCONNECTED` 的 `CallDetailInfo` 并经 `ReportCallInfoHandler::UpdateCallReportInfo` 上报；号码长度超过 `kMaxNumberLen` 返回 `CALL_ERR_NUMBER_OUT_OF_RANGE`

### Requirement: CallBase 呼叫状态机
系统 SHALL 由 `CallBase::SetTelCallState` 驱动外部上报的 `TelCallState` 到本地 `CallRunningState`/时间戳字段的转移（`StateChangesToDialing` 等私有函数），重复状态返回 `CALL_ERR_NOT_NEW_STATE`。

#### Scenario: 状态重复上报
- **WHEN** 对象运行态已非 `CALL_RUNNING_STATE_CREATE` 且 `SetTelCallState` 收到与当前 `callState_` 相同的目标状态（`CALL_STATUS_DIALING` 例外）
- **THEN** 记录状态重复并返回 `CALL_ERR_NOT_NEW_STATE`

#### Scenario: 拨号/回铃态
- **WHEN** 状态置为 `CALL_STATUS_DIALING` 或 `CALL_STATUS_ALERTING`
- **THEN** 运行态均转为 `CALL_RUNNING_STATE_DIALING`；ALERTING 时记录 `ringBeginTime_`，DIALING 时不记

#### Scenario: 来电/等待态
- **WHEN** 状态置为 `CALL_STATUS_INCOMING` 或 `CALL_STATUS_WAITING`
- **THEN** 运行态转为 `CALL_RUNNING_STATE_RINGING` 并记录 `ringBeginTime_`

#### Scenario: 激活态与计时
- **WHEN** 状态置为 `CALL_STATUS_ACTIVE` 且 `callBeginTime_` 尚为 0
- **THEN** 运行态转 `CALL_RUNNING_STATE_ACTIVE`，`callBeginTime_` 与 `ringEndTime_` 同取当前时间，`answerType_` 置 `CALL_ANSWER_ACTIVED`；`startTime_` 对 VoIP 通话取 gettimeofday 毫秒值、其他通话取 `callBeginTime_`

#### Scenario: 保持/断开态与会议联动
- **WHEN** 状态置为 `CALL_STATUS_HOLDING`/`CALL_STATUS_DISCONNECTING`/`CALL_STATUS_DISCONNECTED`
- **THEN** 运行态分别转 HOLD/ENDING/ENDED；HOLDING 时会议态从 `TEL_CONFERENCE_ACTIVE` 改写为 `TEL_CONFERENCE_DISCONNECTED`，DISCONNECTING 时会议态 ACTIVE 改写为 DISCONNECTING，DISCONNECTED 时会议态 DISCONNECTING/ACTIVE 改写为 DISCONNECTED 并记录 `callEndTime_`（`ringEndTime_` 为 0 时补记）

### Requirement: CallBase 基础生命周期钩子与属性导出
系统 SHALL 提供 `DialCallBase`/`IncomingCallBase`/`AnswerCallBase`/`RejectCallBase` 四个基础钩子与 `GetCallAttributeBaseInfo` 属性导出；钩子在派生类流程前置调用，属性导出汇总对象的全部对外字段。

#### Scenario: 拨号前置与 VoIP 抢占
- **WHEN** 调用 `DialCallBase`
- **THEN** 运行态转 `CALL_RUNNING_STATE_CONNECTING`，并经 `ffrt::submit` 异步执行 `HangUpVoipCall`：遍历全表 VoIP 对象，ACTIVE 的跳过、INCOMING 的 `RejectCall`、其余以 `ErrorReason::CELLULAR_CALL_EXISTS` 挂断

#### Scenario: 来电前置
- **WHEN** 调用 `IncomingCallBase`
- **THEN** 运行态转 `CALL_RUNNING_STATE_RINGING`，返回 `TELEPHONY_SUCCESS`

#### Scenario: 应答/拒接前置校验
- **WHEN** 调用 `AnswerCallBase` 时对象非 `CALL_RUNNING_STATE_RINGING`，或调用 `RejectCallBase`
- **THEN** 前者返回 `CALL_ERR_PHONE_ANSWER_IS_BUSY`；后者恒成功并把 `answerType_` 置 `CALL_ANSWER_REJECT`

#### Scenario: 属性导出
- **WHEN** 调用 `GetCallAttributeBaseInfo(info)`
- **THEN** 填充 accountNumber/videoState/startTime/callType/callId/callState/conferenceState/各时间戳/callDirection/answerType/accountId/crsType/originalCallType/isEccContact/celiaCallType/numberLocation/contactName/numberMarkInfo/blockReason/bundleName/detectDetails/phoneOrWatch，并把 `extraParams_` 序列化后解析出 name/namePresentation/antiFraudState；`antiFraudState` 为 `ANTIFRAUD_STATE_RISK` 时把 `numberMarkInfo.markType` 改写为 `MARK_TYPE_FRAUD_RISK`；号码超 `kMaxNumberLen` 时不填充直接返回

### Requirement: CarrierCall 载波通话公共行为
系统 SHALL 由 `CarrierCall`（`slotId_` 取 `info.accountId`，`index_` 取 `info.index`，`isEcc_` 取 `info.isEcc`，持有 `CellularCallConnection` 单例）承载 CS/IMS/卫星/蓝牙共用的拨号、应答、拒接、挂断、保持、恢复、切换、静音、DTMF 与会议出口转发。

#### Scenario: 控制指令经 CellularCallConnection 转发
- **WHEN** 调用 `CarrierAnswerCall`/`CarrierRejectCall`/`CarrierHangUpCall`/`CarrierHoldCall`/`CarrierUnHoldCall`/`CarrierSwitchCall`/`CarrierSetMute`/`StartDtmf`/`StopDtmf`/`PostDialProceed`/`CarrierCombineConference`/`CarrierSeparateConference`/`CarrierKickOutFromConference`
- **THEN** 均先 `PackCellularCallInfo`（callId/callType/videoState/index/slotId=accountId/号码，超长返回 `CALL_ERR_NUMBER_OUT_OF_RANGE`）再转发到 `cellularCallConnectionPtr_` 对应接口；`CarrierHangUpCall` 按 `GetPolicyFlag()` 选择 `POLICY_FLAG_HANG_UP_ACTIVE`→`TYPE_HANG_UP_ACTIVE`、`POLICY_FLAG_HANG_UP_HOLD_WAIT`→`TYPE_HANG_UP_HOLD_WAIT`、否则 `TYPE_DEFAULT` 的挂断补充类型

#### Scenario: 拨号流程失败回滚
- **WHEN** 调用 `CarrierDialingProcess` 且 `DialCallBase` 失败
- **THEN** 调用 `CarrierHangUpCall` 回滚后返回原错误码

#### Scenario: 属性与紧急状态
- **WHEN** 调用 `GetCallAttributeCarrierInfo`/`GetEmergencyState`
- **THEN** 前者在 `GetCallAttributeBaseInfo` 基础上补充 isEcc/slotId/index；后者返回 `isEcc_`

#### Scenario: 紧急呼叫禁入会议
- **WHEN** 调用 `CarrierCall::IsSupportConferenceable` 且对象为紧急呼叫
- **THEN** 返回 `CALL_ERR_EMERGENCY_UNSUPPORT_CONFERENCEABLE`，否则返回 `TELEPHONY_SUCCESS`

### Requirement: IMSCall 通话对象
系统 SHALL 由 `IMSCall` 在 `CarrierCall` 之上提供 RTT 发起/停止、视频升级支持判定与媒体模式协商转发。

#### Scenario: RTT 发起与停止
- **WHEN** 调用 `StartRtt(msg)`/`StopRtt`
- **THEN** `PackCellularCallInfo` 后转发 `CellularCallConnection::StartRtt`/`StopRtt`；失败分别返回 `CALL_ERR_STARTRTT_FAILED`/`CALL_ERR_STOPRTT_FAILED`

#### Scenario: 视频升级支持判定
- **WHEN** 调用 `IsSupportVideoCall`
- **THEN** 默认支持（`ABILITY_CONFIG_SUPPORT` 分支改读 `GetCarrierConfig(ITEM_VIDEO_CALL)`，该宏本仓未定义恒关闭）；当前处于 `CALL_STATUS_INCOMING` 或 `GetEmergencyState()` 为真时强制返回 false

#### Scenario: 媒体模式协商收发
- **WHEN** 调用 `SendUpdateCallMediaModeRequest`/`SendUpdateCallMediaModeResponse`/`RecieveUpdateCallMediaModeRequest`/`ReceiveUpdateCallMediaModeResponse`
- **THEN** 均经 `videoCallState_` 状态对象分发或直接转发 `CellularCallConnection`；对端响应非 `TYPE_REQUEST_SUCCESS` 时本地回退按 `CALL_MODE_AUDIO_ONLY` 处理

#### Scenario: 视频扩展指令转发
- **WHEN** 调用 `ControlCamera`/`SetPreviewWindow`/`SetDisplayWindow`/`SetPausePicture`/`SetDeviceDirection`/`RequestCameraCapabilities`/`CancelCallUpgrade`
- **THEN** 均以 `GetSlotId()`+`GetCallIndex()` 转发 `CellularCallConnection` 对应接口

### Requirement: IMSCall 视频状态对象与 NetCallBase
系统 SHALL 由 `IMSCall::InitVideoCall` 构造 5 个 `VideoCallState` 子类对象（`AudioOnlyState`/`VideoSendState`/`VideoReceiveState`/`VideoSendReceiveState`/`VideoPauseState`，按 `ImsCallMode` 建 `videoStateMap_`），由 `UpdateImsCallMode` 依当前 `VideoUpdateStatus` 分发请求或响应，并经 `SwitchVideoState` 切换状态对象；`NetCallBase` 为状态对象提供会议占位接口（全部直通 `TELEPHONY_SUCCESS`）。

#### Scenario: 视频状态初始化
- **WHEN** 调用 `InitVideoCall`（幂等，`isInitialized_` 置位后仅重选当前状态）
- **THEN** 按 `GetVideoStateType()`（TYPE_VOICE/SEND_ONLY/RECEIVE_ONLY/TYPE_VIDEO，缺省语音）经 `AssignVideoCallState` 选中 `videoCallState_`

#### Scenario: 媒体模式更新分发
- **WHEN** `UpdateImsCallMode` 在通话非 `CALL_STATUS_ACTIVE` 或 `videoCallState_` 为空时调用
- **THEN** 分别返回 `CALL_ERR_CALL_STATE`/`TELEPHONY_ERR_LOCAL_PTR_NULL`；状态为 `STATUS_NONE` 时走 `SendUpdateCallMediaModeRequest`，为 `STATUS_RECV_REQUEST` 时走 `SendUpdateCallMediaModeResponse`

#### Scenario: 纯语音态发起视频升级
- **WHEN** `AudioOnlyState::SendUpdateCallMediaModeRequest(CALL_MODE_SEND_RECEIVE)`，通话支持视频（`IsCallSupportVideoCall`）且 `VideoUpdateStatus` 为 `STATUS_NONE`
- **THEN** 下发请求并把状态置 `STATUS_SEND_REQUEST`；不支持视频返回 `CALL_ERR_VIDEO_NOT_SUPPORTED`，更新中返回 `CALL_ERR_VIDEO_IN_PROGRESS`

#### Scenario: 纯语音态收到升级请求
- **WHEN** `AudioOnlyState::RecieveUpdateCallMediaModeRequest` 收到 `CALL_MODE_RECEIVE_ONLY`/`CALL_MODE_SEND_RECEIVE`
- **THEN** 状态非 NONE 时返回 `CALL_ERR_VIDEO_IN_PROGRESS`；`CALL_MODE_SEND_RECEIVE` 且不支持视频时回 `CALL_MODE_AUDIO_ONLY` 响应并返回 `CALL_ERR_VIDEO_ILLEAGAL_SCENARIO`；否则上报应用并把状态置 `STATUS_RECV_REQUEST`

#### Scenario: 已连接视频态的降级/暂停
- **WHEN** `VideoSendReceiveState`/`VideoPauseState`/`VideoSendState`/`VideoReceiveState` 收到 `CALL_MODE_AUDIO_ONLY`/`CALL_MODE_VIDEO_PAUSED` 等模式请求或响应
- **THEN** 各子类按 `video_call_state.cpp` 的 switch 矩阵分发：合法路径经 `SwitchCallVideoState` 切换状态对象并复位 `VideoUpdateStatus`，非法/进行中路径返回 `CALL_ERR_VIDEO_ILLEAGAL_SCENARIO`/`CALL_ERR_VIDEO_IN_PROGRESS`/`CALL_ERR_VIDEO_ILLEGAL_MEDIA_TYPE`

### Requirement: VoIPCall 通话对象
系统 SHALL 由 `VoIPCall`（继承 `CarrierCall`，构造时从 `info.voipCallInfo` 提取 voipCallId/userName/userProfile/abilityName/extensionId/voipBundleName/uid 等畅连字段）承载 VoIP 通话的对象行为，控制指令经 `VoipCallConnection` 出口。

#### Scenario: 拨号/保持/切换空实现
- **WHEN** 调用 `DialingProcess`/`HoldCall`/`UnHoldCall`/`SwitchCall` 及全部会议族接口（`CombineConference` 等 14 个）
- **THEN** 直接返回 `TELEPHONY_SUCCESS`，不产生任何外部调用

#### Scenario: 应答/拒接/挂断经 VoipCallConnection
- **WHEN** 调用 `AnswerCall`/`RejectCall`/`HangUpCall()`
- **THEN** `PackVoipCallInfo`（voipCallId/bundleName/uid）后转发 `VoipCallConnection::AnswerCall`/`RejectCall`/`HangUpCall`；无参 `HangUpCall` 固定携带 `ErrorReason::USER_ANSWER_CELLULAR_FIRST`

#### Scenario: 带原因挂断
- **WHEN** 调用 `HangUpCall(const ErrorReason &status)`（由 `CallBase::HangUpVoipCall` 抢占场景使用）
- **THEN** 携带传入原因转发 `VoipCallConnection::HangUpCall`

#### Scenario: VoIP 静音
- **WHEN** 调用 `SetMute(mute, slotId)`
- **THEN** 以 "bundleName:uid:voipCallId" 拼接 voipCallId，按 mute 取 `CallAudioEvent::AUDIO_EVENT_MUTED`/`AUDIO_EVENT_UNMUTED` 经 `VoipCallConnection::SendCallUiEvent` 上报

#### Scenario: 属性导出与麦克风权限更新
- **WHEN** 调用 `GetCallAttributeInfo` 或 `UpdateCallAttributeInfo`
- **THEN** 前者在载波属性之上回填 `voipCallInfo` 全部畅连字段；后者仅在 `hasMicPermission` 变化时更新本地值

### Requirement: 会议对象模型与 CS/IMS 会议联动
系统 SHALL 由 `ConferenceBase`（mainCallId_ 初始 `ERR_ID`、state_ 初始 `CONFERENCE_STATE_IDLE`、`subCallIdSet_` 成员集合）及 `CsConference`/`ImsConference`（maxSubCallLimits_ 初始 `CS_CONFERENCE_MAX_CALLS_CNT`=5，`ABILITY_CONFIG_SUPPORT` 恒关闭）承载会议成员管理，并由 `CSCall`/`IMSCall` 的会议接口联动对象会议态。

#### Scenario: 主叫设置与成员查询
- **WHEN** 调用 `SetMainCall`（callId < `ERR_ID` 返回 `CALL_ERR_INVALID_CALLID`）、`GetSubCallIdList(callId, list)`、`GetCallIdListForConference(callId, list)`
- **THEN** 后两者在 callId 不在成员集合（`GetCallIdListForConference` 还接受 callId==mainCallId_）时清空列表并返回 `CALL_ERR_THE_CALL_IS_NOT_IN_THE_CONFERENCE`，否则导出成员（后者额外包含 mainCallId_）

#### Scenario: 加入/退出会议
- **WHEN** 调用 `CsConference`/`ImsConference` 的 `JoinToConference`（要求 state_ 为 CREATING/ACTIVE/LEAVING/HOLDING 之一，否则 `CALL_ERR_ILLEGAL_CALL_OPERATION`）或 `LeaveFromConference`
- **THEN** 加入后置 `CONFERENCE_STATE_ACTIVE` 并记录 beginTime_；退出时移除成员，若退出者为主叫则取集合首个为新主叫；集合空时 mainCallId_=ERR_ID、state_=IDLE、beginTime_=0；退出不在集合的 callId 返回 `CALL_ERR_CONFERENCE_SEPERATE_FAILED`

#### Scenario: 保持会议与容量/可操作校验
- **WHEN** 调用 `HoldConference`（HOLDING 幂等成功；callId 不在集合或集合空返回 `CALL_ERR_CONFERENCE_SEPERATE_FAILED`）或 `CanCombineConference`（成员数 >= maxSubCallLimits_ 返回 `CALL_ERR_CONFERENCE_CALL_EXCEED_LIMIT`）/`CanSeparateConference`（成员空返回 `CALL_ERR_CONFERENCE_NOT_EXISTS`、非 ACTIVE 返回 `CALL_ERR_CONFERENCE_CALL_IS_NOT_ACTIVE`）/`CanKickOutFromConference`（成员空返回 `CALL_ERR_CONFERENCE_NOT_EXISTS`）
- **THEN** CsConference 与 ImsConference 行为一致（两个单例语义相同，仅 conferenceType_ 与配置项名不同）

#### Scenario: CSCall/IMSCall 会议发起与失败恢复
- **WHEN** 调用 `CSCall::CombineConference`/`IMSCall::CombineConference`
- **THEN** 先 `SetMainCall(GetCallID())`，若会议单例状态已是 `CONFERENCE_STATE_CREATING` 则跳过并返回成功（防重入），否则置 CREATING 后经 `CarrierCombineConference` 转发蜂窝

#### Scenario: 会议态联动
- **WHEN** 调用 `LaunchConference`/`ExitConference`/`HoldConference`（CSCall/IMSCall 层）
- **THEN** 分别经会议单例 `JoinToConference`/`LeaveFromConference`/`HoldConference` 成功后把对象 `TelConferenceState` 置 `TEL_CONFERENCE_ACTIVE`/`TEL_CONFERENCE_IDLE`/`TEL_CONFERENCE_HOLDING`

#### Scenario: 合并失败回滚
- **WHEN** 调用 `HandleCombineConferenceFailEvent`
- **THEN** 成员集合空时 `SetMainCall(ERR_ID)`，否则取集合首个为主叫；会议状态恢复 `GetOldConferenceState()`

### Requirement: OTT 通话与会议对象
系统 SHALL 由 `OTTCall`（直接继承 `CallBase`）+`OTTCallConnection`（经 `CallAbilityReportProxy::OttCallRequest` 向应用上报请求）+`OttConference` 承载 OTT 类型通话与会议的对象行为。

#### Scenario: 控制指令上报应用
- **WHEN** 调用 `OTTCall` 的 `AnswerCall`/`RejectCall`/`HangUpCall`/`HoldCall`/`UnHoldCall`/`SwitchCall`/`CombineConference`/`SeparateConference`/`KickOutFromConference`
- **THEN** `PackOttCallRequestInfo`（号码/bundleName/videoState）后经 `OTTCallConnection` 以对应 `OttCallRequestId`（OTT_REQUEST_ANSWER 等）上报；拨打经 `CallRequestProcess::OttDialProcess` 走 `OTT_REQUEST_DIAL`

#### Scenario: 不支持能力固定返回
- **WHEN** 调用 `StartDtmf`/`StopDtmf`/`PostDialProceed`/`GetSlotId` 及视频族/媒体模式族/`SetMute`
- **THEN** 分别返回 `CALL_ERR_FUNCTION_NOT_SUPPORTED`/`CALL_ERR_ILLEGAL_CALL_OPERATION`

#### Scenario: OTT 会议成员管理
- **WHEN** 调用 `OttConference::JoinToConference`（state_ 需为 CREATING/ACTIVE/LEAVING，不含 HOLDING）
- **THEN** 加入置 ACTIVE；`HoldConference` 会把 callId 从成员集合移除（与 CS/IMS 不同）；容量/可分离/可踢出校验与 `CS_CONFERENCE_MAX_CALLS_CNT` 上限逻辑同 CS/IMS；`OttCall::HandleCombineConferenceFailEvent`/`LaunchConference`/`ExitConference`/`HoldConference` 与 CSCall/IMSCall 同构（联动 `OttConference` 单例）

### Requirement: BluetoothCall 通话对象与蓝牙状态回调
系统 SHALL 由 `BluetoothCall`（继承 `CarrierCall`，额外持有 `macAddress_`）承载蓝牙通话对象行为，控制指令经 `Bluetooth::HandsFreeUnit` 框架下发；`BluetoothCallState` 仅做 HFP 连接与 SCO 状态回调转储。蓝牙管理链路（设备发现、状态同步等）不在本能力范围。

#### Scenario: 控制指令经 HFP 框架
- **WHEN** 调用 `AnswerCall`/`RejectCall`/`HangUpCall`/`StartDtmf`
- **THEN** 分别经 `Bluetooth::HandsFreeUnit::GetProfile()` 的 `AcceptIncomingCall`/`RejectIncomingCall`/`FinishActiveCall`/`SendDTMFTone` 以 `BluetoothRemoteDevice(macAddress_)` 下发；profile 为空分别返回 `CALL_ERR_ANSWER_FAILED`/`CALL_ERR_REJECT_FAILED`/`CALL_ERR_HANGUP_FAILED`/`CALL_ERR_FUNCTION_NOT_SUPPORTED`

#### Scenario: 不产生设备动作的接口
- **WHEN** 调用 `DialingProcess`/`HoldCall`/`UnHoldCall`/`SwitchCall`/`SetMute`/会议族接口
- **THEN** 直接返回 `TELEPHONY_SUCCESS`

#### Scenario: HFP/SCO 状态回调
- **WHEN** `BluetoothCallState::OnConnectionStateChanged` 收到 CONNECTED/DISCONNECTED，或 `OnScoStateChanged` 收到 SCO_CONNECTED/SCO_DISCONNECTED
- **THEN** 分别调用 `BluetoothCallConnection::SetHfpConnected`（断开时同时清 `SetHfpContactName`、清 SCO）或 `SetBtCallScoConnected`，SCO 变化时同步 `AudioDeviceManager::ReportAudioDeviceInfo`

### Requirement: SatelliteCall 通话对象
系统 SHALL 由 `SatelliteCall`（继承 `CarrierCall`）承载卫星通话对象：基本语音控制复用载波流程，多方/保持类能力一律返回 `TELEPHONY_ERROR`。

#### Scenario: 基本控制复用载波流程
- **WHEN** 调用 `DialingProcess`/`AnswerCall`/`RejectCall`/`HangUpCall`
- **THEN** 分别转发 `CarrierDialingProcess`/`CarrierAnswerCall`/`CarrierRejectCall`/`CarrierHangUpCall`

#### Scenario: 多方与保持能力禁用
- **WHEN** 调用 `HoldCall`/`UnHoldCall`/`SwitchCall`/`SetMute`/`CombineConference`/`SeparateConference`/`KickOutFromConference`/`CanCombineConference`/`CanSeparateConference`/`CanKickOutFromConference`/`LaunchConference`/`ExitConference`/`HoldConference`/`GetMainCallId`/`GetSubCallIdList`/`GetCallIdListForConference`/`IsSupportConferenceable`
- **THEN** 一律返回 `TELEPHONY_ERROR`（卫星通话不支持保持、切换与会议）

### Requirement: CallWiredHeadSet 有线耳机按键
系统 SHALL 由 `CallWiredHeadSet` 在首个通话创建时（`Init`）向 `MMI::InputManager` 订阅 `KEYCODE_HEADSETHOOK` 的按下/抬起回调（优先级 `PRIORITY_100`），对象表清空时（`DeInit`）注销，并在有线耳机已连接（`AudioDeviceManager::IsWiredHeadsetConnected`）时按短按/长按（阈值 `FINAL_KEY_DOWN_DURATION_TWO`=2000ms）执行通话操作。

#### Scenario: 短按接听
- **WHEN** 按键抬起与按下的间隔小于 2000ms 且存在 `CALL_RUNNING_STATE_RINGING` 通话
- **THEN** 以振铃通话的 `GetVideoStateType()`（非法时回退 `GetOriginalCallType()`）调用 `CallControlManager::AnswerCall`

#### Scenario: 短按免提保持恢复或静音翻转
- **WHEN** 短按且无振铃通话
- **THEN** 若同时存在 ACTIVE 与 HOLD 通话则 `UnHoldCall` 保持通话；否则取 `GetAudioLiveCall` 并按 `AudioProxy::IsMicrophoneMute()` 取反调用 `SetMuted`

#### Scenario: 长按拒接或挂断
- **WHEN** 按下持续达到 2000ms（长按）
- **THEN** 存在振铃通话时 `RejectCall`；否则取 `GetForegroundCall`，其会议态非 `TEL_CONFERENCE_IDLE` 时挂断 `ImsConference::GetMainCall()`，否则直接挂断该前台通话

### Requirement: NOT_SUPPORT_MULTICALL 一号双终端对象判定
系统 SHALL 在定义 `NOT_SUPPORT_MULTICALL` 时提供四个对象表形态判定（`CALL_MAX_COUNT`=2），供 `CallControlManager::HangUpFirstCall` 系列在应答新来电前决定是否先释放既有通话；未定义该宏时这些函数不存在。

#### Scenario: 蓝牙与 eSIM 混合双呼
- **WHEN** 对象表恰有 2 个对象，其一为 `TYPE_CS`/`TYPE_IMS`、另一为 `TYPE_BLUETOOTH`
- **THEN** `IsTwoCallBtCallAndESIM` 在两者号码不同时返回 true、号码相同时返回 false；`IsOneNumberDualTerminal` 在号码相同时返回 true

#### Scenario: 纯蓝牙双呼
- **WHEN** 对象表恰有 2 个对象且全部为 `TYPE_BLUETOOTH`
- **THEN** `IsTwoCallBtCall` 返回 true；对象数不为 2 时四个判定均返回 false

#### Scenario: 纯 eSIM 双呼判定恒假（HMOS 现状）
- **WHEN** 调用 `IsTwoCallESIMCall`
- **THEN** 其成员判定为 `GetCallType() != TYPE_CS || GetCallType() != TYPE_IMS`，该条件对任意 callType 恒真，因此函数对任何对象表恒返回 false（HMOS 原样行为，疑似应为 `&&`）