# Spec Delta

## MODIFIED Requirements

### Requirement: 补充业务接口转发与前置策略
系统 SHALL 由 `CallSettingManager` 的全部设置接口先过私有 Policy（`CallWaitingPolicy`/`GetCallRestrictionPolicy`/`SetCallRestrictionPolicy`/`GetCallTransferInfoPolicy`/`SetCallTransferInfoPolicy`/`CloseUnFinishedUssdPolicy`）再经 `CellularCallClient::GetInstance()` 桩转发同名接口（替代 `cellularCallConnectionPtr_` 的 IPC 转发）：`GetCallWaiting/SetCallWaiting`、`GetCallRestriction/SetCallRestriction/SetCallRestrictionPassword`、`GetCallTransferInfo/SetCallTransferInfo`、`CanSetCallTransferTime`。
#### Scenario: 设置呼叫等待
- **WHEN** 应用经 `CallControlManager::SetCallWaiting(slotId, activate)` 下发
- **THEN** `CallWaitingPolicy` 校验通过后以 `CellularCallClient::GetInstance().SetCallWaiting(...)` 桩转发，桩配置的结果经回调回填

### Requirement: IMS 配置与能力查询
系统 SHALL 由 `CallSettingManager` 提供 `SetCallPreferenceMode`、`GetImsConfig/SetImsConfig`（`ImsConfigItem`，string/int 两形态）、`GetImsFeatureValue/SetImsFeatureValue`（`FeatureType`）、`EnableImsSwitch/DisableImsSwitch/IsImsSwitchEnabled`、`SetVoNRState/GetVoNRState`，全部经 `CellularCallClient::GetInstance()` 桩转发同名接口。
#### Scenario: 查询 IMS 开关状态
- **WHEN** 应用查询 `IsImsSwitchEnabled(slotId, enabled)`
- **THEN** 经 `CellularCallClient::GetInstance().GetImsSwitchStatus(...)` 桩查询，桩配置结果回填 enabled

### Requirement: USSD 会话关闭
系统 SHALL 由 `CallSettingManager::CloseUnFinishedUssd(slotId)` 先经 `CloseUnFinishedUssdPolicy` 校验再经 `CellularCallClient::GetInstance().CloseUnFinishedUssd(slotId)` 桩转发，关闭未完成的 USSD 会话。
#### Scenario: MMI 码触发未完成 USSD 会话
- **WHEN** 应用在 USSD 会话未结束时调用 `CloseUnFinishedUssd`
- **THEN** 校验通过后经桩关闭未完成会话，后续 MMI 结果不再回调
