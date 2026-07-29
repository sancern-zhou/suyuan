# Multipoint Curve Visual Audit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a multimodal audit that compares quarterly gas multipoint curve gradients with RF form concentration points and sends suspected mismatches and insufficient evidence to the final report with persistent image paths.

**Architecture:** A focused `multipoint_curve_visual_rules.py` module will aggregate one task per work order/RF pollutant, select curve-image candidates, persist each reviewed image into the audit output directory, call the existing Qwen-compatible multimodal adapter with form concentrations in the prompt, validate the three-state response, and emit candidate issues. The audit engine will schedule these tasks only when visual review is enabled; the final issue builder will expose report classification and attachment paths as top-level fields.

**Tech Stack:** Python 3.11, pytest, requests, existing ops-audit rule engine, existing OpenAI-compatible Qwen/MiMo visual adapter, YAML rule configuration.

---

## File map

- Create `backend/app/services/ops_audit/rules/multipoint_curve_visual_rules.py`: candidate selection, form concentration extraction, persistent evidence download/copy, prompt construction, result validation, multi-attachment aggregation, issue emission.
- Create `backend/app/services/ops_audit/rules/multipoint_curve_visual_rules_test.py`: unit tests for scheduling, three-state model output, multi-image aggregation and evidence paths.
- Modify `backend/app/services/ops_work_order_audit_engine.py`: pass a visual evidence directory into the audit and schedule the new group tasks.
- Modify `backend/app/services/ops_audit/rule_engine.py`: resolve the output directory before auditing and provide its persistent evidence subdirectory.
- Modify `backend/app/services/ops_audit/final_issue_list.py`: lift report classification and image path fields from evidence into final issue items.
- Modify `backend/app/services/ops_audit/configs/semantic_review.yaml`: enable the new visual rule.
- Modify `backend/app/services/ops_audit/configs/rule_catalog.yaml`: document the rule.
- Modify `backend/app/services/ops_audit/configs/rule_review_stages.yaml`: classify the output as manual visual review rather than a deterministic hard error.
- Modify `backend/app/services/ops_audit/config.py`: keep fallback/default catalog metadata aligned.
- Modify or create focused engine/final-list tests under `backend/app/services/ops_audit/`.

### Task 1: Build RF concentration context and curve candidate selection

**Files:**
- Create: `backend/app/services/ops_audit/rules/multipoint_curve_visual_rules.py`
- Test: `backend/app/services/ops_audit/rules/multipoint_curve_visual_rules_test.py`

- [ ] **Step 1: Write failing tests for RF context extraction**

Add tests proving that only the four quarterly multipoint tables are selected and numeric `MCLBZ10/20/40/60/80` values are returned in field order while blank, `/`, `无` and invalid values are skipped:

```python
def test_build_tasks_uses_valid_form_concentrations(tmp_path):
    tasks = build_multipoint_curve_visual_tasks(
        {"WORKINGORDERCODE": "CH1", "STATIONID": "1001"},
        [("RF_Q_GASEOUSMULTIPOINT_O3", {
            "WORKINGORDERCODE": "CH1", "POLLUTANTTYPE": "O3",
            "MCLBZ10": "90", "MCLBZ20": "160", "MCLBZ40": "240",
            "MCLBZ60": "320", "MCLBZ80": "410",
        })],
        [], [], evidence_dir=tmp_path,
    )
    assert tasks[0]["form_concentrations"] == [90.0, 160.0, 240.0, 320.0, 410.0]
    assert tasks[0]["pollutant"] == "O3"
```

- [ ] **Step 2: Write failing tests for curve candidate selection**

Cover filenames `梯度图.jpg`, `O3多点曲线.png`, `SO2多点记录表.jpg`, `O3多点90.jpg`, and an unrelated photo. Assert that only names/types clearly representing a curve are candidates; point photos and generic record-table photos are excluded.

- [ ] **Step 3: Run tests and verify RED**

