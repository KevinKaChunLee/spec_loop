# Distributed Call Specification

## Purpose
描述 HMOS `telephony_call_manager` 中分布式通话（跨设备接续）子系统的移植前现状，落点 `services/distributed_call/`：`distributed_call_manager.cpp`（管理器生命周期/设备表/切换）、`distributed_call_proxy.cpp`（`dlopen("libdistributed_call_client.z.so")` 加载 `DistributedHardware::IDCallClient` SDK 的代理）、`distributed_communication/` 一族（`DistributedCommunicationManager`、`DistributedDeviceObserver`、`DistributedDataController`/`DistributedDataSourceController`/`DistributedDataSinkController`、`DistributedSourceSwitchController`/`DistributedSinkSwitchController`）、`transmission/` 一族（`TransmissionManager`、`SessionAdapter`、`ClientSession`/`ServerSession`，基于软总线 `Socket` 会话）。分布式设备特性由 `ABILITY_BLUETOOTH_SUPPORT` 宏门控部分场点（`distributed_call_manager.cpp` 的 `AddDCallDevice`/`OnDCallDeviceOffline` 的 HFP 监听、`distributed_source_switch_controller.cpp`/`distributed_sink_switch_controller.cpp` 的 HFP 联动），该宏由 `callmanager.gni` 按 `communication_bluetooth` 部件定义。

## Requirements

### Requirement: 管理器生命周期与系统能力订阅
系统 SHALL 由 `DistributedCallManager::Init` 创建 `DCallSystemAbilityListener` 并经 samgr `SubscribeSystemAbility` 订阅 `DISTRIBUTED_CALL_SOURCE_SA_ID`。`OnDCallSystemAbilityAdded` SHALL 创建 `DistributedCallProxy`（构造时 `dlopen("libdistributed_call_client.z.so")` 并 `dlsym` 符号 `DCALL_LOADER_GET_DCALL_CLIENT_HANDLER` 获取 `IDCallClient`），依次 `Init`、`RegisterDeviceCallback(CALLBACK_NAME, dcallDeviceListener_)`、`GetOnlineDeviceList`，并把已在线设备经 `NotifyOnlineDCallDevices` 逐个 `AddDCallDevice`。`OnDCallSystemAbilityRemoved` SHALL 置空代理与监听、`ClearDCallDevices`/`ClearConnectedDCallDevice`、`AudioDeviceManager::ResetDistributedCallDevicesList`，且若 `dCallDeviceSwitchedOn_` 为真则 `InitAudioDevice` 并复位该标记。

#### Scenario: 分布式通话源服务上线
- **WHEN** `DCallSystemAbilityListener::OnAddSystemAbility` 收到 `DISTRIBUTED_CALL_SOURCE_SA_ID` 事件
- **THEN** 代理初始化、设备回调注册完成，已在线设备进入设备表与音频设备列表

#### Scenario: 分布式通话源服务下线且已切换到分布式设备
- **WHEN** 源服务移除时 `IsDCallDeviceSwitchedOn` 为真
- **THEN** 分布式设备列表清空、已连设备清空，并触发 `InitAudioDevice` 重建本端音频

### Requirement: 分布式设备发现与设备对象构造
系统 SHALL 由 `CreateDAudioDevice` 经 `dcallProxy_->GetDCallDeviceInfo` 查询设备信息，把 `DCallDeviceType::DISTRIBUTED_DEVICE_PHONE`/`DISTRIBUTED_DEVICE_PAD`/其余分别映射为 `AudioDeviceType::DEVICE_DISTRIBUTED_PHONE`/`DEVICE_DISTRIBUTED_PAD`/`DEVICE_DISTRIBUTED_AUTOMOTIVE`，并把 `{"devName","devId"}` JSON 串写入 `AudioDevice::address`；`GetDevIdFromAudioDevice` SHALL 反向解析该 JSON。`AddDCallDevice` SHALL 去重后经 `AudioDeviceManager::AddAudioDeviceList` 注册，且在未切换过设备、通话已激活、设备为车机且 `IsSelectVirtualModem` 时异步 `SwitchOnDCallDeviceAsync` 切换。`OnDCallDeviceOffline` SHALL 移除设备，且在 `ABILITY_BLUETOOTH_SUPPORT` 打开且全部设备离线时注销 `dcallHfpListener_`。

#### Scenario: 在线设备加入
- **WHEN** `OnDCallDeviceOnline(devId)` 且 devId 不在 `onlineDCallDevices_`
- **THEN** 以映射后的设备类型与 JSON 地址加入音频设备列表，返回 `TELEPHONY_SUCCESS`

#### Scenario: 非分布式设备地址解析
- **WHEN** `GetDevIdFromAudioDevice` 收到 `deviceType` 非分布式或 address 非法 JSON
- **THEN** 返回空串，切换流程被拒绝

#### Scenario: 车机上线自动切换
- **WHEN** 通话已激活、尚未切换过分布式设备、上线设备为 `DEVICE_DISTRIBUTED_AUTOMOTIVE` 且 `IsSelectVirtualModem` 为真
- **THEN** 异步发起向该车机的切换

