# build-config Specification

## Purpose
描述 `telephony_call_manager/` 的构建面在 OpenHarmony v6.0 快照中的现状：`callmanager.gni`（sources/include_dirs/external_deps/能力宏块/watch 特化）、根 `BUILD.gn` 的 `tel_call_manager` 服务库 target 与 `declare_args` feature 开关、`bundle.json` 部件声明、`sa_profile/`（4005.json 与 4005_auto_start_optimize.json 双 profile、rk3568 切换）、`frameworks/native/BUILD.gn` 的 `tel_call_manager_api` inner-api target 与 `tel_call_manager_api.versionscript` 导出符号面、`interfaces/` 目录组织、`test/` 的 unittest/fuzztest/mock 组织。本规格是后续裁剪 delta 的修改载体：所有能力宏与文件的增删都以这里列出的块为单位。本规格描述原仓构建脚本本身，不重复 pc-test-harness 规格已经覆盖的 PC 门禁内容（test/ 下 8 个 must-pass 套件与原仓 target 的关系详见 pc-test-harness 规格）。本能力声明以下编译宏（场点为 `callmanager.gni` 的 define 块、根/子目录 `BUILD.gn` 的定义块与仓内 `#ifdef` 场点，宏语义逐块列出见 Requirements）：`ABILITY_BLUETOOTH_SUPPORT`、`ABILITY_SMS_SUPPORT`、`ABILITY_CELLULAR_SUPPORT`、`ABILITY_POWER_SUPPORT`、`SUPPORT_VIBRATOR`、`CELLULAR_DATA_SUPPORT`、`HICOLLIE_ENABLE`、`TELEPHONY_CUST_SUPPORT`、`OHOS_BUILD_ENABLE_TELEPHONY_CUST`、`OHOS_SUBSCRIBE_MOTION_ENABLE`、`ABILITY_SCREENLOCKMGR_SUPPORT`、`SUPPORT_MUTE_BY_DATABASE`（watch 注入）、`HFP_ASYNC_ENABLE` 与 `NOT_SUPPORT_MULTICALL`（declare_args feature 显示 define）、`CALL_MANAGER_AUTO_START_OPTIMIZE`（rk3568 注入）。仓内另有 `CONFIG_FACTORY_VERSION`、`CALL_MANAGER_THERMAL_PROTECTION`、`CALL_MANAGER_WATCH_CALL_BLOCKING` 等宏在全仓零引用（无 `#ifdef` 场点亦无 gni/BUILD 定义块），不构成行为开关，本规格不为其建模。

## Requirements

### Requirement: callmanager.gni 统一源与头组织
系统 SHALL 由 `callmanager.gni` 以 `call_manager_path = "//base/telephony/call_manager"` 为前缀定义：`call_manager_sources`（约 100 个 .cpp，覆盖 services 下 antifraud/audio/audio_state/bluetooth/call/call_earthquake_alarm/call_manager_service/call_report/call_setting/call_voice_assistant/display/distributed_call/hisysevent/interoperable_call/number_identity_proxy/satellite_call/spam_call/telephony_interaction/video 各子目录 + utils 全部 11 个源文件）、`call_manager_include_dirs`（与子目录 include 对应的约 30 条路径）。根 `BUILD.gn` 的 `tel_call_manager` 直接消费这两个列表，双计清单由该单点维护。

#### Scenario: utils 源随主库编译
- **WHEN** `tel_call_manager` target 编译
- **THEN** `utils/src/` 全部 11 文件（含 edm_call_policy.cpp、incoming_flash_reminder.cpp、motion_recognition.cpp）均在 sources 内

#### Scenario: 路径前缀单一来源
- **WHEN** gni 各列表引用仓内路径
- **THEN** 全部以 `${call_manager_path}` 变量拼接，无硬编码仓外路径

### Requirement: callmanager.gni 公共外部依赖面
系统 SHALL 由 `callmanager.gni` 的 `call_manager_external_deps` 固定主库外部依赖基面：ability_base:base/want/zuri、ability_runtime（ability_connect_callback_stub/ability_deps_wrapper/ability_manager/abilitykit_native/app_manager/dataobs_manager）、access_token（libaccesstoken_sdk/libprivacy_sdk）、audio_framework 四件套、c_utils、common_event_service、core_service 两件、data_share:datashare_consumer、device_manager、distributed_notification_service、dsoftbus、eventhandler、ffrt、graphic_surface、hilog、hisysevent、hitrace、init、input、ipc、location 两个、openssl 两个、os_account、player_framework、safwk、samgr。三库由根 `BUILD.gn` 另行直接声明：`cJSON:cjson`、`libphonenumber:phonenumber_standard`。

