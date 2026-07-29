# Session Resource Manifest Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build one session-scoped resource-reference mechanism that captures, persists, restores, projects, and lists important data/file/artifact/URL/visual references across requests and across every agent mode, including Social.

**Architecture:** Normalize references once at the shared `ReActAgent.analyze` event boundary, accumulate them for the run, and persist them before a terminal event is delivered. The canonical store is one independent `session_resource_manifests` table keyed only by `session_id`; it has no foreign key to mode-specific transcript tables, so Web, Social, expert, and every other mode read and merge the same row even when their transcript backends differ. Existing session fields are derived compatibility views only. The model receives a bounded projection of active references; full historical tool events remain excluded.

**Tech Stack:** Python 3.11, Pydantic, SQLAlchemy async sessions, PostgreSQL JSONB/JSON, pytest, existing ReAct runtime and tool registry. Run all Python commands with `conda run -p /root/miniconda3/envs/backend_py311`.

---

## File Structure

Create a focused `app.agent.resources` package:

- `backend/app/agent/resources/models.py`: typed resource kinds, statuses, locators, and immutable reference identity.
- `backend/app/agent/resources/normalizer.py`: pure structural extraction from canonical and compatibility tool-result shapes.
- `backend/app/agent/resources/manifest.py`: deterministic merge, supersession, compatibility projections, filtering, and bounded projection.
- `backend/app/agent/resources/service.py`: mode-independent load/merge/delete API used by runtime and tools.
- `backend/app/db/session_resource_repository.py`: atomic access to the independent shared manifest table.
- `backend/app/tools/utility/list_session_resources_tool.py`: authorized read-only discovery tool.

Modify existing integration points without creating mode-specific variants:

- A standalone table persists the typed manifest independently of transcript storage.
- `ReActAgent.analyze` captures and flushes references for all consumers.
- `SimplifiedContextBuilder` injects the same projected resource section for all modes.
- Web and Social stop owning `data_id` collection.
- True session deletion and expiry delete the shared manifest; Social mapping deletion alone does not.
- Operations audit declares ordinary file/data refs but receives no persistence-specific code.

## Task 1: Typed Resource Model and Stable Identity

**Files:**
- Create: `backend/app/agent/resources/__init__.py`
- Create: `backend/app/agent/resources/models.py`
- Create: `backend/app/agent/resources/models_test.py`

- [ ] **Step 1: Write failing model tests**

```python
from app.agent.resources.models import (
    ResourceImportance,
    ResourceKind,
    ResourceLocator,
    ResourceRole,
    ResourceStatus,
    SessionResourceRef,
)


def test_ref_id_is_stable_for_equivalent_file_paths(tmp_path):
    target = tmp_path / "out" / "report.json"
    target.parent.mkdir()
    target.write_text("{}", encoding="utf-8")

    first = SessionResourceRef.create(
        kind=ResourceKind.FILE,
        locator=ResourceLocator(path=str(target)),
        role=ResourceRole.OUTPUT,
        label="Report",
        tool_name="report_tool",
        run_id="run-a",
        turn_sequence=1,
    )
    second = SessionResourceRef.create(
        kind=ResourceKind.FILE,
        locator=ResourceLocator(path=str(target.parent / "." / target.name)),
        role=ResourceRole.OUTPUT,
        label="Report v2",
        tool_name="report_tool",
        run_id="run-b",
        turn_sequence=2,
    )

    assert first.ref_id == second.ref_id
    assert first.locator.path == str(target.resolve())


def test_locator_requires_exactly_one_primary_identifier():
    try:
        ResourceLocator(data_id="dataset:v1:a", path="/tmp/a.json")
    except ValueError as exc:
        assert "exactly one" in str(exc)
    else:
        raise AssertionError("mixed locator must fail")


def test_new_reference_defaults_to_active_and_normal():
    ref = SessionResourceRef.create(
        kind=ResourceKind.DATA,
        locator=ResourceLocator(data_id="dataset:v1:a"),
        role=ResourceRole.PRIMARY,
        label="Dataset",
        tool_name="query",
        run_id="run-a",
        turn_sequence=1,
    )
    assert ref.status is ResourceStatus.ACTIVE
    assert ref.importance is ResourceImportance.NORMAL
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```bash
cd /home/xckj/suyuan/backend
conda run -p /root/miniconda3/envs/backend_py311 pytest -q app/agent/resources/models_test.py
```

Expected: FAIL during collection with `ModuleNotFoundError: No module named 'app.agent.resources'`.

- [ ] **Step 3: Implement the model**

Create `models.py` with these public types and behavior:

```python
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, model_validator


class ResourceKind(str, Enum):
    DATA = "data"
    FILE = "file"
    ARTIFACT = "artifact"
    URL = "url"
    VISUAL = "visual"


class ResourceRole(str, Enum):
    PRIMARY = "primary"
    SOURCE = "source"
    REPORT = "report"
    OUTPUT = "output"
    ATTACHMENT = "attachment"


class ResourceStatus(str, Enum):
    ACTIVE = "active"
    SUPERSEDED = "superseded"
    MISSING = "missing"
    INVALID = "invalid"


class ResourceImportance(str, Enum):
    NORMAL = "normal"
    HIGH = "high"
    PINNED = "pinned"


