# Design

## Context

基线是手机平台 OpenHarmony v6.0 的 SA 4005 部件（进程 foundation、IPC、ffrt、-fno-exceptions/-fno-rtti），25 个 baseline 能力规格（见 `openspec/specs/`）描述其现状。目标平台为 LiteOS + MCU 手表：单进程、当前单线程、无 samgr/safwk/IPC、无 OHOS 系统服务生态。移植方式是整棵拷贝出 `telephony_call_manager_mini/` 后"裁剪而非重写"，所有桩集中于 `telephony_call_manager_mini/stub/`（本设计新增目录）。PC 门禁（`test/`，规格 `pc-test-harness`）将 `//base/telephony/call_manager` 软链指向 mini 后作为验收工具。动机见 proposal.md「Why」。

## Goals / Non-Goals

**Goals:**

- mini 与基线在保留功能上行为一致；裁剪点全部能从 AGENTS.md 条文找到依据。
- 暂不可用的外部接口只替换调用点（todo 占位 / 客户端单例桩 / 同名桩），不丢功能逻辑。
- 桩有统一形态与统一目录，测试可在 PC 门禁中驱动。

**Non-Goals:** 见 proposal.md「非目标」。此外设计层面再明确：不做锁的替代实现（删除而非替换）；不做权限校验的门禁替代；不重排 IPC 枚举。

## 决策索引

1. 变更载体：整拷 `telephony_call_manager_mini/`，目录/文件命名与基线一致，只删不改名。
2. 运行形态：无 SystemAbility/safwk/samgr/IPC，`CallManagerClient` 直调 `CallManagerService` 单例。
3. IPC 层处置：stub/proxy/death recipient/versionscript 不迁移；IPC 枚举值原样保留（ABI）。
4. 跨模块交互：连接类（`CellularCallConnection`、`CoreServiceConnection`、`VoipCallConnection`、`TelephonyCustWrapper` 等）保留为适配器，内部改调 `XxxClient::GetInstance().Xxx()` 桩。
5. 外部依赖五类处置：暂不调用（todo 占位）、客户端单例打桩、同名桩、替代、不调用；统一 todo 标签语法。
6. 并发原语：ffrt 队列/任务 → 打桩 EventHandler（保持串行语义）；全部锁删除，不设替代。
7. 特性宏：支持宏原样保留（含 declare_args feature）；不支持宏做"删源文件 / 退役宏块 / 去守卫"，逐宏见处置表；零引用宏记录处置结论为"无迁移动作"。
8. 功能裁剪：AGENTS「不支持，相关代码无需迁移」→ 删源文件 + gni 同步；「暂不支持/暂不调用」→ 保留逻辑 + 出口桩化（含 VoIP 冲突链）。
9. DSDA/eSIM/一号双终端：`GetDsdsMode()` 恒 0、eSIM 不支持，相关判定分支删除，`slotId` 参数保留供双卡扩展。
10. 单主帐号：os_account 查询精简为"默认主帐号常量"，分支结构保留。
11. 权限校验：整体移除（不调用 access_token 系接口）。
12. 维测：HiSysEvent/hitrace 改日志；`CallManagerDumpHelper` 保留，Dump 输出走日志。
13. 桩目录：`telephony_call_manager_mini/stub/` 集中承载全部新增桩（新代码）。
14. 行为保持默认：AGENTS 未明令改变的基线语义（含已发现的疑似缺陷）一律照抄并登记 Open Questions。

## Decisions（决策详情）

### D1 变更载体与目录结构

- **决策**：从 `telephony_call_manager/` 整棵拷贝出 `telephony_call_manager_mini/`，目录结构与文件命名保持一致；被移除的源文件直接删除而不留空文件；桩新增目录 `telephony_call_manager_mini/stub/`。
- **理由**：AGENTS「liteOS 代码架构与 HMOS 实现尽量保持一致」「目录结构和文件命名尽量与 HMOS 保持一致」「外部接口打桩函数统一放到 liteOS 代码的根目录的 stub 文件夹中」。
- **落点**：`telephony_call_manager_mini/`（新），其 `callmanager.gni`、根 `BUILD.gn` 同步裁剪（见 `build-config` delta 与 D7 宏处置表、被删文件表）。

### D2 运行形态：客户端直调服务