#### Scenario: 特定部件未启用的依赖
- **WHEN** 产品裁剪 global_parts_info 中某部件
- **THEN** 该外部依赖与对应宏块（见能力宏 Requirement）应同步摘除，不可残留悬空 external_deps

### Requirement: callmanager.gni 能力宏块（parts_info 联动）
系统 SHALL 由 `callmanager.gni` 以 `defined(global_parts_info.X) && global_parts_info.X` 为条件维护 12 个部件条件块（其中 11 个"部件 → 追加依赖 → 追加 define"块，1 个仅追加依赖），define 经 `call_manager_defines` 累积后由根 BUILD.gn `defines += call_manager_defines` 全量注入：`communication_bluetooth` → bluetooth:btframework + `ABILITY_BLUETOOTH_SUPPORT`；`telephony_sms_mms` → sms_mms:tel_sms_mms_api + `ABILITY_SMS_SUPPORT`；`telephony_cellular_call` → 仅 `ABILITY_CELLULAR_SUPPORT`；`powermgr_power_manager` → power_manager:powermgr_client + `ABILITY_POWER_SUPPORT`；`sensors_miscdevice` → miscdevice:vibrator_interface_native + `SUPPORT_VIBRATOR`；`telephony_cellular_data` → cellular_data:tel_cellular_data_api + `CELLULAR_DATA_SUPPORT`；`hiviewdfx_hicollie` → hicollie:libhicollie + `HICOLLIE_ENABLE`；`telephony_telephony_enhanced` → 仅 `TELEPHONY_CUST_SUPPORT`；`telephony_telephony_cust` → 仅 `OHOS_BUILD_ENABLE_TELEPHONY_CUST`；`msdp_motion` → 仅 `OHOS_SUBSCRIBE_MOTION_ENABLE`；`theme_screenlock_mgr` → screenlock_mgr:screenlock_client + `ABILITY_SCREENLOCKMGR_SUPPORT`。另有一块只追加依赖不加 define：`multimedia_camera_framework` → camera_framework:camera_framework。

#### Scenario: 无蜂窝呼叫部件的构建
- **WHEN** `global_parts_info.telephony_cellular_call` 未定义或为 false
- **THEN** `ABILITY_CELLULAR_SUPPORT` 不注入 `call_manager_defines`，源码中该宏的 `#ifdef` 场点走裁剪分支

#### Scenario: 蓝牙部件关闭
- **WHEN** `communication_bluetooth` 未启
- **THEN** `bluetooth:btframework` 不进 external_deps 且无 `ABILITY_BLUETOOTH_SUPPORT` define

#### Scenario: 相机框架仅依赖不加宏
- **WHEN** `multimedia_camera_framework` 启用
- **THEN** 仅链接 camera_framework 依赖，本仓 gni 不产生 `ABILITY_CAMERA_FRAMEWORK_SUPPORT` define（该宏场点在 utils/src/incoming_flash_reminder.cpp，来源需产品配置另议）

### Requirement: watch 平台特化（SUPPORT_MUTE_BY_DATABASE 与互通设置处理）
系统 SHALL 在 `callmanager.gni` 末段当 `target_platform == "watch"` 时做两处注入：`call_manager_defines += ["SUPPORT_MUTE_BY_DATABASE"]`（仓内 `#ifdef` 场点：`services/call/call_state_observer/src/call_records_manager.cpp` 与 `services/call_manager_service/src/call_manager_service.cpp`，静音持久化改走设置数据库路径）与 `call_manager_sources` 追加 `services/interoperable_call/src/interoperable_settings_handler.cpp`（该文件仅在 watch 平台进入编译清单）。

#### Scenario: 手表静音持久化
- **WHEN** watch 产品编译
- **THEN** `SUPPORT_MUTE_BY_DATABASE` 生效，静音状态经设置数据库读写（`call_records_manager` 相关分支）

#### Scenario: 非手表不引入互通设置处理器
- **WHEN** target_platform 非 watch
- **THEN** `interoperable_settings_handler.cpp` 不进 sources，`SUPPORT_MUTE_BY_DATABASE` 未定义

