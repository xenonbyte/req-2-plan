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

1. Codex 的 implementer、reviewer、fixer、re-reviewer 与 final roles 均使用 `fork_turns="none"`；不得共享 implementer session。
2. Claude/OpenCode 使用 fresh/minimal-history 等价能力；Gemini 入口必须把相同 hard prerequisite 写入可表达的 prompt/description。平台没有 subagent 能力时按现有协议 fail explicitly。
3. 每个 role handoff 必须自包含：work ID/run dir、role、task brief 或 final input paths、context-view 命令、Git/BASE 边界、verification/report/inline return contract。控制器不得粘贴 ACS 或上一角色正文。

### SPEC-SAMPLE-003 — Representative metrics checkpoint
Upstream: DES-EXEC-001 [ADDRESSED]；DES-PROFILE-004 [ADDRESSED]

Phase 3 task 接受用户明确指定的本地 archived run directories 作为只读证据。合格集合必须同时满足：

- 至少三个不同的 `(canonical run path, work_id)`；每个 `run.md` status 为 `archived`。
- metrics header 的 `profile` 为 `strict`、`instrumentation_schema` 等于当前受支持值、`metrics_finalized=true`、`change_shape` 是合法非 unavailable 枚举，并记录非空 `r2p_version`。
- PLAN task count 与 metrics `task_count` 一致；progress 中全部 PLAN tasks 为 `[x]`；final-review 的最后 verdict 为 Approved。
- 每个 run 对每个 task 至少有 implementer 与 task-reviewer block，并有 final-reviewer block；实际发生的 fixer、task re-reviewer、final fixer、final re-reviewer 也必须各有 sequence-contiguous block。无法证明的隐藏调用不做推算，但发现 report/review/fix-wave 证据而缺 block 时样本失败。
- 每个 role block 含有效 role/task/status；started/ended/elapsed、context bytes、verification records/total、report bytes 与 Token 可以是 measured value 或 `unavailable`，不得填估算值。
- 三个样本至少具有两个不同 `task_count`，或两个不同 finalized `change_shape`。

任一条件失败时，Phase 3 role 返回 `BLOCKED: representative_metrics_missing`，列出失败 sample/reason，不修改 Phase 3 源码，不勾选任务。证据校验通过后，task report 固化 paths、work IDs、r2p versions、schemas、task counts、shapes、role coverage、verdict 与 completeness 结论。

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
3. fast resume 跳过 `[x]` tasks 和具有合法 implemented marker 的 tasks，选择编号最小、两者都没有的 task。implemented markers 必须从 Task 1 起连续且与 PLAN task number 对齐。
4. Task 1 BASE 仅来自 full `Execution BASE`；Task N BASE 仅来自 Task N-1 合法 complete/implemented marker 的 head。不得使用 `HEAD~1` 或 resume 时的新 HEAD 推断 BASE。
5. checked task 不得仍保留 implemented marker。fast final approval将每个 implemented marker 替换为 `Task N: complete (commits <base7>..<head7>, final review clean)` 后才置 `[x]`。
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

`run-execute-start --profile strict|fast` 在 `execution/` 不存在时原子生成 `progress.md` 和 `metrics.md`。metrics 不参与 run state、resume、completion 或 archive gate。已存在 metrics 不被 resume 覆盖。

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

Invocation block schema:

```text
## Invocation <contiguous positive integer>
role: implementer|task_reviewer|fixer|task_rereviewer|final_reviewer|final_fixer|final_rereviewer
task: <positive integer>|final
model: <non-empty identifier>|unavailable
started_at: <ISO-8601 timestamp>|unavailable
ended_at: <ISO-8601 timestamp>|unavailable
elapsed_seconds: <non-negative decimal>|unavailable
context_mode: direct_acs|semantic_view
context_bytes_kind: declared_payload_bytes|semantic_payload_bytes
context_bytes: <non-negative integer>|unavailable
verification_records: <ordered records>|unavailable
verification_total_seconds: <non-negative decimal>|unavailable
report_bytes: <non-negative integer>|unavailable
status: <role return status>
concerns: none|<non-empty concise items>
fix_wave: <non-negative integer>
input_tokens: <non-negative integer>|unavailable
output_tokens: <non-negative integer>|unavailable
total_tokens: <non-negative integer>|unavailable
```

