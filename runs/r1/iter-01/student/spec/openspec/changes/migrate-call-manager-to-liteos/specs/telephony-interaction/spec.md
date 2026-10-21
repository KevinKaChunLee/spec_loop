# Spec Delta

## REMOVED Requirements

### Requirement: CallStatusCallbackStub IPC 分发表

**Reason**: AGENTS「以下接口不调用」明确 liteOS 中 callmanager 不继承 SystemAbility 也不实现 IPC 调用；design D3 删除 `services/telephony_interaction/src/call_status_callback_stub.cpp`（stub 分发表不迁移），design D2 运行形态为客户端直调服务。
**Migration**: 删除 `call_status_callback_stub.cpp/.h`（`InitBasicFuncMap/InitSupplementFuncMap/InitImsFuncMap` 的 37 命令码 `memberFuncMap_` 分发表、`OnRemoteRequest` 描述符比对与查表分发、`ReadRawData(len)` 解包及 `MAX_LEN=100000`/`MAX_CALL_NUM=10` 越界守卫、`BuildCallReportInfo` 约定序列解包均不迁移）并同步 `callmanager.gni`；cellular_call 上行入口改经 `stub/cellular_call_client` 桩直调——测试中由 cellular_call 桩触发 `CallStatusCallback` 等价函数进入（design D3/D4），全部回调语义保留在本 delta「CallStatusCallback 上行转换与 app 上报」与「上行单队列串行化（ReportCallInfoHandler）」条；与 cellular_call 交换的 `CallReportInfo` 等跨部件结构体按基线签名平移，桩面兼容需人工复核（design D4）。恢复条件：恢复 SA/IPC 形态时按基线重建 stub 分发表、描述符校验与解包守卫。

### Requirement: BluetoothCallConnection 与蓝牙通话框架交互

**Reason**: AGENTS「功能范围」明确 liteOS 不支持 BLUETOOTH 类型通话，`ABILITY_BLUETOOTH_SUPPORT` 属不支持宏（「特性宏支持范围」）；design D7 被删文件表列出 `services/telephony_interaction/src/bluetooth_call_connection.cpp` 与 `services/bluetooth/` 全目录。
**Migration**: 删除 `bluetooth_call_connection.cpp/.h`（`Dial`/`ConnectBtSco`/`DisConnectBtSco`/`GetBtScoIsConnected`/`SetMacAddress`/`GetMacAddress`/`SetHfpConnected` 及 `HfpDisConnectedEndBtCall` 补报链/`SetBtCallScoConnected`/`GetBtCallScoConnected`/`SetHfpContactName`/`GetHfpContactName`）并同步 `callmanager.gni`；下游引用点随删：`ReportCallInfoHandler::UpdateCallReportInfo` 的 `TYPE_BLUETOOTH` 过滤分支、`CallStatusCallback::UpdateCallReportInfo` 的蓝牙拨号 index 归零特例（见本 delta MODIFIED 对应条）、`AudioDeviceManager::ReportAudioDeviceInfo` 的 SCO 显示映射（见 audio-device-management delta）。恢复条件：接入蓝牙 HFP 通话框架后按基线重建连接类与 HFP 断开结束链。

## MODIFIED Requirements

### Requirement: cellular_call SA 连接、回调注册与重连

