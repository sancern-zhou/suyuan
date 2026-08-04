# Unified Session Resources Design

## Summary

Replace the current combination of `session_resource_manifests`, `Session.data_ids`,
`Session.visual_ids`, `Session.office_documents`, and
`Session.metadata.visualizations` with one authoritative, row-oriented session
resource store.

The new mechanism covers data references, files, artifacts, document previews,
visualizations, and URLs. Tools declare resources explicitly. The shared Agent
runtime validates and persists those declarations once. Model context projection,
the composer resource menu, document panels, visualization panels, and restore
counts all query the same service and table.

This is a hard cutover. Existing resource and preview state is neither migrated nor
read through compatibility fallbacks. Existing conversations may continue to restore
messages, but their resource lists start empty until new tools produce resources under
the new contract.

## Goals

- Establish one authoritative representation and persistence path for all
  session-scoped resources.
- Eliminate duplicate state and overwrite races between resource references,
  document previews, visualization metadata, route collectors, and frontend stores.
- Preserve resources across requests, process restarts, transports, and Agent modes.
- Support lazy, filtered resource queries without loading every resource payload.
- Make real-time resource rendering and restored rendering consume the same resource
  object and frontend upsert method.
- Keep only the latest version of a mutable logical resource.
- Preserve successfully produced resources on complete, incomplete, interrupted, and
  fatal terminal paths.
- Reject ambiguous or inferred persistence instead of reconstructing resources from
  historical messages or loosely related result fields.

## Non-goals

- Migrating resource references, document previews, or visualizations from old
  sessions.
- Supporting legacy `file_path`, `data_id`, `data_ids`, `visuals`, or nested-result
  inference.
- Preserving old versions of edited documents or regenerated logical artifacts.
- Persisting full files, datasets, arbitrary tool results, or unbounded Markdown in
  resource rows.
- Providing a dual-write or mixed-version deployment window.

## Current Problem

The existing implementation has multiple independently persisted resource views:

- a canonical-looking JSONB Session Resource Manifest;
- `sessions.data_ids`;
- `sessions.visual_ids`;
- `sessions.office_documents`;
- `sessions.metadata.visualizations`;
- preview metadata repeated in tool messages;
- route-local and `ReActAgent._session_store` collections;
- separate frontend document and visualization histories.

The resource-manifest compatibility projection converts every active file or artifact
path into a lightweight `office_documents` entry. At terminal time that list replaces
the rich preview entries previously collected from `office_document` and
`html_document` events. Restore then treats a non-empty lightweight list as valid,
does not inspect the messages, and returns entries the document panel cannot render.

The failure is structural: a file identity and a document presentation are related,
but they are not interchangeable and must not be independently persisted under the
same field name.

## Chosen Architecture

Use a row-oriented `session_resources` table behind one
`SessionResourceService`.

```text
Tool.execute()
    |
    v
explicit ToolResult.resources
    |
    v
ResourceNormalizer
    |
    v
RunResourceAccumulator
    |
    v
SessionResourceService --transactional upsert--> session_resources
    |
    +--> bounded model context projection
    +--> composer resource query
    +--> document presentation query
    +--> visualization presentation query
    +--> restore counts
```

The table is the only resource state. `Session`, transcript messages, route-local
collectors, and frontend mode state do not own independent persistent copies.

### Rejected Alternatives

#### Extend the existing one-row JSONB manifest

This requires loading and locking a complete session resource array for filtered
queries, counts, and updates. Large visualization presentations would amplify the
cost. It also makes cursor pagination and type-specific indexes awkward.

#### Hide multiple stores behind one service

This unifies an API without unifying state. It retains the same drift and overwrite
risks between reference, preview, and visualization stores.

#### Use historical tool events as the resource store

This couples durable resources to transcript retention, pruning, pagination, and
message schemas. It also requires replay and inference during restore.

## Persistence Model

Create `session_resources` with one row per current logical resource.

| Column | Contract |
| --- | --- |
| `session_id` | Authorized logical conversation ID. |
| `resource_key` | Stable key within the session. |
| `resource_id` | Stable external ID returned to clients and model tools. |
| `logical_key` | Mutable business slot; required for mutable presentations. |
| `kind` | `data`, `file`, `artifact`, `visual`, or `url`. |
| `role` | `primary`, `source`, `report`, `output`, or `attachment`. |
| `label` | Short user-facing label. |
| `locator` | Type-validated resolver identity. |
| `presentation_type` | Null, `document`, or `visualization`. |
| `presentation` | Bounded type-specific rendering descriptor. |
| `metadata` | Bounded allowlisted operational metadata. |
| `tool_name` | Producing tool. |
| `run_id` | Producing Agent run. |
| `turn_sequence` | Producing turn sequence. |
| `status` | `active`, `missing`, or `invalid`. |
| `created_at` | Original creation time for this resource key. |
| `updated_at` | Last successful replacement time. |

