# PLAN Review (-r1) — WF-20260626-r2p-execute-controller-context-manag-r1

**Verdict: Approved with notes**

The R16/R19 gate failure is correctly resolved (4 change-type-homogeneous tasks), all three human improvements are folded in soundly, and every conclusion I verified in the prior run survived unchanged. Two Minor findings, no Critical/Important. The only real inconsistency is cosmetic: the SPEC snapshot **embedded** in `07-plan.md` is stale (still the 3-task handoff) versus the correctly-realigned live `06-spec.md` — it is stripped before any gate/trace computation, so it has no functional effect.

---

## 1. Gate-Failure Resolution (change-type homogeneity)

**Resolved — verified.** No task mixes a new file with existing files:

| Task | Change Type | Files | Homogeneous? |
|---|---|---|---|
| PLAN-TASK-001 (`07-plan.md:14-18`) | modify | `cli.py`, `tests/test_cli.py` (both existing) | ✓ modify |
| PLAN-TASK-002 (`07-plan.md:63-66`) | create | `tools/r2p-task-brief` (new only) | ✓ create |
| PLAN-TASK-003 (`07-plan.md:88-92`) | modify | `agent_shortcuts.py`, `tests/test_cli.py` (both existing) | ✓ modify |
| PLAN-TASK-004 (`07-plan.md:114-119`) | modify | two templates + `test_docs_consistency.py` (all existing) | ✓ modify |

The human's failure (one task with `modify/create` mixing the new wrapper + existing shortcut/test files) is fixed by isolating the wrapper as its own pure-`create` task (PLAN-TASK-002). R16 (`_check_plan_task_fields`, change-type/files agreement) and R19 (`_check_plan_file_refs`, create⇒new path, modify⇒existing path) are satisfied: `tools/r2p-task-brief` does not yet exist (confirmed — no such wrapper in `tools/`), and all modify targets exist. Two tasks (001, 003) both modifying `tests/test_cli.py` is permitted (R19 checks existence, not exclusivity). Gate-consistent.

---

## 2. Improvements Folded Correctly

**(a) Symlink-target test — present and sound.** PLAN-TASK-001 Step 3 (`07-plan.md:56`) now asserts "a pre-existing symlinked `logs/task-N-brief.md` target gives EXIT_CONFLICT and does not write through the link", in addition to the symlinked-`logs/`-dir case. The skeleton already guards it: `_reject_symlink_or_exit(brief_path, "brief target is a symlink")` (`07-plan.md:43`), which checks `path.is_symlink()` (`cli.py:165-167`) before the write. Sound — and defense-in-depth, since `atomic_write_text` writes a unique O_EXCL temp then `os.replace`s the path (`atomic.py:16-21`), so it would not corrupt the link target even absent the guard; the guard makes it the specified EXIT_CONFLICT.

**(b) Two new FR-CM1 tokens — load-bearing, verified.** PLAN-TASK-004 adds `"brief_path"` (`07-plan.md:126`) and `"not pasted task text"` (`07-plan.md:127`). I confirmed both are **absent (grep count 0)** from both `agent_templates/claude/commands/r2p-execute.md` and `agent_templates/codex/skills/r2p-execute/SKILL.md` pre-edit, so each genuinely guards the FR-CM1 brief-handoff prose. (`Minor:` likewise re-confirmed absent = 0.)

**(c) Robust wrapper e2e mechanism — robust on local AND CI; judged below.** PLAN-TASK-003 Step 2(2) (`07-plan.md:107`): subprocess-run the wrapper with `python3` made to resolve to a deps-complete interpreter "by prepending to PATH a temp dir whose `python3` symlinks to `sys.executable`", explicitly forbidding a hardcoded `.venv/bin`.

> **Robustness judgment:** Sound on both environments. The wrapper's `command -v python3` (`07-plan.md:74`) resolves to the prepended temp-dir `python3` → `sys.executable`, which is by construction the interpreter running pytest. That interpreter is *necessarily* dependency-complete (pyaml-equipped): the test suite cannot import `tools.workflow_cli` at all without pyyaml, so any interpreter that reaches this test has it. This holds locally (`sys.executable` = the venv python, per CLAUDE.md) and on the CI 3.11/3.12 matrix (`sys.executable` = the CI venv with `requirements-dev.txt`). The wrapper sets its own `PYTHONPATH` from `$SCRIPT_DIR/..` (`07-plan.md:72-73`), so imports resolve regardless of the caller's cwd. Symlinking to `sys.executable` is exactly how venvs locate their prefix, so site-packages resolution is the well-trodden path. **Residual fragility is negligible** — see F2 for the one implementation discipline the executor must observe.

---

## 3. Carry-Forward of Verified Conclusions

