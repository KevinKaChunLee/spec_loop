# Design

## Context

基线 `telephony_call_manager/`（OpenHarmony-v6.0-Release，commit `f99813be`）是 SA 4005（进程 foundation）形态的 C++17 部件：构建真源是 `callmanager.gni`（sources / include_dirs / external_deps / 12 个 `global_parts_info` 能力宏块）加根 `BUILD.gn` 的两个 `declare_args` feature；并发用 ffrt 队列 + 非递归锁；对象模型是 `sptr<CallBase>` + `CallObjectManager` 静态表。目标平台为 LiteOS + MCU 手表：单进程单线程、无 SystemAbility/IPC、无 ffrt/DataShare/公共事件/通知/音频框架。约束文件为本仓根 `AGENTS.md`（路径映射：`./HMOS/telephony_call_manager/` → 本仓 `telephony_call_manager/`，`./liteOS/call_manager/` → 本仓待建的 `telephony_call_manager_mini/`）。动机见 proposal.md「Why」，逐能力行为变化见本 change `specs/` 的 delta。

## Goals / Non-Goals

**Goals:**
- 产出 `telephony_call_manager_mini/`：目录结构与文件命名与基线一致，功能做裁剪而非重写，保留代码的行级行为与基线一致。
- 每个外部依赖都有确定处置（打桩 / todo 占位 / 替代），且处置可被 PC 门禁验证。
- `test/` PC 门禁在裁剪后副本上重新收敛为全绿（`MUST-PASS GATE: PASS`）。

**Non-Goals:**
- 不为 liteOS 实现任何真实后端（音频、数据库、广播、通知、功耗锁、骚扰查询、号码识别、RTT 通路）。
- 不引入新线程、不加新锁；不改 IPC 枚举值（只退役其使用）。
- 不做 DSDA/双卡/多用户业务；不做 VoIP/畅连（后续 change）。

## 决策索引

- **D1 拷贝先行、基线只读**：mini 由基线整棵拷贝而来，所有裁剪只发生在 mini。
- **D2 移除能力 = 删源文件**：10 个能力整目录/整文件删除，见删除清单表。
- **D3 进程内直连架构**：无 SystemAbility、无 IPC、无权限校验，`CallManagerClient` 直调 `CallManagerService`。
- **D4 指针与数据结构替换**：`sptr` → `std::shared_ptr`/`std::unique_ptr`；`AppExecFwk::PacMap` → 结构体。
- **D5 异步与并发原语**：ffrt（queue/submit/mutex）→ `stub/` 打桩 EventHandler；`std::mutex` 原样保留。
- **D6 外部模块客户端单例打桩**：cellular_call / core_service / cellular_data / sms_mms / TelephonyCust 走 `XxxClient::GetInstance()` 桩。
- **D7 暂不调用依赖 todo 占位**：audio / database / broadcast / powerLock / notification / spamCall / numberIdentity / rtt 调用点写 todo，逻辑保留。
- **D8 UI 类外部依赖打桩**：CallConnectAbility、CallDialog 及 ability 连接类经桩实现。
- **D9 特性宏处置**：不支持宏退役（按未定义清理）、支持宏去守卫（按已定义生效）、基线未出现的宏无迁移点，见宏表。
- **D10 通话类型收敛**：仅保留 CS/IMS；会议/视频/VoIP/OTT/卫星/蓝牙对象与入口删除，类型枚举与错误码保留。
- **D11 单卡与单帐号**：`GetDsdsMode` 恒 0（经 CoreServiceClient 桩）、slotId 字段保留、os_account 精简为单主帐号。
- **D12 维测日志化**：HiSysEvent/HITRACE/hidump 改日志，隐私字段约束不变。
- **D13 构建面重排**：`callmanager.gni` 与 `bundle.json` 按裁剪结果重写。
- **D14 测试工程接线**：软链重指 mini、must-pass 收敛、mini 内 unittest 同步裁剪。
- **D15 需人工复核项**：ECC、权限校验、IPC 枚举、跨部件结构体四处改动。

## Decisions

