# Spec Delta

## REMOVED Requirements

### Requirement: 卫星拨号准入

**Reason**: AGENTS 功能范围：不支持卫星通话，相关代码无需迁移；卫星开关/连通性查询与温度限拨判定链在 liteOS 无卫星形态可判；design D7 被删文件表列出 `services/satellite_call/src/satellite_call_control.cpp`。
**Migration**: 删除 `services/satellite_call/src/satellite_call_control.cpp`（含 `services/satellite_call/include/satellite_call_control.h`）与 `services/call/src/satellite_call.cpp`（含头文件，卫星对象见 call-object-management delta）并同步 `callmanager.gni` 的 `call_manager_sources` 与 `call_manager_include_dirs` 的 satellite_call 目录条目（design D7 表）；`call_control_manager.cpp` 的 `IsSatelliteSwitchEnable`/`IsAllowedSatelliteDialCall` 拨号准入与 `CallType::TYPE_SATELLITE` 置位分支删除（见 call-control-management delta）。恢复条件：支持卫星通话后重建准入链并恢复 gni 条目，或由后续 change 恢复。

### Requirement: 温度等级管理

**Reason**: AGENTS 功能范围：不支持卫星通话，相关代码无需迁移；`SetSatcommTempLevel`/`SetShowDialog` 的卫星高温断链弹窗与倒计时启动仅服务卫星通话，liteOS 无该形态；design D7 被删文件表列出 `satellite_call_control.cpp`。
**Migration**: 删除 `services/satellite_call/src/satellite_call_control.cpp`（含对应头文件）并同步 `callmanager.gni` 条目（design D7 表）；`call_broadcast_subscriber.cpp` 的 `HighTempLevelChangedBroadcast`→`SetSatcommTempLevel` 卫星高温广播分支删除（见 call-control-management delta 的广播订阅收窄）。恢复条件：支持卫星通话后重建温度等级链并恢复 gni 条目，或由后续 change 恢复。

### Requirement: 卫星通话状态联动

**Reason**: AGENTS 功能范围：不支持卫星通话，相关代码无需迁移；`HandleSatelliteCallStateUpdate` 的来话 `SetUsedModem`、高温弹窗与限时任务启停仅对 `TYPE_SATELLITE` 通话生效，liteOS 无该类型；design D7 被删文件表列出 `satellite_call_control.cpp`、`satellite_call.cpp`。
**Migration**: 删除 `services/satellite_call/src/satellite_call_control.cpp` 与 `services/call/src/satellite_call.cpp`（含对应头文件）并同步 `callmanager.gni` 条目（design D7 表）；`call_status_manager.cpp` 的 `HandleSatelliteCallStateUpdate` 分支与对象表谓词中的 `TYPE_SATELLITE` 条件删除（见 call-status-management/call-object-management delta）。恢复条件：支持卫星通话后重建状态联动并恢复 gni 条目，或由后续 change 恢复。

### Requirement: 通话限时与倒计时任务

**Reason**: AGENTS 功能范围：不支持卫星通话，相关代码无需迁移；270 秒限时弹窗与 30 秒倒计时拒接/挂断任务仅对卫星通话生效，liteOS 无该形态；design D7 被删文件表列出 `satellite_call_control.cpp`。
**Migration**: 删除 `services/satellite_call/src/satellite_call_control.cpp`（含对应头文件，`CallDurationLimitHandler_`/`CallCountDownHandler_` 随文件消失）并同步 `callmanager.gni` 条目（design D7 表）；其经 `CallDialog::DialogConnectExtension` 的弹窗出口与 `CallControlManager::RejectCall`/`HangUpCall` 联动调用点随卫星删除，蜂窝侧控制主线不受影响（见 call-control-management delta）。恢复条件：支持卫星通话后重建限时/倒计时任务并恢复 gni 条目，或由后续 change 恢复。

### Requirement: modem 参数映射

**Reason**: AGENTS 功能范围：不支持卫星通话，相关代码无需迁移；`SetUsedModem` 按 `const.telephony.satellite.support_type` 位掩码向音频系统写 `USEDMODEM` 扩展参数，卫星形态不存在后无触发点；design D7 被删文件表列出 `satellite_call_control.cpp`。
**Migration**: 删除 `services/satellite_call/src/satellite_call_control.cpp`（含对应头文件）并同步 `callmanager.gni` 条目（design D7 表）；`SetUsedModem` 的系统参数读取与 `AudioSystemManager::SetExtraParameters` 音频调用点随文件删除（audio 侧其余调用按 `[audio]` todo 桩化，见 audio-device-management delta）。恢复条件：支持卫星通话后重建参数映射并恢复 gni 条目，或由后续 change 恢复。
