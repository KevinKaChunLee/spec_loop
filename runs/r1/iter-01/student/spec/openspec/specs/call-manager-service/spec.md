# Call Manager Service Specification

## Purpose
描述 HMOS `telephony_call_manager` 中作为 SA 门面的 `CallManagerService`（`services/call_manager_service/src/call_manager_service.cpp`、`call_manager_service_stub.cpp`、`telephony_cust_wrapper.cpp` 及 `include/` 三头文件）：本身不含通话业务逻辑，职责是 SystemAbility 生命周期管理、接口权限校验、IPC 消息分发、以及将 `frameworks/native/include/i_call_manager_service.h` 声明的全部纯虚接口（RegisterCallBack、DialCall、AnswerCall、MakeCall、SET 类、会议类、RTT、蓝牙/代理类、特殊码、VoIP/OTT 类、SendCallUiEvent、SetCallPolicyInfo、GetProxyObjectPtr 等）逐一转发给 `CallControlManager`/`VideoControlManager`/`AudioDeviceManager`/`VoipCallConnection`/`CallAbilityReportProxy` 等内部管理者或外部模块连接。本规格为移植前现状基线，不涉及裁剪决策。

本能力涉及的特性宏（均有真实 #ifdef 场点）：
- `OHOS_BUILD_ENABLE_TELEPHONY_CUST`（`call_manager_service.cpp` include/`Init()`/`DialCall()` 三处；定义于 `callmanager.gni`，控制 `TelephonyCustWrapper` dlopen 定制库）；
- `SUPPORT_MUTE_BY_DATABASE`（`call_manager_service.cpp` include/`MuteRinger()`；定义于 `callmanager.gni`，控制 `InteroperableSettingsHandler::SendMuteRinger()` 广播静音标记）；
- `HICOLLIE_ENABLE`（`call_manager_service_stub.cpp` `SetTimer()`/`CancelTimer()`；定义于 `callmanager.gni`，控制 XCollie 看门狗计时器）；
- `CALL_MANAGER_AUTO_START_OPTIMIZE`（定义于 `frameworks/native/BUILD.gn`，仅客户端 `frameworks/native/src/call_manager_proxy.cpp`：SA 未启动时订阅 `COMMON_EVENT_RADIO_STATE_CHANGE` 广播延迟连接，与 SA 按需启动生命周期相关，须与门面一起评估）。

## Requirements

### Requirement: SystemAbility 注册与按需启动生命周期
系统 SHALL 以 `DelayedSingleton<CallManagerService>` 形式在静态初始化时由 `SystemAbility::MakeAndRegisterAbility`（`g_registerResult`，call_manager_service.cpp）注册进 SA 框架；`CallManagerService` 构造时以 `SystemAbility(TELEPHONY_CALL_MANAGER_SYS_ABILITY_ID, true)` 声明按需启动标志。`OnStart()` SHALL 在 `lock_` 保护下幂等（`state_` 已为 `STATE_RUNNING` 直接返回），先执行 `Init()`，成功后 `SystemAbility::Publish`，将 `state_` 置 `STATE_RUNNING`，并记录启动耗时 `spendTime_`（供 `GetStartServiceSpent()`）；`OnStart()` 末尾调用 `LocationSubscriber::Subscriber()`（地震预警位置订阅，定义于 `call_earthquake_alarm_subscriber.cpp`）。`OnStop()` SHALL 将 `state_` 置 `STATE_STOPPED` 并调用 `UnInit()`。`UnInit()` SHALL 依次执行 `CellularCallConnection::UnInit()`、`CallControlManager::UnInit()`、置空 `callControlManagerPtr_` 并在 `bluetoothCallCallbackLock_` 下置空 `bluetoothCallCallbackPtr_`。`Dump()` 与 `GetBindTime()`/`GetServiceRunningState()` 为门面自描述接口。

#### Scenario: 重复 OnStart 幂等
- **WHEN** SA 框架在 `state_ == STATE_RUNNING` 时再次回调 `OnStart()`
- **THEN** 直接返回，不再次 `Init()`/`Publish`

#### Scenario: Init 失败不发布
- **WHEN** `CallManagerManager::Init()` 依赖的 `CallControlManager::Init()` 返回 false
- **THEN** `OnStart()` 记录 "init failed" 日志后返回，SA 不 `Publish`，`state_` 保持 `STATE_STOPPED`

#### Scenario: OnStop 后状态查询
- **WHEN** `OnStop()` 完成
- **THEN** `GetServiceRunningState()` 返回 `STATE_STOPPED`（0），`CellularCallConnection` 已 `UnInit()`