### D1 拷贝先行、基线只读
- 决策：`telephony_call_manager_mini/` 由 `telephony_call_manager/` 整棵拷贝（含 `BUILD.gn`、`callmanager.gni`、`bundle.json`、`test/unittest/`，不含 `test/fuzztest/`）后裁剪；基线目录一字不改。
- 理由：AGENTS.md「代码逻辑与HMOS实现保持一致」「目录结构和文件命名尽量与HMOS保持一致」；整棵拷贝保证遗漏最小，diff 即裁剪面。
- 落点：新增目录 `telephony_call_manager_mini/`；`test/base/telephony/call_manager` 符号链接改指该目录（见 D14）。

### D2 移除能力 = 删源文件
- 决策：proposal 中标「移除」的 10 个能力直接删除源文件，不做宏开关式保留；对应的 include 目录同步删除。
- 理由：AGENTS.md「相关代码无需迁移」；保留死代码会放大 mini 的 ROM 与维护面，且这些模块的外部依赖（dsoftbus、location、camera、bluetooth）在 liteOS 上不存在。
- 落点（删除清单，均相对 `telephony_call_manager_mini/`，名称已对照基线核实）：

| 类别 | 删除项 |
|---|---|
| 整目录 | `services/antifraud/`、`services/bluetooth/`、`services/call_earthquake_alarm/`、`services/call_voice_assistant/`、`services/display/`、`services/distributed_call/`、`services/interoperable_call/`、`services/satellite_call/`、`services/video/`、`frameworks/js/`、`frameworks/ets/`、`frameworks/cj/`、`interfaces/kits/`、`sa_profile/`、`test/fuzztest/` |
| services/call/src | `bluetooth_call.cpp`、`bluetooth_call_state.cpp`、`video_call_state.cpp`、`satellite_call.cpp`、`ott_call.cpp`、`ott_call_connection.cpp`、`voip_call.cpp`、`conference_base.cpp`、`cs_conference.cpp`、`ims_conference.cpp`、`ott_conference.cpp`、`call_wired_headset.cpp`、`call_superprivacy_control_manager.cpp` |
| services/call/call_state_observer/src | `proximity_sensor.cpp`、`status_bar.cpp`、`wired_headset.cpp` |
| services/telephony_interaction/src | `voip_call_connection.cpp`、`bluetooth_call_connection.cpp`、`call_status_callback_stub.cpp` |
| services/call_report/src | `app_state_observer.cpp`、`call_ability_callback_death_recipient.cpp`、`call_ability_callback_proxy.cpp` |
| services/call_manager_service/src | `call_manager_service_stub.cpp` |
| frameworks/native/src | `call_manager_proxy.cpp`、`call_manager_service_proxy.cpp`、`call_status_callback_proxy.cpp`、`cellular_call_proxy.cpp`、`cellular_call_callback_death_recipient.cpp`、`call_manager_death_recipient.cpp`、`call_ability_callback_stub.cpp`、`bluetooth_call_client.cpp`、`bluetooth_call_proxy.cpp`、`voip_call_manager_proxy.cpp`、`nearlink_call_client.cpp`、`super_privacy_manager_client.cpp` |
| services/audio/src/audio_state | `bluetooth_device_state.cpp`、`wired_headset_device_state.cpp`、`ott_call_state.cpp` |
| utils/src | `edm_call_policy.cpp`、`incoming_flash_reminder.cpp`、`motion_recognition.cpp`、`screen_sensor_plugin.cpp` |

保留但桩化的 UI 辅助：`utils/src/call_dialog.cpp`、`call_ability_connection.cpp`、`call_setting_ability_connection.cpp`（`CallDialog` 被 `call_policy.cpp`、`call_request_process.cpp`、`call_control_manager.cpp`、`audio_control_manager.cpp` 引用，不能删，见 D8）。`utils/src/number_identity_data_base_helper.cpp` 保留（number-identity-proxy 能力，DataShare 调用点 todo，见 D7）。

### D3 进程内直连架构
- 决策：`CallManagerService` 不再继承 `SystemAbility`，退化为 `DelayedSingleton` 普通类；`CallManagerClient::Init` 直接取进程内服务实例；删除全部 stub/proxy/death-recipient；服务侧不调用 `TelephonyPermission::CheckCallerIsSystemApp`/`CheckPermission`（免校验直通）；`CallManagerService::Init` 保留原签名（systemAbilityId 参数忽略，最小改动）。
- 理由：AGENTS.md「liteOS中callmanager不继承SystemAbility也不实现IPC调用，直接从CallManagerClient调用CallManagerService的接口」「权限校验接口暂不调用」。
- 落点：`services/call_manager_service/src/call_manager_service.cpp`（去 `MakeAndRegisterAbility`/`OnStart`/`OnAddSystemAbility`/Publish，Init 链保留：`CallControlManager`、`ReportCallInfoHandler`、`CellularCallConnection`、`CallRecordsManager` 等）；`frameworks/native/src/call_manager_client.cpp`；删除件见 D2 表。**需人工复核**（权限校验、IPC 枚举见 D15）。

