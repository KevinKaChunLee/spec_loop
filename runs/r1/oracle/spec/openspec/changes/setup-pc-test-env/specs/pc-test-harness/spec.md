# Spec Delta

## MODIFIED Requirements

### Requirement: 桩层替代 OHOS 系统内部 C++ API
系统 SHALL 在 `stubs/include/`（含 `c_utils/`、`ffrt/`、`hilog/`、`hitrace/`、`openssl/`、`phonenumbers/`、`nlohmann/`、`transport/`、`syspara/`、`liteos/`）以"头优先遮蔽"方式提供 ipc / samgr / safwk / eventhandler / c_utils(sptr, refbase) / want / data_share / os_account / audio / bluetooth / notification / location 等内部 API 的桩，`stubs/src/{refbase,dlfcn,secure_zero}.cpp` 提供必要实现，聚合为 `//stubs:ohos_stubs` 与 `//stubs:ext_ohos`（后者含真实 cJSON 源）。桩层 MUST 不依赖任何 OHOS SDK/NDK 的头或库；桩层 MUST NOT 遮蔽本机标准库已提供的头。

#### Scenario: 桩模拟"服务不存在"
- **WHEN** 被测代码通过 samgr 获取外部服务代理
- **THEN** 桩返回空/失败，被测代码走"服务不存在"分支（这是 PC 测试的主要语义）

#### Scenario: OHOS 公开 API 走桩
- **WHEN** 依赖属于 OHOS 公开 API（ffrt、hilog C 宏、hitrace、hiappevent、crypto/ssl、IPCKit C）
- **THEN** 由 `stubs/include/` 的桩满足，不链接任何 OHOS 真库；不存在"换成 sysroot 真库"的路线图

#### Scenario: 标准库头不被遮蔽
- **WHEN** 被测代码或桩包含 `<codecvt>`、`<locale>` 等标准库头
- **THEN** 解析到本机 libc++ 的实现；`stubs/include/` 下不存在同名文件

### Requirement: 工具链与运行时
系统 SHALL 以本机 clang（`clang-18` / `clang++-18` / `llvm-ar-18`，`-stdlib=libc++`，`-std=gnu++17`）在 Linux 主机上原生编译，不使用 `-target` 与 `--sysroot`，工具链定义 MUST 不含任何 OHOS SDK/NDK、Windows 或 `/mnt/d` 路径。产物为普通 x86_64 Linux ELF，链接本机 glibc 与 libc++。运行只需 `LD_PRELOAD=tools/libohos_dl_shim.so`（`dlopen` interposer，由 `tools/build_shim.sh` 用本机 cc 构建）：对设备端 `*.so` 默认发假句柄、`dlsym` 返回恒 0 的空函数；对 interposer 内"不存在列表"中的库名 MUST 返回 NULL 句柄，模拟该库缺失。

#### Scenario: 编译命令零 OHOS 残留
- **WHEN** 检索 `gn gen` 生成的 `toolchain.ninja` 中全部 `command =` 行，以及 `build/toolchain/`、`build/config/` 下的文件
- **THEN** 不出现 `ohos`、`sysroot`、`musl`、`/mnt/d`、`D:/` 任一字符串。（`build/ohos.gni` 中 `ohos_shared_library` 等模板名是上游 `BUILD.gn` 的调用约定，属兼容模板层而非工具链，不在此检查范围）

#### Scenario: 运行时缺件
- **WHEN** `run_tests.sh` 启动
- **THEN** 依次自检 interposer、测试二进制，缺哪件打印对应构建命令并以 rc=2 退出；不再检查 musl loader

#### Scenario: 产物可直接运行
- **WHEN** 门禁中任一测试二进制被执行
- **THEN** 无需设置 `LD_LIBRARY_PATH` 即可加载运行