### Requirement: 设备切换与音频输出路由
系统 SHALL 由 `SwitchOnDCallDeviceSync` 执行切换：`isCallActived_` 为假时直接返回 true；非分布式设备或 devId 无效返回 false；切换期间 `isSwitching_` 拒绝重入；先 `ReportDistributedDeviceInfo` 再经 `dcallProxy_->SwitchDevice(devId, DCALL_SWITCH_DEVICE_TYPE_SINK)`，成功后置 `dCallDeviceSwitchedOn_`、`SetConnectedDCallDevice` 并 `AudioDeviceManager::SetCurrentAudioDevice`。`ReportDistributedDeviceInfo` SHALL 经 `AudioSystemManager::GetDevices(DISTRIBUTED_OUTPUT_DEVICES_FLAG)` 匹配当前 devId 并 `SelectOutputDevice`（`STREAM_USAGE_VOICE_MODEM_COMMUNICATION`）；`SwitchOffDCallDeviceSync` 与 `ReportDistributedDeviceInfoForSwitchOff` SHALL 优先切回 `DEVICE_TYPE_EARPIECE`；`SetCallState` SHALL 维护 `isCallActived_`；`DealDisconnectCall` SHALL 复位已切换标记并清空已连设备。

#### Scenario: 无活跃通话时请求切换
- **WHEN** `SwitchOnDCallDeviceSync` 在 `isCallActived_` 为假时调用
- **THEN** 不发起远端切换，直接返回 true

#### Scenario: 切换重入
- **WHEN** 一次 `SwitchDevice` 进行中再次调用 `SwitchOnDCallDeviceSync`
- **THEN** 返回 false，不发起第二次远端调用

#### Scenario: 关闭分布式设备
- **WHEN** `SwitchOffDCallDeviceSync` 执行
- **THEN** 音频输出切回本端听筒（`DEVICE_TYPE_EARPIECE`）

### Requirement: 分布式通信管理与数据控制器
系统 SHALL 由 `DistributedCommunicationManager::Init` 创建 `DistributedDeviceObserver` 并注册设备状态回调；`InitExtWrapper` SHALL `dlopen("libtelephony_ext_innerkits.z.so")` 并 `dlsym` `RegisterDistributedDevState`/`UnRegisterDistributedDevState`/`SwitchDistributedDevice` 作为包装函数。`SwitchToSinkDevice`/`SwitchToSourceDevice` SHALL 幂等（已是 sink/非 sink 时直接返回 true）；`SetMuted`/`MuteRinger` SHALL 转发给 `DistributedDataController`（`CreateMuteMsg`/`CreateMuteRingerMsg` 组 JSON 后经会话发送）；`NewCallCreated`/`CallDestroyed` SHALL 经 `ProcessCallInfo` 驱动 source/sink 控制器同步通话名与位置数据：`DistributedDataSourceController` 保存本地数据（`SaveLocalData`）并响应远端查询（`HandleDataQueryMsg`→`SendLocalDataRsp`），`DistributedDataSinkController` 在通话创建时 `ConnectRemote` 建会话、`SendDataQueryReq` 拉取远端数据并 `UpdateCallName`/`UpdateCallLocation` 后 `ReportCallInfo`。

#### Scenario: 通话在 sink 设备上创建
- **WHEN** 本机为 sink 角色且新通话创建
- **THEN** 建立传输会话并向 source 端发起数据查询请求

#### Scenario: 远端查询静音状态
- **WHEN** source 端收到 mute 查询消息
- **THEN** `SendLocalDataRsp` 回应本地静音数据

#### Scenario: 已在 sink 时重复切换请求
- **WHEN** `SwitchToSinkDevice` 在 `IsAudioOnSink` 已为真时调用
- **THEN** 直接返回 true，不重复切换

### Requirement: 软总线会话传输
系统 SHALL 由 `TransmissionManager`（`OnBind`/`OnShutdown`/`OnReceiveMsg`）承接会话事件并转发给当前 `SessionAdapter`，后者经 `ISessionCallback` 回调到 `DistributedDataController::OnReceiveMsg`；`ServerSession::Create` SHALL 经软总线 `Socket` API 以固定会话名创建服务端 socket，`ClientSession::Connect` SHALL 按对端 devId 发起连接；`SessionAdapter` SHALL 提供 `IsReady`/`SendMsg`/`OnBytes`/`OnError` 适配；会话收发 SHALL 以 cJSON 消息（含 `msgType` 等）承载分布式数据。

#### Scenario: 服务端会话创建
- **WHEN** source 侧 `ServerSession::Create` 调用且软总线 socket 创建成功
- **THEN** socket 就绪，等待 sink 端 `ClientSession::Connect` 接入

#### Scenario: 会话消息到达
- **WHEN** `OnReceiveMsg` 收到合法 cJSON 消息
- **THEN** 按 `msgType` 分发到对应数据控制器处理（如 mute、数据查询/应答）
