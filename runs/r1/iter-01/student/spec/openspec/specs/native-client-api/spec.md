# native-client-api Specification

## Purpose
描述 `telephony_call_manager/frameworks/native/` 下的原生客户端层在 OpenHarmony v6.0 快照中的现状：`CallManagerClient` 门面（`call_manager_client.cpp`）+ `CallManagerProxy` 服务连接管理（`call_manager_proxy.cpp`）+ `CallManagerServiceProxy` / `CallManagerProxy` 族 IPC 编解码（`call_manager_service_proxy.cpp`）、上行回调入口 `CallAbilityCallback`/`CallAbilityCallbackStub`（`call_ability_callback.cpp`、`call_ability_callback_stub.cpp`）、cellular_call 上行代理 `CallStatusCallbackProxy` 与下行代理 `CellularCallProxy`（`call_status_callback_proxy.cpp`、`cellular_call_proxy.cpp`）、死亡通知类（`call_manager_death_recipient.cpp`、`cellular_call_callback_death_recipient.cpp`）、蓝牙通话链（`bluetooth_call_client.cpp`、`bluetooth_call_proxy.cpp`、`i_bluetooth_call.h`）、星闪客户端 `nearlink_call_client.cpp`、VOIP 代理 `voip_call_manager_proxy.cpp`、超级隐私客户端 `super_privacy_manager_client.cpp`、维测助手 `native_call_manager_hisysevent.cpp` / `native_call_manager_utils.cpp`。头文件分置 `frameworks/native/include/` 与 `interfaces/innerkits/`。本能力为移植前基线，不涉及裁剪决策；本能力不含 JS/ETS/Cangjie 绑定（`frameworks/js`、`frameworks/ets`、`frameworks/cj` 另行裁剪）。本能力声明以下编译宏：`CALL_MANAGER_AUTO_START_OPTIMIZE`（场点：`call_manager_proxy.cpp`/`call_manager_proxy.h` 的多处 `#ifdef`，由 `frameworks/native/BUILD.gn` 在 `device_name == "rk3568"` 时注入 define；配套 `sa_profile/4005_auto_start_optimize.json`）。

## Requirements

### Requirement: CallManagerClient 延迟单例门面
系统 SHALL 由 `CallManagerClient`（`DECLARE_DELAYED_SINGLETON`，`interfaces/innerkits/call_manager_client.h` + `frameworks/native/src/call_manager_client.cpp`）持有文件级全局 `g_callManagerProxy`（`DelayedSingleton<CallManagerProxy>`），`Init(systemAbilityId)` 首次调用时创建并初始化 proxy，此后全部 ~60 个业务方法（`RegisterCallBack`/`UnRegisterCallBack`/`ObserverOnCallDetailsChange`/`DialCall`/`MakeCall`/`AnswerCall`/`RejectCall`/`HangUpCall`/`GetCallState`/`HoldCall`/`UnHoldCall`/`SwitchCall`/`CombineConference`/`SeparateConference`/`KickOutFromConference`/会议列表与补充业务 Get/Set 簇/`StartRtt`/`StopRtt`/`PostDialProceed`/`SetMuted`/`MuteRinger`/`SetAudioDevice`/`ControlCamera`/`SetPreviewWindow`/`SetDisplayWindow`/号码格式化转发/`InputDialerSpecialCode`/`RemoveMissedIncomingCallNotification`/`SetVoIPCallState`/`GetVoIPCallState`/`SetVoIPCallInfo`/`GetVoIPCallInfo`/`SendCallUiEvent`/`SendUssdResponse`/`SetCallPolicyInfo` 等）只做"proxy 为空判 + 转发"。proxy 未初始化时各方法返回 `TELEPHONY_ERR_UNINIT`（`HasCall` 返回 false、`RegisterBluetoothCallManagerCallbackPtr` 返回 nullptr）。例外两方法脱离 proxy 本地实现：`HasVoiceCapability` 读系统参数 `const.telephony.voice.capable`（`GetParameter`，值 "false" 即 false）。

#### Scenario: 未初始化调用
- **WHEN** 未先 `Init` 即调用任一业务方法（如 `DialCall`）
- **THEN** 返回 `TELEPHONY_ERR_UNINIT` 且不触发 IPC

#### Scenario: 重复初始化幂等
- **WHEN** `Init` 被再次调用
- **THEN** `g_callManagerProxy` 已存在时仅记日志，不重复创建 proxy

