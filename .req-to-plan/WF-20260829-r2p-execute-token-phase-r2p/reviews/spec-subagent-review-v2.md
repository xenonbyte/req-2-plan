# SPEC 强制独立评审 v2

Verdict: Changes Requested

## Review Scope

已完整复审 `06-spec.md` v2，并逐项回查 `spec-subagent-review-v1.md` 的 I-1..I-6、M-1/M-2；同时核对已批准 DESIGN v4、Requirement Brief/Risk Discovery、当前 `run-execute-start`/state persistence、tier model 与 workspace `.gitignore` 约束。

v2 已实质闭合大部分上一轮问题，但 recoverable start 的 crash/no-clobber 边界、monotonic duration 的六位小数量化、以及 Git name-status 的接受集合仍不是唯一实现。它们会分别改变恢复安全、跨运行指标值和 `change_shape`，因此 SPEC 尚未 decision-complete。

## v1 Finding Closure

| v1 finding | Status | v2 evidence |
|---|---|---|
| I-1 representative samples | Closed | `SPEC-SAMPLE-003` 强制每个 invocation 的核心性能字段 measured，Token 仅可选，并要求逐 run 汇总 invocation/elapsed/context/verification/report/full-suite/Token。 |
| I-2 metrics grammar/matrix | Partially closed | canonical JSON、exact keys、Decimal total、role/task/status/wave 和 context pair 已定义；但原始 monotonic delta 到六位小数的量化仍未定义，见 N-I1。 |
| I-3 exact classifier | Partially closed | path extraction、rename/copy、test-first、case/component/module 算法已自包含；但接受的 Git status token 仍使用“等”，见 N-I2。 |
| I-4 atomic fast final migration | Closed | `SPEC-RESUME-006` 要求内存构造全 ledger，并且只调用一次 `atomic_write_text`；replace 前后 crash state 均有确定语义。 |
| I-5 recoverable execute start | Partially closed | closed/executing retry矩阵、initial-ledger reconciliation、legacy bootstrap 和 fault injection 已加入；但 pre-install crash 与 no-clobber install 仍缺决定，见 N-I3。 |
| I-6 platform fresh session | Closed | `SPEC-ROLE-002` 明确全新 invocation、零 inherited turns/messages、无保证则 dispatch 前 fail closed，并要求逐平台写明机制。 |
| M-1 marker/event character grammar | Closed | 正十进制 N、精确 7 位 lowercase SHA、单行非空 reason、唯一 marker、fence/comment-aware fail-closed parser 均已定义。 |
| M-2 sample path trust | Closed | canonical path 去重、WorkId/basename、root-to-leaf no-follow directory-fd traversal、pinned-fd regular reads 和只读失败语义均已定义。 |

## Critical

无。

## Important

### N-I1 — 六位小数格式已固定，但 monotonic measurement 的量化算法仍未决定

**证据**

- `SPEC-METRICS-009` 第 125、140、149 行要求 controller/role 的 monotonic duration 输出 exactly six fractional digits，并用 `Decimal` 汇总已经序列化的 record durations。
- SPEC 没有规定原始 monotonic measurement 使用 `monotonic()` 还是 `monotonic_ns()`，也没有规定超过六位时是 truncate、round-half-even 或 round-half-up。
- 因此同一个 0.0000005s 边界值可合法序列化为 `0.000000` 或 `0.000001`；controller elapsed、verification record、Phase 3 aggregate 会随实现而变。

**最小修订**

固定一个算法并用于 controller 与 role，例如：用 `time.monotonic_ns()` 取整数差，转为 `Decimal(delta_ns) / Decimal(1_000_000_000)`，再以明确的 rounding mode quantize 到 `Decimal("0.000001")`；序列化必须保留六位。`verification_total_seconds` 只对已量化的 record strings 精确求和，不再次量化。增加小于半微秒、恰为半微秒、进位和多 records 求和测试。

### N-I2 — classifier 的 Git status token 集合仍以“等”表示，不是 exact classifier

**证据**

- `SPEC-METRICS-009` 第 151 行写成“A/M/D 等单路径 status”，同时又规定“未知 status”失败。
- `git diff --name-status -z` 还可能输出 `T`、带 similarity score 的 `Rnnn`/`Cnnn`，以及异常/未合并类 token。当前文本不能唯一决定 `T` 是否接受、R/C score 的精确 grammar/范围，以及哪些 token 必须 fail finalization。
- `change_shape` 是 Phase 3 sample diversity gate 的输入；这里不能由实现者选择。

**最小修订**

逐字列出 accepted token grammar 和 path arity，例如明确单路径 token 集、`R`/`C` score 的格式与范围，以及其余 token 一律 fail；补 `T`、合法/非法 similarity score、unmerged/unknown token 的 table tests。其余 path/classification 算法可以保持不变。

### N-I3 — start transaction 没有覆盖 pre-install crash orphan，且普通 directory rename 不保证目标 no-clobber

**证据**

- `SPEC-METRICS-009` 第 96–99 行先在 run directory 下创建 sibling temporary execution directory，再以 directory rename 安装；crash recovery 只定义了 `closed_at_plan_checkpoint + execution/`，没有定义 crash 发生在 rename 前遗留 temporary directory时的重试/清理。
- 当前 `.req-to-plan/.gitignore` 只忽略 `/*/execution/`，未命名的 sibling temp directory 默认会成为 untracked dirty-tree 输入，并可能让执行恢复被自身残留阻断。
- POSIX 普通 directory rename 可替换并移除一个并发出现的空目标目录；仅在 rename 前检查“`execution/` 不存在”不能同时满足“目标必须不存在”和 symlink/partial/mismatched target 不覆盖的契约。

**最小修订**

定义 transaction temp 的精确命名/忽略与 crash-retry规则：如何识别本事务残留、何时按 inode/预期 children 安全清理、何时 conflict。另固定一个 atomic no-clobber install protocol；若依赖平台 capability，则 capability 不可用时 fail closed。补 crash-before-rename、stale owned/foreign temp、rename 前并发空目录/文件/symlink 目标测试，并断言不覆盖、不制造阻断后续 clean-tree 的残留。

## Minor

无新的 Minor finding。

## Confirmed Contract Consistency

- role/task/status/fix-wave 的单 block 矩阵、canonical single-line JSON、Token 三字段联动与 context mode/kind 配对一致。
- task-state segment 允许 fast→strict recovery 逐步移动 reviewed prefix；fast final marker/checkbox 迁移为单文件一次原子替换，不再产生 v1 的中间非法状态。
- LIGHT 且 modifier set 为空的结构门、两步 semantic handshake、direct-confirm trust boundary 和 executing profile matrix一致。
- directory-fd context/sample reads 的 `O_NONBLOCK`、pre-stat/open/fstat、pinned-parent 与 no-partial-output 语义闭合。
- 代表性样本不再允许核心 measured 字段 unavailable，且报告聚合足以审计 elapsed/context/verification/report/full-suite；不同 context byte kind 不被误当 Token 对比。
- 四个 PLAN handoff slices 覆盖全部 SPEC，没有把 Phase 3 或其他 scope 推迟到未来 run。

## Ambiguity / Deferral Conclusion

- 仍有 unresolved ambiguity / undecided point：N-I1、N-I2、N-I3。
- 未发现未锚定 deferral。`BLOCKED: representative_metrics_missing` 是当前 Phase 3 的明确 prerequisite 行为，不是 scope deferral。

## Approval Condition

只需补齐 N-I1..N-I3 的确定算法/恢复分支及对应测试矩阵，即可再次复审；无需重写已闭合的其他契约。
