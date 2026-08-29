# SPEC 最终聚焦强制独立评审 v7

Verdict: Approved

## Review Scope

聚焦复审 `06-spec.md` v7，并逐项核对 `spec-subagent-review-v6.md` 的 N-I1-R1、N-I2-R1、N-M1；同时检查修订对九任务 Phase ownership、旧 PLAN 兼容、no-clobber trust boundary 和 validator evidence contract 的影响。未修改阶段产物或源码。

## Finding Closure

### N-I1-R1 — Closed

- Implementation v1 + requested semantics 1：执行 strict-only v1，返回 `implementation_version:1`、`semantics_version:1`；requested 2 固定 exit 6、zero mutation。
- Implementation v2 + requested semantics 1：继续执行旧 strict semantics，返回 `implementation_version:2`、`semantics_version:1`、`effective_profile:"strict"`；旧已生成 PLAN 保持兼容。
- Implementation v2 + requested semantics 2：调用完整 effective-profile/task-state parser，返回 `implementation_version:2`、`semantics_version:2` 与实际 effective profile；strict、fast、fast→strict recovery satisfaction matrix 均保持原合同。
- 当前 self-hosted run 的 Task003–009 固定请求 version 1，因此 Task009 自身在升级前仍有可执行 preflight；升级后的 command也能继续接受该旧请求。
- Task007 明确静态更新五个 continue/PLAN-author surfaces 为 version 1；Task009 在同一个 modify task 中再次更新并测试同五面为 version 2，不依赖运行时探测或 LLM选择。PLAN Handoff已同步Task009 ownership。

四格 capability/semantics/exit/JSON矩阵和surface adoption时点唯一，Phase2可独立交付strict-compatible规则，Phase3完成后新PLAN确定生成v2 preflight。

### N-I2-R1 — Closed

- Temp fd从`O_EXCL` create起保持打开；write/fsync后以open-fd `fstat`保存regular mode/dev/ino，再用no-follow temp lstat做pre-link identity验证。
- `os.link` success后，在temp fd仍打开时对temp name和`metrics.md`分别no-follow lstat；open-fd fstat、temp lstat、final lstat必须三方匹配同一saved regular inode后才接受。
- Pre-link temp unlink/regular replacement/symlink replacement，以及post-link final-name replacement都会因missing/type/dev/ino mismatch exit 6；协议不读取、不接受或删除mismatched final。
- 三方通过后才fsync directory、按saved identity unlink本invocation temp、再次fsync并close；缺少所需dir-fd/link/lstat/fsync能力时fail closed，绝不退化为replace。
- Test Matrix已覆盖source/final replacement、三方identity、EEXIST、abandoned temp和各crash point。

该协议同时证明destination no-replace和published inode provenance，v6指出的TOCTOU已闭合。

### N-M1 — Closed

- 0/少于/多于三次参数统一产生唯一`argument_count` detail，使用固定`sample_dir="invocation"`、`work_id="unavailable"`，且该分支不读取路径。
- Canonical duplicate对首项不报错，对每个后续重复项按input order生成`identity_unique` failure，并固定使用原始absolute argument及parsed/unavailable work ID。
- Aggregate diversity failure固定使用`sample_dir="aggregate"`、unavailable work ID和`aggregate_representative`。
- 其余details按input order再按九个rule order稳定排列；schema仍禁止正文、raw blocks和额外keys。Test Matrix明确覆盖0/2/3/4 argument counts和duplicate ordering。

Failure JSON现在能无歧义表达所有声明的blocked分支。

## Consistency Check

- Task001/002 legacy preflight → Task002 checker v1 → Task003–009 requested v1 → Task009 implementation/surfaces v2 的执行链完整。
- `2 / 4 / 1 / 2` operation-homogeneous布局、Steps-only prerequisite、group-only rollback和PLAN schema/gates保持不变。
- Validator success schema仍包含Task008所需全部per-run aggregates；Task008只消费`execution/phase-3-sample-evidence.json`，不二次读取样本。
- Self-host metrics canonical gap、existing-header retry/resume、Task003+ blocks和future complete instrumentation未发生漂移。
- Context helper ownership、wrapper顺序、strict/fast ledger/BASE/final-review契约未产生新冲突。

## Critical

无。

## Important

无。

## Minor

无。

## Ambiguity Conclusion

未发现 unresolved ambiguity / undecided point；未引入新的无法执行命令、未锚定deferral、范围漂移、第三profile或远程mutation授权。SPEC v7可进入PLAN修订。
