# Call Report Specification

## Purpose
描述 HMOS `telephony_call_manager` 中向上层回报通话信息的两个代理及其配套对象（`services/call_report/src/{call_ability_report_proxy,call_ability_callback_proxy,call_state_report_proxy,call_ability_callback_death_recipient,app_state_observer}.cpp` 及 `include/` 头文件）：`CallAbilityReportProxy` 维护应用侧 `ICallAbilityCallback` 观察者列表并把通话状态/事件/结果多播给全部注册方；`CallAbilityCallbackProxy` 把每次回报封装成一次 TF_ASYNC IPC（接口码 `CallManagerCallAbilityInterfaceCode`）送到应用进程；`CallStateReportProxy`（继承 `CallStateListenerBase`，由 `CallControlManager` 经 `CallStateListener::AddOneObserver` 注册，见 `services/call/src/call_control_manager.cpp`）把"全局"与"按 slotId"两路通话状态上报并存地送 `TelephonyStateRegistryClient`；`CallAbilityCallbackDeathRecipient` 在应用回调死亡时清理观察者；`ApplicationStateObserver` 监听系统应用进程死亡以复位 VoIP 通话状态。本规格为移植前现状基线，不涉及裁剪决策。本能力不涉及条件编译特性宏。

## Requirements

### Requirement: 应用侧回调注册与解除
系统 SHALL 由 `CallAbilityReportProxy::RegisterCallBack(callback, bundleInfo)` 判空回调后将 `bundleInfo` 写入回调（`SetBundleInfo`）并加入 `callbackPtrList_`（`std::list<sptr<ICallAbilityCallback>>`，`mutex_` 保护），随后为其 `AsObject()` 挂接新建的 `CallAbilityCallbackDeathRecipient`；`UnRegisterCallBack(bundleInfo)` 按注册时记下的 bundleInfo 匹配后移除一项，`UnRegisterCallBack(sptr<IRemoteObject>)` 按远端对象指针匹配移除一项；两者在列表为空时返回 `TELEPHONY_ERR_LOCAL_PTR_NULL`，正常路径返回 `TELEPHONY_SUCCESS`；析构时遍历清空全部回调。

#### Scenario: 重复注册
- **WHEN** 同一应用再次注册不同回调对象并携带相同 bundleInfo
- **THEN** 列表中出现两个表项（无去重），两次回报均能到达

#### Scenario: 空回调对象
- **WHEN** `RegisterCallBack` 收到空的 `callAbilityCallbackPtr`
- **THEN** 返回 `TELEPHONY_ERR_LOCAL_PTR_NULL`，不入列表

#### Scenario: 按 bundleInfo 解除
- **WHEN** `UnRegisterCallBack(bundleInfo)` 且某表项 `GetBundleInfo()` 相等
- **THEN** 该表项被移除并停止接收回报

### Requirement: 回调死亡回收
系统 SHALL 由 `CallAbilityCallbackDeathRecipient::OnRemoteDied`：将 `object.promote()` 得到的 `wptr` 提升为 `sptr<ICallAbilityCallback>`（空则返回），随后调用 `DelayedSingleton<CallAbilityReportProxy>::GetInstance()->UnRegisterCallBack(object.promote())` 完成按远端对象移除，避免向已死进程回报。

#### Scenario: 应用进程死亡
- **WHEN** 某已注册回调所在的远端对象死亡
- **THEN** 该观察者从 `callbackPtrList_` 被移除，后续多播不再向其发送

### Requirement: 通话详情多播（CallStateUpdated）
系统 SHALL 由 `CallAbilityReportProxy::CallStateUpdated(callObjectPtr, priorState, nextState)`：取 `CallAttributeInfo` 后截断 `accountNumber` 中首个 `,` 或 `;`（截断处写入 '\0'）且长度限幅 `kMaxNumberLen`；`nextState == CALL_STATUS_ANSWERED` 时置 `info.callState` 为 ANSWERED；随后 `ReportCallStateInfo(info)` 多播。`ReportCallStateInfo(info)` SHALL 给全部观察者发 `OnCallDetailsChange`（单个失败记日志继续下一个）；定向版本 `ReportCallStateInfo(info, bundleInfo)` SHALL 只发给 `GetBundleInfo()` 相等的一个观察者。两路多播成功后 SHALL 联动 `BluetoothCallManager::SendCallDetailsChange(callId, callState)`。

#### Scenario: 携带分机分隔符的号码
- **WHEN** 通话属性 `accountNumber` 含 `,`（示例 unknown,unknown）
- **THEN** 上报给观察者的号码在 `,` 处截断

#### Scenario: 应答态覆盖
- **WHEN** nextState 为 `CALL_STATUS_ANSWERED`
- **THEN** 上报的 `callState` 为 ANSWERED

#### Scenario: 定向上报
- **WHEN** `ObserverOnCallDetailsChange()` 触发按 bundleInfo 的定向上报（见 call-manager-service 能力）
- **THEN** 只有匹配 bundleInfo 的观察者收到 `OnCallDetailsChange`

