# Spec Delta

## REMOVED Requirements

### Requirement: 客户端延迟拉起优化（CALL_MANAGER_AUTO_START_OPTIMIZE）

**Reason**: `CALL_MANAGER_AUTO_START_OPTIMIZE` 属 AGENTS「特性宏支持范围-不支持」清单；design D7 不支持宏表裁决"客户端 autostart 守卫块与 proxy 一并删除（随 D2/D3）"；该路径整体服务于 SA 按需启动生命周期，liteOS 无 SystemAbility/samgr（design D2），广播订阅出口亦属 AGENTS「暂不调用」的公共事件面。
**Migration**: `frameworks/native/src/call_manager_proxy.cpp/.h` 的 `#ifdef CALL_MANAGER_AUTO_START_OPTIMIZE` 守卫块（`IsServiceStart` 的 `CheckSystemAbility` 探测、`CallManagerProxySubcribed` 对 `COMMON_EVENT_RADIO_STATE_CHANGE` 的订阅与 `OnReceiveEvent` 补注册链、`ConnectService` 后消费暂存回调、`SetInitState(true)`、退订、`callBack_` 暂存成员）随 `call_manager_proxy.cpp` 整体删除（design D7 被删文件表 frameworks/native 行；native-client-api delta 同名 REMOVED 条）；`sa_profile/4005_auto_start_optimize.json` 随 sa_profile 整目录不迁移（design D10）。liteOS 上 `CallManagerClient::Init` 直取 `CallManagerService` 进程内单例（design D2），无"SA 未启动"态，订阅拉起链无可达场景。恢复条件：恢复 SA 按需启动形态时按基线重建守卫块与配套 sa_profile。

### Requirement: 接口权限校验（集中）

**Reason**: AGENTS「以下接口不调用」明确 liteOS 上 callmanager 提供的外部接口暂不需要进行权限校验，权限校验接口暂不调用；design 决策 11 权限校验整体移除；属安全面弱化，design Risks 已标注需人工复核。
**Migration**: 删除 `call_manager_service.cpp` 各转发入口的 `TelephonyPermission::CheckCallerIsSystemApp`/`CheckPermission` 校验块与权限常量分组（`ohos.permission.SET_TELEPHONY_STATE`/`GET_TELEPHONY_STATE`/`PLACE_CALL`/`ANSWER_CALL`/`READ_CALL_LOG`/`WRITE_CALL_LOG`），全部接口直接转发内部管理者；`TELEPHONY_ERR_ILLEGAL_USE_OF_SYSTEM_API`/`TELEPHONY_ERR_PERMISSION_ERR` 的权限类返回路径不再产生（错误码枚举值本身保留）；`DialCall` 缺 `PLACE_CALL` 时 `WriteDialCallFaultEvent` 记权限错误的分支随校验块删除（拨号失败故障记录保留于本 delta MODIFIED「DialCall 拨号转发与语音信箱计数清零」条）；`SetPreviewWindow` 的 `PrivacyKit` 相机权限维护随视频面删除（见本 delta REMOVED「视频通话控制转发」条）。恢复条件：目标平台接入 access_token 系权限框架后按基线分组规则重建校验链。

### Requirement: IPC 分发表（CallManagerServiceStub）

**Reason**: AGENTS 明确 liteOS 中 callmanager 不继承 SystemAbility 也不实现 IPC 调用；design D2 裁决 `CallManagerServiceStub` 的 IPC 分发表不迁移、D3 删除 `call_manager_service_stub.cpp`；`HICOLLIE_ENABLE` 属不支持宏且唯一场点在该文件（design D7），随文件消亡。
**Migration**: 删除 `services/call_manager_service/src/call_manager_service_stub.cpp/.h`（`InitCallBasicRequest`/`InitCallUtilsRequest`/`InitCallConferenceRequest`/`InitCallDtmfRequest`/`InitCallSupplementRequest`/`initCallConferenceExRequest`/`InitCallMultimediaRequest`/`InitImsServiceRequest`/`InitOttServiceRequest`/`InitVoipOperationRequest`/`InitBluetoothOperationRequest` 与 `INTERFACE_GET_PROXY_OBJECT_PTR` 直填项的 `memberFuncMap_` 构建、`OnRemoteRequest` 描述符比对与查表分发、`SetTimer`/`CancelTimer` XCollie 计时（`XCOLLIE_TIMEOUT_SECONDS=30`）、`OnReportOttCallDetailsInfo` 的 `(0, MAX_CALLS_NUM=5]` 计数守卫均不迁移）并同步 `callmanager.gni`；客户端直调后各接口经 `frameworks/native/include/i_call_manager_service.h` 接口头直接调用（接口头保留，design D3）；`CallManagerInterfaceCode` 枚举值原样保留作为 ABI 约定、不再承载实际 IPC（design D3，需人工复核：后续恢复系统形态须保证枚举值与基线一致）。恢复条件：恢复 IPC 形态时按基线重建分发表、描述符校验与解包守卫。

### Requirement: 会议通话转发（集中）

**Reason**: AGENTS「功能范围」明确 liteOS 不支持会议通话，相关代码无需迁移；design D7 被删文件表列出 `conference_base.cpp`/`cs_conference.cpp`/`ims_conference.cpp`/`ott_conference.cpp`。
**Migration**: 删除 `CallManagerService` 的会议类转发分支（`CombineConference`/`SeparateConference`/`KickOutFromConference`/`JoinConference`/`GetMainCallId`/`GetSubCallIdList`/`GetCallIdListForConference`）及指针空时清空输出列表的降级路径；会议对象族与控制面删除见 call-object-management/call-control-management delta REMOVED 条，cellular_call 侧会议转发分支删除见 telephony-interaction delta「会议、视频与 RTT 下行出口」条；`CallManagerInterfaceCode` 中会议相关码位随枚举整体保留（ABI 约定，design D3）。恢复条件：支持会议通话后按基线重建转发面与会议对象族。