Run:

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest -q backend/app/services/ops_audit/rules/multipoint_curve_visual_rules_test.py
```

Expected: collection/import failure because the module and functions do not exist.

- [ ] **Step 4: Implement the minimum task builder**

Define:

```python
RULE_ID = "ATTACHMENT_MULTIPOINT_GRADIENT_REVIEW"
MULTIPOINT_TABLES = {
    "RF_Q_GASEOUSMULTIPOINT_CO": ("CO", "ppm"),
    "RF_Q_GASEOUSMULTIPOINT_NO2": ("NO2", "ppb"),
    "RF_Q_GASEOUSMULTIPOINT_O3": ("O3", "ppb"),
    "RF_Q_GASEOUSMULTIPOINT_SO2": ("SO2", "ppb"),
}
CONCENTRATION_FIELDS = ("MCLBZ10", "MCLBZ20", "MCLBZ40", "MCLBZ60", "MCLBZ80")

def build_multipoint_curve_visual_tasks(order, forms, attachments, wo_commonfiles, *, evidence_dir):
    items = _attachment_items(attachments, wo_commonfiles)
    tasks = []
    for table, form in forms:
        if table not in MULTIPOINT_TABLES or form.get("_query_error"):
            continue
        pollutant, unit = MULTIPOINT_TABLES[table]
        tasks.append(_build_form_task(order, table, form, items, pollutant, unit, evidence_dir))
    return tasks
```

Each task must contain `task_type`, `order`, `table`, `form`, `pollutant`, `unit`, `form_concentrations`, `candidate_items`, and an absolute `evidence_dir`. Emit one task even when no candidate exists so missing/unusable evidence can be reported.

- [ ] **Step 5: Run focused tests and verify GREEN**

Run the Task 1 test file and expect all tests to pass.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/ops_audit/rules/multipoint_curve_visual_rules.py backend/app/services/ops_audit/rules/multipoint_curve_visual_rules_test.py
git commit -m "feat: select multipoint curve audit tasks"
```

### Task 2: Persist curve evidence and call the multimodal reviewer

**Files:**
- Modify: `backend/app/services/ops_audit/rules/multipoint_curve_visual_rules.py`
- Modify: `backend/app/services/ops_audit/rules/multipoint_curve_visual_rules_test.py`

- [ ] **Step 1: Write failing persistence tests**

Use `tmp_path` and monkeypatch `requests.get` to prove that URL attachments are written under `<evidence_dir>/<working_order_code>/<pollutant>/`, local files are copied there, duplicate filename collisions receive stable unique names, and the returned metadata contains:

```python
{
    "attachment_filename": "O3多点曲线.jpg",
    "attachment_local_path": "/tmp/audit-evidence/CH1/O3/O3多点曲线.jpg",
    "attachment_original_path": "/WebFiles/NewFiles/2026/5/14/curve.jpg",
    "attachment_url": "http://example.test/curve.jpg",
}
```

- [ ] **Step 2: Write failing prompt/result tests**

Monkeypatch `extract_attachment_json` and assert the prompt contains pollutant, unit, exact form concentrations, the three allowed results, explicit permission for ascending/descending curves, and the instruction not to invent confidence or exact platform values. Test normalization of valid output and conversion of API/JSON/enumeration errors into `INSUFFICIENT_EVIDENCE` with a useful reason.

- [ ] **Step 3: Run tests and verify RED**

Run the focused file; expect failures for missing persistence and review functions.

- [ ] **Step 4: Implement persistence and one-image review**

Implement bounded download/copy helpers using `requests.get(timeout=30)` and `shutil.copy2`. Call:

```python
extract_attachment_json(
    attachment_local_path,
    provider="flow_visual",
    task="multipoint_curve_gradient_review",
    prompt=prompt,
)
```

Accept only:

```python
VALID_RESULTS = {"PASS", "ISSUE_REVIEW", "INSUFFICIENT_EVIDENCE"}
VALID_REASON_CODES = {
    "NONE", "GRADIENT_MISMATCH", "POINT_COUNT_MISMATCH",
    "NO_CLEAR_GRADIENT", "POLLUTANT_MISMATCH", "NOT_MULTIPOINT_CURVE",
    "CURVE_INCOMPLETE", "IMAGE_UNREADABLE",
}
```

Do not read or branch on model confidence.

- [ ] **Step 5: Run focused tests and verify GREEN**

