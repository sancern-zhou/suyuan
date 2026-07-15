# Session Resource Manifest Design

## Summary

Important resources produced by tools must remain discoverable across requests in the same session without replaying full historical tool results. This design introduces a canonical Session Resource Manifest shared by every agent mode and transport, including Web, operations, reporting, query, chart, graph, expert/deliberation, social, scheduled, heartbeat, and consolidation runs.

The manifest separates three concerns:

- tools and storage systems own resource creation;
- the session manifest owns resource identity, provenance, and lifecycle;
- a bounded projector decides which references enter the model context for the current request.

Historical sessions and historical conversation transcripts will not be migrated or scanned. Only references produced after this mechanism is deployed are guaranteed to participate.

## Problem

The current system has several independent reference paths:

- runtime `ExecutionContext.available_data_ids`;
- persisted `Session.data_ids`;
- `office_documents` and visualization metadata;
- `refs` and `context_refs` embedded in tool results;
- file paths mentioned only in tool result summaries;
- Web and Social code that independently parses streamed tool events.

These paths do not share a canonical contract. A resource can be written successfully while its reference is lost before session persistence or prompt restoration. Restoring full display tool transcripts is not a suitable fix because stale failures and large tool results can compete with the current request.

## Goals

- Preserve important tool-produced references for the full lifetime of a session.
- Share one mechanism across all modes and transports, including Social.
- Keep reference persistence independent from historical message replay and context compression.
- Inject a bounded, relevant resource summary into each model request.
- Support data, files, artifacts, URLs, and visuals with one typed contract.
- Merge references safely under multi-worker concurrency.
- Preserve successfully produced references on complete, incomplete, interrupted, and fatal terminal paths.
- Retain existing `data_ids`, `office_documents`, and visualization consumers during migration through derived compatibility writes.
- Make missing, invalid, or superseded resources explicit instead of silently forgetting them.

## Non-goals

- Backfilling sessions or conversation transcripts created before deployment.
- Replaying full historical `tool_use` or `tool_result` messages.
- Reading resource contents into every prompt.
- Changing the lifetime or deletion policy of DataRegistry records and files.
- Sharing resources automatically between different session IDs.
- Inferring resources from arbitrary natural-language text.

## Chosen Approach

The chosen approach is a canonical Session Resource Manifest.

Two alternatives were rejected:

1. Restoring lightweight historical tool messages keeps resource durability coupled to transcript representation and pruning rules.
2. Registering every resource in DataRegistry handles structured data well but gives files, URLs, and visual artifacts unnatural semantics and still does not provide session awareness.

The manifest uses DataRegistry and the filesystem as resolvers for underlying resources, not as substitutes for session-level reference state.

## Architecture

```text
tool result from any mode
        |
        v
ReferenceNormalizer
        |
        v
RunReferenceAccumulator
        |
        v
SessionResourceManifest --atomic merge--> shared manifest store
        |
        +--> compatibility projections: data_ids / office_documents / visuals
        |
        v
ResourceContextProjector
        |
        v
bounded Session Resources context for the next model request
```

### ReferenceNormalizer

`ReferenceNormalizer` is the sole extraction boundary. It consumes the canonical tool result before transport-specific event handling and returns normalized `SessionResourceRef` objects.

Extraction priority is:

1. explicit tool-declared `refs`;
2. canonical top-level fields such as `data_id`, `report_data_id`, `file_path`, `url`, and `visuals`;
3. compatibility fields in known nested result containers, including `event.data.result` and result `data` payloads.

It must not regex-scan summaries, errors, or normal conversational text for paths or IDs. Explicit structured declarations always win over compatibility inference.

### RunReferenceAccumulator

Every `ReActAgent` run owns one accumulator initialized from the persisted manifest. It receives normalized references immediately after each successful tool result. It performs in-memory idempotent merging for the current run and records rejected references as structured diagnostics.

The accumulator belongs to the runtime, not to Web routes or `SocialAgentBridge`. Transport code may display references but cannot be responsible for their durability.

### SessionResourceManifest

The manifest is the canonical session resource state. It is stored in an independent shared `session_resource_manifests` database table keyed by `session_id`. It must not be embedded in either the database-backed Web Session record, the file-backed Social Session snapshot, or generic session metadata.

This storage boundary is required because Social transcripts currently use a file-backed `SessionManager` while other modes use database-backed Sessions. A mode-dependent manifest store would split one session's resources when the same session moves between Web and Social. All modes therefore use one manifest repository even though their transcript repositories remain different.

The manifest is session-scoped. Mode switches within one session use the same manifest. Different session IDs, including independently generated heartbeat or consolidation sessions, do not inherit resources unless a future feature explicitly defines a parent-session relationship.

### ResourceContextProjector

The projector creates a compact `Session Resources` context block for every agent mode. It receives the current query, mode, available tools, and manifest, then selects references within a fixed token budget.

The projector does not authorize access. Existing ownership, path, and tool checks still run when a resource is used.