### Requirement: Init 装配次序与依赖 SA 事件监听
系统 SHALL 在 `CallManagerService::Init()` 内按固定次序装配内部管理者：宏 `OHOS_BUILD_ENABLE_TELEPHONY_CUST` 打开时先 `TELEPHONY_CUST_WRAPPER.InitTelephonyCustWrapper()`；随后 `CallControlManager::Init()`（失败即整体失败）、缓存 `callControlManagerPtr_`、`ReportCallInfoHandler::Init()`、`CellularCallConnection::Init(TELEPHONY_CELLULAR_CALL_SYS_ABILITY_ID)`、`CallRecordsManager::Init()`、`BluetoothConnection::Init()`、`DistributedCallManager::Init()`、`DistributedCommunicationManager::Init()`；最后 `AddSystemAbilityListener(AUDIO_POLICY_SERVICE_ID)` 与 `AddSystemAbilityListener(DISTRIBUTED_HARDWARE_DEVICEMANAGER_SA_ID)`。`OnAddSystemAbility()` SHALL 按 SA id 分发：`AUDIO_POLICY_SERVICE_ID` 时注册 `AudioProxy` 的 `SetAudioMicStateChangeCallback`/`SetAudioDeviceChangeCallback`/`SetAudioPreferDeviceChangeCallback`；`DISTRIBUTED_HARDWARE_DEVICEMANAGER_SA_ID` 时 `InteroperableDeviceObserver::Init()`；其余打 unhandle 日志。

#### Scenario: 音频策略 SA 上线
- **WHEN** 系统回调 `OnAddSystemAbility(AUDIO_POLICY_SERVICE_ID, deviceId)`
- **THEN** `AudioProxy` 三个回调（麦克风状态、音频设备变化、偏好设备变化）被注册

#### Scenario: 依赖服务装配失败的传播
- **WHEN** `DelayedSingleton<CallControlManager>::GetInstance()->Init()` 失败
- **THEN** `Init()` 返回 false，`OnStart()` 不发布 SA

### Requirement: 客户端延迟拉起优化（CALL_MANAGER_AUTO_START_OPTIMIZE）
当宏 `CALL_MANAGER_AUTO_START_OPTIMIZE` 打开（`frameworks/native/BUILD.gn`）时，系统 SHALL 允许客户端 `CallManagerProxy::Init()`（`frameworks/native/src/call_manager_proxy.cpp`）以 `IsServiceStart()`（`CheckSystemAbility`）探测 SA：未启动则不直接连服务，而是订阅 `EventFwk::CommonEventSupport::COMMON_EVENT_RADIO_STATE_CHANGE`，在 `CallManagerProxySubcribed::OnReceiveEvent` 中收到广播后 `ConnectService()`、`RegisterCallBack(GetCallBack())`、`SetInitState(true)` 并退订。`RegisterCallBack()` 遇 `callManagerServicePtr_` 为空时把回调暂存到 `callBack_`。宏关闭时该分支不编译。

#### Scenario: SA 未启动时客户端不阻塞
- **WHEN** 宏打开且 `CheckSystemAbility(TELEPHONY_CALL_MANAGER_SYS_ABILITY_ID)` 返回空
- **THEN** 客户端订阅 radio 状态广播后立即返回，`initStatus_` 保持 false

#### Scenario: 广播到达后补注册
- **WHEN** `COMMON_EVENT_RADIO_STATE_CHANGE` 广播到达且连接服务成功
- **THEN** 暂存的回调被注册，`SetInitState(true)`，并退订广播

### Requirement: 接口权限校验（集中）
系统 SHALL 在 `CallManagerService` 各转发接口入口处通过 `TelephonyPermission::CheckCallerIsSystemApp()`（非系统应用返回 `TELEPHONY_ERR_ILLEGAL_USE_OF_SYSTEM_API`）与 `TelephonyPermission::CheckPermission(...)`（失败返回 `TELEPHONY_ERR_PERMISSION_ERR`）执行校验，权限常量为 `ohos.permission.SET_TELEPHONY_STATE`、`GET_TELEPHONY_STATE`、`PLACE_CALL`、`ANSWER_CALL`、`READ_CALL_LOG`、`WRITE_CALL_LOG`。分组规则：拨号类（DialCall/StartRtt/StopRtt/KickOutFromConference/JoinConference/CancelCallUpgrade/InputDialerSpecialCode）用 PLACE_CALL；应答保持类（AnswerCall/HoldCall/UnHoldCall/SwitchCall）用 ANSWER_CALL；RejectCall/HangUpCall/RegisterCallBack/SetVoIPCallState/SetVoIPCallInfo 接受两种权限之一；RegisterVoipCallManagerCallback/UnRegisterVoipCallManagerCallback/ReportOttCallDetailsInfo/ReportOttCallEventInfo 用 GET_TELEPHONY_STATE；查询读类用 GET_TELEPHONY_STATE、设置写类用 SET_TELEPHONY_STATE；RemoveMissedIncomingCallNotification 需 SET+READ+WRITE_CALL_LOG 三权齐备；SetCallPreferenceMode/SendCallUiEvent/ReportAudioDeviceInfo/SetCallPolicyInfo 不做系统应用校验仅校验 SET_TELEPHONY_STATE；GetCallState/HasCall/IsEmergencyPhoneNumber/FormatPhoneNumber/FormatPhoneNumberToE164 完全不校验。`SetPreviewWindow()` 额外调用 `PrivacyKit::StartUsingPermission`/`StopUsingPermission`/`AddPermissionUsedRecord`（"ohos.permission.CAMERA"）。

