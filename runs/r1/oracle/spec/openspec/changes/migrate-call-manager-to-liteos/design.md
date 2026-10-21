# Design

## 决策索引

| # | 决策 |
| --- | --- |
| D1 | 整棵拷贝基线到 `telephony_call_manager_mini/`，裁剪而非重写 |
| D2 | `CallManagerService` 去 SystemAbility 化，`CallManagerClient` 进程内直调；不做 IPC 与权限校验【需人工复核：IPC 枚举、权限校验】 |
| D3 | IPC 码表头全量保留，枚举值 ABI 冻结【需人工复核：IPC 枚举】 |
| D4 | 外部依赖按 AGENTS.md 四类处置：todo 占位 / 客户端单例打桩 / 同名桩 / 原语替换 |
| D5 | 桩统一放 `telephony_call_manager_mini/stub/`，跨模块客户端桩命名固定 |
| D6 | ffrt 全量替换为打桩 `EventHandler`：队列保 FIFO 串行，延时/取消语义保留 |
| D7 | 锁全量不迁移：删除锁成员与加锁调用；单线程运行 |
| D8 | `sptr` → `std::shared_ptr` 全量替换 |
| D9 | `AppExecFwk::PacMap`/`WantParams` → 结构体【需人工复核：跨部件结构体】 |
| D10 | DSDS 恒 0、单卡保留 slotId 传参、单主帐号精简 |
| D11 | 九个模块组整体删除（目录级），保留能力内再做分支级裁剪 |
| D12 | 特性宏：不支持宏连守卫代码删除，支持宏去守卫恒定义，feature 开关收敛 |
| D13 | HiSysEvent/HITRACE 维测点改日志打印，隐私红线不变 |
| D14 | RTT 保留接口与状态链，文件节点调用点 todo 占位 |
| D15 | VoIP 代码全保留，`VoipCallConnection` 桩化待畅连对接 |
| D16 | ECC 主干保留：ECC 豁免、`SetIsEccContact(true)` 与强制不静音不变，查卡/运营商判定经桩【需人工复核：ECC】 |
| D17 | 构建系统：gni/bundle.json/sa_profile/test target 按裁剪结果重组 |
| D18 | `test/` 门禁联动：软链切向 mini、must-pass 套件集调整、兼容层注手表宏集 |

## Context

基线 `telephony_call_manager/`（OpenHarmony-v6.0-Release 快照）是 SA 4005 形态的 HMOS 部件：`CallManagerService : SystemAbility` 经 IPC 对外，上行经 `ffrt::queue reportCallInfoQueue` 串行（`services/telephony_interaction/src/report_call_info_handler.cpp`），并发原语为锁（`std::mutex` 约 87 个文件、`ffrt::mutex` 41 个文件、`ffrt::shared_mutex` 8 个文件、`std::shared_mutex`/递归锁 3 个文件，合计约 629 处，均非递归语义为主）+ 条件变量（`TimeWaitHelper`、`HsdrHelper` 的 `cv_`）。构建真源是 `callmanager.gni`（`call_manager_sources`/`call_manager_include_dirs`/`call_manager_external_deps` + 12 个 `global_parts_info` 宏块与 watch 块）。目标平台 LiteOS + MCU：单进程单线程、无 samgr/IPC、无 OHOS 部件生态；PC 化测试工程 `test/`（见 `openspec/specs/pc-test-harness/spec.md`）以 must-pass 门禁验收。约束来源 AGENTS.md（功能范围、外部依赖处理、特性宏清单）。

## Goals / Non-Goals

**Goals:**
- `telephony_call_manager_mini/` 在 PC 测试工程上编译通过且 must-pass 门禁全绿。
- 保留能力的行为规格与基线一致（逻辑保留，仅换外部依赖调用形态）。
- 全部处置可追溯：每一处删除/占位/桩化在 delta specs 与 tasks 中有对应条目。

**Non-Goals:**
- 不实现音频/DataShare/广播/功耗锁/通知/骚扰/号码识别/RTT 文件节点的真实 liteOS 适配（仅占位，待外部接口就绪）。
- 不做畅连（meetime）VoIP 对接、不做双卡/DSDA、不做多线程并发。
- 不迁移 JS/ETS/仓颉绑定与 fuzztest。
- 本 change 仅规划，不产出业务代码。

## Decisions

