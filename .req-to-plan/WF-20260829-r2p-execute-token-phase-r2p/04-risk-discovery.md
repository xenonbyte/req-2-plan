---
r2p_stage: risk_discovery
r2p_version: 3
r2p_status: approved
r2p_created_at: 2026-08-29T14:01:34.734301+00:00
r2p_updated_at: 2026-08-29T15:08:31.264602+00:00
---

# Risk Discovery

## Risks
### RISK-PERF-001 — targeted verification 规则过宽或过窄
Status: mitigated
Mitigation basis: 已选 mitigation 给出可审计的 shared/core/high-risk 升级条件，并保持 final full suite 兜底。

### RISK-CTX-002 — 零继承历史导致角色缺少必要约束
Status: mitigated
Mitigation basis: 已选 mitigation 要求全新零历史 invocation、自包含 handoff，以及无法保证时 fail closed。

### RISK-METRIC-003 — metrics 漂移成第二状态源或伪精确数据
Status: mitigated
Mitigation basis: 已选 mitigation 使 metrics non-authoritative，固定 measured/unavailable 语法并禁止 Token 推算。

### RISK-IO-004 — context view 扩大可信输入攻击面
Status: mitigated
Mitigation basis: 已选 mitigation 使用 pinned directory fd、no-follow pre-stat/open/fstat、WorkId/run/status 校验并覆盖 race。

### RISK-CONTRACT-005 — human/JSON 输出或字节口径不稳定
Status: mitigated
Mitigation basis: 已选 mitigation 固定 source 顺序、分隔符、UTF-8 byte 公式、human/JSON shape、exit code 和 no-partial-output。

### RISK-AUDIT-006 — 报告压缩丢失 concern 或 deferred evidence
Status: mitigated
Mitigation basis: 已选 mitigation 固定持久与 inline 审计字段，并要求每条 concern 与 `⚠️ DEFER` 双写。

### RISK-GRAN-007 — cohesive slice 规则造成过大任务或追踪断裂
Status: mitigated
Mitigation basis: 已选 mitigation 固定独立验证、评审、回滚三项判据和正反边界，同时禁止修改 PLAN schema/gates。

### RISK-PROFILE-008 — fast 资格判断含糊导致高风险运行降级
Status: mitigated
Mitigation basis: 已选 mitigation 固定 LIGHT/no-modifier 结构门与逐任务 semantic gate，任何 false/unknown 在 mutation 前拒绝。

### RISK-RESUME-009 — implemented marker 与现有复选框语义冲突
Status: mitigated
Mitigation basis: 已选 mitigation 固定 task-state segments、BASE chain、精确 grammar 和一次原子 final migration。

### RISK-FINAL-010 — fast final reviewer 输入缺失或负载过大
Status: mitigated
Mitigation basis: 已选 mitigation 按 profile 固定输入，fast final 是逐任务 primary review 并无条件运行 full suite。

### RISK-PARITY-011 — 多平台执行表面发生语义漂移
Status: mitigated
Mitigation basis: 已选 mitigation 固定 Claude/Codex 锁步、OpenCode 派生测试和 Gemini truthful fail-closed 摘要。

### RISK-SEQUENCE-012 — Phase 3 在无代表性基线时提前落地
Status: mitigated
Mitigation basis: 已选 mitigation 将三个 finalized archived strict runs 设为 Phase 3 源码修改前的强制证据 gate。

## Boundaries
- SCOPE-IN-001 [ADDRESSED] 验证节奏只能减少 task-level 重复，不能取消 final full suite。
- SCOPE-IN-002 [ADDRESSED] 历史最小化不得改变 fresh implementer、串行写分支和独立 reviewer 的 strict 边界。
- SCOPE-IN-003 [ADDRESSED] metrics 是 append/update 的本地观测记录，不参与 workflow 正确性判断。
- SCOPE-IN-004 [ADDRESSED] context view 只做确定性读取、过滤和组装，不写 run、不生成语义结论。
- SCOPE-IN-005 [ADDRESSED] 紧凑输出的最低审计字段和 `⚠️ DEFER`/concern 保留是硬约束。
- SCOPE-IN-006 [ADDRESSED] 只调整任务形成规则，不调整 PLAN 字段、trace、gate 或 checkbox 含义。
- SCOPE-IN-007 [ADDRESSED] strict 默认行为必须兼容；Phase 3 以真实 Phase 0 metrics 为进入条件。
- SCOPE-IN-008 [ADDRESSED] fast 必须显式选择、资格 fail closed、角色仍为 fresh implementer 加 final reviewer。
- SCOPE-IN-009 [ADDRESSED] fast 的 implemented 状态不能冒充 reviewed complete，异常必须升级 strict recovery。
- SCOPE-IN-010 [ADDRESSED] 两个主要模板面、派生面、CLI 与测试必须在同一变更切片内同步。