### Requirement: 视频通话控制转发（VideoControlManager）

**Reason**: AGENTS「功能范围」明确 liteOS 不支持视频通话，`ABILITY_CAMERA_SUPPORT` 恒关（「特性宏支持范围-不支持」）；design D7 被删文件表列出 `services/video/src/video_control_manager.cpp` 与 `video_call_state.cpp`。
**Migration**: 删除 `CallManagerService` 的视频面转发分支（`ControlCamera`/`SetPreviewWindow`/`SetDisplayWindow`/`SetPausePicture`/`SetDeviceDirection`/`SetCameraZoom`/`UpdateImsCallMode`/`CancelCallUpgrade`/`RequestCameraCapabilities`）及 `SetPreviewWindow` 的 `PrivacyKit`（"ohos.permission.CAMERA"）授权维护；视频对象族与媒体面上行删除见 call-object-management/telephony-interaction delta 对应条；`CallManagerInterfaceCode` 中视频相关码位随枚举整体保留（ABI 约定，design D3）。恢复条件：接入 camera 框架与视频通话后按基线重建。

### Requirement: 蓝牙通话代理与回调注册（集中）

**Reason**: AGENTS「功能范围」明确 liteOS 不支持 BLUETOOTH 类型通话，`ABILITY_BLUETOOTH_SUPPORT` 属不支持宏；design D7 被删文件表列出 `services/bluetooth/` 全目录与 `services/telephony_interaction/src/bluetooth_call_connection.cpp`。
**Migration**: 删除 `CallManagerService` 的 `GetProxyObjectPtr(proxyType)` 入口与 `proxyObjectPtrMap_` 缓存（`PROXY_BLUETOOTH_CALL` 惰性创建 `BluetoothCallService` 链）、`RegisterBluetoothCallManagerCallbackPtr(macAddress)`（`bluetoothCallCallbackLock_`/`bluetoothCallCallbackPtr_` 成员、`Bluetooth::HandsFreeUnit::GetProfile()->RegisterObserver` 注册 `BluetoothCallState` 观察者、`BluetoothCallConnection::SetMacAddress`）；`UnInit` 中的蓝牙回调清理随成员删除（见本 delta MODIFIED「SystemAbility 注册与按需启动生命周期」条）；调用方 `BluetoothCallClient`/`NearlinkCallClient` 随 native-client-api delta REMOVED 条删除。恢复条件：接入蓝牙 HFP 通话框架后按基线重建代理与回调注册链。

### Requirement: EDM 呼叫管控策略

**Reason**: AGENTS「功能范围」明确 liteOS 不支持 EDM 企业禁拨；design D7 被删文件表列出 `utils/src/edm_call_policy.cpp`。
**Migration**: 删除 `CallManagerService::SetCallPolicyInfo(isDialingTrustlist, dialingList, isIncomingTrustlist, incomingList)` 入口、`EDM_UID=3057` 的 `IPCSkeleton::GetCallingUid` 判定与 `CallControlManager::SetEdmPolicy` 转发链（EDM 策略工具面删除见 call-utils delta 对应条）；恢复条件：接入 EDM 管控框架后按基线重建入口与 uid 判定。

## MODIFIED Requirements

### Requirement: SystemAbility 注册与按需启动生命周期

系统 SHALL 以 `DelayedSingleton<CallManagerService>` 进程内单例提供 `CallManagerService`（`services/call_manager_service/src/call_manager_service.cpp`），不再继承 `SystemAbility`、无 `SystemAbility::MakeAndRegisterAbility` 静态注册（`g_registerResult`）与 `SystemAbility(TELEPHONY_CALL_MANAGER_SYS_ABILITY_ID, true)` 按需启动声明（design D2 删 SA 装饰）；`OnStart()`/`OnStop()` SHALL 保留为进程内生命周期入口，由 `CallManagerClient::Init` 直取单例时驱动（design D2）。`OnStart()` SHALL 保留幂等语义（`state_` 已为 `STATE_RUNNING` 直接返回）与启动耗时 `spendTime_` 记录（供 `GetStartServiceSpent()`，`GetBindTime()` 每次调用刷新时间戳的行为照抄，design D9 行为保持）；基线 `Init()` 成功后的 `SystemAbility::Publish` 改为本地注册（进入 `STATE_RUNNING` 即视为服务就绪，客户端可绑定）。`OnStop()` SHALL 将 `state_` 置 `STATE_STOPPED` 并调用 `UnInit()`。`UnInit()` SHALL 保留次序：`CellularCallConnection::UnInit()` → `CallControlManager::UnInit()` → 置空 `callControlManagerPtr_`；基线 `bluetoothCallCallbackLock_` 下置空 `bluetoothCallCallbackPtr_` 的清理随蓝牙成员删除（本 delta REMOVED 蓝牙条）。基线 `lock_`/`bluetoothCallCallbackLock_` 锁保护删除、不设替代（design D6 锁行、D8 单线程）。`OnStart()` 末尾的 `LocationSubscriber::Subscriber()` 随地震预警删除（AGENTS「功能范围」；design D7 `call_earthquake_alarm_subscriber.cpp` 删除）。`Dump()`/`GetBindTime()`/`GetServiceRunningState()` 自描述接口保留（Dump 行为见 hisysevent-diagnostics delta）。

#### Scenario: 重复 OnStart 幂等
- **WHEN** 客户端在 `state_ == STATE_RUNNING` 时再次触发生命周期入口（重复 `Init` 驱动 `OnStart()`）
- **THEN** 直接返回，不再次执行 `Init()`/本地注册（照抄基线幂等语义）

