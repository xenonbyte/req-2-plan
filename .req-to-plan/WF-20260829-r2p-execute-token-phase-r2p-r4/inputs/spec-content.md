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

Phase 0 必须落地只读 internal command `execution-samples-validate`，公开给 controller 的参数恰为重复三次的 `--sample-dir <absolute-archived-run-dir>`；没有默认扫描、glob、相对路径、第四份样本或隐式选择。原始执行的 Phase 3 controller 只接受用户明确提供的三个 absolute paths，并在派发 `PLAN-TASK-008` 及任何 Phase 3 source mutation 前执行该命令。若执行中因原 Task 009 的 PLAN 权限缺口从 SPEC/PLAN 重开，新的 delta run 必须在其唯一 source task dispatch/mutation 前，使用同一组三个用户已确认的 absolute paths重新运行该 validator；不得把旧 evidence 文件当作新运行的验证结果，也不得重新发现或替换样本。参数个数不是三、canonical path 重复或证据不足时输出 `BLOCKED: representative_metrics_missing` 并 exit 3；未知 flag/语法错误 exit 2。命令本身只写 stdout/stderr，不修改样本、当前 run 或源码；controller 仅可把 JSON stdout 重定向到当前 run 已忽略的 `execution/phase-3-sample-evidence.json`。

每个候选先 lstat 拒绝 symlink/non-directory，再取得 strict canonical path，并从 filesystem root 对 canonical components 做 no-follow stable directory-fd traversal；三个 canonical paths 必须两两不同，目录 basename 必须等于经 `WorkId.parse` 验证的 embedded work ID。`run.md`、PLAN、progress、metrics 和 final-review 均相对 pinned sample fd 使用 no-follow pre-stat/open/fstat regular-file read；任何 symlink、non-regular、race 或读取失败只令该 sample 不合格，不修改样本或当前 run。

合格集合必须同时满足：

- 至少三个不同的 `(canonical run path, work_id)`；每个 `run.md` status 为 `archived`。
- metrics header 的 `profile` 为 `strict`、`instrumentation_schema` 等于当前受支持值、`instrumentation_complete=true`、`bootstrap_gap=none`、`metrics_finalized=true`、`change_shape` 是合法非 unavailable 枚举，并记录非空 `r2p_version`；当前 self-hosted run 固定不合格。
- PLAN task count 与 metrics `task_count` 一致；progress 中全部 PLAN tasks 为 `[x]`；final-review 的最后 verdict 为 Approved。
- 每个 run 对每个 task 至少有 implementer 与 task-reviewer block，并有 final-reviewer block；实际发生的 fixer、task re-reviewer、final fixer、final re-reviewer 也必须各有 sequence-contiguous block。发现 report/review/fix-wave 证据而缺 block 时样本失败；不推算不可见调用。
- 每个 invocation 必须有 measured `started_at`、`ended_at`、`elapsed_seconds`、`context_bytes`、`report_bytes`、非空 `verification_records_json` 和 measured `verification_total_seconds`；任一字段为 `unavailable`、invalid 或 totals 不一致时整个 sample 不合格。`context_mode` 与 `context_bytes_kind` 必须是 SPEC-METRICS-009 的合法配对，每条 verification record 必须含 measured duration 与合法 status。
- `model` 和 Token 三字段可为 `unavailable`；Token 不可得不影响资格，但 evidence report 必须明确写 `token comparison: unavailable`，不得用 bytes 推算 Token。
- 三个样本至少具有两个不同 `task_count`，或两个不同 finalized `change_shape`。

Validator 用 SPEC-METRICS-009 相同的 canonical JSON writer（UTF-8、`ensure_ascii=False`、`allow_nan=False`、`sort_keys=True`、compact separators、唯一尾随 newline）。Success 顶层 exact keys/types 为：

```text
status: "ok"
message: "representative_metrics_accepted"
samples: list[Sample]  # input order, length 3
aggregate: Aggregate
```

