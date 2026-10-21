# 跨设备互通通话（Interoperable Call）Specification

## Purpose
描述 HMOS call_manager 当前的跨设备互通通话能力：手表/车机与手机之间的互通通信管理——基于 device_manager 的设备观察、按本机设备类型判定 PHONE/OTHERS 角色、经 softbus 会话同步静音/来电要件数据与蓝牙通话 slotId、手表侧经 DataShare 设置数据库联动静音。源码落点：`telephony_call_manager/services/interoperable_call/{include,src}`：`interoperable_communication_manager.cpp`（`InteroperableCommunicationManager`，角色判定与通话状态回调）、`interoperable_device_observer.cpp`（`InteroperableDeviceObserver`/`DmStateCallback`，device_manager 注册）、`interoperable_data_controller.cpp`（`InteroperableDataController`，消息收发与 slotId 管理）、`interoperable_client_manager.cpp`（`InteroperableClientManager`，OTHERS 侧客户端）、`interoperable_server_manager.cpp`（`InteroperableServerManager`，PHONE 侧服务器）、`interoperable_settings_handler.cpp`（`InteroperableSettingsHandler`，DataShare 静音设置联动）。编译开关：无专属能力宏；`callmanager.gni` 中仅 `interoperable_settings_handler.cpp` 在 `target_platform == "watch"` 时加入 `call_manager_sources`，并同时定义 `SUPPORT_MUTE_BY_DATABASE`，其余文件无条件编译；依赖 `device_manager:devicemanagersdk`、`dsoftbus:softbus_client` 等。

## Requirements

### Requirement: 设备观察与角色判定
系统 SHALL 由 `InteroperableDeviceObserver::Init` 以 `PACKAGE_NAME`("ohos.telephony.callmanager") 调用 `DistributedHardware::DeviceManager` 的 `InitDeviceManager` 与 `RegisterDevStateCallback` 注册 `DmStateCallback`；`DmStateCallback::OnDeviceOnline`/`OnDeviceOffline` 转发给 `InteroperableCommunicationManager`；`OnDeviceOnline` 依据 `DmDeviceInfo.deviceTypeId` 与本机 `const.product.devicetype` 系统参数判定角色：对端 0x0E（手机）且本机 wearable/car 时置 `InteroperableRole::OTHERS` 并创建 `InteroperableClientManager`，对端 0x6D（手表）/0x83（车机）时置 PHONE 并创建 `InteroperableServerManager`；非互通设备 MUST 直接返回不做处理；对端全部离线时角色复位 UNKNOWN、`dataController_` 释放。

#### Scenario: 手表配对手机上线
- **WHEN** 本机 `const.product.devicetype` 为 "wearable"，deviceTypeId 为 0x0E 的手机上线
- **THEN** `role_` 置 OTHERS，`dataController_` 创建为 `InteroperableClientManager`，networkId 记入 `peerDevices_`

#### Scenario: 非互通设备上线
- **WHEN** 对端 deviceTypeId 不满足 0x0E/0x6D/0x83 的角色组合条件
- **THEN** 记录错误日志并直接返回，不更新 `peerDevices_`、不创建控制器

#### Scenario: 对端全部离线
- **WHEN** 最后一台互通设备 `OnDeviceOffline` 处理完成
- **THEN** `peerDevices_` 为空，`role_` 复位 `InteroperableRole::UNKNOWN`，`dataController_` 释放置空

#### Scenario: 重复注册状态回调
- **WHEN** `RegisterDevStatusCallback` 传入已在 `callbacks_` 列表中的回调
- **THEN** 记录日志并直接返回，不重复入列

### Requirement: 互通消息与静音同步
系统 SHALL 由 `InteroperableDataController::OnReceiveMsg` 解析 cJSON 消息（上限 `INTEROPERABLE_MAX_RECV_DATA_LEN`=2048）按 dataType 分发：MUTE(104)→`HandleMuted` 调用 `CallControlManager::SetMuted`、MUTE_RINGER(102)→`HandleMuteRinger` 调用 `CallControlManager::MuteRinger`、REQUISITES(0)→`HandleRequisitesData` 保存 slotId，其余转 `HandleSpecificMsg`；`SetMuted`/`MuteRinger` 经会话向对端发送对应消息；超长数据 MUST 直接丢弃不解析。

