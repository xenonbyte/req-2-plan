# Upstream-Gap Operator Surface Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expose an in-place upstream-gap routing operator surface (CLI `gap-open` / `gap-resolve`, status visibility, and `r2p-*` shortcuts) so an open run can route back to an owning upstream stage, safely invalidate downstream, and re-derive.

**Architecture:** Two new structural CLI commands reuse the existing state helpers (`add_open_route`, `close_route`, `record_stale_artifact`, `ArtifactManager.mark_stale`) and the existing per-stage flow. `gap-open` opens a route, downgrades every downstream active artifact to `stale` and drops its approved checkpoint (so the forward flow cannot skip re-derivation), and lands the run in `ACTIVE_STAGE_DRAFT` at the owner stage via two legal status transitions. `gap-resolve` closes the route once the owner is re-worked, marked `ready`, and passes `gate-quality` into checkpoint readiness (the route, honored by the existing open-route guards in `checkpoint-decide` and `stage-advance`, must close before owner re-approval). CLI does only structural state bookkeeping; the agent supplies the owner stage, the required action, and all artifact content.

**Tech Stack:** Python 3 stdlib + PyYAML; pytest (`.venv/bin/python -m pytest`); argparse CLI under `tools/workflow_cli/`.

**Spec:** `docs/specs/2026-06-04-upstream-gap-operator-surface-design.md`

**Baseline:** 602 tests passing — must stay green. New tests use `tempfile.TemporaryDirectory` + `--base-path`; never touch real `~/.req-to-plan/`.

---

## File Structure

| File | Responsibility | Action |
|---|---|---|
| `tools/workflow_cli/cli.py` | `_cmd_gap_open`, `_cmd_gap_resolve`, `_register_route_commands`, wire into `main()`, enrich `_cmd_status_run` | Modify |
| `tools/workflow_cli/agent_shortcuts.py` | `r2p-gap-open` / `r2p-gap-resolve` subcommands delegating via `_run_cli` | Modify |
| `tools/r2p-gap-open`, `tools/r2p-gap-resolve` | Installed wrapper scripts that call `agent_shortcuts` subcommands | Create |
| `tools/workflow_cli/agent_templates/{claude,codex,gemini}/...` | 6 install templates for the two shortcuts (auto-installed via existing `r2p-*` globs) | Create |
| `tests/test_cli.py` | Fixture helper + gap-open/gap-resolve/status/safety/integration tests | Modify |
| `tests/test_agent_shortcuts.py` | Shortcut delegation tests | Modify |
| `tests/test_install.py` | Assert the new templates install | Modify |
| `docs/req-to-plan-design.md` | Update §6 once the surface is exposed | Modify |

**No state-model or serialization changes:** `RunStatus.UPSTREAM_GAP_ROUTING`, `OpenRoute`, `StaleArtifact`, their transitions, and their `run.md` round-trip (state.py save/load) already exist.

---

## Task 1: Shared test fixture `_seed_plan_approved_run`

**Files:**
- Modify: `tests/test_cli.py` (add imports near top; add helper after the existing `requirement_checkpoint()` at ~line 66)

- [ ] **Step 1: Add the fixture helper**

Add to the imports block in `tests/test_cli.py` (the `from tools.workflow_cli.models import (...)` group) these names if missing: `WorkId`, `RunStatus`, `CheckpointRecord`, `OpenRoute`, `Stage`, `STAGE_ARTIFACT_MAP`, `TierBase`, `TierEstimate`. Then add this helper after `requirement_checkpoint()`:

```python
def _seed_plan_approved_run(base_path, work_id="WF-20260604-gap"):
    """A run at PLAN with the full upstream chain active+approved on disk."""
    from tools.workflow_cli.state import create_run_record, upsert_active_artifact
    from tools.workflow_cli.artifact import write_artifact

    record = create_run_record(WorkId(work_id))
    record.current_stage = Stage.PLAN
    record.status = RunStatus.CHECKPOINT_APPROVED
    record.tier_locked = TierEstimate(base=TierBase.LIGHT)
    run_dir = Path(base_path) / ".req-to-plan" / work_id
    run_dir.mkdir(parents=True, exist_ok=True)
    for stage in (
        Stage.REQUIREMENT_BRIEF,
        Stage.RISK_DISCOVERY,
        Stage.DESIGN,
        Stage.SPEC,
        Stage.PLAN,
    ):
        artifact_file = STAGE_ARTIFACT_MAP[stage]
        write_artifact(run_dir, stage, f"# {stage.value} body\n", version=1, status="approved")
        upsert_active_artifact(record, stage, artifact_file, 1, "approved")
        record.approved_checkpoints.append(
            CheckpointRecord(
                stage=stage,
                artifact=artifact_file,
                version=1,
                approved_at="2026-06-04T00:00:00+00:00",
                downstream_authorization="next_stage",
            )
        )
    RunStateManager(run_dir).save(record)
    return work_id, run_dir
```

- [ ] **Step 2: Smoke-check the fixture round-trips**

Add this test (it also proves the seed loads back):

```python
def test_seed_plan_approved_run_roundtrips():
    with tempfile.TemporaryDirectory() as tmp:
        work_id, _ = _seed_plan_approved_run(tmp)
        rec = load_record(tmp, work_id)
        assert rec.current_stage == Stage.PLAN
        assert rec.tier_locked.base == TierBase.LIGHT
        assert {cp.stage for cp in rec.approved_checkpoints} == {
            Stage.REQUIREMENT_BRIEF,
            Stage.RISK_DISCOVERY,
            Stage.DESIGN,
            Stage.SPEC,
            Stage.PLAN,
        }
        assert all(aa.status == "approved" for aa in rec.active_artifacts)
```

- [ ] **Step 3: Run it**

Run: `.venv/bin/python -m pytest tests/test_cli.py::test_seed_plan_approved_run_roundtrips -v`
Expected: PASS.

- [ ] **Step 4: Optional checkpoint**

If the user or workflow explicitly requested commits, commit this checkpoint. Otherwise leave the verified change uncommitted and continue with the next task.

---

## Task 2: `gap-open` command (happy path)

**Files:**
- Modify: `tools/workflow_cli/cli.py` (imports; add `_cmd_gap_open`; add `_register_route_commands`; call it in `main()`)
- Modify: `tests/test_cli.py`

- [ ] **Step 1: Write the failing test**

```python
def test_gap_open_routes_back_and_invalidates_downstream(capsys):
    with tempfile.TemporaryDirectory() as tmp:
        work_id, _ = _seed_plan_approved_run(tmp)
        invoke(
            ["gap-open", "--work-id", work_id, "--owner-stage", "design",
             "--required-action", "fixed-window burst flaw"],
            base_path=tmp, expect_exit=0,
        )
        rec = load_record(tmp, work_id)
        assert rec.current_stage == Stage.DESIGN
        assert rec.status == RunStatus.ACTIVE_STAGE_DRAFT
        # one open route from plan -> design
        assert len(rec.open_routes) == 1
        r = rec.open_routes[0]
        assert (r.from_stage, r.owner_stage, r.status) == (Stage.PLAN, Stage.DESIGN, "open")
        # spec + plan downgraded to stale, their checkpoints dropped
        downstream = {aa.stage: aa.status for aa in rec.active_artifacts}
        assert downstream[Stage.SPEC] == "stale"
        assert downstream[Stage.PLAN] == "stale"
        assert downstream[Stage.DESIGN] == "approved"
        assert {cp.stage for cp in rec.approved_checkpoints} == {
            Stage.REQUIREMENT_BRIEF,
            Stage.RISK_DISCOVERY,
            Stage.DESIGN,
        }
        assert len(rec.stale_artifacts) == 2
        assert "r2p_status: stale" in (Path(tmp) / ".req-to-plan" / work_id / STAGE_ARTIFACT_MAP[Stage.SPEC]).read_text(encoding="utf-8")
        assert "r2p_status: stale" in (Path(tmp) / ".req-to-plan" / work_id / STAGE_ARTIFACT_MAP[Stage.PLAN]).read_text(encoding="utf-8")
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_cli.py::test_gap_open_routes_back_and_invalidates_downstream -v`
Expected: FAIL — `invalid choice: 'gap-open'` (command not registered).

