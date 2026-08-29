# PLAN 强制独立评审 v2

Verdict: Changes Requested

## Review Scope

已完整审阅 `03-requirement-brief.md` v1、`04-risk-discovery.md` v3、`05-design.md` v5、`06-spec.md` v4 与 `07-plan.md` v2，并只读核对当前 PLAN file gate、wrapper bootstrap、`run-execute-start`、CLI registration 与现有测试路径。

PLAN 的 ID 覆盖是完整的：14 个 `SPEC-*`、SCOPE-IN-001..010、12 个 mitigated `RISK-*` 均被 task trace/risk table消费；TDD、targeted/full-suite 命令、Git BASE、无远程 mutation 和 Phase 3 zero-source-write 意图也已保留。但以下问题使若干任务无法按自身 Files/Verification 独立执行，且留下会改变实现/执行顺序的未决选择。

## Critical

无。

## Important

### I-1 — create/modify 拆分与批准的 cohesive-slice 契约冲突，当前上游没有决定“task group”是否可替代 task slice

**证据**

- `SPEC-GRANULARITY-004` 要求每个 task 自己可独立验证、评审、回滚，并规定同一行为所需实现、直接测试、wrapper、安装面、agent surfaces 和文档属于一个 slice；`SPEC PLAN Handoff` 第 275–280 行进一步要求四个顺序 cohesive slices，且每个 task 的 `Files` 同时覆盖实现、测试和同步 surface。
- PLAN 将 Phase 0、1、3 分别拆成 `001→002`、`003→004`、`006→007`。三个 modify task 都直接依赖前一个 create task；在后续集成保留时单独回滚 `001`、`003` 或 `006` 会留下 broken imports/entrypoint，和第 228 行“each task independently ... revertible”冲突。
- 这不是普通 PLAN 排版选择：当前 `gates.py::_check_plan_file_refs` 第 729–765 行强制 create task 的所有 paths 不存在、modify task 的所有 paths 已存在，因此一个 task 无法同时列出新 module/wrapper 与现有 CLI/template 文件。
- PLAN 没有上游决定说明一个“Phase task group”可作为 cohesive slice，也没有把 group-level verification/review/rollback 写入 SPEC；同时 SCOPE-IN-006 明确不修改 PLAN schema/gates。

**影响**

执行者只能自行选择：违反 R19 mixed-path gate、违反已批准的 per-task cohesion，或把“独立回滚”降为仅允许按依赖逆序回滚。这是未经上游决定的实现/交付语义。

**具体修订建议**

先路由到拥有该冲突的 DESIGN/SPEC：明确选择并编码以下之一，再重写 PLAN：

1. 允许一个 cohesive Phase slice 由固定的 create→integrate task group 实现，并把独立验证/评审/回滚定义为 group-level，同时承认子 task 的有序依赖；或
2. 扩展 PLAN operation schema/gate以表达 mixed create+modify（这会改变当前 SCOPE-IN-006）；或
3. 重新设计文件落点，使每个 PLAN task 真正拥有一个完整、可运行、可回滚的可观察结果。

不能仅在 PLAN 中继续声称七个 task 都独立，从而掩盖结构冲突。

### I-2 — PLAN-TASK-003 的 wrapper 在自己的 Files 边界内没有可执行 bootstrap target

**证据**

- PLAN 第 72–105 行要求 Task 003 创建 `execution_context.py`、`tools/r2p-context-view` 和测试，并在该 task 的 Verification 中通过 wrapper smoke test；Task 004 到第 129 行才修改 `cli.py` 注册 internal `context-view`。
- 仓库 load-bearing wrapper invariant 是 `python -E .../tools/workflow_cli/__main__.py <target>`。当前 `__main__.py` 第 8–15、59–75 行只允许 `tools.workflow_cli`、`tools.workflow_cli.agent_shortcuts`、`tools.workflow_cli.install_cli` 三个 targets；Task 003 的 Files 不包含 `__main__.py` 或 `cli.py`。
- DESIGN v5 第 77 行还明确要求在 `atomic.py` 增加 stable directory-fd/relative no-follow primitives；Task 003 第 103 行把 primitives 放入新 `execution_context.py`，Task 003/004 的 Files 都遗漏 `atomic.py`，属于未说明的架构落点漂移。

**影响**

Task 003 无法同时满足“薄 `-E` wrapper”“现有 bootstrap isolation”“独立 wrapper smoke test”和自己的 create-only Files。若绕过 `__main__.py` 直接执行新模块，会违反仓库 wrapper bootstrap invariant；若等待 Task 004，则 Task 003 不独立可验证。

**具体修订建议**

在解决 I-1 的 task-group/schema 决定后，把 directory-fd primitives、bootstrap target/internal handler、wrapper、tests、install/docs 边界放入同一个被批准的 cohesive slice；若决定偏离 `atomic.py`，必须先回到 DESIGN 记录该模块所有权变化。

### I-3 — 当前 run 的 legacy metrics bootstrap 在 PLAN 中发生得太晚

**证据**

