from __future__ import annotations

import asyncio
import shutil
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from app.agent.cognition.llm_factory import create_llamaindex_llm
from app.agent.cognition.models import (
    CandidateEntity,
    CandidateRelation,
    CognitiveMapQuery,
    CognitiveSchema,
    ExtractionDiagnostic,
    ExtractionResult,
    ReviewStatus,
    SourceFile,
)
from app.agent.cognition.provider_factory import create_extractor_provider, create_parser_provider
from app.agent.cognition.view_builder import CognitiveMapViewBuilder
from app.utils.path_config import get_data_registry


router = APIRouter(prefix="/api/cognitive-maps", tags=["cognitive-maps"])

COGNITIVE_MAPS_ROOT = get_data_registry() / "cognitive_maps"
STALE_BUILDING_SECONDS = 600


class CognitiveMapCreateRequest(BaseModel):
    name: str
    description: str = ""


class CognitiveMapBuildRequest(BaseModel):
    parser_provider: str = "auto"
    extractor_provider: str = "local"
    llm_provider: str | None = None
    timeout_seconds: float = 300.0


class CognitiveMapBindingUpdateRequest(BaseModel):
    agent_modes: list[str]
    enabled: bool = True
    description: str = ""


class CognitiveMapQueryRequest(BaseModel):
    task: str
    agent_mode: str
    agent_role: str | None = None
    map_ids: list[str] | None = None
    data_ids: list[str] = Field(default_factory=list)
    entity_hints: list[str] = Field(default_factory=list)
    max_entities: int = 20
    max_relations: int = 20
    max_evidence: int = 10


class CognitiveMapEntityCreateRequest(BaseModel):
    name: str
    entity_type: str = "Entity"
    canonical_name: str | None = None
    aliases: list[str] = Field(default_factory=list)
    description: str | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)
    source_evidence_ids: list[str] = Field(default_factory=list)
    confidence: float = 1.0
    review_status: ReviewStatus = "confirmed"


class CognitiveMapEntityUpdateRequest(BaseModel):
    name: str | None = None
    entity_type: str | None = None
    canonical_name: str | None = None
    aliases: list[str] | None = None
    description: str | None = None
    attributes: dict[str, Any] | None = None
    review_status: ReviewStatus | None = None


class CognitiveMapRelationCreateRequest(BaseModel):
    source_entity_id: str
    target_entity_id: str
    relation_type: str = "related_to"
    description: str | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)
    source_evidence_ids: list[str] = Field(default_factory=list)
    confidence: float = 1.0
    review_status: ReviewStatus = "confirmed"


class CognitiveMapRelationUpdateRequest(BaseModel):
    source_entity_id: str | None = None
    target_entity_id: str | None = None
    relation_type: str | None = None
    description: str | None = None
    attributes: dict[str, Any] | None = None
    review_status: ReviewStatus | None = None


class CognitiveMapEntityMergeRequest(BaseModel):
    target_entity_id: str


def _ensure_root() -> Path:
    COGNITIVE_MAPS_ROOT.mkdir(parents=True, exist_ok=True)
    return COGNITIVE_MAPS_ROOT


def _map_dir(map_id: str) -> Path:
    return _ensure_root() / map_id


def _meta_path(map_id: str) -> Path:
    return _map_dir(map_id) / "map.json"


def _files_path(map_id: str) -> Path:
    return _map_dir(map_id) / "files.json"


def _extraction_path(map_id: str) -> Path:
    return _map_dir(map_id) / "extraction.json"


def _runs_path(map_id: str) -> Path:
    return _map_dir(map_id) / "build_runs.json"


def _evaluation_path(map_id: str) -> Path:
    return _map_dir(map_id) / "evaluation.json"


def _bindings_path() -> Path:
    return _ensure_root() / "agent_bindings.json"


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return path.read_text(encoding="utf-8")


def _load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    import json

    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Any) -> None:
    import json

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _require_map(map_id: str) -> dict[str, Any]:
    meta = _load_json(_meta_path(map_id), None)
    if meta is None:
        raise HTTPException(status_code=404, detail=f"Cognitive map not found: {map_id}")
    return meta


