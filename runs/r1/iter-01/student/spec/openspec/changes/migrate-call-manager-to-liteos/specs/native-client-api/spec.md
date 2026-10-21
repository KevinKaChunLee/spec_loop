# Spec Delta

## REMOVED Requirements

### Requirement: CallManagerProxy 服务连接与死亡重建

**Reason**: AGENTS 明确 liteOS 中 callmanager 不继承 SystemAbility 也不实现 IPC 调用，直接从 CallManagerClient 调用 CallManagerService 的接口；design D2 客户端直调服务、D3 所有 proxy/death recipient 传输类不迁移；`call_manager_proxy.cpp` 与 `call_manager_death_recipient.cpp` 均在 design D7 被删文件表。
**Migration**: 删除 `frameworks/native/src/call_manager_proxy.cpp/.h`（`GetSystemAbility` 连接、`iface_cast<ICallManagerService>` 缓存 `callManagerServicePtr_`、`ConnectService`/`DisconnectService`/`ReConnectService` 按需重连与 `ReRegisterCallBack` 补注册、`OnRemoteDied` 死亡清理、`ffrt::shared_mutex clientLock_`）与内嵌类 `CallManagerServiceDeathRecipient`；`CallManagerClient` 改 `Init` 直取 `CallManagerService` 进程内单例（见本 delta MODIFIED「CallManagerClient 延迟单例门面」条）；`frameworks/native/include/i_call_manager_service.h` 接口头保留（design D3）。恢复条件：恢复 SA/IPC 形态时按基线重建连接与死亡重建链。

### Requirement: 服务未启动时的延时自治拉起（CALL_MANAGER_AUTO_START_OPTIMIZE）

**Reason**: `CALL_MANAGER_AUTO_START_OPTIMIZE` 属 AGENTS「特性宏支持范围-不支持」清单；design D7 裁决该块随 proxy 删除；liteOS 无 SA 按需启动生命周期与公共事件订阅通路（design D2/D6 广播行）。
**Migration**: 删除 `call_manager_proxy.h` 的 `#ifdef CALL_MANAGER_AUTO_START_OPTIMIZE` 块（`IsServiceStart`/`SetInitState`/`GetCallBack`/`callBack_` 暂存成员）与 `CallManagerProxySubcribed` 订阅 `COMMON_EVENT_RADIO_STATE_CHANGE` 延迟连接链；`frameworks/native/BUILD.gn` 的 rk3568 defines 注入块删除、`sa_profile/4005_auto_start_optimize.json` 随 sa_profile 整目录不迁移（design D10，build-config delta）。恢复条件：恢复 SA 按需启动形态时按基线重建。

### Requirement: CallManagerServiceProxy 下行 IPC 编解码面

**Reason**: AGENTS 不实现 IPC 调用；design D3 裁决 `call_manager_service_proxy.cpp` 不迁移；`CallManagerClient` 直调后无 MessageParcel 编解码面。
**Migration**: 删除 `frameworks/native/src/call_manager_service_proxy.cpp/.h`（`WriteInterfaceToken(CallManagerServiceProxy::GetDescriptor())` 描述符写入、各命令的 parcel 组包与回包 Int32 读取、`DialCall` 的 PacMap 7 键解包与空号码本地拒绝——PacMap 按 design D5 换普通结构体、拨号参数以结构体直传，空号码拒绝语义在直调面保留）；`CallManagerInterfaceCode` 等命令码枚举值原样保留为 ABI 约定、不再承载实际 IPC（design D3，需人工复核：后续恢复系统形态须保证枚举值与基线一致）。恢复条件：恢复 IPC 形态时按基线重建编解码面。

### Requirement: CallStatusCallbackProxy 上行代理

