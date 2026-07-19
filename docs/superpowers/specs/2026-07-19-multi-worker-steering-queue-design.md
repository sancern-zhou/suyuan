# Multi-Worker Steering Queue Design

## Goal

Make in-flight user steering reliable when the FastAPI service runs with the production default of four Uvicorn workers, while preserving FIFO fallback behavior when steering cannot be accepted.

## Current Problem

The active-run steering registry is process-local. An `/agent/analyze` stream and a later `/agent/{session_id}/steer` request can be handled by different workers, so the steering request cannot see the active run and is incorrectly rejected. The frontend safely falls back to a queued turn, but the user-requested instruction is not applied to the current run.

The fallback path also has three correctness gaps:

- unapplied steering entries are deduplicated by normalized text, which loses repeated instructions;
- transport failures leave queued turns stranded and allow a newer turn to run first;
- ordinary queued turns are omitted from mode-state persistence.

## Architecture

Use Redis as the authoritative cross-worker steering store. Each worker creates its own Redis client, but all registry operations act on shared keys and use atomic Redis operations or Lua scripts.

The registry remains the interface used by the runtime and router. It will delegate to a Redis-backed store in production and expose dependency injection for deterministic unit tests. It must not silently fall back to process-local state: if Redis is unavailable, registration or steering returns a non-accepted result and the frontend converts the instruction into a normal queued turn.

PostgreSQL is not used because steering is short-lived coordination state rather than durable conversation data. Sticky routing is not used because it cannot guarantee that two independent HTTP requests reach the same Uvicorn worker.

## Redis Data Model

Keys use a configurable prefix and encode the session and run identifiers safely.

- Active key: one hash per session containing `run_id`, `mode`, and `status`.
- Queue key: one Redis list per session and run. Each entry is JSON containing a unique input ID, content, attachments, and creation timestamp.
- Both keys receive a bounded TTL so crashed workers cannot leave an active run permanently registered.

Queue insertion uses `RPUSH`; consumption returns entries in list order. Registration replaces stale active metadata for the session and creates a fresh queue namespace for the new run. Unregister only removes keys when the stored run ID still matches, preventing an older run from deleting a newer run's registration.

## Lifecycle and Race Handling

An active run has two states:

- `accepting`: `/steer` may append input;
- `closing`: new steering is rejected and must be queued as a later turn by the frontend.

At ordinary iteration boundaries the runtime atomically drains the current list while the run stays `accepting`.

Before emitting a terminal response, the runtime performs an atomic completion check:

1. If queued steering exists, drain it and keep the run `accepting`; the runtime starts another iteration.
2. If no steering exists, change the run to `closing` in the same atomic operation.
3. Any later `/steer` request receives `accepted=false`, so it is deterministically promoted to the frontend FIFO queue instead of being acknowledged and lost.

Timeout, interruption, and fatal-error paths mark the run `closing` before their terminal event. Final cleanup compare-and-deletes the matching active and queue keys.

## Redis Failure Policy

Redis failures must not abort the main analysis stream.

- Registration failure logs a structured warning and makes the run non-steerable.
- `/steer` failure returns `accepted=false` with a stable reason such as `steering_store_unavailable`.
- Drain failure logs a warning and continues the current run without applying steering.
- The frontend treats any non-accepted result or request failure as a normal queued turn.

No process-local fallback is allowed under multi-worker deployment because it would reintroduce nondeterministic behavior.

## Frontend Queue Semantics

Every queued or steering input receives a stable client-side ID. Promotion of unapplied steering preserves each item independently, including repeated identical text, and checks identity rather than content for deduplication.

Queued turns remain FIFO. When a stream ends because of a transport error, existing queued turns remain ahead of newly submitted input. Starting a new turn while an idle state already contains queued input first enqueues the new input and resumes the oldest queued item.

Mode-state persistence includes `pendingUserInputs` and `pendingSteeringInputs`. Restored queues do not run merely because the page loaded; the next explicit send resumes the oldest saved item first, preventing unexpected background execution while retaining order.

Applied steering becomes a traceable user message in the current transcript rather than disappearing when its pending indicator is cleared.

## Compatibility

- The existing `/agent/{session_id}/steer` response retains `success`, `accepted`, `session_id`, and `message`; an optional stable `reason` is added.
- Assistant-mode behavior remains “append when possible, otherwise queue.”
- Non-steerable modes continue to queue immediately in the frontend.
- Social-mode callers continue using the same registry interface, including attachment support.

## Testing

Backend tests must cover:

- two registry instances sharing the same fake Redis backend, proving cross-worker visibility;
- FIFO append and drain, including attachments;
- compare-and-delete protection for replaced runs;
- atomic closing behavior and rejection after closing;
- Redis unavailable behavior returning non-accepted without crashing the runtime;
- timeout, interruption, fatal-error, and normal completion closing the run before terminal output.

Frontend tests must cover:

- repeated identical steering inputs promote to separate queued turns;
- identity-based deduplication prevents only the same item from being queued twice;
- queued turns preserve FIFO across a transport failure and a later send;
- persisted queue state restores without losing options, skill IDs, or context references;
- applied steering is represented once in the transcript.

## Success Criteria

- With four workers, a steering request accepted by any worker is visible to the worker running the analysis.
- `accepted=true` means the instruction will either be drained by that run or was accepted before an observable store failure; completion closing removes the known late-arrival race.
- Redis failure never terminates the main analysis and always causes frontend queue fallback.
- Repeated input text is never collapsed solely because its text matches another input.
- Existing backend steering tests and frontend composer tests continue to pass.