每个 `Sample` exact keys/types 为：`path:str`、`work_id:str`、`r2p_version:str`、`instrumentation_schema:int`、`profile:"strict"`、`task_count:int`、`change_shape:<classifier enum>`、`instrumentation_complete:true`、`bootstrap_gap:"none"`、`metrics_finalized:true`、`plan_complete:true`、`final_verdict:"Approved"`、`invocation_count:int`、`role_counts:RoleCounts`、`role_elapsed_total_seconds:<six-decimal string>`、`verification_total_seconds:<six-decimal string>`、`report_bytes_total:int`、`full_suite:FullSuite`、`context_totals:ContextTotals`、`token_totals:TokenTotals`、`rules:list[RuleResult]`。

`RoleCounts` exact keys are all seven role enums from SPEC-METRICS-009, each non-negative int；implementer/task_reviewer counts must equal task_count, final_reviewer至少 1，fix/re-review counts may be zero。`FullSuite` exact keys are `count:int` and `duration_seconds:<six-decimal string>`，由 verification records 中 `scope=full_suite` 求和。`ContextTotals` exact keys are `direct_acs` and `semantic_view`；each value exact keys are `invocation_count:int`、the mode's fixed `context_bytes_kind`、`context_bytes:int`，即使 count 为零也保留 zero object。`TokenTotals` exact keys are `status:"available"|"unavailable"`、`input_tokens:int|"unavailable"`、`output_tokens:int|"unavailable"`、`total_tokens:int|"unavailable"`；仅当该 sample 每个 invocation 三项 Token 都 measured 时 available并求和，否则三项全部 unavailable。所有 decimal totals使用 parsed six-decimal strings做 `Decimal` exact sum并以六位输出。

`RuleResult` exact keys are `rule`、`status`、`details`；success 中 rule 顺序固定为 `path_safety, identity_unique, archived_strict, instrumentation_complete, plan_complete, final_review_approved, role_coverage, measured_fields_complete, metrics_totals_consistent`，status 恰为 `passed`，details 恰为 `[]`。`Aggregate` exact keys are `sample_count:3`、`work_ids:list[str]`（input order）、`task_counts:list[int]`（sorted unique）、`change_shapes:list[str]`（sorted unique）、`task_count_diverse:bool`、`change_shape_diverse:bool`、`representative:true`；representative 要求两个 diversity bool 至少一个为 true。

Failure JSON exact keys为 `status:"error"`、`message:"BLOCKED: representative_metrics_missing"`、`exit_code:3`、`details:list[FailureDetail]`。`FailureDetail` exact keys为 `sample_dir:str`、`work_id:str|"unavailable"`、`rule:<上述九个 sample rules|"argument_count"|"aggregate_representative">`、`message:str`。零/少于/多于三次 `--sample-dir` 产生唯一 item：`sample_dir="invocation"`、`work_id="unavailable"`、`rule="argument_count"`，message含 observed count；此分支不读取任何路径。Canonical duplicate 对第一个出现保留正常 identity result，对每个后续重复项按 input order产生 `identity_unique` failure，sample_dir用该次原始 absolute argument，work_id用已解析值或 unavailable。Aggregate diversity failure使用 `sample_dir="aggregate"`、work_id unavailable。其余 details按 input order/上述 rule order稳定排列；不得含 source file contents、raw metrics blocks或任意额外 keys。Human output从同一 typed result渲染逐 sample identity/aggregates/rules，success 末行固定 `status: representative_metrics_accepted`；不得另行读取。

任一条件失败时，controller 不派发 Phase 3 role；原始执行的 `PLAN-TASK-008/009` 或 reopened delta 的 `PLAN-TASK-001` 保持 `[ ]`，source worktree/HEAD 必须与各自 Phase 3/delta BASE 相同。证据通过后，原 Task 008 或 reopened delta Task 001 只消费并引用本 run 的 `execution/phase-3-sample-evidence.json`，不得二次读取样本目录；其 report 直接呈现每个 Sample 的 identity/header/verdict/coverage/rules 与全部 measured aggregates。跨 `direct_acs`/`semantic_view` 只比较各自 context totals，不能把不同 byte kind 直接相减为 Token 收益；TokenTotals unavailable 时固定写 `token comparison: unavailable`。