### ReferenceResolver

The resolver validates a reference on use:

- DataRegistry existence for data references;
- allowed path and file existence for file references;
- ownership and availability for artifacts and visuals;
- allowed URL policy for URL references.

Resolution updates `last_used_at` and can change status to `missing` or `invalid`.

### SessionFinalizer

All terminal outcomes use one resource finalizer that persists the merged manifest before the terminal event is reported as durable. Transcript persistence can continue through the existing mode-specific managers, but Web and Social must not implement separate resource finalization paths.

## Reference Model

```json
{
  "ref_id": "stable deterministic identifier",
  "kind": "data|file|artifact|url|visual",
  "locator": {
    "data_id": "optional registry identifier",
    "path": "optional canonical path",
    "url": "optional URL",
    "artifact_id": "optional artifact identifier",
    "visual_id": "optional visual identifier"
  },
  "logical_key": "optional business slot such as ops_audit.final_issue_list",
  "role": "primary|source|report|output|attachment",
  "label": "short user-facing description",
  "tool_name": "producing tool",
  "run_id": "producing run",
  "turn_sequence": 12,
  "status": "active|superseded|missing|invalid",
  "importance": "normal|high|pinned",
  "created_at": "ISO-8601 timestamp",
  "last_seen_at": "ISO-8601 timestamp",
  "last_used_at": "optional ISO-8601 timestamp",
  "supersedes": ["older-ref-id"],
  "metadata": {}
}
```

`metadata` is bounded and must not contain full datasets, documents, chart specifications, or arbitrary tool output.

### Identity

`ref_id` is derived from normalized `kind` and canonical locator. Equivalent paths and identifiers therefore deduplicate across requests. `logical_key` represents a business slot whose resource may change between runs. For example, a newly generated final issue list can supersede the previous reference even when the physical path differs.

### Lifecycle

- `active`: eligible for projection and use.
- `superseded`: retained for audit but replaced in its logical slot.
- `missing`: target no longer exists.
- `invalid`: malformed, unauthorized, or outside allowed boundaries.

An empty set of new references means that the current run produced no references. It never clears existing manifest entries. Removal and replacement require explicit operations.

Deleting a session deletes its manifest. It does not independently delete referenced DataRegistry data, files, or external resources.

## Tool Result Contract

New or updated tools should declare explicit references:

```json
{
  "status": "success",
  "summary": "Audit completed",
  "refs": {
    "files": [
      {
        "path": "/absolute/path/final_issue_list.json",
        "logical_key": "ops_audit.final_issue_list",
        "role": "output",
        "label": "Final issue list",
        "importance": "high"
      }
    ],
    "data": [
      {
        "data_id": "ops_audit_rule_summary:v1:...",
        "role": "primary",
        "label": "Audit rule summary"
      }
    ]
  }
}
```

The compatibility normalizer supports existing top-level and known nested fields while tools migrate. Compatibility extraction is structural and does not parse free text.

## Unified Data Flow Across Modes

1. A tool returns a standard result.
2. The runtime normalizes references before emitting transport events.
3. The run accumulator merges normalized references.
4. Web SSE, Social, scheduled tasks, and other consumers receive the same normalized event and may render it without owning persistence.
5. A common resource finalizer atomically merges the accumulator into the shared manifest table for every terminal outcome.
6. The next request loads the manifest by session ID.
7. The context builder calls the shared projector regardless of mode.
8. The model receives a bounded resource summary and can query older resources through `list_session_resources`.

This flow applies to assistant, ops, report, query, chart, graph, expert/deliberation, social, scheduled, heartbeat, and consolidation runs. Separate system-generated session IDs remain isolated.

## Persistence and Concurrency

Add an independent `session_resource_manifests` table with:

- `session_id`: primary key;
- `resource_refs`: JSONB, defaulting to an empty list;
- `version`: integer, defaulting to zero;
- `created_at` and `updated_at` timestamps.

The table intentionally has no foreign key to the database `sessions` table because Social session transcripts may exist only in file-backed storage. Session ownership continues to come from Conversation Catalog and the existing Social user mapping.

All modes use the same manifest repository. Manifest updates use an atomic merge with row locking or optimistic version checks and bounded retries. The merge operates on the latest shared value, never on a stale route-local or Social file snapshot.

The terminal event must not claim cross-request durability until manifest persistence completes. Persistence failures are retried and surfaced through structured terminal diagnostics instead of being silently ignored. If the shared database is unavailable, the current turn may continue using its in-memory references, including in Social, but the terminal result must state that those references were not persisted and cannot be assumed available on the next request.

During migration, new manifest state may be projected into existing mode-specific compatibility fields:

- active data refs derive `Session.data_ids`;
- appropriate file/artifact refs derive `office_documents` where required by existing preview consumers;
- active visual refs derive existing visual metadata.

These are compatibility projections, not independent sources of truth. Historical values are not imported into the manifest, and compatibility writes never feed back into the shared table.