- [ ] **Step 3: Extend cli.py imports**

In `tools/workflow_cli/cli.py`, extend the `from tools.workflow_cli.models import (...)` group with `STAGE_ORDER` and `is_transition_allowed`, and the `from tools.workflow_cli.state import (...)` group with `add_open_route`, `close_route`, `record_stale_artifact`.

- [ ] **Step 4: Add the `_cmd_gap_open` handler**

Add after `_cmd_run_reopen` (near line 435) in `tools/workflow_cli/cli.py`:

```python
def _cmd_gap_open(args):
    record, mgr, run_dir = _load_run(args.work_id, args.base_path)
    owner = _parse_stage(args.owner_stage)

    if record.status == RunStatus.CLOSED_AT_PLAN_CHECKPOINT:
        print_and_exit(
            format_error("Cannot gap-open a closed run; use run-reopen", exit_code=EXIT_CONFLICT),
            EXIT_CONFLICT,
        )
    if not args.required_action or not args.required_action.strip():
        print_and_exit(
            format_error("--required-action must be non-empty", exit_code=EXIT_CLI_ERR),
            EXIT_CLI_ERR,
        )

    cur = record.current_stage
    if owner not in STAGE_ORDER or cur not in STAGE_ORDER:
        print_and_exit(
            format_error(f"Stage {owner.value!r} not in stage order", exit_code=EXIT_CONFLICT),
            EXIT_CONFLICT,
        )
    if STAGE_ORDER.index(owner) >= STAGE_ORDER.index(cur):
        print_and_exit(
            format_error(
                f"owner-stage {owner.value!r} must be strictly upstream of current stage {cur.value!r}",
                exit_code=EXIT_CONFLICT,
            ),
            EXIT_CONFLICT,
        )
    if not is_transition_allowed(record.status, RunStatus.UPSTREAM_GAP_ROUTING):
        print_and_exit(
            format_error(
                f"Cannot route a gap from status {record.status.value!r}; resolve the current step first",
                exit_code=EXIT_CONFLICT,
            ),
            EXIT_CONFLICT,
        )
    if any(r.owner_stage == owner and r.status == "open" for r in record.open_routes):
        print_and_exit(
            format_error(f"An open route to {owner.value!r} already exists", exit_code=EXIT_CONFLICT),
            EXIT_CONFLICT,
        )

    run_md_path = run_dir / "run.md"
    run_md_before = run_md_path.read_text(encoding="utf-8")
    downstream = []
    for d in STAGE_ORDER[STAGE_ORDER.index(owner) + 1: STAGE_ORDER.index(cur) + 1]:
        aa = get_active_artifact(record, d)
        if aa is None:
            continue
        artifact_file = STAGE_ARTIFACT_MAP[d]
        artifact_path = run_dir / artifact_file
        if not artifact_path.exists():
            print_and_exit(
                format_error(
                    f"Cannot gap-open: downstream artifact file missing for {d.value!r}: {artifact_file}",
                    exit_code=EXIT_NOT_FOUND,
                ),
                EXIT_NOT_FOUND,
            )
        downstream.append((d, aa, artifact_file, artifact_path, artifact_path.read_text(encoding="utf-8")))

    route_id = f"R-{len(record.open_routes) + 1}"
    am = ArtifactManager(run_dir)
    reason = f"upstream gap at {owner.value}"
    staled = []
    try:
        add_open_route(record, route_id, from_stage=cur, owner_stage=owner, required_action=args.required_action)
        for d, aa, artifact_file, _artifact_path, _artifact_before in downstream:
            record_stale_artifact(
                record, artifact=artifact_file, reason=reason,
                replaced_by="(pending re-derivation)", required_action=route_id,
            )
            am.mark_stale(d, reason, "(pending re-derivation)")
            upsert_active_artifact(record, d, artifact_file, aa.version, "stale")
            record.approved_checkpoints = [cp for cp in record.approved_checkpoints if cp.stage != d]
            staled.append(d.value)

        record.current_stage = owner
        record = update_run_status(record, RunStatus.UPSTREAM_GAP_ROUTING)
        record = update_run_status(record, RunStatus.ACTIVE_STAGE_DRAFT)
        update_resume_context(
            record, last_operation=f"gap_open_{route_id}",
            next_operation="stage_update", active_item=owner.value,
            reason=f"repair owner for {route_id}",
        )
        mgr.save(record)
    except Exception as e:
        run_md_path.write_text(run_md_before, encoding="utf-8")
        for _d, _aa, _artifact_file, artifact_path, artifact_before in reversed(downstream):
            artifact_path.write_text(artifact_before, encoding="utf-8")
        print_and_exit(
            format_error(
                f"Cannot gap-open: failed to mark downstream stale atomically ({e})",
                exit_code=EXIT_CONFLICT,
            ),
            EXIT_CONFLICT,
        )
    print_and_exit(
        format_success(
            {"route_id": route_id, "owner_stage": owner.value, "from_stage": cur.value, "staled_stages": staled},
            message=f"Gap routed to {owner.value}; repair it, then gap-resolve --route-id {route_id}",
        ),
        EXIT_OK,
    )
```

- [ ] **Step 5: Register the route command group**

Add this function near the other `_register_*_commands` (e.g., after `_register_run_commands`) in `tools/workflow_cli/cli.py`:

```python
def _register_route_commands(subparsers):
    # gap-open
    p = subparsers.add_parser("gap-open", help="Route an upstream gap back to an owner stage")
    p.add_argument("--work-id", required=True)
    p.add_argument("--owner-stage", required=True)
    p.add_argument("--required-action", required=True)
    p.add_argument("--confirm", action="store_true")
    p.set_defaults(func=_cmd_gap_open)

```

Then in `main()`, after `_register_run_commands(subparsers)`, add:

```python
    _register_route_commands(subparsers)
```

`gap-resolve` is registered in Task 4, after `_cmd_gap_resolve` exists. This keeps strict task-by-task execution import-safe.

