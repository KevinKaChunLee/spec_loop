# 评分报告

总分 **90.5**（满分 100）。其中代码判定 63.9 分、模型判定 26.6 分（代码占比 71%）。

| 维度 | 权重 | 得分(0-5) | 组成 |
|---|---|---|---|
| agents_compliance | 10 | 4.8 | agents_compliance 0.96 |
| open_decisions | 15 | 5.0 | open_decisions 1.00 |
| baseline_coverage | 35 | 4.23 | module_coverage 1.00，behaviour_coverage 0.84，requirements_correctness 0.80 |
| code_level_design | 15 | 4.3 | build_coverage 1.00，design_quality 0.80 |
| testability_grounding | 15 | 4.68 | grounding_rate 0.92，task_rules 0.88，scenario_quality 1.00 |
| readability_rules | 10 | 4.64 | rule_checklist 0.98，readability 0.80 |

## 决策对照

settled = AGENTS.md 已定（参考取 AGENTS.md 的值、模块裁剪、无引用的宏），只检验是否遵守 AGENTS.md；open = AGENTS.md 未定或参考另作决定。

| 分组 / 类别 | 条目 | 代码一致 | 裁定计为一致 | 一致率 |
|---|---|---|---|---|
| open | 6 | 5 | 1 | 1.00 |
| settled | 101 | 93 | 4 | 0.96 |
| modules | 22 | 21 | 1 | 1.00 |
| features | 24 | 24 | 0 | 1.00 |
| macros | 34 | 26 | 4 | 0.88 |
| dependencies | 22 | 22 | 0 | 1.00 |
| architecture | 5 | 5 | 0 | 1.00 |

### 不一致项与裁定