### D4 指针与数据结构替换
- 决策：服务内部 `sptr<T>` 一律换 `std::shared_ptr<T>`（独占场景 `std::unique_ptr`）；`AppExecFwk::PacMap` 换为本 change 新增的等价结构体（dial/应答 extras 等），字段名与 PacMap 键名保持一致，便于后续对照。
- 理由：AGENTS.md「sptr在liteOS中使用C++的智能指针替代」「PacMap等无法使用的数据结构建议使用结构体替换」。
- 落点：`services/call/include/call_base.h`、`call_object_manager.h`、`call_control_manager.h`、`carrier_call.h`、`ims_call.h`、`cs_call.h`、`services/call_manager_service/include/call_manager_service.h`、`services/call_report/include/call_ability_report_proxy.h`、`utils/include/call_number_utils.h` 等保留文件中的 `sptr`/`PacMap` 出现点；`DelayedSingleton`/`DelayedRefSingleton` 模板保留（c_utils 桩提供，见 D6/D9）。**需人工复核**（跨部件结构体对齐，见 D15）。

### D5 异步与并发原语
- 决策：ffrt 全部经 `stub/` 打桩的 EventHandler 承接——`ffrt::submit`/`ffrt::submit_h`（含 `task_attr().delay` 延时）→ EventHandler 任务提交（单线程顺序派发）；ffrt `queue`（`report_call_info_handler.cpp` 的 `report_call_info_queue`、`audio_scene_processor.cpp` 的 `reportAudioStateChangeQueue`）→ EventHandler 专有队列桩（保序串行）；`ffrt::mutex` → 空实现桩（保持 `std::lock_guard` 代码形态不动）；`std::mutex`/`std::shared_mutex` 原样保留（单线程下无争用，行为一致）。
- 理由：AGENTS.md「liteOS不支持HMOS中的ffrt，异步任务需要使用EventHandler替代」「目前只有一个线程，因此不需要加锁」；保留锁形态是为了最小 diff 与未来加线程时的可回退性。
- 落点：`services/call/src/call_request_handler.cpp`（`ffrt::submit` × N）、`services/call/src/call_request_event_handler_helper.cpp`（`PostTask` 3000ms 延时任务 `RestoreDialingFlag`）、`services/telephony_interaction/src/report_call_info_handler.cpp`（`report_call_info_queue` 单队列串行语义不变）、`services/audio/src/audio_scene_processor.cpp`、`audio_proxy.cpp`、`audio_control_manager.cpp`、`ring.cpp`（`ffrt::mutex`）、`services/spam_call/src/time_wait_helper.cpp`、`spam_call_adapter.cpp`、`services/number_identity_proxy/src/number_identity_service.cpp`、`services/hisysevent/src/call_manager_hisysevent.cpp` 等保留文件中的 ffrt 出现点。

### D6 外部模块客户端单例打桩
- 决策：与 cellular_call / core_service / cellular_data / sms_mms / TelephonyCust 的 IPC 一律改为 `XxxClient::GetInstance().Xxx()`（桩实现在 `telephony_call_manager_mini/stub/`，方法名与基线 `ICellularCall`/`ICoreService` 等接口一致）；基线里已存在的 `DelayedRefSingleton<CoreServiceClient>::GetInstance()` 调用形态保留，仅换桩实现。上行回调由 cellular_call 桩侧直接进程内调用 `CallStatusCallback` 的同名方法（替代 `call_status_callback_stub.cpp` 的 IPC 入口）。
- 理由：AGENTS.md「与cellular_call模块进行IPC通信时，使用CellularCallClient::GetInstance().Xxx()的形式替代」等五条。
- 落点：`services/telephony_interaction/src/cellular_call_connection.cpp`（`Dial/Answer/Reject/HangUp/HoldCall/UnHoldCall/SwitchCall/IsMmiCode/IsEmergencyPhoneNumber` 等转发点）、`core_service_connection.cpp`（FDN 相关 `QueryIccDiallingNumbers`、`GetLockState` 等，以基线实际为准）、`services/call_setting/src/call_setting_manager.cpp`（补充业务转发）、`services/call/src/call_request_process.cpp` 与 `call_status_manager.cpp`（`GetDsdsMode` 等 CoreServiceClient 调用）、`services/call/call_state_observer/src/reject_call_sms.cpp`（`SmsClient`）、`services/call_manager_service/src/telephony_cust_wrapper.cpp`（dlopen → `TelephonyCustClient` 桩）。

