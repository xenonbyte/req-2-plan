# Plan

## Tasks

### PLAN-TASK-001 — Phase 0: verification cadence, zero-history dispatch, and execution metrics foundation
Spec References: SPEC-VERIFY-001, SPEC-ROLE-002, SPEC-METRICS-009, SPEC-PARITY-008
Change Type: add/modify
TDD Applicable: yes
Files:
- `tools/workflow_cli/execution_metrics.py` (new)
- `tools/workflow_cli/atomic.py`
- `tools/workflow_cli/cli.py`
- `tools/workflow_cli/agent_templates/claude/commands/r2p-execute.md`
- `tools/workflow_cli/agent_templates/codex/skills/r2p-execute/SKILL.md`
- `tools/workflow_cli/agent_templates/gemini/commands/r2p-execute.toml`
- `tests/test_execution_metrics.py` (new)
- `tests/test_atomic_write.py`
- `tests/test_cli.py`
- `tests/test_docs_consistency.py`
- `tests/test_install.py`
- `README.md`
Skeleton:
```python
INSTRUMENTATION_SCHEMA = 1

def measured_seconds(start_ns: int, end_ns: int) -> str:
    """Return the SPEC-METRICS-009 six-decimal ROUND_HALF_UP value."""

def start_execution_transaction(run_dir, record, plan_anchors, profile):
    """Seed progress and metrics with lock, marker, no-clobber, and recovery."""

def parse_metrics(text: str):
    """Validate the exact header, invocation JSON, role matrix, and totals."""

def classify_change_shape(name_status_z: bytes) -> str:
    """Apply the exact A/M/D/T/Rddd/Cddd path classifier."""
```
Steps:
- [ ] Write failing unit tests first for six-decimal monotonic quantization, canonical JSON/role-wave validation, context byte pairs, Token availability, invocation sequencing, and every change-shape table row.
- [ ] Add fault-injection tests for the exclusive lock, atomic no-clobber `execution/` creation, transaction marker lifecycle, closed/executing crash recovery, owned rollback, foreign residue, symlink/non-regular targets, and the legacy self-bootstrap guard.
- [ ] Implement `execution_metrics.py` as the single parser/renderer/classifier authority and extend `atomic.py` only with the narrow dir-fd/lock primitives required by the transaction.
- [ ] Change `run-execute-start` to seed `progress.md` plus `metrics.md` through the recoverable transaction while defaulting existing callers to strict and preserving all exit-code/JSON conventions.
- [ ] Update Claude and Codex execute surfaces in lockstep so every actual role dispatch is a new zero-history invocation, records targeted-first verification and a metrics block, and preserves mandatory final full-suite review; keep Gemini truthful and fail closed where subagents cannot be guaranteed.
- [ ] Add install/derived-surface assertions and document metrics ownership, unavailable Token semantics, and strict compatibility without making metrics authoritative.
Verification: Run `.venv/bin/python -m pytest tests/test_execution_metrics.py tests/test_atomic_write.py tests/test_cli.py tests/test_docs_consistency.py tests/test_install.py -q`; record exit 0 and the command duration. Because this slice changes shared `atomic.py` and `cli.py`, also run `.venv/bin/python -m pytest tests/ -q` and record the full-suite trigger reason as `shared/core execution-start path`.

### PLAN-TASK-002 — Phase 1: symlink-safe semantic context view and compact audit artifacts
Spec References: SPEC-CONTEXT-010, SPEC-CONTEXT-011, SPEC-REPORT-012, SPEC-PARITY-008
Change Type: add/modify
TDD Applicable: yes
Files:
- `tools/workflow_cli/execution_context.py` (new)
- `tools/workflow_cli/atomic.py`
- `tools/workflow_cli/cli.py`
- `tools/r2p-context-view` (new)
- `tools/workflow_cli/agent_templates/claude/commands/r2p-execute.md`
- `tools/workflow_cli/agent_templates/codex/skills/r2p-execute/SKILL.md`
- `tools/workflow_cli/agent_templates/gemini/commands/r2p-execute.toml`
- `tests/test_execution_context.py` (new)
- `tests/test_atomic_write.py`
- `tests/test_cli.py`
- `tests/test_docs_consistency.py`
- `tests/test_install.py`
- `README.md`
Skeleton:
```python
@dataclass(frozen=True)
class ContextSource:
    path: str
    raw_bytes: int
    semantic_bytes: int

@dataclass(frozen=True)
class ContextView:
    work_id: str
    sources: tuple[ContextSource, ...]
    raw_bytes: int
    semantic_bytes: int
    content: str

def build_context_view(base_path, work_id) -> ContextView:
    """Read the fixed sources through one pinned run tree and emit no partial view."""
```
Steps:
- [ ] Write failing tests first for component-by-component directory-fd pinning, final-file pre-stat/open/fstat identity, FIFO/device/directory/symlink rejection, capability failure, fd closure, and parent-path replacement after pin.
- [ ] Add golden human/JSON tests for fixed source order, `strip_nonsemantic_markdown`, Unicode byte counts, whitespace-only content, separators, exactly one final newline, stable success/error keys, exit codes, and no partial output.
- [ ] Implement the reusable no-follow directory-fd readers in `atomic.py` and the deterministic aggregation/result model in `execution_context.py`; validate `run.md`, WorkId, and `EXECUTING` through the same pinned run fd.
- [ ] Register internal `context-view --work-id`, add `tools/r2p-context-view`, and rely on the existing installer glob while testing install/uninstall/bootstrap forwarding.
- [ ] Replace direct ACS ingestion in both full execute surfaces with role-side context-view use, set `semantic_view/semantic_payload_bytes`, and reduce persistent reports/reviews to the required sections while preserving every concern and `⚠️ DEFER` both on disk and inline.
- [ ] Update Gemini's concise prerequisite, docs-consistency locks, and README command/output documentation without creating a persistent context bundle or weakening final-review inputs.
Verification: Run `.venv/bin/python -m pytest tests/test_execution_context.py tests/test_atomic_write.py tests/test_cli.py tests/test_docs_consistency.py tests/test_install.py -q`; record exit 0, byte-count fixtures, and duration. Because this slice changes shared safe-read and CLI paths, also run `.venv/bin/python -m pytest tests/ -q` with trigger reason `shared/core trusted-input path`.