def _load_files(map_id: str) -> list[dict[str, Any]]:
    return _load_json(_files_path(map_id), [])


def _load_extraction(map_id: str) -> ExtractionResult | None:
    raw = _read_json(_extraction_path(map_id), None)
    if raw is None:
        return None
    return ExtractionResult.model_validate_json(raw)


def _require_extraction(map_id: str) -> ExtractionResult:
    extraction = _load_extraction(map_id)
    if extraction is None:
        raise HTTPException(status_code=404, detail=f"Cognitive map extraction not found: {map_id}")
    return extraction


def _load_runs(map_id: str) -> list[dict[str, Any]]:
    return _load_json(_runs_path(map_id), [])


def _latest_run(map_id: str) -> dict[str, Any] | None:
    runs = _load_runs(map_id)
    return runs[0] if runs else None


def _load_evaluation(map_id: str) -> dict[str, Any] | None:
    return _load_json(_evaluation_path(map_id), None)


def _load_bindings() -> list[dict[str, Any]]:
    return _load_json(_bindings_path(), [])


def _write_bindings(bindings: list[dict[str, Any]]) -> None:
    _write_json(_bindings_path(), bindings)


def _bindings_for_map(map_id: str) -> list[dict[str, Any]]:
    return [binding for binding in _load_bindings() if binding.get("map_id") == map_id]


def _enabled_binding_map_ids(agent_mode: str) -> list[str]:
    bindings = [
        binding for binding in _load_bindings()
        if binding.get("agent_mode") == agent_mode and binding.get("enabled", True)
    ]
    bindings.sort(key=lambda item: (item.get("priority", 100), item.get("updated_at", "")))
    return [binding["map_id"] for binding in bindings if binding.get("map_id")]


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _record_build_run(map_id: str, run: dict[str, Any]) -> None:
    runs = _load_runs(map_id)
    runs.insert(0, run)
    _write_json(_runs_path(map_id), runs[:50])


def _mark_stale_build_failed(meta: dict[str, Any]) -> dict[str, Any]:
    if meta.get("status") != "building":
        return meta
    updated_at = _parse_datetime(meta.get("updated_at") or meta.get("created_at"))
    if updated_at is None:
        return meta
    age_seconds = (datetime.utcnow() - updated_at).total_seconds()
    if age_seconds < STALE_BUILDING_SECONDS:
        return meta

    finished_at = datetime.utcnow().isoformat()
    error = f"Cognitive map stale building state exceeded {STALE_BUILDING_SECONDS} seconds"
    map_id = meta["id"]
    meta["status"] = "failed"
    meta["build_error"] = error
    meta["updated_at"] = finished_at
    _write_json(_meta_path(map_id), meta)
    latest_run = _latest_run(map_id)
    if latest_run is None or latest_run.get("status") != "failed" or latest_run.get("error") != error:
        _record_build_run(
            map_id,
            {
                "run_id": f"run_{uuid.uuid4().hex[:12]}",
                "status": "failed",
                "parser_provider": meta.get("parser_provider"),
                "requested_extractor_provider": meta.get("requested_extractor_provider"),
                "extractor_provider": meta.get("extractor_provider"),
                "llm_provider": meta.get("llm_provider"),
                "file_count": len(_load_files(map_id)),
                "chunk_count": 0,
                "timeout_seconds": STALE_BUILDING_SECONDS,
                "entity_count": 0,
                "relation_count": 0,
                "evidence_count": 0,
                "started_at": updated_at.isoformat(),
                "finished_at": finished_at,
                "duration_ms": int(age_seconds * 1000),
                "error": error,
            },
        )
    return meta


