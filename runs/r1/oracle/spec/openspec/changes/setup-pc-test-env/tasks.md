# Tasks

> 工作目录均为 `communication_mcu/`（本仓根）；`test/` 下命令另注。门禁命令：`cd test && bash build.sh all`，期望 `MUST-PASS GATE: PASS`。
> 1～3 组完成前门禁无法运行，各组以 `gn gen` 成功为阶段验收；第 4 组起以门禁 PASS 为完成条件。
> 只改本仓；`../telephony_call_manager/` 只读。

## 1. 副本与源码位置落地

- [ ] 1.0 只读基线切到 `OpenHarmony-v6.0-Release`：`git -C ../telephony_call_manager checkout OpenHarmony-v6.0-Release`（design D8）；验证 `git -C ../telephony_call_manager rev-parse --short HEAD` 为 `f99813be`，`status --short` 为空
- [ ] 1.1 `rsync -a --delete --exclude=.git ../telephony_call_manager/ telephony_call_manager/`，删除 `.gitkeep`；验证 `diff -rq --exclude=.git ../telephony_call_manager telephony_call_manager` 无输出，且 `git -C ../telephony_call_manager status --short` 为空（基线未被碰）
- [ ] 1.4 `openspec/config.yaml` 基线描述由"master 克隆"改为"tag OpenHarmony-v6.0-Release（f99813be）"，并注明桩层与该 tag 对齐；验证 `rg -n "v6.0-Release" openspec/config.yaml` 命中
- [ ] 1.2 创建相对符号链接 `test/base/telephony/call_manager -> ../../../telephony_call_manager`；验证 `readlink test/base/telephony/call_manager` 输出该相对路径，`ls test/base/telephony/call_manager/BUILD.gn` 存在
- [ ] 1.3 新增 `.gitmodules`，声明 `test/third_party/googletest`（url `https://github.com/google/googletest.git`）与 `test/third_party/cjson`（url `https://github.com/DaveGamble/cJSON.git`），不改 gitlink 指针；验证 `git submodule status` 输出两行且 sha 分别为 `283c1756…` 与 `fb16e5c…`，无 `-`/`+` 前缀

## 2. 工具链替换（零 OHOS 残留）

- [ ] 2.1 重写 `test/build/toolchain/BUILD.gn`：单一 `toolchain("host_clang")`，cc/cxx 用 `clang-18`/`clang++-18` 加 `-stdlib=libc++`，alink 用 `llvm-ar-18`，solink/link 用 `clang++-18 -stdlib=libc++`；删除 `-target`、`--sysroot`、`import("profiles.gni")`；验证 `gn format --dry-run` 通过
- [ ] 2.2 删除 `test/build/toolchain/profiles.gni`；`test/build/config/BUILDCONFIG.gn` 改为 `set_default_toolchain("//build/toolchain:host_clang")` 并更新注释；验证 `rg -n "ohos_ndk|host_os_profile|profiles.gni" test/build test/.gn test/BUILD.gn` 无输出
- [ ] 2.3 删除 `test/stubs/include/codecvt`；验证 `ls test/stubs/include/codecvt` 不存在，`rg -n "STUB_CODECVT" test/` 无输出
- [ ] 2.4 `cd test && gn gen out` 成功；验证 `rg -n "^\s*command =" out/toolchain.ninja | rg -i "ohos|sysroot|musl|/mnt/d|D:/"` 无输出，且 `rg -n -i "ohos|sysroot|musl|/mnt/d|D:/" test/build/toolchain test/build/config` 无输出（`build/ohos.gni` 的模板名不在检查范围）

## 3. 脚本入口替换

- [ ] 3.1 重写 `test/build.sh`：`OUT_DIR="${OUT_DIR:-out}"`；`build`/`gen`/`rebuild`/`clean`/`run`/`all` 全部本机执行（`gn gen`、`ninja -C "$OUT_DIR" mustpass_tests`、`run_tests.sh`），删除 `WINPROJ`/`cmd.exe`/`fwd`；验证 `bash build.sh gen && bash build.sh clean` 分别创建与删除 `out/`，`bash build.sh bogus` 打印 usage 并 rc=2
- [ ] 3.2 修改 `test/run_tests.sh`：`OUT="$ROOT/${OUT_DIR:-out}"`；删除 `CXXRUN`/`LD_LIBRARY_PATH` 与 musl loader 检查；缺 interposer/二进制时的提示改为 `bash tools/build_shim.sh` / `bash build.sh`；验证 `rg -n "musl|out_win|/mnt/d|cmd.exe|WINPROJ" test/build.sh test/run_tests.sh` 无输出
- [ ] 3.3 删除 `test/build.cmd`、`test/setup_wsl.cmd`；验证 `ls test/*.cmd` 无匹配