class ResourceLocator(BaseModel):
    data_id: str | None = None
    path: str | None = None
    url: str | None = None
    artifact_id: str | None = None
    visual_id: str | None = None

    @model_validator(mode="after")
    def validate_one_identifier(self) -> "ResourceLocator":
        values = [self.data_id, self.path, self.url, self.artifact_id, self.visual_id]
        if sum(bool(value) for value in values) != 1:
            raise ValueError("resource locator requires exactly one identifier")
        if self.path:
            self.path = str(Path(self.path).expanduser().resolve())
        return self

    def identity_payload(self) -> dict[str, str]:
        return {
            key: value
            for key, value in self.model_dump().items()
            if isinstance(value, str) and value
        }


class SessionResourceRef(BaseModel):
    ref_id: str
    kind: ResourceKind
    locator: ResourceLocator
    logical_key: str | None = None
    role: ResourceRole = ResourceRole.OUTPUT
    label: str
    tool_name: str
    run_id: str
    turn_sequence: int
    status: ResourceStatus = ResourceStatus.ACTIVE
    importance: ResourceImportance = ResourceImportance.NORMAL
    created_at: datetime
    last_seen_at: datetime
    last_used_at: datetime | None = None
    supersedes: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def create(cls, *, kind: ResourceKind, locator: ResourceLocator, **kwargs: Any) -> "SessionResourceRef":
        identity = json.dumps(
            {"kind": kind.value, "locator": locator.identity_payload()},
            ensure_ascii=False,
            sort_keys=True,
        )
        now = datetime.now(timezone.utc)
        return cls(
            ref_id=hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24],
            kind=kind,
            locator=locator,
            created_at=now,
            last_seen_at=now,
            **kwargs,
        )
```

Export these names from `app/agent/resources/__init__.py`.

- [ ] **Step 4: Run tests and verify GREEN**

Run the Task 1 command. Expected: `3 passed`.

- [ ] **Step 5: Commit**

```bash
git add backend/app/agent/resources
git commit -m "feat: add typed session resource references"
```

## Task 2: Structural Reference Normalizer

**Files:**
- Create: `backend/app/agent/resources/normalizer.py`
- Create: `backend/app/agent/resources/normalizer_test.py`
- Modify: `backend/app/tools/resource_refs.py`

- [ ] **Step 1: Write failing extraction tests**

Test these independent behaviors:

```python
from app.agent.resources.models import ResourceKind
from app.agent.resources.normalizer import normalize_tool_result_refs


def test_explicit_refs_take_precedence_and_preserve_business_metadata():
    refs, rejected = normalize_tool_result_refs(
        tool_name="ops_audit_run_rules",
        run_id="run-1",
        turn_sequence=3,
        result={
            "refs": {
                "files": [{
                    "path": "/tmp/final.json",
                    "logical_key": "ops_audit.final_issue_list",
                    "role": "output",
                    "label": "Final issue list",
                    "importance": "high",
                }]
            },
            "final_issue_list_path": "/tmp/ignored-compatibility.json",
        },
    )
    assert rejected == []
    assert len(refs) == 1
    assert refs[0].kind is ResourceKind.FILE
    assert refs[0].logical_key == "ops_audit.final_issue_list"
    assert refs[0].locator.path == "/tmp/final.json"


def test_known_nested_compatibility_fields_are_extracted():
    refs, rejected = normalize_tool_result_refs(
        tool_name="legacy_tool",
        run_id="run-2",
        turn_sequence=4,
        result={
            "data": {
                "data_id": "dataset:v1:abc",
                "file_path": "/tmp/output.csv",
            },
            "visuals": [{"id": "visual-a", "title": "Chart"}],
        },
    )
    assert rejected == []
    assert {ref.kind.value for ref in refs} == {"data", "file", "visual"}


def test_free_text_path_is_not_extracted():
    refs, rejected = normalize_tool_result_refs(
        tool_name="text_tool",
        run_id="run-3",
        turn_sequence=5,
        result={"summary": "Saved at /tmp/not-a-structured-ref.json"},
    )
    assert refs == []
    assert rejected == []


def test_invalid_explicit_ref_is_reported_without_failing_other_refs():
    refs, rejected = normalize_tool_result_refs(
        tool_name="mixed_tool",
        run_id="run-4",
        turn_sequence=6,
        result={"refs": {"files": [{"label": "missing path"}], "data": [{"data_id": "ok:v1:1"}]}},
    )
    assert [ref.locator.data_id for ref in refs] == ["ok:v1:1"]
    assert len(rejected) == 1
```

- [ ] **Step 2: Verify RED**

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest -q app/agent/resources/normalizer_test.py
```

Expected: FAIL because `normalize_tool_result_refs` does not exist.

- [ ] **Step 3: Implement explicit and compatibility extraction**

Implement `normalize_tool_result_refs(tool_name, run_id, turn_sequence, result) -> tuple[list[SessionResourceRef], list[dict[str, str]]]` as a pure function. Use fixed mappings:

```python
BUCKET_KINDS = {
    "data": ResourceKind.DATA,
    "files": ResourceKind.FILE,
    "artifacts": ResourceKind.ARTIFACT,
    "urls": ResourceKind.URL,
    "visuals": ResourceKind.VISUAL,
}

COMPATIBILITY_FIELDS = {
    "data_id": (ResourceKind.DATA, "data_id"),
    "report_data_id": (ResourceKind.DATA, "data_id"),
    "file_path": (ResourceKind.FILE, "path"),
    "local_path": (ResourceKind.FILE, "path"),
    "url": (ResourceKind.URL, "url"),
    "artifact_id": (ResourceKind.ARTIFACT, "artifact_id"),
    "visual_id": (ResourceKind.VISUAL, "visual_id"),
}
```

