# Spec Delta

## REMOVED Requirements

### Requirement: 超级隐私模式拨号拦截

**Reason**: AGENTS「功能范围」明确 liteOS 不支持超级隐私（"不支持：……超级隐私……相关代码无需迁移"）；其依赖的 `CallSuperPrivacyControlManager` 与 `CallDialog` 隐私模式确认框分别随源文件删除与对话框桩化（design D7、D6）。
**Migration**: 删除源文件 `services/call/src/call_superprivacy_control_manager.cpp`（含头文件）并同步 `callmanager.gni`（design D7 表）；`call_policy.cpp` 的 `CallPolicy::SuperPrivacyMode` 拨号拦截段与 `CallDialog::DialogConnectPrivpacyModeExtension` 调用移除；`CloseCallSuperPrivacyMode` 重新拨号回调链随管理器删除。恢复条件：手表平台引入超级隐私框架后按基线重建拦截链与确认框回调。

### Requirement: CanDialMulityCall 多呼与视频拨号约束

**Reason**: 该需求的两个分支分别依赖视频通话（`GetVideoCallWaiting` 视频等待约束、`TYPE_VIDEO`/`HasVideoCall`）与分布式通话（`DistributedCommunicationManager::IsConnected`/`IsSinkRole`），两者均被 AGENTS「功能范围」明确不支持（视频通话、分布式通话），liteOS 上无可达分支。
**Migration**: `call_policy.cpp` 的 `CanDialMulityCall` 视频通话等待占用分支与分布式 sink 禁拨分支删除（`distributed_call_manager.cpp` 等 12 个分布式源文件随 D7 删除清单整体删除并同步 `callmanager.gni`；视频判定见「视频拨号能力归一」需求的 Migration）。恢复条件：支持视频通话或分布式通话后重建对应约束。

### Requirement: 视频拨号能力归一

**Reason**: AGENTS「功能范围」明确 liteOS 不支持视频通话（`ABILITY_CAMERA_SUPPORT` 恒关）；design D7 明确 `ABILITY_CONFIG_SUPPORT`/`ABILIT_CONFIG_SUPPORT` 守卫块删除（config 部件不迁移），任务范围明确该守卫下的 `IsSupportVideoCall` 分支移除。
**Migration**: `call_policy.cpp` 的 `CallPolicy::IsSupportVideoCall`（含 `GetCarrierConfig(ITEM_VIDEO_CALL)` 分支、`CallNumberUtils::IsCarrierVtConfig` 运营商 VT 判定）与 `call_control_manager.cpp` 的 `SetCallTypeExtras` 视频归一/IMS 升级段删除；`video_control_manager.cpp` 随 design D7 删除清单删除并同步 `callmanager.gni`；拨号入口不再改写 videoState/callType 为视频形态。恢复条件：支持视频通话后重建归一链与视频控制管理器。

### Requirement: 会议控制路径

**Reason**: AGENTS「功能范围」明确 liteOS 不支持会议通话（"不支持：……会议通话……相关代码无需迁移"）；会议对象族删除见 call-object-management delta「会议对象模型与 CS/IMS 会议联动」。
**Migration**: `call_control_manager.cpp` 中 `CombineConference`/`SeparateConference`/`KickOutFromConference`/`GetMainCallId`/`GetSubCallIdList`/`GetCallIdListForConference` 会议控制入口与 `call_request_handler.cpp`/`call_request_process.cpp` 的 `CombineConferenceRequest`/`SeparateConferenceRequest`/`KickOutFromConferenceRequest` 下发链删除；`CallPolicy::InviteToConferencePolicy`/`JoinConference` 分支删除（见本 delta「DTMF/RTT/后拨与邀会指令路径」）；会议对象族源文件删除并同步 `callmanager.gni`（design D7 表）。恢复条件：支持会议通话后重建控制路径与下发链。

### Requirement: CallSuperPrivacyControlManager 超级隐私管理

**Reason**: AGENTS「功能范围」明确 liteOS 不支持超级隐私；design D7 被删文件表列出 `call_superprivacy_control_manager.cpp`，`frameworks/native` 侧 `super_privacy_manager_client.cpp` 一并删除。
**Migration**: 删除源文件 `services/call/src/call_superprivacy_control_manager.cpp`、`frameworks/native/src/super_privacy_manager_client.cpp`（含对应头文件）并同步 `callmanager.gni`（design D7 表）；`parameter_stub` 侧不提供 `persist.super_privacy.mode` 监听（该 WatchParameter 链整体消失）；`call_status_manager.cpp` 断开路径对 `RestoreSuperPrivacyMode` 的调用、`CallControlManager::Init` 的 `RegisterSuperPrivacyMode` 注册与应答/拨号路径的 `CurrentIsSuperPrivacyMode` 拦截同步移除。恢复条件：引入超级隐私框架后重建参数监听、通话清理与模式恢复链。

## MODIFIED Requirements

### Requirement: DialCall 拨号入口链
系统 SHALL 由 `CallControlManager::DialCall` 承载拨号入口：号码合法性校验 → 紧急号码识别 → `CanDial` 策略 → 暂存拨号参数 → 转发 `CallRequestHandler::DialCall`（同步调用）；因卫星/蓝牙通话不支持（AGENTS），基线入口的卫星/蓝牙拨号类型改写分支移除。ECC 判定链保留，需人工复核（ECC）（proposal「BREAKING」清单）。

#### Scenario: 号码合法性
- **WHEN** 号码为空或长度超过 `kMaxNumberLen`
- **THEN** `NumberLegalityCheck` 分别返回 `CALL_ERR_PHONE_NUMBER_EMPTY`/`CALL_ERR_NUMBER_OUT_OF_RANGE`，拨号终止（行为照抄基线）

#### Scenario: 紧急号码识别
- **WHEN** 号码经 `CallNumberUtils::RemoveSeparatorsPhoneNumber` 清洗后 `CheckNumberIsEmergency` 判定为紧急号码
- **THEN** extras 写入 `dialScene = CALL_EMERGENCY`；`CallNumberUtils` 的 libphonenumber 依赖经 `stub/phonenumber_stub` 打桩（design D5），紧急号码识别链完整保留（需人工复核（ECC），须可成紧急呼叫拨号 gtest）

#### Scenario: 卫星拨号改写
- **WHEN** `DialCall` 评估拨号类型
- **THEN** 因卫星通话不支持（AGENTS），基线 `SatelliteCallControl::IsSatelliteSwitchEnable`/`IsAllowedSatelliteDialCall` 卫星拨号改写分支随 `satellite_call_control.cpp` 删除（design D7）移除，不存在 `callType = TYPE_SATELLITE` 改写路径

#### Scenario: 蓝牙拨号改写
- **WHEN** `DialCall` 评估拨号类型
- **THEN** 因 BLUETOOTH 类型通话不支持（AGENTS），基线 extras `dialType` 为 `DIAL_BLUETOOTH_TYPE` 时写入 `callType = TYPE_BLUETOOTH` 的改写分支移除

#### Scenario: 策略通过后暂存并下发
- **WHEN** `CanDial`（= `DialPolicy` + 常规判定，视频/分布式多呼约束已移除）通过
- **THEN** `PackageDialInformation` 把号码/callType/accountId/dialType/videoState/bundleName/isEcc 暂存到 `dialSrcInfo_`/`extras_`，调用 `CallRequestHandlerPtr_->DialCall()`；策略失败经 `WriteDialCallFaultEvent` 记录（`CallManagerHisysevent` 保留、内部经 `stub/hisysevent_stub` 输出日志，design D5）后返回错误码

测试落点：`call_manager_zero_gtest/src/zero_branch2_test.cpp` 新增 `Telephony_CallControlManager_Dial_01x` 系用例（空号/超长错误码、紧急号码识别经桩、卫星/蓝牙改写分支缺失断言、暂存下发）。

### Requirement: CallPolicy::DialPolicy 拨号参数判定链
系统 SHALL 由 `CallPolicy::DialPolicy` 依次校验拨号参数与既有通话状态，任一环节失败即终止拨号；因 EDM 企业禁拨不支持（AGENTS），基线 EDM 禁拨叶子移除（`edm_call_policy.cpp` 随 design D7 删除清单删除）。

