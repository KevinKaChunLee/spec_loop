# Bluetooth Call Specification

## Purpose
描述 HMOS `telephony_call_manager` 中蓝牙 HFP 通话服务侧（`services/bluetooth/src/` 下 `bluetooth_call_manager.cpp`、`bluetooth_call_policy.cpp`、`bluetooth_call_service.cpp`、`bluetooth_call_stub.cpp`、`bluetooth_connection.cpp`）的移植前现状：`BluetoothCallManager` 作为门面向通话链路上报蓝牙通话状态，`BluetoothConnection` 维护 HFP 连接与 SCO 音频设备表，`BluetoothCallService`（继承 `BluetoothCallStub` 与 `BluetoothCallPolicy`）提供蓝牙侧来电去电控制面。本能力不含 `frameworks/native` 的 `bluetooth_call_client`/`bluetooth_call_proxy`/`IBluetoothCall`，也不含 `services/telephony_interaction/` 的 `BluetoothCallConnection`。蓝牙特性由 `ABILITY_BLUETOOTH_SUPPORT` 宏门控：`callmanager.gni` 在 `global_parts_info.communication_bluetooth` 部件存在时定义该宏并依赖 `bluetooth:btframework`；`services/bluetooth` 内 `#ifdef ABILITY_BLUETOOTH_SUPPORT` 场点位于 `bluetooth_call_manager.cpp`（`IsBtAvailble`）与 `bluetooth_connection.cpp`（`Init`/`IsBtAvailble`/`SendBtCallState`/`SendCallDetailsChange`/`ResetBtConnection`/`RegisterObserver`/`AddBtDevice` 等实现体）。

## Requirements

### Requirement: 蓝牙连接初始化与系统能力订阅
系统 SHALL 由 `BluetoothConnection::Init` 创建 `SystemAbilityListener` 并经 samgr `SubscribeSystemAbility` 订阅 `BLUETOOTH_HOST_SYS_ABILITY_ID`，随后经 `Bluetooth::HandsFreeAudioGateway::GetProfile()->GetConnectedDevices` 枚举已连接设备，逐个 `AddBtDevice` 记入 `mapConnectedBtDevices_` 并调用 `AudioDeviceManager::AddAudioDeviceList(macAddress, AudioDeviceType::DEVICE_BLUETOOTH_SCO, deviceName)` 注册为可选音频设备。蓝牙 SA 上下线 SHALL 由 `SystemAbilityListener::OnAddSystemAbility`/`OnRemoveSystemAbility` 处理：上线时 `RegisterObserver` 向 HFG profile 注册观察者；下线时调用 `ResetBtConnection` 清空设备表、`AudioDeviceManager::ResetBtAudioDevicesList`，且若当前音频设备为 `DEVICE_BLUETOOTH_SCO` 则 `ProcessEvent(AudioEvent::INIT_AUDIO_DEVICE)` 重建音频设备。

#### Scenario: 初始化收集已连接设备
- **WHEN** `Init` 执行且 `GetConnectedDevices` 返回非空设备列表
- **THEN** 每个 MAC 地址均进入 `mapConnectedBtDevices_` 且以 `DEVICE_BLUETOOTH_SCO` 加入音频设备列表，`IsBtAvailble` 返回 true

#### Scenario: 蓝牙服务下线
- **WHEN** `OnRemoveSystemAbility` 收到 `BLUETOOTH_HOST_SYS_ABILITY_ID` 移除事件且当前音频设备为 `DEVICE_BLUETOOTH_SCO`
- **THEN** 设备表清空、蓝牙音频设备列表重置，并触发 `AudioEvent::INIT_AUDIO_DEVICE`

### Requirement: HFP 通话状态上报
系统 SHALL 由 `BluetoothCallManager::SendBtCallState` 先经 `CallAbilityReportProxy::ReportPhoneStateChange` 上报，再转发 `BluetoothConnection::SendBtCallState`，后者在 `ABILITY_BLUETOOTH_SUPPORT` 打开时调用 `HandsFreeAudioGateway` profile 的 `PhoneStateChanged(numActive, numHeld, callState, number, PHONE_NUMBER_TYPE, nickName)`；`SendCallDetailsChange` 同样经 profile 的 `CallDetailsChanged(callId, callState)` 上报。`BluetoothCallManager::IsBtAvailble` 在宏关闭时 SHALL 恒返回 false，宏打开时以 `mapConnectedBtDevices_` 是否非空为准。

