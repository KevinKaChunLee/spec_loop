# call-control-management Specification

## Purpose
描述 `telephony_call_manager`（OpenHarmony v6.0 快照）中呼叫控制路径的"移植前现状"：`CallControlManager` 公有控制面与下行转发（`services/call/src/call_control_manager.cpp` + `include/call_control_manager.h`）、异步请求层 `CallRequestHandler`/`CallRequestProcess`（`call_request_handler.cpp`/`call_request_process.cpp`）、拨号/应答判定链 `CallPolicy`（`call_policy.cpp`）、来电过滤 `CallIncomingFilterManager`（`call_incoming_filter_manager.cpp`）、超级隐私控制 `CallSuperPrivacyControlManager`（`call_superprivacy_control_manager.cpp`）、拨号标志与挂起管理 `CallRequestEventHandlerHelper`（`call_request_event_handler_helper.cpp`）。控制请求最终出口为 `CellularCallConnection`（cellular_call 模块 IPC 代理）、`VoipCallConnection`（畅连）、`BluetoothCallConnection` 与 `CallAbilityReportProxy::OttCallRequest`（OTT 上报）。通话对象模型与状态上报（`call_object_manager.cpp`、`call_status_manager.cpp`）不在本能力范围。

控制本能力行为的构建开关（均已逐点 rg 核实场点）：
- `NOT_SUPPORT_MULTICALL`：由 `BUILD.gn` 的 `declare_args` 变量 `call_manager_feature_not_support_multicall` 控制；场点 `call_control_manager.h:159`（声明 `HangUpFirstCall` 族）与 `call_control_manager.cpp`（`AnswerCall` 内先挂第一路、`HangUpFirstCall` 系列实现）。
- `HFP_ASYNC_ENABLE`：由 `BUILD.gn` 的 `declare_args` 变量 `call_manager_feature_hfp_async_enable` 控制；场点仅 `call_control_manager.cpp` 的 `SystemAbilityListener::HfpBroadcastSubscriber`（订阅 `usual.event.bluetooth.CONNECT_HFP_HF`）。
- `ABILITY_POWER_SUPPORT`：由 `callmanager.gni` 在 `powermgr_power_manager` 部件存在时定义；场点 `call_control_manager.h`（`disconnectedRunningLock_` 成员）与 `call_control_manager.cpp` 的 `AcquireDisconnectedLock`/`ReleaseDisconnectedLock`。
- `ABILITY_MEDIA_SUPPORT`：场点仅 `call_control_manager.cpp` 的 `onButtonDealing`（耳机按键处理）；本仓 `BUILD.gn`/`callmanager.gni` 未定义该宏，恒不编译。
- `ABILITY_CONFIG_SUPPORT`：场点 `call_policy.cpp` 的 `IsSupportVideoCall`（改读 `GetCarrierConfig(ITEM_VIDEO_CALL)`）；本仓 GN 未定义，恒关闭。

## Requirements

### Requirement: DialCall 拨号入口链
系统 SHALL 由 `CallControlManager::DialCall` 承载拨号入口：号码合法性校验 → 紧急号码识别 → 卫星/蓝牙拨号类型改写 → `CanDial` 策略 → 暂存拨号参数 → 转发 `CallRequestHandler::DialCall`（同步调用）。

#### Scenario: 号码合法性
- **WHEN** 号码为空或长度超过 `kMaxNumberLen`
- **THEN** `NumberLegalityCheck` 分别返回 `CALL_ERR_PHONE_NUMBER_EMPTY`/`CALL_ERR_NUMBER_OUT_OF_RANGE`，拨号终止

#### Scenario: 紧急号码识别
- **WHEN** 号码经 `CallNumberUtils::RemoveSeparatorsPhoneNumber` 清洗后 `CheckNumberIsEmergency` 判定为紧急号码
- **THEN** extras 写入 `dialScene = CALL_EMERGENCY`

#### Scenario: 卫星拨号改写
- **WHEN** `SatelliteCallControl::IsSatelliteSwitchEnable` 成功
- **THEN** 继续校验 `IsAllowedSatelliteDialCall`（失败直接返回错误），通过后 extras 写入 `callType = TYPE_SATELLITE`

#### Scenario: 蓝牙拨号改写
- **WHEN** extras 中 `dialType` 为 `DIAL_BLUETOOTH_TYPE`
- **THEN** extras 写入 `callType = TYPE_BLUETOOTH`

#### Scenario: 策略通过后暂存并下发
- **WHEN** `CanDial`（= `DialPolicy` + `CanDialMulityCall`）通过
- **THEN** `PackageDialInformation` 把号码/callType/accountId/dialType/videoState/bundleName/isEcc 暂存到 `dialSrcInfo_`/`extras_`，调用 `CallRequestHandlerPtr_->DialCall()`；策略失败经 `WriteDialCallFaultEvent` 记录后返回错误码

### Requirement: CallPolicy::DialPolicy 拨号参数判定链
系统 SHALL 由 `CallPolicy::DialPolicy` 依次校验拨号参数与既有通话状态，任一环节失败即终止拨号。

#### Scenario: 拨号类型与场景参数合法性
- **WHEN** extras 的 `dialType` 不属于 `DIAL_CARRIER_TYPE`/`DIAL_VOICE_MAIL_TYPE`/`DIAL_OTT_TYPE`/`DIAL_BLUETOOTH_TYPE`，或 `callType` 不属于 `TYPE_CS`/`TYPE_IMS`/`TYPE_OTT`/`TYPE_SATELLITE`/`TYPE_BLUETOOTH`，或 `dialScene` 不属于 `CALL_NORMAL`/`CALL_PRIVILEGED`/`CALL_EMERGENCY`，或 `videoState` 非 `TYPE_VOICE`/`TYPE_VIDEO`
- **THEN** 分别返回 `TELEPHONY_ERR_ARGUMENT_INVALID`/`CALL_ERR_UNKNOW_CALL_TYPE`/`TELEPHONY_ERR_ARGUMENT_INVALID`/`TELEPHONY_ERR_ARGUMENT_INVALID`

#### Scenario: EDM 禁拨
- **WHEN** `IsDialingEnable(phoneNum)` 为 false，展开为 `EdmCallPolicy::IsCallEnable`：系统参数 `persist.edm.telephony_call_disable` 为 true，或已设策略为黑名单（POLICY_FLAG_BLOCK）且号码命中黑名单，或策略为白名单（POLICY_FLAG_TRUST）且号码未命中白名单
- **THEN** 返回 `TELEPHONY_ERR_POLICY_DISABLED`

#### Scenario: 无效卡槽回退
- **WHEN** `dialType` 为 `DIAL_CARRIER_TYPE` 且 `CallNumberUtils::SelectAccountId` 判定 accountId 无效
- **THEN** extras 的 `accountId` 改写为 0 并继续

