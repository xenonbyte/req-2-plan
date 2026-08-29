# DESIGN 强制评审 v1

Verdict: Changes Requested

## Review Scope

已完整阅读并交叉核对：

- `02-project-context.md`
- `03-requirement-brief.md`
- `04-risk-discovery.md`
- `05-design.md`
- `00-raw-requirement.md` 与 `run.md`（用于核对原始进入条件和当前 tier）
- 当前 `r2p-execute` Codex/Claude/Gemini surfaces
- `tools/workflow_cli/cli.py::_cmd_run_execute_start`
- `tools/workflow_cli/agent_shortcuts.py::_cmd_execute` / `_build_parser`
- `tools/workflow_cli/atomic.py::read_regular_text`
- `tools/workflow_cli/cli.py::_reject_symlinked_run_paths`
- `tools/workflow_cli/install.py` 的 wrapper glob、Claude/Codex/Gemini/OpenCode 安装路径
- `tools/workflow_cli/stage_templates.py` 与 `tests/test_docs_consistency.py` 的现有表面约束

总体上，DESIGN 对 SCOPE-IN-001..010 和 RISK-PERF-001..RISK-SEQUENCE-012 都建立了显式 coverage，四个 Phase 的架构落点与“CLI 管状态/结构、agent 管语义和执行编排”的现有边界基本兼容；dirty-tree、逐任务 commit/diff、Execution BASE、final whole-branch review、final full suite、final verdict 和 archive gate 也都保留。未发现未锚定 deferral，`Decision Requests: none` 本身也没有隐藏的用户产品选择。

但以下 Important 问题会让 Phase 3 在证据不足时进入，或让 metrics / resume / I/O 安全无法按当前文字确定实现，因此本版本不能批准进入 SPEC。

## Critical

无。

## Important

### I-1 — “3 个代表性执行样本”被弱化为同一执行中的 3 条角色记录

**证据**

- 原始需求第 15 行要求 Phase 3 只能在“至少收集 3 个具有代表性的执行样本”后进入实现决策与验收。
- Requirement Brief 的 Assumptions 进一步要求代表性样本覆盖“不同任务数量或变更形态”。
- DESIGN 第 97 行却把入口改成 `metrics.md` 中至少 3 条角色 block、覆盖至少两个 task number，并包含 implementer/task-reviewer。三个角色调用可以全部来自同一个 run、同一种变更形态，并不等价于三个代表性执行样本。
- DESIGN 第 12、61 行还假设“当前执行”能自举产生这些记录；但仓库模板修改不会自动更新当前已加载的 installed skill，DESIGN 第 114 行自己也承认源模板不会自动覆盖 agent home。仅创建 metrics header 不能让旧 controller 自动执行新采集协议。

**影响**

Phase 3 可能只凭一个 run 的少量角色调用就通过前置条件，无法比较 Phase 0/1 在不同任务规模或变更形态下的收益，也无法证明 fast 值得引入。当前单一执行自举还可能根本拿不到格式完整且可信的 Phase 0/1 数据。

**建议**

把“样本”定义为完成 final review 的独立 execution run，而不是 role block。至少要求 3 个 run，覆盖不少于两种 task count 或 change shape；每个 run 的 metrics 必须同时包含 implementer、task reviewer 和 final reviewer 的完整记录，并标明采样所用 r2p 版本/阶段能力。Phase 3 应作为独立后续 r2p run，或在本 run 中设置一个明确的人工证据 checkpoint，在外部三个真实 run 完成前不得实现；不能靠当前执行内三条记录自举通过。若产品意图确实只是三条角色记录，必须先回到 Requirement Brief 修改上游要求。

### I-2 — metrics 的两个核心值没有可执行的测量来源

**证据**

- DESIGN 第 63–65 行要求 controller 写 `verification_elapsed_seconds` 和“实际交付”的 `context_bytes`，并说角色返回后由 controller 读取“验证摘要”。
- 当前 implementer/reviewer inline contract 只有 `test_summary`，report 最低合同只有命令和结果；controller 看不到子代理内部测试命令的开始/结束时间，不能从整个角色 elapsed 推导 verification elapsed。
- Phase 0 仍是角色自行读取六个 ACS 文件，不存在 controller 真正“handed”的单一 payload。文件大小之和、角色实际打开的字节数、工具分块读取产生的传输字节数是三个不同口径。
- `verification_command` 是单值，但一个角色可以运行多个 targeted/directly affected 命令并在触发后再运行 full suite；当前设计未决定如何记录多命令及其总耗时。

**影响**

