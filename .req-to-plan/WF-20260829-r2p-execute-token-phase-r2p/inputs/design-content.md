# Design

## Design Summary
采用四个顺序化、可独立验证的 cohesive change slices。Phase 0 先修正验证节奏、子代理历史传递和度量结构；Phase 1 增加确定性上下文视图并缩短报告契约；Phase 2 收紧 PLAN 任务形成规则；Phase 3 在当前执行已经形成至少三条代表性角色度量后引入 strict/fast profile。所有状态正确性继续由 `run.md`、`execution/progress.md`、PLAN 复选框和 final-review gate 决定，`execution/metrics.md` 只负责观测。

## Current Code Evidence
- `tools/workflow_cli/agent_templates/{codex,claude}/.../r2p-execute` 当前承载绝大多数执行编排：每任务 fresh implementer、task reviewer、fix loop、final reviewer、BASE/resume 和 archive 协议都属于提示契约，不是 Python orchestrator。
- 当前 Authoritative Context Set 要求每个 implementer/reviewer/fixer 直接完整读取 `02`–`06` 与 `execution/progress.md`；模板中的“可跳过嵌入 read-only block”不能阻止普通整文件读取先把这些字节放入角色上下文。
- `tools/workflow_cli/stage_templates.py` 已在 PLAN 的 `Verification` guidance 中表达 targeted tests 优先和 final review 全量回归，但 task-reviewer 模板没有同等强度的升级条件，历史执行因此仍可重复运行完整套件。
- `tools/workflow_cli/cli.py::_cmd_run_execute_start` 只从 PLAN anchors 生成 `execution/progress.md`；`gates.py::check_execution_complete` 只信复选框，`check_final_review_recorded` 只信 final-review 的最后一个合法 verdict。
- `tools/workflow_cli/agent_shortcuts.py::_cmd_execute` 负责 closed→executing 或 resume 的快捷入口；当前没有 profile 参数，resume 文案固定选择最低未勾选任务。
- `tools/workflow_cli/cli.py::_cmd_plan_task_brief` 已复用 `strip_nonsemantic_markdown`，并用内部 run loader、WorkId 校验和路径检查生成 scoped task brief，证明只读执行辅助命令可以保持 CLI/agent 分层。
- `tools/workflow_cli/atomic.py::read_regular_text` 已提供 lstat、`O_NOFOLLOW`、fstat identity 的可信文本读取；`markdown.py::strip_nonsemantic_markdown` 已提供 fence-aware、offset-preserving 的确定性过滤。
- `tools/workflow_cli/output.py` 已用 `R2P_JSON=1` 切换 human/JSON 输出；`install.py` 会自动安装所有 `tools/r2p-*` wrapper，因此新增同命名 wrapper 不需要维护静态清单。
- `tests/test_docs_consistency.py` 对 Claude/Codex execute surfaces 的关键 token 和禁用行为做锁步检查；OpenCode 从 Claude Markdown 派生，Gemini execute surface 仅负责调用 wrapper。