系统 SHALL 将 `CellularCallConnection`（`services/telephony_interaction/src/cellular_call_connection.cpp`，DelayedSingleton 形态保留）保留为适配器（design D4）：基线经 `SystemAbilityManagerClient` → `GetSystemAbility(systemAbilityId_)` → `iface_cast<CellularCallInterface>` 取 `cellularCallInterfacePtr_` 的连接面改为 `stub/cellular_call_client` 桩的可用性判定与绑定，业务转发改 `CellularCallClient::GetInstance().Xxx()`；桩 MUST 默认配置为不可用（返回失败），与基线"服务未连接"分支语义一致（基线失败码 `TELEPHONY_ERR_IPC_CONNECT_STUB_FAIL` 照抄；测试可配置桩返回值，design Risks）。`ConnectService` SHALL 保留成功后 `RegisterCallBackFun` 创建 `CallStatusCallback` 并经 `RegisterCallManagerCallBack` 在桩面注册；失败时 `Clean`（UnRegisterCallBack + 清空回调/接口两指针 + `connectState_ = false`）照抄（sptr 成员按 design D5 换 std 智能指针）。无 samgr（design D2），基线 `Init` 的 `SystemAbilityListener` 与 `SubscribeSystemAbility`、`OnAddSystemAbility`/`OnRemoveSystemAbility` 上下线回调不迁移；服务上线/下线语义改由测试配置桩状态模拟。`ReConnectService` SHALL 保留代理为空时执行一次 `ConnectService` 的单次重连语义与 `#ifdef ABILITY_CELLULAR_SUPPORT` 守卫（支持宏与部件保留，design D7 支持宏表）；基线 `#ifdef RECONNECT_MAX_TRY_COUNT` 头部常量守卫（`CONNECT_MAX_TRY_COUNT = 5`，仓内无使用点）删除（不支持宏，design D7）；基线 `ffrt::shared_mutex` `clientLock_` 锁删除、不设替代（design D6 锁行、D8 单线程）。

#### Scenario: 服务未启动时下行调用
- **WHEN** cellular_call 桩配置为不可用（默认态，等价基线 `GetSystemAbility` 返回空）
- **THEN** `ConnectService` 失败返回 `TELEPHONY_ERR_IPC_CONNECT_STUB_FAIL` 语义、接口指针为空、`connectState_` 为 false；后续每次业务调用经 `ReConnectService` 单次重试连接判定，失败返回 `TELEPHONY_ERR_IPC_CONNECT_STUB_FAIL`（照抄）

#### Scenario: 服务上线监听重连
- **WHEN** 测试把桩从不可用切换为可用（基线 `OnAddSystemAbility` 场景的桩面等价，liteOS 无 samgr 监听）
- **THEN** 下一次业务调用前置重连判定成功并绑定桩；随后调 `ClearAllCalls` 向"对端"同步本端在途通话（逐通组包后 sleep `DELAY_TIME` 100ms 再发照抄；空表返回 `TELEPHONY_ERR_ARGUMENT_INVALID`，见「DTMF 与其它杂项下行出口」）

#### Scenario: 服务下线清理
- **WHEN** 测试把桩切换回不可用并触发注销（基线 `OnRemoveSystemAbility` 场景的桩面等价）
- **THEN** `Clean` 链保留：`UnRegisterCallBack`、清空回调/接口指针、`connectState_` 复位为 false（照抄）

测试落点：`call_manager_zero_gtest`（交互面用例所在 `tel_call_manager_zero1_gtest`/`tel_call_manager_zero5_gtest`~`tel_call_manager_zero8_gtest` 套件）新增 `Telephony_CellularConnection_01x` 系用例（桩不可用/可用两态的连接、注册回调、Clean 链、单次重连守卫）。

### Requirement: 呼叫控制下行出口

系统 SHALL 由 `CellularCallConnection` 的 `Dial/HangUp/Reject/Answer/HoldCall/UnHoldCall/SwitchCall` 提供呼叫控制转发：每个方法先过 `ReConnectService`（失败即返回 `TELEPHONY_ERR_IPC_CONNECT_STUB_FAIL`；Dial/HangUp/Reject/Answer 并经 `CallManagerHisysevent::WriteDialCallFaultEvent/WriteHangUpFaultEvent/WriteAnswerCallFaultEvent` 记故障事件——HiSysEvent 维测出口经 `stub/hisysevent_stub` 改日志打印、签名不变，design D5），再调 `CellularCallClient::GetInstance()` 桩的同名接口（`Dial(CellularCallInfo)`、`HangUp(callInfo, CallSupplementType)`、`Reject`、`Answer`、`HoldCall`、`UnHoldCall`、`SwitchCall`，design D4），非成功返回码原样透传。

