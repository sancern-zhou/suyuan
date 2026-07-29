# System SSE Heartbeat Design

## Goal

Provide transparent keepalive traffic for every Server-Sent Events endpoint so reverse proxies do not terminate an otherwise healthy stream during long periods without business events.

The mechanism is system infrastructure. It must not be coupled to the Agent runtime, a specific Agent mode, an individual tool, or the operations work-order audit flow.

## Scope

The first release covers every current response whose media type is `text/event-stream`:

- Agent analysis
- knowledge-base question answering
- report generation
- expert deliberation

Future SSE endpoints must use the same response factory. Ordinary `StreamingResponse` uses, such as file downloads, remain unchanged.

This release adds transport keepalives only. It does not add visible progress, resumable event replay, task persistence, or frontend reconnection.

## Standards and framework basis

The WHATWG SSE authoring guidance recommends sending a comment line beginning with `:` approximately every 15 seconds to protect an idle event stream from proxy timeouts. Nginx defines `proxy_read_timeout` as the maximum interval between successive upstream reads, not a total response-duration limit. Therefore a standards-compliant comment heartbeat prevents the current 600-second idle timeout without weakening the proxy timeout policy.

The implementation will use `sse-starlette`'s `EventSourceResponse`, which coordinates stream output, ping output, disconnect detection, send timeouts, and application shutdown as separate concurrent responsibilities. This avoids duplicating subtle ASGI lifecycle behavior in application code.

Because the project currently pins FastAPI 0.115.0 and Starlette 0.38.6, the initial dependency will be compatibility-pinned to `sse-starlette==2.4.1`. The project already runs Python 3.11 and AnyIO 4.12.0, satisfying that release's Python and AnyIO requirements. Upgrading FastAPI, Starlette, and `sse-starlette` is a separate change and is not part of this feature.

References:

- https://html.spec.whatwg.org/multipage/server-sent-events.html#authoring-notes
- https://nginx.org/en/docs/http/ngx_http_proxy_module.html#proxy_read_timeout
- https://github.com/sysid/sse-starlette
- https://pypi.org/project/sse-starlette/2.4.1/

## Architecture

Add a focused system module at `backend/app/core/sse.py`. It exposes one public response factory:

```python
def create_sse_response(
    source: AsyncIterable[str | bytes],
    *,
    heartbeat_interval_seconds: float | None = None,
    send_timeout_seconds: float | None = None,
    headers: Mapping[str, str] | None = None,
) -> EventSourceResponse:
    ...
```

All SSE routes pass their existing business generator to this factory. The factory owns protocol and transport policy; route generators continue to own business events, persistence, terminal events, and domain-specific exception handling.

The response runs these concerns concurrently:

1. Consume and transmit business frames in their original order.
2. Send a comment heartbeat every configured interval.
3. Detect a disconnected client and cancel stream consumption.
4. Bound an individual socket send operation.
5. Stop all response tasks during completion, failure, disconnect, or server shutdown.

No heartbeat crosses into the business event generator. It therefore cannot be added to Agent conversation history, SessionMemory, LLM context, report state, or frontend ReAct messages.

## Wire protocol

The default heartbeat interval is 15 seconds. The heartbeat is an SSE comment:

```text
: keepalive

```

It contains no `data`, `event`, or `id` field and therefore does not dispatch a browser message event. The existing frontend stream parser only processes lines beginning with `data: `, so it ignores the heartbeat without a frontend change.

The default send timeout is 30 seconds. This protects the server when a connected client stops consuming data and the socket send blocks.

The response factory applies these defaults unless a caller provides a stricter compatible value:

```http
Content-Type: text/event-stream
Cache-Control: no-store
Connection: keep-alive
X-Accel-Buffering: no
```

Caller-provided headers may add route-specific values but must not re-enable buffering or caching.

## Compatibility with existing streams

Current endpoints yield complete serialized frames such as:

```text
data: {"type":"streaming_text","data":{...}}

```

`EventSourceResponse` treats a Python string as event data and would wrap it in another `data:` field. The system adapter must therefore encode existing complete frames to UTF-8 bytes before passing them to `EventSourceResponse`. The library transmits byte frames unchanged.

This compatibility adapter permits a small, behavior-preserving migration. Converting every route to structured `ServerSentEvent` objects can be considered later but is not required for transparent heartbeats.

The adapter accepts only `str` and bytes-like frames. Unsupported values fail immediately with a descriptive type error instead of producing a malformed event stream.

## Configuration

Add two application settings with environment-variable support:

- `SSE_HEARTBEAT_INTERVAL_SECONDS`, default `15`
- `SSE_SEND_TIMEOUT_SECONDS`, default `30`

The heartbeat interval must be positive and materially shorter than every proxy idle timeout. The deployment keeps `proxy_read_timeout 600s`; it is a safety limit rather than the primary keepalive mechanism.

Configuration is global so every SSE endpoint has the same transport behavior. Per-route overrides exist only for tests or a demonstrated protocol requirement, not routine business customization.

## Agent and tool execution contract

Heartbeats require the asyncio event loop to remain schedulable. The system therefore establishes this invariant:

> SSE-producing request paths must not execute long synchronous, CPU-bound, or blocking work directly on the event-loop thread.

Agent tools that call synchronous libraries must use the project's executor boundary, `asyncio.to_thread`, or an external worker. This is a system execution rule rather than heartbeat logic and applies to all Agent tools and all SSE producers.

The heartbeat feature will not attempt to move arbitrary generator code to another thread automatically. Doing so would break coroutine affinity, request-scoped resources, and cancellation semantics. Known blocking call sites should be migrated explicitly and verified independently.

## Disconnect, cancellation, and errors

Client disconnect is a transport termination, not a business failure. `EventSourceResponse` detects the ASGI disconnect and cancels the response task group. Existing generators must continue to propagate `CancelledError` and run their `finally` cleanup.

The response layer does not translate business exceptions into SSE events. Each route retains its existing error-event contract. If an exception escapes the source generator after response headers have been sent, the response closes and logs the exception through the existing ASGI path.

Heartbeats stop immediately when:

- the business source completes;
- the source raises an exception;
- the client disconnects;
- a send times out;
- the application shuts down.

No heartbeat may be sent after the terminal business frame or the final empty ASGI body.

## Observability

Do not log every heartbeat at info level. That would create high-volume noise. The system should expose low-cardinality lifecycle information:

- SSE stream opened and closed, at debug level;
- close reason: completed, disconnected, send timeout, source error, or shutdown;
- send-timeout and unexpected source failures at warning/error level;
- optional aggregate counters for active streams and close reasons if the existing metrics stack supports them.

Logs must identify the route and, when already available, session or run identifiers. The SSE core must not inspect Agent payloads to obtain those values.

## Migration

Replace only the four current `StreamingResponse(..., media_type="text/event-stream")` constructions with `create_sse_response(...)`. Their event generators and business logic remain unchanged.

Add an architecture test that scans application Python sources and fails when a new raw `StreamingResponse` is constructed with `text/event-stream` outside the central SSE module. This makes system-wide coverage enforceable rather than conventional.

Deployment remains backward compatible:

- no frontend release is required for comment heartbeats;
- Nginx keeps buffering disabled and retains the 600-second read timeout;
- event payloads and ordering do not change;
- endpoint URLs and authentication do not change.

## Testing

Unit tests for the SSE core must prove:

1. A comment heartbeat is sent at the configured interval while the source is idle.
2. Existing pre-serialized string and byte frames are transmitted once and unchanged.
3. Business frames preserve their order when heartbeats occur between them.
4. Completing the source stops the ping task and closes the response.
5. Source exceptions terminate the response and are not converted into business events.
6. Client disconnect cancels the source and executes its `finally` block.
7. A blocked send triggers the configured send timeout and cleanup.
8. Standard no-cache and no-buffer headers are present.
9. The architecture guard finds all four existing SSE endpoints and rejects raw future SSE responses.

Route-level regression tests must verify that each migrated endpoint still emits its existing first and terminal business frames. Agent tests must additionally verify that heartbeat comments never appear in persisted conversation history or Agent memory.

Use short injected intervals in tests; production timing values must not make the test suite sleep for 15 or 30 seconds.

## Rollout and acceptance criteria

Roll out with the existing Nginx read timeout unchanged. Validate one deliberately idle test stream through the real Nginx container for longer than 600 seconds.

The feature is accepted when:

- every current SSE endpoint uses the central response factory;
- an idle stream remains connected through Nginx beyond 600 seconds;
- the client receives comment heartbeats approximately every 15 seconds;
- no heartbeat appears as a frontend message or persisted business event;
- disconnect and send-timeout tests demonstrate cleanup;
- existing SSE endpoint regression tests pass;
- no unrelated non-SSE `StreamingResponse` behavior changes.

## Future evolution

Transparent heartbeats preserve a live connection but do not make a long Agent run durable. Runs that must survive browser refreshes, backend restarts, or deployment replacement require a separate design based on persistent run IDs, background execution, event storage, and resumable subscription. That work is explicitly outside this feature.
