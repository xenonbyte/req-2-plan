# DESIGN 强制独立评审 v6

Verdict: Changes Requested

## Review Scope

已完整审阅 `03-requirement-brief.md` v1、`04-risk-discovery.md` v3、`05-design.md` v6，以及触发 R-2 的 `reviews/plan-subagent-review-v2.md`；并只读核对当前 `PLAN_TASK_FIELDS`、PLAN field-body 解析、`plan-task-brief` 传递行为、R19 file gate 与 wrapper bootstrap 入口。

DESIGN v6 已正确把四个 Phase 定义为 phase-level cohesive slices，并用固定 `2 / 4 / 1 / 2` operation-homogeneous task 布局解决现有 R19 create/modify 冲突。它也已修复 context wrapper 的不可执行顺序、Phase 3 的 pre-mutation validator 缺口，以及 `start_execution_transaction` 的签名和 ownership 分裂。仍有两个契约级未决点，因此不能进入 SPEC/PLAN 重写。

## Critical

无。

## Important

### N-I1 — self-hosted metrics bootstrap 在原子写成功后的崩溃重试没有可恢复分支

**证据**

- DESIGN 第 66 行规定 `execution-metrics-bootstrap` 只接受“尚无 metrics”的 legacy run，并规定“已存在 metrics”一律 conflict 且不覆盖。
- 同一行要求命令使用原子 header writer，但没有 transaction marker，也没有定义“原子 rename/replace 已成功、进程在向 controller 返回 success 前崩溃”的重试矩阵。
- 在该故障点上，磁盘已经存在由本命令写出的合法 self-host header；controller 无法证明上一次调用已完成，只能重试，而重试按当前契约必然 conflict。DESIGN 也没有授权 controller 在不调用命令的情况下把任意现存 metrics 判为已完成 bootstrap。
- `bootstrap_gap` 被称为“精确”，但 DESIGN 只给出 `--self-hosted-gap-through-task <number>`，未固定 header 中 `bootstrap_gap` 的 canonical value/grammar，也未说明它是否精确覆盖该 task 之前的 implementer、reviewer 和 fix-wave 调用。这使“现存 header 是否与本次 bootstrap 完全相同”无法稳定判断。

**影响**

当前 self-hosted run 在最关键的 capability 切换点不能实现 crash-idempotent resume；执行者必须自行选择把 exact existing header 当成功、清理后重建，或保持永久 conflict。前两种会改变 no-clobber/foreign-residue 安全边界，后一种违反本次要求的可恢复执行。

**具体修订要求**

在 DESIGN 中固定唯一 bootstrap recovery contract，并交给 SPEC 精化语法：

1. 定义 canonical `bootstrap_gap` 值，至少唯一表达“从执行开始至 Phase 0 最后一个 task 的全部角色调用均未 instrument，下一次 role sequence 才开始记录”；不得只留下自由文本。
2. 定义 crash retry 矩阵。最小可行选择是：metrics 不存在时原子创建；存在且 header 与预期 work/profile/task-count/canonical gap 完全一致、结构合法时视为幂等 success/resume；存在但任一字段不一致、unsafe、非本命令 self-host header 或结构损坏时 conflict 且不覆盖。若选择 marker transaction，则同样必须给出 marker × metrics × progress/run 状态的 complete/fail-closed 表。
3. 明确合法 exact header 已含后续 role blocks 时，resume 继续 append 而不是要求重新 bootstrap；任何不完整/乱序 block 仍 fail closed。

### N-I2 — `Dependencies` 的编码方式与“不新增 PLAN 字段”声明互相矛盾

**证据**

- DESIGN 第 100 行要求 task group 用 ``Dependencies``、Steps 和 Verification 明示顺序；第 128 行又明确“不新增 PLAN 字段或 change type”，SPEC Handoff 第 163 行同样把 dependency 与 schema 不变并列。
- 当前 `PLAN_TASK_FIELDS` 只有 `Spec References`、`Change Type`、`TDD Applicable`、`Files`、`Skeleton`、`Steps`、`Verification`，没有 `Dependencies`。当前解析器只把这些名称识别为 field boundary；若 PLAN 写入独立 `Dependencies:` 行，它会被吞入前一个已知 field 的 body，而不是一个有确定语义的字段。
- `plan-task-brief` 会传递整个 task body，所以依赖关系可以编码在既有 `Steps` 中；但 DESIGN 尚未选择这个兼容表示，仍让 PLAN author 决定是新增未识别字段、自由正文还是 Steps 内容。

