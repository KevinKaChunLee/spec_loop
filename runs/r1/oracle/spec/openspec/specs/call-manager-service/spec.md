# 服务与 IPC 入口（call-manager-service）Specification

## Purpose
描述 `telephony_call_manager/services/call_manager_service/` 的服务层：`CallManagerService`（SA 4005，进程 foundation，`sa_profile/4005.json` 与 `sa_profile/4005_auto_start_optimize.json`）、`CallManagerServiceStub`（IPC 码表分发）、`TelephonyCustWrapper`（`libtelephony_cust_api.z.so` dlopen 包装）。IPC 枚举落点：`interfaces/innerkits/call_manager_service_ipc_interface_code.h`（`CallManagerInterfaceCode` 共 79 项）、`call_status_callback_ipc_interface_code.h`（`CallStatusInterfaceCode` 共 41 项）等。编译开关：`OHOS_BUILD_ENABLE_TELEPHONY_CUST`（`Init` 时初始化 cust wrapper）、`HICOLLIE_ENABLE`（stub 的 `SetTimer`/`CancelTimer`）、`SUPPORT_MUTE_BY_DATABASE`（`MuteRinger` 联动 `InteroperableSettingsHandler::SendMuteRinger`，仅 `target_platform == "watch"`）。

## Requirements

### Requirement: SystemAbility 生命周期
系统 SHALL 由 `CallManagerService : public SystemAbility, public CallManagerServiceStub`（`DECLARE_DELAYED_SINGLETON` + `DECLARE_SYSTEM_ABILITY`，构造 `SystemAbility(TELEPHONY_CALL_MANAGER_SYS_ABILITY_ID, true)`，文件级 `SystemAbility::MakeAndRegisterAbility` 注册）在 `OnStart()` 中先 `Init()`（失败即退出）再 `SystemAbility::Publish`，以 `state_ == STATE_RUNNING` 防重入，末尾调用 `LocationSubscriber::Subscriber()` 订阅地震预警广播；`Init()` 依次初始化 `CallControlManager`、`ReportCallInfoHandler`、`CellularCallConnection`（`Init(TELEPHONY_CELLULAR_CALL_SYS_ABILITY_ID)`）、`CallRecordsManager`、`BluetoothConnection`、`DistributedCallManager`、`DistributedCommunicationManager`，并 `AddSystemAbilityListener(AUDIO_POLICY_SERVICE_ID)` 与 `AddSystemAbilityListener(DISTRIBUTED_HARDWARE_DEVICEMANAGER_SA_ID)`。
#### Scenario: 音频策略服务上线
- **WHEN** `OnAddSystemAbility` 收到 `AUDIO_POLICY_SERVICE_ID` 上线
- **THEN** `AudioProxy` 注册 `SetAudioMicStateChangeCallback`/`SetAudioDeviceChangeCallback`/`SetAudioPreferDeviceChangeCallback` 三个回调

### Requirement: IPC 码表分发
系统 SHALL 由 `CallManagerServiceStub : public IRemoteStub<ICallManagerService>` 在构造时经 `InitCallBasicRequest`/`InitCallUtilsRequest`/`InitCallConferenceRequest`/`InitCallDtmfRequest`/`InitCallSupplementRequest`/`initCallConferenceExRequest`/`InitCallMultimediaRequest`/`InitImsServiceRequest`/`InitOttServiceRequest`/`InitVoipOperationRequest`/`InitBluetoothOperationRequest` 十一组建表方法把 `CallManagerInterfaceCode` 全量映射进 `memberFuncMap_`；`OnRemoteRequest` 先比对 descriptor（失配返回 `TELEPHONY_ERR_DESCRIPTOR_MISMATCH`）再查表执行，未命中回落 `IPCObjectStub::OnRemoteRequest`；stub 层不做权限校验，权限校验统一在 `CallManagerService` 方法内经 `TelephonyPermission::CheckCallerIsSystemApp()` 与 `TelephonyPermission::CheckPermission(...)`（`OHOS_PERMISSION_SET_TELEPHONY_STATE`/`GET_TELEPHONY_STATE`/`PLACE_CALL`/`ANSWER_CALL`/`READ_CALL_LOG`/`WRITE_CALL_LOG`）执行。
#### Scenario: 拨号 IPC 解包与分发
- **WHEN** 客户端以 `INTERFACE_DIAL_CALL` 码请求
- **THEN** `OnDialCall` 读 accountId/videoState/dialScene/dialType/callType/extraParams/bundleName/btSlotIdUnknown 填 `AppExecFwk::PacMap`，号码超长返回 `CALL_ERR_NUMBER_OUT_OF_RANGE`，权限通过后进入 `CallManagerService::DialCall`

