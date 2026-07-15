# System SSE Heartbeat Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a transparent, standards-compliant 15-second heartbeat to every SSE endpoint without creating Agent events, frontend messages, or persisted conversation records.

**Architecture:** Introduce one `app.core.sse.create_sse_response()` factory backed by compatibility-pinned `sse-starlette`. Existing route generators remain business-only and their pre-serialized SSE frames are converted to bytes for unchanged transmission; `EventSourceResponse` independently owns ping, disconnect, send-timeout, and shutdown behavior.

**Tech Stack:** Python 3.11, FastAPI 0.115.0, Starlette 0.38.6, AnyIO 4.12.0, `sse-starlette==2.4.1`, pytest, pytest-asyncio, Nginx 1.27.

---

## File map

- Create `backend/app/core/sse.py`: the only application-level SSE response factory and legacy-frame adapter.
- Create `backend/tests/core/test_sse.py`: settings, frame compatibility, heartbeat, disconnect, and send-timeout tests.
- Create `backend/tests/test_sse_architecture.py`: enforce that application routes cannot construct raw SSE `StreamingResponse` objects.
- Create `backend/tests/api/test_sse_route_responses.py`: lightweight response-contract tests for report and expert-deliberation factories.
- Modify `backend/config/settings.py`: global heartbeat and send-timeout settings.
- Modify `backend/requirements.txt`: compatibility-pin `sse-starlette`.
- Modify `backend/app/routers/agent.py`: use the central SSE factory.
- Modify `backend/app/routers/knowledge_qa.py`: use the central SSE factory.
- Modify `backend/app/routers/report_generation.py`: use the central SSE factory while retaining `JSONResponse` for non-SSE responses.
- Modify `backend/app/routers/expert_deliberation.py`: use the central SSE factory.
- Modify `backend/tests/api/test_agent_conversation_access.py`: assert the Agent route returns the system SSE response contract.
- Modify `backend/tests/api/test_authenticated_knowledge_routes.py`: assert the knowledge route returns the system SSE response contract.

All commands below run from `/home/xckj/suyuan/backend` in the required environment.

### Task 1: Pin the SSE dependency and define global settings

**Files:**

- Modify: `backend/requirements.txt`
- Modify: `backend/config/settings.py`
- Create: `backend/tests/core/test_sse.py`

- [ ] **Step 1: Write failing settings tests**

Create `tests/core/test_sse.py` with:

```python
from config.settings import Settings


def test_sse_transport_defaults():
    config = Settings(_env_file=None)

    assert config.sse_heartbeat_interval_seconds == 15.0
    assert config.sse_send_timeout_seconds == 30.0


def test_sse_transport_settings_load_from_environment(monkeypatch):
    monkeypatch.setenv("SSE_HEARTBEAT_INTERVAL_SECONDS", "22.5")
    monkeypatch.setenv("SSE_SEND_TIMEOUT_SECONDS", "45")

    config = Settings(_env_file=None)

    assert config.sse_heartbeat_interval_seconds == 22.5
    assert config.sse_send_timeout_seconds == 45.0
```

- [ ] **Step 2: Run the tests and verify the missing settings**

Run:

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest tests/core/test_sse.py -q
```

Expected: both tests fail with `AttributeError` for `sse_heartbeat_interval_seconds` or validation errors indicating the fields do not exist.

- [ ] **Step 3: Add the dependency pin and settings fields**

Add under `# Core Framework` in `requirements.txt`:

```text
sse-starlette==2.4.1
```

Add after the server configuration fields in `config/settings.py`:

```python
    # System SSE transport configuration
    sse_heartbeat_interval_seconds: float = Field(
        default=15.0,
        gt=0,
        description="Interval between transparent SSE comment heartbeats",
    )
    sse_send_timeout_seconds: float = Field(
        default=30.0,
        gt=0,
        description="Maximum duration of one SSE socket send operation",
    )
```

- [ ] **Step 4: Install the compatibility-pinned dependency**

Run:

```bash
conda run -p /root/miniconda3/envs/backend_py311 python -m pip install sse-starlette==2.4.1
```

Expected: installation succeeds without changing FastAPI 0.115.0, Starlette 0.38.6, or AnyIO 4.12.0.

Verify versions:

```bash
conda run -p /root/miniconda3/envs/backend_py311 python -c "from importlib.metadata import version; assert version('sse-starlette') == '2.4.1'; assert version('fastapi') == '0.115.0'; assert version('starlette') == '0.38.6'; print('compatible')"
```