Controller owns every block and measures role timestamps/report bytes；`elapsed_seconds` uses controller monotonic delta while timestamps use wall clock。Role measures each verification command with monotonic time, persists `Verification Records`, and returns `verification_records` plus total inline. Controller copies values, never infers them. `direct_acs/declared_payload_bytes` is the raw UTF-8 sum of the six declared ACS sources；`semantic_view/semantic_payload_bytes` is context-view aggregate semantic bytes。

Final clean 时 controller 根据 final diff 一次性分类并原子写 `change_shape=<enum>`、`metrics_finalized=true`。Classifier 规则与 DESIGN v4 完全一致：test-path matcher、doc/config suffix sets、migration priority、source top-level module counting，以及 `migration|single_module_code|cross_module_code|docs_only|config_only|test_only|mixed` 枚举。任何分类/写入失败保留 unavailable/false，archive 正确性不受影响，但该 run 不能成为 Phase 3 样本。

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

## External Documentation Checked
N/A — no external dependencies

## Test Matrix
| Contract | Required deterministic coverage |
|---|---|
| SPEC-VERIFY-001 / SPEC-ROLE-002 | 双 execute surfaces 包含 targeted escalation matrix、final full suite、all-role metrics、Codex `fork_turns="none"`；旧 hardening tokens 仍存在。 |
| SPEC-METRICS-009 | execute-start 原子 seed progress+metrics；header/role schema；resume 不覆盖；monotonic/unavailable；fix/re-review/final-fix blocks；change classifier 与 failed-finalize non-gating。 |
| SPEC-CONTEXT-010 | temp workspace 中 directory/file symlink、non-regular、FIFO、pre-stat/open race、capability unavailable、fd cleanup、parent replacement pinned-tree behavior。 |
| SPEC-CONTEXT-011 | Unicode、comments、read-only blocks、fences、whitespace-only、fixed order/separators/one newline、per-source/aggregate bytes、human/JSON exact keys、missing/no partial、wrong status。 |
| SPEC-REPORT-012 | 两完整 execute surfaces 强制所有 section、inline verification、every-role `⚠️ DEFER` propagation；fast/strict final input matrix。 |
| SPEC-GRANULARITY-004 / SPEC-PARITY-008 | stage template + 五 continue surfaces + OpenCode derived install + Gemini description；PLAN fields/schema/trace tests unchanged。 |
| SPEC-PROFILE-013 | closed handshake 参数矩阵、zero-mutation snapshots、structure recheck、reject reason newline rejection、direct confirm、executing same/different/flags、legacy strict。 |
| SPEC-LEDGER-014 / SPEC-RESUME-006 | unique profile/events、malformed lines、marker continuity、BASE chain、checked/implemented conflict、first actionable task、strict escalation/recovery、legacy strict complete marker。 |
| SPEC-FAST-005 / SPEC-FINAL-007 | fast no per-task reviews、runtime triggers strict recovery、final primary task-by-task review、full suite、fix/re-review metrics、checkbox only after approval、archive gate fails before approval。 |
| SPEC-SAMPLE-003 | 三 archived paths、schema/profile/finalized/verdict/task count/role coverage、fix-wave evidence、shape/task diversity；每个失败分支保持 Phase 3 source/checkbox 不变。 |

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

## Upstream Summary (read-only)
# Design

## Design Summary
采用四个顺序化、可独立验证的 cohesive change slices。Phase 0 先修正验证节奏、子代理历史传递和度量结构；Phase 1 增加确定性上下文视图并缩短报告契约；Phase 2 收紧 PLAN 任务形成规则；Phase 3 的当前-run任务设置显式证据 gate，只有三次独立、完成 final review 且使用 Phase 0/1 instrumentation 的 strict execution run 满足代表性条件后才进入实现。证据不足时 Phase 3 任务保持当前 run 的未完成状态并返回 `BLOCKED`，不把它移出本需求。所有状态正确性继续由 `run.md`、`execution/progress.md`、PLAN 复选框和 final-review gate 决定，`execution/metrics.md` 只负责观测。

