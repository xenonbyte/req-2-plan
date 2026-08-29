# DESIGN 强制评审 v4

Verdict: Approved

## Summary

DESIGN v4 已闭合 v3 的 N-I1、N-I2、N-M1、N-M2，且没有引入新的 unresolved ambiguity、undecided point、架构冲突或未锚定 deferral。四个 Phase 已达到可进入 SPEC 的 decision-complete 程度。

## v3 Finding Closure

| v3 Finding | v4 evidence | Result |
|---|---|---|
| N-I1 fast semantic门/exit/direct bypass | 第 99–101 行定义两步 handshake：首次 fast 只做结构门并返回 review stop、零 mutation；confirm 后才 start；reject 稳定 exit 6；direct confirm 明确为可信人工 attestation boundary | Closed |
| N-I2 sample provenance/change shape | 第 63、67、111–113 行改用跨仓库可验证的 `r2p_version` + `instrumentation_schema`，删除 SHA ancestry；shape 在 final diff 后一次性 finalize，样本只接受 finalized archived metrics | Closed |
| N-M1 directory-fd error semantics | 第 79–81、89 行明确 pinned parent 被替换后安全读取原树、不承诺检测 path-name drift；relative pre-stat/open/fstat、`O_NONBLOCK`、FIFO 与替换树测试均明确 | Closed |
| N-M2 role elapsed clock | 第 65 行明确 wall clock 只产 started/ended timestamps，`elapsed_seconds` 使用 controller monotonic clock | Closed |

## Scope and Risk Coverage

- SCOPE-IN-001..010 均有 Chosen Design 和测试/表面落点。
- RISK-PERF-001..RISK-SEQUENCE-012 均有具体 mitigation；metrics、I/O、profile、resume、parity、sequence 的高风险项已有可测试契约。
- strict 仍是默认，现有 N implementer + N reviewer + final reviewer、安全 Git/BASE、final full suite、final verdict 和 archive gate 语义保持不变。
- fast 只在 LIGHT、无 modifier、语义资格显式确认后进入；运行中风险只能单向升级 strict。
- Phase 0/1/2 可独立落地和回滚；Phase 3 的三份 finalized archived strict-run 证据是原始需求规定的入口条件。

## Contract Checks

### Fast handshake

- 首次 `--profile fast` 成功只返回 `fast_profile_review`，不创建 progress/metrics、不改变 run status。
- `--confirm-fast-eligible` 重跑结构门后才 mutation；confirm 失败保持零 mutation。
- `--reject-fast-ineligible` 在 run 仍 closed 时稳定返回 exit 6，且不自动降为 strict。
- 两个 flag 的互斥、profile 组合、closed/executing 状态限制和 direct terminal trust boundary 均已决定。

### Metrics and representative samples

- controller/role producer、monotonic elapsed、verification records、context byte kinds 和 unavailable 口径完整。
- `instrumentation_schema` 取代跨仓库 Git ancestry，可覆盖不同目标仓库和无 Git 安装。
- `change_shape` 从最终 execution-base→HEAD diff 通过固定分类器一次性 finalize；未 finalized 数据不能用于 Phase 3。
- 三个样本必须来自不同 work ID、archived strict runs，包含完整任务角色与 final review/full suite，且满足 task-count/shape 代表性条件。

### Context view safety and I/O

- repo/run/execution 通过 pinned directory fds 和 relative no-follow traversal 读取。
- source 采用 pre-stat、`O_NOFOLLOW | O_NONBLOCK`、fstat dev/ino/mode 校验；FIFO 不会阻塞。
- parent path 在 pin 后替换不会切换读取树；该行为与错误表和测试预期一致。
- human/JSON schema、byte 公式、source 顺序、no-partial-output 和错误码均已固定。

### Resume, BASE and platform parity

- immutable initial profile、ordered escalation event、legacy strict、same/different resume 参数、implemented marker、BASE chain 和 checkbox 时点无歧义。
- Claude/Codex 完整 execute surfaces 同步；OpenCode 验证 Claude-derived 输出；Gemini 保留 wrapper forwarding 并承载其可表达的 fail-closed 入口提示。
- Phase 2 的五个 continue surfaces 和 OpenCode 派生矩阵完整。

## Ambiguity / Deferral Audit

- `Decision Requests: none` 与正文一致，没有隐藏的用户选择。
- 未发现 TBD、TODO、待决定或依赖实现者自行选择的关键合同。
- 未发现无 `SCOPE-OUT-*` 锚点的“以后再做/本轮不做”式 deferral。
- Phase 3 证据不足时保持当前 run 的任务未完成并返回 `BLOCKED`，没有把 in-scope 工作移到另一个未来需求，因此不构成 R20 deferral。

## Non-blocking SPEC Note

SPEC 的 metrics completeness 测试应明确：若一次 run 出现 fixer、re-review 或 final-fixer wave，这些实际发生的角色调用也必须各有 metrics block；不能只检查最小 implementer/reviewer/final 三类角色。这是对第 63、65 行“每个角色调用”的直接编码，不需要回改 DESIGN。
