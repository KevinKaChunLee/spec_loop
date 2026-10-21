# Spec Delta

## MODIFIED Requirements

### Requirement: callmanager.gni 统一源与头组织
系统 SHALL 由 mini 的 `callmanager.gni` 以 `call_manager_path` 变量前缀单一来源维护 `call_manager_sources` / `call_manager_include_dirs`（照抄基线形态，无硬编码仓外路径）；`call_manager_sources` 删除 design D7「删除的源文件」表所列全部条目（services 侧 antifraud/bluetooth/call（会议/OTT/卫星/视频/蓝牙对象/超级隐私/有线耳机）/call_state_observer（proximity_sensor/status_bar/wired_headset）/call_earthquake_alarm/call_voice_assistant/display/distributed_call/interoperable_call/satellite_call/telephony_interaction（bluetooth_call_connection）/call_manager_service（call_manager_service_stub）各删除文件与 utils 侧 `edm_call_policy.cpp`、`incoming_flash_reminder.cpp`、`motion_recognition.cpp`、`screen_sensor_plugin.cpp`），并新增 `stub/` 桩源（见 ADDED「stub 桩目录纳入 mini 构建」条）；`call_manager_include_dirs` 删除 antifraud/bluetooth/call_earthquake_alarm/call_voice_assistant/display/distributed_call/interoperable_call/satellite_call/video 目录条目（design D10）；根 `BUILD.gn` 的 `tel_call_manager` 直接消费这两个列表、双计清单由该单点维护（照抄）。

#### Scenario: utils 源随主库编译
- **WHEN** `tel_call_manager` target 编译
- **THEN** `utils/src/` 保留源文件均在 sources 内；`edm_call_policy.cpp`、`incoming_flash_reminder.cpp`、`motion_recognition.cpp`、`screen_sensor_plugin.cpp` 已随能力删除移出 sources

#### Scenario: 路径前缀单一来源
- **WHEN** gni 各列表引用仓内路径
- **THEN** 全部以 `${call_manager_path}` 变量拼接，无硬编码仓外路径（照抄）

### Requirement: callmanager.gni 公共外部依赖面
系统 SHALL 收敛 mini `callmanager.gni` 的 `call_manager_external_deps`（design D10）：移除不再真实调用的系统依赖——ability_runtime 系大部分、audio_framework 系、common_event_service、data_share:datashare_consumer、device_manager、dsoftbus、hicollie、input、ipc:ipc_single、location、player_framework、safwk、samgr_proxy、access_token（libaccesstoken_sdk/libprivacy_sdk）、privacy、screenlock、camera_framework、bluetooth 等（保留 core_service 系头依赖经桩使用）；securec / c_utils / hilog（log）/ eventhandler 基础库与 cJSON / libphonenumber 三方库依赖移除，改由 `stub/` 同名桩源承载（`stub/securec_stub`、`stub/c_utils_stub`、`stub/log_stub`、`stub/eventhandler_stub`、`stub/cjson_stub`、`stub/phonenumber_stub`、`stub/parameter_stub`、`stub/hisysevent_stub`，design D5/D6）。依赖与宏块联动原则照抄：被裁部件的依赖与对应宏块同步摘除、不残留悬空 external_deps。

#### Scenario: 特定部件未启用的依赖
- **WHEN** 产品裁剪 global_parts_info 中某部件（本变更已按 design D7 宏清理裁剪 bluetooth/miscdevice/hicollie/motion/screenlock/camera_framework 等部件块）
- **THEN** 该外部依赖与对应宏块同步摘除，不可残留悬空 external_deps（照抄）