#### Scenario: Init 失败不发布
- **WHEN** `CallManagerService::Init()` 依赖的 `CallControlManager::Init()` 返回 false
- **THEN** `OnStart()` 记录 "init failed" 日志后返回，服务不进入 `STATE_RUNNING`（基线"SA 不 Publish"分支的进程内等价），`state_` 保持 `STATE_STOPPED`，客户端侧后续业务调用返回指针空类错误

#### Scenario: OnStop 后状态查询
- **WHEN** `OnStop()` 完成
- **THEN** `GetServiceRunningState()` 返回 `STATE_STOPPED`（0），`CellularCallConnection` 已 `UnInit()`（照抄）

测试落点：`test/unittest/call_manager_zero_gtest`（zero_branch 系）新增生命周期用例（幂等、Init 失败不进入 RUNNING、OnStop 状态复位与 UnInit 次序断言）。

### Requirement: Init 装配次序与依赖 SA 事件监听

系统 SHALL 在 `CallManagerService::Init()` 内保留固定装配次序：宏 `OHOS_BUILD_ENABLE_TELEPHONY_CUST` 打开时先执行 `TELEPHONY_CUST_WRAPPER` 初始化（内部改经 `stub/telephony_cust_client` 桩，见本 delta MODIFIED「TelephonyCustWrapper 动态库加载」条）；随后 `CallControlManager::Init()`（失败即整体失败）、缓存 `callControlManagerPtr_`（空即失败）、`ReportCallInfoHandler::Init()`、`CellularCallConnection::Init(TELEPHONY_CELLULAR_CALL_SYS_ABILITY_ID)`（SA id 常量平移、连接改驱动 `stub/cellular_call_client` 桩，design D4）、`CallRecordsManager::Init()`。基线 `BluetoothConnection::Init()`/`DistributedCallManager::Init()`/`DistributedCommunicationManager::Init()` 三项随蓝牙/分布式删除（AGENTS「功能范围」；design D7）。基线 `AddSystemAbilityListener(AUDIO_POLICY_SERVICE_ID)`/`AddSystemAbilityListener(DISTRIBUTED_HARDWARE_DEVICEMANAGER_SA_ID)` 与 `OnAddSystemAbility()` 按 SA id 分发不迁移（无 samgr，design D2）；`AUDIO_POLICY_SERVICE_ID` 分支的 `AudioProxy` 三个回调注册调用点（`SetAudioMicStateChangeCallback`/`SetAudioDeviceChangeCallback`/`SetAudioPreferDeviceChangeCallback`）SHALL 保留并移入装配路径执行，其内部 audio_framework 调用按 `// todo!!! [audio] ref to audio_proxy.cpp <函数>` 占位（design D6 音频行；`AudioProxy` 本体见 audio-device-management delta）；`DISTRIBUTED_HARDWARE_DEVICEMANAGER_SA_ID` 分支的 `InteroperableDeviceObserver::Init()` 随互信互联删除（design D7）。

#### Scenario: 音频策略 SA 上线
- **WHEN** 服务装配执行到音频回调注册调用点（基线 `OnAddSystemAbility(AUDIO_POLICY_SERVICE_ID)` 场景的进程内等价，liteOS 无 SA 上线回调）
- **THEN** `AudioProxy` 三个回调注册调用（麦克风状态、音频设备变化、偏好设备变化）被触发，内部 audio_framework 调用经 `[audio]` todo 桩占位（桩面可断言调用点到达）

#### Scenario: 依赖服务装配失败的传播
- **WHEN** `DelayedSingleton<CallControlManager>::GetInstance()->Init()` 失败
- **THEN** `Init()` 返回 false，服务不进入 `STATE_RUNNING`（基线"不发布 SA"的进程内等价，照抄传播语义）

测试落点：`test/unittest/call_manager_zero_gtest`（zero_branch 系）新增装配次序与失败传播用例、音频回调注册调用点断言（经 `[audio]` todo 桩）。

### Requirement: TelephonyCustWrapper 动态库加载（OHOS_BUILD_ENABLE_TELEPHONY_CUST）

系统 SHALL 在宏 `OHOS_BUILD_ENABLE_TELEPHONY_CUST` 打开时（宏守卫保留，design D7 支持宏表）由 `TELEPHONY_CUST_WRAPPER`（`services/call_manager_service/src/telephony_cust_wrapper.cpp`，`DelayedRefSingleton<TelephonyCustWrapper>` 形态保留）提供定制判定：不再 `dlopen("libtelephony_cust_api.z.so")`/`dlsym`/`dlclose`（AGENTS：与 TelephonyCust 模块通信改 `TelephonyCustClient::GetInstance().Xxx()` 桩；design D4），`IsHideViolenceOrEmcNumbersInCallLog`（`bool(const CallAttributeInfo&)`，供 `call_records_manager.cpp` 判断是否在通话记录中隐藏暴力/紧急号码）与 `IsChangeDialNumberToTwEmc`（`bool(std::u16string&, int32_t)`，供 `DialCall()` 修改特殊号码）两个判定 SHALL 改经 `stub/telephony_cust_client` 桩的同名接口，函数签名与调用点判空习惯保持基线形态；桩默认返回不可用（等价基线 dlopen 失败函数指针为空、调用方跳过判定分支），测试可配置桩返回值（design Risks）。

#### Scenario: 定制库不存在
- **WHEN** `stub/telephony_cust_client` 桩处于默认不可用态（等价基线 `libtelephony_cust_api.z.so` 缺失、`dlopen` 返回空）
- **THEN** 两个判定按"不可用"处理，`DialCall()` 跳过号码改写分支、通话记录不隐藏暴力/紧急号码（照抄基线判空跳过语义）