Only inspect the result root and a root `data` dictionary. Handle `data_ids`, `report_data_ids`, `source_data_ids`, and a root `visuals` list explicitly. Do not recurse arbitrary dictionaries and do not recognize arbitrary `*_path` keys.

Add optional `logical_key`, `role`, `label`, and `importance` keyword arguments to the builders in `app/tools/resource_refs.py`; preserve current callers through defaults and `**metadata`.

- [ ] **Step 4: Verify GREEN and existing builder compatibility**

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest -q \
  app/agent/resources/normalizer_test.py \
  app/tools/visualization/create_report_chart/report_chart_tool_checks.py \
  app/agent/memory/context_compressor_test.py -k 'resource_refs or resume_refs'
```

Expected: all selected tests pass. Do not address the two already-known display-tool restoration failures in this task.

- [ ] **Step 5: Commit**

```bash
git add backend/app/agent/resources/normalizer.py backend/app/agent/resources/normalizer_test.py backend/app/tools/resource_refs.py
git commit -m "feat: normalize tool resource references"
```

## Task 3: Manifest Merge, Supersession, Compatibility Views, and Projection

**Files:**
- Create: `backend/app/agent/resources/manifest.py`
- Create: `backend/app/agent/resources/manifest_test.py`

- [ ] **Step 1: Write failing merge tests**

```python
from app.agent.resources.manifest import merge_resource_refs
from app.agent.resources.models import ResourceKind, ResourceLocator, ResourceRole, ResourceStatus, SessionResourceRef


def make_ref(data_id: str, *, run_id: str, logical_key: str | None = None) -> SessionResourceRef:
    return SessionResourceRef.create(
        kind=ResourceKind.DATA,
        locator=ResourceLocator(data_id=data_id),
        logical_key=logical_key,
        role=ResourceRole.PRIMARY,
        label=data_id,
        tool_name="query",
        run_id=run_id,
        turn_sequence=1,
    )


def test_empty_incoming_does_not_clear_existing_refs():
    existing = [make_ref("data:v1:a", run_id="run-a")]
    assert merge_resource_refs(existing, []) == existing


def test_merge_is_idempotent_and_updates_last_seen_provenance():
    first = make_ref("data:v1:a", run_id="run-a")
    later = make_ref("data:v1:a", run_id="run-b")
    merged = merge_resource_refs([first], [later])
    assert len(merged) == 1
    assert merged[0].run_id == "run-b"
    assert merged[0].created_at == first.created_at


def test_new_logical_slot_value_supersedes_old_value():
    old = make_ref("data:v1:a", run_id="run-a", logical_key="result.primary")
    new = make_ref("data:v1:b", run_id="run-b", logical_key="result.primary")
    merged = merge_resource_refs([old], [new])
    assert next(ref for ref in merged if ref.ref_id == old.ref_id).status is ResourceStatus.SUPERSEDED
    assert old.ref_id in next(ref for ref in merged if ref.ref_id == new.ref_id).supersedes
```

- [ ] **Step 2: Write failing projection and compatibility tests**

```python
from app.agent.resources.manifest import derive_legacy_views, project_session_resources


def test_projection_excludes_inactive_refs_and_honors_character_budget():
    refs = [make_ref(f"data:v1:{index}", run_id="run") for index in range(40)]
    refs[0].status = ResourceStatus.MISSING
    text = project_session_resources(refs, query="latest data", available_tools={"read_data_registry"}, max_chars=1200)
    assert "data:v1:0" not in text
    assert len(text) <= 1200
    assert "additional resources" in text


def test_legacy_views_are_derived_only_from_active_manifest_refs():
    active = make_ref("data:v1:active", run_id="run")
    inactive = make_ref("data:v1:old", run_id="run")
    inactive.status = ResourceStatus.SUPERSEDED
    views = derive_legacy_views([active, inactive])
    assert views.data_ids == ["data:v1:active"]
```

- [ ] **Step 3: Verify RED**

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest -q app/agent/resources/manifest_test.py
```

Expected: FAIL because manifest functions do not exist.

- [ ] **Step 4: Implement deterministic merge and projection**

Implement these public functions:

