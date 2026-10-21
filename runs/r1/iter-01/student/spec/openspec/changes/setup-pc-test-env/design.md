# Design

## Context

见 proposal.md「Why」。与方案相关的现状：

- `build/toolchain/BUILD.gn` 只定义一个 toolchain `ohos_ndk`，5 个 tool 的 command 都带 `-target x86_64-linux-ohos --sysroot=$sysroot`；`profiles.gni` 用 `host_os_profile` 在 win/wsl 两组 NDK 绝对路径间切换；`BUILDCONFIG.gn` `set_default_toolchain("//build/toolchain:ohos_ndk")`。
- `build/ohos.gni` 是"OHOS build 仓模板层"的 PC 替身：`_pc_force_includes`（含 `-include codecvt`）、`_pc_blocklist`、`_pc_common_cflags_cc`，与工具链无关。
- 全部 GN 无 `libs`/`ldflags` 指向 sysroot，无 `include_dirs` 指向 sysroot；被测源码与桩层无 `__OHOS__` / `__MUSL__` / `OHOS_PLATFORM`。
- `stubs/include/codecvt` 遮蔽标准头，为 NDK libc++ 缺失 `<codecvt>` 而补；被测源码 4 个 .cpp 用 `wstring_convert<codecvt_utf8_utf16<char16_t>>`。本机 libc++ 18 自带 `<codecvt>`（已实测编译运行）。
- `run_tests.sh` 硬编码 `OUT=$ROOT/out_win`、`LD_LIBRARY_PATH=/mnt/d/ohos_tools/.../x86_64-linux-ohos`、musl loader 检查；`build.sh` 全部子命令转发 `cmd.exe /c cd /d D:\code\call_manager_gn_test && build.cmd`。
- `third_party/googletest`、`third_party/cjson` 是 mode 160000 gitlink，无 `.gitmodules`；本机已按 gitlink 指向的 commit 检出。
- `telephony_call_manager/` 仅 `.gitkeep`；`test/base/` 不存在。
- 本机已装：`clang-18 libc++-18-dev libc++abi-18-dev lld-18 ninja-build gcc musl`（musl 此后无用）、`/usr/local/bin/gn`。

## Goals / Non-Goals

**Goals:**
- `build/` 与脚本层零 OHOS/Windows/`/mnt/d` 字面量；用 grep 即可验证（spec「编译命令零 OHOS 残留」场景）。
- 工具链定义与主机解耦到"只依赖 PATH 里有 clang-18"的程度，不再有 profile 概念。
- 全新 clone → 三条命令 → GATE PASS。

**Non-Goals:**
- 不追求与任何 OHOS 版本的 ABI/行为一致；不保留切回 NDK 的开关（保留开关就是保留残留）。
- 不改 `ohos.gni` 的 blocklist/force-includes 策略；仅在实测报错时最小调整。
- 不把 gn/ninja/clang 的安装脚本化进仓（README 写 apt 命令即可）。

## Decisions

### D1. 单一 `host_clang` toolchain，删除 profile 机制
**选择**：`build/toolchain/BUILD.gn` 只留 `toolchain("host_clang")`，命令直接写 `clang-18` / `clang++-18` / `llvm-ar-18`，编译加 `-stdlib=libc++`，链接加 `-stdlib=libc++ -fuse-ld=lld-18`（可选，缺 lld 时回退默认 ld）；删除 `profiles.gni` 与 `host_os_profile` arg；`BUILDCONFIG.gn` 指向新 toolchain。
**备选**：(a) 保留 `host_os_profile` 加一个 `host` 分支——违背"零残留"目标，且 win/wsl 分支无人能用；(b) 用 gn arg `cc`/`cxx` 让用户指定编译器——增加一层间接，当前只有一台机器、一种编译器，YAGNI。
**理由**：残留清理的验收是"grep 不到"，任何保留分支都会破坏它。

### D2. 标准库用 libc++ 而非 libstdc++
**选择**：`-stdlib=libc++`。
**备选**：libstdc++（gcc 默认，clang 也能链）。
**理由**：现有 `_pc_common_cflags_cc` 告警黑名单、`ohos.gni` 的 force-includes、`ohos_gtest_shim.h` 都在 libc++ 下调过；换 libstdc++ 会引入一批新告警/头差异（如 `<codecvt>` 的 deprecated 属性形态不同），与本 change 目标无关。目标平台最终是 ARM 工具链，PC 门禁选哪个 STL 都不代表目标，选改动最小的。

### D3. 删除 `stubs/include/codecvt`，不做条件保留
**选择**：直接删；`-include codecvt` 保留在 `_pc_force_includes`，解析到 libc++ 真头。
**备选**：保留桩并加 `#if __has_include(<codecvt>)` 之类的探测——桩文件本身就叫 `codecvt`，`__has_include` 会命中自己，探测无意义。
**理由**：libc++ 18 有 `<codecvt>`（deprecated 但存在），`-Wno-deprecated-declarations` 已在黑名单里。若实测出现 `codecvt_mode` 枚举值差异等问题，改被测代码不在本 change 范围，届时回退为保留桩并在 design 记录。