#### Scenario: 拨号命中定制改号
- **WHEN** 桩 `IsChangeDialNumberToTwEmc_(number, slotId)` 返回 true
- **THEN** `DialCall()` 打 "changed dial num to tw emc" 日志后继续正常拨号流程（照抄）

测试落点：`test/unittest/call_manager_special_test`（special_branch 系）扩展 TelephonyCust 两判定的桩返回值矩阵用例（默认不可用跳过、命中改号继续拨号）。

### Requirement: 上层回调注册与解除

系统 SHALL 由 `CallManagerService::RegisterCallBack()`/`UnRegisterCallBack()`/`ObserverOnCallDetailsChange()` 承接应用的观察者接入（权限校验整体移除，本 delta REMOVED「接口权限校验」条）：`RegisterCallBack` 把回调连同 `GetBundleInfo()` 结果交给 `CallAbilityReportProxy::RegisterCallBack`（直调登记、无 DeathRecipient 挂接，见 call-report delta）；`UnRegisterCallBack` 按 bundleInfo 移除；`ObserverOnCallDetailsChange()` 遍历 `CallObjectManager::GetAllCallInfoList()` 对每个 `CallAttributeInfo` 定向上报。`GetBundleInfo()` SHALL 保留 bundleInfo 拼装语义（格式 bundleName:pid）：基线 `IPCSkeleton::GetCallingUid`/`GetCallingPid` 随 IPC 层删除（单进程直调，取本进程标识）；`TelephonyPermission::GetBundleNameByUid(uid, bundleName)` 的 bundleName 反查属 ability 查询调用点，SHALL 以 todo 占位桩化（同 getBundleInfo 处置，design D6 ability 查询类；反查失败回退为 uid+pid 拼接照抄）。

#### Scenario: 注册成功
- **WHEN** 应用调用 `RegisterCallBack(callback)`（liteOS 无权限校验与系统应用判定）
- **THEN** `CallAbilityReportProxy` 登记回调（单进程直持回调对象，无 DeathRecipient），返回 `TELEPHONY_SUCCESS`

#### Scenario: 观察详情变更补报
- **WHEN** 调用 `ObserverOnCallDetailsChange()`
- **THEN** 当前全部通话属性按注册时的 bundleInfo 定向逐条上报（照抄，无权限前置）

测试落点：`test/unittest/call_manager_zero_gtest`（zero_branch 系）新增注册/解除/补报直调用例与 `GetBundleInfo` 回退拼接断言（ability 反查 todo 桩默认失败态）。

### Requirement: DialCall 拨号转发与语音信箱计数清零

系统 SHALL 由 `CallManagerService::DialCall()`（`call_manager_service.cpp`）执行拨号前置处理并转发 `CallControlManager::DialCall`：先 `CallManagerHisysevent::SetDialStartTime()`（维测经桩日志输出，design D5）；基线 `StartAsyncTrace(HITRACE_TAG_OHOS, "DialCall")`/`FinishAsyncTrace` hitrace 改日志打印（design D5）；extras 的 "bundleName" 键写入保留（bundleName 反查经 ability 查询 todo 桩，见本 delta MODIFIED「上层回调注册与解除」条；`AppExecFwk::PacMap` 按 design D5 换普通结构体）；`PLACE_CALL` 校验块删除（权限整体移除）；宏 `OHOS_BUILD_ENABLE_TELEPHONY_CUST` 判空调用 `isChangeDialNumberToTwEmc_` 保留（改经 TelephonyCust 桩）；转发成功且号码等于 `CoreManagerInner::GetVoiceMailNumber(slotId)` 时调用 `SetVoiceMailCount(slotId, CLEAR_VOICE_MAIL_COUNT=0)` 清计数——两出口 SHALL 经 `stub/core_service_client` 桩（`CoreServiceClient::GetInstance().Xxx()`，design D4），清零语义照抄；转发失败 `GetErrorDescription` 后 `WriteDialCallFaultEvent`（经维测桩日志）；`callControlManagerPtr_` 为空返回 `TELEPHONY_ERR_LOCAL_PTR_NULL`。基线 extras 带 `btSlotIdUnknown` 时走 `BtCallWaitSlotId()`（`InteroperableCommunicationManager::GetBtCallSlotId` + `CoreServiceClient::HasSimCard` 补写 "accountId"）的分支随蓝牙/互信互联删除（AGENTS「功能范围」；design D7），liteOS 上 extras 不含该标记、分支不可达。

#### Scenario: 拨打语音信箱号码
- **WHEN** `DialCall` 成功且被叫号码与 `CoreServiceClient` 桩返回的 `GetVoiceMailNumber(slotId)` 相同（示例号码以 unknown 占位）
- **THEN** `SetVoiceMailCount(slotId, CLEAR_VOICE_MAIL_COUNT=0)` 经 core_service 桩被调用（清零语义照抄）

#### Scenario: 拨号失败故障记录
- **WHEN** `CallControlManager::DialCall` 返回非 0
- **THEN** 按 `GetErrorDescription(ret)` 描述经维测桩日志输出 CALL_DIAL_FAILED 故障事件并记 hitrace 替代日志（照抄）

#### Scenario: 蓝牙回拨槽位未知
- **WHEN** 基线 extras 中 `btSlotIdUnknown` 为真的拨号请求到达
- **THEN** 因 BLUETOOTH 类型通话与互信互联删除（AGENTS），`BtCallWaitSlotId` 补写 accountId 的分支不迁移；liteOS 上该标记不存在，场景改写为负向断言（分支不可达、extras 不含 btSlotIdUnknown 键）