#### Scenario: 语音能力参数判定
- **WHEN** 系统参数 `const.telephony.voice.capable` 设为 "false"
- **THEN** `HasVoiceCapability` 返回 false

### Requirement: CallManagerProxy 服务连接与死亡重建
系统 SHALL 由 `CallManagerProxy`（`DECLARE_DELAYED_SINGLETON` 声明，`frameworks/native/src/call_manager_proxy.cpp`）以 `systemAbilityId_`（构造时默认 `TELEPHONY_CALL_MANAGER_SYS_ABILITY_ID`）经 samgr `GetSystemAbility` 连接系统服务，`ConnectService` 成功时 `iface_cast<ICallManagerService>` 缓存 `callManagerServicePtr_` 并以内部类 `CallManagerServiceDeathRecipient`（持有 proxy 引用，`OnRemoteDied` 转发 `CallManagerProxy::OnRemoteDied`）挂接死亡通知；每个对外方法前置 `ReConnectService()`（持锁拷贝指针后判空，空则 `ConnectService`，已注册过回调则 `ReRegisterCallBack`）。`OnRemoteDied` 校验死亡对象与缓存一致后清除指针并复位 `initStatus_`。`DisconnectService` 前 `UnRegisterCallBack`。锁原语使用 `ffrt::shared_mutex`（`clientLock_`）。

#### Scenario: 服务死亡后按需重连
- **WHEN** 服务侧死亡触发 `OnRemoteDied` 后应用再次调用 `DialCall`
- **THEN** `ReConnectService` 重新 `ConnectService`，若此前已注册回调则 `ReRegisterCallBack` 补注册

#### Scenario: 连接失败透传
- **WHEN** samgr / SystemAbility 取回空
- **THEN** `ConnectService` 返回 `TELEPHONY_ERR_LOCAL_PTR_NULL` / `TELEPHONY_ERR_IPC_CONNECT_STUB_FAIL`，业务方法透传

#### Scenario: 死亡对象校验
- **WHEN** `OnRemoteDied` 收到的对象与 `callManagerServicePtr_.AsObject()` 不同
- **THEN** 不清理缓存状态

### Requirement: 服务未启动时的延时自治拉起（CALL_MANAGER_AUTO_START_OPTIMIZE）
系统 SHALL 在定义 `CALL_MANAGER_AUTO_START_OPTIMIZE` 时（`frameworks/native/BUILD.gn` 的 rk3568 defines + `sa_profile/4005_auto_start_optimize.json` 的 run-on-create=false 配套）提供延迟起服路径：`CallManagerProxy::Init` 先经 `IsServiceStart`（samgr `CheckSystemAbility`）探测 SA 是否已在位，不在位时创建内部订阅者 `CallManagerProxySubcribed`（`EventFwk::CommonEventSubscriber`，订阅 `EventFwk::CommonEventSupport::COMMON_EVENT_RADIO_STATE_CHANGE`，thread mode `COMMON`）暂存并返回；收到广播回调里 `ConnectService` + 用 `GetCallBack()` 取暂存回调补 `RegisterCallBack` + `SetInitState(true)` + `UnSubscribeCommonEvent` 退订；`RegisterCallBack` 在服务未连上时把回调缓存进 `callBack_` 后返回 `TELEPHONY_ERR_LOCAL_PTR_NULL`。相关成员（`IsServiceStart`/`SetInitState`/`GetCallBack`/`CallManagerProxySubcribed`/`callBack_`）均在 `call_manager_proxy.h` 的 `#ifdef CALL_MANAGER_AUTO_START_OPTIMIZE` 块中。

#### Scenario: SA 未起时订阅开机路拉起
- **WHEN** rk3568 产品上调用 `Init` 且 SA 4005 尚未运行
- **THEN** 订阅 COMMON_EVENT_RADIO_STATE_CHANGE，并缓存注册回调不立即报最终失败

#### Scenario: 广播到达完成注册
- **WHEN** 射频状态变化广播触发 `OnReceiveEvent` 且 `ConnectService` 成功
- **THEN** 消费缓存回调完成注册、置初始化态并退订公共事件

