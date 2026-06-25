# PLAN Review — WF-20260626-r2p-execute-controller-context-manag

**Verdict: Approved with notes**

The machine gate's structural checks pass and the core extraction logic (PLAN-TASK-001) is sound and code-grounded. Three Important findings are skeleton/test-guidance defects that, if implemented literally, ship latent regressions the specified tests would not catch: a broken shortcut exit-code propagation (F1), a non-load-bearing FR-CM4 guard token (F2), and a wrapper-test that can fail locally on the documented missing-pyyaml constraint (F3). No Critical findings; nothing is unimplementable or contradicts a SPEC contract at the prose level.

---

## SPEC Realization

Every SPEC ID is consumed by a task (gate-verified), and the prose Steps cover each contract:

| Task | SPEC | Realization |
|---|---|---|
| PLAN-TASK-001 | SPEC-CLI-001 | EXECUTING guard, EXIT_CONFLICT/NOT_FOUND/CLI_ERR, symlink, atomic write, `format_success` 3-key payload, byte-identical extraction — all present. Sound. |
| PLAN-TASK-002 | SPEC-SURFACE-001 (wrapper) | Wrapper skeleton matches the existing pattern exactly. Sound. |
| PLAN-TASK-003 | SPEC-SURFACE-001 (shortcut + equivalence) | Shortcut + equivalence/delegation tests — **realization weak**: see F1 (exit-code propagation) and F3 (wrapper-test form). |
| PLAN-TASK-004 | SPEC-PROSE-001..004, SPEC-GUARD-001 | Prose Steps cover FR-CM1–CM4; token guard — **weak** on FR-CM4: see F2. |

No SPEC dropped or contradicted at the contract level. The two realization gaps (F1, F2) are in the executable guidance, not the contracts.

---

## Executability / Code-Grounding (per skeleton)

**PLAN-TASK-001 — sound, verified against real code.**
- `plan_task_anchors(plan_text)` returns `[(task_id, title), ...]` — confirmed `markdown.py:139-148` (`m.group(1)` = `PLAN-TASK-NNN`, `m.group(2)` = title). ✓
- `heading_bounded_bodies(plan_text, PLAN_TASK_ANCHOR_RE.match)` yields bodies in document order (`markdown.py:151-178`, iterates `unfenced_markdown_lines` in order). `plan_task_anchors` filters the same lines via the same `PLAN_TASK_ANCHOR_RE` (primary filter); its extra `_PLAN_TASK_ANCHOR_LINE_RE` is a strict superset, so it never drops a line the body-iterator kept. **The `zip(anchors, bodies)` aligns 1:1.** ✓ And resolution is by integer **value** (`int(re.match(r"PLAN-TASK-(\d+)", tid).group(1)) == args.task`), so it is order-independent and correctly handles zero-padding (`int("002") == 2`). Sound. ✓
- `_load_run` (`cli.py:85`), `_reject_symlink_or_exit` (`cli.py:165-167`), `atomic_write_text` (`atomic.py:9`), `format_success` (`output.py:46`), `read_artifact` raising `FileNotFoundError` (`artifact.py:108-117`), `Stage.PLAN`, `strip_readonly_sections` (`markdown.py:62`), and `EXIT_*` constants (`output.py:6-12`) all exist and are used correctly.
- **Byte-identity claim achievable**: the brief uses `strip_readonly_sections(read_artifact(...))` then `heading_bounded_bodies(.., PLAN_TASK_ANCHOR_RE.match)` — the same pipeline `_plan_task_ids`/`_iter_plan_task_bodies` use (`gates.py:1237`, `gates.py:300-301`). Read-only sections are trailing `##`-level blocks after the last `###` task, so stripping never shifts a task's heading-bounded body. ✓

**PLAN-TASK-002 — sound.** The wrapper skeleton is byte-for-byte the established shape: compared to `tools/r2p-status`, only the trailing subcommand differs (`task-brief` vs `status`). Auto-discovered by the `install.py` `glob("tools/r2p-*")` loops. ✓

