from pathlib import Path
import asyncio
from datetime import datetime, timedelta

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.agent.cognition.models import (
    CandidateEntity,
    CognitiveSchema,
    Evidence,
    ExtractionDiagnostic,
    ExtractionResult,
)


def test_cognitive_map_api_runs_file_to_entities_flow(tmp_path: Path, monkeypatch):
    from app.api import cognitive_map_routes

    monkeypatch.setattr(cognitive_map_routes, "COGNITIVE_MAPS_ROOT", tmp_path)

    app = FastAPI()
    app.include_router(cognitive_map_routes.router)
    client = TestClient(app)

    create_response = client.post(
        "/api/cognitive-maps",
        json={"name": "臭氧过程认知地图", "description": "用于污染过程分析"},
    )
    assert create_response.status_code == 200
    created = create_response.json()
    assert created["name"] == "臭氧过程认知地图"
    map_id = created["id"]

    upload_response = client.post(
        f"/api/cognitive-maps/{map_id}/files",
        files={"file": ("notes.md", "深圳市监测站监测臭氧。臭氧受光化学反应影响。", "text/markdown")},
    )
    assert upload_response.status_code == 200
    uploaded = upload_response.json()
    assert uploaded["filename"] == "notes.md"

    build_response = client.post(
        f"/api/cognitive-maps/{map_id}/build",
        json={"extractor_provider": "local", "parser_provider": "text"},
    )
    assert build_response.status_code == 200
    built = build_response.json()
    assert built["status"] == "completed"
    assert built["entity_count"] >= 2
    assert built["relation_count"] >= 1
    assert built["evidence_count"] >= 1

    entities_response = client.get(f"/api/cognitive-maps/{map_id}/entities")
    relations_response = client.get(f"/api/cognitive-maps/{map_id}/relations")
    evidence_response = client.get(f"/api/cognitive-maps/{map_id}/evidence")

    assert entities_response.status_code == 200
    assert relations_response.status_code == 200
    assert evidence_response.status_code == 200
    assert any(entity["name"] == "臭氧" for entity in entities_response.json()["entities"])
    assert relations_response.json()["relations"]
    assert evidence_response.json()["evidence"]


def test_cognitive_map_api_returns_404_for_missing_map(tmp_path: Path, monkeypatch):
    from app.api import cognitive_map_routes

    monkeypatch.setattr(cognitive_map_routes, "COGNITIVE_MAPS_ROOT", tmp_path)

    app = FastAPI()
    app.include_router(cognitive_map_routes.router)
    client = TestClient(app)

    response = client.get("/api/cognitive-maps/missing/entities")

    assert response.status_code == 404


def test_cognitive_map_api_builds_docx_with_auto_parser(tmp_path: Path, monkeypatch):
    from docx import Document

    from app.api import cognitive_map_routes

    monkeypatch.setattr(cognitive_map_routes, "COGNITIVE_MAPS_ROOT", tmp_path)

    docx_path = tmp_path / "ozone.docx"
    document = Document()
    document.add_paragraph("深圳市监测站监测臭氧。臭氧受光化学反应影响，机动车排放支持本地生成假设。")
    document.save(docx_path)

    app = FastAPI()
    app.include_router(cognitive_map_routes.router)
    client = TestClient(app)

    create_response = client.post("/api/cognitive-maps", json={"name": "DOCX地图"})
    map_id = create_response.json()["id"]

    with docx_path.open("rb") as docx_file:
        upload_response = client.post(
            f"/api/cognitive-maps/{map_id}/files",
            files={
                "file": (
                    "ozone.docx",
                    docx_file,
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                )
            },
        )

    assert upload_response.status_code == 200

    build_response = client.post(
        f"/api/cognitive-maps/{map_id}/build",
        json={"extractor_provider": "local", "parser_provider": "auto", "timeout_seconds": 180},
    )

    assert build_response.status_code == 200
    built = build_response.json()
    assert built["status"] == "completed"
    assert built["entity_count"] >= 2

    entities_response = client.get(f"/api/cognitive-maps/{map_id}/entities")
    assert any(entity["name"] == "臭氧" for entity in entities_response.json()["entities"])


