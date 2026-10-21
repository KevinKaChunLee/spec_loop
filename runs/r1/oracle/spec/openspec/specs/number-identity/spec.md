# 号码识别数据源（number-identity）Specification

## Purpose
描述 `telephony_call_manager/services/number_identity_proxy/` 的号码识别数据源模块组：`NumberIdentityServiceHelper`（黄页/号码标记数据文件更新通知）。落点：`services/number_identity_proxy/src/number_identity_service.cpp` 与 `include/number_identity_service.h`。该模块组无独有编译开关，连接方式为 `AAFwk::ExtensionManagerClient::ConnectServiceExtensionAbility`（非 dlopen）。号码标记的实际查询入口在 `CallNumberUtils::QueryYellowPageAndMarkInfo`（见 call-manager-utils 能力），本模块只负责通知 `com.numberidentity` 侧导入标记数据文件。

## Requirements

### Requirement: 标记数据文件更新通知
系统 SHALL 由 `NumberIdentityServiceHelper`（`DECLARE_DELAYED_REF_SINGLETON`）以 `working_` 原子标志防重入，连接 `NUMBER_IDENTITY_BUNDLE_NAME = "com.numberidentity"` / `NUMBER_IDENTITY_SERVICE_EXT_ABILITY = "NumberIdentityServiceExtAbility"`（`USER_ID = 100`）后经 `NumberIdentityServiceProxy : IRemoteProxy<INumberIdentityService>`（descriptor `u"com.numberidentity:NumberIdentityService"`）以 `SendRequest(NumberIdentityServiceMessageCode::IMPORT_NUMBER_MARK_DATA_FILE = 0)` 触发标记数据导入，完成或失败后 `Disconnect()`。
#### Scenario: HSDR 数据就绪广播触发通知
- **WHEN** `CallBroadcastSubscriber` 收到 "usual.event.HSDR_EVENT" 且 data 含 "com.numberidentity.devicenumber"
- **THEN** `NumberIdentityServiceHelper::NotifyNumberMarkDataUpdate()` 异步（`ffrt::submit`，qos_background）连接扩展并请求导入标记数据文件

#### Scenario: 并发触发防重入
- **WHEN** 上一次通知尚未完成时再次触发
- **THEN** `working_` 标志使后续触发直接返回，不产生并发连接
