---
r2p_stage: design
r2p_version: 8
r2p_status: approved
r2p_created_at: 2026-08-29T14:08:23.425675+00:00
r2p_updated_at: 2026-08-29T15:50:02.304588+00:00
---

# Design

## Design Summary
采用四个顺序化、可独立交付的 phase-level cohesive change slices。现有 PLAN R19 file gate 不允许同一 task 的 `Files` 混合新建与既有路径，因此每个 Phase 可以确定性展开为一个按依赖排序、operation-homogeneous 的 task group，而不是把不完整的新文件和入口集成伪装成一个 task。组内每个 task 都有可独立验证和评审的中间契约；Phase 的最终 integration/adoption task 证明整组验收；回滚按反向依赖顺序进行且不要求回滚其他 Phase。Phase 0 先修正验证节奏、子代理历史传递和度量结构；Phase 1 增加确定性上下文视图并缩短报告契约；Phase 2 收紧 PLAN 任务形成规则；Phase 3 的当前-run task group 设置显式证据 gate，只有三次独立、完成 final review 且使用 Phase 0/1 instrumentation 的 strict execution run 满足代表性条件后才进入实现。证据不足时 Phase 3 task group 保持当前 run 的未完成状态并返回 `BLOCKED`，不把它移出本需求。所有状态正确性继续由 `run.md`、`execution/progress.md`、PLAN 复选框和 final-review gate 决定，`execution/metrics.md` 只负责观测。

## Current Code Evidence
- `tools/workflow_cli/agent_templates/{codex,claude}/.../r2p-execute` 当前承载绝大多数执行编排：每任务 fresh implementer、task reviewer、fix loop、final reviewer、BASE/resume 和 archive 协议都属于提示契约，不是 Python orchestrator。
- 当前 Authoritative Context Set 要求每个 implementer/reviewer/fixer 直接完整读取 `02`–`06` 与 `execution/progress.md`；模板中的“可跳过嵌入 read-only block”不能阻止普通整文件读取先把这些字节放入角色上下文。
- `tools/workflow_cli/stage_templates.py` 已在 PLAN 的 `Verification` guidance 中表达 targeted tests 优先和 final review 全量回归，但 task-reviewer 模板没有同等强度的升级条件，历史执行因此仍可重复运行完整套件。
- `tools/workflow_cli/cli.py::_cmd_run_execute_start` 只从 PLAN anchors 生成 `execution/progress.md`；`gates.py::check_execution_complete` 只信复选框，`check_final_review_recorded` 只信 final-review 的最后一个合法 verdict。
- `tools/workflow_cli/agent_shortcuts.py::_cmd_execute` 负责 closed→executing 或 resume 的快捷入口；当前没有 profile 参数，resume 文案固定选择最低未勾选任务。
- `tools/workflow_cli/cli.py::_cmd_plan_task_brief` 已复用 `strip_nonsemantic_markdown`，并用内部 run loader、WorkId 校验和路径检查生成 scoped task brief，证明只读执行辅助命令可以保持 CLI/agent 分层。
- `tools/workflow_cli/atomic.py::read_regular_text` 已提供 final-component lstat、`O_NOFOLLOW`、fstat identity 的可信文本读取，但不固定父目录 identity；context view 需要补充基于稳定 directory fd 的逐组件读取。`markdown.py::strip_nonsemantic_markdown` 已提供 fence-aware、offset-preserving 的确定性过滤。
- `gates.py::_check_plan_file_refs` 要求 `Change Type: create` 的全部 `Files` 尚不存在、其他 change type 的全部 `Files` 已存在；当前 schema 没有 mixed operation。由于 SCOPE-IN-006 禁止修改该 schema/gate，新增 module/wrapper 与既有 CLI/template 的一个 Phase 必须展开为固定 task group，不能声称单个 mixed-path task 可通过现有门禁。
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
| SCOPE-IN-006 | phase-level cohesive slice + operation-homogeneous task group 形成规则，不改机器 schema | [ADDRESSED] |
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
| RISK-PROFILE-008 | CLI 结构门 + controller 语义门；显式 fast 的未知项在 mutation 前 conflict，运行时风险单向升级 strict | [ADDRESSED] |
| RISK-RESUME-009 | `[x]` 仍只表示 reviewed complete，implemented marker 独立存在 | [ADDRESSED] |
| RISK-FINAL-010 | fast final contract 不读取 task review 文件，但逐任务承担 primary review | [ADDRESSED] |
| RISK-PARITY-011 | 同切片修改 Claude/Codex 并测试派生/简面 | [ADDRESSED] |
| RISK-SEQUENCE-012 | Phase 3 当前-run任务以三个独立、完成 final review 的 instrumented strict runs 为证据 gate | [ADDRESSED] |

