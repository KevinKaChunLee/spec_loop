# 对应用上报（Call Report）Specification

## Purpose
描述 HMOS `telephony_call_manager` 中向注册回调的应用及系统状态注册中心上报通话状态/事件的能力：回调的注册与注销、通话详情/事件/挂断原因及各类辅助信息上报、回调代理的 IPC 序列化、死亡通知清理、系统级通话状态上报与应用进程死亡观察。源码落点：`telephony_call_manager/services/call_report/{include,src}`：`call_ability_report_proxy.cpp/.h`（类 `CallAbilityReportProxy`，实现 `CallStateListenerBase`）、`call_state_report_proxy.cpp/.h`（类 `CallStateReportProxy`）、`call_ability_callback_proxy.cpp/.h`（类 `CallAbilityCallbackProxy`，`ICallAbilityCallback` 的 IPC 代理）、`call_ability_callback_death_recipient.cpp/.h`（类 `CallAbilityCallbackDeathRecipient`）、`app_state_observer.cpp/.h`（类 `ApplicationStateObserver`，派生自 `AppExecFwk::ApplicationStateObserverStub`；`CallAbilityReportProxy` 另持有 `sptr<ApplicationStateObserver>` 与 `sptr<AppExecFwk::IAppMgr>` 成员）。该目录无专属编译开关（`callmanager.gni` 与 `BUILD.gn` 未为其定义宏）。

## Requirements

### Requirement: 回调注册与注销
系统 SHALL 由 `CallAbilityReportProxy::RegisterCallBack` 对非空 `ICallAbilityCallback` 先 `SetBundleInfo` 记录 bundle 名，再加入 `callbackPtrList_`，并为其 `AsObject()` 添加 `CallAbilityCallbackDeathRecipient`；`UnRegisterCallBack` 支持按 bundleInfo 或按 `IRemoteObject` 两种方式移除列表中首个匹配项；列表为空时注销返回 TELEPHONY_ERR_LOCAL_PTR_NULL。
#### Scenario: 注册携带死亡通知
- **WHEN** 应用以 bundleInfo 注册回调
- **THEN** 回调入列且其远程对象被挂上 `CallAbilityCallbackDeathRecipient`
#### Scenario: 按对象注销
- **WHEN** 以某 `IRemoteObject` 调用 `UnRegisterCallBack` 且列表中存在 `AsObject()` 相同的回调
- **THEN** 该回调从 `callbackPtrList_` 移除并返回 TELEPHONY_SUCCESS
#### Scenario: 空列表注销
- **WHEN** `callbackPtrList_` 为空时调用任一 `UnRegisterCallBack`
- **THEN** 返回 TELEPHONY_ERR_LOCAL_PTR_NULL

### Requirement: 通话状态与事件上报
系统 SHALL 由 `CallAbilityReportProxy::CallStateUpdated` 取 `CallAttributeInfo`（号码中 ','/';' 及之后内容截断）后 `ReportCallStateInfo` 遍历回调调用 `OnCallDetailsChange`；nextState 为 CALL_STATUS_ANSWERED 时上报状态覆写为 CALL_STATUS_ANSWERED；`CallDestroyed` 遍历调用 `OnCallDisconnectedCause`；`CallEventUpdated` 经 `ReportCallEvent` 调用 `OnCallEventChange`；`MeeTimeStateUpdated` 经 `ReportMeeTimeStateInfo` 调用 `OnMeeTimeDetailsChange`；带 bundleInfo 的 `ReportCallStateInfo` 重载仅向指定 bundle 上报。单个回调失败仅记日志继续遍历。
#### Scenario: 号码截断
- **WHEN** 上报的 accountNumber 含 ',' 或 ';'
- **THEN** 分隔符及之后内容被截断后才随 `CallAttributeInfo` 上报
#### Scenario: 定向详情上报
- **WHEN** 调用 `ReportCallStateInfo(info, bundleInfo)`
- **THEN** 仅 bundle 匹配的回调收到一次 `OnCallDetailsChange`
#### Scenario: 挂断原因广播
- **WHEN** 通话销毁触发 `CallDestroyed`
- **THEN** 列表中每个回调均被调用 `OnCallDisconnectedCause(details)`

### Requirement: 辅助结果与 OTT 请求上报
系统 SHALL 由 `CallAbilityReportProxy` 提供 `ReportAsyncResults`、`ReportMmiCodeResult`、`ReportPostDialDelay`、`ReportImsCallModeChange`、`ReportAudioDeviceChange`、`ReportCallSessionEventChange`、`ReportPeerDimensionsChange`、`ReportCallDataUsageChange`、`ReportCameraCapabilities`、`ReportPhoneStateChange` 等接口，均在互斥锁保护下遍历 `callbackPtrList_` 调用对应 `OnReport*`/`OnPhoneStateChange` 接口；`OttCallRequest` 仅向 bundle 为 "com.ohos.callservice" 的回调发送 `OnOttCallRequest`。
#### Scenario: MMI 结果上报
- **WHEN** 调用 `ReportMmiCodeResult(info)`
- **THEN** 每个注册回调收到 `OnReportMmiCodeResult`
#### Scenario: OTT 请求定向
- **WHEN** 调用 `OttCallRequest` 且存在 bundle 为 "com.ohos.callservice" 的回调
- **THEN** 仅该回调收到 `OnOttCallRequest`
#### Scenario: 单回调失败不中断
- **WHEN** 遍历中某回调的 `OnReportAsyncResults` 返回非 TELEPHONY_SUCCESS
- **THEN** 记录告警日志并继续遍历其余回调