### D7 暂不调用依赖 todo 占位
- 决策：下表依赖的调用点统一写 `// todo!!! [标签] ref to <文件> <函数>` 占位（本 change 引入的标签约定），逻辑分支保留并按"未就绪/默认值"走；不删除所在文件。

| 标签 | 依赖（基线调用形态） | 处置 | 主要落点 |
|---|---|---|---|
| `[audio]` | AudioSystem/AudioRoutingManager、`player_framework` 系统铃声（经 `audio_proxy.cpp`） | 不调用，返回失败/默认值，状态机字段照常变化 | `services/audio/src/audio_proxy.cpp`、`ring.cpp`、`sound.cpp`、`tone.cpp`、`audio_device_manager.cpp` |
| `[database]` | DataShare（通话记录、拦截名单、增强联系人、设置库、号码识别库） | 不调用，查询返回未命中/失败 | `services/call/call_state_observer/src/call_data_base_helper.cpp`、`call_records_handler.cpp`、`call_records_manager.cpp`、`utils/src/settings_datashare_helper.cpp`、`number_identity_data_base_helper.cpp` |
| `[broadcast]` | `EventFwk::CommonEventManager` 订阅/发布 | 不订阅不发布 | `services/call/src/call_broadcast_subscriber.cpp`、`services/call/call_state_observer/src/missed_call_notification.cpp`、`call_records_manager.cpp`（DATA_SHARE_READY 等订阅） |
| `[powerLock]` | RunningLock / 亮屏（ABILITY_POWER_SUPPORT 接口） | 不调用 | `services/call/call_state_observer/src/incoming_call_wake_up.cpp` |
| `[notification]` | NotificationHelper（来电/未接通知） | 不调用 | `services/call/call_state_observer/src/incoming_call_notification.cpp`、`missed_call_notification.cpp` |
| `[spamCall]` | `com.spamshield` 扩展连接（SpamShieldServiceExtAbility，不用 dlopen） | 不连接不查询，等待超时放行 | `services/spam_call/src/spam_call_connection.cpp`、`spam_call_adapter.cpp` |
| `[numberIdentity]` | 号码识别/黄页 DataShare 查询 | 不调用，回填空 | `services/number_identity_proxy/src/number_identity_service.cpp` |
| `[rtt]` | RTT 文件节点通路 | 不调用（接口保留，经 cellular_call 桩转发） | `services/call/src/call_request_handler.cpp` 的 `StartRtt`/`StopRtt` 相关链路 |

- 理由：AGENTS.md「代码按功能实现，不能因为无外部接口而丢弃功能：暂不可用的外部接口只换掉调用（todo 占位），逻辑保留」。
- 系统参数（`GetParameter`/`WatchParameter`，出现在 `call_number_utils.cpp`、`call_control_manager.cpp`、`audio_scene_processor.cpp`、`call_records_manager.cpp` 等）：按 AGENTS「系统参数（parameter）相关接口通过打桩实现」，桩返回默认值（超级隐私相关 `WatchParameter` 调用随 D2 删除）。

### D8 UI 类外部依赖打桩
- 决策：`CallConnectAbility`（`com.ohos.callui` 连接）、`CallDialog`（对话框）及其 ability 连接类保留代码结构，`AbilityManagerClient::ConnectAbility`、`AlertDialog` 等 AAFwk 调用经 `stub/` 桩实现（连接回调桩实现，`isConnecting_`/`isDisconnecting_`/`WaitForConnectResult` 竞态保护逻辑不变）。
- 理由：AGENTS.md「拉起通话界面CallConnectAbility，对应外部依赖接口通过打桩实现」。
- 落点：`services/call/src/call_connect_ability.cpp`、`call_ability_connect_callback.cpp`、`utils/src/call_dialog.cpp`、`call_ability_connection.cpp`、`call_setting_ability_connection.cpp`。

