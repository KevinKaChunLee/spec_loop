# Spec Delta

## Purpose

liteOS 移植的桩层约定：承载 `telephony_call_manager_mini/stub/` 桩目录的组织、跨模块客户端单例桩、同名替代桩、todo 占位标签语法与单线程无桩线程约束（本变更新增能力，依据 design.md D5/D6/D8）。

## ADDED Requirements

### Requirement: 桩目录与桩面组织
系统 SHALL 把全部新增桩集中在 `telephony_call_manager_mini/stub/`（AGENTS「liteOS 的外部接口打桩函数统一放到 liteOS 代码的根目录的 stub 文件夹中」），桩源码随 `callmanager.gni` 纳入 mini 构建（见能力 `build-config` delta 的 ADDED），桩层 MUST NOT 含任何真实业务逻辑（不做真实音频/数据库/通知/功耗锁操作），桩 MUST NOT 被业务代码绕过。

#### Scenario: 桩表收入构建
- **WHEN** 编译 mini 的 `tel_call_manager` target
- **THEN** `stub/` 下的桩源（`cellular_call_client.cpp`、`core_service_client.cpp`、`cellular_data_client.cpp`、`sms_client.cpp`、`telephony_cust_client.cpp`、`voip_call_client.cpp`、`state_registry_client.cpp` 及同名基础桩）出现在 `callmanager.gni` 的 sources 列表中，随桩头目录参与 include_dirs

#### Scenario: 桩无业务逻辑
- **WHEN** 检查 `stub/` 目录内容
- **THEN** 不出现对 audio_framework、data_share、common_event、notification、power 等真实系统库的调用，桩仅返回预置/注入值

### Requirement: todo 占位标签语法
系统 SHALL 在所有“暂不调用（依赖后续适配）”的外部接口调用点保留原逻辑并以注释占位，语法统一为 `// todo!!! [标签] ref to <基线文件名> <函数名>`；标签集固定为 `[audio] [database] [broadcast] [powerLock] [callUi] [notification] [spamCall] [numberIdentity] [rtt]`（AGENTS「外部依赖处理」与 design D6 表一一对应）。标注处 MUST 保留基线的判定与回退分支逻辑，仅替换外部调用本身。

#### Scenario: 暂不调用接口留痕
- **WHEN** 检索 mini 中 audio/数据/广播/通知/功耗锁/骚扰/号码识别/RTT/UI 拉起类外部调用点
- **THEN** 每处均带有上述语法的 todo 注释，且标签落在固定集合内；`rg -n "todo!!!\\[(audio|database|broadcast|powerLock|callUi|notification|spamCall|numberIdentity|rtt)\\]"` 可作为评审检查命令

#### Scenario: 逻辑保留
- **WHEN** todo 标注点的外部调用恒定失败（桩/未适配）
- **THEN** 基线中该调用失败后的回退/置位/记录行为按基线执行（如未接来电通知发送失败仍置 unread 标记、通话记录入库失败返回错误码）

### Requirement: 跨模块客户端单例桩
系统 SHALL 在 `stub/` 提供 `CellularCallClient`、`CoreServiceClient`、`CellularDataClient`、`SmsClient`、`TelephonyCustClient`、`VoipCallClient`、`StateRegistryClient` 的 `GetInstance()` 单例，形态为 `XxxClient::GetInstance().Xxx()`（AGENTS「与 cellular_call/core_service/cellular_data/sms_mms/TelephonyCust 模块通信的替代形态」）；适配器（`CellularCallConnection`/`CoreServiceConnection`/`VoipCallConnection`/`TelephonyCustWrapper`）保留类名并内部改调桩（design D4）。桩默认返回值表达“服务不存在/不可用”，与基线未连接分支语义一致（design Risks）；测试 MUST 可按用例注入桩返回值。

#### Scenario: 桩默认拒绝
- **WHEN** 业务经适配器调用任一客户端桩且测试未注入返回值
- **THEN** 桩返回基线“服务未连接”语义的失败码（如 `TELEPHONY_ERR_IPC_CONNECT_STUB_ERR` 一类基线错误码，具体取值以对应适配器的基线实现为准，如 `cellular_call_connection.cpp` 的 `ReConnectService` 失败返回），业务走基线失败分支（**需人工复核**：桩错误码与基线逐点对齐）

#### Scenario: 桩注入成功路径
- **WHEN** gtest 用例向客户端桩注入成功返回值（如拨号请求返回 `TELEPHONY_SUCCESS`）
- **THEN** 业务按基线成功语义继续（如 `CallRequestProcess::DialRequest` 走 `CarrierDialProcess` 下发链）

### Requirement: 同名替代桩
系统 SHALL 提供与基线签名一致的同名桩替代以下依赖（design D5）：`HiSysEvent::HiSysEventWrite`/hitrace → 日志打印（`stub/hisysevent_stub`，映射维测动作的可观测日志输出）；ffrt → 打桩 EventHandler（队列/提交/延迟原语签名不变，保持上行单队列串行语义）；`securec`（`memcpy_s` 等）、`cJSON`、libphonenumber、系统参数（parameter）、`c_utils`（sptr 兼容）、hilog（log）桩。

#### Scenario: 维测动作转日志
- **WHEN** 业务调用 `CallManagerHisysevent` 的写入族（如 `WriteIncomingCallBehaviorEvent`）
- **THEN** 不链接真实 hisysevent 库，同名桩输出含事件名的日志一行，且不携带号码/联系人名明文（隐私约束照抄，见能力 `hisysevent-diagnostics` delta）

#### Scenario: ffrt 换单线程事件原语
- **WHEN** 业务提交 `report_call_info_queue_` 上行任务或 1s/3s 定时任务
- **THEN** 打桩 EventHandler 在当前线程同步/串行执行任务，保持“上行单队列串行”语义（design D8）；全流程不新增线程（**需人工复核**：若产品要求独立事件线程，须先与用户对齐）