#### Scenario: 宏关闭时可用性恒假
- **WHEN** `ABILITY_BLUETOOTH_SUPPORT` 未定义且调用 `BluetoothCallManager::IsBtAvailble`
- **THEN** 返回 false，不触碰 profile

#### Scenario: 状态上报透传
- **WHEN** `SendBtCallState(1, 0, CALL_STATUS_INCOMING, "123")` 在宏打开且 profile 有效时调用
- **THEN** `PhoneStateChanged` 收到相同参数，函数返回 `TELEPHONY_SUCCESS`

### Requirement: 蓝牙设备连接变化处理
系统 SHALL 在 `BluetoothConnection::OnConnectionStateChanged` 中按状态分发：`Bluetooth::BTConnectState::CONNECTED` 时 `AddAudioDeviceList` + `AddBtDevice`，`DISCONNECTED` 时 `RemoveAudioDeviceList` + `RemoveBtDevice`。`OnVirtualDeviceChanged` SHALL 按 `VIRTUAL_DEVICE_ADD`/`VIRTUAL_DEVICE_REMOVE` 处理虚拟设备，其中 REMOVE 仅在 `GetDeviceState` 确认设备非 CONNECTED 时才移除。`GetWearBtHeadsetAddress` SHALL 遍历已连设备，仅当 `BluetoothAudioManager::IsDeviceWearing` 为真且设备 CoD 为 `MAJOR_AUDIO_VIDEO` 且 `AUDIO_VIDEO_HEADPHONES`/`AUDIO_VIDEO_WEARABLE_HEADSET` 时返回该地址，否则返回空串。

#### Scenario: 设备断开
- **WHEN** `OnConnectionStateChanged` 收到 DISCONNECTED
- **THEN** 该地址从 `mapConnectedBtDevices_` 与音频设备列表中同时移除

#### Scenario: 虚拟设备移除但物理链路仍在
- **WHEN** `OnVirtualDeviceChanged` 收到 `VIRTUAL_DEVICE_REMOVE` 且 `GetDeviceState` 返回 CONNECTED
- **THEN** 不移除该设备

#### Scenario: 无佩戴耳机
- **WHEN** 所有已连设备均 `IsDeviceWearing` 为假时调用 `GetWearBtHeadsetAddress`
- **THEN** 返回空字符串

### Requirement: 蓝牙侧控制面 IPC 分发
系统 SHALL 由 `BluetoothCallStub::OnRemoteRequest` 先比对 `GetDescriptor` 与 `data.ReadInterfaceToken`，不匹配返回 `TELEPHONY_ERR_DESCRIPTOR_MISMATCH`；匹配时经 `memberFuncMap_`（以 `BluetoothCallInterfaceCode::INTERFACE_BT_*` 为键）分发到 `OnAnswerCall`/`OnRejectCall`/`OnHangUpCall`/`OnGetBtCallState`/`OnHoldCall`/`OnUnHoldCall`/`OnSwitchCall`/`OnCombineConference`/`OnSeparateConference`/`OnKickOutFromConference`/`OnStartDtmf`/`OnStopDtmf`/`OnGetCurrentCallList`/`OnAddAudioDeviceList`/`OnRemoveAudioDeviceList`/`OnResetNearlinkDeviceList`/`OnResetBtHearingAidDeviceList`，未知 code 回落 `IPCObjectStub::OnRemoteRequest`。`OnGetCurrentCallList` SHALL 转发 `BluetoothCallService::GetCurrentCallList`：slotId 小于 0 返回 `GetAllCallInfoList(false)`，否则返回 `GetCallInfoList(slotId, false)`。

#### Scenario: 描述符不匹配
- **WHEN** 请求 `MessageParcel` 的接口 token 与 `BluetoothCallStub::GetDescriptor` 不一致
- **THEN** 直接返回 `TELEPHONY_ERR_DESCRIPTOR_MISMATCH`，不进入业务处理