### D1 整棵拷贝后裁剪
- **决策**：`telephony_call_manager_mini/` 由 `telephony_call_manager/` 整棵拷贝而来，随后做目录级删除、宏守卫删除、原语替换与桩化；目录结构与文件命名与基线保持一致。
- **理由**：AGENTS.md「代码逻辑与基线保持一致、功能做裁剪而不是重写」「目录结构与文件命名与基线保持一致」；整拷贝保证 diff 可审计、回退容易。
- **落点**：新增 `telephony_call_manager_mini/`（本阶段不创建）；后续 tasks 的拷贝步骤。

### D2 去 SystemAbility 化与直调【需人工复核：IPC 枚举、权限校验】
- **决策**：`CallManagerService` 去掉 `SystemAbility` 继承与 `DECLARE_SYSTEM_ABILITY`/`SystemAbility::MakeAndRegisterAbility`/`Publish`/`OnStart` 生命周期，保留 `DelayedSingleton` 与 `Init()`（首次 `GetInstance()` 懒初始化）；`CallManagerServiceStub` 及 11 个 `Init*Request` 建表不迁移；`CallManagerClient` 直调服务单例；`TelephonyPermission::CheckCallerIsSystemApp`/`CheckPermission` 不调用。
- **理由**：AGENTS.md「liteOS 中 callmanager 不继承 SystemAbility 也不实现 IPC 调用，直接从 CallManagerClient 调用 CallManagerService 的接口」「liteOS 上 callmanager 提供的外部接口暂不需要进行权限校验」。
- **落点**：`services/call_manager_service/src/call_manager_service.cpp`（去继承与生命周期）、`services/call_manager_service/src/call_manager_service_stub.cpp`（删除）、`interfaces/innerkits/call_manager_client.h`/`frameworks/native/`（直调改造）；权限校验调用点删除（原 `CheckPermission(Permission::PLACE_CALL)` 等）。

### D3 IPC 码表头保留【需人工复核：IPC 枚举】
- **决策**：`interfaces/innerkits/` 下 5 个 IPC 码表头（`call_manager_service_ipc_interface_code.h`（`CallManagerInterfaceCode` 79 项）、`call_status_callback_ipc_interface_code.h`（`CallStatusInterfaceCode` 41 项）、`call_ability_callback_ipc_interface_code.h`（`CallManagerCallAbilityInterfaceCode` 15 项）、`bluetooth_call_ipc_interface_code.h`（`BluetoothCallInterfaceCode` 17 项）、`cellular_call_ipc_interface_code.h`（`CellularCallInterfaceCode` 60 项））全量保留、不改枚举值；stub/proxy 类不迁移。
- **理由**：IPC 枚举值即 ABI，只能末尾追加（AGENTS.md 项目事实）；保留头文件使后续恢复 IPC/对拍桩时不破坏值域；删除枚举无收益。
- **落点**：`interfaces/innerkits/*_ipc_interface_code.h`（保留不动）。

### D4 外部依赖四类处置
- **决策/理由/落点**：按 AGENTS.md「外部依赖处理」分类逐项处置，见下表；表内「桩」均指 `telephony_call_manager_mini/stub/`（新代码）。