不同 controller/platform 会写出不可比较的数字，三样本门可能接受推算值或把 role elapsed 错当 test elapsed，违反 RISK-METRIC-003 和验收标准 3。

**建议**

在 DESIGN 中固定数据生产者和口径：

1. controller 只测 role `started_at`/`ended_at`/`elapsed_seconds` 与 report bytes；
2. role 必须用单调时钟包围每条 verification 命令，并在固定结构中回传/落盘 `command`、`scope`、`reason`、`elapsed_seconds`、`status`；metrics 将 verification 记录为有序列表并另给 total；
3. Phase 0 的 `context_mode=direct_acs` 明确定义为模板要求角色完整读取的六个 source 的 UTF-8 raw byte 总和，并标注为 `declared_payload_bytes`，不得称工具层真实 consumed bytes；
4. Phase 1 的 `context_mode=semantic_view` 才直接使用 context-view JSON 的 aggregate `semantic_bytes` 作为 handed payload bytes；
5. 任一字段无法观测时写 `unavailable`，不得由其他时间或历史快照推算。

### I-3 — profile 首次选择、resume 冲突和 fast 拒绝行为仍是未决契约

**证据**

- DESIGN 第 89 行决定首次省略 profile 为 strict，但“语义门失败”时又说把有效 profile 记成 strict 并继续，没有决定显式 `--profile fast` 被拒绝时是 conflict、停止等待用户，还是自动降级并执行 strict。
- DESIGN 第 131 行把“executing resume 参数冲突行为”留给 SPEC，却没有在 Chosen Design 中决定：resume 不带参数、带相同参数、带不同参数分别如何处理。
- 未决定 legacy executing ledger 缺少 `Execution Profile:` 时是否确定性解释为 strict。
- escalation 文本 `strict (escalated from fast: <reason>)` 只是一段展示文案，未决定它是否替换唯一 profile 行、追加事件行，或如何被 resume parser 解析。
- 当前 `_cmd_execute` 的 resume 路径固定为 first unchecked task，shortcut parser 也只接受 `--work-id`；这些都是 Phase 3 必须一次性替换并兼容旧 ledger 的机器/提示消费点。

**影响**

相同 ledger 可能因调用参数不同而产生不同执行拓扑；自动降级还可能在用户明确选择 fast 后未经确认执行 strict 的额外 reviewer 成本。恢复实现没有唯一可测试结果。

**建议**

在 DESIGN 直接做出以下决定，而不是交给 SPEC：首次 closed run 无参数写 strict；显式 fast 任一资格门失败都在 task dispatch 前返回 conflict 并说明原因；executing resume 无参数复用 ledger profile、相同参数幂等接受、不同参数 conflict；legacy ledger 缺 profile 行按 strict 解释；fast 运行中触发风险时允许自动升级且不可降回 fast，并用一个不可变初始 profile 行加有序 `Profile Escalation:` 事件记录，resume 取最后有效状态。然后让 SPEC 只编码该决定。

### I-4 — context-view 的目录路径竞态没有被现有 helper 覆盖

**证据**

- DESIGN 第 73 行承诺 workspace/run 先拒绝 symlink，再由每个 source 走 `read_regular_text`，并声称 symlink/non-regular/race fail closed。
- 当前 `read_regular_text` 的文档和实现只保证“不跟随 final-component symlink”，通过 file `lstat` → `open(O_NOFOLLOW)` → `fstat` 检查最终文件身份。
- 当前 `_reject_symlinked_run_paths` 对 `.req-to-plan` 和 run dir 仅调用 `Path.is_symlink()` 后返回普通 path；目录检查与后续逐文件 open 不是同一个稳定目录句柄。并发替换父目录后，`O_NOFOLLOW` 不会阻止路径中的父组件指向 workspace 外。

**影响**

设计承诺的 raced-path fail-closed 比当前复用原语实际提供的保证更强。按现设计实现，最终文件 race 会被拦截，但 workspace/run 父目录 race 仍可越界读取，与 RISK-IO-004 不一致。

**建议**

选择并写明一种实现：优先在打开并校验 workspace/run directory fd 后，使用相对该稳定 dir fd 的 `open(..., dir_fd=..., O_NOFOLLOW)` 读取所有固定 source，并对 run identity 做同一目录句柄下的校验；不支持该能力的平台 fail closed。若本需求只打算覆盖 final source identity race，则必须回到 Requirement Brief 明确缩小“raced input”承诺，不能在 DESIGN 中笼统声称所有路径 race 都 fail closed。

### I-5 — Phase 2 的平台表面清单不完整

**证据**

