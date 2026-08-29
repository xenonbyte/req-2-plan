# Intake Brief

work_id: WF-20260829-r2p-execute-token-phase-r2p
requirement: 需求名称：r2p-execute 性能与 Token 成本优化（Phase 0–3）。

背景与目标：
当前 r2p-execute 对每个 PLAN 任务使用 fresh implementer、逐任务 reviewer 和 final reviewer。质量与安全结果可接受，但一个只改少量类的需求也会产生较长执行时间和较高 Token 消耗。已审查的代表性 4 任务运行中，最低需要 9 次角色调用，完整测试套件实际运行 9 次；按归档最终快照重建的静态输入约 902,676 bytes。该数字是重建快照，不等同于精确历史 Token 流。目标是在不削弱最终质量、安全边界和可恢复性的前提下，分阶段降低重复上下文、重复验证和角色调用成本，并建立可量化的性能基线。

总体交付策略：
将以下 Phase 0、Phase 1、Phase 2、Phase 3 拆成四个可独立验证、评审、回滚和交付的变更切片；后续阶段不得阻塞前面阶段独立落地。Phase 3 只能在至少收集 3 个具有代表性的执行样本后进入实现决策与验收。

Phase 0：低风险立即优化与度量。
1. 统一 implementer 与 task reviewer 的验证节奏：任务内默认只运行 targeted tests 或直接受影响测试；仅当任务触及 shared/core/high-risk 区域、出现不确定性或 targeted verification 无法建立充分信心时，才运行完整测试套件。final reviewer 始终运行完整测试套件。
2. Codex 子代理采用零继承历史语义（例如 fork_turns none）；其他平台在能力允许时使用等价的最小历史传递。不得共享 implementer 会话。
3. 新增 execution/metrics.md 作为独立于 progress.md 的本地执行度量，不改变 progress ledger 的硬解析契约。至少记录 role、task、model（可得时）、开始结束时间、elapsed、实际交付给该角色的 ACS/context bytes、验证范围与耗时、report bytes、状态、concerns、fix waves；平台能暴露 Token 时再记录 Token，不能暴露时不得估算成真实 Token。
4. Claude 与 Codex 的 r2p-execute 模板语义必须同步，OpenCode 派生面保持一致，相关文档一致性测试同步更新。

Phase 1：减少重复上下文与报告体积。
1. 新增统一只读命令 r2p-context-view --work-id <id>，首版不提供 --role。
2. 命令必须实时读取 02-project-context.md、03-requirement-brief.md、04-risk-discovery.md、05-design.md、06-spec.md 和 execution/progress.md，并使用现有 strip_nonsemantic_markdown 去除非语义 Markdown；所有可信输入继续走 symlink-safe regular-file read。
3. 默认 human mode 向 stdout 输出合并后的语义内容；R2P_JSON=1 时输出至少包含 sources、raw_bytes、semantic_bytes、content 的稳定结构。
4. 不生成持久化 task-N-context.md、context bundle、manifest、hash 或 drift 检查，避免复制事实源。子代理必须在自己的上下文中调用该命令，控制器不得先读取完整 ACS 后转发。
5. 本需求明确取代旧归档需求中仅针对该旧改动的 no new CLI 限制；CLI 不生成语义摘要，只做确定性过滤与组装，继续保持 CLI 管状态和结构、agent 写语义内容的架构边界。
6. 压缩 task report 和 task review 的模板与读取契约，保留 commit/base/head、实际文件、验证证据、状态、concerns 以及所有 ⚠️ DEFER 信息；不得因压缩丢失任何 concern 或 deferred evidence。final reviewer 必须读取全部紧凑输出。

Phase 2：调整 PLAN 任务粒度规则。
1. 将 PLAN 任务拆分原则从按文件或过细步骤，调整为一个 cohesive change slice：任务内部语义内聚，能够独立验证、独立评审、独立回滚。
2. 不改变 PLAN task schema、trace closure、质量 gate、复选框语义或现有执行恢复基础字段。
3. 更新生成模板、agent 表面与测试，使该粒度成为可执行规则，避免把同一行为链拆成多个高度重复上下文的小任务，也避免形成无法独立验证的大任务。

