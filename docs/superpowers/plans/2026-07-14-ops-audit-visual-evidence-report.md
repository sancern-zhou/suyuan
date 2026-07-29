# Operations Audit Visual Evidence Report Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Archive every photo associated with confirmed or pending-review operations-audit visual findings and embed at most three photos per finding in generated reports while retaining every photo in the evidence package.

**Architecture:** Add a focused post-audit evidence archiver that normalizes local and remote attachment sources, copies/downloads each unique image into the current audit output, writes a manifest, and enriches issue evidence before the final issue list is assembled. Keep confirmed issues sourced from `final_issue_list`; have the report writer separately render non-promoted visual-review candidates from the current audit and reference only successfully archived local images.

**Tech Stack:** Python 3.11, pathlib, requests, JSON, Markdown, pytest, Conda environment `/root/miniconda3/envs/backend_py311`

---

## File Structure

- Create `backend/app/services/ops_audit/visual_evidence.py`: detect visual findings, resolve/copy/download image sources, de-duplicate files, enrich issue evidence, and write the manifest.
- Create `backend/tests/test_ops_audit_visual_evidence.py`: unit tests for local/remote archiving, de-duplication, full multi-image retention, and failure degradation.
- Modify `backend/app/services/ops_audit/rule_engine.py`: run the archiver after visual auditing and expose the manifest path/counts.
- Modify `backend/app/services/ops_audit/final_issue_list.py`: expose `evidence_images` on confirmed visual issue items.
- Modify `backend/tests/test_ops_audit_final_issue_list.py`: verify image metadata propagation.
- Modify `backend/app/services/ops_audit/report_writer.py`: render confirmed evidence and a separate pending visual-review section, with at most three images per finding.
- Modify `backend/tests/test_ops_audit_report_writer.py`: verify report sections, image cap, retained-count note, and failed-image notice.
- Modify `backend/tests/test_ops_audit_phase2_modularization.py`: verify the rule engine persists and returns the manifest.

### Task 1: Archive visual evidence locally

**Files:**
- Create: `backend/app/services/ops_audit/visual_evidence.py`
- Create: `backend/tests/test_ops_audit_visual_evidence.py`

- [ ] **Step 1: Write failing tests for local copy, all-image retention, and de-duplication**

Create fixtures with one flow-photo issue and one multipoint issue whose `reviewed_images` contains four local images. Call `archive_visual_evidence` and assert:

```python
def test_archive_visual_evidence_keeps_all_images_and_reuses_duplicate_source(tmp_path: Path) -> None:
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    photos = []
    for index in range(4):
        photo = source_dir / f"curve-{index}.jpg"
        photo.write_bytes(f"image-{index}".encode())
        photos.append(photo)

    audit = _audit_with_visual_issues(
        flow_source=str(photos[0]),
        reviewed_images=[
            {"attachment_filename": photo.name, "attachment_local_path": str(photo)}
            for photo in photos
        ],
    )

    result = archive_visual_evidence(audit, tmp_path / "output")

    assert result["success_count"] == 5
    assert result["unique_file_count"] == 4
    assert Path(result["manifest_path"]).is_file()
    issues = audit["records"][0]["scoring_issues"]
    assert len(json.loads(issues[0]["evidence"])["evidence_images"]) == 1
    assert len(json.loads(issues[1]["evidence"])["evidence_images"]) == 4
    assert all(Path(item["local_path"]).is_file() for item in result["items"] if item["status"] == "success")
```

- [ ] **Step 2: Run the tests and verify RED**