### Requirement: 应用上行回调注册链
系统 SHALL 由 `CallManagerProxy::RegisterCallBack`（受 `registerStatus_` 防重，重复注册返回 `TELEPHONY_ERR_REGISTER_CALLBACK_FAIL`）创建 `CallAbilityCallback` 通过 `callManagerServicePtr_->RegisterCallBack` 注册进系统服务，成功后 `CallAbilityCallback::SetProcessCallback` 持住应用的 `CallManagerCallback`；服务侧返回的错误码按 `TELEPHONY_ERR_PERMISSION_ERR` / `TELEPHONY_ERR_ILLEGAL_USE_OF_SYSTEM_API` / 其他映射为 `TELEPHONY_ERR_REGISTER_CALLBACK_FAIL` 族。`UnRegisterCallBack` 反向对称。`CallAbilityCallback`（`call_ability_callback.cpp`）以 mutex_ 保护 callbackPtr_，把 `OnCallDetailsChange`/`OnMeeTimeDetailsChange`/`OnCallEventChange`/`OnCallDisconnectedCause`/`OnReportAsyncResults`/`OnReportMmiCodeResult`/`OnOttCallRequest`/`OnReportAudioDeviceChange`/`OnReportPostDialDelay`/`OnReportImsCallModeChange`/`OnReportCallSessionEventChange`/`OnReportPeerDimensionsChange` 等逐个转发（空回调返回 `TELEPHONY_SUCCESS`）。

#### Scenario: 注册成功
- **WHEN** 侧 SA 4005 注册成功（未定义任何需要入口权限的场景）
- **THEN** `registerStatus_` 置 true，后续状态变化经 `CallAbilityCallback` 转发到应用回调

#### Scenario: 未注册时状态上报丢弃
- **WHEN** `CallAbilityCallback` 收到上报但 callbackPtr_ 为空
- **THEN** 记为成功且不向应用分发

### Requirement: CallManagerServiceProxy 下行 IPC 编解码面
系统 SHALL 由 `CallManagerServiceProxy`（`IRemoteProxy<ICallManagerService>`，`frameworks/native/src/call_manager_service_proxy.cpp`）实现 `ICallManagerService` 全部命令的 MessageParcel 编解码：每命令先 `WriteInterfaceToken(CallManagerServiceProxy::GetDescriptor())`（失败返回 `TELEPHONY_ERR_WRITE_DESCRIPTOR_TOKEN_FAIL`）；代表命令码 `INTERFACE_REGISTER_CALLBACK`/`INTERFACE_UNREGISTER_CALLBACK`/`INTERFACE_OBSERVER_ON_CALL_DETAILS_CHANGE`/`INTERFACE_DIAL_CALL`/`INTERFACE_MAKE_CALL`/`INTERFACE_ANSWER_CALL` 等（`interfaces/innerkits/call_manager_service_ipc_interface_code.h` 定义）。`DialCall` 逐项解包 PacMap（accountId/videoState/dialScene/dialType/callType/extraParams/"btSlotIdUnknown"）且空号码本地拒绝（`TELEPHONY_ERR_ARGUMENT_INVALID`）。回包读 Int32 透传。

#### Scenario: DialCall 参数解包
- **WHEN** 应用经 `CallManagerProxy::DialCall` 发起拨号
- **THEN** proxy 侧把 PacMap 中 7 个键逐项写入 dataParcel，SA 返回码从 replyParcel 读取

#### Scenario: 描述符校验失败
- **WHEN** `WriteInterfaceToken` 失败
- **THEN** 返回 `TELEPHONY_ERR_WRITE_DESCRIPTOR_TOKEN_FAIL` 不发请求

