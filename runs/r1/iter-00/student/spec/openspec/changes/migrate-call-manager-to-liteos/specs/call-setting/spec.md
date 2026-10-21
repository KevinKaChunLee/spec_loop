# Spec Delta

## MODIFIED Requirements

### Requirement: 呼叫等待转发
系统 SHALL 由 `CallSettingManager::GetCallWaiting`/`SetCallWaiting` 先经 `CallWaitingPolicy`（`CallNumberUtils::IsValidSlotId` 校验 slotId，失败返回 CALL_ERR_INVALID_SLOT_ID）校验，再转发到本 change 引入的 `CellularCallClient::GetInstance().GetCallWaiting`/`SetCallWaiting`（stub/ 打桩，方法名与基线 ICellularCall 接口一致，由 cellular_call 执行）；IPC 代理通道（`CellularCallConnection`）MUST NOT 保留，连接不可用时返回原基线空指针错误码语义。

#### Scenario: 无效 slotId 被拒绝
- **WHEN** 以 IsValidSlotId 校验不通过的 slotId 调用 GetCallWaiting(slotId)
- **THEN** 返回 CALL_ERR_INVALID_SLOT_ID，不发起任何转发

#### Scenario: 正常设置呼叫等待
- **WHEN** 以合法 slotId 调用 SetCallWaiting(slotId, true) 且打桩客户端可用
- **THEN** 转发 CellularCallClient::GetInstance().SetCallWaiting(true, slotId) 并透传其返回值

### Requirement: 呼叫限制转发
系统 SHALL 由 `CallSettingManager::GetCallRestriction` 校验 type 在 `CallRestrictionType::RESTRICTION_TYPE_ALL_INCOMING` 至 `RESTRICTION_TYPE_INCOMING_SERVICES` 范围内（越界返回 CALL_ERR_INVALID_RESTRICTION_TYPE）后转发 `CellularCallClient::GetInstance().GetCallRestriction`；`SetCallRestriction` 额外校验 info.mode 必须为 `RESTRICTION_MODE_DEACTIVATION` 或 `RESTRICTION_MODE_ACTIVATION`（否则返回 CALL_ERR_INVALID_RESTRICTION_MODE）后转发 `CellularCallClient::GetInstance().SetCallRestriction`；`SetCallRestrictionPassword` 复用 GetCallRestrictionPolicy 校验后经打桩客户端转发改密请求。

#### Scenario: 限制类型越界被拒绝
- **WHEN** GetCallRestriction(slotId, type) 传入超出 RESTRICTION_TYPE_INCOMING_SERVICES 的 type
- **THEN** 返回 CALL_ERR_INVALID_RESTRICTION_TYPE，不转发

#### Scenario: 非法限制模式被拒绝
- **WHEN** SetCallRestriction 传入 mode 既非 RESTRICTION_MODE_DEACTIVATION 也非 RESTRICTION_MODE_ACTIVATION
- **THEN** 返回 CALL_ERR_INVALID_RESTRICTION_MODE，不转发

#### Scenario: 限制密码修改转发
- **WHEN** 以合法 slotId 与 fac 调用 SetCallRestrictionPassword(slotId, fac, oldPassword, newPassword)
- **THEN** 转发 CellularCallClient::GetInstance().SetCallRestrictionPassword 并透传返回值

### Requirement: 呼叫转移转发
系统 SHALL 由 `CallSettingManager::GetCallTransferInfo` 经 `GetCallTransferInfoPolicy` 校验 type 在 `CallTransferType::TRANSFER_TYPE_UNCONDITIONAL` 至 `TRANSFER_TYPE_NOT_REACHABLE` 范围内后转发 `CellularCallClient::GetInstance().GetCallTransferInfo`；`SetCallTransferInfo` 额外经 `SetCallTransferInfoPolicy` 校验 info.settingType 必须为 CALL_TRANSFER_DISABLE/ENABLE/REGISTRATION/ERASURE 之一（否则 CALL_ERR_INVALID_TRANSFER_SETTING_TYPE）、转移时间在 MIN_HOUR~MAX_HOUR 与 MIN_MINUTE~MAX_MINUTE 界内（否则 CALL_ERR_INVALID_TRANSFER_TIME）、strlen(info.transferNum) 不超过 kMaxNumberLen（否则 CALL_ERR_NUMBER_OUT_OF_RANGE）后转发 `CellularCallClient::GetInstance().SetCallTransferInfo`；`CanSetCallTransferTime` 不做额外校验直接经打桩客户端转发并经出参 result 返回能力。