| 依赖域 | 处置类别 | 落点（调用点形态） |
| --- | --- | --- |
| 音频 audio | todo 占位 | `// todo!!! [audio] ref to <文件> <函数>`（`AudioProxy` 系列调用点） |
| 数据库 DataShare | todo 占位 | `// todo!!! [database]`（`CallDataBaseHelper`/`SettingsDataShareHelper`/`NumberIdentityDataBaseHelper`/通话记录与黄页查询调用点） |
| 广播 EventFwk::CommonEventManager | todo 占位 | `// todo!!! [broadcast]`（七组广播订阅与全部 `PublishCommonEvent` 调用点） |
| 功耗锁 RunningLock/亮屏灭屏 | todo 占位（空操作） | `// todo!!! [powerLock]`（`AcquireIncomingLock` 等调用点保留为空操作） |
| 通知 NotificationHelper | todo 占位 | `// todo!!! [notification]`（未接提醒调用点） |
| 骚扰来电（spamshield 扩展） | todo 占位、不用 dlopen | `// todo!!! [spam]`（`SpamCallAdapter` 扩展连接调用点） |
| 号码识别/黄页标记 | todo 占位 | `// todo!!! [numberIdentity]`（`NumberIdentityServiceHelper` 连接与导入请求调用点） |
| RTT 文件节点 | todo 占位 | `// todo!!! [rttFile]`（`StartRtt/StopRtt` 文件节点读写调用点，逻辑保留） |
| 拉起通话界面 CallConnectAbility | 外部接口经桩 | `stub/` 提供 `AbilityManagerClient::ConnectAbility` 形态桩（不真正拉起） |
| cellular_call 交互 | 客户端单例桩 | `CellularCallClient::GetInstance().Xxx()`（新桩） |
| core_service 交互 | 客户端单例桩 | `CoreServiceClient::GetInstance().Xxx()`（含 `GetVoiceMailNumber`/`HasSimCard`/FDN 查询） |
| cellular_data 交互 | 客户端单例桩 | `CellularDataClient::GetInstance().Xxx()`（默认数据卡查询） |
| sms_mms 交互 | 客户端单例桩 | `SmsClient::GetInstance().SendMessage(...)`（拒接短信） |
| TelephonyCust 交互 | 客户端单例桩（替代 dlopen） | `TelephonyCustClient::GetInstance().Xxx()`（台湾紧急号码改写/暴力急救号隐藏） |
| 状态注册上报（core_service 域） | 同名桩 | `TelephonyStateRegistryClient` 同名桩（`UpdateCallState/UpdateCallStateForSlotId` 空操作成功） |
| 系统参数 parameter | 同名桩 | `GetParameter/SetParameter/WatchParameter` 桩内参数表 |
| securec/c_utils/log/eventhandler 基础库 | 同名桩 | `stub/` 提供（含 `sptr` 别名到 `std::shared_ptr` 的兼容层） |
| cJSON | 同名桩 | `stub/` 提供 cJSON 接口形态 |
| libphonenumber | 同名桩 | `stub/` 提供 `ParseAndKeepRawInput/Format*` 形态 |
| HiSysEvent/HITRACE | 替代 | 日志打印（见 D13） |
| sptr | 替代 | `std::shared_ptr`（见 D8） |
| ffrt | 替代 | 打桩 `EventHandler`（见 D6） |
| PacMap/WantParams | 替代 | 结构体（见 D9） |

### D5 桩目录与客户端桩命名
- **决策**：全部桩收敛到 `telephony_call_manager_mini/stub/`；跨模块客户端桩类名固定为 `CellularCallClient`/`CoreServiceClient`/`CellularDataClient`/`SmsClient`/`TelephonyCustClient`（均为本 change 引入的新桩代码），方法名与基线 IPC 接口语义同名，桩支持测试配置返回值。
- **理由**：AGENTS.md「liteOS 的外部接口打桩函数统一放到 liteOS 代码的根目录的 stub 文件夹中」及各模块「XxxClient::GetInstance().Xxx()」的规定形式。
- **落点**：新目录 `telephony_call_manager_mini/stub/`（含 `cellular_call_client.h/.cpp`、`core_service_client.h/.cpp`、`cellular_data_client.h/.cpp`、`sms_client.h/.cpp`、`telephony_cust_client.h/.cpp`、`telephony_state_registry_client.*`、`syspara_stub.*`、`eventhandler_stub.*`、`cjson_stub.*`、`phonenumber_stub.*` 等文件，实施时定稿）。

### D6 ffrt → 打桩 EventHandler
- **决策**：`ffrt::queue`（`reportCallInfoQueue`、`reportAudioStateChangeQueue`（`audio_scene_processor.cpp`））、`ffrt::submit`（`DialCallBase` 的 `HangUpVoipCall`、`QueryCallerInfo`、`StoreCallRecord` 等）、`ffrt::submit_h + ffrt::task_attr().delay`（`DelayedDisconnectCallConnectAbility`、`ConnectCallUiService` 延时断开、`SendMmiCodeResult` 延迟上报）与 `ffrt::skip` 取消，全部替换为打桩 `EventHandler` 的投递/延时任务/取消；队列语义保持 FIFO 串行。
- **理由**：AGENTS.md「liteOS 不支持 ffrt，异步任务需要使用 EventHandler 替代，EventHandler 接口通过打桩实现」；上行单队列串行是基线行为契约，必须保留。
- **落点**：`services/telephony_interaction/src/report_call_info_handler.cpp`、`services/audio/src/audio_scene_processor.cpp`、`services/call/src/call_base.cpp`、`services/call/src/call_object_manager.cpp`、`services/call/src/call_control_manager.cpp`、`services/call/call_state_observer/src/call_records_manager.cpp`、`services/telephony_interaction/src/call_status_callback.cpp` 等 ffrt 调用点（`callVoiceAssistantQueue`/`unregisterCallbackQueue` 随模块移除）。