### Requirement: CallAbilityCallbackStub 服务端上行解包入口
系统 SHALL 由 `CallAbilityCallbackStub`（`frameworks/native/src/call_ability_callback_stub.cpp`）在构造函数把 `CallManagerCallAbilityInterfaceCode` 家族（UPDATE_CALL_STATE_INFO/UPDATE_MEETIME_STATE_INFO/UPDATE_CALL_EVENT/UPDATE_CALL_DISCONNECTED_CAUSE/UPDATE_CALL_ASYNC_RESULT_REQUEST/REPORT_OTT_CALL_REQUEST/UPDATE_MMI_CODE_RESULT_REQUEST/UPDATE_AUDIO_DEVICE_CHANGE_RESULT_REQUEST/REPORT_POST_DIAL_DELAY/UPDATE_IMS_CALL_MODE_RECEIVE/CALL_SESSION_EVENT_CHANGE/PEERD_DIMENSIONS_CHANGE/CALL_DATA_USAGE_CHANGE/CAMERA_CAPABILITIES_CHANGE/UPDATE_PHONE_STATE，`interfaces/innerkits/call_ability_callback_ipc_interface_code.h`）注册进 memberFuncMap_；`OnRemoteRequest` 校验接口描述符（不符返回 `TELEPHONY_ERR_DESCRIPTOR_MISMATCH`）后分派。`OnUpdateCallStateInfo`/`OnUpdateMeeTimeStateInfo` 解包复用 `NativeCallManagerUtils::ReadCallAttributeInfo`；`OnUpdateCallEvent` 对 len 做 `MAX_LEN`=100000 边界检查后 `ReadRawData` 取 `CallEventInfo`；`OnUpdateAysncResults` 按 `CallResultReportId` 组装 PacMap 结果。

#### Scenario: 描述符不匹配
- **WHEN** 请求 parcel 的接口令牌与 `CallAbilityCallbackStub::GetDescriptor()` 不符
- **THEN** 返回 `TELEPHONY_ERR_DESCRIPTOR_MISMATCH`

#### Scenario: 长度越界防护
- **WHEN** `OnUpdateCallEvent` 读到的 len <= 0 或 >= MAX_LEN
- **THEN** 返回 `TELEPHONY_ERR_ARGUMENT_INVALID`

### Requirement: CallStatusCallbackProxy 上行代理
系统 SHALL 由 `CallStatusCallbackProxy`（`IRemoteProxy<ICallStatusCallback>`，`frameworks/native/src/call_status_callback_proxy.cpp`）实现 cellular_call 上行面（`interfaces/innerkits/call_status_callback_ipc_interface_code.h`），覆盖 `UpdateCallReportInfo`/`UpdateCallsReportInfo`（逐条 `CallReportInfo`，`TYPE_VOIP` 追加 voipCallInfo 11 项）、`UpdateDisconnectedCause`、`UpdateEventResultInfo`（WriteRawData sizeof CellEvent）、`UpdateRBTPlayInfo`、Get/Set Waiting/Restriction/RestrictionPwd/Transfer/CallClip/CallClir 结果、`StartRttResult`/`StopRttResult`、`GetImsConfigResult`/`SetImsConfigResult`/`GetImsFeatureValueResult`/`SetImsFeatureValueResult`、`ReceiveUpdateCallMediaModeRequest`/`ReceiveUpdateCallMediaModeResponse`、`InviteToConferenceResult`、`StartDtmfResult`/`StopDtmfResult`、`SendUssdResult`/`SendMmiCodeResult`/`GetImsCallDataResult`/`CloseUnFinishedUssdResult`、`ReportPostDialChar`/`ReportPostDialDelay`、`UpdateVoipEventInfo`、`HandleCallSessionEventChanged`/`HandlePeerDimensionsChanged`/`HandleCallDataUsageChanged`/`HandleCameraCapabilitiesChanged`（结构体经 WriteInt32(sizeof) + WriteRawData）。

#### Scenario: 结构体上行
- **WHEN** 调用 `UpdateGetTransferResult`
- **THEN** CallTransferResponse 以 len+RawData 序列化发送 `UPDATE_GET_TRANSFER` 命令

#### Scenario: VOIP 事件
- **WHEN** Cellular 侧上报 `UpdateVoipEventInfo`
- **THEN** voipCallId/bundleName/uid/voipCallEvent/errorReason 逐项写入 `UPDATE_VOIP_EVENT_INFO`

### Requirement: CellularCallProxy 命令面
系统 SHALL 由 `CellularCallProxy`（`IRemoteProxy<CellularCallInterface>`，`frameworks/native/src/cellular_call_proxy.cpp`）按 `CellularCallInterfaceCode`（`DIAL`/`HANG_UP`/`REJECT`/`ANSWER`/`HOLD_CALL` 等，`interfaces/innerkits/cellular_call_ipc_interface_code.h`）向 cellular_call 发送命令：逐命令 `WriteInterfaceToken(CellularCallProxy::GetDescriptor())`，`CellularCallInfo` 以 `WriteInt32(MAX_SIZE=10)` + `WriteRawData(sizeof(CellularCallInfo))` 传输，Remote() 空返回 `TELEPHONY_ERR_IPC_CONNECT_STUB_FAIL`。