### Requirement: 事件与结果多播族
系统 SHALL 由 `CallAbilityReportProxy` 提供同构的多播函数（`mutex_` 下遍历 `callbackPtrList_`，单个失败继续）：`CallEventUpdated(info)`→`OnCallEventChange`；`CallDestroyed(details)`→`OnCallDisconnectedCause`；`ReportAsyncResults(reportId, resultInfo)`→`OnReportAsyncResults`；`ReportMmiCodeResult(info)`→`OnReportMmiCodeResult`；`ReportAudioDeviceChange(info)`→`OnReportAudioDeviceChange`；`ReportPostDialDelay(str)`→`OnReportPostDialDelay`；`ReportImsCallModeChange(imsCallModeInfo)`→`OnReportImsCallModeChange`；`ReportCallSessionEventChange(callSessionEventOptions)`→`OnReportCallSessionEventChange`；`ReportPeerDimensionsChange(peerDimensionsDetail)`→`OnReportPeerDimensionsChange`；`ReportCallDataUsageChange(dataUsage)`→`OnReportCallDataUsageChange`；`ReportCameraCapabilities(cameraCapabilities)`→`OnReportCameraCapabilities`；`ReportPhoneStateChange(numActive, numHeld, callState, number)`→`OnPhoneStateChange`；`MeeTimeStateUpdated(info, ...)`→`ReportMeeTimeStateInfo`→`OnMeeTimeDetailsChange`；`OttCallRequest(requestId, info)` SHALL 只发给 `GetBundleInfo() == "com.ohos.callservice"` 的观察者。

#### Scenario: MMI 码结果多播
- **WHEN** 补充业务操作产出 `MmiCodeInfo` 并调用 `ReportMmiCodeResult`
- **THEN** 全部观察者各收一次 `OnReportMmiCodeResult`

#### Scenario: OTT 请求只给通话服务
- **WHEN** `OttCallRequest` 时列表中存在非 com.ohos.callservice 的观察者
- **THEN** 后者不接收 `OnOttCallRequest`

#### Scenario: 单个观察者回报失败不中断
- **WHEN** 列表中第一个回调返回非 `TELEPHONY_SUCCESS`
- **THEN** 记日志后继续尝试其余回调

### Requirement: 应用回报 IPC 封装（CallAbilityCallbackProxy）
系统 SHALL 由 `CallAbilityCallbackProxy`（`IRemoteProxy<ICallAbilityCallback>`）将每个回报封装为 TF_ASYNC 的 `SendRequest`，逐个对应 `CallManagerCallAbilityInterfaceCode` 码：`UPDATE_CALL_STATE_INFO`（OnCallDetailsChange 与 OnMeeTimeDetailsChange 分用 `UPDATE_MEETIME_STATE_INFO`，参数均经 `CallManagerUtils::WriteCallAttributeInfo` 序列化）、`UPDATE_CALL_EVENT`(OnCallEventChange，整结构 `WriteRawData`)、`UPDATE_CALL_DISCONNECTED_CAUSE`、`UPDATE_CALL_ASYNC_RESULT_REQUEST`、`UPDATE_MMI_CODE_RESULT_REQUEST`、`REPORT_OTT_CALL_REQUEST`、`UPDATE_AUDIO_DEVICE_CHANGE_RESULT_REQUEST`（OnReportAudioDeviceChange）、`REPORT_POST_DIAL_DELAY`、`UPDATE_IMS_CALL_MODE_RECEIVE`、`CALL_SESSION_EVENT_CHANGE`、`PEERD_DIMENSIONS_CHANGE`、`CALL_DATA_USAGE_CHANGE`、`CAMERA_CAPABILITIES_CHANGE`、`UPDATE_PHONE_STATE`。每次 SHALL 先写接口描述符令牌，`Remote()` 为空返回 `TELEPHONY_ERR_IPC_CONNECT_STUB_FAIL`。

#### Scenario: 描述符写入失败
- **WHEN** `WriteInterfaceToken` 失败
- **THEN** 返回 `TELEPHONY_ERR_WRITE_DESCRIPTOR_TOKEN_FAIL`，不发起 SendRequest

#### Scenario: 通话详情序列化
- **WHEN** 发送 `OnCallDetailsChange`
- **THEN** 请求码为 `UPDATE_CALL_STATE_INFO` 且经 `CallManagerUtils::WriteCallAttributeInfo` 组包

### Requirement: 状态监听接入（CallStateListenerBase）
系统 SHALL 让 `CallStateReportProxy` 继承 `CallStateListenerBase`（虚函数 `CallStateUpdated/MeeTimeStateUpdated` 等，`services/call/include/call_state_listener_base.h`），由 `CallControlManager::InitEvents`（`call_control_manager.cpp`）经 `callStateListenerPtr_->AddOneObserver(DelayedSingleton<CallStateReportProxy>::GetInstance())` 纳入 `CallStateListener` 观察者集合，通话状态变化时经该监听器回调 `CallStateReportProxy::CallStateUpdated`。`CallStateUpdated` SHALL 对 `CallType::TYPE_VOIP` 的通话直接跳过（日志 "voip call no need to report call state"）、空对象跳过，否则同时进入 `UpdateCallState`（全局）与 `UpdateCallStateForSlotId`（按槽位）两路处理。

