# Proposal

## Why

目标仓 communication_mcu 的手表平台（LiteOS + MCU，单进程单线程）需要通话管理能力，但现有 `telephony_call_manager/`（OpenHarmony v6.0-Release，SA 4005，进程 foundation，C++17）按手机形态实现：依赖 SystemAbility/IPC、ffrt、DataShare、公共事件、通知、音频框架、libphonenumber 等大量 liteOS 上不存在或未适配的外部件。本 change 按 AGENTS.md 的约束把基线整棵拷贝到 `telephony_call_manager_mini/` 后做裁剪与外部依赖替换：功能做裁剪而不是重写，暂不可用的外部接口只换掉调用（todo 占位），业务逻辑保留，并继续以 `test/` PC 门禁验收。

## What Changes

- **BREAKING** 产物目录：新增 `telephony_call_manager_mini/`（由 `telephony_call_manager/` 整棵拷贝而来），裁剪与修改只在此进行；外部接口的桩统一放在其根目录 `stub/`。原基线 `telephony_call_manager/` 一字不改。
- **BREAKING** 进程模型：callmanager 不继承 SystemAbility、不做 IPC、不做权限校验；`CallManagerClient` 直接调用 `CallManagerService` 接口；`CallManagerServiceStub`、`sa_profile/`、IPC 代理类（`CallManagerServiceProxy`、`CellularCallProxy`、`CallStatusCallbackProxy` 等）与 samgr/safwk 依赖退役。
- **BREAKING** 功能裁剪：视频通话、会议通话、卫星通话、分布式与互通通话、BLUETOOTH/OTT 通话、地震预警、视频彩振、有线耳机、语音播报（`call_voice_assistant`）、防诈、超级隐私、折叠屏、EDM 企业禁拨、来电闪光、状态栏静音图标、贴耳灭屏、运动识别、MAKE_CALL_WITH_TOKEN、STR 模式、ESIM、新通话相关代码不迁移；VoIP 类型通话暂不支持（依赖后续 meetime 畅连适配）；DSDA 流程不迁移（`GetDsdsMode` 恒 0）；只支持单卡（保留 slotId 供双卡扩展）与单主帐号。
- 外部依赖替换：`sptr` → `std::shared_ptr`/`std::unique_ptr`；ffrt 异步 → 打桩的 EventHandler；HiSysEvent/HITRACE → 日志打印；与 cellular_call / core_service / cellular_data / sms_mms / TelephonyCust 的交互改为 `XxxClient::GetInstance().Xxx()`（打桩）；libphonenumber / 系统参数 / cJSON / securec / c_utils / log / eventhandler 基础库打桩；`AppExecFwk::PacMap` 等改结构体。
- 外部依赖 todo 占位（逻辑保留，调用点写 `// todo!!! [标签] ref to <文件> <函数>`）：audio、DataShare、公共事件（EventFwk::CommonEventManager）、功耗锁 RunningLock、通知 NotificationHelper、骚扰来电、号码识别/黄页、RTT 文件节点；拉起通话界面（CallConnectAbility）与对话框（CallDialog）通过打桩实现。
- 退役宏清理与支持宏去守卫：按 AGENTS.md 宏清单处理（详见 design.md 决策表）。
- **BREAKING** 测试工程：`test/base/telephony/call_manager` 符号链接改指 `telephony_call_manager_mini/`，must-pass 套件集合按裁剪结果调整（被移除模块的套件退出 must-pass），门禁验证裁剪后的代码。

## 裁剪范围

按 `openspec/specs` baseline 能力 id 逐条列出处置（移除 = delta 全部 Requirement REMOVED；修改 = delta 含 REMOVED/MODIFIED；保留 = 不出 delta）：