### D9 特性宏处置
- 决策：分三类。**不支持宏**：从 `callmanager.gni`/`BUILD.gn` 移除定义块（或该 target_platform 分支），源码中 `#ifdef` 按未定义清理（即删除该分支代码）；**支持宏**：在 mini 的 `callmanager.gni` 以固定 `defines` 直接生效（去 `global_parts_info` 守卫），并删除源码中对应 `#ifdef/#else` 的关闭分支；**基线未出现的宏**：无迁移点，记录于 Open Questions。

| 宏 | 类别 | 处置与理由 | 落点 |
|---|---|---|---|
| `ABILITY_BLUETOOTH_SUPPORT` | 不支持 | gni `global_parts_info.communication_bluetooth` 块删除；引用文件已随 D2 删除 | `callmanager.gni` |
| `SUPPORT_VIBRATOR`、`HICOLLIE_ENABLE`、`ABILITY_SCREENLOCKMGR_SUPPORT` | 不支持 | gni 块删除，无源码引用 | `callmanager.gni` |
| `SUPPORT_MUTE_BY_DATABASE` | 不支持 | gni `target_platform == "watch"` 块删除；`call_manager_service.cpp`、`call_records_manager.cpp` 中该宏分支退役 | `callmanager.gni`、两处源码 |
| `HFP_ASYNC_ENABLE` | 不支持 | `BUILD.gn` 的 `declare_args` 项与 `call_control_manager.cpp` 的 HFP 订阅宏分支删除（蓝牙不支持） | `BUILD.gn`、`call_control_manager.cpp` |
| `ABILITY_NOTIFICATION_SUPPORT`、`ABILITY_DISPLAY_SUPPORT`、`ABILITY_STATUS_BAR_CONTROL_SUPPORT`、`ABILITY_MEDIA_SUPPORT`、`ABILITY_CONFIG_SUPPORT`、`AUDIO_SUPPORT`、`ABILITY_AUDIO_SUPPORT` | 不支持 | 基线中仅源码 `#ifdef` 引用（gni 未定义，产品侧注入）；按未定义清理分支。`ABILITY_CONFIG_SUPPORT` 在保留文件 `call_policy.cpp`、`ims_call.cpp` 中有分支需退役 | `incoming_call_notification.cpp`、`status_bar.cpp`（已删）、`call_policy.cpp`、`ims_call.cpp`、`call_status_manager.cpp`、`tone.cpp` |
| `RECONNECT_MAX_TRY_COUNT` | 不支持 | `cellular_call_connection.cpp` 重连逻辑删除（直连架构无重连） | `cellular_call_connection.cpp` |
| `ABILITY_CAMERA_FRAMEWORK_SUPPORT` | 不支持 | 文件已删（`incoming_flash_reminder.cpp`） | — |
| `ABILITY_CAMERA_SUPPORT` | 不支持 | 文件已删（`video_control_manager.cpp`） | — |
| `OHOS_SUBSCRIBE_MOTION_ENABLE` | 不支持 | 文件已删（`motion_recognition.cpp`） | — |
| `ABILITY_CELLULAR_SUPPORT`、`ABILITY_SMS_SUPPORT`、`CELLULAR_DATA_SUPPORT`、`TELEPHONY_CUST_SUPPORT`、`OHOS_BUILD_ENABLE_TELEPHONY_CUST` | 支持 | gni 固定 defines 生效，去 `global_parts_info` 守卫；`cellular_data` 相关调用点保留经 `CellularDataClient` 桩 | `callmanager.gni` |
| `NOT_SUPPORT_MULTICALL` | 支持 | `BUILD.gn` feature `call_manager_feature_not_support_multicall` 固定为 true（去 `declare_args`），手表不支持多通话 | `BUILD.gn`、`call_status_manager.cpp`、`call_object_manager.cpp`、`call_control_manager.cpp` |
| `ABILITY_POWER_SUPPORT` | 支持（接口暂不调用） | 宏生效保留代码路径；RunningLock 调用点按 D7 `[powerLock]` todo | `incoming_call_wake_up.cpp` |
| `SUPPORT_RTT_CALL`、`CALL_MANAGER_SOS_NO_RINGBACK_TONE`、`CALL_MANAGER_WATCH_CALL_BLOCKING`、`CALL_MANAGER_THERMAL_PROTECTION`、`CONFIG_FACTORY_VERSION` | 基线未出现 | v6.0 call_manager 源码零引用（详见 Open Questions），无迁移点 | — |
| `CALL_MANAGER_CALL_TRANSFER`、`SUPPORT_HEARING_AID`、`SUPPORT_DSOFTBUS`、`CALL_MANAGER_AUTO_START_OPTIMIZE`、`OHOS_SUBSCRIBE_USER_STATUS_ENABLE` | 基线未出现 | 同上；`sa_profile/4005_auto_start_optimize.json` 已随 D2 删除；UT 呼叫转移（`SetCallTransferInfo` 等）不属此列，照常保留 | — |

