# Guard Hardening (R9–R13) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 堵住 R1–R8 落地后暴露的四个旁路（SCOPE-OUT 经 SPEC 中转、Context Pack 静默缺失/不可用、Change Type 词汇缝隙、技术选型无显式停点）并同步全部用户/开发文档。

**Architecture:** 全部是既有 gate/trace 防线的局部补漏——trace.py 补对称扫描、gates.py 补三个小检查、schema/template 加一个 DESIGN 章节。无新 CLI 命令、无新状态机、无公共接口变更。每条 gate 收紧都先写红队 fixture（red→green→commit）。

**Tech Stack:** Python 3.11+（标准库 only：re/json/pathlib），unittest + pytest runner，无新依赖。

**权威输入:** `docs/requirements/2026-06-05-guard-hardening.md`（R9–R13，已锁定）。本计划与该文档冲突时以该文档为准。

---

## Implementer Context（先读这段）

**运行测试（本仓库铁律——系统 Python 缺 PyYAML）：**

```bash
.venv/bin/python -m pytest tests/ -q                 # 全量
.venv/bin/python -m pytest tests/test_trace.py -v    # 单模块
```

永远不要用裸 `pytest`。

**关键边界（Agent/CLI 分界）：** CLI 只做结构校验，不做语义判断。本计划新增的所有 gate 检查都是结构性的（正则/枚举/存在性），不要加任何"内容好不好"的判断。

**关键既有设施（直接复用，不要重写）：**

| 设施 | 位置 | 用途 |
|---|---|---|
| `unfenced_markdown_lines/text` | `tools/workflow_cli/markdown.py:24,58` | 跳过 fenced code 的行迭代——所有扫描都必须基于它 |
| `heading_level(line)` | `tools/workflow_cli/markdown.py:125` | ATX 标题层级 |
| `_spec_blocks` / `_heading_blocks` | `tools/workflow_cli/trace.py:140,116` | SPEC ID → block 文本（block 止于下一个同级或更高级标题，已去 fence） |
| `plan_consumed_spec_ids` | `tools/workflow_cli/trace.py:106` | PLAN-TASK `Spec References:` 实际消费的 SPEC ID 集 |
| `_section_body(content, heading)` | `tools/workflow_cli/gates.py:512` | 取某 `## heading` 下的章节正文（unfenced、含更深层标题行） |
| `_plan_task_field_value` | `tools/workflow_cli/gates.py:292` | PLAN-TASK 字段值（含续行） |
| `STAGE_ARTIFACT_MAP` | `tools/workflow_cli/models.py:80` | stage → 文件名（SPEC=`06-spec.md`, PLAN=`07-plan.md`） |
| run 目录布局 | `cli.py:65-68` | `<base>/.req-to-plan/<work-id>/`，即 `run_dir.name == work-id` |

**测试 fixture 约定：** `tempfile.TemporaryDirectory` 隔离；`TierEstimate(base=TierBase.STANDARD, modifiers=frozenset())`；gate 测试统一签名 `check_quality_gate(run_dir, stage, tier, [], content)`。

**提交节奏：** 每个 R 一个 commit（red fixture → green → commit）。三批边界：R9+R10+R11 → R12 → R13。

---

## File Structure

| 文件 | 批次 | 变更 |
|---|---|---|
| `tools/workflow_cli/trace.py` | 1 | `_strip_nested_non_goals()` 新增；`scope_out_violations()` 增查 consumed SPEC block |
| `tools/workflow_cli/gates.py` | 1 | `_CHANGE_TYPE_*` 枚举 + `_normalized_change_type()`；`_context_pack_repo_root()` 抽取；`_check_plan_context_pack()` 新增并接线 |
| `tools/workflow_cli/gates.py` | 2 | `_check_decision_requests()` 新增并接线（Check 10）；imports 加 `heading_level` |
| `tools/workflow_cli/stage_schema.py` | 2 | DESIGN STANDARD 加 `## Decision Requests` |
| `tools/workflow_cli/stage_templates.py` | 2 | `## Decision Requests` 预置体（单行注释 + fenced 示例） |
| `tests/test_trace.py` | 1 | R9 红队/合规 fixture ×5 |
| `tests/test_gates.py` | 1+2 | R10/R11/R12 fixture + 既有 fixture 清扫 |
| `tests/test_integration.py` | 1+2 | `Change Type: new`→`create`；e2e 加 `--repo-path`；`_STANDARD_REQUIRED` 与 `_drive_stage` 加 Decision Requests |
| `tests/test_cli.py`, `tests/test_agent_shortcuts.py` | 1+2 | 清扫（按 Task 7/12 决策表） |
| `tests/test_stage_schema.py`, `tests/test_stage_templates.py` | 2 | R12 schema/template 断言 |
| `README.md`, `README.zh-CN.md` | 3 | quickstart `--repo-path .` + context-build 补救注记 |
| `tools/workflow_cli/agent_templates/claude/SKILL.md` | 3 | 命令表补 `--repo-path` + 两条 gap 命令 |
| `.claude/skills/req-to-plan.md` | 3 | 模块树整体对齐 v0.3.0 |
| `CLAUDE.md` | 3 | module map 补 7 模块 + docs/ 引用注记 |

---

## 第一批 · gate 补漏（R10/R11 因 fixture 互相掩护必须同批，R9 顺势并入）

### Task 1: R9 红队/合规 fixtures

**Files:**
- Modify: `tests/test_trace.py`（追加到 `class TestTrace`，紧跟既有 `test_plan_referencing_scope_out_is_a_violation` 之后）

- [ ] **Step 1: 写 5 个失败测试**

追加到 `tests/test_trace.py` 的 `TestTrace` 类内：