#### Scenario: 拨号成功
- **WHEN** `Dial(callInfo)` 且桩配置为可用
- **THEN** `CellularCallClient::GetInstance().Dial` 返回 0 时透传成功；非 0 时记录 errCode 日志并透传（照抄）

#### Scenario: 挂断失败带故障事件
- **WHEN** `HangUp` 前的重连判定失败（桩不可用，默认态）
- **THEN** `WriteHangUpFaultEvent` 以 `TELEPHONY_ERR_IPC_CONNECT_STUB_FAIL`/"HangUp ipc reconnect failed" 经维测桩输出日志并返回该错误码（照抄）

测试落点：`tel_call_manager_zero1_gtest` 套件新增 `Telephony_CellularConnection_02x` 系用例（控制面转发矩阵、故障事件维测桩断言、透传返回码）。

### Requirement: 补充业务与 MMI/USSD 下行出口

系统 SHALL 由 `CellularCallConnection` 提供补充业务（UT/USSI/USSD/MMI）转发族，语义全部保留（AGENTS「特性宏支持范围」说明 1：补充业务 UT/USSI/USSD/MMI 相关功能需要支持）：`SetCallTransferInfo/CanSetCallTransferTime/GetCallTransferInfo`、`SetCallWaiting/GetCallWaiting/GetVideoCallWaiting`、`SetCallRestriction/GetCallRestriction/SetCallRestrictionPassword`、`SetCallPreferenceMode`、`SetImsSwitchStatus/GetImsSwitchStatus`、`GetCarrierVtConfig`、`SetVoNRState/GetVoNRState`、`SetImsConfig`（两重载）/`GetImsConfig`、`SetImsFeatureValue/GetImsFeatureValue`、`SendUssdResponse(slotId, content)`、`CloseUnFinishedUssd`、`IsMmiCode(slotId, number)`、`IsEmergencyPhoneNumber(slotId, phoneNum, enabled)`。各方法 SHALL 统一以 `ReConnectService` 前置（失败返回 `TELEPHONY_ERR_IPC_CONNECT_STUB_FAIL`），内部调用 `CellularCallClient::GetInstance()` 桩的同名接口（design D4），其余返回码透传。

#### Scenario: USSD 应答回发
- **WHEN** 用户在 USSD 会话中应答、`SendUssdResponse` 被调用
- **THEN** 重连判定成功后调桩 `SendUssdResponse(slotId, content)`，非 0 返回码透传（照抄）

#### Scenario: MMI 码判定
- **WHEN** 拨号串需判定是否为功能码、`IsMmiCode(slotId, number)` 被调用
- **THEN** 由桩 `IsMmiCode` 的返回值决定（bool 透传）；重连判定失败时返回错误码值（照抄）

测试落点：`call_manager_special_test`（`tel_call_manager_special2_test` 套件，补充业务面现有用例所在）扩展 `Telephony_CellularSetting`/`Telephony_CellularConnection` 系用例（UT/USSD/MMI 陈述式转发矩阵经桩出口断言）。

### Requirement: 会议、视频与 RTT 下行出口

