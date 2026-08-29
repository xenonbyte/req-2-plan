# SPEC 强制独立评审 v1

Verdict: Changes Requested

## Review Scope

已完整阅读 `06-spec.md`，并交叉核对同 run 的 `03-requirement-brief.md`、`04-risk-discovery.md`、已批准 `05-design.md` v4，以及当前仓库的 execute surfaces、`_cmd_execute`、`_cmd_run_execute_start`、`read_regular_text`/`atomic_write_text`、ledger/archive gates、install/OpenCode 派生和 docs-consistency tests。

SPEC 对 DESIGN v4 的主干覆盖良好：fast 两步 handshake、profile/resume、directory-fd、context human/JSON、compact reports、跨平台 parity 和四个 PLAN slices 都已落位。以下问题仍会让 Phase 3 在无可比较数据时通过、让 metrics/classifier 无唯一实现，或让中断恢复进入自相矛盾状态，因此当前不能批准进入 PLAN。

## Critical

无。

## Important

### I-1 — 代表性样本允许所有性能字段为 `unavailable`，不能支撑 Phase 3 决策

**证据**

- `SPEC-SAMPLE-003` 第 37 行允许每个 role block 的 started/ended/elapsed、context bytes、verification records/total、report bytes 和 Token 全部为 measured 或 `unavailable`。
- 同一 checkpoint 第 33–38 行只强制 archived/profile/schema/finalized/shape/task/role coverage；因此三份只有空壳 role blocks、所有性能字段均 unavailable 的 run 仍可通过。
- Requirement Brief acceptance 3 要求每个角色调用可审计 elapsed、实际 context bytes、verification scope/duration 和 output size；Token 才是“平台真实暴露时记录”的可选项。
- PLAN handoff 的 Phase 3 需要根据这些样本决定/验收 fast，但第 40 行的 task report 只固化 metadata/completeness，没有要求输出任何可比较的 per-run aggregate。

**影响**

Phase 3 可以在没有角色耗时、上下文大小、测试耗时或报告体积的情况下实现，直接破坏 RISK-METRIC-003、RISK-SEQUENCE-012 和本次优化的证据基础。

**具体修订建议**

把 sample eligibility 分成 required measured 与 optional：

- 每个实际 invocation 必须有 measured `started_at`、`ended_at`、`elapsed_seconds`、`context_bytes`、`report_bytes`、非空 ordered `verification_records` 和 measured `verification_total_seconds`；这些字段任一 unavailable 则整个 sample 不合格。
- `model` 与 Token 三字段允许 unavailable；Token unavailable 不影响资格，但报告必须显式说明不能比较 Token。
- context mode/kind 必须成对匹配，且每条 verification record 的 duration/status 都是 measured；total 必须按规定精度等于 records 之和。
- Phase 3 evidence report 必须按 run 汇总 invocation count、role elapsed total、context bytes total、verification total、report bytes total、full-suite count/duration，以及可得时的 Token totals，并标明 Phase 0/1 前后口径差异；不能只列“complete”。

### I-2 — metrics invocation block 仍不是可解析的完整语法，“有效/合法”没有定义

**证据**

- `SPEC-METRICS-009` 第 105–127 行把 `verification_records` 写成 `<ordered records>`、`status` 写成 `<role return status>`、`concerns` 写成“concise items”，没有规定 Markdown/JSON 编码、转义、列表边界或 parser grammar。
- `SPEC-SAMPLE-003` 第 37 行要求“有效 role/task/status”，但没有给 role→task/status 的合法矩阵。
- `verification_total_seconds` 没有规定 unavailable 传播、decimal 精度和求和规则；`fix_wave` 对 implementer、首次 reviewer、fixer/re-review、final waves 的取值也未定义。
- Phase 3 要检查 sequence-contiguous blocks、隐藏 fix-wave 证据和 completeness；测试矩阵还要求验证 header/role schema，因此这些不是纯展示字段。

**影响**

不同实现可生成彼此不兼容的 Markdown，sample reviewer 无法确定什么是合法 block，`unavailable`/空列表/多命令/带换行 command 的处理也会漂移。

**具体修订建议**

在 SPEC 中给出一份逐字可解析 grammar。推荐每个 scalar 使用单行，复杂字段使用单行 JSON：

```text
verification_records_json: [{"command":"...","scope":"targeted|directly_affected|full_suite","reason":"...","elapsed_seconds":0.0,"status":"passed|failed"}]
concerns_json: []
```

同时固定：