| id | 分组 | 参考 | 学生 | 裁定 | 严重度 | 理由 |
|---|---|---|---|---|---|---|
| `module/services/call_setting` | settled | modify | keep | student_defensible | low | 两侧迁移结果一致：均按 AGENTS「特性宏支持范围」说明 1 保留 UT/USSD/USSD/MMI 补充业务，cellular_call 出口经 CellularCallClient 桩、设置项 DataShare 查询 todo，差异仅在裁剪范围表的标签。reference 因其设计（CallSettingManager 直接改调 CellularCallClient，替代 cellularCallConnectionPtr_ 转发）标「修改」，student 因该目录自身代码零改动（适配器改造落在 telephony-interaction）标「保留」；源码中 call_setting_manager.cpp 确实只经 DelayedSingleton<CellularCallConnection>::GetInstance() 转发，两种归因均有依据，属同一结果的不同表达。 |
| `macro/ABILITY_NOTIFICATION_SUPPORT` | settled | remove | unguard | student_defensible | medium | AGENTS.md 两条规则对此文件真实冲突：「特性宏支持范围」把该宏列入不支持宏（代码无需迁移），「外部依赖处理」却规定 NotificationHelper 调用点迁移时以 todo 注释占位、待通知接口适配。student 保留观察者并把发布/撤销点 todo 桩化，reference 整文件删除，两读法各有条文支撑；且行为等价（IsFullScreen 恒 false，liteOS 上均不真正发通知）。注意 PublishNotification 调用点本就无宏守卫（仅 Cancel 分支受宏控制），「调用点用 todo 占位」规则只能落在 student 的保留方案上。 |
| `macro/ABILITY_DISPLAY_SUPPORT` | settled | remove | unguard | student_defensible | low | 两 spec 对该宏守卫代码的实质处置相同：DisplayManager::IsFullScreen 调用均不迁移、IsFullScreen() 恒返回 false（等价基线默认构建，该宏在仓内 gni 从未定义），仅提取值标签不同（unguard vs remove）。文件整体去留的差异已由 ABILITY_NOTIFICATION_SUPPORT 争议覆盖，本条本身无实质分歧。 |
| `macro/ABILITY_CELLULAR_SUPPORT` | settled | unguard | keep | student_defensible | low | 该宏唯一场点 cellular_call_connection.cpp:147 仅守卫 ReConnectService 的单次重连判定，student 的 pc-test-harness delta 与 tasks 7.5 明确保留兼容层注入 ABILITY_CELLULAR_SUPPORT=0x1，与 reference 的 gni 恒定义在规格定义的构建（PC 门禁）中同为生效。AGENTS 规定的 CellularCallClient::GetInstance().Xxx() 桩形态位于守卫之外、两者均存活，实际差异仅剩 gni 机制（部件条件块照抄 vs 恒定义），影响很小。 |
| `macro/ABILITY_SMS_SUPPORT` | settled | unguard | keep | student_wrong | high | AGENTS 把该宏列入支持宏并规定 sms_mms 交互「使用SmsClient::GetInstance().Xxx()的形式替代、对应接口通过打桩实现」，但 student 保留 global_parts_info 部件条件块且兼容层仅注入 ABILITY_CELLULAR_SUPPORT（liteOS 无 sms_mms 部件、PC 构建无 global_parts_info），reject_call_sms.cpp:37 守卫内的 SmsClient 桩发送在规格定义的一切构建中均为死代码，拒接短信功能被静默丢弃，其自身「发送条件」场景也不可达，违背「不能因为无外部接口而丢弃功能」与支持宏语义。reference 恒定义使该链路存活。 |
| `macro/CELLULAR_DATA_SUPPORT` | settled | unguard | keep | student_wrong | medium | call_number_utils.cpp:256 守卫内正是 AGENTS 规定的 CellularDataClient::GetInstance().GetDefaultCellularDataSlotId() 桩回退，student 的构建设计（部件条件块照抄、兼容层不注入该宏）使其恒被编译裁掉，SelectAccountId 静默失去默认数据卡这最后一级回退，违背支持宏语义与 cellular_data 替代规则。reference 恒定义使该回退存活，属单函数内局部分支的差异。 |
| `macro/ABILITY_POWER_SUPPORT` | open | remove | keep | reference_questionable | high | AGENTS「特性宏支持范围」明确把 ABILITY_POWER_SUPPORT 列入支持宏，「外部依赖处理」对功耗锁的规定是调用点以 todo 注释占位而非删文件，但 reference 把该 gni 块归入「gni 不支持块」删除（design D12、tasks 3.1）并整体删除 incoming_call_wake_up.*（tasks 2.4），「来电亮屏与运行锁」完整功能被无条文依据地移除——功能范围不支持清单只有贴耳灭屏（proximity_sensor），并无来电亮屏。student 保留观察者并把 RunningLock/WakeupDevice 调用点 todo 桩化，更贴合 AGENTS 的支持宏与 todo 占位规定。 |
| `macro/TELEPHONY_CUST_SUPPORT` | settled | unguard | keep | student_wrong | medium | call_data_base_helper.cpp:451（QueryContactInfoEnhanced）与 call_status_manager.cpp:702（后缀匹配增强分支）守卫内正是 AGENTS 规定的 TelephonyCustClient::GetInstance() 桩替换落点，student 的构建设计使该宏在一切已定义构建中不被定义，增强查询分支与 cust 桩全部成为死代码，违背支持宏语义与「与TelephonyCust模块进行通信时使用TelephonyCustClient::GetInstance().Xxx()的形式替代」的规定。reference 恒定义使该分支存活；差异限于联系人查询的一条增强分支，属局部差异。 |
| `macro/OHOS_BUILD_ENABLE_TELEPHONY_CUST` | settled | unguard | keep | student_wrong | high | 该宏守卫 TelephonyCustWrapper 的初始化与 IsChangeDialNumberToTwEmc_ 改号判定（call_manager_service.cpp:52/90/319），是整条 TelephonyCust 定制链的开关（通话记录隐藏判定也依赖 wrapper 初始化）。student 保留部件条件块且不注入该宏，整链在规格定义的构建中失效，AGENTS 规定的 TelephonyCustClient::GetInstance().Xxx() 桩形态成为死代码，整条定制功能被静默丢弃；reference 恒定义使整链存活。 |

