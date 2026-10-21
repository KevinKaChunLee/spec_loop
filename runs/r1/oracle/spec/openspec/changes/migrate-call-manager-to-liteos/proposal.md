# Proposal

## Why

手表平台（LiteOS + MCU、单进程单线程）需要通话管理能力，但 HMOS 基线 `telephony_call_manager`（SA 4005）依赖 SystemAbility/IPC、ffrt 并发原语与十余个外部部件，无法直接在该平台构建运行。按 AGENTS.md 规定的功能范围与外部依赖处理规则，将基线裁剪为可在 LiteOS 上运行的 `telephony_call_manager_mini/`，并以本 change 固化"移除/保留/修改"的行为规格，供人工评审与后续实施。

## What Changes

- **整体架构（BREAKING）**：`telephony_call_manager_mini/` 由基线整棵拷贝后裁剪；`CallManagerService` 不再继承 `SystemAbility`、不做 IPC 与权限校验，`CallManagerClient` 进程内直调 `CallManagerService`（**需人工复核**：IPC 枚举表与跨部件结构体的处置见 design.md）。
- **移除 9 个模块组**：蓝牙通话、视频通话、卫星通话、分布式通话、互通通话（手表特有 settings 联动）、防诈、号码助手（语音拨号）、地震预警、折叠屏显示，连同对应源码目录、gni 源与测试套件。
- **保留能力内部裁剪**：会议通话、卫星/蓝牙/OTT 通话对象、超级隐私、EDM 企业禁拨、来电闪光、状态栏静音图标、贴耳灭屏（`ProximitySensor`）、星闪、有线耳机、来电全屏通知、视频彩振（`crsType == CRS_TYPE`）等分支不再迁移；CS/IMS/VoIP 通话、RTT、UT/USSI/MMI 补充业务保留。
- **外部依赖统一处置**（AGENTS.md「外部依赖处理」）：暂不可用接口调用点写 `// todo!!! [<标签>] ref to <文件> <函数>` 占位（音频、DataShare、公共事件广播、功耗锁、通知、骚扰来电、号码识别、RTT 文件节点、拉起通话界面）；跨模块 IPC 改客户端单例打桩（`CellularCallClient` / `CoreServiceClient` / `CellularDataClient` / `SmsClient` / `TelephonyCustClient::GetInstance().Xxx()`）；原语替换（`sptr`→`std::shared_ptr`、ffrt→打桩 `EventHandler`、`PacMap`→结构体、HiSysEvent/HITRACE→日志）。桩统一放 `telephony_call_manager_mini/stub/`。
- **DSDA（BREAKING）**：DSDS 模式查询（`CoreServiceClient::GetInstance().GetDsdsMode()`，经桩实现）恒返回 0，非 0 分支不迁移；仅支持单卡但保留 `slotId` 传参以备双卡扩展。
- **紧急呼叫（需人工复核）**：ECC 拨号流程随单卡/单帐号裁剪精简，三张 ECC 策略表保留主干。
- **并发模型（BREAKING）**：单线程运行，ffrt 队列改打桩 `EventHandler` 串行分发，不迁移锁。
- **构建与门禁**：`callmanager.gni` 裁 sources/依赖/宏集合；`test/` 的 `//base/telephony/call_manager` 软链改指 `telephony_call_manager_mini/`，must-pass 套件集随移除能力调整（**需人工复核**：套件集合变化清单见 design.md）。

## 裁剪范围

| 基线能力 | 处置 | 理由（一行） |
| --- | --- | --- |
| call-object-model | 修改 | 裁会议/卫星/蓝牙/OTT 对象与视频彩振，保留 CS/IMS/VoIP；`sptr`→`std::shared_ptr` |
| call-control-manager | 修改 | PacMap→结构体、ffrt→打桩 EventHandler、CallConnectAbility/广播/功耗锁 todo 占位，裁超级隐私/有线耳机/DSDA/权限校验 |
| call-status-manager | 修改 | 裁防诈/ESIM/DSDA/免打扰 DataShare/动作识别分支，`GetDsdsMode()` 恒 0，OOBE 判定改打桩系统参数 |
| call-state-observer | 修改 | 裁通知/亮屏/贴耳灭屏/状态栏/有线耳机观察者，通话记录与设置 DataShare todo 占位，拒接短信改 SmsClient 打桩 |
| call-manager-service | 修改 | 不继承 SystemAbility、无 IPC stub 与权限校验，CallManagerClient 直调；TelephonyCust 改客户端单例打桩 |
| call-report | 修改 | 回调经 proxy 的 IPC 上报改进程内直调，死亡通知简化 |
| telephony-interaction | 修改 | 四个 Connection 改 CellularCallClient/CoreServiceClient 单例打桩，上行 ffrt 队列改打桩 EventHandler |
| call-setting | 修改 | 转发 cellular_call 的接口改打桩客户端，设置项 DataShare 查询 todo 占位 |
| audio-control-manager | 修改 | 音频系统 API 调用点 todo 占位，逻辑保留；裁有线耳机/蓝牙/星闪/助听器设备态与视频彩振 |
| spam-call | 修改 | 查询逻辑保留，dlopen/骚扰库调用点 todo 占位（AGENTS.md：暂不调用、不用 dlopen） |
| number-identity | 修改 | 黄页/标记逻辑保留，DataShare 与 libphonenumber 调用点 todo/打桩占位 |
| hisysevent-observability | 修改 | HiSysEvent/HITRACE 改日志打印，HiDumper 接口保留骨架 |
| call-manager-utils | 修改 | 裁 edm/incoming_flash/motion/screen_sensor 工具，设置查询 todo 占位，libphonenumber/cJSON 打桩 |
| client-frameworks | 修改 | JS/ETS/仓颉绑定不迁移；native 客户端直调，proxy/死亡通知/蓝牙星闪客户端移除 |
| build-and-feature-flags | 修改 | gni 裁源与依赖，defines 收敛为支持宏集合，测试 target 重组 |
| pc-test-harness | 修改 | 软链指向 telephony_call_manager_mini/，must-pass 套件集随移除能力调整，门禁改验裁剪后代码 |
| bluetooth-call | 移除 | AGENTS.md：BLUETOOTH 类型通话不支持 |
| video-call | 移除 | AGENTS.md：视频通话不支持 |
| satellite-call | 移除 | AGENTS.md：卫星通话不支持 |
| distributed-call | 移除 | AGENTS.md：分布式（distributed 及 interoperable）通话不支持 |
| interoperable-call | 移除 | 同上，手表 settings 联动一并移除 |
| antifraud-call | 移除 | AGENTS.md：防诈 antifraud 不支持 |
| call-voice-assistant | 移除 | AGENTS.md：语音播报/号码助手不支持 |
| call-earthquake-alarm | 移除 | AGENTS.md：地震预警不支持 |
| fold-display | 移除 | AGENTS.md：折叠屏不支持 |

