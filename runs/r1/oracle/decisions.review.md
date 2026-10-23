# 参考决策表（待人工确认）

由 extractor 从参考 spec 抽取。确认无误后运行 `loop.py freeze --run <run>` 冻结；
需要更正时直接编辑 `decisions.proposed.json` 的 value（可选值见 decision_vocab.json）。

两次抽取一致率：100.0%（89/89），有值项一致率 100.0%。下表「第二次」列只在两次不一致时出现值。

## 模块（代码解析：裁剪范围表 + ## Purpose 目录）

| 模块目录 | 处置 | 归属能力 |
|---|---|---|
| `build` | 修改 | build-and-feature-flags |
| `frameworks` | 修改 | client-frameworks |
| `services/antifraud` | 移除 | antifraud-call |
| `services/audio` | 修改 | audio-control-manager |
| `services/bluetooth` | 移除 | bluetooth-call |
| `services/call` | 修改 | call-object-model |
| `services/call/call_state_observer` | 修改 | call-state-observer |
| `services/call_earthquake_alarm` | 移除 | call-earthquake-alarm |
| `services/call_manager_service` | 修改 | call-manager-service |
| `services/call_report` | 修改 | call-report |
| `services/call_setting` | 修改 | call-setting |
| `services/call_voice_assistant` | 移除 | call-voice-assistant |
| `services/display` | 移除 | fold-display |
| `services/distributed_call` | 移除 | distributed-call |
| `services/hisysevent` | 修改 | hisysevent-observability |
| `services/interoperable_call` | 移除 | interoperable-call |
| `services/number_identity_proxy` | 修改 | number-identity |
| `services/satellite_call` | 移除 | satellite-call |
| `services/spam_call` | 修改 | spam-call |
| `services/telephony_interaction` | 修改 | telephony-interaction |
| `services/video` | 移除 | video-call |
| `utils` | 修改 | call-manager-utils |

## 功能范围（features）

| key | 值 | AGENTS.md | 第二次 | 证据 |
|---|---|---|---|---|
| video_call | **remove** | remove |  | \| `services/video/` \| video-call \| 视频通话不支持 \| |
| conference_call | **remove** | remove |  | **Reason**: AGENTS.md 功能范围：liteOS 不支持会议通话，会议对象族不迁移。 |
| satellite_call | **remove** | remove |  | \| `services/satellite_call/` \| satellite-call \| 卫星通话不支持 \| |
| distributed_call | **remove** | remove |  | \| `services/distributed_call/`（含 `transmission/`、`distributed_communication/`） \| distributed-call \| 分布式通话不支持（SUPPORT_ |
| bluetooth_call | **remove** | remove |  | \| `services/bluetooth/` \| bluetooth-call \| BLUETOOTH 类型通话不支持 \| |
| ott_call | **remove** | remove |  | **Reason**: AGENTS.md 功能范围：OTT 类型通话不支持。 |
| earthquake_alarm | **remove** | remove |  | \| `services/call_earthquake_alarm/` \| call-earthquake-alarm \| 地震预警不支持 \| |
| crs_video_ring | **remove** | remove |  | **Reason**: AGENTS.md 功能范围：视频彩振不支持；`SUPPORT_VIBRATOR` 为不支持宏。 |
| wired_headset | **remove** | remove |  | **Reason**: AGENTS.md 功能范围：有线耳机不支持（`ABILITY_MEDIA_SUPPORT` 为不支持宏）。 |
| voice_broadcast | **remove** | remove |  | \| `services/call_voice_assistant/` \| call-voice-assistant \| 语音播报不支持 \| |
| antifraud | **remove** | remove |  | \| `services/antifraud/`（含 `antiinclude/`） \| antifraud-call \| 防诈不支持；不用 dlopen \| |
| super_privacy | **remove** | remove |  | **Reason**: AGENTS.md 功能范围：超级隐私不支持。 |
| fold_screen | **remove** | remove |  | \| `services/display/` \| fold-display \| 折叠屏不支持 \| |
| edm_dial_block | **remove** | remove |  | **Reason**: AGENTS.md 功能范围：EDM 企业禁拨不支持。 |
| incoming_flash | **remove** | remove |  | **Reason**: AGENTS.md 功能范围：来电闪光（incoming flash）不支持（`ABILITY_CAMERA_FRAMEWORK_SUPPORT`/`ABILITY_SCREENLOCKMGR_SUPPORT` 为不 |
| status_bar_icon | **remove** | remove |  | **Reason**: AGENTS.md 功能范围：状态栏静音图标（StatusBar）不支持（`ABILITY_STATUS_BAR_CONTROL_SUPPORT` 为不支持宏）。 |
| proximity_sensor | **remove** | remove |  | **Reason**: AGENTS.md 功能范围：贴耳灭屏（proximity_sensor）不支持。 |
| nearlink | **remove** | remove |  | **Reason**: AGENTS.md 功能范围：BLUETOOTH 类型通话与星闪（NearLink）耳机设备连接不支持。 |
| make_call_with_token | **-** | remove |  |  |
| str_mode | **-** | remove |  |  |
| esim | **remove** | remove |  | \| call-status-manager \| 修改 \| 裁防诈/ESIM/DSDA/免打扰 DataShare/动作识别分支，`GetDsdsMode()` 恒 0，OOBE 判定改打桩系统参数 \| |
| new_call | **-** | remove |  |  |
| voip | **stub** | - |  | \| D15 \| VoIP 代码全保留，`VoipCallConnection` 桩化待畅连对接 \| |
| dsda | **remove** | remove |  | - **DSDA（BREAKING）**：DSDS 模式查询（`CoreServiceClient::GetInstance().GetDsdsMode()`，经桩实现）恒返回 0，非 0 分支不迁移；仅支持单卡但保留 `slotId` 传 |
| single_sim | **simplify** | simplify |  | - **DSDA（BREAKING）**：DSDS 模式查询（`CoreServiceClient::GetInstance().GetDsdsMode()`，经桩实现）恒返回 0，非 0 分支不迁移；仅支持单卡但保留 `slotId` 传 |
| single_account | **simplify** | simplify |  | `OsAccountManager` 多帐号逻辑精简为单主帐号（`IsOsAccountVerified` 恒已解锁形态、`MAIN_USER_SPACE(100)` 恒真）。 |
| bindings | **remove** | remove |  | **Reason**: AGENTS.md 功能范围：JS/ETS/仓颉绑定的外部接口不需要实现。 |