## Context Projection

The default projection budget is approximately 2,000 tokens. Selection order is:

1. references explicitly named by the current request;
2. pinned references;
3. high-importance references;
4. active references compatible with currently available tools;
5. most recently used or seen references.

Normal projection excludes `missing`, `invalid`, and `superseded` references. It includes a count of additional searchable references when the budget truncates the list.

Each projected item contains only its ID, kind, label, locator, role, source tool, creation time, and a short usage hint. Resource contents stay out of the prompt.

All modes use the same projector. Mode can affect which tools are available but cannot erase or fork the underlying manifest.

## Resource Discovery Tool

A read-only `list_session_resources` tool supports filters for:

- `kind`;
- `status`;
- `label`;
- `tool_name`;
- `run_id`;
- `logical_key`.

The tool only lists resources belonging to the current authorized session. Existing tools perform actual reads: `read_data_registry` for data, `read_file` or `present_artifact` for files, and the appropriate URL or visual tool for other kinds.

## Security

- Session ownership is verified through Conversation Catalog or the existing authorized Social mapping before loading or projecting the manifest.
- A stored path does not bypass filesystem allowlists or tool authorization.
- Social user mapping does not relax session ownership or path checks.
- Invalid or unauthorized references are never projected as usable resources.
- Different session IDs do not share manifests automatically.
- Web and Social access the same manifest row when they operate on the same authorized session ID.
- Reference logs avoid embedding full sensitive payloads.

## Failure Handling and Observability

An invalid individual reference does not fail an otherwise successful business tool. It is rejected or stored as `invalid` with a bounded diagnostic. Manifest persistence failure is different: it affects the durability guarantee and must not be silent.

Required metrics and logs include:

- extracted references by tool, kind, and mode;
- references added, updated, superseded, rejected, or marked missing;
- persistence retries and failures;
- projection count, token estimate, and truncation count;
- optimistic version conflicts and retries;
- Web, Social, and mode coverage.

## Historical Behavior

There is no historical migration or transcript backfill.

- Existing pre-deployment sessions have no manifest row until a post-deployment tool produces a reference.
- New references generated in those sessions after deployment are captured normally.
- Historical display tool events remain excluded from model restoration.
- Existing `data_ids`, `office_documents`, and visual metadata are not imported into the new manifest.

This avoids ambiguous inference and keeps the rollout deterministic.

## Rollout

1. Add typed models and the independent shared manifest table.
2. Add normalization and manifest merge tests before production code.
3. Integrate normalization at the common runtime boundary.
4. Add the accumulator and common terminal finalizer.
5. Add context projection and `list_session_resources`.
6. Route Web and Social through the shared manifest service and remove their reference parsing responsibilities.
7. Dual-write new compatibility fields while treating the manifest as canonical.
8. Observe metrics before separately considering removal of legacy writes; legacy removal is outside this change.

## Test Strategy

### Unit tests

- normalize explicit and compatibility references for all five kinds;
- extract nested `event.data.result` fields;
- reject free-text-only paths and invalid locators;
- deduplicate stable identities;
- merge empty current-run sets without deleting old references;
- supersede by `logical_key`;
- enforce lifecycle transitions;
- rank and truncate context projection within budget.

### Persistence and concurrency tests

- persist and restore references across two requests;
- preserve successful references on complete, incomplete, interrupted, and fatal paths;
- merge concurrent disjoint updates into a union;
- retry optimistic version conflicts without losing references;
- delete manifest state through every public session-deletion workflow.

### Mode and transport tests

- two-request Web flow;
- two-request Social flow;
- Web-to-Social and Social-to-Web mode switches in the same session;
- shared-table access is independent of Web database transcript versus Social file transcript storage;
- all registered agent modes use the shared projector and finalizer;
- independently identified heartbeat and consolidation sessions remain isolated.

### Security tests

- reject resource projection for unauthorized session access;
- retain but do not use missing or invalid references;
- enforce filesystem and URL policies at resolution time.

### Business regression examples

- operations audit final issue list as a generic high-importance file reference;
- standard query `data_id`;
- generated report file;
- chart artifact and visual ID;
- URL reference.

No operations-audit-specific persistence logic is permitted.

## Acceptance Criteria

- A resource produced in request A is available without filesystem guessing in request B of the same session.
- References survive any mode switch in the same session, including Social.
- A request producing no references does not reduce the manifest.
- References produced before interruption remain durable.
- Concurrent requests cannot overwrite one another's references.
- Web and Social resolve the same manifest row for the same authorized session ID even though their transcripts use different storage backends.
- Prompt projection remains within its configured budget.
- A shared-store outage is reported as non-durable instead of silently claiming cross-request preservation.
- Historical tool failures are not replayed.
- Pre-deployment conversations and references are not migrated.
- Unauthorized users and other sessions cannot access the manifest.
- Deleting a session through any public workflow deletes its shared manifest.
- `final_issue_list_path` passes only through the generic file-reference contract.
