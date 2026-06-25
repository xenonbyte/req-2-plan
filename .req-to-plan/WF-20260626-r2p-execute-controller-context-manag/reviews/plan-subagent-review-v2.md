# PLAN Review v2 — WF-20260626-r2p-execute-controller-context-manag

**Verdict: Approved**

## Scope

Scoped re-review of the five v1 findings (F1–F3 Important, F4–F5 Minor) applied to `07-plan.md`. v1's full conclusions are carried forward unchanged and were not disturbed by the edits:

- **SPEC realization** — all 7 SPEC IDs consumed by the 4 tasks; contracts faithfully covered. Still holds.
- **Extraction soundness (PLAN-TASK-001)** — `zip(anchors, bodies)` alignment + integer-value resolution (zero-padding safe) verified against `markdown.py:139-178`. The logic is byte-for-byte unchanged except the single F4 line; still sound.
- **Phase independence** — Phase 1 (tasks 1–3) independently mergeable; Phase 2 (task 4) correctly sequenced after. Still holds.
- **Task ordering** — 002-before-003 acceptable (002's verification is structural). Unchanged.

## Per-finding resolution

- **F1 (Important) — RESOLVED.** PLAN-TASK-003 skeleton (`07-plan.md:98-103`) now reads `def _cmd_task_brief(ns, base_path):` then `exit_code = _run_cli([...], base_path)` / `if exit_code != 0: sys.exit(exit_code)`, and registers in "the shortcut parser AND the handlers dict". This matches the established delegation pattern (`agent_shortcuts.py:497-499`) and fixes both the `TypeError` (correct `(ns, base_path)` signature) and the silent exit-0 defect (the code is now captured and re-exited rather than `return`ed and discarded by `main()`'s `sys.exit(0)` at `agent_shortcuts.py:1108-1109`). A clarifying comment (`07-plan.md:96-97`) documents the `main()`-always-exits-0 hazard. Step 1 (`07-plan.md:106`) now requires a **non-zero** equivalence case ("a non-EXECUTING run where both exit EXIT_CONFLICT"), so the propagation is test-proven. Correct.
- **F2 (Important) — RESOLVED.** The FR-CM4 guard token is now `"Minor:"` (`07-plan.md:128`), and `"final whole-branch review"` is gone from `REQUIRED_FR_CM_TOKENS`. Verified load-bearing: `grep -c "Minor:"` returns **0** in both `agent_templates/claude/commands/r2p-execute.md` and `agent_templates/codex/skills/r2p-execute/SKILL.md` (no bare "Minor" either), so the token is absent pre-edit and the assertion genuinely guards the FR-CM4 carry-forward. Aligns with SPEC-GUARD-001's `Minor:` intent. Correct.
- **F3 (Important) — RESOLVED.** PLAN-TASK-003 Step 2 (`07-plan.md:107`) now scopes wrapper coverage to "structurally only: assert it is discovered/installed and its body delegates to `agent_shortcuts task-brief` (grep)", explicitly "Do NOT subprocess-run the shell wrapper (it invokes system `python3`, which lacks pyyaml)", and proves "payload/exit equivalence in-process at the shortcut layer". This eliminates the local-fail/CI-fragile path. Correct.
- **F4 (Minor) — RESOLVED.** PLAN-TASK-001 skeleton (`07-plan.md:46`) now computes `rel = brief_path.relative_to(run_dir.parent.parent)` — base-path independent (`run_dir` = `<base>/.req-to-plan/<id>`, so `.parent.parent` = the workspace root), removing the `Path(args.base_path)` None-hazard. The relative result is still the repo-root-relative `.req-to-plan/<id>/logs/task-N-brief.md`. Correct, and the rest of the extraction logic is unchanged.
- **F5 (Minor) — RESOLVED.** The register comment (`07-plan.md:50-51`) now specifies `--task uses a positive-int type that rejects values < 1 (the argparse type error exits EXIT_CLI_ERR)`, making the non-positive → EXIT_CLI_ERR mechanism explicit. Correct.

## No regression — structure intact

The edits touched only the four task skeletons/Steps; the Tasks structure and Trace are undisturbed:
- Still **4 tasks**, contiguous PLAN-TASK-001..004 (`07-plan.md:12,61,86,112`).
- All **7 SPEC IDs** still consumed via `Spec References` (TASK-001→SPEC-CLI-001; TASK-002/003→SPEC-SURFACE-001; TASK-004→SPEC-PROSE-001..004 + SPEC-GUARD-001).
- All **6 SCOPE-IN** still carried (TASK-001/002/003 → SCOPE-IN-001; TASK-004 → SCOPE-IN-002..006), per the `Carries` lines and Trace table.
- F4 changed exactly one line of the PLAN-TASK-001 skeleton; the `plan_task_anchors` / `heading_bounded_bodies` / `zip` / integer-resolution / symlink / `atomic_write_text` / `format_success` logic verified in v1 is otherwise byte-identical.

No new inaccuracy introduced; no field/numbering/trace regression.

## Findings

No remaining Critical, Important, or Minor findings. All five v1 findings are correctly resolved and the PLAN is clean and ready for execution.