**Reason**: AGENTS 不实现 IPC 调用；design D3 裁决 `call_status_callback_proxy.cpp` 不迁移（D7 被删文件表 frameworks/native 行）；cellular_call 上行改经 `stub/cellular_call_client` 桩直调。
**Migration**: 删除 `frameworks/native/src/call_status_callback_proxy.cpp/.h`（`UpdateCallReportInfo`/`UpdateCallsReportInfo` 的 `CallReportInfo` 逐条与 TYPE_VOIP 的 voipCallInfo 11 项追写、`UpdateDisconnectedCause`/`UpdateEventResultInfo`/`UpdateRBTPlayInfo`、补充业务 Get/Set 结果族、`StartRttResult`/`StopRttResult`、媒体面回调族、`ReportPostDialChar`/`ReportPostDialDelay`、`UpdateVoipEventInfo` 的 parcel 上行封装均不迁移）；cellular_call 上行语义由 services 侧 `CallStatusCallback` 直调改造承载（design D3/D4；telephony-interaction delta「CallStatusCallback 上行转换与 app 上报」条，测试经 `stub/cellular_call_client` 桩触发等价函数进入）；`CallStatusCallbackInterfaceCode` 枚举值保留（ABI 约定，design D3）。恢复条件：恢复 IPC 形态时按基线重建上行代理。

### Requirement: CellularCallProxy 命令面

**Reason**: AGENTS 规定与 cellular_call 模块 IPC 通信改用 `CellularCallClient::GetInstance().Xxx()` 形式替代、对应接口通过打桩实现；design D3/D4；`cellular_call_proxy.cpp` 在 D7 被删文件表。
**Migration**: 删除 `frameworks/native/src/cellular_call_proxy.cpp/.h`（`CellularCallInterfaceCode` 命令直发、`CellularCallInfo` 的 `WriteInt32(MAX_SIZE=10)` + `WriteRawData(sizeof(CellularCallInfo))` 组包、`Remote()` 空返回 `TELEPHONY_ERR_IPC_CONNECT_STUB_FAIL` 分支）；cellular_call 下行命令出口由 services 侧 `CellularCallConnection` 适配器改调 `stub/cellular_call_client` 桩（design D4；telephony-interaction delta「呼叫控制下行出口」条承载语义，桩默认不可用与基线"服务未连接"分支语义一致）；`CellularCallInterfaceCode` 枚举值保留（ABI 约定，design D3）。恢复条件：恢复 IPC 形态时按基线重建命令面。

### Requirement: 死亡通知收件类

**Reason**: AGENTS 不实现 IPC 调用；design D3 裁决 death recipient 传输类全部不迁移；`call_manager_death_recipient.cpp`/`cellular_call_callback_death_recipient.cpp` 在 D7 被删文件表。
**Migration**: 删除 `frameworks/native/src/call_manager_death_recipient.cpp/.h` 与 `cellular_call_callback_death_recipient.cpp/.h`（构造收 `std::function<void(wptr<IRemoteObject>)>`、`OnRemoteDied` 转发的通用包装器）及 `CallManagerProxy` 内嵌 `CallManagerServiceDeathRecipient`（随 proxy 删除）；服务上下线/死亡清理语义改由桩状态切换在测试中模拟（telephony-interaction delta 连接条）。恢复条件：恢复 IPC 形态时按基线重建收件类。

### Requirement: 蓝牙通话链（BluetoothCallClient/BluetoothCallProxy/IBluetoothCall）

**Reason**: AGENTS「功能范围」明确 liteOS 不支持 BLUETOOTH 类型通话，`ABILITY_BLUETOOTH_SUPPORT` 属不支持宏；design D7 被删文件表 frameworks/native 行列出 `bluetooth_call_client.cpp`/`bluetooth_call_proxy.cpp`。
**Migration**: 删除 `frameworks/native/src/bluetooth_call_client.cpp`、`bluetooth_call_proxy.cpp`、`frameworks/native/include/i_bluetooth_call.h`、`interfaces/innerkits/bluetooth_call_client.h` 与 `bluetooth_call_ipc_interface_code.h`（`GetProxyObjectPtr(PROXY_BLUETOOTH_CALL)` 取对象与 `iface_cast<IBluetoothCall>`、`btSlotIdUnknown` 拨号标记、`BluetoothCallInterfaceCode` 码位收发、设备管理族 `AddAudioDevice`/`RemoveAudioDevice`/`GetCurrentCallList`/`ResetHearingAidDeviceList`）；SA 侧 `GetProxyObjectPtr` 入口随 call-manager-service delta REMOVED 蓝牙条删除。恢复条件：接入蓝牙 HFP 通话框架后按基线重建三件套。

### Requirement: 星闪客户端 NearlinkCallClient