#### Scenario: 被声明为不存在的设备端库
- **WHEN** 被测代码 `dlopen("libtelephony_ext_innerkits.z.so")`
- **THEN** 得到 NULL 句柄，wrapper 走"库不存在"分支返回 `TELEPHONY_ERROR`（`distributed_communication_test` 的 `Telephony_DcManagerTest_001` 与 `Telephony_DcManager_SwitchToSinkDevice` 据此通过）

#### Scenario: 其余设备端库
- **WHEN** 被测代码 `dlopen("libtelephony_cust_api.z.so")` 等不在列表中的 `*.so`
- **THEN** 得到假句柄，`dlsym` 返回恒 0 的空函数（`voice_assistant`、`zero_branch5`、`special_branch2` 等依赖该语义）

### Requirement: 一键入口
系统 SHALL 提供 `build.sh`（bash，本机执行）：`build`（增量编译，首次自动 `gn gen`）/ `run`（仅运行门禁）/ `all`（编译 + 门禁）/ `clean`（删除输出目录）/ `rebuild` / `gen`。输出目录默认 `out/`，MUST 可用环境变量 `OUT_DIR` 覆盖；`build.sh` 与 `run_tests.sh` MUST 使用同一输出目录约定。仓内 MUST NOT 存在 Windows 批处理入口或对 Windows 侧的转发。

#### Scenario: 全新 clone 后一条命令走通
- **WHEN** 在已安装 clang-18 / libc++ / gn / ninja / gcc 的 Linux 主机上执行 `git submodule update --init && bash tools/build_shim.sh && bash build.sh all`
- **THEN** 完成 `gn gen`、编译 `mustpass_tests`、运行门禁并输出 `MUST-PASS GATE: PASS`

#### Scenario: 自定义输出目录
- **WHEN** `OUT_DIR=out_dbg bash build.sh all`
- **THEN** 编译产物与门禁读取的二进制均位于 `out_dbg/`

#### Scenario: 纯 Linux / WSL 编译
- **WHEN** 在 WSL 或任意 Linux 主机上执行 `bash build.sh all`
- **THEN** 编译与运行全部在本机完成，不调用 `cmd.exe`、不依赖任何 Windows 侧路径；WSL 与原生 Linux 无差别

### Requirement: 本机环境与工程假设的差异（已核实）
系统 SHALL 视以下事实为当前状态：本机为 Ubuntu 24.04；`gn`（预编译二进制）、`ninja`、`clang-18`、`libc++-18-dev`、`gcc` 已安装；`third_party/googletest`（`283c1756`）与 `third_party/cjson`（`fb16e5c`）以 submodule 形式声明在 `.gitmodules` 中；`test/base/telephony/call_manager` 为相对符号链接，指向仓内副本 `telephony_call_manager/`；只读基线 `../telephony_call_manager/` 检出在 tag `OpenHarmony-v6.0-Release`（commit `f99813be`），副本内容与之逐字节一致。桩层 API 面与该 tag 对齐；对更新的上游版本（v6.1 起）不保证可编译。

#### Scenario: 原仓位置解析到副本
- **WHEN** GN 解析 `//base/telephony/call_manager`
- **THEN** 得到 `telephony_call_manager/`（仓内副本）而不是工作区顶层的只读基线

#### Scenario: 在本机运行门禁
- **WHEN** 环境落地完成后，在本机 `test/` 下执行 `bash build.sh all`
- **THEN** 从 `gn gen` 到 `MUST-PASS GATE` 全程在本机完成，不再有"一条命令都无法运行"的状态

#### Scenario: 副本未裁剪时门禁通过
- **WHEN** 副本与基线逐字节一致，执行 `bash build.sh all`
- **THEN** must-pass 8 套件全部 rc=0 且 0 失败，输出 `MUST-PASS GATE: PASS`，该提交打 tag `baseline-unmodified`

#### Scenario: 子模块缺失
- **WHEN** clone 后未执行 `git submodule update --init`
- **THEN** `gn gen` 报 `third_party/googletest` 源文件缺失，`README.md` 快速开始第一步即为该命令