#### Scenario: 拨号类型与场景参数合法性
- **WHEN** extras 的 `dialType` 不属于 `DIAL_CARRIER_TYPE`/`DIAL_VOICE_MAIL_TYPE`，或 `callType` 不属于 `TYPE_CS`/`TYPE_IMS`，或 `dialScene` 不属于 `CALL_NORMAL`/`CALL_PRIVILEGED`/`CALL_EMERGENCY`，或 `videoState` 非 `TYPE_VOICE`/`TYPE_VIDEO`
- **THEN** 分别返回 `TELEPHONY_ERR_ARGUMENT_INVALID`/`CALL_ERR_UNKNOW_CALL_TYPE`/`TELEPHONY_ERR_ARGUMENT_INVALID`/`TELEPHONY_ERR_ARGUMENT_INVALID`；因 OTT/蓝牙/卫星通话不支持，基线合法集中的 `DIAL_OTT_TYPE`/`DIAL_BLUETOOTH_TYPE` 与 `TYPE_OTT`/`TYPE_SATELLITE`/`TYPE_BLUETOOTH` 移除，命中即拒绝；`videoState` 参数校验照抄保留（视频拨号归一链已移除，见 REMOVED「视频拨号能力归一」）

#### Scenario: EDM 禁拨
- **WHEN** `DialPolicy` 评估拨号使能
- **THEN** 因 EDM 企业禁拨不支持（AGENTS），`IsDialingEnable(phoneNum)`/`EdmCallPolicy::IsCallEnable` 判定（`persist.edm.telephony_call_disable`、`POLICY_FLAG_BLOCK`/`POLICY_FLAG_TRUST` 黑白名单）随 `edm_call_policy.cpp` 删除（design D7 utils 表）而移除，拨号链不再做 EDM 禁拨校验

#### Scenario: 无效卡槽回退
- **WHEN** `dialType` 为 `DIAL_CARRIER_TYPE` 且 `CallNumberUtils::SelectAccountId` 判定 accountId 无效
- **THEN** extras 的 `accountId` 改写为 0 并继续（照抄；号码工具数据面经 `CellularDataClient::GetInstance().Xxx()` 桩，design D4）

#### Scenario: 非 ECC 拨号的占用校验
- **WHEN** 非 ECC 拨号，且存在语音振铃通话（`IsVoiceCallValid`：已有非 VoIP、TYPE_VOICE 的 RINGING 通话）、或 `HasNewCall` 报新通话未完成、或 `HasEmergencyCall` 报紧急呼叫进行中
- **THEN** 返回 `CALL_ERR_CALL_COUNTS_EXCEED_LIMIT`（行为照抄基线；ECC 豁免语义需人工复核（ECC））

测试落点：`call_manager_zero_gtest/src/zero_branch2_test.cpp` 新增 `Telephony_CallPolicy_01x` 系用例（参数合法性矩阵、EDM 分支缺失断言、占用校验）。

### Requirement: HasNormalCall 常规拨号前置判定链
系统 SHALL 由 `CallPolicy::HasNormalCall` 对非 ECC 的载波拨号执行 SIM/飞行模式/网络注册/CT 卡 IMS 注册四段判定，失败时弹出对应对话框（对话框经 `stub/` 打桩、调用点 todo [callUi]，design D6）；数据库查询点标 [database] todo（design D6 表）。ECC 豁免保留，需人工复核（ECC）。

#### Scenario: 判定豁免
- **WHEN** `isEcc` 为真
- **THEN** 直接返回 `TELEPHONY_SUCCESS`；因卫星/蓝牙通话不支持，基线 `callType` 为 `TYPE_SATELLITE`/`TYPE_BLUETOOTH` 的豁免条件随对应对象消失而移除（ECC 豁免需人工复核（ECC））

#### Scenario: 无 SIM 卡
- **WHEN** `CoreServiceClient::HasSimCard(slotId)` 返回无卡
- **THEN** `DialogConnectExtension("CALL_FAILED_NO_SIM_CARD")` 并返回 `TELEPHONY_ERR_NO_SIM_CARD`；core_service 查询经 `CoreServiceConnection` 适配器内的 `CoreServiceClient::GetInstance()` 桩（design D4），对话框连接经 callUi 桩（调用点标 `// todo!!! [callUi] ref to call_dialog.cpp DialogConnectExtension`）

#### Scenario: 飞行模式
- **WHEN** `CallDataBaseHelper::GetAirplaneMode` 查询设置库得到飞行模式开启
- **THEN** `DialogConnectExtension("CALL_FAILED_IN_AIRPLANE_MODE")` 并返回 `TELEPHONY_ERR_AIRPLANE_MODE_ON`；DataShare 查询暂不调用，查询点标 `// todo!!! [database] ref to call_data_base_helper.cpp GetAirplaneMode`（design D6 数据库行），判定逻辑与错误码照抄

#### Scenario: 无服务
- **WHEN** `CoreServiceClient::GetNetworkState(slotId)` 的注册态非 `REG_STATE_IN_SERVICE`
- **THEN** `DialogConnectExtension("CALL_FAILED_NO_SERVICE")` 并返回 `TELEPHONY_ERR_NETWORK_NOT_IN_SERVICE`（查询经 `CoreServiceClient::GetInstance()` 桩，design D4，其余照抄）

#### Scenario: CT 卡无 IMS
- **WHEN** `CoreServiceClient::IsCTSimCard` 判定为 CT 卡，且非漫游、`GetImsRegStatus(TYPE_VOICE)` 未注册，且 `IsCtSimCardSwitchToChnOrMc`（`GetResidentNetworkNumeric` 与 `GetSimOperatorNumeric` 的 MCC 段同为中国 `CHN_MCC` 或澳门 `MC_MCC`）为 true
- **THEN** `DialogConnectExtension("CALL_FAILED_CTCARD_NO_IMS", slotId)` 并返回 `CALL_ERR_DIAL_FAILED`（查询均经 `CoreServiceClient::GetInstance()` 桩，design D4，其余照抄）

测试落点：`call_manager_zero_gtest/src/zero_branch2_test.cpp` 新增 `Telephony_CallPolicy_02x` 系用例（四段判定的桩注入返回值驱动、错误码矩阵）。

### Requirement: AnswerCall 应答入口链
系统 SHALL 由 `CallControlManager::AnswerCall` 承载应答入口：定位振铃通话 → 状态上报 → VoIP 冲突处理 → 策略校验 → 异步下发；因视频彩振、超级隐私、卫星/视频预处理不支持（AGENTS），基线对应分支移除。

#### Scenario: callId 定位
- **WHEN** 传入 `INVALID_CALLID`（0）且当前存在 `CALL_RUNNING_STATE_RINGING` 通话
- **THEN** 取该振铃通话的 callId 继续处理；无振铃通话返回 `TELEPHONY_ERR_LOCAL_PTR_NULL`（行为照抄基线）

#### Scenario: 视频彩振应答关扬声器
- **WHEN** `AnswerCall` 执行应答预处理
- **THEN** 因视频彩振（crsType==CRS_TYPE）不支持（AGENTS），基线目标通话 `GetCrsType() == CRS_TYPE` 且应答 videoState 非 `TYPE_VIDEO` 时 `AudioProxy::SetSpeakerDevActive(false)` 关闭免提扬声器的分支移除，不再产生彩振应答处理

#### Scenario: 超级隐私应答拦截
- **WHEN** `AnswerCall` 执行应答预处理
- **THEN** 因超级隐私不支持（AGENTS），基线 `CurrentIsSuperPrivacyMode` 拦截（`AudioControlManager::MuteRinger` 静铃 + `CallDialog::DialogConnectAnswerPrivpacyModeExtension` 弹窗、返回 `TELEPHONY_SUCCESS` 不下发）分支随 `CallSuperPrivacyControlManager` 删除移除（见 REMOVED「CallSuperPrivacyControlManager 超级隐私管理」）

#### Scenario: 卫星/视频应答预处理
- **WHEN** `AnswerCall` 执行应答预处理
- **THEN** 因卫星与视频通话不支持（AGENTS），基线"目标通话为 `TYPE_IMS` 且应答 videoState 与对象当前 `GetVideoStateType()` 不同时更新 videoState 并 `IMSCall::InitVideoCall`"与"为 `TYPE_SATELLITE` 且存在 ACTIVE 卫星通话时先挂断"两个分支移除

#### Scenario: VoIP 活动时排队应答
- **WHEN** `VoIPCallState_` 非 `CALL_STATE_IDLE` 且目标通话非 `TYPE_VOIP`
- **THEN** 把 callId/videoState 存入 `AnsweredCallQueue_` 并返回成功，待 VoIP 转为 IDLE 时（见 SetVoIPCallState）自动补发 `AnswerCall`（行为照抄基线，VoIP 冲突链保留）

#### Scenario: 策略失败转 VoIP 事件
- **WHEN** `AnswerCallPolicy` 失败且存在 VoIP 通话（`IsVoipCallExist`）
- **THEN** 经 `sendEventToVoip(EVENT_ANSWER_VOIP_CALL)` 走事件通知路径（出口经 `VoipCallConnection` 适配器/`VoipCallClient::GetInstance()` 桩，design D4）并返回成功；否则记录 `WriteAnswerCallFaultEvent`（经 `stub/hisysevent_stub` 日志输出，design D5）并返回错误码