#### Scenario: 非 ECC 拨号的占用校验
- **WHEN** 非 ECC 拨号，且存在语音振铃通话（`IsVoiceCallValid`：已有非 VoIP、TYPE_VOICE 的 RINGING 通话）、或 `HasNewCall` 报新通话未完成、或 `HasEmergencyCall` 报紧急呼叫进行中
- **THEN** 返回 `CALL_ERR_CALL_COUNTS_EXCEED_LIMIT`

### Requirement: 超级隐私模式拨号拦截
系统 SHALL 由 `CallPolicy::SuperPrivacyMode` 在拨号判定链末端拦截超级隐私模式下的普通拨号。

#### Scenario: 紧急拨号豁免
- **WHEN** 本次拨号 `isEcc` 为真或 `dialScene` 为 `CALL_EMERGENCY`
- **THEN** 跳过超级隐私拦截，直接进入 `HasNormalCall` 常规判定

#### Scenario: 超级隐私模式拦截
- **WHEN** `CallSuperPrivacyControlManager::GetCurrentIsSuperPrivacyMode()` 为 true
- **THEN** 调用 `CallDialog::DialogConnectPrivpacyModeExtension("SUPER_PRIVACY_MODE", ...)` 弹出隐私模式确认框并返回 `CALL_ERR_DIAL_FAILED`；用户确认后由 `CloseCallSuperPrivacyMode` 关闭隐私模式再重新拨号

### Requirement: HasNormalCall 常规拨号前置判定链
系统 SHALL 由 `CallPolicy::HasNormalCall` 对非 ECC、非卫星、非蓝牙的载波拨号执行 SIM/飞行模式/网络注册/CT 卡 IMS 注册四段判定，失败时弹出对应对话框。

#### Scenario: 判定豁免
- **WHEN** `isEcc` 为真，或 `callType` 为 `TYPE_SATELLITE`/`TYPE_BLUETOOTH`
- **THEN** 直接返回 `TELEPHONY_SUCCESS`

#### Scenario: 无 SIM 卡
- **WHEN** `CoreServiceClient::HasSimCard(slotId)` 返回无卡
- **THEN** `DialogConnectExtension("CALL_FAILED_NO_SIM_CARD")` 并返回 `TELEPHONY_ERR_NO_SIM_CARD`

#### Scenario: 飞行模式
- **WHEN** `CallDataBaseHelper::GetAirplaneMode` 查询设置库（DataShare）得到飞行模式开启
- **THEN** `DialogConnectExtension("CALL_FAILED_IN_AIRPLANE_MODE")` 并返回 `TELEPHONY_ERR_AIRPLANE_MODE_ON`

#### Scenario: 无服务
- **WHEN** `CoreServiceClient::GetNetworkState(slotId)` 的注册态非 `REG_STATE_IN_SERVICE`
- **THEN** `DialogConnectExtension("CALL_FAILED_NO_SERVICE")` 并返回 `TELEPHONY_ERR_NETWORK_NOT_IN_SERVICE`

#### Scenario: CT 卡无 IMS
- **WHEN** `CoreServiceClient::IsCTSimCard` 判定为 CT 卡，且非漫游、`GetImsRegStatus(TYPE_VOICE)` 未注册，且 `IsCtSimCardSwitchToChnOrMc`（`GetResidentNetworkNumeric` 与 `GetSimOperatorNumeric` 的 MCC 段同为中国 `CHN_MCC` 或澳门 `MC_MCC`）为 true
- **THEN** `DialogConnectExtension("CALL_FAILED_CTCARD_NO_IMS", slotId)` 并返回 `CALL_ERR_DIAL_FAILED`

### Requirement: CanDialMulityCall 多呼与视频拨号约束
系统 SHALL 由 `CallPolicy::CanDialMulityCall` 在拨号策略通过后追加视频通话等待与分布式场景约束。

#### Scenario: 视频通话等待关闭时的占用限制
- **WHEN** `CellularCallConnection::GetVideoCallWaiting(slotId)` 返回关闭，且本次为 `TYPE_VIDEO` 拨号而已有任一蜂窝通话存在，或本次为非 ECC 的 `TYPE_VOICE` 拨号而已存在视频通话（`HasVideoCall`）
- **THEN** 返回 `CALL_ERR_DIAL_IS_BUSY`

#### Scenario: 分布式 sink 角色禁拨
- **WHEN** `DistributedCommunicationManager::IsConnected` 且 `IsSinkRole` 且已有蜂窝通话
- **THEN** 返回 `CALL_ERR_CALL_COUNTS_EXCEED_LIMIT`

### Requirement: 视频拨号能力归一
系统 SHALL 由 `CallControlManager::SetCallTypeExtras` + `CallPolicy::IsSupportVideoCall` 在下发前归一视频拨号参数。

#### Scenario: 不支持视频时降级语音
- **WHEN** `dialType` 为 `DIAL_CARRIER_TYPE`/`DIAL_VOICE_MAIL_TYPE` 且 `IsSupportVideoCall` 为 false
- **THEN** extras 的 `videoState` 改写为 `TYPE_VOICE`

#### Scenario: 视频拨号升级为 IMS
- **WHEN** 归一后 `videoState` 仍为 `TYPE_VIDEO`
- **THEN** extras 的 `callType` 改写为 `TYPE_IMS`

#### Scenario: IsSupportVideoCall 判定链
- **WHEN** 调用 `IsSupportVideoCall`：`ABILITY_CONFIG_SUPPORT` 分支读 `GetCarrierConfig(ITEM_VIDEO_CALL)`（该宏本仓未定义，默认 true），`CallNumberUtils::IsCarrierVtConfig` 校验运营商 VT 配置，`dialScene` 非 `CALL_NORMAL`（如紧急拨号）
- **THEN** 运营商 VT 配置关闭或非普通拨号场景返回 false，否则返回 true

### Requirement: AnswerCall 应答入口链
系统 SHALL 由 `CallControlManager::AnswerCall` 承载应答入口：定位振铃通话 → 静音彩振处理 → 超级隐私拦截 → 卫星/视频预处理 → 状态上报 → VoIP 冲突处理 → 策略校验 → 异步下发。

#### Scenario: callId 定位
- **WHEN** 传入 `INVALID_CALLID`（0）且当前存在 `CALL_RUNNING_STATE_RINGING` 通话
- **THEN** 取该振铃通话的 callId 继续处理；无振铃通话返回 `TELEPHONY_ERR_LOCAL_PTR_NULL`

#### Scenario: 视频彩振应答关扬声器
- **WHEN** 目标通话 `GetCrsType() == CRS_TYPE`（2）且应答 videoState 非 `TYPE_VIDEO`
- **THEN** `AudioProxy::SetSpeakerDevActive(false)` 关闭免提扬声器

#### Scenario: 超级隐私应答拦截
- **WHEN** `CurrentIsSuperPrivacyMode` 判定超级隐私模式开启
- **THEN** `AudioControlManager::MuteRinger` 静铃并 `CallDialog::DialogConnectAnswerPrivpacyModeExtension("SUPER_PRIVACY_MODE", ...)` 弹窗，本次调用返回 `TELEPHONY_SUCCESS` 不再下发应答