Run:

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest -q backend/tests/test_ops_audit_visual_evidence.py
```

Expected: collection fails with `ModuleNotFoundError: app.services.ops_audit.visual_evidence`.

- [ ] **Step 3: Implement source extraction and local persistence**

Implement this public interface and focused helpers:

```python
def archive_visual_evidence(audit: dict[str, Any], output_dir: Path) -> dict[str, Any]:
    evidence_root = output_dir.resolve() / "visual_evidence"
    items: list[dict[str, Any]] = []
    persisted_by_source: dict[str, dict[str, Any]] = {}
    for record in audit.get("records", []):
        for issue in record.get("scoring_issues", []):
            evidence = _parse_evidence(issue.get("evidence"))
            if not _is_visual_finding(issue, evidence):
                continue
            archived = []
            for source_item in _image_sources(evidence):
                archived_item = _archive_one(
                    source_item,
                    evidence_root=evidence_root,
                    working_order_code=str(record.get("working_order_code") or evidence.get("working_order_code") or "unknown"),
                    rule_id=str(issue.get("rule_id") or "UNKNOWN_VISUAL_RULE"),
                    persisted_by_source=persisted_by_source,
                )
                archived.append(archived_item)
                items.append({
                    "working_order_code": record.get("working_order_code"),
                    "rule_id": issue.get("rule_id"),
                    **archived_item,
                })
            evidence["evidence_images"] = archived
            issue["evidence"] = json.dumps(evidence, ensure_ascii=False, default=str)
    manifest_path = evidence_root / "manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "item_count": len(items),
        "success_count": sum(item["status"] == "success" for item in items),
        "failed_count": sum(item["status"] == "failed" for item in items),
        "unique_file_count": len({item.get("local_path") for item in items if item.get("local_path")}),
        "items": items,
    }
    manifest_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return {**payload, "manifest_path": str(manifest_path)}
```

`_image_sources` must include the top-level `source`/attachment path and every item in `reviewed_images`; `_archive_one` must use safe path components plus a SHA-256 source suffix and reuse `persisted_by_source` for duplicate sources. Accept only `.jpg`, `.jpeg`, `.png`, `.bmp`, `.gif`, `.webp`, and `.heic`.

- [ ] **Step 4: Run the local archive tests and verify GREEN**

Run the Task 1 test command. Expected: all current tests pass.

- [ ] **Step 5: Write failing tests for attachment-root resolution, HTTP download, and failure degradation**

Add tests that set `OPS_ATTACHMENT_ROOT`, monkeypatch `requests.get`, and supply an unresolvable source. Assert `/WebFiles/...` resolves from the root before HTTP, HTTP content is saved when no local file exists, and a failed response produces an `evidence_images` entry with `status == "failed"` and a non-empty `error` without raising from `archive_visual_evidence`.

- [ ] **Step 6: Run the new tests and verify RED**

Expected: assertions fail because non-local source resolution is not implemented.

- [ ] **Step 7: Implement remote resolution and graceful failure**

Implement `_resolve_source` in this order:

```python
def _resolve_source(source: str) -> tuple[str, Path | str]:
    direct = Path(source).expanduser()
    if direct.is_file():
        return "local", direct.resolve()
    attachment_root = str(os.getenv("OPS_ATTACHMENT_ROOT") or os.getenv("ATTACHMENT_ROOT") or "").strip()
    if attachment_root:
        rooted = Path(attachment_root).expanduser() / source.lstrip("/")
        if rooted.is_file():
            return "local", rooted.resolve()
    if source.startswith(("http://", "https://")):
        return "remote", source
    base_url = str(os.getenv("OPS_ATTACHMENT_BASE_URL") or os.getenv("ATTACHMENT_BASE_URL") or "").strip()
    if source.startswith("/") and base_url:
        return "remote", urljoin(base_url.rstrip("/") + "/", source.lstrip("/"))
    raise FileNotFoundError(f"无法解析视觉证据来源: {source}")
```

Catch per-file exceptions in `_archive_one`, return `status="failed"`, preserve `source`/`filename`, and never abort the batch. Use `requests.get(url, timeout=30)` and `raise_for_status()` for remote sources.

- [ ] **Step 8: Run all visual evidence tests and verify GREEN**

Run the Task 1 test command. Expected: all tests pass.

- [ ] **Step 9: Commit Task 1**

```bash
git add backend/app/services/ops_audit/visual_evidence.py backend/tests/test_ops_audit_visual_evidence.py
git commit -m "feat: archive operations audit visual evidence"
```

### Task 2: Integrate evidence archiving with rule outputs

**Files:**
- Modify: `backend/app/services/ops_audit/rule_engine.py:28-90`
- Modify: `backend/app/services/ops_audit/final_issue_list.py:96-136`
- Modify: `backend/tests/test_ops_audit_final_issue_list.py`
- Modify: `backend/tests/test_ops_audit_phase2_modularization.py:480-490`

- [ ] **Step 1: Write a failing final-issue propagation test**

Add a confirmed visual issue containing successful and failed `evidence_images`, then assert:

```python
result = build_final_issue_list(audit)
assert result["items"][0]["evidence_images"] == evidence_images
```

Ensure the visual comparison has confidence `0.95`, a non-empty field, values, and unit so it qualifies for promotion.

- [ ] **Step 2: Run the propagation test and verify RED**

Run:

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest -q backend/tests/test_ops_audit_final_issue_list.py -k evidence_images
```

