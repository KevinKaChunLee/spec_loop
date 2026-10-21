# 蓝牙通话（Bluetooth Call）Specification

## Purpose
描述 HMOS call_manager 当前的蓝牙 HFP 免提通话能力：向蓝牙侧 HFP AG 上报通话状态与通话明细、维护已连接蓝牙耳机设备、并向蓝牙宿主提供接听/挂断/保持/DTMF 等通话控制的 IPC 服务。源码落点：`telephony_call_manager/services/bluetooth/{include,src}`，含 `bluetooth_call_manager.cpp`（`BluetoothCallManager`，状态上报入口）、`bluetooth_connection.cpp`（`BluetoothConnection`，HFP 连接维护与 observer）、`bluetooth_call_service.cpp`（`BluetoothCallService`，控制服务）、`bluetooth_call_policy.cpp`（`BluetoothCallPolicy`，目标通话选取策略）、`bluetooth_call_stub.cpp`（`BluetoothCallStub`，IPC 分发）。编译开关：`ABILITY_BLUETOOTH_SUPPORT`——`callmanager.gni` 在 `global_parts_info.communication_bluetooth` 存在时定义该宏并依赖 `bluetooth:btframework`；未定义该宏时 `BluetoothConnection` 不再继承 `HandsFreeAudioGatewayObserver`，与蓝牙框架交互的代码退化为空实现。

## Requirements

### Requirement: HFP通话状态上报
系统 SHALL 在通话状态变化时由 `BluetoothCallManager::SendBtCallState` 将 numActive/numHeld/callState/number 先经 `CallAbilityReportProxy::ReportPhoneStateChange` 上报，再经 `BluetoothConnection::SendBtCallState` 调用 `Bluetooth::HandsFreeAudioGateway::GetProfile()->PhoneStateChanged` 推送给 HFP AG；`SendCallDetailsChange` 以相同方式调用 `CallDetailsChanged` 上报单通话明细；profile 为空时两者 MUST 返回 `TELEPHONY_ERROR`。

#### Scenario: 正常上报
- **WHEN** HFP AG profile 可用，调用 `SendBtCallState(1, 0, 5, "10086")`
- **THEN** `PhoneStateChanged` 以相同参数被调用，函数返回 `TELEPHONY_SUCCESS`

#### Scenario: 蓝牙框架不可用
- **WHEN** `HandsFreeAudioGateway::GetProfile()` 返回 nullptr
- **THEN** `SendBtCallState` 与 `SendCallDetailsChange` 均返回 `TELEPHONY_ERROR`，不发生任何 HFP 推送

#### Scenario: 蓝牙可用性查询
- **WHEN** 定义了 `ABILITY_BLUETOOTH_SUPPORT` 且 `mapConnectedBtDevices_` 非空
- **THEN** `BluetoothCallManager::IsBtAvailble` 经 `BluetoothConnection::IsBtAvailble` 返回 true；未定义宏或设备表为空时返回 false

### Requirement: 蓝牙设备连接监听
系统 SHALL 由 `BluetoothConnection::Init` 订阅 `BLUETOOTH_HOST_SYS_ABILITY_ID` 系统能力（`SystemAbilityListener`），经 `HandsFreeAudioGateway::GetProfile()->GetConnectedDevices` 拉取已连 HFP 设备并 `AddBtDevice` 记入 `mapConnectedBtDevices_`、经 `AudioDeviceManager::AddAudioDeviceList` 以 `DEVICE_BLUETOOTH_SCO` 类型注册；`OnConnectionStateChanged` 在 CONNECTED 时添加设备、DISCONNECTED 时移除设备。

#### Scenario: HFP设备连接成功
- **WHEN** observer 的 `OnConnectionStateChanged` 收到 state 为 `BTConnectState::CONNECTED` 的设备（含 macAddress/deviceName）
- **THEN** 该设备被 `AddBtDevice` 记入设备表，且 `AudioDeviceManager` 新增 `DEVICE_BLUETOOTH_SCO` 音频设备

#### Scenario: 蓝牙系统服务移除
- **WHEN** `SystemAbilityListener::OnRemoveSystemAbility` 收到 `BLUETOOTH_HOST_SYS_ABILITY_ID` 下线
- **THEN** 执行 `ResetBtConnection` 与 `ResetBtAudioDevicesList`；若当前音频设备为 `DEVICE_BLUETOOTH_SCO`，触发 `INIT_AUDIO_DEVICE` 事件重新初始化音频设备

### Requirement: 蓝牙通话控制服务
系统 SHALL 由 `BluetoothCallService`（继承 `BluetoothCallStub` 与 `BluetoothCallPolicy`）把蓝牙侧控制请求转为本端通话操作：`BluetoothCallStub` 按 `memberFuncMap_` 将 IPC code 分发到 `OnAnswerCall`/`OnRejectCall`/`OnHangUpCall`/`OnHoldCall`/`OnUnHoldCall`/`OnSwitchCall`/`OnStartDtmf` 等处理函数；`BluetoothCallPolicy` 各 XxxPolicy 用 `IsCallExist` 按通话状态选取 callId，选不到时 MUST 返回 `CALL_ERR_ILLEGAL_CALL_OPERATION`。

#### Scenario: 蓝牙侧接听来电
- **WHEN** 存在 `CALL_STATUS_INCOMING`（或 `CALL_STATUS_WAITING`）通话且蓝牙侧请求 AnswerCall
- **THEN** `AnswerCallPolicy` 返回该 callId，接听操作作用到该通话

#### Scenario: 无可操作通话
- **WHEN** 无 INCOMING/WAITING 通话时蓝牙侧请求 AnswerCall
- **THEN** `AnswerCallPolicy` 返回 `CALL_ERR_ILLEGAL_CALL_OPERATION`

#### Scenario: 通话列表查询
- **WHEN** 蓝牙侧经 stub 请求 `GetCurrentCallList(slotId)`
- **THEN** 返回由 `getCarrierCallInfoNum`（含 `GetVoipCallState`/`sendEventToVoip` 辅助）汇总的 `CallAttributeInfo` 列表