## 特性宏（macros）

| key | 值 | AGENTS.md | 第二次 | 证据 |
|---|---|---|---|---|
| CALL_MANAGER_CALL_TRANSFER | **remove** | remove |  | `SUPPORT_DSOFTBUS`/`SUPPORT_HEARING_AID`/`CALL_MANAGER_CALL_TRANSFER`/`ABILITY_POWER_SUPPORT`（gni 块）/`OHOS_SUBSCRIBE_USE |
| SUPPORT_HEARING_AID | **remove** | remove |  | `SUPPORT_DSOFTBUS`/`SUPPORT_HEARING_AID`/`CALL_MANAGER_CALL_TRANSFER`/`ABILITY_POWER_SUPPORT`（gni 块）/`OHOS_SUBSCRIBE_USE |
| SUPPORT_DSOFTBUS | **remove** | remove |  | `SUPPORT_DSOFTBUS`/`SUPPORT_HEARING_AID`/`CALL_MANAGER_CALL_TRANSFER`/`ABILITY_POWER_SUPPORT`（gni 块）/`OHOS_SUBSCRIBE_USE |
| CALL_MANAGER_AUTO_START_OPTIMIZE | **remove** | remove |  | \| `CALL_MANAGER_AUTO_START_OPTIMIZE` \| 删 \| `frameworks/native/BUILD.gn`(rk3568) + `call_manager_proxy.*`（proxy 随 D2 改 |
| HFP_ASYNC_ENABLE | **remove** | remove |  | \| `HFP_ASYNC_ENABLE` \| 删（含 declare_args/bundle.json feature） \| `BUILD.gn` + `call_control_manager.cpp` 守卫块 \| |
| ABILITY_BLUETOOTH_SUPPORT | **remove** | remove |  | \| `ABILITY_BLUETOOTH_SUPPORT` \| 删 \| `callmanager.gni` + bluetooth/distributed 组（随 D11） \| |
| ABILITY_CAMERA_FRAMEWORK_SUPPORT | **remove** | remove |  | \| `ABILITY_CAMERA_FRAMEWORK_SUPPORT` \| 删 \| `incoming_flash_reminder.cpp`（随来电闪光移除） \| |
| SUPPORT_MUTE_BY_DATABASE | **remove** | remove |  | \| `SUPPORT_MUTE_BY_DATABASE` \| 删（watch 块） \| `callmanager.gni` + `interoperable_settings_handler.cpp`（随 D11 删） \| |
| SUPPORT_VIBRATOR | **remove** | remove |  | \| `SUPPORT_VIBRATOR` \| 删 \| `callmanager.gni` + `audio_proxy.cpp` 振动块 \| |
| HICOLLIE_ENABLE | **remove** | remove |  | \| `HICOLLIE_ENABLE` \| 删 \| `callmanager.gni` + `call_manager_service_stub.cpp`（随 stub 删除） \| |
| OHOS_SUBSCRIBE_USER_STATUS_ENABLE | **remove** | remove |  | `SUPPORT_DSOFTBUS`/`SUPPORT_HEARING_AID`/`CALL_MANAGER_CALL_TRANSFER`/`ABILITY_POWER_SUPPORT`（gni 块）/`OHOS_SUBSCRIBE_USE |
| ABILITY_SCREENLOCKMGR_SUPPORT | **remove** | remove |  | \| `ABILITY_SCREENLOCKMGR_SUPPORT` \| 删 \| `callmanager.gni` + `incoming_flash_reminder.cpp` \| |
| ABILITY_NOTIFICATION_SUPPORT | **remove** | remove |  | \| `ABILITY_NOTIFICATION_SUPPORT` \| 删 \| `incoming_call_notification.cpp` \| |
| ABILITY_DISPLAY_SUPPORT | **remove** | remove |  | \| `ABILITY_DISPLAY_SUPPORT` \| 删 \| `incoming_call_notification.cpp`（随通知观察者移除） \| |
| ABILITY_STATUS_BAR_CONTROL_SUPPORT | **remove** | remove |  | \| `ABILITY_STATUS_BAR_CONTROL_SUPPORT` \| 删 \| `status_bar.cpp` \| |
| ABILITY_MEDIA_SUPPORT | **remove** | remove |  | \| `ABILITY_MEDIA_SUPPORT` \| 删 \| `wired_headset.cpp`/`call_control_manager.cpp` 耳机按键块 \| |
| ABILITY_CONFIG_SUPPORT | **remove** | remove |  | \| `ABILITY_CONFIG_SUPPORT`/`ABILIT_CONFIG_SUPPORT` \| 删守卫代码（carrier config 查询走默认值） \| `call_policy/cs_conference*/ims_c |
| RECONNECT_MAX_TRY_COUNT | **remove** | remove |  | \| `RECONNECT_MAX_TRY_COUNT` \| 删（无重连） \| `cellular_call_connection.cpp` 重连块 \| |
| ABILITY_CAMERA_SUPPORT | **remove** | remove |  | \| `ABILITY_CAMERA_SUPPORT` \| 删 \| `video_control_manager.cpp`（随 D11 删目录） \| |
| OHOS_SUBSCRIBE_MOTION_ENABLE | **remove** | remove |  | \| `OHOS_SUBSCRIBE_MOTION_ENABLE` \| 删 \| `callmanager.gni` + `motion_recognition.*` \| |
| SUPPORT_RTT_CALL | **no_code** | unguard |  | \| `SUPPORT_RTT_CALL`/`CALL_MANAGER_SOS_NO_RINGBACK_TONE`/`CALL_MANAGER_WATCH_CALL_BLOCKING`/`CALL_MANAGER_THERMAL_PROTE |
| NOT_SUPPORT_MULTICALL | **keep** | unguard |  | \| `NOT_SUPPORT_MULTICALL` \| 保留 feature（默认 false 不定义） \| `BUILD.gn`/`bundle.json` + `call_{control,status,object}_manag |
| CALL_MANAGER_SOS_NO_RINGBACK_TONE | **no_code** | unguard |  | \| `SUPPORT_RTT_CALL`/`CALL_MANAGER_SOS_NO_RINGBACK_TONE`/`CALL_MANAGER_WATCH_CALL_BLOCKING`/`CALL_MANAGER_THERMAL_PROTE |
| CALL_MANAGER_WATCH_CALL_BLOCKING | **no_code** | unguard |  | \| `SUPPORT_RTT_CALL`/`CALL_MANAGER_SOS_NO_RINGBACK_TONE`/`CALL_MANAGER_WATCH_CALL_BLOCKING`/`CALL_MANAGER_THERMAL_PROTE |
| CALL_MANAGER_THERMAL_PROTECTION | **no_code** | unguard |  | \| `SUPPORT_RTT_CALL`/`CALL_MANAGER_SOS_NO_RINGBACK_TONE`/`CALL_MANAGER_WATCH_CALL_BLOCKING`/`CALL_MANAGER_THERMAL_PROTE |
| ABILITY_CELLULAR_SUPPORT | **unguard** | unguard |  | \| `ABILITY_CELLULAR_SUPPORT`/`ABILITY_SMS_SUPPORT`/`CELLULAR_DATA_SUPPORT`/`TELEPHONY_CUST_SUPPORT`/`OHOS_BUILD_ENABLE_ |
| ABILITY_SMS_SUPPORT | **unguard** | unguard |  | \| `ABILITY_CELLULAR_SUPPORT`/`ABILITY_SMS_SUPPORT`/`CELLULAR_DATA_SUPPORT`/`TELEPHONY_CUST_SUPPORT`/`OHOS_BUILD_ENABLE_ |
| CELLULAR_DATA_SUPPORT | **unguard** | unguard |  | \| `ABILITY_CELLULAR_SUPPORT`/`ABILITY_SMS_SUPPORT`/`CELLULAR_DATA_SUPPORT`/`TELEPHONY_CUST_SUPPORT`/`OHOS_BUILD_ENABLE_ |
| ABILITY_POWER_SUPPORT | **remove** | unguard |  | 删除 `ABILITY_BLUETOOTH_SUPPORT`/`SUPPORT_VIBRATOR`/`HICOLLIE_ENABLE`/`OHOS_SUBSCRIBE_MOTION_ENABLE`/`ABILITY_SCREENLOCKMG |
| TELEPHONY_CUST_SUPPORT | **unguard** | unguard |  | \| `ABILITY_CELLULAR_SUPPORT`/`ABILITY_SMS_SUPPORT`/`CELLULAR_DATA_SUPPORT`/`TELEPHONY_CUST_SUPPORT`/`OHOS_BUILD_ENABLE_ |
| OHOS_BUILD_ENABLE_TELEPHONY_CUST | **unguard** | unguard |  | \| `ABILITY_CELLULAR_SUPPORT`/`ABILITY_SMS_SUPPORT`/`CELLULAR_DATA_SUPPORT`/`TELEPHONY_CUST_SUPPORT`/`OHOS_BUILD_ENABLE_ |
| CONFIG_FACTORY_VERSION | **keep** | keep |  | \| `CONFIG_FACTORY_VERSION` \| 按宏定义能力保留（产线开/商用走 `#else`，两分支都支持）；v6.0 零引用故当前无代码改动 \| 见 Open Questions Q1 \| |
| ABILITY_AUDIO_SUPPORT | **remove** | - |  | \| `ABILITY_AUDIO_SUPPORT` \| 删（基线死分支：调用不存在的 `AudioProxy::GetToneDescriptorPath`） \| `tone.cpp` \| |
| AUDIO_SUPPORT | **-** | - |  |  |
| ABILIT_CONFIG_SUPPORT | **remove** | - |  | \| `ABILITY_CONFIG_SUPPORT`/`ABILIT_CONFIG_SUPPORT` \| 删守卫代码（carrier config 查询走默认值） \| `call_policy/cs_conference*/ims_c |

## 外部依赖处理（dependencies）

| key | 值 | AGENTS.md | 第二次 | 证据 |
|---|---|---|---|---|
| audio | **todo** | todo |  | \| 音频 audio \| todo 占位 \| `// todo!!! [audio]` ref to <文件> <函数>（`AudioProxy` 系列调用点） \| |
| database | **todo** | todo |  | \| 数据库 DataShare \| todo 占位 \| `// todo!!! [database]`（`CallDataBaseHelper`/`SettingsDataShareHelper`/`NumberIdentityDat |
| broadcast | **todo** | todo |  | \| 广播 EventFwk::CommonEventManager \| todo 占位 \| `// todo!!! [broadcast]`（七组广播订阅与全部 `PublishCommonEvent` 调用点） \| |
| power_lock | **todo** | todo |  | \| 功耗锁 RunningLock/亮屏灭屏 \| todo 占位（空操作） \| `// todo!!! [powerLock]`（`AcquireIncomingLock` 等调用点保留为空操作） \| |
| call_ui | **stub** | stub |  | \| 拉起通话界面 CallConnectAbility \| 外部接口经桩 \| `stub/` 提供 `AbilityManagerClient::ConnectAbility` 形态桩（不真正拉起） \| |
| notification | **todo** | todo |  | \| 通知 NotificationHelper \| todo 占位 \| `// todo!!! [notification]`（未接提醒调用点） \| |
| spam_call | **todo** | todo |  | \| 骚扰来电（spamshield 扩展） \| todo 占位、不用 dlopen \| `// todo!!! [spam]`（`SpamCallAdapter` 扩展连接调用点） \| |
| number_identity | **todo** | todo |  | \| 号码识别/黄页标记 \| todo 占位 \| `// todo!!! [numberIdentity]`（`NumberIdentityServiceHelper` 连接与导入请求调用点） \| |
| rtt_file_node | **todo** | todo |  | \| RTT 文件节点 \| todo 占位 \| `// todo!!! [rttFile]`（`StartRtt/StopRtt` 文件节点读写调用点，逻辑保留） \| |
| sptr | **replace** | replace |  | \| sptr \| 替代 \| `std::shared_ptr`（见 D8） \| |
| hisysevent_hitrace | **replace** | replace |  | \| HiSysEvent/HITRACE \| 替代 \| 日志打印（见 D13） \| |
| cellular_call | **stub** | stub |  | \| cellular_call 交互 \| 客户端单例桩 \| `CellularCallClient::GetInstance().Xxx()`（新桩） \| |
| core_service | **stub** | stub |  | \| core_service 交互 \| 客户端单例桩 \| `CoreServiceClient::GetInstance().Xxx()`（含 `GetVoiceMailNumber`/`HasSimCard`/FDN 查询） \| |
| cellular_data | **stub** | stub |  | \| cellular_data 交互 \| 客户端单例桩 \| `CellularDataClient::GetInstance().Xxx()`（默认数据卡查询） \| |
| sms_mms | **stub** | stub |  | \| sms_mms 交互 \| 客户端单例桩 \| `SmsClient::GetInstance().SendMessage(...)`（拒接短信） \| |
| telephony_cust | **stub** | stub |  | \| TelephonyCust 交互 \| 客户端单例桩（替代 dlopen） \| `TelephonyCustClient::GetInstance().Xxx()`（台湾紧急号码改写/暴力急救号隐藏） \| |
| ffrt | **replace** | replace |  | \| ffrt \| 替代 \| 打桩 `EventHandler`（见 D6） \| |
| libphonenumber | **stub** | stub |  | \| libphonenumber \| 同名桩 \| `stub/` 提供 `ParseAndKeepRawInput/Format*` 形态 \| |
| parameter | **stub** | stub |  | \| 系统参数 parameter \| 同名桩 \| `GetParameter/SetParameter/WatchParameter` 桩内参数表 \| |
| cjson | **stub** | stub |  | \| cJSON \| 同名桩 \| `stub/` 提供 cJSON 接口形态 \| |
| base_libs | **stub** | stub |  | \| securec/c_utils/log/eventhandler 基础库 \| 同名桩 \| `stub/` 提供（含 `sptr` 别名到 `std::shared_ptr` 的兼容层） \| |
| pacmap | **replace** | replace |  | \| PacMap/WantParams \| 替代 \| 结构体（见 D9） \| |