Run the Task 2 tests and expect all to pass.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/ops_audit/rules/multipoint_curve_visual_rules.py backend/app/services/ops_audit/rules/multipoint_curve_visual_rules_test.py
git commit -m "feat: review and persist multipoint curves"
```

### Task 3: Aggregate multiple images and emit report-ready issues

**Files:**
- Modify: `backend/app/services/ops_audit/rules/multipoint_curve_visual_rules.py`
- Modify: `backend/app/services/ops_audit/rules/multipoint_curve_visual_rules_test.py`

- [ ] **Step 1: Write failing aggregation tests**

Test these exact precedence rules:

```text
ISSUE_REVIEW + anything                    -> ISSUE_REVIEW issue
PASS + INSUFFICIENT_EVIDENCE               -> no issue
INSUFFICIENT_EVIDENCE only                 -> INSUFFICIENT_EVIDENCE issue
no candidate curve                         -> INSUFFICIENT_EVIDENCE issue
fewer than three valid RF concentration points -> INSUFFICIENT_EVIDENCE issue without model call
```

Assert emitted evidence contains `report_classification`, `needs_manual_review`, form concentrations, reason code/text, observed summary, local path, original path, URL, and all reviewed image summaries.

- [ ] **Step 2: Run tests and verify RED**

Expected: aggregation assertions fail because no issue-emission function exists.

- [ ] **Step 3: Implement task execution and issue emission**

Define:

```python
def run_multipoint_curve_visual_task(task: dict[str, Any], issues: list[Issue]) -> None:
    if len(task["form_concentrations"]) < 3:
        _add_review_issue(task, _insufficient_form_result(task), issues)
        return
    reviews = [_review_candidate(task, item) for item in task["candidate_items"]]
    selected = _select_aggregate_result(reviews)
    if selected["result"] != "PASS":
        _add_review_issue(task, selected, issues)
```

Use `add_issue` with rule `ATTACHMENT_MULTIPOINT_GRADIENT_REVIEW`, category `附件质量问题`, severity `中`, and field `attachment.multipoint_curve.<pollutant>`. Set classification to `疑似问题待人工复核` for `ISSUE_REVIEW` and `资料不足待人工复核` for insufficient evidence.

- [ ] **Step 4: Run focused tests and verify GREEN**

Run all module tests and expect pass.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/ops_audit/rules/multipoint_curve_visual_rules.py backend/app/services/ops_audit/rules/multipoint_curve_visual_rules_test.py
git commit -m "feat: emit multipoint curve review issues"
```

### Task 4: Integrate tasks into the visual audit engine

**Files:**
- Modify: `backend/app/services/ops_work_order_audit_engine.py`
- Modify: `backend/app/services/ops_audit/rule_engine.py`
- Test: `backend/app/services/ops_audit/rules/multipoint_curve_visual_rules_test.py`

- [ ] **Step 1: Write failing integration tests**

Assert `audit_dataset(dataset, enable_visual=False)` does not schedule or emit the new rule. Assert `audit_dataset(dataset, enable_visual=True, visual_evidence_dir=tmp_path)` schedules one grouped task per multipoint form and writes evidence under `tmp_path`. Monkeypatch the new runner so no external model is called.

- [ ] **Step 2: Run integration tests and verify RED**

Expected: `audit_dataset` rejects `visual_evidence_dir` and no multipoint tasks are scheduled.

- [ ] **Step 3: Implement engine integration**

Change the signature to:

```python
def audit_dataset(
    dataset: dict[str, Any],
    *,
    enable_visual: bool = True,
    visual_evidence_dir: Path | None = None,
) -> dict[str, Any]:
```

Import the new builder/runner. When visual review is enabled, append grouped tasks and route `task_type == "multipoint_curve_visual"` to the new runner. Resolve `output_dir` before `audit_dataset` in `run_rule_engine` and pass `output_dir / "visual_evidence" / "multipoint_curves"`.

- [ ] **Step 4: Run integration tests and verify GREEN**

