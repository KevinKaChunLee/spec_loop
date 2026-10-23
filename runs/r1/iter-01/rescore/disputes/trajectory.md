# Trajectory: disputes iter-01-rescore

- model: GLM 5.3 Max  session: ea9c1a3d-9f03-4e42-b552-96af14a42e66
- finished: True  duration: 14.1 min
- tokens: input 159939, output 76480, cache read 1963390
- tool calls: 42 (read 24, grep 10, shell 5, glob 2, edit 1), failures 2
- HMOS .cpp/.h files read: 8 / 454 (main agent 8)
- subagents: 0  openspec validate runs: 0 (failed 0)
- thinking: 287537 chars  assistant text: 2077 chars

## Steps

**[0001] THINK** (58 chars): Let me start by reading the inputs to understand the task.

[0002] read _inputs/task.md -> 67 lines
[0003] read _inputs/disputes.json -> 317 lines
**[0004] THINK** (9388 chars): Let me understand the disputes. There are 8 entries: 1. `module/services/call_setting`: reference says modify, student says keep. This is about the trim value for the module directory. Note that the ruling options here: "student_defensible" covers "a module the reference trims inside a modified capability while the student removes it as a capability of its own" — i.e., differences in how trim is expressed. Actually here both are "keep the functionality", just reference marks module as "modify" (because cellular_call forwarding is stubbed and DataShare queries are todo), while student marks "ke ...[+8764 chars]

[0005] glob -> FAILED {"error": {"error": "Invalid arguments:\nglob_pattern: Invalid input: expected string, received undefined"}} **FAILED**
[0006] shell `find /home/kevin/Work/spec-loop-ws/r1/iter-01-rescore-disputes -maxdepth 2 -type d | sort` -> exit 0, 36 lines
**[0007] THINK** (91 chars): Let me look at the structure of _inputs/reference and _inputs/student openspec directories.

[0008] shell `ls -R /home/kevin/Work/spec-loop-ws/r1/iter-01-rescore-disputes/_inputs/reference/openspec /home/kevin/Work/spec-loop-ws/r1/iter-01-rescore-disputes/_inputs/student/openspec | head -100` -> exit 0, 100 lines
[0009] shell `ls /home/kevin/Work/spec-loop-ws/r1/iter-01-rescore-disputes/_inputs/student/openspec/changes/migrate-call-manager-to-liteos/specs/ 2>/dev/null; echo ---; ls /home/kevin/Work/spec-loop-ws/r1/iter-01-rescore-disputes/_inputs/student/openspec/specs/ 2>/dev/null` -> exit 0, 51 lines
**[0010] THINK** (656 chars): The student's baseline specs include `call-setting-management` but the change specs list doesn't show `call-setting-management`. Interesting — the student has `call-setting-management` in baseline specs (25 dirs) but in changes specs there's no `call-setting-management` — which likely means the student decided the `services/call_setting` module is "kept" (no delta spec needed, since behavior is unchanged). That matches the dispute #1: student says "keep" for the call_setting module. Now, let me check the source of truth. First the HMOS source: `telephony_call_manager/callmanager.gni` — wait, t ...[+55 chars]

[0011] glob -> FAILED {"error": {"error": "Invalid arguments:\nglob_pattern: Invalid input: expected string, received undefined"}} **FAILED**
[0012] grep /ABILITY_NOTIFICATION_SUPPORT|ABILITY_DISPLAY_SUPPORT/ in telephony_call_manager -> 2 matches in 1 files
[0013] read telephony_call_manager/services/call/call_state_observer/src/incoming_call_notification.cpp -> 115 lines
[0014] shell `find /home/kevin/Work/spec-loop-ws/r1/iter-01-rescore-disputes/telephony_call_manager -name "*.gni" -o -name "BUILD.gn" | sort` -> exit 0, 37 lines
**[0015] THINK** (562 chars): Interesting. In `incoming_call_notification.cpp`: - `CancelIncomingCallNotification()` has `#ifdef ABILITY_NOTIFICATION_SUPPORT` → calls `NotificationHelper::CancelNotification(...)`; without the macro it returns `TELEPHONY_SUCCESS`. Note the `PublishIncomingCallNotification` uses `Notification::NotificationHelper::PublishNotification(request)` WITHOUT a macro guard. - `IsFullScreen()` has `#ifdef ABILITY_DISPLAY_SUPPORT` → calls `DisplayManager::IsFullScreen()`; without it returns `false`. Now let me look at callmanager.gni to see how macros are defined.