### Requirement: 根 BUILD.gn tel_call_manager 服务库 target
系统 SHALL 由根 `BUILD.gn` 定义 `ohos_shared_library("tel_call_manager")`：sources/include_dirs 用 gni 三个变量；deps 仅 `frameworks/native:tel_call_manager_api`；external_deps = cJSON + libphonenumber + gni 公共依赖；sanitize 开启 cfi/cfi_cross_dso/cfi_vcall_icall_only、`branch_protector_ret = "pac_ret"`；cflags_cc 固定 `-Wunused -Wunreachable-code -fno-exceptions -fno-rtti -fstack-protector-all -Os -D_FORTIFY_SOURCE=2 -flto -Wno-unused-but-set-variable -fdata-sections -ffunction-sections -fno-asynchronous-unwind-tables -fno-unwind-tables -fvisibility=hidden` 且 ldflags `-flto -Wl,--gc-sections`；固定 defines `TELEPHONY_LOG_TAG = "CallManager"`、`LOG_DOMAIN = 0xD001F10`。

#### Scenario: 异常与 RTTI 关闭
- **WHEN** 主库编译
- **THEN** `-fno-exceptions -fno-rtti` 全量生效，仓内代码不使用异常与 dynamic_cast 语义

#### Scenario: 日志域固定
- **WHEN** 任一源文件打点 TELEPHONY_LOG*
- **THEN** tag 为 "CallManager"、domain 0xD001F10

### Requirement: declare_args 双 feature 与显示 define 对应
系统 SHALL 由根 `BUILD.gn` 的 `declare_args()` 定义两个默认 false 的 feature：`call_manager_feature_hfp_async_enable`（true 时 defines += ["HFP_ASYNC_ENABLE"] 并打印 "Support hfp async enable."）与 `call_manager_feature_not_support_multicall`（true 时 defines += ["NOT_SUPPORT_MULTICALL"] 并打印 "not Support multi call."）。仓内 `#ifdef` 场点：`HFP_ASYNC_ENABLE`（services/call/src/call_control_manager.cpp）、`NOT_SUPPORT_MULTICALL`（call_control_manager / call_object_manager / call_status_manager 的 .h/.cpp 共 10 处多呼仲裁开关）。两个 feature 同步声明在 `bundle.json` 的 `component.features`。

#### Scenario: HFP 异步默认关
- **WHEN** 产品未显式置 `call_manager_feature_hfp_async_enable`
- **THEN** 默认 false，`HFP_ASYNC_ENABLE` 不定义，HFP 同步路径编译

#### Scenario: 多呼关闭置位
- **WHEN** 产品配置 `call_manager_feature_not_support_multicall = true`
- **THEN** `NOT_SUPPORT_MULTICALL` 注入 call_manager_defines，`CallControlManager`/`CallObjectManager`/`CallStatusManager` 的多呼分支走受限仲裁

### Requirement: bundle.json 部件声明
系统 SHALL 由 `bundle.json` 声明部件 `call_manager`（subsystem telephony、destPath `base/telephony/call_manager`）：`component.syscap` 两项（`SystemCapability.Telephony.CallManager`、`SystemCapability.Applications.Contacts`）；`component.features` 仅 `call_manager_feature_hfp_async_enable` 与 `call_manager_feature_not_support_multicall`；`deps.components` 约 40 项（bluetooth/cellular_data/core_service/sms_mms/screenlock_mgr/dsoftbus 等）；`build.group_type` 三组（fwk_group `//base/telephony/call_manager/frameworks/js:call`，service_group `tel_call_manager` 与 `//base/telephony/call_manager/sa_profile:call_manager_sa_profile`）；`build.inner_kits` 两项（`frameworks/native:tel_call_manager_api` header_base `interfaces/innerkits/`、`frameworks/cj:cj_telephony_call_ffi` header_base `frameworks/cj/src`）；`build.test` 指向 `test/unittest:unittest` 与 `test/fuzztest:fuzztest`；adapted_system_type 仅 standard。

#### Scenario: feature 面向产品 GN 参数
- **WHEN** 产品配置部件开关
- **THEN** 仅两个 call_manager_feature_* 出现在 component.features 候选中

#### Scenario: 内 API 两个出口
- **WHEN** 查看部件 inner_kits
- **THEN** native 内 kit（tel_call_manager_api）与 cj FFI kit 两个出口，JS/ETS 出口走 fwk_group

