# 客户端框架与接口（client-frameworks）Specification

## Purpose
描述 `telephony_call_manager/frameworks/` 与 `interfaces/` 的客户端框架：`frameworks/native`（`CallManagerClient`/`CallManagerProxy`/`CallManagerServiceProxy`/`CallAbilityCallback`/`CallManagerDeathRecipient`/`CellularCallProxy`/`BluetoothCallClient`/`NearlinkCallClient`/`SuperPrivacyManagerClient`/`VoipCallManagerProxy`/`NativeCallManagerUtils`/`NativeCallManagerHisysevent`/`CallStatusCallbackProxy`，target `tel_call_manager_api`）、`frameworks/js`（napi 模块 `telephony.call`，target `call`）、`frameworks/ets/taihe`（taihe 绑定）与 `frameworks/cj`（仓颉 FFI，target `cj_telephony_call_ffi`）；接口定义在 `interfaces/innerkits`（`call_manager_client.h`、`call_manager_base.h`（CallType/TelCallState/DialScene/CallStateToApp/PhoneOrWatchDial 等枚举族）、`call_manager_info.h`（`CallAttributeInfo`/`VoipCallReportInfo`/`NumberMarkInfo` 等结构）、`call_manager_errors.h`（`CallManagerErrorCode` 82 项）、`call_manager_service_ipc_interface_code.h` 等 5 个 IPC 码表头）与 `interfaces/kits/js`（`@ohos.telephony.call.d.ts`）。编译开关：`CALL_MANAGER_AUTO_START_OPTIMIZE`（`frameworks/native/BUILD.gn` 中 `device_name == "rk3568"` 时定义，广播触发延迟连接）。

## Requirements

### Requirement: 客户端单例与服务连接
系统 SHALL 由 `CallManagerClient`（`interfaces/innerkits/call_manager_client.h`，`DelayedSingleton`）全量转发文件级 `g_callManagerProxy`（`std::shared_ptr<CallManagerProxy>`），未 `Init` 的方法返回 `TELEPHONY_ERR_UNINIT`；`CallManagerProxy::Init(systemAbilityId)`→`ConnectService`（samgr `GetSystemAbility`→`AddDeathRecipient`（`CallManagerServiceDeathRecipient`）→`iface_cast<ICallManagerService>`），`OnRemoteDied` 校验 remote 一致后清指针并置 `initStatus_ = false`；`ReConnectService` 重连成功且先前已注册则 `ReRegisterCallBack`；`CALL_MANAGER_AUTO_START_OPTIMIZE` 下订阅 `COMMON_EVENT_RADIO_STATE_CHANGE` 延迟连接。
#### Scenario: 服务死亡后重建回调
- **WHEN** call_manager 服务死亡触发 `CallManagerServiceDeathRecipient::OnRemoteDied`
- **THEN** 代理清空并允许 `ReConnectService`；重连成功后已注册回调经 `ReRegisterCallBack` 恢复

### Requirement: 应用侧回调注册
系统 SHALL 由 `CallManagerProxy::RegisterCallBack` 创建 `CallAbilityCallback`（`: CallAbilityCallbackStub`，`SetProcessCallback` 持有应用 `CallManagerCallback`）注册到服务并 `registerStatus_` 防重；`CallAbilityCallback` 覆盖 `OnCallDetailsChange/OnMeeTimeDetailsChange/OnCallEventChange/OnCallDisconnectedCause/OnReportAsyncResults/OnOttCallRequest/OnReportMmiCodeResult/OnReportAudioDeviceChange/OnReportPostDialDelay/OnReportImsCallModeChange/OnReportCallSessionEventChange/OnReportPeerDimensionsChange/OnReportCallDataUsageChange/OnReportCameraCapabilities/OnPhoneStateChange` 后转交应用回调。
#### Scenario: 注册回调重复注册
- **WHEN** 同一客户端二次调用 `RegisterCallBack`
- **THEN** `registerStatus_` 防重，不重复向服务注册

