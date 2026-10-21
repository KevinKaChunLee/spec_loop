# Spec Delta

## REMOVED Requirements

### Requirement: 回调死亡回收

**Reason**: AGENTS 明确 liteOS 不实现 IPC 调用；design D3 裁决所有 death recipient 传输类不迁移（`call_ability_callback_death_recipient.cpp` 在 D7 被删文件表 services 侧），单进程直调环境下应用回调对象的远端死亡通知不可达。
**Migration**: 删除 `services/call_report/src/call_ability_callback_death_recipient.cpp/.h`（`OnRemoteDied` 的 `object.promote()` 提升 `wptr`→`sptr<ICallAbilityCallback>`、转调 `CallAbilityReportProxy::UnRegisterCallBack` 的按远端对象移除链）；`CallAbilityReportProxy::RegisterCallBack` 中为 `AsObject()` 挂接 DeathRecipient 的调用点删除（见本 delta MODIFIED「应用侧回调注册与解除」条）；观察者生命周期改由 `UnRegisterCallBack` 解除接口与进程收尾清理承载（liteOS 单进程、服务直接持有回调对象指针）。恢复条件：恢复 IPC 形态时按基线重建死亡回收类与挂接点。

### Requirement: 系统应用进程死亡复位 VoIP 状态

**Reason**: `ApplicationStateObserver` 依赖 `AppExecFwk::ApplicationStateObserverStub` 的应用管理服务订阅与进程死亡 IPC 通知，liteOS 无该系统服务通路（AGENTS 不实现 IPC、不迁移 ability_runtime 系外部依赖；design D2/D3）；死亡通知路径整体删除（已定裁决）。
**Migration**: 删除 `services/call_report/src/app_state_observer.cpp/.h`（`OnProcessDied(processData)` 的 `processName == "ui"` 判定、`CallControlManager::SetVoIPCallState(CALL_STATE_IDLE)` + `CallObjectManager::ClearVoipList()` 复位链）；`CallControlManager::AppStateObserver()` 的 `RegisterApplicationStateObserver` 注册调用点不迁移；VoIP 全局状态复位由保留路径承载（`CallControlManager::UnInit`/`UpdateCallStateForVoIPOrRestart()`，见本 delta MODIFIED「全局通话状态上报（UpdateCallState）」条；`ClearVoipList` 冲突链见 telephony-interaction delta VoipCallConnection 条）。恢复条件：接入应用状态订阅框架后按基线重建观察者与复位链。

## MODIFIED Requirements

### Requirement: 应用侧回调注册与解除

系统 SHALL 由 `CallAbilityReportProxy::RegisterCallBack(callback, bundleInfo)`（`services/call_report/src/call_ability_report_proxy.cpp`）判空回调后将 `bundleInfo` 写入回调（`SetBundleInfo`）并加入 `callbackPtrList_`（基线 `std::list<sptr<ICallAbilityCallback>>` 按 design D5 换 `std::shared_ptr` 持有；基线 `mutex_` 保护删除、不设替代，design D6 锁行、D8 单线程）；基线随后为 `AsObject()` 挂接 `CallAbilityCallbackDeathRecipient` 的调用点删除（无 IPC，见本 delta REMOVED「回调死亡回收」条）。`UnRegisterCallBack(bundleInfo)` SHALL 按注册时记下的 bundleInfo 匹配后移除一项；`UnRegisterCallBack` 的按对象指针匹配移除形态 SHALL 保留（基线按远端 `IRemoteObject` 匹配改为按直持的回调对象指针匹配，语义一致）；两者在列表为空时返回 `TELEPHONY_ERR_LOCAL_PTR_NULL`，正常路径返回 `TELEPHONY_SUCCESS`（照抄）；析构时遍历清空全部回调（照抄）。

#### Scenario: 重复注册
- **WHEN** 同一应用再次注册不同回调对象并携带相同 bundleInfo
- **THEN** 列表中出现两个表项（无去重），两次回报均能到达（照抄）

#### Scenario: 空回调对象
- **WHEN** `RegisterCallBack` 收到空的 `callAbilityCallbackPtr`
- **THEN** 返回 `TELEPHONY_ERR_LOCAL_PTR_NULL`，不入列表（照抄）

#### Scenario: 按 bundleInfo 解除
- **WHEN** `UnRegisterCallBack(bundleInfo)` 且某表项 `GetBundleInfo()` 相等
- **THEN** 该表项被移除并停止接收回报（照抄）

测试落点：`test/unittest/call_manager_zero_gtest`（zero_branch 系，含 `zero_branch4_test.cpp`/`zero_branch6_test.cpp` 的 CallAbilityReportProxy 用例面）新增注册/解除矩阵与智能指针持有断言。