- [ ] **Step 6: Run the test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_cli.py::test_gap_open_routes_back_and_invalidates_downstream -v`
Expected: PASS.

- [ ] **Step 7: Add the atomicity regression test**

This proves missing downstream files are caught before any route or stale mutation is written:

```python
def test_gap_open_missing_downstream_artifact_is_atomic():
    with tempfile.TemporaryDirectory() as tmp:
        work_id, run_dir = _seed_plan_approved_run(tmp)
        spec_path = run_dir / STAGE_ARTIFACT_MAP[Stage.SPEC]
        plan_path = run_dir / STAGE_ARTIFACT_MAP[Stage.PLAN]
        spec_before = spec_path.read_text(encoding="utf-8")
        plan_path.unlink()

        invoke(["gap-open", "--work-id", work_id, "--owner-stage", "design",
                "--required-action", "x"], base_path=tmp, expect_exit=7)

        rec = load_record(tmp, work_id)
        assert rec.current_stage == Stage.PLAN
        assert rec.open_routes == []
        assert {cp.stage for cp in rec.approved_checkpoints} == {
            Stage.REQUIREMENT_BRIEF,
            Stage.RISK_DISCOVERY,
            Stage.DESIGN,
            Stage.SPEC,
            Stage.PLAN,
        }
        assert {aa.stage: aa.status for aa in rec.active_artifacts}[Stage.SPEC] == "approved"
        assert {aa.stage: aa.status for aa in rec.active_artifacts}[Stage.PLAN] == "approved"
        assert spec_path.read_text(encoding="utf-8") == spec_before
```

- [ ] **Step 8: Add the mid-write rollback regression test**

This proves a later stale write failure restores an earlier stale write and leaves `run.md` unchanged:

```python
def test_gap_open_rolls_back_mid_stale_write_failure(monkeypatch):
    from tools.workflow_cli.artifact import ArtifactManager

    with tempfile.TemporaryDirectory() as tmp:
        work_id, run_dir = _seed_plan_approved_run(tmp)
        run_md_path = run_dir / "run.md"
        spec_path = run_dir / STAGE_ARTIFACT_MAP[Stage.SPEC]
        plan_path = run_dir / STAGE_ARTIFACT_MAP[Stage.PLAN]
        run_md_before = run_md_path.read_text(encoding="utf-8")
        spec_before = spec_path.read_text(encoding="utf-8")
        plan_before = plan_path.read_text(encoding="utf-8")

        original_mark_stale = ArtifactManager.mark_stale

        def fail_on_plan(self, stage, reason, replaced_by):
            if stage == Stage.PLAN:
                raise RuntimeError("forced mark_stale failure")
            return original_mark_stale(self, stage, reason, replaced_by)

        monkeypatch.setattr(ArtifactManager, "mark_stale", fail_on_plan)

        invoke(["gap-open", "--work-id", work_id, "--owner-stage", "design",
                "--required-action", "x"], base_path=tmp, expect_exit=6)

        rec = load_record(tmp, work_id)
        assert rec.current_stage == Stage.PLAN
        assert rec.open_routes == []
        assert rec.stale_artifacts == []
        assert {cp.stage for cp in rec.approved_checkpoints} == {
            Stage.REQUIREMENT_BRIEF,
            Stage.RISK_DISCOVERY,
            Stage.DESIGN,
            Stage.SPEC,
            Stage.PLAN,
        }
        assert run_md_path.read_text(encoding="utf-8") == run_md_before
        assert spec_path.read_text(encoding="utf-8") == spec_before
        assert plan_path.read_text(encoding="utf-8") == plan_before
```

- [ ] **Step 9: Run the atomicity tests**

Run: `.venv/bin/python -m pytest tests/test_cli.py -k "gap_open_missing_downstream_artifact_is_atomic or gap_open_rolls_back_mid_stale_write_failure" -v`
Expected: PASS.

- [ ] **Step 10: Optional checkpoint**

If the user or workflow explicitly requested commits, commit this checkpoint. Otherwise leave the verified change uncommitted and continue with the next task.

---

## Task 3: `gap-open` validations

**Files:**
- Modify: `tests/test_cli.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_gap_open_rejects_owner_not_upstream():
    with tempfile.TemporaryDirectory() as tmp:
        work_id, _ = _seed_plan_approved_run(tmp)
        # plan is current; routing to plan (==current) is not strictly upstream
        invoke(["gap-open", "--work-id", work_id, "--owner-stage", "plan",
                "--required-action", "x"], base_path=tmp, expect_exit=6)


def test_gap_open_rejects_empty_required_action():
    with tempfile.TemporaryDirectory() as tmp:
        work_id, _ = _seed_plan_approved_run(tmp)
        invoke(["gap-open", "--work-id", work_id, "--owner-stage", "design",
                "--required-action", "   "], base_path=tmp, expect_exit=2)


def test_gap_open_rejects_duplicate_open_route():
    with tempfile.TemporaryDirectory() as tmp:
        work_id, _ = _seed_plan_approved_run(tmp)
        rec = load_record(tmp, work_id)
        rec.open_routes.append(
            OpenRoute(
                route_id="R-existing",
                from_stage=Stage.PLAN,
                owner_stage=Stage.DESIGN,
                required_action="already open",
                status="open",
            )
        )
        save_record(tmp, rec)

        invoke(["gap-open", "--work-id", work_id, "--owner-stage", "design",
                "--required-action", "y"], base_path=tmp, expect_exit=6)


def test_gap_open_rejects_closed_run():
    with tempfile.TemporaryDirectory() as tmp:
        work_id, _ = _seed_plan_approved_run(tmp)
        rec = load_record(tmp, work_id)
        rec.status = RunStatus.CLOSED_AT_PLAN_CHECKPOINT
        save_record(tmp, rec)

        invoke(["gap-open", "--work-id", work_id, "--owner-stage", "design",
                "--required-action", "x"], base_path=tmp, expect_exit=6)


def test_gap_open_rejects_unrouteable_current_status():
    with tempfile.TemporaryDirectory() as tmp:
        work_id, _ = _seed_plan_approved_run(tmp)
        rec = load_record(tmp, work_id)
        rec.status = RunStatus.NEXT_STAGE
        save_record(tmp, rec)

        invoke(["gap-open", "--work-id", work_id, "--owner-stage", "design",
                "--required-action", "x"], base_path=tmp, expect_exit=6)


def test_gap_open_rejects_invalid_owner_stage():
    with tempfile.TemporaryDirectory() as tmp:
        work_id, _ = _seed_plan_approved_run(tmp)
        invoke(["gap-open", "--work-id", work_id, "--owner-stage", "not-a-stage",
                "--required-action", "x"], base_path=tmp, expect_exit=2)


def test_gap_open_rejects_missing_run():
    with tempfile.TemporaryDirectory() as tmp:
        invoke(["gap-open", "--work-id", "WF-20260604-none", "--owner-stage", "design",
                "--required-action", "x"], base_path=tmp, expect_exit=7)
```

- [ ] **Step 2: Run them**

Run: `.venv/bin/python -m pytest tests/test_cli.py -k gap_open_rejects -v`
Expected: PASS (validations already implemented in Task 2). If any fails, fix the corresponding branch in `_cmd_gap_open`.

- [ ] **Step 3: Optional checkpoint**

If the user or workflow explicitly requested commits, commit this checkpoint. Otherwise leave the verified change uncommitted and continue with the next task.

---

## Task 4: `gap-resolve` command

**Files:**
- Modify: `tools/workflow_cli/cli.py` (add `_cmd_gap_resolve`; ensure `gap-resolve` registered — see Task 2 Step 5)
- Modify: `tests/test_cli.py`

- [ ] **Step 1: Write the failing tests**

```python
def _open_gap_to_design(tmp):
    work_id, run_dir = _seed_plan_approved_run(tmp)
    invoke(["gap-open", "--work-id", work_id, "--owner-stage", "design",
            "--required-action", "fix"], base_path=tmp, expect_exit=0)
    return work_id, run_dir


