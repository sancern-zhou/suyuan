# Tender Information Fetcher Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a scheduled tender information fetcher that runs daily at 06:30, collects previous-day Qianlima tender/winning-bid notices for the approved keywords, filters and cleans details, and stores candidates, notices, and run summaries in SQL Server.

**Architecture:** Keep tender crawling and extraction logic in `backend/app/services/tenders/`, add a SQL Server repository backed by the existing `settings.sqlserver_connection_string`, and expose the workflow through `TenderInformationFetcher` in `backend/app/fetchers/tenders/`. Register the fetcher with the existing APScheduler-based fetcher lifecycle so scheduled and manual trigger paths work consistently.

**Tech Stack:** Python 3.11, FastAPI backend conventions, APScheduler, pyodbc, Playwright, OpenAI-compatible LLM client, pytest.

---

### Task 1: Tender Service Module And Config

**Files:**
- Create: `backend/app/services/tenders/__init__.py`
- Create: `backend/app/services/tenders/models.py`
- Create: `backend/app/services/tenders/filters.py`
- Create: `backend/app/services/tenders/extractor.py`
- Create: `backend/app/services/tenders/llm.py`
- Create: `backend/app/services/tenders/qianlima_client.py`
- Create: `backend/app/services/tenders/pipeline.py`
- Create: `backend/app/services/tenders/config.py`
- Modify: `backend/config/settings.py`
- Test: `backend/tests/services/tenders/test_tender_config.py`

- [ ] **Step 1: Write failing config tests**

Create `backend/tests/services/tenders/test_tender_config.py` with tests for default keywords, notice types, schedule, and previous-day target date.

- [ ] **Step 2: Run config tests and verify failure**

Run: `conda run -p /root/miniconda3/envs/backend_py311 pytest backend/tests/services/tenders/test_tender_config.py -q`
Expected: FAIL because `app.services.tenders.config` does not exist.

- [ ] **Step 3: Add service package and config**

Copy the existing tender service modules from `Bidding-Information-Crawling/src/tenders/` into `backend/app/services/tenders/`, then add `config.py` with `TenderFetcherConfig`, `parse_keywords`, `parse_notice_types`, and `default_target_date`.

- [ ] **Step 4: Add settings fields**

Add tender fetcher, Qianlima, and tender LLM settings to `backend/config/settings.py` with the approved defaults.

- [ ] **Step 5: Run config tests and verify pass**

Run: `conda run -p /root/miniconda3/envs/backend_py311 pytest backend/tests/services/tenders/test_tender_config.py -q`
Expected: PASS.

### Task 2: SQL Server Repository And Migration

**Files:**
- Create: `backend/app/services/tenders/repository.py`
- Create: `backend/migrations/create_tender_information_tables.sql`
- Test: `backend/tests/services/tenders/test_sqlserver_repository.py`
- Test: `backend/tests/services/tenders/test_tender_migration_sql.py`

- [ ] **Step 1: Write failing repository tests**

Create tests using fake pyodbc connection/cursor objects to verify candidate insert de-duplicates by rowcount, candidate decision update writes accepted/rejected status, notice upsert updates then inserts when needed, and run summaries are finalized.

- [ ] **Step 2: Write failing migration SQL test**

Create a text-based test that asserts the SQL migration contains `tender_candidates`, `tender_notices`, `tender_fetch_runs`, and unique URL indexes.

- [ ] **Step 3: Run repository tests and verify failure**

Run: `conda run -p /root/miniconda3/envs/backend_py311 pytest backend/tests/services/tenders/test_sqlserver_repository.py backend/tests/services/tenders/test_tender_migration_sql.py -q`
Expected: FAIL because repository and migration do not exist.

- [ ] **Step 4: Implement SQL Server repository**

Implement `SQLServerTenderRepository` with `candidate_exists`, `save_candidate`, `update_candidate_decision`, `save_notice`, `create_run`, and `finish_run`. Use `UPDATE` then `INSERT` for notice upsert rather than `MERGE`.

- [ ] **Step 5: Add migration SQL**

Create the three SQL Server tables and indexes from the approved design.

- [ ] **Step 6: Run repository tests and verify pass**

