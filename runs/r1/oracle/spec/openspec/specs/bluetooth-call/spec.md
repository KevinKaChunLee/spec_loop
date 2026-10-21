# 蓝牙通话（bluetooth-call）Specification

## Purpose
描述 `telephony_call_manager/services/bluetooth/` 的蓝牙通话模块组：`BluetoothCallManager`（HFP AG 状态上报）、`BluetoothCallService`/`BluetoothCallStub`（对外 IPC 接口与策略）、`BluetoothCallPolicy`（操作前置校验）、`BluetoothConnection`（HFP AG 连接与设备管理）。IPC 枚举落点：`interfaces/innerkits/bluetooth_call_ipc_interface_code.h`（`BluetoothCallInterfaceCode` 共 17 项）。编译开关：`ABILITY_BLUETOOTH_SUPPORT`（`BluetoothConnection` 以 `OHOS::Bluetooth::HandsFreeAudioGatewayObserver` 形态编译；宏关闭时为裸类）。

## Requirements

### Requirement: HFP AG 状态上报
系统 SHALL 由 `BluetoothCallManager::SendBtCallState(numActive, numHeld, callState, number)` 先经 `CallAbilityReportProxy::ReportPhoneStateChange` 上报框架层，再转发 `BluetoothConnection::SendBtCallState`→`Bluetooth::HandsFreeAudioGateway::GetProfile()->PhoneStateChanged(..., PHONE_NUMBER_TYPE = 0x81, ...)`；`SendCallDetailsChange(callId, callState)`→`CallDetailsChanged(callId, callState)`；`IsBtAvailble()` 仅在 `ABILITY_BLUETOOTH_SUPPORT` 下转发 `btConnection_->IsBtAvailble()`。
#### Scenario: 通话状态变化上报 HFP
- **WHEN** 通话状态经 `CallAbilityReportProxy::CallStateUpdated` 上报后触发 `SendCallDetailsChange`
- **THEN** 蓝牙 HFP AG 侧同步收到 `CallDetailsChanged(callId, callState)`

### Requirement: 对外接口与权限
系统 SHALL 由 `BluetoothCallStub` 把 17 个 `BluetoothCallInterfaceCode` 映射进 `memberFuncMap_`（descriptor 失配返回 `TELEPHONY_ERR_DESCRIPTOR_MISMATCH`），`BluetoothCallService : public BluetoothCallStub, public BluetoothCallPolicy` 每个对外方法先 `TelephonyPermission::CheckPermission`（控制类 `Permission::ANSWER_CALL`，查询类 `GET_TELEPHONY_STATE`，设备列表 `SET_TELEPHONY_STATE`）再过 Policy 取 callId，最后转 `CallControlManager`。
#### Scenario: 蓝牙侧接听
- **WHEN** 蓝牙侧经 `INTERFACE_BT_ANSWER_CALL` 请求接听
- **THEN** 权限与 `AnswerCallPolicy`（存在 INCOMING 或 WAITING 呼叫）通过后转 `CallControlManager::AnswerCall`；策略失败时改发 `EVENT_ANSWER_VOIP_CALL` 给 VoIP 侧

### Requirement: 通话状态聚合
系统 SHALL 由 `BluetoothCallService::GetCallState` 以 `getCarrierCallInfoNum` 统计各状态数量，融合 VoIP 在线状态（`GetVoipCallState`）后经 `BluetoothCallManager::SendBtCallState` 上报 HFP。
#### Scenario: 仅有保持通话时上报 IDLE
- **WHEN** `numHeld > 0` 且无活动通话
- **THEN** 向 HFP 上报的 callState 为 IDLE

### Requirement: HFP AG 连接与音频设备联动
系统 SHALL 由 `BluetoothConnection`（`DECLARE_DELAYED_SINGLETON`）在 `Init()` 经 samgr `SubscribeSystemAbility(BLUETOOTH_HOST_SYS_ABILITY_ID, statusChangeListener_)` 后 `Bluetooth::HandsFreeAudioGateway::GetProfile()->GetConnectedDevices` 逐个 `AddBtDevice` + `AudioDeviceManager::AddAudioDeviceList(macAddress, DEVICE_BLUETOOTH_SCO, deviceName)`；`OnConnectionStateChanged` 按连接/断开增删设备；蓝牙 SA 掉线时执行 `BluetoothCallConnection::HfpDisConnectedEndBtCall` + `ResetBtConnection` + `AudioDeviceManager::ResetBtAudioDevicesList`（当前设备为 `DEVICE_BLUETOOTH_SCO` 时补发 `AudioEvent::INIT_AUDIO_DEVICE`）。
#### Scenario: 蓝牙服务下线
- **WHEN** `OnRemoveSystemAbility` 收到蓝牙 host 服务下线
- **THEN** 结束蓝牙通话、重置连接状态并重建音频路由

### Requirement: 可穿戴蓝牙耳机地址
系统 SHALL 由 `GetWearBtHeadsetAddress()` 经 `GetDeviceProductType(cod, majorClass, majorMinorClass)` 与 `Bluetooth::BluetoothAudioManager::GetInstance().IsDeviceWearing(device)` 匹配 `MAJOR_AUDIO_VIDEO` 且 `AUDIO_VIDEO_HEADPHONES`/`AUDIO_VIDEO_WEARABLE_HEADSET` 的设备返回其地址。
#### Scenario: sink 端优先切蓝牙耳机
- **WHEN** 分布式 sink 角色收到新来话且佩戴中的蓝牙耳机在位
- **THEN** `DistributedSinkSwitchController::TrySwitchToBtHeadset` 以该地址切换音频输出