Expected: `KeyError: 'evidence_images'`.

- [ ] **Step 3: Pass image metadata through final issue items**

Add `"evidence_images"` to the existing key-copy tuple in `_issue_item`; do not modify issue inclusion or promotion rules.

- [ ] **Step 4: Run the propagation test and verify GREEN**

Run the Step 2 command. Expected: pass.

- [ ] **Step 5: Write a failing rule-engine integration test**

Monkeypatch `rule_engine.audit_dataset` to return an audit containing a local visual photo, and monkeypatch semantic builders to return empty results. Run `run_rule_engine(..., persist_outputs=True)` and assert:

```python
assert Path(result["visual_evidence_manifest_path"]).is_file()
assert result["visual_evidence_success_count"] == 1
persisted = json.loads(Path(result["audit_result_path"]).read_text(encoding="utf-8"))
evidence = json.loads(persisted["records"][0]["scoring_issues"][0]["evidence"])
assert Path(evidence["evidence_images"][0]["local_path"]).is_file()
```

- [ ] **Step 6: Run the integration test and verify RED**

Run:

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest -q backend/tests/test_ops_audit_phase2_modularization.py -k visual_evidence_manifest
```

Expected: result lacks `visual_evidence_manifest_path`.

- [ ] **Step 7: Call the archiver before final issue assembly**

In `run_rule_engine`, call:

```python
visual_evidence = archive_visual_evidence(audit, output_dir)
final_issue_list = build_final_issue_list(audit, semantic_review_results)
```

Return:

```python
"visual_evidence_manifest_path": visual_evidence["manifest_path"],
"visual_evidence_success_count": visual_evidence["success_count"],
"visual_evidence_failed_count": visual_evidence["failed_count"],
```

Keep manifest persistence enabled even when `persist_outputs=False`, because the archiver is required to materialize image evidence for the in-memory result; tests must use a temporary output directory.

- [ ] **Step 8: Run Task 2 tests and verify GREEN**

Run:

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest -q backend/tests/test_ops_audit_final_issue_list.py backend/tests/test_ops_audit_phase2_modularization.py
```

Expected: all tests pass.

- [ ] **Step 9: Commit Task 2**

```bash
git add backend/app/services/ops_audit/rule_engine.py backend/app/services/ops_audit/final_issue_list.py backend/tests/test_ops_audit_final_issue_list.py backend/tests/test_ops_audit_phase2_modularization.py
git commit -m "feat: expose visual evidence in audit outputs"
```

### Task 3: Embed confirmed and pending-review photos in reports

**Files:**
- Modify: `backend/app/services/ops_audit/report_writer.py:89-260`
- Modify: `backend/tests/test_ops_audit_report_writer.py`

- [ ] **Step 1: Write failing tests for confirmed issue images and the three-image cap**

Create four archived files below `tmp_path/visual_evidence/...`, pass them in one final issue's `evidence_images`, write `tmp_path/report.md`, and assert:

```python
assert text.count("![视觉证据：") == 3
assert "报告展示 3 张，证据包共保存 4 张" in text
assert "visual_evidence/WO-1/RULE/photo-0.jpg" in text
assert "photo-3.jpg" not in text
```

- [ ] **Step 2: Run the confirmed-image test and verify RED**

Run:

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest -q backend/tests/test_ops_audit_report_writer.py -k visual
```

Expected: the report contains no Markdown images.

- [ ] **Step 3: Render archived images under confirmed items**

Pass the report output path into the formatter and add helpers with these contracts:

```python
def _format_evidence_images(item: dict[str, Any], report_path: Path, limit: int = 3) -> list[str]:
    images = _evidence_images(item)
    successful = [image for image in images if image.get("status") == "success" and _existing_local_path(image)]
    lines = []
    for image in successful[:limit]:
        local_path = Path(str(image["local_path"])).resolve()
        relative = local_path.relative_to(report_path.parent.resolve()).as_posix()
        filename = str(image.get("filename") or local_path.name)
        lines.extend(["", f"![视觉证据：{filename}]({relative})"])
    if len(successful) > limit:
        lines.extend(["", f"> 报告展示 {limit} 张，证据包共保存 {len(successful)} 张。"])
    if not successful and any(image.get("status") == "failed" for image in images):
        error = next(str(image.get("error") or "未知原因") for image in images if image.get("status") == "failed")
        lines.extend(["", f"> 证据图片获取失败：{error}"])
    return lines
