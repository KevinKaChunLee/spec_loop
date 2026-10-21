# Call Setting Management Specification

## Purpose
描述 HMOS `telephony_call_manager` 中补充业务设置管理器 `CallSettingManager`（`services/call_setting/src/call_setting_manager.cpp` + `include/call_setting_manager.h`）：作为 `CallControlManager`（门面见 call-manager-service 能力）与 `cellular_call` 模块之间的设置下发层，职责为呼叫等待、呼叫限制（含密码）、呼叫转移（含时间支持查询）、通话偏好模式、IMS 配置与特性值、VoLTE/VoNR 开关、未完 USSD 会话关闭等设置的参数校验（`CallWaitingPolicy` 等 6 个 Policy 私有函数）与远程调用转发（经构造期缓存的 `DelayedSingleton<CellularCallConnection>` 实例 `cellularCallConnectionPtr_` 下行到 cellular_call）。本规格为移植前现状基线，不涉及裁剪决策。本能力不涉及条件编译特性宏。

## Requirements

### Requirement: 呼叫等待设置与查询
系统 SHALL 由 `CallSettingManager::GetCallWaiting(slotId)`/`SetCallWaiting(slotId, activate)` 先经 `CallWaitingPolicy(slotId)` 校验槽位号有效性（`CallNumberUtils::IsValidSlotId`，失败返回 `CALL_ERR_INVALID_SLOT_ID`），再转发 `cellularCallConnectionPtr_->GetCallWaiting(slotId)` / `SetCallWaiting(activate, slotId)`；连接指针为空返回 `TELEPHONY_ERR_LOCAL_PTR_NULL`。

#### Scenario: 非法槽位拨查
- **WHEN** 以无效 slotId 调用 `SetCallWaiting`
- **THEN** 不发起远程调用，返回 `CALL_ERR_INVALID_SLOT_ID`

#### Scenario: 查询转发
- **WHEN** slotId 合法且连接有效
- **THEN** 转发 `CellularCallConnection::GetCallWaiting(slotId)` 并透传其返回码

### Requirement: 呼叫限制设置、查询与密码修改
系统 SHALL 由 `CallSettingManager::GetCallRestriction(slotId, type)`/`SetCallRestriction(slotId, info)`/`SetCallRestrictionPassword(slotId, fac, oldPassword, newPassword)` 完成：`GetCallRestrictionPolicy` 校验槽位有效且 type 在 `RESTRICTION_TYPE_ALL_INCOMING..RESTRICTION_TYPE_INCOMING_SERVICES` 范围（失败返回 `CALL_ERR_INVALID_RESTRICTION_TYPE`）；`SetCallRestrictionPolicy` 额外校验 `info.mode` 属于 `RESTRICTION_MODE_DEACTIVATION/ACTIVATION`（失败返回 `CALL_ERR_INVALID_RESTRICTION_MODE`）；随后分别转发 `GetCallRestriction(type, slotId)`/`SetCallRestriction(info, slotId)`/`SetCallRestrictionPassword(slotId, fac, oldPassword, newPassword)`，指针为空返回 `TELEPHONY_ERR_LOCAL_PTR_NULL`。`SetCallRestriction`/`SetCallRestrictionPassword` 打日志记录 slotId 与业务参数，不打印密码明文之外内容（密码不出现在日志格式串中）。

#### Scenario: 限制类型越界
- **WHEN** type 超出枚举范围调用 `GetCallRestriction`
- **THEN** 返回 `CALL_ERR_INVALID_RESTRICTION_TYPE` 且不远程调用

#### Scenario: 修改 restrictionPassword 成功
- **WHEN** slot 与 fac 合法且连接有效
- **THEN** 新旧密码透传 `CellularCallConnection::SetCallRestrictionPassword`

### Requirement: 呼叫转移设置、查询与时间支持判断
系统 SHALL 由 `CallSettingManager::GetCallTransferInfo(slotId, type)` 校验（`GetCallTransferInfoPolicy`：槽位有效 + type 在 `TRANSFER_TYPE_UNCONDITIONAL..TRANSFER_TYPE_NOT_REACHABLE`）后转发 `GetCallTransferInfo(type, slotId)`；`SetCallTransferInfo(slotId, info)` 经 `SetCallTransferInfoPolicy` 校验 type 范围、`info.settingType` 属于 CALL_TRANSFER_DISABLE/ENABLE/REGISTRATION/ERASURE 四值（失败返回 `CALL_ERR_INVALID_TRANSFER_SETTING_TYPE`）、起止时分在允许范围（`MIN_HOUR/MAX_HOUR/MIN_MINUTE/MAX_MINUTE`，失败返回 `CALL_ERR_INVALID_TRANSFER_TIME`）、`info.transferNum` 长度不超 `kMaxNumberLen`（失败返回 `CALL_ERR_NUMBER_OUT_OF_RANGE`）后转发 `SetCallTransferInfo(info, slotId)`；`CanSetCallTransferTime(slotId, result)` 不做参数策略校验直接转发。

#### Scenario: 非法转移时间段
- **WHEN** `info.startHour/endHour/startMinute/endMinute` 越界
- **THEN** 返回 `CALL_ERR_INVALID_TRANSFER_TIME`，不发起设置

