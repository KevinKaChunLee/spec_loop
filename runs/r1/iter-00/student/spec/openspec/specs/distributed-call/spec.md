# 分布式通话（Distributed Call）Specification

## Purpose
描述 HMOS call_manager 当前的分布式通话能力：基于 dsoftbus 通道的设备发现与 source/sink 角色协商、跨设备通话数据（来话号码姓名/归属地/静音状态）同步、分布式音频设备开关控制。源码落点：`telephony_call_manager/services/distributed_call/{include,src}`：`distributed_call_manager.cpp`（`DistributedCallManager`，订阅分布式通话 SA）、`distributed_call_proxy.cpp`（`DistributedCallProxy`，dlopen `libdistributed_call_client.z.so` 获取 `IDCallClient`）、`distributed_communication/`（`DistributedCommunicationManager`、`DistributedDataController` 及 `DistributedDataSinkController`/`DistributedDataSourceController`、`DistributedDeviceObserver`、`DistributedSinkSwitchController`/`DistributedSourceSwitchController`）、`transmission/`（`TransmissionManager`、`SessionAdapter`、`ServerSession`、`ClientSession`，基于 `transport/socket.h` 的 softbus 会话）。编译开关：无专属宏；`callmanager.gni` 的 `call_manager_external_deps` 含 `dsoftbus:softbus_client`（仓内未定义名为 `SUPPORT_DSOFTBUS` 的宏）；HFP 联动代码由 `ABILITY_BLUETOOTH_SUPPORT` 守护。

## Requirements

### Requirement: 分布式设备在线管理
系统 SHALL 由 `DistributedCallManager::Init` 订阅 `DISTRIBUTED_CALL_SOURCE_SA_ID`(9855) 系统能力（`DCallSystemAbilityListener`）；设备上线时 `CreateDAudioDevice` 将 `DCallDeviceInfo` 映射为 `DEVICE_DISTRIBUTED_PHONE`/`DEVICE_DISTRIBUTED_PAD`/`DEVICE_DISTRIBUTED_AUTOMOTIVE` 音频设备（devName+devId 组成 JSON 地址），经 `AudioDeviceManager::AddAudioDeviceList` 注册并记入 `onlineDCallDevices_`；通话激活期间车机设备上线且 `IsSelectVirtualModem()` 为真时 MUST 执行 `SwitchOnDCallDeviceAsync` 异步切换。

#### Scenario: 车机上线自动切换
- **WHEN** `isCallActived_` 为 true、`dCallDeviceSwitchedOn_` 为 false 且 `DEVICE_DISTRIBUTED_AUTOMOTIVE` 设备上线、`IsSelectVirtualModem()` 为真
- **THEN** 在名为 "switch on dcall" 的独立线程中执行 `SwitchOnDCallDeviceSync`

#### Scenario: 已在线设备重复上线
- **WHEN** `AddDCallDevice` 传入的 devId 已存在于 `onlineDCallDevices_`
- **THEN** 直接返回 `TELEPHONY_SUCCESS`，不重复创建与注册音频设备

#### Scenario: 当前连接设备被移除
- **WHEN** `RemoveDCallDevice` 移除的是当前已连接的分布式通话设备
- **THEN** 复位 `dCallDeviceSwitchedOn_`、`ClearConnectedDCallDevice`，并经 `InitAudioDevice` 重新初始化音频设备

### Requirement: 分布式设备开关切换
系统 SHALL 由 `SwitchOnDCallDeviceSync` 在通话激活且设备为分布式音频设备时，经 `DistributedCallProxy::SwitchDevice(devId, DCALL_SWITCH_DEVICE_TYPE_SINK)` 打开设备通路，成功后置 `dCallDeviceSwitchedOn_`=true、`SetConnectedDCallDevice` 记录当前设备并 `SetCurrentAudioDevice` 切换音频；`isCeliaCall()` 为真（前台通话 `GetCeliaCallType()` 为 `IS_CELIA_CALL`）时 MUST NOT 发起切换。