## Current Code Evidence
- `tools/workflow_cli/agent_templates/{codex,claude}/.../r2p-execute` 当前承载绝大多数执行编排：每任务 fresh implementer、task reviewer、fix loop、final reviewer、BASE/resume 和 archive 协议都属于提示契约，不是 Python orchestrator。
- 当前 Authoritative Context Set 要求每个 implementer/reviewer/fixer 直接完整读取 `02`–`06` 与 `execution/progress.md`；模板中的“可跳过嵌入 read-only block”不能阻止普通整文件读取先把这些字节放入角色上下文。
- `tools/workflow_cli/stage_templates.py` 已在 PLAN 的 `Verification` guidance 中表达 targeted tests 优先和 final review 全量回归，但 task-reviewer 模板没有同等强度的升级条件，历史执行因此仍可重复运行完整套件。
- `tools/workflow_cli/cli.py::_cmd_run_execute_start` 只从 PLAN anchors 生成 `execution/progress.md`；`gates.py::check_execution_complete` 只信复选框，`check_final_review_recorded` 只信 final-review 的最后一个合法 verdict。
- `tools/workflow_cli/agent_shortcuts.py::_cmd_execute` 负责 closed→executing 或 resume 的快捷入口；当前没有 profile 参数，resume 文案固定选择最低未勾选任务。
- `tools/workflow_cli/cli.py::_cmd_plan_task_brief` 已复用 `strip_nonsemantic_markdown`，并用内部 run loader、WorkId 校验和路径检查生成 scoped task brief，证明只读执行辅助命令可以保持 CLI/agent 分层。
- `tools/workflow_cli/atomic.py::read_regular_text` 已提供 final-component lstat、`O_NOFOLLOW`、fstat identity 的可信文本读取，但不固定父目录 identity；context view 需要补充基于稳定 directory fd 的逐组件读取。`markdown.py::strip_nonsemantic_markdown` 已提供 fence-aware、offset-preserving 的确定性过滤。
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
5. **四个增量切片 + 确定性只读 view + 两档 profile**：每一步都能独立衡量收益，strict 保持兼容，fast 只在证据充分且资格明确时减少逐任务 reviewer；选择。

## Chosen Design
### DES-EXEC-001 — Phase 0：验证节奏、零历史与 controller-owned metrics

`run-execute-start` 在创建 `execution/progress.md` 时同时创建结构化 `execution/metrics.md`。metrics 文件不被任何 gate 或 resume parser 读取；当前自举执行若因旧代码未自动生成该文件，controller 在首个角色 dispatch 前以相同 header 创建一次。

metrics header 固定记录 `work_id`、`r2p_version`、`instrumentation_schema`、`profile`、`task_count`、`change_shape: unavailable` 和 `metrics_finalized: false`。`instrumentation_schema` 是跨目标仓库/无 Git 安装均可验证的执行度量能力版本；Phase 0/1 落地时定义首个整数版本，字段或口径不兼容变更必须递增。一个角色调用对应一个有序 Markdown block，controller 是唯一写入者；block 字段为 sequence、role、task、model（或 unavailable）、started_at、ended_at、elapsed_seconds、context_mode、context_bytes_kind、context_bytes、verification_records、verification_total_seconds、report_bytes、status、concerns、fix_wave，以及 input/output/total Token（平台没有真实值时全部为 unavailable）。不得用归档快照、role elapsed 或其他派生值填充不可观测字段。

controller 用 wall-clock timestamps 记录 role started_at/ended_at，用自身单调时钟差记录 elapsed_seconds，并在角色返回后读取 report bytes；任一时钟不可用就写 unavailable。每个 implementer/reviewer/fixer/final reviewer 必须用单调时钟包围自己执行的每条 verification command，在持久 report/review 中写有序 `Verification Records`，每项包含 command、scope、reason、elapsed_seconds、status；同时在 inline return 中给出同结构的紧凑 `verification_records` 与 `verification_total_seconds`。controller 逐项复制到 metrics；缺失或无法解析时写 unavailable 并把该缺口加入 concerns，绝不从 role elapsed 推算 verification time。多条 targeted 命令和升级后的 full suite 各占一项。

