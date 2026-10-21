# Proposal

## Why

手表平台（LiteOS + MCU，单进程多线程）需要通话管理部件，但当前仓内的 `telephony_call_manager/` 是 OpenHarmony v6.0 手机平台快照（SA 4005、IPC、ffrt、多类通话形态），无法直接在 liteOS 上落地。按 AGENTS.md 的约束把它裁剪移植到 `telephony_call_manager_mini/`，需要一份以 baseline 规格（`openspec/specs/`，共 25 个能力）为对照、逐能力说明移除/保留/修改方式的变更规划。

## What Changes

- 以 `telephony_call_manager/`（v6.0，只读）为唯一基线，整棵拷贝出 `telephony_call_manager_mini/`，所有裁剪与修改只在 mini 内进行（**BREAKING**：不再提供 IPC/SystemAbility 对外接口形态）。
- 移除手表平台不支持的功能（视频、会议、卫星、分布式/互信互联、蓝牙通话、OTT、地震预警、视频彩振、有线耳机、语音播报、防诈、超级隐私、折叠屏、EDM、来电闪光、状态栏静音图标、贴耳灭屏、星闪、MAKE_CALL_WITH_TOKEN、STR、eSIM、新通话/CeliaCall、地震预警响铃链路等全部相关代码与需求）。
- 保留但桩化暂不可用的外部依赖调用点：音频、DataShare 数据库、公共事件广播、功耗锁、通知、骚扰来电查询、号码识别/黄页、RTT 文件节点、拉起通话界面，均以 `// todo!!! [标签] ref to <文件> <函数>` 占位，**逻辑保留**（代码按功能实现，不因无外部接口而丢弃功能）。
- 跨模块交互改造：与 cellular_call / core_service / cellular_data / sms_mms / TelephonyCust 的 IPC 通信改为 `XxxClient::GetInstance().Xxx()` 单例桩；ffrt 换打桩的 EventHandler；sptr 换 std::shared_ptr/unique_ptr；HiSysEvent/hitrace 换日志；不继承 SystemAbility、不做 IPC，`CallManagerClient` 直调 `CallManagerService`；不做权限校验。
- 构建面同步裁剪：`callmanager.gni` 的 sources/宏块、根 `BUILD.gn` declare_args、bundle.json features、sa_profile（整体不迁移）、测试 target 一并调整。
- **BREAKING**（涉及 ECC、权限校验、IPC 枚举、跨部件结构体，标注需人工复核）：
  - ECC：拨号/拒接判定链中紧急呼叫豁免逻辑保留，但判定树裁剪（DSDA/eSIM/一号双终端分支删除）——**需人工复核**。
  - 权限校验：liteOS 不做权限校验，基线的校验行为整体移除——**需人工复核**。
  - IPC 枚举值即 ABI：`CallManagerCallAbilityInterfaceCode` 等枚举保留原值只做末尾追加约定，不再承载实际 IPC——**需人工复核**。
  - 跨部件结构体：`AppExecFwk::PacMap` 等替换为结构体，涉及与 cellular_call 等模块的数据交换面——**需人工复核**。

## Capabilities

### New Capabilities

- `liteos-stub-layer`：liteOS 桩层约定——`telephony_call_manager_mini/stub/` 目录、`XxxClient::GetInstance().Xxx()` 单例桩形态、`// todo!!! [标签] ref to <文件> <函数>` 占位标签、EventHandler/日志/参数/基础库（securec、c_utils、log、cJSON、libphonenumber）桩的使用方式。

### Modified Capabilities

按 baseline 能力逐一给出 delta（`specs/<id>/spec.md`，REMOVED/MODIFIED/ADDED），能力清单与处置见下方「裁剪范围」表：