### PLAN-TASK-003 — Phase 2: cohesive PLAN task formation across every continue surface
Spec References: SPEC-GRANULARITY-004, SPEC-PARITY-008
Change Type: modify
TDD Applicable: yes
Files:
- `tools/workflow_cli/stage_templates.py`
- `tools/workflow_cli/agent_templates/claude/SKILL.md`
- `tools/workflow_cli/agent_templates/claude/commands/r2p-continue.md`
- `tools/workflow_cli/agent_templates/codex/skills/r2p-continue/SKILL.md`
- `tools/workflow_cli/agent_templates/gemini/commands/r2p-continue.toml`
- `tests/test_stage_templates.py`
- `tests/test_docs_consistency.py`
- `tests/test_install.py`
Skeleton:
```python
_PLAN_GRANULARITY_NOTE = (
    "Group one observable contract outcome with its implementation, tests, "
    "required wrappers, synchronized agent surfaces, and documentation."
)
```
Steps:
- [ ] Write failing tests first that require the three cohesive-slice criteria and positive/negative examples on the stage seed, Claude generic/command surfaces, Codex skill, Gemini prompt, and installed OpenCode-derived command.
- [ ] Replace the task-per-file/task-per-class guidance with outcome-first grouping: independently verifiable, independently reviewable, and independently reversible without a broken interface or schema.
- [ ] State that implementation, direct tests, wrappers, install surfaces, agent surfaces, and docs for one behavior stay in one task, while unrelated acceptance outcomes stay separate.
- [ ] Preserve `PLAN_TASK_FIELDS`, stage schema, trace closure, quality gates, checkbox grammar, no-deferral text, and existing ambiguity/hardening tokens unchanged.
Verification: Run `.venv/bin/python -m pytest tests/test_stage_templates.py tests/test_docs_consistency.py tests/test_install.py -q`; record exit 0 and duration. Do not run a task-level full suite unless the diff escapes the listed template/test files or a directly affected test fails; the final reviewer still runs the mandatory full suite.

### PLAN-TASK-004 — Phase 3: representative-evidence gate and fail-closed strict/fast execution profiles
Spec References: SPEC-SAMPLE-003, SPEC-FAST-005, SPEC-RESUME-006, SPEC-FINAL-007, SPEC-PROFILE-013, SPEC-LEDGER-014, SPEC-PARITY-008
Change Type: add/modify
TDD Applicable: yes
Files:
- `tools/workflow_cli/execution_profile.py` (new)
- `tools/workflow_cli/execution_metrics.py`
- `tools/workflow_cli/execution_context.py`
- `tools/workflow_cli/agent_shortcuts.py`
- `tools/workflow_cli/cli.py`
- `tools/workflow_cli/agent_templates/claude/commands/r2p-execute.md`
- `tools/workflow_cli/agent_templates/codex/skills/r2p-execute/SKILL.md`
- `tools/workflow_cli/agent_templates/gemini/commands/r2p-execute.toml`
- `tests/test_execution_profile.py` (new)
- `tests/test_agent_shortcuts.py`
- `tests/test_cli.py`
- `tests/test_gates.py`
- `tests/test_docs_consistency.py`
- `tests/test_install.py`
- `README.md`
Skeleton:
```python
class ExecutionProfile(Enum):
    STRICT = "strict"
    FAST = "fast"

def parse_execution_ledger(text, plan_task_ids):
    """Return initial/effective profile and the legal task-state segments."""

def validate_representative_samples(sample_dirs, instrumentation_schema):
    """Validate three pinned archived strict runs and return measured aggregates."""

def fast_structure_eligible(tier) -> bool:
    """Accept only locked LIGHT with an empty modifier set."""
```
Steps:
- [ ] Before any Phase 3 source edit, validate three user-specified local archived run directories against SPEC-SAMPLE-003; persist the per-run aggregates in the task report. If the evidence set is insufficient, return `BLOCKED: representative_metrics_missing`, leave this task unchecked, and make no Phase 3 source change.
- [ ] After the evidence gate passes, write failing tests first for the closed fast preflight/confirm/reject zero-mutation matrix, direct-confirm trust boundary, exact LIGHT/no-modifier structure gate, semantic reject path, executing same/different/flag conflicts, and legacy strict behavior.
- [ ] Add parser tests for exact profile/event/marker characters, fence/comment masking, reviewed/implemented/untouched segments, unique SHA resolution, BASE ancestry, first actionable task, strict recovery ordering, and one-way escalation.
- [ ] Add crash tests for the one-write fast final marker/checkbox migration and archive tests proving implemented tasks remain incomplete until final primary review and the last Approved verdict.
- [ ] Implement profile/sample/ledger pure helpers, wire shortcut arguments and `run-execute-start --profile`, and keep omitted profile strict. Reuse pinned safe reads for samples and never mutate evidence directories.
- [ ] Update Claude/Codex execute protocols in lockstep for the two-step semantic handshake, N-plus-one minimum fast topology, runtime fast-to-strict recovery, profile-specific final inputs, full suite, metrics for every actual fix/re-review role, and atomic final completion; keep OpenCode derived and Gemini truthful/concise.
- [ ] Update README and regression locks without changing the existing PLAN checkbox regex, completion gate, final-review gate, archive contract, dirty-tree discipline, or wrapper forwarding.
Verification: Run `.venv/bin/python -m pytest tests/test_execution_profile.py tests/test_agent_shortcuts.py tests/test_cli.py tests/test_gates.py tests/test_docs_consistency.py tests/test_install.py -q`; record exit 0 and duration. Because this slice changes shared shortcut/CLI/resume paths, also run `.venv/bin/python -m pytest tests/ -q` with trigger reason `shared/core profile and recovery path`.

## Execution Readiness