### Requirement: IPC 序列化层
系统 SHALL 由 `CallManagerServiceProxy`（`: IRemoteProxy<ICallManagerService>`）以 `CallManagerInterfaceCode` 全量打包发送各接口；`CellularCallProxy` 以 `CellularCallInterfaceCode` 直发且 `WriteRawData(&callInfo, sizeof(CellularCallInfo))` 前先 `WriteInt32(MAX_SIZE = 10)`；`CallStatusCallbackProxy` 按 `CallStatusInterfaceCode` 发送上行回调；`VoipCallManagerProxy` 提供 `ReportIncomingCall/ReportIncomingCallError/ReportCallStateChange/ReportOutgoingCall`（写 callId/voipCallType/userName/abilityName/voipCallState/showBannerForIncomingCall/isConferenceCall/isVoiceAnswerSupported/startReportTime + userProfile）。
#### Scenario: 序列化回读对称
- **WHEN** 服务端 `WriteCallAttributeInfo` 序列化、客户端 `NativeCallManagerUtils::ReadCallAttributeInfo` 反序列化
- **THEN** 字段序完全对称，VOIP 附加字段一致回读

### Requirement: 语音能力与系统参数
系统 SHALL 由 `CallManagerClient::HasVoiceCapability` 读系统参数 `const.telephony.voice.capable`（缺省 true）；`SuperPrivacyManagerClient`（单例）按需 `LoadSystemAbility(SUPER_PRIVACY_MANAGER_SA_ID = 66102, 4s)` 以 `COMMAND_SET_SUPER_PRIVACY_MODE = MIN_TRANSACTION_ID + 0` 直发 `SetSuperPrivacyMode(mode, source)`。
#### Scenario: 查询语音能力
- **WHEN** 客户端调用 `HasVoiceCapability`
- **THEN** 按 `const.telephony.voice.capable` 参数返回（未配置视为 true）

### Requirement: 蓝牙与星闪客户端
系统 SHALL 由 `BluetoothCallClient::Init` 经 `CallManagerProxy::GetProxyObjectPtr(PROXY_BLUETOOTH_CALL)`→`iface_cast<IBluetoothCall>`，`DialCall` 时 extras 加 `PutBooleanValue("btSlotIdUnknown", true)`；`NearlinkCallClient`（`DelayedRefSingleton`）复用同一 proxy，提供 `GetCurrentCallList(slotId)`、`AddAudioDevice/RemoveAudioDevice` 等。
#### Scenario: 蓝牙框架拨号
- **WHEN** 蓝牙侧经 `BluetoothCallClient::DialCall` 拨号
- **THEN** 请求以 `btSlotIdUnknown` 标记进入 `CallManagerService::DialCall` 的 `BtCallWaitSlotId` 流程

### Requirement: JS/ETS/仓颉绑定
系统 SHALL 由 `frameworks/js` 以 `DECLARE_NAPI_FUNCTION` 注册 dial/dialCall/makeCall/answer/reject/hangup、getCallWaitingStatus/setCallWaiting、getCallTransferInfo/setCallTransfer、startDTMF/stopDTMF/postDialProceed、startRTT/stopRTT、setAudioDevice、controlCamera、on/off 等 API（`native_module.cpp` `RegisterModule` 模块名 `telephony.call`，导出 call.js/call.abc）；`frameworks/ets/taihe`（`ohos_taihe("run_taihe")`、`taihe_shared_library("telephony_call_taihe_native")`、`generate_static_abc("telephony_call_abc")`）与 `frameworks/cj`（`cj_telephony_call_ffi`，依赖 `napi:cj_bind_ffi`）提供对应语言绑定。
#### Scenario: JS 侧订阅通话事件
- **WHEN** 应用 JS 侧调用 `telephony.call.on('callDetailsChange', ...)`
- **THEN** 经 napi 注册应用回调并经 `ICallAbilityCallback` 路径收到状态变化
