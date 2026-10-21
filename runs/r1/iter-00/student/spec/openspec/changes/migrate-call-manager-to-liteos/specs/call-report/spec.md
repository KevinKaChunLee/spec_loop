# Spec Delta

## MODIFIED Requirements

### Requirement: 回调注册与注销
系统 SHALL 由 `CallAbilityReportProxy::RegisterCallBack` 对非空 `ICallAbilityCallback` 先 `SetBundleInfo` 记录 bundle 名，再加入 `callbackPtrList_`（单进程模型下回调对象进程内直持，不再经 `AsObject()` 挂载 `CallAbilityCallbackDeathRecipient` 死亡通知）；`UnRegisterCallBack` 支持按 bundleInfo 或按回调对象两种方式移除列表中首个匹配项；列表为空时注销返回 TELEPHONY_ERR_LOCAL_PTR_NULL。
#### Scenario: 注册进程内直持
- **WHEN** 应用以 bundleInfo 注册回调
- **THEN** 回调入列并被进程内直持，不挂载任何死亡通知
#### Scenario: 注册携带死亡通知
- **WHEN** 应用以 bundleInfo 注册回调
- **THEN** 单进程模型下不挂载 `CallAbilityCallbackDeathRecipient`（call_ability_callback_death_recipient.cpp 不迁移），回调对象进程内直持、无 `AsObject()` 死亡通知链路
#### Scenario: 按对象注销
- **WHEN** 以某已注册回调对象调用 `UnRegisterCallBack` 且列表中存在同一回调对象
- **THEN** 该回调从 `callbackPtrList_` 移除并返回 TELEPHONY_SUCCESS
#### Scenario: 空列表注销
- **WHEN** `callbackPtrList_` 为空时调用任一 `UnRegisterCallBack`
- **THEN** 返回 TELEPHONY_ERR_LOCAL_PTR_NULL

### Requirement: 通话状态与事件上报
系统 SHALL 由 `CallAbilityReportProxy::CallStateUpdated` 取 `CallAttributeInfo`（号码中 ','/';' 及之后内容截断）后 `ReportCallStateInfo` 遍历 `callbackPtrList_` 进程内直调 `ICallAbilityCallback` 的 `OnCallDetailsChange`（无 IPC 序列化）；nextState 为 CALL_STATUS_ANSWERED 时上报状态覆写为 CALL_STATUS_ANSWERED；`CallEventUpdated` 经 `ReportCallEvent` 直调 `OnCallEventChange`；`MeeTimeStateUpdated` 经 `ReportMeeTimeStateInfo` 直调 `OnMeeTimeDetailsChange`；带 bundleInfo 的 `ReportCallStateInfo` 重载仅向指定 bundle 上报；单个回调失败仅记日志继续遍历；`CallDestroyed` 的挂断原因向回调直调 `OnCallDisconnectedCause` 上报保留，挂断原因对外公共事件发布调用点以 `// todo!!! [broadcast] ref to call_ability_report_proxy.cpp CallDestroyed` 占位、不实际发布。
#### Scenario: 号码截断
- **WHEN** 上报的 accountNumber 含 ',' 或 ';'
- **THEN** 分隔符及之后内容被截断后才随 `CallAttributeInfo` 上报
#### Scenario: 定向详情上报
- **WHEN** 调用 `ReportCallStateInfo(info, bundleInfo)`
- **THEN** 仅 bundle 匹配的回调收到一次 `OnCallDetailsChange`
#### Scenario: 挂断原因广播
- **WHEN** 通话销毁触发 `CallDestroyed`
- **THEN** 挂断原因经进程内直调逐个回调 `OnCallDisconnectedCause(details)`，公共事件发布调用点为 `// todo!!! [broadcast] ref to call_ability_report_proxy.cpp CallDestroyed` 占位、不发布公共事件