- 理由：AGENTS.md「宏定义按实际代码实现来判断是否需要迁移，不能按宏的描述来判断」。

### D10 通话类型收敛
- 决策：`CreateNewCallByCallType` 仅构造 `CsCall`/`ImsCall`（经 `CarrierCall`）；会议类（`ConferenceBase`/`CsConference`/`ImsConference`）、视频（`VideoCallState`）、VoIP/OTT/卫星/蓝牙对象全部删除；`CombineConference`/`SeparateConference`/`KickOutFromConference`/`JoinConference` 及视频相关入口从服务面删除；`CallType`/`ImsCallMode`/`VideoStateType` 等枚举与 `CallManagerInterfaceCode` 等 IPC 枚举在接口头中保留且不动值（供 cellular_call 桩与后续恢复对照）；被移除 callType 的上报在 `report_call_info_handler` 判为不支持类型后丢弃。RTT（`StartRtt`/`StopRtt`）接口保留并经 cellular_call 桩转发，文件节点通路按 D7 `[rtt]` todo。
- 理由：AGENTS.md 功能范围（视频/会议/卫星/蓝牙/OTT 不支持、VoIP 暂不支持）；「IPC 枚举值即 ABI，只能末尾追加」（openspec/config.yaml 技术事实），故保留枚举不动值。**需人工复核**（IPC 枚举）。
- 落点：`services/call/src/call_object_manager.cpp`、`call_request_process.cpp`、`call_control_manager.cpp`、`services/call_manager_service/src/call_manager_service.cpp`、`interfaces/innerkits/call_manager_base.h`（枚举保留）、`services/telephony_interaction/src/report_call_info_handler.cpp`。

### D11 单卡与单帐号
- 决策：`GetDsdsMode` 的唯一数据源是 CoreServiceClient 桩，恒返回 0（`IsDsdsMode3`/`IsDsdsMode5` 恒 false，DSDA 分支按死代码删除）；slotId 参数与字段全量保留；`OsAccountManager` 相关多用户逻辑精简为固定主帐号（保留基线默认用户常量，如 `call_records_manager.cpp` 的 `ACTIVE_USER_ID`）。
- 理由：AGENTS.md「CallManagerUtils::GetDsdsMode()在liteOS上恒返回0，非0流程不需要迁移」「只支持单卡，实现时需预留双卡扩展能力」「只支持单主帐号能力」。注：AGENTS 所写 `CallManagerUtils::GetDsdsMode` 在 v6.0 基线已上移为 `DelayedRefSingleton<CoreServiceClient>::GetInstance().GetDsdsMode`（`call_request_process.cpp`/`call_status_manager.cpp`），处置语义不变（见 Open Questions）。
- 落点：`services/call/src/call_request_process.cpp`、`call_status_manager.cpp`（DSDA 分支删除）、`services/call/call_state_observer/src/call_records_manager.cpp`、`call_data_base_helper.cpp`、`services/call/src/call_broadcast_subscriber.cpp`（已删，随文件移除）、`services/audio/src/audio_control_manager.cpp`（os_account 精简）。

### D12 维测日志化
- 决策：`CallManagerHisysevent` 的全部 HiSysEvent 上报、`HITRACE` 打点、`CallManagerDumpHelper` 的 hidumper 输出统一改为日志打印（保留 `TELEPHONY_LOG_TAG`/`LOG_DOMAIN` 前缀与事件字段组织）；号码与联系人名不进日志的约束不变（用 callId/slotId/index 定位）；`native_call_manager_hisysevent.cpp` 同样日志化。
- 理由：AGENTS.md「HiSysEvent、HITRACE相关维测使用日志打印替代」；openspec/config.yaml 隐私红线。
- 落点：`services/hisysevent/src/call_manager_hisysevent.cpp`、`call_manager_dump_helper.cpp`、`frameworks/native/src/native_call_manager_hisysevent.cpp`。