```python
import json
from dataclasses import dataclass

from app.agent.resources.models import (
    ResourceImportance,
    ResourceKind,
    ResourceStatus,
    SessionResourceRef,
)


@dataclass(frozen=True)
class LegacyResourceViews:
    data_ids: list[str]
    office_documents: list[dict[str, object]]
    visual_ids: list[str]


def merge_resource_refs(
    existing: list[SessionResourceRef],
    incoming: list[SessionResourceRef],
) -> list[SessionResourceRef]:
    by_id = {ref.ref_id: ref.model_copy(deep=True) for ref in existing}
    for candidate_source in incoming:
        candidate = candidate_source.model_copy(deep=True)
        if candidate.logical_key:
            for current in by_id.values():
                if (
                    current.logical_key == candidate.logical_key
                    and current.ref_id != candidate.ref_id
                    and current.status is ResourceStatus.ACTIVE
                ):
                    current.status = ResourceStatus.SUPERSEDED
                    if current.ref_id not in candidate.supersedes:
                        candidate.supersedes.append(current.ref_id)

        previous = by_id.get(candidate.ref_id)
        if previous is not None:
            candidate.created_at = previous.created_at
            candidate.last_used_at = candidate.last_used_at or previous.last_used_at
            if previous.importance is ResourceImportance.PINNED:
                candidate.importance = ResourceImportance.PINNED
            candidate.supersedes = list(dict.fromkeys([*previous.supersedes, *candidate.supersedes]))
        by_id[candidate.ref_id] = candidate
    return sorted(by_id.values(), key=lambda ref: (ref.created_at, ref.ref_id))

def derive_legacy_views(refs: list[SessionResourceRef]) -> LegacyResourceViews:
    active = [ref for ref in refs if ref.status is ResourceStatus.ACTIVE]
    return LegacyResourceViews(
        data_ids=[ref.locator.data_id for ref in active if ref.kind is ResourceKind.DATA and ref.locator.data_id],
        office_documents=[
            {"file_path": ref.locator.path, "file_name": ref.label, "resource_ref_id": ref.ref_id}
            for ref in active
            if ref.kind in {ResourceKind.FILE, ResourceKind.ARTIFACT} and ref.locator.path
        ],
        visual_ids=[ref.locator.visual_id for ref in active if ref.kind is ResourceKind.VISUAL and ref.locator.visual_id],
    )

def project_session_resources(
    refs: list[SessionResourceRef],
    *,
    query: str,
    available_tools: set[str],
    max_chars: int = 8000,
) -> str:
    query_text = query.casefold()
    resolver_tool = {
        ResourceKind.DATA: "read_data_registry",
        ResourceKind.FILE: "read_file",
        ResourceKind.ARTIFACT: "present_artifact",
        ResourceKind.URL: "web_fetch",
        ResourceKind.VISUAL: "present_artifact",
    }

    def score(ref: SessionResourceRef) -> tuple[int, int, int, str]:
        searchable = " ".join([
            ref.label,
            ref.logical_key or "",
            json.dumps(ref.locator.identity_payload(), ensure_ascii=False),
        ]).casefold()
        query_match = int(bool(query_text and query_text in searchable))
        importance = {
            ResourceImportance.NORMAL: 0,
            ResourceImportance.HIGH: 1,
            ResourceImportance.PINNED: 2,
        }[ref.importance]
        tool_available = int(resolver_tool[ref.kind] in available_tools)
        recent = (ref.last_used_at or ref.last_seen_at).isoformat()
        return query_match, importance, tool_available, recent

    active = [ref for ref in refs if ref.status is ResourceStatus.ACTIVE]
    active.sort(key=score, reverse=True)
    lines = ["Available resources from this session:"]
    included = 0
    for ref in active:
        locator = next(iter(ref.locator.identity_payload().values()))
        line = f"- {ref.ref_id} | {ref.kind.value} | {ref.label} | {locator} | via {resolver_tool[ref.kind]}"
        suffix = f"\n- {len(active) - included} additional resources; use list_session_resources."
        if len("\n".join([*lines, line])) + len(suffix) > max_chars:
            break
        lines.append(line)
        included += 1
    if included < len(active):
        lines.append(f"- {len(active) - included} additional resources; use list_session_resources.")
    return "\n".join(lines)[:max_chars]

def filter_session_resources(
    refs: list[SessionResourceRef],
    *,
    kind: ResourceKind | None = None,
    status: ResourceStatus | None = None,
    label: str | None = None,
    tool_name: str | None = None,
    run_id: str | None = None,
    logical_key: str | None = None,
) -> list[SessionResourceRef]:
    label_text = label.casefold() if label else None
    return [
        ref
        for ref in refs
        if (kind is None or ref.kind is kind)
        and (status is None or ref.status is status)
        and (label_text is None or label_text in ref.label.casefold())
        and (tool_name is None or ref.tool_name == tool_name)
        and (run_id is None or ref.run_id == run_id)
        and (logical_key is None or ref.logical_key == logical_key)
    ]
```

Use deterministic priority `explicit query match > pinned > high > available resolver tool > last_used_at > last_seen_at`. Never mutate caller-owned model instances; use `model_copy(deep=True)`.

- [ ] **Step 5: Verify GREEN**

Run the Task 3 test command. Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add backend/app/agent/resources/manifest.py backend/app/agent/resources/manifest_test.py
git commit -m "feat: merge and project session resource manifests"
```

## Task 4: Add the Independent Shared Manifest Store

**Files:**
- Create: `backend/app/db/migrations/008_create_session_resource_manifests.sql`
- Modify: `backend/app/db/models_session.py`
- Create: `backend/app/db/session_resource_repository.py`
- Create: `backend/app/db/session_resource_repository_test.py`
- Create: `backend/app/agent/resources/service.py`
- Create: `backend/app/agent/resources/service_test.py`

- [ ] **Step 1: Write failing service contract tests**

Use a fake repository to prove the service API is independent of mode and transcript manager:

```python
@pytest.mark.asyncio
async def test_same_session_id_has_one_manifest_across_modes(fake_repository, make_ref):
    service = SessionResourceManifestService(fake_repository)
    await service.merge("shared-a", [make_ref("data:v1:web")])
    await service.merge("shared-a", [make_ref("data:v1:social")])

    loaded = await service.load("shared-a")
    assert {ref.locator.data_id for ref in loaded.refs} == {
        "data:v1:web",
        "data:v1:social",
    }
    assert loaded.version == 2
