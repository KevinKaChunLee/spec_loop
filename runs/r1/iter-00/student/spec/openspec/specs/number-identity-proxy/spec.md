# 号码识别代理（Number Identity Proxy） Specification

## Purpose
描述号码识别/黄页标记能力的基线行为：号码识别数据更新通知服务与号码归属地/黄页标记的数据库查询。源码落点：`telephony_call_manager/services/number_identity_proxy/{include,src}`（`number_identity_service.cpp`：`NumberIdentityServiceHelper`/`NumberIdentityServiceProxy`）与 `telephony_call_manager/utils/{include,src}`（`number_identity_data_base_helper.cpp`：`NumberIdentityDataBaseHelper`）。该能力无专属编译宏：源文件无条件列入 `callmanager.gni` 的 `call_manager_sources`。

## Requirements

### Requirement: 号码识别数据更新通知
系统 SHALL 在 `CallBroadcastSubscriber::HsdrEventBroadcast` 收到数据包含 `com.numberidentity.devicenumber` 的公共事件时，调用 `NumberIdentityServiceHelper::NotifyNumberMarkDataUpdate`：通过 `AAFwk::ExtensionManagerClient::ConnectServiceExtensionAbility`（bundle `com.numberidentity`、ability `NumberIdentityServiceExtAbility`、`USER_ID` 100）连接号码识别服务，经 `NumberIdentityServiceProxy::NotifyNumberMarkDataUpdate` 以 `IMPORT_NUMBER_MARK_DATA_FILE` 发起数据更新通知，通知完成后断开连接；`working_` 标志置位期间 MUST NOT 重复发起通知。
#### Scenario: 触发数据更新通知
- **WHEN** HSDR 公共事件数据中出现 `com.numberidentity.devicenumber`
- **THEN** 连接 `NumberIdentityServiceExtAbility` 并发送 `IMPORT_NUMBER_MARK_DATA_FILE` 请求
#### Scenario: 通知进行中防重入
- **WHEN** 上一次通知尚未回调断开（`working_` 为 true）时再次收到触发事件
- **THEN** 跳过本次通知请求

### Requirement: 号码归属地查询
系统 SHALL 由 `NumberIdentityDataBaseHelper::Query` 通过 `DataShare::DataShareHelper`（以 `TELEPHONY_CALL_MANAGER_SYS_ABILITY_ID` 创建，URI `datashare:///numberlocationability`）按号码精确匹配查询归属地：查询结果行数为 0 时返回成功且 `numberLocation` 保持为空；否则读取 `number_location` 列值返回。
#### Scenario: 命中归属地
- **WHEN** 归属地数据库中存在该号码的记录
- **THEN** `numberLocation` 被填充为 `number_location` 列的值，`Query` 返回 true
#### Scenario: 未命中
- **WHEN** 查询返回结果行数为 0
- **THEN** `Query` 返回 `TELEPHONY_SUCCESS`，`numberLocation` 不被填充

### Requirement: 黄页与号码标记查询
系统 SHALL 由 `NumberIdentityDataBaseHelper::QueryYellowPageAndMark` 通过 URI `datashare:///numbermarkability/number_mark_info` 查询黄页与号码标记：结果行数为 0 时 `NumberMarkInfo.markType` 置为 `MARK_TYPE_NONE` 并返回成功；否则由 `SetMarkInfoValues` 读取 `markType`/`markContent`/`markCount`/`markSource`/`isCloud`/`markDetails` 填充 `NumberMarkInfo`。
#### Scenario: 命中黄页标记
- **WHEN** 号码标记库中存在该号码的标记记录
- **THEN** `NumberMarkInfo` 按列值填充（`isCloud` 列为 1 时置 true），`QueryYellowPageAndMark` 返回 true
#### Scenario: 无标记记录
- **WHEN** 查询结果行数为 0
- **THEN** `markType` 为 `MARK_TYPE_NONE`，返回 `TELEPHONY_SUCCESS`

### Requirement: 查询入口与更新回流
系统 SHALL 由 `CallNumberUtils::QueryNumberLocationInfo` 与 `CallNumberUtils::QueryYellowPageAndMarkInfo`（入参为通话号码）封装上述 DataShare 查询（返回 `TELEPHONY_ERR_DATABASE_READ_FAIL` 等错误码），并由 `NumberLocationUpdate`/`YellowPageAndMarkUpdate` 将查询结果写入通话对象（`SetNumberLocation`/`SetNumberMarkInfo`）后经 `CallAbilityReportProxy::ReportCallStateInfo` 上报；`YellowPageAndMarkUpdate` MUST 仅在系统参数 `const.global.region` 为 `CN` 时执行。
#### Scenario: 归属地回填上报
- **WHEN** `NumberLocationUpdate` 查询到非空且非 `default` 的归属地
- **THEN** 通话对象 `SetNumberLocation` 后上报通话信息
#### Scenario: 非中国区域跳过黄页
- **WHEN** `const.global.region` 不为 `CN`
- **THEN** `YellowPageAndMarkUpdate` 直接返回，不查询号码标记