### Requirement: 辅助结果与 OTT 请求上报
系统 SHALL 由 `CallAbilityReportProxy` 提供 `ReportAsyncResults`、`ReportMmiCodeResult`、`ReportPostDialDelay`、`ReportImsCallModeChange`、`ReportAudioDeviceChange`、`ReportCallSessionEventChange`、`ReportPeerDimensionsChange`、`ReportCallDataUsageChange`、`ReportCameraCapabilities`、`ReportPhoneStateChange` 等接口，均在互斥锁保护下遍历 `callbackPtrList_` 进程内直调对应 `OnReport*`/`OnPhoneStateChange` 接口（`AppExecFwk::PacMap` 参数以结构体替换）；`OttCallRequest` 仅向 bundle 为 "com.ohos.callservice" 的回调发送 `OnOttCallRequest` 的 OTT 请求定向随 OTT 类型通话不支持移除。
#### Scenario: MMI 结果上报
- **WHEN** 调用 `ReportMmiCodeResult(info)`
- **THEN** 每个注册回调收到 `OnReportMmiCodeResult`
#### Scenario: OTT 请求定向
- **WHEN** 调用 `OttCallRequest` 且存在 bundle 为 "com.ohos.callservice" 的回调
- **THEN** OTT 请求定向链路随 OTT 类型通话不支持移除，不产生任何 `OnOttCallRequest` 调用
#### Scenario: 单回调失败不中断
- **WHEN** 遍历中某回调的 `OnReportAsyncResults` 返回非 TELEPHONY_SUCCESS
- **THEN** 记录告警日志并继续遍历其余回调

### Requirement: 系统状态注册上报
系统 SHALL 由 `CallStateReportProxy::CallStateUpdated` 对通话状态变化计算前台状态（经 `CallObjectManager::GetForegroundCall`，与 `currentCallState_` 相同或为 CALL_STATUS_DISCONNECTING 时不报；TYPE_VOIP 直接跳过的分支随 VoIP 暂不支持移除、VoIP 状态计算路径不迁移）；基线经 `TelephonyStateRegistryClient` 的 IPC 双路上报（不带 slotId 的全局 `ReportCallState` 与带 slotId 的 `ReportCallStateForCallId`）收敛为进程内直调一路：保留带 slotId 的 `UpdateCallStateForSlotId`→`ReportCallStateForCallId` 单路直调，全局状态仅用于去重判定、不再单独上报；`UpdateCallStateForVoIPOrRestart` 以 CALL_STATUS_IDLE 重置上报状态。
#### Scenario: 状态去重
- **WHEN** 计算出的前台状态与 `currentCallState_` 一致
- **THEN** 本次不重复上报
#### Scenario: 断开中不上报
- **WHEN** 通话状态为 CALL_STATUS_DISCONNECTING
- **THEN** 分卡上报被跳过
#### Scenario: 双路上报
- **WHEN** 非 VoIP 通话状态变化触发 `CallStateUpdated`
- **THEN** 基线 IPC 双路上报收敛为进程内直调的带 slotId 一路（`UpdateCallStateForSlotId`→`ReportCallStateForCallId`），全局状态仅用于去重判定，不再产生不带 slotId 的全局上报
#### Scenario: 单路直调上报
- **WHEN** 通话状态变化触发 `CallStateUpdated`
- **THEN** 仅产生一条进程内直调的带 slotId 上报，不再产生不带 slotId 的全局上报

## REMOVED Requirements

### Requirement: 回调死亡清理
**Reason**: 单进程模型下不存在跨进程回调死亡（call_ability_callback_death_recipient.cpp 不迁移）。
**Migration**: 无。

### Requirement: 回调 IPC 代理序列化
**Reason**: liteOS 无 IPC 序列化路径（call_ability_callback_proxy.cpp 的 proxy 路径不迁移）。
**Migration**: CallAbilityReportProxy 进程内直调 `ICallAbilityCallback` 回调对象。

### Requirement: 应用进程死亡观察
**Reason**: app_state_observer.cpp 依赖 AppManager IPC 的应用前后台/死亡观察，单进程模型下不迁移。
**Migration**: 无。