- Requirement brief, risk discovery, DESIGN v4, and SPEC v3 are approved; forced reviews report no unresolved ambiguity or undecided point.
- The four tasks are the requested Phase 0, Phase 1, Phase 2, and Phase 3 sequence; each owns one independently testable/reviewable/revertible outcome rather than a file/class quota.
- Phase 3's three-run evidence checkpoint is an explicit in-task prerequisite; failure keeps the same task incomplete and does not remove any in-scope behavior from this requirement.
- All source edits occur serially on the current branch. At each task boundary capture full HEAD as BASE, require a clean tree, make one task-scoped commit, and review the exact BASE-to-HEAD diff; never use `HEAD~1` to reconstruct BASE.
- Use fresh zero-history role invocations. The controller may retain only bounded summaries; role artifacts and metrics remain the local audit record.
- No push, pull request, remote mutation, shared implementer, parallel current-branch writes, batch reviewer, balanced profile, persistent context bundle, third-party dependency, or change to PLAN/gate checkbox semantics is authorized.
- Task-level verification follows SPEC-VERIFY-001; every final reviewer and final re-reviewer runs a fresh `.venv/bin/python -m pytest tests/ -q`.

## Risk Handling

| Risk | Handling Task | Closure |
|---|---|---|
| RISK-PERF-001 | PLAN-TASK-001 | [ADDRESSED] targeted-first role matrix plus recorded full-suite triggers and mandatory final suite |
| RISK-CTX-002 | PLAN-TASK-001, PLAN-TASK-002 | [ADDRESSED] zero-history self-contained dispatch and role-side semantic view |
| RISK-METRIC-003 | PLAN-TASK-001, PLAN-TASK-004 | [ADDRESSED] exact measured schema, non-authoritative finalization, and strict sample gate |
| RISK-IO-004 | PLAN-TASK-001, PLAN-TASK-002, PLAN-TASK-004 | [ADDRESSED] no-clobber transaction and pinned no-follow reads |
| RISK-CONTRACT-005 | PLAN-TASK-002 | [ADDRESSED] fixed source order, byte formulas, output schema, and no partial content |
| RISK-AUDIT-006 | PLAN-TASK-001, PLAN-TASK-002 | [ADDRESSED] canonical invocation blocks and compact concern/defer-preserving artifacts |
| RISK-GRAN-007 | PLAN-TASK-003 | [ADDRESSED] three cohesive-slice tests across all continue surfaces |
| RISK-PROFILE-008 | PLAN-TASK-004 | [ADDRESSED] strict default plus structural and semantic fast gates before mutation |
| RISK-RESUME-009 | PLAN-TASK-004 | [ADDRESSED] exact ledger segments, BASE chain, atomic final migration, and strict recovery |
| RISK-FINAL-010 | PLAN-TASK-004 | [ADDRESSED] profile-specific primary final review, fresh full suite, and unchanged archive gates |
| RISK-PARITY-011 | PLAN-TASK-001, PLAN-TASK-002, PLAN-TASK-003, PLAN-TASK-004 | [ADDRESSED] Claude/Codex lockstep, OpenCode derivation, Gemini truthfulness, and install tests |
| RISK-SEQUENCE-012 | PLAN-TASK-004 | [ADDRESSED] three finalized archived strict runs must pass before any Phase 3 source edit |

## Trace

| This ID | Upstream | Status |
|---|---|---|
| PLAN-TASK-001 | SPEC-VERIFY-001, SPEC-ROLE-002, SPEC-METRICS-009, SPEC-PARITY-008; SCOPE-IN-001, SCOPE-IN-002, SCOPE-IN-003, SCOPE-IN-010 | [ADDRESSED] Phase 0 foundation is independently verifiable and revertible |
| PLAN-TASK-002 | SPEC-CONTEXT-010, SPEC-CONTEXT-011, SPEC-REPORT-012, SPEC-PARITY-008; SCOPE-IN-004, SCOPE-IN-005, SCOPE-IN-010 | [ADDRESSED] Phase 1 context and audit path is one cohesive behavior slice |
| PLAN-TASK-003 | SPEC-GRANULARITY-004, SPEC-PARITY-008; SCOPE-IN-006, SCOPE-IN-010 | [ADDRESSED] Phase 2 changes guidance only and preserves machine schema |
| PLAN-TASK-004 | SPEC-SAMPLE-003, SPEC-FAST-005, SPEC-RESUME-006, SPEC-FINAL-007, SPEC-PROFILE-013, SPEC-LEDGER-014, SPEC-PARITY-008; SCOPE-IN-007, SCOPE-IN-008, SCOPE-IN-009, SCOPE-IN-010 | [ADDRESSED] Phase 3 remains in this run behind its explicit evidence prerequisite |

## Upstream Summary (read-only)
# Spec

## Behavior Contracts
### SPEC-VERIFY-001 — Role verification cadence
Upstream: DES-EXEC-001 [ADDRESSED]

1. Implementer、task reviewer、fixer 和 task re-reviewer 默认只运行当前 task `Verification` 指定的 targeted tests 与可证明 directly affected tests。
2. 仅当满足下列任一条件时，task-level role 才运行 full suite：task 修改 shared/core path；风险/安全/迁移边界要求；targeted 失败；changed files 超出 brief 且无法证明安全；依赖覆盖关系不清；reviewer 无法从 diff、report 和 targeted evidence 建立充分信心。
3. 每次升级必须在 `Verification Records` 和 metrics 中记录 `scope=full_suite` 与具体 `reason`，不能只写“为保险起见”。
4. final reviewer 与每次 final re-reviewer 无条件运行 fresh full suite；final fixer 自己默认 targeted，修复后的 final re-review 再执行 full suite。
5. PLAN `Verification` 仍可显式要求 task-level full suite；显式要求属于 trigger，角色不得擅自降为 targeted。

### SPEC-ROLE-002 — Fresh role dispatch and zero inherited history
Upstream: DES-EXEC-001 [ADDRESSED]

1. 每次 role dispatch 都必须创建一个新的 child/subagent invocation；不得继续、复用或重新唤醒任何先前 implementer、reviewer、fixer、re-reviewer 或 final-role thread/session。
2. Codex 每次 dispatch 固定使用 `fork_turns="none"`。其他平台若暴露 inherited-history 参数，必须把 inherited turns/messages 设为零；若没有该参数，只能使用平台明确保证“不继承 controller/parent conversation”的新会话 API。无法保证时该平台在 dispatch 前 fail explicitly，不得以“fresh/minimal-history 等价”宣称合规。
3. Claude、OpenCode 与 Gemini 的安装 surface 必须分别写明其实际可调用的新会话机制或上述 fail-closed 分支；Gemini 仅能表达 wrapper/prompt prerequisite 时，不得声称已提供 subagent 能力。
4. 每个 role handoff 只包含自包含字段：work ID/run dir、role、task brief 或 final input paths、context-view 命令、Git/BASE 边界、verification/report/inline return contract。控制器不得粘贴 ACS、上一角色正文或 controller 对话摘要。