final reviewer 依据 execution-base→HEAD final diff 对 `change_shape` 做一次性 finalize。测试路径定义为任一 component 是 `test`/`tests`，或 basename 匹配 `test_*`、`*_test.*`、`*.test.*`、`*.spec.*`；文档定义为位于 `docs/` 或扩展名属于 `.md/.rst/.adoc/.txt`；配置扩展名固定为 `.json/.yaml/.yml/.toml/.ini/.cfg/.properties`；其余为 source，root-level source 的 module 名为 `_root`，其他 source 的 module 是第一 path component。分类优先级为：任一路径含 `migration`/`migrations` → `migration`；忽略测试后 source module 数为一 → `single_module_code`，大于一 → `cross_module_code`；没有 source 且全部非测试路径为文档 → `docs_only`；没有 source 且全部非测试路径为配置 → `config_only`；只有测试 → `test_only`；其余 → `mixed`。final clean 后 controller 原子替换 header 为该枚举值和 `metrics_finalized: true`；此前不得用于样本判定。

Phase 0 的 `context_mode=direct_acs` 使用 `context_bytes_kind=declared_payload_bytes`：值严格等于模板要求角色完整读取的六个 ACS source 的 UTF-8 raw bytes 之和。它衡量声明交付量，不声称等于工具分块传输或模型实际 consumed bytes。Phase 1 的 `context_mode=semantic_view` 使用 `context_bytes_kind=semantic_payload_bytes`，值直接取该角色调用的 context-view aggregate `semantic_bytes`。controller 可用 stdout 重定向到 byte counter 验证数值，但不得把 ACS 正文读入自己的上下文。任何平台不能观察的 Token 或 timing 都写 unavailable。

角色调用串行，避免 metrics 写入竞争；report/review 仍由对应角色写入既有文件。任何角色发现的每条 `⚠️ DEFER` 都必须同时进入其持久 report/review 的固定 `⚠️ DEFER` section 和 inline `concerns`；没有时写 `none`，不得省略。strict final 读取 reports 与 reviews；fast final 从所有 reports 取得 implementer-side `⚠️ DEFER`。

implementer 与 task reviewer 的 verification matrix 一致：默认 targeted/directly affected；触及 shared/core/high-risk、targeted 失败、覆盖关系不清或 reviewer 无法建立充分信心时升级 full suite，并在 metrics 记录原因。final reviewer 无条件运行 full suite。Codex dispatch 固定 `fork_turns="none"`；Claude/其他平台使用其可表达的 fresh/minimal-history 语义，缺少 subagent 能力仍 fail explicitly。

### DES-CTX-002 — Phase 1：确定性 execution context view 与紧凑审计输出

新增 `tools/workflow_cli/execution_context.py`，只负责构建只读 view；在 `atomic.py` 增加稳定 directory-fd 与 relative no-follow text-read 原语；新增内部 `context-view` CLI handler；新增安装型 `tools/r2p-context-view` wrapper，公开接口为 `r2p-context-view --work-id <id>`，首版没有 `--role`。

命令只接受合法 work ID 和 `EXECUTING` run。它先以 directory fd 打开 repo root，再使用相对 fd 的 `os.open(..., O_DIRECTORY | O_NOFOLLOW | O_NONBLOCK)` 逐组件打开 `.req-to-plan`、work-id run dir 和 `execution`；所有固定 source 先相对 pinned fd 做 no-follow pre-stat，再以 `os.open(..., O_NOFOLLOW | O_NONBLOCK)` 打开并用 `fstat` 比对 dev/ino/regular-mode 后读取。`run.md` 也从同一 run-dir fd 读取并解析，在该 handle 下核对 embedded work ID 与 `EXECUTING` status；不先信任一次 path-based load 再读取另一个可能已被替换的目录。平台缺少所需 dir-fd/flag 能力时 fail closed。目录在打开后被 rename 不会改变 fd 所指 inode；父路径被替换时继续从已 pinned 的原目录树安全读取，不承诺检测 path-name identity drift，也绝不切换到替换后的目录。

content 固定按以下顺序读取：`02-project-context.md`、`03-requirement-brief.md`、`04-risk-discovery.md`、`05-design.md`、`06-spec.md`、`execution/progress.md`。missing 返回 not-found；symlink、non-directory、non-regular、检测到的 final-component identity race 或 capability unavailable 返回 conflict。父 path replacement 若发生在 fd pinning 后，不是错误：结果来自完整、稳定的 pinned tree。所有 source 全部读取并校验成功后才构建/打印结果，错误路径不输出 partial content。