### Requirement: 通话详情多播（CallStateUpdated）

系统 SHALL 由 `CallAbilityReportProxy::CallStateUpdated(callObjectPtr, priorState, nextState)` 保留全部判定：取 `CallAttributeInfo` 后截断 `accountNumber` 中首个 `,` 或 `;`（截断处写入 '\0'）且长度限幅 `kMaxNumberLen`；`nextState == CALL_STATUS_ANSWERED` 时置 `info.callState` 为 ANSWERED；随后 `ReportCallStateInfo(info)` 多播。`ReportCallStateInfo(info)` SHALL 给全部观察者直调 `OnCallDetailsChange`（单个失败记日志继续下一个；回报直调形态见本 delta MODIFIED「应用回报 IPC 封装（CallAbilityCallbackProxy）」条）；定向版本 `ReportCallStateInfo(info, bundleInfo)` SHALL 只发给 `GetBundleInfo()` 相等的一个观察者（照抄）。基线两路多播成功后联动 `BluetoothCallManager::SendCallDetailsChange(callId, callState)` 的调用点随 BLUETOOTH 类型通话删除（AGENTS「功能范围」；design D7 `bluetooth_call_manager.cpp` 删除）。

#### Scenario: 携带分机分隔符的号码
- **WHEN** 通话属性 `accountNumber` 含 `,`（示例 unknown,unknown）
- **THEN** 上报给观察者的号码在 `,` 处截断（照抄）

#### Scenario: 应答态覆盖
- **WHEN** nextState 为 `CALL_STATUS_ANSWERED`
- **THEN** 上报的 `callState` 为 ANSWERED（照抄）

#### Scenario: 定向上报
- **WHEN** `ObserverOnCallDetailsChange()` 触发按 bundleInfo 的定向上报（见 call-manager-service delta）
- **THEN** 只有匹配 bundleInfo 的观察者收到 `OnCallDetailsChange`（照抄）

测试落点：`test/unittest/call_manager_zero_gtest`（zero_branch 系）新增截断/覆盖/定向多播用例与蓝牙联动删除负向断言。

### Requirement: 事件与结果多播族

系统 SHALL 由 `CallAbilityReportProxy` 提供同构的多播函数（遍历 `callbackPtrList_`，单个失败继续；基线 `mutex_` 保护删除、不设替代，design D8），回报直调观察者对象（无 IPC 封装层）：`CallEventUpdated(info)`→`OnCallEventChange`；`CallDestroyed(details)`→`OnCallDisconnectedCause`；`ReportAsyncResults(reportId, resultInfo)`→`OnReportAsyncResults`；`ReportMmiCodeResult(info)`→`OnReportMmiCodeResult`；`ReportAudioDeviceChange(info)`→`OnReportAudioDeviceChange`；`ReportPostDialDelay(str)`→`OnReportPostDialDelay`；`ReportPhoneStateChange` 的同构多播形态保留但唯一调用方 `BluetoothCallManager` 随蓝牙删除（AGENTS BLUETOOTH 不支持；design D7），liteOS 上无调用可达；`MeeTimeStateUpdated(info, ...)`→`ReportMeeTimeStateInfo`→`OnMeeTimeDetailsChange` 保留（VoIP/畅连上报面，VoIP 冲突链保留，AGENTS「暂不支持 VOIP……依赖后续跟 meetime 畅连通话」）；基线 `AppExecFwk::PacMap` 参数按 design D5 换普通结构体。以下多播函数删除：`OttCallRequest`（OTT 类型通话删除，AGENTS「功能范围」；上游 `ReportOttCallEventInfo` 入口已随 call-manager-service delta 删除，`com.ohos.callservice` 定向过滤不再可达）；`ReportImsCallModeChange`/`ReportCallSessionEventChange`/`ReportPeerDimensionsChange`/`ReportCallDataUsageChange`/`ReportCameraCapabilities`（视频通话与媒体面事件链删除，AGENTS 视频通话不支持；上游 `CallStatusCallback` 媒体面回调族已随 telephony-interaction delta 删除，视频对象族见 call-object-management delta）。

#### Scenario: MMI 码结果多播
- **WHEN** 补充业务操作产出 `MmiCodeInfo` 并调用 `ReportMmiCodeResult`
- **THEN** 全部观察者各收一次 `OnReportMmiCodeResult`（直调，照抄）

#### Scenario: OTT 请求只给通话服务
- **WHEN** 基线 `OttCallRequest` 时列表中存在非 com.ohos.callservice 的观察者
- **THEN** 因 OTT 类型通话删除（AGENTS），`OttCallRequest` 多播与定向过滤不迁移；场景改写为负向断言（该多播函数无调用可达）

