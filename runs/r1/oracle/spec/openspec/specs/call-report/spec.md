# 应用上报层（call-report）Specification

## Purpose
描述 `telephony_call_manager/services/call_report/` 的应用侧上报层：`CallAbilityReportProxy`（回调注册表与事件上报）、`CallAbilityCallbackProxy`（`ICallAbilityCallback` 的 IPC 代理）、`CallAbilityCallbackDeathRecipient`（回调死亡清理）、`CallStateReportProxy`（`TelephonyStateRegistryClient` 状态上报）、`AppStateObserver`（"ui" 进程死亡监听）。IPC 枚举落点：`interfaces/innerkits/call_ability_callback_ipc_interface_code.h`（`CallManagerCallAbilityInterfaceCode` 共 15 项）。该模块组无独有编译开关。

## Requirements

### Requirement: 回调注册与死亡清理
系统 SHALL 由 `CallAbilityReportProxy`（`DECLARE_DELAYED_SINGLETON`，继承 `CallStateListenerBase`）以 `std::list<sptr<ICallAbilityCallback>> callbackPtrList_` 维护回调注册表：`RegisterCallBack(callback, bundleInfo)` 执行 `callback->SetBundleInfo` 后入表并为 `AsObject()` 挂 `CallAbilityCallbackDeathRecipient`；`UnRegisterCallBack(bundleInfo)` 按 bundleInfo 匹配删除；`OnRemoteDied` 时 `UnRegisterCallBack(object.promote())`。
#### Scenario: 注册应用回调后进程死亡
- **WHEN** 已注册回调的应用进程死亡触发 `OnRemoteDied`
- **THEN** 该应用的回调从 `callbackPtrList_` 移除，后续事件不再向其上报

### Requirement: 通话事件上报
系统 SHALL 由 `CallAbilityReportProxy` 遍历 `callbackPtrList_` 上报：`CallStateUpdated`→`ReportCallStateInfo(info)`（`OnCallDetailsChange`，号码遇 ','/';' 截断，`CALL_STATUS_ANSWERED` 强制覆盖 `info.callState`，成功后联动 `BluetoothCallManager::SendCallDetailsChange(callId, callState)`）、`MeeTimeStateUpdated`→`ReportMeeTimeStateInfo`（`OnMeeTimeDetailsChange`）、`CallEventUpdated`→`ReportCallEvent`（`OnCallEventChange`）、`CallDestroyed`→`OnCallDisconnectedCause`、`ReportAsyncResults`（`OnReportAsyncResults`）、`ReportMmiCodeResult`、`ReportAudioDeviceChange`、`ReportPostDialDelay`、`ReportImsCallModeChange`、`ReportCallSessionEventChange`、`ReportPeerDimensionsChange`、`ReportCallDataUsageChange`、`ReportCameraCapabilities`、`ReportPhoneStateChange`；另有带 bundleInfo 定向的 `ReportCallStateInfo(info, bundleInfo)`。
#### Scenario: 状态上报给多个注册应用
- **WHEN** 通话状态变化触发 `CallStateUpdated`
- **THEN** 全部注册回调依次收到 `OnCallDetailsChange`，且蓝牙侧同步收到 `SendCallDetailsChange`

#### Scenario: OTT 命令仅发指定应用
- **WHEN** `OttCallRequest(OttCallRequestId, info)` 执行
- **THEN** 仅 `bundleName == "com.ohos.callservice"` 的回调收到 `OnOttCallRequest`

### Requirement: 回调 IPC 序列化
系统 SHALL 由 `CallAbilityCallbackProxy : public IRemoteProxy<ICallAbilityCallback>`（全部 `MessageOption::TF_ASYNC`）按 `CallManagerCallAbilityInterfaceCode` 打包上报：`OnCallDetailsChange`→`UPDATE_CALL_STATE_INFO`、`OnMeeTimeDetailsChange`→`UPDATE_MEETIME_STATE_INFO`、`OnCallEventChange`→`UPDATE_CALL_EVENT`（`WriteRawData` 序列化 `CallEventInfo`）、`OnReportAsyncResults`→`UPDATE_CALL_ASYNC_RESULT_REQUEST`（`PackDataParcel` 按 `GET_CALL_WAITING_REPORT_ID`/`GET_CALL_RESTRICTION_REPORT_ID`/`GET_CALL_TRANSFER_REPORT_ID`/`GET_CALL_CLIP_ID`/`GET_CALL_CLIR_ID`/`GET_IMS_CONFIG_REPORT_ID`/`GET_IMS_FEATURE_VALUE_REPORT_ID`/`START_RTT_REPORT_ID`/`STOP_RTT_REPORT_ID` 差异化序列化）、`OnReportMmiCodeResult`→`UPDATE_MMI_CODE_RESULT_REQUEST`、`OnOttCallRequest`→`REPORT_OTT_CALL_REQUEST` 等；`CallAttributeInfo` 序列化复用 `CallManagerUtils::WriteCallAttributeInfo`。
#### Scenario: 补充业务查询结果回传
- **WHEN** `ReportAsyncResults` 上报呼叫等待查询结果
- **THEN** 客户端以 `GET_CALL_WAITING_REPORT_ID` 对应的 parcel 格式收到 `UPDATE_CALL_ASYNC_RESULT_REQUEST`

### Requirement: 框架层状态上报
系统 SHALL 由 `CallStateReportProxy`（`DECLARE_DELAYED_SINGLETON`，继承 `CallStateListenerBase`）在 `CallStateUpdated` 过滤 `TYPE_VOIP` 后经 `UpdateCallState`（取 `CallObjectManager::GetForegroundCall(false)` 前台通话并融合 `GetVoipCallState()` 的 `CallStateToApp` 映射，`currentCallState_` 去重，DISCONNECTING 不报）与 `UpdateCallStateForSlotId` 双路上报 `DelayedRefSingleton<TelephonyStateRegistryClient>::GetInstance()->UpdateCallState/UpdateCallStateForSlotId`；`UpdateCallStateForVoIPOrRestart()` 在初始化时以 IDLE 补报一次。
#### Scenario: 前台通话状态去重上报
- **WHEN** 前台通话状态与上次上报相同
- **THEN** 不重复向 `TelephonyStateRegistryClient` 上报

### Requirement: UI 进程死亡监听
系统 SHALL 由 `AppStateObserver : public AppExecFwk::ApplicationStateObserverStub` 仅实现 `OnProcessDied(const AppExecFwk::ProcessData&)`：`processName == "ui"` 时执行 `CallControlManager::SetVoIPCallState((int32_t)CallStateToApp::CALL_STATE_IDLE)` 与 `CallObjectManager::ClearVoipList()`；注册由 `CallControlManager::AppStateObserver()` 经 samgr `GetSystemAbility(APP_MGR_SERVICE_ID)`→`RegisterApplicationStateObserver` 完成。
#### Scenario: 通话界面进程死亡
- **WHEN** 进程名为 "ui" 的应用进程死亡
- **THEN** VoIP 状态复位为 IDLE 并清空 VoIP 属性缓存表