#### Scenario: 呼叫未知态错误
- **WHEN** Remote() 为空（对端 broker 缺失）
- **THEN** 返回 `TELEPHONY_ERR_IPC_CONNECT_STUB_FAIL`

#### Scenario: 命令码直发
- **WHEN** `Dial`
- **THEN** 无参命令族/带 parcel 命令族均以 CellularCallInterfaceCode 码位发送

### Requirement: 死亡通知收件类
系统 SHALL 提供三层死亡通知：`CallManagerDeathRecipient` 与 `CellularCallCallbackDeathRecipient`（`frameworks/native/src/call_manager_death_recipient.cpp`、`cellular_call_callback_death_recipient.cpp`）为通用回调包装器（构造时收 `std::function<void(wptr<IRemoteObject>)>`，`OnRemoteDied` 时调用）；`CallManagerProxy` 内嵌类 `CallManagerServiceDeathRecipient`（`call_manager_proxy.h`，见服务连接 Requirement）转发到 `CallManagerProxy::OnRemoteDied`。

#### Scenario: CallManagerService 死亡通知
- **WHEN** SA 4005 侧对象死亡触发 `CallManagerDeathRecipient::OnRemoteDied`
- **THEN** 注册的回调函数收到 wptr，proxy 执行清理逻辑

#### Scenario: CellularCallCallback 死亡通知
- **WHEN** cellular_call 侧回调对象死亡
- **THEN** `CellularCallCallbackDeathRecipient` 执行注册的清理函数

### Requirement: 蓝牙通话链（BluetoothCallClient/BluetoothCallProxy/IBluetoothCall）
系统 SHALL 由 `BluetoothCallClient`（`interfaces/innerkits/bluetooth_call_client.h` + `frameworks/native/src/bluetooth_call_client.cpp`）持有 `g_callManagerProxyPtr` 与 `g_bluetoothCallProxyPtr`：`Init` 经 `DelayedSingleton<CallManagerProxy>::GetInstance()` 初始化并 `GetProxyObjectPtr(PROXY_BLUETOOTH_CALL)` 取对象 `iface_cast<IBluetoothCall>`。部分能力（`RegisterCallBack`/`DialCall`/`IsRinging`/`HasCall`/`SetMuted`/`MuteRinger`/`SetAudioDevice` 等）复用 callManagerProxyPtr，通话控制族（`AnswerCall`/`RejectCall`/`HangUpCall`/`GetCallState`/`HoldCall`/`UnHoldCall`/`SwitchCall`/会议族/DTMF 族）走 IBluetoothCall。`DialCall` 在 extras 补写 `PutBooleanValue("btSlotIdUnknown", true)`；`SetAudioDevice` 手动组 `AudioDevice` 结构（memset_s/memcpy_s/kMaxAddressLen）；设备管理 `AddAudioDevice`/`RemoveAudioDevice`/`GetCurrentCallList`/`ResetHearingAidDeviceList` 全走 IBluetoothCall。`BluetoothCallProxy`（`frameworks/native/src/bluetooth_call_proxy.cpp`）以 `BluetoothCallInterfaceCode` 码位（INTERFACE_BT_ANSWER_CALL/INTERFACE_BT_REJECT_CALL/…/INTERFACE_BT_GET_CURRENT_CALL_LIST/INTERFACE_BT_ADD_AUDIO_DEVICE/INTERFACE_BT_REMOVE_AUDIO_DEVICE/INTERFACE_BT_RESET_NEARLINK_AUDIO_DEVICE/INTERFACE_BT_RESET_BT_HEARINGAID_AUDIO_DEVICE，在 `interfaces/innerkits/bluetooth_call_ipc_interface_code.h`）收发;`IBluetoothCall`（`interfaces/innerkits/bluetooth_call_client.h` 对应 `frameworks/native/include/i_bluetooth_call.h`，`IRemoteBroker`，`DECLARE_INTERFACE_DESCRIPTOR(u"OHOS.Telephony.IBluetoothCall")`) 定义上述纯虚接口。

#### Scenario: 蓝牙侧拨号
- **WHEN** 蓝牙框架调 `BluetoothCallClient::DialCall`
- **THEN** extras 标记 btSlotIdUnknown=true 后经 CallManagerProxy 转发到 SA 4005