#### Scenario: 非系统应用调用系统接口
- **WHEN** 非系统应用调用 `AnswerCall()`
- **THEN** 返回 `TELEPHONY_ERR_ILLEGAL_USE_OF_SYSTEM_API`

#### Scenario: 拨号缺权限
- **WHEN** 调用 `DialCall()` 且未授予 `ohos.permission.PLACE_CALL`
- **THEN** 返回 `TELEPHONY_ERR_PERMISSION_ERR` 并 `CallManagerHisysevent::WriteDialCallFaultEvent` 记录权限错误

#### Scenario: OSS API 与系统 API 差异
- **WHEN** 调用 `HasCall()` / `FormatPhoneNumber()`
- **THEN** 无系统应用与权限校验，直接转发 `CallControlManager`

### Requirement: IPC 分发表（CallManagerServiceStub）
系统 SHALL 由 `CallManagerServiceStub`（`services/call_manager_service/src/call_manager_service_stub.cpp`）在构造函数中通过 `InitCallBasicRequest`/`InitCallUtilsRequest`/`InitCallConferenceRequest`/`InitCallDtmfRequest`/`InitCallSupplementRequest`/`initCallConferenceExRequest`/`InitCallMultimediaRequest`/`InitImsServiceRequest`/`InitOttServiceRequest`/`InitVoipOperationRequest`/`InitBluetoothOperationRequest` 及 `INTERFACE_GET_PROXY_OBJECT_PTR` 直接项，将 `CallManagerInterfaceCode` 全部枚举码映射到 `memberFuncMap_`（`std::function<int32_t(MessageParcel&, MessageParcel&)>`）。`OnRemoteRequest()` SHALL 先比对接口令牌描述符（不一致返回 `TELEPHONY_ERR_DESCRIPTOR_MISMATCH`），再查表执行 `SetTimer(code)` → 处理函数 → `CancelTimer`；未命中转发 `IPCObjectStub::OnRemoteRequest`。反序列化参数校验示例：`OnReportOttCallDetailsInfo` 要求向量计数在 `(0, MAX_CALLS_NUM=5]` 且逐元素 `ReadRawData` 成功。

#### Scenario: 描述符不匹配
- **WHEN** 客户端请求的接口令牌与 `CallManagerServiceStub::GetDescriptor()` 不一致
- **THEN** 返回 `TELEPHONY_ERR_DESCRIPTOR_MISMATCH`，不进入处理函数

#### Scenario: 未知消息码
- **WHEN** `code` 不在 `memberFuncMap_`
- **THEN** 回落到 `IPCObjectStub::OnRemoteRequest`

#### Scenario: XCollie 计时（HICOLLIE_ENABLE）
- **WHEN** 宏 `HICOLLIE_ENABLE` 打开且命中 `collieCodeStringMap_`（当前仅登记 INTERFACE_REGISTER_CALLBACK）
- **THEN** `SetTimer` 以 `XCOLLIE_TIMEOUT_SECONDS=30`、`HiviewDFX::XCOLLIE_FLAG_NOOP` 启动计时，处理完 `CancelTimer`；宏关闭时 `SetTimer` 恒返回 -1

### Requirement: TelephonyCustWrapper 动态库加载（OHOS_BUILD_ENABLE_TELEPHONY_CUST）
系统 SHALL 在宏 `OHOS_BUILD_ENABLE_TELEPHONY_CUST` 打开时由 `TELEPHONY_CUST_WRAPPER`（`DelayedRefSingleton<TelephonyCustWrapper>`）执行 `InitTelephonyCustWrapper()`：`dlopen("libtelephony_cust_api.z.so", RTLD_NOW)` 并 `dlsym` 解析 `IsHideViolenceOrEmcNumbersInCallLog`（签名 `bool(const CallAttributeInfo&)`，供 `call_records_manager.cpp` 判断是否在通话记录中隐藏暴力/紧急号码）与 `IsChangeDialNumberToTwEmc`（签名 `bool(std::u16string&, int32_t)`，供 `DialCall()` 修改特殊号码）；dlopen 或 dlsym 失败时打错误日志并保持函数指针为空，调用方（`call_manager_service.cpp`、`call_records_manager.cpp`）SHALL 判空后才调用。析构/卸载时 `dlclose` 句柄。

#### Scenario: 定制库不存在
- **WHEN** `libtelephony_cust_api.z.so` 缺失导致 `dlopen` 返回空
- **THEN** 打日志后返回，两个函数指针保持 nullptr，`DialCall()` 跳过号码改写分支