Run: `conda run -p /root/miniconda3/envs/backend_py311 pytest backend/tests/services/tenders/test_sqlserver_repository.py backend/tests/services/tenders/test_tender_migration_sql.py -q`
Expected: PASS.

### Task 3: Fetcher Wrapper And Registration

**Files:**
- Create: `backend/app/fetchers/tenders/__init__.py`
- Create: `backend/app/fetchers/tenders/tender_information_fetcher.py`
- Modify: `backend/app/services/lifecycle_manager.py`
- Modify: `backend/app/fetchers/__init__.py`
- Test: `backend/tests/fetchers/test_tender_information_fetcher.py`
- Test: `backend/tests/fetchers/test_tender_fetcher_registration.py`

- [ ] **Step 1: Write failing fetcher tests**

Create tests that verify the fetcher name, description, schedule, default target date, configured keywords/types, disabled mode, and that `fetch_and_store` records run summary when the pipeline returns errors.

- [ ] **Step 2: Write failing registration tests**

Create tests that monkeypatch the scheduler register method and verify `TenderInformationFetcher` is registered by both lifecycle initialization and `create_scheduler()`.

- [ ] **Step 3: Run fetcher tests and verify failure**

Run: `conda run -p /root/miniconda3/envs/backend_py311 pytest backend/tests/fetchers/test_tender_information_fetcher.py backend/tests/fetchers/test_tender_fetcher_registration.py -q`
Expected: FAIL because the fetcher does not exist.

- [ ] **Step 4: Implement fetcher**

Implement `TenderInformationFetcher` so it builds `QianlimaClient`, `SQLServerTenderRepository`, optional `OpenAICompatibleTenderLLMClient`, and `TenderPipeline`; computes yesterday as target date; creates and finalizes run summaries.

- [ ] **Step 5: Register fetcher**

Import and register `TenderInformationFetcher` in `backend/app/services/lifecycle_manager.py` and `backend/app/fetchers/__init__.py`.

- [ ] **Step 6: Run fetcher tests and verify pass**

Run: `conda run -p /root/miniconda3/envs/backend_py311 pytest backend/tests/fetchers/test_tender_information_fetcher.py backend/tests/fetchers/test_tender_fetcher_registration.py -q`
Expected: PASS.

### Task 4: Real Integration Test Entry Points

**Files:**
- Create: `backend/tests/integration/test_tender_real_qianlima_llm.py`
- Modify: `docs/superpowers/specs/2026-07-01-tender-information-fetcher-design.md`

- [ ] **Step 1: Write integration test**

Create an opt-in integration test that requires `RUN_TENDER_REAL_INTEGRATION=1`, a real LLM key, and network access. It should run one keyword, one notice type, one page, and assert at least that the pipeline reaches the external services without fake clients.

- [ ] **Step 2: Update spec test strategy**

Revise the spec to state that unit tests isolate external dependencies, while real Qianlima and real LLM coverage is provided by explicit integration tests.

- [ ] **Step 3: Run skipped integration test by default**

Run: `conda run -p /root/miniconda3/envs/backend_py311 pytest backend/tests/integration/test_tender_real_qianlima_llm.py -q`
Expected: SKIPPED unless `RUN_TENDER_REAL_INTEGRATION=1` and credentials are present.

### Task 5: Verification

**Files:**
- All files changed above.

- [ ] **Step 1: Run focused tender tests**

Run: `conda run -p /root/miniconda3/envs/backend_py311 pytest backend/tests/services/tenders backend/tests/fetchers/test_tender_information_fetcher.py backend/tests/fetchers/test_tender_fetcher_registration.py backend/tests/integration/test_tender_real_qianlima_llm.py -q`
Expected: PASS for unit tests, integration test skipped unless explicitly enabled.

- [ ] **Step 2: Check git diff**

Run: `git status --short && git diff --stat`
Expected: only tender integration files, registration changes, settings, migration, plan, and spec update.

- [ ] **Step 3: Commit implementation**

Run: `git add ... && git commit -m "feat: add tender information fetcher"`
Expected: commit created on `feat/tender-information-fetcher`.