### D7 锁全量不迁移
- **决策**：`std::mutex`/`ffrt::mutex`/`ffrt::shared_mutex`/`std::shared_mutex`/`recursive_mutex` 与条件变量全部不迁移：锁成员与 `lock()/unlock()` 调用直接删除（不留空操作包装）；`TimeWaitHelper` 的 `WaitForResult/NotifyAll` 保留骨架（单线程下等待立即按超时返回）；如需新增线程先与用户对齐再补锁。
- **理由**：AGENTS.md「liteOS 是单进程多线程环境，目前只有一个线程，因此不需要加锁」；删除优于空操作（编译器可见、无残留语义）。
- **落点**：全仓锁声明与调用点（`toneStateLock_`（`audio_control_manager.cpp`）、`EdmCallPolicy` 的 `ffrt::shared_mutex`（随 EDM 移除）、`CellularCallConnection` 的 `clientLock_`（随重连移除）等）。

### D8 sptr → std::shared_ptr
- **决策**：`sptr<T>` 全量替换为 `std::shared_ptr<T>`，`wptr`/`RefPtr` 相关形态随 `c_utils` 桩提供兼容别名或直接改写。
- **理由**：AGENTS.md「sptr 在 liteOS 中使用 C++ 的智能指针（std::shared_ptr 或 unique_ptr）替代」。
- **落点**：`services/call/src/call_object_manager.cpp`（`callObjectPtrList_`）、`services/call_report/`（`callbackPtrList_`）、各 `sptr<CallBase>`/`sptr<ICallAbilityCallback>` 声明点。

### D9 PacMap/WantParams → 结构体【需人工复核：跨部件结构体】
- **决策**：`AppExecFwk::PacMap`（`DialCall(number, extras)` 的 extras、`SendCallUiEventForWindow`、`CallControlManager` 各入口的参数包）与 `WantParams`（`isNeedMuteRing` 补静音标志）替换为新增的纯 C++ 结构体（新代码，字段对齐现有 PacMap 键：`accountId`/`callType`/`videoState`/`dialScene`/`extraParams`/`bundleName` 等），`PutIntValue/GetIntValue` 形态改为结构体成员读写。
- **理由**：AGENTS.md「AppExecFwk::PacMap 等在 LiteOS 中无法使用的数据结构建议使用结构体替换」。
- **落点**：`services/call/src/call_control_manager.cpp`、`common_type.h`（新增结构体定义）、`services/call/src/call_base.cpp`（`isNeedMuteRing` 传递）。

### D10 DSDS 恒 0、单卡、单主帐号
- **决策**：DSDS 模式查询（`CoreServiceClient::GetInstance().GetDsdsMode()`，经桩实现）恒返回 0；`DSDS_MODE_V3`/`DSDS_MODE_V5_DSDA`/`DSDS_MODE_V5_TDM` 分支不迁移（`HandleHoldCallOrAutoAnswerCall`、`HandleDsdaInfo`、`IsDsdsMode3` 分档）；`slotId`/`accountId` 参数与传参链路保留；`OsAccountManager` 多帐号逻辑精简为单主帐号（`IsOsAccountVerified` 恒已解锁形态、`MAIN_USER_SPACE(100)` 恒真）。
- **理由**：AGENTS.md「不支持 DSDA，GetDsdsMode() 恒返回 0」「只支持单卡，实现时需预留双卡扩展能力」「只支持单主帐号能力，相关逻辑可以精简」。AGENTS.md 将该查询表述为 `CallManagerUtils::GetDsdsMode()`；v6.0 源码中实际调用点为 `CoreServiceClient::GetInstance().GetDsdsMode(dsdsMode)`（见落点），按源码实际形态执行，桩内恒填 0 即可满足 AGENTS.md 语义。
- **落点**：`telephony_call_manager_mini/stub/` 的 `CoreServiceClient` 桩（`GetDsdsMode()` 恒 0）、`services/call/src/call_status_manager.cpp`（`HandleDsdaInfo`、`HandleHoldCallOrAutoAnswerCall`）、`services/call/src/call_request_process.cpp`（`IsDsdsMode3`）、`services/call/call_state_observer/src/call_data_base_helper.cpp`（静默代理 URI 分支移除）。

### D11 九个模块组目录级删除
- **决策**：删除下表模块组（连源目录、子 BUILD.gn、gni 源）；保留能力内的分支级裁剪（会议对象族、`InitVideoCall`、OTT/卫星/蓝牙对象、超级隐私、有线耳机、EDM、闪光、状态栏、贴耳、星闪、通知观察者、彩振、动作识别、ESIM、防诈联动、`WantParams` 弹窗等）见各 delta spec。

