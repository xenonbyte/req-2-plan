# Requirement Brief

## Goal
在保持 `r2p-execute` 现有质量、安全边界、Git 边界和恢复能力的前提下，按四个可独立交付的 Phase 降低重复上下文、重复验证和不必要角色调用造成的执行时长与 Token 成本，并建立可用于决定是否启用 fast profile 的可审计度量基线。

## In-Scope
- SCOPE-IN-001 Phase 0：统一任务内验证节奏，implementer 与 task reviewer 默认运行 targeted/directly affected tests，仅在 shared/core/high-risk、出现不确定性或 targeted verification 不足时运行完整套件；final reviewer 始终运行完整套件。
- SCOPE-IN-002 Phase 0：Codex 子代理采用 `fork_turns="none"` 的零继承历史语义，其他平台在能力允许时采用等价最小历史传递；implementer 会话保持 fresh 且不共享。
- SCOPE-IN-003 Phase 0：新增独立于 `execution/progress.md` 的 `execution/metrics.md`，记录角色、任务、可得的模型信息、起止时间、elapsed、实际交付 context bytes、验证范围与耗时、report bytes、状态、concerns、fix waves，以及平台真实暴露时的 Token。
- SCOPE-IN-004 Phase 1：新增只读 `r2p-context-view --work-id <id>`，实时、symlink-safe 地读取 ACS 与 progress，使用 `strip_nonsemantic_markdown` 做确定性过滤，并提供 human stdout 与 `R2P_JSON=1` 的稳定 JSON 输出。
- SCOPE-IN-005 Phase 1：让子代理在自己的上下文中调用 context view；不生成持久化上下文副本；压缩 task report/review，同时完整保留提交边界、文件、验证、状态、concerns 和所有 `⚠️ DEFER` 证据。
- SCOPE-IN-006 Phase 2：把 PLAN 任务粒度约束调整为可独立验证、评审和回滚的 cohesive change slice，并同步生成模板、agent 表面与测试，不改变现有 PLAN task schema 或 trace/gate 契约。
- SCOPE-IN-007 Phase 3：在至少取得 3 个代表性度量样本后，引入默认 `strict` 与显式 opt-in `fast` 两种 profile；strict 保持当前 N implementer + N reviewer + final reviewer 语义。
- SCOPE-IN-008 Phase 3：仅允许 LIGHT、无 modifier、局部、机械且可确定性验证的运行选择 fast；fast 使用 N 个 fresh implementer + 1 个承担 primary review 的 final reviewer。
- SCOPE-IN-009 Phase 3：为 fast 定义 profile-aware ledger、implemented marker、逐任务 BASE 推导、resume、异常升级 strict recovery、最终逐任务批准与 archive 契约。
- SCOPE-IN-010 跨 Phase：Claude 与 Codex 模板语义锁步、OpenCode 派生一致，补齐 CLI、模板、状态恢复、安全读取、gate 和 profile 行为的回归测试与文档。

## Out-of-Scope
- SCOPE-OUT-001 不使用更低成本模型或降低推理质量作为本次主要性能方案。
- SCOPE-OUT-002 不共享 implementer 上下文，不在当前分支并行写入，不引入中间 batch reviewer。
- SCOPE-OUT-003 不让 LLM 摘要成为事实源，不生成 `task-N-context.md`、持久化 context bundle、manifest、hash 或 drift 机制。
- SCOPE-OUT-004 不移除 final whole-branch review、final full suite、`Verdict: Approved` gate、archive gate、dirty-tree 防护、Execution BASE 或逐任务 commit/diff 边界。
- SCOPE-OUT-005 不新增 balanced 或其他第三种执行 profile。
- SCOPE-OUT-006 不在本次需求中执行未经用户授权的提交、推送、PR 或任何远程状态修改。

## Non-Goals
- 不以牺牲 strict 的现有安全语义换取速度。
- 不把确定性 CLI 扩展为语义内容生成器。
- 不冻结某次历史运行的测试数量、耗时或 Token 数为长期通过阈值。
- 不改变与本需求无关的 artifact schema、状态机或仓库工具链。

