# SPEC 强制独立评审 v5

Verdict: Changes Requested

## Review Scope

已完整审阅 `03-requirement-brief.md` v1、`04-risk-discovery.md` v3、Approved `05-design.md` v8 与 `06-spec.md` v5，并对照 `plan-subagent-review-v2.md` 的 I-1..I-5；只读核对当前 progress/execute shortcut、PLAN field schema、R19 file gate 和已存在的 parser/CLI surfaces。

SPEC v5 已把九任务布局、context wrapper 顺序、唯一 transaction signature、self-host Task002→Task003 gap、Phase 0 sample validator 和 strict/fast ledger 主干写入语义正文。以下三项仍使当前 PLAN 无法按自己的前置验证执行，或使 crash/no-write/evidence 契约需要实现者自行选择算法与 JSON shape。

## Critical

无。

## Important

### N-I1 — 所有 task 都要求调用的 prerequisite parser 要到 Task008 才拥有实现，Task001–007 没有可执行检查路径

**证据**

- `SPEC-GRANULARITY-004` 第 55–57 行要求九个 task 的 `Verification` 第一项调用“同一 effective-profile/task-state parser”，且 parser failure/state mismatch 时不得 dispatch 或修改源码。
- `PLAN Handoff` 第 297–300 行把 Phase 0 的 Task001–002 限定为 metrics/transaction/sample validator，把 Phase 1 限定为 context view，把 Phase 2 Task007 限定为生成规则；profile/ledger core 到 Phase 3 Task008 才创建，Task009 才接入 CLI/shortcut/surfaces。
- 当前源码只有 legacy 最低未勾选任务选择，没有 profile line、implemented marker、escalation 或该 satisfaction matrix 的 parser/command。SPEC 也没有命名一个在 Task001 dispatch 前已存在的 CLI/API。
- 因此 Task001–007 的 canonical Verification 无法执行；Task007 落地后的 Phase 2 surface 还可能开始生成依赖一个尚未交付的 parser 的 PLAN，破坏 Phase 2 独立交付。

**影响**

PLAN author 只能删掉必需的 pre-dispatch check、让 agent 自由文本解析 progress，或把 profile parser 偷移到更早 task。三种选择都会改变 task Files/ownership、验证确定性或 Phase 边界。

**具体修订要求**

在 SPEC/PLAN handoff 中固定一个 bootstrap-safe ownership 与调用面。可行的最小方案是把 profile-neutral prerequisite/task-state parser 和只读 preflight command 放进 Phase 0 core/integration，使 Task003 起可调用；同时为 Task001/002 给出当前 legacy strict ledger 可执行的唯一 bootstrap preflight。若希望到 Phase 3 才交付该 parser，则 Phase 2 不能强制现有执行依赖它，必须定义在 Phase 3 adoption 后才生效的版本化规则和当前九任务的另一条 exact pass path。无论选择哪种，PLAN 必须能写出逐字可执行命令，而不能只写“调用同一 parser”。

### N-I2 — self-host bootstrap 的 `O_EXCL/atomic no-clobber` 没有唯一可实现算法，mid-write crash 会留下不可恢复 partial header

**证据**

- `SPEC-METRICS-009` 第 118 行只写“以 O_EXCL/atomic no-clobber 写 exact header”，没有定义 lock、owned temp、publish primitive、fsync、cleanup/retry marker 或 crash matrix。
- 直接以 `O_CREAT|O_EXCL` 打开最终 `metrics.md` 再写入，多行 header 写到一半崩溃会留下 partial final file；下一次调用按同一行的规则把结构损坏视为 foreign/conflict，无法收敛为 idempotent success。
- 复用仓库 `atomic_write_text` 的 temp+`os.replace` 虽可避免 partial final，但会覆盖在 precheck 后并发出现的 foreign target，违反 no-clobber/zero-overwrite。
- 正常 start transaction 有 lock、marker、owned-directory rollback/rebuild 的完整恢复表；self-host bootstrap 在已有 `execution/` 目录中写单文件，不能隐式借用该目录删除规则。

**影响**

`first-create vs retry/resume` 仅覆盖“完整 header 已发布后崩溃”，没有覆盖发布过程本身；不同实现会在 crash safety 与 foreign-file no-clobber 之间做不同取舍。

**具体修订要求**

固定一个 stdlib 可执行的 no-replace publish protocol及故障表。例如：取得独立 no-follow bootstrap lock；在 pinned `execution/` fd 下用唯一 temp + `O_EXCL` 完整写入并 fsync；使用不会替换既有 destination 的原子 publish primitive；成功后 fsync dir并清理 owned temp。平台缺少该 primitive 时 fail closed。也可以使用 bootstrap transaction marker，但必须列出 marker/temp/final header 的 complete、owned cleanup 与 foreign-residue矩阵。测试必须覆盖 header 每个写入/发布/清理 crash point和并发 final target创建。