#### Scenario: 卫星/视频应答预处理
- **WHEN** 目标通话为 `TYPE_IMS` 且应答 videoState 与对象当前 `GetVideoStateType()` 不同，或为 `TYPE_SATELLITE` 且存在 ACTIVE 卫星通话
- **THEN** 前者更新对象 videoState 并 `IMSCall::InitVideoCall`；后者先经 `CallRequestHandlerPtr_->HangUpCall` 挂断既有活动卫星通话

#### Scenario: VoIP 活动时排队应答
- **WHEN** `VoIPCallState_` 非 `CALL_STATE_IDLE` 且目标通话非 `TYPE_VOIP`
- **THEN** 把 callId/videoState 存入 `AnsweredCallQueue_` 并返回成功，待 VoIP 转为 IDLE 时（见 SetVoIPCallState）自动补发 `AnswerCall`

#### Scenario: 策略失败转 VoIP 事件
- **WHEN** `AnswerCallPolicy` 失败且存在 VoIP 通话（`IsVoipCallExist`）
- **THEN** 经 `sendEventToVoip(EVENT_ANSWER_VOIP_CALL)` 走事件通知路径并返回成功；否则记录 `WriteAnswerCallFaultEvent` 并返回错误码

### Requirement: CarrierAndVoipConflictProcess 载波与 VoIP 冲突处理
系统 SHALL 在载波通话应答成功（`CALL_STATUS_ANSWERED`）时清理冲突的 VoIP 通话。

#### Scenario: 仅应答时触发
- **WHEN** `callState` 非 `CALL_STATUS_ANSWERED`
- **THEN** 不做任何处理直接返回成功

#### Scenario: 清理冲突 VoIP
- **WHEN** 被应答通话为 `TYPE_CS`/`TYPE_IMS`/`TYPE_SATELLITE`，且 VoIP 列表中存在 INCOMING 或 DIALING 状态的通话
- **THEN** INCOMING 的执行 `RejectCall`（携带原因 "CarrierAndVoipConflictProcess"），DIALING 的执行 `HangUpCall`

### Requirement: RejectCall 与 HangUpCall 挂断路径
系统 SHALL 由 `RejectCall`/`HangUpCall` 承载拒接与挂断入口，含默认目标选择、策略校验与 VoIP 事件回退。

#### Scenario: 拒接默认目标
- **WHEN** `RejectCall` 传入 `INVALID_CALLID` 且存在振铃通话
- **THEN** 取该通话 callId；`RejectCallPolicy` 校验其处于 `CALL_STATUS_INCOMING`/`CALL_STATUS_WAITING`（否则 `CALL_ERR_ILLEGAL_CALL_OPERATION`），通过后同步转发 `CallRequestHandlerPtr_->RejectCall(callId, rejectWithMessage, textMessage)` 并上报 `WriteVoipCallStatisticalEvent(callId, "MtBannerReject")`

#### Scenario: 挂断默认目标顺选
- **WHEN** `HangUpCall` 传入 `INVALID_CALLID`
- **THEN** 按 ACTIVE → DIALING → CONNECTING → HOLD 的顺序取第一个存在的通话；全部不存在返回 `TELEPHONY_ERR_ARGUMENT_INVALID`

#### Scenario: 挂断策略失败回退 VoIP
- **WHEN** `HangUpPolicy` 失败且 callId >= `VOIP_CALL_MINIMUM`（10000）且存在 VoIP 通话
- **THEN** 分别经 `sendEventToVoip(EVENT_REJECT_VOIP_CALL)`（拒接路径）/`sendEventToVoip(EVENT_HANGUP_VOIP_CALL)`（挂断路径）回退并返回成功

#### Scenario: MO 拨号处理中延迟挂断
- **WHEN** `HangUpCall` 时 `CallRequestEventHandlerHelper::HasPendingMo(callId)` 为 true（拨号请求已下发、CLCC 流程未完成）
- **THEN** 置 `SetPendingMo(false, -1)`、`SetPendingHangup(true, callId)` 暂存挂断请求（待 `CallStatusManager` 在拨号流程收尾时消费），本次调用返回成功不再下发

### Requirement: HoldCall/UnHoldCall/SwitchCall 保持与切换路径
系统 SHALL 由 Hold/UnHold/Switch 三个入口先经对应 CallPolicy 前置校验再转发 `CallRequestHandler`。

#### Scenario: 保持前置
- **WHEN** `HoldCallPolicy` 校验目标通话运行态非 `CALL_RUNNING_STATE_ACTIVE`
- **THEN** 返回 `CALL_ERR_CALL_IS_NOT_ACTIVATED`，不转发

#### Scenario: 恢复前置
- **WHEN** `UnHoldCallPolicy` 校验目标通话运行态非 `CALL_RUNNING_STATE_HOLD`
- **THEN** 返回 `CALL_ERR_CALL_IS_NOT_ON_HOLDING`，不转发

#### Scenario: 切换前置
- **WHEN** `SwitchCallPolicy` 校验载波通话数少于 2（`onlyTwoCall_`）、目标通话非 `CALL_STATUS_HOLDING`、或存在 DIALING/ALERTING 通话
- **THEN** 分别返回 `CALL_ERR_PHONE_CALLS_TOO_FEW`/`CALL_ERR_ILLEGAL_CALL_OPERATION`，不转发

### Requirement: DTMF/RTT/后拨与邀会指令路径
系统 SHALL 由 StartDtmf/StopDtmf/PostDialProceed/StartRtt/StopRtt/JoinConference 承载通话中指令：对象存活性与策略校验后转发。

#### Scenario: DTMF 校验与提示音
- **WHEN** `StartDtmf`/`StopDtmf` 的目标通话不存在或 `IsAliveState()` 为 false
- **THEN** 分别返回 `TELEPHONY_ERR_ARGUMENT_INVALID`/`CALL_ERR_CALL_STATE_MISMATCH_OPERATION`；`StartDtmf` 成功转发对象 `StartDtmf` 后经 `ffrt::submit` 异步 `AudioControlManager::PlayDtmfTone`，`StopDtmf` 同步 `StopDtmfTone`

#### Scenario: RTT 仅限活动 IMS 通话
- **WHEN** `StartRttPolicy`/`StopRttPolicy` 校验目标通话非 `TYPE_IMS`（`CALL_ERR_UNSUPPORTED_NETWORK_TYPE`）或状态非 `CALL_STATUS_ACTIVE`（`CALL_ERR_ILLEGAL_CALL_OPERATION`）
- **THEN** 拒绝并返回；通过后转发 `CallRequestHandlerPtr_->StartRtt`/`StopRtt`

#### Scenario: 后拨确认
- **WHEN** `PostDialProceed` 的目标通话非存活态
- **THEN** 返回 `CALL_ERR_CALL_STATE_MISMATCH_OPERATION`；通过后转发对象 `PostDialProceed(proceed)`

