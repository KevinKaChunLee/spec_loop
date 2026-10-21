# Interoperable Call Specification

## Purpose
描述 HMOS `telephony_call_manager` 中多设备协同通话（互信互联，手表/车机与手机协同）的移植前现状，落点 `services/interoperable_call/src/` 下 `interoperable_communication_manager.cpp`、`interoperable_device_observer.cpp`、`interoperable_client_manager.cpp`、`interoperable_server_manager.cpp`、`interoperable_data_controller.cpp`：手机侧作为服务端、手表/车机侧作为客户端，通过软总线会话（会话名 `ohos.telephony.callmanager.interoperable_communication`，QoS `QOS_BW_BT`）同步静音状态与来电卡槽信息（btCallSlotId）。`interoperable_settings_handler.cpp` 仅在 GN `target_platform == "watch"` 时由 `callmanager.gni` 编入并配套定义 `SUPPORT_MUTE_BY_DATABASE`（该宏的 `#ifdef` 场点位于 `call_manager_service.cpp` 与 `call_records_manager.cpp`，不在本目录）；其余五文件在所有平台编入。本能力经 `call_control_manager.cpp`（`AddOneObserver(InteroperableCommunicationManager)`）与 `call_manager_service.cpp`（`GetBtCallSlotId`/`SetMuted`/`MuteRinger`）接入主流程。

## Requirements

### Requirement: 设备发现与角色判定
系统 SHALL 由 `InteroperableCommunicationManager::OnDeviceOnline` 基于对端 `DmDeviceInfo` 判定协同角色：对端 devType 为 0x0E（手机）且本机 `const.product.devicetype` 为 wearable/car 时本机为 `InteroperableRole::OTHERS`（客户端）；对端 devType 为 0x6D（手表）或 0x83（车机）时本机为 `InteroperableRole::PHONE`（服务端）；其余组合忽略。角色判定后 SHALL 按角色惰性创建 `InteroperableClientManager` 或 `InteroperableServerManager` 作为 `dataController_`，登记 `peerDevices_` 并经 `InteroperableDeviceObserver::OnDeviceOnline` 通知。`OnDeviceOffline` SHALL 在最后一个对端离线后复位角色与 `dataController_`。`InteroperableDeviceObserver::Init` SHALL 经 `DistributedHardware::DeviceManager` 以 `PACKAGE_NAME`（"ohos.telephony.callmanager"）执行 `InitDeviceManager` 与 `RegisterDevStateCallback`。

#### Scenario: 手表本机连上手机
- **WHEN** 本机 `const.product.devicetype` 为 wearable 且对端 devType 为 0x0E 上线
- **THEN** 本机角色置为 `OTHERS`，创建 `InteroperableClientManager` 作为数据控制器

#### Scenario: 手机侧手表上线
- **WHEN** 对端 devType 为 0x6D 的设备上线
- **THEN** 本机角色置为 `PHONE`，创建 `InteroperableServerManager` 作为数据控制器

#### Scenario: 非协同设备上线
- **WHEN** 对端 devType 既非 0x0E 也非 0x6D/0x83（本机亦非 wearable/car）
- **THEN** 忽略该设备，不创建数据控制器

#### Scenario: 全部对端离线
- **WHEN** `peerDevices_` 中最后一个设备离线
- **THEN** 角色复位为 `UNKNOWN`，`dataController_` 释放

### Requirement: 协同通话状态联动
系统 SHALL 由 `InteroperableCommunicationManager::CallStateUpdated` 在协同对端存在时联动：本端来话（转 `CALL_STATUS_INCOMING`）且角色非 `PHONE` 时经 `dataController_->OnCallCreated(call, peerDevices_.front())` 发起连接与数据同步；通话断开（`CALL_STATUS_DISCONNECTED`/`DISCONNECTING`）时经 `OnCallDestroyed` 断开会话；`SetMuted`/`MuteRinger` SHALL 在 `dataController_` 存在时转发静音与静默响铃指令。

#### Scenario: 客户端本端来话
- **WHEN** 角色为 `OTHERS`、`peerDevices_` 非空且本端通话转 `CALL_STATUS_INCOMING`
- **THEN** 对首个对端设备发起 `OnCallCreated`，建立客户端会话

#### Scenario: 手机本端来话不外发
- **WHEN** 角色为 `PHONE` 且本端通话转 `CALL_STATUS_INCOMING`
- **THEN** 不调用 `OnCallCreated`，不建立会话

#### Scenario: 协同通话结束
- **WHEN** 协同通话转 `CALL_STATUS_DISCONNECTED`
- **THEN** `OnCallDestroyed` 被调用，客户端断开并释放会话