**Reason**: AGENTS「功能范围」明确 liteOS 不支持星闪（NearLink）耳机设备连接；design D7 被删文件表 frameworks/native 行列出 `nearlink_call_client.cpp`。
**Migration**: 删除 `frameworks/native/src/nearlink_call_client.cpp` 与 `interfaces/innerkits/nearlink_call_client.h`（复用 `PROXY_BLUETOOTH_CALL` 通路，随蓝牙链消亡）。恢复条件：接入星闪通话框架后按基线重建。

### Requirement: 超级隐私客户端 SuperPrivacyManagerClient

**Reason**: AGENTS「功能范围」明确 liteOS 不支持超级隐私；design D7 被删文件表 frameworks/native 行列出 `super_privacy_manager_client.cpp`。
**Migration**: 删除 `frameworks/native/src/super_privacy_manager_client.cpp` 与 `interfaces/innerkits/super_privacy_manager_client.h`（`LoadSystemAbility(SUPER_PRIVACY_MANAGER_SA_ID=66102, LOAD_SA_TIMEOUT_SECONDS=4)`、`COMMAND_SET_SUPER_PRIVACY_MODE` 的 TF_SYNC 发送链、`ERR_INVALID_VALUE`/`ERR_INVALID_DATA` 失败分支）；services 侧超级隐私管理器删除见 call-object-management/call-control-management delta 对应条。恢复条件：接入超级隐私服务后按基线重建。

### Requirement: 手表移植预计移除面（native 层）

**Reason**: 该基线条目为移除预测的集中登记面，最终裁决已由本 delta 各 REMOVED/MODIFIED 条落实；其中 VOIP 代理与 `native_call_manager_hisysevent.cpp` 与基线预测不同——按 design D4（`VoipCallConnection` → `stub/voip_call_client` 桩）与 D7（两文件均未列入被删文件表）保留改桩，不删除。
**Migration**: 蓝牙通话链/星闪客户端/超级隐私客户端/`CALL_MANAGER_AUTO_START_OPTIMIZE` 块已由本 delta上述 REMOVED 条落实（基线预测与最终裁决一致）；`voip_call_manager_proxy.cpp` 删除但命令族经 `stub/voip_call_client` 桩保留（见本 delta MODIFIED「VoipCallManagerProxy 代理」条）；`native_call_manager_hisysevent.cpp` 保留、输出经维测桩日志（见本 delta MODIFIED「客户端维测与解码助手」条与 hisysevent-diagnostics delta）；`GetProxyObjectPtr(PROXY_BLUETOOTH_CALL)` 的 SA 侧裁剪口径在 call-manager-service delta 蓝牙条对齐（调用方清零成立）。恢复条件：无需恢复（登记面由各条目各自的恢复条件承载）。

## MODIFIED Requirements

### Requirement: CallManagerClient 延迟单例门面

系统 SHALL 由 `CallManagerClient`（`DECLARE_DELAYED_SINGLETON`，`interfaces/innerkits/call_manager_client.h` + `frameworks/native/src/call_manager_client.cpp`）保留延迟单例门面形态，但不再持有 `g_callManagerProxy`（`DelayedSingleton<CallManagerProxy>` 随 proxy 删除，本 delta REMOVED 条）：`Init(systemAbilityId)` SHALL 直接绑定 `DelayedSingleton<CallManagerService>` 进程内单例（design D2；形参保留、不再驱动 SA 连接），重复调用仅记日志不重复装配（幂等照抄）。全部保留的业务方法 SHALL 保持"服务指针为空判 + 直调转发"：`RegisterCallBack`/`UnRegisterCallBack`/`ObserverOnCallDetailsChange`/`DialCall`/`MakeCall`/`AnswerCall`/`RejectCall`/`HangUpCall`/`GetCallState`/`HoldCall`/`UnHoldCall`/`SwitchCall`/补充业务 Get/Set 簇/`StartRtt`/`StopRtt`/`PostDialProceed`/`SetMuted`/`MuteRinger`/`SetAudioDevice`/号码格式化转发/`InputDialerSpecialCode`/`RemoveMissedIncomingCallNotification`/`SetVoIPCallState`/`GetVoIPCallState`/`SetVoIPCallInfo`/`GetVoIPCallInfo`/`SendCallUiEvent`/`SendUssdResponse`/`IsNewCallAllowed` 等；未初始化时各方法返回 `TELEPHONY_ERR_UNINIT`（`HasCall` 返回 false，照抄）。会议族（`CombineConference`/`SeparateConference`/`KickOutFromConference`/会议列表）、视频族（`ControlCamera`/`SetPreviewWindow`/`SetDisplayWindow` 等）、蓝牙族（`RegisterBluetoothCallManagerCallbackPtr` 返回 nullptr 的例外分支）、`SetCallPolicyInfo`（EDM）与 OTT 上报族（`ReportOttCallDetailsInfo`/`ReportOttCallEventInfo`）方法随上游能力删除（call-manager-service delta 对应 REMOVED/MODIFIED 条）。`HasVoiceCapability` SHALL 保留本地实现：读系统参数 `const.telephony.voice.capable`（`KEY_VOICECALL_CAP`）改经 `stub/parameter_stub` 桩的 `GetParameter` 同名桩（design D6 系统参数行；值 "false" 即 false、默认 "true"，照抄）。