Phase 3：基于度量引入 strict 与 fast 两种执行 profile。
1. strict 保持现有安全语义并作为默认：N 个 fresh implementer + N 个逐任务 reviewer + 1 个 final reviewer；STANDARD、带 modifier、边界不清或不满足 fast 条件的运行必须 strict。
2. fast 必须显式选择，且仅适用于 LIGHT、无 modifier、局部、机械性强、具有确定性验证手段的任务。fast 的最低角色结构为 N 个 fresh implementer + 1 个 final reviewer，不共享 implementer，不增加中间 batch reviewer。
3. fast 的 progress ledger 使用 profile-aware 状态：记录 Execution Profile: fast；实现完成后记录 Task N: implemented (commits <base7>..<head7>, verification recorded)，但复选框保持 [ ]，只有 final reviewer 逐任务批准后才批量更新为 [x]。
4. fast resume 选择第一个既没有 reviewed complete 也没有 implemented marker 的任务。Task 1 的 BASE 来自 Execution BASE；后续任务从前一个合法 implemented marker 推导 BASE，并继续保持每任务 BASE 的捕获、校验和提交边界纪律。若提交存在但 marker 缺失、HEAD 与 marker 分叉、验证失败、出现 concern、unexpected file、上游歧义或 shared/core 风险，必须升级到 strict recovery，对所有 implemented-but-unreviewed 任务补做逐任务评审。
5. fast final reviewer 是 primary review：读取经过确定性压缩的 ACS、PLAN、progress、所有 task report 和最终 diff；不得要求不存在的 task-N-review.md；逐任务审查并运行完整测试套件。全部批准后才写 final-review.md、将任务复选框置为 [x] 并允许 archive。
6. strict 与 fast 之外不新增 balanced profile；Phase 0 和 Phase 1 已承担中间档优化。

必须保留的安全与兼容性约束：
保留 dirty-tree 防护、Execution BASE 和逐任务 commit/diff 边界、symlink-safe reads、路径限定 git 操作、resume/recovery、final whole-branch review、final full suite、final Verdict: Approved gate、archive gate、不得未经用户授权 commit/push/PR 或修改远程状态。不得并行写当前分支，不得使用共享 implementer，不得用更便宜模型作为主要优化方案，不得让 LLM 摘要成为事实源，不得删除 final review 或 final full suite。

验收与验证：
每个 Phase 先补失败测试再实现；使用项目规定的 .venv/bin/python -m pytest 路径运行 targeted tests，并在各 Phase 最终验证时运行完整 tests/ 套件。验证 Codex/Claude 两套模板锁步、OpenCode 派生行为、CLI human/JSON 输出、symlink/race 安全、progress 解析与 archive gate、strict 兼容、fast resume/升级/最终批准状态机。文档明确记录度量口径，其中 context bytes 是实际交付给角色的字节数，重建快照与真实历史流不得混称。

## Tier Estimate
base: standard
modifiers: cross_project, dependency, migration, safety, scope_expanding

## Evidence Block
keywords_hit: ['升级到', 'python', '项目', 'project', '删除', '实时', '角色', 'token', 'role', 'token', '调用', '全部', '所有', '批量', 'whole', 'full']
repo_baseline_summary: loc=26328, modules=3, monorepo=False, languages=['Python', 'JavaScript']
linked_context: - execution/metrics.md: local_missing
  error: File not found: /Users/xubo/x-skills/req-to-plan/execution/metrics.md
- execution/progress.md: local_missing
  error: File not found: /Users/xubo/x-skills/req-to-plan/execution/progress.md
scope_signals: ['全部', '所有', '批量', 'whole', 'full']
escalation_candidates: ['migration', 'cross_project', 'safety', 'dependency']
confirm_status: pending