测试落点：`call_manager_zero_gtest/src/zero_branch2_test.cpp` 新增 `Telephony_CallControlManager_Answer_01x` 系用例（callId 定位、排队应答、策略失败转 VoIP 事件、彩振/超级隐私/卫星分支缺失断言）。

### Requirement: CarrierAndVoipConflictProcess 载波与 VoIP 冲突处理
系统 SHALL 在载波通话应答成功（`CALL_STATUS_ANSWERED`）时清理冲突的 VoIP 通话；VoIP 真实对端暂不支持但冲突处理逻辑保留（AGENTS「暂不支持 VOIP……解决畅连通话和蜂窝通话冲突场景」；design D1/D8）。

#### Scenario: 仅应答时触发
- **WHEN** `callState` 非 `CALL_STATUS_ANSWERED`
- **THEN** 不做任何处理直接返回成功（行为照抄基线）

#### Scenario: 清理冲突 VoIP
- **WHEN** 被应答通话为 `TYPE_CS`/`TYPE_IMS`，且 VoIP 列表中存在 INCOMING 或 DIALING 状态的通话
- **THEN** INCOMING 的执行 `RejectCall`（携带原因 "CarrierAndVoipConflictProcess"），DIALING 的执行 `HangUpCall`；因卫星通话不支持，基线类型集合中的 `TYPE_SATELLITE` 条件移除；VoIP 侧操作经 `VoipCallClient::GetInstance()` 桩驱动（design D4）

测试落点：`call_manager_zero_gtest/src/zero_branch5_test.cpp` 新增 `Telephony_CallControlManager_VoipConflict_01x` 系用例（桩注入 VoIP INCOMING/DIALING 状态驱动清理矩阵）。

### Requirement: RejectCall 与 HangUpCall 挂断路径
系统 SHALL 由 `RejectCall`/`HangUpCall` 承载拒接与挂断入口，含默认目标选择、策略校验与 VoIP 事件回退；等待通话（waitingCall）链在单卡下保留。

#### Scenario: 拒接默认目标
- **WHEN** `RejectCall` 传入 `INVALID_CALLID` 且存在振铃通话
- **THEN** 取该通话 callId；`RejectCallPolicy` 校验其处于 `CALL_STATUS_INCOMING`/`CALL_STATUS_WAITING`（否则 `CALL_ERR_ILLEGAL_CALL_OPERATION`），通过后同步转发 `CallRequestHandlerPtr_->RejectCall(callId, rejectWithMessage, textMessage)` 并上报 `WriteVoipCallStatisticalEvent(callId, "MtBannerReject")`（经 `stub/hisysevent_stub` 日志输出，design D5）（行为照抄基线）

#### Scenario: 挂断默认目标顺选
- **WHEN** `HangUpCall` 传入 `INVALID_CALLID`
- **THEN** 按 ACTIVE → DIALING → CONNECTING → HOLD 的顺序取第一个存在的通话；全部不存在返回 `TELEPHONY_ERR_ARGUMENT_INVALID`（行为照抄基线）

#### Scenario: 挂断策略失败回退 VoIP
- **WHEN** `HangUpPolicy` 失败且 callId >= `VOIP_CALL_MINIMUM`（10000）且存在 VoIP 通话
- **THEN** 分别经 `sendEventToVoip(EVENT_REJECT_VOIP_CALL)`（拒接路径）/`sendEventToVoip(EVENT_HANGUP_VOIP_CALL)`（挂断路径）回退（出口经 `VoipCallClient::GetInstance()` 桩）并返回成功（照抄）

#### Scenario: MO 拨号处理中延迟挂断
- **WHEN** `HangUpCall` 时 `CallRequestEventHandlerHelper::HasPendingMo(callId)` 为 true（拨号请求已下发、CLCC 流程未完成）
- **THEN** 置 `SetPendingMo(false, -1)`、`SetPendingHangup(true, callId)` 暂存挂断请求（待 `CallStatusManager` 在拨号流程收尾时消费），本次调用返回成功不再下发（行为照抄基线）

测试落点：`call_manager_zero_gtest/src/zero_branch2_test.cpp` 新增 `Telephony_CallControlManager_HangUp_01x` 系用例（默认目标顺选矩阵、VoIP 回退、MO 挂断暂存）。

### Requirement: HoldCall/UnHoldCall/SwitchCall 保持与切换路径
系统 SHALL 由 Hold/UnHold/Switch 三个入口先经对应 CallPolicy 前置校验再转发 `CallRequestHandler`（行为照抄基线，无裁剪点）。

#### Scenario: 保持前置
- **WHEN** `HoldCallPolicy` 校验目标通话运行态非 `CALL_RUNNING_STATE_ACTIVE`
- **THEN** 返回 `CALL_ERR_CALL_IS_NOT_ACTIVATED`，不转发

#### Scenario: 恢复前置
- **WHEN** `UnHoldCallPolicy` 校验目标通话运行态非 `CALL_RUNNING_STATE_HOLD`
- **THEN** 返回 `CALL_ERR_CALL_IS_NOT_ON_HOLDING`，不转发

#### Scenario: 切换前置
- **WHEN** `SwitchCallPolicy` 校验载波通话数少于 2（`onlyTwoCall_`）、目标通话非 `CALL_STATUS_HOLDING`、或存在 DIALING/ALERTING 通话
- **THEN** 分别返回 `CALL_ERR_PHONE_CALLS_TOO_FEW`/`CALL_ERR_ILLEGAL_CALL_OPERATION`，不转发

测试落点：`call_manager_zero_gtest/src/zero_branch2_test.cpp` 新增 `Telephony_CallControlManager_Hold_01x` 系用例（三策略错误码矩阵）。

### Requirement: DTMF/RTT/后拨与邀会指令路径
系统 SHALL 由 StartDtmf/StopDtmf/PostDialProceed/StartRtt/StopRtt 承载通话中指令：对象存活性与策略校验后转发；因会议通话不支持，基线 `JoinConference` 邀会分支移除（AGENTS）。

#### Scenario: DTMF 校验与提示音
- **WHEN** `StartDtmf`/`StopDtmf` 的目标通话不存在或 `IsAliveState()` 为 false
- **THEN** 分别返回 `TELEPHONY_ERR_ARGUMENT_INVALID`/`CALL_ERR_CALL_STATE_MISMATCH_OPERATION`；`StartDtmf` 成功转发对象 `StartDtmf` 后经打桩 EventHandler 异步执行 `AudioControlManager::PlayDtmfTone`（`ffrt::submit` 替换，design D8；audio 调用点标 `// todo!!! [audio] ref to audio_proxy.cpp PlayDtmfTone`，design D6），`StopDtmf` 同步 `StopDtmfTone`（其 audio 出口同经 [audio] todo 桩）

#### Scenario: RTT 仅限活动 IMS 通话
- **WHEN** `StartRttPolicy`/`StopRttPolicy` 校验目标通话非 `TYPE_IMS`（`CALL_ERR_UNSUPPORTED_NETWORK_TYPE`）或状态非 `CALL_STATUS_ACTIVE`（`CALL_ERR_ILLEGAL_CALL_OPERATION`）
- **THEN** 拒绝并返回；通过后转发 `CallRequestHandlerPtr_->StartRtt`/`StopRtt`（下发链至 `IMSCall::StartRtt/StopRtt`，适配器出口标 `// todo!!! [rtt] ref to cellular_call_connection.cpp StartRtt/StopRtt`，design D6，见 call-object-management delta）

#### Scenario: 后拨确认
- **WHEN** `PostDialProceed` 的目标通话非存活态
- **THEN** 返回 `CALL_ERR_CALL_STATE_MISMATCH_OPERATION`；通过后转发对象 `PostDialProceed(proceed)`（行为照抄基线）

#### Scenario: 邀请入会校验
- **WHEN** 评估邀请入会
- **THEN** 因会议通话不支持（AGENTS），`InviteToConferencePolicy`（callId/号码列表校验、`ImsConference::GetMainCall()` 比对）与 `CallRequestHandlerPtr_->JoinConference` 下发分支随会议移除，liteOS 不提供邀会路径

测试落点：`special_branch2_test.cpp` 新增 `Telephony_CallControlManager_DtmfRtt_01x` 系用例（DTMF 存活性校验、RTT 类型/状态校验、后拨确认、邀会分支缺失断言）。