## 架构开关（architecture）

| key | 值 | AGENTS.md | 第二次 | 证据 |
|---|---|---|---|---|
| systemability_ipc | **remove** | remove |  | \| D2 \| `CallManagerService` 去 SystemAbility 化，`CallManagerClient` 进程内直调；不做 IPC 与权限校验【需人工复核：IPC 枚举、权限校验】 \| |
| permission_checks | **remove** | remove |  | - [ ] 5.3 权限校验调用点全删（`TelephonyPermission::CheckCallerIsSystemApp`/`CheckPermission`）；IPC 码表头保留不动；验证：rg 权限校验零命中 + gtest ` |
| locks | **remove** | - |  | \| D7 \| 锁全量不迁移：删除锁成员与加锁调用；单线程运行 \| |
| dsds_mode_zero | **yes** | yes |  | - **DSDA（BREAKING）**：DSDS 模式查询（`CoreServiceClient::GetInstance().GetDsdsMode()`，经桩实现）恒返回 0，非 0 分支不迁移；仅支持单卡但保留 `slotId` 传 |
| slot_id_kept | **yes** | yes |  | 系统 SHALL 使 DSDS 模式查询（`CoreServiceClient::GetInstance().GetDsdsMode()`，经桩实现）恒返回 0，非 0（DSDA/TDM）分支不迁移；单卡运行但 `slotId`/`acco |