### SPEC-SAMPLE-003 — Representative metrics checkpoint
Upstream: DES-EXEC-001 [ADDRESSED]；DES-PROFILE-004 [ADDRESSED]

Phase 3 task 接受用户明确指定的本地 archived run directories 作为只读证据。每个候选先 lstat 拒绝 symlink/non-directory，再取得 strict canonical path，并从 filesystem root 对 canonical components 做 no-follow stable directory-fd traversal；三个 canonical paths 必须两两不同，目录 basename 必须等于经 `WorkId.parse` 验证的 embedded work ID。`run.md`、PLAN、progress、metrics 和 final-review 均相对 pinned sample fd 使用 no-follow pre-stat/open/fstat regular-file read；任何 symlink、non-regular、race 或读取失败只令该 sample 不合格，不修改样本或当前 run。

合格集合必须同时满足：

- 至少三个不同的 `(canonical run path, work_id)`；每个 `run.md` status 为 `archived`。
- metrics header 的 `profile` 为 `strict`、`instrumentation_schema` 等于当前受支持值、`metrics_finalized=true`、`change_shape` 是合法非 unavailable 枚举，并记录非空 `r2p_version`。
- PLAN task count 与 metrics `task_count` 一致；progress 中全部 PLAN tasks 为 `[x]`；final-review 的最后 verdict 为 Approved。
- 每个 run 对每个 task 至少有 implementer 与 task-reviewer block，并有 final-reviewer block；实际发生的 fixer、task re-reviewer、final fixer、final re-reviewer 也必须各有 sequence-contiguous block。发现 report/review/fix-wave 证据而缺 block 时样本失败；不推算不可见调用。
- 每个 invocation 必须有 measured `started_at`、`ended_at`、`elapsed_seconds`、`context_bytes`、`report_bytes`、非空 `verification_records_json` 和 measured `verification_total_seconds`；任一字段为 `unavailable`、invalid 或 totals 不一致时整个 sample 不合格。`context_mode` 与 `context_bytes_kind` 必须是 SPEC-METRICS-009 的合法配对，每条 verification record 必须含 measured duration 与合法 status。
- `model` 和 Token 三字段可为 `unavailable`；Token 不可得不影响资格，但 evidence report 必须明确写 `token comparison: unavailable`，不得用 bytes 推算 Token。
- 三个样本至少具有两个不同 `task_count`，或两个不同 finalized `change_shape`。

任一条件失败时，Phase 3 role 返回 `BLOCKED: representative_metrics_missing`，逐 sample 列出 path/work ID/失败规则，不修改 Phase 3 源码，不勾选任务。证据通过后，task report 除固化 paths、work IDs、r2p versions、schemas、task counts、shapes、role coverage、verdict 与 completeness 外，还必须逐 run 汇总 invocation count、role elapsed total、context bytes total、verification total、report bytes total、full-suite count/duration，以及可得时的 input/output/total Token；若样本跨 `direct_acs`/`semantic_view`，按 context mode 分栏，不能把不同 byte kind 直接相减为 Token 收益。

### SPEC-GRANULARITY-004 — Cohesive change slice rule
Upstream: DES-PLAN-003 [ADDRESSED]

PLAN author 先按一个可观察行为/契约结果分组。每个 task 必须同时满足：自己的 Verification 可独立通过；reviewer 无需等待未完成 sibling 即可判断；task commits 可独立回滚且不会留下破损接口/schema。实现、直接测试、同一行为所需 wrapper、安装面、agent surfaces 和文档属于一个 slice。

禁止 task-per-file/task-per-class 式拆分；也禁止把没有共同验收结果的多个行为合并。此规则只改变生成指导，不改变 `PLAN_TASK_FIELDS`、trace closure、quality gate、checkbox 或 BASE/commit/diff contract。

### SPEC-FAST-005 — Strict/fast role topology and runtime escalation
Upstream: DES-PROFILE-004 [ADDRESSED]

1. strict 是默认且保持 `N fresh implementers + N task reviewers + 1 final reviewer` 的最低结构。
2. fast 仅在 handshake 完成后使用 `N fresh implementers + 1 primary final reviewer` 的最低结构；fix/re-review waves 会增加调用数，`N+1` 不是硬上限。
3. fast implementer 提交并验证后，controller 保持 task checkbox `[ ]`，追加合法 implemented marker；不得生成空 task review 充数。
4. 发生 marker/HEAD/BASE 异常、verification failure、unexpected file、concern、`⚠️ DEFER` 未裁决、上游歧义或 shared/core/security/migration/dependency/config 风险时，controller 追加单向 fast→strict escalation event。
5. escalation 后先按 task 顺序 review 所有 implemented-but-unreviewed ranges；clean 后置 `[x]` 并写 strict-compatible complete marker，再从第一个未实现 task 继续 strict loop。已经升级的 run 不得恢复 fast。

### SPEC-RESUME-006 — Profile-aware ledger and BASE recovery
Upstream: DES-PROFILE-004 [ADDRESSED]

1. 新 run 恰有一个 immutable initial profile line；legacy ledger 没有 profile line 且没有 fast-only marker/event 时按 strict 解释。
2. effective profile 是 initial profile 经过最后一个合法 escalation event 后的结果。重复 initial line、strict-origin escalation、重复/逆向 escalation、malformed reason 或 legacy ledger 携带 fast-only marker/event 均为 conflict。
3. Ledger task states 必须按 PLAN number 形成 `reviewed-complete prefix → implemented-but-unreviewed contiguous segment → untouched suffix`；初始 fast 的 reviewed prefix 为空，因此 implemented segment 从 Task 1 开始；fast→strict recovery 可逐 task 扩大 reviewed prefix，剩余 implemented segment 必须紧邻其后。fast resume 跳过前两个 segment，选择 untouched suffix 的最小编号；strict recovery 必须先 review implemented segment，不能先实现 untouched task。任何空洞、乱序或重叠均为 conflict。
4. Task 1 BASE 仅来自 full `Execution BASE`；Task N BASE 仅来自 Task N-1 合法 complete/implemented marker 的 head。不得使用 `HEAD~1` 或 resume 时的新 HEAD 推断 BASE。
5. checked task 不得仍保留 implemented marker。fast final approval 前，controller 重新验证 HEAD、BASE chain、全部 markers 和 task count 未变化，在内存中构造完整新 ledger，将所有 implemented markers 替换为 `Task N: complete (commits <base7>..<head7>, final review clean)` 并将对应 checkbox 全部置 `[x]`，随后只调用一次 `atomic_write_text(progress.md, full_text)`；禁止逐 task 写盘。replace 前失败保留完整旧 fast ledger；replace 后即使进程中断，ledger 也处于全部 strict-compatible complete 状态，final-review gate 仍阻止缺少 Approved verdict 的 archive。
6. abbreviation 必须能由 `git rev-parse --verify` 唯一解析且形成从 Execution BASE 到 current HEAD 的有序祖先链；否则升级 strict recovery 或在无法确定 BASE 时 BLOCKED。