测试落点：`test/unittest/call_manager_zero_gtest`（zero_branch 系）与 `test/unittest/call_manager_gtest`（`call_manager2_gtest`）新增 DialCall 前置链用例（语音信箱清零经桩断言、失败故障维测桩断言、btSlotIdUnknown 分支删除负向断言）。

### Requirement: MakeCall 拉起拨号前编辑页

系统 SHALL 由 `CallManagerService::MakeCall()` 保留拉起拨号前编辑页语义：构造指向 `com.ohos.contacts` `MainAbility` 的 Want（参数 phoneNumber 与 `pageFlag=page_flag_edit_before_calling`，照抄），基线 `AAFwk::AbilityManagerClient::StartAbility` 调用点属拉起 ability 类外部依赖，SHALL 经 stub 打桩并在调用点以 todo 占位（`// todo!!! [callUi] ref to call_manager_service.cpp MakeCall`，AGENTS「拉起通话界面……对应外部依赖接口通过打桩实现」；design D6 拉起通话界面行）；桩返回失败时 `MakeCall` 返回 `TELEPHONY_ERR_UNINIT` 照抄。基线 `IPCSkeleton::ResetCallingIdentity`/`SetCallingIdentity` 身份切换随 IPC 层删除（单进程直调）；系统应用校验删除（权限整体移除）。

#### Scenario: 拉起联系人编辑页成功
- **WHEN** 调用 `MakeCall(unknown)` 且 `[callUi]` 桩配置为成功
- **THEN** Want 参数照抄（phoneNumber、page_flag_edit_before_calling）经桩发起拉起，返回 `TELEPHONY_SUCCESS`

#### Scenario: 拉起失败
- **WHEN** `[callUi]` 桩返回错误（默认不可用态）
- **THEN** `MakeCall` 返回 `TELEPHONY_ERR_UNINIT`（照抄）

测试落点：`test/unittest/call_manager_zero_gtest`（zero_branch 系）新增 MakeCall 两态用例（桩成功/失败、`[callUi]` todo 标签断言）。

### Requirement: 通话控制转发（应答/挂断/保持/切换）

系统 SHALL 将控制类接口原样转发 `CallControlManager`（权限校验整体移除，本 delta REMOVED「接口权限校验」条）：`AnswerCall`（`SetAnswerStartTime()` 后转发 `AnswerCall(callId, videoState)`）、`RejectCall`（转发 `RejectCall(callId, rejectWithMessage, textMessage)`）、`HangUpCall`（转发 `HangUpCall(callId)`）、`HoldCall`/`UnHoldCall`/`SwitchCall`、`GetCallState()`。`callControlManagerPtr_` 为空时统一返回 `TELEPHONY_ERR_LOCAL_PTR_NULL`（照抄）。

#### Scenario: 应答开始计时
- **WHEN** `AnswerCall()` 被调用（liteOS 无权限前置）
- **THEN** `SetAnswerStartTime()` 记录起始时间后转发 `CallControlManager::AnswerCall`（照抄）

#### Scenario: 权限二选一通过（RejectCall）
- **WHEN** 调用者调用 `RejectCall`（基线持 SET_TELEPHONY_STATE 单权限通过的场景）
- **THEN** 权限校验整体移除后调用直接转发 `CallControlManager::RejectCall`，不再产生 `TELEPHONY_ERR_PERMISSION_ERR`/`TELEPHONY_ERR_ILLEGAL_USE_OF_SYSTEM_API` 权限类返回（场景改写为直转发的负向断言）

测试落点：`test/unittest/call_manager_zero_gtest`（zero_branch 系）新增控制面转发矩阵与指针空降级用例。

### Requirement: 麦克风静音与音频设备转发

系统 SHALL 由 `CallManagerService` 转发音频面接口（权限校验整体移除）：`SetMuted` 转发 `CallControlManager::SetMuted`；基线成功后联动 `DistributedCommunicationManager::SetMuted` 与 `InteroperableCommunicationManager::SetMuted` 的两处联动随分布式/互信互联删除（AGENTS「功能范围」；design D7）；`MuteRinger` 转发保留、同样两处联动删除，基线宏 `SUPPORT_MUTE_BY_DATABASE` 打开时调用 `InteroperableSettingsHandler::SendMuteRinger()` 持久化静音标记的守卫块删除（不支持宏，design D7；`interoperable_settings_handler.cpp` 随互信互联删除）；`SetAudioDevice` 转发失败返回 `CALL_ERR_SETTING_AUDIO_DEVICE_FAILED`（照抄）；`ReportAudioDeviceInfo` 以 `DEVICE_UNKNOWN` 音频设备调用 `AudioDeviceManager::ReportAudioDeviceChange`（照抄）。

#### Scenario: 静音状态联动
- **WHEN** `SetMuted(true)` 转发返回 `TELEPHONY_SUCCESS`
- **THEN** 仅本地 `CallControlManager::SetMuted` 生效；分布式与互通两个通信管理器的联动删除（AGENTS），场景改写为负向断言（无联动调用可达）

#### Scenario: 数据库静音标记（SUPPORT_MUTE_BY_DATABASE）
- **WHEN** 基线宏打开且 `MuteRinger()` 成功的路径
- **THEN** 宏与守卫块删除（design D7 不支持宏表），`InteroperableSettingsHandler::SendMuteRinger()` 随互信互联删除，该持久化分支不迁移（场景改写为负向断言）

#### Scenario: 设置音频设备失败
- **WHEN** `CallControlManager::SetAudioDevice` 返回非 0
- **THEN** 门面返回 `CALL_ERR_SETTING_AUDIO_DEVICE_FAILED`（照抄）

测试落点：`test/unittest/call_manager_zero_gtest`（zero_branch 系）新增静音/振铃静音/音频设备转发用例与联动删除负向断言。

