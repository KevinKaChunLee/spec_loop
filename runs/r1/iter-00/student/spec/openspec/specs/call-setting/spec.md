# 通话设置与补充业务（Call Setting）Specification

## Purpose
描述 HMOS `telephony_call_manager` 模块当前的通话设置与补充业务能力：`CallSettingManager` 作为策略校验层，将呼叫等待、呼叫限制（含改密）、呼叫转移、通话偏好、IMS 配置/特性值/开关、VoNR 状态、未完成 USSD 会话关闭等请求在参数校验后转发给 `CellularCallConnection`（延迟单例，IPC 代理到 cellular_call 模块），结果经 `CallStatusCallback` 异步回报给应用。源码落点：`telephony_call_manager/services/call_setting/{include,src}`，仅有 call_setting_manager.h/.cpp 一个类；转发目标为 `services/telephony_interaction/` 的 cellular_call_connection.cpp，结果回报落在 call_status_callback.cpp。控制开关：本子模块无 `callmanager.gni` 专属特性宏（补充业务不受特性宏控制，随 telephony_cellular_call 部件的 `ABILITY_CELLULAR_SUPPORT` 间接可用）。

## Requirements

### Requirement: 呼叫等待转发
系统 SHALL 由 `CallSettingManager::GetCallWaiting`/`SetCallWaiting` 先经 `CallWaitingPolicy`（`CallNumberUtils::IsValidSlotId` 校验 slotId，失败返回 CALL_ERR_INVALID_SLOT_ID）校验，再在 cellularCallConnectionPtr_ 为空时返回 TELEPHONY_ERR_LOCAL_PTR_NULL，否则转发到 `CellularCallConnection::GetCallWaiting`/`SetCallWaiting` 由 cellular_call 执行。

#### Scenario: 无效 slotId 被拒绝
- **WHEN** 以 IsValidSlotId 校验不通过的 slotId 调用 GetCallWaiting(slotId)
- **THEN** 返回 CALL_ERR_INVALID_SLOT_ID，不发起任何转发

#### Scenario: 正常设置呼叫等待
- **WHEN** 以合法 slotId 调用 SetCallWaiting(slotId, true) 且连接可用
- **THEN** 转发 CellularCallConnection::SetCallWaiting(true, slotId) 并透传其返回值

### Requirement: 呼叫限制转发
系统 SHALL 由 `CallSettingManager::GetCallRestriction` 校验 type 在 `CallRestrictionType::RESTRICTION_TYPE_ALL_INCOMING` 至 `RESTRICTION_TYPE_INCOMING_SERVICES` 范围内（越界返回 CALL_ERR_INVALID_RESTRICTION_TYPE）后转发 `GetCallRestriction`；`SetCallRestriction` 额外校验 info.mode 必须为 `RESTRICTION_MODE_DEACTIVATION` 或 `RESTRICTION_MODE_ACTIVATION`（否则返回 CALL_ERR_INVALID_RESTRICTION_MODE）；`SetCallRestrictionPassword` 复用 GetCallRestrictionPolicy 校验后转发改密请求。

#### Scenario: 限制类型越界被拒绝
- **WHEN** GetCallRestriction(slotId, type) 传入超出 RESTRICTION_TYPE_INCOMING_SERVICES 的 type
- **THEN** 返回 CALL_ERR_INVALID_RESTRICTION_TYPE，不转发

#### Scenario: 非法限制模式被拒绝
- **WHEN** SetCallRestriction 传入 mode 既非 RESTRICTION_MODE_DEACTIVATION 也非 RESTRICTION_MODE_ACTIVATION
- **THEN** 返回 CALL_ERR_INVALID_RESTRICTION_MODE，不转发

#### Scenario: 限制密码修改转发
- **WHEN** 以合法 slotId 与 fac 调用 SetCallRestrictionPassword(slotId, fac, oldPassword, newPassword)
- **THEN** 转发 CellularCallConnection::SetCallRestrictionPassword 并透传返回值

### Requirement: 呼叫转移转发
系统 SHALL 由 `CallSettingManager::GetCallTransferInfo` 经 `GetCallTransferInfoPolicy` 校验 type 在 `CallTransferType::TRANSFER_TYPE_UNCONDITIONAL` 至 `TRANSFER_TYPE_NOT_REACHABLE` 范围内后转发；`SetCallTransferInfo` 额外经 `SetCallTransferInfoPolicy` 校验 info.settingType 必须为 CALL_TRANSFER_DISABLE/ENABLE/REGISTRATION/ERASURE 之一（否则 CALL_ERR_INVALID_TRANSFER_SETTING_TYPE）、转移时间在 MIN_HOUR~MAX_HOUR 与 MIN_MINUTE~MAX_MINUTE 界内（否则 CALL_ERR_INVALID_TRANSFER_TIME）、strlen(info.transferNum) 不超过 kMaxNumberLen（否则 CALL_ERR_NUMBER_OUT_OF_RANGE）；`CanSetCallTransferTime` 不做额外校验直接转发并经出参 result 返回能力。

#### Scenario: 转移设置类型非法被拒绝
- **WHEN** SetCallTransferInfo 传入 settingType 不属于四种合法取值
- **THEN** 返回 CALL_ERR_INVALID_TRANSFER_SETTING_TYPE，不转发

#### Scenario: 转移时间越界被拒绝
- **WHEN** SetCallTransferInfo 传入 startHour 超出 MAX_HOUR 界限
- **THEN** 返回 CALL_ERR_INVALID_TRANSFER_TIME，不转发

#### Scenario: 查询能否设置转移时间
- **WHEN** 以合法 slotId 调用 CanSetCallTransferTime(slotId, result)
- **THEN** 直接转发 CellularCallConnection::CanSetCallTransferTime(slotId, result) 并透传返回值