### Requirement: 补充业务设置接口族
系统 SHALL 由 GetCallWaiting/SetCallWaiting/GetCallRestriction/SetCallRestriction/SetCallRestrictionPassword/GetCallTransferInfo/SetCallTransferInfo/CanSetCallTransferTime/SetCallPreferenceMode/GetImsConfig/SetImsConfig/GetImsFeatureValue/SetImsFeatureValue/EnableImsSwitch/DisableImsSwitch/IsImsSwitchEnabled/SetVoNRState/GetVoNRState/CloseUnFinishedUssd 统一按"CallPolicy slotId 前置 → `callSettingManagerPtr_` 转发"模式工作（UT/USSI/USSD/MMI 补充业务须支持，AGENTS 说明第 1 条：CALL_MANAGER_CALL_TRANSFER 是跨设备通话转移，UT 呼叫转移不在裁剪范围）。

#### Scenario: slotId 前置校验
- **WHEN** 任一补充业务接口的 `CallPolicy::IsValidSlotId(slotId)` 失败（含 `VoNRStatePolicy` 对 state 非 `VONR_STATE_ON`/`VONR_STATE_OFF` 的附加校验）
- **THEN** 返回 `CALL_ERR_INVALID_SLOT_ID`（VoNR state 非法返回 `TELEPHONY_ERR_ARGUMENT_INVALID`），不转发（行为照抄基线）

#### Scenario: 设置管理器转发
- **WHEN** 前置通过且 `callSettingManagerPtr_` 非空
- **THEN** 透传 `CallSettingManager` 对应接口（UT/USSD 补充业务经 `callSettingManagerPtr_` 出口，最终经 `CellularCallConnection` 适配器/`CellularCallClient::GetInstance()` 桩下发，design D4）；`callSettingManagerPtr_` 为空返回 `TELEPHONY_ERR_LOCAL_PTR_NULL`（照抄）

测试落点：`call_manager_zero_gtest/src/zero_branch5_test.cpp` 新增 `Telephony_CallControlManager_SupplSvc_01x` 系用例（slotId 校验、空指针错误码、转发出口断言）。

### Requirement: 音频控制接口
系统 SHALL 由 SetMuted/MuteRinger/SetAudioDevice 承载控制层音频入口；转发保留、经音频能力（audio 框架调用暂不调用、调用点 todo [audio]，design D6）；因语音播报不支持，基线 `CallVoiceAssistantManager::MuteRinger` 调用移除。

#### Scenario: 静音目标选择
- **WHEN** 调用 `SetMuted(isMute)`，取 `CallObjectManager::GetAudioLiveCall` 为目标
- **THEN** 无活动通话返回 `CALL_ERR_AUDIO_SETTING_MUTE_FAILED`；目标为 VoIP 时仅调对象 `SetMute`；目标为 CS/IMS 时对象 `SetMute` 之外再调 `AudioControlManager::SetMute`；其他类型仅调 `AudioControlManager::SetMute`（判定逻辑照抄；`AudioControlManager` 内部 audio_framework 调用点标 `// todo!!! [audio] ref to audio_proxy.cpp SetMute`，design D6）

#### Scenario: 静铃与音频设备
- **WHEN** 调用 `MuteRinger` 或 `SetAudioDevice`
- **THEN** 前者仅调 `AudioControlManager::MuteRinger`（其 audio 出口经 [audio] todo 桩）——因语音播报（HiCar 语音助手）不支持（AGENTS），基线前置的 `CallVoiceAssistantManager::MuteRinger` 调用随 `call_voice_assistant_manager.cpp` 删除（design D7）移除；后者透传 `AudioControlManager::SetAudioDevice(audioDevice, true)`（照抄）

测试落点：`call_manager_zero_gtest/src/zero_branch5_test.cpp` 新增 `Telephony_CallControlManager_Audio_01x` 系用例（静音目标三分支、静铃链路、语音助手调用缺失断言）。

### Requirement: 查询与号码工具族
系统 SHALL 提供 GetCallState/HasCall/HasVoipCall/IsNewCallAllowed/IsRinging/HasEmergency 查询入口及 IsEmergencyPhoneNumber/FormatPhoneNumber/FormatPhoneNumberToE164 号码工具入口；`IsNewCallAllowed` 与"新通话/CeliaCall"无关、保留（design D9 已证明）；因视频通话不支持，基线视频控制接口与 `VideoCallPolicy` 判定移除。

#### Scenario: 应用侧通话状态聚合
- **WHEN** 调用 `GetCallState`
- **THEN** 无蜂窝通话且 VoIP 状态为 IDLE/UNKNOWN 时返回 `CALL_STATE_IDLE`；否则基础 OFFHOOK，且存在振铃通话或 VoIP 为 RINGING 时返回 `CALL_STATE_RINGING`（行为照抄基线）

#### Scenario: 简单存在性查询
- **WHEN** 调用 `HasCall`/`HasVoipCall`/`IsNewCallAllowed`/`IsRinging`/`HasEmergency`
- **THEN** 分别透传对象层 `HasCellularCallExist`+VoIP 状态、`HasVoipCallExist`、`IsNewCallAllowedCreate`（判定非 VoIP 通话处于 CREATE/CONNECTING/DIALING/RINGING 态时禁止再建，design D9 证明与新通话无关、保留）、`HasRingingCall`、`HasEmergencyCall`（照抄）

#### Scenario: 紧急号码判定与号码格式化
- **WHEN** 调用 `IsEmergencyPhoneNumber`（slotId 非法返回 `CALL_ERR_INVALID_SLOT_ID`）或 `FormatPhoneNumber`/`FormatPhoneNumberToE164`
- **THEN** 均透传 `CallNumberUtils::CheckNumberIsEmergency`/`FormatPhoneNumber`/`FormatPhoneNumberToE164`（libphonenumber 依赖经 `stub/phonenumber_stub` 打桩，design D5）；因视频通话不支持，基线附带的 `UpdateImsCallMode` 与 ControlCamera/SetPreviewWindow 等视频控制接口的空实现随视频族移除

#### Scenario: 视频控制前置策略
- **WHEN** 评估视频控制前置策略
- **THEN** 因视频通话不支持（AGENTS），`VideoControlManager` 与其复用的 `CallPolicy::VideoCallPolicy(callId)` 判定随 `video_control_manager.cpp` 删除（design D7）移除，liteOS 不提供视频控制前置判定

测试落点：`call_manager_zero_gtest/src/zero_branch2_test.cpp` 新增 `Telephony_CallControlManager_Query_01x` 系用例（状态聚合、存在性透传、紧急号码经桩判定）。

### Requirement: 状态通知分发与观察者注册
系统 SHALL 由 NotifyNewCallCreated/NotifyCallDestroyed/NotifyCallStateUpdated/NotifyVoipCallStateUpdated/NotifyIncomingCallAnswered/NotifyIncomingCallRejected/NotifyCallEventUpdated 统一经 `callStateListenerPtr_`（`CallStateListener`）分发，并在 `CallStateObserve` 中注册固定观察者清单；因分布式/互信互联/语音播报不支持，对应观察者移除。

#### Scenario: 观察者清单
- **WHEN** `CallControlManager::Init` 调用 `CallStateObserve`
- **THEN** 依次注册 `CallAbilityReportProxy`（直调回调形态，design D3）、`CallStateReportProxy`（core_service 上报出口经 `stub/state_registry_client` 桩，design D4）、`AudioControlManager`、`RejectCallSms`、`MissedCallNotification`、`IncomingCallWakeup`、`CallRecordsManager`；因分布式、互信互联、语音播报不支持（AGENTS），基线清单中的 `DistributedCommunicationManager`、`InteroperableCommunicationManager`、`CallVoiceAssistantManager` 随对应源文件删除（design D7）移除

#### Scenario: 状态变化附加处理
- **WHEN** `NotifyCallStateUpdated` 分发非 VoIP 通话且状态转移命中 `IsCallActivated`（DIALING→ALERTING/DIALING→ACTIVE/INCOMING→ACTIVE/ALERTING→ACTIVE）
- **THEN** ACTIVE/DISCONNECTING→DISCONNECTED 且无保持通话时调 `OnActivedCallDisconnected`（照抄）；因分布式通话不支持，基线 `AudioDeviceManager::CheckAndSwitchDistributedAudioDevice` 与 `DistributedCallManager::IsDCallDeviceSwitchedOn` 的分布式音频切换分支移除

测试落点：`call_manager_zero_gtest/src/zero_branch5_test.cpp` 新增 `Telephony_CallControlManager_Notify_01x` 系用例（观察者注册清单断言、IsCallActivated 计时触发）。