def _generate_evaluation(extraction: ExtractionResult) -> dict[str, Any]:
    entity_count = len(extraction.candidate_entities)
    relation_count = len(extraction.candidate_relations)
    evidence_count = len(extraction.evidence)
    entities_with_evidence = sum(1 for entity in extraction.candidate_entities if entity.source_evidence_ids)
    relations_with_evidence = sum(1 for relation in extraction.candidate_relations if relation.source_evidence_ids)
    entity_types: dict[str, int] = {}
    relation_types: dict[str, int] = {}
    for entity in extraction.candidate_entities:
        entity_types[entity.entity_type] = entity_types.get(entity.entity_type, 0) + 1
    for relation in extraction.candidate_relations:
        relation_types[relation.relation_type] = relation_types.get(relation.relation_type, 0) + 1
    return {
        "map_id": extraction.map_id,
        "entity_count": entity_count,
        "relation_count": relation_count,
        "evidence_count": evidence_count,
        "entities_with_evidence": entities_with_evidence,
        "relations_with_evidence": relations_with_evidence,
        "entity_evidence_ratio": round(entities_with_evidence / entity_count, 4) if entity_count else 0,
        "relation_evidence_ratio": round(relations_with_evidence / relation_count, 4) if relation_count else 0,
        "entity_types": entity_types,
        "relation_types": relation_types,
        "generated_at": datetime.utcnow().isoformat(),
        "diagnostic": extraction.diagnostics.model_dump(mode="json"),
    }


def _save_extraction(map_id: str, extraction: ExtractionResult) -> None:
    _extraction_path(map_id).write_text(
        extraction.model_dump_json(indent=2),
        encoding="utf-8",
    )
    _write_json(_evaluation_path(map_id), _generate_evaluation(extraction))

    meta = _require_map(map_id)
    meta["updated_at"] = datetime.utcnow().isoformat()
    _write_json(_meta_path(map_id), meta)


def _enrich_map(meta: dict[str, Any]) -> dict[str, Any]:
    extraction = _load_extraction(meta["id"])
    return {
        **meta,
        "file_count": len(_load_files(meta["id"])),
        "entity_count": len(extraction.candidate_entities) if extraction else 0,
        "relation_count": len(extraction.candidate_relations) if extraction else 0,
        "evidence_count": len(extraction.evidence) if extraction else 0,
        "parser_provider": meta.get("parser_provider"),
        "requested_extractor_provider": meta.get("requested_extractor_provider"),
        "extractor_provider": meta.get("extractor_provider"),
        "llm_provider": meta.get("llm_provider"),
        "build_error": meta.get("build_error"),
        "latest_run": _latest_run(meta["id"]),
        "evaluation": _load_evaluation(meta["id"]),
        "agent_bindings": _bindings_for_map(meta["id"]),
    }


def _entity_names(extraction: ExtractionResult) -> dict[str, str]:
    return {entity.entity_id: entity.name for entity in extraction.candidate_entities}


def _relation_to_response(relation: CandidateRelation, entity_names: dict[str, str]) -> dict[str, Any]:
    item = relation.model_dump(mode="json")
    item["source_name"] = entity_names.get(relation.source_entity_id, relation.source_entity_id)
    item["target_name"] = entity_names.get(relation.target_entity_id, relation.target_entity_id)
    return item


def build_cognitive_map_prompt_context(
    task: str,
    agent_mode: str,
    agent_role: str | None = None,
    map_ids: list[str] | None = None,
    entity_hints: list[str] | None = None,
) -> str:
    """Build compact cognitive map context for Agent prompt injection."""
    selected_map_ids = map_ids or _enabled_binding_map_ids(agent_mode)
    if not selected_map_ids:
        return ""

    query = CognitiveMapQuery(
        task=task,
        agent_mode=agent_mode,
        agent_role=agent_role,
        map_ids=selected_map_ids,
        entity_hints=entity_hints or [],
    )
    builder = CognitiveMapViewBuilder()
    summaries = []
    for map_id in selected_map_ids[:3]:
        extraction = _load_extraction(map_id)
        if extraction is None:
            continue
        view = builder.build_from_extraction(query, extraction)
        meta = _load_json(_meta_path(map_id), {})
        title = meta.get("name") or map_id
        summaries.append(f"### {title}\n{view.prompt_summary}")

    if not summaries:
        return ""
    return "\n\n".join([
        "## 已接入认知地图",
        "以下内容来自当前 Agent 模式绑定的认知地图。回答中涉及地图事实时，应优先依据这些实体、关系和证据；无证据内容需要明确标为假设或待确认。",
        *summaries,
    ])