### Requirement: 补充业务与 USSD 设置转发

系统 SHALL 由 `CallManagerService` 将 SET 类接口转发 `CallControlManager`（权限校验整体移除；补充业务 UT/USSI/USSD/MMI 功能须支持，AGENTS「特性宏支持范围」说明 1）：`GetCallWaiting`/`CanSetCallTransferTime`/`GetCallRestriction`/`GetCallTransferInfo` 与 `SetCallWaiting`/`SetCallRestriction`/`SetCallRestrictionPassword`/`SetCallTransferInfo`/`CloseUnFinishedUssd` 照抄转发；`SendUssdResponse` SHALL 转发 `CellularCallConnection::SendUssdResponse(slotId, content)`（内部经 `stub/cellular_call_client` 桩，design D4）且恒返回 `TELEPHONY_SUCCESS`（照抄）。

#### Scenario: 查询呼叫等待
- **WHEN** 调用 `GetCallWaiting(slotId)`（liteOS 无权限前置）
- **THEN** 转发 `CallControlManager::GetCallWaiting`（照抄）

#### Scenario: 发送 USSD 应答
- **WHEN** 调用 `SendUssdResponse(slotId, content)`
- **THEN** 经 `CellularCallConnection`（cellular_call 桩）下发 mod 层，门面返回 `TELEPHONY_SUCCESS`（照抄）

测试落点：`test/unittest/call_manager_special_test`（special_branch 系）扩展补充业务转发矩阵用例（经桩出口断言）。

### Requirement: IMS 配置 / VoLTE / VoNR 转发

系统 SHALL 由 `CallManagerService` 转发 IMS 类接口到 `CallControlManager`（权限校验整体移除）：`GetImsConfig`/`GetImsFeatureValue`/`GetVoNRState` 与 `SetImsConfig`/`SetImsFeatureValue`/`EnableImsSwitch`/`DisableImsSwitch`/`SetVoNRState` 照抄转发；`IsImsSwitchEnabled` 直接转发（基线"仅系统应用校验"随权限移除消失）。

#### Scenario: VoLTE 开关读取
- **WHEN** 调用 `IsImsSwitchEnabled(slotId, enabled)`
- **THEN** 直接转发 `CallControlManager::IsImsSwitchEnabled`（照抄，无校验前置）

测试落点：`test/unittest/call_manager_special_test`（special_branch 系）扩展 IMS 配置转发矩阵用例。

### Requirement: 通话状态查询转发

系统 SHALL 由 `CallManagerService` 转发查询接口（权限校验整体移除）：`HasCall(isInCludeVoipCall)`（含 VoIP 时取 `HasCall()`，仅蜂窝时取 `HasCellularCallExist()`，指针为空返回 false，照抄）、`IsRinging`、`IsInEmergencyCall`（转发 `HasEmergency`）、`IsEmergencyPhoneNumber`、`FormatPhoneNumber`/`FormatPhoneNumberToE164`（号码格式化内部 libphonenumber 调用经桩，design D6 libphonenumber 行）。

#### Scenario: 仅统计蜂窝通话
- **WHEN** 以 `isInCludeVoipCall=false` 调用 `HasCall`
- **THEN** 返回 `HasCellularCallExist()` 结果（照抄）

#### Scenario: 紧急来电查询
- **WHEN** 调用 `IsInEmergencyCall`
- **THEN** 输出 `CallControlManager::HasEmergency` 的结果（照抄，无权限前置）

测试落点：`test/unittest/call_manager_zero_gtest`（zero_branch 系）新增查询面转发矩阵用例。

### Requirement: DTMF 与后拨号继续转发

系统 SHALL 由 `CallManagerService` 转发 `StartDtmf(callId, str)`/`StopDtmf(callId)`/`PostDialProceed(callId, proceed)` 至 `CallControlManager`（权限校验整体移除，转发语义照抄）。

#### Scenario: 后拨号确认
- **WHEN** 调用 `PostDialProceed(callId, true)`
- **THEN** 转发 `CallControlManager::PostDialProceed`（照抄，无权限前置）

测试落点：`test/unittest/call_manager_zero_gtest`（zero_branch 系）新增 DTMF/后拨号转发用例。

### Requirement: RTT 转发

系统 SHALL 由 `CallManagerService::StartRtt(callId, msg)`/`StopRtt(callId)` 转发 `CallControlManager`（权限校验整体移除；`SUPPORT_RTT_CALL` 支持宏保留，design D7）；RTT API 链路（`CallManagerService::StartRtt/StopRtt` → `IMSCall::StartRtt/StopRtt` → `CellularCallConnection::StartRtt/StopRtt`）保留，适配器出口按 `// todo!!! [rtt] ref to cellular_call_connection.cpp StartRtt/StopRtt` 占位（AGENTS：RTT 业务不再使用文件节点的方式，相关调用暂不实现；design D6 RTT 行；telephony-interaction delta RTT 条）。

#### Scenario: 启动 RTT
- **WHEN** 调用 `StartRtt`
- **THEN** 转发 `CallControlManager::StartRtt`，失败路径不追加补偿动作（照抄，无权限前置）

测试落点：`test/unittest/call_manager_special_test`（special_branch 系）扩展 RTT 转发用例与 `[rtt]` todo 标签断言。

### Requirement: SendCallUiEvent UI 事件分发