Expected: `compatible`.

- [ ] **Step 5: Run the settings tests**

Run:

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest tests/core/test_sse.py -q
```

Expected: `2 passed`.

- [ ] **Step 6: Commit the dependency and settings contract**

```bash
git add requirements.txt config/settings.py tests/core/test_sse.py
git commit -m "chore: configure system SSE transport"
```

### Task 2: Preserve existing pre-serialized SSE frames

**Files:**

- Create: `backend/app/core/sse.py`
- Modify: `backend/tests/core/test_sse.py`

- [ ] **Step 1: Add failing frame-adapter tests**

Add `import pytest` to the import block at the top of `tests/core/test_sse.py`, then append:

```python
from app.core.sse import _encode_sse_frames


async def _collect(source):
    return [item async for item in source]


@pytest.mark.asyncio
async def test_encode_sse_frames_preserves_existing_wire_format():
    async def source():
        yield 'data: {"type":"start"}\n\n'
        yield b'data: {"type":"complete"}\n\n'
        yield bytearray(b": existing-comment\n\n")
        yield memoryview(b'data: {"type":"final"}\n\n')

    frames = await _collect(_encode_sse_frames(source()))

    assert frames == [
        b'data: {"type":"start"}\n\n',
        b'data: {"type":"complete"}\n\n',
        b": existing-comment\n\n",
        b'data: {"type":"final"}\n\n',
    ]


@pytest.mark.asyncio
async def test_encode_sse_frames_rejects_non_wire_values():
    async def source():
        yield {"data": "not pre-serialized"}

    with pytest.raises(TypeError, match="SSE source must yield str or bytes-like frames"):
        await _collect(_encode_sse_frames(source()))
```

- [ ] **Step 2: Run the adapter tests and verify the import failure**

Run:

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest tests/core/test_sse.py -q
```

Expected: collection fails because `app.core.sse` does not exist.

- [ ] **Step 3: Implement the focused frame adapter**

Create `app/core/sse.py`:

```python
"""Shared transport policy for every Server-Sent Events response."""

from __future__ import annotations

from collections.abc import AsyncIterable, AsyncIterator
from typing import TypeAlias


SSEFrame: TypeAlias = str | bytes | bytearray | memoryview


async def _encode_sse_frames(source: AsyncIterable[SSEFrame]) -> AsyncIterator[bytes]:
    """Encode legacy complete SSE frames without adding another ``data:`` layer."""

    async for frame in source:
        if isinstance(frame, str):
            yield frame.encode("utf-8")
            continue
        if isinstance(frame, (bytes, bytearray, memoryview)):
            yield bytes(frame)
            continue
        raise TypeError(
            "SSE source must yield str or bytes-like frames, "
            f"got {type(frame).__name__}"
        )
```

- [ ] **Step 4: Run the adapter tests**

Run:

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest tests/core/test_sse.py -q
```

Expected: `4 passed`.

- [ ] **Step 5: Commit the compatibility adapter**

```bash
git add app/core/sse.py tests/core/test_sse.py
git commit -m "feat: preserve existing SSE wire frames"
```

### Task 3: Implement the system EventSourceResponse factory

**Files:**

- Modify: `backend/app/core/sse.py`
- Modify: `backend/tests/core/test_sse.py`

- [ ] **Step 1: Add failing factory-policy tests**

Add these imports to the import block at the top of `tests/core/test_sse.py`:

```python
from sse_starlette import EventSourceResponse

from app.core.sse import create_sse_response
```

Then append:

```python
def test_create_sse_response_applies_system_transport_policy():
    async def source():
        yield 'data: {"type":"complete"}\n\n'

    response = create_sse_response(
        source(),
        heartbeat_interval_seconds=0.05,
        send_timeout_seconds=0.25,
        headers={"X-Route-Name": "test", "Cache-Control": "public"},
    )

    assert isinstance(response, EventSourceResponse)
    assert response.media_type == "text/event-stream"
    assert response.ping_interval == 0.05
    assert response.send_timeout == 0.25
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["connection"] == "keep-alive"
    assert response.headers["x-accel-buffering"] == "no"
    assert response.headers["x-route-name"] == "test"
    assert response.ping_message_factory().encode() == b": keepalive\r\n\r\n"