### D13 构建面重排
- 决策：mini 的 `callmanager.gni` 重写——`call_manager_sources`/`call_manager_include_dirs` 删除 D2 清单条目；`call_manager_external_deps` 清空 OHOS 部件依赖（全部经 `stub/` 与进程内实现承接，仅保留对 `stub/` 的依赖与 cJSON/libphonenumber 的桩声明）；12 个 `global_parts_info` 块替换为固定 `call_manager_defines`（D9 支持宏集）；`target_platform == "watch"` 块删除。根 `BUILD.gn`：`declare_args` 仅保留（或直接固化）`call_manager_feature_not_support_multicall = true`，删除 `call_manager_feature_hfp_async_enable`；保留 `-fno-exceptions -fno-rtti` 等原仓编译约束。`bundle.json`：`component.features` 同步为 `["call_manager_feature_not_support_multicall"]`，`deps.components` 收缩为实际依赖。
- 理由：构建真源在 `callmanager.gni`（openspec/config.yaml 技术事实）；AGENTS.md「外部接口打桩函数统一放到liteOS代码的根目录的stub文件夹中」。
- 落点：`telephony_call_manager_mini/callmanager.gni`、`BUILD.gn`、`bundle.json`、新增 `telephony_call_manager_mini/stub/`（客户端单例桩、EventHandler 桩、ffrt 兼容桩、libphonenumber/parameter/cJSON/securec/c_utils/log/eventhandler 同名桩、CallConnectAbility/CallDialog UI 桩）。

### D14 测试工程接线
- 决策：`test/base/telephony/call_manager` 符号链接由 `telephony_call_manager/` 改指 `telephony_call_manager_mini/`（`//base/telephony/call_manager` 解析到裁剪产物）；`test/tests/BUILD.gn` 的 `mustpass_tests` 移除 `${_cm}/call_voice_assistant_test`、`${_cm}/distributed_communication_test`、`${_cm}/call_earthquake_alarm_test` 三项（模块已删，目录不拷贝）；`tel_call_manager_zero2_gtest`、`tel_call_manager_zero5_gtest`、`tel_call_manager_special2_test` 保留——其源文件随整棵拷贝进入 mini，但需同步删除/改写引用已移除类的用例（mini 的 `test/unittest/` 内进行，基线不动）；`test/build/ohos.gni` 的统一宏注入由 `ABILITY_BLUETOOTH_SUPPORT=0x1`+`ABILITY_CELLULAR_SUPPORT=0x1` 改为 D9 手表宏集。门禁标准不变（全部 rc=0 且 0 FAILED → `MUST-PASS GATE: PASS`）。
- 理由：openspec/config.yaml「test 的 //base/telephony/call_manager 应指向 telephony_call_manager_mini/（移植产物），门禁验证裁剪后的代码」；被删模块的套件无法编译。
- 落点：`test/base/telephony/call_manager`（symlink）、`test/tests/BUILD.gn`、`test/build/ohos.gni`、`telephony_call_manager_mini/test/unittest/`（裁剪）。

### D15 需人工复核项
- `EccDialPolicy`（`call_request_process.cpp`）：删除卫星通话清理分支，`HasNormalCall` 的 ECC 旁路原样保留——紧急呼叫放行语义需人工复核。
- 权限校验（D3）：全部外部接口免校验直通。
- IPC 枚举（D10）：`CallManagerInterfaceCode` 等枚举保留不动值但退役使用。
- 跨部件结构体（D4）：`PacMap` → 结构体、`CallAttributeInfo` 等字段随 VoIP/会议收缩，需与 cellular_call 桩数据面对齐。

## Risks / Trade-offs