### Requirement: 回调死亡清理
系统 SHALL 由 `CallAbilityCallbackDeathRecipient::OnRemoteDied` 在回调服务进程死亡时将 `object.promote()` 经 `iface_cast<ICallAbilityCallback>` 提升后交 `CallAbilityReportProxy::UnRegisterCallBack(IRemoteObject)` 移除，提升失败或代理为空时仅记日志返回。
#### Scenario: 进程死亡移除回调
- **WHEN** 某已注册回调的进程死亡触发 `OnRemoteDied`
- **THEN** 该回调对象从 `callbackPtrList_` 中被移除
#### Scenario: 提升失败保护
- **WHEN** `OnRemoteDied` 中 `iface_cast` 提升结果为空
- **THEN** 记录 "callback is nullptr" 并直接返回，不做移除

### Requirement: 回调 IPC 代理序列化
系统 SHALL 由 `CallAbilityCallbackProxy` 以 `MessageOption::TF_ASYNC` 发送请求：先写入接口描述符（`GetDescriptor`），`OnCallDetailsChange`/`OnMeeTimeDetailsChange` 经 `CallManagerUtils::WriteCallAttributeInfo` 序列化并以 `CallManagerCallAbilityInterfaceCode` 的 UPDATE_CALL_STATE_INFO/UPDATE_MEETIME_STATE_INFO 发送；`OnCallEventChange` 以 UPDATE_CALL_EVENT 发送原始 `CallEventInfo`；`OnCallDisconnectedCause` 以 UPDATE_CALL_DISCONNECTED_CAUSE 发送 reason 与 message；`Remote()` 为空或 SendRequest 失败返回 TELEPHONY_ERR_IPC_CONNECT_STUB_FAIL。
#### Scenario: 详情异步发送
- **WHEN** 调用 `OnCallDetailsChange(info)`
- **THEN** 以 TF_ASYNC 发送 UPDATE_CALL_STATE_INFO，报文含接口描述符与序列化的通话属性
#### Scenario: 远端失效
- **WHEN** `Remote()` 返回 nullptr
- **THEN** 返回 TELEPHONY_ERR_IPC_CONNECT_STUB_FAIL 不发送

### Requirement: 系统状态注册上报
系统 SHALL 由 `CallStateReportProxy::CallStateUpdated` 对 TYPE_VOIP 通话直接跳过，其余经 `UpdateCallState`（以 `CallObjectManager::GetForegroundCall` 或 VoIP 状态 `GetVoipCallState` 计算前台状态，与 `currentCallState_` 相同或为 CALL_STATUS_DISCONNECTING 时不报）调用 `ReportCallState`→`TelephonyStateRegistryClient::UpdateCallState`，并经 `UpdateCallStateForSlotId` 调用 `ReportCallStateForCallId`→`TelephonyStateRegistryClient::UpdateCallStateForSlotId`；`UpdateCallStateForVoIPOrRestart` 以 CALL_STATUS_IDLE 重置全局上报状态。
#### Scenario: 双路上报
- **WHEN** 非 VoIP 通话状态变化触发 `CallStateUpdated`
- **THEN** 同时产生不带 slotId 的全局上报与带 slotId 的 `UpdateCallStateForSlotId` 上报
#### Scenario: 状态去重
- **WHEN** 计算出的前台状态与 `currentCallState_` 一致
- **THEN** 本次不向 `TelephonyStateRegistryClient` 重复上报
#### Scenario: 断开中不上报
- **WHEN** 通话状态为 CALL_STATUS_DISCONNECTING
- **THEN** 全局与分卡上报均被跳过

### Requirement: 应用进程死亡观察
系统 SHALL 由 `ApplicationStateObserver::OnProcessDied` 在死亡进程 `processName` 为 "ui" 时经 `CallControlManager::SetVoIPCallState` 置 VoIP 状态为 CALL_STATE_IDLE，并调用 `CallObjectManager::ClearVoipList` 清空 VoIP 通话列表；非 "ui" 进程死亡不做处理。
#### Scenario: UI 进程死亡
- **WHEN** `OnProcessDied` 收到 processName 为 "ui" 的进程数据
- **THEN** VoIP 全局状态被置为 CALL_STATE_IDLE 且 VoIP 呼叫列表被清空
#### Scenario: 其它进程死亡
- **WHEN** `OnProcessDied` 收到 processName 不为 "ui" 的进程数据
- **THEN** 不触发任何状态变更