## Requirements Coverage
| Upstream | Design coverage | Status |
|---|---|---|
| SCOPE-IN-001 | task-level targeted-first escalation matrix + final mandatory full suite | [ADDRESSED] |
| SCOPE-IN-002 | self-contained zero-history role dispatch；Codex 明确 `fork_turns="none"` | [ADDRESSED] |
| SCOPE-IN-003 | controller-owned、non-authoritative metrics ledger 与精确字段口径 | [ADDRESSED] |
| SCOPE-IN-004 | symlink-safe deterministic context-view module、internal CLI 和 wrapper | [ADDRESSED] |
| SCOPE-IN-005 | role-side context invocation + compact audit-preserving report contracts | [ADDRESSED] |
| SCOPE-IN-006 | outcome-based cohesive change slice 形成规则，不改机器 schema | [ADDRESSED] |
| SCOPE-IN-007 | strict default、三样本进入条件和兼容执行路径 | [ADDRESSED] |
| SCOPE-IN-008 | fast 显式参数、结构与语义双重资格检查、N+1 角色结构 | [ADDRESSED] |
| SCOPE-IN-009 | profile-aware ledger、implemented marker、BASE chain、recovery 和 final approval | [ADDRESSED] |
| SCOPE-IN-010 | 双模板同步、OpenCode/Gemini 入口、wrapper 安装和回归矩阵 | [ADDRESSED] |
| RISK-PERF-001 | 记录 verification scope/reason/duration，只有列明 trigger 才运行 task-level full suite | [ADDRESSED] |
| RISK-CTX-002 | 每个角色提示携带完整启动协议并由角色自己取得语义视图 | [ADDRESSED] |
| RISK-METRIC-003 | metrics 不参与 gate；Token 只允许 measured integer 或 unavailable | [ADDRESSED] |
| RISK-IO-004 | 每个 source 独立安全读取，run/work-id/status fail closed | [ADDRESSED] |
| RISK-CONTRACT-005 | 固定 source 顺序、分隔符、UTF-8 byte 定义和 JSON shape | [ADDRESSED] |
| RISK-AUDIT-006 | compact contract 强制保留 concerns、验证、文件和 `⚠️ DEFER` | [ADDRESSED] |
| RISK-GRAN-007 | 三项独立性判据、正反例和现有 schema 不变 | [ADDRESSED] |
| RISK-PROFILE-008 | CLI 结构门 + controller 语义门；任一未知即 strict | [ADDRESSED] |
| RISK-RESUME-009 | `[x]` 仍只表示 reviewed complete，implemented marker 独立存在 | [ADDRESSED] |
| RISK-FINAL-010 | fast final contract 不读取 task review 文件，但逐任务承担 primary review | [ADDRESSED] |
| RISK-PARITY-011 | 同切片修改 Claude/Codex 并测试派生/简面 | [ADDRESSED] |
| RISK-SEQUENCE-012 | Phase 3 任务入口检查当前执行 metrics 的三条代表性记录 | [ADDRESSED] |

## Options Considered
1. **只调整模型或 reasoning 档位**：改动小，但不能消除 `(2N+1)` 次重复输入和重复完整测试，也会把质量变化与性能变化混在一起；拒绝。
2. **共享 implementer、并行写当前分支或加入 batch reviewer**：可减少角色启动，但破坏任务隔离、提交边界或冲突可控性；拒绝。
3. **生成持久化 task context bundle**：读取快，但产生新的复制事实源、manifest/hash/drift 生命周期和敏感路径风险；拒绝。
4. **一次性把执行编排迁入 Python orchestrator**：可提供最强确定性，但会跨越“CLI 管状态/结构，agent 写语义和编排”的现有边界，扩大迁移风险；本需求不选。
5. **四个增量切片 + 确定性只读 view + 两档 profile**：每一步都能独立衡量收益，strict 保持兼容，fast 只在证据充分且资格明确时减少逐任务 reviewer；选择。

## Chosen Design
### DES-EXEC-001 — Phase 0：验证节奏、零历史与 controller-owned metrics

`run-execute-start` 在创建 `execution/progress.md` 时同时创建结构化 `execution/metrics.md`。metrics 文件不被任何 gate 或 resume parser 读取；当前自举执行若因旧代码未自动生成该文件，controller 在首个角色 dispatch 前以相同 header 创建一次。

metrics 使用一个角色调用一个 Markdown block 的顺序记录，controller 是唯一写入者。字段为：sequence、role、task、model（或 unavailable）、started_at、ended_at、elapsed_seconds、context_mode、context_bytes、verification_scope、verification_reason、verification_command、verification_elapsed_seconds、report_bytes、status、concerns、fix_wave，以及 input/output/total Token（平台没有真实值时全部为 unavailable）。`context_bytes` 表示实际交付的 ACS/semantic payload UTF-8 bytes，不包含 system prompt、工具协议或 agent 输出；不得用归档快照推算值冒充测量值。

controller 在 dispatch 前记时并只计算字节数，不读取 ACS 正文；角色返回后读取文件大小/验证摘要并完成 block。角色调用串行，避免 metrics 追加竞争。report/review 仍由对应角色写入既有文件。

implementer 与 task reviewer 的 verification matrix 一致：默认 targeted/directly affected；触及 shared/core/high-risk、targeted 失败、覆盖关系不清或 reviewer 无法建立充分信心时升级 full suite，并在 metrics 记录原因。final reviewer 无条件运行 full suite。Codex dispatch 固定 `fork_turns="none"`；Claude/其他平台使用其可表达的 fresh/minimal-history 语义，缺少 subagent 能力仍 fail explicitly。