### Requirement: sa_profile 双 profile（4005 与 4005_auto_start_optimize）
系统 SHALL 由 `sa_profile/BUILD.gn` 的 `ohos_sa_profile("call_manager_sa_profile")` 按 device 切换 profile：`device_name == "rk3568"` 用 `4005_auto_start_optimize.json`，否则用 `4005.json`。两份 json 声明同一 SA：name 4005、process "foundation"、libpath 均为 `libtel_call_manager.z.so`、distributed false、dump_level 1；唯一差异为 `run-on-create`——`4005.json` 为 true（随 foundation 启动即创建），`4005_auto_start_optimize.json` 为 false（延迟创建，与 `CALL_MANAGER_AUTO_START_OPTIMIZE` 客户端延时拉起配套，互为开关两面）。

#### Scenario: 常规产品启动即建
- **WHEN** 非 rk3568 产品烧录 `4005.json`
- **THEN** SA 4005 在 foundation 进程启动即创建（run-on-create true）

#### Scenario: rk3568 延迟拉起
- **WHEN** device_name 为 rk3568
- **THEN** sa_profile 取 `4005_auto_start_optimize.json`（run-on-create false），客户端经 CALL_MANAGER_AUTO_START_OPTIMIZE 分支等射频广播后再连接

### Requirement: frameworks/native tel_call_manager_api inner-api target
系统 SHALL 由 `frameworks/native/BUILD.gn` 定义 `ohos_shared_library("tel_call_manager_api")`：sources 为 14 个客户端源文件（bluetooth_call_client/bluetooth_call_proxy/call_ability_callback/call_ability_callback_stub/call_manager_client/call_manager_proxy/call_manager_service_proxy/call_status_callback_proxy/cellular_call_proxy/native_call_manager_hisysevent/native_call_manager_utils/nearlink_call_client/super_privacy_manager_client/voip_call_manager_proxy）；public_configs（include/ + interfaces/innerkits + utils/include）；version_script 指向 `tel_call_manager_api.versionscript`；`device_name == "rk3568"` 时 defines += ["CALL_MANAGER_AUTO_START_OPTIMIZE"]；`innerapi_tags = ["platformsdk"]`；`part_name = "call_manager"`；external_deps 为 ability/appmgr/c_utils/ces/core_service 两件/graphic_surface/hilog/ffrt/hisysevent/hitracechain/init/ipc/safwk/samgr；sanitize 关闭 cfi（client target）；同样关闭异常与 RTTI。

#### Scenario: 客户端库独立产物
- **WHEN** 部件编译
- **THEN** 客户端编为独立 .z.so（tel_call_manager_api），与服务库 tel_call_manager 分离

#### Scenario: rk3568 客户端注入自动限时优化宏
- **WHEN** device_name 为 rk3568
- **THEN** `CALL_MANAGER_AUTO_START_OPTIMIZE` 注入 `tel_call_manager_api` 编译面，`call_manager_proxy.cpp` 延时拉起路径成立

### Requirement: versionscript 导出符号面
系统 SHALL 由 `tel_call_manager_api.versionscript` 的 1.0 版本节控制 `tel_call_manager_api` 只导出 12 类 C++ 符号模式（global 段）：`*BluetoothCallClient*`、`*CallAbilityCallback*`、`*CallManagerCallback*`、`*CallManagerClient*`、`*CallStatusCallbackProxy*`、`*CellularCallInterface*`、`*CellularCallProxy*`、`*ICallStatusCallback*`、`*NearlinkCallClient*`、`*VoipCallConnection*`、`*VoipCallManagerProxy*`、`*SuperPrivacyManagerClient*`；local 段 `*` 隐藏其余全部符号（含 IBluetoothCall/ICallManagerService 等内部 broker 类型与私有实现）。

#### Scenario: 内部类型不外泄
- **WHEN** 链接 tel_call_manager_api 的外部模块尝试引用 `IBluetoothCall` 符号
- **THEN** 该符号因 local `*` 通配而被隐藏，导出面不含内部 broker 类型

#### Scenario: 裁剪影响导出面
- **WHEN** 手表基线移除蓝牙/星闪/超级隐私客户端
- **THEN** versionscript 中 `*BluetoothCallClient*`、`*NearlinkCallClient*`、`*SuperPrivacyManagerClient*` 等通配需随之删除（具体由裁剪 delta 决定）