#### Scenario: 拨号命中定制改号
- **WHEN** `IsChangeDialNumberToTwEmc_(number, slotId)` 返回 true
- **THEN** `DialCall()` 打 "changed dial num to tw emc" 日志后继续正常拨号流程

### Requirement: 上层回调注册与解除
系统 SHALL 由 `CallManagerService::RegisterCallBack()`/`UnRegisterCallBack()`/`ObserverOnCallDetailsChange()` 承接应用的观察者接入：RegisterCallBack 校验 SET 或 GET_TELEPHONY_STATE 后把回调连同 `GetBundleInfo()`（uid 反查 bundleName，失败回退为 uid+pid 拼接，格式 bundleName:pid）交给 `CallAbilityReportProxy::RegisterCallBack`；UnRegisterCallBack 校验 SET_TELEPHONY_STATE 后按 bundleInfo 移除；`ObserverOnCallDetailsChange()` 校验后遍历 `CallObjectManager::GetAllCallInfoList()` 对每个 `CallAttributeInfo` 定向上报。三个入口均要求系统应用。

#### Scenario: 注册成功
- **WHEN** 系统应用持 SET 或 GET_TELEPHONY_STATE 调用 `RegisterCallBack(callback)`
- **THEN** `CallAbilityReportProxy` 登记回调并附加 DeathRecipient（见 call-report 能力），返回 `TELEPHONY_SUCCESS`

#### Scenario: 观察详情变更补报
- **WHEN** 调用 `ObserverOnCallDetailsChange()`
- **THEN** 当前全部通话属性按注册时的 bundleInfo 定向逐条上报

### Requirement: DialCall 拨号转发与语音信箱计数清零
系统 SHALL 由 `CallManagerService::DialCall()`（call_manager_service.cpp）执行拨号前置处理并转发 `CallControlManager::DialCall`：先 `CallManagerHisysevent::SetDialStartTime()` 与 `StartAsyncTrace(HITRACE_TAG_OHOS, "DialCall")`；以 `IPCSkeleton::GetCallingUid` 反查 bundleName 写入 extras 的 "bundleName" 键；extras 带 `btSlotIdUnknown` 时走 `BtCallWaitSlotId()`（`InteroperableCommunicationManager::GetBtCallSlotId(phoneNum)` 取槽位、`CoreServiceClient::HasSimCard` 验证后写入 extras 的 "accountId"）；校验 PLACE_CALL 失败即 `WriteDialCallFaultEvent`；宏 OHOS_BUILD_ENABLE_TELEPHONY_CUST 判空调用 `isChangeDialNumberToTwEmc_`；转发成功且号码等于 `CoreManagerInner::GetVoiceMailNumber(slotId)` 时调用 `SetVoiceMailCount(slotId, 0)` 清计数；转发失败 `GetErrorDescription` 后 `WriteDialCallFaultEvent`；`callControlManagerPtr_` 为空返回 `TELEPHONY_ERR_LOCAL_PTR_NULL`。

#### Scenario: 拨打语音信箱号码
- **WHEN** `DialCall` 成功且被叫号码与 `GetVoiceMailNumber(slotId)` 相同（示例号码以 unknown 占位）
- **THEN** `SetVoiceMailCount(slotId, CLEAR_VOICE_MAIL_COUNT=0)` 被调用

#### Scenario: 拨号失败故障记录
- **WHEN** `CallControlManager::DialCall` 返回非 0
- **THEN** 按 `GetErrorDescription(ret)` 描述写 CALL_DIAL_FAILED 故障事件并 FinishAsyncTrace

#### Scenario: 蓝牙回拨槽位未知
- **WHEN** extras 中 `btSlotIdUnknown` 为真且该号码对应槽位有卡
- **THEN** extras 的 accountId 被补写为 `GetBtCallSlotId` 结果

### Requirement: MakeCall 拉起拨号前编辑页
系统 SHALL 由 `CallManagerService::MakeCall()` 在系统应用校验后，经 `IPCSkeleton::ResetCallingIdentity` 切换身份、构造指向 `com.ohos.contacts` `MainAbility` 的 Want（参数 phoneNumber 与 `pageFlag=page_flag_edit_before_calling`），调用 `AAFwk::AbilityManagerClient::StartAbility`，随后 `SetCallingIdentity` 还原身份；StartAbility 失败返回 `TELEPHONY_ERR_UNINIT`。

#### Scenario: 拉起联系人编辑页成功
- **WHEN** 系统应用调用 `MakeCall(unknown)`
- **THEN** contacts MainAbility 以 edit_before_calling 页面标志被拉起，返回 `TELEPHONY_SUCCESS`

#### Scenario: 拉起失败
- **WHEN** `StartAbility` 返回错误码
- **THEN** `MakeCall` 返回 `TELEPHONY_ERR_UNINIT`