#### Scenario: 单个观察者回报失败不中断
- **WHEN** 列表中第一个回调返回非 `TELEPHONY_SUCCESS`
- **THEN** 记日志后继续尝试其余回调（照抄）

测试落点：`test/unittest/call_manager_zero_gtest`（zero_branch 系）新增保留多播族直调矩阵用例与 OTT/视频媒体面多播删除负向断言。

### Requirement: 应用回报 IPC 封装（CallAbilityCallbackProxy）

系统 SHALL 将基线 `CallAbilityCallbackProxy`（`services/call_report/src/call_ability_callback_proxy.cpp`，`IRemoteProxy<ICallAbilityCallback>`）的 IPC 封装删除、回报直调化（design D3：proxy 传输类不迁移，应用侧注册的回调由服务直接持有对象指针调用）：每个回报 SHALL 以结构体直调观察者对象的 `OnXxx` 方法（`OnCallDetailsChange`/`OnMeeTimeDetailsChange` 携带 `CallAttributeInfo` 结构体，不再经 `CallManagerUtils::WriteCallAttributeInfo` 序列化组包；`OnCallEventChange` 携带 `CallEventInfo` 结构体，不再 `WriteRawData`）；基线 `CallManagerCallAbilityInterfaceCode` 码位（`UPDATE_CALL_STATE_INFO`/`UPDATE_MEETIME_STATE_INFO`/`UPDATE_CALL_EVENT`/`UPDATE_CALL_DISCONNECTED_CAUSE`/`UPDATE_CALL_ASYNC_RESULT_REQUEST`/`UPDATE_MMI_CODE_RESULT_REQUEST`/`REPORT_OTT_CALL_REQUEST`/`UPDATE_AUDIO_DEVICE_CHANGE_RESULT_REQUEST`/`REPORT_POST_DIAL_DELAY`/`UPDATE_IMS_CALL_MODE_RECEIVE`/`CALL_SESSION_EVENT_CHANGE`/`PEERD_DIMENSIONS_CHANGE`/`CALL_DATA_USAGE_CHANGE`/`CAMERA_CAPABILITIES_CHANGE`/`UPDATE_PHONE_STATE`）原样保留为 ABI 约定、不再承载实际 IPC 传输（design D3，需人工复核：后续恢复系统形态须保证枚举值与基线一致）；基线 `SendRequest`（TF_ASYNC）、`WriteInterfaceToken` 描述符写入与 `Remote()` 为空返回 `TELEPHONY_ERR_IPC_CONNECT_STUB_FAIL` 的分支不迁移（单进程无对端 broker）。

#### Scenario: 描述符写入失败
- **WHEN** 基线 `WriteInterfaceToken` 失败
- **THEN** 因 IPC 封装层删除（design D3），描述符写入与 `TELEPHONY_ERR_WRITE_DESCRIPTOR_TOKEN_FAIL` 失败分支不迁移；场景改写为负向断言（直调路径无该失败态）

#### Scenario: 通话详情序列化
- **WHEN** 发送 `OnCallDetailsChange`
- **THEN** 直调传递 `CallAttributeInfo` 结构体（不再以 `UPDATE_CALL_STATE_INFO` 码位组包、不再经 `WriteCallAttributeInfo` 序列化），观察者方法被同步调用（语义等价照抄）

测试落点：`test/unittest/call_manager_zero_gtest`（zero_branch 系）新增直调回报用例（结构体字段矩阵、同步调用断言）与 IPC 封装删除负向断言。

### Requirement: 状态监听接入（CallStateListenerBase）

系统 SHALL 让 `CallStateReportProxy`（`services/call_report/src/call_state_report_proxy.cpp`）继承 `CallStateListenerBase`（虚函数 `CallStateUpdated/MeeTimeStateUpdated` 等，`services/call/include/call_state_listener_base.h`），由 `CallControlManager::InitEvents`（`services/call/src/call_control_manager.cpp`）经 `callStateListenerPtr_->AddOneObserver(DelayedSingleton<CallStateReportProxy>::GetInstance())` 纳入 `CallStateListener` 观察者集合（注册链照抄），通话状态变化时经该监听器回调 `CallStateReportProxy::CallStateUpdated`。`CallStateUpdated` SHALL 对 `CallType::TYPE_VOIP` 的通话直接跳过（日志 "voip call no need to report call state"）、空对象跳过（照抄），否则同时进入 `UpdateCallState`（全局）与 `UpdateCallStateForSlotId`（按槽位）两路处理——两路上报并存保留（两路消费方不同：全局面向状态注册的全局监听、带槽位面向按卡槽订阅方；行为保持默认，design 决策 14）。

