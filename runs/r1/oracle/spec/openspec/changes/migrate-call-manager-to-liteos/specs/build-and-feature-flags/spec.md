# Spec Delta

## MODIFIED Requirements

### Requirement: 业务库构建
系统 SHALL 以根 `BUILD.gn` 的 `ohos_shared_library("tel_call_manager")` 编译业务库：`sources = call_manager_sources`（裁剪后的源集：移除 bluetooth/video/satellite_call/distributed_call/interoperable_call/antifraud/call_voice_assistant/call_earthquake_alarm/display 模块组源与不支持宏守护文件）、`include_dirs = call_manager_include_dirs`、`external_deps` 收敛为桩与保留部件依赖（cJSON/libphonenumber 经 `stub/`），`deps = ["frameworks/native:tel_call_manager_api"]` 保留，cflags_cc 保留 `-fno-exceptions`、`-fno-rtti`、`-fstack-protector-all`、`-Os`、`-flto`、`-fvisibility=hidden` 等，defines 保留 `TELEPHONY_LOG_TAG = "CallManager"` 与 `LOG_DOMAIN = 0xD001F10`。
#### Scenario: 禁用异常与 RTTI
- **WHEN** 业务库编译
- **THEN** `-fno-exceptions -fno-rtti` 生效，代码不得使用 try/catch 与 dynamic_cast

#### Scenario: 裁剪后源集可编译
- **WHEN** 以裁剪后的 `call_manager_sources` 编译业务库
- **THEN** 全部保留源文件编译通过，不存在对已移除模块组头文件/符号的引用

### Requirement: 两个 declare_args feature
系统 SHALL 以根 `BUILD.gn` 的 `declare_args()` 保留 `call_manager_feature_not_support_multicall = false`（定义 `NOT_SUPPORT_MULTICALL`，支持宏，默认不定义）；`call_manager_feature_hfp_async_enable`（`HFP_ASYNC_ENABLE` 不支持宏）移除；`bundle.json` 的 `component.features` 与保留 feature 成对。
#### Scenario: 打开不支持多通话 feature
- **WHEN** 产品配置 `call_manager_feature_not_support_multicall = true`
- **THEN** 业务库带 `NOT_SUPPORT_MULTICALL` 编译，通话上限降为 1 并启用 `HangUpFirstCall` 系列逻辑

### Requirement: 部件在位条件宏
系统 SHALL 由 `callmanager.gni` 的宏集合收敛为支持集：恒定义 `ABILITY_SMS_SUPPORT`、`ABILITY_CELLULAR_SUPPORT`、`CELLULAR_DATA_SUPPORT`、`TELEPHONY_CUST_SUPPORT`、`OHOS_BUILD_ENABLE_TELEPHONY_CUST`（对应源迁移，外部交互经桩）；`ABILITY_BLUETOOTH_SUPPORT`、`ABILITY_POWER_SUPPORT`、`SUPPORT_VIBRATOR`、`HICOLLIE_ENABLE`、`OHOS_SUBSCRIBE_MOTION_ENABLE`、`ABILITY_SCREENLOCKMGR_SUPPORT` 与 multimedia_camera_framework 依赖块移除（对应源不迁移或调用点占位）；构建不再依赖 `global_parts_info` 条件求值。
#### Scenario: 部件缺失时对应功能退役
- **WHEN** `callmanager.gni` 求值（不依赖 `global_parts_info` 部件在位探测）
- **THEN** 支持宏集合恒定（`ABILITY_SMS_SUPPORT` 等恒定义、对应源迁移且交互经桩），不支持宏块不存在，裁掉任一 OHOS 部件不影响源集与宏集

### Requirement: 客户端库与 JS 模块构建
系统 SHALL 由 `frameworks/native/BUILD.gn` 产出 `ohos_shared_library("tel_call_manager_api")`（直调客户端，版本符号语义保留）；`CALL_MANAGER_AUTO_START_OPTIMIZE`（rk3568 分支）不迁移；`frameworks/js` 的 `ohos_shared_library("call")` 与 `frameworks/cj` 的 `cj_telephony_call_ffi` 不迁移；`bundle.json` 的 inner_kits 仅 `tel_call_manager_api`，fwk_group 与 service_group 相应调整，`sa_profile` 不再交付。
#### Scenario: rk3568 设备自动优化
- **WHEN** 构建 `frameworks/native:tel_call_manager_api`（无 `device_name` 分支）
- **THEN** `CALL_MANAGER_AUTO_START_OPTIMIZE` 分支不迁移，客户端恒为直调形态（广播延迟连接不存在）

### Requirement: 单元与模糊测试 target
系统 SHALL 由 `test/unittest/BUILD.gn` 保留 gtest target 并随源裁剪调整：`call_manager_gtest`（`tel_call_manager1~8_gtest`）、`call_manager_zero_gtest`（存活 zero 系列）、`call_manager_special_test`（存活 special 系列）、`ui_client`（`tel_call_manager_ui_test`）保留；`call_earthquake_alarm_test`、`call_voice_assistant_test`、`distributed_communication_test` target 移除（对应能力已移除）；`test/fuzztest` 不迁移。
#### Scenario: 跑模块单测
- **WHEN** 构建系统编译 `test/unittest:call_manager_gtest`
- **THEN** 存活的 gtest 可执行 target 全部产出并可在 PC 门禁运行

#### Scenario: 移除能力的测试 target 不存在
- **WHEN** 检索 `test/unittest/BUILD.gn`
- **THEN** 不存在 `call_earthquake_alarm_test`/`call_voice_assistant_test`/`distributed_communication_test` target

## REMOVED Requirements

### Requirement: watch 平台专属源与宏
**Reason**: AGENTS.md 功能范围：分布式（distributed 及 interoperable）通话不支持，`interoperable_settings_handler.cpp` 为互通通话专属源。
**Migration**: `SUPPORT_MUTE_BY_DATABASE` define 与 `services/interoperable_call/src/interoperable_settings_handler.cpp` 源不迁移；`MuteRinger` 不再联动 settingsdata 静音开关。