```

- [ ] **Step 2: Run the policy test and verify the missing factory**

Run:

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest tests/core/test_sse.py::test_create_sse_response_applies_system_transport_policy -q
```

Expected: collection fails because `create_sse_response` is not defined.

- [ ] **Step 3: Implement the central factory**

Replace `app/core/sse.py` with:

```python
"""Shared transport policy for every Server-Sent Events response."""

from __future__ import annotations

from collections.abc import AsyncIterable, AsyncIterator, Mapping
from typing import TypeAlias

from sse_starlette import EventSourceResponse, ServerSentEvent

from config.settings import settings


SSEFrame: TypeAlias = str | bytes | bytearray | memoryview


async def _encode_sse_frames(source: AsyncIterable[SSEFrame]) -> AsyncIterator[bytes]:
    """Encode legacy complete SSE frames without adding another ``data:`` layer."""

    async for frame in source:
        if isinstance(frame, str):
            yield frame.encode("utf-8")
            continue
        if isinstance(frame, (bytes, bytearray, memoryview)):
            yield bytes(frame)
            continue
        raise TypeError(
            "SSE source must yield str or bytes-like frames, "
            f"got {type(frame).__name__}"
        )


def _keepalive_comment() -> ServerSentEvent:
    return ServerSentEvent(comment="keepalive")


def create_sse_response(
    source: AsyncIterable[SSEFrame],
    *,
    heartbeat_interval_seconds: float | None = None,
    send_timeout_seconds: float | None = None,
    headers: Mapping[str, str] | None = None,
) -> EventSourceResponse:
    """Build an SSE response whose heartbeats stay outside business event streams."""

    response_headers = dict(headers or {})
    response_headers.update(
        {
            "Cache-Control": "no-store",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )
    return EventSourceResponse(
        _encode_sse_frames(source),
        ping=(
            settings.sse_heartbeat_interval_seconds
            if heartbeat_interval_seconds is None
            else heartbeat_interval_seconds
        ),
        ping_message_factory=_keepalive_comment,
        send_timeout=(
            settings.sse_send_timeout_seconds
            if send_timeout_seconds is None
            else send_timeout_seconds
        ),
        headers=response_headers,
    )
```

- [ ] **Step 4: Run the policy and adapter tests**

Run:

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest tests/core/test_sse.py -q
```

Expected: `5 passed`.

- [ ] **Step 5: Add failing ASGI lifecycle tests**

Add `import asyncio` to the import block at the top of `tests/core/test_sse.py`, then append:

```python
def _http_scope():
    return {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": "/events",
        "raw_path": b"/events",
        "query_string": b"",
        "root_path": "",
        "headers": [],
        "client": ("test", 1234),
        "server": ("test", 80),
    }


@pytest.mark.asyncio
async def test_idle_stream_sends_comment_heartbeat_and_cleans_up_on_disconnect():
    source_cleaned = asyncio.Event()
    disconnect = asyncio.Event()
    sent = []

    async def source():
        try:
            await asyncio.Event().wait()
            yield b"unreachable"
        finally:
            source_cleaned.set()

    async def receive():
        await disconnect.wait()
        return {"type": "http.disconnect"}

    async def send(message):
        sent.append(message)
        if message["type"] == "http.response.body" and message.get("body", b"").startswith(
            b": keepalive"
        ):
            disconnect.set()

    response = create_sse_response(
        source(),
        heartbeat_interval_seconds=0.01,
        send_timeout_seconds=0.25,
    )
    await asyncio.wait_for(response(_http_scope(), receive, send), timeout=1)

    bodies = [message.get("body", b"") for message in sent]
    assert any(body.startswith(b": keepalive") for body in bodies)
    await asyncio.wait_for(source_cleaned.wait(), timeout=1)


@pytest.mark.asyncio
async def test_business_frames_are_sent_once_and_in_order():
    sent = []

    async def source():
        yield 'data: {"type":"start"}\n\n'
        yield 'data: {"type":"complete"}\n\n'

    async def receive():
        await asyncio.Event().wait()

    async def send(message):
        sent.append(message)

    response = create_sse_response(
        source(),
        heartbeat_interval_seconds=10,
        send_timeout_seconds=0.25,
    )
    await asyncio.wait_for(response(_http_scope(), receive, send), timeout=1)

    bodies = [
        message.get("body", b"")
        for message in sent
        if message["type"] == "http.response.body" and message.get("body")
    ]
    assert bodies == [
        b'data: {"type":"start"}\n\n',
        b'data: {"type":"complete"}\n\n',
    ]