[0016] read telephony_call_manager/callmanager.gni -> 309 lines
**[0017] THINK** (4536 chars): Very useful. Key observations from `callmanager.gni`: 1. `ABILITY_NOTIFICATION_SUPPORT` is NOT defined anywhere in callmanager.gni. So the student's claim "仓内 gni 无定义" (the repo's gni has no definition) is correct — the macro is never defined in this repo's gni. So `#ifdef ABILITY_NOTIFICATION_SUPPORT` in `incoming_call_notification.cpp` always evaluates false in this snapshot. Similarly `ABILITY_DISPLAY_SUPPORT` — not in gni either. Let me verify by grepping for these macros across the repo. 2. `ABILITY_CELLULAR_SUPPORT` is defined when `global_parts_info.telephony_cellular_call` part exists. ...[+3923 chars]

[0018] read _inputs/reference/openspec/changes/migrate-call-manager-to-liteos/proposal.md -> 77 lines
**[0019] THINK** (139 chars): Reference proposal: `call-setting` | 修改 | 转发 cellular_call 的接口改打桩客户端，设置项 DataShare 查询 todo 占位. Now the student's proposal. Let me read it.

[0020] read _inputs/student/openspec/changes/migrate-call-manager-to-liteos/proposal.md -> 83 lines
**[0021] THINK** (2357 chars): The student's proposal table says `call-setting-management | 保留 | UT 补充业务（呼转/呼限/等待/USSD/MMI）须支持（AGENTS 说明第 1 条）；行为不变，cellular_call 出口桩化体现在 telephony-interaction`. So the student does keep the call_setting functionality and treats the cellular_call exit stubbing in telephony-interaction, and DataShare queries — hmm, does the student handle the DataShare setting query (settings_datashare_helper) todo? Let me check the student's design and spec for call-setting / call_utils. The dispute is about the trim value for the module directory `services/call_setting`: reference says "modify", student says ...[+1751 chars]

[0022] grep /Connection|DataShare|GetInstance|Helper/ in telephony_call_manager/services/call_setting/src/call_setting_manager.cpp -> 59 matches in 1 files
[0023] grep /ABILITY_CELLULAR_SUPPORT|ABILITY_SMS_SUPPORT|CELLULAR_DATA_SUPPORT|ABILITY_POWER_SUPPORT|TELEPHONY_CUST_SUPPORT|OHOS_BUI ...[+24 chars]/ in telephony_call_manager -> 32 matches in 15 files
**[0024] THINK** (710 chars): Now let me look at the actual usage of each of these macros in the source to understand what "keep both branches" vs "unguard" means: 1. `ABILITY_SMS_SUPPORT` in `reject_call_sms.h:20` and `reject_call_sms.cpp:37` — let me look. 2. `ABILITY_CELLULAR_SUPPORT` in `cellular_call_connection.cpp:147`. 3. `CELLULAR_DATA_SUPPORT` in `call_number_utils.cpp:256`. 4. `ABILITY_POWER_SUPPORT` in several files (incoming_call_wake_up, proximity_sensor, call_control_manager). 5. `TELEPHONY_CUST_SUPPORT` in `call_data_base_helper.h/cpp`, `call_status_manager.cpp`. 6. `OHOS_BUILD_ENABLE_TELEPHONY_CUST` in `cal ...[+108 chars]

[0025] read telephony_call_manager/services/call/call_state_observer/src/reject_call_sms.cpp offset=25 limit=80 -> 59 lines
[0026] read telephony_call_manager/services/telephony_interaction/src/cellular_call_connection.cpp offset=130 limit=60 -> 1022 lines
**[0027] THINK** (5591 chars): So the `#ifdef` usages: - `reject_call_sms.cpp:37`: `#ifdef ABILITY_SMS_SUPPORT` guards the actual `SmsServiceManagerClient::SendMessage` call. Without the macro, `SendMessage` is a no-op (empty function). The AGENTS.md rule says "与sms_mms模块进行IPC通信时，使用SmsClient::GetInstance().Xxx()的形式替代，对应接口通过打桩实现" — the SMS interaction should be replaced with `SmsClient::GetInstance().Xxx()` stub form. That implies the SMS sending code should be migrated and the call replaced with the stub client — i.e., the guarded code is in effect (unguard/always-defined), with the SmsClient stub. The student's "keep" — ke ...[+4982 chars]