### SPEC-GRANULARITY-004 — Cohesive change slice rule
Upstream: DES-PLAN-003 [ADDRESSED]

PLAN author 先按一个可观察行为/契约结果形成 phase-level cohesive slice。若一个 slice 同时需要 create 与 modify paths，现有 R19 gate 下必须展开为 operation-homogeneous task group；组内每个 task 必须交付可直接测试的 intermediate contract，reviewer 只可依赖已完成前驱，最后一个 integration/adoption task 运行完整 Phase acceptance。单 task rollback 只在先回滚其组内 declared dependents 后执行；整个 group 可反向拓扑回滚且不触及其他 Phase。

原始执行 PLAN 的布局和编号固定为 `2 / 4 / 1 / 2`：Phase 0 = 001 metrics core create → 002 integration modify；Phase 1 = 003 context core create → 004 internal CLI modify → 005 wrapper create/smoke → 006 surface adoption modify；Phase 2 = 007 modify；Phase 3 = 008 profile core create → 009 integration modify。依赖不新增 field。每个 task 的 `Steps` 第一条 semantic line exact 为 `Prerequisite: none` 或 `Prerequisite: PLAN-TASK-NNN`；declared edges 仅为 001→002、003→004→005→006、008→009，001/003/007/008 使用 none。跨 Phase 顺序只由 PLAN 编号、最低 actionable task selector 与上一 Phase acceptance 控制，不进入 rollback graph。

若原始执行在 Task 009 因 PLAN `Files` 权限缺口停止并从 SPEC/PLAN 重开，reopened run 以重开时排除 `.req-to-plan/` 的 source-tree snapshot 与该 run 启动时动态记录的 full `Execution BASE` 共同作为 operational baseline：scoped workflow commit 可以推进 HEAD，但已 reviewed-complete 的原 Task 001–008 不得重放、不得生成 no-op source commits，也不得复制旧 execution ledger。新 PLAN 只形成一个从 001 重新编号的 modify-only delta task，合并原 Task 009 integration paths 与完成 fast role topology 所必需的 `execution_metrics.py`/direct tests；该 task 承担新的 Phase acceptance。这个 delta 例外不改变未来由 continue surfaces 生成的 `2 / 4 / 1 / 2` 布局规则。

Prerequisite checker 分两个兼容版本交付。Task 001/002 尚无新 command，使用当前 strict controller 已消费的 legacy progress 做唯一 bootstrap preflight：Task 001 要求 run=`EXECUTING`、Execution BASE 为 full SHA、PLAN 恰有九个 anchors/checkboxes 且全部 `[ ]`、没有 profile/escalation/task marker、HEAD=Execution BASE、Task 001 是最低 unchecked；Task 002 要求同一 run/BASE/task-count，Task 001 恰有 `[x]` 与唯一 `review clean` complete marker、Task 002 是最低 unchecked、HEAD=Task 001 marker head。任一条件 unknown/mismatch 时不得 dispatch 或修改源码。

Task 002 integration 注册 read-only internal command `execution-prerequisite-check --work-id <id> --task <N> --require-version 1|2`，由 Phase 0 core 的 profile-neutral parser 实现 implementation v1。v1 只接受 requested semantics 1；原始执行的 Task 003–009 在 dispatch 前逐字传 `--require-version 1`。它只接受 legacy/explicit strict ledger，按 `Prerequisite` 检查唯一 reviewed-complete 前驱或 none+最低 unchecked，并对 fast-only marker/event fail closed。Phase 2 的五个 continue/PLAN-author surfaces 静态生成 version 1 preflight，不宣称 fast 支持。Success human 必须含 `prerequisite_satisfied`、work ID、task、`implementation_version: 1`、`semantics_version: 1`；JSON 在现有 success envelope 中加入 exact fields `work_id:str`、`task:int`、`implementation_version:int`、`semantics_version:int`、`effective_profile:"strict"`、`prerequisite:str`、`satisfied:true`。Requested 2 在 implementation v1 exit 6且不 mutation。