#### Scenario: 未初始化调用
- **WHEN** 未先 `Init` 即调用任一业务方法（如 `DialCall`）
- **THEN** 返回 `TELEPHONY_ERR_UNINIT` 且不触发服务转发（照抄）

#### Scenario: 重复初始化幂等
- **WHEN** `Init` 被再次调用
- **THEN** 服务单例已绑定时仅记日志，不重复装配（照抄基线幂等语义）

#### Scenario: 语音能力参数判定
- **WHEN** parameter 桩将 `const.telephony.voice.capable` 配置为 "false"
- **THEN** `HasVoiceCapability` 返回 false（照抄；桩默认 "true" 时返回 true）

测试落点：`test/unittest/call_manager_zero_gtest`（zero_branch 系）与 `test/unittest/ui_client`（`call_manager_connect` 系用例面）新增直调门面用例（未初始化/幂等/参数桩两态、删除方法族的负向断言）。

### Requirement: 应用上行回调注册链

系统 SHALL 由 `CallManagerClient::RegisterCallBack` 直调注册（无 proxy 层，本 delta REMOVED「CallManagerProxy 服务连接与死亡重建」条）：`registerStatus_` 防重保留（重复注册返回 `TELEPHONY_ERR_REGISTER_CALLBACK_FAIL`，照抄）；创建 `CallAbilityCallback`（`frameworks/native/src/call_ability_callback.cpp`）后直接向 `CallManagerService` 单例注册，成功后 `CallAbilityCallback::SetProcessCallback` 持住应用的 `CallManagerCallback`（照抄）；基线服务侧返回码向 `TELEPHONY_ERR_PERMISSION_ERR`/`TELEPHONY_ERR_ILLEGAL_USE_OF_SYSTEM_API` 的映射分支随权限校验移除消失（权限类错误不再产生），其余错误映射为 `TELEPHONY_ERR_REGISTER_CALLBACK_FAIL` 族保留（照抄）。`UnRegisterCallBack` 反向对称（照抄）。`CallAbilityCallback` 的 `callbackPtr_` 转发 SHALL 保留（基线 `mutex_` 保护删除、不设替代，design D8）：`OnCallDetailsChange`/`OnMeeTimeDetailsChange`/`OnCallEventChange`/`OnCallDisconnectedCause`/`OnReportAsyncResults`/`OnReportMmiCodeResult`/`OnReportAudioDeviceChange`/`OnReportPostDialDelay` 逐个转发、空回调返回 `TELEPHONY_SUCCESS`（照抄）；视频媒体面与 OTT 转发（`OnReportImsCallModeChange`/`OnReportCallSessionEventChange`/`OnReportPeerDimensionsChange` 等及 `OnOttCallRequest`）随视频通话/OTT 类型通话删除（AGENTS「功能范围」；上游多播删除见 call-report delta「事件与结果多播族」条）。

#### Scenario: 注册成功
- **WHEN** 直调注册成功（liteOS 无权限校验前置）
- **THEN** `registerStatus_` 置 true，后续状态变化经 `CallAbilityCallback` 直调转发到应用回调（照抄）

#### Scenario: 未注册时状态上报丢弃
- **WHEN** `CallAbilityCallback` 收到上报但 callbackPtr_ 为空
- **THEN** 记为成功且不向应用分发（照抄）

测试落点：`test/unittest/call_manager_zero_gtest`（zero_branch 系）新增注册链用例（防重、错误映射、空回调丢弃、视频/OTT 转发删除负向断言）。

### Requirement: CallAbilityCallbackStub 服务端上行解包入口