#### Scenario: 邀请入会校验
- **WHEN** `InviteToConferencePolicy` 校验 callId 不存在、号码列表为空/含空号码（`CALL_ERR_PHONE_NUMBER_EMPTY`）、号码超长（`CALL_ERR_NUMBER_OUT_OF_RANGE`）、或 callId 不是 `ImsConference::GetMainCall()`（`CALL_ERR_CONFERENCE_NOT_EXISTS`）
- **THEN** 拒绝；通过后号码转 string 转发 `CallRequestHandlerPtr_->JoinConference`

### Requirement: 会议控制路径
系统 SHALL 由 CombineConference/SeparateConference/KickOutFromConference/GetMainCallId/GetSubCallIdList/GetCallIdListForConference 承载会议控制。

#### Scenario: 合并会议前置
- **WHEN** `CombineConference(mainCallId)` 的主叫通话不存在、非 `CALL_STATUS_ACTIVE`、或不存在同 callType 的 `CALL_STATUS_HOLDING` 通话
- **THEN** 分别返回 `TELEPHONY_ERR_ARGUMENT_INVALID`/`CALL_ERR_CALL_STATE_MISMATCH_OPERATION`；`CanCombineConference` 失败亦拒绝；通过后转发 `CallRequestHandlerPtr_->CombineConference`

#### Scenario: 分离/踢出校验
- **WHEN** `SeparateConference`/`KickOutFromConference` 的目标对象 `CanSeparateConference`/`CanKickOutFromConference` 校验失败
- **THEN** 返回对应会议错误码；通过后转发 handler

#### Scenario: 会议信息查询
- **WHEN** 调用 `GetMainCallId`/`GetSubCallIdList`/`GetCallIdListForConference`
- **THEN** 目标对象不存在返回 `TELEPHONY_ERR_ARGUMENT_INVALID`，否则透传对象层会议单例查询结果

### Requirement: 补充业务设置接口族
系统 SHALL 由 GetCallWaiting/SetCallWaiting/GetCallRestriction/SetCallRestriction/SetCallRestrictionPassword/GetCallTransferInfo/SetCallTransferInfo/CanSetCallTransferTime/SetCallPreferenceMode/GetImsConfig/SetImsConfig/GetImsFeatureValue/SetImsFeatureValue/EnableImsSwitch/DisableImsSwitch/IsImsSwitchEnabled/SetVoNRState/GetVoNRState/CloseUnFinishedUssd 统一按"CallPolicy slotId 前置 → `callSettingManagerPtr_` 转发"模式工作。

#### Scenario: slotId 前置校验
- **WHEN** 任一补充业务接口的 `CallPolicy::IsValidSlotId(slotId)` 失败（含 `VoNRStatePolicy` 对 state 非 `VONR_STATE_ON`/`VONR_STATE_OFF` 的附加校验）
- **THEN** 返回 `CALL_ERR_INVALID_SLOT_ID`（VoNR state 非法返回 `TELEPHONY_ERR_ARGUMENT_INVALID`），不转发

#### Scenario: 设置管理器转发
- **WHEN** 前置通过且 `callSettingManagerPtr_` 非空
- **THEN** 透传 `CallSettingManager` 对应接口（UT/USSD 补充业务经 `callSettingManagerPtr_` 出口）；`callSettingManagerPtr_` 为空返回 `TELEPHONY_ERR_LOCAL_PTR_NULL`

### Requirement: 音频控制接口
系统 SHALL 由 SetMuted/MuteRinger/SetAudioDevice 承载控制层音频入口。

#### Scenario: 静音目标选择
- **WHEN** 调用 `SetMuted(isMute)`，取 `CallObjectManager::GetAudioLiveCall` 为目标
- **THEN** 无活动通话返回 `CALL_ERR_AUDIO_SETTING_MUTE_FAILED`；目标为 VoIP 时仅调对象 `SetMute`；目标为 CS/IMS 时对象 `SetMute` 之外再调 `AudioControlManager::SetMute`；其他类型仅调 `AudioControlManager::SetMute`

#### Scenario: 静铃与音频设备
- **WHEN** 调用 `MuteRinger` 或 `SetAudioDevice`
- **THEN** 前者依次调 `CallVoiceAssistantManager::MuteRinger` 与 `AudioControlManager::MuteRinger`；后者透传 `AudioControlManager::SetAudioDevice(audioDevice, true)`

### Requirement: 查询与号码工具族
系统 SHALL 提供 GetCallState/HasCall/HasVoipCall/IsNewCallAllowed/IsRinging/HasEmergency 查询入口及 IsEmergencyPhoneNumber/FormatPhoneNumber/FormatPhoneNumberToE164 号码工具入口。

#### Scenario: 应用侧通话状态聚合
- **WHEN** 调用 `GetCallState`
- **THEN** 无蜂窝通话且 VoIP 状态为 IDLE/UNKNOWN 时返回 `CALL_STATE_IDLE`；否则基础 OFFHOOK，且存在振铃通话或 VoIP 为 RINGING 时返回 `CALL_STATE_RINGING`

#### Scenario: 简单存在性查询
- **WHEN** 调用 `HasCall`/`HasVoipCall`/`IsNewCallAllowed`/`IsRinging`/`HasEmergency`
- **THEN** 分别透传对象层 `HasCellularCallExist`+VoIP 状态、`HasVoipCallExist`、`IsNewCallAllowedCreate`、`HasRingingCall`、`HasEmergencyCall`

#### Scenario: 紧急号码判定与号码格式化
- **WHEN** 调用 `IsEmergencyPhoneNumber`（slotId 非法返回 `CALL_ERR_INVALID_SLOT_ID`）或 `FormatPhoneNumber`/`FormatPhoneNumberToE164`
- **THEN** 均透传 `CallNumberUtils::CheckNumberIsEmergency`/`FormatPhoneNumber`/`FormatPhoneNumberToE164`；`UpdateImsCallMode` 与 ControlCamera/SetPreviewWindow 等视频控制接口在 `CallControlManager` 层恒返回 `TELEPHONY_SUCCESS`（空实现）

#### Scenario: 视频控制前置策略
- **WHEN** `VideoControlManager` 调用 `CallPolicy::VideoCallPolicy(callId)`
- **THEN** 仅校验通话对象存在（不存在返回 `TELEPHONY_ERR_ARGUMENT_INVALID`），通过即放行（该策略被视频能力复用，本能力只提供判定本身）

### Requirement: 状态通知分发与观察者注册
系统 SHALL 由 NotifyNewCallCreated/NotifyCallDestroyed/NotifyCallStateUpdated/NotifyVoipCallStateUpdated/NotifyIncomingCallAnswered/NotifyIncomingCallRejected/NotifyCallEventUpdated 统一经 `callStateListenerPtr_`（`CallStateListener`）分发，并在 `CallStateObserve` 中注册固定观察者清单。