## 代码检查

- 模块目录覆盖：1.00；未覆盖：无
- 行为覆盖：0.84（参考 baseline 引用的 1295 个 HMOS 名称中覆盖 84%；学生共引用 2517 个，折算系数 1.0）
- 引用接地率：0.920
- tasks 规则：0.88（{"gate": 1.0, "gtest": 0.9, "gni_sync": 0.727}）
- callmanager.gni / bundle.json 覆盖：1.00（design 点名 1.0，构建词覆盖 1.00）
- 规则清单：0.98
  - design_decision_structure = 0.818 9/11 decisions have 决策/理由/落点

## 软性评审（模型）

# 软评分报告：migrate-call-manager-to-liteos（学生 vs 参考）

## 总体结论

学生规格的总体质量高于"弱模型"预期，多数维度与参考实现实质等价，部分地方甚至更准确：基线规格对源码的抽查（含多处高风险论断与具体行号）全部与 `telephony_call_manager/` 一致，且学生正确记录了若干上游怪癖（`ProximitySensor` 在仍有通话时灭屏、`IsTwoCallESIMCall` 恒 false、`SetDialingCallProcessing` 的 PostTask 返回值反判、`GetBindTime` 每次刷新、`SetCallPreferenceMode` 缺判空），其中贴耳灭屏一处参考实现反而写反了。主要扣分集中在工件内部一致性与可读性：一处同一决策两种说法（AppStateObserver 的保留/删除在两个 delta 里互相矛盾）、design D6 与 OQ6 对 spam 三文件处置相左、以及 delta 以"全文复述"方式呈现（161/275 条需求标 MODIFIED，约 4148 行）导致人工评审负担显著高于参考的手术式 delta；另有基线里混入两条面向 liteOS 的"预计移除面"需求和一处虚构函数名 `CallControlManager::InitEvents`（实为 `CallStateObserve()`）。安全相关行为（紧急呼叫、拒接链）场景与 gtest 任务齐备且有强制门禁条款，是学生的突出优点。

## 分项得分

| 部分 | 得分 | 一句话理由 |
| --- | --- | --- |
| requirements_correctness | 4 | 事实准确度极高、判定链逐分支展开且多处优于参考；小缺口：基线混入 2 条迁移预览需求（非 HMOS 现状、场景不可测）与 1 处虚构函数名 |
| scenario_quality | 5 | 732 个场景均有具体触发与可观察结果，delta 逐需求标注具名 gtest 落点；ECC/拒接场景与任务门禁齐备，无凑数场景 |
| design_quality | 4 | 删除/宏/桩/锁/直调架构的代码级落点与跨工件一致性极强；扣在 AppStateObserver 处置两说（中）及 spam 文件处置、ffrt 音频队列漏列、TimeWaitHelper 单线程语义、tasks fuzz 清单等数处轻微不一致 |
| readability | 4 | proposal/design 表格化、开放问题真实、复核标注清晰；但 delta 全文复述式写法（未变场景逐字照抄）使实际改动埋在 4000 余行中，评审负担高于参考 |

## 分项缺口（按严重度排序）

### requirements_correctness → baseline_coverage

1. **[低] 基线混入迁移预览需求**（student_wrong）
   - 参考：基线只写 HMOS 现状，无任何迁移预告。
   - 学生：`native-client-api` 与 `call-utils` 两个基线规格各含一条"手表移植预计移除面"需求，描述 liteOS 迁移计划，场景写"具体由裁剪 delta 决定"，无法落 gtest，违反 task.md"describe what the HMOS module does today"。
   - 裁定：学生错。迁移面应由 change 的 proposal/delta 承载，不应进基线。程度有限（2/275 条），扣为小缺口。
   - 证据：`_inputs/student/openspec/specs/native-client-api/spec.md`、`.../call-utils/spec.md` 末条需求。

