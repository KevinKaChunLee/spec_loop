# Spec Delta

## MODIFIED Requirements

### Requirement: 回调注册与死亡清理
系统 SHALL 由 `CallAbilityReportProxy`（`DECLARE_DELAYED_SINGLETON`，继承 `CallStateListenerBase`）以 `std::list<std::shared_ptr<ICallAbilityCallback>> callbackPtrList_`（替代 `sptr`）维护进程内回调注册表：`RegisterCallBack(callback, bundleInfo)` 执行 `callback->SetBundleInfo` 后入表；`UnRegisterCallBack(bundleInfo)` 按 bundleInfo 匹配删除；死亡收件人（`CallAbilityCallbackDeathRecipient`）不迁移（单进程无远端死亡，注销由应用显式调用完成）。
#### Scenario: 注册应用回调后进程死亡
- **WHEN** 回调注册表维护（单进程无远端死亡通知）
- **THEN** 无 `OnRemoteDied` 清理路径，注销仅经应用显式 `UnRegisterCallBack(bundleInfo)` 完成

#### Scenario: 应用注销回调
- **WHEN** 已注册回调的应用调用 `UnRegisterCallBack(bundleInfo)`
- **THEN** 该应用的回调从 `callbackPtrList_` 移除，后续事件不再向其上报

### Requirement: 通话事件上报
系统 SHALL 由 `CallAbilityReportProxy` 遍历 `callbackPtrList_` 以进程内直调上报（不再经 IPC 代理打包）：`CallStateUpdated`→`ReportCallStateInfo(info)`（`OnCallDetailsChange`，号码遇 ','/';' 截断，`CALL_STATUS_ANSWERED` 强制覆盖 `info.callState`）、`MeeTimeStateUpdated`→`ReportMeeTimeStateInfo`（`OnMeeTimeDetailsChange`）、`CallEventUpdated`→`ReportCallEvent`（`OnCallEventChange`）、`CallDestroyed`→`OnCallDisconnectedCause`、`ReportAsyncResults`（`OnReportAsyncResults`）、`ReportMmiCodeResult`、`ReportAudioDeviceChange`、`ReportPostDialDelay`、`ReportImsCallModeChange`、`ReportCallSessionEventChange`、`ReportPeerDimensionsChange`、`ReportCallDataUsageChange`、`ReportCameraCapabilities`、`ReportPhoneStateChange`；另有带 bundleInfo 定向的 `ReportCallStateInfo(info, bundleInfo)`；蓝牙联动（`BluetoothCallManager::SendCallDetailsChange`）不迁移。
#### Scenario: OTT 命令仅发指定应用
- **WHEN** 检索 OTT 定向上报路径（`OttCallRequest`/`OnOttCallRequest`）
- **THEN** OTT 命令链路已移除（`com.ohos.callservice` 定向上报不可达），带 bundleInfo 的定向上报仅匹配存活注册回调

#### Scenario: 状态上报给多个注册应用
- **WHEN** 通话状态变化触发 `CallStateUpdated`
- **THEN** 全部注册回调依次直接收到 `OnCallDetailsChange`，上报内容与状态迁移一致

### Requirement: 框架层状态上报
系统 SHALL 由 `CallStateReportProxy`（`DECLARE_DELAYED_SINGLETON`，继承 `CallStateListenerBase`）在 `CallStateUpdated` 过滤 `TYPE_VOIP` 后经 `UpdateCallState`（取 `CallObjectManager::GetForegroundCall(false)` 前台通话并融合 `GetVoipCallState()` 的 `CallStateToApp` 映射，`currentCallState_` 去重，DISCONNECTING 不报）与 `UpdateCallStateForSlotId` 双路上报 `TelephonyStateRegistryClient`（状态注册桩，空操作返回成功）；`UpdateCallStateForVoIPOrRestart()` 在初始化时以 IDLE 补报一次。
#### Scenario: 前台通话状态去重上报
- **WHEN** 前台通话状态与上次上报相同
- **THEN** 不重复向状态注册桩发起上报

## REMOVED Requirements

### Requirement: 回调 IPC 序列化
**Reason**: AGENTS.md 架构约束：不实现 IPC 调用；回调上报改进程内直调。
**Migration**: `CallAbilityCallbackProxy`（`CallManagerCallAbilityInterfaceCode` 打包路径）不迁移；`CallManagerCallAbilityInterfaceCode` 码表头保留（ABI 冻结，需人工复核）；`CallManagerUtils::WriteCallAttributeInfo`/`NativeCallManagerUtils::ReadCallAttributeInfo` 序列化函数保留供测试对拍。

### Requirement: UI 进程死亡监听
**Reason**: liteOS 单进程运行，无 "ui" 进程与 samgr 应用管理订阅。
**Migration**: `AppStateObserver` 与 `CallControlManager::AppStateObserver()` 注册不迁移；`CallControlManager::SetVoIPCallState((int32_t)CallStateToApp::CALL_STATE_IDLE)` 与 `CallObjectManager::ClearVoipList()` 复位函数保留，供桩/后续畅连对接触发。