#### Scenario: 切换成功
- **WHEN** 通话激活且 `SwitchDevice` 返回 `TELEPHONY_SUCCESS`
- **THEN** `dCallDeviceSwitchedOn_` 为 true，当前音频设备切换为该分布式设备

#### Scenario: Celia通话抑制
- **WHEN** 前台通话为 celia call 时调用 `SwitchOnDCallDeviceAsync`
- **THEN** 直接返回，不创建切换线程

#### Scenario: 通话结束复位
- **WHEN** 通话全部结束触发 `DealDisconnectCall`
- **THEN** `dCallDeviceSwitchedOn_` 复位 false 且 `ClearConnectedDCallDevice`

### Requirement: source/sink角色协商与数据同步
系统 SHALL 由 `DistributedCommunicationManager::OnDeviceOnline` 依据对端 devRole（0 表示本端 sink）设置 `DistributedRole` 并按角色创建 sink/source 侧的 `DistributedDataController` 与开关控制器；source 端 `SaveLocalData` 缓存号码姓名/归属地并在收到 `DATA_REQ`/`CURRENT_DATA_REQ` 时应答 `DATA_RSP`/`CURRENT_DATA_RSP`，sink 端建连后主动 `SendDataQueryReq` 查询；`MUTE`(104)/`MUTE_RINGER`(102) 消息按 `DistributedMsgType` 双向同步。

#### Scenario: sink端建连查询
- **WHEN** 本端角色为 SINK 且会话 `OnConnected`
- **THEN** sink 控制器向对端发送数据查询请求，收到 `DATA_RSP` 后经 `UpdateCallName`/`UpdateCallLocation` 更新来话姓名与归属地

#### Scenario: 对端静音同步
- **WHEN** 对端经会话发来 msgType 为 MUTE(104) 且 mute=true 的 cJSON 消息
- **THEN** `HandleMuted` 调用 `CallControlManager::SetMuted(true)` 同步本端静音状态

#### Scenario: 对端全部离线
- **WHEN** `OnDeviceOffline` 后 `peerDevices_` 清空
- **THEN** `status_` 置 DISCONNECT、`role_` 置 UNKNOWN，`dataController_`/`devSwitchController_` 释放

### Requirement: softbus会话传输
系统 SHALL 由 `TransmissionManager` 创建 `ServerSession`/`ClientSession`（`SessionAdapter` 封装 `transport/socket.h`）：会话使用 `SESSION_NAME` "ohos.telephony.callmanager.distributed_communication"、`QOS_MIN_BW` 4*1024*1024；`ServerSession::Create` 监听、`ClientSession::Connect` 主动建连，`OnSessionBind`/`OnSessionShutdown` 维护 socket，消息经 `SendMsg`/`OnReceiveMsg` 分发到 `ISessionCallback`；`DistributedCommunicationManager` 另经 `InitExtWrapper` dlopen `libtelephony_ext_innerkits.z.so`（RegisterDistributedDevState/UnRegisterDistributedDevState/SwitchDistributedDevice）对接扩展能力。

#### Scenario: 服务端会话创建
- **WHEN** source 端调用 `TransmissionManager::CreateServerSession(callback)`
- **THEN** `ServerSession` 以 `SESSION_NAME` 创建 softbus 监听 socket，`OnBind` 后会话 `IsReady()` 为真

#### Scenario: 扩展库缺失
- **WHEN** dlopen("libtelephony_ext_innerkits.z.so") 失败
- **THEN** `RegDevCallbackWrapper`/`UnRegDevCallbackWrapper`/`SwitchDevWrapper` 返回 `TELEPHONY_ERROR`，不调用扩展函数指针

#### Scenario: dcall客户端SDK加载
- **WHEN** `DistributedCallProxy` 构造时 dlopen `libdistributed_call_client.z.so` 成功
- **THEN** `Init` 经 dlsym 符号 `DCALL_LOADER_GET_DCALL_CLIENT_HANDLER` 获取 `IDCallClient` 并完成初始化