#### Scenario: 收到对端静音请求
- **WHEN** 会话收到 dataType=104 且 mute=true 的消息
- **THEN** 本端执行 `CallControlManager::SetMuted(true)`

#### Scenario: 超长消息丢弃
- **WHEN** `OnReceiveMsg` 收到 dataLen > 2048 的数据
- **THEN** 直接返回，不做 JSON 解析

#### Scenario: 向对端发送静音
- **WHEN** 会话就绪时调用 `SetMuted(true)`
- **THEN** 经 `CreateMuteMsg` 构造 dataType=104 的 JSON 并由 `SessionAdapter::SendMsg` 发送

### Requirement: 蓝牙通话slotId同步
系统 SHALL 由 `GetBtCallSlotId` 按 phoneNum 查询对端同步来的蓝牙通话 slotId：未查到时经 `WaitForBtSlotId` 等待对端 `DATA_TYPE_QUERY_REQUISITES_DATA`(105) 应答，查询成功后 `DeleteBtSlotIdByPhoneNumber` 删除缓存；无控制器时 MUST 直接返回 `BT_CALL_INVALID_SLOT`(-1)。

#### Scenario: 首次查询未命中
- **WHEN** `GetBtCallSlotId("13800138000")` 且 `slotIdMap_` 尚无该号码条目
- **THEN** 触发等待对端应答，拿到 slotId 后返回该值并删除缓存条目

#### Scenario: 无互通会话
- **WHEN** `dataController_` 为 nullptr 时调用 `GetBtCallSlotId`
- **THEN** 直接返回 `BT_CALL_INVALID_SLOT`

### Requirement: 客户端建连与要件数据交互
系统 SHALL 由 `InteroperableClientManager`（OTHERS 侧）以来电触发互通：`CallCreated` 记录 `phoneNum_` 并经 `TransmissionManager::CreateClientSession` 以 `SOFTNET_SESSION_NAME`("ohos.telephony.callmanager.interoperable_communication")、`QOS_BW_BT` 建连；会话 `OnConnected` 后按通话方向分流：手表侧去电（`GetPhoneOrWatchDial` 为 WATCH_DIAL）`SendRequisiteDataToPeer` 主动上报 slotId 与号码，否则 `SendRequisiteDataQueryToPeer` 向对端查询；通话结束 `OnCallDestroyed` MUST 断开会话并清空 `phoneNum_`。

#### Scenario: 来电触发查询
- **WHEN** OTHERS 端收到 INCOMING/WAITING 来电且会话已建连
- **THEN** 经 `SendRequisiteDataQueryToPeer` 向手机侧发起要件数据查询

#### Scenario: 手表侧去电上报
- **WHEN** 会话连接时通话为呼出方向且 `GetPhoneOrWatchDial()` 为 WATCH_DIAL
- **THEN** 经 `SendRequisiteDataToPeer(callPtr->GetAccountId(), callPtr->GetAccountNumber())` 向手机侧上报

#### Scenario: 通话结束断连
- **WHEN** 通话迁移到 DISCONNECTED 触发 `OnCallDestroyed` 且会话存在
- **THEN** 断开会话、`phoneNum_` 清空

### Requirement: 手表侧设置数据库静音联动
系统 SHALL（仅 `target_platform == "watch"` 编入的 `interoperable_settings_handler.cpp`）由 `InteroperableSettingsHandler::RegisterObserver` 以 `SYNERGY_INCOMING_MUTE_URI` 向 `SettingsDataShareHelper` 注册 `InteroperableRecvObserver`；数据库 `synergy_incoming_mute` 键值变为 "3" 时 `OnChange` 调用 `CallControlManager::MuteRinger` 并 `RecoverMuteRinger` 复位为 "0"；`SendMuteRinger` 将 `call_mute_ringer` 键写为 "3"。

#### Scenario: 数据库变更触发静音
- **WHEN** 已注册 observer 且 `synergy_incoming_mute` 键值更新为 "3"
- **THEN** `InteroperableRecvObserver::OnChange` 调用 `CallControlManager::MuteRinger` 并将该键恢复为 "0"

#### Scenario: 重复注册观察者
- **WHEN** `RegisterObserver` 在 `recvObserver_` 已存在时再次调用
- **THEN** 直接返回，不重复注册

#### Scenario: 通知手机侧静音
- **WHEN** 调用 `SendMuteRinger`
- **THEN** `call_mute_ringer` 键经 DataShare 更新为 "3"