#### Scenario: 观察者注册
- **WHEN** `CallControlManager::InitEvents` 执行
- **THEN** `CallStateReportProxy` 成为 `CallStateListener` 观察者之一

#### Scenario: VoIP 通话不入两路上报
- **WHEN** VoIP 通话状态变化回调到来
- **THEN** 两路上报均被跳过

### Requirement: 全局通话状态上报（UpdateCallState）
系统 SHALL 由 `CallStateReportProxy::UpdateCallState(callObjectPtr, nextState)` 计算全局前景通话并去重后上报：nextState 为 ANSWERED 时前景取触发对象本身，否则取 `CallObjectManager::GetForegroundCall(false)`（为空时退回触发对象）；取 `GetVoipCallState()` 结果（经 `CallControlManager::GetVoIPCallState` 把 CallStateToApp 映射为 TelCallState）作为兜底状态；前景通话处于 INCOMING/WAITING 或 ANSWERED 转换时取前景对象属性（ANSWERED 覆盖），无前景通话时按 VoIP 状态或 `currentCallState_` 兜底；`info.callState` 等于 `currentCallState_`（去重）或为 `CALL_STATUS_DISCONNECTING` 时不报；状态有变则更新 `currentCallState_` 并调用 `ReportCallState(callState, accountNumber)`，后者 SHALL 经 `TelephonyStateRegistryClient::UpdateCallState(callState, phoneNumber)` 上报（失败返回其错误码）。`UpdateCallStateForVoIPOrRestart()` SHALL 以空对象、IDLE 态再次执行全局处理（VoIP 结束/服务重启时校准全局状态）。

#### Scenario: 重复状态去重
- **WHEN** 计算出的全局状态与 `currentCallState_` 相同
- **THEN** 不向状态注册服务发送

#### Scenario: DISCONNECTING 状态不报
- **WHEN** 前景通话状态为 `CALL_STATUS_DISCONNECTING`
- **THEN** 直接跳过上报

#### Scenario: VoIP 结束复位
- **WHEN** `CallControlManager` 在 UnInit 或 VoIP 收尾路径调用 `UpdateCallStateForVoIPOrRestart()`
- **THEN** 以 IDLE 态走全局判定后再次上报

### Requirement: 按槽位通话状态上报（UpdateCallStateForSlotId）
系统 SHALL 由 `CallStateReportProxy::UpdateCallStateForSlotId(callObjectPtr, nextState)`：取对象属性，nextState 为 ANSWERED 覆盖 state，`CALL_STATUS_DISCONNECTING` 跳过；随后 `ReportCallStateForCallId(accountId, callState, accountNumber)` 经 `TelephonyStateRegistryClient::UpdateCallStateForSlotId(slotId, callState, incomingNumber)` 上报（失败返回其错误码）。上报的号码字段沿用 `CallAttributeInfo.accountNumber`。

#### Scenario: 状态带槽位上报
- **WHEN** 蜂窝通话状态变化且通过 Disconnecting 过滤
- **THEN** `UpdateCallStateForSlotId` 以通话 accountId 作为 slotId 上报（示例号码 unknown）

#### Scenario: 上报调用失败
- **WHEN** `TelephonyStateRegistryClient::UpdateCallStateForSlotId` 返回错误
- **THEN** `ReportCallStateForCallId` 返回该错误码并记日志 "NotifyCallStateUpdated failed"

### Requirement: 系统应用进程死亡复位 VoIP 状态
系统 SHALL 提供 `ApplicationStateObserver`（继承 `AppExecFwk::ApplicationStateObserverStub`，由 `CallControlManager::AppStateObserver()` 经 `RegisterApplicationStateObserver` 注册），仅覆写 `OnProcessDied(processData)`：当 `processData.processName == "ui"` 时调用 `CallControlManager::SetVoIPCallState(CALL_STATE_IDLE)` 且 `CallObjectManager::ClearVoipList()`。本类不订阅应用前后台切换，仅处理进程死亡事件。

#### Scenario: ui 进程死亡
- **WHEN** processName 为 "ui" 的进程死亡
- **THEN** VoIP 全局状态复位为 IDLE 且 VoIP 通话列表被清空

#### Scenario: 其它进程死亡
- **WHEN** processName 不是 "ui"
- **THEN** 不做任何处理

#### Scenario: 观察者仅进程死亡语义（不订阅前后台）
- **WHEN** 检索 `app_state_observer.h/cpp` 的能力面
- **THEN** 只有 `OnProcessDied` 一个覆写，没有前台/后台事件处理