- DESIGN 第 85 行只点名 `stage_templates.py`、Claude/Codex `r2p-continue` 和一致性测试。
- 当前 `tests/test_docs_consistency.py` 的 continue surface 集合实际上包含四处：Claude 通用 `SKILL.md`、Claude `commands/r2p-continue.md`、Codex `r2p-continue/SKILL.md`、Gemini `r2p-continue.toml`。
- OpenCode 从 Claude command 派生，需要安装派生结果测试而不是独立编辑；Gemini 的 description 是它唯一可表达的阶段指导面。
- DESIGN 第 101 行只为 execute/profile 更新 Gemini description，没有明确 Phase 2 的 cohesive-slice 规则也进入 Gemini continue description；也没有明确 Claude 通用 `SKILL.md`。

**影响**

Phase 2 可能在 Claude/Codex 某些入口生效、在 Gemini 或 Claude 通用 skill 入口缺失，RISK-PARITY-011 仍未完全关闭。

**建议**

把 Phase 2 同步矩阵明确列为：`stage_templates.py`、Claude 通用 `SKILL.md`、Claude continue command、Codex continue skill、Gemini continue description；OpenCode 不手改，但安装后断言其派生 command 含同一 cohesive-slice 规则。Phase 0/1/3 的 execute 矩阵也应明确区分“完整协议面（Claude/Codex）”和“wrapper 指针/description 面（Gemini/OpenCode 派生）”。

## Minor

### M-1 — context-view byte/JSON invariant 还差一个精确定义

**证据**

- DESIGN 第 75 行先说每个 source 过滤后 `rstrip()`，随后把 per-source `semantic_bytes` 描述为“过滤后”字节；未明确它是 `rstrip()` 前还是后的值。
- aggregate `raw_bytes` 不包含分隔符，而 aggregate `semantic_bytes` 包含固定分隔符和尾随换行；这是可行设计，但应明确说明 aggregate 不等于 per-source semantic bytes 之和。
- “使用现有 success envelope”没有列出 JSON 顶层 `status`/`message` 是否属于稳定 schema；human stdout 又要求只含 content，不能直接复用 `format_success` 的 human 文案。

**建议**

固定公式：per-source semantic bytes 为 `strip_nonsemantic_markdown(raw).rstrip().encode("utf-8")`；aggregate semantic bytes 为最终拼装 content 的 UTF-8 长度，因此显式包含所有 separator 与唯一尾随换行。列出 JSON 完整顶层 keys/类型及失败 envelope；human 成功路径直接输出 content，不附加成功提示。对 Unicode、空白-only source、HTML comments、fence、缺失 source 和 no-partial-output 写 golden tests。

### M-2 — compact review 的 `⚠️ DEFER` 归属应统一

**证据**

- DESIGN 第 79 行说 review “额外保留 Spec/Quality Verdict 和 `⚠️ DEFER`”，容易被实现成只有 review 模板保留该字段。
- fast 不生成 task review，final 只读 reports；若 implementer/report 本身出现不可从 diff 验证的 deferred evidence，仍必须让 fast final 看见。

**建议**

把规则写成：任何角色发现的每条 `⚠️ DEFER` 都必须进入该角色对应的持久 report/review 和 inline `concerns`；fast final 读取所有 task reports 的该字段，strict final 同时读取 reports 和 reviews。不存在时使用显式 `none`，不得省略 section。

## Coverage / Deferral Conclusion

- SCOPE-IN-001..010：均有设计映射，但 SCOPE-IN-003、004、007、009、010 受 I-1..I-5 阻塞，当前不能视为 decision-complete。
- RISK-PERF-001..RISK-SEQUENCE-012：均有 mitigation；RISK-METRIC-003、RISK-IO-004、RISK-CONTRACT-005、RISK-PROFILE-008、RISK-RESUME-009、RISK-PARITY-011、RISK-SEQUENCE-012 仍有上述合同缺口。
- 四个 Phase 的顺序依赖合理，Phase 0/1/2 可各自独立落地；Phase 3 依赖真实多-run 遥测和 Phase 1 context-view，应作为证据满足后的独立切片，不能用同一 run 的三个 role block 代替进入条件。
- 未发现无 SCOPE-OUT 锚点的“以后再做/本轮不做”式 deferral。Phase 3 的数据前置条件来自原始需求，不属于非法 deferral；但必须用可执行 checkpoint 表达。

## Approval Condition

修订 DESIGN 并解决 I-1..I-5 后可重新评审。M-1、M-2 应在进入 SPEC 前一并收紧，以避免把实现选择留给下游。