#### Scenario: 观察者清单
- **WHEN** `CallControlManager::Init` 调用 `CallStateObserve`
- **THEN** 依次注册 `CallAbilityReportProxy`、`CallStateReportProxy`、`AudioControlManager`、`RejectCallSms`、`MissedCallNotification`、`IncomingCallWakeup`、`CallRecordsManager`、`DistributedCommunicationManager`、`InteroperableCommunicationManager`、`CallVoiceAssistantManager`

#### Scenario: 状态变化附加处理
- **WHEN** `NotifyCallStateUpdated` 分发非 VoIP 通话且状态转移命中 `IsCallActivated`（DIALING→ALERTING/DIALING→ACTIVE/INCOMING→ACTIVE/ALERTING→ACTIVE）
- **THEN** 调 `AudioDeviceManager::CheckAndSwitchDistributedAudioDevice`；ACTIVE/DISCONNECTING→DISCONNECTED 且无保持通话时调 `OnActivedCallDisconnected`；WAITING→ACTIVE 且 `DistributedCallManager::IsDCallDeviceSwitchedOn` 时再次检查切换分布式音频

### Requirement: CallRequestHandler ffrt 异步下发
系统 SHALL 由 `CallRequestHandler` 以 `ffrt::submit` 异步下发除 DialCall 外的全部控制请求，调用方立即得到 `TELEPHONY_SUCCESS`（`callRequestProcessPtr_` 为空时同步返回 `TELEPHONY_ERR_LOCAL_PTR_NULL`）。

#### Scenario: 异步请求集
- **WHEN** 调用 `AnswerCall`/`RejectCall`/`HangUpCall`/`HoldCall`/`UnHoldCall`/`SwitchCall`/`StartRtt`/`StopRtt`/`CombineConference`/`SeparateConference`/`KickOutFromConference`
- **THEN** 对应 `CallRequestProcess::AnswerRequest`/`RejectRequest`/`HangUpRequest`/`HoldRequest`/`UnHoldRequest`/`SwitchRequest`/`StartRttRequest`/`StopRttRequest`/`CombineConferenceRequest`/`SeparateConferenceRequest`/`KickOutFromConferenceRequest` 在 ffrt 任务中执行，接口本身恒返回 `TELEPHONY_SUCCESS`

#### Scenario: 拨号与邀会特殊路径
- **WHEN** 调用 `DialCall` 或 `JoinConference`
- **THEN** 前者同步调用 `DialRequest` 并透传其返回值；后者以 `weak_ptr` 捕获 `CallRequestProcess` 在 ffrt 任务中执行 `JoinConference`（避免延长对象生命周期）

### Requirement: CallRequestProcess::DialRequest 拨号请求处理
系统 SHALL 由 `DialRequest` 校验拨号暂态与 FDN 限制后按 `dialType` 分发到 `CarrierDialProcess`/`VoiceMailDialProcess`/`OttDialProcess`/`BluetoothDialProcess`。

#### Scenario: 暂态与号码校验
- **WHEN** `GetDialParaInfo` 的 `isDialing` 为 false 或号码超长
- **THEN** 分别返回 `CALL_ERR_ILLEGAL_CALL_OPERATION`（并记录 `CALL_ERROR_DEVICE_NOT_DIALING` 故障）/`CALL_ERR_NUMBER_OUT_OF_RANGE`

#### Scenario: FDN 固定拨号限制
- **WHEN** 非 ECC、`DIAL_CARRIER_TYPE` 且 `CoreServiceConnection::IsFdnEnabled(slotId)` 为 true，FDN 号码列表为空或去空格后的号码不在列表中
- **THEN** 上报 `EVENT_INVALID_FDN_NUMBER` 事件、`DialogConnectExtension("CALL_FAILED_DUE_TO_FDN")` 并返回 `CALL_ERR_DIAL_FAILED`

#### Scenario: 拨号类型分发
- **WHEN** `HandleDialRequest` 按 `info.dialType` 分发
- **THEN** `DIAL_CARRIER_TYPE`/`DIAL_VOICE_MAIL_TYPE` 走载波流程（后者复用 `CarrierDialProcess`）、`DIAL_OTT_TYPE` 走 `OttDialProcess`（经 `CallAbilityReportProxy::OttCallRequest(OTT_REQUEST_DIAL)` 上报）、`DIAL_BLUETOOTH_TYPE` 走 `BluetoothDialProcess`（经 `BluetoothCallConnection::Dial`，非 ECC 且已有通话或拨号中时返回 `CALL_ERR_CALL_COUNTS_EXCEED_LIMIT`）；未知类型返回 `CALL_ERR_UNKNOW_DIAL_TYPE`

### Requirement: CarrierDialProcess 载波拨号流程
系统 SHALL 由 `CarrierDialProcess` 执行拨号防并发、DSDA 前置、MMI 短路与蜂窝下发，失败时回滚。

#### Scenario: 拨号防并发
- **WHEN** `CallRequestEventHandlerHelper::IsDialingCallProcessing()` 为 true
- **THEN** 返回 `CALL_ERR_CALL_COUNTS_EXCEED_LIMIT`；否则置 `RestoreDialingFlag(true)` + `SetDialingCallProcessing()`

#### Scenario: DSDA 前置与 ECC 挤占
- **WHEN** `HandleDialingInfo` 中号码为 ECC 或 `IsNewCallAllowedCreate` 拒绝或 `IsDsdsMode5()`（`CoreServiceClient::GetDsdsMode` 为 `DSDS_MODE_V5_DSDA`/`DSDS_MODE_V5_TDM`）下 `IsDialCallForDsda` 需先保持异卡活动通话
- **THEN** ECC 走 `EccDialPolicy`；拒绝时返回 `CALL_ERR_CALL_COUNTS_EXCEED_LIMIT` 并复位拨号标志；DSDA 保持成功置 `needWaitHold_ = true`（保持失败返回其错误码）

#### Scenario: MMI 码短路
- **WHEN** 非 ECC 号码经 `CellularCallConnection::IsMmiCode` 判定为 MMI 码
- **THEN** 不上报 DIALING 状态、不占拨号标志（复位并移除延迟任务），调 `CallDialog::DialogProcessMMICodeExtension` 弹出 MMI 处理框

#### Scenario: 正常下发与失败回滚
- **WHEN** `HandleStartDial` 组包（`PackCellularCallInfo`）后，`needWaitHold_` 为 true 且非 MMI
- **THEN** 把 `CellularCallInfo` 暂存 `dialCallInfo_`（待保持完成后由 CallStatusManager 消费）返回成功；否则调 `CellularCallConnection::Dial`，失败且非 MMI 时 `HandleDialFail`：等待 `isFirstDialCallAdded_`（超时 1 秒 `WAIT_TIME_ONE_SECOND`）后对 CREATE/CONNECTING/DIALING 状态通话执行 `DealFailDial` 补报断开，最终返回拨号错误码