### Requirement: interfaces 目录组织
系统 SHALL 由 `interfaces/` 对外只暴露两个子面：`interfaces/innerkits/` 存放 23 个 C/C++ 头（bluetooth_call_client.h、bluetooth_call_ipc_interface_code.h、call_ability_callback_ipc_interface_code.h、call_manager_base.h、call_manager_callback.h、call_manager_client.h、call_manager_disconnected_details.h、call_manager_errors.h、call_manager_info.h、call_manager_inner_type.h、call_manager_service_ipc_interface_code.h、call_status_callback_ipc_interface_code.h、call_status_callback_proxy.h、cellular_call_interface.h、cellular_call_ipc_interface_code.h、cellular_call_proxy.h、i_call_status_callback.h、i_voip_call_manager_callback.h、i_voip_call_manager_service.h、nearlink_call_client.h、super_privacy_manager_client.h、voip_call_manager_info.h、voip_call_manager_proxy.h）；`interfaces/kits/js/` 仅 `@ohos.telephony.call.d.ts`（JS API 声明）。

#### Scenario: IPC 码表独立成头
- **WHEN** 客户端/服务端需对齐命令码
- **THEN** 4 份 *_ipc_interface_code.h（call_manager_service/call_ability_callback/call_status_callback/cellular_call/bluetooth_call）内置于 innerkits 目录

#### Scenario: JS kit 仅类型声明
- **WHEN** 查看 interfaces/kits
- **THEN** 仅存在 @ohos.telephony.call.d.ts，实现体在 frameworks/js

### Requirement: unittest 组织
系统 SHALL 由 `test/unittest/BUILD.gn` 的 `group("unittest")` 聚合原仓 gtest target（组内清单）：`tel_call_manager1_gtest` ~ `tel_call_manager8_gtest`（test/unittest/call_manager_gtest/，8 个）、`tel_call_manager_zero2_gtest/zero4/zero5/zero6/zero7/zero8/zero9/zero10_gtest`（test/unittest/call_manager_zero_gtest/，10 个 target 中进组 8 个，zero1/zero3 不进组）、`tel_call_manager_special1_test/special3_test`（call_manager_special_test/，3 个 target 中 special2 不进组）、`tel_call_manager_ui_test`（ui_client/，ohos_executable）、`tel_call_earthquake_alarm_test`、`tel_call_voice_assistant_test`、`distributed_communication_test`。此清单同时是 bundle.json `build.test` 与 PC 门禁选择 target 的原仓依据。

#### Scenario: 组内选择性聚合
- **WHEN** 按 group("unittest") 编译
- **THEN** `tel_call_manager_zero1_gtest`、`tel_call_manager_zero3_gtest`、`tel_call_manager_special2_test` 虽有 target 定义但不在组内

#### Scenario: ui 测试是可执行件
- **WHEN** 聚合组编译
- **THEN** `tel_call_manager_ui_test` 以 ohos_executable（install_enable）产出，非 gtest 套件

### Requirement: fuzztest 与 mock 组织
系统 SHALL 由 `test/fuzztest/BUILD.gn` 的 `group("fuzztest")` 聚合 19 个 fuzzer 子目录，每目录一个 `ohos_fuzztest` target：AudioDeviceFuzzTest、BluetoothDialCallFuzzTest、CallFuzzTest、CallAbilityCallbackFuzzTest、CallManagerServiceStubFuzzTest、CallNotificationFuzzTest、ControlCameraFuzzTest、DialCallFuzzTest、DisplayFuzzTest、FormatPhoneNumberFuzzTest、FormatPhoneNumberToE164FuzzTest、IsEmergencyPhoneNumberFuzzTest、RejectCallFuzzTest、SetAudioDeviceFuzzTest、SetCallTransferInfoFuzzTest、SetPausePictureFuzzTest、StartDtmfFuzzTest、TelephonyInteractionFuzzTest、DistributedCommunicationFuzzTest。`test/fuzztest/callvoiceassistantmanager_fuzzer/` 目录存在 `ohos_fuzztest("CallVoiceAssistantManagerFuzzTest")` target 但不在组内；`common_fuzzer/` 为公共支撑目录。另有 `test/mock/BUILD.gn`（仅版权头的占位文件，无 target）与 `test/cfi_blocklist.txt`（CFI 黑名单，服务库 cfi 开启时生效）。

#### Scenario: 组外 fuzzer
- **WHEN** 按 group("fuzztest") 编译
- **THEN** `callvoiceassistantmanager_fuzzer` 的 target 不进组

#### Scenario: mock 空壳
- **WHEN** 查询 test/mock 构建能力
- **THEN** BUILD.gn 无任何 target 定义，不产出物

#### Scenario: CFI 黑名单参与构建
- **WHEN** `tel_call_manager` 开启 cfi 编译
- **THEN** `test/cfi_blocklist.txt` 对黑名单内符号豁免 CFI 校验（黑名单内容随裁剪 delta 维护）