- implementer/fixer/final_fixer status 集与 reviewer/re-reviewer/final-reviewer status 集；
- task roles 的 `task=<positive PLAN number>`，final roles 的 `task=final`；
- `fix_wave=0` 适用于 implementer/首次 reviewer/final reviewer，fixer 与对应 re-review 使用从 1 开始的同一 wave；
- JSON 必须 UTF-8、单行、无 NaN/Infinity；字符串通过 JSON 转义；records 非空；
- total 由 controller 对 measured record durations 求和并按固定精度序列化，任一 record unavailable 时 total unavailable；
- `context_mode` 与 `context_bytes_kind` 的唯一合法配对。

### I-3 — change classifier 通过“与 DESIGN v4 完全一致”引用上游，且 test-only 分支存在空集歧义

**证据**

- `SPEC-METRICS-009` 第 131 行没有复述算法，只说 classifier 与 DESIGN v4 完全一致，并列出若干类别名。这不满足 SPEC 自包含要求。
- DESIGN/SPEC 的优先顺序先判断“没有 source 且全部非测试路径为文档/配置”，后判断“只有测试”。若 non-test set 为空，常见 `all([])` 实现会先把 test-only 错分为 docs_only 或 config_only。
- 没有规定 final diff 的 path 提取命令/格式、rename 使用 old/new/both、deleted file 如何计入、路径分隔/大小写、`migration` 是完整 component 还是 substring、glob 是否 case-sensitive。
- `SPEC-SAMPLE-003` 把 finalized shape 当代表性 gate，因此 classifier 必须可复现，不能靠实现者解释。

**影响**

相同 diff 可产生不同 shape，三样本 diversity gate 会因实现细节得到不同结论。

**具体修订建议**

把完整算法写入 SPEC，而不是引用 DESIGN：

1. 用明确命令（建议 `git diff --name-status -z <Execution BASE> HEAD`）取得 changed paths；定义 add/modify/delete/rename/copy 分别采用哪些 path。
2. 统一转为 repo-relative POSIX path；明确 component、basename、suffix/glob 均区分大小写。
3. 明确 migration 仅在某个完整 component 等于 `migration`/`migrations` 时命中。
4. 先分出 test paths；若全部 paths 都是 test，立即返回 `test_only`，避免空集真值。
5. non-test 非空后再判断 docs_only/config_only；随后计算 source top-level modules；混合文档/配置且无 source 返回 mixed。
6. 对 rename/delete、root-level source、docs+tests、config+tests、docs+config、migration test path 写 table tests。

### I-4 — fast final approval 的 marker/checkbox 迁移不是原子的，现有连续性规则会阻断崩溃恢复

**证据**

- `SPEC-RESUME-006` 第 63 行要求 implemented markers 必须从 Task 1 起连续。
- 第 65 行要求 final approval “将每个 implemented marker 替换”为 complete 后才置 `[x]`，但未要求一次原子重写整个 ledger。
- 若 controller 先转换 Task 1 后中断，ledger 会出现 Task 1 `[x]` + complete marker、Task 2..N `[ ]` + implemented markers。剩余 implemented markers 不再“从 Task 1 起连续”，下一次 resume 会按第 62/63 行判 conflict。
- `SPEC-LEDGER-014` 的精确 grammar 也没有给出这种合法的 approval-in-progress 状态；当前 `atomic_write_text` 只能在调用者构造完整新内容后保证单文件原子替换。

**影响**

一次正常 crash 可以把已通过 primary final review 的 fast run 变成无法自动恢复的 ledger，违反 SCOPE-IN-009 和 RISK-RESUME-009。

**具体修订建议**

要求 controller 在内存中构造完整新 ledger，一次 `atomic_write_text(progress.md, full_text)` 同时完成所有 implemented→complete marker 和 `[ ]`→`[x]` 迁移；不得逐 task 写盘。写前重新验证 HEAD/marker chain 未变化。若原子替换前失败，旧 fast ledger 完整保留；替换后失败，全部 tasks 已是 strict-compatible complete，final-review gate 仍阻止未写 verdict 的 archive。补充 crash-before-replace、replace-after-crash、all-checked-but-final-review-missing 的 resume tests。

### I-5 — `run-execute-start` 的双 ledger seed/状态迁移缺少事务和重试恢复契约

**证据**

- `SPEC-METRICS-009` 第 90 行说“原子生成 progress.md 和 metrics.md”，但没有说明是各文件单独原子还是 progress+metrics+run status 的整体事务。
- 当前 `_cmd_run_execute_start` 先写 progress，再把 run 保存为 EXECUTING；引入 metrics 后会增加一个中间失败点。若 metrics 或 run save 失败，closed run 可能残留一份 ledger；重试时如何处理未定义。
- SPEC 只说 resume 不覆盖 metrics，没有定义 closed run 遇到零个/一个/两个既存 target、空 execution dir、symlink target或内容不匹配时的行为。
- DESIGN v4 还要求当前自举执行在旧代码未 seed metrics 时由 controller 创建 header，SPEC 与 PLAN handoff 未编码该 bootstrap 分支。