### Requirement: callmanager.gni 能力宏块（parts_info 联动）
系统 SHALL 处置 12 个部件条件块（design D7 宏清理，`defined(global_parts_info.X) && global_parts_info.X` 条件形态与 `call_manager_defines` 累积注入机制照抄）：删除 6 块——`communication_bluetooth`（bluetooth:btframework + `ABILITY_BLUETOOTH_SUPPORT`，BLUETOOTH 通话不迁移）、`sensors_miscdevice`（miscdevice:vibrator_interface_native + `SUPPORT_VIBRATOR`，振动不支持）、`hiviewdfx_hicollie`（hicollie:libhicollie + `HICOLLIE_ENABLE`，维测走日志桩）、`msdp_motion`（`OHOS_SUBSCRIBE_MOTION_ENABLE`，运动识别不迁移）、`theme_screenlock_mgr`（screenlock_mgr:screenlock_client + `ABILITY_SCREENLOCKMGR_SUPPORT`，随来电闪光删除）、`multimedia_camera_framework`（camera_framework:camera_framework 仅依赖块）；保留 6 块——`telephony_sms_mms`（sms_mms:tel_sms_mms_api + `ABILITY_SMS_SUPPORT`）、`telephony_cellular_call`（`ABILITY_CELLULAR_SUPPORT`，交互经 `stub/cellular_call_client` 桩）、`powermgr_power_manager`（power_manager:powermgr_client + `ABILITY_POWER_SUPPORT`，功耗锁调用点 todo [powerLock]）、`telephony_cellular_data`（cellular_data:tel_cellular_data_api + `CELLULAR_DATA_SUPPORT`，经桩）、`telephony_telephony_enhanced`（`TELEPHONY_CUST_SUPPORT`）、`telephony_telephony_cust`（`OHOS_BUILD_ENABLE_TELEPHONY_CUST`，经 `stub/telephony_cust_client` 桩）。

#### Scenario: 无蜂窝呼叫部件的构建
- **WHEN** `global_parts_info.telephony_cellular_call` 未定义或为 false
- **THEN** `ABILITY_CELLULAR_SUPPORT` 不注入 `call_manager_defines`，源码中该宏的 `#ifdef` 场点走裁剪分支（保留块条件语义照抄）

#### Scenario: 蓝牙部件关闭
- **WHEN** 构建 mini
- **THEN** `communication_bluetooth` 部件块整体删除：bluetooth:btframework 不进 external_deps 且无 `ABILITY_BLUETOOTH_SUPPORT` define（BLUETOOTH 通话与 HFP 链路不迁移）

#### Scenario: 相机框架仅依赖不加宏
- **WHEN** 构建 mini
- **THEN** `multimedia_camera_framework` 依赖块删除（基线该宏唯一场点 `utils/src/incoming_flash_reminder.cpp` 已随来电闪光删除，本仓 gni 无 `ABILITY_CAMERA_FRAMEWORK_SUPPORT` define 的状态保持）

### Requirement: 根 BUILD.gn tel_call_manager 服务库 target
系统 SHALL 保留根 `BUILD.gn` 的 `ohos_shared_library("tel_call_manager")` target 形态（PC 门禁经 test/ 兼容层使用，design D10）：sources/include_dirs 用 gni 变量照抄；deps 仅 `frameworks/native:tel_call_manager_api` 照抄；external_deps 中另行直接声明的 `cJSON:cjson`、`libphonenumber:phonenumber_standard` 两项移除、改由 `stub/cjson_stub` / `stub/phonenumber_stub` 桩源承载（design D5/D6）；cflags_cc 原样保留（含 `-fno-exceptions -fno-rtti`、`-fstack-protector-all`、`-Os` 等全量旗标）且 ldflags 照抄；固定 defines `TELEPHONY_LOG_TAG = "CallManager"`、`LOG_DOMAIN = 0xD001F10` 照抄；sanitize 与 `branch_protector_ret` 配置照抄（`test/cfi_blocklist.txt` 黑名单随裁剪同步维护，见 fuzztest 条）。

#### Scenario: 异常与 RTTI 关闭
- **WHEN** 主库编译
- **THEN** `-fno-exceptions -fno-rtti` 全量生效，仓内代码不使用异常与 dynamic_cast 语义（照抄）

#### Scenario: 日志域固定
- **WHEN** 任一源文件打点 TELEPHONY_LOG*（经 `stub/log_stub` 同名桩）
- **THEN** tag 为 "CallManager"、domain 0xD001F10（照抄）