| 模块组（目录） | 能力 id | 一行理由（AGENTS.md） |
| --- | --- | --- |
| `services/bluetooth/` | bluetooth-call | BLUETOOTH 类型通话不支持 |
| `services/video/` | video-call | 视频通话不支持 |
| `services/satellite_call/` | satellite-call | 卫星通话不支持 |
| `services/distributed_call/`（含 `transmission/`、`distributed_communication/`） | distributed-call | 分布式通话不支持（SUPPORT_DSOFTBUS 不支持） |
| `services/interoperable_call/` | interoperable-call | 互通通话不支持（含 watch 专属 `interoperable_settings_handler.cpp`） |
| `services/antifraud/`（含 `antiinclude/`） | antifraud-call | 防诈不支持；不用 dlopen |
| `services/call_voice_assistant/` | call-voice-assistant | 语音播报不支持 |
| `services/call_earthquake_alarm/` | call-earthquake-alarm | 地震预警不支持 |
| `services/display/` | fold-display | 折叠屏不支持 |

- **理由**：AGENTS.md 功能范围清单（「相关代码无需迁移」项）。
- **落点**：`callmanager.gni` 的 `call_manager_sources`/`call_manager_include_dirs` 对应条目；`sa_profile/`（随 D2 直调整体不迁移）；`test/unittest` 对应 target。

### D12 特性宏处置
- **决策**：不支持宏 → 守卫代码与宏块一并删除；支持宏 → 宏块恒定义（去 `global_parts_info` 守卫）；feature 开关只保留 `call_manager_feature_not_support_multicall`。

| 宏 | 处置 | 落点 |
| --- | --- | --- |
| `HFP_ASYNC_ENABLE` | 删（含 declare_args/bundle.json feature） | `BUILD.gn` + `call_control_manager.cpp` 守卫块 |
| `NOT_SUPPORT_MULTICALL` | 保留 feature（默认 false 不定义） | `BUILD.gn`/`bundle.json` + `call_{control,status,object}_manager.*` |
| `ABILITY_CONFIG_SUPPORT`/`ABILIT_CONFIG_SUPPORT` | 删守卫代码（carrier config 查询走默认值） | `call_policy/cs_conference*/ims_call/ott_call.cpp` |
| `ABILITY_CAMERA_SUPPORT` | 删 | `video_control_manager.cpp`（随 D11 删目录） |
| `ABILITY_CAMERA_FRAMEWORK_SUPPORT` | 删 | `incoming_flash_reminder.cpp`（随来电闪光移除） |
| `ABILITY_SCREENLOCKMGR_SUPPORT` | 删 | `callmanager.gni` + `incoming_flash_reminder.cpp` |
| `OHOS_SUBSCRIBE_MOTION_ENABLE` | 删 | `callmanager.gni` + `motion_recognition.*` |
| `SUPPORT_VIBRATOR` | 删 | `callmanager.gni` + `audio_proxy.cpp` 振动块 |
| `HICOLLIE_ENABLE` | 删 | `callmanager.gni` + `call_manager_service_stub.cpp`（随 stub 删除） |
| `SUPPORT_MUTE_BY_DATABASE` | 删（watch 块） | `callmanager.gni` + `interoperable_settings_handler.cpp`（随 D11 删） |
| `RECONNECT_MAX_TRY_COUNT` | 删（无重连） | `cellular_call_connection.cpp` 重连块 |
| `ABILITY_MEDIA_SUPPORT` | 删 | `wired_headset.cpp`/`call_control_manager.cpp` 耳机按键块 |
| `ABILITY_DISPLAY_SUPPORT` | 删 | `incoming_call_notification.cpp`（随通知观察者移除） |
| `ABILITY_NOTIFICATION_SUPPORT` | 删 | `incoming_call_notification.cpp` |
| `ABILITY_STATUS_BAR_CONTROL_SUPPORT` | 删 | `status_bar.cpp` |
| `CALL_MANAGER_AUTO_START_OPTIMIZE` | 删 | `frameworks/native/BUILD.gn`(rk3568) + `call_manager_proxy.*`（proxy 随 D2 改造删除） |
| `ABILITY_BLUETOOTH_SUPPORT` | 删 | `callmanager.gni` + bluetooth/distributed 组（随 D11） |
| `ABILITY_AUDIO_SUPPORT` | 删（基线死分支：调用不存在的 `AudioProxy::GetToneDescriptorPath`） | `tone.cpp` |
| `SUPPORT_DSOFTBUS`/`SUPPORT_HEARING_AID`/`CALL_MANAGER_CALL_TRANSFER`/`ABILITY_POWER_SUPPORT`（gni 块）/`OHOS_SUBSCRIBE_USER_STATUS_ENABLE` 等 gni 不支持块 | 删块 | `callmanager.gni`；`ABILITY_POWER_SUPPORT` 的调用点按 D4 功耗锁 todo 占位 |
| `ABILITY_CELLULAR_SUPPORT`/`ABILITY_SMS_SUPPORT`/`CELLULAR_DATA_SUPPORT`/`TELEPHONY_CUST_SUPPORT`/`OHOS_BUILD_ENABLE_TELEPHONY_CUST` | 恒定义（源迁移，外部交互经桩） | `callmanager.gni` 宏块改恒定义、依赖改指向 `stub/` |
| `SUPPORT_RTT_CALL`/`CALL_MANAGER_SOS_NO_RINGBACK_TONE`/`CALL_MANAGER_WATCH_CALL_BLOCKING`/`CALL_MANAGER_THERMAL_PROTECTION` | 无需显式定义（v6.0 源码零引用，无代码可迁移） | — |
| `CONFIG_FACTORY_VERSION` | 按宏定义能力保留（产线开/商用走 `#else`，两分支都支持）；v6.0 零引用故当前无代码改动 | 见 Open Questions Q1 |