@pytest.mark.asyncio
async def test_source_exception_terminates_the_response():
    async def source():
        raise RuntimeError("source exploded")
        yield b"unreachable"

    async def receive():
        await asyncio.Event().wait()

    async def send(message):
        return None

    response = create_sse_response(
        source(),
        heartbeat_interval_seconds=10,
        send_timeout_seconds=0.25,
    )
    with pytest.raises(BaseException) as exc:
        await asyncio.wait_for(response(_http_scope(), receive, send), timeout=1)

    assert "source exploded" in repr(exc.value)


@pytest.mark.asyncio
async def test_stalled_socket_send_times_out_and_closes_source():
    source_cleaned = asyncio.Event()

    async def source():
        try:
            yield b'data: {"type":"start"}\n\n'
            await asyncio.Event().wait()
        finally:
            source_cleaned.set()

    async def receive():
        await asyncio.Event().wait()

    async def send(message):
        if message["type"] == "http.response.body" and message.get("body"):
            await asyncio.Event().wait()

    response = create_sse_response(
        source(),
        heartbeat_interval_seconds=10,
        send_timeout_seconds=0.01,
    )
    with pytest.raises(BaseException) as exc:
        await asyncio.wait_for(response(_http_scope(), receive, send), timeout=1)

    assert "SendTimeoutError" in repr(exc.value)
    await asyncio.wait_for(source_cleaned.wait(), timeout=1)
```

- [ ] **Step 6: Run the lifecycle tests**

Run:

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest tests/core/test_sse.py -q
```

Expected: `9 passed`. If the compatibility-pinned library exposes a cancellation defect with Starlette 0.38.6, stop and resolve the version compatibility before migrating routes; do not replace the lifecycle with per-route timers.

- [ ] **Step 7: Commit the system response factory**

```bash
git add app/core/sse.py tests/core/test_sse.py
git commit -m "feat: add system SSE heartbeat response"
```

### Task 4: Enforce system-wide SSE construction and migrate all routes

**Files:**

- Create: `backend/tests/test_sse_architecture.py`
- Modify: `backend/app/routers/agent.py`
- Modify: `backend/app/routers/knowledge_qa.py`
- Modify: `backend/app/routers/report_generation.py`
- Modify: `backend/app/routers/expert_deliberation.py`

- [ ] **Step 1: Write the failing architecture guard**

Create `tests/test_sse_architecture.py`:

```python
import ast
from pathlib import Path


APP_ROOT = Path(__file__).resolve().parents[1] / "app"
SSE_ROUTES = {
    Path("routers/agent.py"),
    Path("routers/knowledge_qa.py"),
    Path("routers/report_generation.py"),
    Path("routers/expert_deliberation.py"),
}


def _raw_sse_streaming_response_lines(path: Path) -> list[int]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    lines = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        function_name = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
        if function_name != "StreamingResponse":
            continue
        for keyword in node.keywords:
            if (
                keyword.arg == "media_type"
                and isinstance(keyword.value, ast.Constant)
                and keyword.value.value == "text/event-stream"
            ):
                lines.append(node.lineno)
    return lines


def test_application_has_no_raw_sse_streaming_responses():
    violations = {
        str(path.relative_to(APP_ROOT)): lines
        for path in APP_ROOT.rglob("*.py")
        if "deprecated" not in path.relative_to(APP_ROOT).parts
        if (lines := _raw_sse_streaming_response_lines(path))
    }

    assert violations == {}


def test_every_current_sse_route_uses_the_system_factory():
    for relative_path in SSE_ROUTES:
        source = (APP_ROOT / relative_path).read_text(encoding="utf-8")
        assert "from app.core.sse import create_sse_response" in source
        assert "create_sse_response(" in source
```

- [ ] **Step 2: Run the architecture test and verify all four violations**

Run:

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest tests/test_sse_architecture.py -q
```

Expected: failure lists raw SSE `StreamingResponse` calls in exactly the four current route files. The retired `app/deprecated` tree is intentionally excluded because it is not registered runtime code.

- [ ] **Step 3: Migrate the Agent route**

In `app/routers/agent.py`, remove:

```python
from fastapi.responses import StreamingResponse
```

Add:

```python
from app.core.sse import create_sse_response
```

Replace the SSE response construction with:

```python
        return create_sse_response(event_generator())