#### Scenario: 转移设置类型非法被拒绝
- **WHEN** SetCallTransferInfo 传入 settingType 不属于四种合法取值
- **THEN** 返回 CALL_ERR_INVALID_TRANSFER_SETTING_TYPE，不转发

#### Scenario: 转移时间越界被拒绝
- **WHEN** SetCallTransferInfo 传入 startHour 超出 MAX_HOUR 界限
- **THEN** 返回 CALL_ERR_INVALID_TRANSFER_TIME，不转发

#### Scenario: 查询能否设置转移时间
- **WHEN** 以合法 slotId 调用 CanSetCallTransferTime(slotId, result)
- **THEN** 直接转发 CellularCallClient::GetInstance().CanSetCallTransferTime(slotId, result) 并透传返回值

### Requirement: 通话偏好模式
系统 SHALL 由 `CallSettingManager::SetCallPreferenceMode` 将 mode 归一化：仅接受 CS_VOICE_ONLY、CS_VOICE_PREFERRED、IMS_PS_VOICE_PREFERRED、IMS_PS_VOICE_ONLY 四种取值，其他值一律改写为 `CS_VOICE_ONLY`，再转发 `CellularCallClient::GetInstance().SetCallPreferenceMode`（stub/ 打桩）。

#### Scenario: 非法模式归一为纯 CS
- **WHEN** SetCallPreferenceMode(slotId, mode) 传入不在四种取值内的 mode
- **THEN** 实际经打桩客户端转发的是 preferenceMode=CS_VOICE_ONLY

#### Scenario: 合法模式正常转发
- **WHEN** SetCallPreferenceMode(slotId, CS_VOICE_PREFERRED) 且打桩客户端可用
- **THEN** 转发 CellularCallClient::GetInstance().SetCallPreferenceMode(slotId, CS_VOICE_PREFERRED) 并透传返回值

### Requirement: IMS 配置与特性值转发
系统 SHALL 由 `CallSettingManager::GetImsConfig`/`GetImsFeatureValue`/`SetImsFeatureValue` 直接转发对应 `CellularCallClient::GetInstance()` 接口（stub/ 打桩）；`SetImsConfig` 在 item 为 `ITEM_VIDEO_QUALITY` 或 `ITEM_IMS_SWITCH_STATUS` 时将 u16string 值经 Str16ToStr8/StrToInt 转为 int 后走整数版转发，转换失败返回 TELEPHONY_ERR_STRTOINT_FAIL，其他 item 直接以字符串值转发。

#### Scenario: 数值型配置字符串转换失败
- **WHEN** SetImsConfig(slotId, ITEM_IMS_SWITCH_STATUS, value) 传入无法转为整数的字符串
- **THEN** 返回 TELEPHONY_ERR_STRTOINT_FAIL，不转发

#### Scenario: 非数值型配置直接转发
- **WHEN** SetImsConfig 传入 item 既非 ITEM_VIDEO_QUALITY 也非 ITEM_IMS_SWITCH_STATUS
- **THEN** 以字符串值转发 CellularCallClient::GetInstance().SetImsConfig(item, value, slotId)

### Requirement: IMS 开关与 VoNR 状态转发
系统 SHALL 由 `CallSettingManager::EnableImsSwitch`/`DisableImsSwitch` 分别转发 `CellularCallClient::GetInstance().SetImsSwitchStatus(slotId, true/false)`，`IsImsSwitchEnabled` 转发 `GetImsSwitchStatus` 经出参 enabled 返回；`SetVoNRState`/`GetVoNRState` 转发打桩客户端同名接口；打桩客户端接口不可用时 MUST 返回原基线空指针错误码 TELEPHONY_ERR_LOCAL_PTR_NULL（替代基线连接指针为空场景）。