def _build_query_views(payload: CognitiveMapQueryRequest) -> list[dict[str, Any]]:
    map_ids = payload.map_ids or _enabled_binding_map_ids(payload.agent_mode)
    query = CognitiveMapQuery(
        task=payload.task,
        agent_mode=payload.agent_mode,
        agent_role=payload.agent_role,
        map_ids=map_ids,
        data_ids=payload.data_ids,
        entity_hints=payload.entity_hints,
    )
    builder = CognitiveMapViewBuilder()
    views = []
    for map_id in map_ids:
        extraction = _load_extraction(map_id)
        if extraction is None:
            continue
        view = builder.build_from_extraction(
            query,
            extraction,
            max_entities=payload.max_entities,
            max_relations=payload.max_relations,
            max_evidence=payload.max_evidence,
        )
        item = view.model_dump(mode="json")
        meta = _load_json(_meta_path(map_id), {})
        item["map_name"] = meta.get("name") or map_id
        views.append(item)
    return views


def _safe_filename(filename: str) -> str:
    name = Path(filename or "upload.txt").name
    return name.replace("/", "_").replace("\\", "_")


def _delete_map_directory(map_id: str) -> None:
    root = _ensure_root().resolve()
    map_dir = _map_dir(map_id).resolve()
    if map_dir == root or root not in map_dir.parents:
        raise HTTPException(status_code=400, detail="Invalid cognitive map id")
    shutil.rmtree(map_dir)


def _parser_provider_for_source(source_file: SourceFile, requested_provider: str) -> str:
    provider = (requested_provider or "auto").strip().lower()
    if provider != "auto":
        return provider

    suffix = Path(source_file.filename).suffix.lower()
    if suffix == ".docx":
        return "docx"
    return "text"


@router.get("")
async def list_cognitive_maps() -> dict[str, Any]:
    root = _ensure_root()
    maps = []
    for map_path in sorted(root.iterdir()):
        if not map_path.is_dir():
            continue
        meta = _load_json(map_path / "map.json", None)
        if meta:
            meta = _mark_stale_build_failed(meta)
            maps.append(_enrich_map(meta))
    maps.sort(key=lambda item: item.get("updated_at") or item.get("created_at") or "", reverse=True)
    return {"maps": maps}


@router.post("")
async def create_cognitive_map(payload: CognitiveMapCreateRequest) -> dict[str, Any]:
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="name is required")

    now = datetime.utcnow().isoformat()
    map_id = f"cm_{uuid.uuid4().hex[:12]}"
    meta = {
        "id": map_id,
        "name": name,
        "description": payload.description,
        "status": "draft",
        "created_at": now,
        "updated_at": now,
    }
    _map_dir(map_id).mkdir(parents=True, exist_ok=True)
    _write_json(_meta_path(map_id), meta)
    _write_json(_files_path(map_id), [])
    return _enrich_map(meta)


@router.get("/bindings")
async def list_cognitive_map_agent_bindings(agent_mode: str | None = None) -> dict[str, Any]:
    bindings = _load_bindings()
    if agent_mode:
        bindings = [binding for binding in bindings if binding.get("agent_mode") == agent_mode]
    map_names = {}
    for binding in bindings:
        map_id = binding.get("map_id")
        if map_id and map_id not in map_names:
            meta = _load_json(_meta_path(map_id), None)
            map_names[map_id] = meta.get("name") if meta else map_id
    return {
        "bindings": [
            {
                **binding,
                "map_name": map_names.get(binding.get("map_id"), binding.get("map_id")),
            }
            for binding in bindings
        ]
    }


@router.post("/query")
async def query_cognitive_maps(payload: CognitiveMapQueryRequest) -> dict[str, Any]:
    views = _build_query_views(payload)
    return {
        "views": views,
        "prompt_context": "\n\n".join(view["prompt_summary"] for view in views),
    }