## Options Considered
1. **只调整模型或 reasoning 档位**：改动小，但不能消除 `(2N+1)` 次重复输入和重复完整测试，也会把质量变化与性能变化混在一起；拒绝。
2. **共享 implementer、并行写当前分支或加入 batch reviewer**：可减少角色启动，但破坏任务隔离、提交边界或冲突可控性；拒绝。
3. **生成持久化 task context bundle**：读取快，但产生新的复制事实源、manifest/hash/drift 生命周期和敏感路径风险；拒绝。
4. **一次性把执行编排迁入 Python orchestrator**：可提供最强确定性，但会跨越“CLI 管状态/结构，agent 写语义和编排”的现有边界，扩大迁移风险；本需求不选。
5. **四个 phase-level 增量切片 + operation-homogeneous task groups + 确定性只读 view + 两档 profile**：显式承认当前 R19 gate 的 create/modify 边界；每个 group 的中间 task 有局部可验证契约，最后一个 integration/adoption task 证明 Phase 验收，strict 保持兼容，fast 只在证据充分且资格明确时减少逐任务 reviewer；选择。

## Chosen Design
### DES-EXEC-001 — Phase 0：验证节奏、零历史与 controller-owned metrics

Phase 0 展开为固定的 create→integrate task group：create task 只新增并直接测试 `execution_metrics.py` 的纯解析、量化、分类、样本验证和 transaction/recovery core；随后的 modify task 才把它接入既有 CLI、shortcut、execute surfaces、测试与文档。对 Phase 0 的验收以 integrate task 的 CLI/fault-injection/模板测试为准；create task 的验收只证明 core API，不宣称入口已可用。

`run-execute-start` 通过唯一 public entry `start_execution_transaction(base_path: Path, work_id: WorkId, profile: str) -> RunRecord` 创建 `execution/progress.md` 与结构化 `execution/metrics.md`。该函数拥有完整 transaction trust boundary：内部加载并验证 `RunRecord`、安全读取 PLAN anchors、固定 run directory handle、写入 `.start-transaction.json`、以 no-clobber 方式创建 progress/metrics、保存 state，并只在三者一致后删除 marker；CLI handler 只解析参数、调用该 entry 并格式化 human/JSON 输出，不在外层重复加载 record 或 anchors。崩溃恢复再次调用同一 entry，并按 marker 与三份权威状态的组合完成或 fail closed。metrics 文件不被任何 gate 或 resume parser 读取。

当前 `WF-20260829-r2p-execute-token-phase-r2p` 是实现 instrumentation 的 self-hosted run，新 entry 在 Phase 0 integrate task 完成前客观上不可调用；因此不再要求 controller 在首个 role dispatch 前手写未来格式。Phase 0 integrate task（固定为 `PLAN-TASK-002`）通过后，controller 必须在派发 `PLAN-TASK-003` 前运行新 internal command `execution-metrics-bootstrap --work-id WF-20260829-r2p-execute-token-phase-r2p --profile strict --self-hosted-gap-through-task 002`。canonical header 值固定为 `instrumentation_complete: false` 和 `bootstrap_gap: execution_start_through_task_002_reviewed_complete`；该 gap 精确包含从 execution start 到 Task 002 reviewer-clean 为止的全部 implementer、reviewer、fixer 和 re-review role calls，首个可记录 role 是 Task 003 implementer。未来正常 start 固定写 `instrumentation_complete: true` 与 `bootstrap_gap: none`。

bootstrap 是 crash-idempotent no-clobber operation。所有分支先验证 run 为 `EXECUTING`、合法 Execution BASE/task anchors、Task 001/002 各恰有一个 reviewed-complete record且 profile 为 strict。若 metrics 不存在，这是首次 bootstrap：还必须证明 Task 003 尚未开始、HEAD 等于 Task 002 reviewed-complete head，随后才原子创建 exact self-host header。若 metrics 已存在，这是 retry/resume：不再要求 Task 003 未开始；安全 regular file 的 header 必须与预期 work/profile/task_count/instrumentation schema/completeness/canonical gap 完全一致，exact header 后没有 block或只有从 Task 003 开始、与 progress/task order 一致、sequence 连续且结构完整的 blocks 时视为幂等 success，不重写 header，并从下一 sequence 继续 append。任何 partial/乱序 block、Task 001/002 block、unsafe file、结构损坏、foreign header 或任一 exact field 不匹配都返回 conflict 且不覆盖/清理。这样“原子创建后、success 返回前崩溃”与“已记录 Task 003+ role 后 controller 重启”都会收敛。当前 run 永不成为 Phase 3 sample。