### Requirement: declare_args 双 feature 与显示 define 对应
系统 SHALL 处置根 `BUILD.gn` 的 `declare_args()`（design D7/D10，一删一留）：删除 `call_manager_feature_hfp_async_enable`（`HFP_ASYNC_ENABLE` 为不支持宏——蓝牙不支持；`services/call/src/call_control_manager.cpp` 的 HfpBroadcastSubscriber 守卫块随蓝牙链路删除）；保留 `call_manager_feature_not_support_multicall`（默认 false；`NOT_SUPPORT_MULTICALL` 的 `#ifdef` 骨架保留，骨架内引用蓝牙/eSIM 的判定族（`IsTwoCallBtCallAndESIM` / `IsTwoCallESIMCall` 及调用点 `HangUpFirstCall` 判定链）随其移除、仅由非零 DSDS 分支进入的等待矩阵（`HoldOrDisconnectedCall`→`HandleCallWaitingNumTwo/One/Zero`）删除，`needWaitHold_`/`dialCallInfo_` 字段与复位写点、读取接口作骨架照抄，design D7 支持宏表；场景语义见 call-status-management delta）。`bundle.json` 的 `component.features` 同步（见 bundle.json 条）。

#### Scenario: HFP 异步默认关
- **WHEN** 构建 mini
- **THEN** `call_manager_feature_hfp_async_enable` declare_args 项与 feature 声明删除，`HFP_ASYNC_ENABLE` 守卫块不存在（蓝牙链路不迁移）

#### Scenario: 多呼关闭置位
- **WHEN** 产品配置 `call_manager_feature_not_support_multicall = true`
- **THEN** `NOT_SUPPORT_MULTICALL` 注入 defines，`CallControlManager`/`CallObjectManager`/`CallStatusManager` 的多呼仲裁骨架走受限仲裁（骨架照抄；蓝牙/eSIM 判定族与 DSDA 等待矩阵分支已删）

### Requirement: bundle.json 部件声明
系统 SHALL 收敛 mini `bundle.json`（design D10）：`component.features` 移除 `call_manager_feature_hfp_async_enable`、保留 `call_manager_feature_not_support_multicall`（与 declare_args 一删一留成对）；`build.group_type` 中 sa_profile service_group 项随 `sa_profile/` 整目录不迁移移除、`frameworks/js` fwk_group 项随 JS 出口不迁移移除（AGENTS：JS/ETS/仓颉绑定不实现）；`build.inner_kits` 收敛为 native 内 kit（`frameworks/native:tel_call_manager_api`，header_base `interfaces/innerkits/`），cj FFI kit（`frameworks/cj`）不迁移；`component.syscap` 与 `deps.components` 按 mini 实际保留面收敛（bluetooth/dsoftbus/screenlock/camera 等被裁部件依赖移出）；`build.test` 指向调整后的 test 组织（见 unittest/fuzztest 条）；adapted_system_type 照抄。

#### Scenario: feature 面向产品 GN 参数
- **WHEN** 产品配置部件开关
- **THEN** 仅 `call_manager_feature_not_support_multicall` 出现在 component.features 候选中（hfp_async 已删）

#### Scenario: 内 API 两个出口
- **WHEN** 查看部件 inner_kits
- **THEN** 仅 native 内 kit（tel_call_manager_api）一个出口；cj FFI kit 不迁移，JS/ETS 出口不设 fwk_group