@router.delete("/{map_id}")
async def delete_cognitive_map(map_id: str) -> dict[str, Any]:
    _require_map(map_id)
    _delete_map_directory(map_id)
    _write_bindings([binding for binding in _load_bindings() if binding.get("map_id") != map_id])
    return {"deleted": True, "map_id": map_id}


@router.get("/{map_id}/bindings")
async def get_cognitive_map_agent_bindings(map_id: str) -> dict[str, Any]:
    _require_map(map_id)
    return {"bindings": _bindings_for_map(map_id)}


@router.put("/{map_id}/bindings")
async def update_cognitive_map_agent_bindings(
    map_id: str,
    payload: CognitiveMapBindingUpdateRequest,
) -> dict[str, Any]:
    _require_map(map_id)
    now = datetime.utcnow().isoformat()
    requested_modes = []
    for mode in payload.agent_modes:
        normalized = str(mode or "").strip()
        if normalized and normalized not in requested_modes:
            requested_modes.append(normalized)

    remaining = [binding for binding in _load_bindings() if binding.get("map_id") != map_id]
    new_bindings = [
        {
            "binding_id": f"cmb_{uuid.uuid4().hex[:12]}",
            "map_id": map_id,
            "agent_mode": mode,
            "enabled": payload.enabled,
            "priority": index + 1,
            "description": payload.description,
            "created_at": now,
            "updated_at": now,
        }
        for index, mode in enumerate(requested_modes)
    ]
    _write_bindings([*remaining, *new_bindings])
    return {"bindings": new_bindings}


@router.post("/{map_id}/files")
async def upload_cognitive_map_file(
    map_id: str,
    file: UploadFile = File(...),
) -> dict[str, Any]:
    meta = _require_map(map_id)
    file_id = f"file_{uuid.uuid4().hex[:12]}"
    filename = _safe_filename(file.filename or f"{file_id}.txt")
    storage_dir = _map_dir(map_id) / "files"
    storage_dir.mkdir(parents=True, exist_ok=True)
    storage_path = storage_dir / f"{file_id}_{filename}"

    with storage_path.open("wb") as target:
        shutil.copyfileobj(file.file, target)

    record = SourceFile(
        file_id=file_id,
        map_id=map_id,
        filename=filename,
        content_type=file.content_type or "application/octet-stream",
        storage_path=str(storage_path),
    ).model_dump(mode="json")
    files = _load_files(map_id)
    files.append(record)
    _write_json(_files_path(map_id), files)

    meta["status"] = "draft"
    meta["updated_at"] = datetime.utcnow().isoformat()
    _write_json(_meta_path(map_id), meta)
    return record


@router.get("/{map_id}/files")
async def list_cognitive_map_files(map_id: str) -> dict[str, Any]:
    _require_map(map_id)
    return {"files": _load_files(map_id)}


