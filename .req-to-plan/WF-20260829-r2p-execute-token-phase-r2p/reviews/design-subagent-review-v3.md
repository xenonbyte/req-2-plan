# DESIGN 强制评审 v3

Verdict: Changes Requested

## Summary

v3 已实质闭合 v1 的 I-1..I-5、M-1..M-2：三样本恢复为三个独立 archived strict runs；metrics 的 producer/单位明确；profile/resume 矩阵明确；context-view 改为稳定 directory-fd traversal；五个 continue surfaces 与 OpenCode 派生矩阵补齐；JSON/byte 公式和任意角色 `⚠️ DEFER` 传播规则也已固定。

但 v3 新增的 fast pre-mutation 语义门与样本 provenance 仍存在两个会改变实现结构的缺口。它们不能留给 SPEC 自行选择，因此当前仍不批准。

## v1 Finding Closure

| v1 Finding | v3 evidence | Result |
|---|---|---|
| I-1 三样本被弱化 | 第 107–109 行要求三个不同 work ID、archived、strict、完整 role blocks，并覆盖不同 task count/change shape | Closed |
| I-2 metrics 测量来源不闭合 | 第 63–67 行区分 controller/role producer、ordered verification records、direct/semantic 两种 byte kind 与 unavailable | Closed |
| I-3 profile/resume 未决 | 第 97–103 行确定 strict 默认、fast 不自动降级、resume 参数矩阵、legacy strict、单向 escalation 与 BASE selector | Closed |
| I-4 父目录竞态 | 第 75–79、87 行引入稳定 directory fd、relative no-follow read、同-handle run 校验与 parent replacement tests | Closed；精确错误语义见新 Minor N-M1 |
| I-5 跨平台表面缺失 | 第 93、113–117 行列出五个 continue surfaces、两套完整 execute surfaces、OpenCode 派生和 Gemini 精简入口 | Closed |
| M-1 JSON/byte invariant | 第 81–83、87 行给出 per-source/aggregate 公式、完整 success/error shape 和 golden cases | Closed |
| M-2 `⚠️ DEFER` 归属 | 第 69、85 行要求任意角色持久化并 inline 上报，fast/strict final 分别消费 | Closed |

## Critical

无。

## Important

### N-I1 — agent surface 无法在“不调用 wrapper”时产生 CLI exit 6，direct wrapper 又能绕过语义门

**证据**

- DESIGN 第 97 行要求 agent surface 在任何 execution mutation 前完成完整 PLAN 的语义 eligibility，并在失败时“返回 exit 6 conflict”，同时“不调用 execute-start”。
- 当前 `tools/r2p-execute` 只是把参数直接 exec 到 `agent_shortcuts execute`；真正的进程 exit code 只能由 wrapper/CLI 产生。Agent prompt 自己可以停止并输出文字，但不能让一个未调用的进程返回 exit 6。
- 若 agent 判断合格后直接调用 `r2p-execute --profile fast`，shortcut 只能复核 tier/modifier 结构门；直接从终端调用同一 wrapper 则可完全绕过 agent 的语义门，让一个结构合格但语义高风险的 PLAN 进入 fast。
- 当前 `_cmd_execute` 的 closed 路径一旦调用 `run-execute-start` 就写 ledger 并把 run 变为 EXECUTING；没有“只返回待语义审查且不 mutation”的 handshake 状态。

**影响**

实现者必须在“agent 文字级 fail closed”与“CLI 可观察 exit 6 / direct-wrapper fail closed”之间自行选一个，验收 7 的“不满足 fast 全部条件无法进入 fast”也无法在现有单次 wrapper 协议下同时对 agent 与直接 CLI 成立。

**建议**

在 DESIGN 选择一个明确协议。推荐两步 handshake：

1. closed run 的首次 `r2p-execute --profile fast` 只做 deterministic structure check，成功后返回 `stop: fast_profile_review`、PLAN path 和 tier，绝不调用 `run-execute-start`；
2. agent 完成语义审查后，合格时调用显式确认入口（例如同 wrapper 的 `--confirm-fast-eligible`）才 mutation；不合格时调用一个无 mutation 的 reject/result 路径以稳定返回 exit 6，或明确规定这里只是 agent-level blocked response、不是进程 exit code；
3. internal CLI 继续验证结构门和确认参数，测试证明首次 fast 调用、reject、confirm 前都不创建 progress/metrics、不改 run status；
4. 明确直接 wrapper 是可信人工确认边界，或让它也必须经历同一两步协议。不能同时声称 agent 不调用 wrapper又要求 wrapper exit 6。