2. **[低] 虚构函数名 `CallControlManager::InitEvents`**（student_wrong）
   - 参考：写"由 `CallControlManager` 经 `callStateListenerPtr_->AddOneObserver` 注册"，未点错函数。
   - 学生：`call-report` 基线与 delta 的"状态监听接入"需求均引用不存在的 `InitEvents`；实际注册发生在 `CallStateObserve()`（`call_control_manager.cpp:1648`），且学生自己的 `call-control-management` 规格用的是正确名。
   - 裁定：学生错（虚构引用 + 自相矛盾），但行为描述正确、仅 2 处，属小缺口。
   - 证据：源码 `call_control_manager.cpp:1648`；`_inputs/student/.../specs/call-report/spec.md`。

### scenario_quality → testability_grounding

无实质性缺口。学生场景的可测性（具名套件/用例族落点、`tasks 5.2`"ECC 豁免链必须整组具名 gtest 全过才算完成"、`tasks 9.1` ECC 判定链复核）不低于参考，安全相关行为（紧急呼叫、拒接）场景与 gtest 任务完备。

### design_quality → code_level_design

1. **[中] AppStateObserver 处置同一决策两种说法**（student_wrong）
   - 参考：一致地移除"UI 进程死亡监听"，`AppStateObserver` 与注册点不迁移（call-report delta REMOVED）。
   - 学生：`call-report` delta 删除 `app_state_observer.cpp/.h` 并声明注册点不迁移；但 `call-control-management` delta 的"VoIP 状态注入与畅连冲突"场景却写"IDLE/UNKNOWN 时注销 `ApplicationStateObserver`，否则经 `AppStateObserver` 向 `AppMgr` 注册应用状态观察者（照抄保留）"。
   - 裁定：学生错——同一决策在两个 delta 中一删一留，实施者无所适从；学生自己的基线与源码（`call_control_manager.cpp:1587-1609`）说明该注册真实存在，必须二选一。这是 rubric 明列的"a decision stated two ways"缺口。
   - 证据：`_inputs/student/.../specs/call-control-management/spec.md:422` vs `.../specs/call-report/spec.md` REMOVED 条。

2. **[低] spam 三文件处置两说**（student_wrong）
   - 参考：`SpamCallProxy/SpamCallStub` 不迁移，检测结果改由桩/默认值供给（单一口径）。
   - 学生：design D6 表写"spam_call_proxy/stub/connection 文件删除"，而 OQ6 与 spam delta、tasks 5.4 默认"保留可编译最小形"。
   - 裁定：学生错，但 OQ6 已将其登记为开放问题并给出默认值，矛盾部分被缓解，降为低。
   - 证据：`_inputs/student/.../design.md` D6 骚扰来电行 vs Open Questions 6。

3. **[低] design 的 ffrt 枚举漏掉音频场景队列**（student_wrong）
   - 参考：design D6 明确列出 `reportAudioStateChangeQueue`（`audio_scene_processor.cpp`）。
   - 学生：design D6/D8 只列 `report_call_info_handler` 等四处与音频无关的 ffrt 点，音频队列仅出现在 audio delta 里。
   - 裁定：学生错（design 落点清单不全，delta 已兜住），低。
   - 证据：`_inputs/student/.../design.md` D8 vs `.../specs/audio-device-management/spec.md`。

4. **[低] TimeWaitHelper 单线程阻塞语义未裁决**（student_wrong）
   - 参考：design D7 明确"TimeWaitHelper 保留骨架（单线程下等待立即按超时返回）"。
   - 学生：spam delta 保留 `cv_.wait_until` 阻塞等待语义，与 design D8"桩内同步逐条执行、不新增线程"组合后，响一声/骚扰检测窗口会阻塞唯一线程 3-5 秒，未显式裁决该冲突。
   - 裁定：学生欠考虑（默认配置下 database 桩失败使开关关闭，影响有限），低。
   - 证据：`_inputs/student/.../specs/spam-call-identification/spec.md` vs `_inputs/reference/.../design.md` D7。