@router.post("/{map_id}/build")
async def build_cognitive_map(map_id: str, payload: CognitiveMapBuildRequest) -> dict[str, Any]:
    meta = _require_map(map_id)
    source_files = [SourceFile.model_validate(item) for item in _load_files(map_id)]
    if not source_files:
        raise HTTPException(status_code=400, detail="No files uploaded for cognitive map")

    meta["status"] = "building"
    meta["updated_at"] = datetime.utcnow().isoformat()
    _write_json(_meta_path(map_id), meta)
    run_id = f"run_{uuid.uuid4().hex[:12]}"
    started_at = datetime.utcnow().isoformat()
    start_time = time.perf_counter()
    chunks = []

    try:
        schema = CognitiveSchema.default_air_quality_schema()
        parser_providers_used = set()
        for source_file in source_files:
            parser_provider = _parser_provider_for_source(source_file, payload.parser_provider)
            parser_providers_used.add(parser_provider)
            parser = create_parser_provider(parser_provider)
            chunks.extend(await parser.parse(source_file))

        requested_extractor = (payload.extractor_provider or "local").strip().lower()
        llm = None
        if requested_extractor == "llamaindex":
            llm = create_llamaindex_llm(payload.llm_provider or "project")
        extractor = create_extractor_provider(requested_extractor, llm=llm)
        try:
            extraction = await asyncio.wait_for(
                extractor.extract(chunks=chunks, schema=schema),
                timeout=payload.timeout_seconds,
            )
        except asyncio.TimeoutError as exc:
            raise RuntimeError(
                f"Cognitive map extraction timed out after {payload.timeout_seconds:g} seconds"
            ) from exc
        if extraction is None:
            raise RuntimeError("Cognitive map extractor returned no extraction result")

        _extraction_path(map_id).write_text(
            extraction.model_dump_json(indent=2),
            encoding="utf-8",
        )
        evaluation = _generate_evaluation(extraction)
        _write_json(_evaluation_path(map_id), evaluation)

        meta["status"] = "completed"
        meta["parser_provider"] = ",".join(sorted(parser_providers_used))
        meta["requested_extractor_provider"] = requested_extractor
        meta["extractor_provider"] = requested_extractor
        meta["llm_provider"] = payload.llm_provider
        meta["build_error"] = None
        meta["updated_at"] = datetime.utcnow().isoformat()
        _write_json(_meta_path(map_id), meta)
        _record_build_run(
            map_id,
            {
                "run_id": run_id,
                "status": "completed",
                "parser_provider": meta["parser_provider"],
                "requested_extractor_provider": requested_extractor,
                "extractor_provider": requested_extractor,
                "llm_provider": payload.llm_provider,
                "file_count": len(source_files),
                "chunk_count": len(chunks),
                "timeout_seconds": payload.timeout_seconds,
                "entity_count": evaluation["entity_count"],
                "relation_count": evaluation["relation_count"],
                "evidence_count": evaluation["evidence_count"],
                "started_at": started_at,
                "finished_at": meta["updated_at"],
                "duration_ms": int((time.perf_counter() - start_time) * 1000),
                "error": None,
            },
        )
        return _enrich_map(meta)
    except Exception as exc:
        requested_extractor = (payload.extractor_provider or "local").strip().lower()
        finished_at = datetime.utcnow().isoformat()
        meta["status"] = "failed"
        meta["requested_extractor_provider"] = requested_extractor
        meta["extractor_provider"] = requested_extractor
        meta["llm_provider"] = payload.llm_provider
        meta["build_error"] = str(exc)
        meta["updated_at"] = finished_at
        _write_json(_meta_path(map_id), meta)
        _record_build_run(
            map_id,
            {
                "run_id": run_id,
                "status": "failed",
                "parser_provider": payload.parser_provider,
                "requested_extractor_provider": requested_extractor,
                "extractor_provider": requested_extractor,
                "llm_provider": payload.llm_provider,
                "file_count": len(source_files),
                "chunk_count": len(chunks),
                "timeout_seconds": payload.timeout_seconds,
                "entity_count": 0,
                "relation_count": 0,
                "evidence_count": 0,
                "started_at": started_at,
                "finished_at": finished_at,
                "duration_ms": int((time.perf_counter() - start_time) * 1000),
                "error": str(exc),
            },
        )
        raise HTTPException(status_code=500, detail=f"Failed to build cognitive map: {exc}") from exc


@router.get("/{map_id}/build-runs")
async def list_cognitive_map_build_runs(map_id: str) -> dict[str, Any]:
    _require_map(map_id)
    return {"runs": _load_runs(map_id)}


@router.get("/{map_id}/evaluation")
async def get_cognitive_map_evaluation(map_id: str) -> dict[str, Any]:
    _require_map(map_id)
    evaluation = _load_evaluation(map_id)
    if evaluation is None:
        extraction = _load_extraction(map_id)
        if extraction is None:
            return {"evaluation": None}
        evaluation = _generate_evaluation(extraction)
        _write_json(_evaluation_path(map_id), evaluation)
    return {"evaluation": evaluation}


@router.get("/{map_id}/entities")
async def list_cognitive_map_entities(map_id: str) -> dict[str, Any]:
    _require_map(map_id)
    extraction = _load_extraction(map_id)
    entities = extraction.candidate_entities if extraction else []
    return {"entities": [entity.model_dump(mode="json") for entity in entities]}