- **决策**：不继承 SystemAbility、不注册 samgr、无 InitServiceExtAbility 系生命周期；`CallManagerService` 以进程内单例提供，`CallManagerClient`（DelayedSingleton 形态保留）`Init` 时直接绑定该单例；`CallManagerServiceStub` 的 IPC 分发表不迁移；`OnStart` 中对蜂窝/VoIP 服务的回调注册改经 D4 适配器完成。
- **理由**：AGENTS「liteOS 中 callmanager 不继承 SystemAbility 也不实现 IPC 调用，直接从 CallManagerClient 调用 CallManagerService 的接口」；config.yaml「单进程单线程、不做权限校验」。
- **落点**：`frameworks/native/src/call_manager_client.cpp`（改 Init 直取单例）、`services/call_manager_service/src/call_manager_service.cpp`（删 SA 装饰、`PublishCallManagerService` 类逻辑改本地注册）、删 `call_manager_service_stub.cpp`；`sa_profile/`（4005.json、4005_auto_start_optimize.json）整体不迁移。
- **替代方案**：保留 stub 作为空实现——被否：dm 无 IPC 时分发表成为死代码，违反"删源文件"处置原则。

### D3 IPC 层处置（需人工复核：IPC 枚举）

- **决策**：所有 proxy/stub/death recipient 传输类不迁移；`ICallManagerService` 接口头与 `CallManagerCallAbilityInterfaceCode` 等枚举原样保留（枚举值 ABI 只允许末尾追加），供测试与后续系统恢复使用；`CallAbilityCallbackStub` 收敛为直调回调对象的薄入口。应用侧注册的回调（`CallAbilityCallback`）由服务直接持有对象指针调用。
- **理由**：AGENTS「不实现 IPC 调用」；config.yaml「IPC 枚举值即 ABI，只能末尾追加」。
- **落点**：删 `call_manager_proxy.cpp`、`call_manager_service_proxy.cpp`、`call_status_callback_proxy.cpp`、`cellular_call_proxy.cpp`、`cellular_call_callback_death_recipient.cpp`、`call_manager_death_recipient.cpp`、`call_ability_callback_proxy.cpp`、`call_ability_callback_death_recipient.cpp`、`services/telephony_interaction/src/call_status_callback_stub.cpp`；回调直调改造落 `call_report` 相关文件。
- **需人工复核**：若后续恢复系统形态，需保证枚举与基线值一致；本设计不改任何枚举值。

### D4 跨模块交互：连接类保留为适配器（需人工复核：跨部件结构体）

- **决策**：基线的连接/包装类保留作适配器，类名不变，内部实现从"取远端代理发 IPC"改为调用 stub/ 下的客户端单例：`CellularCallConnection` → `CellularCallClient::GetInstance().Xxx()`、`CoreServiceConnection` → `CoreServiceClient::GetInstance().Xxx()`、`VoipCallConnection`（对 voip_call_manager 的注册/控制出口）→ `VoipCallClient::GetInstance().Xxx()`（新代码桩）、`TelephonyCustWrapper` → `TelephonyCustClient::GetInstance().Xxx()`（不再 dlopen）、拒接短信 `SmsServiceManagerClient::SendMessage` → `SmsClient::GetInstance().Xxx()`、号码工具数据面 `CellularDataClient::GetInstance().Xxx()`。`BluetoothCallConnection` 属 BLUETOOTH 通话链路，删除。
- **理由**：AGENTS 明文规定该调用形态；保留 wrapper 是改动最小且保持"目录结构与基线一致"的读法（AGENTS 未要求删除连接类）。
- **替代方案**：删除连接类、在各调用点直接写 Client 单例——被否：改动面扩散到所有调用文件，违背"尽量保持一致"。
- **落点**：`stub/cellular_call_client.h/.cpp`、`stub/core_service_client.h/.cpp`、`stub/cellular_data_client.h/.cpp`、`stub/sms_client.h/.cpp`、`stub/telephony_cust_client.h/.cpp`、`stub/voip_call_client.h/.cpp`、`stub/state_registry_client.h/.cpp`（`CallStateReportProxy` 对 core_service 的 TelephonyStateRegistry 上报出口，均为本设计新增代码）；`services/telephony_interaction/src/{cellular_call_connection,core_service_connection,voip_call_connection}.cpp` 与 `services/call_manager_service/src/telephony_cust_wrapper.cpp` 内部改造。
- **需人工复核**：与 cellular_call 等模块交换的数据结构在桩面以基线结构体为签名的兼容问题；PacMap 按下条替换。

### D5 替代类改造

