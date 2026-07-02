# Lightweight Tender Candidate Screening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make tender candidate pre-screening faster by batching 50 list-page candidates and asking the LLM to return only retained candidate indexes.

**Architecture:** Keep the existing pipeline and detail review flow. Change only the batch candidate prompt/response protocol in `OpenAICompatibleTenderLLMClient.review_candidates`, mapping returned indexes back to accepted candidates and marking omitted candidates as rejected by the pipeline fallback behavior.

**Tech Stack:** Python 3.11, pytest, existing OpenAI-compatible GLM client.

---

### Task 1: Lightweight Batch Output Protocol

**Files:**
- Modify: `backend/app/services/tenders/llm.py`
- Test: `backend/tests/services/tenders/test_tender_llm_config.py`

- [ ] **Step 1: Write failing tests**

Add tests that assert `_candidate_batch_prompt` requests a compact `keep` array, omits verbose decision schemas, and truncates list text.

- [ ] **Step 2: Verify tests fail**

Run: `conda run -n backend_py311 pytest backend/tests/services/tenders/test_tender_llm_config.py -q`

- [ ] **Step 3: Implement minimal code**

Change `_candidate_batch_prompt` to emit compact candidate rows using `i`, `t`, `n`, and optional truncated `x`; change `review_candidates` to parse either `{"keep":[...]}` or `[ ... ]` and return accepted decisions only.

- [ ] **Step 4: Verify tests pass**

Run: `conda run -n backend_py311 pytest backend/tests/services/tenders/test_tender_llm_config.py -q`

### Task 2: Default Batch Size

**Files:**
- Modify: `backend/app/services/tenders/pipeline.py`
- Test: `backend/tests/services/tenders/test_tender_config.py`

- [ ] **Step 1: Write failing test**

Add or update a test asserting the default LLM candidate batch size is 50 when `TENDER_LLM_BATCH_SIZE` is unset.

- [ ] **Step 2: Verify test fails**

Run: `conda run -n backend_py311 pytest backend/tests/services/tenders/test_tender_config.py -q`

- [ ] **Step 3: Implement minimal code**

Change the default in `_initial_decisions` from `20` to `50`.

- [ ] **Step 4: Verify focused tender tests**

Run: `conda run -n backend_py311 pytest backend/tests/services/tenders backend/tests/fetchers/test_tender_information_fetcher.py -q`

### Task 3: Real Flow Smoke Check

**Files:**
- No code changes expected.

- [ ] **Step 1: Run a controlled real flow**

Run a small real Qianlima + GLM flow with one keyword, one notice type, and one page so the new compact protocol is exercised without triggering a large daily run.

- [ ] **Step 2: Inspect database effect**

Confirm the run finishes and either stores accepted notices or records rejected candidates without hanging in the initial screening stage.