def test_gap_resolve_rejects_when_owner_not_ready():
    with tempfile.TemporaryDirectory() as tmp:
        work_id, _ = _open_gap_to_design(tmp)
        # owner (design) is still 'approved', not re-worked to 'ready'
        invoke(["gap-resolve", "--work-id", work_id, "--route-id", "R-1"],
               base_path=tmp, expect_exit=6)


def test_gap_resolve_rejects_before_owner_quality_gate():
    with tempfile.TemporaryDirectory() as tmp:
        work_id, _ = _open_gap_to_design(tmp)
        invoke(["stage-update", "--work-id", work_id, "--stage", "design",
                "--content", "# design v2\n"], base_path=tmp, expect_exit=0)
        invoke(["stage-ready", "--work-id", work_id, "--stage", "design"],
               base_path=tmp, expect_exit=0)
        # artifact is ready, but the run is still active_stage_draft until gate-quality passes
        invoke(["gap-resolve", "--work-id", work_id, "--route-id", "R-1"],
               base_path=tmp, expect_exit=6)


def test_gap_resolve_rejects_unknown_route():
    with tempfile.TemporaryDirectory() as tmp:
        work_id, _ = _open_gap_to_design(tmp)
        invoke(["gap-resolve", "--work-id", work_id, "--route-id", "R-9"],
               base_path=tmp, expect_exit=7)


def test_gap_resolve_rejects_missing_run():
    with tempfile.TemporaryDirectory() as tmp:
        invoke(["gap-resolve", "--work-id", "WF-20260604-none", "--route-id", "R-1"],
               base_path=tmp, expect_exit=7)


def test_gap_resolve_closes_route_when_owner_checkpoint_ready():
    with tempfile.TemporaryDirectory() as tmp:
        work_id, _ = _open_gap_to_design(tmp)
        # Re-work the owner: update design (-> v2 draft), mark ready, then pass quality gate
        invoke(["stage-update", "--work-id", work_id, "--stage", "design",
                "--content", "# design v2\n"], base_path=tmp, expect_exit=0)
        invoke(["stage-ready", "--work-id", work_id, "--stage", "design"],
               base_path=tmp, expect_exit=0)
        invoke(["gate-quality", "--work-id", work_id, "--stage", "design"],
               base_path=tmp, expect_exit=0)
        invoke(["gap-resolve", "--work-id", work_id, "--route-id", "R-1"],
               base_path=tmp, expect_exit=0)
        rec = load_record(tmp, work_id)
        assert rec.open_routes[0].status == "repaired"
        assert not [r for r in rec.open_routes if r.status == "open"]
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/python -m pytest tests/test_cli.py -k gap_resolve -v`
Expected: FAIL — `invalid choice: 'gap-resolve'` (if not yet registered) or `_cmd_gap_resolve` undefined.

- [ ] **Step 3: Implement `_cmd_gap_resolve`**

Add after `_cmd_gap_open` in `tools/workflow_cli/cli.py`:

```python
def _cmd_gap_resolve(args):
    record, mgr, run_dir = _load_run(args.work_id, args.base_path)
    route = next(
        (r for r in record.open_routes if r.route_id == args.route_id and r.status == "open"),
        None,
    )
    if route is None:
        print_and_exit(
            format_error(f"No open route with id {args.route_id!r}", exit_code=EXIT_NOT_FOUND),
            EXIT_NOT_FOUND,
        )
    owner = route.owner_stage
    aa = get_active_artifact(record, owner)
    checkpoint_ready_statuses = {
        RunStatus.READY_FOR_CHECKPOINT_REVIEW,
        RunStatus.CHECKPOINT_REVIEW,
    }
    if aa is None or aa.status != "ready" or record.status not in checkpoint_ready_statuses:
        print_and_exit(
            format_error(
                f"Owner stage {owner.value!r} must pass gate-quality before resolving the route",
                exit_code=EXIT_CONFLICT,
            ),
            EXIT_CONFLICT,
        )
    close_route(record, args.route_id)
    next_operation = (
        "checkpoint_decide"
        if record.status == RunStatus.CHECKPOINT_REVIEW
        else "checkpoint_review"
    )
    update_resume_context(
        record, last_operation=f"gap_resolve_{args.route_id}",
        next_operation=next_operation, active_item=owner.value,
    )
    mgr.save(record)
    print_and_exit(
        format_success(
            {"route_id": args.route_id, "status": "repaired", "owner_stage": owner.value,
             "resume_from": owner.value},
            message=f"Route {args.route_id} resolved; continue owner checkpoint approval",
        ),
        EXIT_OK,
    )
```

Add the `gap-resolve` parser block to `_register_route_commands` now that `_cmd_gap_resolve` exists:

```python
    # gap-resolve
    p = subparsers.add_parser("gap-resolve", help="Resolve an open upstream-gap route")
    p.add_argument("--work-id", required=True)
    p.add_argument("--route-id", required=True)
    p.add_argument("--confirm", action="store_true")
    p.set_defaults(func=_cmd_gap_resolve)
```

- [ ] **Step 4: Run to verify pass**

Run: `.venv/bin/python -m pytest tests/test_cli.py -k gap_resolve -v`
Expected: PASS.

- [ ] **Step 5: Optional checkpoint**

If the user or workflow explicitly requested commits, commit this checkpoint. Otherwise leave the verified change uncommitted and continue with the next task.

---

## Task 5: Safety invariant + deadlock-avoidance tests

**Files:**
- Modify: `tests/test_cli.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_checkpoint_decide_blocked_while_route_open_then_allowed_after_resolve():
    with tempfile.TemporaryDirectory() as tmp:
        work_id, _ = _open_gap_to_design(tmp)
        invoke(["stage-update", "--work-id", work_id, "--stage", "design",
                "--content", "# design v2\n"], base_path=tmp, expect_exit=0)
        invoke(["stage-ready", "--work-id", work_id, "--stage", "design"],
               base_path=tmp, expect_exit=0)
        invoke(["gate-quality", "--work-id", work_id, "--stage", "design"],
               base_path=tmp, expect_exit=0)
        invoke(["review-checkpoint", "--work-id", work_id, "--stage", "design"],
               base_path=tmp, expect_exit=0)
        # route still open -> approval blocked (exit 6)
        invoke(["checkpoint-decide", "--work-id", work_id, "--stage", "design",
                "--decision", "approved", "--confirm"], base_path=tmp, expect_exit=6)
        # resolve, then approval works
        invoke(["gap-resolve", "--work-id", work_id, "--route-id", "R-1"],
               base_path=tmp, expect_exit=0)
        invoke(["checkpoint-decide", "--work-id", work_id, "--stage", "design",
                "--decision", "approved", "--confirm"], base_path=tmp, expect_exit=0)


def test_stage_advance_blocked_while_route_open():
    with tempfile.TemporaryDirectory() as tmp:
        work_id, _ = _open_gap_to_design(tmp)
        # Force the other stage-advance preconditions true so this test reaches
        # the open-route guard instead of a status/artifact/checkpoint guard.
        rec = load_record(tmp, work_id)
        rec.status = RunStatus.CHECKPOINT_APPROVED
        save_record(tmp, rec)
        invoke(["stage-advance", "--work-id", work_id], base_path=tmp, expect_exit=6)