### Requirement: 通话偏好模式
系统 SHALL 由 `CallSettingManager::SetCallPreferenceMode` 将 mode 归一化：仅接受 CS_VOICE_ONLY、CS_VOICE_PREFERRED、IMS_PS_VOICE_PREFERRED、IMS_PS_VOICE_ONLY 四种取值，其他值一律改写为 `CS_VOICE_ONLY`，再转发 `CellularCallConnection::SetCallPreferenceMode`。

#### Scenario: 非法模式归一为纯 CS
- **WHEN** SetCallPreferenceMode(slotId, mode) 传入不在四种取值内的 mode
- **THEN** 实际转发的是 preferenceMode=CS_VOICE_ONLY

### Requirement: IMS 配置与特性值转发
系统 SHALL 由 `CallSettingManager::GetImsConfig`/`GetImsFeatureValue`/`SetImsFeatureValue` 直接转发对应 `CellularCallConnection` 接口；`SetImsConfig` 在 item 为 `ITEM_VIDEO_QUALITY` 或 `ITEM_IMS_SWITCH_STATUS` 时将 u16string 值经 Str16ToStr8/StrToInt 转为 int 后走整数版转发，转换失败返回 TELEPHONY_ERR_STRTOINT_FAIL，其他 item 直接以字符串值转发。

#### Scenario: 数值型配置字符串转换失败
- **WHEN** SetImsConfig(slotId, ITEM_IMS_SWITCH_STATUS, value) 传入无法转为整数的字符串
- **THEN** 返回 TELEPHONY_ERR_STRTOINT_FAIL，不转发

#### Scenario: 非数值型配置直接转发
- **WHEN** SetImsConfig 传入 item 既非 ITEM_VIDEO_QUALITY 也非 ITEM_IMS_SWITCH_STATUS
- **THEN** 以字符串值转发 CellularCallConnection::SetImsConfig(item, value, slotId)

### Requirement: IMS 开关与 VoNR 状态转发
系统 SHALL 由 `CallSettingManager::EnableImsSwitch`/`DisableImsSwitch` 分别转发 `CellularCallConnection::SetImsSwitchStatus(slotId, true/false)`，`IsImsSwitchEnabled` 转发 `GetImsSwitchStatus` 经出参 enabled 返回；`SetVoNRState`/`GetVoNRState` 转发同名接口；连接指针为空时均返回 TELEPHONY_ERR_LOCAL_PTR_NULL。

#### Scenario: 启用 IMS 开关
- **WHEN** 连接可用时调用 EnableImsSwitch(slotId)
- **THEN** 转发 SetImsSwitchStatus(slotId, true) 并透传返回值

#### Scenario: 连接为空时报空指针错误
- **WHEN** cellularCallConnectionPtr_ 为空时调用 GetVoNRState(slotId, state)
- **THEN** 返回 TELEPHONY_ERR_LOCAL_PTR_NULL

### Requirement: 未完成 USSD 会话关闭
系统 SHALL 由 `CallSettingManager::CloseUnFinishedUssd` 先经 `CloseUnFinishedUssdPolicy` 校验 slotId 合法（失败返回 CALL_ERR_INVALID_SLOT_ID），再转发 `CellularCallConnection::CloseUnFinishedUssd` 关闭 cellular_call 侧未完成的 USSD 会话。

#### Scenario: 关闭未完成 USSD 会话
- **WHEN** 以合法 slotId 调用 CloseUnFinishedUssd(slotId) 且连接可用
- **THEN** 转发 CellularCallConnection::CloseUnFinishedUssd(slotId) 并透传返回值

### Requirement: 补充业务结果回报
系统 SHALL 在补充业务请求发出后由 cellular_call 经 `CallStatusCallback`（CallStatusCallbackStub）异步回报结果，并由 `CallAbilityReportProxy::ReportAsyncResults` 按 `CallResultReportId` 推给注册的应用回调：UpdateGetWaitingResult/UpdateSetWaitingResult（GET/SET_CALL_WAITING_REPORT_ID）、UpdateGetRestrictionResult/UpdateSetRestrictionResult/UpdateSetRestrictionPasswordResult（GET/SET_CALL_RESTRICTION_REPORT_ID、SET_CALL_RESTRICTION_PWD_REPORT_ID）、UpdateGetTransferResult/UpdateSetTransferResult（GET/SET_CALL_TRANSFER_REPORT_ID）、UpdateGetCallClipResult/UpdateGetCallClirResult/UpdateSetCallClirResult（GET_CALL_CLIP_ID、GET_CALL_CLIR_ID、SET_CALL_CLIR_ID）；`SendMmiCodeResult` 经 ffrt::submit_h 延迟 REPORT_SEND_USSD_DELAY_TIME 后上报 MMI 结果。

#### Scenario: 呼叫等待查询结果回报
- **WHEN** cellular_call 上报 UpdateGetWaitingResult(response)（response.result 为 0）
- **THEN** 以 GET_CALL_WAITING_REPORT_ID 与 result/status/classCw 字段 ReportAsyncResults 给应用

#### Scenario: MMI 码结果延迟回报
- **WHEN** cellular_call 上报 SendMmiCodeResult(info)
- **THEN** 延迟 REPORT_SEND_USSD_DELAY_TIME 后经 ReportMmiCodeResult 上报，函数立即返回 TELEPHONY_SUCCESS

#### Scenario: CLIR 查询结果回报
- **WHEN** cellular_call 上报 UpdateGetCallClirResult(clirResponse)
- **THEN** 以 GET_CALL_CLIR_ID 与 result/action/clirStat 字段 ReportAsyncResults 给应用