### Requirement: EccDialPolicy 紧急拨号挤占
系统 SHALL 由 `EccDialPolicy` 在紧急拨号时清理既有通话：卫星通话、拨号中（CREATE/CONNECTING/DIALING）、活动与保持通话挂断，振铃通话拒接。

#### Scenario: 已有紧急拨号在途
- **WHEN** 既有 CREATE/CONNECTING/DIALING 通话中存在 `GetEmergencyState()` 为真的对象
- **THEN** 清空挂断/拒接列表并直接返回 `CALL_ERR_CALL_COUNTS_EXCEED_LIMIT`

#### Scenario: 清理既有通话
- **WHEN** 无在途紧急拨号
- **THEN** 对 SATELLITE、CREATE/CONNECTING/DIALING、ACTIVE/HOLD 的对象逐个 `HangUpCall`，对 RINGING 的对象逐个 `RejectCall`，返回 `TELEPHONY_SUCCESS`

### Requirement: AnswerRequest 应答请求处理与 DSDA 判定链
系统 SHALL 由 `CallRequestProcess::AnswerRequest` 按 VoIP/单卡/DSDA 模式（叶子为 `CoreServiceClient::GetDsdsMode`）选择应答策略。

#### Scenario: VoIP 应答
- **WHEN** 目标通话为 `TYPE_VOIP`
- **THEN** 直接对象 `AnswerCall` 并 `NotifyIncomingCallAnswered`

#### Scenario: DSDS 模式 3（`IsDsdsMode3`，GetDsdsMode==`DSDS_MODE_V3`）
- **WHEN** 存在其他 slotId 的载波通话
- **THEN** `DisconnectOtherSubIdCall`：对异卡通话置 `SetAutoAnswerState(true)` 并挂断，全部清理后应答本路；无异卡通话直接应答并通知

#### Scenario: DSDA 模式 5（`IsDsdsMode5`）视频/语音互斥
- **WHEN** `NeedAnswerVTAndEndActiveVO`（有连接中/活动通话且应答为视频）或 `NeedAnswerVOAndEndActiveVT`（应答语音且既有活动/保持通话为视频）
- **THEN** `DisconnectOtherCallForVideoCall` 挂断既有 ACTIVE/DIALING/HOLD 载波通话，本路置 `SetAutoAnswerState(true)` 后应答

#### Scenario: DSDA 模式 5 常规应答与 CRS 挤占
- **WHEN** 上述互斥不成立
- **THEN** 若存在另一振铃通话且其 `GetCrsType()`==2（CRS），先挂断该彩振通话；本路置 `SetAutoAnswerState(true)` 后进入 `HoldOrDisconnectedCall`，按等待通话数（>1/==1/==0）执行 `HandleCallWaitingNumTwo/One/Zero` 的保持/挂断矩阵（活动通话 HoldCall 或异卡 HangUpCall、保持通话 HangUpCall、拨号中 HangUpCall），最终应答并通知

#### Scenario: 单卡直接应答
- **WHEN** 非 DSDS 模式 3/5
- **THEN** 对象 `AnswerCall(videoState)` 成功后 `NotifyIncomingCallAnswered`

### Requirement: Reject/HangUp/UnHold/Switch Request 处理与策略标志
系统 SHALL 由 `RejectRequest`/`HangUpRequest`/`UnHoldRequest`/`SwitchRequest` 执行对象层操作并设置挂断策略标志。

#### Scenario: 拒接后保持通话不可恢复
- **WHEN** `RejectRequest` 成功且存在 `CALL_RUNNING_STATE_HOLD` 通话
- **THEN** 对保持通话置 `SetCanUnHoldState(false)`（该路保持通话本次不可恢复），随后 `NotifyIncomingCallRejected`

#### Scenario: 挂断活动通话恢复保持
- **WHEN** `HangUpRequest` 目标为 ACTIVE 且存在同 callType 的 HOLDING 通话，或目标会议态为 `TEL_CONFERENCE_ACTIVE`，且无等待通话
- **THEN** 先尝试 `HangUpForDsdaRequest`（DSDA 模式且异卡有通话时逐个踢出会议成员后返回 true）；否则置 `POLICY_FLAG_HANG_UP_ACTIVE`（挂活动路、恢复保持路）

#### Scenario: 挂断保持中的会议
- **WHEN** 目标会议态为 `TEL_CONFERENCE_HOLDING` 且无等待通话，或会议态 HOLDING/ACTIVE 且存在等待通话
- **THEN** 前者置 `POLICY_FLAG_HANG_UP_HOLD_WAIT`；后者经 `GetSubCallIdList` 逐个 `KickOutFromConferenceRequest` 后挂断

#### Scenario: 恢复与切换请求
- **WHEN** `UnHoldRequest` 在 DSDA 模式 5 下存在异卡 ACTIVE 通话（其 `GetCanSwitchCallState()` 为 true）
- **THEN** 对异卡通话置 `SetCanSwitchCallState(false)` 并 HoldCall（已置 false 时直接返回"不可交换"）；无异卡通话时才执行本路 `UnHoldCall`；`SwitchRequest` 直接透传对象 `SwitchCall`

### Requirement: CallRequestEventHandlerHelper 拨号标志与挂起管理
系统 SHALL 由 `CallRequestEventHandlerHelper`（独立 `EventRunner`，任务名 `handler_restore_dialing_flag`）管理拨号进行标志与 MO 挂断暂存。

#### Scenario: 拨号标志自动复位
- **WHEN** `SetDialingCallProcessing` 在标志已为 true 时被调用
- **THEN** 移除旧任务并以 `PostTask` 投递 3000ms（`DELAY_TIME`）延迟任务把标志复位为 false；按 HMOS 现状，`PostTask` 返回 true（投递成功）时反被判为失败并返回 `TELEPHONY_ERROR`（原样保留的疑似反逻辑）；标志本为 false 时直接返回 `TELEPHONY_ERROR`

#### Scenario: 成功路径即时清标志
- **WHEN** 拨号成功返回（如 MMI 短路）或拨号完成
- **THEN** 调用方显式 `RestoreDialingFlag(false)` + `RemoveEventHandlerTask` 清除标志与延迟任务

#### Scenario: MO 挂断暂存语义
- **WHEN** `SetPendingMo(true, callId)` 后 `HasPendingMo(callId)` 为 true；`SetPendingHangup(true, callId)` 后 `IsPendingHangup`/`HasPendingHangup(callId)`/`GetPendingHangupCallId` 生效
- **THEN** 暂存的挂断请求由 `CallStatusManager` 在拨号 CLCC 流程收尾时按 `pendingHangupCallId_` 消费并清除（`SetPendingHangup(false, -1)`）

### Requirement: CallIncomingFilterManager 来电过滤
系统 SHALL 由 `CallIncomingFilterManager::DoIncomingFilter`（由 `CallStatusManager::IncomingFilterPolicy` 调用）在来电创建前执行过滤判定；v6.0 基线的语义分支仅两条（EDM 禁入与 ECC 豁免）。