### SPEC-FINAL-007 — Profile-specific final review inputs
Upstream: DES-PROFILE-004 [ADDRESSED]

- strict final reviewer 读取 semantic context view、`07-plan.md`、progress、所有 task reports、所有 task reviews、所有 Minor/concern/`⚠️ DEFER` 和 execution-base→HEAD final diff。
- fast final reviewer 读取 semantic context view、`07-plan.md`、progress、所有 task reports、所有 Minor/concern/`⚠️ DEFER` 和 final diff；不得要求不存在的 task review files。
- fast final reviewer 是每个 task 的 primary reviewer，必须逐 task 检查 Spec References、Files vs diff、verification records、commit range 和 cross-task behavior，并运行 full suite。
- findings 使用现有 single final-fixer + regenerated final diff + final re-review loop。所有实际 dispatch 都产生 metrics block。
- 只有 clean final review 才能替换 markers、置全部 `[x]`、finalize metrics、写最后 `Verdict: Approved` 并调用 archive；archive gate 的 checkbox/final-verdict 语义不变。

### SPEC-PARITY-008 — Agent surface parity
Upstream: DES-COMPAT-005 [ADDRESSED]

- 完整 execute protocol：Claude execute command 与 Codex execute skill 同步。
- OpenCode execute/continue 由 Claude commands 派生；安装测试必须核对派生结果包含 load-bearing tokens。
- Gemini execute/continue 保留 wrapper forwarding，并在 description/prompt 中携带 strict default、fast handshake/preflight、cohesive slice 和 fail-closed 摘要。
- Phase 2 continue 同步面固定为 `stage_templates.py`、Claude 通用 skill、Claude continue command、Codex continue skill、Gemini continue command；不得只更新部分表面。
- `tests/test_docs_consistency.py` 同时保护旧 EXE/FR-CM tokens 与本需求新增 tokens，不删除 dirty-tree、BASE、final review、full suite、`⚠️ DEFER` 或 archive 契约。

## API / Data / Config Contracts
### SPEC-METRICS-009 — Metrics file schema and ownership
Upstream: DES-EXEC-001 [ADDRESSED]

metrics 不参与 run state、resume、completion 或 archive gate；已存在 metrics 永不被普通 resume 覆盖。首次 `run-execute-start --profile strict|fast` 使用下列 recoverable start transaction：

1. 相对 pinned run fd 安全打开 `logs/execute-start.lock`，取得 process-released exclusive nonblocking lock；POSIX 使用 `fcntl.flock(LOCK_EX|LOCK_NB)`。lock busy 或平台没有可靠等价 capability 时 exit 6、zero mutation。lock file 位于已忽略的 `logs/`，必须是 no-follow regular file。
2. 持锁期间用 `mkdir("execution", dir_fd=run_fd)` 原子创建最终目录；`mkdir` 的 EEXIST 是 no-clobber conflict/recovery input，任何并发创建的 empty dir、file 或 symlink 都不会被替换。记录 directory dev/ino，并在其中用 O_EXCL 写 `.start-transaction.json`；它是 canonical single-line JSON，exact fields 为 `schema: 1`、`work_id`、`profile`、`task_count`、`execution_base`（full SHA）。随后原子写入并校验 `progress.md` 与 `metrics.md`。
3. 两个 ledgers 验证完成且 marker 仍存在时保存 `run.md` 的 `EXECUTING` 状态；save 成功后才删除 marker并 fsync directory（capability available 时）。save 前的普通异常触发 best-effort rollback，但只能在仍持锁、directory dev/ino 未变、marker 内容匹配且 children 是 marker/progress/metrics 的允许子集时删除本次目录。save 已成功但 marker cleanup 失败时不得删除 execution；保留 marker 并由 executing recovery 完成。其他情况保留现场并 exit 6。
4. process crash 自动释放 lock。重试取得 lock 后：`closed + marker` 仅在 marker 匹配当前 work/profile/task count/BASE、目录 identity 稳定且 children 是允许子集时删除该 owned partial directory并从步骤 2 重建；`closed + no marker + two exact initial ledgers` 在 structure gate 仍通过时只补做 status transition。fast 两种 recovery 都要求调用者重新给出 `--profile fast --confirm-fast-eligible`。其他 single-file、partial、mismatched、symlinked、foreign-marker 或 extra-child 状态 exit 6 且不覆盖。
5. `executing + no marker + complete ledgers` 走 normal idempotent resume；`executing + matching marker + complete ledgers` 在持锁复核 status/work/profile/task count/BASE 后只删除 marker并继续 resume；`executing + marker/missing/partial/mismatched ledgers` fail closed。没有 sibling temporary directory，因此 crash-before-ledger 不产生未忽略的 worktree residue。fault injection 必须覆盖 lock/capability、mkdir 前后 crash、marker/progress/metrics writes、status save、marker removal、owned rollback/rebuild、executing marker cleanup、foreign residue和 concurrent file/empty-dir/symlink no-clobber。

本需求自身由旧版本启动执行时允许一次 bootstrap exception：在首个 role dispatch 前，controller 仅可在 run 已为 `EXECUTING`、现有 progress 为 no-profile legacy strict、work ID/PLAN task count/Execution BASE 均匹配、`metrics.md` 经 lstat 确认为不存在且 pinned `execution/` directory 安全时创建同 schema 的 strict header；否则返回 `BLOCKED`。这不是普通 resume 的 silent repair。