```python
    def test_scope_out_via_consumed_spec_is_a_violation(self):
        """R9 red-team: SCOPE-OUT carried by a consumed SPEC block must fail."""
        from tools.workflow_cli.trace import scope_out_violations
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = self._run_dir(
                tmp,
                "## SPEC-ADMIN-001 admin dashboard\nImplements SCOPE-OUT-001\n",
                "### PLAN-TASK-001\nSpec References: SPEC-ADMIN-001\n",
            )
            self.assertEqual(scope_out_violations(run_dir), ["SCOPE-OUT-001"])

    def test_scope_out_in_nested_non_goals_subsection_is_not_a_violation(self):
        """R9 pass fixture: SCOPE-OUT under an in-block Non-goals subheading is exempt.
        Must use a subheading INSIDE the SPEC block (deeper level), not the
        document-level ## Non-goals, so the exclusion path is actually exercised."""
        from tools.workflow_cli.trace import scope_out_violations
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = self._run_dir(
                tmp,
                "## SPEC-AUTH-001 login\nbehavior\n\n"
                "### Non-goals\n- SCOPE-OUT-001 explicitly excluded\n",
                "### PLAN-TASK-001\nSpec References: SPEC-AUTH-001\n",
            )
            self.assertEqual(scope_out_violations(run_dir), [])

    def test_scope_out_in_sibling_section_after_non_goals_is_a_violation(self):
        """R9 boundary: exemption ends at the next same-or-higher heading."""
        from tools.workflow_cli.trace import scope_out_violations
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = self._run_dir(
                tmp,
                "## SPEC-AUTH-001 login\nbehavior\n\n"
                "### Non-goals\n- excluded items\n\n"
                "### Follow-up work\nImplements SCOPE-OUT-001\n",
                "### PLAN-TASK-001\nSpec References: SPEC-AUTH-001\n",
            )
            self.assertEqual(scope_out_violations(run_dir), ["SCOPE-OUT-001"])

    def test_scope_out_in_unconsumed_spec_is_not_a_violation(self):
        """Only SPEC blocks actually consumed by PLAN-TASK Spec References count."""
        from tools.workflow_cli.trace import scope_out_violations
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = self._run_dir(
                tmp,
                "## SPEC-AUTH-001 login\nbehavior\n\n"
                "## SPEC-OTHER-001 other\nImplements SCOPE-OUT-001\n",
                "### PLAN-TASK-001\nSpec References: SPEC-AUTH-001\n",
            )
            self.assertEqual(scope_out_violations(run_dir), [])

    def test_non_goals_heading_case_variants_are_exempt(self):
        """Normalized heading match: Non-Goals / non-goals both exempt."""
        from tools.workflow_cli.trace import scope_out_violations
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = self._run_dir(
                tmp,
                "## SPEC-AUTH-001 login\nbehavior\n\n"
                "### Non-Goals\n- SCOPE-OUT-002 excluded\n",
                "### PLAN-TASK-001\nSpec References: SPEC-AUTH-001\n",
            )
            self.assertEqual(scope_out_violations(run_dir), [])
```

- [ ] **Step 2: 跑测试确认红**

Run: `.venv/bin/python -m pytest tests/test_trace.py -v -k "scope_out or non_goals"`
Expected: 新增 5 个中 `via_consumed_spec`、`sibling_section` 共 2 个 FAIL（返回 `[]` ≠ 期望违规）；3 个豁免类 PASS（当前实现本来就不扫 SPEC）。这是预期红：收紧类必须 fail 的先红，豁免类的价值在 Task 2 之后防回归。

### Task 2: R9 实现

**Files:**
- Modify: `tools/workflow_cli/trace.py:203-213`（`scope_out_violations`）+ 在其上方新增 helper

- [ ] **Step 1: 新增 `_strip_nested_non_goals`（放在 `scope_out_violations` 定义之前）**