metrics header 固定记录 `work_id`、`r2p_version`、`instrumentation_schema`、`profile`、`task_count`、`instrumentation_complete`、`bootstrap_gap`、`change_shape: unavailable` 和 `metrics_finalized: false`。`instrumentation_schema` 是跨目标仓库/无 Git 安装均可验证的执行度量能力版本；Phase 0/1 落地时定义首个整数版本，字段或口径不兼容变更必须递增。一个角色调用对应一个有序 Markdown block，controller 是唯一写入者；block 字段为 sequence、role、task、model（或 unavailable）、started_at、ended_at、elapsed_seconds、context_mode、context_bytes_kind、context_bytes、verification_records、verification_total_seconds、report_bytes、status、concerns、fix_wave，以及 input/output/total Token（平台没有真实值时全部为 unavailable）。不得用归档快照、role elapsed 或其他派生值填充不可观测字段。

controller 用 wall-clock timestamps 记录 role started_at/ended_at，用自身单调时钟差记录 elapsed_seconds，并在角色返回后读取 report bytes；任一时钟不可用就写 unavailable。每个 implementer/reviewer/fixer/final reviewer 必须用单调时钟包围自己执行的每条 verification command，在持久 report/review 中写有序 `Verification Records`，每项包含 command、scope、reason、elapsed_seconds、status；同时在 inline return 中给出同结构的紧凑 `verification_records` 与 `verification_total_seconds`。controller 逐项复制到 metrics；缺失或无法解析时写 unavailable 并把该缺口加入 concerns，绝不从 role elapsed 推算 verification time。多条 targeted 命令和升级后的 full suite 各占一项。

final reviewer 依据 execution-base→HEAD final diff 对 `change_shape` 做一次性 finalize。测试路径定义为任一 component 是 `test`/`tests`，或 basename 匹配 `test_*`、`*_test.*`、`*.test.*`、`*.spec.*`；文档定义为位于 `docs/` 或扩展名属于 `.md/.rst/.adoc/.txt`；配置扩展名固定为 `.json/.yaml/.yml/.toml/.ini/.cfg/.properties`；其余为 source，root-level source 的 module 名为 `_root`，其他 source 的 module 是第一 path component。分类优先级为：任一路径含 `migration`/`migrations` → `migration`；忽略测试后 source module 数为一 → `single_module_code`，大于一 → `cross_module_code`；没有 source 且全部非测试路径为文档 → `docs_only`；没有 source 且全部非测试路径为配置 → `config_only`；只有测试 → `test_only`；其余 → `mixed`。final clean 后 controller 原子替换 header 为该枚举值和 `metrics_finalized: true`；此前不得用于样本判定。

Phase 0 的 `context_mode=direct_acs` 使用 `context_bytes_kind=declared_payload_bytes`：值严格等于模板要求角色完整读取的六个 ACS source 的 UTF-8 raw bytes 之和。它衡量声明交付量，不声称等于工具分块传输或模型实际 consumed bytes。Phase 1 的 `context_mode=semantic_view` 使用 `context_bytes_kind=semantic_payload_bytes`，值直接取该角色调用的 context-view aggregate `semantic_bytes`。controller 可用 stdout 重定向到 byte counter 验证数值，但不得把 ACS 正文读入自己的上下文。任何平台不能观察的 Token 或 timing 都写 unavailable。

角色调用串行，避免 metrics 写入竞争；report/review 仍由对应角色写入既有文件。任何角色发现的每条 `⚠️ DEFER` 都必须同时进入其持久 report/review 的固定 `⚠️ DEFER` section 和 inline `concerns`；没有时写 `none`，不得省略。strict final 读取 reports 与 reviews；fast final 从所有 reports 取得 implementer-side `⚠️ DEFER`。