系统 SHALL 由 `CallManagerService::SendCallUiEvent(callId, eventName)` 按事件名分发（`SET_TELEPHONY_STATE` 权限校验删除）：`EVENT_SPEAKER_OFF` → `AudioProxy::SetSpeakerDevActive(false)`（AudioProxy 本体与 audio 框架调用 `[audio]` todo 见 audio-device-management delta），失败返回 `TELEPHONY_ERR_FAIL`（照抄）；`DISPLAY_SPECIFIED_CALL_PAGE_BY_CALL_ID` → `HandleDisplaySpecifiedCallPage`（保留，见本 delta MODIFIED「CeliaCall（新通话）事件（集中独立）」条）；`EVENT_VOIP_CALL_SUCCESS`/`EVENT_VOIP_CALL_FAILED` → `HandleVoIPCallEvent`（保留，VoIP 冲突链）；未匹配事件名静默返回 `TELEPHONY_SUCCESS`（照抄）。以下分支删除：`EVENT_IS_CELIA_CALL` → `dealCeliaCallEvent` 与 `EVENT_CELIA_AUTO_ANSWER_CALL_ON`/`OFF` → `HandleCeliaAutoAnswerCall`（新通话/Celia 族，AGENTS「功能范围」新通话不支持；裁决仅移除 dealCeliaCallEvent/HandleCeliaAutoAnswerCall/HandleCeliaCall/IS_CELIA_CALL 链）；`EVENT_BLUETOOTH_SCO_STATE_OFF`/`ON` → `BluetoothCallConnection::DisConnectBtSco`/`ConnectBtSco` 与 `EVENT_SUPPORT_BLUETOOTH_CALL`/`EVENT_NOT_SUPPORT_BLUETOOTH_CALL` → `GetSupportBtCall()` 匹配（BLUETOOTH 类型通话删除，`bluetooth_call_connection.cpp` 随删，design D7）；`EVENT_INVALID_VIDEO_FD` → `CallControlManager::HandleVideoRingPlayFail`（视频彩振面：liteOS 无视频彩振（crsType==CRS_TYPE）通话、无效视频 FD 事件不可达，AGENTS「功能范围」）。

#### Scenario: 关闭免提扬声器
- **WHEN** eventName 为 `EVENT_SPEAKER_OFF` 且 `SetSpeakerDevActive(false)` 返回成功（经 `[audio]` todo 桩面判定）
- **THEN** 返回 `TELEPHONY_SUCCESS`（照抄）

#### Scenario: 未知事件
- **WHEN** eventName 不匹配任何保留分支
- **THEN** 无副作用返回 `TELEPHONY_SUCCESS`（照抄）

测试落点：`test/unittest/call_manager_zero_gtest`（zero_branch 系，含 `zero_branch7_test.cpp` 的 SendCallUiEvent 用例面）新增分发矩阵用例（保留分支正断言、Celia/蓝牙/视频彩振分支删除负向断言）。

### Requirement: CeliaCall（新通话）事件（集中独立）

系统 SHALL 集中处理本需求中保留的分支，新通话/Celia 族删除（AGENTS「功能范围」新通话不支持；裁决仅移除 `dealCeliaCallEvent`/`HandleCeliaAutoAnswerCall`/`HandleCeliaCall`/`IS_CELIA_CALL` 链）：`HandleDisplaySpecifiedCallPage(callId)` SHALL 保留——通话 extras 注入 `sosWithOutCallUiAbility="2"` 后经 `CallAbilityReportProxy::ReportCallStateInfo` 直调上报（`AAFwk::WantParams`/`WantParamWrapper` 数据面按 design D5 以普通结构体/字符串参数替换，注入与上报语义照抄）；`HandleVoIPCallEvent` SHALL 保留——对 TYPE_VOIP 通话组装 callId/eventName/publishTime（基线 `AppExecFwk::PacMap` 按 design D5 换普通结构体）经 `VoipCallConnection::SendCallUiEventForWindow` 上报（出口经 voip 桩并带 `[callUi]` todo，见 telephony-interaction delta VoipCallConnection 条）；`IsNewCallAllowed(enabled)` SHALL 保留并转发 `CallControlManager::IsNewCallAllowed`（实测与 Celia 无关：判定非 VoIP 通话处于 CREATE/CONNECTING/DIALING/RINGING 态时禁止再建新通话，design D9；系统应用校验随权限移除消失）。删除的分支：`dealCeliaCallEvent(callId)`（`GetOneCallObject` 判空、`HandleCeliaCall`、`SetCeliaCallType(IS_CELIA_CALL=1)`、`DistributedCallManager::IsDCallDeviceSwitchedOn` → `SwitchOffDCallDeviceSync`/`ReportDistributedDeviceInfoForSwitchOff` 分布式联动——分布式与新通话均删除）、`HandleCeliaAutoAnswerCall(callId, enable)`（`SetAiAutoAnswer`）。

#### Scenario: Celia 事件设置通话类型
- **WHEN** 基线 `EVENT_IS_CELIA_CALL` 分支对有效 callId 执行
- **THEN** 因新通话（CeliaCall）删除（AGENTS），`dealCeliaCallEvent`/`SetCeliaCallType(IS_CELIA_CALL)` 及分布式关断联动不迁移；场景改写为负向断言（该事件名不再被分发处理）

#### Scenario: AI 自动接听开关
- **WHEN** 基线分别以 `EVENT_CELIA_AUTO_ANSWER_CALL_ON`/`OFF` 分发
- **THEN** 因新通话删除，`HandleCeliaAutoAnswerCall`/`SetAiAutoAnswer` 分支不迁移；场景改写为负向断言

#### Scenario: 指定通话页面拉起
- **WHEN** `DISPLAY_SPECIFIED_CALL_PAGE_BY_CALL_ID` 分发且 callId 有效
- **THEN** extras 注入 sosWithOutCallUiAbility 后经 `CallAbilityReportProxy::ReportCallStateInfo` 直调上报通话状态（数据面结构体替换，语义照抄）