系统 SHALL 由 `CellularCallConnection` 仅保留 RTT 下行出口：`StartRtt(callInfo, msg)`/`StopRtt(callInfo)` 转发语义保留（`SUPPORT_RTT_CALL` 支持宏保留，design D7 支持宏表；`CallManagerService::StartRtt/StopRtt` → `IMSCall::StartRtt/StopRtt` → `CellularCallConnection::StartRtt/StopRtt` API 链路保留，见 call-object-management delta）；连接前置失败返回 `TELEPHONY_ERR_IPC_CONNECT_STUB_FAIL`、内部改调 `CellularCallClient::GetInstance().StartRtt/StopRtt` 桩（design D4），适配器出口按 design D6 RTT 行标 `// todo!!! [rtt] ref to cellular_call_connection.cpp StartRtt/StopRtt`（AGENTS：RTT 业务不再使用文件节点的方式，相关调用暂不实现）。因会议/视频通话不支持（AGENTS「功能范围」；design D7 `cs_conference.cpp`/`ims_conference.cpp`/`video_call_state.cpp` 删除，会议/视频对象族见 call-object-management delta REMOVED 条），会议族转发 `CombineConference/SeparateConference/KickOutFromConference/InviteToConference` 与视频族转发 `ControlCamera/SetPreviewWindow/SetDisplayWindow/SetCameraZoom/SetPausePicture/SetDeviceDirection/SendUpdateCallMediaModeRequest/SendUpdateCallMediaModeResponse/CancelCallUpgrade/RequestCameraCapabilities` 的 Connection 侧分支删除——上游控制入口随 call-control-management delta 的会议/视频需求移除，liteOS 下该转发分支删除、函数族不迁移。`GetVideoCallWaiting` 的 UT 查询转发已在「补充业务与 MMI/USSD 下行出口」保留，本需求不重复列出。

#### Scenario: 合并会议
- **WHEN** 基线 `CombineConference(callInfo)` 被调用
- **THEN** 因会议通话不支持（AGENTS），该转发分支与场景不迁移；liteOS 上会议对象族已删除，无调用可达该出口

#### Scenario: 视频模式升级请求
- **WHEN** 基线 `SendUpdateCallMediaModeRequest` 被调用
- **THEN** 因视频通话不支持（AGENTS），该转发分支与对端响应上行（`CallStatusCallback::ReceiveUpdateCallMediaModeResponse`，见本 delta MODIFIED 对应条）删除，场景不迁移

测试落点：`tel_call_manager_special2_test` 套件新增 `Telephony_CellularConnection_03x` 系用例（StartRtt/StopRtt 桩出口与 `[rtt]` todo 标签断言、会议/视频转发负向断言）。

### Requirement: DTMF 与其它杂项下行出口

系统 SHALL 由 `CellularCallConnection` 提供 DTMF 与杂项转发，逐项照抄：`StartDtmf/StopDtmf/SendDtmf/SendDtmfString/PostDialProceed`、`SetMute`、`RegisterCallBack/UnRegisterCallBack`（本端回调注册生命周期，改桩注册）；`ClearAllCalls` SHALL 保留遍历本端在途通话组包 `callsInfo`（slotId/accountId/callType/videoState/index/phoneNum 字段照抄），`std::this_thread::sleep_for(DELAY_TIME=100ms)` 后调桩 `ClearAllCalls(callsInfo)`，`callsInfo` 为空返回 `TELEPHONY_ERR_ARGUMENT_INVALID`。所有方法 SHALL 保持统一的 `ReConnectService` 前置与返回码透传约定，内部经 `stub/cellular_call_client`（design D4）。

#### Scenario: 后拨字符上报
- **WHEN** 对端通知后拨序列、`PostDialProceed` 被调用
- **THEN** 桩 `PostDialProceed` 被调用，结果码透传（照抄）

#### Scenario: 服务上线后的通话同步
- **WHEN** 重连判定成功后 `ClearAllCalls` 被调用且本端有在途通话
- **THEN** 逐通组包（slotId/accountId/callType/videoState/index/phoneNum）后延迟 100ms 调桩 `ClearAllCalls`，桩侧可断言收到的组包内容；无通话时返回参数错误（照抄）

测试落点：`tel_call_manager_zero1_gtest` 套件新增 `Telephony_CellularConnection_04x` 系用例（DTMF 转发矩阵、ClearAllCalls 组包与空表错误码）。

### Requirement: 与 core_service 的 FDN 交互