原 Task 009 adoption；或执行中重开后的 delta Task 001；将 implementation 升级为 v2，并在同一个 modify task 中再次修改/测试 Phase 2 的五个 continue/PLAN-author surfaces，使新生成 PLAN 静态传 `--require-version 2`；不依赖运行时探测或 LLM选择。Implementation v2 + requested 1 精确执行旧 strict semantics，返回 `implementation_version:2`、`semantics_version:1`、`effective_profile:"strict"`；implementation v2 + requested 2 调用 SPEC-RESUME-006 parser，返回 `implementation_version:2`、`semantics_version:2` 与实际 effective profile。后者 strict 要求前驱唯一 reviewed-complete；fast 接受合法 implemented marker 或 reviewed-complete；fast→strict recovery 必须先补齐 marker-chain review再满足 strict；none 要求 Execution BASE 存在且自己是最小 actionable task。旧已生成 PLAN 的 version 1 invocation继续兼容，future fast-capable PLAN固定 version 2；任何 requested version大于 implementation version exit 6。这样已落地 Phase 0–2 不依赖尚未创建的 Phase 3 parser，且不新增 PLAN field。

Reopened delta 的唯一 Task 001 不调用 prerequisite v1：execute-start 必然写入唯一 `Execution Profile: strict`，而 v1 Task 001 为原 self-host bootstrap 特意要求 profile line 不存在，两者不可同时满足。Controller 在任何 source mutation/role dispatch 前执行等价且更窄的 current-run bootstrap：run status=`EXECUTING`；PLAN/ledger 恰有一个 Task 001 且 `[ ]`；恰有一个 `Execution Profile: strict`；无 escalation/implemented/complete marker；full `Execution BASE` 存在并等于当前 HEAD；排除 `.req-to-plan/` 后 source tree 与 `ac3233cd9782c96a665e0f56e43fc17c5d82187f` 无 diff；SPEC-SAMPLE-003 本 run evidence accepted。任一 mismatch 均不得 dispatch/mutate。该 exception 只用于本次已批准的 execution-reopen delta，不改变旧 v1、未来生成 PLAN 的 v2要求，也不允许 controller 修改 ledger 来伪造兼容。

禁止 task-per-file/task-per-class 式拆分；R19 拆分必须有上述 intermediate contract，不得创建指向未来 handler 的不可运行 wrapper。也禁止把没有共同验收结果的多个行为合并。此规则只改变生成指导，不增加 `Dependencies`、不改变 `PLAN_TASK_FIELDS`、trace closure、quality gate、checkbox 或 BASE/commit/diff contract。

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
- Phase 2 首次把上述五面写为 prerequisite checker semantics v1；原 Phase 3 Task 009 或 reopened delta Task 001 在同一 patch 把这五面与 OpenCode-derived test 升级为 v2。两次都是现有文件 modify，不新增生成面或 capability auto-detection。
- `tests/test_docs_consistency.py` 同时保护旧 EXE/FR-CM tokens 与本需求新增 tokens，不删除 dirty-tree、BASE、final review、full suite、`⚠️ DEFER` 或 archive 契约。

## API / Data / Config Contracts
### SPEC-METRICS-009 — Metrics file schema and ownership
Upstream: DES-EXEC-001 [ADDRESSED]

metrics 不参与 run state、resume、completion 或 archive gate；已存在 metrics 永不被普通 resume 覆盖。首次 `run-execute-start --profile strict|fast` 使用下列 recoverable start transaction：