### Requirement: 拨号后语音信箱计数清零
系统 SHALL 由 `CallManagerService::DialCall` 在拨号成功后比对号码与 `CoreManagerInner::GetInstance().GetVoiceMailNumber(...)`，相等则 `SetVoiceMailCount(slotId, 0)` 清零语音信箱计数；失败路径记 `CallManagerHisysevent::WriteDialCallFaultEvent`。
#### Scenario: 拨打语音信箱号码
- **WHEN** 拨号号码等于该 slot 的语音信箱号码
- **THEN** 拨号继续执行且语音信箱未读计数被清零

### Requirement: 特殊拨号盘指令
系统 SHALL 由 `InputDialerSpecialCode` 匹配 `supportSpecialCode_`（"*#2846#"、"*#*#2846579#*#*" 等 16 项）后以 `EventFwk::CommonEventManager::PublishCommonEvent` 发布 `COMMON_EVENT_SPECIAL_CODE`。
#### Scenario: 输入工程模式指令
- **WHEN** 应用经 IPC 调用 `InputDialerSpecialCode` 且指令串命中 `supportSpecialCode_`
- **THEN** 发布 `COMMON_EVENT_SPECIAL_CODE` 公共事件

### Requirement: UI 事件路由
系统 SHALL 由 `SendCallUiEvent(callId, eventName)` 按事件名路由：`EVENT_IS_CELIA_CALL`→`dealCeliaCallEvent`、`EVENT_SPEAKER_OFF`→`AudioProxy::SetSpeakerDevActive(false)`、`DISPLAY_SPECIFIED_CALL_PAGE_BY_CALL_ID`→`HandleDisplaySpecifiedCallPage`、`EVENT_BLUETOOTH_SCO_STATE_ON/OFF`→`BluetoothCallConnection::ConnectBtSco/DisConnectBtSco`、`EVENT_SUPPORT_BLUETOOTH_CALL`/`EVENT_NOT_SUPPORT_BLUETOOTH_CALL`→`GetSupportBtCall`、`EVENT_CELIA_AUTO_ANSWER_CALL_ON/OFF`→`HandleCeliaAutoAnswerCall`、`EVENT_VOIP_CALL_SUCCESS/FAILED`→`HandleVoIPCallEvent`、`EVENT_INVALID_VIDEO_FD`→`HandleVideoRingPlayFail`。
#### Scenario: 蓝牙 SCO 开启事件
- **WHEN** 通话界面经 `SendCallUiEvent` 上报 `EVENT_BLUETOOTH_SCO_STATE_ON`
- **THEN** `BluetoothCallConnection::ConnectBtSco` 建立 SCO 音频链路

### Requirement: 蓝牙与 VoIP 回调注册
系统 SHALL 由 `GetProxyObjectPtr(PROXY_BLUETOOTH_CALL)` 懒创建 `BluetoothCallService` 并缓存于 `proxyObjectPtrMap_`；`RegisterBluetoothCallManagerCallbackPtr(macAddress)` 懒建 `CallStatusCallback` 并经 `Bluetooth::HandsFreeUnit::GetProfile()->RegisterObserver(bluetoothCallObserver_)`（`BluetoothCallState`）注册、`BluetoothCallConnection::SetMacAddress` 记录地址；`RegisterVoipCallManagerCallback` 经 `VoipCallConnection::Init(TELEPHONY_VOIP_CALL_MANAGER_SYS_ABILITY_ID)` 注册回调。
#### Scenario: 蓝牙框架索取代理
- **WHEN** 蓝牙侧经 `INTERFACE_GET_PROXY_OBJECT_PTR` 请求 `PROXY_BLUETOOTH_CALL`
- **THEN** 返回缓存的 `BluetoothCallService` 远端对象供 `BluetoothCallClient` 使用

### Requirement: EDM 策略下发
系统 SHALL 由 `SetCallPolicyInfo` 仅在 `uid == EDM_UID(3057)` 时把策略转交 `callControlManagerPtr_->SetEdmPolicy`（进入 `EdmCallPolicy::SetCallPolicy` 名单）。
#### Scenario: 非 EDM uid 拒绝
- **WHEN** 非 3057 的 uid 调用 `SetCallPolicyInfo`
- **THEN** 策略不生效

### Requirement: TelephonyCust dlopen 包装
系统 SHALL 由 `TelephonyCustWrapper::InitTelephonyCustWrapper` 经 `dlopen("libtelephony_cust_api.z.so", RTLD_NOW)` + `dlsym` 绑定 `IsHideViolenceOrEmcNumbersInCallLog`（`isHideViolenceOrEmcNumbersInCallLog_`）与 `IsChangeDialNumberToTwEmc`（`isChangeDialNumberToTwEmc_`）两个函数指针，析构 `dlclose`；供 `DialCall` 改写台湾紧急号码与 `CallRecordsManager` 隐藏暴力/急救号记录。
#### Scenario: 台湾紧急号码改写
- **WHEN** `OHOS_BUILD_ENABLE_TELEPHONY_CUST` 在位且拨号命中 `isChangeDialNumberToTwEmc_`
- **THEN** 拨号号码被改写后再下发