### Requirement: frameworks/native tel_call_manager_api inner-api target
系统 SHALL 收敛 `frameworks/native/BUILD.gn` 的 `ohos_shared_library("tel_call_manager_api")`（design D10）：sources 缩减为直调面保留文件——删除 `bluetooth_call_client.cpp`、`bluetooth_call_proxy.cpp`、`nearlink_call_client.cpp`、`super_privacy_manager_client.cpp`、`call_manager_proxy.cpp`、`call_manager_service_proxy.cpp`、`call_status_callback_proxy.cpp`、`cellular_call_proxy.cpp`、`cellular_call_callback_death_recipient.cpp`、`call_manager_death_recipient.cpp`、`call_ability_callback_proxy.cpp`、`call_ability_callback_death_recipient.cpp`（对应头文件随删，design D7 frameworks/native 删除清单；D2/D3：客户端直调、proxy/death recipient 传输类不迁移），保留 `call_manager_client.cpp`、`call_ability_callback.cpp`、`call_ability_callback_stub.cpp`、`native_call_manager_hisysevent.cpp`、`native_call_manager_utils.cpp`、`voip_call_manager_proxy.cpp`（VoIP 代理出口桩化，VoIP 冲突链保留）；version_script 引用移除（见 REMOVED「versionscript 导出符号面」条）；`device_name == "rk3568"` 时 defines += `CALL_MANAGER_AUTO_START_OPTIMIZE` 的注入块删除（design D7：`CALL_MANAGER_AUTO_START_OPTIMIZE` 为不支持宏，`call_manager_proxy.cpp` 与 sa_profile 均不迁移）；public_configs、`innerapi_tags`、`part_name` 与关闭异常/RTTI 的配置照抄；external_deps 按收敛面同步（ipc/safwk/samgr 系移除）。

#### Scenario: 客户端库独立产物
- **WHEN** 部件编译
- **THEN** 客户端编为独立库 target（tel_call_manager_api），与服务库 tel_call_manager 分离（target 形态照抄，PC 门禁兼容层使用）

#### Scenario: rk3568 客户端注入自动限时优化宏
- **WHEN** device_name 为 rk3568
- **THEN** 该 defines 注入块删除（`CALL_MANAGER_AUTO_START_OPTIMIZE` 不支持宏，autostart 客户端守卫与 sa_profile 延迟拉起面均不迁移），无该宏注入

### Requirement: interfaces 目录组织
系统 SHALL 收敛 mini `interfaces/` 对外面：`interfaces/innerkits/` 头面按客户端裁剪收敛——`bluetooth_call_client.h`、`nearlink_call_client.h`、`super_privacy_manager_client.h` 随对应客户端删除（design D7「对应头文件随删」），`call_manager_service_ipc_interface_code.h`、`call_ability_callback_ipc_interface_code.h`、`call_status_callback_ipc_interface_code.h`、`cellular_call_ipc_interface_code.h` 等 IPC 枚举头与其余基线头（`call_manager_base.h`、`call_manager_info.h`、`i_voip_call_manager_callback.h`、`voip_call_manager_info.h` 等）原样保留（design D3：枚举值 ABI 只允许末尾追加、不改任何枚举值）；`interfaces/kits/js/` 不迁移（AGENTS：JS 绑定不实现）。

#### Scenario: IPC 码表独立成头
- **WHEN** 客户端/服务端需对齐命令码（含测试与后续系统恢复）
- **THEN** IPC 枚举头保留于 innerkits 且枚举值与基线一致（需人工复核（IPC 枚举 ABI）：恢复 IPC 形态时须保证码值不变，见 proposal BREAKING 项）

#### Scenario: JS kit 仅类型声明
- **WHEN** 查看 mini interfaces/kits
- **THEN** 该目录不迁移，JS API 声明面不存在（实现体 frameworks/js 同不迁移）

### Requirement: unittest 组织
系统 SHALL 调整 `test/unittest/BUILD.gn` 的 `group("unittest")`（design D10）：删除 `tel_call_earthquake_alarm_test`、`tel_call_voice_assistant_test`、`distributed_communication_test` 三个 target（地震预警/语音播报/分布式通信不支持，design D7 删除对应源文件目录）；`tel_call_manager1_gtest` ~ `tel_call_manager8_gtest` 与 zero 系（`tel_call_manager_zero2/zero4/zero5/zero6/zero7/zero8/zero9/zero10_gtest` 进组，zero1/zero3 维持组外）、special 系（`tel_call_manager_special1_test`/`special3_test` 进组，special2 维持组外）保留并随裁剪同步（被删模块对应用例面裁剪）；`tel_call_manager_ui_test`（ohos_executable，install_enable）保留并随裁剪同步。PC 门禁 must-pass 套件集合调整由 pc-test-harness delta 承载（design D11），本条仅约束仓内 target 组织。