系统 SHALL 将 `CoreServiceConnection`（`services/telephony_interaction/src/core_service_connection.cpp`）保留为适配器（design D4）：基线 `DelayedRefSingleton<CoreServiceClient>` 改为 `stub/core_service_client` 桩的 `CoreServiceClient::GetInstance()`；`GetFdnNumberList(slotId)` SHALL 转发 `QueryIccDiallingNumbers(slotId, DiallingNumbersInfo::SIM_FDN, diallingNumbers)`——空表返回空 vector，否则逐条收集 `GetNumber()` 照抄；`IsFdnEnabled(slotId)` SHALL 转发 `GetLockState(slotId, LockType::FDN_LOCK, lockState)`，仅当返回成功且 `lockState == LOCK_ON` 时为 true 照抄；FDN 判定链整体保留。`HasSimCard`/`GetSimState` 等 core_service 查询的调用点不在本目录（`call_policy.cpp`、`call_manager_service.cpp`、`call_manager_dump_helper.cpp`），不纳入本能力（照基线口径）。与 core_service 交换的 `DiallingNumbersInfo` 等跨部件结构体在桩面的兼容性需人工复核（design D4）。

#### Scenario: FDN 号码白名单查询
- **WHEN** 拨号前需校验受限拨号、`GetFdnNumberList` 被调用
- **THEN** 桩 `QueryIccDiallingNumbers` 返回的 SIM FDN 记录号码列表被收集返回；查询为空时返回空列表（照抄）

#### Scenario: FDN 开关判定
- **WHEN** `IsFdnEnabled` 被调用且桩 `GetLockState` 失败或状态非 LOCK_ON（桩默认失败）
- **THEN** 返回 false（FDN 未启用，不阻断拨号；照抄）

测试落点：`tel_call_manager_zero1_gtest` 套件新增 `Telephony_CoreServiceConnection_01x` 系用例（FDN 两查询的桩返回值矩阵）。

### Requirement: 上行单队列串行化（ReportCallInfoHandler）

系统 SHALL 由 `ReportCallInfoHandler`（`services/telephony_interaction/src/report_call_info_handler.cpp`）保持上行单队列串行语义：基线命名空间级 ffrt 队列 `report_call_info_queue`（`ffrt::queue_attr().qos(ffrt_qos_user_interactive)`）改打桩 EventHandler 的串行任务队列（`stub/eventhandler_stub`，design D8；桩内同步逐条执行、不新增线程，qos 语义随 ffrt 消失不迁移），`std::weak_ptr<CallStatusManager>` 捕获照抄。`UpdateCallReportInfo` SHALL 保留立即返回成功、队列内 `HandleCallReportInfo` 失败仅记日志的语义；基线"OOBE 期 `CallStatusManager::GetDevProvisioned() != DEVICE_PROVISION_VALID` 且 `TYPE_BLUETOOTH` 来电直接丢弃"过滤分支按裁剪改写：蓝牙类型通话不存在（AGENTS），丢弃分支删除；`GetDevProvisioned` 的 DataShare 查询调用点按 database todo 桩化（`// todo!!! [database] ref to settings_datashare_helper.cpp Query`，design D6 数据库行），判定链其余部分照抄（桩默认失败时 `deviceProvisioned_` 维持未定义值）。`UpdateCallsReportInfo` SHALL 保留 `BuildCallDetailsInfo` 逐条字段拷贝主链与队列内 `HandleCallsReportInfo`，incoming 额外 `WriteIncomingCallFaultEvent` 记账改经维测桩日志（design D5）；`UpdateDisconnectedCause` SHALL 保留 `RilDisconnectedReason::DISCONNECTED_REASON_NORMAL` 归一为 `DisconnectedReason::NORMAL_CALL_CLEARING` 照抄；`UpdateEventResultInfo`/`UpdateVoipEventInfo`（队列内 `HandleEventResultReportInfo`/`HandleVoipEventReportInfo`）保留；`UpdateOttEventInfo`（`HandleOttEventReportInfo`）随 OTT 类型通话删除（design D7 `ott_call.cpp`；call-object-management delta OTT 条）。会议/视频相关上行转发删除：基线 `ReceiveImsCallModeRequest/ReceiveImsCallModeResponse` 按 `response.callIndex`（Response 先按 slotId 再按 index）取 `CallObjectManager` 通话对象并 `reinterpret_cast<IMSCall *>` 转发到 `RecieveUpdateCallMediaModeRequest/ReceiveUpdateCallMediaModeResponse` 的整链随视频通话删除。`Init` SHALL 保留构造 `CallStatusManager` 并经 `SetCallStatusManager` 注入 `CallManagerService`；基线向 `AntiFraudService` 注入的一行随防诈删除（design D7 antifraud 模块文件删除）。