All unchanged from the version I previously approved:
- **Extraction logic** (`07-plan.md:32-35`): `plan_task_anchors(plan_text)` + `heading_bounded_bodies(plan_text, PLAN_TASK_ANCHOR_RE.match)` filter the same lines in document order (both keyed on `PLAN_TASK_ANCHOR_RE`), so `zip` aligns; integer resolution `int(re.match(r"PLAN-TASK-(\d+)", tid).group(1)) == args.task` is order-independent and zero-pad-safe. Byte-identical. ✓
- **Shortcut signature + exit-code re-raise** (`07-plan.md:98-102`): `def _cmd_task_brief(ns, base_path):` with `exit_code = _run_cli(...); if exit_code != 0: sys.exit(exit_code)` — the F1 fix (matching `agent_shortcuts.py:497-499`) is intact, with the `main()`-always-exits-0 hazard comment retained. ✓
- **`Minor:` FR-CM4 token** (`07-plan.md:130`): present. ✓

---

## 4. SPEC Consistency

**Live `06-spec.md` is correctly realigned.** Its PLAN Handoff (`06-spec.md:99-103`) now reads "Four PLAN tasks", explicitly documents the create-isolation rule ("the `tools/r2p-task-brief` wrapper is a new file, so it is its own `create` task: ... R16/R19 forbids ... mixing a new file (create) with edits to existing files (modify)"), and lists four items matching the PLAN. Its Trace (`06-spec.md:109-115`) maps **SPEC-SURFACE-001 → "consumed by PLAN-TASK-2 and PLAN-TASK-3"** and SPEC-PROSE-001..004 + SPEC-GUARD-001 → PLAN-TASK-4 — matching the 4-task PLAN exactly.

**Trace closure holds.** All 7 SPEC IDs are consumed by the actual PLAN's `Spec References` (001→SPEC-CLI-001; 002 & 003→SPEC-SURFACE-001; 004→SPEC-PROSE-001..004 + SPEC-GUARD-001), and all 6 SCOPE-IN are carried (001 across tasks 001-003; 002-006 by task 004). The machine gate passed, consistent with this.

**One inconsistency (F1, Minor):** the SPEC copy embedded as `## Upstream Summary (read-only)` inside `07-plan.md` is a stale snapshot — it still says "Three PLAN tasks" (`07-plan.md:246`) and maps SPEC-SURFACE-001 → "PLAN-TASK-2" / SPEC-PROSE → "PLAN-TASK-3" (`07-plan.md:256-261`), contradicting the realigned live SPEC. Because `strip_readonly_sections` removes this block before trace/gate computation, it has **zero functional effect** on closure or the gate; it is purely a frozen reference copy that predates the realignment.

---

## 5. Unresolved Ambiguity

None blocking. The two prior "latitude" points are now decided: PLAN-TASK-004's token finalization is constrained by a concrete 8-token list plus the explicit "every guard token must be distinctive (absent before this edit)" rule (`07-plan.md:143`); PLAN-TASK-003's wrapper e2e mechanism is pinned (sys.executable symlink on PATH). No hedging without a decision.

---

## Findings List

| # | Severity | Finding | Fix |
|---|---|---|---|
| F1 | Minor | The embedded read-only SPEC snapshot in `07-plan.md:244-261` is stale — it shows the pre-realignment 3-task handoff (SPEC-SURFACE-001 → PLAN-TASK-2; SPEC-PROSE → PLAN-TASK-3), contradicting the live `06-spec.md:99-115` 4-task handoff. No functional impact (the block is stripped before gate/trace), but a human (or the r2p-execute Pre-flight contradiction scan) reading the PLAN could be briefly confused by the 3-vs-4 discrepancy. | If the tooling supports re-seeding the Upstream Summary from the realigned SPEC, refresh it; otherwise note in the run that the embedded SPEC snapshot predates the handoff realignment and the live `06-spec.md` is authoritative. Does not block execution. |
| F2 | Minor | The wrapper e2e mechanism (`07-plan.md:107`) is robust in principle but depends on implementation discipline the skeleton leaves implicit: the temp `python3` symlink must be executable and the temp dir must be genuinely first on the **child** process's PATH (pass `env={**os.environ, "PATH": tmp + os.pathsep + os.environ["PATH"]}` to `subprocess.run`, do not clear the env). | Have the test build the child env explicitly with the temp dir prepended and `chmod +x` (or rely on the symlink's target perms) the `python3` link; assert the subprocess exit/JSON/file equal the in-process CLI. Optional one-line note in the skeleton. |

No Critical or Important findings. The corrected `-r1` PLAN is gate-valid, faithfully realizes the realigned SPEC, folds the three improvements soundly, and is ready for execution.