Header fields and values:

```text
# Execution Metrics
work_id: <validated WorkId>
r2p_version: <R2P_VERSION>
instrumentation_schema: <positive integer constant>
profile: strict|fast
task_count: <PLAN anchor count>
change_shape: unavailable
metrics_finalized: false
```

Invocation block grammar（字段顺序固定，每个 scalar 占一行；invocation 编号从 1 连续且唯一）：

```text
## Invocation <contiguous positive integer>
role: implementer|task_reviewer|fixer|task_rereviewer|final_reviewer|final_fixer|final_rereviewer
task: <positive integer>|final
model: <non-empty identifier>|unavailable
started_at: <UTC YYYY-MM-DDTHH:MM:SS.ffffffZ>
ended_at: <UTC YYYY-MM-DDTHH:MM:SS.ffffffZ>
elapsed_seconds: <non-negative decimal with exactly 6 fractional digits>
context_mode: direct_acs|semantic_view
context_bytes_kind: declared_payload_bytes|semantic_payload_bytes
context_bytes: <non-negative integer>
verification_records_json: <single-line canonical JSON array>|unavailable
verification_total_seconds: <non-negative decimal with exactly 6 fractional digits>|unavailable
report_bytes: <non-negative integer>
status: complete|approved|changes_requested|blocked
concerns_json: <single-line canonical JSON array of strings>
fix_wave: <non-negative integer>
input_tokens: <non-negative integer>|unavailable
output_tokens: <non-negative integer>|unavailable
total_tokens: <non-negative integer>|unavailable
```

`verification_records_json` 的每项恰有 `command`、`scope`、`reason`、`elapsed_seconds`、`status`；scope 为 `targeted|directly_affected|full_suite`，status 为 `passed|failed`，command/reason 是非空 string，elapsed 是匹配 `^[0-9]+\.[0-9]{6}$` 的 JSON string。Writer 使用 `json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":"))`；parser 要求单行 UTF-8 JSON、exact keys、无 NaN/Infinity。`concerns_json` 同样 canonical；无 concern 为 `[]`。successful invocation 的 records 必须非空；仅 `blocked` invocation 可写 `unavailable`，此时 total 也必须 unavailable。其他情况下 controller 用 `Decimal` 对 record duration strings 求和并输出 exactly six decimals；total 必须精确相等。

Role/task/status/fix-wave matrix 固定如下：

- `implementer|fixer`：task 是正 PLAN task number，status `complete|blocked`；`implementer` wave 0，`fixer` wave 从 1 开始。
- `task_reviewer|task_rereviewer`：task 是正 PLAN task number，status `approved|changes_requested|blocked`；初次 reviewer wave 0，fixer 与其对应 re-reviewer 使用相同正 wave。
- `final_reviewer|final_fixer|final_rereviewer`：task 恰为 `final`；initial final reviewer wave 0，final fixer 与对应 final re-reviewer 使用相同正 wave；mutation role 只允许 `complete|blocked`，review role 只允许 `approved|changes_requested|blocked`。
- `direct_acs` 只配 `declared_payload_bytes`，`semantic_view` 只配 `semantic_payload_bytes`。Token 三字段要么全部 unavailable，要么全是整数且 `total=input+output`。

Controller owns every block and measures role timestamps/context/report bytes；timestamps use wall clock。Controller 与 role 均用 `time.monotonic_ns()` 捕获 start/end，要求 `end_ns >= start_ns`，再计算 `Decimal(end_ns-start_ns) / Decimal(1_000_000_000)`，以 `ROUND_HALF_UP` quantize 到 `Decimal("0.000001")` 并保留六位序列化；小于/等于/大于半微秒的边界都按此规则。Role 对每条 verification command 使用同一算法，persists `Verification Records`, and returns records plus total inline；total 只精确求和已量化 strings，不再次 quantize。Controller validates/copies values, never infers them；invalid return becomes a blocked/concerned block and cannot qualify as a representative sample。`direct_acs/declared_payload_bytes` is the raw UTF-8 sum of the six declared ACS sources；`semantic_view/semantic_payload_bytes` is context-view aggregate semantic bytes。

Final clean 时 controller 从 full `Execution BASE` 与 `HEAD` 运行 `git diff --name-status -z <base> HEAD --` 并按 NUL records 解析。accepted token grammar 恰为：单路径 `A|M|D|T`；双路径 `Rddd|Cddd`，其中 `ddd` 恰为三位十进制 `000..100`。A/M/D/T 使用一个 path；R/C 同时计 old 与 new path。`U|X|B`、缺失/多余 path、score >100、非三位 score 及任何其他 token 一律使 finalization 失败。Invalid Git output、空 changed-path set 或不是 repo-relative POSIX path 的值同样失败。路径比较 case-sensitive；拒绝 absolute、空 component、`.` 或 `..`。对所有合法 changed paths 执行以下唯一算法：

1. 若任一完整 path component 恰为 `migration` 或 `migrations`，返回 `migration`。
2. Test path：任一 component 恰为 `test|tests`，或 basename 匹配 `^test_.+`、`^.+_test(?:\..+)?$`、`^.+\.test\..+$`、`^.+\.spec\..+$`。若所有 changed paths 都是 test，立即返回 `test_only`。
3. 从后续判断移除 tests。Doc path：first component 为 `docs`，或 suffix 恰为 `.md|.rst|.adoc|.txt`。Config path：suffix 恰为 `.json|.yaml|.yml|.toml|.ini|.cfg|.properties`。其余 non-test path 为 source。
4. 若 source 非空，root-level source module 为 `_root`，其他 source module 为 first component；一个 unique module 返回 `single_module_code`，多于一个返回 `cross_module_code`。同行存在 docs/config 不改变该 code 分类。
5. 若 source 为空且 non-test set 非空：全部 doc 返回 `docs_only`；否则全部 config 返回 `config_only`；docs+config 或其他组合返回 `mixed`。

Classifier 枚举仅为 `migration|single_module_code|cross_module_code|docs_only|config_only|test_only|mixed`。tests 必须覆盖 add/modify/delete、rename/copy、root source、大小写、migration test path、docs+tests、config+tests、docs+config 与 empty diff。Controller 一次 `atomic_write_text` 替换完整 metrics header 为枚举值和 `metrics_finalized: true`；任何分类/写入失败保留 unavailable/false，archive 正确性不受影响，但该 run 不能成为 Phase 3 样本。