implementer 与 task reviewer 的 verification matrix 一致：默认 targeted/directly affected；触及 shared/core/high-risk、targeted 失败、覆盖关系不清或 reviewer 无法建立充分信心时升级 full suite，并在 metrics 记录原因。final reviewer 无条件运行 full suite。Codex dispatch 固定 `fork_turns="none"`；Claude/其他平台使用其可表达的 fresh/minimal-history 语义，缺少 subagent 能力仍 fail explicitly。

Phase 0 同时交付只读 internal validator `execution-samples-validate`。它接收恰好三次 `--sample-dir <absolute-archived-run-dir>`，不扫描默认目录、不猜测路径、不写源文件；复用 metrics parser 与 pinned directory-fd/no-follow reader，逐 sample 验证 work ID 唯一、archived strict 状态、受支持 schema、`instrumentation_complete: true`、`bootstrap_gap: none`、finalized shape、完整 role blocks、final full-suite/Approved verdict 和跨 sample 的代表性。human/JSON 都逐 sample 返回规则结果；参数缺失、重复、unsafe、任一规则失败或代表性不足均以 `BLOCKED: representative_metrics_missing` 结束。该 validator 在 Phase 0 integrate task 落地，所以 Phase 3 不依赖尚未创建的 profile module。

### DES-CTX-002 — Phase 1：确定性 execution context view 与紧凑审计输出

Phase 1 展开为四个有序 task：先 create `execution_context.py` 与直接单元测试；再 modify 既有 CLI/tests 注册并验证 internal `context-view`；再 create `tools/r2p-context-view` 与独立 wrapper smoke test；最后 modify Claude/Codex/Gemini/OpenCode-derived surfaces、docs 与 consistency/install tests，让角色正式消费 wrapper。稳定 directory-fd 与 relative no-follow text-read helpers 是该固定六源 view 的私有实现，归 `execution_context.py` 所有，不扩张 `atomic.py` 的单文件 API；这是明确的模块所有权决定，不是 PLAN 临时漂移。每一步只依赖已完成前驱，且在自己的 Files 范围内有可运行 verification；Phase 验收由最后一个 adoption task 证明。

命令只接受合法 work ID 和 `EXECUTING` run。它先以 directory fd 打开 repo root，再使用相对 fd 的 `os.open(..., O_DIRECTORY | O_NOFOLLOW | O_NONBLOCK)` 逐组件打开 `.req-to-plan`、work-id run dir 和 `execution`；所有固定 source 先相对 pinned fd 做 no-follow pre-stat，再以 `os.open(..., O_NOFOLLOW | O_NONBLOCK)` 打开并用 `fstat` 比对 dev/ino/regular-mode 后读取。`run.md` 也从同一 run-dir fd 读取并解析，在该 handle 下核对 embedded work ID 与 `EXECUTING` status；不先信任一次 path-based load 再读取另一个可能已被替换的目录。平台缺少所需 dir-fd/flag 能力时 fail closed。目录在打开后被 rename 不会改变 fd 所指 inode；父路径被替换时继续从已 pinned 的原目录树安全读取，不承诺检测 path-name identity drift，也绝不切换到替换后的目录。

content 固定按以下顺序读取：`02-project-context.md`、`03-requirement-brief.md`、`04-risk-discovery.md`、`05-design.md`、`06-spec.md`、`execution/progress.md`。missing 返回 not-found；symlink、non-directory、non-regular、检测到的 final-component identity race 或 capability unavailable 返回 conflict。父 path replacement 若发生在 fd pinning 后，不是错误：结果来自完整、稳定的 pinned tree。所有 source 全部读取并校验成功后才构建/打印结果，错误路径不输出 partial content。

每个 source 的 semantic text 精确定义为 `strip_nonsemantic_markdown(raw).rstrip()`，per-source `semantic_bytes` 是该结果的 UTF-8 长度。最终 `content` 为每个 source 的固定可见分隔行 `===== <relative-path> =====`、semantic text、源间空行和全局唯一尾随换行。aggregate `raw_bytes` 是各 raw UTF-8 bytes 之和；aggregate `semantic_bytes` 是最终 `content.encode("utf-8")` 的长度，显式包含分隔符/源间空行/唯一尾随换行，因此不要求等于 per-source semantic bytes 之和。

