# Spec Delta

## Purpose
固化 LiteOS 手表目标平台的运行时约定：进程内直调架构、`stub/` 桩目录与跨模块客户端桩、`// todo!!!` 占位格式、打桩 `EventHandler` 串行、单线程不加锁、DSDS 恒 0 与单卡预留。`telephony_call_manager_mini/` 全部保留能力的行为均受本能力约束。

## ADDED Requirements

### Requirement: 进程内直调架构
系统 SHALL 使 `CallManagerClient` 不经 samgr 与 IPC，直接调用进程内 `CallManagerService`（保留 `DelayedSingleton`，首次 `GetInstance()` 时执行 `Init()` 懒初始化）；`CallManagerService` 不继承 `SystemAbility`、不注册 SA、不实现 stub/proxy；外部接口不做权限校验（`TelephonyPermission::CheckCallerIsSystemApp`/`CheckPermission` 不调用）。
#### Scenario: 客户端首次调用触发服务初始化
- **WHEN** `CallManagerClient` 首次发起任一业务调用（如 `DialCall`）
- **THEN** `CallManagerService::Init()` 按序完成子管理器初始化后，该调用同步直调执行并返回结果

#### Scenario: 外部接口不做权限校验
- **WHEN** 任一外部接口被调用
- **THEN** 不执行权限校验，接口行为不受调用方身份与权限影响

### Requirement: 桩目录与跨模块客户端桩
系统 SHALL 将全部外部依赖桩统一放在 `telephony_call_manager_mini/stub/`：与 cellular_call / core_service / cellular_data / sms_mms / TelephonyCust 的交互分别经 `CellularCallClient::GetInstance()` / `CoreServiceClient::GetInstance()` / `CellularDataClient::GetInstance()` / `SmsClient::GetInstance()` / `TelephonyCustClient::GetInstance()` 单例桩，接口名与原语义同名，桩可配置返回值供测试注入。
#### Scenario: 拨号经 cellular_call 客户端桩
- **WHEN** 下行拨号到达协议栈边界
- **THEN** 以 `CellularCallClient::GetInstance().Dial(...)` 形式调用桩并按桩配置返回结果

#### Scenario: FDN 查询经 core_service 客户端桩
- **WHEN** 拨号前置校验查询 FDN 名单
- **THEN** 以 `CoreServiceClient::GetInstance().QueryIccDiallingNumbers(...)` 形式调用桩，桩按配置返回名单与开关状态

### Requirement: todo 占位
系统 SHALL 对暂不可用的外部接口调用点以 `// todo!!! [<标签>] ref to <文件> <函数>` 注释占位并保留周边逻辑；标签取 audio/database/broadcast/powerLock/notification/spam/numberIdentity/rttFile/callUi 等依赖域；占位调用点按"不产生外部副作用、返回默认成功或默认值"语义执行。
#### Scenario: 音频调用点占位
- **WHEN** 保留代码执行到音频系统 API 调用点（如播放铃声）
- **THEN** 调用点为 todo 占位，无音频副作用，铃声状态机按成功路径继续推进

#### Scenario: 数据库调用点占位
- **WHEN** 保留代码执行到 DataShare 查询调用点（如联系人查询）
- **THEN** 调用点为 todo 占位，返回默认值（联系人未命中），来电创建流程不受阻

### Requirement: 打桩 EventHandler 替代 ffrt
系统 SHALL 以打桩 `EventHandler`（单线程串行分发）替代全部 `ffrt::queue`/`ffrt::submit`/`ffrt::submit_h` 异步与延时语义：任务先进先出串行执行，延时任务按给定延时触发，可取消未决任务；上行状态处理保持单队列串行。
#### Scenario: 上行全量列表串行处理
- **WHEN** 协议栈桩连续上报两次全量列表
- **THEN** 两次上报按提交顺序串行处理，不并发交错

#### Scenario: 延时任务按期触发
- **WHEN** 保留代码提交带延时的断开任务（如通话界面延时断开）
- **THEN** 任务按配置延时由打桩 `EventHandler` 触发执行

### Requirement: 单线程不加锁
系统 SHALL 在单线程模型下运行：不迁移 `std::mutex`/`ffrt::mutex`/`ffrt::shared_mutex` 等锁原语，原临界区代码直接执行；如需新增线程先与用户对齐。
#### Scenario: 并发入口直接执行
- **WHEN** 测试中多个外部接口先后调用同一管理器
- **THEN** 各调用顺序直接执行，无锁保护且状态一致

### Requirement: DSDS 恒 0 与单卡预留
系统 SHALL 使 DSDS 模式查询（`CoreServiceClient::GetInstance().GetDsdsMode()`，经桩实现）恒返回 0，非 0（DSDA/TDM）分支不迁移；单卡运行但 `slotId`/`accountId` 参数与传参链路完整保留以备双卡扩展。
#### Scenario: 查询 DSDS 模式
- **WHEN** 任一路径（`HandleDsdaInfo`、`HandleHoldCallOrAutoAnswerCall`、`IsDsdsMode3`）经 `CoreServiceClient::GetInstance().GetDsdsMode()` 查询 DSDS 模式
- **THEN** 恒返回 0，DSDA 相关分支不可达

#### Scenario: slotId 全链路保留
- **WHEN** 拨号/接听/设置接口携带 slotId
- **THEN** slotId 透传至协议栈边界桩，不因单卡而被删除

### Requirement: 系统参数与基础库桩
系统 SHALL 使系统参数（parameter）、securec、c_utils（`sptr`→`std::shared_ptr`）、日志、`EventHandler`、cJSON、libphonenumber 基础库均经 `stub/` 桩提供：`GetParameter`/`SetParameter` 读写桩内参数表（未配置项返回调用方默认值）；HiSysEvent/HITRACE 维测点改日志打印。
#### Scenario: 系统参数读桩
- **WHEN** 保留代码读取 `const.telephony.voice.capable` 等系统参数
- **THEN** 从桩参数表读取，未配置项返回调用方给定默认值

#### Scenario: sptr 替换
- **WHEN** 保留代码原以 `sptr<T>` 持有对象
- **THEN** 改为 `std::shared_ptr<T>`，引用计数与生命周期语义等价