```

Only accept image paths located under the report parent directory; otherwise show a failure notice instead of creating an escaping reference.

- [ ] **Step 4: Run confirmed-image test and verify GREEN**

Run the Step 2 command. Expected: confirmed visual image test passes.

- [ ] **Step 5: Write failing tests for pending-review separation and failed images**

Build an audit record with:

- one multipoint `ISSUE_REVIEW` item containing a successful archived image;
- one `INSUFFICIENT_EVIDENCE` item containing only a failed image;
- neither item present in `final_issue_list`.

Assert the report contains `## 视觉待人工复核`, both classifications, the first image reference, and `证据图片获取失败` for the second item. Assert neither item is listed under the confirmed issue count.

- [ ] **Step 6: Run pending-review tests and verify RED**

Expected: the pending-review section is absent.

- [ ] **Step 7: Add pending visual-review collection and rendering**

Implement `_collect_pending_visual_reviews(audit, final_issue_list)` using current `scoring_issues`. Select issues with archived `evidence_images` and one of:

- `needs_visual_review is True`;
- `needs_manual_review is True`;
- `rule_id == "ATTACHMENT_FLOW_VISUAL_ERROR"`.

Exclude an issue if its `(working_order_code, rule_id, field, message)` key already exists in `final_issue_list.items`. Render the remaining entries under `## 视觉待人工复核`, grouped by operation unit, and reuse `_format_evidence_images` with limit 3.

- [ ] **Step 8: Run all report writer tests and verify GREEN**

Run:

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest -q backend/tests/test_ops_audit_report_writer.py
```

Expected: all tests pass.

- [ ] **Step 9: Commit Task 3**

```bash
git add backend/app/services/ops_audit/report_writer.py backend/tests/test_ops_audit_report_writer.py
git commit -m "feat: embed visual evidence in audit reports"
```

### Task 4: Regression and package-level verification

**Files:**
- Verify only; modify prior files only if a failing regression exposes an in-scope defect.

- [ ] **Step 1: Run the focused audit test suite**

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest -q \
  backend/tests/test_ops_audit_visual_evidence.py \
  backend/tests/test_ops_audit_report_writer.py \
  backend/tests/test_ops_audit_final_issue_list.py \
  backend/tests/test_ops_audit_phase2_modularization.py \
  backend/app/services/ops_work_order_audit_engine_test.py \
  backend/app/services/ops_audit/semantic/test_reviewer.py
```

Expected: all selected tests pass with zero failures.

- [ ] **Step 2: Run static syntax validation**

```bash
conda run -p /root/miniconda3/envs/backend_py311 python -m compileall -q \
  backend/app/services/ops_audit/visual_evidence.py \
  backend/app/services/ops_audit/rule_engine.py \
  backend/app/services/ops_audit/final_issue_list.py \
  backend/app/services/ops_audit/report_writer.py
```

Expected: exit code 0 and no output.

- [ ] **Step 3: Run a deterministic local end-to-end fixture**

Use a pytest integration fixture that runs the rule engine with a monkeypatched visual audit result and then calls `write_report` with the returned audit/final issue list. Assert the manifest, archived files, final issue JSON, report image references, and three-image cap all agree.

Run:

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest -q backend/tests/test_ops_audit_visual_evidence.py -k end_to_end
```

Expected: pass.

- [ ] **Step 4: Check formatting and repository diff**

```bash
git diff --check
git status --short
```

Expected: no whitespace errors; only intended implementation/test files and the pre-existing unrelated `NormCraftAI/` entry appear.

- [ ] **Step 5: Commit any final in-scope correction**

If verification required an in-scope correction, commit only the affected audit files:

```bash
git add backend/app/services/ops_audit backend/tests/test_ops_audit_*.py
git commit -m "test: verify audit visual evidence reporting"
```

Do not add or modify the unrelated `NormCraftAI/` worktree content.