**影响**

异常或中断可能制造 closed status + partial execution files；后续 strict/fast handshake 的“零 mutation”快照与首次启动不再有唯一恢复行为。

**具体修订建议**

明确一个可实现的事务协议，例如：在 run dir 下创建并完全写好唯一临时 execution directory，校验后原子 rename 为 `execution/`，最后保存 EXECUTING status；若 status save 抛错则回滚刚安装的 execution dir。对 crash 后出现 closed + 完整 initial ledgers，重试必须校验内容与 PLAN/profile 完全一致后完成 status transition；任何 partial/mismatched/symlinked target exit 6，不覆盖。分别测试 progress write、metrics write、directory install、status save 的 fault injection。另为当前自举 run 明确：已有 legacy progress 且 metrics 缺失时，controller 仅在 profile 可确定为 strict、work/task count 匹配且目标非 symlink时创建 schema header；否则 BLOCKED。

### I-6 — “fresh/minimal-history 等价能力”仍是平台行为的未决占位词

**证据**

- `SPEC-ROLE-002` 第 25 行只写 Claude/OpenCode 使用“fresh/minimal-history 等价能力”，正是本轮要求排查的未定义等价措辞。
- 没有说明什么条件算 fresh、是否允许继承 controller 对话、平台没有显式 history-control 参数时是继续还是 fail。
- 第 26 行虽规定 handoff 自包含，但不能证明目标会话没有继承历史。

**影响**

Phase 0 的零历史收益在 Codex 外无法审计，不同 surface 可以用完全不同的继承语义却都声称合规。

**具体修订建议**

固定平台无关判据：每次 role 必须创建全新 child/subagent invocation；不得复用任何先前 role thread/session；handoff 只包含第 26 行列出的自包含字段；若平台支持 history 参数，必须设置为零 inherited turns/messages；若平台不支持且不能保证新会话不继承 controller history，则 fail explicitly。Claude/OpenCode/Gemini surface 分别声明其可表达的调用方式或明确“不支持即失败”，不要再使用“等价能力”作为验收文本。

## Minor

### M-1 — marker/event grammar 需要补齐字符级约束

`SPEC-LEDGER-014` 第 202–212 行列了行形，但仍应明确 `N` 是无前导零的正十进制任务号、SHA 恰为 `[0-9a-f]{7}`、reason 拒绝 `\r`/`\n` 且 trim 后非空、每个 task 最多一条 complete/implemented marker。解析必须 fence-aware/comment-aware，与现有 ledger checkbox 扫描保持一致。否则“malformed reason/合法 marker”仍依赖 regex 选择。

### M-2 — sample evidence path 的可信读取边界未说明

`SPEC-SAMPLE-003` 接受用户指定的任意本地 archived directories，但没有说明 canonical path/work ID 防重复算法和 symlink/non-regular 处理。建议要求 canonical run paths 两两不同且 basename 等于 validated WorkId；run/PLAN/progress/metrics/final-review 均以 no-follow regular-file read，archive dir 自身不得为 symlink。读取失败只使 sample 不合格，不修改任何目标 run。

## Confirmed Complete Areas

- Fast handshake closed/executing 参数矩阵、confirm/reject trust boundary和失败零 mutation目标清楚。
- Directory-fd traversal、`O_NONBLOCK`、relative pre-stat/open/fstat、pinned-parent semantics 与 fd cleanup 自包含。
- Context-view source 顺序、filter/byte 公式、human/JSON success/error keys、exit codes 和 no-partial-output 充分。
- Strict/fast final inputs、fast primary review、full suite、final fixer/re-review metrics 和 archive gates 均覆盖。
- Claude/Codex/OpenCode/Gemini 与五个 continue surfaces 的 parity 范围完整。
- PLAN handoff 明确形成 Phase 0–3 四个 cohesive slices，没有把任一 phase 移出当前需求。

## Ambiguity / Deferral Conclusion

- I-2、I-3、I-4、I-5、I-6 仍是会改变实现/恢复行为的 unresolved ambiguity；`Decision Requests` 虽无用户产品选择，但 SPEC 尚未 decision-complete。
- 未发现未锚定 scope deferral。Phase 3 在代表性证据不足时保持当前 task 未完成并返回 `BLOCKED`，属于上游明确 prerequisite，不是“以后再做/本轮跳过”。

## Approval Condition

修订 SPEC，解决 I-1..I-6，并补齐 M-1/M-2 后再进入 PLAN。