**影响**

这会再次把 I-1 的关键问题下放给 PLAN：不同生成者可能写出不同 dependency 表示，gate、reviewer 和执行角色无法依据一个确定规则核对 `2 / 4 / 1 / 2` 前驱关系；独立回滚所依赖的 declared dependents 也没有稳定来源。把 `Dependencies:` 当新字段还会直接偷换 SCOPE-IN-006 的 schema 不变约束。

**具体修订要求**

固定一个不扩展 schema 的表示并同步全文措辞。最小兼容方案是：每个有前驱的 task 在既有 `Steps` field 的第一条使用精确语法（例如 `Prerequisite: PLAN-TASK-NNN reviewed complete`），无前驱 task 使用固定的 `Prerequisite: none`；Verification 必须先验证该前驱状态，rollback 依赖也从同一已声明关系读取。删除任何会被理解为新顶层 `Dependencies:` field 的要求。若确需新增真正字段，则必须显式修改 SCOPE-IN-006，而不能在本 DESIGN 中暗含。

## Minor

无单独 Minor。

## Five-blocker Closure Check

| PLAN v2 blocker | v6 result | Evidence |
|---|---|---|
| I-1 phase/task cohesion 与 R19 | **部分闭合** | phase-level slice、operation-homogeneous group、intermediate contract、Phase acceptance 与反向拓扑 rollback 已决定；但依赖编码仍有 N-I2。该 group 模型本身未改变 trace/gate/checkbox，也未把 SCOPE-IN-006 的行为移出当前需求。 |
| I-2 context wrapper bootstrap target | **闭合** | Phase 1 固定为 core create → internal CLI modify → wrapper create/smoke → surfaces adoption；wrapper 创建时 CLI target 已存在。directory-fd helper ownership 也明确留在 `execution_context.py`。 |
| I-3 self-host metrics bootstrap | **部分闭合** | 当前 run 的诚实 gap、`instrumentation_complete: false`、不得作为样本，以及未来 run 从首 role 完整采集均一致；但 bootstrap crash retry/canonical gap 仍有 N-I1。 |
| I-4 Phase 3 validator pass path | **闭合** | `execution-samples-validate` 在 Phase 0 integrate 落地；Phase 3 在任何 implementer dispatch/source mutation 前，以恰好三次 absolute `--sample-dir` 的唯一 machine preflight 执行。失败保持两个 checkbox 未完成且 source worktree 等于 Phase 3 BASE。 |
| I-5 transaction signature/ownership | **闭合** | 唯一 public signature 为 `start_execution_transaction(base_path: Path, work_id: WorkId, profile: str) -> RunRecord`；record/PLAN/pinned run/marker/progress/metrics/state save 均由 core entry 拥有，CLI 只解析和格式化。 |

## Architecture, Safety, and Command Check

- `2 / 4 / 1 / 2` 布局与当前 R19 create/modify file gate兼容；Phase 1 wrapper 独立 smoke 不再依赖未来 task。
- Phase 0 validator 是 Phase 3 source mutation 前唯一已落地的安全 pass path；不允许人工目测或 Phase 3 临时代码替代，符合 RISK-SEQUENCE-012。
- Phase 3 invocation 选定的 `/opt/homebrew/opt/python@3.14/bin/python3.14` 在当前环境存在，`yaml` 可导入，且 `-E tools/workflow_cli/__main__.py tools.workflow_cli` bootstrap shape 可执行；DESIGN 正确要求 PLAN 将 repo/sample placeholders 解析成绝对值。
- 未发现新的未锚定 deferral、远程 mutation 授权、第三 profile、共享 implementer、并行写分支或 final-review/full-suite 弱化。

## Ambiguity Conclusion

仍存在 unresolved ambiguity / undecided point：N-I1 的 bootstrap crash-idempotency 与 canonical gap，以及 N-I2 的 schema-compatible dependency encoding。其余三个原始阻断已闭合，phase-level group 决策也没有把 SCOPE-IN-006 偷换为 schema/gate 修改。

## Approval Condition

仅需在 DESIGN 中补齐 N-I1、N-I2 的确定性契约，再做聚焦复审；无需重开其他已闭合的 Phase、profile、context I/O 或 transaction 设计。
