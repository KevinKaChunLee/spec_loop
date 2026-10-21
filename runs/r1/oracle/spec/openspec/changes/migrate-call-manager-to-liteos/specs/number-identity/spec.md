# Spec Delta

## MODIFIED Requirements

### Requirement: 标记数据文件更新通知
系统 SHALL 由 `NumberIdentityServiceHelper`（`DECLARE_DELAYED_REF_SINGLETON`）保留 `working_` 原子标志防重与通知编排骨架；`AAFwk::ExtensionManagerClient::ConnectServiceExtensionAbility` 扩展连接（`NUMBER_IDENTITY_BUNDLE_NAME = "com.numberidentity"` / `NUMBER_IDENTITY_SERVICE_EXT_ABILITY = "NumberIdentityServiceExtAbility"`，`USER_ID = 100`）与 `SendRequest(NumberIdentityServiceMessageCode::IMPORT_NUMBER_MARK_DATA_FILE = 0)` 调用点以 `// todo!!! [numberIdentity]` 占位（不真正连接扩展、不触发导入），完成或失败后 `Disconnect()`（占位）；HSDR 广播触发链（`CallBroadcastSubscriber` 收到 "usual.event.HSDR_EVENT"）随广播不订阅而不迁移（订阅调用点 todo 占位）。
#### Scenario: HSDR 数据就绪广播触发通知
- **WHEN** HSDR 广播到达（广播订阅调用点为 `// todo!!! [broadcast]` 占位，不真实订阅）
- **THEN** 标记数据导入通知不被广播触发；`NotifyNumberMarkDataUpdate()` 仅可由测试/后续接口直调触发并走占位路径

#### Scenario: 通知调用点占位
- **WHEN** `NotifyNumberMarkDataUpdate()` 被调用
- **THEN** `working_` 防重判定执行，扩展连接与导入请求调用点为 todo 占位并按完成路径收尾

#### Scenario: 并发触发防重入
- **WHEN** 上一次通知尚未完成时再次触发
- **THEN** `working_` 标志使后续触发直接返回，不产生重复执行