```python
_NON_GOALS_TITLE = "non-goals"


def _strip_nested_non_goals(block: str) -> str:
    """Remove Non-goals subsections nested inside a SPEC block (R9).

    Only headings deeper than the block's own heading qualify; an exempt
    subsection runs to the next same-or-higher heading, so a later sibling
    section still counts toward scope-overflow scanning. The document-level
    `## Non-goals` never enters a SPEC block (see `_heading_blocks`), so it
    needs no handling here.
    """
    headings: list[tuple[int, int, bool]] = []  # (offset, level, is_non_goals)
    block_level: int | None = None
    offset = 0
    for line in block.splitlines(keepends=True):
        level = heading_level(line)
        if level is not None:
            if block_level is None:
                block_level = level  # the SPEC block's own heading
            else:
                title = line.lstrip().lstrip("#").strip().lower()
                headings.append((offset, level, title == _NON_GOALS_TITLE))
        offset += len(line)
    removals: list[tuple[int, int]] = []
    for i, (start, level, is_non_goals) in enumerate(headings):
        if not is_non_goals or (block_level is not None and level <= block_level):
            continue
        end = len(block)
        for next_start, next_level, _ in headings[i + 1:]:
            if next_level <= level:
                end = next_start
                break
        removals.append((start, end))
    for start, end in reversed(removals):
        block = block[:start] + block[end:]
    return block
```

注：`heading_level` 已在 trace.py 顶部 import，无需改 import。

- [ ] **Step 2: 改写 `scope_out_violations`（整体替换 trace.py:203-213 的函数体）**

```python
def scope_out_violations(run_dir: Path) -> list[str]:
    """SCOPE-OUT-* ids that PLAN-TASK bodies reference, directly or via a
    consumed SPEC block — a scope overflow (R8/R9). Non-goals subsections
    nested inside a consumed SPEC block are exempt (legitimate exclusion
    declarations)."""
    plan_text = _artifact_text(run_dir, Stage.PLAN)
    plan_task_text = "\n".join(unfenced_markdown_text(body) for body in _plan_task_bodies(plan_text))
    violations = {
        m.group(0)
        for m in _ID_RE.finditer(plan_task_text)
        if m.group(0).startswith("SCOPE-OUT-")
    }
    spec_blocks = _spec_blocks(_artifact_text(run_dir, Stage.SPEC))
    for spec_id in plan_consumed_spec_ids(run_dir):
        scanned = _strip_nested_non_goals(spec_blocks.get(spec_id, ""))
        violations.update(
            m.group(0)
            for m in _ID_RE.finditer(scanned)
            if m.group(0).startswith("SCOPE-OUT-")
        )
    return sorted(violations)
```

- [ ] **Step 3: 跑 trace 测试确认绿**

Run: `.venv/bin/python -m pytest tests/test_trace.py -v`
Expected: 全部 PASS（含既有 fenced / read-only / 直接引用回归）。

- [ ] **Step 4: 跑全量确认无涟漪**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: 全绿。gates.py 的 scope-out 消息走同一函数，consumed-SPEC 命中会以既有 `"PLAN references out-of-scope item ..."` 消息报出，无需改 gates。若有 standard e2e 测试因其 SPEC fixture 携带 SCOPE-OUT 而新红：那是真实的中转旁路被抓住了，把该 fixture 的 SCOPE-OUT 引用移进 SPEC block 内 `### Non-goals` 子章节或删除。

- [ ] **Step 5: Commit**

```bash
git add tools/workflow_cli/trace.py tests/test_trace.py
git commit -m "fix(r2p): flag SCOPE-OUT carried into PLAN via consumed SPEC blocks (R9)"
```

### Task 3: R10 红队 fixtures

**Files:**
- Modify: `tests/test_gates.py`（追加到包含 `test_files_referencing_missing_path_fails_unless_create` 的类）

- [ ] **Step 1: 写 2 个失败测试**

```python
    def test_change_type_new_is_accepted_as_create_alias(self):
        """R10: 'new' aliases 'create' — a missing path under it is exempt."""
        import json, tempfile
        from pathlib import Path
        from tools.workflow_cli.models import STAGE_ARTIFACT_MAP
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run"
            run_dir.mkdir()
            repo = Path(tmp) / "repo"
            repo.mkdir()
            (run_dir / "02-project-context.json").write_text(
                json.dumps({"repo_root": str(repo)}), encoding="utf-8")
            (run_dir / STAGE_ARTIFACT_MAP[self.Stage.SPEC]).write_text(
                "## SPEC-AUTH-001 login\n", encoding="utf-8")
            plan = ("## Tasks\n\n### PLAN-TASK-001 a\n"
                    "Spec References: SPEC-AUTH-001\nChange Type: new\n"
                    "TDD Applicable: no\nFiles:\n- src/brand_new.py\n"
                    "Skeleton: outline\nSteps:\n- [ ] build it\nVerification: pytest\n")
            (run_dir / STAGE_ARTIFACT_MAP[self.Stage.PLAN]).write_text(plan, encoding="utf-8")
            r = self.check(run_dir, self.Stage.PLAN, self.tier, [], plan)
        self.assertFalse(any("brand_new.py" in i for i in r.issues))
        self.assertFalse(any("invalid 'Change Type" in i for i in r.issues))

    def test_change_type_outside_enum_fails_loud(self):
        """R10: values outside create|modify|delete (alias new) are a gate issue."""
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            plan = ("## Tasks\n\n### PLAN-TASK-001 a\n"
                    "Spec References: none\nChange Type: refactor\n"
                    "TDD Applicable: no\nFiles: n/a\n"
                    "Skeleton: outline\nSteps:\n- [ ] do\nVerification: pytest\n")
            r = self.check(Path(tmp), self.Stage.PLAN, self.tier, [], plan)
        self.assertFalse(r.passed)
        self.assertTrue(any("invalid 'Change Type: refactor'" in i for i in r.issues))
```

- [ ] **Step 2: 跑测试确认红**

Run: `.venv/bin/python -m pytest tests/test_gates.py -v -k change_type`
Expected: `new_is_accepted` FAIL（`new` 被当非 create → 报 brand_new.py missing）；`outside_enum` FAIL（无 invalid 消息）。

### Task 4: R10 实现

**Files:**
- Modify: `tools/workflow_cli/gates.py`（枚举常量 + `_check_plan_task_fields` + `_check_plan_file_refs:384-385`）
- Modify: `tests/test_integration.py:664,690`（`Change Type: new` → `create`）

- [ ] **Step 1: 加枚举常量与归一化函数（放在 `_check_plan_task_fields` 定义之前，gates.py ~430 行附近）**

```python
# R10: Change Type is a closed operation-kind enum; 'new' is a legacy alias.
_CHANGE_TYPE_VALUES = frozenset({"create", "modify", "delete"})
_CHANGE_TYPE_ALIASES = {"new": "create"}


def _normalized_change_type(raw: str) -> str:
    value = raw.strip().lower()
    return _CHANGE_TYPE_ALIASES.get(value, value)
```

- [ ] **Step 2: `_check_plan_task_fields` 内加枚举校验**

在 `for field in PLAN_TASK_FIELDS:` 循环结束后（仍在 `for body in _iter_plan_task_bodies(content):` 内）追加：

```python
        raw_change_type = _plan_task_field_value(body, "Change Type").strip()
        if raw_change_type and _normalized_change_type(raw_change_type) not in _CHANGE_TYPE_VALUES:
            issues.append(
                f"{label} has invalid 'Change Type: {raw_change_type}'; "
                "allowed: create|modify|delete (alias: new = create)."
            )
```

（空值已由上面 missing-field 检查报告，此处只管非法词汇。）

- [ ] **Step 3: `_check_plan_file_refs` 用归一化值**

把 gates.py:384-385 的：

```python
        change_type = _plan_task_field_value(body, "Change Type").strip().lower()
        skip_missing_path = change_type == "create"
```

替换为：

```python
        skip_missing_path = _normalized_change_type(_plan_task_field_value(body, "Change Type")) == "create"
```

- [ ] **Step 4: 修正 integration fixture 词汇**

`tests/test_integration.py` 中 `_PLAN_WELL_FORMED`（line ~664）与 `_PLAN_CODE_OUTSIDE_SKELETON`（line ~690）的 `Change Type: new` 都改为 `Change Type: create`（alias 合法但 fixture 统一到规范词汇，G8）。

- [ ] **Step 5: 跑测试确认绿**

Run: `.venv/bin/python -m pytest tests/test_gates.py tests/test_integration.py -q`
Expected: 全 PASS。

- [ ] **Step 6: 全量 + Commit**

Run: `.venv/bin/python -m pytest tests/ -q` → 全绿。

```bash
git add tools/workflow_cli/gates.py tests/test_gates.py tests/test_integration.py
git commit -m "fix(r2p): validate Change Type as closed enum with new=create alias (R10)"
```

### Task 5: R11 红队 fixtures

**Files:**
- Modify: `tests/test_gates.py`（新增独立测试类）

- [ ] **Step 1: 写新测试类（追加到文件末尾，`if __name__` 之前如有）**

```python
class TestPlanContextPackGate(unittest.TestCase):
    """R11: standard-tier PLAN requires a usable Context Pack truth anchor."""

    _VALID_PLAN = (
        "## Tasks\n\n"
        "### PLAN-TASK-001 wire limiter\n"
        "Spec References: SPEC-AUTH-001\n"
        "Change Type: modify\n"
        "TDD Applicable: no\n"
        "Files: n/a\n"
        "Skeleton: inspect current middleware\n"
        "Steps:\n"
        "- [ ] update implementation\n"
        "Verification: pytest\n"
    )

    def setUp(self):
        from tools.workflow_cli.gates import check_quality_gate
        from tools.workflow_cli.models import Stage, TierBase, TierEstimate
        self.check = check_quality_gate
        self.Stage = Stage
        self.TierBase = TierBase
        self.standard = TierEstimate(base=TierBase.STANDARD, modifiers=frozenset())
        self.light = TierEstimate(base=TierBase.LIGHT, modifiers=frozenset())

    def _run_dir_with_spec(self, tmp):
        import json
        from pathlib import Path
        from tools.workflow_cli.models import STAGE_ARTIFACT_MAP
        run_dir = Path(tmp) / "run"
        run_dir.mkdir()
        (run_dir / STAGE_ARTIFACT_MAP[self.Stage.SPEC]).write_text(
            "## SPEC-AUTH-001 login\n", encoding="utf-8")
        (run_dir / STAGE_ARTIFACT_MAP[self.Stage.PLAN]).write_text(
            self._VALID_PLAN, encoding="utf-8")
        return run_dir

    def _assert_pack_issue(self, r):
        self.assertFalse(r.passed)
        self.assertTrue(
            any("python3 -m tools.workflow_cli context-build" in i for i in r.issues),
            f"expected context-build remediation in issues, got: {r.issues}")

    def test_standard_plan_without_pack_fails_with_remediation(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = self._run_dir_with_spec(tmp)
            r = self.check(run_dir, self.Stage.PLAN, self.standard, [], self._VALID_PLAN)
        self._assert_pack_issue(r)

    def test_standard_plan_with_corrupt_pack_json_fails(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = self._run_dir_with_spec(tmp)
            (run_dir / "02-project-context.json").write_text("{not json", encoding="utf-8")
            r = self.check(run_dir, self.Stage.PLAN, self.standard, [], self._VALID_PLAN)
        self._assert_pack_issue(r)

    def test_standard_plan_with_pack_missing_repo_root_fails(self):
        import json, tempfile
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = self._run_dir_with_spec(tmp)
            (run_dir / "02-project-context.json").write_text(
                json.dumps({"languages": {}}), encoding="utf-8")
            r = self.check(run_dir, self.Stage.PLAN, self.standard, [], self._VALID_PLAN)
        self._assert_pack_issue(r)

    def test_standard_plan_with_nonexistent_repo_root_fails(self):
        import json, tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = self._run_dir_with_spec(tmp)
            (run_dir / "02-project-context.json").write_text(
                json.dumps({"repo_root": str(Path(tmp) / "gone")}), encoding="utf-8")
            r = self.check(run_dir, self.Stage.PLAN, self.standard, [], self._VALID_PLAN)
        self._assert_pack_issue(r)

    def test_standard_plan_with_usable_pack_passes(self):
        import json, tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = self._run_dir_with_spec(tmp)
            repo = Path(tmp) / "repo"
            repo.mkdir()
            (run_dir / "02-project-context.json").write_text(
                json.dumps({"repo_root": str(repo)}), encoding="utf-8")
            r = self.check(run_dir, self.Stage.PLAN, self.standard, [], self._VALID_PLAN)
        self.assertTrue(r.passed, f"unexpected issues: {r.issues}")

    def test_light_plan_without_pack_passes(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            content = "## Tasks\n- [ ] do the small thing\n"
            r = self.check(Path(tmp), self.Stage.PLAN, self.light, [], content)
        self.assertTrue(r.passed, f"unexpected issues: {r.issues}")
```

- [ ] **Step 2: 跑测试确认红**

Run: `.venv/bin/python -m pytest tests/test_gates.py::TestPlanContextPackGate -v`
Expected: 4 个 unusable 变体 FAIL（gate 静默通过，无补救消息）；`usable_pack_passes` 与 `light` PASS。

### Task 6: R11 实现

**Files:**
- Modify: `tools/workflow_cli/gates.py:368-381`（抽取 helper）+ `check_quality_gate` Check 5 区接线

- [ ] **Step 1: 抽取 `_context_pack_repo_root` 并新增 `_check_plan_context_pack`（放在 `_check_plan_file_refs` 之前）**

```python
def _context_pack_repo_root(run_dir: Path) -> Path | None:
    """Usable Context Pack repo_root, or None when the pack is missing,
    unreadable, invalid JSON, lacks repo_root, or points at a missing dir."""
    import json
    pack_json = run_dir / "02-project-context.json"
    if not pack_json.exists():
        return None
    try:
        raw = json.loads(pack_json.read_text(encoding="utf-8")).get("repo_root", "")
    except (ValueError, OSError):
        return None
    if not raw:
        return None
    repo_root = Path(raw)
    if not repo_root.exists():
        return None
    return repo_root.resolve()


def _check_plan_context_pack(run_dir: Path) -> list[str]:
    """R11: standard-tier PLAN must anchor file facts to a usable Context Pack.

    Every no-usable-truth-anchor path blocks loudly; the remediation command
    is literally executable (run_dir.name is the work-id, see cli._get_run_dir).
    """
    if _context_pack_repo_root(run_dir) is not None:
        return []
    return [
        "Standard-tier PLAN requires a usable Project Context Pack: "
        "02-project-context.json is missing, unreadable, invalid, or its "
        "repo_root is unavailable. Build it with: "
        f"python3 -m tools.workflow_cli context-build --work-id {run_dir.name} "
        "--repo-path <repo-dir> (add --base-path <base-dir> when the run uses "
        "a non-default base path)."
    ]
```

- [ ] **Step 2: `_check_plan_file_refs` 头部改用 helper**

把 gates.py:368-381 的开头（从 `import json` 到 `repo_root = repo_root.resolve()`）替换为：

```python
def _check_plan_file_refs(run_dir: Path, content: str) -> list[str]:
    """Hard-check Files paths against the Context Pack repo_root. create-type tasks
    are exempt; the part after '::' (a symbol) is advisory and not checked (no AST pack yet)."""
    repo_root = _context_pack_repo_root(run_dir)
    if repo_root is None:
        return []  # no usable ground truth; standard tier blocks via _check_plan_context_pack
    issues: list[str] = []
```

（函数其余部分不动。）

- [ ] **Step 3: 接线到 quality gate 的 standard-PLAN 分支（gates.py:719）**

```python
        if stage == Stage.PLAN and tier.base == TierBase.STANDARD:
            # R11: a usable Context Pack is the truth anchor for file-ref checks.
            issues.extend(_check_plan_context_pack(run_dir))
            if not _plan_task_starts(gate_content):
```

- [ ] **Step 4: 跑 R11 测试确认绿**

Run: `.venv/bin/python -m pytest tests/test_gates.py::TestPlanContextPackGate -v`
Expected: 7 个全 PASS。

### Task 7: R11 涟漪清扫 + 第一批收口

R11 会打红所有"standard tier 走到 PLAN gate 且无 pack 仍断言通过"的既有测试。这是需求文档预言的 fixture 掩护被揭开，按决策表逐个修：

**清扫决策表：**

| 失败形态 | 修法 |
|---|---|
| e2e 流水线（`test_integration.py` `_setup_run_through_design` 驱动的用例）PLAN gate 退出码非 0 | `run-start` 调用加 repo-path（Step 2） |
| `test_gates.py` 直接调 `check_quality_gate(..., Stage.PLAN, STANDARD)` 且断言 `passed`/无某 issue | fixture 开头写入可用 pack（Step 3 的两行） |
| 上述 fixture 的 `Files:` 列了 bullet 真实路径且 `Change Type: modify` | 在 pack 的 `repo_root` 下创建该文件，或将任务改 `Change Type: create` |
| `test_agent_shortcuts.py`/`test_cli.py` standard run 走到 PLAN gate | 同上两类，按调用形态选 |
| 断言 fail 的测试多出一条 R11 issue | 不用动（断言是子串匹配，多余 issue 无害） |

- [ ] **Step 1: 跑全量，记下失败清单**

Run: `.venv/bin/python -m pytest tests/ -q 2>&1 | tail -30`
Expected: 数个 FAIL，全部命中上表形态。任何不符合上表的失败 = 实现有 bug，先回 Task 6 排查，不要硬改 fixture。

- [ ] **Step 2: 修 e2e——`tests/test_integration.py` `_setup_run_through_design`**

把：

```python
        invoke_fn(["run-start", "--work-id", work_id, "--requirement", "Add rate limiting to the API gateway"], base_path=tmp)
```

改为：

```python
        invoke_fn(["run-start", "--work-id", work_id, "--requirement", "Add rate limiting to the API gateway",
                   "--repo-path", str(tmp)], base_path=tmp)
```

（`run-start --repo-path` 会生成真实 pack，`repo_root=tmp` 存在 → 可用。PLAN fixture 的 `Files: src/middleware.py` 是 inline 非 bullet，file-ref 不解析它，无需建文件。）

- [ ] **Step 3: 修直接 gate 调用——对每个失败的 pass-断言 fixture，在写 PLAN artifact 之前加**

```python
            import json
            (run_dir / "02-project-context.json").write_text(
                json.dumps({"repo_root": str(run_dir)}), encoding="utf-8")
```

（`repo_root=run_dir` 永远存在 → pack 可用；`Files: n/a` 类 inline 值不会被 file-ref 解析。若该 fixture 用 `Path(tmp)` 直接当 run_dir，替换变量名一致即可。）

- [ ] **Step 4: 复跑全量到绿**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: 全绿。

- [ ] **Step 5: Commit（第一批收口）**

```bash
git add tools/workflow_cli/gates.py tests/test_gates.py tests/test_integration.py tests/test_cli.py tests/test_agent_shortcuts.py
git commit -m "feat(r2p): block standard-tier PLAN gate when Context Pack is missing or unusable (R11)"
```

（`git add` 只加实际改动的文件；上面列的是可能触及的全集。）

---

## 第二批 · R12 Decision Requests（模板 + schema + gate 三件套，缺一不可）

### Task 8: R12 schema + template 红测试

**Files:**
- Modify: `tests/test_stage_schema.py`、`tests/test_stage_templates.py`（各追加一个测试）

- [ ] **Step 1: schema 断言（追加到 `tests/test_stage_schema.py` 既有测试类）**

```python
    def test_standard_design_requires_decision_requests(self):
        from tools.workflow_cli.models import Stage, TierBase
        from tools.workflow_cli.stage_schema import required_headings
        self.assertIn("## Decision Requests", required_headings(Stage.DESIGN, TierBase.STANDARD))
        self.assertNotIn("## Decision Requests", required_headings(Stage.DESIGN, TierBase.LIGHT))
```

- [ ] **Step 2: template 断言（追加到 `tests/test_stage_templates.py` 既有测试类）**

```python
    def test_standard_design_template_seeds_decision_requests(self):
        from tools.workflow_cli.models import Stage, TierBase
        from tools.workflow_cli.stage_templates import template_for
        standard = template_for(Stage.DESIGN, TierBase.STANDARD)
        self.assertIn("## Decision Requests", standard)
        self.assertIn("`none`", standard)          # guidance mentions the none escape
        self.assertIn("Status: pending", standard)  # fenced example shows the contract
        self.assertNotIn("## Decision Requests", template_for(Stage.DESIGN, TierBase.LIGHT))
```

- [ ] **Step 3: 确认红**

Run: `.venv/bin/python -m pytest tests/test_stage_schema.py tests/test_stage_templates.py -v -k decision`
Expected: 2 个 FAIL。

### Task 9: R12 schema + template 实现

**Files:**
- Modify: `tools/workflow_cli/stage_schema.py:34-38`
- Modify: `tools/workflow_cli/stage_templates.py:20-41`（`_HEADING_BODY`）

- [ ] **Step 1: schema 加章节（DESIGN STANDARD 列表，`## Chosen Design` 之后）**

```python
        TierBase.STANDARD: [
            "## Design Summary", "## Current Code Evidence", "## Requirements Coverage",
            "## Options Considered", "## Chosen Design", "## Decision Requests",
            "## Rollback", "## Observability", "## SPEC Handoff",
        ],
```

- [ ] **Step 2: template 加预置体（`_HEADING_BODY` 字典内，DESIGN Chosen Design 条目之后）**

```python
    (Stage.DESIGN, "## Decision Requests"): (
        "<!-- fill in -->\n"
        "<!-- Write exactly `none` when no human decision is needed; otherwise list one `### DECISION-NNN` block per choice (fenced example below; keep guidance comments single-line). -->\n"
        "```text\n"
        "### DECISION-001 <short title>\n"
        "Question: <what must a human choose?>\n"
        "Options: A) ... / B) ...\n"
        "Recommended: A\n"
        "Status: pending\n"
        "```\n"
    ),
```

设计要点（不要改动）：示例放 fenced code 内 → 所有基于 `unfenced_markdown_lines` 的扫描器都看不见它，agent 留着示例也不会误触 gate；guidance 必须单行注释（多行注释的续行会被 `_has_meaningful_body` 和 R12 gate 当成正文）。

- [ ] **Step 3: 确认绿**

Run: `.venv/bin/python -m pytest tests/test_stage_schema.py tests/test_stage_templates.py -q`
Expected: 全 PASS。（全量先不跑——schema 收紧的涟漪在 Task 12 统一清扫。）

### Task 10: R12 decision gate 红测试

**Files:**
- Modify: `tests/test_gates.py`（新增测试类）

- [ ] **Step 1: 写测试类**

```python
class TestDecisionRequestsGate(unittest.TestCase):
    """R12: standard DESIGN must explicitly resolve decision requests."""

    def setUp(self):
        from tools.workflow_cli.gates import check_quality_gate
        from tools.workflow_cli.models import Stage, TierBase, TierEstimate
        self.check = check_quality_gate
        self.Stage = Stage
        self.standard = TierEstimate(base=TierBase.STANDARD, modifiers=frozenset())
        self.light = TierEstimate(base=TierBase.LIGHT, modifiers=frozenset())

    def _design(self, decision_section: str) -> str:
        return (
            "# Design\n\n"
            "## Design Summary\ncontent\n\n"
            "## Current Code Evidence\ncontent\n\n"
            "## Requirements Coverage\ncontent\n\n"
            "## Options Considered\ncontent\n\n"
            "## Chosen Design\n### DES-ARCH-001 selected architecture\ncontent\n\n"
            f"## Decision Requests\n{decision_section}\n"
            "## Rollback\ncontent\n\n"
            "## Observability\ncontent\n\n"
            "## SPEC Handoff\ncontent\n"
        )

    def _issues(self, content, tier=None):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            return self.check(Path(tmp), self.Stage.DESIGN, tier or self.standard, [], content).issues

    def test_none_is_a_valid_explicit_statement(self):
        self.assertEqual([i for i in self._issues(self._design("none\n")) if "R12" in i], [])

    def test_pending_decision_fails_and_lists_id(self):
        section = ("### DECISION-001 limiter backend\n"
                   "Question: Redis or in-process?\nOptions: A / B\n"
                   "Recommended: A\nStatus: pending\n")
        issues = self._issues(self._design(section))
        self.assertTrue(any("DECISION-001" in i and "pending" in i for i in issues))

    def test_selected_with_fields_passes(self):
        section = ("### DECISION-001 limiter backend\n"
                   "Question: Redis or in-process?\nOptions: A / B\n"
                   "Recommended: A\nStatus: selected\n"
                   "Selected: A\nRationale: multi-instance deployment\n")
        self.assertEqual([i for i in self._issues(self._design(section)) if "R12" in i], [])

    def test_selected_missing_rationale_fails(self):
        section = ("### DECISION-001 limiter backend\n"
                   "Question: q\nOptions: A / B\nRecommended: A\n"
                   "Status: selected\nSelected: A\n")
        issues = self._issues(self._design(section))
        self.assertTrue(any("DECISION-001" in i and "Rationale" in i for i in issues))

    def test_status_outside_enum_fails(self):
        section = ("### DECISION-001 limiter backend\n"
                   "Question: q\nOptions: A / B\nRecommended: A\nStatus: chosen\n")
        issues = self._issues(self._design(section))
        self.assertTrue(any("invalid 'Status: chosen'" in i for i in issues))

    def test_block_missing_status_line_fails(self):
        section = ("### DECISION-001 limiter backend\n"
                   "Question: q\nOptions: A / B\nRecommended: A\n")
        issues = self._issues(self._design(section))
        self.assertTrue(any("DECISION-001" in i and "missing a 'Status:'" in i for i in issues))

    def test_none_mixed_with_blocks_fails(self):
        section = ("none\n\n### DECISION-001 limiter backend\n"
                   "Question: q\nOptions: A / B\nRecommended: A\nStatus: pending\n")
        issues = self._issues(self._design(section))
        self.assertTrue(any("mixes" in i for i in issues))

    def test_empty_section_fails(self):
        issues = self._issues(self._design("<!-- a comment only -->\n"))
        self.assertTrue(any("Decision Requests" in i and "empty" in i for i in issues))

    def test_light_design_is_exempt(self):
        content = ("# Design\n\n## Design Summary\ncontent\n\n"
                   "## Chosen Design\n### DES-ARCH-001 arch\ncontent\n\n"
                   "## SPEC Handoff\ncontent\n")
        issues = self._issues(content, tier=self.light)
        self.assertEqual([i for i in issues if "Decision Requests" in i], [])
```

- [ ] **Step 2: 确认红**

Run: `.venv/bin/python -m pytest tests/test_gates.py::TestDecisionRequestsGate -v`
Expected: `none_is_valid`、`selected_with_fields`、`light_design` 3 个 PASS（gate 还不存在 → 无 R12 issue），其余 6 个 FAIL。

### Task 11: R12 decision gate 实现

**Files:**
- Modify: `tools/workflow_cli/gates.py`（imports + 新检查 + Check 10 接线）

- [ ] **Step 1: 给 markdown import 行加 `heading_level`**

找到 gates.py 顶部的 `from tools.workflow_cli.markdown import ...`，在其导入清单中加入 `heading_level`。

- [ ] **Step 2: 新增检查（放在 `_check_elicitation` 之后）**

```python
# R12: decision-request lifecycle vocabulary. The gate owns ONLY the Status
# lifecycle (enum, line presence, section non-emptiness, Selected/Rationale
# when selected); Question/Options/Recommended are template guidance enforced
# at checkpoint, not here (Agent/CLI boundary).
_DECISION_SECTION = "## Decision Requests"
_DECISION_BLOCK_RE = re.compile(r"^###\s+(DECISION-\d+)\b")
_DECISION_STATUS_VALUES = frozenset({"pending", "selected"})


def _decision_field_value(block_lines: list[str], field: str) -> str | None:
    """Value of a `Field:` line within a DECISION block; None when absent."""
    field_re = re.compile(rf"^{re.escape(field)}:\s*(.*)$")
    for line in block_lines:
        m = field_re.match(line.strip())
        if m:
            return m.group(1).strip()
    return None


def _check_decision_requests(stage: Stage, tier: TierEstimate, content: str) -> list[str]:
    """R12: standard DESIGN must list pending human decisions or state `none`."""
    from tools.workflow_cli.models import TierBase
    if stage != Stage.DESIGN or tier.base != TierBase.STANDARD:
        return []
    lines = _section_body(content, _DECISION_SECTION).splitlines()
    starts = [i for i, line in enumerate(lines) if _DECISION_BLOCK_RE.match(line.strip())]
    blocks: list[tuple[str, list[str]]] = []
    covered: set[int] = set()
    for idx, start in enumerate(starts):
        end = len(lines)
        for j in range(start + 1, len(lines)):
            level = heading_level(lines[j])
            if level is not None and level <= 3:
                end = j
                break
        decision_id = _DECISION_BLOCK_RE.match(lines[start].strip()).group(1)
        blocks.append((decision_id, lines[start + 1:end]))
        covered.update(range(start, end))
    stray = [
        line.strip()
        for i, line in enumerate(lines)
        if i not in covered and line.strip() and not line.strip().startswith("<!--")
    ]

    issues: list[str] = []
    if not blocks:
        if stray == ["none"]:
            return []
        if not stray:
            issues.append(
                "## Decision Requests is empty; state exactly `none` or list "
                "`### DECISION-NNN` blocks (R12)."
            )
        else:
            issues.append(
                "## Decision Requests must be exactly `none` (sole non-comment "
                "content) or `### DECISION-NNN` blocks (R12)."
            )
        return issues
    if "none" in stray:
        issues.append(
            "## Decision Requests mixes `none` with DECISION blocks; keep one (R12)."
        )
    for decision_id, body in blocks:
        status = _decision_field_value(body, "Status")
        if status is None:
            issues.append(
                f"{decision_id} is missing a 'Status:' line; allowed: pending|selected (R12)."
            )
            continue
        if status.lower() not in _DECISION_STATUS_VALUES:
            issues.append(
                f"{decision_id} has invalid 'Status: {status}'; allowed: pending|selected (R12)."
            )
            continue
        if status.lower() == "pending":
            issues.append(
                f"Unresolved decision request {decision_id} (Status: pending); "
                "a human must choose before this gate can pass (R12)."
            )
            continue
        for field in ("Selected", "Rationale"):
            if not (_decision_field_value(body, field) or "").strip():
                issues.append(
                    f"{decision_id} is 'Status: selected' but missing a non-empty "
                    f"'{field}:' line (R12)."
                )
    return issues
```

- [ ] **Step 3: 接线（`check_quality_gate` 内，Check 9 elicitation 之后）**

```python
        # Check 10 (R12): standard DESIGN must resolve decision requests.
        issues.extend(_check_decision_requests(stage, tier, gate_content))
```

- [ ] **Step 4: 确认绿**

Run: `.venv/bin/python -m pytest tests/test_gates.py::TestDecisionRequestsGate -v`
Expected: 10 个全 PASS。

### Task 12: R12 涟漪清扫 + 第二批收口

schema 新增 required heading 会打红所有硬编码 standard DESIGN 标题清单的 fixture。已知清单 + 决策表：

| 位置 | 修法 |
|---|---|
| `tests/test_integration.py` `_STANDARD_REQUIRED["design"]`（~line 714） | 列表加 `"## Decision Requests"` |
| `tests/test_integration.py` `_drive_stage` 的 heading 注入分支（~line 736） | 加 elif（Step 2） |
| `tests/test_gates.py` 8 处 `"## Options Considered\ncontent\n\n"` DESIGN fixture（lines ~183,242,277,301,324,347,370,661） | 断言 pass 的，在该行后插 `"## Decision Requests\nnone\n\n"`；断言 fail 的不动（多一条 issue 无害） |
| `tests/test_cli.py` ~lines 1551,1845 | 内容串中 `## Options Considered\ncontent\n` 后插 `## Decision Requests\nnone\n` |
| `tests/test_agent_shortcuts.py` standard DESIGN 内容 | 失败的同样插 `## Decision Requests\nnone\n` |

- [ ] **Step 1: 应用 `_STANDARD_REQUIRED` 修改**

```python
        "design": [
            "## Design Summary", "## Current Code Evidence", "## Requirements Coverage",
            "## Options Considered", "## Chosen Design", "## Decision Requests",
            "## Rollback", "## Observability", "## SPEC Handoff",
        ],
```

- [ ] **Step 2: `_drive_stage` 加注入分支（`## Assumptions` 的 elif 之后）**

```python
                elif heading == "## Decision Requests":
                    # R12: the gate requires exactly `none` or DECISION blocks.
                    content = content + f"\n\n{heading}\nnone\n"
```

- [ ] **Step 3: 跑全量，按决策表清扫**

Run: `.venv/bin/python -m pytest tests/ -q 2>&1 | tail -30`
对每个失败按上表处理。不符合表内形态的失败 = gate 实现 bug，回 Task 11。

- [ ] **Step 4: 复跑全量到绿**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: 全绿。

- [ ] **Step 5: Commit（第二批收口）**

```bash
git add tools/workflow_cli/stage_schema.py tools/workflow_cli/stage_templates.py tools/workflow_cli/gates.py \
  tests/test_stage_schema.py tests/test_stage_templates.py tests/test_gates.py \
  tests/test_integration.py tests/test_cli.py tests/test_agent_shortcuts.py
git commit -m "feat(r2p): Decision Requests pending gate for standard DESIGN (R12)"
```

---

## 第三批 · R13 文档同步

### Task 13: 用户文档（README ×2 + claude SKILL 模板）

**Files:**
- Modify: `README.md:70-75`（quickstart）
- Modify: `README.zh-CN.md:64-69`（quickstart，行号按 en 版对应找）
- Modify: `tools/workflow_cli/agent_templates/claude/SKILL.md:16,21,25`

- [ ] **Step 1: README.md quickstart**

把：

```bash
r2p install                       # install all platforms (default)
r2p-start "Add rate limiting"     # start a workflow run
r2p-continue                      # advance it stage by stage
r2p status                        # see what is installed
```

改为：

```bash
r2p install                                   # install all platforms (default)
r2p-start "Add rate limiting" --repo-path .   # start a run grounded in this repo's facts
r2p-continue                                  # advance it stage by stage
r2p status                                    # see what is installed
```

并紧随代码块后加一段：

```markdown
Pass `--repo-path .` whenever the requirement targets the current project (use the
target repo's path for cross-repo work); it generates the Project Context Pack that
grounds tier estimation and PLAN file-reference checks. If a standard-tier PLAN gate
later reports a missing or unusable Context Pack, build it mid-run with
`python3 -m tools.workflow_cli context-build --work-id <id> --repo-path <dir>`
(there is no standalone `context-build` executable).
```

- [ ] **Step 2: README.zh-CN.md 同位置等价修改**

```bash
r2p-start "Add rate limiting" --repo-path .   # 启动一次以当前仓库事实为锚点的工作流
```

加注：

```markdown
需求针对当前项目时必传 `--repo-path .`（跨仓库需求传目标仓库路径）；它生成的
Project Context Pack 是 tier 估算与 PLAN 文件引用校验的真值锚点。若 standard tier
的 PLAN gate 提示 Context Pack 缺失/不可用，可中途补建：
`python3 -m tools.workflow_cli context-build --work-id <id> --repo-path <dir>`
（不存在独立的 `context-build` 可执行文件）。
```

- [ ] **Step 3: claude SKILL.md 命令表（`tools/workflow_cli/agent_templates/claude/SKILL.md`）**

start 行改为：

```markdown
| `{{R2P_BIN_DIR}}/r2p-start [--separate] [--repo-path <dir>] ("<requirement>" \| --file <path>)` | Start a new workflow run; `--repo-path` grounds tier estimation and the Context Pack in real repo facts |
```

表尾（`r2p-reopen` 行之后）加两行：

```markdown
| `{{R2P_BIN_DIR}}/r2p-gap-open --work-id <id> --owner-stage <stage> --required-action "<text>"` | Route an upstream gap back to its owner stage |
| `{{R2P_BIN_DIR}}/r2p-gap-resolve --work-id <id> --route-id <route-id>` | Resolve an open upstream-gap route after the owner stage re-passes gate-quality |
```

Usage Pattern 第 1 步改为：

```markdown
1. `r2p-start [--repo-path <dir>] ("<requirement>" | --file <path>)` — start a new run; pass `--repo-path` when the requirement targets an existing repo
```

codex/gemini 模板**不改**（per-command 形态，gap 模板与 `--repo-path` 注记已存在——核对 `agent_templates/gemini/commands/r2p-start.toml:2` 与 `agent_templates/codex/skills/r2p-gap-open/` 存在即可）。

- [ ] **Step 4: 验证文档测试**

Run: `.venv/bin/python -m pytest tests/test_readme.py tests/test_docs_consistency.py tests/test_install.py -q`
Expected: 全 PASS（`test_every_workflow_skill_is_documented` 要求两份 README 提到全部 8 个 skill 名，本次修改只增不删；install 模板渲染测试覆盖 SKILL.md 变更）。

### Task 14: 开发文档（dev skill + CLAUDE.md）+ 终验收口

**Files:**
- Modify: `.claude/skills/req-to-plan.md:12-30`（模块树整体替换）
- Modify: `CLAUDE.md`（module map + Workflow Docs 注记）

- [ ] **Step 1: `.claude/skills/req-to-plan.md` 模块树整体替换（lines 12-30 的 ``` 块）**

```text
tools/workflow_cli/
├── models.py          # Core types: RunStatus, Stage, TierBase, TierModifier, TierEstimate,
│                      # EvidenceBlock, WorkId, STAGE_ORDER, STAGE_ARTIFACT_MAP, ALLOWED_TRANSITIONS
├── state.py           # RunStateManager (run.md read/write), state transition validation
├── artifact.py        # ArtifactManager (produce/update/ready/mark_stale), YAML frontmatter
├── tier.py            # scan_keywords (L1), compute_floor, estimate_tier (L1-L4)
├── tier_keywords.yaml # Keyword bank: 5 modifiers × zh+en entries
├── repo_baseline.py   # Repo baseline scan: LOC, languages, monorepo/submodule signals
├── context_pack.py    # Project Context Pack v1: deps, test commands, entrypoints, config, source dirs
├── link_expander.py   # Local relative-link expansion for requirement intake
├── stage_schema.py    # STAGE_SCHEMA required headings per stage × tier; PLAN_TASK_FIELDS
├── stage_templates.py # Render STAGE_SCHEMA into per-stage/tier seed templates
├── markdown.py        # Fence-aware Markdown helpers: unfenced lines, read-only strip, heading blocks
├── trace.py           # Derived trace model: SPEC consumption, scope/risk closure, scope-out violations
├── gates.py           # check_entry_gate, check_quality_gate, check_forced_subagent_review
├── output.py          # Exit codes, format_success/error/gate_result, is_json_mode
├── cli.py             # argparse router: run/tier/gate/status/stage/context command groups
├── agent_shortcuts.py # r2p-* shortcut surface: start/continue/status/switch/reopen/gap
├── install.py         # InstallService: install/uninstall/status, manifest safety
├── install_cli.py     # r2p lifecycle binary (delegates to InstallService)
├── version.py         # R2P_VERSION single source — do not hardcode its value in docs
└── agent_templates/   # Install templates (rendered by r2p install)
    ├── claude/        # SKILL.md + commands/r2p-*.md
    ├── codex/         # skills/r2p-*/SKILL.md (per-command)
    └── gemini/        # commands/r2p-*.toml (per-command)
```

（消灭三处漂移：`install_cli.py` stub 注记、`version.py # R2P_VERSION = "v1"` 硬编码、`codex/ # AGENTS.md` 形态错误。）

- [ ] **Step 2: CLAUDE.md module map 补 7 行（按模块表既有格式，插在 `tier_keywords.yaml` 行后）**

```markdown
| `tools/workflow_cli/repo_baseline.py` | Repo baseline scan: LOC, languages, monorepo/submodule signals |
| `tools/workflow_cli/context_pack.py` | Project Context Pack v1: deps, test commands, entrypoints, config files, source dirs |
| `tools/workflow_cli/link_expander.py` | Local relative-link expansion for requirement intake |
| `tools/workflow_cli/stage_schema.py` | STAGE_SCHEMA required headings per stage × tier; PLAN_TASK_FIELDS |
| `tools/workflow_cli/stage_templates.py` | Render STAGE_SCHEMA into per-stage/tier seed templates |
| `tools/workflow_cli/markdown.py` | Fence-aware Markdown helpers: unfenced lines, read-only strip, heading blocks |
| `tools/workflow_cli/trace.py` | Derived trace model: SPEC consumption, scope/risk closure, scope-out violations |
```

- [ ] **Step 3: CLAUDE.md Workflow Docs 注记**

把：

```markdown
- `docs/req-to-plan-design.md` — the authoritative entry doc: background, goals,
  architecture, and the per-stage quality model (enforced gate criteria).
```

改为：

```markdown
- `docs/req-to-plan-design.md` — the authoritative entry doc: background, goals,
  architecture, and the per-stage quality model (enforced gate criteria).
  Note: `docs/` is local-only (gitignored) except `docs/requirements/`, which is
  whitelisted and versioned as the authoritative PLAN inputs.
```

- [ ] **Step 4: 终验（完成口径）**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: 全绿，无跳过激增。
Run: `git diff --stat`
Expected: 仅本批 5 个文档文件。

- [ ] **Step 5: Commit（第三批收口）**

```bash
git add README.md README.zh-CN.md tools/workflow_cli/agent_templates/claude/SKILL.md \
  .claude/skills/req-to-plan.md CLAUDE.md
git commit -m "docs(r2p): sync README/SKILL/dev docs with v0.3.0 surface (R13)"
```

---

## 完成口径（来自需求文档，逐字）

全量测试绿（`.venv/bin/python -m pytest tests/ -v`）+ 新增 fixture 全绿 + CI（3.11/3.12 matrix）在 PR 跑通。不钉死精确测试数（R6 原则）。

## 遗留确认项

- R9 既有 e2e fixture 若有 SPEC 携带 SCOPE-OUT 的情况（Task 2 Step 4 的条件分支）——执行时确认，预期无。
- `tests/test_cli.py`/`tests/test_agent_shortcuts.py` 受 R11/R12 涟漪影响的具体测试名——由 Task 7/12 的全量运行现场确定，修法已由决策表完全覆盖。