### Requirement: 通话控制转发（应答/挂断/保持/切换）
系统 SHALL 将控制类接口原样转发 `CallControlManager`：`AnswerCall`（校验 ANSWER_CALL、`SetAnswerStartTime()`、`AnswerCall(callId, videoState)`）、`RejectCall`（接受 ANSWER_CALL 或 SET_TELEPHONY_STATE 任一、`RejectCall(callId, rejectWithMessage, textMessage)`）、`HangUpCall`（同 RejectCall 权限组、`HangUpCall(callId)`）、`HoldCall`/`UnHoldCall`/`SwitchCall`（ANSWER_CALL）、`GetCallState()`（无校验）。`callControlManagerPtr_` 为空时统一返回 `TELEPHONY_ERR_LOCAL_PTR_NULL`。

#### Scenario: 应答开始计时
- **WHEN** `AnswerCall()` 通过权限校验
- **THEN** `SetAnswerStartTime()` 记录起始时间后转发 `CallControlManager::AnswerCall`

#### Scenario: 权限二选一通过（RejectCall）
- **WHEN** 调用者仅持 SET_TELEPHONY_STATE 调用 `RejectCall`
- **THEN** 校验通过并转发

### Requirement: 麦克风静音与音频设备转发
系统 SHALL 由 `CallManagerService` 转发音频面接口：`SetMuted`（SET_TELEPHONY_STATE）成功后联动 `DistributedCommunicationManager::SetMuted` 与 `InteroperableCommunicationManager::SetMuted`；`MuteRinger`（SET_TELEPHONY_STATE）成功后联动两者 `MuteRinger()`，宏 `SUPPORT_MUTE_BY_DATABASE` 打开时再调用 `InteroperableSettingsHandler::SendMuteRinger()`；`SetAudioDevice`（SET_TELEPHONY_STATE）转发失败返回 `CALL_ERR_SETTING_AUDIO_DEVICE_FAILED`；`ReportAudioDeviceInfo`（仅 SET_TELEPHONY_STATE 权限）以 `DEVICE_UNKNOWN` 音频设备调用 `AudioDeviceManager::ReportAudioDeviceChange`。

#### Scenario: 静音状态联动
- **WHEN** `SetMuted(true)` 返回 `TELEPHONY_SUCCESS`
- **THEN** 分布式与互通两个通信管理器同步收到静音状态

#### Scenario: 数据库静音标记（SUPPORT_MUTE_BY_DATABASE）
- **WHEN** 宏打开且 `MuteRinger()` 成功
- **THEN** `InteroperableSettingsHandler::SendMuteRinger()` 持久化静音标记

#### Scenario: 设置音频设备失败
- **WHEN** `CallControlManager::SetAudioDevice` 返回非 0
- **THEN** 门面返回 `CALL_ERR_SETTING_AUDIO_DEVICE_FAILED`

### Requirement: 补充业务与 USSD 设置转发
系统 SHALL 由 `CallManagerService` 将 SET 类接口转发 `CallControlManager`（后者落入 call-setting-management 能力）：`GetCallWaiting`/`CanSetCallTransferTime`（GET_TELEPHONY_STATE）、`SetCallWaiting`/`SetCallRestriction`/`SetCallRestrictionPassword`/`SetCallTransferInfo`/`CloseUnFinishedUssd`/`SendUssdResponse`（SET_TELEPHONY_STATE）、`GetCallRestriction`/`GetCallTransferInfo`（GET_TELEPHONY_STATE）；`SendUssdResponse` 转发 `CellularCallConnection::SendUssdResponse(slotId, content)` 且恒返回 `TELEPHONY_SUCCESS`。

#### Scenario: 查询呼叫等待
- **WHEN** 系统应用持 GET_TELEPHONY_STATE 调用 `GetCallWaiting(slotId)`
- **THEN** 转发 `CallControlManager::GetCallWaiting`

#### Scenario: 发送 USSD 应答
- **WHEN** 调用 `SendUssdResponse(slotId, content)`
- **THEN** 经 `CellularCallConnection` 下发 mod 层，门面返回 `TELEPHONY_SUCCESS`

### Requirement: IMS 配置 / VoLTE / VoNR 转发
系统 SHALL 由 `CallManagerService` 转发 IMS 类接口到 `CallControlManager`：`GetImsConfig`/`GetImsFeatureValue`（GET_TELEPHONY_STATE）、`SetImsConfig`/`SetImsFeatureValue`/`EnableImsSwitch`/`DisableImsSwitch`/`SetVoNRState`（SET_TELEPHONY_STATE）、`GetVoNRState`（GET_TELEPHONY_STATE）、`IsImsSwitchEnabled`（仅系统应用校验，无权限校验）。