系统 SHALL 将 `CallAbilityCallbackStub`（`frameworks/native/src/call_ability_callback_stub.cpp`）收敛为直调薄入口（design D3：`CallAbilityCallbackStub` 收敛为直调回调对象的薄入口，应用侧注册的回调由服务直接持有对象指针调用）：基线构造函数的 `CallManagerCallAbilityInterfaceCode` 家族（`UPDATE_CALL_STATE_INFO`/`UPDATE_MEETIME_STATE_INFO`/`UPDATE_CALL_EVENT`/`UPDATE_CALL_DISCONNECTED_CAUSE`/`UPDATE_CALL_ASYNC_RESULT_REQUEST`/`REPORT_OTT_CALL_REQUEST`/`UPDATE_MMI_CODE_RESULT_REQUEST`/`UPDATE_AUDIO_DEVICE_CHANGE_RESULT_REQUEST`/`REPORT_POST_DIAL_DELAY`/`UPDATE_IMS_CALL_MODE_RECEIVE`/`CALL_SESSION_EVENT_CHANGE`/`PEERD_DIMENSIONS_CHANGE`/`CALL_DATA_USAGE_CHANGE`/`CAMERA_CAPABILITIES_CHANGE`/`UPDATE_PHONE_STATE`，`interfaces/innerkits/call_ability_callback_ipc_interface_code.h`）`memberFuncMap_` 注册与 `OnRemoteRequest` 分发不迁移，枚举值原样保留为 ABI 约定（design D3，需人工复核：后续恢复系统形态须保证枚举值与基线一致）；`OnUpdateCallStateInfo`/`OnUpdateMeeTimeStateInfo` 的 `NativeCallManagerUtils::ReadCallAttributeInfo` parcel 解包复用、`OnUpdateCallEvent` 的 `MAX_LEN=100000` 边界检查与 `ReadRawData`、`OnUpdateAysncResults` 的 PacMap 组装（结构体替换，design D5）均改为结构体直传的直调转发（不经 parcel，长度守卫随之不迁移）。

#### Scenario: 描述符不匹配
- **WHEN** 基线请求 parcel 的接口令牌与 `CallAbilityCallbackStub::GetDescriptor()` 不符
- **THEN** 因 IPC 传输层删除（design D3），描述符校验与 `TELEPHONY_ERR_DESCRIPTOR_MISMATCH` 分支不迁移；场景改写为负向断言（直调薄入口无该校验态）

#### Scenario: 长度越界防护
- **WHEN** 基线 `OnUpdateCallEvent` 读到的 len <= 0 或 >= MAX_LEN
- **THEN** 因 `ReadRawData` 解包删除，parcel 长度守卫与 `TELEPHONY_ERR_ARGUMENT_INVALID` 该分支不迁移；场景改写为负向断言（`CallEventInfo` 以结构体引用直传、不经长度检查）

测试落点：`test/unittest/call_manager_zero_gtest`（zero_branch 系，含 `zero_branch5_test.cpp`/`zero_branch8_test.cpp` 的 callback 用例面）新增直调薄入口转发矩阵用例与 IPC 守卫删除负向断言。

### Requirement: VoipCallManagerProxy 代理