### N-I3 — validator JSON 没有 exact nested schema，且唯一安全输出缺少 Task008 强制引用的性能 aggregates

**证据**

- `SPEC-SAMPLE-003` 第 46 行只固定 success 顶层 keys；`samples` 用“含上述字段”描述，`aggregate` 只说含 diversity verdict，没有列出 exact nested key names、types、枚举、顺序或 failure `details` shape。
- 第 48 行又要求 Task008 report逐 run固化 invocation count、role elapsed total、context bytes total、verification total、report bytes total、full-suite count/duration和可得 Token，并按 `direct_acs`/`semantic_view` 分栏。
- 第 46 行的 validator output并不要求输出这些 per-run aggregates；第 32–34 行又把 validator 定义为 Phase 3 source mutation前唯一 pinned/no-follow sample read path。Task008 若要满足第 48 行，只能重新读取任意 archived directories，或由实现者自行给 `samples` 增加未规定字段。

**影响**

同一组三样本可产生不兼容 evidence JSON，Task008/report reviewer也没有唯一、安全、可复现的数据来源。PLAN 无法为 JSON golden tests和 evidence consumption写出确定 skeleton。

**具体修订要求**

把 validator success/error JSON 写成完整 exact schema。每个 sample object 必须列出固定 key/type，包括身份、header/verdict/coverage/rules，以及第 48 行全部 measured aggregate；context totals以固定 `direct_acs`/`semantic_view` 子对象分组，Token明确 integer totals或 `unavailable`。固定 aggregate object 的 sample count、task-count/shape diversity inputs和 verdict，固定 failure `details` item shape，并规定不包含 sample正文。Task008只能消费该 evidence JSON，不得二次读取样本目录。

## Minor

无单独 Minor。

## PLAN v2 Original Finding Closure

| Original finding | SPEC v5 status | Evidence |
|---|---|---|
| I-1 task-vs-group cohesion/R19 | **主决策已闭合** | 固定 `2/4/1/2` operation-homogeneous groups、intermediate contract、Phase acceptance、group-only rollback及 schema不变；但 prerequisite 可执行性仍受 N-I1 阻断。 |
| I-2 context wrapper bootstrap/ownership | **闭合** | Phase 1 明确为 context core create → internal CLI modify → wrapper create/smoke → surface adoption；private pinned-tree helpers归 `execution_context.py`，不扩张 `atomic.py`。 |
| I-3 self-host metrics timing | **时点已闭合** | Task002 reviewed complete后、Task003 dispatch前运行唯一 bootstrap；gap/header组合、首次与existing-header分支、Task003+ resume均已定义；但首次发布的 crash/no-clobber算法仍有 N-I2。 |
| I-4 Phase 3 validator pass path | **入口已闭合** | validator在Phase 0 integrate落地且是Task008 source mutation前唯一machine preflight；input/error/no-write主体明确，但输出/aggregate consumption仍有 N-I3。 |
| I-5 transaction signature/ownership | **闭合** | 唯一 public signature为 `start_execution_transaction(base_path, work_id, profile)`；core拥有record/PLAN/pinned dir/lock/marker/ledgers/state/recovery，CLI只解析和format。 |

## Confirmed Complete Areas

- Header `instrumentation_complete/bootstrap_gap` 组合是封闭集合；当前 self-host run不会成为样本，未来 run从首 role 完整采集。
- 正常 start transaction的lock、marker、closed/executing crash recovery、foreign residue和state-save ownership已达到decision-complete。
- Context helper所有权、directory-fd/no-follow/O_NONBLOCK语义、human/JSON context view及wrapper先CLI后创建顺序一致。
- strict/fast handshake、ledger segment、BASE chain、implemented marker、单向recovery、profile-specific final inputs和atomic final marker migration没有新冲突；N-I1仅是prerequisite checker交付时序问题。
- 九任务编号和Files operation布局一致：001–002、003–006、007、008–009；未发现未锚定deferral、远程mutation授权或第三profile范围漂移。

## Ambiguity Conclusion

仍存在 unresolved ambiguity / undecided point：N-I1 的 prerequisite checker ownership/可调用时点，N-I2 的 bootstrap atomic no-replace publication算法，以及 N-I3 的 validator nested output/aggregate source。其余上游决策与原始 PLAN v2 阻断已经闭合。

## Approval Condition

补齐以上三项后做聚焦 SPEC 复审；不需要重开已批准的九任务布局、context architecture、fast handshake或正常 start transaction设计。