- **决策**：
  - `sptr<T>`/`RefPtr` → `std::shared_ptr<T>`（强引用语义）或 `std::unique_ptr`；`DelayedSingleton<T>` 保留模板形态，内部实现基于静态单例。
  - `AppExecFwk::PacMap` → 对应普通结构体（如上抛数据的 `CallAttributeInfo` 结构体族按基线字段平移；`PackParaInfo` 的 PacMap 出口改成结构体出口，供直调回调使用）。
  - `HiSysEvent::HiSysEventWrite`/hitrace → `stub/hisysevent_stub`（做日志打印，保持函数签名不变的同名桩）；`CallManagerHisysevent` 文件保留，内部经桩输出日志。
- **理由**：AGENTS「sptr 用 std::shared_ptr 或 unique_ptr 替代」「HiSysEvent、HITRACE 维测用日志替代」「PacMap 等用结构体替换」「基础库 securec、c_utils、log、eventhandler 的使用通过打桩实现」。
- **落点**：全仓类型替换（`services/`、`frameworks/native/`）；`stub/` 下新增 `securec_stub`、`c_utils_stub`（含 `sptr` 兼容别名视需要）、`log_stub`（hilog 同名桩）、`eventhandler_stub`、`cjson_stub`、`phonenumber_stub`（libphonenumber 桩）、`parameter_stub`（系统参数桩）。test/ 侧桩层 API 面不变（`pc-test-harness` 规格），mini 侧桩为独立实现。

### D6 外部依赖处置表（AGENTS「外部依赖处理」逐行对齐）

| 依赖类别 | 处置 | todo/桩 落点（调用方文件） |
| --- | --- | --- |
| 音频 audio（audio_framework 全族） | 暂不调用（todo 占位） | `services/audio/src/audio_proxy.cpp`、`ring.cpp`、`sound.cpp`、`tone.cpp`、`audio_player.cpp` 调用点标 `// todo!!! [audio] ref to <原文件> <函数>`，状态机与音量策略逻辑保留 |
| 数据库 DataShare（含 settings_datashare_helper、call_data_base_helper、number_identity_data_base_helper、call_records_handler 入库） | 暂不调用（todo 占位） | `utils/src/settings_datashare_helper.cpp`、`services/call/call_state_observer/src/{call_data_base_helper,call_records_handler}.cpp`、`utils/src/number_identity_data_base_helper.cpp` |
| 广播 EventFwk::CommonEventManager（订阅与发布） | 暂不调用（todo 占位） | `services/call/src/call_broadcast_subscriber.cpp`、`call_manager_service.cpp` 特殊码广播发布等 |
| 功耗锁（ABILITY_POWER_SUPPORT 内 RunningLockKeeper 系） | 暂不调用（todo 占位） | `services/call/call_state_observer/src/incoming_call_wake_up.cpp`、`services/call/src/call_control_manager.cpp` Acquire/Release 系 |
| 拉起通话界面 CallConnectAbility / CallUIAbility、对话框与设置页 ability、ability/bundle 信息查询（`MakeCall` 的 `StartAbility`、`GetBundleInfo`、`GetBundleNameByUid`、`IsBundleInstalled` 等出口） | 打桩 + todo 占位，标签统一用 [callUi] | `services/call/src/call_connect_ability.cpp`（ConnectAbility 语义经 `stub/` 打桩）、`call_ability_connect_callback.cpp`、`utils/src/{call_dialog,call_ability_connection,call_setting_ability_connection,call_manager_utils}.cpp` |
| 通知 NotificationHelper | 暂不调用（todo 占位） | `services/call/call_state_observer/src/{incoming_call_notification,missed_call_notification}.cpp` |
| 骚扰来电（不 dlopen） | 暂不调用（todo 占位），逻辑保留 | `services/spam_call/src/spam_call_adapter.cpp` 等的 Ability 连接改打桩；`spam_call_proxy/stub/connection` 文件删除，检测判定链与码表保留 |
| 号码识别/黄页标记 | 暂不调用（todo 占位） | `services/number_identity_proxy/src/number_identity_service.cpp`（IPC 新建删除，留桩）、`utils/src/number_identity_data_base_helper.cpp` |
| RTT 文件节点 | 暂不调用（todo 占位） | 本仓 v6.0 的 RTT 链路（`CallManagerService::StartRtt/StopRtt` → `IMSCall::StartRtt/StopRtt` → `CellularCallConnection::StartRtt/StopRtt`）不含文件节点操作，按 AGENTS「RTT 相关调用暂不实现」在适配器出口标 `// todo!!! [rtt] ref to cellular_call_connection.cpp StartRtt/StopRtt`，API 链路保留 |
| cellular_call / core_service / cellular_data / sms_mms / TelephonyCust | 客户端单例打桩 | 见 D4 |
| ffrt（队列与任务） | 替代：打桩 EventHandler | `report_call_info_handler.cpp` 串行队列、`call_request_handler.cpp`、`call_records_handler.cpp`、`call_status_callback.cpp` 1s/3s 延迟任务、`call_request_event_handler_helper.cpp`（基线 `PostTask` 已是 EventHandler 形态，替为桩） |
| libphonenumber | 打桩（签名相同的空实现） | `utils/src/call_number_utils.cpp` |
| 系统参数 parameter（SystemGetParameter 等） | 打桩 | `call_number_utils.cpp`、`call_incoming_filter_manager.cpp`、`call_manager_service.cpp` 等调用点 |
| cJSON | 打桩 | 解析侧（spam_call/json 数据面、voip 解析等） |
| securec / c_utils / hilog（log） / eventhandler | 同名桩（`stub/`） | 全仓 |
| 权限校验（access_token、PrivacyKit） | 不调用（直接删除校验块） | `call_manager_service.cpp` 校验族、视频摄像头权限块（视频已移除） |
| 锁（std::mutex/ffrt::mutex/shared_mutex） | 不调用（删除；不设替代） | 全仓约 72+41 处锁成员与用具；单线程假设见 D8 |
| OsAccountManager（os_account） | 精简：默认主帐号常量 | `call_status_manager.cpp` IsRejectCall 链、`call_request_handler.cpp` 等帐号查询点 |