### Requirement: CallRequestHandler ffrt 异步下发
系统 SHALL 由 `CallRequestHandler` 以打桩 EventHandler 异步下发除 DialCall 外的全部控制请求（`ffrt::submit` 替换为 `stub/eventhandler_stub` 提交，保持串行语义，design D8），调用方立即得到 `TELEPHONY_SUCCESS`（`callRequestProcessPtr_` 为空时同步返回 `TELEPHONY_ERR_LOCAL_PTR_NULL`）；因会议不支持，会议族请求移除。

#### Scenario: 异步请求集
- **WHEN** 调用 `AnswerCall`/`RejectCall`/`HangUpCall`/`HoldCall`/`UnHoldCall`/`SwitchCall`/`StartRtt`/`StopRtt`
- **THEN** 对应 `CallRequestProcess::AnswerRequest`/`RejectRequest`/`HangUpRequest`/`HoldRequest`/`UnHoldRequest`/`SwitchRequest`/`StartRttRequest`/`StopRttRequest` 在桩 EventHandler 任务中执行，接口本身恒返回 `TELEPHONY_SUCCESS`；因会议通话不支持，基线集中的 `CombineConference`/`SeparateConference`/`KickOutFromConference` 请求随会议移除

#### Scenario: 拨号与邀会特殊路径
- **WHEN** 调用 `DialCall`
- **THEN** 同步调用 `DialRequest` 并透传其返回值（照抄）；因会议不支持，基线 `JoinConference` 的 ffrt 延迟捕获（`weak_ptr` 捕获 `CallRequestProcess`）邀会路径移除

测试落点：`call_manager_zero_gtest/src/zero_branch2_test.cpp` 新增 `Telephony_CallRequestHandler_01x` 系用例（异步集返回值、空进程指针错误码、会议请求缺失断言）。

### Requirement: CallRequestProcess::DialRequest 拨号请求处理
系统 SHALL 由 `DialRequest` 校验拨号暂态与 FDN 限制后按 `dialType` 分发到 `CarrierDialProcess`/`VoiceMailDialProcess`；因 OTT/蓝牙通话不支持，基线 `OttDialProcess`/`BluetoothDialProcess` 分发分支移除。

#### Scenario: 暂态与号码校验
- **WHEN** `GetDialParaInfo` 的 `isDialing` 为 false 或号码超长
- **THEN** 分别返回 `CALL_ERR_ILLEGAL_CALL_OPERATION`（并记录 `CALL_ERROR_DEVICE_NOT_DIALING` 故障，经 `stub/hisysevent_stub` 日志输出）/`CALL_ERR_NUMBER_OUT_OF_RANGE`（行为照抄基线）

#### Scenario: FDN 固定拨号限制
- **WHEN** 非 ECC、`DIAL_CARRIER_TYPE` 且 `CoreServiceConnection::IsFdnEnabled(slotId)` 为 true，FDN 号码列表为空或去空格后的号码不在列表中
- **THEN** 上报 `EVENT_INVALID_FDN_NUMBER` 事件、`DialogConnectExtension("CALL_FAILED_DUE_TO_FDN")`（经 callUi 桩，调用点标 `// todo!!! [callUi] ref to call_dialog.cpp DialogConnectExtension`）并返回 `CALL_ERR_DIAL_FAILED`；`IsFdnEnabled` 查询经 `CoreServiceConnection` 适配器内 `CoreServiceClient::GetInstance()` 桩（design D4）

#### Scenario: 拨号类型分发
- **WHEN** `HandleDialRequest` 按 `info.dialType` 分发
- **THEN** `DIAL_CARRIER_TYPE`/`DIAL_VOICE_MAIL_TYPE` 走载波流程（后者复用 `CarrierDialProcess`）照抄；因 OTT 通话不支持，基线 `DIAL_OTT_TYPE` 走 `OttDialProcess`（经 `CallAbilityReportProxy::OttCallRequest(OTT_REQUEST_DIAL)` 上报）分支移除；因 BLUETOOTH 通话不支持，基线 `DIAL_BLUETOOTH_TYPE` 走 `BluetoothDialProcess`（经 `BluetoothCallConnection::Dial`）分支移除；未知类型返回 `CALL_ERR_UNKNOW_DIAL_TYPE`（照抄）

测试落点：`call_manager_zero_gtest/src/zero_branch2_test.cpp` 新增 `Telephony_CallRequestProcess_01x` 系用例（暂态校验、FDN 限制经桩、类型分发与未知类型错误码）。

### Requirement: CarrierDialProcess 载波拨号流程
系统 SHALL 由 `CarrierDialProcess` 执行拨号防并发、ECC 挤占、MMI 短路与蜂窝下发，失败时回滚；因 DSDA 不支持（`CallManagerUtils::GetDsdsMode()` 在 liteOS 恒返回 0，design D9），基线 DSDA 非零分支移除。ECC 判定链完整保留，需人工复核（ECC）。

#### Scenario: 拨号防并发
- **WHEN** `CallRequestEventHandlerHelper::IsDialingCallProcessing()` 为 true
- **THEN** 返回 `CALL_ERR_CALL_COUNTS_EXCEED_LIMIT`；否则置 `RestoreDialingFlag(true)` + `SetDialingCallProcessing()`（行为照抄基线）

#### Scenario: DSDA 前置与 ECC 挤占
- **WHEN** `HandleDialingInfo` 中号码为 ECC 或 `IsNewCallAllowedCreate` 拒绝
- **THEN** ECC 走 `EccDialPolicy`（完整保留，需人工复核（ECC））；拒绝时返回 `CALL_ERR_CALL_COUNTS_EXCEED_LIMIT` 并复位拨号标志；因 DSDA 不支持（GetDsdsMode 恒 0，design D9），基线 `IsDsdsMode5()` 下 `IsDialCallForDsda` 先保持异卡活动通话并置 `needWaitHold_ = true` 的分支随非零 DSDS 流程删除（双卡扩展以参数面保留 `slotId` 为准，AGENTS）

#### Scenario: MMI 码短路
- **WHEN** 非 ECC 号码经 `CellularCallConnection::IsMmiCode` 判定为 MMI 码（查询经 `CellularCallClient::GetInstance()` 桩，design D4）
- **THEN** 不上报 DIALING 状态、不占拨号标志（复位并移除延迟任务），调 `CallDialog::DialogProcessMMICodeExtension` 弹出 MMI 处理框（经 callUi 桩，调用点标 `// todo!!! [callUi] ref to call_dialog.cpp DialogProcessMMICodeExtension`）（照抄）

#### Scenario: 正常下发与失败回滚
- **WHEN** `HandleStartDial` 组包（`PackCellularCallInfo`）后非 MMI 场景
- **THEN** 调 `CellularCallConnection::Dial`（适配器内经 `CellularCallClient::GetInstance().Dial` 桩下发）；失败且非 MMI 时 `HandleDialFail`：等待 `isFirstDialCallAdded_`（超时 1 秒 `WAIT_TIME_ONE_SECOND`）后对 CREATE/CONNECTING/DIALING 状态通话执行 `DealFailDial` 补报断开，最终返回拨号错误码；基线 `needWaitHold_` 为 true 时暂存 `CellularCallInfo` 到 `dialCallInfo_` 的等待保持段属非零 DSDS 流程、不迁移（置位点 `IsDialCallForDsda` 已删，`needWaitHold_` 字段与复位写点、`dialCallInfo_` 暂态字段与 `GetDialCallInfo` 读取接口作为骨架照抄，liteOS 上恒 false、暂存不可达）

测试落点：`call_manager_zero_gtest/src/zero_branch2_test.cpp` 新增 `Telephony_CarrierDialProcess_01x` 系用例（防并发、ECC 挤占经桩、MMI 短路、失败回滚补报；ECC 用例须成紧急呼叫拨号 gtest 并标注需人工复核（ECC））。

### Requirement: EccDialPolicy 紧急拨号挤占
系统 SHALL 由 `EccDialPolicy` 在紧急拨号时清理既有通话：拨号中（CREATE/CONNECTING/DIALING）、活动与保持通话挂断，振铃通话拒接；ECC 判定链完整保留，需人工复核（ECC）（proposal「BREAKING」清单）。

#### Scenario: 已有紧急拨号在途
- **WHEN** 既有 CREATE/CONNECTING/DIALING 通话中存在 `GetEmergencyState()` 为真的对象
- **THEN** 清空挂断/拒接列表并直接返回 `CALL_ERR_CALL_COUNTS_EXCEED_LIMIT`（行为照抄基线）

#### Scenario: 清理既有通话
- **WHEN** 无在途紧急拨号
- **THEN** 对 CREATE/CONNECTING/DIALING、ACTIVE/HOLD 的对象逐个 `HangUpCall`，对 RINGING 的对象逐个 `RejectCall`，返回 `TELEPHONY_SUCCESS`；因卫星通话不支持（AGENTS），基线对 SATELLITE 对象的清理分支移除；`HangUpCall`/`RejectCall` 出口经 `CellularCallClient::GetInstance()` 桩（design D4）

