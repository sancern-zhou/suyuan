# Shared Agent Workflow Runtime

This package contains the domain-neutral coordination primitives used by all
Agent modes.  It does not encode report, expert, operations, or coding
workflows.

## Contracts

Use `build_agent_task()` for a task contract.  A contract identifies the task,
its parent, objective, inputs, constraints, dependencies, capabilities, and
the expected result schema.  Use `build_result_envelope()` for a stable result
shape containing outputs, evidence, uncertainties, artifacts, errors, and
metadata.  A mode may add a stricter schema inside `result_schema`.

## Runtime

`WorkflowRuntime` records task lifecycle transitions and append-only events:

```text
queued -> running -> waiting/repairing -> succeeded/failed/cancelled
```

Its snapshot is JSON serializable and can be persisted in a session, database,
or Redis.  Reconstructing a runtime from that snapshot preserves task state,
lineage, attempts, cancellation, and the event journal.

`WorkflowGraph` handles dependencies for multi-agent DAGs.  Tasks become ready
only after every dependency succeeds.  `WorkflowConcurrencyGovernor` provides
a domain-neutral concurrency bound.

`AgentActorRegistry` serializes turns for the same logical child runtime while
allowing different child runtimes to execute concurrently.  `call_sub_agent`
uses `session_id + target_mode` as its actor key.

## Mode adapters

Mode code supplies prompts, tool capabilities, task-specific contracts, and
result schemas.  The shared runtime owns scheduling, persistence, retries,
repair states, cancellation, capability filtering, and observability.  New
modes should call the runtime through the existing handoff tool rather than
implementing another parent/child execution path.

## Fixed workflow catalog

`catalog.py` is the shared registry for bounded Agent-mode workflows and
deterministic scheduled workflows. Both entry points publish a versioned
definition made of named phases; they differ only in their adapter:

- Agent-mode workflows let the model choose tool arguments while the runtime
  owns phase transitions, visible tools, retry bounds, and completion.
- Scheduled workflows bind a deterministic handler and continue to run without
  starting an Agent.

Latency-sensitive query modes are defined in `mode_workflows.py`. They use a
bounded acquire/normalize/deliver flow, so report DAG nodes and future scheduled
jobs can share the same execution policy instead of copying prompt conventions.