每个 source 的 semantic text 精确定义为 `strip_nonsemantic_markdown(raw).rstrip()`，per-source `semantic_bytes` 是该结果的 UTF-8 长度。最终 `content` 为每个 source 的固定可见分隔行 `===== <relative-path> =====`、semantic text、源间空行和全局唯一尾随换行。aggregate `raw_bytes` 是各 raw UTF-8 bytes 之和；aggregate `semantic_bytes` 是最终 `content.encode("utf-8")` 的长度，显式包含分隔符/源间空行/唯一尾随换行，因此不要求等于 per-source semantic bytes 之和。

human success 直接向 stdout 输出 `content`，不附加 `✓`、message 或统计前缀。JSON success 的稳定顶层 keys/类型为：`status: "ok"`、`message: str`、`work_id: str`、`sources: list[{path: str, raw_bytes: int, semantic_bytes: int}]`、`raw_bytes: int`、`semantic_bytes: int`、`content: str`。失败继续使用 `status: "error"`、`message: str`、`exit_code: int` 和可选 `details: list[str]`，且不含 partial `content`/`sources`。子代理在自己的上下文中调用该命令，controller 不得读取/转发正文。不创建任何持久化 context artifact。

task report/review 改为紧凑固定 section：Status、Commit Range、Changed Files、Verification Records、Concerns、`⚠️ DEFER`；review 额外保留 Spec Verdict 与 Quality Verdict。字段内容可以简短，但每条 concern/`⚠️ DEFER` 必须逐项保留并进入 inline concerns。strict final 读取所有 reports/reviews；fast final 读取所有 reports 的同名 section，不要求不存在的 reviews。

golden/security tests 覆盖 Unicode、whitespace-only source、HTML comment、fenced content、固定顺序/分隔/bytes、human/JSON shape、missing/no-partial-output、final source symlink/race、raced-in FIFO 不阻塞、execution dir symlink，以及 fd pinning 后 workspace/run parent replacement 仍读取原树且绝不读取替换树。

### DES-PLAN-003 — Phase 2：cohesive change slice 任务形成规则

PLAN author 先按可观察行为或契约结果分组，再把实现、直接测试、同步 agent surfaces 和必要文档放入同一 slice。一个 slice 必须同时满足：可用自己的 Verification 独立判定；reviewer 不依赖未完成 sibling 才能判断；其 commits 可独立回滚且不会留下破损 schema/接口。

禁止仅因文件不同拆任务；同一行为链的 Python handler、wrapper、安装测试和 surface 更新可以属于一个 slice。也禁止把没有共同验收结果的多个行为塞入大任务。规则同步矩阵精确包含 `stage_templates.py`、Claude 通用 `agent_templates/claude/SKILL.md`、Claude `commands/r2p-continue.md`、Codex `skills/r2p-continue/SKILL.md`、Gemini `commands/r2p-continue.toml` 的 description/prompt 可表达部分，以及 `tests/test_docs_consistency.py`。OpenCode 不维护独立正文，由安装测试断言其 Claude-derived continue command 含同一 cohesive-slice 规则。`PLAN_TASK_FIELDS`、trace closure、gate 和 checkbox 解析不变。

### DES-PROFILE-004 — Phase 3：strict/fast 选择、ledger 与恢复

`r2p-execute` wrapper 增加可选 `--profile strict|fast`，并为 closed fast start 使用两步 handshake。closed run 省略参数固定选择 strict；显式 strict 等价且立即走现有 start。首次 `r2p-execute --profile fast` 只执行 deterministic tier/modifier 结构门；失败时 exit 6，成功时返回 `stop: fast_profile_review`、work ID、PLAN path、tier/modifiers，且不创建 progress/metrics、不改变 run status。Claude/Codex/OpenCode/Gemini agent surface 随后读取完整 `07-plan.md` 做语义门：全部任务必须局部且机械、无 shared/core/security/migration/dependency/config 风险、Files 边界清楚、Verification 为可直接执行的确定性命令。