[0028] read _inputs/student/openspec/changes/migrate-call-manager-to-liteos/design.md -> 223 lines
**[0029] THINK** (11156 chars): Now I have a good understanding of the student's design. Key points from D7 macro table: **Supported macros handling in student's design:** - `ABILITY_CELLULAR_SUPPORT` | gni 部件块 + `cellular_call_connection.cpp` | 保留（cellular_call 交互经 D4 桩） - `ABILITY_SMS_SUPPORT` | gni 部件块 + `reject_call_sms.cpp/.h` | 保留（SmsClient 桩） - `CELLULAR_DATA_SUPPORT` | gni 部件块 + `call_number_utils.cpp` | 保留（CellularDataClient 桩） - `ABILITY_POWER_SUPPORT` | gni 部件块 + 7 文件 | gni 保留；功耗锁调用点 todo（proximity_sensor 文件删除） - `TELEPHONY_CUST_SUPPORT` | gni 部件块 + `call_status_manager.cpp`、`call_data_base_helper.cpp` | 保留（DataSh ...[+10527 chars]

[0030] read _inputs/reference/openspec/changes/migrate-call-manager-to-liteos/design.md -> 241 lines
**[0031] THINK** (37939 chars): Now I have both designs. Let me now focus on each dispute. **Dispute 1: `module/services/call_setting` — reference: modify, student: keep.** The reference has a `call-setting` capability (trim: modify), with the reason "转发 cellular_call 的接口改打桩客户端，设置项 DataShare 查询 todo 占位". The student has `call-setting-management` capability (trim: keep), reason "UT 补充业务（呼转/呼限/等待/USSD/MMI）须支持（AGENTS 说明第 1 条）；行为不变，cellular_call 出口桩化体现在 telephony-interaction". The student's change specs don't include a `call-setting-management` delta (consistent with keep = no behavior change in that module). Both keep the modul ...[+37234 chars]

**[0032] SAY**: 现在我来查看两个规范中相关的 delta 规范，以了解每个宏决策的背景信息。

[0033] read _inputs/student/openspec/changes/migrate-call-manager-to-liteos/specs/build-config/spec.md -> 149 lines
[0034] read _inputs/reference/openspec/changes/migrate-call-manager-to-liteos/specs/build-and-feature-flags/spec.md -> 48 lines
**[0035] THINK** (18853 chars): Now I see the student's build-config delta. Key: "### Requirement: callmanager.gni 能力宏块（parts_info 联动）... 保留 6 块——`telephony_sms_mms`（sms_mms:tel_sms_mms_api + `ABILITY_SMS_SUPPORT`）、`telephony_cellular_call`（`ABILITY_CELLULAR_SUPPORT`，交互经 `stub/cellular_call_client` 桩）、`powermgr_power_manager`（power_manager:powermgr_client + `ABILITY_POWER_SUPPORT`，功耗锁调用点 todo [powerLock]）、`telephony_cellular_data`（cellular_data:tel_cellular_data_api + `CELLULAR_DATA_SUPPORT`，经桩）、`telephony_telephony_enhanced`（`TELEPHONY_CUST_SUPPORT`）、`telephony_telephony_cust`（`OHOS_BUILD_ENABLE_TELEPHONY_CUST`，经 `stub/tele ...[+18204 chars]

**[0036] SAY**: 现在我来检查这些宏的实际源码使用点，以确定它们所保护的内容。