## Scope Overflow Risks
- SCOPE-OUT-001 [OUT-OF-SCOPE] 不把模型降档、缩短 reasoning 或不透明缓存列为验收手段。
- SCOPE-OUT-002 [OUT-OF-SCOPE] 不通过共享会话、并行写当前分支或 batch reviewer 减少角色数。
- SCOPE-OUT-003 [OUT-OF-SCOPE] 不增加持久化上下文制品及其同步协议。
- SCOPE-OUT-004 [OUT-OF-SCOPE] 不放松 final review/full suite、Git/BASE、archive 和 dirty-tree 安全边界。
- SCOPE-OUT-005 [OUT-OF-SCOPE] 不扩张为三档以上 profile 设计。
- SCOPE-OUT-006 [OUT-OF-SCOPE] 需求拆解和后续实现均不隐含远程 mutation 授权。

## Mitigations
- RISK-PERF-001 [ADDRESSED] 在模板中列出 full-suite escalation trigger，并在 metrics 中记录实际 verification scope/reason/duration；final reviewer 无条件全量验证。
- RISK-CTX-002 [ADDRESSED] 每个角色提示成为自包含启动协议，由角色在自身上下文执行确定性 context view，再读取 task brief/PLAN 和 Git 状态。
- RISK-METRIC-003 [ADDRESSED] metrics 与 progress 分文件；字段区分 measured、unavailable，不接受 estimated-as-actual；所有 gate 继续只信既有权威文件。
- RISK-IO-004 [ADDRESSED] 复用 WorkId/run 解析和 `read_regular_text`，逐源 fail closed；为 symlink、non-regular、missing、race 和越界 work ID 增加测试。
- RISK-CONTRACT-005 [ADDRESSED] 规定固定 source 顺序、UTF-8 字节口径、分隔格式和 JSON schema，并用 golden/结构测试覆盖 human 与 JSON。
- RISK-AUDIT-006 [ADDRESSED] 定义紧凑模板的强制字段；concerns 与 `⚠️ DEFER` 原样保留，final reviewer 读取所有 task report/review（fast 仅 report）。
- RISK-GRAN-007 [ADDRESSED] 用独立验证、评审、回滚三项判据及反例约束 cohesive slice，同时保持现有机器解析字段不变。
- RISK-PROFILE-008 [ADDRESSED] strict 为默认；fast eligibility 同时检查 tier、modifier 和语义条件，任何未知/异常都 fail closed 并切回 strict。
- RISK-RESUME-009 [ADDRESSED] 为 profile、implemented marker、BASE/HEAD 单调链和恢复选择器写解析测试；只有 final 批准才能置 `[x]`。
- RISK-FINAL-010 [ADDRESSED] final 输入契约按 profile 分支；fast 不要求 task review 文件，但必须逐任务记录结论、检查最终 diff 并运行完整套件。
- RISK-PARITY-011 [ADDRESSED] Claude/Codex 同步修改并由 docs-consistency token/行为测试锁定；验证 OpenCode 派生结果和 Gemini 可表达的入口提示。
- RISK-SEQUENCE-012 [ADDRESSED] 把三样本证据设为 Phase 3 任务的显式前置条件；样本不足时 Phase 3 不得实现或验收。

## Trace
<!-- Map this stage's IDs to upstream/downstream. R3 derives & checks closure. -->
| This ID | Upstream | Status |
|---|---|---|
| Risk headings above | Requirement brief scope and acceptance criteria | [ADDRESSED] Risks cover verification cost, context transfer, metrics trust, I/O safety, audit integrity, task granularity, profile eligibility, resume, final review, parity, and sequencing. |

## Upstream Summary (read-only)
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