#### Scenario: VoLTE 开关读取
- **WHEN** 系统应用调用 `IsImsSwitchEnabled(slotId, enabled)`
- **THEN** 免权限校验直接转发 `CallControlManager::IsImsSwitchEnabled`

### Requirement: 会议通话转发（集中）
系统 SHALL 由 `CallManagerService` 集中转发会议类接口（均需系统应用）：`CombineConference`（SET_TELEPHONY_STATE）、`SeparateConference`（SET_TELEPHONY_STATE）、`KickOutFromConference`（PLACE_CALL）、`JoinConference`（PLACE_CALL）、以及会议查询 `GetMainCallId`/`GetSubCallIdList`/`GetCallIdListForConference`（GET_TELEPHONY_STATE）；后三者 `callControlManagerPtr_` 为空时还需清空输出列表再返回 `TELEPHONY_ERR_LOCAL_PTR_NULL`。

#### Scenario: 合并会议
- **WHEN** 系统应用持 SET_TELEPHONY_STATE 调用 `CombineConference(mainCallId)`
- **THEN** 转发 `CallControlManager::CombineConference`

#### Scenario: 会议列表查询降级
- **WHEN** `CallControlManager` 指针为空时调用 `GetSubCallIdList`
- **THEN** `callIdList` 被清空并返回 `TELEPHONY_ERR_LOCAL_PTR_NULL`

### Requirement: 通话状态查询转发
系统 SHALL 由 `CallManagerService` 转发查询接口：`HasCall(isInCludeVoipCall)`（无校验；含 VoIP 时取 `HasCall()`，仅蜂窝时取 `HasCellularCallExist()`，指针为空返回 false）、`IsRinging`（SET_TELEPHONY_STATE）、`IsInEmergencyCall`（GET_TELEPHONY_STATE，转发 `HasEmergency`）、`IsEmergencyPhoneNumber`（无校验）、`FormatPhoneNumber`/`FormatPhoneNumberToE164`（无校验）。

#### Scenario: 仅统计蜂窝通话
- **WHEN** 以 `isInCludeVoipCall=false` 调用 `HasCall`
- **THEN** 返回 `HasCellularCallExist()` 结果

#### Scenario: 紧急来电查询
- **WHEN** 系统应用持 GET_TELEPHONY_STATE 调用 `IsInEmergencyCall`
- **THEN** 输出 `CallControlManager::HasEmergency` 的结果

### Requirement: DTMF 与后拨号继续转发
系统 SHALL 由 `CallManagerService` 转发 `StartDtmf(callId, str)`/`StopDtmf(callId)`/`PostDialProceed(callId, proceed)` 至 `CallControlManager`（均需系统应用 + SET_TELEPHONY_STATE）。

#### Scenario: 后拨号确认
- **WHEN** 系统应用持 SET_TELEPHONY_STATE 调用 `PostDialProceed(callId, true)`
- **THEN** 转发 `CallControlManager::PostDialProceed`

### Requirement: RTT 转发
系统 SHALL 由 `CallManagerService::StartRtt(callId, msg)`/`StopRtt(callId)` 在系统应用 + PLACE_CALL 校验后转发 `CallControlManager`。

#### Scenario: 启动 RTT
- **WHEN** 系统应用持 PLACE_CALL 调用 `StartRtt`
- **THEN** 转发 `CallControlManager::StartRtt`，失败路径不追加补偿动作

### Requirement: 视频通话控制转发（VideoControlManager）
系统 SHALL 由 `CallManagerService` 将视频面接口转发 `DelayedSingleton<VideoControlManager>`（均需系统应用 + SET_TELEPHONY_STATE）：`ControlCamera`（附带 CallingUid/CallingPid）、`SetPreviewWindow`/`SetDisplayWindow`/`SetPausePicture`/`SetDeviceDirection`、`SetCameraZoom` 走 `CallControlManager`、`UpdateImsCallMode`、`CancelCallUpgrade`（PLACE_CALL）、`RequestCameraCapabilities`（GET_TELEPHONY_STATE）。`SetPreviewWindow` SHALL 额外维护相机隐私授权：surface 为空时 `PrivacyKit::StopUsingPermission(token, "ohos.permission.CAMERA")`；surface 非空且该通话非 TYPE_RECEIVE_ONLY 时 `AddPermissionUsedRecord` + `StartUsingPermission`。

#### Scenario: 关闭预览触发相机权限回收
- **WHEN** 应用以空 surface 调用 `SetPreviewWindow`
- **THEN** `PrivacyKit::StopUsingPermission` 被调用后转发 `VideoControlManager::SetPreviewWindow`

#### Scenario: 视频控制降级
- **WHEN** `VideoControlManager` 实例为空
- **THEN** 返回 `TELEPHONY_ERR_LOCAL_PTR_NULL`

