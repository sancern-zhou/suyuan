# Online LLM Chunking Failover Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make online intelligent document chunking use the shared `LLMService` fallback chain instead of a direct single-provider HTTP request.

**Architecture:** Keep `DocumentProcessor._call_llm_api()` and its `str` return contract stable. Replace only `_call_online_llm()` with an adapter around the existing non-streaming shared LLM service, so provider selection, `LLM_FALLBACKS`, cooldown, concurrency and timeouts remain owned by `LLMService`; retain the current sentence fallback above this boundary.

**Tech Stack:** Python 3.11, asyncio, pytest, pytest-asyncio, existing `LLMService` and `llm_failover` utilities.

---

### Task 1: Lock the online chunking service boundary with tests

**Files:**
- Modify: `backend/tests/knowledge_base/test_document_processor.py`
- Inspect: `backend/app/services/llm_service.py`

- [ ] **Step 1: Write a failing online delegation test**

Add a test that injects a fake shared LLM service into `DocumentProcessor`, calls `_call_online_llm("prompt")`, and asserts that the service receives the JSON-only system/user messages and returns raw text. It must fail because the current implementation has no injectable service boundary.

```python
@pytest.mark.asyncio
async def test_online_chunking_delegates_to_shared_llm_service():
    service = FakeTextLLMService(result='{"chunks": []}')
    processor = DocumentProcessor(llm_service=service)
    result = await processor._call_online_llm("split this document")
    assert result == '{"chunks": []}'
    assert service.calls[0]["messages"][1]["content"] == "split this document"
```

- [ ] **Step 2: Run the focused test and verify RED**

Run `/root/miniconda3/envs/backend_py311/bin/python -m pytest backend/tests/knowledge_base/test_document_processor.py::test_online_chunking_delegates_to_shared_llm_service -q`.

Expected: FAIL because `DocumentProcessor.__init__` does not accept `llm_service` or the method bypasses it.

- [ ] **Step 3: Confirm the correct existing LLMService text method**

Read the complete public non-streaming text method and its tests. Select the method already wrapped by the shared candidate fallback logic; do not implement another fallback loop in `DocumentProcessor`.

### Task 2: Replace direct online HTTP with the shared service

**Files:**
- Modify: `backend/app/knowledge_base/document_processor.py`
- Modify: `backend/tests/knowledge_base/test_document_processor.py`

- [ ] **Step 1: Add the minimal injectable service dependency**

Extend initialization without breaking existing callers and create the default service lazily:

```python
def __init__(self, *, llm_service=None):
    self._llm_service = llm_service
    # retain the existing initialization fields
```

- [ ] **Step 2: Implement online delegation**

Remove the online provider switch, direct environment reads, fixed 300-second client and local retry loop. Build the existing JSON-only system instruction plus user prompt, invoke the shared non-streaming text method with temperature `0.1`, and return assistant content as `str`.

- [ ] **Step 3: Run the focused delegation test and verify GREEN**

Run the focused command from Task 1. Expected: PASS.

- [ ] **Step 4: Add and run a local-mode regression test**

Verify `_call_llm_api(prompt, "local")` still delegates to `_call_local_llm` and does not instantiate the shared online service. Expected: PASS.

### Task 3: Prove candidate failover and terminal sentence fallback

**Files:**
- Modify: `backend/tests/knowledge_base/test_document_processor.py`
- Optionally modify only if an observed failing test requires it: `backend/app/services/llm_service.py`

- [ ] **Step 1: Add a failover integration-style test**

Use the real `LLMService` fallback loop with provider requests patched at the transport boundary: make the configured primary raise `httpx.ConnectError`, make the next candidate return valid chunk JSON, and assert candidate order plus successful result. Avoid mocking `_call_online_llm` itself.

- [ ] **Step 2: Run the failover test**

Run `/root/miniconda3/envs/backend_py311/bin/python -m pytest backend/tests/knowledge_base/test_document_processor.py -k "online_chunking or failover" -q`.

Expected: PASS, with primary failure followed by fallback success.

- [ ] **Step 3: Add an all-candidates-fail sentence fallback test**

Call the public chunking path with `strategy="llm"` and `llm_mode="online"`, make the shared service exhaust candidates, and assert returned chunks use the sentence strategy rather than propagating an upload failure.

- [ ] **Step 4: Run the document processor suite**

Run `/root/miniconda3/envs/backend_py311/bin/python -m pytest backend/tests/knowledge_base/test_document_processor.py -q`. Expected: all tests PASS.

### Task 4: Regression verification and commit

**Files:**
- Verify: `backend/app/knowledge_base/document_processor.py`
- Verify: `backend/tests/knowledge_base/test_document_processor.py`

- [ ] **Step 1: Run knowledge-base regression tests**

Run `/root/miniconda3/envs/backend_py311/bin/python -m pytest backend/tests/knowledge_base -q`. Expected: all knowledge-base tests PASS.

- [ ] **Step 2: Run shared failover tests**

Locate exact modules using `rg --files backend/tests | rg 'llm.*(failover|service)'`, then run the relevant failover and LLM service modules. Expected: all selected tests PASS.

- [ ] **Step 3: Validate syntax and diff**

Run `/root/miniconda3/envs/backend_py311/bin/python -m compileall -q backend/app/knowledge_base backend/app/services` and `git diff --check`. Expected: exit code 0.

- [ ] **Step 4: Commit the implementation**

Stage only `document_processor.py` and its focused tests, then commit with message `fix: 智能分块接入统一 LLM 故障切换`.