唯一 public core entry signature 为 `start_execution_transaction(base_path: Path, work_id: WorkId, profile: str) -> RunRecord`。它内部拥有 `RunStateManager` load/status validation、symlink-safe PLAN read/anchor extraction、pinned run-directory handle、lock/marker/progress/metrics writes、state save 和 recovery；CLI `_cmd_run_execute_start` 只负责 argparse、调用该 entry 和 human/JSON formatting，不得预加载 `RunRecord`、另行解析 anchors 或以另一 signature 调用。

1. 相对 pinned run fd 安全打开 `logs/execute-start.lock`，取得 process-released exclusive nonblocking lock；POSIX 使用 `fcntl.flock(LOCK_EX|LOCK_NB)`。lock busy 或平台没有可靠等价 capability 时 exit 6、zero mutation。lock file 位于已忽略的 `logs/`，必须是 no-follow regular file。
2. 持锁期间用 `mkdir("execution", dir_fd=run_fd)` 原子创建最终目录；`mkdir` 的 EEXIST 是 no-clobber conflict/recovery input，任何并发创建的 empty dir、file 或 symlink 都不会被替换。记录 directory dev/ino，并在其中用 O_EXCL 写 `.start-transaction.json`；它是 canonical single-line JSON，exact fields 为 `schema: 1`、`work_id`、`profile`、`task_count`、`execution_base`（full SHA）。随后原子写入并校验 `progress.md` 与 `metrics.md`。
3. 两个 ledgers 验证完成且 marker 仍存在时保存 `run.md` 的 `EXECUTING` 状态；save 成功后才删除 marker并 fsync directory（capability available 时）。save 前的普通异常触发 best-effort rollback，但只能在仍持锁、directory dev/ino 未变、marker 内容匹配且 children 是 marker/progress/metrics 的允许子集时删除本次目录。save 已成功但 marker cleanup 失败时不得删除 execution；保留 marker 并由 executing recovery 完成。其他情况保留现场并 exit 6。
4. process crash 自动释放 lock。重试取得 lock 后：`closed + marker` 仅在 marker 匹配当前 work/profile/task count/BASE、目录 identity 稳定且 children 是允许子集时删除该 owned partial directory并从步骤 2 重建；`closed + no marker + two exact initial ledgers` 在 structure gate 仍通过时只补做 status transition。fast 两种 recovery 都要求调用者重新给出 `--profile fast --confirm-fast-eligible`。其他 single-file、partial、mismatched、symlinked、foreign-marker 或 extra-child 状态 exit 6 且不覆盖。
5. `executing + no marker + complete ledgers` 走 normal idempotent resume；`executing + matching marker + complete ledgers` 在持锁复核 status/work/profile/task count/BASE 后只删除 marker并继续 resume；`executing + marker/missing/partial/mismatched ledgers` fail closed。没有 sibling temporary directory，因此 crash-before-ledger 不产生未忽略的 worktree residue。fault injection 必须覆盖 lock/capability、mkdir 前后 crash、marker/progress/metrics writes、status save、marker removal、owned rollback/rebuild、executing marker cleanup、foreign residue和 concurrent file/empty-dir/symlink no-clobber。

本需求自身由旧版本启动执行时使用唯一 self-hosted bootstrap command：

```text
execution-metrics-bootstrap --work-id WF-20260829-r2p-execute-token-phase-r2p --profile strict --self-hosted-gap-through-task 002
```

Bootstrap 使用独立 `logs/metrics-bootstrap.lock`：相对 pinned run fd 以 `O_CREAT|O_RDWR|O_NOFOLLOW` 打开、fstat regular/identity 后取得 `fcntl.flock(LOCK_EX|LOCK_NB)`；lock busy 或平台缺少等价 capability 时 exit 6。首次发布在 pinned `execution/` fd 下创建唯一 `.metrics-bootstrap.<pid>.<32-lower-hex>.tmp`，flags 固定 `O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW`、mode `0o600`。Temp fd 从 create 保持打开直到 publish identity验证完成：写完 exact UTF-8 header并 fsync 后，对 open fd `fstat` 保存 regular mode/dev/ino，再对 temp name no-follow lstat并要求三者匹配；不得先 close。