@router.post("/{map_id}/entities")
async def create_cognitive_map_entity(
    map_id: str,
    payload: CognitiveMapEntityCreateRequest,
) -> dict[str, Any]:
    _require_map(map_id)
    extraction = _load_extraction(map_id)
    if extraction is None:
        extraction = ExtractionResult(
            map_id=map_id,
            diagnostics=ExtractionDiagnostic(
                provider_name="manual",
                provider_version="0.1",
                status="success",
                messages=["Created manually from cognitive map management"],
            ),
        )
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="entity name is required")
    entity = CandidateEntity(
        entity_id=f"entity_{uuid.uuid4().hex[:12]}",
        map_id=map_id,
        entity_type=payload.entity_type,
        name=name,
        canonical_name=payload.canonical_name,
        aliases=payload.aliases,
        description=payload.description,
        attributes=payload.attributes,
        source_evidence_ids=payload.source_evidence_ids,
        confidence=payload.confidence,
        review_status=payload.review_status,
        created_by="user",
    )
    extraction.candidate_entities.append(entity)
    _save_extraction(map_id, extraction)
    return entity.model_dump(mode="json")


@router.patch("/{map_id}/entities/{entity_id}")
async def update_cognitive_map_entity(
    map_id: str,
    entity_id: str,
    payload: CognitiveMapEntityUpdateRequest,
) -> dict[str, Any]:
    _require_map(map_id)
    extraction = _require_extraction(map_id)
    entity = next((item for item in extraction.candidate_entities if item.entity_id == entity_id), None)
    if entity is None:
        raise HTTPException(status_code=404, detail=f"Cognitive map entity not found: {entity_id}")

    updates = payload.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(entity, field, value)
    _save_extraction(map_id, extraction)
    return entity.model_dump(mode="json")


@router.post("/{map_id}/entities/{entity_id}/merge")
async def merge_cognitive_map_entity(
    map_id: str,
    entity_id: str,
    payload: CognitiveMapEntityMergeRequest,
) -> dict[str, Any]:
    _require_map(map_id)
    if entity_id == payload.target_entity_id:
        raise HTTPException(status_code=400, detail="source and target entity must be different")
    extraction = _require_extraction(map_id)
    source = next((item for item in extraction.candidate_entities if item.entity_id == entity_id), None)
    target = next((item for item in extraction.candidate_entities if item.entity_id == payload.target_entity_id), None)
    if source is None:
        raise HTTPException(status_code=404, detail=f"Cognitive map entity not found: {entity_id}")
    if target is None:
        raise HTTPException(status_code=404, detail=f"Cognitive map entity not found: {payload.target_entity_id}")

    target.aliases = sorted(set([*target.aliases, source.name, *(source.aliases or [])]))
    target.source_evidence_ids = sorted(set([*target.source_evidence_ids, *source.source_evidence_ids]))
    target.attributes = {**source.attributes, **target.attributes}
    if not target.description and source.description:
        target.description = source.description
    target.review_status = "merged"

    for relation in extraction.candidate_relations:
        if relation.source_entity_id == entity_id:
            relation.source_entity_id = payload.target_entity_id
        if relation.target_entity_id == entity_id:
            relation.target_entity_id = payload.target_entity_id

    extraction.candidate_entities = [
        item for item in extraction.candidate_entities if item.entity_id != entity_id
    ]
    _save_extraction(map_id, extraction)
    return {
        "merged": True,
        "source_entity_id": entity_id,
        "target_entity": target.model_dump(mode="json"),
    }


@router.delete("/{map_id}/entities/{entity_id}")
async def delete_cognitive_map_entity(map_id: str, entity_id: str) -> dict[str, Any]:
    _require_map(map_id)
    extraction = _require_extraction(map_id)
    original_entity_count = len(extraction.candidate_entities)
    original_relation_count = len(extraction.candidate_relations)
    extraction.candidate_entities = [
        entity for entity in extraction.candidate_entities if entity.entity_id != entity_id
    ]
    if len(extraction.candidate_entities) == original_entity_count:
        raise HTTPException(status_code=404, detail=f"Cognitive map entity not found: {entity_id}")

    extraction.candidate_relations = [
        relation
        for relation in extraction.candidate_relations
        if relation.source_entity_id != entity_id and relation.target_entity_id != entity_id
    ]
    removed_relation_count = original_relation_count - len(extraction.candidate_relations)
    _save_extraction(map_id, extraction)
    return {
        "deleted": True,
        "entity_id": entity_id,
        "removed_relation_count": removed_relation_count,
    }