```

Also assert an empty merge never clears prior refs, `delete(session_id)` removes the row, and repository failures surface as `ManifestPersistenceError` rather than returning a false success.

- [ ] **Step 2: Write failing repository transaction tests**

Against the project's disposable PostgreSQL test database, assert:

- a missing session ID loads as an empty manifest without requiring a row in `sessions` or a Social transcript file;
- two `asyncio.gather()` merges with disjoint refs leave their union;
- each successful non-empty merge increments `version` exactly once;
- deletion is idempotent;
- no foreign key exists from the new table to `sessions`.

- [ ] **Step 3: Verify RED**

```bash
cd /home/xckj/suyuan/backend
conda run -p /root/miniconda3/envs/backend_py311 pytest -q \
  app/agent/resources/service_test.py \
  app/db/session_resource_repository_test.py
```

Expected: FAIL because the shared table, repository, and service do not exist.

- [ ] **Step 4: Add the standalone schema and ORM model**

Migration content:

```sql
CREATE TABLE IF NOT EXISTS session_resource_manifests (
    session_id VARCHAR(255) PRIMARY KEY,
    resource_refs JSONB NOT NULL DEFAULT '[]'::jsonb,
    version INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_session_resource_manifests_updated_at
    ON session_resource_manifests (updated_at);
```

Add `SessionResourceManifestDB` to `models_session.py` so the existing session database metadata/import path sees it. Deliberately add no relationship and no foreign key: Social can own the same logical session ID while its transcript remains file-backed.

- [ ] **Step 5: Implement one atomic repository for every mode**

`SessionResourceRepository` exposes only:

```python
async def load(self, session_id: str) -> StoredSessionResourceManifest: ...
async def merge(self, session_id: str, incoming: list[SessionResourceRef]) -> StoredSessionResourceManifest: ...
async def delete(self, session_id: str) -> bool: ...
```

For a non-empty merge, start one transaction, insert the row with `ON CONFLICT DO NOTHING`, select it `FOR UPDATE`, parse refs, call the pure `merge_resource_refs()`, update refs/version/timestamp, and commit. The row lock serializes concurrent writers; never perform read-modify-write across separate transactions. Empty merges return `load()` and do not create a row or increment the version.

- [ ] **Step 6: Implement the mode-independent service**

`SessionResourceManifestService` validates `session_id`, converts stored JSON through `SessionResourceRef`, delegates atomic operations to the repository, and wraps database failures in `ManifestPersistenceError`. Its public methods contain no `mode`, `SessionManager`, or `session_resolver` parameter. Export a dependency/getter used by runtime, tools, and deletion workflows.

Do not add canonical manifest fields to `Session`, `SessionDB`, or Social JSON. Do not backfill from `data_ids`, `office_documents`, old tool events, or other historical fields.

- [ ] **Step 7: Verify GREEN**

Run the Task 4 test command. Expected: all service and repository tests pass, including the concurrent union.

- [ ] **Step 8: Commit**

```bash
git add backend/app/db/migrations/008_create_session_resource_manifests.sql \
  backend/app/db/models_session.py backend/app/db/session_resource_repository.py \
  backend/app/db/session_resource_repository_test.py \
  backend/app/agent/resources/service.py backend/app/agent/resources/service_test.py
git commit -m "feat: add shared session resource manifest store"
```

## Task 5: Capture References Once in ReActAgent and Flush Every Terminal Path

**Files:**
- Create: `backend/app/agent/resources/runtime.py`
- Create: `backend/app/agent/resources/runtime_test.py`
- Modify: `backend/app/agent/react_agent.py`

- [ ] **Step 1: Write failing accumulator tests**

```python
from app.agent.resources.runtime import RunReferenceAccumulator


def test_accumulator_reads_nested_streaming_tool_result():
    accumulator = RunReferenceAccumulator(run_id="run-a")
    event = {
        "type": "tool_result",
        "data": {
            "tool_name": "query",
            "result": {"data_id": "dataset:v1:a"},
            "is_error": False,
        },
    }
    accumulator.capture(event, turn_sequence=2)
    assert [ref.locator.data_id for ref in accumulator.refs] == ["dataset:v1:a"]


def test_accumulator_ignores_failed_tool_results():
    accumulator = RunReferenceAccumulator(run_id="run-a")
    accumulator.capture({
        "type": "tool_result",
        "data": {"tool_name": "query", "result": {"data_id": "bad:v1:a"}, "is_error": True},
    }, turn_sequence=2)
    assert accumulator.refs == []
```

- [ ] **Step 2: Write failing ReActAgent terminal-path tests**

Use a fake ReAct loop that emits one successful tool result followed separately by each of `complete`, `incomplete`, `interrupted`, and `fatal_error`. Inject a fake `SessionResourceManifestService` and assert `merge(actual_session_id, refs)` is awaited before the terminal event is yielded to the consumer. Parameterize over every runtime mode, including `assistant`, expert/deliberation modes, and `social`, and assert they call the same service method with no mode-specific store.

- [ ] **Step 3: Verify RED**

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest -q app/agent/resources/runtime_test.py
```

Expected: FAIL because the accumulator and common flush do not exist.

- [ ] **Step 4: Implement the accumulator**

`RunReferenceAccumulator.capture()` must unwrap `event.data.result`, call the normalizer, merge duplicate refs, and expose bounded rejected diagnostics. It must also capture `office_document` and `html_document` structured refs through the same normalizer adapter.

- [ ] **Step 5: Integrate at the shared analyze boundary**

In `ReActAgent.analyze`, create one accumulator immediately before `react_loop.run`. For every emitted event:

```python
event_data = event.get("data") if isinstance(event.get("data"), dict) else {}
accumulator.capture(event, turn_sequence=int(event_data.get("iteration") or 0))
if event.get("type") in {"complete", "incomplete", "interrupted", "fatal_error"}:
    manifest = await resource_manifest_service.merge(actual_session_id, accumulator.refs)
    event.setdefault("data", {}).update({
        "resource_refs_version": manifest.version,
        "resource_refs_durable": True,
    })
yield event
```

Guard this block with run ownership so a stale run cannot publish terminal metadata for a newer run. Repository row locking still preserves the union if legitimate runs overlap. In `finally`, flush once if the generator is closed after successful tool events but before a terminal event.

If persistence fails before a terminal event is sent, emit `resource_refs_durable=False` plus a bounded error code on that terminal event and log at error level; never report a version or claim success. Current-turn refs may remain available in memory for that response, but the next request must reload only the shared table. If generator closure prevents an event, log the non-durable flush with session/run identifiers.

After a successful merge, derive legacy `data_ids`, `office_documents`, and visual IDs and update them through the existing mode-specific session manager only as compatibility projections. A failure to update that projection must not roll back or redefine the canonical manifest. `_session_store` may cache the projection for same-process display, but never becomes a read source for the next model request.

- [ ] **Step 6: Verify GREEN**

Run the Task 5 test command. Expected: all terminal-path and mode cases pass.

- [ ] **Step 7: Commit**

```bash
git add backend/app/agent/resources/runtime.py backend/app/agent/resources/runtime_test.py backend/app/agent/react_agent.py
git commit -m "feat: capture resource refs at shared agent boundary"
```

## Task 6: Inject a Bounded Resource Context in Every Mode

**Files:**
- Modify: `backend/app/agent/context/context_builder.py`
- Modify: `backend/app/agent/react_agent.py`
- Create: `backend/app/agent/context/session_resource_context_test.py`

- [ ] **Step 1: Write failing all-mode projection tests**

Parameterize over every mode listed in `app.agent.prompts.prompt_builder.AgentMode`, including `social` and `memory_consolidator`. Set `builder.session_resource_context` to a known block, build the system prompt, and assert the block occurs exactly once for every mode.

Add a test that `ReActAgent` calls the shared manifest service with `actual_session_id`, calls `project_session_resources()` with the current query and available tool names, and assigns the result before the first planner call. Use different transcript managers for Web and Social but the same fake shared manifest service, and assert identical projected content.

- [ ] **Step 2: Verify RED**

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest -q app/agent/context/session_resource_context_test.py
```

Expected: FAIL because the context builder has no session resource context.

- [ ] **Step 3: Implement mode-independent prompt injection**

Add `self.session_resource_context: str | None = None` to `SimplifiedContextBuilder`. In `_build_system_prompt`, append it after the mode prompt and before runtime metadata:

```python
if self.session_resource_context:
    sections.append(
        "<session_resources>\n"
        + self.session_resource_context.strip()
        + "\n</session_resources>"
    )
```

Do not clear it in `_apply_mode_context_policy`; resource context is explicitly shared across modes.

After `_get_or_create_session`, load current refs from `SessionResourceManifestService` using only `actual_session_id`, compute a projection with an 8,000-character budget, and assign it to the new run's context builder. An empty manifest produces no section. Transcript restoration remains mode-specific and continues to omit display-only tool events; resource restoration does not depend on transcript replay.

- [ ] **Step 4: Verify GREEN and token accounting**

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest -q \
  app/agent/context/session_resource_context_test.py \
  app/agent/context/context_builder_prompt_isolation_test.py
```

Expected: all selected tests pass and existing mode-specific isolation remains intact.

- [ ] **Step 5: Commit**

```bash
git add backend/app/agent/context/context_builder.py backend/app/agent/react_agent.py \
  backend/app/agent/context/session_resource_context_test.py
git commit -m "feat: project session resources into every mode"
```

## Task 7: Add Authorized Resource Discovery Tool

**Files:**
- Create: `backend/app/tools/utility/list_session_resources_tool.py`
- Create: `backend/app/tools/utility/list_session_resources_tool_test.py`
- Create: `backend/app/agent/prompts/session_resource_tool_registry_test.py`
- Modify: `backend/app/tools/__init__.py`
- Modify: `backend/app/agent/prompts/tool_registry.py`

- [ ] **Step 1: Write failing tool tests**

Test that a context-aware `ListSessionResourcesTool`:

- loads only `context.session_id` through the shared manifest service;
- filters by kind, status, label, tool name, run ID, and logical key;
- returns compact dictionaries without resource contents;
- rejects attempts to pass another session ID because the schema contains no session parameter;
- returns the same manifest for Web and `runtime_mode="social"` when `context.session_id` is the same.

Representative assertion:

```python
result = await tool.execute(context, kind="file", logical_key="ops_audit.final_issue_list")
assert result["success"] is True
assert result["data"][0]["locator"]["path"].endswith("final.json")
assert "session_id" not in tool.get_function_schema()["parameters"]["properties"]
```

In `session_resource_tool_registry_test.py`, import every `*_TOOL_NAMES` list from `tool_registry.py` and parameterize over them. Assert `list_session_resources` occurs exactly once in assistant, expert, query, report, chart, ops, graph, social, memory consolidator, and all four deliberation lists.

- [ ] **Step 2: Verify RED**

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest -q app/tools/utility/list_session_resources_tool_test.py
```

Expected: FAIL because the tool does not exist.

- [ ] **Step 3: Implement and register the tool**

Initialize it with `LLMTool(name="list_session_resources", description="List resources saved in the current authorized session", category=ToolCategory.QUERY, version="1.0.0", requires_context=True)` and use `filter_session_resources`. The schema must not accept `session_id`; the tool gets the authorized current session solely from `ExecutionContext`. Return no more than 100 refs and include `total_matches` plus a truncation flag. Register it once in the global registry and add it to every ReAct mode tool list, including Social and memory consolidation modes.

- [ ] **Step 4: Verify GREEN and registry coverage**

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest -q \
  app/tools/utility/list_session_resources_tool_test.py \
  app/agent/prompts/session_resource_tool_registry_test.py
```

Expected: all selected tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/app/tools/utility/list_session_resources_tool.py \
  backend/app/tools/utility/list_session_resources_tool_test.py \
  backend/app/agent/prompts/session_resource_tool_registry_test.py \
  backend/app/tools/__init__.py backend/app/agent/prompts/tool_registry.py
git commit -m "feat: list resources from the current session"
```

## Task 8: Remove Transport-Owned Reference Persistence

**Files:**
- Modify: `backend/app/routers/agent.py`
- Modify: `backend/app/social/agent_bridge.py`
- Modify: `backend/app/agent/session/conversation_persistence.py`
- Modify: `backend/app/api/session_routes.py`
- Modify: `backend/app/conversations/service.py`
- Modify: `backend/app/agent/session/persistence_contract_test.py`
- Modify: `backend/app/agent/session/social_session_storage_test.py`
- Create: `backend/app/agent/session/transport_resource_ownership_test.py`
- Create: `backend/app/conversations/session_resource_lifecycle_test.py`

- [ ] **Step 1: Write failing ownership tests**

Add source-level or behavior-level tests asserting:

- Web and Social no longer initialize or mutate `collected_data_ids` from tool events;
- `ConversationPersistenceService.apply_metadata()` cannot clear resource-derived compatibility fields when the current turn has no refs;
- transcript persistence with a stale Session object cannot overwrite a manifest already merged by `ReActAgent` because transcripts do not contain the canonical field;
- an authorized true conversation deletion removes transcript/catalog data and the shared manifest;
- deleting only a Social user mapping does not delete the manifest;
- expiry cleanup invokes the same true-deletion lifecycle instead of leaving orphan manifests.

- [ ] **Step 2: Verify RED**

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest -q app/agent/session/transport_resource_ownership_test.py
```

Expected: FAIL because both transports still parse `event.data.data_id` and Web persistence still applies empty current-turn collections.

- [ ] **Step 3: Remove duplicated collection and replacement semantics**

Delete transport code that extracts `data_id`/`data_ids`. Keep visual rendering collection only where the frontend needs immediate display; it must not own manifest durability. Remove `collected_data_ids` parameters from route-owned transcript persistence calls after updating `ConversationPersistenceService` to leave canonical compatibility fields to the manifest service.

Retain the deliberate policy in `SessionMemory.load_history_messages`: display `tool_use` and `tool_result` rows are not restored into model history. Update conflicting old tests in `context_compressor_test.py` so they assert references come from the manifest projection rather than historical tool replay.

- [ ] **Step 4: Centralize true-deletion lifecycle**

Add the manifest service to the authenticated conversation deletion workflow. After `catalog.require_write()` authorizes access and the source adapter deletes the transcript, delete the manifest and catalog entry as one explicit orchestration sequence. Treat manifest deletion as idempotent; if a downstream deletion fails, return an error and log the partial state so retry is safe.

Route expiry cleanup through the same session-ID lifecycle helper or explicitly delete each successfully expired manifest. Do not attach manifest deletion to `social_routes.delete_session`, because that endpoint currently deletes only `social_user_id -> session_id` mapping ownership, not the logical conversation itself. Add a separate explicit true-delete path later if product semantics require Social users to erase the whole conversation.

- [ ] **Step 5: Verify GREEN**

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest -q \
  app/agent/session/transport_resource_ownership_test.py \
  app/conversations/session_resource_lifecycle_test.py \
  app/agent/session/persistence_contract_test.py \
  app/agent/session/social_session_storage_test.py \
  app/agent/memory/context_compressor_test.py
```

Expected: all selected tests pass, including the two tests that failed during diagnosis after being rewritten to the approved manifest behavior.

- [ ] **Step 6: Commit**

```bash
git add backend/app/routers/agent.py backend/app/social/agent_bridge.py \
  backend/app/agent/session/conversation_persistence.py \
  backend/app/api/session_routes.py backend/app/conversations/service.py \
  backend/app/agent/session/persistence_contract_test.py \
  backend/app/agent/session/social_session_storage_test.py \
  backend/app/agent/session/transport_resource_ownership_test.py \
  backend/app/conversations/session_resource_lifecycle_test.py \
  backend/app/agent/memory/context_compressor_test.py
git commit -m "refactor: centralize session resource persistence"
```

## Task 9: Make Operations Audit Declare Generic Resource Refs

**Files:**
- Modify: `backend/app/tools/analysis/ops_work_order_audit/tool.py`
- Create: `backend/app/tools/analysis/ops_work_order_audit/resource_refs_test.py`

- [ ] **Step 1: Write a failing tool-contract test**

Run the rules tool with a small fixture or patch its rule engine result. Assert that the result declares:

- every returned output path as a normal file ref;
- `final_issue_list_path` with `logical_key="ops_audit.final_issue_list"`, label `Final issue list`, role `output`, and high importance;
- the generated summary `data_id` as a data ref when present.

Do not assert any session persistence behavior in this test.

- [ ] **Step 2: Verify RED**

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest -q app/tools/analysis/ops_work_order_audit/resource_refs_test.py
```

Expected: FAIL because the audit result currently returns paths without explicit `refs`.

- [ ] **Step 3: Add ordinary resource declarations**

Use `build_file_ref`, `build_data_ref`, and `merge_refs` from `app.tools.resource_refs`. Keep all logic inside the tool-result contract; do not import the session manifest service or add audit-specific persistence code.

- [ ] **Step 4: Verify GREEN and audit regressions**

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest -q \
  app/tools/analysis/ops_work_order_audit/resource_refs_test.py \
  app/services/ops_audit/final_issue_list_test.py \
  app/services/ops_audit/test_visual_evidence_reporting.py
```

Expected: all selected tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/app/tools/analysis/ops_work_order_audit/tool.py \
  backend/app/tools/analysis/ops_work_order_audit/resource_refs_test.py
git commit -m "feat: declare operations audit resource references"
```

## Task 10: End-to-End Cross-Request, Cross-Mode, Concurrency, and Security Verification

**Files:**
- Create: `backend/tests/agent/test_session_resource_manifest_e2e.py`
- Create: `backend/tests/social/test_social_session_resource_manifest_e2e.py`
- Create: `backend/tests/agent/test_session_resource_manifest_security.py`

- [ ] **Step 1: Write the Web two-request test**

Request A must emit representative data, file, artifact, URL, and visual refs. Request B uses the same session and a different mode. Capture the planner system prompt and assert that active refs are present without historical tool-result replay or filesystem searching.

- [ ] **Step 2: Run Web E2E and verify RED if integration is incomplete**

```bash
cd /home/xckj/suyuan/backend
conda run -p /root/miniconda3/envs/backend_py311 pytest -q tests/agent/test_session_resource_manifest_e2e.py
```

Expected before final integration corrections: at least one cross-mode assertion fails for a concrete missing boundary.

- [ ] **Step 3: Write Social and mode-switch tests**

Cover Social request A followed by Web request B and Web request A followed by Social request B, using the same authorized session ID and the mode resolver patched to a temporary storage backend. Also verify separate heartbeat/consolidation session IDs remain isolated.

- [ ] **Step 4: Write concurrency and security tests**

Run two concurrent manifest merges with disjoint refs and assert the union. Verify a different catalog user cannot load or project another session's resources. Verify missing and invalid refs are excluded from the prompt and discoverable only when explicitly filtering their status.

- [ ] **Step 5: Run the new E2E suite**

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest -q \
  tests/agent/test_session_resource_manifest_e2e.py \
  tests/social/test_social_session_resource_manifest_e2e.py \
  tests/agent/test_session_resource_manifest_security.py
```

Expected: all tests pass.

- [ ] **Step 6: Run focused regression suites**

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest -q \
  app/agent/resources \
  app/agent/session \
  app/agent/context \
  app/tools/analysis/ops_work_order_audit \
  tests/social
```

Expected: all tests pass. If unrelated pre-existing failures exist, record their exact test names and confirm they reproduce on the base commit before proceeding.

- [ ] **Step 7: Run static and migration checks**

```bash
conda run -p /root/miniconda3/envs/backend_py311 python -m compileall -q app
git diff --check
```

Expected: both commands exit 0 with no output from `git diff --check`.

- [ ] **Step 8: Commit**

```bash
git add backend/tests/agent/test_session_resource_manifest_e2e.py \
  backend/tests/social/test_social_session_resource_manifest_e2e.py \
  backend/tests/agent/test_session_resource_manifest_security.py
git commit -m "test: verify session resources across requests and modes"
```

## Task 11: Final Verification and Operational Handoff

**Files:**
- Modify only if verification reveals a defect in files already listed above.

- [ ] **Step 1: Run the complete backend test suite**

```bash
cd /home/xckj/suyuan/backend
conda run -p /root/miniconda3/envs/backend_py311 pytest -q
```

Expected: suite passes, apart from explicitly documented unrelated base-branch failures approved by the user.

- [ ] **Step 2: Verify the database migration in a disposable database**

Use the project's existing migration runner or startup migration path against a disposable database. Query `information_schema.tables`, `information_schema.columns`, and PostgreSQL constraints. Assert `session_resource_manifests` exists with `session_id`, non-null `resource_refs`/`version` defaults, and no foreign key to any transcript table.

- [ ] **Step 3: Verify observability**

Run one two-request Web flow and one Social flow. Confirm structured logs include:

```text
session_resource_refs_extracted
session_resource_manifest_merged
session_resource_context_projected
```

Each event must include `session_id`, `run_id`, mode, counts by kind, version, and truncation/retry data without resource contents.

- [ ] **Step 4: Verify acceptance criteria manually from persisted state**

Inspect the shared manifest row plus one database-backed transcript and one Social session JSON. Confirm:

- manifests contain only post-deployment refs;
- the canonical refs exist only in `session_resource_manifests`, not in either transcript record;
- an empty second run did not clear refs;
- cross-mode prompt projection contains the same active resource;
- superseded and missing refs are absent from normal projection;
- true deletion removes the manifest, while Social mapping deletion alone does not;
- no audit-specific session persistence code exists (`rg "final_issue_list.*session|session.*final_issue_list" backend/app/agent backend/app/routers backend/app/social` returns no matches).

- [ ] **Step 5: Record final verification evidence**

Include exact test counts, migration result, log examples, and any accepted unrelated failures in the implementation handoff. Do not claim completion without fresh command output.