随后调用 `os.link(temp, "metrics.md", src_dir_fd=execution_fd, dst_dir_fd=execution_fd, follow_symlinks=False)` 原子 no-replace publish。link success 后立即在仍打开 temp fd 的条件下，分别对 temp name 与 `metrics.md` 做 no-follow lstat；open-fd fstat、temp lstat、final lstat 必须都是同一个 saved regular dev/ino，任一 missing/symlink/replacement/mismatch 均 exit 6、不得读取/接受/删除 final。三方匹配后才 fsync execution fd、按 saved identity unlink本 invocation temp、再次 fsync并关闭 fd。平台缺少 dir-fd hard-link/no-follow/lstat 或 fsync capability时 fail closed，绝不退化为 `os.replace`；final target永不由协议 unlink/replace。

Crash/retry matrix 固定如下：publish 前崩溃最多留下唯一 temp，retry 不信任/不删除任何 abandoned temp并创建新 nonce temp；link success 后崩溃时 final 已是完整 hard-linked header，retry 走 exact-existing success；并发/foreign final 在 link 时产生 EEXIST，随后只安全读取 exact final，exact 才 idempotent success，mismatch/unsafe 则 conflict。普通异常只可在仍持 lock、final 尚不存在且当前 temp path仍与 saved dev/ino匹配时 best-effort删除当前 temp；cleanup失败保留 ignored residue，不改变判定。Tests fault-inject temp create/write/fsync、pre-link temp unlink/regular replacement/symlink replacement、link/EEXIST、post-link final-name replacement、三方 identity check、dir fsync、temp unlink/close、post-publish return，并验证 mid-write crash 永不产生 partial `metrics.md`、source swap 永不被接受。

所有调用先验证 run 为 `EXECUTING`、work ID/PLAN task count/Execution BASE 匹配、legacy profile 按 strict 解释、Task 001/002 分别有唯一 reviewed-complete record。metrics 不存在时属于首次创建：还必须确认 Task 003 没有 role/task state、HEAD 等于 Task 002 complete head，再使用上述 publish protocol。metrics 已存在时属于 retry/resume：不得再要求 Task 003 未开始；必须安全读取并 exact-match work/profile/task_count/schema、`instrumentation_complete=false` 与 canonical `bootstrap_gap=execution_start_through_task_002_reviewed_complete`。Header 后为空或只含从 Task 003 起、与 progress/task order 一致、sequence 连续且完整的 invocation blocks 时返回 idempotent success，并从下一 sequence append。Task 001/002 block、partial/乱序 block、unsafe/non-regular、foreign/mismatched header 或结构损坏均 exit 6 且 zero overwrite/delete。该 exception 不做历史回填，首个 measured role 是 Task 003 implementer，当前 run 永不符合 SPEC-SAMPLE-003。未来正常 start 从首个 role 采集，并只写 complete/none 组合。

Header fields and values:

```text
# Execution Metrics
work_id: <validated WorkId>
r2p_version: <R2P_VERSION>
instrumentation_schema: <positive integer constant>
profile: strict|fast
task_count: <PLAN anchor count>
instrumentation_complete: true|false
bootstrap_gap: none|execution_start_through_task_002_reviewed_complete
change_shape: unavailable
metrics_finalized: false
```

Header combination matrix 是封闭集合：正常 start 只允许 `instrumentation_complete=true` + `bootstrap_gap=none`；仅上述精确 work ID 的 self-hosted bootstrap 允许 `false` + `execution_start_through_task_002_reviewed_complete`。任何其他组合 parse fail closed；normal resume 不把 false 改成 true，finalization 只更新 shape/finalized。

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