## Assumptions
- 现有 `strip_nonsemantic_markdown` 与 `read_regular_text` 可分别作为确定性过滤和 symlink-safe 读取的复用基础。
- `execution/` 继续是本地审计轨迹；`metrics.md` 不成为 workflow state 或 archive gate 的第二事实源。
- 代表性样本至少覆盖不同任务数量或变更形态，且 context bytes 使用实际交付字节数；没有平台 Token 数据时明确记为 unavailable，不做伪精确估算。
- 本需求对只读 `r2p-context-view` 的明确授权，取代旧归档需求中仅针对旧改动的 `no new CLI` 限制。

## Acceptance Criteria
1. 四个 Phase 在 PLAN 中形成可按顺序实现、又能独立验证、评审和回滚的 cohesive change slices；Phase 3 明确依赖至少 3 个代表性 metrics 样本。
2. Phase 0 后，task-level 角色默认只运行 targeted/directly affected tests，触发完整套件的条件可审计；final reviewer 仍无条件运行完整套件。
3. Phase 0 后，每个角色调用可在 `execution/metrics.md` 中审计 elapsed、实际 context bytes、验证范围/耗时、输出体积、状态与 concerns；Token 仅记录平台真实值。
4. Phase 1 后，`r2p-context-view --work-id <id>` 的 human 与 JSON 模式均能输出实时确定性语义视图；JSON 至少包含 `sources`、`raw_bytes`、`semantic_bytes`、`content`，且 unsafe/raced input 继续 fail closed。
5. Phase 1 后，不存在新持久化上下文副本；紧凑 report/review 不丢失任何 concern 或 `⚠️ DEFER`，final reviewer 读取全部紧凑输出。
6. Phase 2 后，模板明确要求 cohesive change slice，同时 PLAN schema、trace closure、quality gate、复选框语义和既有恢复基础字段保持兼容。
7. Phase 3 后，strict 仍是默认且与当前行为兼容；不满足 fast 全部资格条件的运行无法进入 fast。
8. fast 能可靠记录 implemented-but-unreviewed 状态，按 Execution BASE/前一合法 marker 恢复；marker 缺失、HEAD 分叉、验证失败、concern、unexpected file、上游歧义或 shared/core 风险均升级 strict recovery 并补做逐任务评审。
9. fast final reviewer 不依赖不存在的 `task-N-review.md`，能够把所有 task report 和最终 diff 作为 primary review 输入，运行完整套件，并仅在逐任务批准后写 final review、勾选任务和允许 archive。
10. 每个 Phase 遵循测试先行，targeted tests 与最终 `.venv/bin/python -m pytest tests/ -q` 通过；Codex/Claude 模板锁步和 OpenCode 派生行为有回归覆盖。

## Open Questions
- 无待用户决策项；具体模块落点和命令注册位置由后续设计阶段依据当前代码证据确定，但不得改变上述行为边界。

## Sources
- 原始需求：`00-raw-requirement.md`。
- 项目上下文：`02-project-context.md`、仓库根 `AGENTS.md` 与当前源码/测试。
- 性能审查：`/Users/xubo/Desktop/r2p-execute-性能审查结论-2026-08-29.md`。
- 修订版评审：`/Users/xubo/Desktop/r2p-execute-修订版评审报告-2026-08-29.md`。
- 修订结论：`/Users/xubo/Desktop/r2p-execute-性能审查结论-修订版-2026-08-29.md`。

## Trace
<!-- Map this stage's IDs to upstream/downstream. R3 derives & checks closure. -->
| This ID | Upstream | Status |
|---|---|---|
| Scope set above | Raw requirement has no stable IDs | [ADDRESSED] Full raw requirement is normalized into the in-scope, out-of-scope, assumptions, and acceptance sections. |

## Upstream Summary (read-only)
需求名称：r2p-execute 性能与 Token 成本优化（Phase 0–3）。

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
<!-- /r2p-read-only -->

## Project Context (read-only)
# Project Context Pack

- repo_root: `/Users/xubo/x-skills/req-to-plan`
- languages: {'Python': 26297, 'JavaScript': 31}
- package_managers: npm, pip
- test_commands: ['npm test']
- entrypoints: ['tools/workflow_cli/__main__.py']
- config_files: ['requirements.txt']
- dependencies (1):
  - pyyaml>=6.0 (pip)
- source_dirs: ['bin', 'docs', 'requirements', 'tests', 'tools']
<!-- /r2p-read-only -->