#### Scenario: 转移号码超长
- **WHEN** `transferNum` 长度大于 `kMaxNumberLen`（示例号码以 unknown 占位）
- **THEN** 返回 `CALL_ERR_NUMBER_OUT_OF_RANGE`

#### Scenario: 时间支持查询
- **WHEN** 连接非空调用 `CanSetCallTransferTime`
- **THEN** 透传 `CellularCallConnection::CanSetCallTransferTime(slotId, result)` 结果

### Requirement: 通话偏好模式收窄
系统 SHALL 由 `CallSettingManager::SetCallPreferenceMode(slotId, mode)` 在 mode 为 CS_VOICE_ONLY/CS_VOICE_PREFERRED/IMS_PS_VOICE_PREFERRED/IMS_PS_VOICE_ONLY 之一时原样下传，否则静默收窄为 `CS_VOICE_ONLY` 后转发 `SetCallPreferenceMode(slotId, preferenceMode)`。

#### Scenario: 非法偏好值
- **WHEN** mode 不属于四种合法枚举
- **THEN** 下发值变为 `CS_VOICE_ONLY`

### Requirement: IMS 配置查询与设置
系统 SHALL 由 `CallSettingManager::GetImsConfig(slotId, item)` 直接转发 `GetImsConfig(item, slotId)`；`SetImsConfig(slotId, item, value)` 对 `ITEM_VIDEO_QUALITY` 与 `ITEM_IMS_SWITCH_STATUS` 先做 `StrToInt(Str16ToStr8(value), flag)` 转整数，成功则以整型转发 `SetImsConfig(item, flag, slotId)`，失败返回 `TELEPHONY_ERR_STRTOINT_FAIL`；其余 item 以字符串形式转发 `SetImsConfig(item, Str16ToStr8(value), slotId)`。

#### Scenario: 开关状态项以整型下发
- **WHEN** item 为 `ITEM_IMS_SWITCH_STATUS` 且 value 可解析为整数
- **THEN** 以整型重载 `SetImsConfig` 下发

#### Scenario: 字符串转整数失败
- **WHEN** item 为 `ITEM_VIDEO_QUALITY` 且 value 无法转整数
- **THEN** 返回 `TELEPHONY_ERR_STRTOINT_FAIL`，不下发

### Requirement: IMS 特性值查询与设置
系统 SHALL 由 `CallSettingManager::GetImsFeatureValue(slotId, type)`/`SetImsFeatureValue(slotId, type, value)` 在连接指针判空（`TELEPHONY_ERR_LOCAL_PTR_NULL`）后分别转发 `GetImsFeatureValue(type, slotId)`/`SetImsFeatureValue(type, value, slotId)`。

#### Scenario: 查询特性值
- **WHEN** 连接有效
- **THEN** 透传 `CellularCallConnection::GetImsFeatureValue` 返回码

### Requirement: VoLTE（IMS）开关
系统 SHALL 由 `CallSettingManager::EnableImsSwitch(slotId)`/`DisableImsSwitch(slotId)` 判空后分别转发 `SetImsSwitchStatus(slotId, true/false)`，`IsImsSwitchEnabled(slotId, enabled)` 判空后转发 `GetImsSwitchStatus(slotId, enabled)`。

#### Scenario: 启停开关
- **WHEN** 分别调用 `EnableImsSwitch`/`DisableImsSwitch`
- **THEN** 经 `SetImsSwitchStatus` 以 true/false 下发

### Requirement: VoNR 状态设置与查询
系统 SHALL 由 `CallSettingManager::SetVoNRState(slotId, state)`/`GetVoNRState(slotId, state)` 判空后转发 `CellularCallConnection::SetVoNRState/GetVoNRState`。

#### Scenario: 查询 VoNR 状态
- **WHEN** 连接非空调用 `GetVoNRState`
- **THEN** 透传结果与 state 出参

### Requirement: 未完 USSD 会话关闭
系统 SHALL 由 `CallSettingManager::CloseUnFinishedUssd(slotId)` 先经 `CloseUnFinishedUssdPolicy(slotId)` 校验槽位有效（失败返回 `CALL_ERR_INVALID_SLOT_ID`），判空后转发 `CellularCallConnection::CloseUnFinishedUssd(slotId)`。

#### Scenario: 关闭非法槽位 USSD
- **WHEN** slotId 无效
- **THEN** 返回 `CALL_ERR_INVALID_SLOT_ID`，不发起远程调用

### Requirement: 连接对象缺失统一降级
系统 SHALL 对所有经 `cellularCallConnectionPtr_` 下发的方法在指针为空时打印 "cellularCallConnectionPtr_ is nullptr" 日志并返回 `TELEPHONY_ERR_LOCAL_PTR_NULL`，不下发任何远程调用（`SetCallPreferenceMode` 除外：其不加判空直接调用，欠缺点留在基线如实记录）。

#### Scenario: 连接缺省
- **WHEN** `cellularCallConnectionPtr_` 为空时调用 `GetImsConfig`
- **THEN** 返回 `TELEPHONY_ERR_LOCAL_PTR_NULL`

#### Scenario: 判空豁免（现状）
- **WHEN** 指针为空时调用 `SetCallPreferenceMode`
- **THEN** 直接解引用连接对象（基线现状无判空保护）