### SPEC-CONTEXT-010 — Stable directory-fd read API
Upstream: DES-CTX-002 [ADDRESSED]

新增 atomic primitives 必须：

1. 用 `os.open` 的 `dir_fd`、`O_DIRECTORY`、`O_NOFOLLOW`、`O_NONBLOCK` 逐组件打开 repo root → `.req-to-plan` → work ID → `execution`；缺少平台能力时抛出 unsafe conflict。
2. 相对 pinned dir fd 对 final file 执行 no-follow pre-stat → `open(O_NOFOLLOW|O_NONBLOCK)` → fstat，并比较 dev/ino/regular mode；FIFO/device/directory/symlink/race 均不读取。
3. 从同一个 pinned run fd 读取并解析 `run.md`，验证 embedded WorkId 与请求值相同、status 为 `EXECUTING`；不得混用另一次 path-based record load。
4. pin 后父 path 被 rename/replaced 时继续读取原 pinned tree；不承诺侦测 path-name drift，也不得重开路径切换到替换树。
5. 所有 fds 在成功/异常路径关闭；不产生临时 context files。

### SPEC-CONTEXT-011 — Context view command and output
Upstream: DES-CTX-002 [ADDRESSED]

Public wrapper：`r2p-context-view --work-id <id>`；internal command：`context-view --work-id <id>`；无 `--role`。仅 EXECUTING run 可成功。

Source order is fixed:

1. `02-project-context.md`
2. `03-requirement-brief.md`
3. `04-risk-discovery.md`
4. `05-design.md`
5. `06-spec.md`
6. `execution/progress.md`

For each source:

```text
semantic = strip_nonsemantic_markdown(raw).rstrip()
source.raw_bytes = len(raw.encode("utf-8"))
source.semantic_bytes = len(semantic.encode("utf-8"))
chunk = "===== " + relative_path + " =====\n" + semantic
content = "\n\n".join(chunks) + "\n"
aggregate.raw_bytes = sum(source.raw_bytes)
aggregate.semantic_bytes = len(content.encode("utf-8"))
```

Human success uses `sys.stdout.write(content)` and no formatter prefix. JSON success keys are exactly the existing success envelope plus `work_id: str`、`sources: list[{path,raw_bytes,semantic_bytes}]`、`raw_bytes: int`、`semantic_bytes: int`、`content: str`；`status="ok"` and `message` remain present. Invalid args exit 2；missing run/source exit 7；wrong status、unsafe path/type/race/capability exit 6。Error JSON uses existing `status/message/exit_code/details?` and never includes partial content/sources。

### SPEC-REPORT-012 — Compact role artifacts and inline return
Upstream: DES-CTX-002 [ADDRESSED]

Every persistent report/review has these non-optional sections：`Status`、`Commit Range`、`Changed Files`、`Verification Records`、`Concerns`、`⚠️ DEFER`。Task review additionally has `Spec Verdict` and `Quality Verdict`。不存在的 concerns/defer 明确写 `none`。任何角色发现的每条 concern/defer 必须同时进入持久文件和 inline `concerns`。

Inline return keeps existing status/path/commit/test fields and adds `verification_records` and `verification_total_seconds`；controller narration仍只保留 bounded summary，不粘贴报告正文。Fast final consumes every task report；strict final consumes reports and reviews。

### SPEC-PROFILE-013 — Execute profile CLI handshake
Upstream: DES-PROFILE-004 [ADDRESSED]

Shortcut arguments：`--profile {strict,fast}` optional、`--confirm-fast-eligible` boolean、`--reject-fast-ineligible` boolean、`--reason <single-line>`。Confirm/reject mutually exclusive；它们只允许和 `--profile fast` 一起；reason 只允许且必须和 reject 一起。Invalid combinations exit 2 before mutation。

Deterministic structure eligibility 恰为 locked tier base `LIGHT` 且 modifier set 为空；STANDARD、任何 modifier、未锁 tier 或无法解析的 tier 都是 ineligible。结构门通过后，agent semantic gate 必须逐 PLAN task 确认：行为局部且机械；`Files` 明确且不触及 shared/core/security/migration/dependency/config；没有 unresolved ambiguity/undecided point；`Verification` 是可直接执行且能独立判定该 task 的确定性命令。任一 false/unknown 都必须 reject，不能 confirm。

Closed run matrix:

| Invocation | Result | Mutation |
|---|---|---|
| profile omitted / `strict` | start strict; seed ledgers | yes |
| `fast` without decision flag, structure ineligible | exit 6 `fast_profile_ineligible` | none |
| `fast` without decision flag, structure eligible | exit 0 stop `fast_profile_review` with work/plan/tier/modifiers | none |
| `fast --reject-fast-ineligible --reason ...` | exit 6 `fast_profile_ineligible` | none |
| `fast --confirm-fast-eligible`, structure eligible | start fast; seed ledgers | yes |
| `fast --confirm-fast-eligible`, structure changed/ineligible | exit 6 | none |

Direct terminal confirm is an explicit trusted human attestation；CLI validates structure but does not claim semantic validation。Agent surfaces must always perform PLAN semantic review between first stop and confirm/reject。

Executing matrix：no profile → reuse effective；same profile → idempotent resume；different profile → exit 6；任何 confirm/reject flag → exit 6。Legacy ledger without profile → strict。Other run statuses retain `plan_not_ready` conflict。

### SPEC-LEDGER-014 — Profile and task marker grammar
Upstream: DES-PROFILE-004 [ADDRESSED]

New ledger lines use exact unfenced grammar:

```text
Execution Profile: strict
Execution Profile: fast
Profile Escalation: fast -> strict (reason: <non-empty single line>)
Task N: implemented (commits <base7>..<head7>, verification recorded)
Task N: complete (commits <base7>..<head7>, final review clean)
```

Initial profile is unique and immutable。Only one fast→strict event is legal。Parser rejects malformed/duplicate/contradictory lines and fast-only lines in a legacy profile-less ledger。Existing strict marker `Task N: complete (commits <base7>..<head7>, review clean)` remains accepted for backward compatibility。Checkbox regex/gate stays unchanged；implemented marker never satisfies completion。