#### Scenario: 观察者注册
- **WHEN** `CallControlManager::InitEvents` 执行
- **THEN** `CallStateReportProxy` 成为 `CallStateListener` 观察者之一（照抄）

#### Scenario: VoIP 通话不入两路上报
- **WHEN** VoIP 通话状态变化回调到来
- **THEN** 两路上报均被跳过（照抄）

测试落点：`test/unittest/call_manager_zero_gtest`（zero_branch 系）新增监听接入与 VoIP 跳过用例（经桩注入通话状态驱动）。

### Requirement: 全局通话状态上报（UpdateCallState）

系统 SHALL 由 `CallStateReportProxy::UpdateCallState(callObjectPtr, nextState)` 保留全局前景通话计算与去重上报链（照抄）：nextState 为 ANSWERED 时前景取触发对象本身，否则取 `CallObjectManager::GetForegroundCall(false)`（为空时退回触发对象）；取 `GetVoipCallState()` 结果（经 `CallControlManager::GetVoIPCallState` 把 CallStateToApp 映射为 TelCallState）作为兜底状态；前景通话处于 INCOMING/WAITING 或 ANSWERED 转换时取前景对象属性（ANSWERED 覆盖），无前景通话时按 VoIP 状态或 `currentCallState_` 兜底；`info.callState` 等于 `currentCallState_`（去重）或为 `CALL_STATUS_DISCONNECTING` 时不报；状态有变则更新 `currentCallState_` 并调用 `ReportCallState(callState, accountNumber)`。`ReportCallState` 的出口 SHALL 改经 `stub/state_registry_client` 桩的 `TelephonyStateRegistryClient::UpdateCallState(callState, phoneNumber)`（基线对 core_service `.telephonyStateRegistry` 的 IPC 上报出口，design D4 落点；失败返回其错误码照抄）。`UpdateCallStateForVoIPOrRestart()` SHALL 以空对象、IDLE 态再次执行全局处理（照抄；基线 `ApplicationStateObserver` 进程死亡触发的复位路径删除，VoIP 收尾/UnInit 校准路径保留，见本 delta REMOVED「系统应用进程死亡复位 VoIP 状态」条）。

#### Scenario: 重复状态去重
- **WHEN** 计算出的全局状态与 `currentCallState_` 相同
- **THEN** 不向状态注册出口发送（照抄）

#### Scenario: DISCONNECTING 状态不报
- **WHEN** 前景通话状态为 `CALL_STATUS_DISCONNECTING`
- **THEN** 直接跳过上报（照抄）

#### Scenario: VoIP 结束复位
- **WHEN** `CallControlManager` 在 UnInit 或 VoIP 收尾路径调用 `UpdateCallStateForVoIPOrRestart()`
- **THEN** 以 IDLE 态走全局判定后再次上报（照抄）

测试落点：`test/unittest/call_manager_zero_gtest`（zero_branch 系）新增全局上报判定链用例（去重/DISCONNECTING/IDLE 复位矩阵）与 state_registry 桩出口断言。

### Requirement: 按槽位通话状态上报（UpdateCallStateForSlotId）

系统 SHALL 由 `CallStateReportProxy::UpdateCallStateForSlotId(callObjectPtr, nextState)` 保留（照抄）：取对象属性，nextState 为 ANSWERED 覆盖 state，`CALL_STATUS_DISCONNECTING` 跳过；随后 `ReportCallStateForCallId(accountId, callState, accountNumber)` 经 `stub/state_registry_client` 桩的 `TelephonyStateRegistryClient::UpdateCallStateForSlotId(slotId, callState, incomingNumber)` 上报（design D4 落点；失败返回其错误码照抄）；上报的号码字段沿用 `CallAttributeInfo.accountNumber`（照抄）。

#### Scenario: 状态带槽位上报
- **WHEN** 蜂窝通话状态变化且通过 Disconnecting 过滤
- **THEN** `UpdateCallStateForSlotId` 以通话 accountId 作为 slotId 上报（示例号码 unknown，经 state_registry 桩可断言入参；照抄）

#### Scenario: 上报调用失败
- **WHEN** state_registry 桩的 `UpdateCallStateForSlotId` 返回错误
- **THEN** `ReportCallStateForCallId` 返回该错误码并记日志 "NotifyCallStateUpdated failed"（照抄）

测试落点：`test/unittest/call_manager_zero_gtest`（zero_branch 系）新增带槽位上报用例（桩两态返回值矩阵）。
