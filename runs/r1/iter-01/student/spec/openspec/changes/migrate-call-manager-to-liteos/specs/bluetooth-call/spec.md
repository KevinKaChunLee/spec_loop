# Spec Delta

## REMOVED Requirements

### Requirement: 蓝牙连接初始化与系统能力订阅

**Reason**: AGENTS 功能范围：不支持 BLUETOOTH 类型通话，相关代码无需迁移；本需求的 samgr `SubscribeSystemAbility` 订阅与 HFG profile 设备枚举在 liteOS 无系统服务生态可达；design D7 被删文件表列出 `services/bluetooth/src/bluetooth_connection.cpp`。
**Migration**: 删除 `services/bluetooth/src/bluetooth_connection.cpp`（含对应头文件）并同步 `callmanager.gni` 的 `call_manager_sources` 条目（design D7 表）；`callmanager.gni` 的 `ABILITY_BLUETOOTH_SUPPORT` 部件块（`global_parts_info.communication_bluetooth`）删除（design D7 宏处置行）；`CallManagerService::Init` 的 `BluetoothConnection::Init()` 装配调用删除（见 call-manager-service delta）。恢复条件：接入蓝牙 HFP 通话框架后重建本文件并恢复 gni 条目与宏块，或由后续 change 恢复。

### Requirement: HFP 通话状态上报

**Reason**: AGENTS 功能范围：不支持 BLUETOOTH 类型通话，相关代码无需迁移；`ABILITY_BLUETOOTH_SUPPORT` 属不支持宏（AGENTS 特性宏支持范围），宏关闭时 `IsBtAvailble` 恒 false 的链路在 liteOS 无保留价值；design D7 被删文件表列出 `bluetooth_call_manager.cpp`、`bluetooth_connection.cpp`。
**Migration**: 删除 `services/bluetooth/src/bluetooth_call_manager.cpp`、`bluetooth_connection.cpp`（含对应头文件）并同步 `callmanager.gni` 条目（design D7 表）；`ABILITY_BLUETOOTH_SUPPORT` 的 gni 部件块删除（design D7 宏处置行），`SendBtCallState`/`SendCallDetailsChange` 的消费与被消费链随蓝牙分支删除（`call_control_manager.cpp`/`call_status_manager.cpp` 蓝牙分支见对应 delta）。恢复条件：接入蓝牙 HFP 通话框架后重建状态上报链并恢复 gni 条目与宏块，或由后续 change 恢复。

### Requirement: 蓝牙设备连接变化处理

**Reason**: AGENTS 功能范围：不支持 BLUETOOTH 类型通话，相关代码无需迁移；设备连接变化回调（含 `IsDeviceWearing` 佩戴判定与虚拟设备处理）依赖蓝牙框架观察者，liteOS 不接入；design D7 被删文件表列出 `bluetooth_connection.cpp`。
**Migration**: 删除 `services/bluetooth/src/bluetooth_connection.cpp`（含对应头文件）并同步 `callmanager.gni` 条目（design D7 表）；`ABILITY_BLUETOOTH_SUPPORT` 的 gni 部件块删除（design D7 宏处置行），`AddAudioDeviceList`/`RemoveAudioDeviceList` 的 `DEVICE_BLUETOOTH_SCO` 路由消费方（audio 路由蓝牙分支）随蓝牙删除（见 audio-device-management delta）。恢复条件：接入蓝牙 HFP 通话框架后重建设备表与观察者并恢复 gni 条目与宏块，或由后续 change 恢复。

### Requirement: 蓝牙侧控制面 IPC 分发

**Reason**: AGENTS 功能范围：不支持 BLUETOOTH 类型通话，相关代码无需迁移；且 liteOS 不实现 IPC 调用（AGENTS 架构要求），`OnRemoteRequest` 分发表无承载对象（design D2/D3）；design D7 被删文件表列出 `bluetooth_call_stub.cpp`。
**Migration**: 删除 `services/bluetooth/src/bluetooth_call_stub.cpp`（含对应头文件）并同步 `callmanager.gni` 条目（design D7 表）；`ABILITY_BLUETOOTH_SUPPORT` 的 gni 部件块删除（design D7 宏处置行）。恢复条件：支持蓝牙通话且恢复 IPC/系统形态后重建 stub 分发表并恢复 gni 条目与宏块，或由后续 change 恢复。

### Requirement: 控制操作前置策略判定

**Reason**: AGENTS 功能范围：不支持 BLUETOOTH 类型通话，相关代码无需迁移；策略族仅服务蓝牙侧控制面，控制对象在 liteOS 不存在；design D7 被删文件表列出 `bluetooth_call_policy.cpp`。
**Migration**: 删除 `services/bluetooth/src/bluetooth_call_policy.cpp`（含对应头文件）并同步 `callmanager.gni` 条目（design D7 表）；`ABILITY_BLUETOOTH_SUPPORT` 的 gni 部件块删除（design D7 宏处置行）；蜂窝侧通用控制策略（`CallPolicy` 系）不受影响、随 call-control-management 能力保留。恢复条件：接入蓝牙 HFP 通话框架后重建策略判定链并恢复 gni 条目与宏块，或由后续 change 恢复。

### Requirement: 控制操作执行与状态汇总

**Reason**: AGENTS 功能范围：不支持 BLUETOOTH 类型通话，相关代码无需迁移；蓝牙侧控制执行与 `GetCallState` 状态汇总（含 VOIP 合并、`DEVICE_NEARLINK`/`DEVICE_BLUETOOTH_HEARING_AID` 设备类型）依赖蓝牙与星闪链路，均属裁剪范围；design D7 被删文件表列出 `bluetooth_call_service.cpp`、`bluetooth_call_manager.cpp`。
**Migration**: 删除 `services/bluetooth/src/bluetooth_call_service.cpp`、`bluetooth_call_manager.cpp`（含对应头文件）并同步 `callmanager.gni` 条目（design D7 表）；`ABILITY_BLUETOOTH_SUPPORT` 的 gni 部件块删除（design D7 宏处置行）；星闪（NearLink）客户端 `nearlink_call_client.cpp` 随 native-client-api delta 删除，audio 侧蓝牙设备类型分支见 audio-device-management delta。恢复条件：接入蓝牙 HFP 通话框架后重建控制面与状态汇总并恢复 gni 条目与宏块，或由后续 change 恢复。
