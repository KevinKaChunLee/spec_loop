# Spec Delta

## MODIFIED Requirements

### Requirement: 按原仓 GN 编译，兼容层零业务知识
系统 SHALL 由 `build/ohos.gni`（`build/test.gni` 仅转发）扮演 OHOS build 仓的模板角色：`ohos_shared_library` → `static_library(name)` + `shared_library(name+"_so")`；`ohos_static_library` → `static_library`；`ohos_unittest` → `executable` 并注入 gtest/gmock 与 shim；其他模板 → 占位 group。业务 target `//base/telephony/call_manager:tel_call_manager` 与测试 target 直接引用 `telephony_call_manager_mini/` 的 `BUILD.gn`，sources / include_dirs / defines / feature 开关全部来自该 GN。兼容层为业务与测试 target 注入手表宏集（`ABILITY_CELLULAR_SUPPORT`、`ABILITY_SMS_SUPPORT`、`CELLULAR_DATA_SUPPORT`、`TELEPHONY_CUST_SUPPORT`、`OHOS_BUILD_ENABLE_TELEPHONY_CUST`），不再注入 `ABILITY_BLUETOOTH_SUPPORT`，并依赖 `//stubs:ext_ohos`。
#### Scenario: 兼容层剔除设备专属 flag
- **WHEN** 原 target 携带 `-flto`、`-fno-exceptions`、`-fno-rtti`、`-fvisibility=hidden`、`-fstack-protector-*`、`-fno-(asynchronous-)unwind-tables`
- **THEN** 兼容层按 `_pc_blocklist` 剔除，并追加 `_pc_force_includes`（`dlfcn.h`、`securec.h`、常用 STL 头等）与 `-Wno-c++11-narrowing -Wno-unused-parameter -Wno-deprecated-declarations`

#### Scenario: 兼容层统一注入宏
- **WHEN** 任一业务/测试 target 编译
- **THEN** 注入手表宏集（`ABILITY_CELLULAR_SUPPORT` 等），不注入 `ABILITY_BLUETOOTH_SUPPORT`，并依赖 `//stubs:ext_ohos`

#### Scenario: 原仓位置
- **WHEN** GN 解析 `//base/telephony/call_manager`
- **THEN** 该路径经 `test/base/telephony/call_manager` 软链指向仓内 `telephony_call_manager_mini/`（裁剪产物）

### Requirement: must-pass 门禁
系统 SHALL 由 `tests/BUILD.gn` 的 `mustpass_tests` 组聚合并由 `run_tests.sh` 顺序运行：`sanity_test`、`liteos_stub_test`（自有）、`tel_call_manager_zero2_gtest`、`tel_call_manager_zero5_gtest`、`tel_call_manager_special2_test`（原仓 target）；`tel_call_voice_assistant_test`、`distributed_communication_test`、`tel_call_earthquake_alarm_test` 从门禁移除（对应能力已移除）。每个套件 `timeout 240`，日志写 `${TMPDIR:-/tmp}/gn_<suite>.$UID.log`。门禁标准：全部套件 rc=0 且 `[  FAILED` 计数为 0，输出 `MUST-PASS GATE: PASS`。
#### Scenario: 任一套件失败
- **WHEN** 某套件 rc≠0 或有 FAILED 用例
- **THEN** 门禁输出 `MUST-PASS GATE: FAIL` 并以非零退出

#### Scenario: 门禁仅运行保留套件
- **WHEN** `run_tests.sh` 顺序执行门禁
- **THEN** 仅运行保留的 5 个套件，已移除能力的 3 个套件不在门禁内

#### Scenario: 不在门禁内的套件
- **WHEN** 套件含被测代码 UB（如 `zero_branch3`、`special_branch0` 的 `reinterpret_cast` 兄弟类）
- **THEN** 不纳入 must-pass，行为按旧工程"已知差异"记录
