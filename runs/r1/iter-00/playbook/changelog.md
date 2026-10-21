# Changelog — playbook v1（首次生成，基础：iter-0 学生得分 71/100 与评委缺口明细）

说明：本版为第一版 playbook，无历史版本，全部为新增规则；每条注明所针对的 `student_wrong` 缺口 id（`student_defensible` 与 `reference_questionable` 缺口不设规则）。

- [新增] Phase 0「裁剪清单工作表（唯一事实源）」规则：AGENTS 功能范围逐条建表，proposal/delta/design 全部从表派生，杜绝"宣告不迁移但 delta 保活行为"的不自洽 — 针对 trim_scope/crs-video-ring-chain-kept、trim_scope/dead-esim-bt-branch-kept。
- [新增] 「构建面独立能力」规则：gni/declare_args/bundle.json/sa_profile/测试 target 必须有基线能力与 delta 承载，不允许只散落在 design — 针对 baseline_coverage/build-system-capability-missing。
- [新增] 「基线函数清单覆盖检查」规则：核心类成员函数清单逐一核对（含服务门面散行为锚点 rg 法），配合接口头纯虚函数全集当清单 — 针对 baseline_coverage/service-entry-behaviors-missing。
- [新增] 「判定链展开到外部依赖叶子」规则：ShouldXxx/IsXxx/CanXxx/NeedXxx 谓词逐环展开，每个分支独立成场景 — 针对 baseline_coverage/incoming-rejection-oobe-dnd-missing。
- [新增] 「AGENTS 措辞分级」规则：「不支持…无需迁移」=删除，「暂不支持/暂不调用/依赖后续」=保留代码+桩化，以 AGENTS/config.yaml 的"不能因为无外部接口而丢弃功能"为判据，VoIP 依此定稿且各 artifact 不得摇摆 — 针对 trim_scope/voip-deleted-instead-of-stubbed（唯一高严重度缺口）。
- [新增] 「宏零引用单宏 rg + 负结论二次复核」规则：不允许多宏拼一条大正则；构建文件/frameworks/sa_profile 必须在扫描范围；换命令复验后才可下"零引用"结论 — 针对 code_level_design/auto-start-optimize-misclassified。
- [新增] 「delta 质检三查」规则：涟漪清扫（不迁移功能符号 sweep 全部输出物）、被删能力上游反查（不留悬空转发/死链）、一致性 grep（同一 wrapper 各文件只许一种说法） — 针对 code_level_design/removed-feature-ripple-inconsistent、trim_scope/crs-video-ring-chain-kept、trim_scope/dead-esim-bt-branch-kept、code_level_design/cellular-call-connection-contradiction。
- [新增] 「适配决策表先行」规则：wrapper 类去留、桩名/todo 标签在派工前一次性定稿并逐字附给每个子代理 — 针对 code_level_design/cellular-call-connection-contradiction。
- [新增] 「行为保持默认原则」规则：AGENTS 未明令改变的行为一律照基线保留、出口用桩，禁止无依据收敛/改语义（如状态上报双路） — 针对 trim_scope/state-report-dual-path-converged。
- [新增] 「MODIFIED 带全部基线场景名 + 场景规模核控」规则：改行为沿用原场景名改写 WHEN/THEN、不新增近义变体，仅差参数值的场景合并，delta 场景数与基线基本持平 — 针对 readability_rules/scenario-duplication。
- [新增] 「基线场景为移植着想」规则：预计 liteOS 上整组消失的分支在基线就集中于独立 Requirement，delta 才能整条 REMOVED 而非逐场景改写 — 针对 readability_rules/scenario-duplication（并服务 trim_scope 各缺口的收口方式）。
- [新增] 「需人工复核不豁免 gtest」规则：复核标记之外每个行为改动仍配自解释用例，安全行为（ECC 拨号豁免/强制不静音/查卡判定）成组具名 gtest — 针对 testability_grounding/ecc-gtest-missing。
- [新增] 「子代理派工单协议 + 主线程采信纪律」规则：派工单带函数级覆盖硬性要求，子代理返回结构化摘要并上浮模糊点、禁止静默决定；主线程对关键能力做抽查复核（计划覆盖类缺口的流程根因：服务入口行为与拒接语义缺失源于子代理浅读+主线程零复核，仅设为通用兜底，辅助 baseline_coverage/service-entry-behaviors-missing、baseline_coverage/incoming-rejection-oobe-dnd-missing）。
- [新增] 「收尾自检清单」规则：validate 双跑（全域+单 change）、status 全 done、git 路径边界、名字反查、涟漪清扫终跑一遍后按裁剪清单核销 — 兜底上述全部缺口的最终验证环节。