```

Do not move heartbeat comments through the existing `async for event in agent.analyze(...)` loop.

- [ ] **Step 4: Migrate the knowledge QA route**

In `app/routers/knowledge_qa.py`, remove the `StreamingResponse` import, add:

```python
from app.core.sse import create_sse_response
```

Replace the SSE response construction with:

```python
        return create_sse_response(event_generator())
```

- [ ] **Step 5: Migrate the report-generation route**

In `app/routers/report_generation.py`, change:

```python
from fastapi.responses import StreamingResponse, JSONResponse
```

to:

```python
from fastapi.responses import JSONResponse, Response

from app.core.sse import create_sse_response
```

Change the helper annotation:

```python
) -> Response:
```

Replace its SSE response construction with:

```python
    return create_sse_response(event_generator())
```

Keep all JSON response paths unchanged.

- [ ] **Step 6: Migrate the expert-deliberation route**

In `app/routers/expert_deliberation.py`, change the FastAPI import to include `Response`, remove the `StreamingResponse` import, and add:

```python
from app.core.sse import create_sse_response
```

Change the route annotation:

```python
async def run_deliberation_stream(request: DeliberationRequest) -> Response:
```

Replace its SSE response construction with:

```python
    return create_sse_response(event_stream())
```

Keep the existing 0.5-second queue poll because it controls business progress delivery; it no longer owns keepalive behavior.

- [ ] **Step 7: Run the architecture guard**

Run:

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest tests/test_sse_architecture.py -q
```

Expected: `2 passed`.

- [ ] **Step 8: Commit the route migration**

```bash
git add app/routers/agent.py app/routers/knowledge_qa.py app/routers/report_generation.py app/routers/expert_deliberation.py tests/test_sse_architecture.py
git commit -m "refactor: route all SSE responses through system transport"
```

### Task 5: Add route-level response-contract regressions

**Files:**

- Modify: `backend/tests/api/test_agent_conversation_access.py`
- Modify: `backend/tests/api/test_authenticated_knowledge_routes.py`
- Create: `backend/tests/api/test_sse_route_responses.py`

- [ ] **Step 1: Strengthen the existing Agent response assertion**

In `tests/api/test_agent_conversation_access.py`, import:

```python
from sse_starlette import EventSourceResponse

from config.settings import settings
```

Extend `test_new_client_session_id_is_allowed_when_catalog_and_source_are_absent` after response creation:

```python
    assert isinstance(response, EventSourceResponse)
    assert response.media_type == "text/event-stream"
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-accel-buffering"] == "no"
    assert response.ping_interval == settings.sse_heartbeat_interval_seconds
```

- [ ] **Step 2: Strengthen the existing knowledge response assertion**

In `tests/api/test_authenticated_knowledge_routes.py`, import:

```python
from sse_starlette import EventSourceResponse

from config.settings import settings
```

Extend `test_qa_stream_stores_authenticated_user_id`:

```python
    assert isinstance(response, EventSourceResponse)
    assert response.media_type == "text/event-stream"
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-accel-buffering"] == "no"
    assert response.ping_interval == settings.sse_heartbeat_interval_seconds
```

- [ ] **Step 3: Add lazy response-contract tests for the remaining routes**

Create `tests/api/test_sse_route_responses.py`:

```python
from sse_starlette import EventSourceResponse

from app.routers.expert_deliberation import run_deliberation_stream
from app.routers.report_generation import _stream_template_report_agent
from app.services.expert_deliberation.schemas import DeliberationRequest
from config.settings import settings


def _assert_system_sse_response(response):
    assert isinstance(response, EventSourceResponse)
    assert response.media_type == "text/event-stream"
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["connection"] == "keep-alive"
    assert response.headers["x-accel-buffering"] == "no"
    assert response.ping_interval == settings.sse_heartbeat_interval_seconds
    assert response.send_timeout == settings.sse_send_timeout_seconds


def test_report_generation_uses_system_sse_response():
    response = _stream_template_report_agent(
        template_content="# Template",
        target_time_range={"start": "2026-07-01", "end": "2026-07-15"},
    )

    _assert_system_sse_response(response)


async def test_expert_deliberation_uses_system_sse_response():
    response = await run_deliberation_stream(DeliberationRequest())

    _assert_system_sse_response(response)
```

These tests do not consume the lazy generators, so they do not invoke an LLM, database, or expert engine.

- [ ] **Step 4: Run the route-contract tests**