#### Scenario: 单通话状态上报
- **WHEN** cellular_call 桩触发的上行经 `CallStatusCallback::UpdateCallReportInfo` 转为 `CallDetailInfo` 进入本处理器
- **THEN** `UpdateCallReportInfo` 立即返回成功，`HandleCallReportInfo` 在打桩 EventHandler 队列内串行执行，失败仅记日志不回传（照抄）

#### Scenario: 通话列表上报
- **WHEN** `UpdateCallsReportInfo` 收到多通通话列表
- **THEN** 逐条字段拷贝（`BuildCallDetailsInfo`）后队列内 `HandleCallsReportInfo` 串行执行；列表中有 incoming 状态通话时额外经维测桩日志记录 `WriteIncomingCallFaultEvent` 记账（照抄）

#### Scenario: IMS 视频模式请求
- **WHEN** 基线 `ReceiveImsCallModeRequest` 被调用且 index 对应通话为 `TYPE_IMS`
- **THEN** 因视频通话不支持（AGENTS），媒体模式请求/响应的队列内处理与 `IMSCall` 转发分支删除，该场景不迁移（对端媒体面事件在 liteOS 不存在）

测试落点：`tel_call_manager_zero5_gtest`~`tel_call_manager_zero8_gtest` 套件新增 `Telephony_ReportHandler_01x` 系用例（桩队列串行顺序断言、BuildCallDetailsInfo 字段矩阵、蓝牙丢弃分支删除负向断言、VoIP 事件路径保留）。

### Requirement: CallStatusCallback 上行转换与 app 上报

