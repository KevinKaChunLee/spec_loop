# Proposal

## Why

`test/` 目前一条命令都跑不起来：工具链绑死在 OHOS NDK（`-target x86_64-linux-ohos --sysroot=D:/或/mnt/d/ohos_tools/...`），一键入口转发到不存在的 Windows 路径，`third_party/` 两个 gitlink 没有 `.gitmodules`，`//base/telephony/call_manager` 指向的 junction 也不在仓里。核实后发现 NDK 提供的只有 clang + musl + libc++ 三样通用件——GN 里没有一处链接 sysroot 的 `.so`，没有一处 include 指向 sysroot，被测源码和桩层也没有一处 `__OHOS__`/`__MUSL__`。项目目标已从"手机 call_manager 的 PC 化测试"变成"移植到 LiteOS + MCU"，"与手机真机编译器同源"的前提不再成立，NDK 依赖成了纯粹的历史残留。这个 change 把 test 工程里所有 OHOS 工具链/运行时残留清掉，换成本机 clang，并把环境落地到可以在本机 `gn gen → ninja → run_tests.sh` 走通门禁——这是 `trim-call-manager-for-watch` 的前置条件。

## What Changes

- **BREAKING** 工具链：删除 `ohos_ndk` toolchain 与 win/wsl 两个 NDK profile，改为单一 `host_clang` toolchain（本机 `clang-18` + `libc++`，不再 `-target`/`--sysroot`）。产物从 OHOS ELF（musl）变为普通 Linux ELF（glibc + libc++）。
- **BREAKING** 运行时：`run_tests.sh` 删除 musl loader 检查与 `/mnt/d/ohos_tools/.../libc++_shared.so` 的 `LD_LIBRARY_PATH`；输出目录由硬编码 `out_win` 改为 `out`（可用 `OUT_DIR` 覆盖）。保留 `LD_PRELOAD=tools/libohos_dl_shim.so`（它模拟"设备端 .so 不存在"，是测试语义而非 OHOS 工具链残留）。
- **BREAKING** 一键入口：`build.sh` 改为在本机直接调用 gn/ninja；删除 `build.cmd`、`setup_wsl.cmd`（Windows 侧转发链路整条废弃）。
- 删除 `stubs/include/codecvt` 桩：它只为 OHOS NDK libc++ 缺失 `<codecvt>` 而存在，本机 libc++ 18 自带该头（已验证 `wstring_convert<codecvt_utf8<char16_t>>` 可编译运行）。若实测本机头触发告警，用 `-Wno-deprecated-declarations`（已在 `_pc_common_cflags_cc`）覆盖。
- 修复 `third_party/`：为 `googletest`（`283c1756`）与 `cjson`（`fb16e5c`）补 `.gitmodules`，让 clone 后 `git submodule update --init` 能拿到源码。
- **BREAKING** 基线版本：只读基线 `../telephony_call_manager/` 从 `master@24e1785f` 改为 tag `OpenHarmony-v6.0-Release`（commit `f99813be`，2025-09-01）。原因：test 工程的桩层 API 面与该 tag 完全吻合，与 master 相差约 25 项桩 API（详见 design.md「实施中发现」）；稳定发布版也更适合作为移植基线。`config.yaml` 同步修改。
- 桩层修正：`tools/dl_shim.c` 增加"按库名判定不存在"列表，`libtelephony_ext_innerkits.z.so` 返回 NULL 句柄而非假句柄——上游 `distributed_communication_test` 有 2 例断言该库不存在时 wrapper 返回 `TELEPHONY_ERROR`。
- 环境落地：把只读基线（`f99813be`，工作树干净）的工作树复制到 `telephony_call_manager/`（替换 `.gitkeep`），并以相对符号链接 `test/base/telephony/call_manager -> ../../../telephony_call_manager` 让 `//base/telephony/call_manager` 解析到副本。
- 文档：`test/README.md` 与 `test/docs/liteos_sdk_mapping.md` 中的 NDK/Windows 说明改为本机工具链说明；后者"工具链同源"一节标注为历史决策并说明废弃原因。
- 门禁：未裁剪的副本在新工具链下 must-pass 8 套件全部 PASS 后，打 tag `baseline-unmodified`。