todo 占位统一语法：`// todo!!! [audio/database/broadcast/powerLock/callUi/notification/spamCall/numberIdentity/rtt] ref to <基线文件名> <函数名>`（标签集即本表第一列；AGENTS「暂不调用」类必须逐调用点标注，不得删函数）。

### D7 特性宏处置表

**不支持宏（AGENTS「特性宏支持范围-不支持」）逐宏处置**（引用源均为 v6.0 零引用结论或 rg 命中清单）：

| 宏 | 场点（rg 结论） | 处置 |
| --- | --- | --- |
| CALL_MANAGER_CALL_TRANSFER | 零引用（含构建文件） | 无迁移动作 |
| SUPPORT_HEARING_AID | 零引用 | 无迁移动作 |
| SUPPORT_DSOFTBUS | 零引用（test/ 文档侧提及不计） | 无迁移动作（分布式链路整体删除） |
| CALL_MANAGER_AUTO_START_OPTIMIZE | frameworks/native `call_manager_proxy.cpp/.h`、`frameworks/native/BUILD.gn`、`sa_profile/4005_auto_start_optimize.json` | 客户端 autostart 守卫块与 proxy 一并删除（随 D2/D3）；profile 不迁移 |
| HFP_ASYNC_ENABLE | 根 `BUILD.gn` declare_args + `call_control_manager.cpp`（HfpBroadcastSubscriber） | feature 与守卫块删除（蓝牙不支持） |
| ABILITY_BLUETOOTH_SUPPORT | `callmanager.gni` 部件块 + 14 文件场点 | gni 部件块删除；bluetooth/ 与 distributed_call/ 相关文件删除；`call_control_manager.cpp`/`call_status_manager.cpp`/`call_object_manager.cpp`/audio 路由的蓝牙分支删除 |
| ABILITY_CAMERA_FRAMEWORK_SUPPORT | `incoming_flash_reminder.cpp` | 随文件删除 |
| SUPPORT_MUTE_BY_DATABASE | gni `target_platform=="watch"` 块 + `call_records_manager.cpp`、`call_manager_service.cpp` | watch 专设块整体删除（手表 mini 也不启用该行为）；两处 #ifdef 守卫块删除 |
| SUPPORT_VIBRATOR | gni 部件块 + `audio_proxy.cpp` | 部件块与守卫块删除 |
| HICOLLIE_ENABLE | gni 部件块 + `call_manager_service_stub.cpp` | 部件块删除；stub 文件随 D2 删除 |
| OHOS_SUBSCRIBE_USER_STATUS_ENABLE | 零引用 | 无迁移动作 |
| ABILITY_SCREENLOCKMGR_SUPPORT | gni 部件块 + `incoming_flash_reminder.cpp` | 随文件删除 + gni 部件块删除 |
| ABILITY_NOTIFICATION_SUPPORT | `incoming_call_notification.cpp`（仓内 gni 无定义） | 去守卫：保留通知判定逻辑，通知发送点按 notification todo 桩化（见 D6） |
| ABILITY_CONFIG_SUPPORT（及拼写变体 `ABILIT_CONFIG_SUPPORT`） | `call_policy.cpp`、`ims_call.cpp`、`cs_call.cpp`（变体）、`cs_conference.cpp`、`ims_conference.cpp`、`ott_conference.cpp`（仓内无定义恒关） | 会议/OTT 文件删除；`call_policy.cpp`/`ims_call.cpp`/`cs_call.cpp` 守卫块删除（config 部件不迁移） |
| ABILITY_STATUS_BAR_CONTROL_SUPPORT | `status_bar.cpp`（仓内无定义，开启分支还引用本仓未定义符号） | 随文件删除 |
| ABILITY_MEDIA_SUPPORT | `call_control_manager.cpp`（onButtonDealing）、`wired_headset.cpp` | 两处守卫块随文件/块删除 |
| RECONNECT_MAX_TRY_COUNT | `cellular_call_connection.cpp`（恒关，`CONNECT_MAX_TRY_COUNT` 零使用） | 守卫块删除 |
| ABILITY_CAMERA_SUPPORT | `video_control_manager.cpp` | 随文件删除 |
| OHOS_SUBSCRIBE_MOTION_ENABLE | gni 部件块 + `motion_recognition.cpp/.h` | 部件块删除；文件删除 |