测试落点：`call_manager_zero_gtest/src/zero_branch2_test.cpp` 新增 `Telephony_EccDialPolicy_01x` 系用例（在途紧急拦截、清理矩阵，须成紧急呼叫拨号 gtest，标注需人工复核（ECC））。

### Requirement: AnswerRequest 应答请求处理与 DSDA 判定链
系统 SHALL 由 `CallRequestProcess::AnswerRequest` 按 VoIP/单卡模式选择应答策略；因 DSDA 不支持（`CoreServiceClient::GetDsdsMode` 恒 0，AGENTS「不支持 DSDA」、design D9），基线 DSDS 模式 3/DSDA 模式 5 等非零 DSDS 模式流程不迁移（双卡扩展以参数面保留 `slotId` 为准，AGENTS），仅由非零分支进入的等待通话保持/挂断矩阵随之删除。

#### Scenario: VoIP 应答
- **WHEN** 目标通话为 `TYPE_VOIP`
- **THEN** 直接对象 `AnswerCall` 并 `NotifyIncomingCallAnswered`（行为照抄基线）

#### Scenario: DSDS 模式 3（`IsDsdsMode3`，GetDsdsMode==`DSDS_MODE_V3`）
- **WHEN** 评估应答策略
- **THEN** 因 DSDA/DSDS 非零模式不支持（GetDsdsMode 恒 0，design D9），基线"存在其他 slotId 的载波通话时 `DisconnectOtherSubIdCall` 置 `SetAutoAnswerState(true)` 并挂断异卡通话"分支移除，`DisconnectOtherSubIdCall` 随异卡概念（仅双卡存在）删除

#### Scenario: DSDA 模式 5（`IsDsdsMode5`）视频/语音互斥
- **WHEN** 评估应答策略
- **THEN** 因 DSDA 与视频通话均不支持（AGENTS），基线 `NeedAnswerVTAndEndActiveVO`/`NeedAnswerVOAndEndActiveVT` 互斥判定与 `DisconnectOtherCallForVideoCall` 挂断链移除

#### Scenario: DSDA 模式 5 常规应答与 CRS 挤占
- **WHEN** 评估应答策略
- **THEN** 因 DSDA 与视频彩振（crsType==CRS_TYPE）不支持，基线 `GetOtherRingingCall` 的 CRS 挤占分支移除；仅由 `IsDsdsMode5` 非零分支进入的等待通话保持/挂断矩阵（`HoldOrDisconnectedCall`→`HandleCallWaitingNumTwo`/`HandleCallWaitingNumOne`/`HandleCallWaitingNumZero` 及其调用点）按 AGENTS「GetDsdsMode 恒 0，非 0 流程不需要迁移」删除，单卡流程中不进入该矩阵

#### Scenario: 单卡直接应答
- **WHEN** 非 VoIP 通话且 GetDsdsMode 为 0（liteOS 唯一可达路径）
- **THEN** 对象 `AnswerCall(videoState)` 成功后 `NotifyIncomingCallAnswered`（行为照抄基线）

测试落点：`call_manager_zero_gtest/src/zero_branch5_test.cpp` 新增 `Telephony_AnswerRequest_01x` 系用例（VoIP/单卡应答、DSDS3/DSDA5 分支缺失断言、单卡流程不进入等待矩阵断言）。

### Requirement: Reject/HangUp/UnHold/Switch Request 处理与策略标志
系统 SHALL 由 `RejectRequest`/`HangUpRequest`/`UnHoldRequest`/`SwitchRequest` 执行对象层操作并设置挂断策略标志；因 DSDA/会议不支持，基线 DSDA 异卡与会议态分支移除，等待通话条件与策略标志保留。

#### Scenario: 拒接后保持通话不可恢复
- **WHEN** `RejectRequest` 成功且存在 `CALL_RUNNING_STATE_HOLD` 通话
- **THEN** 对保持通话置 `SetCanUnHoldState(false)`（该路保持通话本次不可恢复），随后 `NotifyIncomingCallRejected`（行为照抄基线）

#### Scenario: 挂断活动通话恢复保持
- **WHEN** `HangUpRequest` 目标为 ACTIVE 且存在同 callType 的 HOLDING 通话，且无等待通话
- **THEN** 置 `POLICY_FLAG_HANG_UP_ACTIVE`（挂活动路、恢复保持路）供 `CarrierHangUpCall` 选择 `TYPE_HANG_UP_ACTIVE`（照抄）；因 DSDA 与会议不支持，基线"先尝试 `HangUpForDsdaRequest`（DSDA 模式且异卡有通话时逐个踢出会议成员）"与"目标会议态为 `TEL_CONFERENCE_ACTIVE`"条件分支移除

#### Scenario: 挂断保持中的会议
- **WHEN** `HangUpRequest` 评估目标会议态
- **THEN** 因会议通话不支持（AGENTS），基线"目标会议态为 `TEL_CONFERENCE_HOLDING` 且无等待通话时置 `POLICY_FLAG_HANG_UP_HOLD_WAIT`"与"会议态 HOLDING/ACTIVE 且存在等待通话时经 `GetSubCallIdList` 逐个 `KickOutFromConferenceRequest`"分支随会议移除，liteOS 上对象会议态恒 `TEL_CONFERENCE_IDLE`，该场景描述的原分支不复存在

#### Scenario: 恢复与切换请求
- **WHEN** `UnHoldRequest` 执行且无异卡 ACTIVE 通话
- **THEN** 执行本路 `UnHoldCall`（照抄）；因 DSDA 不支持，基线 `IsDsdsMode5()` 下异卡 ACTIVE 通话的 `GetCanSwitchCallState()`/`SetCanSwitchCallState(false)`/异卡 HoldCall 交换分支移除（`SetCanSwitchCallState`/`GetCanSwitchCallState` 机制保留）；`SwitchRequest` 直接透传对象 `SwitchCall`（照抄）

测试落点：`call_manager_zero_gtest/src/zero_branch5_test.cpp` 新增 `Telephony_RequestPolicy_01x` 系用例（拒接后不可恢复、策略标志置位矩阵、DSDA/会议分支缺失断言）。

### Requirement: CallRequestEventHandlerHelper 拨号标志与挂起管理
系统 SHALL 由 `CallRequestEventHandlerHelper` 管理拨号进行标志与 MO 挂断暂存；基线 `PostTask` 已是 EventHandler 形态，替换为打桩 EventHandler（design D8：`call_request_event_handler_helper.cpp` 替为桩）；`SetDialingCallProcessing` 返回值反判按 HMOS 现状照抄保留、不修正（design D9 Open Question 2）。

#### Scenario: 拨号标志自动复位
- **WHEN** `SetDialingCallProcessing` 在标志已为 true 时被调用
- **THEN** 移除旧任务并以桩 EventHandler `PostTask` 投递 3000ms（`DELAY_TIME`）延迟任务把标志复位为 false；按 HMOS 现状，`PostTask` 返回 true（投递成功）时反被判为失败并返回 `TELEPHONY_ERROR`（原样保留的疑似反逻辑，design D9 登记待人工定夺是否修正，默认不修）；标志本为 false 时直接返回 `TELEPHONY_ERROR`

#### Scenario: 成功路径即时清标志
- **WHEN** 拨号成功返回（如 MMI 短路）或拨号完成
- **THEN** 调用方显式 `RestoreDialingFlag(false)` + `RemoveEventHandlerTask` 清除标志与延迟任务（行为照抄基线）

#### Scenario: MO 挂断暂存语义
- **WHEN** `SetPendingMo(true, callId)` 后 `HasPendingMo(callId)` 为 true；`SetPendingHangup(true, callId)` 后 `IsPendingHangup`/`HasPendingHangup(callId)`/`GetPendingHangupCallId` 生效
- **THEN** 暂存的挂断请求由 `CallStatusManager` 在拨号 CLCC 流程收尾时按 `pendingHangupCallId_` 消费并清除（`SetPendingMo(false, -1)`）（行为照抄基线）

测试落点：`call_manager_zero_gtest/src/zero_branch5_test.cpp` 新增 `Telephony_CallRequestEventHandlerHelper_01x` 系用例（标志复位反判行为断言、暂存语义）。

### Requirement: CallIncomingFilterManager 来电过滤
系统 SHALL 由 `CallIncomingFilterManager::DoIncomingFilter`（由 `CallStatusManager::IncomingFilterPolicy` 调用）在来电创建前执行过滤判定；因 EDM 企业禁拨不支持（AGENTS），基线 EDM 禁入分支移除，仅剩 ECC 豁免/放行语义。