@router.get("/{map_id}/relations")
async def list_cognitive_map_relations(map_id: str) -> dict[str, Any]:
    _require_map(map_id)
    extraction = _load_extraction(map_id)
    if extraction is None:
        return {"relations": []}

    entity_names = {entity.entity_id: entity.name for entity in extraction.candidate_entities}
    relations = []
    for relation in extraction.candidate_relations:
        item = relation.model_dump(mode="json")
        item["source_name"] = entity_names.get(relation.source_entity_id, relation.source_entity_id)
        item["target_name"] = entity_names.get(relation.target_entity_id, relation.target_entity_id)
        relations.append(item)
    return {"relations": relations}


@router.post("/{map_id}/relations")
async def create_cognitive_map_relation(
    map_id: str,
    payload: CognitiveMapRelationCreateRequest,
) -> dict[str, Any]:
    _require_map(map_id)
    extraction = _require_extraction(map_id)
    entity_ids = {entity.entity_id for entity in extraction.candidate_entities}
    if payload.source_entity_id not in entity_ids:
        raise HTTPException(status_code=404, detail=f"source entity not found: {payload.source_entity_id}")
    if payload.target_entity_id not in entity_ids:
        raise HTTPException(status_code=404, detail=f"target entity not found: {payload.target_entity_id}")
    relation = CandidateRelation(
        relation_id=f"relation_{uuid.uuid4().hex[:12]}",
        map_id=map_id,
        source_entity_id=payload.source_entity_id,
        target_entity_id=payload.target_entity_id,
        relation_type=payload.relation_type,
        description=payload.description,
        attributes=payload.attributes,
        source_evidence_ids=payload.source_evidence_ids,
        confidence=payload.confidence,
        review_status=payload.review_status,
        created_by="user",
    )
    extraction.candidate_relations.append(relation)
    _save_extraction(map_id, extraction)
    return _relation_to_response(relation, _entity_names(extraction))


@router.patch("/{map_id}/relations/{relation_id}")
async def update_cognitive_map_relation(
    map_id: str,
    relation_id: str,
    payload: CognitiveMapRelationUpdateRequest,
) -> dict[str, Any]:
    _require_map(map_id)
    extraction = _require_extraction(map_id)
    relation = next(
        (item for item in extraction.candidate_relations if item.relation_id == relation_id),
        None,
    )
    if relation is None:
        raise HTTPException(status_code=404, detail=f"Cognitive map relation not found: {relation_id}")

    updates = payload.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(relation, field, value)
    _save_extraction(map_id, extraction)

    return _relation_to_response(relation, _entity_names(extraction))


@router.delete("/{map_id}/relations/{relation_id}")
async def delete_cognitive_map_relation(map_id: str, relation_id: str) -> dict[str, Any]:
    _require_map(map_id)
    extraction = _require_extraction(map_id)
    original_relation_count = len(extraction.candidate_relations)
    extraction.candidate_relations = [
        relation for relation in extraction.candidate_relations if relation.relation_id != relation_id
    ]
    if len(extraction.candidate_relations) == original_relation_count:
        raise HTTPException(status_code=404, detail=f"Cognitive map relation not found: {relation_id}")

    _save_extraction(map_id, extraction)
    return {"deleted": True, "relation_id": relation_id}


@router.get("/{map_id}/evidence")
async def list_cognitive_map_evidence(map_id: str) -> dict[str, Any]:
    _require_map(map_id)
    extraction = _load_extraction(map_id)
    evidence = extraction.evidence if extraction else []
    return {"evidence": [item.model_dump(mode="json") for item in evidence]}