**支持宏处置**：

| 宏 | 场点 | 处置 |
| --- | --- | --- |
| SUPPORT_RTT_CALL | 零引用 | 无迁移动作（RTT API 本体无宏门控，保留；文件节点调用 todo） |
| NOT_SUPPORT_MULTICALL | 根 `BUILD.gn` declare_args + 7 文件 | 保留 declare_args 与 #ifdef 骨架（默认 false）；骨架内引用蓝牙/eSIM 的判定族（`IsTwoCallBtCallAndESIM`/`IsTwoCallESIMCall` 及调用点 `HangUpFirstCall` 判定链）随其移除，其余骨架逻辑照抄；AGENTS 非零 DSDS 流程不迁移，仅由非零分支进入的等待矩阵（`HoldOrDisconnectedCall`→`HandleCallWaitingNumTwo/One/Zero`）删除，`needWaitHold_`/`dialCallInfo_` 字段与复位写点、读取接口作骨架照抄 |
| CALL_MANAGER_SOS_NO_RINGBACK_TONE | 零引用 | 无迁移动作 |
| CALL_MANAGER_WATCH_CALL_BLOCKING | 零引用 | 无迁移动作 |
| CALL_MANAGER_THERMAL_PROTECTION | 零引用 | 无迁移动作 |
| ABILITY_CELLULAR_SUPPORT | gni 部件块 + `cellular_call_connection.cpp` | 保留（cellular_call 交互经 D4 桩） |
| ABILITY_SMS_SUPPORT | gni 部件块 + `reject_call_sms.cpp/.h` | 保留（SmsClient 桩） |
| CELLULAR_DATA_SUPPORT | gni 部件块 + `call_number_utils.cpp` | 保留（CellularDataClient 桩） |
| ABILITY_POWER_SUPPORT | gni 部件块 + 7 文件 | gni 保留；功耗锁调用点 todo（proximity_sensor 文件删除） |
| TELEPHONY_CUST_SUPPORT | gni 部件块 + `call_status_manager.cpp`、`call_data_base_helper.cpp` | 保留（DataShare/cust 出口 todo 或 Client 桩） |
| OHOS_BUILD_ENABLE_TELEPHONY_CUST | gni 部件块 + `call_manager_service.cpp` | 保留（`telephony_cust_wrapper.cpp` 改 TelephonyCustClient 桩，不再 dlopen） |
| CONFIG_FACTORY_VERSION | 零引用（v6.0 快照中该宏无 #ifdef 场点） | 保留宏约定不迁移任何分支：AGENTS 要求两分支都支持，基线实测无分支，按实际代码判定，登入 Open Questions 复核 |

**被裁剪功能的代码层处理方式汇总**（删除源文件清单，`callmanager.gni` 的 `call_manager_sources` 同步去项）：

