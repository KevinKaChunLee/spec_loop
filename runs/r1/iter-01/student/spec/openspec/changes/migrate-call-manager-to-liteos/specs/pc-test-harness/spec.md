# Spec Delta

## MODIFIED Requirements

### Requirement: 按原仓 GN 编译，兼容层零业务知识
系统 SHALL 由 `build/ohos.gni`（`build/test.gni` 仅转发）扮演 OHOS build 仓的模板角色：`ohos_shared_library` → `static_library(name)` + `shared_library(name+"_so")`；`ohos_static_library` → `static_library`；`ohos_unittest` → `executable` 并注入 gtest/gmock 与 shim；其他模板 → 占位 group。业务 target `//base/telephony/call_manager:tel_call_manager` 与测试 target 直接引用被测模块的 `BUILD.gn`，sources / include_dirs / defines / feature 开关全部来自被测 GN。本变更落地后，被测源码为裁剪产物 `telephony_call_manager_mini/`（由 `telephony_call_manager/` 整拷后裁剪，见 `migrate-call-manager-to-liteos`），`test/base/telephony/call_manager` 软链指向 mini；兼容层本身保持零业务知识不变。

#### Scenario: 兼容层剔除设备专属 flag
- **WHEN** 被测 target 携带 `-flto`、`-fno-exceptions`、`-fno-rtti`、`-fvisibility=hidden`、`-fstack-protector-*`、`-fno-(asynchronous-)unwind-tables`
- **THEN** 兼容层按 `_pc_blocklist` 剔除，并追加 `_pc_force_includes`（`dlfcn.h`、`securec.h`、常用 STL 头等）与 `-Wno-c++11-narrowing -Wno-unused-parameter -Wno-deprecated-declarations`

#### Scenario: 兼容层统一注入宏
- **WHEN** 任一业务/测试 target 编译
- **THEN** 追加 `ABILITY_CELLULAR_SUPPORT=0x1`，并依赖 `//stubs:ext_ohos`；`ABILITY_BLUETOOTH_SUPPORT` 不再注入（mini 已无该宏场点，蓝牙链路整体裁剪）；mini 引入的桩（`telephony_call_manager_mini/stub/`，详见能力 `liteos-stub-layer` 与能力 `build-config` delta）一并纳入被测编译

#### Scenario: 原仓位置
- **WHEN** GN 解析 `//base/telephony/call_manager`
- **THEN** 该路径经 `test/base/telephony/call_manager` 软链指向仓内裁剪产物 `telephony_call_manager_mini/`

### Requirement: must-pass 门禁
系统 SHALL 由 `tests/BUILD.gn` 的 `mustpass_tests` 组聚合并由 `run_tests.sh` 顺序运行。本变更落地后，must-pass 套件为 5 套：`sanity_test`、`liteos_stub_test`（自有）、`tel_call_manager_zero2_gtest`、`tel_call_manager_zero5_gtest`、`tel_call_manager_special2_test`（原仓 target，随 mini 测试组织裁剪）。原 8 套中的 `tel_call_voice_assistant_test`、`distributed_communication_test`、`tel_call_earthquake_alarm_test` 因被测源文件与测试 target 随能力移除（见 `voice-assistant-call`、`distributed-call`、`earthquake-alarm-call` 的 REMOVED delta 及 `build-config` delta）而移出门禁。每个套件 `timeout 240`，日志写 `${TMPDIR:-/tmp}/gn_<suite>.$UID.log`。门禁标准：全部套件 rc=0 且 `[  FAILED` 计数为 0，输出 `MUST-PASS GATE: PASS`。

#### Scenario: 任一套件失败
- **WHEN** 某套件 rc≠0 或有 FAILED 用例
- **THEN** 门禁输出 `MUST-PASS GATE: FAIL` 并以非零退出

#### Scenario: 不在门禁内的套件
- **WHEN** 套件含被测代码 UB（如 `zero_branch3`、`special_branch0` 的 `reinterpret_cast` 兄弟类）或其被测源文件已随裁剪移除
- **THEN** 不纳入 must-pass；移除行为按旧工程“已知差异”记录

### Requirement: 本机环境与工程假设的差异（已核实）
系统 SHALL 视以下事实为当前状态：本机为 Ubuntu 24.04；`gn`（预编译二进制）、`ninja`、`clang-18`、`libc++-18-dev`、`gcc` 已安装；`third_party/googletest`（`283c1756`）与 `third_party/cjson`（`fb16e5c`）以 submodule 形式声明在 `.gitmodules` 中；`test/base/telephony/call_manager` 为相对符号链接，本变更后指向仓内裁剪产物 `telephony_call_manager_mini/`；只读基线 `telephony_call_manager/` 为 tag `OpenHarmony-v6.0-Release`（commit `f99813be`），仅作对照，不再被编译；桩层 API 面与该 tag 对齐；对更新的上游版本（v6.1 起）不保证可编译。

#### Scenario: 原仓位置解析到副本
- **WHEN** GN 解析 `//base/telephony/call_manager`
- **THEN** 得到 `telephony_call_manager_mini/` 裁剪产物，而不是只读基线 `telephony_call_manager/`

#### Scenario: 在本机运行门禁
- **WHEN** 裁剪落地完成后，在本机 `test/` 下执行 `bash build.sh all`
- **THEN** 从 `gn gen` 到 `MUST-PASS GATE` 全程在本机完成

#### Scenario: 副本未裁剪时门禁通过
- **WHEN** `telephony_call_manager_mini/` 为刚整拷自基线的未裁剪副本（与 tag `baseline-unmodified` 等价，本变更 Migration Plan 第 1 步）时执行 `bash build.sh all`
- **THEN** 原 must-pass 8 套件全部 rc=0 且 0 失败，输出 `MUST-PASS GATE: PASS`（作为移植第一步的门禁基线；完成裁剪与桩化后改按 5 套件门禁验收，见 must-pass 门禁需求）

#### Scenario: 子模块缺失
- **WHEN** clone 后未执行 `git submodule update --init`
- **THEN** `gn gen` 报 `third_party/googletest` 源文件缺失，`README.md` 快速开始第一步即为该命令