def test_cognitive_map_api_returns_error_when_llamaindex_build_fails(tmp_path: Path, monkeypatch):
    from app.api import cognitive_map_routes

    monkeypatch.setattr(cognitive_map_routes, "COGNITIVE_MAPS_ROOT", tmp_path)

    class FailingExtractor:
        async def extract(self, chunks, schema):
            raise RuntimeError("llamaindex unavailable")

    class FakeLocalExtractor:
        async def extract(self, chunks, schema: CognitiveSchema):
            chunk = chunks[0]
            return ExtractionResult(
                map_id=chunk.map_id,
                candidate_entities=[
                    CandidateEntity(
                        entity_id="ent_test",
                        map_id=chunk.map_id,
                        entity_type="Pollutant",
                        name="臭氧",
                        canonical_name="臭氧",
                        source_evidence_ids=["ev_test"],
                    )
                ],
                evidence=[
                    Evidence(
                        evidence_id="ev_test",
                        map_id=chunk.map_id,
                        source_file_id=chunk.source_file_id,
                        chunk_id=chunk.chunk_id,
                        location=chunk.location,
                        text_span=chunk.text,
                        normalized_summary=chunk.text,
                    )
                ],
                diagnostics=ExtractionDiagnostic(provider_name="fake_local"),
            )

    def fake_create_extractor_provider(name=None, llm=None):
        if name == "llamaindex":
            return FailingExtractor()
        return FakeLocalExtractor()

    monkeypatch.setattr(cognitive_map_routes, "create_llamaindex_llm", lambda provider: object())
    monkeypatch.setattr(cognitive_map_routes, "create_extractor_provider", fake_create_extractor_provider)

    app = FastAPI()
    app.include_router(cognitive_map_routes.router)
    client = TestClient(app)

    create_response = client.post("/api/cognitive-maps", json={"name": "LlamaIndex降级测试"})
    map_id = create_response.json()["id"]
    client.post(
        f"/api/cognitive-maps/{map_id}/files",
        files={"file": ("notes.md", "臭氧污染过程分析", "text/markdown")},
    )

    build_response = client.post(
        f"/api/cognitive-maps/{map_id}/build",
        json={
            "extractor_provider": "llamaindex",
            "llm_provider": "project",
            "parser_provider": "auto",
        },
    )

    assert build_response.status_code == 500
    assert "llamaindex unavailable" in build_response.json()["detail"]

    maps_response = client.get("/api/cognitive-maps")
    failed_map = next(item for item in maps_response.json()["maps"] if item["id"] == map_id)
    assert failed_map["status"] == "failed"
    assert failed_map["requested_extractor_provider"] == "llamaindex"
    assert failed_map["extractor_provider"] == "llamaindex"
    assert "llamaindex unavailable" in failed_map["build_error"]


def test_cognitive_map_api_records_build_runs_and_evaluation(tmp_path: Path, monkeypatch):
    from app.api import cognitive_map_routes

    monkeypatch.setattr(cognitive_map_routes, "COGNITIVE_MAPS_ROOT", tmp_path)

    app = FastAPI()
    app.include_router(cognitive_map_routes.router)
    client = TestClient(app)

    create_response = client.post("/api/cognitive-maps", json={"name": "评估测试"})
    map_id = create_response.json()["id"]
    client.post(
        f"/api/cognitive-maps/{map_id}/files",
        files={"file": ("notes.md", "深圳市监测站监测臭氧。臭氧受光化学反应影响。", "text/markdown")},
    )

    build_response = client.post(
        f"/api/cognitive-maps/{map_id}/build",
        json={"extractor_provider": "local", "parser_provider": "auto", "timeout_seconds": 180},
    )

    assert build_response.status_code == 200
    built = build_response.json()
    assert built["latest_run"]["status"] == "completed"
    assert built["latest_run"]["extractor_provider"] == "local"
    assert built["latest_run"]["timeout_seconds"] == 180
    assert built["latest_run"]["duration_ms"] >= 0
    assert built["evaluation"]["entity_count"] >= 2
    assert built["evaluation"]["relation_count"] >= 1
    assert built["evaluation"]["evidence_count"] >= 1
    assert built["evaluation"]["entity_evidence_ratio"] == 1.0

    runs_response = client.get(f"/api/cognitive-maps/{map_id}/build-runs")
    evaluation_response = client.get(f"/api/cognitive-maps/{map_id}/evaluation")

    assert runs_response.status_code == 200
    assert runs_response.json()["runs"][0]["status"] == "completed"
    assert runs_response.json()["runs"][0]["timeout_seconds"] == 180
    assert evaluation_response.status_code == 200
    assert evaluation_response.json()["evaluation"]["entity_count"] == built["evaluation"]["entity_count"]


