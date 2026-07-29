# O3 Upper Standard Identity Audit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add deterministic O3 RF-to-XLS upper-standard identity checks and manual-review findings for missing workbooks and conflicting historical batch metadata.

**Architecture:** Extend the existing `o3_value_pass_xls_rules.py` label-driven workbook parser so current-result and upper-standard comparisons share one attachment read. Add a separate pure history-conflict function that consumes the current plus fetched history form index and returns issues keyed by current work-order code. Keep certificate interpretation outside deterministic hard errors.

**Tech Stack:** Python 3.11, pytest, openpyxl, xlrd, existing ops-audit rule engine and YAML rule configuration.

---

## File Map

- Modify `backend/app/services/ops_audit/rules/o3_value_pass_xls_rules.py`: parse and compare six upper-standard fields, emit missing-XLS review issues, and build batch-history conflict issues.
- Modify `backend/app/services/ops_audit/rules/o3_value_pass_xls_rules_test.py`: focused parser, normalization, missing-evidence, and history-conflict tests.
- Modify `backend/app/services/ops_work_order_audit_engine.py`: build history conflicts once and attach them to current audit records.
- Modify `backend/app/services/ops_audit/configs/rule_catalog.yaml`: document the two new review rules and expanded deterministic XLS comparison.
- Modify `backend/app/services/ops_audit/configs/rule_review_stages.yaml`: classify missing-XLS and history conflict findings as manual evidence review.
- Modify `backend/app/services/ops_audit/configs/business_calibration.yaml`: keep hard-error scoring limited to actual RF/XLS mismatches.
- Modify `backend/app/services/ops_audit/config.py`: align fallback rule catalog and review-stage defaults.
- Modify or create a focused audit-engine test under `backend/tests/` if module tests do not exercise issue attachment to current orders.

### Task 1: Parse And Compare Upper-Standard XLS Fields

**Files:**
- Modify: `backend/app/services/ops_audit/rules/o3_value_pass_xls_rules.py`
- Modify: `backend/app/services/ops_audit/rules/o3_value_pass_xls_rules_test.py`

- [ ] **Step 1: Write failing matching-layout tests**

Add a workbook fixture with this first-sheet content:

```python
ws["A16"] = "上级臭氧传递标准："
ws["A17"], ws["C17"], ws["D17"], ws["G17"] = "型号：", "49ips", "传递日期：", "2026-3-4 to 6"
ws["A18"], ws["C18"], ws["D18"], ws["G18"] = "设备号：", "N.A.", "传递公式：", "Y=1.00338X+0.20(ppb)"
ws["A19"], ws["C19"], ws["D19"], ws["G19"] = "序列号：", "CM26037055", "传递有效期限：", "2027-3-6"
```

Use an RF form containing `DELIVER6VALUE`, `DELIVERFROM6VALUE`, `AVALUE`,
`WORKDENSITY6VALUE`, `DELIVERTO6VALUE`, and `BVALUE`. Assert no issue is added
after case, whitespace, date-separator, and formula-presentation normalization.

- [ ] **Step 2: Write failing mismatch and layout-variant tests**

Add one test where XLS device number is `N.A.` but RF device number is
`CM20457343`; assert the existing mismatch rule reports
`DELIVERFROM6VALUE`. Add another fixture anchored by `参考光电仪` using
`认证日期`, `认证公式`, and `认证有效期限`; assert `T703 / 569 / 569` matches and
is not forced into a `49ips` convention.

- [ ] **Step 3: Run focused tests and verify RED**

Run:

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest -q \
  backend/app/services/ops_audit/rules/o3_value_pass_xls_rules_test.py \
  -k 'upper_standard'