def test_stage_advance_rejects_stale_downstream_after_route_resolved():
    with tempfile.TemporaryDirectory() as tmp:
        work_id, _ = _open_gap_to_design(tmp)

        invoke(["stage-update", "--work-id", work_id, "--stage", "design",
                "--content", "# design v2\n"], base_path=tmp, expect_exit=0)
        invoke(["stage-ready", "--work-id", work_id, "--stage", "design"],
               base_path=tmp, expect_exit=0)
        invoke(["gate-quality", "--work-id", work_id, "--stage", "design"],
               base_path=tmp, expect_exit=0)
        invoke(["gap-resolve", "--work-id", work_id, "--route-id", "R-1"],
               base_path=tmp, expect_exit=0)
        invoke(["review-checkpoint", "--work-id", work_id, "--stage", "design"],
               base_path=tmp, expect_exit=0)
        invoke(["checkpoint-decide", "--work-id", work_id, "--stage", "design",
                "--decision", "approved", "--confirm"], base_path=tmp, expect_exit=0)
        invoke(["stage-advance", "--work-id", work_id], base_path=tmp, expect_exit=0)
        invoke(["gate-entry", "--work-id", work_id, "--stage", "spec"],
               base_path=tmp, expect_exit=0)

        rec = load_record(tmp, work_id)
        assert rec.current_stage == Stage.SPEC
        assert {aa.stage: aa.status for aa in rec.active_artifacts}[Stage.SPEC] == "stale"
        assert not any(cp.stage == Stage.SPEC for cp in rec.approved_checkpoints)

        # Force only the status precondition true; stage-advance must still reject
        # the stale spec active artifact instead of skipping re-derivation.
        rec.status = RunStatus.CHECKPOINT_APPROVED
        save_record(tmp, rec)
        invoke(["stage-advance", "--work-id", work_id], base_path=tmp, expect_exit=6)
```

- [ ] **Step 2: Run them**

Run: `.venv/bin/python -m pytest tests/test_cli.py -k "route_open or stale_downstream" -v`
Expected: PASS (these assert open-route guard behavior and the stale downstream skip guard reached via gap-open).

- [ ] **Step 3: Optional checkpoint**

If the user or workflow explicitly requested commits, commit this checkpoint. Otherwise leave the verified change uncommitted and continue with the next task.

---

## Task 6: End-to-end cascade integration test

**Files:**
- Modify: `tests/test_cli.py`

- [ ] **Step 1: Write the failing test**

```python
def test_gap_routing_full_cascade_back_to_plan():
    with tempfile.TemporaryDirectory() as tmp:
        work_id, _ = _seed_plan_approved_run(tmp)

        def rework_content(stage_value):
            if stage_value == "spec":
                return "# spec v2\n\n## External Documentation Checked\n\nN/A — no external dependencies\n"
            return f"# {stage_value} v2\n"

        def rework_and_approve(stage_value):
            invoke(["stage-update", "--work-id", work_id, "--stage", stage_value,
                    "--content", rework_content(stage_value)], base_path=tmp, expect_exit=0)
            invoke(["stage-ready", "--work-id", work_id, "--stage", stage_value],
                   base_path=tmp, expect_exit=0)
            invoke(["gate-quality", "--work-id", work_id, "--stage", stage_value],
                   base_path=tmp, expect_exit=0)
            invoke(["review-checkpoint", "--work-id", work_id, "--stage", stage_value],
                   base_path=tmp, expect_exit=0)
            invoke(["checkpoint-decide", "--work-id", work_id, "--stage", stage_value,
                    "--decision", "approved", "--confirm"], base_path=tmp, expect_exit=0)

        # 1. open gap to design, 2. re-work design, 3. resolve, 4. approve design
        invoke(["gap-open", "--work-id", work_id, "--owner-stage", "design",
                "--required-action", "fix"], base_path=tmp, expect_exit=0)
        invoke(["stage-update", "--work-id", work_id, "--stage", "design",
                "--content", "# design v2\n"], base_path=tmp, expect_exit=0)
        invoke(["stage-ready", "--work-id", work_id, "--stage", "design"],
               base_path=tmp, expect_exit=0)
        invoke(["gate-quality", "--work-id", work_id, "--stage", "design"],
               base_path=tmp, expect_exit=0)
        invoke(["gap-resolve", "--work-id", work_id, "--route-id", "R-1"],
               base_path=tmp, expect_exit=0)
        invoke(["review-checkpoint", "--work-id", work_id, "--stage", "design"],
               base_path=tmp, expect_exit=0)
        invoke(["checkpoint-decide", "--work-id", work_id, "--stage", "design",
                "--decision", "approved", "--confirm"], base_path=tmp, expect_exit=0)

        # 5. advance to spec and re-derive; 6. advance to plan and re-derive
        invoke(["stage-advance", "--work-id", work_id], base_path=tmp, expect_exit=0)
        invoke(["gate-entry", "--work-id", work_id, "--stage", "spec"], base_path=tmp, expect_exit=0)
        rework_and_approve("spec")
        invoke(["stage-advance", "--work-id", work_id], base_path=tmp, expect_exit=0)
        invoke(["gate-entry", "--work-id", work_id, "--stage", "plan"], base_path=tmp, expect_exit=0)
        rework_and_approve("plan")

        rec = load_record(tmp, work_id)
        assert rec.current_stage == Stage.PLAN
        outstanding = [aa.stage.value for aa in rec.active_artifacts if aa.status == "stale"]
        assert outstanding == []
```

- [ ] **Step 2: Run it**

Run: `.venv/bin/python -m pytest tests/test_cli.py::test_gap_routing_full_cascade_back_to_plan -v`
Expected: PASS. If a per-stage transition rejects (e.g., gate-entry/stage-ready status), read the failing command's error and adjust the sequence — do not weaken gap-open/gap-resolve. Capture any sequence correction as a comment in the test.

- [ ] **Step 3: Optional checkpoint**

If the user or workflow explicitly requested commits, commit this checkpoint. Otherwise leave the verified change uncommitted and continue with the next task.

---

## Task 7: Enrich `status-run` / `status-next` visibility

**Files:**
- Modify: `tools/workflow_cli/cli.py` (`_cmd_status_run`, `_cmd_status_next`)
- Modify: `tests/test_cli.py`

- [ ] **Step 1: Write the failing tests**

```python
import json