#### Scenario: EDM 禁入来电
- **WHEN** `CallControlManager::IsIncomingEnable(phoneNum)` 为 false（展开为 `EdmCallPolicy::IsCallEnable`：`persist.edm.telephony_call_disable` 开启，或黑/白名单策略命中）
- **THEN** 返回 `TELEPHONY_ERR_POLICY_DISABLED`，该来电被拦截（不创建通话对象）

#### Scenario: 紧急来电豁免
- **WHEN** `CellularCallConnection::IsEmergencyPhoneNumber(phoneNum, accountId, isEcc)` 判定为紧急号码
- **THEN** 记录日志并返回 `TELEPHONY_SUCCESS` 放行；普通来电同样返回 `TELEPHONY_SUCCESS` 放行（v6.0 无开机向导未完成、免打扰/静默等独立分支，相关拦截不在本判定链内）

### Requirement: CallSuperPrivacyControlManager 超级隐私管理
系统 SHALL 由 `CallSuperPrivacyControlManager`（`CallControlManager::Init` 时 `RegisterSuperPrivacyMode` 注册）监听系统参数 `persist.super_privacy.mode` 并执行超级隐私的通话清理、关闭与恢复。

#### Scenario: 参数监听与模式上报
- **WHEN** `WatchParameter` 回调 `ParamChangeCallback` 收到参数变化
- **THEN** 先经 `SuperPrivacyModeChangeEvent` 按当前模式向应用上报 `EVENT_IS_SUPER_PRIVACY_MODE_ON`/`OFF`，再处理值本身

#### Scenario: 开启超级隐私清理通话
- **WHEN** 参数值变为 `"2"`（`SUPER_PRIVACY_MODE_PARAM_OPEN`）
- **THEN** 置 `SetIsChangeSuperPrivacyMode(false)` 并 `CloseAllCall`：遍历全部通话属性，非 `isEcc` 且非 `isEccContact` 的通话按状态分别 `RejectCall`（INCOMING/WAITING）或 `HangUpCall`（其余）

#### Scenario: 当前模式判定
- **WHEN** 调用 `GetCurrentIsSuperPrivacyMode`：`system::GetIntParameter("persist.super_privacy.mode")` 为 `CallSuperPrivacyModeType::ALWAYS_ON`，或为 `ON_WHEN_FOLDED` 且 `Rosen::DisplayManager::GetFoldStatus()` 为 `FOLDED`
- **THEN** 返回 true，其余返回 false

#### Scenario: 关闭超级隐私重新拨号
- **WHEN** `CloseCallSuperPrivacyMode` 被隐私模式确认框回调
- **THEN** `SuperPrivacyManagerClient::SetSuperPrivacyMode(OFF, SOURCE_CALL=2)` 成功（`SUPER_PRIVACY_MODE_REQUEST_SUCCESS`=0）时重新 `DialCall`，拨号失败则 `RestoreSuperPrivacyMode`（旧模式为 ALWAYS_ON/ON_WHEN_FOLDED 且当前值已变时恢复旧模式）；应答场景 `CloseAnswerSuperPrivacyMode` 成功后补发 `AnswerCall` 并上报模式变化

### Requirement: NOT_SUPPORT_MULTICALL 应答前先挂第一路
系统 SHALL 在定义 `NOT_SUPPORT_MULTICALL` 时由 `AnswerCall` 入口先执行 `HangUpFirstCall`：按对象表双呼形态（`IsTwoCallBtCallAndESIM`/`IsTwoCallBtCall`/`IsTwoCallESIMCall`）决定是否先释放既有通话再接听新来电；未定义该宏时该路径不存在。

#### Scenario: 双呼形态判定分发
- **WHEN** `HangUpFirstCall(secondCallId)` 时对象表分别为"蓝牙+eSIM 混合且号码不同"、"纯蓝牙双呼"、"纯 eSIM 双呼"（`IsTwoCallESIMCall` 恒 false，见对象层规格）
- **THEN** 仅第一形态返回 true 并执行 `HangUpFirstCallBtAndESIM`（第二路自动接听）；纯蓝牙/纯 eSIM 形态按 HMOS 现状不释放第一路（`IsTwoCallESIMCall` 恒 false 导致 eSIM 分支不可达）

#### Scenario: 先挂后接执行
- **WHEN** `HangUpFirstCallBySecondCallID(secondCallId, secondAutoAnswer)` 执行
- **THEN** 第二路为 INCOMING/WAITING 时置 `SetAutoAnswerState(secondAutoAnswer)`；再对第一路按状态处理：ACTIVE/DIALING/ALERTING 的 `HangUpCall`，INCOMING/WAITING 的 `RejectCall`（第一路与第二路号码相同时跳过拒接避免误杀同号新来电）

### Requirement: VoIP 状态注入与畅连冲突
系统 SHALL 由 SetVoIPCallState/SetVoIPCallInfo 接收畅连（meetime）侧注入的 VoIP 通话状态，维护 `VoIPCallState_`、`voipCallObjectList_` 与蓝牙同步。

#### Scenario: 总状态注入
- **WHEN** `SetVoIPCallState(state)` 收到 `CALL_STATE_ANSWERED`/`CALL_STATE_OFFHOOK`/`CALL_STATE_IDLE`
- **THEN** 更新 `VoIPCallState_` 并 `CallStateReportProxy::UpdateCallStateForVoIPOrRestart`；ANSWERED 时逐个挂断对象表全部通话、OFFHOOK 时 `HangUpVoipCall`（VoIP 活动的跳过、INCOMING 的拒接、其余挂断）、IDLE 时若 `AnsweredCallQueue_` 有排队应答则补发 `AnswerCall`；IDLE/UNKNOWN 时注销 `ApplicationStateObserver`，否则经 `AppStateObserver` 向 `AppMgr` 注册应用状态观察者

#### Scenario: 单通话信息注入
- **WHEN** `SetVoIPCallInfo(callId, state, phoneNumber)` 且 `IsSupportSetVoipInfo`（系统参数 `const.telephony.read_set_voip_call_info` 非 "false"）通过、callId 非 `ILLEGAL_CALLID`（-1）
- **THEN** 按 state 分发 `HandleVoipConnected`（置 ACTIVE 并上报 INCOMING→ACTIVE）、`HandleVoipIncoming`（已有通话时置 WAITING 否则 INCOMING，入 `voipCallObjectList_` 并 `SetVirtualCall(false)`）、`HandleVoipDisconnected`（上报 ACTIVE→DISCONNECTED、出表、`SetVirtualCall(true)`，存在 WAITING 载波通话时向蓝牙补报该路 INCOMING）、`HandleVoipAlerting`（置 ALERTING 入表）；最后记录 `VoipCallInfo_` 并经 `BluetoothCallManager::SendBtCallState` 同步 HFP

