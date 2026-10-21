# 互通通话（interoperable-call）Specification

## Purpose
描述 `telephony_call_manager/services/interoperable_call/` 的互通通话模块组（手表/车机与手机互通）：`InteroperableCommunicationManager`（设备发现与角色判定）、`InteroperableClientManager`/`InteroperableServerManager`（客户端/服务端）、`InteroperableDataController`（JSON 协议 slotId/静音同步）、`InteroperableDeviceObserver`（devicemanager 订阅）、`InteroperableSettingsHandler`（settingsdata 静音联动）。会话通路复用 `services/distributed_call/src/transmission/`（session 名 `ohos.telephony.callmanager.interoperable_communication`）。调用侧编译开关：`SUPPORT_MUTE_BY_DATABASE`（`call_manager_service.cpp`/`call_records_manager.cpp` 包裹 `InteroperableSettingsHandler` 调用，仅 `target_platform == "watch"` 时该 cpp 入编并定义宏；本能力内的 `interoperable_settings_handler.cpp` 即 watch 专属源文件）。

## Requirements

### Requirement: 设备发现与角色判定
系统 SHALL 由 `InteroperableDeviceObserver::Init()` 经 `DistributedHardware::DeviceManager::GetInstance().InitDeviceManager(PACKAGE_NAME, dmInitCallback)` + `RegisterDevStateCallback(PACKAGE_NAME, "", stateCallback)`（`PACKAGE_NAME = "ohos.telephony.callmanager"`）订阅设备上下线；`OnDeviceOnline` 以 `system::GetParameter("const.product.devicetype", "")` 与对端 devType（`0x0E` 手机 / `0x6D` 手表 / `0x83` 车机）判定 `InteroperableRole`（本机 wearable/car 对手机 → 客户端 `InteroperableClientManager`；对手机而言手表/车机 → 服务端 `InteroperableServerManager`）。
#### Scenario: 手表发现手机
- **WHEN** 本机 devicetype 为 wearable 且对端 devType 为 `0x0E`
- **THEN** 本机作为客户端创建 `InteroperableClientManager` 参与会话

### Requirement: 蓝牙通话 slotId 同步
系统 SHALL 由 `InteroperableCommunicationManager::GetBtCallSlotId(phoneNum)`：`GetBtSlotIdByPhoneNumber` 未命中时 `WaitForBtSlotId`（`BT_CALL_WAIT_SLOT_TIME = 2` 秒）再查后删除；`InteroperableDataController::HandleRequisitesData` 收到对端 `slotId` 后 `callPtr->SetAccountId(slotId)` + `CallAbilityReportProxy::ReportCallStateInfo`，查不到 call 时 `SaveBtSlotId` + `slotIdCv_.notify_all()`。
#### Scenario: 手机侧蓝牙去电先查 slotId
- **WHEN** 手机侧（server）收到手表去话（`PhoneOrWatchDial::WATCH_DIAL`）
- **THEN** `InteroperableClientManager::OnConnected` 直发 `SendRequisiteDataToPeer(GetAccountId(), GetAccountNumber())`；非手表拨号则发 `SendRequisiteDataQueryToPeer(phoneNum)` 查询

### Requirement: 互通静音联动
系统 SHALL 由 `InteroperableSettingsHandler` 以 DataShare 操作 `synergy_incoming_mute`/`call_mute_ringer` 两个 key（`SYNERGY_INCOMING_MUTE_URI`/`CALL_MUTE_RINGER_URI`，静音值 `"3"`）：`RegisterObserver()`（`SettingsDataShareHelper::RegisterToDataShare`）、`QueryMuteRinger()`、`RecoverMuteRinger()`、`SendMuteRinger()`；`InteroperableRecvObserver : AAFwk::DataAbilityObserverStub` 的 `OnChange()` 查到 `"3"` 时执行 `CallControlManager::MuteRinger()` + `RecoverMuteRinger`。
#### Scenario: 对端手机静音来话
- **WHEN** 手机侧把 `call_mute_ringer` 写为 `"3"`
- **THEN** 手表侧 `InteroperableRecvObserver::OnChange` 触发 `MuteRinger` 并随后 `RecoverMuteRinger` 复位