### Requirement: 客户端会话管理
系统 SHALL 由 `InteroperableClientManager::CallCreated` 记录本端呼出号码 `phoneNum_` 并经 `TransmissionManager::CreateClientSession` 创建会话后 `Connect(networkId, SOFTNET_SESSION_NAME, SOFTNET_SESSION_NAME, QOS_BW_BT)`，对 `CALL_STATUS_INCOMING`/`CALL_STATUS_WAITING` 通话额外 `SendRequisiteDataQueryToPeer` 查询对端卡槽。`OnConnected` SHALL 判断：`CallDirection::CALL_DIRECTION_OUT` 且 `PhoneOrWatchDial::WATCH_DIAL` 的呼出经 `SendRequisiteDataToPeer(callPtr->GetAccountId(), callPtr->GetAccountNumber())` 上报本端卡槽，否则向对端发起 requisite 查询。

#### Scenario: 手表侧拨打电话
- **WHEN** 手表本端呼出（`WATCH_DIAL`）且会话连接成功
- **THEN** 向手机端发送含本端 slotId 与号码的 requisite 数据消息

#### Scenario: 手表侧来电
- **WHEN** 手表本端来话且会话连接成功
- **THEN** 向手机端发起 requisite 数据查询请求

### Requirement: 服务端会话管理
系统 SHALL 由 `InteroperableServerManager::OnDeviceOnline` 经 `CreateServerSession` 创建服务端会话并 `Create(SOFTNET_SESSION_NAME, QOS_BW_BT)` 监听；`OnDeviceOffline` 时 `Destroy` 会话。`HandleSpecificMsg` SHALL 处理 `InteroperableMsgType::DATA_TYPE_QUERY_REQUISITES_DATA`：经 `OnQueryRequisitesDataMsgReceived` 按消息中号码 `CallObjectManager::GetOneCallObject(phoneNum)` 找到通话后 `SendRequisiteDataToPeer` 回发本端卡槽；`OnCallDestroyed` SHALL `ClearBtSlotId` 清空已缓存的对端卡槽表。

#### Scenario: 手机侧收到卡槽查询
- **WHEN** 服务端会话收到 `DATA_TYPE_QUERY_REQUISITES_DATA` 且号码能匹配到本端通话
- **THEN** 回发含本端 slotId 与号码的 requisite 数据消息

#### Scenario: 号码查无通话
- **WHEN** 查询消息中的号码在本端无对应通话
- **THEN** 不回发数据消息

### Requirement: 卡槽数据控制与一次性查询语义
系统 SHALL 由 `InteroperableDataController` 以 cJSON 消息（`INTEROPERABLE_ITEM_PHONE_NUMBER`/`INTEROPERABLE_ITEM_SLOT`/`INTEROPERABLE_ITEM_CALL_TYPE`）收发 requisite 数据：收到时 `HandleRequisitesData` 解析并 `SaveBtSlotId(phoneNum, slotId)` 缓存；`GetBtCallSlotId` SHALL 实现查询-等待-删除的一次性语义：先查 `GetBtSlotIdByPhoneNumber`，未收到时 `WaitForBtSlotId` 等待后重查，最终 `DeleteBtSlotIdByPhoneNumber` 删除已查记录，查不到返回 `BT_CALL_INVALID_SLOT`。`SetMuted`/`MuteRinger` SHALL 组 `CreateMuteMsg`/`CreateMuteRingerMsg` 消息经会话发送。

#### Scenario: 拨号前获取协同卡槽
- **WHEN** `GetBtCallSlotId(phoneNum)` 且该号码的 slotId 已缓存
- **THEN** 返回缓存 slotId 并删除该缓存记录（下次查询需重新同步）

#### Scenario: 对端卡槽尚未同步
- **WHEN** `GetBtCallSlotId(phoneNum)` 且缓存未命中且等待后仍无数据
- **THEN** 返回 `BT_CALL_INVALID_SLOT`

#### Scenario: 远端静音指令
- **WHEN** 会话收到 mute 消息（`HandleMuted`）
- **THEN** 按消息内容执行本端静音状态同步

### Requirement: watch 平台数据库静音联动
系统 SHALL 在 `target_platform == "watch"` 编入 `InteroperableSettingsHandler`：`RegisterObserver` 对 `synergy_incoming_mute` 数据项注册 `InteroperableRecvObserver`；`OnChange` 时 `QueryMuteRinger` 查询该项，值为 "3"（`VALUE_MUTE`）时执行 `CallControlManager::MuteRinger` 并 `RecoverMuteRinger` 恢复为默认值 "0"；`SendMuteRinger` SHALL 更新 `call_mute_ringer` 数据项为 "3" 通知协同端。

#### Scenario: 协同静音数据变化
- **WHEN** watch 平台 `synergy_incoming_mute` 数据项变为 "3"
- **THEN** 本端执行静默响铃并把该数据项恢复为 "0"

#### Scenario: 本端通知协同端静音
- **WHEN** watch 本端触发 `SendMuteRinger`
- **THEN** `call_mute_ringer` 数据项被更新为 "3"