- [删除文件后残留 include/前向引用导致编译失败] → 每完成一组删除即同步 `callmanager.gni`（tasks 的同步子任务），并跑 `build.sh build` 增量验证。
- [zero/special 套件大量用例引用已删类，裁剪工作量不可预估] → 套件裁剪按用例逐条删除/跳过，先保证可编译，再恢复可断言用例；不追求用例数与基线持平。
- [桩方法名与基线接口名不一致造成行为面偏差] → 桩方法名一律镜像基线 `ICellularCall`/`ICoreService`/`ISmsServiceInterface` 等真实接口名；`Xxx()` 占位写法仅出现在设计文本中。
- [单线程直连使异步时序用例（延时任务、队列串行）不可复现] → EventHandler 桩提供可注入的时钟/派发钩子，供 gtest 控制时序（`RestoreDialingFlag` 3000ms 等用例）。
- [todo 占位静默吞错（返回默认值）掩盖真实回归] → 占位点统一返回可识别的失败/默认值并在日志留痕；后续真实后端接入时可全局检索 `// todo!!!` 清点。
- [锁保留但 ffrt::mutex 桩为空，未来加线程时易漏] → 在 stub 头部注释标明"空实现，加线程前必须替换"，并在 Open Questions 记录加线程需先与用户对齐。

## Migration Plan

1. 整棵拷贝基线 → `telephony_call_manager_mini/`（不含 `test/fuzztest/`），软链暂不切换，门禁先验证"未裁剪副本仍全绿"。
2. 落地 `stub/`（客户端单例、EventHandler/ffrt 兼容、基础库同名桩、UI 桩）。
3. 按 D2 删除文件 + D13 同步 gni（分目录成组进行，每组后编译）。
4. 退役宏清理与支持宏去守卫（D9），直连化改造（D3/D4/D5/D10/D11/D12），todo 占位落点（D7/D8）。
5. 切换软链、调整 `test/tests/BUILD.gn` 与 `test/build/ohos.gni` 宏注入，裁剪 mini 的 `test/unittest/`，收敛 must-pass 至全绿。
6. 回滚策略：任一步失败可把软链指回 `telephony_call_manager/`（tag `baseline-unmodified`）恢复全绿门禁；mini 目录可整体删除重拷。

## Open Questions

1. **VoIP「暂不支持」的口径**：本 change 按"整通路删除（对象、连接、统计事件），仅保留类型枚举与错误码"处理，待 meetime 畅连适配的后续 change 再恢复；若期望保留 VoIP 代码仅屏蔽入口，需返工 `call-object-model`、`telephony-interaction`、`hisysevent-dfx` 的 delta。
2. **AGENTS 与 v6.0 基线的 `GetDsdsMode` 落点差异**：AGENTS 写 `CallManagerUtils::GetDsdsMode()`，但 v6.0 基线实际是 `DelayedRefSingleton<CoreServiceClient>::GetInstance().GetDsdsMode(dsdsMode)`（`call_request_process.cpp`、`call_status_manager.cpp`）；本设计在 CoreServiceClient 桩上恒返回 0，语义与 AGENTS 约束一致。
3. **基线未出现的支持宏**：`SUPPORT_RTT_CALL`、`CALL_MANAGER_SOS_NO_RINGBACK_TONE`、`CALL_MANAGER_WATCH_CALL_BLOCKING`、`CALL_MANAGER_THERMAL_PROTECTION`、`CONFIG_FACTORY_VERSION` 在 v6.0 call_manager 源码零引用（应为 cellular_call 等兄弟模块的宏）。按 AGENTS「宏按实际代码实现判断」，call_manager 侧无迁移点；`CONFIG_FACTORY_VERSION`「两分支都要支持」的约束在本仓无落点，若后续合并 cellular_call 移植需重新核对。
4. **`CallManagerService::Init` 签名**：直连架构下 `systemAbilityId` 参数失去语义，本设计保留原签名、参数忽略（最小改动）；若倾向改签名需同步 `call-manager-service` delta 的措辞。
5. **权限错误码残留**：`TELEPHONY_ERR_PERMISSION_ERR`、`TELEPHONY_ERR_ILLEGAL_USE_OF_SYSTEM_API` 的定义保留在 `call_manager_errors.h`（不动枚举面），仅不再有触发路径；客户端侧原映射分支（`CallManagerProxy::RegisterCallBack`）随 proxy 删除。
6. **`SatcommBroadcastSubscriber`（卫星广播订阅）**：AGENTS 未逐条点名，按「卫星通话不支持」归入删除（`call_broadcast_subscriber.cpp` 相关分支）。
7. **must-pass 套件内的已删类用例**：zero/special 套件需要逐条裁剪用例，工作量与保留比例在实施时才能确定；本设计只约束"套件可编译、保留用例全绿"。
8. **加线程前提**：本设计按单线程不加锁处理（`std::mutex` 保留、`ffrt::mutex` 桩空实现）；未来新增线程前必须先与用户对齐并替换锁实现。