`tools/workflow_cli/execution_context.py` 私有的 pinned-tree read helpers 必须满足以下契约；不得把这组固定六源 traversal 临时下沉到 `atomic.py` 或改变 `atomic.read_regular_text` 的单文件 public contract：

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
| SPEC-METRICS-009 | 唯一 transaction signature/ownership；locked no-clobber execute-start、marker/status crash recovery、foreign residue 与 fault injection；self-host lock + open temp fd + fsync + hard-link no-replace + post-link three-way identity、pre-link temp unlink/regular/symlink replacement、post-link final replacement、每个 crash point、EEXIST race、abandoned temp、first-create vs exact-header retry/resume、canonical gap、Task003+ blocks、mismatch zero-overwrite；exact header/JSON grammar、role/task/status/wave matrix、`monotonic_ns` + `ROUND_HALF_UP` boundary/totals、context pair、all-role blocks；A/M/D/T/Rddd/Cddd classifier table 与 failed-finalize non-gating。 |
| SPEC-CONTEXT-010 | temp workspace 中 directory/file symlink、non-regular、FIFO、pre-stat/open race、capability unavailable、fd cleanup、parent replacement pinned-tree behavior。 |
| SPEC-CONTEXT-011 | Unicode、comments、read-only blocks、fences、whitespace-only、fixed order/separators/one newline、per-source/aggregate bytes、human/JSON exact keys、missing/no partial、wrong status。 |
| SPEC-REPORT-012 | 两完整 execute surfaces 强制所有 section、inline verification、every-role `⚠️ DEFER` propagation；fast/strict final input matrix。 |
| SPEC-GRANULARITY-004 / SPEC-PARITY-008 | Task001/002 legacy bootstrap matrix；reopened-delta-Task001 exact explicit-strict manual bootstrap；implementation×requested `1/1,1/2,2/1,2/2` semantics/exit/JSON fields；Task007五面静态v1、原Task009/reopened-delta-Task001同五面静态v2及旧PLAN兼容；future `2/4/1/2` operation-homogeneous layout、execution-reopen delta 不重放 reviewed-complete tasks、Steps-only exact grammar、group-only edge/rollback、OpenCode derived install + Gemini description；PLAN fields/schema/trace tests unchanged。 |
| SPEC-PROFILE-013 | closed handshake 参数矩阵、zero-mutation snapshots、structure recheck、reject reason newline rejection、direct confirm、executing same/different/flags、legacy strict。 |
| SPEC-LEDGER-014 / SPEC-RESUME-006 | comment/fence-aware exact regex、unique profile/events/markers、malformed lines、marker continuity、BASE chain、checked/implemented conflict、first actionable task、strict escalation/recovery、atomic all-task final migration crash points、legacy strict complete marker。 |
| SPEC-FAST-005 / SPEC-FINAL-007 | fast no per-task reviews、runtime triggers strict recovery、final primary task-by-task review、full suite、fix/re-review metrics、checkbox only after approval、archive gate fails before approval。 |
| SPEC-SAMPLE-003 | 0/2/3/4 argument-count details、canonical duplicate ordering、no discovery/write、canonical exact nested JSON golden/error detail order、三 canonical no-follow archived paths、complete/none header、schema/profile/finalized/verdict/task count/role coverage、all seven role counts、duration/report/full-suite/context/token aggregates、fix-wave evidence、shape/task diversity；原Task008及reopened delta各自在本run重新验证/仅消费 evidence，且每个失败分支保持 source/checkbox/HEAD 不变。 |

Implementation verification uses project-required `.venv/bin/python -m pytest`。每个 PLAN task 先运行其 targeted module/tests；每个 Phase task review 根据 SPEC-VERIFY-001 决定是否 full suite；最终 whole-branch review 必须运行 `.venv/bin/python -m pytest tests/ -q` 并记录 fresh result。