human success 直接向 stdout 输出 `content`，不附加 `✓`、message 或统计前缀。JSON success 的稳定顶层 keys/类型为：`status: "ok"`、`message: str`、`work_id: str`、`sources: list[{path: str, raw_bytes: int, semantic_bytes: int}]`、`raw_bytes: int`、`semantic_bytes: int`、`content: str`。失败继续使用 `status: "error"`、`message: str`、`exit_code: int` 和可选 `details: list[str]`，且不含 partial `content`/`sources`。子代理在自己的上下文中调用该命令，controller 不得读取/转发正文。不创建任何持久化 context artifact。

task report/review 改为紧凑固定 section：Status、Commit Range、Changed Files、Verification Records、Concerns、`⚠️ DEFER`；review 额外保留 Spec Verdict 与 Quality Verdict。字段内容可以简短，但每条 concern/`⚠️ DEFER` 必须逐项保留并进入 inline concerns。strict final 读取所有 reports/reviews；fast final 读取所有 reports 的同名 section，不要求不存在的 reviews。

golden/security tests 覆盖 Unicode、whitespace-only source、HTML comment、fenced content、固定顺序/分隔/bytes、human/JSON shape、missing/no-partial-output、final source symlink/race、raced-in FIFO 不阻塞、execution dir symlink，以及 fd pinning 后 workspace/run parent replacement 仍读取原树且绝不读取替换树。

### DES-PLAN-003 — Phase 2：cohesive change slice 任务形成规则

PLAN author 先按可观察行为或契约结果形成 phase-level slice。若 slice 同时需要新建和修改路径，必须按现有 R19 gate 展开为固定、operation-homogeneous task group；不得声称一个 task 可混合 create/modify，也不得仅为通过门禁而把未完成 wrapper 当作独立交付。依赖不新增 `Dependencies` field，而是使用既有 `Steps`：每个 task 的第一条 semantic step 必须逐字为 `Prerequisite: none`，或 `Prerequisite: PLAN-TASK-NNN`。canonical prerequisite 只表达同一 Phase group 内的实现依赖：001→002、003→004→005→006、008→009；Phase 2 的 007 及各 Phase 首 task 使用 `Prerequisite: none`，跨 Phase 执行顺序由 PLAN 编号、最低未完成任务选择器和上一 Phase acceptance 控制，不进入 rollback dependency graph。

`Verification` 的第一项使用既有 effective-profile/task-state parser 检查 prerequisite：strict 要求前驱 reviewed-complete；fast 接受合法 implemented marker 或 reviewed-complete；fast→strict recovery 必须先按 marker chain 补齐前驱 task review，再按 strict 条件继续。`Prerequisite: none` 时确认 execution BASE 存在且自己是编号最小的未实现/未完成 task。组内 task 必须交付可直接测试的 intermediate contract，reviewer 只依赖已完成前驱、不依赖未完成 sibling；最后一个 integration/adoption task 运行 Phase acceptance verification。rollback 的 declared dependents 只由同组 canonical prerequisite 反向推导：单个 task 的 commit range 可在先回滚其组内 dependents 后撤销；一个 Phase group 可整体反向拓扑回滚，不触及其他 Phase。

禁止仅因文件不同拆成没有中间契约的任务；确因 R19 operation 边界拆分时，每个 task 必须命名其 core/internal CLI/wrapper/adoption 结果及可运行测试。同一行为链仍属于一个 phase-level slice，不能把没有共同验收结果的多个行为塞入大任务。规则同步矩阵精确包含 `stage_templates.py`、Claude 通用 `agent_templates/claude/SKILL.md`、Claude `commands/r2p-continue.md`、Codex `skills/r2p-continue/SKILL.md`、Gemini `commands/r2p-continue.toml` 的 description/prompt 可表达部分，以及 `tests/test_docs_consistency.py`。OpenCode 不维护独立正文，由安装测试断言其 Claude-derived continue command 含同一 cohesive-slice/task-group 规则。`PLAN_TASK_FIELDS`、trace closure、gate 和 checkbox 解析不变。

### DES-PROFILE-004 — Phase 3：strict/fast 选择、ledger 与恢复

Phase 3 展开为 create→integrate task group：create task 新增并直接测试 profile/ledger/eligibility parser core；modify task 接入既有 shortcut、CLI、execute surfaces、docs 与测试。证据 preflight 是整个 group 的 controller-owned entry gate，发生在 create task 的 implementer dispatch 和任何 Phase 3 source mutation 之前；因此 validator 必须使用 Phase 0 已落地的 `execution-samples-validate`，不得由 Phase 3 临时创建或人工目测替代。

