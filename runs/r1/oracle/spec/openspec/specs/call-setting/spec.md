# 补充业务设置（call-setting）Specification

## Purpose
描述 `telephony_call_manager/services/call_setting/` 的补充业务与设置管理：`CallSettingManager`（呼叫等待/呼叫限制/呼叫转移（UT 业务）、IMS 配置与开关、VoNR、USSD 会话关闭）。落点：`services/call_setting/src/call_setting_manager.cpp` 与 `services/call_setting/include/call_setting_manager.h`。该模块组无独有编译开关；底层依赖 `CellularCallConnection`（见 telephony-interaction 能力）。

## Requirements

### Requirement: 补充业务接口转发与前置策略
系统 SHALL 由 `CallSettingManager` 持有 `std::shared_ptr<CellularCallConnection> cellularCallConnectionPtr_`，全部设置接口先过私有 Policy（`CallWaitingPolicy`/`GetCallRestrictionPolicy`/`SetCallRestrictionPolicy`/`GetCallTransferInfoPolicy`/`SetCallTransferInfoPolicy`/`CloseUnFinishedUssdPolicy`）再转发 `CellularCallConnection` 同名接口：`GetCallWaiting/SetCallWaiting`、`GetCallRestriction/SetCallRestriction/SetCallRestrictionPassword`、`GetCallTransferInfo/SetCallTransferInfo`、`CanSetCallTransferTime`。
#### Scenario: 设置呼叫等待
- **WHEN** 应用经 `CallControlManager::SetCallWaiting(slotId, activate)` 下发
- **THEN** `CallWaitingPolicy` 校验通过后由 `CellularCallConnection::SetCallWaiting` 转发给 cellular_call

### Requirement: IMS 配置与能力查询
系统 SHALL 由 `CallSettingManager` 提供 `SetCallPreferenceMode`、`GetImsConfig/SetImsConfig`（`ImsConfigItem`，string/int 两形态）、`GetImsFeatureValue/SetImsFeatureValue`（`FeatureType`）、`EnableImsSwitch/DisableImsSwitch/IsImsSwitchEnabled`、`SetVoNRState/GetVoNRState`，全部转发 `CellularCallConnection` 同名接口。
#### Scenario: 查询 IMS 开关状态
- **WHEN** 应用查询 `IsImsSwitchEnabled(slotId, enabled)`
- **THEN** 结果经 `CallSettingManager` 转发 `CellularCallConnection::GetImsSwitchStatus` 后回填 enabled

### Requirement: USSD 会话关闭
系统 SHALL 由 `CallSettingManager::CloseUnFinishedUssd(slotId)` 先经 `CloseUnFinishedUssdPolicy` 校验再转发 `CellularCallConnection::CloseUnFinishedUssd`，关闭未完成的 USSD 会话。
#### Scenario: MMI 码触发未完成 USSD 会话
- **WHEN** 应用在 USSD 会话未结束时调用 `CloseUnFinishedUssd`
- **THEN** 未完成会话经协议栈侧关闭，后续 MMI 结果不再回调