[0037] read telephony_call_manager/services/call/call_state_observer/src/incoming_call_wake_up.cpp offset=100 limit=60 -> 136 lines
[0038] read telephony_call_manager/utils/src/call_number_utils.cpp offset=245 limit=30 -> 387 lines
**[0039] THINK** (735 chars): CELLULAR_DATA_SUPPORT guards `CellularDataClient::GetInstance().GetDefaultCellularDataSlotId()` in `SelectAccountId` — the default data slot ID query. AGENTS.md: "与cellular_data模块进行IPC通信时，使用CellularDataClient::GetInstance().Xxx()的形式替代，对应接口通过打桩实现" — this interaction must be migrated in stub form. If the macro is undefined (part absent), this call site is compiled out → the cellular_data interaction form mandated by AGENTS never appears → violates the rule + the "don't drop functionality" rule (SelectAccountId would not fall back to default data slot). Now let me check TELEPHONY_CUST_SUPPORT sit ...[+134 chars]

[0040] read telephony_call_manager/services/call/call_state_observer/src/call_data_base_helper.cpp offset=440 limit=50 -> 525 lines
[0041] read telephony_call_manager/services/call/src/call_status_manager.cpp offset=695 limit=25 -> 2517 lines
**[0042] THINK** (418 chars): TELEPHONY_CUST_SUPPORT guards the enhanced contact query (QueryContactInfoEnhanced via DataShare). Interesting: this is a DataShare interaction — AGENTS says DataShare interfaces 暂不调用 (todo). The student's D7 says "TELEPHONY_CUST_SUPPORT | gni 部件块 + call_status_manager.cpp、call_data_base_helper.cpp | 保留（DataShare/cust 出口 todo 或 Client 桩）". Now the OHOS_BUILD_ENABLE_TELEPHONY_CUST sites in call_manager_service.cpp.

[0043] read telephony_call_manager/services/call_manager_service/src/call_manager_service.cpp offset=45 limit=45 -> 1853 lines
[0044] read telephony_call_manager/services/call_manager_service/src/call_manager_service.cpp offset=305 limit=30 -> 1853 lines
**[0045] THINK** (3009 chars): OK — `OHOS_BUILD_ENABLE_TELEPHONY_CUST` guards the TelephonyCust wrapper usage (Taiwan emergency number rewrite etc.). AGENTS.md: "与TelephonyCust模块进行通信时，使用TelephonyCustClient::GetInstance().Xxx()的形式替代，对应接口通过打桩实现" — the TelephonyCust interaction must be migrated in `TelephonyCustClient::GetInstance().Xxx()` stub form. That means the guarded code (the wrapper usage sites) must be migrated and active — i.e., un-guard / always define. The student's "keep" (part-block conditional) would leave it compiled out unless global_parts_info.telephony_telephony_cust is true in the liteOS build. Now, the cri ...[+2404 chars]

[0046] grep /ABILITY_CELLULAR_SUPPORT|ABILITY_SMS_SUPPORT|CELLULAR_DATA_SUPPORT|TELEPHONY_CUST|OHOS_BUILD_ENABLE|global_parts_info/ in test -> 143 matches in 1 files
**[0047] THINK** (227 chars): The test/base/telephony/call_manager/ is the symlink to the HMOS module (test harness builds the baseline). Let me check where macros get injected in the test harness — search for forced macro injection (defines) in test/build.

[0048] grep /defines \+=|defines =|ABILITY_|_SUPPORT/ in test -> 46 matches in 4 files
**[0049] THINK** (480 chars): The PC test compat layer (`test/build/ohos.gni`) injects `_pc_common_defines = ["ABILITY_BLUETOOTH_SUPPORT=0x1", "ABILITY_CELLULAR_SUPPORT=0x1"]` into targets. So in the current PC test build, only bluetooth and cellular macros are force-defined; the others (SMS, CELLULAR_DATA, TELEPHONY_CUST, etc.) depend on `global_parts_info`, which in the PC build is presumably not defined (or defined by the compat?). Let me check whether global_parts_info is defined in the PC test build.