#### Scenario: EDM 禁入来电
- **WHEN** 来电过滤评估禁入策略
- **THEN** 因 EDM 企业禁拨不支持（AGENTS），基线 `CallControlManager::IsIncomingEnable(phoneNum)`（展开为 `EdmCallPolicy::IsCallEnable`：`persist.edm.telephony_call_disable` 开启或黑/白名单策略命中）返回 `TELEPHONY_ERR_POLICY_DISABLED` 拦截来电的分支随 `edm_call_policy.cpp` 删除（design D7 utils 表）移除，来电不再做 EDM 禁入校验

#### Scenario: 紧急来电豁免
- **WHEN** `CellularCallConnection::IsEmergencyPhoneNumber(phoneNum, accountId, isEcc)` 判定为紧急号码（查询经 `CellularCallClient::GetInstance()` 桩，design D4）
- **THEN** 记录日志并返回 `TELEPHONY_SUCCESS` 放行；普通来电同样返回 `TELEPHONY_SUCCESS` 放行（v6.0 无开机向导未完成、免打扰/静默等独立分支，照抄；ECC 豁免语义需人工复核（ECC））

测试落点：`call_manager_zero_gtest/src/zero_branch2_test.cpp` 新增 `Telephony_CallIncomingFilter_01x` 系用例（紧急号码经桩放行、普通来电放行、EDM 分支缺失断言）。

### Requirement: NOT_SUPPORT_MULTICALL 应答前先挂第一路
系统 SHALL 保留 `NOT_SUPPORT_MULTICALL` 宏的 declare_args 与 #ifdef 骨架（design D7 支持宏表，默认值仍 false）；因 BLUETOOTH 通话与 eSIM 均不支持（AGENTS），一号双终端判定族（`IsTwoCallBtCallAndESIM`/`IsTwoCallBtCall`/`IsTwoCallESIMCall`）及其调用点 `HangUpFirstCall` 判定链删除（见 call-object-management delta REMOVED「NOT_SUPPORT_MULTICALL 一号双终端对象判定」），`AnswerCall` 入口不再执行先挂第一路前置，直接进入常规应答链；骨架内其余逻辑照抄。

#### Scenario: 双呼形态判定分发
- **WHEN** 定义 `NOT_SUPPORT_MULTICALL` 时 `AnswerCall` 入口评估先挂第一路
- **THEN** 因判定族（`IsTwoCallBtCallAndESIM`/`IsTwoCallBtCall`/`IsTwoCallESIMCall`）及其调用点 `HangUpFirstCall` 判定链已删除，且 `TYPE_BLUETOOTH` 对象与 eSIM 在 liteOS 均不存在，不执行 `HangUpFirstCallBtAndESIM`/`HangUpFirstCallBtCall`/`HangUpFirstCallESIMCall` 任何分发，应答直接走常规链（振铃通话定位 → 策略校验 → 异步下发）

#### Scenario: 先挂后接执行
- **WHEN** 定义 `NOT_SUPPORT_MULTICALL` 且需先释放第一路再接听新来电
- **THEN** `HangUpFirstCallBySecondCallID(secondCallId, secondAutoAnswer)` 的先挂后接语义（第二路 INCOMING/WAITING 置 `SetAutoAnswerState(secondAutoAnswer)`；第一路 ACTIVE/DIALING/ALERTING 的 `HangUpCall`、INCOMING/WAITING 的 `RejectCall`，同号码跳过拒接）作为骨架逻辑照抄保留（不引用已删判定族）；一号双终端形态在 liteOS 不可达，该路径当前不触发

测试落点：`call_manager_zero_gtest/src/zero_branch5_test.cpp` 新增 `Telephony_NotSupportMulticall_01x` 系用例（定义宏后 `HangUpFirstCall` 恒 false、应答走常规链断言）。

### Requirement: VoIP 状态注入与畅连冲突
系统 SHALL 由 SetVoIPCallState/SetVoIPCallInfo 接收畅连（meetime）侧注入的 VoIP 通话状态，维护 `VoIPCallState_` 与 `voipCallObjectList_`；VoIP 真实对端暂不支持但注入与冲突处理逻辑保留（AGENTS「暂不支持 VOIP」条目、design D1/D8）；因 BLUETOOTH 通话不支持，基线蓝牙同步分支移除。

#### Scenario: 总状态注入
- **WHEN** `SetVoIPCallState(state)` 收到 `CALL_STATE_ANSWERED`/`CALL_STATE_OFFHOOK`/`CALL_STATE_IDLE`
- **THEN** 更新 `VoIPCallState_` 并 `CallStateReportProxy::UpdateCallStateForVoIPOrRestart`（core_service 上报出口经 `stub/state_registry_client` 桩，design D4）；ANSWERED 时逐个挂断对象表全部通话、OFFHOOK 时 `HangUpVoipCall`（VoIP 活动的跳过、INCOMING 的拒接、其余挂断）、IDLE 时若 `AnsweredCallQueue_` 有排队应答则补发 `AnswerCall`（照抄）；IDLE/UNKNOWN 时注销 `ApplicationStateObserver`，否则经 `AppStateObserver` 向 `AppMgr` 注册应用状态观察者（照抄保留）

#### Scenario: 单通话信息注入
- **WHEN** `SetVoIPCallInfo(callId, state, phoneNumber)` 且 `IsSupportSetVoipInfo`（系统参数 `const.telephony.read_set_voip_call_info` 非 "false"，经 `stub/parameter_stub` 桩，design D5）通过、callId 非 `ILLEGAL_CALLID`（-1）
- **THEN** 按 state 分发 `HandleVoipConnected`（置 ACTIVE 并上报 INCOMING→ACTIVE）、`HandleVoipIncoming`（已有通话时置 WAITING 否则 INCOMING，入 `voipCallObjectList_` 并 `SetVirtualCall(false)`）、`HandleVoipDisconnected`（上报 ACTIVE→DISCONNECTED、出表、`SetVirtualCall(true)`）、`HandleVoipAlerting`（置 ALERTING 入表）（照抄）；最后记录 `VoipCallInfo_`——因 BLUETOOTH 通话不支持，基线经 `BluetoothCallManager::SendBtCallState` 的 HFP 同步分支移除

#### Scenario: 非法 callId 与开关关闭
- **WHEN** callId 为 `ILLEGAL_CALLID` 或系统参数为 "false"
- **THEN** 前者 `ClearVoipList` 清空 VoIP 信息表并返回 `TELEPHONY_ERROR`；后者直接返回 `TELEPHONY_ERROR`（行为照抄基线）

测试落点：`call_manager_zero_gtest/src/zero_branch5_test.cpp` 新增 `Telephony_VoipStateInject_01x` 系用例（三态注入矩阵、蓝牙同步分支缺失断言、非法 callId），对端事件以 `VoipCallClient`/`parameter_stub` 桩注入驱动。

### Requirement: 通话界面服务连接与延迟断开
系统 SHALL 由 `ConnectCallUiService(bool)` + `ShouldDisconnectService` + 延迟任务管理通话 UI（`CallConnectAbility`）的连接/延迟断开（`DISCONNECT_DELAY_TIME` 1000000 微秒）；ffrt 延迟/取消替换为打桩 EventHandler（design D8），ConnectAbility/DisconnectAbility 语义经 `stub/` 打桩（design D6「拉起通话界面」行）。

#### Scenario: 连接时取消挂断定时
- **WHEN** `ConnectCallUiService(true)` 且已有挂断延迟任务（`alarmSeted`）
- **THEN** 经桩 EventHandler 取消任务（`ffrt::skip` 替换）后重新 `ConnectAbility`（经 callUi 桩，调用点标 `// todo!!! [callUi] ref to call_connect_ability.cpp ConnectAbility`）；无任务时直接连接并置 `shouldDisconnect = false`（照抄）

#### Scenario: 断开时挂起延迟任务
- **WHEN** `ConnectCallUiService(false)`
- **THEN** 置 `shouldDisconnect = true` 并以桩 EventHandler 投递 `DISCONNECT_DELAY_TIME` 延迟任务（`ffrt::submit_h` 替换，design D8）：到期时对象表已无通话才真正 `DisconnectAbility`（经 callUi 桩），否则保持连接（照抄）

测试落点：`call_manager_zero_gtest/src/zero_branch5_test.cpp` 新增 `Telephony_CallUiService_01x` 系用例（取消定时、延迟断开复查语义，经桩 EventHandler 驱动）。