### N-I2 — `source_revision` 和 `change_shape` 的生产时点/命名空间未定义，三样本 ancestry gate 不可移植

**证据**

- DESIGN 第 63 行把 `source_revision`、`change_shape` 放在 metrics header；第 107 行要求 `git merge-base --is-ancestor <Phase-1-head> <sample-source-revision>`。
- 当前安装 manifest 只记录 `r2p_version` 和 installer `schema_version`，没有 r2p 源提交；发布/npm 安装目录也不保证存在可参与本开发仓库 ancestry 的 `.git` 历史。
- 若 `source_revision` 取样本目标项目的 execution BASE，它与 `req-to-plan` 的 Phase-1-head 通常属于不同 Git 仓库，`merge-base` 必然不能证明 instrumentation 版本。
- `change_shape` 声称由 changed-file 类别确定，但 metrics header 在 `run-execute-start` 时创建，此时实际 changed files 尚未产生；v3 没有决定它是 PLAN Files 的预测值、最终 diff 的实测值，还是可由 controller 后补的 header 字段。

**影响**

同一 instrumentation 的合法跨项目样本可能全部被 ancestry gate 拒绝；反之若 source revision 只是目标仓库 SHA，则不能证明样本使用 Phase 0/1 协议。`change_shape` 在不同实现中也可能一开始预测、结束后重写或永久 unavailable，破坏代表性判定。

**建议**

先决定样本范围并固定 provenance：

- 若 Phase 3 证据只允许来自当前 `req-to-plan` 开发仓库，明确写出这一限制，定义 `source_revision = sample run 的 Execution BASE`，并说明三个样本必须在 Phase-1-head 的后代分支/worktree执行；
- 若允许一般项目，删除跨仓库 Git ancestry，改用由安装/构建明确提供的 `instrumentation_schema` + `r2p_version`（必要时增加可验证的 build/source id，且定义无 Git 安装的值）判断能力版本；
- `change_shape` 应在 start 时为 `unavailable`，final reviewer 完成后由 controller 根据最终 execution-base→HEAD changed files 按固定分类函数一次性 finalize；Phase 3 只接受已 finalised 的 archived metrics。若设计要用 PLAN Files 预测值，应改名为 `planned_change_shape`，不能与实测类别混用。

## Minor

### N-M1 — directory-fd 方案的“安全继续”与“父组件替换时报 conflict”表述冲突

第 77 行正确说明父组件替换不会改变已打开 fd 指向的 inode，也不会把读取导向 workspace 外；第 79、87 行又要求任何 parent replacement 都返回 conflict 并测试。仅凭 pinned fd 并不能可靠证明路径曾被替换后又换回；而安全性本身也不要求失败。请决定：要么规定始终从 pinned tree 安全完成，不承诺检测父路径变化；要么增加可检测的 before/after directory identity check，并把保证限定为“检测到 identity drift 时 conflict”。新的 relative read 还应继承现有 helper 的 `O_NONBLOCK`，避免 raced-in FIFO 在 `fstat` 前阻塞，并用 relative pre-stat/open/fstat identity 检查兑现 final-component race 语义。

### N-M2 — role elapsed 应使用 monotonic clock

第 65 行要求 verification 用 monotonic clock，但 controller role elapsed 写成 wall clock。`started_at`/`ended_at` 应使用 wall-clock timestamp 便于审计，`elapsed_seconds` 应由单调时钟差产生，避免系统时间校正导致负值或异常跳变；无法获得时写 unavailable。

## Ambiguity / Architecture / Deferral Conclusion

- 除 N-I1、N-I2 外，未发现新的 unresolved ambiguity 或 undecided product choice。
- 四 Phase 与现有 prompt-driven orchestration、ledger/archive gate、CLI/agent 分层兼容；strict safety 语义未被削弱。
- 未发现未锚定 deferral。Phase 3 在证据不足时保持本 run 未完成并返回 `BLOCKED`，是原始需求声明的入口条件，不是把 in-scope 工作移到未来 run；但样本收集与恢复操作应在 PLAN 中写成可执行 checkpoint。

## Approval Condition

修订 DESIGN，解决 N-I1、N-I2，并收紧 N-M1、N-M2 后可批准进入 SPEC。