#### Scenario: 启用 IMS 开关
- **WHEN** 打桩客户端可用时调用 EnableImsSwitch(slotId)
- **THEN** 转发 SetImsSwitchStatus(slotId, true) 并透传返回值

#### Scenario: 连接为空时报空指针错误
- **WHEN** 打桩 CellularCallClient 接口不可用（对应基线连接指针为空场景）时调用 GetVoNRState(slotId, state)
- **THEN** 返回 TELEPHONY_ERR_LOCAL_PTR_NULL（保留基线错误码语义）

### Requirement: 未完成 USSD 会话关闭
系统 SHALL 由 `CallSettingManager::CloseUnFinishedUssd` 先经 `CloseUnFinishedUssdPolicy` 校验 slotId 合法（失败返回 CALL_ERR_INVALID_SLOT_ID），再转发 `CellularCallClient::GetInstance().CloseUnFinishedUssd`（stub/ 打桩）关闭 cellular_call 侧未完成的 USSD 会话。

#### Scenario: 关闭未完成 USSD 会话
- **WHEN** 以合法 slotId 调用 CloseUnFinishedUssd(slotId) 且打桩客户端可用
- **THEN** 转发 CellularCallClient::GetInstance().CloseUnFinishedUssd(slotId) 并透传返回值

#### Scenario: 无效 slotId 被拒绝
- **WHEN** 以 IsValidSlotId 校验不通过的 slotId 调用 CloseUnFinishedUssd(slotId)
- **THEN** 返回 CALL_ERR_INVALID_SLOT_ID，不转发

### Requirement: 补充业务结果回报
系统 SHALL 在补充业务请求发出后由 cellular_call 经 `CallStatusCallback`（进程内直调，无 IPC stub）回报结果，并由 `CallAbilityReportProxy::ReportAsyncResults` 按 `CallResultReportId` 推给注册的应用回调：UpdateGetWaitingResult/UpdateSetWaitingResult（GET/SET_CALL_WAITING_REPORT_ID）、UpdateGetRestrictionResult/UpdateSetRestrictionResult/UpdateSetRestrictionPasswordResult（GET/SET_CALL_RESTRICTION_REPORT_ID、SET_CALL_RESTRICTION_PWD_REPORT_ID）、UpdateGetTransferResult/UpdateSetTransferResult（GET/SET_CALL_TRANSFER_REPORT_ID）、UpdateGetCallClipResult/UpdateGetCallClirResult/UpdateSetCallClirResult（GET_CALL_CLIP_ID、GET_CALL_CLIR_ID、SET_CALL_CLIR_ID）；`SendMmiCodeResult` 经打桩 EventHandler 延迟（替代 ffrt::submit_h）REPORT_SEND_USSD_DELAY_TIME 后上报 MMI 结果；非请求结果类型场景 MUST 保留不回调语义。

#### Scenario: 呼叫等待查询结果回报
- **WHEN** cellular_call 上报 UpdateGetWaitingResult(response)（response.result 为 0）
- **THEN** 以 GET_CALL_WAITING_REPORT_ID 与 result/status/classCw 字段 ReportAsyncResults 给应用

#### Scenario: MMI 码结果延迟回报
- **WHEN** cellular_call 上报 SendMmiCodeResult(info)
- **THEN** 经打桩 EventHandler 延迟 REPORT_SEND_USSD_DELAY_TIME 后经 ReportMmiCodeResult 上报，函数立即返回 TELEPHONY_SUCCESS

#### Scenario: CLIR 查询结果回报
- **WHEN** cellular_call 上报 UpdateGetCallClirResult(clirResponse)
- **THEN** 以 GET_CALL_CLIR_ID 与 result/action/clirStat 字段 ReportAsyncResults 给应用