系统 SHALL 将基线 `VoipCallManagerProxy`（`IRemoteProxy<IVoipCallManagerService>`，`frameworks/native/src/voip_call_manager_proxy.cpp`）的 IPC 代理删除、命令族出口改 `stub/voip_call_client` 桩（`VoipCallClient::GetInstance().Xxx()`，design D4 新增桩；VoIP 类型通话暂不支持但对 voip_call_manager 的注册/控制/事件出口保留，AGENTS「暂不支持 VOIP……依赖后续跟 meetime 畅连通话」）：命令族含 `INTERFACE_REPORT_INCOMING_CALL`/`INTERFACE_REPORT_INCOMING_CALL_ERROR`/`INTERFACE_REPORT_CALL_STATE_CHANGE`/`INTERFACE_REPORT_OUTGOING_CALL`/`INTERFACE_REGISTER_CALLBACK`/`INTERFACE_UN_REGISTER_CALLBACK`/`INTERFACE_REPORT_VOIP_INCOMING_CALL`/`INTERFACE_REPORT_VOIP_CALL_EXTENSIONID`/`INTERFACE_ANSWER_VOIP_CALL`/`INTERFACE_HANGUP_VOIP_CALL`/`INTERFACE_REJECT_VOIP_CALL`/`INTERFACE_REGISTER_CALL_MANAGER_CALLBACK`/`INTERFACE_UNREGISTER_CALL_MANAGER_CALLBACK`/`INTERFACE_UNLOAD_VOIP_SA`/`INTERFACE_SEND_CALL_UI_EVENT`/`INTERFACE_REPORT_CALL_AUDIO_EVENT_CHANGE`/`INTERFACE_SEND_CALL_UI_EVENT_FOR_WINDOW`（命令码定义于 `interfaces/innerkits/i_voip_call_manager_service.h`，保留）；基线 `AppExecFwk::PacMap` 键入参（callId/voipCallType/userName/abilityName/voipCallState/showBannerForIncomingCall/isConferenceCall/isVoiceAnswerSupported/startReportTime 等）与 `VoipCallEventInfo` SHALL 按 design D5 换普通结构体；`ReportIncomingCall`/`ReportOutgoingCall` 的 result + `ErrorReason` 双返回值语义保留（桩返回结构透传）；基线 `OHOS::HiviewDFX::HiTraceChain` 开链改日志打印（design D5 hitrace→日志）；失败路径 SHALL 保留 `NativeCallManagerHisysevent::WriteVoipCallEvent` 维测（经维测桩日志，hisysevent-diagnostics delta 同名条）——桩默认不可用（等价基线 `Remote()` 为空分支）时报 `Scenario::VOIP_PROXY_IPC_CONNECTTING` 错误。

#### Scenario: 呼入报告
- **WHEN** 调 `ReportIncomingCall(extras, userProfile, reason)`（结构体入参）
- **THEN** 桩配置可用时逐项透传（extras 结构体字段 + userProfile 向量），result 与 ErrorReason 双返回值透传（照抄语义）

#### Scenario: 对端缺失打维测
- **WHEN** voip 桩处于默认不可用态（等价基线 Remote() 为空）
- **THEN** 向 `NativeCallManagerHisysevent::WriteVoipCallEvent` 报 Scenario::VOIP_PROXY_IPC_CONNECTTING 错误（经维测桩日志，照抄）

测试落点：`test/unittest/call_manager_zero_gtest`（zero_branch 系）新增 voip 桩两态命令族矩阵用例（双返回值透传、失败维测断言、结构体入参字段矩阵）。

### Requirement: 客户端维测与解码助手

系统 SHALL 保留 `NativeCallManagerHisysevent`（`frameworks/native/include/native_call_manager_hisysevent.h` + `frameworks/native/src/native_call_manager_hisysevent.cpp`）：`WriteVoipCallEvent(callId, bundleName, scenario, errorCode, msg, ...)` 输出改经 `stub/hisysevent_stub` 桩日志（签名不变，design D5；调用点为 voip 桩失败路径，见本 delta MODIFIED「VoipCallManagerProxy 代理」条；详细行为见 hisysevent-diagnostics delta 同名条）。`NativeCallManagerUtils`（`frameworks/native/include/native_call_manager_utils.h` + `native_call_manager_utils.cpp`）文件保留（design D7 未列入被删文件表）：`ReadCallAttributeInfo(MessageParcel&)` 的 parcel 反序列化实现保留为兼容入口——liteOS 无 IPC 传输层且 `CallAbilityCallbackStub` 收敛为直调薄入口后无调用可达（结构体直传），供后续恢复 IPC 形态时复用（登需人工复核）。

#### Scenario: 属性回读
- **WHEN** 基线 `CallAbilityCallbackStub::OnUpdateCallStateInfo` 收到 parcel 包
- **THEN** liteOS 直调形态下 `CallAttributeInfo` 以结构体直传、不经 `NativeCallManagerUtils::ReadCallAttributeInfo` 反序列化；场景改写为直调结构体直达断言（函数保留为无调用的兼容入口）

#### Scenario: VOIP IPC 异常上报
- **WHEN** voip 桩任一调用不可用或返回值非 0
- **THEN** `WriteVoipCallEvent` 记录对应 Scenario 与 errorCode（经维测桩日志，照抄）

测试落点：`test/unittest/call_manager_zero_gtest`（zero_branch 系）新增维测助手与解码助手保留性用例（`WriteVoipCallEvent` 字段断言、`ReadCallAttributeInfo` 兼容入口无调用断言）。