### DES-CTX-002 — Phase 1：确定性 execution context view 与紧凑审计输出

新增 `tools/workflow_cli/execution_context.py`，只负责构建只读 view；新增内部 `context-view` CLI handler；新增安装型 `tools/r2p-context-view` wrapper，公开接口为 `r2p-context-view --work-id <id>`，首版没有 `--role`。

命令只接受合法 work ID 和 `EXECUTING` run，固定按以下顺序读取：`02-project-context.md`、`03-requirement-brief.md`、`04-risk-discovery.md`、`05-design.md`、`06-spec.md`、`execution/progress.md`。workspace/run 路径先拒绝 symlink；每个 source 再用 `read_regular_text` 读取。missing 返回 not-found，symlink/non-regular/race 返回 conflict，任何 source 失败都不输出 partial content。

每个 raw text 经过 `strip_nonsemantic_markdown` 后 `rstrip()`，以固定可见分隔行 `===== <relative-path> =====` 和一个尾随换行组成最终 `content`。aggregate `raw_bytes` 是各 raw UTF-8 bytes 之和；aggregate `semantic_bytes` 是最终 `content.encode("utf-8")` 的长度，等于角色实际消费的 semantic payload；`sources` 按固定顺序给出每项 `path`、`raw_bytes`、过滤后 `semantic_bytes`。

human mode 的 stdout 只输出最终 `content`；JSON mode 使用现有 success envelope，并至少输出 `work_id`、`sources`、`raw_bytes`、`semantic_bytes`、`content`。子代理在自己的上下文中调用该命令，controller 只可通过重定向到 byte counter 取得 payload 大小，不得读取/转发正文。不创建任何持久化 context artifact。

task report/review 改为紧凑固定 section：Status、Commit Range、Changed Files、Verification Evidence、Concerns；review 额外保留 Spec/Quality Verdict 和 `⚠️ DEFER`。字段内容可以简短，但 concerns 与每条 `⚠️ DEFER` 必须逐项保留。strict final 读取所有 reports/reviews；fast final 读取所有 reports，不要求不存在的 reviews。

### DES-PLAN-003 — Phase 2：cohesive change slice 任务形成规则

PLAN author 先按可观察行为或契约结果分组，再把实现、直接测试、同步 agent surfaces 和必要文档放入同一 slice。一个 slice 必须同时满足：可用自己的 Verification 独立判定；reviewer 不依赖未完成 sibling 才能判断；其 commits 可独立回滚且不会留下破损 schema/接口。

禁止仅因文件不同拆任务；同一行为链的 Python handler、wrapper、安装测试和 surface 更新可以属于一个 slice。也禁止把没有共同验收结果的多个行为塞入大任务。`stage_templates.py`、Claude/Codex `r2p-continue` 生成指导和一致性测试同步写入该规则；`PLAN_TASK_FIELDS`、trace closure、gate 和 checkbox 解析不变。

### DES-PROFILE-004 — Phase 3：strict/fast 选择、ledger 与恢复

`r2p-execute` wrapper 增加可选 `--profile strict|fast`；省略时首次执行固定为 strict。`run-execute-start` 把 `Execution Profile: <profile>` 写入 progress。fast 的 CLI 结构门要求 tier 为 LIGHT 且 modifier 为空，否则在任何 task dispatch 前返回 conflict。controller 再做语义门：全部任务必须局部、机械、无 shared/core/security/migration/dependency/config 风险，Files 边界清楚，且 Verification 是可直接执行的确定性命令；未知或边界争议均把有效 profile 记为 strict 并记录原因。

strict 沿用 N 个 fresh implementer + N 个 task reviewer + 1 个 final reviewer。fast 使用 N 个 fresh implementer + 1 个 final reviewer；implementer 完成并提交后，controller 保持该任务 `- [ ]`，追加精确 marker：`Task N: implemented (commits <base7>..<head7>, verification recorded)`。只有 final primary review 逐任务批准后，controller 才把所有任务置 `[x]` 并把 marker 收敛为 reviewed-complete 记录。