| 基线模块 | 删除的源文件（均在 `telephony_call_manager_mini/` 下） |
| --- | --- |
| services/antifraud（防诈） | `anonymize_adapter.cpp`、`antifraud_adapter.cpp`、`antifraud_cloud_service.cpp`、`antifraud_hsdr_helper.cpp`、`antifraud_service.cpp` |
| services/bluetooth（蓝牙通话） | `bluetooth_call_manager.cpp`、`bluetooth_call_policy.cpp`、`bluetooth_call_service.cpp`、`bluetooth_call_stub.cpp`、`bluetooth_connection.cpp` |
| services/call（含会议/OTT/卫星/视频/蓝牙对象、超级隐私、有线耳机） | `bluetooth_call.cpp`、`bluetooth_call_state.cpp`、`call_superprivacy_control_manager.cpp`、`call_wired_headset.cpp`、`conference_base.cpp`、`cs_conference.cpp`、`ims_conference.cpp`、`ott_call.cpp`、`ott_call_connection.cpp`、`ott_conference.cpp`、`satellite_call.cpp`、`video_call_state.cpp`、`net_call_base.cpp`（仅被 OTTCall/VideoCallState 派生，随之成死代码） |
| services/call/call_state_observer | `proximity_sensor.cpp`、`status_bar.cpp`、`wired_headset.cpp` |
| services/call_earthquake_alarm（地震预警） | `call_earthquake_alarm_locator.cpp`、`call_earthquake_alarm_subscriber.cpp` |
| services/call_voice_assistant（语音播报） | `call_voice_assistant_manager.cpp` |
| services/display（折叠屏） | `fold_status_manager.cpp` |
| services/distributed_call（分布式） | `distributed_call_manager.cpp`、`distributed_call_proxy.cpp`、`distributed_communication/` 6 个 cpp、`transmission/` 5 个 cpp |
| services/interoperable_call（互信互联） | `interoperable_client_manager.cpp`、`interoperable_communication_manager.cpp`、`interoperable_data_controller.cpp`、`interoperable_device_observer.cpp`、`interoperable_server_manager.cpp`（连同 gni watch 块的 `interoperable_settings_handler.cpp`） |
| services/satellite_call（卫星） | `satellite_call_control.cpp` |
| services/telephony_interaction | `bluetooth_call_connection.cpp` |
| services/video（视频通话） | `video_control_manager.cpp` |
| services/call_manager_service（IPC/sa） | `call_manager_service_stub.cpp` |
| utils | `edm_call_policy.cpp`、`incoming_flash_reminder.cpp`、`motion_recognition.cpp`、`screen_sensor_plugin.cpp` |
| frameworks/native | `bluetooth_call_client.cpp`、`bluetooth_call_proxy.cpp`、`nearlink_call_client.cpp`、`super_privacy_manager_client.cpp`、`call_manager_proxy.cpp`、`call_manager_service_proxy.cpp`、`call_status_callback_proxy.cpp`、`cellular_call_proxy.cpp`、`cellular_call_callback_death_recipient.cpp`、`call_manager_death_recipient.cpp`、`call_ability_callback_proxy.cpp`、`call_ability_callback_death_recipient.cpp`（对应头文件随删；js/ets/cj 目录不迁移） |

其余不在删除清单的（含 spam_call/number_identity_proxy 全部文件、antifraud 之外的服务文件）逻辑保留，外部出口按 D6 处置。**宏清理**：删除的 gni `global_parts_info` 部件块——`communication_bluetooth`、`sensors_miscdevice`、`hiviewdfx_hicollie`、`msdp_motion`、`theme_screenlock_mgr`、`multimedia_camera_framework`（依赖保留为空或删除整块）；保留的部件块——`telephony_sms_mms`、`telephony_cellular_call`、`powermgr_power_manager`、`telephony_cellular_data`、`telephony_telephony_enhanced`、`telephony_telephony_cust`；删除 `target_platform=="watch"` 特设块。**支持宏去守卫**：无（支持宏保持原样，见上表）。

### D8 并发模型（LiteOS 对应原语）