#### Scenario: 未初始化防护
- **WHEN** 未先 `Init` 即调用 `AnswerCall`
- **THEN** 返回 `TELEPHONY_ERR_UNINIT`，不发起任何 IPC

#### Scenario: 取通话列表
- **WHEN** 调用 `GetCurrentCallList(slotId)`
- **THEN** proxy 向 SA 发送 INTERFACE_BT_GET_CURRENT_CALL_LIST 并回传 `std::vector<CallAttributeInfo>`

### Requirement: 星闪客户端 NearlinkCallClient
系统 SHALL 由 `NearlinkCallClient`（`interfaces/innerkits/nearlink_call_client.h` + `frameworks/native/src/nearlink_call_client.cpp`）以成员指针（callManagerProxyPtr_/bluetoothCallProxyPtr_）复用蓝牙通路：`Init` 走同 `CallManagerProxy` 初始化 + `GetProxyObjectPtr(PROXY_BLUETOOTH_CALL)` + `iface_cast<IBluetoothCall>`；`RegisterCallBack`/`UnRegisterCallBack` 走 CallManagerProxy，通话控制族（Answer/Reject/HangUp/会议/DTMF）走同一 IBluetoothCall 接口。

#### Scenario: 星闪与蓝牙共享同一代理
- **WHEN** `NearlinkCallClient::Init`
- **THEN** 复用 `PROXY_BLUETOOTH_CALL` 拉取 IBluetoothCall 对象

#### Scenario: 未初始化防护
- **WHEN** 未 `Init` 时调用任何方法
- **THEN** 返回 `TELEPHONY_ERR_UNINIT`

### Requirement: VoipCallManagerProxy 代理
系统 SHALL 由 `VoipCallManagerProxy`（`IRemoteProxy<IVoipCallManagerService>`，`frameworks/native/src/voip_call_manager_proxy.cpp`，命令码定义于 `interfaces/innerkits/i_voip_call_manager_service.h`）向 VOIP 业务侧发送命令，命令族含 `INTERFACE_REPORT_INCOMING_CALL`/`INTERFACE_REPORT_INCOMING_CALL_ERROR`/`INTERFACE_REPORT_CALL_STATE_CHANGE`/`INTERFACE_REPORT_OUTGOING_CALL`/`INTERFACE_REGISTER_CALLBACK`/`INTERFACE_UN_REGISTER_CALLBACK`/`INTERFACE_REPORT_VOIP_INCOMING_CALL`/`INTERFACE_REPORT_VOIP_CALL_EXTENSIONID`/`INTERFACE_ANSWER_VOIP_CALL`/`INTERFACE_HANGUP_VOIP_CALL`/`INTERFACE_REJECT_VOIP_CALL`/`INTERFACE_REGISTER_CALL_MANAGER_CALLBACK`/`INTERFACE_UNREGISTER_CALL_MANAGER_CALLBACK`/`INTERFACE_UNLOAD_VOIP_SA`/`INTERFACE_SEND_CALL_UI_EVENT`/`INTERFACE_REPORT_CALL_AUDIO_EVENT_CHANGE`/`INTERFACE_SEND_CALL_UI_EVENT_FOR_WINDOW`，入参为 `AppExecFwk::PacMap` 键（callId/voipCallType/userName/abilityName/voipCallState/showBannerForIncomingCall/isConferenceCall/isVoiceAnswerSupported/startReportTime 等）或 `VoipCallEventInfo`，回包带 result + `ErrorReason`（ReportIncomingCall/ReportOutgoingCall 双返回值）。`ReportIncomingCall` 使用 `OHOS::HiviewDFX::HiTraceChain` 开链；失败路径打维测事件 `NativeCallManagerHisysevent::WriteVoipCallEvent`。

#### Scenario: 呼入报告
- **WHEN** SA 调 `ReportIncomingCall(extras, userProfile, reason)`
- **THEN** 逐项序列化 PacMap + userProfile 向量，回包读出 result 与 ErrorReason

#### Scenario: 对端缺失打维测
- **WHEN** Remote() 为空
- **THEN** 向 `NativeCallManagerHisysevent::WriteVoipCallEvent` 报 Scenario::VOIP_PROXY_IPC_CONNECTTING 错误