fast resume 选择编号最小、既无 checked-complete 也无合法 implemented marker 的任务。Task 1 BASE 只来自 `Execution BASE`；Task N BASE 只来自前一任务合法 complete/implemented marker 的 head。已存在 marker 的任务不重复实现。marker 缺失而提交存在、marker 格式/顺序/commit 无法解析、HEAD 不在 marker chain、验证失败、unexpected file、concern、上游歧义或 shared/core 风险都会把 profile 追加为 `strict (escalated from fast: <reason>)`，并按顺序为所有 implemented-but-unreviewed 任务生成 diff、执行 task review，干净后才置 `[x]`，然后继续 strict loop。

fast final reviewer 是 primary review：读取 semantic context view、PLAN、progress、全部 task reports、全部 Minor/concern 和 execution-base→HEAD final diff；不要求 task review 文件。它逐 PLAN task 检查 spec、changed files、verification 和 diff，无条件运行 full suite。发现问题沿用单一 final-fixer + refreshed diff + re-review loop；全部批准后才更新 checkboxes、写 `execution/final-review.md` 的最后 verdict 并允许 archive。

Phase 3 task 的入口证据是当前执行 `metrics.md` 至少三条完整记录，覆盖至少两个 task number，且同时包含 implementer 与 task-reviewer 角色；每条都必须有 elapsed、context bytes、verification scope/duration、report bytes 和 status。证据不足属于任务前置失败，不能用估算或历史最终快照替代。

### DES-COMPAT-005 — 安装、平台与测试兼容

Claude/Codex execute surfaces 在同一 patch 中修改并由 `tests/test_docs_consistency.py` 对 profile、context-view、targeted escalation、metrics、implemented marker、fast recovery、primary final review 和 `⚠️ DEFER` token 做锁步约束。OpenCode 继续从 Claude 派生；Gemini 入口保留 wrapper forwarding，并更新 description 以说明 strict 默认/fast opt-in。

新增 wrapper 会被 `install.py` 的 `tools/r2p-*` glob 自动纳入安装、卸载和 manifest；补充 install/wrapper bootstrap 测试。CLI 与安全读取测试使用临时 workspace；profile/gate tests 证明 strict 旧 ledger 兼容、fast `[ ]` 不会越过 archive completion gate、final 批准后才能通过。

## Decision Requests
none

## Rollback
- 每个 Phase 使用独立任务提交范围；逆序回滚不会要求改变已有 artifact schema。
- Phase 3 可通过移除 profile 参数/协议恢复 strict-only；已有 strict ledger 继续有效，fast ledger 尚未 final approve 时仍因 `[ ]` 被 archive gate 阻止。
- Phase 2 只修改生成指导，可独立恢复旧粒度文案而不迁移已有 PLAN。
- Phase 1 可移除 wrapper、handler 和 helper，并让模板恢复直接读取 ACS；没有持久化 context artifact 需要清理。
- Phase 0 可恢复旧验证文案并停止生成 metrics；metrics 不被 gate 读取，因此残留本地文件不影响运行正确性。
- repo 模板变更不会自动覆盖已安装 agent home；发布/安装验证明确区分源模板和安装结果，回滚使用上一已知版本重新安装。

## Observability
- `execution/metrics.md` 提供 per-role elapsed、context bytes、verification scope/duration、report bytes、status、concerns 和 fix waves；无法取得的平台 Token 显式标记 unavailable。
- context view JSON 的 aggregate/per-source bytes 支持验证过滤比例和实际 semantic payload，且不把重建 snapshot 当历史真实流。
- progress 中的 `Execution Profile`、implemented/complete marker、escalation reason 和既有 `Resolved/Gap/Unresolved/Minor` 共同提供恢复审计。
- final review 继续记录 execution BASE→HEAD 范围、fresh full-suite 结果和最后 verdict；archive gate 行为不变。
- 测试输出分别覆盖 targeted 模块与最终完整 suite，不在文档冻结通过数量。

## SPEC Handoff
SPEC 必须把以下内容写成无歧义契约：