- **决策**：`report_call_info_handler.cpp` 的 `report_call_info_queue_`（ffrt 串行队列）→ 打桩 EventHandler 的串行任务队列（保持"上行单队列串行"语义，桩内同步逐条执行，不新增线程）；`call_request_handler.cpp`、`call_records_handler.cpp` 的 `ffrt::submit` → 桩 EventHandler 提交；`call_status_callback.cpp` 的 1s/3s `ffrt` 延迟 → 桩 EventHandler 定时。全部锁（`std::mutex`/`ffrt::mutex`/`shared_mutex`）删除，不加替代锁。若未来新增线程，需先与用户对齐（AGENTS）。
- **理由**：AGENTS「ffrt 改为打桩的 EventHandler」「单进程多线程环境目前只有一个线程，因此不需要加锁」；config.yaml「上行状态处理单队列串行」语义保持。
- **落点**：`stub/eventhandler_stub`（新代码）；上述 4 个 cpp 的提交点改造；仓内锁声明与 `shared_ptr` 守卫调整随全仓替换（D5）。
- **替代方案**：用真实 LiteOS 消息队列 — 依赖内核通路接口，超出本设计，桩保持可在 PC 上运行。

### D9 零代码锚点的裁剪项与保留判定

- **决策**：AGENTS 裁剪清单中 `MAKE_CALL_WITH_TOKEN`、`TELEPHONY_EXIT_STR`（STR 模式）在 v6.0 基线中 rg 零命中（唯一近似名是 IPC 枚举 `INTERFACE_MAKE_CALL`，属另一事物），按「宏定义按实际代码实现来判断」处理为**无迁移动作**（无代码可删）。`IsNewCallAllowed`（`CallControlManager` → `CallObjectManager::IsNewCallAllowedCreate`）实测与"新通话/CeliaCall"无关（判定的是非 VoIP 通话处于 CREATE/CONNECTING/DIALING/RINGING 态时禁止再建新通话），**保留**；新通话族仅移除 `dealCeliaCallEvent`/`HandleCeliaAutoAnswerCall`/`HandleCeliaCall`/`IS_CELIA_CALL` 链。佩戴状态观察链（`WearStatusObserver`，`IsNotWearOnWrist`，settings 键 `wear_status`）是手表在位佩戴判定，AGENTS 未列入裁剪，**保留**，settings 查询出口按 database todo 桩化。

- **决策**：以下基线"名义与实现不符"处全部照抄不改（AGENTS「代码逻辑与 HMOS 保持一致，除非 HMOS 本身实现存在问题」，这些点单独难以认定为缺陷且不影响主线），登记于 Open Questions：`CallObjectManager::IsTwoCallESIMCall` 恒 false 的判定宽度、`OttConference` 状态字段错置（该文件已删除，自然消解）、`CallRequestEventHandlerHelper::SetDialingCallProcessing` 的返回值反判、`CallRecordsHandlerService::RemoveMissedIncomingCallNotification` 的 true 判失败、`CallManagerService::GetBindTime` 每次刷新、`CallSettingManager::SetCallPreferenceMode` 判空豁免、spam_call_adapter 全局 `connection_` 覆盖隐患（单线程下无并发冲突）。
- **理由**：行为保持默认原则；修正属行为变更，AGENTS 未授权。
- **落点**：逐点在 Open Questions 汇总，供人工复核定夺是否在实施时修正。

### D10 受影响构建面清单

- **决策**：构建裁剪按下表（`build-config` delta 的载体）。
- **理由**：config.yaml「构建真源是 callmanager.gni；feature 开关 declare_args 只在根 BUILD.gn；bundle.json features 与之成对」。
- **落点**：

| 构建面 | 受影响条目 |
| --- | --- |
| `callmanager.gni` | `call_manager_sources`：删除上表全部源文件条目；`call_manager_include_dirs`：删除 antifraud/bluetooth/call_earthquake_alarm/call_voice_assistant/display/distributed_call/interoperable_call/satellite_call/video 目录条目；`call_manager_external_deps`：移除 ability_runtime 系大部分、audio_framework 系、common_event_service、data_share、device_manager、dsoftbus、hicollie（部件块删除后）、input、ipc:ipc_single、location、player_framework、safwk、samgr_proxy、access_token、privacy、screenlock、camera_framework、bluetooth 等（保留 CoreService 系头依赖经桩）；宏部件块：见 D7；`target_platform=="watch"` 块：删除 |
| 根 `BUILD.gn` | `declare_args` 移除 `call_manager_feature_hfp_async_enable`、保留 `call_manager_feature_not_support_multicall`；`ohos_shared_library` target 保持（PC 门禁经 test/ 兼容层使用）；cflags_cc 原样保留（含 `-fno-exceptions -fno-rtti`） |
| `bundle.json` | `component.features` 移除 `call_manager_feature_hfp_async_enable`，保留 `call_manager_feature_not_support_multicall`；inner_kits/syscap 面按 mini 实际保留 |
| `sa_profile/` | 整目录不迁移（无 SystemAbility） |
| `frameworks/native/BUILD.gn` | `tel_call_manager_api` target 的 sources 缩减（仅保留直调面文件）；versionscript 不迁移（无导出面），登入 Open Questions 复核 |
| `test`（仓内单测/fuzz 组织，非 PC 门禁） | unittest/fuzztest 中被移除模块的 target 删除（earthquake、voice assistant、distributed_communication、conference/bluetooth 系）；保留通用 zero/special 系并随裁剪同步 |