## Capabilities

### New Capabilities
- `liteos-runtime`: LiteOS 目标平台的运行时约定——进程内直调架构、`stub/` 桩目录与 `XxxClient::GetInstance()` 客户端桩、`// todo!!!` 占位格式、打桩 `EventHandler` 串行分发、单线程不加锁、`GetDsdsMode()` 恒 0 与单卡 `slotId` 预留。

### Modified Capabilities
- `call-object-model`: 通话对象集合收敛为 CS/IMS/VoIP，会议对象与视频彩振字段移除，智能指针与对象表实现变更。
- `call-control-manager`: 控制入口保留，界面拉起/广播/功耗锁调用点 todo 占位，PacMap 参数结构体化，超级隐私与 DSDA 分支移除。
- `call-status-manager`: 上行状态分派保留，防诈/免打扰 DataShare/动作识别/OOBE 上云分支移除，OOBE 判定改打桩系统参数。
- `call-state-observer`: 观察者集合收敛为通话记录（todo 占位落库）与拒接短信打桩，通知/亮屏/灭屏/状态栏观察者移除。
- `call-manager-service`: 服务入口去 SystemAbility 化、直调化，权限校验不执行，TelephonyCust 客户端打桩。
- `call-report`: 上报回调直调化，注册管理保留单进程语义。
- `telephony-interaction`: 跨模块交互客户端单例打桩化，上行队列改打桩 EventHandler。
- `call-setting`: 呼叫等待/转移/限制的查询与设置转发打桩客户端，设置项 DataShare todo 占位。
- `audio-control-manager`: 音频设备枚举与调用点 todo 占位化，逻辑（听筒/扬声器/提示音/静音）保留。
- `spam-call`: 骚扰拦截决策逻辑保留，外部查询接口 todo 占位返回默认值。
- `number-identity`: 号码标记/黄页匹配逻辑保留，外部查询与解析接口 todo/打桩占位。
- `hisysevent-observability`: 事件上报改日志宏，事件清单与埋点位置保留。
- `call-manager-utils`: 工具函数集合裁剪（edm/闪光/动作/屏传感器），设置与解析类接口 todo/打桩化。
- `client-frameworks`: 仅保留 native 客户端直调面，JS/ETS/仓颉绑定与 proxy 层移除。
- `build-and-feature-flags`: gni/BUILD.gn/bundle.json 按支持宏集合与裁剪后源集重组。
- `pc-test-harness`: 被测对象切换为裁剪产物，must-pass 套件集调整，门禁语义不变（全绿才通过）。

## Impact

- **新增目录**：`telephony_call_manager_mini/`（含 `stub/`）；本阶段仅规划，实施阶段创建。
- **受影响代码**：基线 `telephony_call_manager/` 全部 24 个能力模块组中保留的 15 个（含构建）；构建文件 `callmanager.gni`、根 `BUILD.gn`、`bundle.json`、`sa_profile/`（SA profile 随直调架构移除）、各子目录 `BUILD.gn`。
- **测试**：`test/` 软链与 must-pass 套件集调整（`tel_call_voice_assistant_test`、`distributed_communication_test`、`tel_call_earthquake_alarm_test` 对应能力被移除，需从 must-pass 摘除）；现有 gtest 对裁剪后代码需全部通过。
- **不修改**：基线 `telephony_call_manager/`（只读）、`openspec/specs/pc-test-harness` 之外的既有规格内容、HMOS 上游。