- `call-object-management`、`call-control-management`、`call-status-management`、`call-state-observer`、`audio-device-management`、`telephony-interaction`、`call-manager-service`、`call-report`、`hisysevent-diagnostics`、`spam-call-identification`、`number-identity`、`call-utils`、`native-client-api`、`build-config`、`pc-test-harness` — 修改。
- `bluetooth-call`、`video-call-control`、`satellite-call`、`distributed-call`、`interoperable-call`、`display-management`、`voice-assistant-call`、`antifraud-call`、`earthquake-alarm-call`、以及 `call-setting-management` 之外的整能力移除项见裁剪范围表（删除源文件的能力均产出 REMOVED delta）。
- `call-setting-management` — 保留（无 spec 级行为变更，不出 delta；其 cellular_call 出口变化体现在 `telephony-interaction`）。

## 裁剪范围

按 `openspec/specs/` 的能力 id 逐条列出处置（移除 / 保留 / 修改）与理由；delta、design 决策表、tasks 均从本表派生。

| baseline 能力 id | 处置 | 理由（一行） |
| --- | --- | --- |
| call-manager-service | 修改 | 不继承 SystemAbility/无 IPC（客户端直调）、移除权限校验与 Celia/新通话/会议/视频/蓝牙入口；功能主线与特殊码/语音信箱链路保留 |
| call-setting-management | 保留 | UT 补充业务（呼转/呼限/等待/USSD/MMI）须支持（AGENTS 说明第 1 条）；行为不变，cellular_call 出口桩化体现在 telephony-interaction |
| call-control-management | 修改 | 控制主线保留；移除会议控制、超级隐私管理器、蓝牙/OTT 拨号处理、HFP 广播、EDM/彩振相关入口；外部出口桩化 |
| call-object-management | 修改 | CS/IMS/VoIP 对象主线保留；移除会议对象、OTT/蓝牙/卫星/有线耳机/视频对象；sptr→智能指针 |
| call-status-management | 修改 | 上行状态机与来话判定链保留；移除 DSDA 族（GetDsdsMode 恒 0）、防诈/Celia 钩子、蓝牙/分布式/运动识别分支；广播与焦点模式判定保留并桩化出口 |
| call-state-observer | 修改 | 通话记录/拒接短信/亮屏/通知逻辑保留、外部调用 todo 桩化；移除贴耳灭屏、状态栏静音图标、有线耳机观察者 |
| audio-device-management | 修改 | 音频状态机/静音/回铃逻辑保留、audio 框架调用 todo 桩化；移除彩振（crsType==CRS_TYPE）、蓝牙/有线耳机/星闪路由、振动 |
| telephony-interaction | 修改 | Cellular/CoreService 连接类保留为适配器、内部改调 `XxxClient::GetInstance()` 桩；VoIP 连接外部出口桩化、冲突链保留；移除蓝牙连接；ffrt 队列换打桩 EventHandler |
| call-report | 修改 | 观察者注册与两路（全局/带槽位）上报保留；无 IPC，死亡通知/代理层不可达，改直调回调 |
| hisysevent-diagnostics | 修改 | HiSysEvent/hitrace 维测改日志打印；dump 能力按无 hidumper 服务简化为日志输出 |
| bluetooth-call | 移除 | AGENTS：不支持 BLUETOOTH 类型通话（ABILITY_BLUETOOTH_SUPPORT 不支持） |
| video-call-control | 移除 | AGENTS：不支持视频通话（ABILITY_CAMERA_SUPPORT 恒关，代码无需迁移） |
| satellite-call | 移除 | AGENTS：不支持卫星通话 |
| distributed-call | 移除 | AGENTS：不支持分布式通话（无 dsoftbus，target_platform 非 watch 场景同删） |
| interoperable-call | 移除 | AGENTS：不支持 interoperable 通话 |
| display-management | 移除 | AGENTS：不支持折叠屏 |
| voice-assistant-call | 移除 | AGENTS：不支持语音播报（HiCar 语音助手） |
| spam-call-identification | 修改 | AGENTS：骚扰来电接口"暂不调用，不用 dlopen，依赖外部查询接口适配"——逻辑保留，外部查询出口 todo 桩化 |
| number-identity | 修改 | AGENTS：号码识别/黄页"暂不调用，依赖数据库接口适配"——逻辑保留，出口 todo 桩化 |
| antifraud-call | 移除 | AGENTS：不支持防诈 antifraud，相关代码无需迁移 |
| earthquake-alarm-call | 移除 | AGENTS：不支持地震预警 |
| call-utils | 修改 | 号码/设置/对话框/Ability 连接工具保留（libphonenumber、DataShare 调用桩化）；移除 EDM 禁拨、来电闪光、运动识别+传感插件 |
| native-client-api | 修改 | CallManagerClient 直调 CallManagerService；无 IPC 层；移除蓝牙/NearLink/超级隐私客户端与死亡通知；VoIP 代理桩化；JS/ETS/Cangjie 绑定不实现 |
| build-config | 修改 | gni/BUILD.gn/bundle.json 按裁剪同步；sa_profile 不迁移；declare_args 移除 hfp_async、保留 not_support_multicall；测试 target 调整 |
| pc-test-harness | 修改 | 被测路径软链指向 `telephony_call_manager_mini/`；强制宏集去掉 ABILITY_BLUETOOTH_SUPPORT；must-pass 套件更新（移除语音助手/地震预警/分布式通信套件） |
| liteos-stub-layer | 新增 | 上文 New Capabilities |