## 裁剪范围

本 change 不裁剪任何 call_manager 业务能力，只改测试工程。按 `openspec/specs` 能力 id：

- 移除：无。
- 保留：`call-object-model`、`call-uplink-state-machine`、`call-downlink`、`multi-call-arbitration`、`audio-routing-and-tones`、`supplementary-services`、`extended-call-features`、`distributed-and-interoperable-call`、`bluetooth-call`、`incoming-call-filtering`、`telephony-interaction`、`ipc-service-interface`、`client-frameworks`、`call-state-broadcast`、`call-state-observers`、`observability`、`build-and-feature-flags`——全部原样保留，副本与基线逐字节一致。
- 修改：`pc-test-harness`——「工具链与运行时」「一键入口」「本机环境与工程假设的差异」三条 Requirement 重写，「桩层替代 OHOS 系统内部 C++ API」删除"NDK 公开 API 路线图"场景。

## 非目标

- 不裁剪、不修改副本 `telephony_call_manager/` 的任何源码、GN、feature 宏（那是 `trim-call-manager-for-watch` 的事）。
- 不重写 `build/ohos.gni` / `build/test.gni` 兼容模板层——它扮演 OHOS build 仓的模板角色，是"按原仓 GN 编译"的必要件，不是残留。
- 不动 `stubs/include/` 下 OHOS 系统内部 API 的桩头（ipc / samgr / ffrt / hilog…）——它们替代的是被测代码引用的头，与工具链无关。
- 不把 ffrt / hilog 等换成任何真库。
- 不做 LiteOS 目标平台的交叉编译。
- 不改 must-pass 套件集合（8 套件与 baseline 一致，含 `distributed_communication_test`）。
- 不处理已知含 UB 的套件（`zero_branch3`、`special_branch0`）。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `pc-test-harness`：工具链从 OHOS NDK 交叉改为本机 clang；运行时不再需要 musl 与 NDK libc++；一键入口不再转发 Windows；`//base/telephony/call_manager` 解析到副本；"本机环境差异"Requirement 改为描述落地后的状态；删除 NDK 公开 API 路线图场景。

## Impact

- 代码：`test/build/toolchain/{BUILD.gn,profiles.gni}`、`test/build/config/BUILDCONFIG.gn`、`test/run_tests.sh`、`test/build.sh`、`test/README.md`、`test/docs/liteos_sdk_mapping.md`；删除 `test/build.cmd`、`test/setup_wsl.cmd`、`test/stubs/include/codecvt`；新增 `.gitmodules`、`test/base/telephony/call_manager`（symlink）、`telephony_call_manager/`（约 8 MB 副本）。
- 依赖：新增本机 apt 包 `clang-18 libc++-18-dev libc++abi-18-dev ninja-build gcc`，预编译 `gn`；不再需要 OHOS SDK、`musl`、MSYS2、Windows 侧任何东西。
- 风险：musl → glibc 可能暴露被测代码对 libc 行为的隐含假设（`strerror` 文本、`realpath`、`localtime` 等），会在门禁运行时显现；`-target` 变化不影响 `__OHOS__` 类宏（源码与桩层零引用）。
- 无 ECC / 权限校验 / IPC 枚举 / 跨部件结构体改动，无需人工复核项。
- 与 `trim-call-manager-for-watch` 的关系：该 change 的 `tasks.md` 前置即本 change；两者都对 `pc-test-harness` 写 delta，本 change 先归档。**基线从 master 改为 v6.0-Release 后的跟进（已完成）**：`trim-call-manager-for-watch` 与 `openspec/specs/` 已按 OpenHarmony-v6.0-Release（`f99813be`）重核并改写（会议/视频/卫星引用面、桩头约 143 个 `.h`、`pc-test-harness` baseline 同步为本机 clang + v6.0）。