### D11 目标仓与测试面

- **决策**：`test/base/telephony/call_manager` 软链改指 `telephony_call_manager_mini/`；兼容层强制注入宏集去掉 `ABILITY_BLUETOOTH_SUPPORT=0x1`（手表宏集），must-pass 套件中依赖被删模块的三套件（`tel_call_voice_assistant_test`、`distributed_communication_test`、`tel_call_earthquake_alarm_test`）移出 must-pass，其余保留并验证通过。
- **理由**：`pc-test-harness` 基线规格的验收体系不变；AGENTS 桩约束。
- **落点**：`pc-test-harness` delta；`test/` 框架自身文件按 setup 惯例仅做清单与软链调整。

## Risks / Trade-offs

- [裁剪面大，误删保留功能] → delta 按能力逐条 REMOVED 并做符号涟漪清扫（每个被删符号在 delta/design 中只允许以"不迁移"语义出现）；tasks 设 must-pass 门禁收口。
- [桩导致行为漂移（外部接口恒成功/恒失败）] → 桩默认返回"服务不存在/权限不可用"类负值，与基线"服务未连接"分支语义一致；每个行为改动需求落 gtest 验证。
- [VoIP 保留但无对端，冲突链无法端到端验证] → 用例以桩注入对端事件驱动验证 cellular/VoIP 冲突处理逻辑本身。
- [单线程假设被桩事件破坏] → 桩不新增线程（D8）；如引入调度线程需与用户对齐。
- [权限校验移除属安全面弱化] → 按 AGENTS 属目标平台约束（单用户手表），已标"需人工复核"。

## Migration Plan

1. 整拷基线生成 `telephony_call_manager_mini/`，先落 stub/ 桩目录与基础替换（sptr/ffrt/锁），保证未裁剪整体可编译（此时仍含全部功能文件）。
2. 按能力组分批删除 D7 清单文件并同步 gni/头文件，保持每批 must-pass PASS。
3. 逐能力做外部出口桩化（todo 标签、Client 单例、直调改造）并补 gtest。
4. 收尾更新 bundle.json/BUILD.gn/test 面板/pc-test-harness delta，跑 `openspec validate --all --strict` 与 must-pass。

回滚：mini 为独立新目录，基线仓不受影响，删除目录即回滚。

## Open Questions

1. `IsTwoCallESIMCall`（一号双终端判定）恒 false 疑似笔误（`!= TYPE_CS || != TYPE_IMS` 恒真）。liteOS 上蓝牙通话与 eSIM 均移除、该判定链删除，是否还需在删除外保留"等价修正实现"供未来手表双终端场景恢复，待人工定夺。
2. `CallRequestEventHandlerHelper::SetDialingCallProcessing` 返回值反判、`CallRecordsHandlerService::RemoveMissedIncomingCallNotification` true 判失败、`CallManagerService::GetBindTime` 时间戳刷新、`CallSettingManager::SetCallPreferenceMode` 缺判空：均按 HMOS 现状照抄。是否在移植时顺手修复？默认不修。
3. `CONFIG_FACTORY_VERSION`：AGENTS 要求"两分支都要支持"，但 v6.0 快照全仓无该宏的 #ifdef 场点。按实际代码判定为无迁移动作；若产线后续引入分支需另行 change。
4.EventHandler 桩的调度线程策略：桩内同步执行可满足单线程；若产品要求独立事件线程，需先与用户对齐（AGENTS：新增线程先对齐）。
5. `frameworks/native` 的 versionscript（导出符号面）在 mini 无共享库导出场景下不再需要，是否保留文件以对齐目录结构？默认不迁移。
6. spam_call 保留后的 dlopen 拆除：`spam_call_proxy.cpp`/`spam_call_stub.cpp`/`spam_call_connection.cpp` 的 IPC/Ability 连接在桩面不可达，仅保留码表与判定。这三文件是删除还是保留空壳，按"逻辑保留"原则默认保留可编译的最小形（登入复核）。