测试落点：`test/unittest/call_manager_zero_gtest`（zero_branch 系，含 `zero_branch10_test.cpp` 的 HandleVoIPCallEvent/HandleDisplaySpecifiedCallPage 用例面）新增保留分支用例与 Celia 分支删除负向断言。

### Requirement: VoIP 与 OTT 上报转发

系统 SHALL 由 `CallManagerService` 转发 VoIP 面（权限校验整体移除；VoIP 类型通话暂不支持但冲突链保留，AGENTS「暂不支持 VOIP……解决畅连通话和蜂窝通话冲突场景」）：`RegisterVoipCallManagerCallback` SHALL 经 `VoipCallConnection::Init(TELEPHONY_VOIP_CALL_MANAGER_SYS_ABILITY_ID=65968)`（SA id 常量平移、不驱动真实 SA 连接）创建 `CallStatusCallback` 并经 voip 桩注册（`stub/voip_call_client`，design D4；telephony-interaction delta VoipCallConnection 条）；`UnRegisterVoipCallManagerCallback` 转发解除保留；`SetVoIPCallState`/`GetVoIPCallState`/`SetVoIPCallInfo`/`GetVoIPCallInfo` 转发 `CallControlManager` 保留；基线 `lock_` 锁删除（design D8）。OTT 面删除（AGENTS「功能范围」OTT 类型通话不支持；design D7 `ott_call.cpp`/`ott_call_connection.cpp` 删除，call-object-management delta OTT 条）：`ReportOttCallDetailsInfo`（空向量拒绝 `TELEPHONY_ERR_ARGUMENT_INVALID`、`OttCallDetailsInfo` 拷贝为 `CallDetailInfo`（callType=TYPE_OTT、accountId/index/voiceDomain=ERR_ID）后交 `ReportCallInfoHandler::UpdateCallsReportInfo`）与 `ReportOttCallEventInfo`（交 `UpdateOttEventInfo`，该处理链已随 telephony-interaction delta 删除）的转发分支不迁移。

#### Scenario: VoIP 回调注册
- **WHEN** 调用 `RegisterVoipCallManagerCallback`
- **THEN** `VoipCallConnection` 以常量 65968 初始化（驱动 `stub/voip_call_client` 桩）并注册 `CallStatusCallback`（照抄语义，出口经桩）

#### Scenario: 空列表拒绝
- **WHEN** 基线 `ReportOttCallDetailsInfo` 收到空向量
- **THEN** 因 OTT 类型通话删除（AGENTS），该入口与 `TELEPHONY_ERR_ARGUMENT_INVALID` 空向量校验分支不迁移；场景改写为负向断言（接口面无 OTT 上报入口）

测试落点：`test/unittest/call_manager_zero_gtest`（zero_branch 系）与 `test/unittest/call_manager_gtest`（`call_manager7_gtest`）新增 VoIP 注册/状态转发经桩用例与 OTT 入口删除负向断言。

### Requirement: 拨号器特殊码广播

系统 SHALL 由 `CallManagerService::InputDialerSpecialCode(specialCode)`（权限校验整体移除）先在 `supportSpecialCode_` 白名单（"*#2846#"、"*#2846*"、"*#*#2846579#*#*"、"#1#"、"*#28465#"、"*#*#121314#*#*"、"*#*#19467328#*#*"、"*#*#2589#*#*"、"*#*#2845#*#*"、"*#*#2846#*#*"、"*#*#2847#*#*"、"*#*#28465#*#*"、"*#*#2627#*#*"、"*#*#258#*#*"、"*#28460"）校验，命中后以 `EventFwk::CommonEventSupport::COMMON_EVENT_SPECIAL_CODE` action、data=specialCode 发布公共事件的调用点 SHALL 以 todo 占位（`// todo!!! [broadcast] ref to call_manager_service.cpp InputDialerSpecialCode`，AGENTS：广播 EventFwk::CommonEventManager 相关接口暂不调用；design D6 广播行；白名单与匹配逻辑保留）；未命中返回 `TELEPHONY_ERR_ARGUMENT_INVALID`（照抄）；发布失败返回 `TELEPHONY_ERR_PUBLISH_BROADCAST_FAIL` 的分支保留（桩面可注入失败复现）。

#### Scenario: 白名单特殊码
- **WHEN** 拨号应用以白名单内的 *# 特殊码调用本接口
- **THEN** 匹配命中后广播发布调用点以 `[broadcast]` todo 占位（桩面可断言匹配结果与占位标注），返回 `TELEPHONY_SUCCESS`

#### Scenario: 非白名单
- **WHEN** specialCode 不在 `supportSpecialCode_`
- **THEN** 返回 `TELEPHONY_ERR_ARGUMENT_INVALID` 且不触发发布调用点（照抄）

测试落点：`test/unittest/call_manager_zero_gtest`（zero_branch 系）新增白名单匹配矩阵用例与 `[broadcast]` todo 标签断言。

### Requirement: 未接来电通知清除

系统 SHALL 由 `CallManagerService::RemoveMissedIncomingCallNotification()` 转发 `CallControlManager::RemoveMissedIncomingCallNotification`（基线 SET/READ/WRITE_CALL_LOG 三权限齐备校验随权限整体移除消失；通知发送出口的 `[notification]` todo 桩化见 call-state-observer delta）。

#### Scenario: 权限不齐
- **WHEN** 基线缺任一 READ_CALL_LOG/WRITE_CALL_LOG 权限调用
- **THEN** 权限校验移除后该失败分支不迁移；liteOS 上调用直接转发清除链、不再返回 `TELEPHONY_ERR_PERMISSION_ERR`（场景改写为直转发负向断言）

测试落点：`test/unittest/call_manager_zero_gtest`（zero_branch 系）新增清除转发用例（无权限前置断言）。
