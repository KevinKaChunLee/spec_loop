# Spec Delta

## MODIFIED Requirements

### Requirement: 客户端单例与服务连接
系统 SHALL 由 `CallManagerClient`（`interfaces/innerkits/call_manager_client.h`，`DelayedSingleton`）全量转发进程内 `CallManagerService` 直调引用（不再经文件级 `g_callManagerProxy` 的 samgr `GetSystemAbility`/`iface_cast`/死亡收件人/`ReConnectService` 链路）；`Init()` 幂等触发服务懒初始化，未 `Init` 的方法返回 `TELEPHONY_ERR_UNINIT` 语义保留；`CALL_MANAGER_AUTO_START_OPTIMIZE` 广播延迟连接不迁移。
#### Scenario: 服务死亡后重建回调
- **WHEN** 客户端运行于单进程直调形态（服务进程内常驻）
- **THEN** 无服务死亡通知与 `ReConnectService`/`ReRegisterCallBack` 路径，直调引用恒有效

#### Scenario: 直调同步返回
- **WHEN** 客户端 `Init` 后调用任一业务接口（如 `DialCall`）
- **THEN** 请求直调 `CallManagerService` 同步执行并返回结果，无服务连接与重连过程

#### Scenario: 未初始化返回错误
- **WHEN** 客户端未 `Init` 即调用业务方法
- **THEN** 返回 `TELEPHONY_ERR_UNINIT`

### Requirement: 应用侧回调注册
系统 SHALL 由 `CallManagerClient::RegisterCallBack` 创建 `CallAbilityCallback`（`: CallAbilityCallbackStub`，`SetProcessCallback` 持有应用 `CallManagerCallback`）进程内注册到服务并 `registerStatus_` 防重（不再经 IPC parcel）；`CallAbilityCallback` 覆盖 `OnCallDetailsChange/OnMeeTimeDetailsChange/OnCallEventChange/OnCallDisconnectedCause/OnReportAsyncResults/OnOttCallRequest/OnReportMmiCodeResult/OnReportAudioDeviceChange/OnReportPostDialDelay/OnReportImsCallModeChange/OnReportCallSessionEventChange/OnReportPeerDimensionsChange/OnReportCallDataUsageChange/OnReportCameraCapabilities/OnPhoneStateChange` 后转交应用回调。
#### Scenario: 注册回调重复注册
- **WHEN** 同一客户端二次调用 `RegisterCallBack`
- **THEN** `registerStatus_` 防重，不重复向服务注册

### Requirement: 语音能力与系统参数
系统 SHALL 由 `CallManagerClient::HasVoiceCapability` 读系统参数 `const.telephony.voice.capable`（经系统参数桩，缺省 true）；`SuperPrivacyManagerClient`（`SUPER_PRIVACY_MANAGER_SA_ID = 66102`/`COMMAND_SET_SUPER_PRIVACY_MODE` 直发）不迁移（超级隐私不支持）。
#### Scenario: 查询语音能力
- **WHEN** 客户端调用 `HasVoiceCapability`
- **THEN** 按桩参数表 `const.telephony.voice.capable` 返回（未配置视为 true）

## REMOVED Requirements

### Requirement: IPC 序列化层
**Reason**: AGENTS.md 架构约束：不实现 IPC 调用，接口改进程内直调。
**Migration**: `CallManagerServiceProxy`/`CellularCallProxy`/`CallStatusCallbackProxy`/`VoipCallManagerProxy` 不迁移；`CallManagerInterfaceCode`/`CallStatusInterfaceCode`/`CellularCallInterfaceCode` 码表头保留（枚举值 ABI 冻结，需人工复核）；`NativeCallManagerUtils::ReadCallAttributeInfo` 保留供测试对拍。

### Requirement: 蓝牙与星闪客户端
**Reason**: AGENTS.md 功能范围：BLUETOOTH 类型通话与星闪（NearLink）耳机设备连接不支持。
**Migration**: `BluetoothCallClient`/`NearlinkCallClient` 不迁移；`PROXY_BLUETOOTH_CALL` 代理对象与 `btSlotIdUnknown` 标记链路移除。

### Requirement: JS/ETS/仓颉绑定
**Reason**: AGENTS.md 功能范围：JS/ETS/仓颉绑定的外部接口不需要实现。
**Migration**: `frameworks/js`（napi 模块 `telephony.call`）、`frameworks/ets/taihe`、`frameworks/cj` 不迁移；仅保留 `frameworks/native` 客户端面。