### D4. `run_tests.sh` / `build.sh` 的输出目录约定
**选择**：两者共用 `OUT_DIR="${OUT_DIR:-out}"`，路径相对 `test/`；`build.sh` 不再转发，直接 `gn gen "$OUT_DIR"`（首次或 `gen`）+ `ninja -C "$OUT_DIR" mustpass_tests`，`run` 调 `run_tests.sh`，`clean` 删 `$OUT_DIR`。`run_tests.sh` 删除 musl 检查与 `LD_LIBRARY_PATH`，保留 `LD_PRELOAD` 与 `CM_QUIET=1`。
**备选**：让 `run_tests.sh` 读 gn 的 `--args` 或 `args.gn` 推导目录——过度设计。
**理由**：一个环境变量足够，且两脚本用同一表达式避免再次出现 `out_win` 式漂移。

### D5. `//base/telephony/call_manager` 用仓内相对符号链接
**选择**：`test/base/telephony/call_manager -> ../../../telephony_call_manager`，提交进 git（mode 120000）。
**备选**：(a) 在 `.gn` 或 GN arg 里重映射 `//base/telephony` 到 `//../telephony_call_manager`——GN 不支持源根之外的 `//` 路径，除非把源根提到仓根，那会让 `//tests`、`//stubs` 等全部改名；(b) 复制一份到 `test/base/telephony/call_manager`——副本再复制，两份漂移。
**理由**：spec 已写明"需要 symlink 或等价手段"；相对链接在任何 clone 位置都成立；Windows 检出需 `core.symlinks=true`，但 Windows 侧链路本 change 已废弃，可接受。

### D6. 副本从基线复制而非 submodule / subtree
**选择**：`rsync -a --exclude=.git ../telephony_call_manager/ telephony_call_manager/`，一次性快照（基线检出在 `OpenHarmony-v6.0-Release`），提交后打 tag `baseline-unmodified`。
**备选**：submodule 指向 openharmony 仓——裁剪要改副本内容，submodule 会把改动推回上游仓的语义，与"只读基线"冲突。
**理由**：`config.yaml` 已规定"副本从只读基线复制而来，裁剪与修改都在此进行"，本 change 只是执行它。基线 tag `OpenHarmony-v6.0-Release`（`f99813be`）记入 tag message 与 README，便于日后 diff。

### D7. third_party 补 `.gitmodules`，不改为 vendor
**选择**：新增 `.gitmodules` 声明两个 submodule（url 为 GitHub 上游），commit 指针保持仓内现有 gitlink 值不变。
**备选**：删 gitlink、把源码 vendor 进仓——googletest 约 30 MB 工作树，膨胀仓库；且原作者意图显然是 submodule。
**理由**：最小修复；`README` 快速开始第一步写 `git submodule update --init`。

### 与 config.yaml design 规则的对应
- 被裁剪功能的代码层处理方式：本 change 不裁剪任何功能，四选一不适用。
- 受影响的 `callmanager.gni` 条目与 `bundle.json` features：无——副本与基线逐字节一致，未触碰任何 GN/feature。
- 并发改动：无；ffrt 桩与锁语义原样保留。

## Risks / Trade-offs

- [musl → glibc 行为差异使某套件失败] → 先跑门禁看结果；差异若在桩层（如 `stubs/src/dlfcn.cpp`、`secure_zero.cpp`）就在桩层修；若在被测代码则记录为"已知差异"并排除该套件，**不**在本 change 改副本源码。
- [本机 libc++ `<codecvt>` 与桩在 `codecvt_mode` 等细节上不同导致编译错] → 见 D3 回退路径。
- [clang 18 比 NDK clang 15 多出的新告警被 `-Werror` 放大] → 被测 GN 若带 `-Werror`，由 `_pc_blocklist` 追加剔除；不新增 `-Wno-*` 到黑名单以外的位置。
- [`-fuse-ld=lld` 在某些机器不可用] → 首版不用 lld，默认 ld 即可；只在链接时间成为问题时再加。
- [符号链接在 Windows 检出损坏] → README 注明仅支持 Linux 主机；Windows 链路已整体废弃。
- [副本 8 MB 进仓] → 一次性成本，可接受；后续裁剪只会缩小它。
- [两个 in-flight change 都对 `pc-test-harness` 写 delta] → 本 change 先归档；`trim-call-manager-for-watch` 的 delta 里「原仓位置」场景已指向 `communication_mcu/telephony_call_manager/`，语义一致，归档时按 MODIFIED 规则以后者覆盖前者即可。

## 实施中发现（任务 4.1 首次编译失败的根因与处置）

工具链替换本身成功：`gn gen` 通过，编译命令零 OHOS 残留。但对副本（= 基线 `master@24e1785f`）编译时 146 个目标文件失败，全部是**桩层落后于基线**，与工具链无关：