- **理由**：AGENTS.md「宏定义按实际代码实现来判断是否需要迁移」+ 特性宏支持范围清单；零引用宏经 rg 全仓核验（v6.0 无命中）。
- **落点**：`callmanager.gni`、根 `BUILD.gn`、`bundle.json`、上表各源文件。

### D13 维测改日志
- **决策**：`CallManagerHisysevent` 的全部 HiSysEvent 上报与 `FinishAsyncTrace/StartAsyncTrace` HITRACE 点改日志打印（格式保留事件名与关键参数）；隐私红线不变：号码、联系人名不进日志，用 callId/slotId/index 定位；`CallManagerDumpHelper::Dump` 骨架保留。
- **理由**：AGENTS.md「HiSysEvent、HITRACE 相关维测使用日志打印替代」+ 隐私基线约束。
- **落点**：`services/hisysevent/src/call_manager_hisysevent.cpp`（`WriteDialCallFaultEvent` 等改为日志宏）、各 `FinishAsyncTrace` 调用点。

### D14 RTT 保留
- **决策**：`StartRtt/StopRtt` 接口、RTT 状态与回调链保留；RTT 的文件节点读写调用点 todo 占位（`// todo!!! [rttFile]`），逻辑与错误码路径保留。
- **理由**：AGENTS.md 支持宏清单含 `SUPPORT_RTT_CALL`；「RTT 业务不再使用文件节点的方式，相关调用暂不实现，依赖通路接口适配」。
- **落点**：`services/call_setting`/`CallRequestHandler` 的 RTT 入口、`cellular_call_connection.cpp` 的 `StartRtt/StopRtt` 转发（经桩）。

### D15 VoIP 保留待畅连
- **决策**：`VoIPCall`/`voipCallObjectList_`/冲突处理（`HangUpVoipCall`、`CarrierAndVoipConflictProcess`）与 `HandleVoipCallReportInfo` 全保留；`VoipCallConnection` 经桩实现（模拟 voip_call_manager 缺席，接口可配置返回）。
- **理由**：AGENTS.md「liteOS 项目暂不支持 VOIP 类型通话，依赖后续跟 meetime 畅连通话，解决畅连通话和蜂窝通话冲突场景」——暂不支持指外部接入，代码按功能实现不能丢弃。
- **落点**：`services/call/src/voip_call.cpp`、`services/call/src/call_object_manager.cpp`、`services/telephony_interaction/src/voip_call_connection.cpp`（桩化）。

### D16 ECC 主干保留【需人工复核：ECC】
- **决策**：ECC 判定链保留主干：`CheckNumberIsEmergency`（经 `CellularCallClient::GetInstance().IsEmergencyPhoneNumber(...)` 桩）、`CallPolicy::DialPolicy` 的 `isEcc` 豁免、`HasEmergencyCall`/`HasNormalCall`（无卡/飞行模式/无服务/CT 无 IMS 判定经 `CoreServiceClient` 桩）、`DialScene::CALL_EMERGENCY` 置 `SetIsEccContact(true)`、ECC 禁止入会/禁止视频升级（随会议/视频移除，保持拒绝语义）、紧急呼叫强制不静音；卫星/一号双终端等 ECC 增强分支随对应能力移除。
- **理由**：ECC 是安全行为，裁剪必须保守；AGENTS.md 未将 ECC 列入不支持范围，仅裁剪其多卡/卫星相关增强。
- **落点**：`services/call/src/call_policy.cpp`、`services/call/src/call_control_manager.cpp`（`CanDial/PackageDialInformation`）、`utils/call_number_utils.cpp`、`services/audio/src/audio_control_manager.cpp`（ECC 强制不静音）。