Run focused engine and module tests and expect pass.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/ops_work_order_audit_engine.py backend/app/services/ops_audit/rule_engine.py backend/app/services/ops_audit/rules/multipoint_curve_visual_rules_test.py
git commit -m "feat: schedule multipoint curve visual review"
```

### Task 5: Surface the two report classifications and image paths

**Files:**
- Modify: `backend/app/services/ops_audit/final_issue_list.py`
- Test: `backend/app/services/ops_audit/final_issue_list_test.py`

- [ ] **Step 1: Write failing final-list tests**

Create audit records containing the new issue evidence and assert final items expose these top-level fields:

```python
assert item["report_classification"] == "疑似问题待人工复核"
assert item["needs_manual_review"] is True
assert item["attachment_filename"] == "O3多点曲线.jpg"
assert item["attachment_local_path"] == "/abs/evidence/O3多点曲线.jpg"
assert item["attachment_original_path"] == "/WebFiles/NewFiles/2026/5/14/curve.jpg"
assert item["attachment_url"] == "http://example.test/curve.jpg"
```

Repeat for `资料不足待人工复核`.

- [ ] **Step 2: Run tests and verify RED**

Expected: key assertions fail because `_issue_item` currently leaves these values inside the JSON evidence string.

- [ ] **Step 3: Implement explicit evidence projection**

In `_issue_item`, copy only the approved report fields from parsed evidence. Do not flatten arbitrary evidence keys.

- [ ] **Step 4: Run tests and verify GREEN**

Run final-list tests and expect pass.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/ops_audit/final_issue_list.py backend/app/services/ops_audit/final_issue_list_test.py
git commit -m "feat: expose visual evidence paths in issue list"
```

### Task 6: Register and calibrate the new rule

**Files:**
- Modify: `backend/app/services/ops_audit/configs/semantic_review.yaml`
- Modify: `backend/app/services/ops_audit/configs/rule_catalog.yaml`
- Modify: `backend/app/services/ops_audit/configs/rule_review_stages.yaml`
- Modify: `backend/app/services/ops_audit/config.py`
- Test: `backend/app/services/ops_audit/rules/multipoint_curve_visual_rules_test.py`

- [ ] **Step 1: Write failing configuration tests**

Assert the rule is enabled in `flow_visual_enabled_rule_ids`, appears in the catalog, maps to review stage `manual_visual_review`, and is absent from `hard_error_rules` and `critical_hard_error_rules`.

- [ ] **Step 2: Run tests and verify RED**

Expected: configuration lookup fails for the new rule.

- [ ] **Step 3: Add configuration**

Catalog metadata:

```yaml
- rule_id: ATTACHMENT_MULTIPOINT_GRADIENT_REVIEW
  name: 多点校准曲线梯度与表单浓度待复核
  category: 附件内容质量
  default_severity: 中
  scope: RF_Q_GASEOUSMULTIPOINT_*/多点曲线图片
  rationale: 多点曲线应呈现与RF表单校准浓度点一致的明显梯度；疑似不一致和资料不足均需附图人工确认。
```

Add the rule to `flow_visual_enabled_rule_ids` and to a new `manual_visual_review` stage. Do not add it to hard-error scoring lists.

- [ ] **Step 4: Run configuration tests and verify GREEN**

Run focused tests and expect pass.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/ops_audit/configs/semantic_review.yaml backend/app/services/ops_audit/configs/rule_catalog.yaml backend/app/services/ops_audit/configs/rule_review_stages.yaml backend/app/services/ops_audit/config.py backend/app/services/ops_audit/rules/multipoint_curve_visual_rules_test.py
git commit -m "feat: register multipoint curve review rule"
```

### Task 7: Full regression and real-sample dry run

**Files:**
- Modify only if verification reveals a defect in files already listed above.

- [ ] **Step 1: Run focused tests**

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest -q \
  backend/app/services/ops_audit/rules/multipoint_curve_visual_rules_test.py \
  backend/app/services/ops_audit/final_issue_list_test.py
```

Expected: all pass.

- [ ] **Step 2: Run the ops-audit service test suite**

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest -q backend/app/services/ops_audit backend/app/services/ops_audit/rules
```

Expected: all pass with zero failures.

- [ ] **Step 3: Run a no-network dry run against a historical dataset**

Use the historical dataset `backend/backend_data_registry/ops_audit_rule_validation_20260601/latest_finished_work_orders_dataset.json`, monkeypatch or disable the external visual call, and verify task selection finds known curve filenames such as `梯度图.jpg`, `O3多点曲线.png`, and `CO多点曲线.png` while excluding `O3多点90.jpg`.

- [ ] **Step 4: Run one authorized live visual sample if credentials are configured**

Run a bounded single-order/sample task, verify the model returns only the allowed states, and inspect the produced final issue item and persisted image path. If credentials are unavailable, report that live-model verification was not run; do not claim it passed.

- [ ] **Step 5: Inspect final diff**

```bash
git diff --check
git status --short
```

Confirm only this feature's files and pre-existing unrelated user changes are present.