| baseline 能力 | 处置 | 一行理由 |
|---|---|---|
| `call-manager-service` | 修改 | 去掉 SystemAbility/sa_profile/IPC stub/权限校验，保留初始化管理器链与查询面；`TelephonyCustWrapper` 改客户端单例打桩；`SUPPORT_MUTE_BY_DATABASE` 差异退役 |
| `call-object-model` | 修改 | 保留 CS/IMS 通话对象与 `CallObjectManager`；移除 OTT/VoIP/卫星/蓝牙对象、会议对象与视频状态；`sptr` → `std::shared_ptr` |
| `call-control` | 修改 | 保留 CS/IMS 呼叫控制、ECC 放行与拨号校验；移除超级隐私、陌生来电过滤的 EDM 环节、有线耳机按键、OTT/蓝牙/卫星分发、会议操作；ffrt → EventHandler；拉起通话界面打桩 |
| `call-status-management` | 修改 | 保留上行状态处理与仲裁；移除 VoIP 分流、会议归组与 DSDA 分支；过滤链保留（骚扰识别 todo 占位） |
| `call-state-observer` | 修改 | 通话记录（DataShare）、通知、广播、亮屏/功耗锁调用点 todo 占位；拒接短信经 `SmsClient` 打桩保留；移除状态栏图标、贴耳灭屏、有线耳机联动、多用户精简为单主帐号 |
| `audio-management` | 修改 | 通话状态/设备路由状态机与控制逻辑保留，系统音频调用（AudioProxy、Ring/Sound/Tone）todo 占位；移除蓝牙/有线耳机设备路由 |
| `bluetooth-call` | 移除 | BLUETOOTH 类型通话不支持 |
| `call-setting` | 修改 | 呼叫等待/限制/转移、IMS 配置、USSD/MMI 补充业务全部保留，转发通道改 `CellularCallClient::GetInstance().Xxx()`（打桩） |
| `call-report` | 修改 | 对应用上报逻辑保留并改进程内直调；移除 OTT 上报、IPC 代理序列化、回调死亡清理与应用进程死亡观察 |
| `telephony-interaction` | 修改 | `CellularCallConnection`/`CoreServiceConnection` 改客户端单例打桩；上行单队列保留（ffrt → EventHandler）；`CallStatusCallback` stub 分发改直调；移除 VoIP/蓝牙连接、samgr 状态监听与重连 |
| `video-call` | 移除 | 视频通话不支持 |
| `satellite-call` | 移除 | 卫星通话不支持 |
| `distributed-call` | 移除 | 分布式通话不支持（dsoftbus 依赖不迁移） |
| `interoperable-call` | 移除 | 互通通话不支持 |
| `spam-call` | 修改 | 骚扰识别的等待/解析/判定逻辑保留，`com.spamshield` 扩展连接与 dlopen 调用点 todo 占位 |
| `antifraud-call` | 移除 | 防诈不支持 |
| `number-identity-proxy` | 修改 | 归属地/黄页查询逻辑保留，DataShare 调用点 todo 占位 |
| `call-earthquake-alarm` | 移除 | 地震预警不支持 |
| `call-voice-assistant` | 移除 | 来电语音播报/语音控制（语音助手联动）不支持 |
| `display-control` | 移除 | 折叠屏不支持（display 模块仅折叠状态管理） |
| `hisysevent-dfx` | 修改 | HiSysEvent/HITRACE/hidump 改日志打印，隐私字段约束保留；VOIP 统计事件移除 |
| `call-utils` | 修改 | 号码工具（libphonenumber 打桩）、序列化、卡状态查询保留；设置库 DataShare todo 占位；移除 EDM 禁拨、紧急号码对话框改打桩、运动识别与闪灯提醒移除；帐号选择精简为单主帐号 |
| `client-framework` | 修改 | `CallManagerClient` 改直连 `CallManagerService`；移除连接服务、IPC 码发送、死亡重连与外部 SA 代理类 |
| `js-ets-cj-binding` | 移除 | JS/ETS/仓颉绑定不实现 |
| `pc-test-harness` | 修改 | 被测路径改指 `telephony_call_manager_mini/`，宏注入改手表宏集，must-pass 套件按裁剪结果调整 |

## 非目标

- 不重写业务逻辑：代码逻辑与 HMOS 基线保持一致，除非基线本身实现有问题（此类点在 design.md「Open Questions」记录）。
- 不实现 VoIP 类型通话与畅连（meetime）冲突处理：本 change 仅移除 VoIP 通路，后续 change 适配。
- 不实现音频/数据库/广播/通知/功耗锁/骚扰查询/号码识别/RTT 通路的真实 liteOS 后端：仅 todo 占位 + 打桩，待对应框架接口就绪后另行适配。
- 不做权限校验体系（含 `AccessTokenKit`）：外部接口免校验直通。
- 不引入新线程、不加锁：单进程单线程模型不变；如需新增线程先与用户对齐。
- 不做 DSDA/双卡业务：`GetDsdsMode` 恒 0，仅保留 slotId 字段供双卡扩展。
- 不修改 `telephony_call_manager/`（只读基线）与 `AGENTS.md`。
- 不实现 JS/ETS/仓颉对外接口，不迁移 fuzztest。
- 不做 liteOS 目标板的交叉编译/真机部署（产物仍以 `test/` PC 门禁验证）。

