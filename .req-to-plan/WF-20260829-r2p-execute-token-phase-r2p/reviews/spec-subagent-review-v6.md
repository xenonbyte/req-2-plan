# SPEC 聚焦强制独立评审 v6

Verdict: Changes Requested

## Review Scope

聚焦复审 `06-spec.md` v6，并逐项对照 `spec-subagent-review-v5.md` 的 N-I1..N-I3；同时核对当前九任务 Phase ownership、现有 PLAN/execute surfaces、`os.link` no-replace 语义和 validator evidence consumption。未修改阶段产物或源码。

v6 已为当前 self-hosted run 给出 Task001/002 legacy preflight、Task002 落地 checker v1、Task003–009 使用 v1 的连续执行路径；也已补齐 hard-link no-replace 的大部分 crash矩阵和 validator nested success schema。以下问题仍使版本升级/安全发布或 exact error contract存在未决实现选择。

## Critical

无。

## Important

### N-I1-R1 — `--require-version` 的兼容语义与 PLAN 生成时版本选择机制未闭合

**证据**

- `SPEC-GRANULARITY-004` 第 74 行规定 v1 command 的 success 返回 `checker_version: 1`；第 76 行规定 Task009 升级为 v2 后仍接受旧 `--require-version 1`，但又统一声明“v2 success ... `checker_version: 2`”。
- 因此 installed v2 + `--require-version 1` 有两个互斥解释：执行 v1 strict semantics并返回1，或由v2实现兼容v1请求但返回actual capability 2。旧 PLAN/JSON assertion 应接受哪一个没有定义。
- 第 74 行说 Phase 2 surfaces 在 v1 environment只生成strict-compatible preflight；第 76 行又说 Phase 3 完成后的新 PLAN surfaces固定要求v2。然而 PLAN Handoff第322行把五个continue/PLAN生成surface全部留在Task007，第323行的Task009只明确修改CLI/shortcut/execute surfaces/tests/docs，没有说明谁、何时、按什么确定性信号把以后生成的 PLAN 从require-version1切到2。
- 若Task007模板静态写v1，Phase3后新PLAN仍不会要求v2；若静态写v2，Phase2独立交付到Task008前生成的PLAN不可执行；若让LLM自行探测，则又缺少capability query和exact selection rule。

**影响**

当前九任务本身可以按 Task001/002 legacy → Task003–009 v1 执行，但 Phase2独立交付、Task009 adoption和未来fast-capable PLAN之间没有稳定握手。实现者必须自行修改额外surfaces或发明版本探测/兼容规则，会改变Phase ownership和JSON contract。

**具体修订要求**

固定完整 capability matrix和PLAN author选择路径：

1. 明确 installed implementation v1/v2 × requested version1/2 的语义、exit和JSON；建议区分 `implementation_version` 与 `semantics_version`，或明确 `checker_version`究竟表示哪一个。
2. 给continue/PLAN author一个确定的只读 capability query，Task007 surfaces按返回值生成require-version1或2；或者把五个continue surfaces的v2 adoption明确加入Task009 Files/Steps/tests。不能只用“v1 environment/v2完成后”描述。
3. 保持当前run Task003–009显式require-version1；future fast PLAN必须require-version2，且v1 capability对其exit6。

### N-I2-R1 — hard-link publish 在 pre-link identity check 后关闭 temp fd，仍有 source-name replacement race

**证据**

- `SPEC-METRICS-009` 第137行要求完整写temp、fsync、close并做fstat/lstat identity，然后按temp文件名调用 `os.link(...)`；文字顺序中的close后fstat本身不可执行，且link使用的是可再次解析的目录项名称，而不是已pin的open fd。
- 在最后一次identity check与`os.link`之间，temp name仍可被unlink/replaced。`follow_symlinks=False`只是不跟随replacement symlink；它会把该symlink本身或replacement regular inode硬链接成 `metrics.md`。
- 第137–139行没有link后的final lstat/fstat与保存temp dev/ino比较，也没有覆盖pre-link source swap的fault/race test。独立flock只排除遵守协议的writer，不能代替filesystem identity check。

**影响**

no-replace保护了destination，却没有证明published inode就是本invocation完整写入的regular temp；安全边界仍可在rename/symlink race下发布foreign final。后续exact content parse不能替代inode/type provenance。

**具体修订要求**

保持temp fd打开到publish验证完成：write/fsync后fstat并保存regular dev/ino；link后相对pinned fd对temp和`metrics.md`做no-follow lstat，并与仍打开fd的fstat identity三方比较，只有全部同一regular inode才接受；然后fsync dir、按identity unlink owned temp。任一pre/post-link mismatch或symlink均exit6且不得消费final。测试补充pre-link temp unlink/regular replacement/symlink replacement，以及link后final-name replacement。若无法用stdlib在目标平台建立该证明则fail closed。

## Minor

### N-M1 — arity failure无法用声明的 exact `FailureDetail` schema表达

**证据**

- 第32行规定少于/多于三份`--sample-dir`时exit3 `representative_metrics_missing`。
- 第61行的`FailureDetail.rule`只允许九个sample rules或`aggregate_representative`，且每项必须有实际`sample_dir:str`；零个、缺少或多余参数没有合法rule，也没有规定details可为空或使用何种sentinel。

**具体修订要求**

增加global `argument_count` rule与固定 `sample_dir`/`work_id` sentinel，或明确该错误的 `details: []`。同时把canonical duplicate如何映射到 `identity_unique` 的稳定item顺序写清即可。

## v5 Finding Closure

| v5 finding | v6 result | Conclusion |
|---|---|---|
| N-I1 prerequisite checker delivery | **部分闭合** | Task001/002 legacy strict matrix、Task002 v1 command、当前Task003–009 v1路径均可执行；v1/v2请求语义和future PLAN版本选择仍有N-I1-R1。 |
| N-I2 bootstrap atomic no-replace | **部分闭合** | lock、unique temp、file fsync、hard-link EEXIST、dir fsync、abandoned-temp和crash矩阵已定义；source-name TOCTOU仍有N-I2-R1。 |
| N-I3 validator schema/aggregates | **主体闭合** | success Sample/Aggregate及所有per-run aggregates已exact，Task008仅消费evidence JSON；failure arity只有N-M1的小缺口。 |

## Confirmed Complete Areas

- 当前run的Task001/002 legacy条件、Task002→Task003 metrics bootstrap切换、Task003–009 checker v1调用不会依赖尚未落地的Phase3 parser。
- Self-host header canonical组合、existing exact header retry、Task003+ contiguous block resume、EEXIST exact-vs-mismatch和abandoned temp不删除策略一致。
- Validator success evidence包含identity/header/coverage/rules、七角色counts、role/verification/report/full-suite totals、按context mode分组bytes和measured/unavailable Token；Task008禁止二次读取样本目录。
- Context helper ownership、wrapper顺序、strict/fast ledger/final review主合同未发生漂移。
- 未发现新的未锚定deferral、第三profile、远程mutation授权或PLAN schema/gate变化。

## Ambiguity Conclusion

仍存在 unresolved ambiguity / undecided point：N-I1-R1 的 checker capability/version handshake与surface adoption ownership，以及N-I2-R1的published inode identity证明。N-M1是局部error-schema缺口。

## Approval Condition

补齐以上两项Important和一项Minor后再做聚焦复审；无需重开九任务布局、validator aggregate口径、context architecture或正常start transaction。
