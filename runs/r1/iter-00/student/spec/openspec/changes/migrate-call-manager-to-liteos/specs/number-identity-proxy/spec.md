# Spec Delta

## MODIFIED Requirements

### Requirement: 号码识别数据更新通知
系统 SHALL 在 `CallBroadcastSubscriber::HsdrEventBroadcast` 收到数据包含 `com.numberidentity.devicenumber` 的公共事件时，调用 `NumberIdentityServiceHelper::NotifyNumberMarkDataUpdate`；liteOS 上号码识别服务连接/更新通知的外部接口暂不调用，`number_identity_service.cpp` 的服务连接（bundle `com.numberidentity`、ability `NumberIdentityServiceExtAbility`、`USER_ID` 100）与 `NumberIdentityServiceProxy::NotifyNumberMarkDataUpdate`（`IMPORT_NUMBER_MARK_DATA_FILE`）调用点 MUST 写 `// todo!!! [numberIdentity] ref to number_identity_service.cpp NotifyNumberMarkDataUpdate` 占位，不发起真实连接与数据更新通知；`working_` 防重入逻辑保留，置位期间 MUST NOT 重复发起通知。

#### Scenario: 触发数据更新通知
- **WHEN** HSDR 公共事件数据中出现 `com.numberidentity.devicenumber`
- **THEN** 进入 `NumberIdentityServiceHelper::NotifyNumberMarkDataUpdate` 分支，连接与通知调用点写 `// todo!!! [numberIdentity] ref to number_identity_service.cpp NotifyNumberMarkDataUpdate` 占位，不发起真实服务连接

#### Scenario: 通知进行中防重入
- **WHEN** 上一次通知尚未回调断开（`working_` 为 true）时再次收到触发事件
- **THEN** 跳过本次通知请求

### Requirement: 号码归属地查询
系统 SHALL 由 `NumberIdentityDataBaseHelper::Query` 保留按号码精确匹配查询归属地的逻辑框架；liteOS 上归属地 DataShare 查询（以 `TELEPHONY_CALL_MANAGER_SYS_ABILITY_ID` 创建、URI `datashare:///numberlocationability`）调用点 MUST 写 `// todo!!! [database] ref to number_identity_data_base_helper.cpp Query` 占位，占位期间无进程内注入时查询 SHALL 返回失败或空并兜底，`numberLocation` 不被填充，通话详情不含归属地；查询结果行数为 0 时返回成功且 `numberLocation` 保持为空的未命中语义保留。

#### Scenario: 查询占位返回空兜底
- **WHEN** 调用 `NumberIdentityDataBaseHelper::Query` 且 DataShare 调用点为 `// todo!!! [database] ref to number_identity_data_base_helper.cpp Query` 占位
- **THEN** 查询不真实执行，`numberLocation` 不被填充，通话详情不含归属地

#### Scenario: 命中归属地
- **WHEN** 进程内注入归属地记录（占位查询结果行数非 0，携带 `number_location` 列值）
- **THEN** `numberLocation` 被填充为 `number_location` 列值，列值读取逻辑与基线一致（真实 DataShare 查询调用点为 `// todo!!! [database] ref to number_identity_data_base_helper.cpp Query` 占位，待数据库接口适配后恢复）

#### Scenario: 未命中
- **WHEN** 占位/打桩返回结果行数为 0
- **THEN** `Query` 返回 `TELEPHONY_SUCCESS`，`numberLocation` 不被填充

### Requirement: 黄页与号码标记查询
系统 SHALL 由 `NumberIdentityDataBaseHelper::QueryYellowPageAndMark` 保留黄页与号码标记查询的逻辑框架；liteOS 上黄页标记查询（URI `datashare:///numbermarkability/number_mark_info`）调用点 MUST 写 `// todo!!! [numberIdentity] ref to number_identity_data_base_helper.cpp QueryYellowPageAndMark` 占位，不发起真实查询；结果行数为 0 时 `NumberMarkInfo.markType` 置为 `MARK_TYPE_NONE` 并返回成功的无标记记录语义保留；否则由 `SetMarkInfoValues` 读取 `markType`/`markContent`/`markCount`/`markSource`/`isCloud`/`markDetails` 填充 `NumberMarkInfo` 的解析逻辑保留。

#### Scenario: 无标记记录
- **WHEN** 黄页标记查询调用点为 `// todo!!! [numberIdentity] ref to number_identity_data_base_helper.cpp QueryYellowPageAndMark` 占位（无真实查询结果）
- **THEN** `markType` 为 `MARK_TYPE_NONE`，返回 `TELEPHONY_SUCCESS`

#### Scenario: 命中黄页标记
- **WHEN** 进程内注入标记记录（结果行数非 0）
- **THEN** `NumberMarkInfo` 按 `SetMarkInfoValues` 列值填充（`isCloud` 列为 1 时置 true），解析逻辑与基线一致

### Requirement: 查询入口与更新回流
系统 SHALL 由 `CallNumberUtils::QueryNumberLocationInfo` 与 `CallNumberUtils::QueryYellowPageAndMarkInfo`（入参为通话号码）封装上述占位查询（返回 `TELEPHONY_ERR_DATABASE_READ_FAIL` 等错误码语义保留）的查询入口保留；区域判定保留：`YellowPageAndMarkUpdate` MUST 仅在系统参数 `const.global.region`（经打桩 parameter）为 `CN` 时执行黄页更新，非中国区域直接跳过黄页查询；`NumberLocationUpdate`/`YellowPageAndMarkUpdate` 将查询结果写入通话对象（`SetNumberLocation`/`SetNumberMarkInfo`）后经 `CallAbilityReportProxy::ReportCallStateInfo` 进程内直调上报的回填上报链路保留。

#### Scenario: 归属地回填上报
- **WHEN** `NumberLocationUpdate` 查询到非空且非 `default` 的归属地（进程内注入）
- **THEN** 通话对象 `SetNumberLocation` 后经进程内直调上报通话信息

#### Scenario: 非中国区域跳过黄页
- **WHEN** `const.global.region` 不为 `CN`
- **THEN** `YellowPageAndMarkUpdate` 直接返回，不查询号码标记