`r2p-execute` wrapper 增加可选 `--profile strict|fast`，并为 closed fast start 使用两步 handshake。closed run 省略参数固定选择 strict；显式 strict 等价且立即走现有 start。首次 `r2p-execute --profile fast` 只执行 deterministic tier/modifier 结构门；失败时 exit 6，成功时返回 `stop: fast_profile_review`、work ID、PLAN path、tier/modifiers，且不创建 progress/metrics、不改变 run status。Claude/Codex/OpenCode/Gemini agent surface 随后读取完整 `07-plan.md` 做语义门：全部任务必须局部且机械、无 shared/core/security/migration/dependency/config 风险、Files 边界清楚、Verification 为可直接执行的确定性命令。

语义门通过时，agent 调用 `r2p-execute --profile fast --confirm-fast-eligible`；shortcut 重跑结构门后才调用 `run-execute-start --profile fast`。语义门失败/未知时，agent 调用 `r2p-execute --profile fast --reject-fast-ineligible --reason <single-line>`；该路径验证 run 仍 closed 后以 exit 6 输出 `fast_profile_ineligible`，不 mutation、不自动执行 strict。两个 handshake flag 互斥、只允许和 `--profile fast` 一起使用，closed strict 或 executing run 使用它们均为 CLI error/conflict。直接从终端传 `--confirm-fast-eligible` 被定义为显式、可信的人工 eligibility attestation boundary；CLI 仍验证结构条件，但不声称能确定性判断 PLAN 语义。首次 fast、reject 和 confirm 失败测试都断言 run/status/files 零 mutation。

`run-execute-start --profile <profile>` 在 progress 写一个不可变初始行 `Execution Profile: strict|fast`。executing resume 的 effective profile 由初始行和有序 escalation events 确定：无 `--profile` 复用 effective profile；传入相同 profile 幂等接受；传入不同 profile 返回 conflict。legacy executing ledger 缺少初始行时确定性解释为 strict。fast 运行中触发安全升级时允许 controller 自动追加单行 `Profile Escalation: fast -> strict (reason: <single-line>)`；不改初始行，升级后不可降回 fast，resume 使用最后一个合法 event 的 target。profile 解析放在一个纯 parser/helper 中并由 shortcut 与测试共用。

strict 沿用 N 个 fresh implementer + N 个 task reviewer + 1 个 final reviewer。fast 使用 N 个 fresh implementer + 1 个 final reviewer；implementer 完成并提交后，controller 保持该任务 `- [ ]`，追加精确 marker：`Task N: implemented (commits <base7>..<head7>, verification recorded)`。只有 final primary review 逐任务批准后，controller 才把所有任务置 `[x]` 并把 marker 收敛为 reviewed-complete 记录。

fast resume 选择编号最小、既无 checked-complete 也无合法 implemented marker 的任务。Task 1 BASE 只来自 `Execution BASE`；Task N BASE 只来自前一任务合法 complete/implemented marker 的 head。已存在 marker 的任务不重复实现。marker 缺失而提交存在、marker 格式/顺序/commit 无法解析、HEAD 不在 marker chain、验证失败、unexpected file、concern、上游歧义或 shared/core 风险都会追加 one-way escalation event，并按顺序为所有 implemented-but-unreviewed 任务生成 diff、执行 task review，干净后才置 `[x]`，然后继续 strict loop。

fast final reviewer 是 primary review：读取 semantic context view、PLAN、progress、全部 task reports、全部 Minor/concern 和 execution-base→HEAD final diff；不要求 task review 文件。它逐 PLAN task 检查 spec、changed files、verification 和 diff，无条件运行 full suite。发现问题沿用单一 final-fixer + refreshed diff + re-review loop；全部批准后才更新 checkboxes、写 `execution/final-review.md` 的最后 verdict 并允许 archive。

Phase 3 当前-run group 开始时执行 machine preflight 后再进入人工证据 checkpoint。controller 必须先取得用户明确提供的三个绝对 archived-run directory paths；不允许自动发现或选择样本。唯一 invocation 为 `/opt/homebrew/opt/python@3.14/bin/python3.14 -E tools/workflow_cli/__main__.py tools.workflow_cli --base-path <current-repo> execution-samples-validate --sample-dir <absolute-1> --sample-dir <absolute-2> --sample-dir <absolute-3>`；PLAN 必须把当前环境解析出的 Python/entrypoint 写成可直接执行命令，不保留 `<...>` placeholder。controller 先保存 human/JSON validator 输出到忽略的 execution evidence，再让人工 checkpoint确认三份路径确为预期样本；validator 未返回 success 时不得派发 Phase 3 implementer。