#### Scenario: 组内选择性聚合
- **WHEN** 按 group("unittest") 编译
- **THEN** `tel_call_manager_zero1_gtest`、`tel_call_manager_zero3_gtest`、`tel_call_manager_special2_test` 仍有 target 定义但不在组内（组外形态照抄）；earthquake/voice assistant/distributed_communication 三 target 已删除

#### Scenario: ui 测试是可执行件
- **WHEN** 聚合组编译
- **THEN** `tel_call_manager_ui_test` 以 ohos_executable（install_enable）产出，非 gtest 套件（照抄）

### Requirement: fuzztest 与 mock 组织
系统 SHALL 调整 `test/fuzztest/BUILD.gn` 的 `group("fuzztest")`（design D10）：删除被移除模块对应的 fuzzer target——`BluetoothDialCallFuzzTest`（BLUETOOTH 通话）、`CallManagerServiceStubFuzzTest`（`call_manager_service_stub.cpp` 已随 D2 删除）、`ControlCameraFuzzTest` 与 `SetPausePictureFuzzTest`（视频通话/摄像头控制不支持）、`DisplayFuzzTest`（折叠屏）、`DistributedCommunicationFuzzTest`（分布式通信），及组外的 `callvoiceassistantmanager_fuzzer/` 目录与 `CallVoiceAssistantManagerFuzzTest` target（语音播报，随目录删除）；其余（`AudioDeviceFuzzTest`、`SetAudioDeviceFuzzTest`、`CallFuzzTest`、`DialCallFuzzTest`、`RejectCallFuzzTest`、`CallAbilityCallbackFuzzTest`、`CallNotificationFuzzTest`、`SetCallTransferInfoFuzzTest`、`FormatPhoneNumberFuzzTest`、`FormatPhoneNumberToE164FuzzTest`、`IsEmergencyPhoneNumberFuzzTest`、`StartDtmfFuzzTest`、`TelephonyInteractionFuzzTest`）保留并随裁剪同步。`common_fuzzer/` 公共支撑目录照抄；`test/mock/BUILD.gn` 占位（无 target）照抄；`test/cfi_blocklist.txt` 黑名单内容随裁剪同步维护（被删符号移出黑名单）。

#### Scenario: 组外 fuzzer
- **WHEN** 按 group("fuzztest") 编译
- **THEN** 基线组外的 `callvoiceassistantmanager_fuzzer` 目录已随语音播报能力删除，不再存在组外 target

#### Scenario: mock 空壳
- **WHEN** 查询 test/mock 构建能力
- **THEN** BUILD.gn 无任何 target 定义，不产出物（照抄）

#### Scenario: CFI 黑名单参与构建
- **WHEN** `tel_call_manager` 开启 cfi 编译
- **THEN** `test/cfi_blocklist.txt` 对黑名单内符号豁免 CFI 校验（黑名单内容按裁剪后符号面维护）

## REMOVED Requirements

### Requirement: watch 平台特化（SUPPORT_MUTE_BY_DATABASE 与互通设置处理）
**Reason**: design D7 裁决 `target_platform == "watch"` 特设块整体删除（手表 mini 也不启用 `SUPPORT_MUTE_BY_DATABASE` 行为；interoperable_call 目录整体删除，`interoperable_settings_handler.cpp` 不迁移）。
**Migration**: 删除 gni 末段 `target_platform == "watch"` 的两处注入（`call_manager_defines += ["SUPPORT_MUTE_BY_DATABASE"]` 与 `call_manager_sources` 追加 `services/interoperable_call/src/interoperable_settings_handler.cpp`）；仓内两处 `#ifdef SUPPORT_MUTE_BY_DATABASE` 守卫块（`services/call/call_state_observer/src/call_records_manager.cpp`、`services/call_manager_service/src/call_manager_service.cpp`）删除，静音持久化走宏未定义分支（调用面处置见 call-state-observer / call-manager-service delta）。恢复条件：产品要求 watch 特化静音持久化与互信互联互通（interoperable/dsoftbus 能力就绪）后按基线恢复该块。