#### Scenario: 全量通话列表查询
- **WHEN** `GetCurrentCallList(-1)` 被调用且权限校验通过
- **THEN** 返回全部通话（含 VOIP）的 `CallAttributeInfo` 列表

### Requirement: 控制操作前置策略判定
系统 SHALL 由 `BluetoothCallPolicy` 在每个控制操作前按通话状态判定合法性：`AnswerCallPolicy`/`RejectCallPolicy` 要求存在 `CALL_STATUS_INCOMING` 或 `CALL_STATUS_WAITING`；`HoldCallPolicy` 要求存在 `CALL_STATUS_ACTIVE`；`UnHoldCallPolicy` 在仅存在 `CALL_STATUS_ACTIVE` 时失败、存在 `CALL_STATUS_HOLDING` 时成功；`HangUpPolicy` 依次接受 `HasActivedCallExist`、`CALL_STATUS_DIALING`、`CALL_STATUS_ALERTING`、`CALL_STATUS_INCOMING`、`CALL_STATUS_WAITING`、`CALL_STATUS_HOLDING`；`SwitchCallPolicy`/`CombineConferencePolicy` 要求同时存在 ACTIVE 与 HOLDING；`StartDtmfPolicy` 接受 ACTIVE/ALERTING/DIALING/HOLDING；`SeparateConferencePolicy`/`KickOutFromConferencePolicy` 要求存在 `TEL_CONFERENCE_ACTIVE` 或 `TEL_CONFERENCE_HOLDING` 的会议。判定失败 SHALL 返回 `CALL_ERR_ILLEGAL_CALL_OPERATION`。

#### Scenario: 无可接听的来电时接听
- **WHEN** 通话列表中没有 INCOMING/WAITING 状态的通话时执行 `AnswerCall`
- **THEN** `AnswerCallPolicy` 返回 `CALL_ERR_ILLEGAL_CALL_OPERATION`，`AnswerCall` 不调用 `CallControlManager::AnswerCall`

#### Scenario: 单激活通话时取消保持
- **WHEN** 仅有 `CALL_STATUS_ACTIVE` 通话时执行 `UnHoldCall`
- **THEN** `UnHoldCallPolicy` 返回 `CALL_ERR_ILLEGAL_CALL_OPERATION`

#### Scenario: 非会议通话时请出会议
- **WHEN** 不存在 `TEL_CONFERENCE_ACTIVE`/`TEL_CONFERENCE_HOLDING` 会议时执行 `KickOutFromConference`
- **THEN** `KickOutFromConferencePolicy` 返回 `CALL_ERR_ILLEGAL_CALL_OPERATION`

### Requirement: 控制操作执行与状态汇总
系统 SHALL 由 `BluetoothCallService` 在策略判定通过后调用 `CallControlManager` 对应接口（`AnswerCall`/`RejectCall`/`HangUpCall`/`HoldCall`/`UnHoldCall`/`SwitchCall`/`CombineConference`/`SeparateConference`/`KickOutFromConference`/`StartDtmf`/`StopDtmf`）。`GetCallState` SHALL 经 `getCarrierCallInfoNum` 汇总 `GetCallNum` 各状态计数得到 numActive/numHeld，蜂窝侧无激活通话且存在 VOIP 通话时再由 `GetVoipCallState` 合并 VOIP 状态，最终经 `BluetoothCallManager::SendBtCallState` 下发。`AddAudioDeviceList`/`RemoveAudioDeviceList` SHALL 仅接受 `DEVICE_NEARLINK` 或 `DEVICE_BLUETOOTH_HEARING_AID` 类型，否则返回 `TELEPHONY_ERR_ARGUMENT_INVALID`。

#### Scenario: 仅有 VOIP 激活通话时获取通话状态
- **WHEN** 蜂窝侧无 ACTIVE 通话且 VOIP 属性为 `CALL_STATUS_ACTIVE` 时调用 `GetCallState`
- **THEN** numActive 上报为 1，结果经 HFG `PhoneStateChanged` 下发

#### Scenario: 非法音频设备类型
- **WHEN** `AddAudioDeviceList` 收到 `DEVICE_BLUETOOTH_SCO` 类型
- **THEN** 返回 `TELEPHONY_ERR_ARGUMENT_INVALID`，不修改音频设备列表