#### Scenario: 非法 callId 与开关关闭
- **WHEN** callId 为 `ILLEGAL_CALLID` 或系统参数为 "false"
- **THEN** 前者 `ClearVoipList` 清空 VoIP 信息表并返回 `TELEPHONY_ERROR`；后者直接返回 `TELEPHONY_ERROR`

### Requirement: 通话界面服务连接与延迟断开
系统 SHALL 由 `ConnectCallUiService(bool)` + `ShouldDisconnectService` + ffrt 延迟任务管理通话 UI（`CallConnectAbility`）的连接/延迟断开（`DISCONNECT_DELAY_TIME` 1000000 微秒）。

#### Scenario: 连接时取消挂断定时
- **WHEN** `ConnectCallUiService(true)` 且已有挂断延迟任务（`alarmSeted`）
- **THEN** `ffrt::skip` 取消任务后重新 `ConnectAbility`；无任务时直接连接并置 `shouldDisconnect = false`

#### Scenario: 断开时挂起延迟任务
- **WHEN** `ConnectCallUiService(false)`
- **THEN** 置 `shouldDisconnect = true` 并以 `ffrt::submit_h(..., delay(DISCONNECT_DELAY_TIME))` 投递 `handler()`：到期时对象表已无通话才真正 `DisconnectAbility`，否则保持连接

### Requirement: 通话记录与通知补发
系统 SHALL 由 AddCallLogAndNotification/AddBlockLogAndNotification/RemoveMissedIncomingCallNotification 补发未接/拦截记录与通知。

#### Scenario: 未接来电补记
- **WHEN** 调用 `AddCallLogAndNotification(call)`
- **THEN** 置 `SetAnswerType(CALL_ANSWER_MISSED)`，经 `CallRecordsManager::CallStateUpdated(INCOMING→DISCONNECTED)` 记录并 `MissedCallNotification::PublishMissedCallEvent` 通知；拦截来电走 `AddBlockLogAndNotification`（`CALL_ANSWER_BLOCKED` + `PublishBlockedCallEvent`）

#### Scenario: 清除未接通知
- **WHEN** 调用 `RemoveMissedIncomingCallNotification`
- **THEN** 透传 `CallRecordsManager::RemoveMissedIncomingCallNotification`

### Requirement: 功耗锁与全量断开
系统 SHALL 由 AcquireIncomingLock/ReleaseIncomingLock（经 `IncomingCallWakeup`）管理来电唤醒锁，由 AcquireDisconnectedLock/ReleaseDisconnectedLock（`ABILITY_POWER_SUPPORT` 下 `PowerMgr::RunningLock`，超时 `DISCONNECTED_LOCK_TIMEOUT`=2000ms）管理断开期运行锁，由 `DisconnectAllCalls` 全量清理通话。

#### Scenario: 全量断开
- **WHEN** 调用 `DisconnectAllCalls`
- **THEN** 遍历对象表：`TYPE_BLUETOOTH` 跳过，`CALL_RUNNING_STATE_RINGING` 的走 `RejectCall`，其余走 `HangUpCall`

#### Scenario: 功耗锁分支
- **WHEN** 定义 `ABILITY_POWER_SUPPORT`（powermgr 部件在）时调用 `AcquireDisconnectedLock`/`ReleaseDisconnectedLock`
- **THEN** 创建/持有 `RUNNINGLOCK_BACKGROUND_PHONE` 运行锁并 Lock/UnLock；未定义该宏时两函数为空实现

### Requirement: 系统事件订阅
系统 SHALL 由 `SubscriberSaStateChange` 订阅 `COMMON_EVENT_SERVICE_ID` 的 SA 上下线，`SystemAbilityListener::OnAddSystemAbility` 时注册各公共事件订阅（`CallBroadcastSubscriber`），`OnRemoveSystemAbility` 时统一退订。

#### Scenario: SA 上线注册订阅
- **WHEN** `COMMON_EVENT_SERVICE_ID` 上线
- **THEN** 依次注册：通用订阅（SIM 状态变化/屏幕解锁/蓝牙远端设备名更新/用户切换/关机）、联系人页面状态变化（`event.custom.contacts.PAGE_STATE_CHANGE`）、卫星高温（`usual.event.thermal.satcomm.HIGH_TEMP_LEVEL`，发布者 uid `SATCOMM_UID`=1096）、超级隐私模式（`usual.event.SUPER_PRIVACY_MODE`，发布者 `com.settings`）、HSDR（`usual.event.HSDR_EVENT`，发布者 `com.hsdr`）、静音键（`multimodal.event.MUTE_KEY_PRESS`）；定义 `HFP_ASYNC_ENABLE` 时额外订阅 `usual.event.bluetooth.CONNECT_HFP_HF`，未定义时不订阅

#### Scenario: SA 下线退订
- **WHEN** `COMMON_EVENT_SERVICE_ID` 下线
- **THEN** 遍历 `subscriberPtrList_` 逐个 `CommonEventManager::UnSubscribeCommonEvent` 并清空列表；`UnInit` 同样退订

#### Scenario: 耳机按键处理恒不编译
- **WHEN** 编译单元未定义 `ABILITY_MEDIA_SUPPORT`
- **THEN** `onButtonDealing`（短按接听/挂断、长按拒接/静音的耳机按键处理）不参与编译，本仓该宏未定义、此路径在基线中不存在

### Requirement: 佩戴状态与来电闪光提醒
系统 SHALL 由 `WearStatusObserver`/`RegisterObserver`/`SetWearState`/`IsNotWearOnWrist` 维护手表佩戴状态（DataShare 设置项 `wear_status`，"1"→`WEAR_STATUS_OFF`、"2"→`WEAR_STATUS_ON`、其余 `WEAR_STATUS_INVALID`），由 StartFlashRemind/StopFlashRemind/ClearFlashReminder 管理来电闪光提醒（`IncomingFlashReminder`，`EventRunner` 名 `handler_incoming_flash_reminder`）。

#### Scenario: 佩戴状态订阅
- **WHEN** `RegisterObserver` 以 `SettingsDataShareHelper`（uri key=wear_status）注册 `WearStatusObserver`
- **THEN** DataShare 变化回调 `OnChange` 查询 wear_status 并 `SetWearState`；`IsNotWearOnWrist` 仅在 `WEAR_STATUS_OFF` 时返回 true

#### Scenario: 来电闪光提醒
- **WHEN** `StartFlashRemind` 时 `IncomingFlashReminder::IsFlashRemindNecessary()` 判定需要闪光
- **THEN** 启动闪光提醒（到期自动 `ClearFlashReminder`）；不需要时清空提醒对象不启动；`StopFlashRemind`（应答/拒接路径调用）停止提醒

#### Scenario: 视频铃声播放失败回退
- **WHEN** `HandleVideoRingPlayFail` 且存在振铃载波通话、非免打扰静默
- **THEN** 清空该通话联系人 `ringtonePath` 后 `AudioControlManager::PlayRingtone` 回退系统铃声