```

Expected: the mismatch test fails because upper-standard cells are not parsed
or compared.

- [ ] **Step 4: Implement label-driven metadata extraction**

Extend both openpyxl and xlrd readers to return candidates for:

```python
UPPER_STANDARD_COMPARISONS = (
    ("DELIVER6VALUE", "上级标准型号", "text"),
    ("DELIVERFROM6VALUE", "上级标准设备号", "text"),
    ("AVALUE", "上级标准序列号", "text"),
    ("WORKDENSITY6VALUE", "上级标准传递日期", "date"),
    ("DELIVERTO6VALUE", "上级标准传递公式", "formula"),
    ("BVALUE", "上级标准有效期", "date"),
)
```

Locate the last `上级臭氧传递标准` or `参考光电仪` section, scan the next ten
rows, and associate values with the labels in columns A/D while accepting a
nearby non-empty value cell. Compare only fields whose labels and workbook
values were actually found. Text comparison ignores whitespace, case, and
punctuation; date comparison normalizes Excel serials and supported date text;
formula comparison parses the numeric slope and intercept.

- [ ] **Step 5: Run focused tests and verify GREEN**

Run the Task 1 selection and expect all selected tests to pass.

### Task 2: Report Missing XLS As Manual Review

**Files:**
- Modify: `backend/app/services/ops_audit/rules/o3_value_pass_xls_rules.py`
- Modify: `backend/app/services/ops_audit/rules/o3_value_pass_xls_rules_test.py`
- Modify: `backend/app/services/ops_audit/configs/rule_catalog.yaml`
- Modify: `backend/app/services/ops_audit/configs/rule_review_stages.yaml`
- Modify: `backend/app/services/ops_audit/config.py`

- [ ] **Step 1: Replace the existing missing-attachment expectation with a failing review test**

For an O3 RF form with JPG/PDF evidence but no XLS/XLSX, assert exactly one
issue with:

```python
assert issue.rule_id == "ATTACHMENT_O3_VALUE_PASS_XLS_MISSING_REVIEW"
assert issue.severity == "中"
assert evidence["needs_manual_review"] is True
assert evidence["upper_standard"]["model"] == "49ips"
```

- [ ] **Step 2: Run the focused test and verify RED**

Run the single missing-XLS test. Expected: no issue is currently emitted.

- [ ] **Step 3: Implement the missing-evidence issue**

When a relevant form exists and `_xls_items` is empty, add one medium-severity
issue with category `附件证据复核`, field
`attachment.RF_HY_O3VALUEPASS.xls`, `needs_manual_review=true`, the six RF
identity values, and attachment filenames/paths. Do not emit this rule for an
unavailable path that is present as XLS; preserve the existing unavailable
source behavior.

- [ ] **Step 4: Register the rule and review stage**

Add `ATTACHMENT_O3_VALUE_PASS_XLS_MISSING_REVIEW` to both YAML and Python
fallback catalogs. Add a `manual_evidence_review` review stage containing this
rule. Do not add it to hard-error or critical-hard-error lists.

- [ ] **Step 5: Run focused tests and verify GREEN**

Run all O3 XLS rule tests and the config loader tests that cover rule stages.

### Task 3: Detect Conflicting Historical Batch Metadata

**Files:**
- Modify: `backend/app/services/ops_audit/rules/o3_value_pass_xls_rules.py`
- Modify: `backend/app/services/ops_audit/rules/o3_value_pass_xls_rules_test.py`
- Modify: `backend/app/services/ops_work_order_audit_engine.py`
- Modify: `backend/app/services/ops_audit/configs/rule_catalog.yaml`
- Modify: `backend/app/services/ops_audit/configs/rule_review_stages.yaml`
- Modify: `backend/app/services/ops_audit/config.py`

- [ ] **Step 1: Write failing pure history-conflict tests**

Call a new function with current codes and a `forms_by_code` index. Create two
O3 forms that share normalized serial `CM26037055`, formula
`Y=1.00338X+0.20`, transfer date `2026-3-4to6`, and expiry `2027-3-6`, but use
identity pairs `49ips/N.A.` and `TE/49ips`. Assert issues are returned for both
current codes, evidence lists both alternatives, and neither alternative is
marked canonical.

- [ ] **Step 2: Write failing guard tests**

Assert no conflict for incomplete fingerprints, identical model/device pairs,
or a historical-only order not present in the current-code set.

- [ ] **Step 3: Run focused tests and verify RED**

Expected: import or attribute failure because the history function is absent.

- [ ] **Step 4: Implement the pure conflict builder**

Define:

```python
def build_o3_upper_standard_history_conflicts(
    forms_by_code: dict[str, list[tuple[str, dict[str, Any]]]],
    current_codes: set[str],
) -> dict[str, list[Issue]]:
    ...
```

Require all four fingerprint components. Group normalized model/device pairs,
and only emit when at least two distinct non-empty pairs exist. Include raw
values and supporting order codes, but no `expected_value` or majority choice.

- [ ] **Step 5: Integrate once per dataset audit**

After `merge_device_history(dataset)`, build conflicts using current dataset
order codes. At the start of each current-order audit, extend `issues` with the
precomputed issues for that order before deduplication and scoring.

- [ ] **Step 6: Register the review rule**

Add `RF_O3_UPPER_STANDARD_HISTORY_CONFLICT_REVIEW` to YAML and fallback rule
catalogs and the `manual_evidence_review` stage. Keep it out of hard-error
lists.

- [ ] **Step 7: Run focused tests and verify GREEN**

Run O3 rule tests plus the focused audit-engine integration test.

### Task 4: Regression And Evidence Verification

**Files:**
- Verify all modified files.

- [ ] **Step 1: Run the complete O3 and audit-rule suite**

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest -q \
  backend/app/services/ops_audit/rules/o3_value_pass_xls_rules_test.py \
  backend/app/services/ops_audit/rules/test_o3_value_pass_xls_rules.py \
  backend/tests/test_ops_audit_new_rf_rules.py
```

- [ ] **Step 2: Run the broader ops-audit service suite**

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest -q \
  backend/app/services/ops_audit \
  backend/tests/test_ops_audit_new_rf_rules.py
```

- [ ] **Step 3: Check formatting and changed-file scope**

```bash
git diff --check
git status --short
git diff --stat
```

- [ ] **Step 4: Review requirements against the design**

Confirm the implementation covers six RF/XLS identity comparisons, retains
current-slope semantics, emits review-only missing evidence and history
conflicts, and introduces no global `49ips` assumption.