1. metrics 文件 header、角色 block 字段、writer ownership、测量/不可用值、三样本充分性判定。
2. task-level full-suite escalation matrix 与 final full-suite 不可省略规则。
3. context-view 的参数、允许状态、source 顺序、分隔、字节计算、human/JSON shape、错误码和 symlink/race 行为。
4. compact report/review 的最小字段以及 concern/`⚠️ DEFER` 不可丢失规则。
5. cohesive change slice 的三项判据、跨文件正例、过细/过大反例和 schema 不变约束。
6. `--profile` 首次选择、strict 默认、fast 结构门/语义门和 executing resume 参数冲突行为。
7. progress profile 行、implemented marker grammar、BASE chain、resume selector、fast→strict recovery 和 checkbox 迁移时点。
8. strict/fast final reviewer 输入矩阵、primary review、fix loop、full suite、final verdict 与 archive gate。
9. Claude/Codex/OpenCode/Gemini、wrapper install 和全部临时 workspace 回归测试矩阵。

## Trace
<!-- Map this stage's IDs to upstream/downstream. R3 derives & checks closure. -->
| This ID | Upstream | Status |
|---|---|---|
| Design headings above | Approved requirement brief and risk discovery | [ADDRESSED] The design assigns every in-scope behavior and risk to one of four sequential slices plus cross-platform compatibility. |

## Upstream Summary (read-only)
# Risk Discovery

## Risks
### RISK-PERF-001 — targeted verification 规则过宽或过窄
Status: Open — 过宽会继续重复完整测试，过窄会漏掉 shared/core 回归；设计必须给出可审计的升级条件，并让 final full suite 保持兜底。

### RISK-CTX-002 — 零继承历史导致角色缺少必要约束
Status: Open — `fork_turns="none"` 会消除控制器历史，也会暴露当前角色提示是否自包含；模板必须显式给出读取命令、任务 brief、Git 边界和输出契约。

### RISK-METRIC-003 — metrics 漂移成第二状态源或伪精确数据
Status: Open — 若 metrics 参与 resume/archive 判定，或把估算 Token 当真实 Token，会破坏现有 ledger 权威并污染后续 profile 决策。

### RISK-IO-004 — context view 扩大可信输入攻击面
Status: Open — 新命令会聚合多个文件；若任一读取绕过 `read_regular_text`、允许 symlink/non-regular/race，或未约束 work ID 与 run directory，可能读取工作区外内容。

### RISK-CONTRACT-005 — human/JSON 输出或字节口径不稳定
Status: Open — source 顺序、分隔符、缺失文件处理、`raw_bytes`/`semantic_bytes` 计算对象若不明确，会使子代理输入和 metrics 无法复现。

### RISK-AUDIT-006 — 报告压缩丢失 concern 或 deferred evidence
Status: Open — 仅追求 report bytes 可能删除 reviewer/final reviewer 所需的异常、文件偏差、验证失败或 `⚠️ DEFER`，造成错误批准。

### RISK-GRAN-007 — cohesive slice 规则造成过大任务或追踪断裂
Status: Open — 粒度规则若只用自然语言描述而无正反例，可能把跨模块行为合并成无法独立验证的任务，或改变 PLAN task schema/trace closure。

### RISK-PROFILE-008 — fast 资格判断含糊导致高风险运行降级
Status: Open — LIGHT 只是必要条件，不足以证明局部、机械、确定性可验证；资格必须 fail closed，默认 strict，任一条件不满足即拒绝 fast。

### RISK-RESUME-009 — implemented marker 与现有复选框语义冲突
Status: Open — 当前 `[x]` 表示逐任务 reviewer clean；fast 若提前勾选会让 archive gate 误判。marker 缺失、重复、乱序、HEAD 分叉和中断恢复必须有确定性处理。

### RISK-FINAL-010 — fast final reviewer 输入缺失或负载过大
Status: Open — fast 不产生 `task-N-review.md`，final contract 若仍强制读取会失败；另一方面，primary review 必须逐任务核对全部 report/diff，不能只做整体扫视。

### RISK-PARITY-011 — 多平台执行表面发生语义漂移
Status: Open — Claude、Codex、Gemini 简面与 Claude 派生的 OpenCode 能力不同；只更新一个模板会产生不同验证、恢复或 profile 行为。

### RISK-SEQUENCE-012 — Phase 3 在无代表性基线时提前落地
Status: Open — 未收集至少 3 个实际样本就实现 fast，会缺少可信的收益/风险对照，也无法验证 Phase 0/1 是否已足够降低成本。

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
