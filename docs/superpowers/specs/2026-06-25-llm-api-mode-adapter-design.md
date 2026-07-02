# LLM API Mode Adapter Design

## Goal

Add explicit LLM API protocol selection so the Agent can keep its existing Anthropic-native internal contract while calling either Anthropic Messages endpoints or OpenAI-compatible Chat Completions endpoints such as the new DeepSeek V4 Flash service.

## Current State

The Agent runtime, memory, and frontend streaming path are built around Anthropic Messages semantics:

- Assistant responses are stored and replayed as content blocks, including `text`, `thinking`, and `tool_use`.
- Tool results are stored as user messages with `tool_result` blocks.
- The streaming planner emits Anthropic-style events: `message_start`, `content_block_start`, `content_block_delta`, `content_block_stop`, `message_delta`, and `message_stop`.
- Session history recovery returns Anthropic content blocks from JSONB storage.

The project also has OpenAI-compatible Chat Completions calls for simpler text generation and document processing, but the main ReAct Agent path calls `chat_anthropic()` and `chat_anthropic_streaming()` in `backend/app/services/llm_service.py`.

The new DeepSeek V4 Flash endpoint provided by the service team exposes:

- `POST http://ds.local.ai:30080/v1/chat/completions`
- `POST http://ds.local.ai:30080/compatible-mode/v1/chat/completions`

Those endpoints are OpenAI-compatible Chat Completions endpoints, not Anthropic Messages endpoints. The current DeepSeek initialization assumes an Anthropic-compatible endpoint can be derived by replacing `/v1` with `/anthropic`, which is not valid for this service unless the service team provides such a route.

## Design Decision

Use an explicit `api_mode` and keep the internal Agent protocol unchanged.

Supported modes:

- `anthropic_messages`: use the existing Anthropic SDK path and Anthropic-compatible providers.
- `chat_completions`: use a new OpenAI-compatible adapter at the `LLMService` boundary.

The internal contract remains Anthropic content blocks and Anthropic-style streaming events. The adapter is responsible for converting requests and responses only at the provider boundary.

This mirrors the pattern used by OpenClaw and Hermes: provider configuration selects a concrete API/runtime mode, and adapters normalize provider-specific protocol differences instead of pretending every endpoint is interchangeable.

## Configuration

Add provider-level API mode configuration with conservative defaults:

```text
DEEPSEEK_API_MODE=anthropic_messages
MIMO_API_MODE=anthropic_messages
GLM_API_MODE=anthropic_messages
OPENAI_API_MODE=chat_completions
QWEN_API_MODE=chat_completions
```

For the new DeepSeek V4 Flash service, deployment should use:

```text
LLM_PROVIDER=deepseek
DEEPSEEK_API_MODE=chat_completions
DEEPSEEK_BASE_URL=http://ds.local.ai:30080/compatible-mode/v1
DEEPSEEK_MODEL=DeepSeek-V4-Flash
```

If the gateway requires the service group model ID instead of the display name, use:

```text
DEEPSEEK_MODEL=MDDEEPSEEK25FF2F3E5E17
```

The implementation should not infer `chat_completions` from URL shape alone. URL inference is brittle and would recreate the current `/v1` to `/anthropic` issue.

## Request Adapter

Create an adapter that converts Anthropic-style request inputs into OpenAI-compatible Chat Completions request JSON.

Message conversion:

| Internal Anthropic form | Chat Completions form |
| --- | --- |
| `system` parameter | leading `{ "role": "system", "content": ... }` |
| user `text` block | user message content text |
| assistant `text` block | assistant message content text |
| assistant `thinking` block | omitted by default, or included only if provider requires reasoning replay |
| assistant `tool_use` block | assistant message `tool_calls` |
| user `tool_result` block | `{ "role": "tool", "tool_call_id": ..., "content": ... }` |

Tool schema conversion:

```text
Anthropic tool:
  name
  description
  input_schema

Chat Completions tool:
  type=function
  function.name
  function.description
  function.parameters
```

Provider-specific request fields for DeepSeek V4 Flash:

```json
{
  "stream": true,
  "enable_thinking": true,
  "stream_options": {
    "include_usage": true
  }
}
```

Thinking should be configurable per call profile. The default for Agent tool loops should remain conservative: disable new thinking on fresh user turns unless a product decision is made to show reasoning. The adapter must still parse `reasoning_content` if the provider returns it.

## Non-Streaming Response Adapter

Convert Chat Completions responses back to the internal Anthropic response shape expected by `chat_anthropic()`.

Input fields:

```text
choices[0].message.content
choices[0].message.reasoning_content
choices[0].message.tool_calls
usage.prompt_tokens
usage.completion_tokens
```

Output shape:

```python
{
    "content": [
        {"type": "thinking", "thinking": "..."},
        {"type": "text", "text": "..."},
        {"type": "tool_use", "id": "...", "name": "...", "input": {...}},
    ],
    "model": "...",
    "usage": {
        "input_tokens": ...,
        "output_tokens": ...
    },
    "stop_reason": "tool_use" | "end_turn" | "max_tokens" | "stop_sequence"
}
```