Constraints:

```text
PRIMARY KEY (session_id, resource_key)
UNIQUE (resource_id)
```

`resource_id` is derived from the session ID and resource key so clients receive a
stable identity for the current logical resource.

Create a small `session_resource_versions` coordination table with `session_id` as
its primary key and a monotonically increasing `version`. It contains no resource or
presentation payload. The resource transaction locks this row, changes affected
resource rows, increments the version exactly once, and returns that committed
version to terminal events and clients. This is transaction metadata, not a second
resource source of truth.

### Resource Key

- If `logical_key` is present, `resource_key` is derived from it.
- Otherwise, `resource_key` is derived from `kind` and the canonical locator.
- Mutable documents and visualizations must declare `logical_key`.
- A new result with the same `session_id + logical_key` replaces the complete old
  row in one transaction.
- Replacement preserves `created_at` and updates the other business fields and
  `updated_at`.
- Old rows are not retained as `superseded` history.

### Locator

The locator has exactly one primary identity appropriate to its kind:

- data: `data_id`;
- file: canonical `path`;
- artifact: `artifact_id` or canonical `path`;
- visual: `visual_id`;
- URL: normalized `url`.

Artifact presentation metadata may contain an associated path, but identity remains
unambiguous. Existing resolver authorization, filesystem allowlists, and ownership
checks still apply when the resource is used.

## Resource Contracts

### Data

```json
{
  "kind": "data",
  "logical_key": "query.primary_result",
  "locator": {"data_id": "dataset:v1:..."},
  "presentation_type": null
}
```

The actual dataset remains in DataRegistry.

### File

```json
{
  "kind": "file",
  "logical_key": "upload:<file-id>",
  "locator": {"path": "/absolute/path/file.docx"},
  "presentation_type": null
}
```

A file is available to the model and composer but does not appear in the document
panel until a tool explicitly returns a document presentation. A `file` or
`artifact` resource may carry a document presentation. When `publish_session_file`
previews an existing selected file, it must preserve that resource's `logical_key`
and replace the same row with an added presentation instead of creating a second
resource.

### Document Artifact

```json
{
  "kind": "artifact",
  "logical_key": "report:<report-id>",
  "locator": {
    "artifact_id": "<report-id>"
  },
  "presentation_type": "document",
  "presentation": {
    "format": "html",
    "preview": {
      "type": "html",
      "url": "/api/...",
      "preview_version": "..."
    },
    "download": {},
    "editable": false
  }
}
```

An online edit writes the same logical key with the new locator and presentation.
Only the new version remains visible or addressable.

### Visualization

```json
{
  "kind": "visual",
  "logical_key": "chart:<business-slot>",
  "locator": {"visual_id": "..."},
  "presentation_type": "visualization",
  "presentation": {
    "renderer": "echarts",
    "spec": {}
  }
}
```

Visualization specifications have an explicit size limit. Oversized specifications
are written to an artifact file and the presentation stores only its resolvable
reference.

### URL

```json
{
  "kind": "url",
  "locator": {"url": "https://example.test/resource"},
  "presentation_type": null
}
```

## Payload Boundaries

- `presentation` contains rendering descriptors, not original Office files or
  arbitrary tool output.
- Markdown bodies are not stored inline without a strict small-payload limit. Normal
  Markdown presentations resolve a source artifact on demand.
- Visualization specifications and metadata have configured byte limits.
- `metadata` uses an allowlist and cannot contain nested preview or arbitrary result
  payloads that duplicate `presentation`.
- Invalid type combinations are rejected, such as a data resource with a document
  presentation.

## Tool Result Contract

Every resource-producing tool returns an explicit top-level `resources` list:

```json
{
  "success": true,
  "data": {},
  "resources": [
    {
      "kind": "artifact",
      "logical_key": "report:hzpc",
      "role": "report",
      "label": "高值排查报告",
      "locator": {"path": "/absolute/path/index.html"},
      "presentation_type": "document",
      "presentation": {
        "format": "html",
        "preview": {"type": "html", "url": "/api/..."}
      }
    }
  ]
}
```