### D17 构建系统重组
- **决策**：gni/bundle.json/sa_profile 按裁剪结果重组（受影响条目见下表）；`sa_profile/`（`4005.json`/`4005_auto_start_optimize.json`）整体不迁移；`test/fuzztest` 不迁移；`test/unittest` 保留 gtest target 并随源调整。

| 构建文件 | 受影响条目 |
| --- | --- |
| `callmanager.gni` | `call_manager_sources`：删 9 个模块组源 + 不支持宏守护文件（`incoming_call_notification`、`missed_call_notification`、`status_bar`、`wired_headset`、`incoming_call_wake_up`、`proximity_sensor`、`motion_recognition`、`screen_sensor_plugin`、`incoming_flash_reminder`、`interoperable_settings_handler` 等）；`call_manager_include_dirs` 同步；`call_manager_external_deps`：`cJSON:cjson`/`libphonenumber:phonenumber_standard` 及 OHOS 部件依赖改指向 `stub/`；宏块按 D12 表收敛 |
| 根 `BUILD.gn` | `declare_args()` 删 `call_manager_feature_hfp_async_enable`；defines/cflags 保留（`TELEPHONY_LOG_TAG`/`LOG_DOMAIN`/`-fno-exceptions`/`-fno-rtti` 等） |
| `bundle.json` | `component.features` 删 hfp_async feature；`inner_kits` 删 `cj_telephony_call_ffi`；`fwk_group` 删 `frameworks/js:call`；`service_group` 去 `sa_profile` |
| `sa_profile/` | 整体不迁移（直调架构无 SA） |
| `frameworks/` | 仅保留 `frameworks/native:tel_call_manager_api`；`frameworks/js`/`frameworks/ets`/`frameworks/cj` 不迁移 |
| `test/unittest/BUILD.gn` | 删 `call_earthquake_alarm_test`/`call_voice_assistant_test`/`distributed_communication_test` target；其余 gtest target 随源裁剪调整 |

- **理由**：AGENTS.md 架构要求（无 SA/IPC、stub 统一管理、目录一致）+ D2/D11/D12 的必然结果；「删文件须同步 gni」为 tasks 门禁。
- **落点**：上表全部文件。

### D18 test/ 门禁联动
- **决策**：`test/base/telephony/call_manager` 软链从 `telephony_call_manager/` 副本切向 `telephony_call_manager_mini/`；`tests/BUILD.gn` 的 `mustpass_tests` 移除 `tel_call_voice_assistant_test`、`distributed_communication_test`、`tel_call_earthquake_alarm_test`（对应能力已删，target 不存在），保留 `sanity_test`、`liteos_stub_test`、`tel_call_manager_zero2_gtest`、`tel_call_manager_zero5_gtest`、`tel_call_manager_special2_test`；兼容层注入宏从 `ABILITY_BLUETOOTH_SUPPORT=0x1`+`ABILITY_CELLULAR_SUPPORT=0x1` 改为手表宏集（`ABILITY_CELLULAR_SUPPORT`、`ABILITY_SMS_SUPPORT`、`CELLULAR_DATA_SUPPORT`、`TELEPHONY_CUST_SUPPORT`、`OHOS_BUILD_ENABLE_TELEPHONY_CUST`）；桩层（`test/stubs/`）不动——mini 仍按 v6.0 头面使用 eventhandler/securec 等（由 test/stubs 满足）。
- **理由**：基线 spec「原仓位置」场景即预留该切换；must-pass 语义 = 门禁全绿验证裁剪后代码；已移除能力的套件无被测代码不可运行。
- **落点**：`test/base/telephony/call_manager`（软链）、`test/tests/BUILD.gn`（`mustpass_tests`）、`test/build/ohos.gni`（注入宏集）。

## Risks / Trade-offs

