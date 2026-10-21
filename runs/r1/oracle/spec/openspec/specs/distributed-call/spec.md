# 分布式通话（distributed-call）Specification

## Purpose
描述 `telephony_call_manager/services/distributed_call/` 的分布式通话模块组：`DistributedCallManager`（dPhone/dPad/dCar 音频设备接入，SA `DISTRIBUTED_CALL_SOURCE_SA_ID = 9855`）、`DistributedCallProxy`（dlopen `libdistributed_call_client.z.so`）、`transmission/`（softbus socket 通路：`TransmissionManager`/`SessionAdapter`/`ServerSession`/`ClientSession`）、`distributed_communication/`（`DistributedCommunicationManager`/`DistributedDeviceObserver`（SA `DISTRIBUTED_COMMUNICATION_CALL_SA_ID = 66198`）/`DistributedDataController` 系/`DistributedDeviceSwitchController` 系，经 dlopen `libtelephony_ext_innerkits.z.so` 注册设备回调）。编译开关：`ABILITY_BLUETOOTH_SUPPORT`（sink/source 端 `DcCallHfpListener`/`DcCallSourceHfpListener` 的 `OnHfpStackChanged` 监听）。

## Requirements

### Requirement: 分布式音频设备接入
系统 SHALL 由 `DistributedCallManager::Init()` 订阅 SA 9855，`OnDCallSystemAbilityAdded` 创建 `DistributedCallProxy` 并 `RegisterDeviceCallback("telephony", listener)` + `GetOnlineDeviceList`；设备增删经 `AddDCallDevice/RemoveDCallDevice` 以 `CreateDAudioDevice`（devId/devName/devType 组 JSON 存入 `AudioDevice.address`）同步进 `AudioDeviceManager`；`SwitchOnDCallDeviceSync`/`SwitchOffDCallDeviceSync`/`SwitchOnDCallDeviceAsync` 经 `dcallProxy_->SwitchDevice(devId, DCALL_SWITCH_DEVICE_TYPE_SINK/SOURCE)`，`isCeliaCall()`（`foregroundCall->GetCeliaCallType()`）时放弃切换。
#### Scenario: 分布式设备上线成为音频设备
- **WHEN** 对端分布式设备经 `DistributedCallDeviceListener` 上线
- **THEN** 该设备以 `DEVICE_DISTRIBUTED_PHONE/PAD/AUTOMOTIVE` 形态加入 `AudioDeviceManager` 设备列表

### Requirement: dcall 客户端 dlopen
系统 SHALL 由 `DistributedCallProxy` 经 `dlopen("libdistributed_call_client.z.so", RTLD_LAZY | RTLD_NODELETE)` + `dlsym("GetDCallClientInstance")` 获取 `IDCallClient*`，封装 `Init/UnInit/SwitchDevice/GetOnlineDeviceList/RegisterDeviceCallback/UnRegisterDeviceCallback/GetDCallDeviceInfo/IsSelectVirtualModem`。
#### Scenario: ext 库不可用
- **WHEN** `libdistributed_call_client.z.so` 加载或符号解析失败
- **THEN** 分布式通话设备接入整体不生效（代理方法走空返回）

### Requirement: softbus 会话通路
系统 SHALL 由 `TransmissionManager`（`DECLARE_DELAYED_SINGLETON`）经 `SessionAdapter`（`ISocketListener`：`OnBind/OnShutdown/OnBytes/OnError`，`PACKET_NAME = "ohos.telephony.callmanager"`，`SESSION_NAME = "ohos.telephony.callmanager.distributed_communication"`，DATA_TYPE_BYTES，QOS 限 `QOS_MAX_LATENCY = 10000`）提供 `CreateServerSession`（`Socket` + `Listen`）/`CreateClientSession`（`Socket` + `BindAsync`）与 `SendMsg`（`SendBytes`）。
#### Scenario: 建立分布式通信会话
- **WHEN** sink/source 角色需要同步联系人名或归属地
- **THEN** 经对应端 session 以 JSON 消息（`DistributedMsgType` 的 `DATA_REQ/DATA_RSP/CURRENT_DATA_REQ/CURRENT_DATA_RSP/MUTE/MUTE_RINGER`）交互

### Requirement: 角色化数据同步与远端静音
系统 SHALL 由 `DistributedCommunicationManager : CallStateListenerBase`（`InitExtWrapper` dlopen `libtelephony_ext_innerkits.z.so`，`dlsym` `RegisterDistributedDevState/UnRegisterDistributedDevState/SwitchDistributedDevice`）按 `DistributedRole::SINK/SOURCE` 创建 `DistributedDataSinkController`/`DistributedDataSourceController` 与开关控制器；`ProcessCallInfo(call, type)` 按角色路由 NAME/LOCATION 同步；收到 `MUTE` 时 `CallControlManager::SetMuted`、`MUTE_RINGER` 时 `MuteRinger()`；`NewCallCreated` 仅处理 `TYPE_IMS/TYPE_CS`，sink 角色先 `DistributedSinkSwitchController::TrySwitchToBtHeadset()`。
#### Scenario: 对端请求静音
- **WHEN** source 端收到对端 `MUTE` 消息
- **THEN** 本端执行 `CallControlManager::SetMuted` 同步静音状态

#### Scenario: sink 端来话先切蓝牙耳机
- **WHEN** sink 角色本机产生新来话
- **THEN** 先经 `TrySwitchToBtHeadset`（`BluetoothConnection::GetWearBtHeadsetAddress()`）尝试切到佩戴中的蓝牙耳机