- `SPEC-METRICS-009` 第 102 行要求本需求由旧版本启动时，controller 在首个 role dispatch 前校验 legacy strict ledger并创建 metrics header，否则 `BLOCKED`。
- 当前源码 `_cmd_run_execute_start` 第 906–955 行只创建 `execution/progress.md` 后转为 EXECUTING，不创建 metrics；当前 execute surface 也没有该 producer。
- PLAN-TASK-001 第 39 行只要求为 bootstrap guard 写测试；实际 CLI integration 到 PLAN-TASK-002 第 65–69 行才落地。`Execution Readiness` 没有首个 implementer dispatch 之前可运行的确定命令或 controller procedure。

**影响**

按当前 PLAN 启动执行时，Task 001 implementer 本身会在 bootstrap capability 落地之前被 dispatch，直接违反获批 SPEC 的“before first role”时点。执行者只能手写 metrics、推迟采集或忽略本次 run，三者均未获授权。

**具体修订建议**

在 PLAN 的 pre-task execution prerequisite 中给出可由当前代码执行的唯一 bootstrap procedure/command，包括 pinned execution validation、work/task/BASE/profile checks、atomic header write、失败 `BLOCKED` 和 Task 1 invocation 如何记录；若产品决定允许本次 run 从 Task 002 后才开始 instrumentation，必须回到 SPEC 修改 bootstrap contract，不能由 PLAN 暗中选择。

### I-4 — Phase 3 硬门的 pass path 依赖尚不存在的 validator，“approved no-follow/manual procedure”不是可执行命令

**证据**

- PLAN-TASK-006 第 187 行要求在两个 Phase 3 文件创建前，以“approved no-follow/manual procedure”验证三个 user-specified archived directories。
- 同一 task 的 `validate_representative_samples(...)` 要到证据通过后才在 `execution_profile.py` 中创建；当前仓库没有 metrics sample validator/CLI，也没有绑定 sample paths 的参数、环境变量或 artifact field。
- SPEC-SAMPLE-003 要求 filesystem-root no-follow directory-fd traversal、pinned sample fd、exact metrics parser、role/fix-wave completeness、totals 和逐 sample failure rule。普通人工查看文件不能证明这些条件。
- PLAN 的 blocked branch正确要求不创建 Phase 3 source、不勾选 Task 006；Task 007 第 217 行也正确要求 evidence 缺失时零 source modification。但“如何得到 accepted evidence report”没有唯一 pass path。

**影响**

没有样本时能确定地 BLOCKED，但即使用户提供合格路径，执行者也必须自行发明临时代码/命令才能通过硬门；不同执行者会得到不同安全与 completeness 结论。

**具体修订建议**

在 Phase 3 source gate 之前提供并命名一个已经落地的只读 validator 与 exact invocation/input contract，例如由更早 Phase 安装的命令接受重复 `--sample-dir <absolute-path>`；无参数、少于三份或任一失败时写明逐 sample path/work ID/rule 并 `BLOCKED`。如果不新增命令，则 PLAN 必须给出等价、逐字可执行且零持久 source write 的 preflight procedure，不能保留“manual procedure”。

### I-5 — Phase 0 transaction API 的两个 Skeleton 签名互相矛盾

**证据**

- PLAN-TASK-001 第 27 行定义 `start_execution_transaction(run_dir, record, plan_anchors, profile)`。
- PLAN-TASK-002 第 61 行却调用 `start_execution_transaction(args.base_path, args.work_id, profile)`，少一个参数且把 `run_dir/record/anchors` 换成 `base_path/work_id`。

**影响**

实现者必须自行决定由 core 还是 CLI 负责 load/validation/anchor extraction/state save；这会改变 transaction trust boundary、fault-injection surface 和 recovery ownership。

**具体修订建议**

固定唯一 public signature 与 ownership：明确哪一层加载 `RunRecord`、读取/解析 PLAN anchors、持有 pinned run fd、保存状态并格式化 exit/JSON；同步两个 Skeleton、Steps 和 tests。

## Minor

无单独 Minor；以上均会改变任务边界、入口或恢复行为。

## Confirmed Complete Areas

- 14 个 SPEC IDs、SCOPE-IN-001..010 和 12 个 mitigated risks 均有 PLAN trace/handling task，无未消费上游项。
- 所有列出的 create paths 当前不存在，modify paths当前存在；测试命令使用项目规定的 `.venv/bin/python -m pytest`，TDD-first 与 shared/core full-suite trigger明确。
- Task 005 单独完整覆盖 Phase 2 五个 continue surfaces、OpenCode derived/install tests 和 schema/gate 不变约束。
- Phase 3 blocked branch明确保持 Task 006/007 source 未修改和 checkbox未完成；问题只在合格样本的可执行 pass path。
- dirty-tree、full Execution BASE、每 task commit/diff、final full suite、final verdict/archive gate、无 push/PR 与串行当前分支边界均保留。
- 未发现未锚定 scope deferral；Phase 3 evidence不足时 BLOCKED 是上游已批准的当前需求 prerequisite。

## Ambiguity Conclusion

仍存在 unresolved ambiguity / undecided point：I-1 的 task-vs-group cohesion/schema冲突、I-3 的 self-bootstrap时点、I-4 的 pre-gate validator/input，以及 I-5 的 transaction ownership。I-2 是由 I-1 具体触发的不可执行路径。

## Approval Condition

先解决 I-1 所暴露的上游 schema/granularity冲突，再修订 PLAN 以闭合 I-2..I-5；完成后重新强制评审。