def test_status_run_surfaces_routes_and_outstanding_stale(capsys, monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        work_id, _ = _open_gap_to_design(tmp)
        monkeypatch.setenv("R2P_JSON", "1")
        invoke(["status-run", "--work-id", work_id], base_path=tmp, expect_exit=0)
        out = capsys.readouterr().out
        payload = json.loads(out)
        ids = [r["route_id"] for r in payload["open_routes_detail"]]
        assert ids == ["R-1"]
        assert set(payload["outstanding_stale"]) == {"spec", "plan"}
        assert len(payload["stale_artifacts"]) == 2


def test_status_next_surfaces_gap_route_progress(capsys, monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        work_id, _ = _open_gap_to_design(tmp)
        monkeypatch.setenv("R2P_JSON", "1")

        capsys.readouterr()
        invoke(["status-next", "--work-id", work_id], base_path=tmp, expect_exit=0)
        payload = json.loads(capsys.readouterr().out)
        assert payload["next_allowed_operation"] == "stage_update"
        assert payload["active_item"] == "design"
        assert "R-1" in payload["resume_reason"]

        invoke(["stage-update", "--work-id", work_id, "--stage", "design",
                "--content", "# design v2\n"], base_path=tmp, expect_exit=0)
        invoke(["stage-ready", "--work-id", work_id, "--stage", "design"],
               base_path=tmp, expect_exit=0)
        invoke(["gate-quality", "--work-id", work_id, "--stage", "design"],
               base_path=tmp, expect_exit=0)
        invoke(["gap-resolve", "--work-id", work_id, "--route-id", "R-1"],
               base_path=tmp, expect_exit=0)

        capsys.readouterr()
        invoke(["status-next", "--work-id", work_id], base_path=tmp, expect_exit=0)
        payload = json.loads(capsys.readouterr().out)
        assert payload["next_allowed_operation"] == "checkpoint_review"
        assert payload["active_item"] == "design"
        assert "R-1" in payload["resume_reason"]
```

> Note: `format_success` emits JSON fields at the top level when `R2P_JSON=1`; do not expect a nested `data` object.
> Note: `resume_context.next_allowed_operation` uses the repository's existing snake_case convention (`stage_update`, `checkpoint_review`, `checkpoint_decide`) rather than CLI command spelling with hyphens.

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/python -m pytest tests/test_cli.py -k "status_run_surfaces_routes_and_outstanding_stale or status_next_surfaces_gap_route_progress" -v`
Expected: FAIL — current output lacks `open_routes_detail` / `stale_artifacts` / `outstanding_stale`, and `status-next` does not expose the route resume reason.

- [ ] **Step 3: Enrich `_cmd_status_run` and `_cmd_status_next`**

Replace the body of `_cmd_status_run` in `tools/workflow_cli/cli.py` with (keeping existing keys for backward compatibility, adding new ones):

```python
def _cmd_status_run(args):
    record, mgr, run_dir = _load_run(args.work_id, args.base_path)

    open_route_ids = [r.route_id for r in record.open_routes if r.status == "open"]
    open_routes_detail = [
        {
            "route_id": r.route_id,
            "from_stage": r.from_stage.value,
            "owner_stage": r.owner_stage.value,
            "required_action": r.required_action,
            "status": r.status,
        }
        for r in record.open_routes
        if r.status == "open"
    ]
    stale_artifacts = [
        {
            "artifact": s.artifact,
            "reason": s.reason,
            "replaced_by": s.replaced_by,
            "required_action": s.required_action,
        }
        for s in record.stale_artifacts
    ]
    outstanding_stale = [aa.stage.value for aa in record.active_artifacts if aa.status == "stale"]

    print_and_exit(
        format_success(
            {
                "work_id": str(record.work_id),
                "status": record.status.value,
                "current_stage": record.current_stage.value,
                "tier_locked": (
                    record.tier_locked.base.value if record.tier_locked else "unlocked"
                ),
                "open_routes": open_route_ids,
                "open_routes_detail": open_routes_detail,
                "stale_artifacts": stale_artifacts,
                "outstanding_stale": outstanding_stale,
                "approved_checkpoints": [cp.stage.value for cp in record.approved_checkpoints],
            },
            message="Run status",
        ),
        EXIT_OK,
    )
```

(`open_routes` stays as the id list for backward compatibility; new fields are additive.)

Then update `_cmd_status_next` to include the resume reason while keeping existing keys:

```python
def _cmd_status_next(args):
    record, mgr, run_dir = _load_run(args.work_id, args.base_path)
    rc = record.resume_context
    print_and_exit(
        format_success(
            {
                "work_id": str(record.work_id),
                "next_allowed_operation": rc.next_allowed_operation,
                "active_item": rc.active_item,
                "last_completed_operation": rc.last_completed_operation,
                "resume_reason": rc.resume_reason,
            },
            message="Next operation",
        ),
        EXIT_OK,
    )
```

- [ ] **Step 4: Run to verify pass**

Run: `.venv/bin/python -m pytest tests/test_cli.py -k "status_run_surfaces_routes_and_outstanding_stale or status_next_surfaces_gap_route_progress" -v`
Expected: PASS.

- [ ] **Step 5: Optional checkpoint**

If the user or workflow explicitly requested commits, commit this checkpoint. Otherwise leave the verified change uncommitted and continue with the next task.

---

## Task 8: `r2p-*` shortcuts

**Files:**
- Modify: `tools/workflow_cli/agent_shortcuts.py` (parser, handlers dict, two `_cmd_*`)
- Create: `tools/r2p-gap-open`
- Create: `tools/r2p-gap-resolve`
- Modify: `tests/test_agent_shortcuts.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_agent_shortcuts.py` (reuse its existing run-building helpers; if it imports the CLI `invoke`, mirror that — otherwise seed via the CLI as below):

```python
import os
import subprocess
import tempfile
from pathlib import Path
import pytest
from tools.workflow_cli.agent_shortcuts import main as r2p_main
from tools.workflow_cli.cli import main as cli_main
from tools.workflow_cli.state import RunStateManager


def _seed_via_cli(tmp):
    # minimal: build a plan-approved run using the CLI test fixture shape
    from tests.test_cli import _seed_plan_approved_run
    return _seed_plan_approved_run(tmp)


def test_r2p_gap_open_delegates(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        work_id, _ = _seed_via_cli(tmp)
        import pytest
        with pytest.raises(SystemExit) as exc:
            r2p_main(
                ["gap-open", "--work-id", work_id, "--owner-stage", "design",
                 "--required-action", "fix"],
                base_path=Path(tmp),
            )
        assert exc.value.code == 0
        rec = RunStateManager(Path(tmp) / ".req-to-plan" / work_id).load()
        assert any(r.status == "open" and r.owner_stage.value == "design" for r in rec.open_routes)


def test_r2p_gap_resolve_delegates(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        work_id, _ = _seed_via_cli(tmp)
        import pytest
        with pytest.raises(SystemExit) as exc:
            r2p_main(
                ["gap-open", "--work-id", work_id, "--owner-stage", "design",
                 "--required-action", "fix"],
                base_path=Path(tmp),
            )
        assert exc.value.code == 0

        with pytest.raises(SystemExit) as exc:
            cli_main(["--base-path", tmp, "stage-update", "--work-id", work_id,
                      "--stage", "design", "--content", "# design v2\n"])
        assert exc.value.code == 0
        with pytest.raises(SystemExit) as exc:
            cli_main(["--base-path", tmp, "stage-ready", "--work-id", work_id,
                      "--stage", "design"])
        assert exc.value.code == 0
        with pytest.raises(SystemExit) as exc:
            cli_main(["--base-path", tmp, "gate-quality", "--work-id", work_id,
                      "--stage", "design"])
        assert exc.value.code == 0

        with pytest.raises(SystemExit) as exc:
            r2p_main(["gap-resolve", "--work-id", work_id, "--route-id", "R-1"],
                     base_path=Path(tmp))
        assert exc.value.code == 0
        rec = RunStateManager(Path(tmp) / ".req-to-plan" / work_id).load()
        assert rec.open_routes[0].status == "repaired"


def test_r2p_gap_open_wrapper_executes():
    wrapper = Path(__file__).resolve().parents[1] / "tools" / "r2p-gap-open"
    assert wrapper.exists()
    assert os.access(wrapper, os.X_OK)

    with tempfile.TemporaryDirectory() as tmp:
        work_id, _ = _seed_via_cli(tmp)
        result = subprocess.run(
            [str(wrapper), "--work-id", work_id, "--owner-stage", "design",
             "--required-action", "fix"],
            cwd=tmp,
            text=True,
            capture_output=True,
        )
        assert result.returncode == 0, result.stderr or result.stdout
        rec = RunStateManager(Path(tmp) / ".req-to-plan" / work_id).load()
        assert any(r.status == "open" and r.owner_stage.value == "design" for r in rec.open_routes)


def test_r2p_gap_resolve_wrapper_executes():
    gap_open = Path(__file__).resolve().parents[1] / "tools" / "r2p-gap-open"
    gap_resolve = Path(__file__).resolve().parents[1] / "tools" / "r2p-gap-resolve"
    assert gap_open.exists() and os.access(gap_open, os.X_OK)
    assert gap_resolve.exists() and os.access(gap_resolve, os.X_OK)

    with tempfile.TemporaryDirectory() as tmp:
        work_id, _ = _seed_via_cli(tmp)
        result = subprocess.run(
            [str(gap_open), "--work-id", work_id, "--owner-stage", "design",
             "--required-action", "fix"],
            cwd=tmp,
            text=True,
            capture_output=True,
        )
        assert result.returncode == 0, result.stderr or result.stdout
        with pytest.raises(SystemExit) as exc:
            cli_main(["--base-path", tmp, "stage-update", "--work-id", work_id,
                      "--stage", "design", "--content", "# design v2\n"])
        assert exc.value.code == 0
        with pytest.raises(SystemExit) as exc:
            cli_main(["--base-path", tmp, "stage-ready", "--work-id", work_id,
                      "--stage", "design"])
        assert exc.value.code == 0
        with pytest.raises(SystemExit) as exc:
            cli_main(["--base-path", tmp, "gate-quality", "--work-id", work_id,
                      "--stage", "design"])
        assert exc.value.code == 0
        result = subprocess.run(
            [str(gap_resolve), "--work-id", work_id, "--route-id", "R-1"],
            cwd=tmp,
            text=True,
            capture_output=True,
        )
        assert result.returncode == 0, result.stderr or result.stdout
        rec = RunStateManager(Path(tmp) / ".req-to-plan" / work_id).load()
        assert rec.open_routes[0].status == "repaired"
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/python -m pytest tests/test_agent_shortcuts.py -k "r2p_gap_open_delegates or r2p_gap_resolve_delegates or r2p_gap_open_wrapper_executes or r2p_gap_resolve_wrapper_executes" -v`
Expected: FAIL — `invalid choice: 'gap-open'` in the r2p parser and missing wrappers before Step 4.

- [ ] **Step 3: Add shortcut handlers + parser + dispatch**

In `tools/workflow_cli/agent_shortcuts.py`, add handlers after `_cmd_reopen`:

```python
def _cmd_gap_open(ns: argparse.Namespace, base_path: Path) -> None:
    args = [
        "gap-open",
        "--work-id", ns.work_id,
        "--owner-stage", ns.owner_stage,
        "--required-action", ns.required_action,
    ]
    if ns.confirm:
        args.append("--confirm")
    sys.exit(_run_cli(args, base_path))


def _cmd_gap_resolve(ns: argparse.Namespace, base_path: Path) -> None:
    args = ["gap-resolve", "--work-id", ns.work_id, "--route-id", ns.route_id]
    if ns.confirm:
        args.append("--confirm")
    sys.exit(_run_cli(args, base_path))
```

In `_build_parser()`, before `return parser`, add:

```python
    p_gap_open = sub.add_parser("gap-open")
    p_gap_open.add_argument("--work-id", dest="work_id", required=True)
    p_gap_open.add_argument("--owner-stage", dest="owner_stage", required=True)
    p_gap_open.add_argument("--required-action", dest="required_action", required=True)
    p_gap_open.add_argument("--confirm", action="store_true")

    p_gap_resolve = sub.add_parser("gap-resolve")
    p_gap_resolve.add_argument("--work-id", dest="work_id", required=True)
    p_gap_resolve.add_argument("--route-id", dest="route_id", required=True)
    p_gap_resolve.add_argument("--confirm", action="store_true")
```

In the `handlers` dict inside `main()`, add:

```python
        "gap-open": _cmd_gap_open,
        "gap-resolve": _cmd_gap_resolve,
```

- [ ] **Step 4: Create installed wrapper scripts**

Create `tools/r2p-gap-open` mirroring the existing `tools/r2p-reopen` wrapper:

```bash
#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
export PYTHONPATH="$REPO_ROOT${PYTHONPATH:+:$PYTHONPATH}"
if command -v python3 >/dev/null 2>&1; then
    exec python3 -m tools.workflow_cli.agent_shortcuts gap-open "$@"
else
    exec python -m tools.workflow_cli.agent_shortcuts gap-open "$@"
fi
```

Create `tools/r2p-gap-resolve`:

```bash
#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
export PYTHONPATH="$REPO_ROOT${PYTHONPATH:+:$PYTHONPATH}"
if command -v python3 >/dev/null 2>&1; then
    exec python3 -m tools.workflow_cli.agent_shortcuts gap-resolve "$@"
else
    exec python -m tools.workflow_cli.agent_shortcuts gap-resolve "$@"
fi
```

Then run:

```bash
chmod +x tools/r2p-gap-open tools/r2p-gap-resolve
```

- [ ] **Step 5: Run to verify pass**

Run: `.venv/bin/python -m pytest tests/test_agent_shortcuts.py -k "r2p_gap_open_delegates or r2p_gap_resolve_delegates or r2p_gap_open_wrapper_executes or r2p_gap_resolve_wrapper_executes" -v`
Expected: PASS.

- [ ] **Step 6: Optional checkpoint**

If the user or workflow explicitly requested commits, commit this checkpoint. Otherwise leave the verified change uncommitted and continue with the next task.

---

## Task 9: Install templates (auto-discovered via `r2p-*` globs)

**Files:**
- Create: `tools/workflow_cli/agent_templates/claude/commands/r2p-gap-open.md`
- Create: `tools/workflow_cli/agent_templates/claude/commands/r2p-gap-resolve.md`
- Create: `tools/workflow_cli/agent_templates/codex/skills/r2p-gap-open/SKILL.md`
- Create: `tools/workflow_cli/agent_templates/codex/skills/r2p-gap-resolve/SKILL.md`
- Create: `tools/workflow_cli/agent_templates/gemini/commands/r2p-gap-open.toml`
- Create: `tools/workflow_cli/agent_templates/gemini/commands/r2p-gap-resolve.toml`
- Modify: `tests/test_install.py`

- [ ] **Step 1: Create the claude command templates**

`r2p-gap-open.md`:

```markdown
---
description: Route an upstream gap back to an owner stage on an open run
---
Run `{{R2P_BIN_DIR}}/r2p-gap-open` to route a discovered upstream gap on an OPEN run back to the stage that owns the missing decision. Downstream artifacts are marked stale and must be re-derived.

Usage: `{{R2P_BIN_DIR}}/r2p-gap-open --work-id <work-id> --owner-stage <stage> --required-action "<text>"`

Example: `{{R2P_BIN_DIR}}/r2p-gap-open --work-id WF-20260604-login --owner-stage design --required-action "fixed-window burst flaw"`
```

`r2p-gap-resolve.md`:

```markdown
---
description: Resolve an open upstream-gap route after the owner stage passes gate-quality
---
Run `{{R2P_BIN_DIR}}/r2p-gap-resolve` after the owner stage has been re-worked, marked `ready`, and passed `gate-quality`. It closes the route so the owner can be re-approved and the downstream re-derived.

Usage: `{{R2P_BIN_DIR}}/r2p-gap-resolve --work-id <work-id> --route-id <route-id>`

Example: `{{R2P_BIN_DIR}}/r2p-gap-resolve --work-id WF-20260604-login --route-id R-1`
```

- [ ] **Step 2: Create the codex skill templates**

`codex/skills/r2p-gap-open/SKILL.md`:

```markdown
---
name: r2p-gap-open
description: Route an upstream gap back to an owner stage on an open run
---
Run `{{R2P_BIN_DIR}}/r2p-gap-open --work-id <work-id> --owner-stage <stage> --required-action "<text>"` to route a discovered upstream gap back to the owning stage. Downstream artifacts become stale and must be re-derived.
```

`codex/skills/r2p-gap-resolve/SKILL.md`:

```markdown
---
name: r2p-gap-resolve
description: Resolve an open upstream-gap route after the owner stage passes gate-quality
---
Run `{{R2P_BIN_DIR}}/r2p-gap-resolve --work-id <work-id> --route-id <route-id>` after the owner stage is re-worked and passes `gate-quality` to close the route.
```

- [ ] **Step 3: Create the gemini command templates**

`gemini/commands/r2p-gap-open.toml`:

```toml
description = "Route an upstream gap back to an owner stage on an open run"
prompt = "Run {{R2P_BIN_DIR}}/r2p-gap-open --work-id <work-id> --owner-stage <stage> --required-action \"<text>\" to route a discovered upstream gap back to the owning stage. Downstream artifacts become stale and must be re-derived."
```

`gemini/commands/r2p-gap-resolve.toml`:

```toml
description = "Resolve an open upstream-gap route after the owner stage passes gate-quality"
prompt = "Run {{R2P_BIN_DIR}}/r2p-gap-resolve --work-id <work-id> --route-id <route-id> after the owner stage is re-worked and passes gate-quality to close the route."
```

- [ ] **Step 4: Write a failing install test**

Add to `tests/test_install.py` (mirror an existing install test that runs `install` to a temp home and inspects written paths):

```python
@pytest.mark.parametrize(
    ("platform", "template_suffixes"),
    [
        ("claude", ("commands/r2p-gap-open.md", "commands/r2p-gap-resolve.md")),
        ("codex", ("skills/r2p-gap-open/SKILL.md", "skills/r2p-gap-resolve/SKILL.md")),
        ("gemini", ("commands/r2p-gap-open.toml", "commands/r2p-gap-resolve.toml")),
    ],
)
def test_install_writes_gap_shortcut_templates(tmp_path, platform, template_suffixes):
    svc, manifest_root, ph_root = make_service(tmp_path)
    result = svc.install(platform)
    installed_paths = [Path(p) for p in result.get("installed_paths", [])]
    installed_names = {p.name for p in installed_paths}
    assert {"r2p-gap-open", "r2p-gap-resolve"} <= installed_names
    normalized = {p.as_posix() for p in installed_paths}
    for suffix in template_suffixes:
        assert any(path.endswith(suffix) for path in normalized)
```

> Note: this mirrors the existing `tests/test_install.py` service helper and current `InstallService.install(platform)` signature; do not add ad hoc constructor arguments.

- [ ] **Step 5: Run to verify pass**

Run: `.venv/bin/python -m pytest tests/test_install.py -k gap_shortcut -v`
Expected: PASS (templates are picked up by the existing `r2p-*` glob in `install.py`).

- [ ] **Step 6: Optional checkpoint**

If the user or workflow explicitly requested commits, commit this checkpoint. Otherwise leave the verified change uncommitted and continue with the next task.

---

## Task 10: Update the design SSOT and verify the full suite

**Files:**
- Modify: `docs/req-to-plan-design.md` (§6)

- [ ] **Step 1: Update §6 to reflect the now-exposed surface**

In `docs/req-to-plan-design.md` §6, replace the "当前实现边界" paragraph's claim that the gap route / reimport / mark-stale operation surface is **not** exposed with: the open-run in-place routing surface is now exposed via `gap-open` / `gap-resolve` (and `r2p-gap-open` / `r2p-gap-resolve`); a run still closed at the PLAN checkpoint continues to use `run-reopen`. Keep the "状态名/命令以代码与 `--help` 为准" deferral line. Do not restate exit codes or flags.

- [ ] **Step 2: Run the full suite**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: PASS — `602 + <new tests> passed`, zero failures. If any pre-existing test asserts the old `status-run` shape and breaks, update it to the additive shape (open_routes unchanged; new fields added).

- [ ] **Step 3: Optional checkpoint**

If the user or workflow explicitly requested commits, commit this checkpoint. Otherwise leave the verified change uncommitted and report the final verification results.

---

## Self-Review (completed during planning)

- **Spec coverage:** §4.1 gap-open → Tasks 2–3; §4.2 gap-resolve → Task 4; §5 safety invariant → Task 2 assertions + Task 5 stale-downstream regression; §6 cascade → Task 6; §7 status surfacing → Task 7 (`status-run` route/stale fields + `status-next` resume-context assertions); §8 shortcuts+wrappers+templates → Tasks 8–9; §10 test matrix → distributed across Tasks 2–9, including closed run, unrouteable status, invalid owner stage, duplicate route, missing run/route, owner-not-ready, and stale-skip guards; §11 AC1–AC6 → Tasks 2/4/6/7/8 + Task 10 Step 2; §12 rollback (additive, no schema change) → honored (Task 7 keeps `open_routes`); §13 D1/D2/D3 → encoded in Task 2 (two-hop to ACTIVE_STAGE_DRAFT), Task 4 (owner gate-quality/checkpoint-readiness precondition), Task 7 (outstanding_stale derived).
- **Deviation noted:** spec §7.1 said "upgrade `open_routes` to objects"; plan keeps `open_routes` as ids and adds `open_routes_detail` to preserve backward compatibility (spec §12). Equivalent visibility, safer. Spec §4.2 treated owner `ready` as proof of Quality Gate pass, but current code reaches `READY_FOR_CHECKPOINT_REVIEW` only after `gate-quality`; the plan therefore requires `gate-quality` before `gap-resolve` and records this as an implementation-time correction. Spec §7.2 names CLI commands with hyphens; the implementation stores `resume_context.next_allowed_operation` in the repository's existing snake_case convention, so the plan uses `stage_update`, `checkpoint_review`, and `checkpoint_decide` in code and tests.
- **O1/O2/O3 resolved:** O1 (`stage-update` works from `ACTIVE_STAGE_DRAFT` on a previously-approved owner) confirmed via cli.py:908-991 and exercised in Task 4 with `stage-ready` + `gate-quality`; O2 (install uses `r2p-*` globs → templates auto-install) confirmed in install.py; O3 (`route_id = R-<n>`) round-trips via existing state.py Open Routes table.
- **Placeholder scan:** none — every code step contains complete code; remaining notes point at concrete existing patterns or output shape, not undefined behavior.
- **Type consistency:** `_cmd_gap_open` / `_cmd_gap_resolve`, `_register_route_commands`, `_seed_plan_approved_run`, `_open_gap_to_design` names are used consistently across tasks; `mark_stale(stage, reason, replaced_by)`, `record_stale_artifact(record, artifact, reason, replaced_by, required_action)`, `add_open_route(record, route_id, from_stage, owner_stage, required_action)`, `close_route(record, route_id)` match their definitions in artifact.py/state.py.