语义门通过时，agent 调用 `r2p-execute --profile fast --confirm-fast-eligible`；shortcut 重跑结构门后才调用 `run-execute-start --profile fast`。语义门失败/未知时，agent 调用 `r2p-execute --profile fast --reject-fast-ineligible --reason <single-line>`；该路径验证 run 仍 closed 后以 exit 6 输出 `fast_profile_ineligible`，不 mutation、不自动执行 strict。两个 handshake flag 互斥、只允许和 `--profile fast` 一起使用，closed strict 或 executing run 使用它们均为 CLI error/conflict。直接从终端传 `--confirm-fast-eligible` 被定义为显式、可信的人工 eligibility attestation boundary；CLI 仍验证结构条件，但不声称能确定性判断 PLAN 语义。首次 fast、reject 和 confirm 失败测试都断言 run/status/files 零 mutation。

`run-execute-start --profile <profile>` 在 progress 写一个不可变初始行 `Execution Profile: strict|fast`。executing resume 的 effective profile 由初始行和有序 escalation events 确定：无 `--profile` 复用 effective profile；传入相同 profile 幂等接受；传入不同 profile 返回 conflict。legacy executing ledger 缺少初始行时确定性解释为 strict。fast 运行中触发安全升级时允许 controller 自动追加单行 `Profile Escalation: fast -> strict (reason: <single-line>)`；不改初始行，升级后不可降回 fast，resume 使用最后一个合法 event 的 target。profile 解析放在一个纯 parser/helper 中并由 shortcut 与测试共用。

strict 沿用 N 个 fresh implementer + N 个 task reviewer + 1 个 final reviewer。fast 使用 N 个 fresh implementer + 1 个 final reviewer；implementer 完成并提交后，controller 保持该任务 `- [ ]`，追加精确 marker：`Task N: implemented (commits <base7>..<head7>, verification recorded)`。只有 final primary review 逐任务批准后，controller 才把所有任务置 `[x]` 并把 marker 收敛为 reviewed-complete 记录。

fast resume 选择编号最小、既无 checked-complete 也无合法 implemented marker 的任务。Task 1 BASE 只来自 `Execution BASE`；Task N BASE 只来自前一任务合法 complete/implemented marker 的 head。已存在 marker 的任务不重复实现。marker 缺失而提交存在、marker 格式/顺序/commit 无法解析、HEAD 不在 marker chain、验证失败、unexpected file、concern、上游歧义或 shared/core 风险都会追加 one-way escalation event，并按顺序为所有 implemented-but-unreviewed 任务生成 diff、执行 task review，干净后才置 `[x]`，然后继续 strict loop。

fast final reviewer 是 primary review：读取 semantic context view、PLAN、progress、全部 task reports、全部 Minor/concern 和 execution-base→HEAD final diff；不要求 task review 文件。它逐 PLAN task 检查 spec、changed files、verification 和 diff，无条件运行 full suite。发现问题沿用单一 final-fixer + refreshed diff + re-review loop；全部批准后才更新 checkboxes、写 `execution/final-review.md` 的最后 verdict 并允许 archive。

Phase 3 当前-run任务开始时执行人工证据 checkpoint。合格证据允许来自任意目标 Git 仓库，但必须是三个不同 work ID、`run.md` 状态为 archived 的独立 strict execution runs；每个 run 的 metrics 都记录 `r2p_version`，`instrumentation_schema` 必须等于 Phase 0/1 定义的受支持版本，`metrics_finalized` 必须为 true，且 `change_shape` 不得为 unavailable。每个 run 必须实现全部 PLAN tasks，完成 primary final review/full suite，最后 verdict 为 Approved，并包含其全部 implementer、全部 task reviewer 和 final reviewer 的完整 role blocks；不得用跨仓库 SHA ancestry 或同一 run 的多个 role block证明多个样本。

三个样本合计还必须覆盖至少两个不同 `task_count` 值或至少两个 finalized `change_shape` 枚举。Phase 3 implementer 把三个 sample 的 work ID、archive/run path、r2p version、instrumentation schema、task count、finalized change shape、role coverage、final verdict 和 metrics completeness 写入 task report，reviewer逐项核验。证据不足时返回 `BLOCKED: representative_metrics_missing`，Phase 3 checkbox 保持未完成；证据仍属于当前需求的入口条件，不能用估算、单一历史 snapshot 或未完成 run 替代。

### DES-COMPAT-005 — 安装、平台与测试兼容