There is no compatibility inference from `file_path`, `data_id`, `data_ids`,
`visuals`, nested result containers, summaries, or message text. A tool that does not
return a valid `resources` entry has not produced a durable session resource.

If a resource is the primary business deliverable and cannot be described using the
contract, the tool must return failure. The runtime does not infer whether an invalid
resource is optional or required.

## Runtime Write Path

1. A successful tool result reaches the shared Agent event boundary.
2. `ResourceNormalizer` validates only its explicit `resources` entries and computes
   stable keys and IDs.
3. `RunResourceAccumulator` idempotently merges resources produced in the run.
4. Immediate document or visualization SSE events are derived from the same
   normalized resource objects. They are not a second persistence input.
5. Before any complete, incomplete, interrupted, or fatal terminal event is emitted,
   the runtime verifies run ownership and calls
   `SessionResourceService.upsert_run_resources()`.
6. The service replaces matching resource keys and inserts new resource keys in one
   transaction.
7. Only after commit does the terminal event report `resource_durable=true` and the
   new session resource version.

An empty run resource set does not delete existing rows. Explicit deletion uses
`delete_resource()`.

Routes and transcript persistence do not collect, transform, cache, or persist
resources. `office_document` and `html_document` may remain as transport event names
during frontend migration, but their payload is the canonical Resource object and
they never enter the accumulator a second time.

## Concurrency

- The active run ownership registry decides whether a run may update session
  resources.
- A stale run cannot replace a resource produced by the active run.
- A repeated write from the same run is idempotent.
- Different resource keys are merged as a union.
- Multiple writes to the same logical key within one run resolve to the last valid
  resource emitted by that run.
- The database transaction locks or upserts only the affected resource rows and the
  session resource version record; it does not lock a complete JSONB resource array.

## Query API

Use one endpoint:

```text
GET /api/sessions/{session_id}/resources
```

Supported filters include:

- `kind`;
- `presentation_type`;
- `role`;
- `status`;
- `limit`;
- `cursor`.

The endpoint authorizes the session through Conversation Catalog before querying the
resource service. It returns canonical Resource objects and pagination metadata.

Remove the dedicated `/office-documents` and `/visualizations` endpoints. Their
consumers query `presentation_type=document` and
`presentation_type=visualization`, respectively.

## Restore Flow

The message restore response includes lightweight database counts:

```json
{
  "resource_counts": {
    "total": 8,
    "documents": 2,
    "visualizations": 3,
    "files": 5
  }
}
```

Counts are computed from `session_resources` without loading presentations or
scanning transcript messages. Categories are independent filters and may overlap:
for example, a file with a document presentation contributes to both `files` and
`documents`; callers must not sum category counts to derive `total`.

After the first message paint:

- the document panel loads `presentation_type=document` when needed;
- the visualization panel loads `presentation_type=visualization` when needed;
- the composer loads active file and artifact resources when its resource menu is
  opened.

There is no historical-message fallback and no process-memory fallback.

## Model Context

The bounded Session Resources projector queries active resources through
`SessionResourceService`. It includes stable identity, kind, role, label, locator,
source tool, and usage hints. It does not include document preview payloads or full
visualization specifications unless a tool explicitly resolves the selected resource.

`list_session_resources` uses the same service and authorized session ID. No model
tool accepts an arbitrary session ID from model arguments.

## Frontend State

The frontend has one session-scoped resource store:

```text
sessionResourcesById
resourceCounts
resourcesLoadedByFilter
resourcesLoadingByFilter
```

Computed views provide:

- document resources where `presentation_type=document`;
- visualization resources where `presentation_type=visualization`;
- selectable files where `kind=file|artifact` and `status=active`.

Remove independent `officeDocumentHistory`, `lastOfficeDocument`,
`visualizationHistory`, and resource-specific `lazyArtifacts` state. Real-time SSE
resources and restored resources both call the same resource upsert action.

Switching sessions activates a separate resource map keyed by session ID. Filtered
pagination merges by `resource_id` and cannot duplicate entries.

## Error Handling

### Validation Failure

- Valid entries in a tool result remain eligible for persistence.
- Invalid entries are rejected and omitted from the transaction.
- The terminal event includes bounded structured `resource_errors`.
- The runtime never converts an invalid entry into a path-only fallback.

### Persistence Failure

The terminal event reports:

```json
{
  "resource_durable": false,
  "resource_error": "resource_persistence_failed"
}
```

The route does not retry through another store. The current client may render a
temporary resource, but it must mark it non-durable. A later restore reads only the
database.

### Missing or Invalid Target