## 4. 编译与门禁

- [ ] 4.1 `cd test && bash tools/build_shim.sh && bash build.sh build` 编译 `mustpass_tests` 成功；如遇 clang 18 新告警被 `-Werror` 放大或 libc++ 头差异，仅在 `build/ohos.gni` 的 `_pc_blocklist`/`_pc_common_cflags_cc` 内最小调整并在 design.md「Risks」追加记录；验证 `ninja -C out mustpass_tests` 以 rc=0 结束且 8 个测试二进制存在
- [ ] 4.2 在 `test/tests/src/sanity_test.cpp` 新增用例 `SanityTest.HostLibcxxCodecvtRoundTripsUtf16`（用 `std::wstring_convert<std::codecvt_utf8_utf16<char16_t>, char16_t>` 把 `u"手表"` 转 UTF-8 再转回，断言相等）与 `SanityTest.NotBuiltForOhosTarget`（`static_assert`/`EXPECT_FALSE` 未定义 `__OHOS__`，且 `__linux__` 与 `_LIBCPP_VERSION` 已定义）；验证 `out/obj/tests/sanity_test --gtest_filter='SanityTest.HostLibcxx*:SanityTest.NotBuilt*'` 两例 PASS
- [ ] 4.2b `tools/dl_shim.c` 增加 `kAbsentLibs[]`（首项 `libtelephony_ext_innerkits`），命中返回 NULL 句柄（design D9），`bash tools/build_shim.sh` 重建；验证 `distributed_communication_test` 48/48 PASS（含 `Telephony_DcManagerTest_001`、`Telephony_DcManager_SwitchToSinkDevice`），且 `voice_assistant`/`zero_branch5`/`special_branch2` 仍全绿
- [ ] 4.3 `bash build.sh all` 输出 `MUST-PASS GATE: PASS`（8 套件 rc=0、fail=0）；若某套件因 musl→glibc 差异失败：桩层可修则修桩并在 design.md 记录，被测代码问题则在 README「已知差异」登记并停下向用户报告，不改副本源码；验证门禁输出与各 `/tmp/gn_<suite>.$UID.log` 中 `[  FAILED` 计数为 0
- [ ] 4.4 无需 `LD_LIBRARY_PATH` 即可运行：验证 `env -u LD_LIBRARY_PATH LD_PRELOAD=test/tools/libohos_dl_shim.so test/out/obj/tests/sanity_test` rc=0

## 5. 文档与提交

- [ ] 5.1 重写 `test/README.md`：标题与"目录""快速开始""设计要点"去掉 NDK/Windows/MSYS2/musl；快速开始改为 `apt install clang-18 libc++-18-dev libc++abi-18-dev ninja-build gcc` + gn 二进制 + `git submodule update --init` + `bash tools/build_shim.sh` + `bash build.sh all`；注明仅支持 Linux 主机、基线 tag `OpenHarmony-v6.0-Release`（`f99813be`）；验证 `rg -n -i "ndk|msys|out_win|/mnt/d|D:\\\\|cmd\.exe|musl" test/README.md` 无输出
- [ ] 5.2 修改 `test/docs/liteos_sdk_mapping.md`「本次落地」一节：改为本机 clang-18 + libc++ 描述，原 NDK 段落移入「历史决策（已废弃）」小节并写明废弃原因（目标平台已变为 LiteOS/MCU，NDK 仅贡献通用 clang/musl/libc++）；验证 `rg -n "已废弃" test/docs/liteos_sdk_mapping.md` 命中
- [ ] 5.3 `git add -A && git commit`，提交信息说明工具链替换与副本落地；`git tag -a baseline-unmodified -m "telephony_call_manager copy == openharmony/telephony_call_manager OpenHarmony-v6.0-Release (f99813be); host clang gate PASS"`；验证 `git status --short` 为空，`git tag -l baseline-unmodified` 命中，门禁在该提交上仍为 PASS