**PLAN-TASK-003 — defective skeleton (F1).** `_run_cli` exists (`agent_shortcuts.py:190-197`) and returns an `int` exit code (it swallows the CLI's `SystemExit`). But the skeleton's `def _cmd_task_brief(args): return _run_cli(...)` is wrong on two counts:
1. **Signature**: the dispatch calls `handlers[ns.subcommand](ns, bp)` (`agent_shortcuts.py:1108`) — handlers take `(ns, base_path)`, like `_cmd_execute(ns, base_path)` (`agent_shortcuts.py:853`). A one-arg `(args)` handler reading `args.base_path` raises `TypeError` (and `ns` has no `base_path` attr).
2. **Exit-code propagation**: `main()` discards the handler's return value and unconditionally `sys.exit(0)` (`agent_shortcuts.py:1108-1109`). Every existing delegating handler instead captures and re-exits: `exit_code = _run_cli(...); sys.exit(exit_code)` (`agent_shortcuts.py:497-499`, `606-610`, `620-622`, `641-647`). A `return`ed code is silently dropped → `task-brief` **always exits 0**, breaking SPEC-SURFACE-001's "identical exit code as the direct CLI call" on the non-zero paths (6/7). The specified equivalence test exercises only the **happy path** (exit 0), so it would not catch the divergence.

**PLAN-TASK-004 — prose Steps fine; one guard token non-load-bearing (F2).** `REQUIRED_FR_CM_TOKENS` is mostly distinctive and load-bearing (`plan-task-brief`, `task-brief`, `Resolved:`/`Gap:`/`Unresolved:`, `Narration:` are all absent from the templates pre-edit). But `"final whole-branch review"` (the FR-CM4 token) **already exists in both templates pre-edit** — `agent_templates/claude/commands/r2p-execute.md:104` and `agent_templates/codex/skills/r2p-execute/SKILL.md:105` both contain the lowercase phrase "dispatch a final whole-branch review subagent". So that assertion passes even if the FR-CM4 carry-forward prose is never written — it does not guard FR-CM4. This contradicts SPEC-GUARD-001's stated token intent ("the FR-CM4 carry-to-final-review phrasing" + `Minor:`).

---

## Task Ordering / Dependency Soundness

**Acceptable as ordered.** PLAN-TASK-002 (wrapper) precedes PLAN-TASK-003 (the `task-brief` shortcut it delegates to), so the wrapper is non-functional in the 002→003 interim. This is fine because **002's Verification is purely structural** (`test -x`, `grep -q 'agent_shortcuts task-brief'`, suite stays green) — it never executes the wrapper, and nothing else in the suite runs `task-brief` until 003 adds it (`test_install_copies_bin_scripts` only globs/counts, `test_install.py:514-519`). The full suite stays green after 002. Reordering shortcut-before-wrapper is optional tidiness, not required.

---

## Phase Independence

**Confirmed.** Phase 1 = tasks 1–3 (command + shortcut + wrapper + their `test_cli.py` cases) is self-contained and independently mergeable: it touches `cli.py`, `agent_shortcuts.py`, the new wrapper, and `test_cli.py`, with no dependency on the prose. Phase 2 = task 4 depends on Phase 1 (FR-CM1 prose references `plan-task-brief`), correctly sequenced after. Matches the design's "Phase 1 ships independently of Phase 2" intent.

---

## Unresolved Ambiguity / Undecided Points

- **PLAN-TASK-003 "following the existing wrapper-coverage test pattern"** — acceptable latitude; the pattern is concrete and robust (`test_install.py:514-519`, structural discovery). Slightly under-specified (doesn't name the file), but discoverable. See F3 for the disambiguation it still needs.
- **PLAN-TASK-004 "Finalize the exact token literals against the authored prose"** — acceptable for wording-sensitive tokens (the `Narration:`/adjudication phrasings), since the skeleton already pins concrete literals. **But** this latitude is exactly what produced F2: the FR-CM4 token must be pinned to something distinctive (absent pre-edit), not deferred. The "finalize later" wording should not extend to choosing a non-load-bearing guard.

---

## Findings List

| # | Severity | Finding | Fix |
|---|---|---|---|
| F1 | **Important** | PLAN-TASK-003 shortcut skeleton (`07-plan.md:95-97`) has the wrong handler signature `(args)` (dispatch passes `(ns, base_path)`, `agent_shortcuts.py:1108`) and `return`s the exit code, which `main()` discards before `sys.exit(0)` (`agent_shortcuts.py:1108-1109`). Result: `TypeError`, and after a naive signature fix, `task-brief` always exits 0 — breaking SPEC-SURFACE-001 exit-code equivalence on statuses 6/7. The specified equivalence test (happy path, exit 0) would not catch it. | Skeleton → `def _cmd_task_brief(ns, base_path): code = _run_cli(["plan-task-brief","--work-id",ns.work_id,"--task",str(ns.task)], base_path); sys.exit(code)`, matching `agent_shortcuts.py:497-499`. Add a **non-zero** equivalence case to the test (e.g. non-EXECUTING run → both CLI and shortcut exit 6). |
| F2 | **Important** | PLAN-TASK-004 FR-CM4 guard token `"final whole-branch review"` (`07-plan.md:123`) is already present in both templates pre-edit (claude `r2p-execute.md:104`, codex `SKILL.md:105`), so it does not guard the FR-CM4 carry-forward addition — the test passes even if FR-CM4 prose never lands. Contradicts SPEC-GUARD-001's `Minor:` + carry-to-final-review token intent (`07-plan.md:196`). | Replace with a distinctive token absent before the edit: `"Minor:"` plus a literal from the authored carry-forward sentence (e.g. "carried ... to the final" / the exact phrasing). Keep `Narration:` and `Resolved:`/`Gap:`/`Unresolved:` as-is (those are load-bearing). |
| F3 | **Important** | PLAN-TASK-003 Step 2 + the SPEC Test Matrix "wrapper `r2p-task-brief` end-to-end ... identical JSON/file/exit" could lead an executor to subprocess-run the bash wrapper, which invokes system `python3` (per `CLAUDE.md`, system python3 lacks `pyyaml`) → `ImportError`, failing locally and environment-fragile on CI. | State explicitly that wrapper coverage is **structural** (install-discovery + `grep 'agent_shortcuts task-brief'`, per `test_install.py:514-519`) and that payload/exit equivalence is proven **in-process** at the shortcut layer (`agent_shortcuts.main(["task-brief", ...])`), not by executing the shell wrapper. If a subprocess smoke test is wanted, use `sys.executable` with `PYTHONPATH` set, never bare `python3`. |
| F4 | Minor | PLAN-TASK-001 skeleton `rel = brief_path.relative_to(Path(args.base_path))` (`07-plan.md:46`) assumes `--base-path` is always supplied; if omitted, `args.base_path is None` → `Path(None)` raises, unlike `_load_run`'s `base_path or cwd` tolerance. Tests always pass `--base-path`, so the suite won't surface it. | Resolve the relative path against the same base the run dir was resolved against (cwd fallback when `base_path` is None), e.g. reuse `run_dir.parent.parent` or `(args.base_path or Path.cwd())`. |
| F5 | Minor | PLAN-TASK-001 non-positive `--task` → `EXIT_CLI_ERR` is pinned by Step 3 + a test, but the skeleton doesn't show the enforcing mechanism. | Acceptable (a custom argparse `type=` that rejects `<1` exits 2 = `EXIT_CLI_ERR` naturally); optionally note the custom positive-int type in the skeleton. |

No Critical findings. The PLAN is executable; F1–F3 are concrete pre-execution fixes to keep the equivalence/guard tests from passing on latent regressions.