### Requirement: 通话记录与通知补发
系统 SHALL 由 AddCallLogAndNotification/AddBlockLogAndNotification/RemoveMissedIncomingCallNotification 补发未接/拦截记录与通知；记录入库与通知发布的外部出口分别经 [database]/[notification] todo 桩化（design D6 数据库/通知行），判定逻辑保留。

#### Scenario: 未接来电补记
- **WHEN** 调用 `AddCallLogAndNotification(call)`
- **THEN** 置 `SetAnswerType(CALL_ANSWER_MISSED)`，经 `CallRecordsManager::CallStateUpdated(INCOMING→DISCONNECTED)` 记录（入库调用点标 `// todo!!! [database] ref to call_records_handler.cpp`，design D6）并 `MissedCallNotification::PublishMissedCallEvent` 通知（调用点标 `// todo!!! [notification] ref to incoming_call_notification.cpp PublishMissedCallEvent`）；拦截来电走 `AddBlockLogAndNotification`（`CALL_ANSWER_BLOCKED` + `PublishBlockedCallEvent`，出口同经桩）（照抄）

#### Scenario: 清除未接通知
- **WHEN** 调用 `RemoveMissedIncomingCallNotification`
- **THEN** 透传 `CallRecordsManager::RemoveMissedIncomingCallNotification`（通知清除出口经 [notification] todo 桩）（行为照抄基线）

测试落点：`call_manager_zero_gtest/src/zero_branch5_test.cpp` 新增 `Telephony_CallLogNotification_01x` 系用例（未接/拦截补记状态置位、todo 桩出口断言）。

### Requirement: 功耗锁与全量断开
系统 SHALL 由 AcquireIncomingLock/ReleaseIncomingLock（经 `IncomingCallWakeup`）管理来电唤醒锁，由 AcquireDisconnectedLock/ReleaseDisconnectedLock（`ABILITY_POWER_SUPPORT` 宏按 design D7 支持宏表保留）管理断开期运行锁（超时 `DISCONNECTED_LOCK_TIMEOUT`=2000ms），由 `DisconnectAllCalls` 全量清理通话；功耗锁调用链保留、RunningLock 调用点经 [powerLock] todo 桩化（design D6 功耗锁行）。

#### Scenario: 全量断开
- **WHEN** 调用 `DisconnectAllCalls`
- **THEN** 遍历对象表：`CALL_RUNNING_STATE_RINGING` 的走 `RejectCall`，其余走 `HangUpCall`；因 BLUETOOTH 通话不支持，基线 `TYPE_BLUETOOTH` 跳过分支随蓝牙对象消失移除

#### Scenario: 功耗锁分支
- **WHEN** 定义 `ABILITY_POWER_SUPPORT`（design D7：gni 部件块保留）时调用 `AcquireDisconnectedLock`/`ReleaseDisconnectedLock`
- **THEN** 功耗锁获取/释放调用链保留，`PowerMgr::RunningLock`（`RUNNINGLOCK_BACKGROUND_PHONE`）真实调用点标 `// todo!!! [powerLock] ref to call_control_manager.cpp AcquireDisconnectedLock/ReleaseDisconnectedLock`（design D6），桩默认返回"服务不存在"类负值（design Risks），超时 2000ms 语义保留；未定义该宏时两函数为空实现（照抄）

测试落点：`call_manager_zero_gtest/src/zero_branch5_test.cpp` 新增 `Telephony_DisconnectAllCalls_01x` 系用例（全量断开矩阵、蓝牙跳过分支缺失断言、功耗锁 todo 桩出口断言）。

### Requirement: 系统事件订阅
系统 SHALL 保留公共事件订阅函数族并维护 `subscriberPtrList_` 退订清单；因无 samgr/SA（design D2），基线 SA 上下线触发链移除，订阅/退订的 `EventFwk::CommonEventManager` 调用点经 [broadcast] todo 桩化（design D6 广播行：暂不调用、逻辑保留）。

#### Scenario: SA 上线注册订阅
- **WHEN** `CallControlManager::Init` 执行订阅注册
- **THEN** 因 liteOS 无 samgr/SA（design D2），基线 `SubscriberSaStateChange`/`SystemAbilityListener::OnAddSystemAbility`（`COMMON_EVENT_SERVICE_ID` 上下线触发）链移除，订阅函数族由 Init 直接调用；订阅清单收窄：通用订阅保留 SIM 状态变化/屏幕解锁/用户切换/关机，移除蓝牙远端设备名更新（BLUETOOTH 不支持）、联系人页面状态变化保留、卫星高温（`usual.event.thermal.satcomm.HIGH_TEMP_LEVEL`）订阅随卫星移除、超级隐私模式（`usual.event.SUPER_PRIVACY_MODE`）订阅随超级隐私移除、HFP 广播（`usual.event.bluetooth.CONNECT_HFP_HF`）随 `HFP_ASYNC_ENABLE` 宏删除移除（design D7）、静音键（`multimodal.event.MUTE_KEY_PRESS`）订阅保留；HSDR 订阅（`usual.event.HSDR_EVENT`，发布者 `com.hsdr`）与分发逻辑保留——其数据（`com.numberidentity.devicenumber`）亦供给号码识别链（number-identity 能力保留+桩化），仅防诈侧消费分支随防诈删除（antifraud 已删，design D7）；全部 `CommonEventManager::SubscribeCommonEvent` 调用点标 `// todo!!! [broadcast] ref to call_broadcast_subscriber.cpp`（design D6）

#### Scenario: SA 下线退订
- **WHEN** `CallControlManager` 执行 `UnInit`
- **THEN** 遍历 `subscriberPtrList_` 逐个退订（调用点经 [broadcast] todo 桩）并清空列表；因无 SA 事件，基线 `OnRemoveSystemAbility` 触发的退订链移除，`UnInit` 退订保留（照抄语义）

#### Scenario: 耳机按键处理恒不编译
- **WHEN** 评估 `onButtonDealing` 耳机按键处理
- **THEN** 因 `ABILITY_MEDIA_SUPPORT` 属不支持宏（AGENTS「特性宏支持范围」），基线守卫块本就不编译；liteOS 按 design D7 宏处置表"`call_control_manager.cpp`（onButtonDealing）守卫块随块删除"，该函数不迁移，不存在耳机按键处理路径

测试落点：`call_manager_zero_gtest/src/zero_branch5_test.cpp` 新增 `Telephony_BroadcastSubscribe_01x` 系用例（订阅清单收窄断言、退订链、HFP/耳机分支缺失断言、HSDR 订阅保留与防诈消费分支缺失断言）。

### Requirement: 佩戴状态与来电闪光提醒
系统 SHALL 由 `WearStatusObserver`/`RegisterObserver`/`SetWearState`/`IsNotWearOnWrist` 维护手表佩戴状态（判定链保留，design D9：AGENTS 未列入裁剪；settings 查询出口经 [database] todo 桩化）；因来电闪光不支持（AGENTS），基线闪光提醒链移除。

#### Scenario: 佩戴状态订阅
- **WHEN** `RegisterObserver` 以 `SettingsDataShareHelper`（uri key=wear_status）注册 `WearStatusObserver`
- **THEN** DataShare 查询/订阅暂不调用，调用点标 `// todo!!! [database] ref to settings_datashare_helper.cpp`（design D6 数据库行）；回调 `OnChange` 查询 wear_status 并 `SetWearState` 的判定链照抄（"1"→`WEAR_STATUS_OFF`、"2"→`WEAR_STATUS_ON`、其余 `WEAR_STATUS_INVALID`）；`IsNotWearOnWrist` 仅在 `WEAR_STATUS_OFF` 时返回 true（照抄）

#### Scenario: 来电闪光提醒
- **WHEN** 来电场景评估闪光提醒
- **THEN** 因来电闪光不支持（AGENTS 功能范围），`StartFlashRemind`/`StopFlashRemind`/`ClearFlashReminder` 与 `IncomingFlashReminder`（`EventRunner` 名 `handler_incoming_flash_reminder`）随 `utils/src/incoming_flash_reminder.cpp` 删除（design D7 utils 表）移除，liteOS 不提供来电闪光提醒路径（应答/拒接路径的 `StopFlashRemind` 调用同步移除）

#### Scenario: 视频铃声播放失败回退
- **WHEN** `HandleVideoRingPlayFail` 且存在振铃载波通话、非免打扰静默
- **THEN** 清空该通话联系人 `ringtonePath` 后 `AudioControlManager::PlayRingtone` 回退系统铃声（判定逻辑照抄保留；铃声播放出口经 [audio] todo 桩，design D6）

测试落点：`call_manager_zero_gtest/src/zero_branch5_test.cpp` 新增 `Telephony_WearStatus_01x` 系用例（wear_status 三态判定经 database 桩注入、闪光分支缺失断言、铃声回退链）。