[0050] read test/build/ohos.gni offset=40 limit=120 -> 315 lines
**[0051] THINK** (2213 chars): Key insight: In the PC test build, `global_parts_info` is NOT defined (that's why the compat layer force-injects `ABILITY_BLUETOOTH_SUPPORT=0x1` and `ABILITY_CELLULAR_SUPPORT=0x1`). So currently, in the PC test build of the baseline: - ABILITY_CELLULAR_SUPPORT is defined (injected) — so `cellular_call_connection.cpp`'s reconnect logic is active. - ABILITY_SMS_SUPPORT is NOT defined → `reject_call_sms.cpp`'s SendMessage call is compiled out in the PC test build today! - CELLULAR_DATA_SUPPORT NOT defined → the default-data-slot fallback in SelectAccountId compiled out. - TELEPHONY_CUST_SUPPORT / ...[+1610 chars]

[0052] read _inputs/student/openspec/changes/migrate-call-manager-to-liteos/specs/pc-test-harness/spec.md -> 48 lines
**[0053] THINK** (2131 chars): The student's pc-test-harness delta says: "兼容层统一注入宏 — **WHEN** 任一业务/测试 target 编译 — **THEN** 追加 `ABILITY_CELLULAR_SUPPORT=0x1`，并依赖 `//stubs:ext_ohos`；`ABILITY_BLUETOOTH_SUPPORT` 不再注入（mini 已无该宏场点，蓝牙链路整体裁剪）". So the student keeps injecting ONLY `ABILITY_CELLULAR_SUPPORT=0x1` (removing bluetooth). ABILITY_SMS_SUPPORT, CELLULAR_DATA_SUPPORT, TELEPHONY_CUST_SUPPORT, OHOS_BUILD_ENABLE_TELEPHONY_CUST are NOT injected in the test build, and the gni part blocks don't fire (no global_parts_info in PC build). So in the student's plan: - `reject_call_sms.cpp`'s `#ifdef ABILITY_SMS_SUPPORT` → compiled out.  ...[+1528 chars]

[0054] read _inputs/student/openspec/changes/migrate-call-manager-to-liteos/specs/call-state-observer/spec.md -> 127 lines
**[0055] THINK** (7307 chars): The student's call-state-observer delta is quite detailed and well-reasoned. Key items: 1. **incoming_call_notification**: "通知逻辑保留，NotificationHelper 发布/撤销调用点以 // todo!!! [notification] 占位... 因 ABILITY_DISPLAY_SUPPORT/ABILITY_NOTIFICATION_SUPPORT 均为不支持宏（AGENTS 特性宏支持范围），宏守卫去守卫处理：DisplayManager::IsFullScreen 调用不迁移、IsFullScreen() 恒返回 false（等价基线默认构建）" — hmm interesting, the student here says "因 ABILITY_DISPLAY_SUPPORT/ABILITY_NOTIFICATION_SUPPORT 均为不支持宏（AGENTS 特性宏支持范围），宏守卫去守卫处理" — they acknowledge these are unsupported macros per AGENTS, and treat them by removing the guards with the *baseline def ...[+6692 chars]

[0056] read _inputs/reference/openspec/changes/migrate-call-manager-to-liteos/specs/call-setting/spec.md -> 22 lines
[0057] read _inputs/student/openspec/changes/migrate-call-manager-to-liteos/specs/telephony-interaction/spec.md -> 161 lines
**[0058] THINK** (4977 chars): Very informative. Interesting notes: 1. The student's telephony-interaction delta explicitly says: "`ReConnectService` SHALL 保留代理为空时执行一次 `ConnectService` 的单次重连语义与 `#ifdef ABILITY_CELLULAR_SUPPORT` 守卫（支持宏与部件保留，design D7 支持宏表）" — the ABILITY_CELLULAR_SUPPORT guard is retained with the part. And the scenarios describe reconnect behavior ("后续每次业务调用经 ReConnectService 单次重试连接判定") — which only works if the macro is defined. Hmm — but with the student keeping the part-block conditional and the PC compat injecting ABILITY_CELLULAR_SUPPORT=0x1, the reconnect IS active in the test build (the compat inject ...[+4369 chars]

[0059] grep /ABILITY_SMS_SUPPORT|CELLULAR_DATA_SUPPORT|TELEPHONY_CUST_SUPPORT|OHOS_BUILD_ENABLE_TELEPHONY_CUST|ABILITY_POWER_SUPPORT| ...[+24 chars]/ in _inputs/student/openspec -> 53 matches in 18 files
**[0060] THINK** (78313 chars): Now I have a fairly complete picture of the student's design for the supported macros. The student's approach is coherent in its own framing: "支持宏原样保留" — keep the macros as-is with their gni part blocks and #ifdef guards; the features become active when the corresponding parts are present in the build; the external interactions are stubbed (SmsClient stub inside the guard, etc.). Their scenarios hedge with "WHEN 宏 X 生效" (when the macro is in effect). But AGENTS.md says: "支持宏（无需显示定义宏）" — the script interprets this as "unguard" (guarded code migrated and in effect: drop the guard, or always defi ...[+77589 chars]

**[0061] SAY**: Let me examine the reference's call-state-observer delta and tasks to verify its treatment of the power/wake-up and notification observers.

[0062] read _inputs/reference/openspec/changes/migrate-call-manager-to-liteos/specs/call-state-observer/spec.md -> 52 lines
**[0063] THINK** (23750 chars): Confirmed. The reference's call-state-observer delta: - REMOVED "来电亮屏与电源锁": `IncomingCallWakeup` 不迁移 (not migrated); Acquire/ReleaseIncomingLock call points kept as no-op placeholders. Reason: "功耗锁接口（ABILITY_POWER_SUPPORT 域）在 liteOS 暂不调用，亮屏/灭屏不在 liteOS 范围". So the reference deletes the whole wake-up observer file — despite AGENTS listing ABILITY_POWER_SUPPORT in the 支持宏 list and prescribing todo placeholders for the power-lock interfaces. - REMOVED "来电全屏通知": IncomingCallNotification 不迁移. - REMOVED "未读未接提醒": MissedCallNotification 不迁移. - MODIFIED "短信拒接": via SmsClient::GetInstance() stub ("ABIL ...[+23096 chars]

**[0064] SAY**: Let me verify the reference's tasks.md and the student's tasks.md for macro handling details.

[0065] grep /POWER|NOTIFICATION|DISPLAY|恒定义|wake|incoming_call/ in _inputs/reference/openspec/changes/migrate-call-manager-to-liteos/tasks.md -> 6 matches in 1 files
[0066] grep /SMS_SUPPORT|CELLULAR_DATA|TELEPHONY_CUST|POWER_SUPPORT|CELLULAR_SUPPORT|宏/ in _inputs/student/openspec/changes/migrate-call-manager-to-liteos/tasks.md -> 7 matches in 1 files
**[0067] THINK** (70451 chars): Confirmed. Key facts: - Reference tasks 2.4: deletes `incoming_call_notification.*`, `incoming_call_wake_up.*`, etc. Task 3.1: unconditionally defines the 5 telephony macros; deletes ABILITY_POWER_SUPPORT block (lumped with unsupported macros). - Student tasks 7.1: keeps the 6 part blocks; 7.5: compat keeps only ABILITY_CELLULAR_SUPPORT=0x1 injection. Task 4.1: adapter conversions. Task 6.1: "SelectAccountId 改 stub/cellular_data_client" — hmm interesting, task 6.1 says SelectAccountId changes to use the cellular_data stub — inside the guard presumably. So the student's spec definitively leaves ...[+69477 chars]

**[0068] SAY**: All the evidence is gathered. Let me do two final verification checks on the call_setting baseline specs before writing the rulings.

[0069] grep /services/call_setting|Purpose|CellularCallConnection/ in _inputs/student/openspec/specs/call-setting-management/spec.md -> 8 matches in 1 files
[0070] grep /services/call_setting|Purpose|CellularCallConnection/ in _inputs/reference/openspec/specs/call-setting/spec.md -> 7 matches in 1 files
**[0071] THINK** (1221 chars): Both baseline specs cover `services/call_setting` and describe the forwarding via `CellularCallConnection`. The dispute #1 is confirmed as a labeling/attribution difference with the same migration outcome (UT supplementary services kept; cellular_call exits via stubs). Interesting: the reference's own baseline `call-setting` spec says "全部转发 CellularCallConnection 同名接口" — but the reference's delta says "经 CellularCallClient::GetInstance() 桩转发同名接口（替代 cellularCallConnectionPtr_ 的 IPC 转发）" — so the reference modifies call_setting_manager.cpp to drop the connection indirection → "modify" label fits ...[+618 chars]

**[0072] SAY**: 两个基线均确认了 `call_setting` 的转发架构。我现在已经掌握了所有裁剪所需的依据。正在写入裁决：

[0073] edit _outputs/rulings.json -> +67 -0
[0074] shell `python3 -m json.tool /home/kevin/Work/spec-loop-ws/r1/iter-01-rescore-disputes/_outputs/rulings.json > /dev/null && echo "JSON OK" && python3 -c " import json d = json.load(open('/home/kevin/Work/spec-loop-ws/r1/iter-01-rescore-disputes/_outputs/rulings.json')) ids = [r['id'] for r in d['rulings']]  ...[+306 chars]` -> exit 0, 3 lines
**[0075] THINK** (269 chars): The file is valid: 9 rulings, one per dispute entry, all fields valid, ids unique and matching the 9 dispute entries. Done. Per the task instructions ("Write `_outputs/rulings.json` and nothing else"), I wrote only that file. Let me give a brief summary of the rulings.

**[0076] SAY**: `_outputs/rulings.json` 已写入并通过 `python3 -m json.tool` 校验（9 条、每条一个裁决）。裁决摘要：

| id | 裁决 | 严重度 | 要点 |
|---|---|---|---|
| module/services/call_setting | student_defensible | low | 双方结果一致（UT 补充业务保留、出口桩化），仅「修改/保留」标签与归因不同：`call_setting_manager.cpp:26` 全部经 `CellularCallConnection` 转发，学生把改造落在 telephony-interaction 属实 |
| macro/ABILITY_NOTIFICATION_SUPPORT | student_defensible | medium | AGENTS 两规则真冲突（不支持宏清单 vs 「NotificationHelper 调用点 todo 占位」）；`PublishNotification` 调用点本就无宏守卫，双方行为等价 |
| macro/ABILITY_DISPLAY_SUPPORT | student_defensible | low | 双方实质相同：`IsFullScreen()` 恒 false、Display 调用不迁移，仅提取值标签不同 |
| macro/ABILITY_CELLULAR_SUPPORT | student_defensible | low | 唯一场点仅守卫重连判定；学生的 PC 兼容层显式保留注入 `=0x1`，与参考恒定义同样生效，桩形态在守卫外均存活 |
| macro/ABILITY_SMS_SUPPORT | student_wrong | high | 部件条件块在 liteOS/PC 构建中永不触发，`reject_call_sms.cpp:37` 守卫内的 SmsClient 桩成死代码，拒接短信功能被静默丢弃，违背支持宏与 sms_mms 替代规则 |
| macro/CELLULAR_DATA_SUPPORT | student_wrong | medium | `call_number_utils.cpp:256` 守卫内的 CellularDataClient 桩回退恒被裁掉，SelectAccountId 失去最后一级回退 |
| macro/ABILITY_POWER_SUPPORT | reference_questionable | high | AGENTS 明确列为支持宏且功耗锁是「todo 占位」而非删文件，参考却删 gni 块并整删 `incoming_call_wake_up.*`，「来电亮屏与运行锁」整功能无依据被移除 |
| macro/TELEPHONY_CUST_SUPPORT | student_wrong | medium | 守卫内即 TelephonyCustClient 桩替换落点（增强查询分支），学生构建使宏恒不定义、分支成死代码 |
| macro/OHOS_BUILD_ENABLE_TELEPHONY_CUST | student_wrong | high | 该宏是 TelephonyCust 整条定制链的开关（wrapper 初始化/改号判定），学生构建设计使整链失效、规定桩形态成死代码 |

判定依据均已核对源码：五个「支持宏」的守卫内容、`callmanager.gni` 部件块、`test/build/ohos.gni` 兼容层注入集（仅 bluetooth+cellular），以及双方 spec 的 build-config / pc-test-harness delta 与 tasks。