Parser 先使用 `strip_nonsemantic_markdown`，因此 fenced examples 与 HTML comments 不产生 ledger tokens。`N` 是无前导零的正十进制数并必须等于对应 PLAN number；`base7/head7` 恰为小写 `[0-9a-f]{7}`；reason 拒绝 `\r`/`\n` 且 trim 后非空。每个 task 在任一合法 ledger state 最多一条 implemented 或 complete marker，不得同时存在两者；profile/event/marker-like malformed lines fail closed，而不是被忽略。

## External Documentation Checked
N/A — no external dependencies

## Test Matrix
| Contract | Required deterministic coverage |
|---|---|
| SPEC-VERIFY-001 / SPEC-ROLE-002 | 双 execute surfaces 包含 targeted escalation matrix、final full suite、all-role metrics、Codex `fork_turns="none"`；各平台 new-session/no-history 或 fail-closed；旧 hardening tokens 仍存在。 |
| SPEC-METRICS-009 | locked no-clobber execute-start transaction、marker/status crash recovery、foreign residue 与 fault injection、legacy self-bootstrap；exact header/JSON grammar、role/task/status/wave matrix、`monotonic_ns` + `ROUND_HALF_UP` boundary/totals、context pair、all-role blocks；A/M/D/T/Rddd/Cddd classifier table 与 failed-finalize non-gating。 |
| SPEC-CONTEXT-010 | temp workspace 中 directory/file symlink、non-regular、FIFO、pre-stat/open race、capability unavailable、fd cleanup、parent replacement pinned-tree behavior。 |
| SPEC-CONTEXT-011 | Unicode、comments、read-only blocks、fences、whitespace-only、fixed order/separators/one newline、per-source/aggregate bytes、human/JSON exact keys、missing/no partial、wrong status。 |
| SPEC-REPORT-012 | 两完整 execute surfaces 强制所有 section、inline verification、every-role `⚠️ DEFER` propagation；fast/strict final input matrix。 |
| SPEC-GRANULARITY-004 / SPEC-PARITY-008 | stage template + 五 continue surfaces + OpenCode derived install + Gemini description；PLAN fields/schema/trace tests unchanged。 |
| SPEC-PROFILE-013 | closed handshake 参数矩阵、zero-mutation snapshots、structure recheck、reject reason newline rejection、direct confirm、executing same/different/flags、legacy strict。 |
| SPEC-LEDGER-014 / SPEC-RESUME-006 | comment/fence-aware exact regex、unique profile/events/markers、malformed lines、marker continuity、BASE chain、checked/implemented conflict、first actionable task、strict escalation/recovery、atomic all-task final migration crash points、legacy strict complete marker。 |
| SPEC-FAST-005 / SPEC-FINAL-007 | fast no per-task reviews、runtime triggers strict recovery、final primary task-by-task review、full suite、fix/re-review metrics、checkbox only after approval、archive gate fails before approval。 |
| SPEC-SAMPLE-003 | 三 canonical no-follow archived paths、schema/profile/finalized/verdict/task count/role coverage、required measured fields/totals、fix-wave evidence、shape/task diversity、per-run aggregates；每个失败分支保持 Phase 3 source/checkbox 不变。 |

Implementation verification uses project-required `.venv/bin/python -m pytest`。每个 PLAN task 先运行其 targeted module/tests；每个 Phase task review 根据 SPEC-VERIFY-001 决定是否 full suite；最终 whole-branch review 必须运行 `.venv/bin/python -m pytest tests/ -q` 并记录 fresh result。

## Non-goals
- 不生成持久化 ACS/context bundle、manifest、content hash 或 drift gate。
- 不改变 CLI/agent responsibility boundary；CLI 只管理结构、安全读取和 deterministic parsing/formatting。
- 不引入 shared implementer、parallel current-branch writes、batch reviewer 或 balanced profile。
- 不弱化 dirty-tree、Execution BASE、task commit/diff、final full suite、final verdict 或 archive gate。
- 不把 unavailable/estimated values 写成 measured metrics，不把 bytes reduction 声称为精确 Token reduction。
- 不新增第三方依赖；directory-fd/context/filter/profile logic 使用 Python stdlib 与仓库现有模块。

## PLAN Handoff
PLAN 必须形成四个顺序 cohesive slices，每个 task 的 `Files` 同时覆盖实现、测试和同步 surface，且引用下列完整 SPEC 集合：

1. **Phase 0 — cadence/zero-history/metrics foundation**：实现 SPEC-VERIFY-001、SPEC-ROLE-002、SPEC-METRICS-009，以及 execute surfaces 的相关 SPEC-PARITY-008；包括 instrumentation schema、metrics seeding、all-role producer/records、change finalization contract。
2. **Phase 1 — context view/compact audit**：实现 SPEC-CONTEXT-010、SPEC-CONTEXT-011、SPEC-REPORT-012，以及 wrapper/install/execute-surface parity；安全 directory-fd primitives 与 CLI/wrapper/report protocol 在同一 slice。
3. **Phase 2 — PLAN task granularity**：实现 SPEC-GRANULARITY-004 与 continue 部分的 SPEC-PARITY-008；不修改 PLAN schema/gates。
4. **Phase 3 — strict/fast profile**：入口先执行 SPEC-SAMPLE-003 checkpoint；证据通过后实现 SPEC-PROFILE-013、SPEC-LEDGER-014、SPEC-FAST-005、SPEC-RESUME-006、SPEC-FINAL-007 与 profile-related parity。证据失败保持 task 未完成并返回 BLOCKED。

Global Constraints 必须保留：TDD-first；所有 source edits 在当前分支串行；每 task clean-tree/BASE/commit/diff；无 commit/push/PR 授权扩张；Claude/Codex lockstep；OpenCode derived/Gemini tests；metrics non-authoritative；final review/full suite/archive gates 不变。

## Trace
<!-- Map this stage's IDs to upstream/downstream. R3 derives & checks closure. -->
| This ID | Upstream | Status |
|---|---|---|
| Spec headings above | Approved DESIGN v4 | [ADDRESSED] Every chosen design decision is encoded as behavior, API/data, error, recovery, observability, and test contracts. |
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