The adapter should tolerate missing `reasoning_content`, missing usage, and provider-specific finish reasons.

## Streaming Adapter

The streaming adapter converts OpenAI-compatible SSE chunks into Anthropic-style events so frontend and planner code can remain unchanged.

Chat Completions stream input:

```text
choices[0].delta.reasoning_content
choices[0].delta.content
choices[0].delta.tool_calls
choices[0].finish_reason
usage
```

Anthropic-style output:

```text
message_start
content_block_start
content_block_delta
content_block_stop
message_delta
message_stop
```

Mapping rules:

- The first reasoning delta opens a `thinking` content block.
- Subsequent reasoning deltas emit `thinking_delta`.
- The first text delta opens a `text` content block.
- Subsequent text deltas emit `text_delta`.
- Tool call deltas are accumulated by `index` until each tool call has an ID, name, and parseable JSON arguments.
- Completed tool calls emit `tool_use` content blocks with parsed `input`.
- Finish reason `tool_calls` maps to `stop_reason="tool_use"`.
- Finish reason `stop` maps to `stop_reason="end_turn"`.
- Finish reason `length` maps to `stop_reason="max_tokens"`.

If a provider does not support streaming tool calls reliably, the streaming adapter should support a controlled fallback: use non-streaming Chat Completions for Agent steps that include tools while keeping streaming for final text responses.

## Frontend Behavior

The frontend should continue consuming Anthropic-style stream events. No new OpenAI-specific event protocol should be introduced for the main Agent stream.

Existing rendering paths for:

- text deltas
- thinking blocks
- tool lifecycle events
- `message_delta` usage and stop reason

should continue to work after the backend adapter normalizes events.

If `reasoning_content` is mapped to `thinking`, frontend thinking display and collapse behavior should be reused. If product policy later requires hiding reasoning, the backend can omit `thinking` blocks while still logging metadata.

## Session History Recovery

Do not migrate existing session history.

The canonical persisted history remains Anthropic content blocks. On every request to a `chat_completions` provider, the adapter converts the recovered Anthropic history into OpenAI-compatible messages in memory.

This avoids:

- database migration risk
- mixed protocol history
- frontend conditionals for old and new sessions
- loss of existing `tool_use` / `tool_result` structure

The adapter must handle historic thinking blocks defensively. For Chat Completions providers, persisted thinking blocks should be stripped unless the provider explicitly documents that reasoning replay is required and supported.

## Error Handling

Configuration errors should be explicit:

- `api_mode=anthropic_messages` with no Anthropic-compatible endpoint should fail with a message naming the required endpoint.
- `api_mode=chat_completions` should never try to derive `/anthropic` from `/v1`.
- Unsupported mode values should fail during service initialization.

Provider capability errors should be surfaced with provider, model, mode, and feature:

- unsupported tools
- unsupported stream tool calls
- invalid tool argument JSON
- missing content and missing tool calls

The fallback chain should include API mode in logs so a failed Anthropic-compatible attempt and a failed Chat Completions attempt are distinguishable.

## Testing Strategy

Unit tests:

- Convert Anthropic tools to Chat Completions tools.
- Convert Anthropic messages with text, thinking, tool_use, and tool_result to Chat Completions messages.
- Convert non-streaming Chat Completions text, reasoning, and tool calls back to Anthropic content blocks.
- Convert streamed reasoning, text, and tool call deltas into Anthropic-style events.
- Verify malformed streaming tool arguments produce a controlled error or fallback path.

Integration tests:

- `api_mode=anthropic_messages` continues using the existing Anthropic SDK path.
- `api_mode=chat_completions` calls `/chat/completions` without attempting `/anthropic`.
- Agent step with tools returns normalized `tool_use` blocks.
- Final answer streaming reaches the frontend as the existing event protocol.
- Session recovery with historic Anthropic blocks can be sent to a Chat Completions provider.

Manual DeepSeek V4 Flash tests:

- Non-streaming text request.
- Streaming text request with `enable_thinking=false`.
- Streaming request with `enable_thinking=true` and `reasoning_content`.
- Tool call request without streaming.
- Tool call request with streaming.
- Multi-turn tool result continuation.

## Rollout Plan

1. Add `api_mode` configuration and logging without changing current defaults.
2. Implement adapter unit tests and pure conversion functions.
3. Route `chat_anthropic()` through the Chat Completions adapter when `api_mode=chat_completions`.
4. Route `chat_anthropic_streaming()` through the streaming adapter when `api_mode=chat_completions`.
5. Add DeepSeek V4 Flash environment example.
6. Run local tests in the configured conda environment.
7. Test the live DeepSeek endpoint with the service-provided API key and model identifier.

## Non-Goals

- Rewriting the internal Agent protocol to OpenAI format.
- Migrating historic session storage.
- Changing frontend stream event semantics.
- Depending on URL string replacement to detect provider protocol.
- Implementing provider-specific behavior in planner or frontend code.