### Requirement: 蓝牙通话代理与回调注册（集中）
系统 SHALL 由 `CallManagerService` 集中蓝牙接入：`GetProxyObjectPtr(proxyType)` 在 `lock_` 下缓存 `proxyObjectPtrMap_`，`PROXY_BLUETOOTH_CALL` 惰性创建 `BluetoothCallService` 并缓存其 `AsObject()`，未知类型返回 nullptr；`RegisterBluetoothCallManagerCallbackPtr(macAddress)`（校验 `Permission::GET_TELEPHONY_STATE`）在 `bluetoothCallCallbackLock_` 下惰性创建 `CallStatusCallback`、经 `Bluetooth::HandsFreeUnit::GetProfile()->RegisterObserver` 注册 `BluetoothCallState` 观察者（profile 为空仅打日志）、`BluetoothCallConnection::SetMacAddress(macAddress)`，同一并发只会创建一个回调对象并重复返回。

#### Scenario: 蓝牙代理获取
- **WHEN** 以 `PROXY_BLUETOOTH_CALL` 调用 `GetProxyObjectPtr`
- **THEN** 首次创建 `BluetoothCallService` 并缓存，第二次直接命中缓存返回

#### Scenario: 蓝牙回调复用
- **WHEN** 多次调用 `RegisterBluetoothCallManagerCallbackPtr`
- **THEN** 均返回同一 `bluetoothCallCallbackPtr_`

### Requirement: SendCallUiEvent UI 事件分发
系统 SHALL 由 `CallManagerService::SendCallUiEvent(callId, eventName)`（仅 SET_TELEPHONY_STATE 权限）按事件名分发：`EVENT_IS_CELIA_CALL`→`dealCeliaCallEvent`；`EVENT_SPEAKER_OFF`→`AudioProxy::SetSpeakerDevActive(false)` 失败返回 `TELEPHONY_ERR_FAIL`；`DISPLAY_SPECIFIED_CALL_PAGE_BY_CALL_ID`→`HandleDisplaySpecifiedCallPage`；`EVENT_BLUETOOTH_SCO_STATE_OFF/ON`→`BluetoothCallConnection::DisConnectBtSco/ConnectBtSco`；`EVENT_SUPPORT_BLUETOOTH_CALL`/`EVENT_NOT_SUPPORT_BLUETOOTH_CALL`→按 `GetSupportBtCall()` 与事件匹配返回成功或 `TELEPHONY_ERR_FAIL`；`EVENT_CELIA_AUTO_ANSWER_CALL_ON/OFF`→`HandleCeliaAutoAnswerCall`；`EVENT_VOIP_CALL_SUCCESS/FAILED`→`HandleVoIPCallEvent`；`EVENT_INVALID_VIDEO_FD`→`CallControlManager::HandleVideoRingPlayFail`；未匹配事件名静默成功。

#### Scenario: 关闭免提扬声器
- **WHEN** eventName 为 `EVENT_SPEAKER_OFF` 且设置成功
- **THEN** 返回 `TELEPHONY_SUCCESS`

#### Scenario: 未知事件
- **WHEN** eventName 不匹配任何分支
- **THEN** 无副作用返回 `TELEPHONY_SUCCESS`

### Requirement: CeliaCall（新通话）事件（集中独立）
系统 SHALL 集中处理新通话相关分支：`dealCeliaCallEvent(callId)` 取 `CallObjectManager::GetOneCallObject`（为空返回 `TELEPHONY_ERR_LOCAL_PTR_NULL`），交 `callStatusManagerPtr_->HandleCeliaCall`，`SetCeliaCallType(IS_CELIA_CALL=1)`，若 `DistributedCallManager::IsDCallDeviceSwitchedOn()` 则 `SwitchOffDCallDeviceSync()` 并 `ReportDistributedDeviceInfoForSwitchOff`；`HandleCeliaAutoAnswerCall(callId, enable)` 置 `SetAiAutoAnswer(enable)`；`HandleDisplaySpecifiedCallPage(callId)` 在通话 extras 注入 `sosWithOutCallUiAbility="2"` 后经 `CallAbilityReportProxy::ReportCallStateInfo` 上报；`HandleVoIPCallEvent` 对 TYPE_VOIP 通话组装 callId/eventName/publishTime 的 PacMap 经 `VoipCallConnection::SendCallUiEventForWindow` 上报；`IsNewCallAllowed(enabled)` 仅系统应用校验后转发 `CallControlManager::IsNewCallAllowed`。

#### Scenario: Celia 事件设置通话类型
- **WHEN** `EVENT_IS_CELIA_CALL` 分支对有效 callId 执行
- **THEN** 通话对象 `celiaCallType` 置 1，且分布式设备开关被关闭并上报

#### Scenario: AI 自动接听开关
- **WHEN** 分别以 `EVENT_CELIA_AUTO_ANSWER_CALL_ON`/`OFF` 分发
- **THEN** 对应 `SetAiAutoAnswer(true/false)`

