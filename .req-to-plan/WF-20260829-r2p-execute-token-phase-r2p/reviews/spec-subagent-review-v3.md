# SPEC 强制独立评审 v3

Verdict: Approved

## Review Scope

本轮只读聚焦复核 `spec-subagent-review-v2.md` 的 N-I1..N-I3，并快速检查对应修订是否引入新的 unresolved ambiguity、undecided point、恢复冲突或 scope deferral。

## Finding Closure

### N-I1 — Closed

`SPEC-METRICS-009` 现已固定 controller 与 role 均使用 `time.monotonic_ns()`，要求 `end_ns >= start_ns`，以 `Decimal(delta_ns) / Decimal(1_000_000_000)` 计算并使用 `ROUND_HALF_UP` quantize 到 `Decimal("0.000001")`。每条 verification record 使用同一算法；total 只对已量化的字符串精确求和且不再次量化。小于、等于和大于半微秒的边界及多 record 求和均有确定结果，不再允许实现者选择 rounding 语义。

### N-I2 — Closed

Classifier 已把 accepted token grammar 固定为单路径 `A|M|D|T` 和双路径 `Rddd|Cddd`，其中 `ddd` 必须为三位十进制 `000..100`；同时固定了 path arity、R/C old+new path、`U|X|B`、非法 score、缺失/多余 path 与其余 token 的 fail-finalization 行为。原有 case-sensitive POSIX path、test-first、migration/component 和 module 分类算法保持一致，`change_shape` 已可唯一复现。

### N-I3 — Closed

Start transaction 已取消 sibling temp/rename 方案，改为：

- pinned run fd 下的 no-follow regular lock file与 process-released exclusive nonblocking `flock`；无可靠 capability 时 fail closed；
- 持锁执行 atomic `mkdir("execution", dir_fd=run_fd)`，因此并发 empty dir/file/symlink 均只产生 no-clobber conflict；
- O_EXCL canonical transaction marker记录 work/profile/task count/full BASE，再写入并校验两份 ledger，最后保存 EXECUTING；
- rollback 受 lock、directory dev/ino、marker identity/content 与 exact allowed children 共同约束，不删除 foreign residue；
- `closed + marker`、`closed + no marker + exact initial ledgers`、`executing + matching marker + complete ledgers`、normal executing resume 及所有 partial/mismatched/foreign states 均有确定恢复或 conflict 分支；
- 无 sibling temp，且测试矩阵覆盖 mkdir 前后 crash、写入/status/marker cleanup、owned rollback/rebuild、foreign residue和并发 no-clobber。

该协议与 metrics non-authoritative、fast 二次 confirm、legacy bootstrap 和执行状态机一致。

## New Ambiguity / Deferral Check

- 未发现新的 unresolved ambiguity 或 undecided point。
- 未发现未锚定 deferral。
- `BLOCKED: representative_metrics_missing` 仍是当前 Phase 3 的明确 prerequisite 行为，不是推迟 scope。

## Final Assessment

N-I1..N-I3 已全部关闭。SPEC v3 对 metrics 数值、classifier、recoverable start、fast/resume/BASE/marker、directory-fd、JSON、跨平台 fail-closed 和三样本聚合均已达到 decision-complete，可进入 PLAN。