- 缺头：`voip_call_state_info.h`、`display_manager_lite.h`、`audio_stream_manager.h`、`openssl/rand.h`
- 缺宏/枚举/方法：`HILOG_COMM_INFO/WARN/ERROR`、`SIM_SLOT_COUNT_MD`、`TELEPHONY_ERR_ARGUMENT_NULL`、`STREAM_USAGE_VOICE_TRANSFER_*`、`AudioSystemManager::GetVirtualCall`、`CoreServiceClient::GetSimTelephoneNumber/GetShowNumber`、`TelephonyPermission::GetAppIdentifier`、`SimType::PSIM`、`SimLabel::index`、`KeyEvent::KEYCODE_MEDIA_PLAY_PAUSE`、`AAFwk::String`、`OsAccountManager::GetOsAccountLocalIdFromUid` 返回类型
- `nlohmann::json` 桩缺 `value()`/`push_back()`/`erase()`/`operator<`

用同一套桩对上游各 ref 做 API 指纹比对，**桩层与 `OpenHarmony-v6.0-Release` tag 完全吻合**（有 `nearlink_call_client`，无 `HILOG_COMM_*`/`GetVirtualCall`/`SIM_SLOT_COUNT_MD`）；`v6.1` 起开始出现缺项，`master` 全部缺。原作者的"109/109"是对 v6.0-Release 得出的，不是 master。

用 v6.0-Release 快照做了一次一次性探针构建（未提交任何东西）：868/868 编译通过；门禁 8 套件中 7 套全绿，`distributed_communication_test` 2 例失败，根因是 `tools/dl_shim.c` 对 `libtelephony_ext_innerkits.z.so` 发假句柄而测试假定该库不存在；在 interposer 里为该库单独返回 NULL 后 48/48 通过，其他依赖假句柄的套件不受影响。

**两条路：**

- **A. 基线改为 `OpenHarmony-v6.0-Release`**：只读基线 `../telephony_call_manager` checkout 该 tag，副本重新 rsync；桩层只需改 `dl_shim.c` 一处；`config.yaml`「基线 = master 克隆」与 `trim-call-manager-for-watch` 中按 master 统计的数字（会议引用 77 处等）需重新核对。优点：稳定发布版更适合做移植基线，工作量约半天内收口。
- **B. 保持 `master@24e1785f`**：补齐上述约 25 项桩 API（新增 4 个头、扩 ~10 个既有桩头、重写 nlohmann json 桩的一部分），再跑门禁看运行期还有多少差异。优点：与 config.yaml 现状一致。缺点：工作量估计 1～2 天，且 master 持续漂移，桩层要长期追。

### D8. 采用 A：基线固定到 `OpenHarmony-v6.0-Release`（`f99813be`）
用户在 2026-09-24 确认继续；按推荐方案 A 执行。落地：`git -C ../telephony_call_manager checkout OpenHarmony-v6.0-Release`（detached HEAD，工作树干净），副本重新 rsync，`config.yaml` 的基线描述改为该 tag。`trim-call-manager-for-watch` 与 baseline specs 中按 master 考证的数字列为归档后跟进项（见 proposal「Impact」）。

### D9. `dl_shim.c` 增加"不存在列表"而非全局改 NULL
**选择**：`kAbsentLibs[]` 按子串匹配库名，命中返回 NULL；其余 `*.so` 维持假句柄。首个条目 `libtelephony_ext_innerkits`。
**备选**：(a) 全部返回 NULL——`voice_assistant` / `zero_branch5` / `special_branch2` 依赖假句柄语义，会大面积失败；(b) 在 `run_tests.sh` 用 `--gtest_filter` 排除这 2 例——掩盖问题且门禁计数与上游不一致。
**理由**：上游测试对不同库有不同预期，interposer 是唯一能按库名区分的位置；实测改后 `distributed_communication_test` 48/48，其他套件不受影响。

## Migration Plan

1. 环境准备（本机已完成）：apt 安装 clang-18/libc++/ninja/gcc，`gn` 二进制到 `/usr/local/bin`。
2. 副本落地：rsync 基线 → `telephony_call_manager/`，建 `test/base/telephony/call_manager` 符号链接，`.gitmodules`。
3. 工具链替换：改 `build/toolchain/BUILD.gn`、删 `profiles.gni`、改 `BUILDCONFIG.gn`、删 `stubs/include/codecvt`。
4. 脚本替换：重写 `build.sh`、修 `run_tests.sh`、删 `build.cmd`/`setup_wsl.cmd`。
5. `bash tools/build_shim.sh && bash build.sh all`，迭代到 GATE PASS。
6. 文档：README、`docs/liteos_sdk_mapping.md`。
7. 提交并打 tag `baseline-unmodified`。

回滚：整个 change 在独立提交上，`git revert` 即可；NDK 路径不再保留，回滚等价于回到"一条命令跑不起来"的状态。