### Requirement: sa_profile 双 profile（4005 与 4005_auto_start_optimize）
**Reason**: liteOS 无 SystemAbility/samgr/safwk 形态（AGENTS：不继承 SystemAbility、不实现 IPC；design D2：`CallManagerService` 进程内单例、`sa_profile/` 整体不迁移）。
**Migration**: `sa_profile/` 目录（`sa_profile/BUILD.gn`、`4005.json`、`4005_auto_start_optimize.json` 双 profile 与 rk3568 device 切换）整体不迁移；`CALL_MANAGER_AUTO_START_OPTIMIZE` 的 profile 切换面随 `frameworks/native` 客户端守卫删除消解（design D7）；bundle.json 的 sa_profile service_group 项同步移除（见 MODIFIED bundle.json 条）。恢复条件：恢复 SA 形态（samgr/safwk 就绪）后按基线恢复双 profile 与按 device 切换。

### Requirement: versionscript 导出符号面
**Reason**: mini 无共享库导出面（liteOS 单进程直调，无外部模块经导出符号链接 `tel_call_manager_api` 的场景）；design D10 裁决 versionscript 不迁移并登入 Open Questions 复核（design Open Question 5，默认不迁移）。
**Migration**: `frameworks/native` 的 `tel_call_manager_api.versionscript` 文件不迁移；`tel_call_manager_api` target 的 version_script 引用移除；基线导出的 12 类符号模式（含 `*BluetoothCallClient*`、`*NearlinkCallClient*`、`*SuperPrivacyManagerClient*` 等已删客户端符号）随导出面消失一并不迁移。恢复条件：若后续恢复共享库导出面（design Open Question 5，需人工复核），按基线 versionscript 重建并扣除已删客户端符号。

## ADDED Requirements

### Requirement: stub 桩目录纳入 mini 构建
系统 SHALL 由 mini 的 `callmanager.gni` 把 `telephony_call_manager_mini/stub/` 桩目录源文件纳入构建（design D13 桩目录、D4/D5/D6 给出的新代码）：`stub/` 下全部桩源进入 `call_manager_sources`、桩头文件路径进入 `call_manager_include_dirs`，随根 `BUILD.gn` `tel_call_manager` 主库编译。桩清单：跨模块客户端单例桩 `stub/cellular_call_client.cpp`、`stub/core_service_client.cpp`、`stub/cellular_data_client.cpp`、`stub/sms_client.cpp`、`stub/telephony_cust_client.cpp`、`stub/voip_call_client.cpp`（AGENTS 五模块 `XxxClient::GetInstance().Xxx()` 替换形态，加 voip_call_manager 出口桩）与 `stub/state_registry_client.cpp`（`CallStateReportProxy` 对 core_service TelephonyStateRegistry 上报出口，design D4 落点）；基础同名桩 `stub/eventhandler_stub.cpp`（ffrt 队列/任务/延时的替代，串行语义、不新增线程）、`stub/hisysevent_stub.cpp`（维测日志替代，签名不变）、`stub/parameter_stub.cpp`（系统参数）、`stub/cjson_stub.cpp`（cJSON）、`stub/phonenumber_stub.cpp`（libphonenumber，签名相同的空实现）、`stub/securec_stub.cpp`、`stub/c_utils_stub.cpp`、`stub/log_stub.cpp`（基础库，design D5）。桩为 design 给出的新代码，与基线仓无对应源文件；桩不引入被移除部件的 external_deps（见 MODIFIED 公共外部依赖面条）。

#### Scenario: 桩源随主库编译
- **WHEN** `tel_call_manager` target 编译
- **THEN** `stub/` 全部桩源在 sources 内编译产出，跨模块调用点（`CellularCallClient::GetInstance().Xxx()` 等）与基础库调用点符号可解析

#### Scenario: 桩不新增构建依赖
- **WHEN** `stub/` 桩编译
- **THEN** 桩自身无外部依赖，不引入 audio/data_share/cJSON/libphonenumber 等被移除或打桩的依赖项（`call_manager_external_deps` 收敛面不被桩回引）

#### Scenario: 桩默认负值语义
- **WHEN** 任一桩接口在默认态被调用（如 `CellularCallClient` 未配置服务可用）
- **THEN** 桩返回失败/服务不可用类负值，与基线"服务未连接/代理为空"分支语义一致（design Risks），调用方走既有失败分支