#### Scenario: 指定通话页面拉起
- **WHEN** `DISPLAY_SPECIFIED_CALL_PAGE_BY_CALL_ID` 分发且 callId 有效
- **THEN** extras 注入 sosWithOutCallUiAbility 后上报通话状态

### Requirement: VoIP 与 OTT 上报转发
系统 SHALL 由 `CallManagerService` 转发 VoIP/OTT 面：`RegisterVoipCallManagerCallback`（系统应用 + GET_TELEPHONY_STATE）在 `lock_` 下 `VoipCallConnection::Init(TELEPHONY_VOIP_CALL_MANAGER_SYS_ABILITY_ID=65968)` 创建 `CallStatusCallback` 注册回调；`UnRegisterVoipCallManagerCallback` 转发解除；`SetVoIPCallState`（SET 或 GET 任一权限）`GetVoIPCallState`（仅系统应用校验）`SetVoIPCallInfo`（SET 或 GET）`GetVoIPCallInfo`（仅系统应用校验）转发 `CallControlManager`；`ReportOttCallDetailsInfo`（GET_TELEPHONY_STATE）拒绝空向量（`TELEPHONY_ERR_ARGUMENT_INVALID`），把 `OttCallDetailsInfo` 拷贝为 `CallDetailInfo`（callType=TYPE_OTT、accountId/index/voiceDomain=ERR_ID）后交 `ReportCallInfoHandler::UpdateCallsReportInfo`；`ReportOttCallEventInfo` 直接交 `UpdateOttEventInfo`。

#### Scenario: VoIP 回调注册
- **WHEN** 系统应用持 GET_TELEPHONY_STATE 调用 `RegisterVoipCallManagerCallback`
- **THEN** VoipCallConnection 以 SA id 65968 初始化并注册 CallStatusCallback

#### Scenario: 空列表拒绝
- **WHEN** `ReportOttCallDetailsInfo` 收到空向量
- **THEN** 返回 `TELEPHONY_ERR_ARGUMENT_INVALID`

### Requirement: 拨号器特殊码广播
系统 SHALL 由 `CallManagerService::InputDialerSpecialCode(specialCode)`（系统应用 + PLACE_CALL）先在 `supportSpecialCode_` 白名单（"*#2846#"、"*#2846*"、"*#*#2846579#*#*"、"#1#"、"*#28465#"、"*#*#121314#*#*"、"*#*#19467328#*#*"、"*#*#2589#*#*"、"*#*#2845#*#*"、"*#*#2846#*#*"、"*#*#2847#*#*"、"*#*#28465#*#*"、"*#*#2627#*#*"、"*#*#258#*#*"、"*#28460"）校验，命中后以 `EventFwk::CommonEventSupport::COMMON_EVENT_SPECIAL_CODE` action、data=specialCode 经 `CommonEventManager::PublishCommonEvent` 发布公共事件；未命中返回 `TELEPHONY_ERR_ARGUMENT_INVALID`，发布失败返回 `TELEPHONY_ERR_PUBLISH_BROADCAST_FAIL`。

#### Scenario: 白名单特殊码
- **WHEN** 拨号应用以白名单内的 *# 特殊码调用本接口
- **THEN** COMMON_EVENT_SPECIAL_CODE 公共事件被发布，返回 `TELEPHONY_SUCCESS`

#### Scenario: 非白名单
- **WHEN** specialCode 不在 `supportSpecialCode_`
- **THEN** 返回 `TELEPHONY_ERR_ARGUMENT_INVALID` 且不发布

### Requirement: 未接来电通知清除
系统 SHALL 由 `CallManagerService::RemoveMissedIncomingCallNotification()` 在系统应用 + SET/READ/WRITE_CALL_LOG 三权限齐备后转发 `CallControlManager::RemoveMissedIncomingCallNotification`。

#### Scenario: 权限不齐
- **WHEN** 缺任一 READ_CALL_LOG/WRITE_CALL_LOG 权限调用
- **THEN** 返回 `TELEPHONY_ERR_PERMISSION_ERR`

### Requirement: EDM 呼叫管控策略
系统 SHALL 由 `CallManagerService::SetCallPolicyInfo(isDialingTrustlist, dialingList, isIncomingTrustlist, incomingList)`（仅 SET_TELEPHONY_STATE 权限，不做系统应用校验）在 `IPCSkeleton::GetCallingUid() == EDM_UID=3057` 时转发 `CallControlManager::SetEdmPolicy`，否则返回 `TELEPHONY_ERR_PERMISSION_ERR`。

#### Scenario: EDM 进程下发策略
- **WHEN** uid 为 3057 的调用方下发信任/拦截名单（号码示例 unknown）
- **THEN** `SetEdmPolicy` 收到四个参数并透传结果

#### Scenario: 非 EDM 进程
- **WHEN** 普通进程调用 `SetCallPolicyInfo`
- **THEN** 返回 `TELEPHONY_ERR_PERMISSION_ERR`