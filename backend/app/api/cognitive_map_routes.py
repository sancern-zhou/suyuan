from __future__ import annotations

import asyncio
import shutil
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel

from app.agent.cognition.llm_factory import create_llamaindex_llm
from app.agent.cognition.models import CognitiveSchema, ExtractionResult, SourceFile
from app.agent.cognition.provider_factory import create_extractor_provider, create_parser_provider
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


def _load_runs(map_id: str) -> list[dict[str, Any]]:
    return _load_json(_runs_path(map_id), [])


def _latest_run(map_id: str) -> dict[str, Any] | None:
    runs = _load_runs(map_id)
    return runs[0] if runs else None


def _load_evaluation(map_id: str) -> dict[str, Any] | None:
    return _load_json(_evaluation_path(map_id), None)


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
    }


def _safe_filename(filename: str) -> str:
    name = Path(filename or "upload.txt").name
    return name.replace("/", "_").replace("\\", "_")


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


@router.get("/{map_id}/evidence")
async def list_cognitive_map_evidence(map_id: str) -> dict[str, Any]:
    _require_map(map_id)
    extraction = _load_extraction(map_id)
    evidence = extraction.evidence if extraction else []
    return {"evidence": [item.model_dump(mode="json") for item in evidence]}
