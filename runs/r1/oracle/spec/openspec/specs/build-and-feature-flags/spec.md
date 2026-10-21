# 构建与特性开关（build-and-feature-flags）Specification

## Purpose
描述 `telephony_call_manager` 的构建系统：`callmanager.gni`（`call_manager_sources`/`call_manager_include_dirs`/`call_manager_external_deps` 与 12 个 `global_parts_info` 条件宏）、根 `BUILD.gn`（`ohos_shared_library("tel_call_manager")` 与 `declare_args()` 两个 feature）、`bundle.json`（`component.features` 与 inner_kits）、`sa_profile/`（4005.json 与 4005_auto_start_optimize.json）、子目录 `BUILD.gn` 与 `test/unittest`、`test/fuzztest` 测试 target。编译约束：`-fno-exceptions -fno-rtti`（禁止 try/catch 与 dynamic_cast）。默认手机构建下部件在位与否决定宏：`ABILITY_BLUETOOTH_SUPPORT`、`ABILITY_SMS_SUPPORT`、`ABILITY_CELLULAR_SUPPORT`、`ABILITY_POWER_SUPPORT`、`SUPPORT_VIBRATOR`、`CELLULAR_DATA_SUPPORT`、`HICOLLIE_ENABLE`、`TELEPHONY_CUST_SUPPORT`、`OHOS_BUILD_ENABLE_TELEPHONY_CUST`、`OHOS_SUBSCRIBE_MOTION_ENABLE`、`ABILITY_SCREENLOCKMGR_SUPPORT`（multimedia_camera_framework 仅追加依赖无 define）；`target_platform == "watch"` 时追加 `SUPPORT_MUTE_BY_DATABASE` 与 `interoperable_settings_handler.cpp`。

## Requirements

### Requirement: 业务库构建
系统 SHALL 以根 `BUILD.gn` 的 `ohos_shared_library("tel_call_manager")` 编译业务库：`sources = call_manager_sources`、`include_dirs = call_manager_include_dirs`、`external_deps = ["cJSON:cjson", "libphonenumber:phonenumber_standard"] + call_manager_external_deps`，`deps = ["frameworks/native:tel_call_manager_api"]`，cflags_cc 含 `-fno-exceptions`、`-fno-rtti`、`-fstack-protector-all`、`-Os`、`-flto`、`-fvisibility=hidden` 等，defines 含 `TELEPHONY_LOG_TAG = "CallManager"` 与 `LOG_DOMAIN = 0xD001F10`。
#### Scenario: 禁用异常与 RTTI
- **WHEN** 业务库编译
- **THEN** `-fno-exceptions -fno-rtti` 生效，代码不得使用 try/catch 与 dynamic_cast

### Requirement: 两个 declare_args feature
系统 SHALL 以根 `BUILD.gn` 的 `declare_args()` 暴露 `call_manager_feature_hfp_async_enable = false`（定义 `HFP_ASYNC_ENABLE`）与 `call_manager_feature_not_support_multicall = false`（定义 `NOT_SUPPORT_MULTICALL`），且与 `bundle.json` 的 `component.features` 成对。
#### Scenario: 打开不支持多通话 feature
- **WHEN** 产品配置 `call_manager_feature_not_support_multicall = true`
- **THEN** 业务库带 `NOT_SUPPORT_MULTICALL` 编译，通话上限降为 1 并启用 `HangUpFirstCall` 系列逻辑

### Requirement: 部件在位条件宏
系统 SHALL 由 `callmanager.gni` 以 `global_parts_info` 逐项追加 define 与依赖：`communication_bluetooth`→`ABILITY_BLUETOOTH_SUPPORT`（+btframework）、`telephony_sms_mms`→`ABILITY_SMS_SUPPORT`、`telephony_cellular_call`→`ABILITY_CELLULAR_SUPPORT`、`powermgr_power_manager`→`ABILITY_POWER_SUPPORT`、`sensors_miscdevice`→`SUPPORT_VIBRATOR`、`telephony_cellular_data`→`CELLULAR_DATA_SUPPORT`、`hiviewdfx_hicollie`→`HICOLLIE_ENABLE`、`telephony_telephony_enhanced`→`TELEPHONY_CUST_SUPPORT`、`telephony_telephony_cust`→`OHOS_BUILD_ENABLE_TELEPHONY_CUST`、`msdp_motion`→`OHOS_SUBSCRIBE_MOTION_ENABLE`、`theme_screenlock_mgr`→`ABILITY_SCREENLOCKMGR_SUPPORT`、`multimedia_camera_framework`→仅追加 camera_framework 依赖。
#### Scenario: 部件缺失时对应功能退役
- **WHEN** 产品裁掉 `telephony_sms_mms` 部件
- **THEN** `ABILITY_SMS_SUPPORT` 不定义，`RejectCallSms` 短信拒接编译为空实现

### Requirement: watch 平台专属源与宏
系统 SHALL 在 `target_platform == "watch"` 时为业务库追加 `SUPPORT_MUTE_BY_DATABASE` define 与 `services/interoperable_call/src/interoperable_settings_handler.cpp` 源文件。
#### Scenario: 手表平台构建
- **WHEN** `target_platform == "watch"`
- **THEN** `InteroperableSettingsHandler` 入编且 `MuteRinger` 联动 settingsdata 静音开生效

### Requirement: 客户端库与 JS 模块构建
系统 SHALL 由 `frameworks/native/BUILD.gn` 产出 `ohos_shared_library("tel_call_manager_api")`（innerapi_tags platformsdk、version_script），`device_name == "rk3568"` 时追加 `CALL_MANAGER_AUTO_START_OPTIMIZE`；`frameworks/js/BUILD.gn` 产出 `ohos_shared_library("call")`（relative_install_dir module/telephony，gen_call_abc/call_js/call_abc 三件套）；`frameworks/cj/BUILD.gn` 产出 `cj_telephony_call_ffi`；`bundle.json` 的 inner_kits 为 `tel_call_manager_api` 与 `cj_telephony_call_ffi`，fwk_group `frameworks/js:call`，service_group `:tel_call_manager` + `sa_profile:call_manager_sa_profile`。
#### Scenario: rk3568 设备自动优化
- **WHEN** 以 `device_name == "rk3568"` 构建客户端库
- **THEN** `CALL_MANAGER_AUTO_START_OPTIMIZE` 生效，`CallManagerProxy` 改为广播触发延迟连接

### Requirement: 单元与模糊测试 target
系统 SHALL 由 `test/unittest/BUILD.gn` 组织测试 target：`call_manager_gtest`（`tel_call_manager1~8_gtest` 8 项）、`call_manager_zero_gtest`（zero2/4/5/6/7/8/9/10）、`call_manager_special_test`（`tel_call_manager_special1_test`、`tel_call_manager_special3_test`）、`ui_client`（`tel_call_manager_ui_test`）、`call_earthquake_alarm_test`（`tel_call_earthquake_alarm_test`）、`call_voice_assistant_test`（`tel_call_voice_assistant_test`）、`distributed_communication_test`；`test/fuzztest` 下 24 个 fuzzer target。
#### Scenario: 跑模块单测
- **WHEN** 构建系统编译 `test/unittest:call_manager_gtest`
- **THEN** 8 个 gtest 可执行 target 全部产出