def test_cognitive_map_api_times_out_llamaindex_build_and_records_failed_run(
    tmp_path: Path,
    monkeypatch,
):
    from app.api import cognitive_map_routes

    monkeypatch.setattr(cognitive_map_routes, "COGNITIVE_MAPS_ROOT", tmp_path)

    class HangingExtractor:
        async def extract(self, chunks, schema):
            await asyncio.sleep(1)

    def fake_create_extractor_provider(name=None, llm=None):
        return HangingExtractor()

    monkeypatch.setattr(cognitive_map_routes, "create_llamaindex_llm", lambda provider: object())
    monkeypatch.setattr(cognitive_map_routes, "create_extractor_provider", fake_create_extractor_provider)

    app = FastAPI()
    app.include_router(cognitive_map_routes.router)
    client = TestClient(app)

    create_response = client.post("/api/cognitive-maps", json={"name": "LlamaIndex超时测试"})
    map_id = create_response.json()["id"]
    client.post(
        f"/api/cognitive-maps/{map_id}/files",
        files={"file": ("notes.md", "臭氧污染过程分析", "text/markdown")},
    )

    build_response = client.post(
        f"/api/cognitive-maps/{map_id}/build",
        json={
            "extractor_provider": "llamaindex",
            "llm_provider": "project",
            "parser_provider": "auto",
            "timeout_seconds": 0.01,
        },
    )

    assert build_response.status_code == 500
    assert "timed out" in build_response.json()["detail"]

    runs_response = client.get(f"/api/cognitive-maps/{map_id}/build-runs")
    failed_run = runs_response.json()["runs"][0]
    assert failed_run["status"] == "failed"
    assert failed_run["extractor_provider"] == "llamaindex"
    assert failed_run["chunk_count"] == 1
    assert failed_run["timeout_seconds"] == 0.01
    assert "timed out" in failed_run["error"]


def test_cognitive_map_api_marks_stale_building_maps_failed_on_list(tmp_path: Path, monkeypatch):
    from app.api import cognitive_map_routes

    monkeypatch.setattr(cognitive_map_routes, "COGNITIVE_MAPS_ROOT", tmp_path)
    stale_time = (datetime.utcnow() - timedelta(minutes=20)).isoformat()
    map_dir = tmp_path / "cm_stale"
    map_dir.mkdir(parents=True)
    cognitive_map_routes._write_json(
        map_dir / "map.json",
        {
            "id": "cm_stale",
            "name": "卡住的地图",
            "description": "",
            "status": "building",
            "created_at": stale_time,
            "updated_at": stale_time,
        },
    )
    cognitive_map_routes._write_json(map_dir / "files.json", [])

    app = FastAPI()
    app.include_router(cognitive_map_routes.router)
    client = TestClient(app)

    response = client.get("/api/cognitive-maps")

    assert response.status_code == 200
    stale_map = response.json()["maps"][0]
    assert stale_map["status"] == "failed"
    assert "stale building state" in stale_map["build_error"]
    assert stale_map["latest_run"]["status"] == "failed"
    assert "stale building state" in stale_map["latest_run"]["error"]