Resolution can update a resource to `missing` or `invalid`. Such resources are
excluded from default model projection, composer results, and presentation queries.
The service does not scan the filesystem or historical messages for replacements.

## Session Deletion

True logical conversation deletion performs an authorized, retry-safe lifecycle:

1. delete source-specific transcript or conversation data;
2. delete all `session_resources` rows and the session resource version;
3. delete the Conversation Catalog entry.

Resource deletion is idempotent. Partial failures log the completed stage and permit
retry with the same session ID.

## Hard-Cutover Migration

Deployment uses a maintenance window with no dual-write period:

1. stop application writers;
2. create `session_resources` and required indexes/version storage;
3. drop `session_resource_manifests`;
4. drop `sessions.data_ids`, `sessions.visual_ids`, and
   `sessions.office_documents`;
5. remove existing `visualizations` keys from session metadata;
6. deploy the backend explicit resource contract and unified service;
7. deploy the frontend unified resource store;
8. start services and run new-session smoke tests.

No old resource row, preview payload, visualization payload, or transcript resource
event is migrated. Old conversation messages remain governed by the existing message
retention policy.

## Code Removal Scope

Backend removal includes:

- `LegacyResourceViews` and `derive_legacy_views()`;
- compatibility normalizer fields and nested-result inference;
- `_extract_office_documents_from_messages()`;
- `_capture_office_document()`;
- route-owned visual and office-document collection;
- resource parameters in `ConversationPersistenceService`;
- independent document and visualization restore routes;
- all reads and writes of removed Session resource fields;
- process-memory and transcript-based resource recovery.

Frontend removal includes:

- message-based document and visualization extractors used for recovery;
- independent office-document and visualization histories;
- independent lazy-artifact flags and setters;
- dedicated document and visualization session API functions;
- complete-event handling of legacy `office_documents` and `visuals` fields.

## Observability

Emit structured metrics and logs for:

- accepted and rejected resource entries by tool, kind, and presentation type;
- inserted and replaced resource keys;
- transaction duration and failure counts;
- stale-run writes rejected;
- query counts, filter types, pagination, and response size;
- model projection count and truncation;
- resources marked missing or invalid;
- session resource deletion stages.

Logs include session ID, run ID, tool name, resource key, and bounded error codes, but
not full presentation specifications or sensitive file contents.

## Test Strategy

### Contract Tests

- resource-producing tools return explicit `resources`;
- legacy fields never generate resources;
- mutable documents and visualizations require `logical_key`;
- locator and presentation combinations are type-valid;
- metadata, Markdown, and visualization payload limits are enforced.

### Persistence Tests

- a new logical version completely replaces the old version;
- distinct resource keys remain a union;
- an empty run does not clear resources;
- stale runs cannot replace current resources;
- same-run retries are idempotent;
- complete, incomplete, interrupted, and fatal terminal paths persist successful
  resources;
- persistence failures never claim durability.

### End-to-End Tests

- an upload appears in the composer but not the document panel;
- presenting the upload creates or replaces a document presentation;
- a generated report survives page refresh and service restart;
- editing a document removes the old version and restores only the new version;
- a visualization survives refresh without session metadata;
- Web and Social read the same resources for the same authorized session ID;
- deleting a session removes every resource;
- counts and filtered cursor pagination remain correct.

### Negative Legacy Tests

Assert that none of the following restore a resource:

- removed legacy fields supplied to Session/API contract fixtures;
- legacy `visualizations` content supplied in metadata fixtures;
- transcript `pdf_preview`, `html_preview`, or `visuals` payloads;
- tool results containing only `file_path`, `data_id`, or `data_ids`.

Migration schema tests separately assert that the removed session columns and old
manifest table no longer exist.

### Frontend Tests

- real-time and restored resources use the same upsert action;
- documents, visualizations, and selectable files are computed from one map;
- session switching cannot leak resources;
- filtered pages merge without duplicates;
- non-durable temporary resources do not reappear after refresh.

## Acceptance Criteria

- `session_resources` is the only persistent session resource state.
- No Session model, transcript, metadata field, route collector, or frontend history
  stores a second resource copy.
- Every durable resource originates from an explicit tool `resources` declaration.
- The model, composer, document panel, visualization panel, and restore counts query
  the same service.
- Mutable resources retain only their latest logical version.
- Restore never scans historical messages or process memory for resources.
- Old sessions restore messages but no old resource state.
- Terminal durability reporting matches the committed database state.
- All selected backend and frontend tests pass under the configured Python 3.11
  environment and the project frontend test runner.