- [桩语义与真实 liteOS 接口漂移（后续适配返工）] → 桩方法名/参数与基线 IPC 语义一一对齐，桩配置可注入断言；适配时以桩为契约替换。
- [直调后单例状态在测试与产品间分裂（`DelayedSingleton` 模板静态成员）] → 沿用 `test/` 工程静态包（`complete_static_lib`）单一链接单元实践。
- [删宏/删目录后 gni 残留引用导致编译失败] → tasks 规定每次删除同步 gni，must-pass 全量编译兜底。
- [must-pass 套件缩减导致回归覆盖变弱] → zero2/zero5/special2 覆盖核心上下行链路；`liteos_stub_test` 锁桩语义；后续按 delta specs 场景补 gtest。
- [ffrt→EventHandler 引入任务次序差异] → 打桩 EventHandler 保持 FIFO 与延时语义，delta spec 有「连续两次全量列表串行」用例可测。
- [锁删除后若未来引入多线程产生竞态] → AGENTS.md 约束新增线程先与用户对齐；届时按线程边界补锁。
- [VoIP 保留代码在无畅连对接前为不可达路径] → 桩可注入模拟上报，gtest 覆盖冲突处理逻辑，防止代码腐化。

## Migration Plan

实施阶段（tasks.md 展开为带验收的子任务）：
1. 整拷贝 `telephony_call_manager/` → `telephony_call_manager_mini/`，建 `stub/`。
2. 目录级删除（D11）+ 同步 `callmanager.gni`。
3. 宏处置（D12）+ 构建重组（D17）。
4. 原语替换：ffrt→EventHandler（D6）、锁删除（D7）、sptr（D8）、PacMap/WantParams 结构体（D9）。
5. 直调架构改造（D2/D3）+ 权限校验调用点删除。
6. 外部依赖处置（D4/D5）与维测改日志（D13）、ECC/VoIP/RTT 专项（D14~D16）。
7. `test/` 联动（D18）与 must-pass 门禁全绿。

回退：`telephony_call_manager_mini/` 为新增目录，直接删除即可；`test/` 软链切回 `telephony_call_manager/` 副本、`mustpass_tests` 恢复 8 套件。

## Open Questions

1. **CONFIG_FACTORY_VERSION 与源码现状矛盾**：AGENTS.md 要求宏保留且产线/商用两分支都支持，但 v6.0 源码 rg 零引用。本设计按「保留宏定义能力、当前无代码改动」处置；实施时若上游 mini 引入该宏的引用，需补两分支代码——是否需要现在预留分支骨架，待确认。
2. **VoIP 桩语义**：`VoipCallConnection` 桩按「模拟 voip_call_manager 缺席（接口返回失败/空）」处置；畅连（meetime）对接后改真实通路。桩默认返回值（失败 vs 成功空操作）影响 `ReportIncomingCall` 等路径的可测性，待与畅连方案对齐。
3. **IPC 码表头的长期去留**：按 ABI 冻结保留 5 个码表头，但 liteOS 无消费方；后续是否收敛为单一头或标记 deprecated，待确认（需人工复核项）。
4. **状态注册上报的桩形态**：`TelephonyStateRegistryClient` 按 core_service 域同名桩化（空操作成功）；AGENTS.md 对 core_service 交互规定的形式是 `CoreServiceClient::GetInstance().Xxx()`，是否需要把状态上报改挂到 `CoreServiceClient` 桩面，待确认。
5. **must-pass 套件集**：移除 3 套件后门禁为 5 套件；是否新增 mini 专属 gtest 套件（覆盖 delta specs 场景，如 `liteos_runtime` 的直调/桩/DSDS 用例）入 must-pass，待实施时确认。
6. **DSDS 枚举跨部件值域**：`DSDS_MODE_V3`/`DSDS_MODE_V5_DSDA`/`DSDS_MODE_V5_TDM` 为 core_service 侧枚举值；桩侧 `GetDsdsMode()` 恒 0 的同时，mini 内是否保留对这些枚举名的引用（仅死代码风险）——当前按「分支不迁移」处置，待确认。
7. **PacMap/WantParams 结构体字段命名**：`isNeedMuteRing`、extras（`accountId`/`extraParams` 等）的结构体字段名与调用方（CallUI/畅连侧）对齐方式，实施时定稿。
8. **AGENTS.md 中 `CallManagerUtils::GetDsdsMode()` 的表述差异**：AGENTS.md 以 `CallManagerUtils::GetDsdsMode()` 指称 DSDS 模式查询，但 v6.0 源码中该函数不存在，实际调用点为 `CoreServiceClient::GetInstance().GetDsdsMode(dsdsMode)`（`HandleDsdaInfo`、`HandleHoldCallOrAutoAnswerCall`、`IsDsdsMode3`）。本设计按源码实际形态将桩面落在 `CoreServiceClient` 桩（D10），语义与 AGENTS.md「恒返回 0」一致；该表述是否源自其他版本基线，待人工确认。