## 非目标

- 不实现 JS/ETS/Cangjie 侧外部接口（frameworks/js、frameworks/ets、frameworks/cj、interfaces/kits 不迁移）。
- 不迁移 SystemAbility/samgr/safwk 形态与任何 IPC 传输层（含 IPC 包封装、death recipient、stub 分发表）；liteOS 为单进程环境。
- 不实现权限校验（access_token 系调用不迁移）。
- 不支持并裁剪以下功能，且本变更不做其可恢复性设计：视频通话、会议通话、卫星通话、分布式/互信互联通话、BLUETOOTH 类型通话、OTT 类型通话、地震预警、视频彩振、有线耳机、语音播报、防诈、超级隐私、折叠屏、EDM 企业禁拨、来电闪光、状态栏静音图标、贴耳灭屏、星闪（NearLink）、MAKE_CALL_WITH_TOKEN、STR 模式（TELEPHONY_EXIT_STR）、eSIM、新通话（CeliaCall）。
- 不引入真实音频/数据库/通知/功耗锁实现：调用点只以 todo 占位，待对应框架接口就绪后另行适配。VoIP 与蜂窝冲突场景的处理逻辑保留，但对 voip_call_manager 的真实对接依赖后续畅连通话接入后再做。
- 不新增线程、不加锁（AGENTS：单进程多线程，目前只有一个线程）。
- 不修改只读基线 `telephony_call_manager/`、PC 测试工程框架 `test/` 的桩层 API 面（pc-test-harness 的调整仅限路径指向、宏集与套件清单）。

## Impact

- 新目录：`telephony_call_manager_mini/`（整棵拷贝自基线后裁剪）；`telephony_call_manager_mini/stub/`（本设计新增的桩目录）。
- 受影响构建面：`callmanager.gni`（sources/include_dirs/external_deps/宏块）、根 `BUILD.gn`（declare_args、cflags）、`bundle.json`（features）、`sa_profile/`（不迁移）、`frameworks/native/BUILD.gn`（api target 与 versionscript 简化）、unittest/fuzztest target 组织。
- 受影响测试面：`test/` 软链指向 mini、`tests/BUILD.gn` must-pass 套件集合、强制注入宏集。
- 外部系统：所有 OHOS 系统 API（audio_framework、data_share、common_event、notification、power、screenlock、camera、bluetooth、dsoftbus、miscdevice、hicollie、motion、location 等）不再被 mini 侧真实调用。
- 保持不变：IPC 枚举数值（ABI约定）、`telephony_call_manager/` 只读基线、日志隐私红线（号码/联系人名不进日志）。