Run:

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest tests/api/test_agent_conversation_access.py tests/api/test_authenticated_knowledge_routes.py tests/api/test_sse_route_responses.py -q
```

Expected: all tests pass with no external service calls.

- [ ] **Step 5: Commit the route regressions**

```bash
git add tests/api/test_agent_conversation_access.py tests/api/test_authenticated_knowledge_routes.py tests/api/test_sse_route_responses.py
git commit -m "test: cover system SSE response contracts"
```

### Task 6: Verify the complete system behavior

**Files:**

- Verify: `backend/app/core/sse.py`
- Verify: all four migrated SSE routes
- Verify: `deploy/nginx/templates/default.conf.template`

- [ ] **Step 1: Run the focused SSE suite**

Run:

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest tests/core/test_sse.py tests/test_sse_architecture.py tests/api/test_agent_conversation_access.py tests/api/test_authenticated_knowledge_routes.py tests/api/test_sse_route_responses.py -q
```

Expected: all focused tests pass.

- [ ] **Step 2: Run existing nearby regressions**

Run:

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest tests/api tests/test_template_report_pipeline.py tests/test_expert_deliberation_default_files.py -q
```

Expected: all tests pass. Tests requiring unavailable external services must already carry an integration/external marker; do not hide a new failure by adding a skip.

- [ ] **Step 3: Run formatting and import checks**

Run:

```bash
conda run -p /root/miniconda3/envs/backend_py311 python -m compileall app/core/sse.py app/routers/agent.py app/routers/knowledge_qa.py app/routers/report_generation.py app/routers/expert_deliberation.py config/settings.py
```

Expected: every file compiles successfully.

Run:

```bash
conda run -p /root/miniconda3/envs/backend_py311 ruff check app/core/sse.py app/routers/agent.py app/routers/knowledge_qa.py app/routers/report_generation.py app/routers/expert_deliberation.py config/settings.py tests/core/test_sse.py tests/test_sse_architecture.py tests/api/test_sse_route_responses.py
```

Expected: no lint errors in new or touched code.

- [ ] **Step 4: Confirm the deployed proxy policy remains compatible**

Run from `/home/xckj/suyuan`:

```bash
docker exec suyuan-nginx nginx -T
```

Expected: the `/api/suyuan/` location uses HTTP/1.1 and `proxy_read_timeout 600s`; application responses supply `X-Accel-Buffering: no`.

- [ ] **Step 5: Perform a real proxy heartbeat smoke test**

After rebuilding/restarting the backend with the new dependency, start any authenticated SSE operation and inspect its Network response stream for at least 20 seconds during an idle business period.

Expected wire data includes a comment frame like:

```text
: keepalive

```

The browser console must not log a parsed event for the comment, no ReAct message is added, and `docker logs suyuan-nginx` must contain no `upstream timed out` entry for that request.

- [ ] **Step 6: Review the event-loop contract separately from the heartbeat transport**

Search for known synchronous work directly inside async SSE-producing paths:

```bash
rg -n "async def|requests\.|time\.sleep\(|subprocess\.run\(|run_ops_audit_rules\(" app/routers app/agent app/tools
```

Expected: record each confirmed blocking call site for an explicit executor-boundary follow-up. Do not add tool-specific threading changes to this system heartbeat commit; a blocked event loop cannot be repaired safely by the SSE transport layer.

- [ ] **Step 7: Commit any verification-only corrections**

If verification required a correction, commit only the correction and its regression test:

```bash
git add app config tests requirements.txt
git commit -m "fix: complete system SSE heartbeat verification"
```

If no correction was required, do not create an empty commit.

## Completion criteria

- `sse-starlette==2.4.1` is pinned and imports under the existing FastAPI/Starlette/AnyIO versions.
- All four current SSE routes use `create_sse_response()`.
- Raw route-level `StreamingResponse(media_type="text/event-stream")` construction is prohibited by a test.
- Idle streams emit `: keepalive` approximately every 15 seconds.
- Existing `data:` frames remain byte-for-byte unchanged and ordered.
- Heartbeats never enter Agent events, memory, persistence, or frontend messages.
- Disconnect and socket-send timeout paths clean up their tasks and source generators.
- Nginx retains its 600-second safety timeout and no longer sees an idle upstream while heartbeats are flowing.
- Blocking synchronous Agent/tool work is tracked as a separate executor-boundary concern rather than coupled to SSE transport.