合格证据允许来自任意目标 Git 仓库，但必须是三个不同 work ID、`run.md` 状态为 archived 的独立 strict execution runs；每个 run 的 metrics 都记录 `r2p_version`，`instrumentation_schema` 必须等于 Phase 0/1 定义的受支持版本，`instrumentation_complete` 必须为 true、`bootstrap_gap` 必须为 none、`metrics_finalized` 必须为 true，且 `change_shape` 不得为 unavailable。每个 run 必须实现全部 PLAN tasks，完成 primary final review/full suite，最后 verdict 为 Approved，并包含其全部 implementer、全部 task reviewer 和 final reviewer 的完整 role blocks；不得用当前 self-hosted run、跨仓库 SHA ancestry或同一 run 的多个 role block 证明多个样本。

三个样本合计还必须覆盖至少两个不同 `task_count` 值或至少两个 finalized `change_shape` 枚举。validator 输出并由 Phase 3 report引用三个 sample 的 work ID、archive/run path、r2p version、instrumentation schema、task count、instrumentation completeness、finalized change shape、role coverage、final verdict、metrics completeness 和逐规则 verdict，reviewer 逐项核验。缺少路径、少于/多于三份、任一份不合格或整体代表性不足时返回 `BLOCKED: representative_metrics_missing`，Phase 3 两个 task checkbox 均保持未完成且 source worktree 与 Phase 3 BASE 完全一致；证据仍属于当前需求的入口条件，不能用估算、单一历史 snapshot、当前 self-hosted run 或未完成 run 替代。

### DES-COMPAT-005 — 安装、平台与测试兼容

PLAN 必须把四个 Phase 精确展开为 `2 / 4 / 1 / 2` 个 operation-homogeneous tasks：Phase 0 为 metrics core create + integration modify；Phase 1 为 context core create + internal CLI modify + wrapper create + surface adoption modify；Phase 2 为一个 modify task；Phase 3 为 profile core create + integration modify。同组 task 仅在 `Steps` 第一条用 profile-neutral canonical prerequisite grammar 引用直接前驱；各组首 task/Task 007 使用 `Prerequisite: none`。每组最后一个 task 承担 Phase acceptance verification；不得写独立 `Dependencies:` field，也不得再次把新 wrapper 放进尚无 bootstrap target 的 core create task。该布局是现有 R19 gate 下对四个 phase-level slices 的确定性编码，不新增 PLAN 字段或 change type。

Phase 0/1/3 的完整 execute protocol surfaces 是 Claude `commands/r2p-execute.md` 与 Codex `skills/r2p-execute/SKILL.md`，必须在同一 patch 修改，并由 `tests/test_docs_consistency.py` 对 profile preflight、context-view、targeted escalation、metrics producer/units、implemented marker、fast recovery、primary final review 和 `⚠️ DEFER` token 做锁步约束。OpenCode 不手改，安装测试断言其 Claude-derived execute command 保留完整协议；Gemini 保留 wrapper forwarding，并在 description/prompt 可表达范围内写明 strict 默认、fast opt-in/read-only preflight 和 fail-closed 入口。

Phase 2 continue surfaces 使用上一节的五面同步矩阵，并单独验证 OpenCode 派生输出。Claude 通用 skill 与 command、Codex skill、Gemini description 不得只更新其中一部分。

新增 wrapper 会被 `install.py` 的 `tools/r2p-*` glob 自动纳入安装、卸载和 manifest；补充 install/wrapper bootstrap 测试。CLI 与 directory-fd 安全读取测试使用临时 workspace；profile/gate tests 证明 strict 旧 ledger 兼容、profile 参数 resume 冲突确定、escalation 单向、fast `[ ]` 不会越过 archive completion gate、final 批准后才能通过。

## Decision Requests
none