系统 SHALL 保留 `CallStatusCallback`（`services/telephony_interaction/src/call_status_callback.cpp`）作为 cellular_call 上行回调（`ICallStatusCallback` 实现保留）：liteOS 上不经 IPC stub 分发（分发表已删，见本 delta REMOVED 条），上行入口改经 `stub/cellular_call_client` 在测试中触发等价函数直调进入（design D3/D4），全部回调语义保留：`UpdateCallReportInfo` 把 `CallReportInfo` 转 `CallDetailInfo`（VOIP 字段逐项拷贝照抄；基线"存在 index 0 的蓝牙拨号通话且本条为蓝牙 disconnected 时把 `detailInfo.index` 归零"特例随蓝牙删除）后交 `ReportCallInfoHandler`；`UpdateCallsReportInfo` 记 `WriteCallStateBehaviorEvent`（维测桩日志），incoming 时记 `WriteIncomingCallBehaviorEvent` + `SetIncomingStartTime`，基线 `StartAsyncTrace(HITRACE_TAG_OHOS, "InComingCall", getpid())` hitrace 改日志（design D5）；`UpdateDisconnectedCause`/`UpdateEventResultInfo` 保留；`UpdateRBTPlayInfo` 在 `LOCAL_ALERTING` 时置 `isLocalRingbackNeeded = true` 并经 `CallAbilityReportProxy::CallEventUpdated` 发 `EVENT_LOCAL_ALERTING`，否则置 false，随后调 `AudioControlManager::SetLocalRingbackNeeded`（直调上报照抄）；`StartDtmfResult/StopDtmfResult/SendUssdResult/GetImsCallDataResult/UpdateGetWaitingResult` 等全部补充业务结果 SHALL 以 `CallResultReportId` 经 `CallAbilityReportProxy::ReportAsyncResults` 直调上报 app（基线 `AppExecFwk::PacMap` 按 design D5 换普通结构体出口，跨部件兼容需人工复核 design D4）；`SendMmiCodeResult` SHALL 以打桩 EventHandler 延迟 1s（`REPORT_SEND_USSD_DELAY_TIME`，基线 `ffrt::submit_h` 替换为 `stub/eventhandler_stub` 定时，design D8）上报 `ReportMmiCodeResult`；`StartRttResult/StopRttResult` 转发 `ReportAsyncResults` 照抄（RTT 结果回调保留）；`ReportPostDialChar` SHALL 取首字符转 `AudioControlManager::OnPostDialNextChar` 照抄。视频/会议相关媒体面回调族 SHALL 随视频/会议删除：`ReceiveUpdateCallMediaModeRequest`（转发 `ReportCallInfoHandler::ReceiveImsCallModeRequest`、对 active 且 `CALL_MODE_SEND_RECEIVE` 的通话 `PlayWaitingTone` 并以 ffrt 延迟 3s（`DELAY_STOP_PLAY_TIME`）调 `ShouldStopWaitingTone`）、`ReceiveUpdateCallMediaModeResponse`（`ffrt::skip` 取消延迟并立即判定，`MIN_MULITY_CALL_COUNT`=2 计数）、`HandleCallSessionEventChanged`、`HandlePeerDimensionsChanged`、`HandleCameraCapabilitiesChanged`、`HandleCallDataUsageChanged` ——该媒体面事件链在 liteOS 不存在（`ShouldStopWaitingTone`/`StopWaitingTone` 音频接口本体在 audio-device-management 保留）。

#### Scenario: 网络侧回铃音提示
- **WHEN** 对端开始振铃、`UpdateRBTPlayInfo(LOCAL_ALERTING)` 上行（桩注入）
- **THEN** 本地回铃音需求置 true 并向 app 发 `EVENT_LOCAL_ALERTING` 事件（`CallAbilityReportProxy::CallEventUpdated` 直调，照抄）

#### Scenario: 等待音超时停止
- **WHEN** 基线对端请求升级为视频（active + SEND_RECEIVE）且 3s 内未收到 Response
- **THEN** 因视频通话不支持（AGENTS），该视频升级触发的等待音 3s 延迟监听链删除，场景不迁移；等待音播放/停止接口本体保留于 audio-device-management（`PlayWaitingTone/StopWaitingTone`）

#### Scenario: 视频模式响应取消等待音
- **WHEN** 基线 `ReceiveUpdateCallMediaModeResponse` 在 3s 内到达
- **THEN** 因视频通话不支持，视频模式响应处理与 `ffrt::skip` 取消链删除，场景不迁移

#### Scenario: MMI 结果延迟上报
- **WHEN** `SendMmiCodeResult(info)` 被调用（桩注入）
- **THEN** 1s 后经打桩 EventHandler 定时上报 `ReportMmiCodeResult`（直调），本函数立即返回成功（照抄）

测试落点：`tel_call_manager_zero6_gtest`/`tel_call_manager_zero7_gtest` 套件新增 `Telephony_CallStatusCallback_01x` 系用例（桩直调三路上行、RBT 置位链、MMI 1s 延迟经桩 EventHandler、补充业务结果结构体上报记账、媒体面回调删除负向断言）。

### Requirement: VoipCallConnection 与 voip_call_manager 服务交互