5. **[低] tasks 7.4 的 fuzz 删除清单与 delta 不符**（student_wrong）
   - 参考：无此问题（fuzz 处置单点）。
   - 学生：tasks 7.4 称删除"conference/bluetooth/satellite/antifraud/spam connection 系 fuzz"target，但基线 19 个 fuzz target 中不存在这些；`build-config` delta 给出的实际删除清单（6 个 + voice assistant fuzzer 目录）才是对的。
   - 裁定：学生错（任务清单与 delta 两种说法），低。
   - 证据：`_inputs/student/.../tasks.md` 7.4 vs `.../specs/build-config/spec.md`。

### readability → readability_rules

1. **[中] delta 全文复述式写法**（student_wrong）
   - 参考：手术式 delta，只写真正变化的需求（MODIFIED 63 条、REMOVED 59 条，总量约 1040 行），评审一眼可见改动。
   - 学生：275 条基线需求中 161 条被标 MODIFIED，未变化场景逐字照抄并加"（照抄）"注记，变更总量约 4148 行；单能力 delta 达 300-500 行（call-control-management 504 行 vs 参考 59 行），实际改动埋在逐句括注中，人工需自行 diff。
   - 裁定：学生错但可辩护——OpenSpec MODIFIED 需求本就要求全文，且学生几乎每条需求文本都插入了桩/todo 引用、注释体系系统化；然而"无裁剪点、行为照抄"的需求也整段复述，属 rubric 明列的"repeated content"，构成中等评审负担。proposal/design 层的可读性仍然优秀。
   - 证据：metrics（delta MODIFIED 161 vs 63）；`_inputs/student/.../specs/call-control-management/spec.md`（504 行）vs `_inputs/reference/.../specs/call-control-manager/spec.md`（59 行）。

## 参考实现疑似问题（供人工复核，不扣学生分）

1. **[中] ProximitySensor 行为写反**：参考基线称"CallDestroyed 且 `HasCallExist()` 为假时灭屏"，源码实为"为真时 `ShutDown`、为假时不操作"（`proximity_sensor.cpp:36-42`）；学生如实记录了这一上游反直觉现状。
2. **[中] 功耗锁/亮屏观察者处置存疑**：参考删除 `incoming_call_wake_up.cpp` 并把 `ABILITY_POWER_SUPPORT` 的 gni 块列入"删块"，但 AGENTS 将 `ABILITY_POWER_SUPPORT` 列为支持宏、要求功耗锁调用点 todo 占位，且参考自身 D4/D12 也写"功耗锁调用点按 D4 todo 占位"——参考内部自相矛盾，疑似过度裁剪；学生保留观察者并以 [powerLock] todo 桩化，与 AGENTS 更一致。
3. **[中] 新通话（Celia）链疑似漏裁**：AGENTS 功能范围明确"新通话"不支持，但参考的 `call-manager-service` delta 保留 `EVENT_IS_CELIA_CALL`→`dealCeliaCallEvent`、`EVENT_CELIA_AUTO_ANSWER_CALL_ON/OFF` 路由，tasks 7.6 写"celia 事件保留"；学生移除该链并用 rg 证明 `IsNewCallAllowed` 与新通话无关而单独保留。
4. **[低] call-setting 行理由不实**：参考 proposal 写"设置项 DataShare 查询 todo 占位"，但 `services/call_setting/` 无任何 DataShare 使用（其 delta 也未提）。
5. **[低] RTT"文件节点"表述不准**：参考 D14 将本仓 `StartRtt/StopRtt` 的 IPC 转发称为"文件节点读写调用点"；本仓 RTT 链路无文件节点操作（文件节点在 cellular_call 侧），学生表述更精确；两者实际处置一致，仅标签失真。