Phase 0/1/3 的完整 execute protocol surfaces 是 Claude `commands/r2p-execute.md` 与 Codex `skills/r2p-execute/SKILL.md`，必须在同一 patch 修改，并由 `tests/test_docs_consistency.py` 对 profile preflight、context-view、targeted escalation、metrics producer/units、implemented marker、fast recovery、primary final review 和 `⚠️ DEFER` token 做锁步约束。OpenCode 不手改，安装测试断言其 Claude-derived execute command 保留完整协议；Gemini 保留 wrapper forwarding，并在 description/prompt 可表达范围内写明 strict 默认、fast opt-in/read-only preflight 和 fail-closed 入口。

Phase 2 continue surfaces 使用上一节的五面同步矩阵，并单独验证 OpenCode 派生输出。Claude 通用 skill 与 command、Codex skill、Gemini description 不得只更新其中一部分。

新增 wrapper 会被 `install.py` 的 `tools/r2p-*` glob 自动纳入安装、卸载和 manifest；补充 install/wrapper bootstrap 测试。CLI 与 directory-fd 安全读取测试使用临时 workspace；profile/gate tests 证明 strict 旧 ledger 兼容、profile 参数 resume 冲突确定、escalation 单向、fast `[ ]` 不会越过 archive completion gate、final 批准后才能通过。

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
- `execution/metrics.md` 区分 controller-measured role elapsed/report bytes、role-measured ordered verification records，以及 `declared_payload_bytes`/`semantic_payload_bytes` 两种 context 口径；无法取得的平台 Token/timing 显式标记 unavailable。
- context view JSON 的 aggregate/per-source bytes 支持验证过滤比例和实际 semantic payload，且不把重建 snapshot 当历史真实流。
- progress 中的 immutable `Execution Profile`、ordered `Profile Escalation`、implemented/complete marker 和既有 `Resolved/Gap/Unresolved/Minor` 共同提供恢复审计。
- Phase 3 report 固化三份独立 instrumented strict run 的 work ID/path、r2p version、instrumentation schema、finalized shape/task count、角色覆盖、final verdict 与 metrics 完整性。
- final review 继续记录 execution BASE→HEAD 范围、fresh full-suite 结果和最后 verdict；archive gate 行为不变。
- 测试输出分别覆盖 targeted 模块与最终完整 suite，不在文档冻结通过数量。

## SPEC Handoff
SPEC 必须把以下内容写成无歧义契约：

1. metrics header、instrumentation schema、controller/role 数据生产者、monotonic elapsed、ordered verification records、两种 context byte kind、不可用值、final change-shape classifier，以及三个独立 finalized archived strict runs 的充分性判定与人工证据 checkpoint。
2. task-level full-suite escalation matrix 与 final full-suite 不可省略规则。
3. context-view 的参数、`O_NONBLOCK` 稳定 directory-fd traversal、relative pre-stat/open/fstat、同-handle run validation、pinned-parent replacement 安全语义、source 顺序、分隔/byte 公式、完整 human/JSON schema、错误码和 no-partial-output 行为。
4. compact report/review 的最小字段、Verification Records，以及任何角色的 concern/`⚠️ DEFER` 同时持久化与 inline 上报规则。
5. cohesive change slice 的三项判据、跨文件正例、过细/过大反例、schema 不变约束和五个 continue surfaces + OpenCode 派生矩阵。
6. `--profile` 两步 fast handshake、首次 review stop、confirm/reject flags、direct confirm 的可信人工边界、strict 默认、拒绝不自动降级、closed/executing 参数矩阵和 legacy strict 解释。
7. immutable initial profile、ordered escalation event、implemented marker grammar、BASE chain、effective-profile/resume selector、fast→strict recovery 和 checkbox 迁移时点。
8. strict/fast final reviewer 输入矩阵、primary review、fix loop、full suite、final verdict 与 archive gate。
9. Claude/Codex 完整 execute surfaces、OpenCode 派生、Gemini 精简入口、wrapper install、目录 race 和全部临时 workspace 回归测试矩阵。

## Trace
<!-- Map this stage's IDs to upstream/downstream. R3 derives & checks closure. -->
| This ID | Upstream | Status |
|---|---|---|
| Design headings above | Approved requirement brief and risk discovery | [ADDRESSED] The design assigns every in-scope behavior and risk to one of four sequential slices plus cross-platform compatibility. |
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