## Non-goals
- 不生成持久化 ACS/context bundle、manifest、content hash 或 drift gate。
- 不改变 CLI/agent responsibility boundary；CLI 只管理结构、安全读取和 deterministic parsing/formatting。
- 不引入 shared implementer、parallel current-branch writes、batch reviewer 或 balanced profile。
- 不弱化 dirty-tree、Execution BASE、task commit/diff、final full suite、final verdict 或 archive gate。
- 不把 unavailable/estimated values 写成 measured metrics，不把 bytes reduction 声称为精确 Token reduction。
- 不新增第三方依赖；directory-fd/context/filter/profile logic 使用 Python stdlib 与仓库现有模块。

## PLAN Handoff

本次 reopened run 只规划一个从 `PLAN-TASK-001` 重新编号的 operation-homogeneous `modify` delta；排除 `.req-to-plan/` 的 source tree 必须与原执行 Task 001–008 reviewed-complete 后的 snapshot `ac3233cd9782c96a665e0f56e43fc17c5d82187f` 一致，执行启动后另以本 run 动态记录的 full `Execution BASE` 约束 HEAD。PLAN 不得重放这些任务、复制旧 execution ledger或创建 no-op source commits。

唯一 delta task 必须同时满足：

1. `Files` 包含原 Task 009 的全部 modify paths，并新增 `tools/workflow_cli/execution_metrics.py` 与 `tests/test_execution_metrics.py`；不得包含 create/delete/rename path。
2. source mutation/role dispatch 前，用用户已确认的三个绝对样本路径重新运行 SPEC-SAMPLE-003 validator，并把 JSON stdout 写入 reopened run 自己的 ignored `execution/phase-3-sample-evidence.json`：
   - `/Users/xubo/Desktop/test-1/.req-to-plan/archive/WF-20260831-run-776c763d`
   - `/Users/xubo/Desktop/test-2/.req-to-plan/archive/WF-20260831-run-e31ea18d`
   - `/Users/xubo/Desktop/test-3/.req-to-plan/archive/WF-20260831-1-2`
3. 第一条 semantic Steps line 为 `Prerequisite: none`。派发前由 controller 执行 SPEC-GRANULARITY-004 的 exact explicit-strict manual bootstrap，不能调用必然拒绝 profile line 的 checker v1，也不能修改 ledger 绕过它。实现本身升级 checker 到 v2并同步五个 PLAN-author surfaces；`1/1,1/2,2/1,2/2` 通过隔离 fixture 验证。
4. TDD 先证明 strict metrics sequence 完全兼容，再证明 fast 接受 `N implementers -> primary final reviewer` 以及合法 final repair waves；fast task-reviewer、缺失/重复/乱序/blocked continuation 必须 fail closed，不能生成虚假 role block。
5. 同一个 task 集成 SPEC-PROFILE-013、SPEC-LEDGER-014、SPEC-FAST-005、SPEC-RESUME-006、SPEC-FINAL-007、SPEC-METRICS-009 与相关 parity，并通过直接受影响测试和 fresh full suite；最终 whole-branch review 再运行 fresh full suite。

Global Constraints 必须保留：TDD-first；所有 source edits 在当前分支串行；clean-tree/BASE/task-scoped commit/diff；无 push/PR/远程 mutation授权；Claude/Codex lockstep；OpenCode derived/Gemini tests；metrics non-authoritative；final review/full suite/archive gates 不变。

## Trace
<!-- Map this stage's IDs to upstream/downstream. R3 derives & checks closure. -->
| This ID | Upstream | Status |
|---|---|---|
| Spec headings above | Approved DESIGN v8; execution-reopen source snapshot ac3233c plus dynamic Execution BASE | [ADDRESSED] Behavior contracts remain intact; PLAN handoff prevents replay, defines an executable explicit-strict bootstrap, and gives the remaining profile-aware metrics integration explicit file authority. |

## Upstream Summary (read-only)
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