### Requirement: 超级隐私客户端 SuperPrivacyManagerClient
系统 SHALL 由 `SuperPrivacyManagerClient`（`interfaces/innerkits/super_privacy_manager_client.h` + `frameworks/native/src/super_privacy_manager_client.cpp`，`GetInstance()` 进程内唯一静态实例）提供 `SetSuperPrivacyMode(mode, source)`：经 samgr `LoadSystemAbility(SUPER_PRIVACY_MANAGER_SA_ID=66102, LOAD_SA_TIMEOUT_SECONDS=4)` 拉起超级隐私服务，以接口描述符 `u"OHOS.AppSecurityPrivacy.SecurityPrivacyServer.SuperPrivacy.ISuperPrivacyManager"` 与命令码 `COMMAND_SET_SUPER_PRIVACY_MODE`（= MIN_TRANSACTION_ID + 0）`TF_SYNC` 发送 mode/source 两个 Int32，任一失败返回 `ERR_INVALID_VALUE`/`ERR_INVALID_DATA`。

#### Scenario: SA 加载
- **WHEN** `SetSuperPrivacyMode` 调用
- **THEN** 优先同步 LoadSystemAbility SA 66102，加载失败直接返回 `ERR_INVALID_VALUE`

#### Scenario: 全链成功
- **WHEN** SA 加载成功且 parcel 读写成功
- **THEN** SendRequest 发出后透传返回码

### Requirement: 客户端维测与解码助手
系统 SHALL 由 `NativeCallManagerUtils::ReadCallAttributeInfo(MessageParcel&)`（`frameworks/native/include/native_call_manager_utils.h` + `native_call_manager_utils.cpp`）提供 CallAttributeInfo 反序列化唯一实现（Stub 侧调用），由 `NativeCallManagerHisysevent::WriteVoipCallEvent(callId, bundleName, scenario, errorCode, msg, ...)`（`frameworks/native/include/native_call_manager_hisysevent.h` + `native_call_manager_hisysevent.cpp`）记录 VOIP IPC 异常事件（当前仅 VoipCallManagerProxy 失败路径调用）。

#### Scenario: 属性回读
- **WHEN** `CallAbilityCallbackStub::OnUpdateCallStateInfo` 收到包
- **THEN** 经 `NativeCallManagerUtils::ReadCallAttributeInfo` 逐字段重建 CallAttributeInfo

#### Scenario: VOIP IPC 异常上报
- **WHEN** VoipCallManagerProxy 任一 Remote 为空或 IPC 返回值非 0
- **THEN** `WriteVoipCallEvent` 记录对应 Scenario 与 errorCode

### Requirement: 手表移植预计移除面（native 层）
系统 SHALL 把以下预计在手表目标上整体移除的 native 文件集中登记（基线中它们当前编译且行为如上）：蓝牙通话链（`bluetooth_call_client.cpp`、`bluetooth_call_proxy.cpp`、`i_bluetooth_call.h`、对应 `interfaces/innerkits/bluetooth_call_client.h` 与 `bluetooth_call_ipc_interface_code.h`）、星闪客户端（`nearlink_call_client.cpp`、`nearlink_call_client.h`）、超级隐私客户端（`super_privacy_manager_client.cpp`、`super_privacy_manager_client.h`）、VOIP 代理（`voip_call_manager_proxy.cpp`，手表暂不支持 VOIP；`native_call_manager_hisysevent.cpp` 随之失去唯一调用方）；同时预计随产品定义裁剪 `CALL_MANAGER_AUTO_START_OPTIMIZE` 块（`call_manager_proxy.cpp` 中的延时拉起路径与 `sa_profile/4005_auto_start_optimize.json`）。utils 层预计移除文件见 call-utils 规格同名 Requirement。

#### Scenario: 蓝牙链移除影响 GetProxyObjectPtr
- **WHEN** 手表基线移除蓝牙通话链后调用 `GetProxyObjectPtr(PROXY_BLUETOOTH_CALL)`
- **THEN** 调用方清零，`PROXY_BLUETOOTH_CALL` 通路在 SA 侧的裁剪口径需在裁剪 delta 中对齐（具体由裁剪 delta 决定）

#### Scenario: 维测助手随之裁剪
- **WHEN** VOIP 代理移除
- **THEN** `native_call_manager_hisysevent.cpp` 无剩余调用点，`NativeCallManagerHisysevent` 一并移除（具体由裁剪 delta 决定）