## Capabilities

### New Capabilities

无——本 change 全部为对 baseline 能力的 delta（REMOVED/MODIFIED），不新增手表专属能力。

### Modified Capabilities

- `call-manager-service`：SA/IPC/权限校验/静音数据库差异退役，初始化链与查询面保留并直连化。
- `call-object-model`：通话类型收敛为 CS/IMS，会议/视频/VoIP/OTT/卫星/蓝牙对象移除，智能指针替换。
- `call-control`：控制面收敛为 CS/IMS + ECC，辅助特性（超级隐私、有线耳机、广播订阅）移除或 todo 占位，异步原语替换。
- `call-status-management`：上行状态处理保留，VoIP/会议/DSDA 分支移除。
- `call-state-observer`：外部副作用（库/通知/广播/功耗）todo 占位，短信回拒保留，状态栏/贴耳/耳机移除。
- `audio-management`：音频系统调用 todo 占位，设备路由收敛为听筒/扬声器。
- `call-setting`：补充业务保留，转发通道改客户端单例打桩。
- `call-report`：上报直调化，IPC 代理与死亡观察移除。
- `telephony-interaction`：连接层改客户端单例打桩，上行队列保留。
- `spam-call`：外部识别服务调用 todo 占位，判定逻辑保留。
- `number-identity-proxy`：DataShare 查询 todo 占位，逻辑保留。
- `hisysevent-dfx`：维测改日志打印，VOIP 统计移除。
- `call-utils`：工具收敛（EDM/运动识别/闪灯移除，libphonenumber 与设置库打桩/todo）。
- `client-framework`：直连架构，IPC 代理面退役。
- `bluetooth-call` / `video-call` / `satellite-call` / `distributed-call` / `interoperable-call` / `antifraud-call` / `call-earthquake-alarm` / `call-voice-assistant` / `display-control` / `js-ets-cj-binding`：各自 delta 全部 Requirement REMOVED。
- `pc-test-harness`：被测路径与门禁套件集合、宏注入调整。

## Impact

- 代码：新增 `telephony_call_manager_mini/`（拷贝 + 裁剪，含根目录 `stub/`）；`test/base/telephony/call_manager` 符号链接重指；`test/build/ohos.gni` 宏注入调整；`test/tests/BUILD.gn`、`test/run_tests.sh` must-pass 集合调整。`telephony_call_manager/` 与 `AGENTS.md` 不动。
- 构建：`telephony_call_manager_mini/callmanager.gni` 的 sources/include_dirs/external_deps 全量重排（被移除目录整块删除、外部依赖换成 `stub/`），根 `BUILD.gn` 的 `declare_args` 仅保留 `call_manager_feature_not_support_multicall`（置 true），`bundle.json` features 同步。
- 依赖：不再依赖 SystemAbility/samgr/ipc/ffrt/DataShare/公共事件/通知/音频框架/player_framework/libphonenumber 等部件；上述能力经 `stub/` 或 todo 占位承接。
- **需人工复核**（按 openspec/config.yaml 规则）：
  - ECC：`EccDialPolicy` 移除卫星通话清理分支、`HasNormalCall` 的 ECC 旁路原样保留，涉及紧急呼叫放行语义。
  - 权限校验：全部外部接口免校验直通（`VerifyAccessToken` 等不调用）。
  - IPC 枚举：`CallManagerInterfaceCode` 等枚举在 liteOS 上不再作为 ABI 使用，但保留在接口头中不动值，供后续恢复 IPC 时对照。
  - 跨部件结构体：`AppExecFwk::PacMap` 替换为结构体、`CallAttributeInfo` 等结构体字段随 VoIP/会议裁剪收缩，影响与 cellular_call 桩的数据面对齐。
- 门禁：must-pass 由 8 套件按裁剪结果调整为仅含保留模块的套件（详见 tasks.md），每步以 `MUST-PASS GATE: PASS` 为完成条件之一。