## Rollback
- 每个 Phase 使用一个固定 task group；单 task 只能在先回滚其 declared dependents 后撤销，整组按反向拓扑回滚。该过程不触及其他 Phase，也不要求改变已有 artifact schema/gate。
- Phase 3 可通过移除 profile 参数/协议恢复 strict-only；已有 strict ledger 继续有效，fast ledger 尚未 final approve 时仍因 `[ ]` 被 archive gate 阻止。
- Phase 2 只修改生成指导，可独立恢复旧粒度文案而不迁移已有 PLAN。
- Phase 1 可移除 wrapper、handler 和 helper，并让模板恢复直接读取 ACS；没有持久化 context artifact 需要清理。
- Phase 0 可恢复旧验证文案并停止生成 metrics；metrics 不被 gate 读取，因此残留本地文件不影响运行正确性。
- repo 模板变更不会自动覆盖已安装 agent home；发布/安装验证明确区分源模板和安装结果，回滚使用上一已知版本重新安装。

## Observability
- `execution/metrics.md` 区分 controller-measured role elapsed/report bytes、role-measured ordered verification records，以及 `declared_payload_bytes`/`semantic_payload_bytes` 两种 context 口径；无法取得的平台 Token/timing 显式标记 unavailable。
- context view JSON 的 aggregate/per-source bytes 支持验证过滤比例和实际 semantic payload，且不把重建 snapshot 当历史真实流。
- progress 中的 immutable `Execution Profile`、ordered `Profile Escalation`、implemented/complete marker 和既有 `Resolved/Gap/Unresolved/Minor` 共同提供恢复审计。
- Phase 3 report 固化三份独立 instrumented strict run 的 work ID/path、r2p version、instrumentation schema、finalized shape/task count、角色覆盖、final verdict 与 metrics 完整性。
- final review 继续记录 execution BASE→HEAD 范围、fresh full-suite 结果和最后 verdict；archive gate 行为不变。
- 测试输出分别覆盖 targeted 模块与最终完整 suite，不在文档冻结通过数量。

## SPEC Handoff
SPEC 必须把以下内容写成无歧义契约：

1. 唯一 `start_execution_transaction(base_path, work_id, profile)` signature 及其 record/PLAN/pinned-run ownership、transaction marker/recovery；metrics header、instrumentation schema、controller/role 数据生产者、monotonic elapsed、ordered verification records、两种 context byte kind、不可用值和 final change-shape classifier。
2. 当前 self-hosted run 的唯一 `execution-metrics-bootstrap ... --self-hosted-gap-through-task 002` invocation、canonical `bootstrap_gap: execution_start_through_task_002_reviewed_complete`、exact-header crash-idempotent retry matrix、合法后续 block resume、从 Task 003 role 才实测和永不作为样本的限制；未来 run 必须从首 role 完整采集。
3. task-level full-suite escalation matrix 与 final full-suite 不可省略规则。
4. context-view 私有 directory-fd helper 的模块所有权、参数、`O_NONBLOCK` traversal、relative pre-stat/open/fstat、同-handle run validation、pinned-parent replacement 安全语义、source 顺序、分隔/byte 公式、完整 human/JSON schema、错误码和 no-partial-output 行为。
5. compact report/review 的最小字段、Verification Records，以及任何角色的 concern/`⚠️ DEFER` 同时持久化与 inline 上报规则。
6. phase-level cohesive slice 与 operation-homogeneous task group 的双层定义、组内 intermediate contract、`Steps` 首条 profile-neutral canonical prerequisite grammar、strict/fast/recovery satisfaction matrix、仅组内 dependency graph、Phase acceptance、反向拓扑 rollback、`2/4/1/2` 布局、schema 不变约束和五个 continue surfaces + OpenCode 派生矩阵。
7. `execution-samples-validate` 的 repeated absolute `--sample-dir` contract、pinned/no-follow 读取、逐 sample/aggregate verdict、human/JSON/no-write 行为，以及它作为 Phase 3 source mutation 前唯一 machine preflight 的 exact invocation。
8. `--profile` 两步 fast handshake、首次 review stop、confirm/reject flags、direct confirm 的可信人工边界、strict 默认、拒绝不自动降级、closed/executing 参数矩阵和 legacy strict 解释。
9. immutable initial profile、ordered escalation event、implemented marker grammar、BASE chain、effective-profile/resume selector、fast→strict recovery 和 checkbox 迁移时点。
10. strict/fast final reviewer 输入矩阵、primary review、fix loop、full suite、final verdict 与 archive gate。
11. Claude/Codex 完整 execute surfaces、OpenCode 派生、Gemini 精简入口、wrapper install、目录 race和全部临时 workspace 回归测试矩阵。

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