系统 SHALL 将 `VoipCallConnection`（`services/telephony_interaction/src/voip_call_connection.cpp`，DelayedSingleton 形态保留）保留为适配器（design D4）：对 voip_call_manager 的注册/控制/事件出口改 `stub/voip_call_client` 桩的 `VoipCallClient::GetInstance().Xxx()`（design D4 新增桩）；基线经 samgr `GetSystemAbility` + `iface_cast<IVoipCallManagerService>` 取 `voipCallManagerInterfacePtr_` 的 `GetCallManagerProxy` 改桩可用性判定（默认不可用，同基线"代理为空返回 `TELEPHONY_ERROR`"分支；测试可配）；`TELEPHONY_VOIP_CALL_MANAGER_SYS_ABILITY_ID` 常量随常量表平移、不再驱动真实连接。基线 `Init` 的 `SystemAbilityListener`（OnAdd → 重新 `Init`；OnRemove → `ClearVoipCall` + `UnInit`）不迁移（无 samgr，design D2），上下线语义经测试配置桩状态模拟；`AnswerCall/RejectCall/HangUpCall` SHALL 保留先取代理再调远程的顺序（桩不可用返回 `TELEPHONY_ERROR`），HangUp 前的 `CallManagerHisysevent::WriteVoipCallStatisticalEvent(..., "HungupByCallmanager")` 统计经维测桩日志保留（design D5）；`RegisterCallManagerCallBack` SHALL 保存 `voipCallCallbackPtr_` 并调桩同名接口、`UnRegisterCallManagerCallBack` SHALL 调桩注销后 `UnInit`（照抄；`voipCallCallbackPtr_` 按 design D5 换 std 智能指针）。`SendCallUiEvent(voipCallId, callAudioEvent)` SHALL 把通话 UI 事件经 `VoipCallClient::GetInstance().SendCallUiEvent` 桩转发，调用点标 `// todo!!! [callUi] ref to voip_call_connection.cpp SendCallUiEvent`（design D6 拉起通话界面行）；`SendCallUiEventForWindow` 的 `AppExecFwk::PacMap` 参数按 design D5 换普通结构体（真实对端待畅连通话接入后适配，AGENTS「暂不支持 VOIP……依赖后续跟 meetime 畅连通话」）。基线 `std::mutex` 保护删除、不设替代（design D6 锁行、D8 单线程）。`ClearVoipCall` SHALL 完整保留冲突链：对每通 `TYPE_VOIP` 通话经 `BuildDisconnectedCallInfo` 组 `CALL_STATUS_DISCONNECTED` 报文，`voipCallCallbackPtr_` 存在时补报一次 `UpdateCallReportInfo`（防止界面未销毁），否则直接 `DeleteOneCallObject`（照抄）。

#### Scenario: VOIP 来电接听
- **WHEN** 蜂窝侧判定 VOIP 来电被用户接听、`AnswerCall(events, videoState)` 被调用
- **THEN** 桩配置可用时 `VoipCallClient::GetInstance().Answer` 被调用并透传结果；桩不可用（默认态）返回 `TELEPHONY_ERROR`（照抄基线代理为空分支）

#### Scenario: voip 服务下线清理
- **WHEN** 基线 `OnRemoveSystemAbility` 触发且本端存在 VOIP 通话对象（liteOS 无 samgr 监听，测试直接驱动等价清理路径）
- **THEN** `ClearVoipCall` 冲突链照抄：逐通补报 DISCONNECTED（`BuildDisconnectedCallInfo` 组报文、经 `ReportCallInfoHandler::UpdateCallReportInfo` 上报）或直接删除通话对象，随后 `UnInit` 清空回调/代理指针与连接标志

#### Scenario: 通话 UI 事件转发
- **WHEN** 界面事件需请求 voip 侧 UI（`SendCallUiEvent`/`SendCallUiEventForWindow`）
- **THEN** 桩配置可用时经 `VoipCallClient` 桩转发（调用点带 `[callUi]` todo 标签）；桩不可用返回 `TELEPHONY_ERROR`（照抄）

测试落点：`tel_call_manager_zero6_gtest`/`tel_call_manager_zero8_gtest` 套件新增 `Telephony_VoipConnection_01x` 系用例（桩两态的 Answer/Reject/HangUp、ClearVoipCall 冲突链经桩注入驱动、`[callUi]` todo 标签断言）。