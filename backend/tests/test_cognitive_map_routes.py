from pathlib import Path
import asyncio
from datetime import datetime, timedelta

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.agent.cognition.models import (
    CandidateEntity,
    CandidateRelation,
    CognitiveSchema,
    Evidence,
    ExtractionDiagnostic,
    ExtractionResult,
)


def _write_minimal_text_pdf(path: Path, text: str) -> None:
    content = f"BT /F1 24 Tf 72 720 Td ({text}) Tj ET".encode("ascii")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(content)).encode("ascii") + b" >>\nstream\n" + content + b"\nendstream",
    ]
    pdf = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for index, obj in enumerate(objects, start=1):
        offsets.append(len(pdf))
        pdf.extend(f"{index} 0 obj\n".encode("ascii"))
        pdf.extend(obj)
        pdf.extend(b"\nendobj\n")
    xref_offset = len(pdf)
    pdf.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    pdf.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        pdf.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    pdf.extend(
        f"trailer << /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n".encode("ascii")
    )
    path.write_bytes(bytes(pdf))


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


def test_cognitive_map_build_request_defaults_to_long_llamaindex_timeout():
    from app.api.cognitive_map_routes import CognitiveMapBuildRequest

    assert CognitiveMapBuildRequest().timeout_seconds == 900.0


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


def test_cognitive_map_api_builds_pdf_with_auto_parser(tmp_path: Path, monkeypatch):
    from app.api import cognitive_map_routes

    monkeypatch.setattr(cognitive_map_routes, "COGNITIVE_MAPS_ROOT", tmp_path)

    pdf_path = tmp_path / "ozone.pdf"
    _write_minimal_text_pdf(pdf_path, "O3 monitoring station")

    app = FastAPI()
    app.include_router(cognitive_map_routes.router)
    client = TestClient(app)

    create_response = client.post("/api/cognitive-maps", json={"name": "PDF地图"})
    map_id = create_response.json()["id"]

    with pdf_path.open("rb") as pdf_file:
        upload_response = client.post(
            f"/api/cognitive-maps/{map_id}/files",
            files={"file": ("ozone.pdf", pdf_file, "application/pdf")},
        )

    assert upload_response.status_code == 200

    build_response = client.post(
        f"/api/cognitive-maps/{map_id}/build",
        json={"extractor_provider": "local", "parser_provider": "auto", "timeout_seconds": 180},
    )

    assert build_response.status_code == 200
    built = build_response.json()
    assert built["status"] == "completed"
    assert built["parser_provider"] == "pdf"
    assert built["entity_count"] >= 1

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


def test_cognitive_map_api_records_and_passes_build_requirement(tmp_path: Path, monkeypatch):
    from app.api import cognitive_map_routes

    monkeypatch.setattr(cognitive_map_routes, "COGNITIVE_MAPS_ROOT", tmp_path)
    captured = {}

    class CapturingExtractor:
        async def extract(self, chunks, schema: CognitiveSchema):
            captured["schema_build_requirement"] = schema.build_requirement
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
                diagnostics=ExtractionDiagnostic(provider_name="capturing"),
            )

    monkeypatch.setattr(cognitive_map_routes, "create_extractor_provider", lambda name=None, llm=None: CapturingExtractor())

    app = FastAPI()
    app.include_router(cognitive_map_routes.router)
    client = TestClient(app)

    create_response = client.post("/api/cognitive-maps", json={"name": "需求测试"})
    map_id = create_response.json()["id"]
    client.post(
        f"/api/cognitive-maps/{map_id}/files",
        files={"file": ("notes.md", "臭氧污染过程分析", "text/markdown")},
    )

    requirement = "用于运维故障诊断，关注站点、设备、告警、工单、污染物数据和故障原因之间的关系。"
    build_response = client.post(
        f"/api/cognitive-maps/{map_id}/build",
        json={
            "extractor_provider": "local",
            "parser_provider": "auto",
            "build_requirement": requirement,
        },
    )

    assert build_response.status_code == 200
    built = build_response.json()
    assert built["build_requirement"] == requirement
    assert built["latest_run"]["build_requirement"] == requirement
    assert captured["schema_build_requirement"] == requirement

    maps_response = client.get("/api/cognitive-maps")
    listed = next(item for item in maps_response.json()["maps"] if item["id"] == map_id)
    assert listed["build_requirement"] == requirement


def test_cognitive_map_api_persists_schema_and_build_uses_it(tmp_path: Path, monkeypatch):
    from app.api import cognitive_map_routes

    monkeypatch.setattr(cognitive_map_routes, "COGNITIVE_MAPS_ROOT", tmp_path)

    captured = {}

    class CapturingExtractor:
        async def extract(self, chunks, schema: CognitiveSchema):
            captured["schema"] = schema
            chunk = chunks[0]
            return ExtractionResult(
                map_id=chunk.map_id,
                candidate_entities=[
                    CandidateEntity(
                        entity_id="ent_custom",
                        map_id=chunk.map_id,
                        entity_type="CustomEntity",
                        name="自定义实体",
                        source_evidence_ids=["ev_custom"],
                    )
                ],
                evidence=[
                    Evidence(
                        evidence_id="ev_custom",
                        map_id=chunk.map_id,
                        source_file_id=chunk.source_file_id,
                        chunk_id=chunk.chunk_id,
                        location=chunk.location,
                        text_span=chunk.text,
                        normalized_summary=chunk.text,
                    )
                ],
                diagnostics=ExtractionDiagnostic(provider_name="capturing"),
            )

    monkeypatch.setattr(cognitive_map_routes, "create_extractor_provider", lambda name=None, llm=None: CapturingExtractor())

    app = FastAPI()
    app.include_router(cognitive_map_routes.router)
    client = TestClient(app)

    map_id = client.post("/api/cognitive-maps", json={"name": "Schema测试"}).json()["id"]
    schema_payload = {
        "allowed_entity_types": ["CustomEntity"],
        "allowed_relation_types": ["custom_rel"],
        "allowed_relation_triplets": [["CustomEntity", "custom_rel", "CustomEntity"]],
        "required_evidence": True,
        "domain_aliases": {"自定义实体": ["别名"]},
        "normalization_rules": {"trim": True},
    }

    put_response = client.put(f"/api/cognitive-maps/{map_id}/schema", json=schema_payload)
    get_response = client.get(f"/api/cognitive-maps/{map_id}/schema")
    client.post(
        f"/api/cognitive-maps/{map_id}/files",
        files={"file": ("notes.md", "自定义实体。", "text/markdown")},
    )
    build_response = client.post(f"/api/cognitive-maps/{map_id}/build", json={"extractor_provider": "local"})

    assert put_response.status_code == 200
    assert get_response.json()["schema"]["allowed_entity_types"] == ["CustomEntity"]
    assert build_response.status_code == 200
    assert captured["schema"].allowed_entity_types == ["CustomEntity"]
    assert captured["schema"].allowed_relation_triplets == [("CustomEntity", "custom_rel", "CustomEntity")]


def test_cognitive_map_api_queries_property_graph_subgraph(tmp_path: Path, monkeypatch):
    from llama_index.core.graph_stores.simple_labelled import SimplePropertyGraphStore
    from llama_index.core.graph_stores.types import EntityNode, Relation

    from app.api import cognitive_map_routes

    monkeypatch.setattr(cognitive_map_routes, "COGNITIVE_MAPS_ROOT", tmp_path)

    map_id = "cm_graph"
    map_dir = tmp_path / map_id
    map_dir.mkdir(parents=True)
    cognitive_map_routes._write_json(
        map_dir / "map.json",
        {
            "id": map_id,
            "name": "图查询测试",
            "description": "",
            "status": "completed",
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
        },
    )
    cognitive_map_routes._write_json(map_dir / "files.json", [])

    extraction = ExtractionResult(
        map_id=map_id,
        candidate_entities=[
            CandidateEntity(entity_id="ent_photo", map_id=map_id, entity_type="ProcessMechanism", name="光化学反应", review_status="confirmed"),
            CandidateEntity(entity_id="ent_o3", map_id=map_id, entity_type="Pollutant", name="臭氧", review_status="confirmed"),
            CandidateEntity(entity_id="ent_finding", map_id=map_id, entity_type="Finding", name="臭氧升高", review_status="confirmed"),
        ],
        candidate_relations=[
            CandidateRelation(relation_id="rel_1", map_id=map_id, source_entity_id="ent_photo", target_entity_id="ent_o3", relation_type="affects", review_status="confirmed"),
            CandidateRelation(relation_id="rel_2", map_id=map_id, source_entity_id="ent_o3", target_entity_id="ent_finding", relation_type="indicates", review_status="confirmed"),
        ],
        diagnostics=ExtractionDiagnostic(provider_name="test"),
    )
    cognitive_map_routes._save_extraction(map_id, extraction)

    store = SimplePropertyGraphStore()
    store.upsert_nodes(
        [
            EntityNode(name="光化学反应", label="ProcessMechanism"),
            EntityNode(name="臭氧", label="Pollutant"),
            EntityNode(name="臭氧升高", label="Finding"),
        ]
    )
    store.upsert_relations(
        [
            Relation(label="AFFECTS", source_id="光化学反应", target_id="臭氧"),
            Relation(label="INDICATES", source_id="臭氧", target_id="臭氧升高"),
        ]
    )
    store.persist(str(map_dir / "property_graph_store.json"))

    app = FastAPI()
    app.include_router(cognitive_map_routes.router)
    client = TestClient(app)

    response = client.post(
        f"/api/cognitive-maps/{map_id}/query-graph",
        json={"task": "分析臭氧", "agent_mode": "expert", "entity_hints": ["光化学反应"], "depth": 2, "limit": 10},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["source"] == "property_graph_store"
    assert [entity["name"] for entity in payload["view"]["entities"]] == ["光化学反应", "臭氧", "臭氧升高"]
    assert [relation["relation_type"] for relation in payload["view"]["relations"]] == ["affects", "indicates"]
    assert "光化学反应 --affects--> 臭氧" in payload["prompt_context"]


def test_cognitive_map_prompt_context_uses_property_graph_depth(tmp_path: Path, monkeypatch):
    from llama_index.core.graph_stores.simple_labelled import SimplePropertyGraphStore
    from llama_index.core.graph_stores.types import EntityNode, Relation

    from app.api import cognitive_map_routes

    monkeypatch.setattr(cognitive_map_routes, "COGNITIVE_MAPS_ROOT", tmp_path)

    map_id = "cm_prompt_graph"
    map_dir = tmp_path / map_id
    map_dir.mkdir(parents=True)
    cognitive_map_routes._write_json(
        map_dir / "map.json",
        {
            "id": map_id,
            "name": "注入图查询测试",
            "description": "",
            "status": "completed",
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
        },
    )
    cognitive_map_routes._write_json(map_dir / "files.json", [])
    cognitive_map_routes._save_extraction(
        map_id,
        ExtractionResult(
            map_id=map_id,
            candidate_entities=[
                CandidateEntity(entity_id="ent_photo", map_id=map_id, entity_type="ProcessMechanism", name="光化学反应", review_status="confirmed"),
                CandidateEntity(entity_id="ent_o3", map_id=map_id, entity_type="Pollutant", name="臭氧", review_status="confirmed"),
                CandidateEntity(entity_id="ent_finding", map_id=map_id, entity_type="Finding", name="臭氧升高", review_status="confirmed"),
            ],
            candidate_relations=[
                CandidateRelation(relation_id="rel_1", map_id=map_id, source_entity_id="ent_photo", target_entity_id="ent_o3", relation_type="affects", review_status="confirmed"),
                CandidateRelation(relation_id="rel_2", map_id=map_id, source_entity_id="ent_o3", target_entity_id="ent_finding", relation_type="indicates", review_status="confirmed"),
            ],
            diagnostics=ExtractionDiagnostic(provider_name="test"),
        ),
    )
    store = SimplePropertyGraphStore()
    store.upsert_nodes(
        [
            EntityNode(name="光化学反应", label="ProcessMechanism"),
            EntityNode(name="臭氧", label="Pollutant"),
            EntityNode(name="臭氧升高", label="Finding"),
        ]
    )
    store.upsert_relations(
        [
            Relation(label="affects", source_id="光化学反应", target_id="臭氧"),
            Relation(label="indicates", source_id="臭氧", target_id="臭氧升高"),
        ]
    )
    store.persist(str(map_dir / "property_graph_store.json"))

    context = cognitive_map_routes.build_cognitive_map_prompt_context(
        task="分析光化学反应",
        agent_mode="expert",
        map_ids=[map_id],
        entity_hints=["光化学反应"],
    )

    assert "臭氧 --indicates--> 臭氧升高" in context
    assert "ent_finding" not in context


def test_cognitive_map_evaluation_reports_graph_quality_metrics():
    from app.api import cognitive_map_routes

    extraction = ExtractionResult(
        map_id="map_quality",
        candidate_entities=[
            CandidateEntity(entity_id="ent_confirmed", map_id="map_quality", entity_type="Pollutant", name="臭氧", review_status="confirmed"),
            CandidateEntity(entity_id="ent_candidate", map_id="map_quality", entity_type="Hypothesis", name="待确认假设", review_status="candidate"),
            CandidateEntity(entity_id="ent_isolated", map_id="map_quality", entity_type="Finding", name="孤立发现", review_status="confirmed"),
        ],
        candidate_relations=[
            CandidateRelation(relation_id="rel_1", map_id="map_quality", source_entity_id="ent_confirmed", target_entity_id="ent_candidate", relation_type="supports", review_status="candidate"),
        ],
        diagnostics=ExtractionDiagnostic(provider_name="test"),
    )

    evaluation = cognitive_map_routes._generate_evaluation(extraction, property_graph_persisted=True)

    assert evaluation["property_graph_persisted"] is True
    assert evaluation["candidate_entity_count"] == 1
    assert evaluation["candidate_relation_count"] == 1
    assert evaluation["confirmed_entity_count"] == 2
    assert evaluation["isolated_entity_count"] == 1
    assert evaluation["usable_for_agent"] is False


def test_cognitive_map_api_publishes_candidates_for_agent_use(tmp_path: Path, monkeypatch):
    from llama_index.core.graph_stores.simple_labelled import SimplePropertyGraphStore
    from llama_index.core.graph_stores.types import EntityNode, Relation

    from app.api import cognitive_map_routes

    monkeypatch.setattr(cognitive_map_routes, "COGNITIVE_MAPS_ROOT", tmp_path)
    map_id = "map_publish"
    map_dir = tmp_path / map_id
    map_dir.mkdir(parents=True)
    (map_dir / "map.json").write_text(
        '{"id":"map_publish","name":"发布测试","status":"completed"}',
        encoding="utf-8",
    )
    cognitive_map_routes._save_extraction(
        map_id,
        ExtractionResult(
            map_id=map_id,
            candidate_entities=[
                CandidateEntity(entity_id="ent_alarm", map_id=map_id, entity_type="Alarm", name="质控报警", review_status="candidate"),
                CandidateEntity(entity_id="ent_fault", map_id=map_id, entity_type="FaultSymptom", name="校准失败", review_status="candidate"),
                CandidateEntity(entity_id="ent_rejected", map_id=map_id, entity_type="RootCause", name="错误根因", review_status="rejected"),
            ],
            candidate_relations=[
                CandidateRelation(relation_id="rel_1", map_id=map_id, source_entity_id="ent_alarm", target_entity_id="ent_fault", relation_type="alarm_indicates", review_status="candidate"),
                CandidateRelation(relation_id="rel_rejected", map_id=map_id, source_entity_id="ent_alarm", target_entity_id="ent_rejected", relation_type="alarm_indicates", review_status="rejected"),
            ],
            diagnostics=ExtractionDiagnostic(provider_name="test"),
        ),
    )
    store = SimplePropertyGraphStore()
    store.upsert_nodes([
        EntityNode(name="质控报警", label="Alarm"),
        EntityNode(name="校准失败", label="FaultSymptom"),
        EntityNode(name="错误根因", label="RootCause"),
    ])
    store.upsert_relations([
        Relation(label="ALARM_INDICATES", source_id="质控报警", target_id="校准失败"),
        Relation(label="ALARM_INDICATES", source_id="质控报警", target_id="错误根因"),
    ])
    store.persist(str(map_dir / "property_graph_store.json"))

    app = FastAPI()
    app.include_router(cognitive_map_routes.router)
    client = TestClient(app)

    response = client.post(f"/api/cognitive-maps/{map_id}/publish")

    assert response.status_code == 200
    payload = response.json()
    assert payload["published_entity_count"] == 2
    assert payload["published_relation_count"] == 1
    assert payload["available_entity_count"] == 2
    assert payload["available_relation_count"] == 1
    assert payload["already_published"] is False
    assert payload["evaluation"]["usable_for_agent"] is True

    entities_response = client.get(f"/api/cognitive-maps/{map_id}/entities")
    statuses = {item["entity_id"]: item["review_status"] for item in entities_response.json()["entities"]}
    assert statuses["ent_alarm"] == "published"
    assert statuses["ent_fault"] == "published"
    assert statuses["ent_rejected"] == "rejected"

    query_response = client.post(
        f"/api/cognitive-maps/{map_id}/query-graph",
        json={"task": "诊断质控报警", "agent_mode": "ops", "entity_hints": ["质控报警"]},
    )
    view = query_response.json()["view"]
    assert [item["name"] for item in view["entities"]] == ["质控报警", "校准失败"]
    assert view["relations"][0]["relation_type"] == "alarm_indicates"

    second_response = client.post(f"/api/cognitive-maps/{map_id}/publish")

    assert second_response.status_code == 200
    second_payload = second_response.json()
    assert second_payload["published_entity_count"] == 0
    assert second_payload["published_relation_count"] == 0
    assert second_payload["available_entity_count"] == 2
    assert second_payload["available_relation_count"] == 1
    assert second_payload["already_published"] is True
    assert second_payload["evaluation"]["usable_for_agent"] is True


def test_cognitive_map_api_persists_llamaindex_property_graph_store(tmp_path: Path, monkeypatch):
    from llama_index.core.graph_stores.simple_labelled import SimplePropertyGraphStore
    from llama_index.core.graph_stores.types import EntityNode, Relation

    from app.api import cognitive_map_routes

    monkeypatch.setattr(cognitive_map_routes, "COGNITIVE_MAPS_ROOT", tmp_path)

    class FakeExtractor:
        def __init__(self):
            self.last_property_graph_store = SimplePropertyGraphStore()
            self.last_property_graph_store.upsert_nodes(
                [
                    EntityNode(name="光化学反应", label="ProcessMechanism"),
                    EntityNode(name="臭氧", label="Pollutant"),
                ]
            )
            self.last_property_graph_store.upsert_relations(
                [Relation(label="affects", source_id="光化学反应", target_id="臭氧")]
            )

        async def extract(self, chunks, schema):
            chunk = chunks[0]
            return ExtractionResult(
                map_id=chunk.map_id,
                candidate_entities=[
                    CandidateEntity(
                        entity_id="ent_o3",
                        map_id=chunk.map_id,
                        entity_type="Pollutant",
                        name="臭氧",
                        source_evidence_ids=["ev_1"],
                    )
                ],
                evidence=[
                    Evidence(
                        evidence_id="ev_1",
                        map_id=chunk.map_id,
                        source_file_id=chunk.source_file_id,
                        chunk_id=chunk.chunk_id,
                        location=chunk.location,
                        text_span=chunk.text,
                        normalized_summary=chunk.text,
                    )
                ],
                diagnostics=ExtractionDiagnostic(provider_name="fake_llamaindex"),
            )

    monkeypatch.setattr(cognitive_map_routes, "create_llamaindex_llm", lambda provider: object())
    monkeypatch.setattr(cognitive_map_routes, "create_extractor_provider", lambda name=None, llm=None: FakeExtractor())

    app = FastAPI()
    app.include_router(cognitive_map_routes.router)
    client = TestClient(app)

    map_id = client.post("/api/cognitive-maps", json={"name": "PG持久化"}).json()["id"]
    client.post(
        f"/api/cognitive-maps/{map_id}/files",
        files={"file": ("notes.md", "臭氧受光化学反应影响。", "text/markdown")},
    )

    response = client.post(
        f"/api/cognitive-maps/{map_id}/build",
        json={"extractor_provider": "llamaindex", "llm_provider": "project"},
    )

    assert response.status_code == 200
    assert (tmp_path / map_id / "property_graph_store.json").exists()


def test_cognitive_map_view_can_filter_unreviewed_candidates():
    from app.agent.cognition.view_builder import CognitiveMapViewBuilder
    from app.agent.cognition.models import CognitiveMapQuery

    extraction = ExtractionResult(
        map_id="map_1",
        candidate_entities=[
            CandidateEntity(
                entity_id="ent_confirmed",
                map_id="map_1",
                entity_type="Pollutant",
                name="臭氧",
                review_status="confirmed",
                source_evidence_ids=["ev_1"],
            ),
            CandidateEntity(
                entity_id="ent_candidate",
                map_id="map_1",
                entity_type="Hypothesis",
                name="待审核假设",
                review_status="candidate",
                source_evidence_ids=["ev_1"],
            ),
        ],
        evidence=[
            Evidence(
                evidence_id="ev_1",
                map_id="map_1",
                source_file_id="file_1",
                chunk_id="chunk_1",
                location="paragraph 1",
                text_span="臭氧受光化学反应影响。",
                normalized_summary="臭氧受光化学反应影响。",
            )
        ],
        diagnostics=ExtractionDiagnostic(provider_name="test"),
    )

    view = CognitiveMapViewBuilder().build_from_extraction(
        CognitiveMapQuery(task="分析臭氧", agent_mode="expert", map_ids=["map_1"]),
        extraction,
        allowed_review_statuses={"confirmed"},
    )

    assert [entity.name for entity in view.entities] == ["臭氧"]
    assert "待审核假设" not in view.prompt_summary


def test_cognitive_map_evidence_detail_returns_full_text(tmp_path: Path, monkeypatch):
    from app.api import cognitive_map_routes

    monkeypatch.setattr(cognitive_map_routes, "COGNITIVE_MAPS_ROOT", tmp_path)
    map_id = "map_evidence_detail"
    map_dir = tmp_path / map_id
    map_dir.mkdir(parents=True)
    (map_dir / "map.json").write_text(
        '{"id":"map_evidence_detail","name":"证据详情","status":"published"}',
        encoding="utf-8",
    )
    cognitive_map_routes._save_extraction(
        map_id,
        ExtractionResult(
            map_id=map_id,
            evidence=[
                Evidence(
                    evidence_id="ev_long",
                    map_id=map_id,
                    source_file_id="file_1",
                    chunk_id="chunk_1",
                    location="page 1",
                    text_span="完整原文" * 300,
                    normalized_summary="短证据摘要",
                    quote="关键原文句",
                    support_type="direct",
                )
            ],
            diagnostics=ExtractionDiagnostic(provider_name="test"),
        ),
    )

    app = FastAPI()
    app.include_router(cognitive_map_routes.router)
    client = TestClient(app)

    list_response = client.get(f"/api/cognitive-maps/{map_id}/evidence")
    detail_response = client.get(f"/api/cognitive-maps/{map_id}/evidence/ev_long")

    assert list_response.status_code == 200
    listed = list_response.json()["evidence"][0]
    assert "text_span" not in listed
    assert listed["summary"] == "短证据摘要"
    assert listed["quote"] == "关键原文句"
    assert detail_response.status_code == 200
    detailed = detail_response.json()["evidence"]
    assert detailed["text_span"] == "完整原文" * 300


def test_cognitive_map_guidance_omits_views_and_full_evidence_by_default():
    from app.tools.analysis.cognitive_map_guidance.tool import build_guidance_response

    result = build_guidance_response(
        guidance={
            "matched": True,
            "task": "诊断故障",
            "agent_mode": "ops",
            "graph_entities": [
                {
                    "entity_id": "ent_1",
                    "name": "仪器故障",
                    "source_evidence_ids": ["ev_1"],
                }
            ],
            "graph_relations": [],
            "analysis_directions": [{"hypothesis": "仪器故障 -> 数据无效"}],
            "data_requirements": [],
            "suggested_tools": [],
            "missing_hints": [],
            "evidence": [
                {
                    "evidence_id": "ev_1",
                    "location": "page 1",
                    "normalized_summary": "短证据摘要",
                    "text_span": "很长原文" * 500,
                }
            ],
            "views": [{"prompt_summary": "很长摘要" * 500}],
            "map_ids": ["map_1"],
            "sources": {"map_1": "property_graph_store"},
        },
        include_views=False,
        include_evidence_text=False,
        max_evidence=5,
        max_quote_chars=80,
    )

    data = result["data"]
    assert "views" not in data
    assert data["evidence_refs"] == [
        {
            "evidence_id": "ev_1",
            "location": "page 1",
            "summary": "短证据摘要",
            "quote": "",
            "support_type": "unknown",
            "evidence_quality": "unknown",
            "needs_verification": False,
            "source_file_id": "",
        }
    ]
    assert "text_span" not in data["evidence_refs"][0]
    assert "evidence" not in data


def test_llamaindex_extractor_uses_relation_level_evidence_summary():
    from app.agent.cognition.providers.llamaindex_extractor import LlamaIndexPropertyGraphExtractorProvider

    extractor = LlamaIndexPropertyGraphExtractorProvider()
    extraction = extractor.map_payload_to_extraction(
        map_id="map_1",
        payload={
            "entities": [
                {"name": "流量误差", "type": "DataMetric", "evidence_id": "ev_1"},
                {"name": "流量系统故障", "type": "RootCause", "evidence_id": "ev_1"},
            ],
            "relations": [
                {
                    "source": "流量误差",
                    "source_type": "DataMetric",
                    "type": "metric_anomaly_supports",
                    "target": "流量系统故障",
                    "target_type": "RootCause",
                    "evidence_id": "ev_1",
                    "evidence_quote": "当实测流量与设定流量误差超过±5%时，须对流量进行校准。",
                    "evidence_summary": "流量误差超限可作为流量系统异常的核验依据。",
                    "support_type": "direct",
                }
            ],
        },
        evidence_by_id={
            "ev_1": {
                "source_file_id": "file_1",
                "chunk_id": "chunk_1",
                "location": "page 10",
                "text_span": "完整原文" * 300,
            }
        },
    )

    evidence = extraction.evidence[0]
    assert evidence.quote == "当实测流量与设定流量误差超过±5%时，须对流量进行校准。"
    assert evidence.normalized_summary == "流量误差超限可作为流量系统异常的核验依据。"
    assert evidence.support_type == "direct"
    assert extraction.candidate_relations[0].source_evidence_ids == ["ev_1"]


def test_project_llm_structured_prompt_requests_relation_evidence_properties():
    from app.agent.cognition.llm_factory import ProjectLLMAdapter

    class FakeLLMService:
        async def chat(self, *args, **kwargs):
            return "{}"

    adapter = ProjectLLMAdapter(llm_service=FakeLLMService())

    prompt = adapter._build_structured_kg_prompt("流量误差超过阈值需校准。", 3)

    assert '"properties"' in prompt
    assert '"evidence_quote"' in prompt
    assert '"evidence_summary"' in prompt
    assert '"support_type"' in prompt
    assert "relation.properties.evidence_quote" in prompt


def test_project_llm_does_not_normalize_flat_relation_evidence_into_properties():
    from app.agent.cognition.llm_factory import ProjectLLMAdapter

    class FakeLLMService:
        async def chat(self, *args, **kwargs):
            return "{}"

    adapter = ProjectLLMAdapter(llm_service=FakeLLMService())

    payload = adapter._normalize_structured_payload(
        {
            "triplets": [
                {
                    "subject": {"type": "DataMetric", "name": "流量误差"},
                    "relation": {
                        "type": "metric_anomaly_supports",
                        "evidence_quote": "流量误差超过±5%时需校准。",
                        "evidence_summary": "流量误差超限支持流量系统异常排查。",
                        "support_type": "direct",
                    },
                    "object": {"type": "RootCause", "name": "流量系统故障"},
                }
            ]
        }
    )

    relation = payload["triplets"][0]["relation"]
    assert "properties" not in relation
    assert relation["evidence_quote"] == "流量误差超过±5%时需校准。"
    assert relation["evidence_summary"] == "流量误差超限支持流量系统异常排查。"


def test_llamaindex_property_graph_falls_back_to_relation_level_evidence():
    from llama_index.core.graph_stores.simple_labelled import SimplePropertyGraphStore
    from llama_index.core.graph_stores.types import EntityNode, Relation

    from app.agent.cognition.providers.llamaindex_extractor import LlamaIndexPropertyGraphExtractorProvider

    extractor = LlamaIndexPropertyGraphExtractorProvider()
    store = SimplePropertyGraphStore()
    long_source_text = "前置说明。" + ("无关原文" * 200) + "超长尾部不应进入短证据"
    metadata = {
        "source_file_id": "file_1",
        "chunk_id": "chunk_1",
        "location": "page 10",
        "text_span": long_source_text,
    }
    store.upsert_nodes(
        [
            EntityNode(name="流量误差", label="DataMetric", properties=metadata),
            EntityNode(name="流量系统故障", label="RootCause", properties=metadata),
        ]
    )
    store.upsert_relations(
        [
            Relation(
                label="METRIC_ANOMALY_SUPPORTS",
                source_id="流量误差",
                target_id="流量系统故障",
                properties=metadata,
            )
        ]
    )

    extraction = extractor.map_property_graph_store_to_extraction("map_1", store)

    assert len(extraction.candidate_relations) == 1
    relation = extraction.candidate_relations[0]
    assert relation.source_evidence_ids
    evidence = next(item for item in extraction.evidence if item.evidence_id == relation.source_evidence_ids[0])
    assert evidence.normalized_summary == "流量误差 --metric_anomaly_supports--> 流量系统故障"
    assert evidence.support_type == "fallback"
    assert evidence.evidence_quality == "missing_relation_evidence"
    assert evidence.supported_relation_ids == [relation.relation_id]
    assert "超长尾部不应进入短证据" not in evidence.normalized_summary
    assert evidence.text_span == long_source_text


def test_llamaindex_structured_payload_relation_properties_become_llm_evidence():
    from llama_index.core.graph_stores.simple_labelled import SimplePropertyGraphStore

    from app.agent.cognition.models import DocumentChunk
    from app.agent.cognition.providers.llamaindex_extractor import LlamaIndexPropertyGraphExtractorProvider

    class FakeLLM:
        last_structured_payload = {
            "triplets": [
                {
                    "chunk_id": "chunk_1",
                    "subject": {"type": "DataMetric", "name": "流量误差"},
                    "relation": {
                        "type": "metric_anomaly_supports",
                        "properties": {
                            "evidence_quote": "当实测流量与设定流量误差超过±5%时，须对流量进行校准。",
                            "evidence_summary": "流量误差超限可作为流量系统异常的核验依据。",
                            "support_type": "direct",
                        },
                    },
                    "object": {"type": "RootCause", "name": "流量系统故障"},
                }
            ]
        }

    extractor = LlamaIndexPropertyGraphExtractorProvider(llm=FakeLLM())
    schema = CognitiveSchema.default_air_quality_schema()
    extractor.build_schema_components(schema)
    store = SimplePropertyGraphStore()
    chunk = DocumentChunk(
        chunk_id="chunk_1",
        map_id="map_1",
        source_file_id="file_1",
        chunk_index=0,
        text="当实测流量与设定流量误差超过±5%时，须对流量进行校准。",
        location="page 10",
    )

    extractor._populate_store_from_last_structured_payload(store, [chunk])
    extraction = extractor.map_property_graph_store_to_extraction("map_1", store)

    evidence = next(item for item in extraction.evidence if item.supported_relation_ids)
    assert evidence.quote == "当实测流量与设定流量误差超过±5%时，须对流量进行校准。"
    assert evidence.normalized_summary == "流量误差超限可作为流量系统异常的核验依据。"
    assert evidence.support_type == "direct"
    assert evidence.evidence_quality == "llm_relation_evidence"


def test_cognitive_map_evaluation_exposes_fallback_evidence_quality():
    from app.api import cognitive_map_routes

    extraction = ExtractionResult(
        map_id="map_fallback_quality",
        candidate_entities=[
            CandidateEntity(entity_id="ent_metric", map_id="map_fallback_quality", entity_type="DataMetric", name="流量误差", review_status="published"),
            CandidateEntity(entity_id="ent_root", map_id="map_fallback_quality", entity_type="RootCause", name="流量系统故障", review_status="published"),
        ],
        candidate_relations=[
            CandidateRelation(
                relation_id="rel_1",
                map_id="map_fallback_quality",
                source_entity_id="ent_metric",
                target_entity_id="ent_root",
                relation_type="metric_anomaly_supports",
                source_evidence_ids=["ev_fallback"],
                review_status="published",
            )
        ],
        evidence=[
            Evidence(
                evidence_id="ev_fallback",
                map_id="map_fallback_quality",
                source_file_id="file_1",
                chunk_id="chunk_1",
                location="page 1",
                text_span="完整原文",
                normalized_summary="流量误差 --metric_anomaly_supports--> 流量系统故障",
                support_type="fallback",
                evidence_quality="missing_relation_evidence",
                supported_relation_ids=["rel_1"],
            )
        ],
        diagnostics=ExtractionDiagnostic(provider_name="test"),
    )

    evaluation = cognitive_map_routes._generate_evaluation(extraction, property_graph_persisted=True)

    assert evaluation["fallback_evidence_count"] == 1
    assert evaluation["relation_evidence_summary_ratio"] == 0
    assert evaluation["relation_evidence_quote_ratio"] == 0
    assert evaluation["usable_for_agent"] is False


def test_cognitive_map_prompt_context_uses_short_evidence_not_full_source_text(tmp_path: Path, monkeypatch):
    from app.api import cognitive_map_routes

    monkeypatch.setattr(cognitive_map_routes, "COGNITIVE_MAPS_ROOT", tmp_path)

    map_id = "map_short_prompt"
    map_dir = tmp_path / map_id
    map_dir.mkdir(parents=True)
    cognitive_map_routes._write_json(
        map_dir / "map.json",
        {
            "id": map_id,
            "name": "短证据注入测试",
            "description": "",
            "status": "completed",
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
        },
    )
    cognitive_map_routes._write_json(map_dir / "files.json", [])
    long_text = "有效短句。" + ("长原文" * 300) + "PROMPT中不应出现的长尾"
    cognitive_map_routes._save_extraction(
        map_id,
        ExtractionResult(
            map_id=map_id,
            candidate_entities=[
                CandidateEntity(
                    entity_id="ent_metric",
                    map_id=map_id,
                    entity_type="DataMetric",
                    name="流量误差",
                    review_status="published",
                    source_evidence_ids=["ev_chunk"],
                ),
                CandidateEntity(
                    entity_id="ent_root",
                    map_id=map_id,
                    entity_type="RootCause",
                    name="流量系统故障",
                    review_status="published",
                    source_evidence_ids=["ev_chunk"],
                ),
            ],
            candidate_relations=[
                CandidateRelation(
                    relation_id="rel_1",
                    map_id=map_id,
                    source_entity_id="ent_metric",
                    target_entity_id="ent_root",
                    relation_type="metric_anomaly_supports",
                    review_status="published",
                    source_evidence_ids=["ev_rel"],
                )
            ],
            evidence=[
                Evidence(
                    evidence_id="ev_chunk",
                    map_id=map_id,
                    source_file_id="file_1",
                    chunk_id="chunk_1",
                    location="page 10",
                    text_span=long_text,
                    normalized_summary="ENTITY_CHUNK_HEADER " + long_text,
                ),
                Evidence(
                    evidence_id="ev_rel",
                    map_id=map_id,
                    source_file_id="file_1",
                    chunk_id="chunk_1",
                    location="page 10",
                    text_span=long_text,
                    normalized_summary="流量误差 --metric_anomaly_supports--> 流量系统故障",
                    quote="流量误差超限需检查流量系统。",
                    support_type="direct",
                    evidence_quality="llm_relation_evidence",
                    supported_relation_ids=["rel_1"],
                )
            ],
            diagnostics=ExtractionDiagnostic(provider_name="test"),
        ),
    )

    context = cognitive_map_routes.build_cognitive_map_prompt_context(
        task="诊断流量误差",
        agent_mode="ops",
        map_ids=[map_id],
        entity_hints=["流量误差"],
    )

    assert "流量误差超限需检查流量系统。" in context
    assert "证据质量: llm_relation_evidence" in context
    assert "ENTITY_CHUNK_HEADER" not in context
    assert "PROMPT中不应出现的长尾" not in context
    assert len(context) < 1200


def test_cognitive_map_graph_cleanup_removes_self_loops_and_duplicate_relations():
    from app.api import cognitive_map_routes

    extraction = ExtractionResult(
        map_id="map_1",
        candidate_entities=[
            CandidateEntity(entity_id="ent_a", map_id="map_1", entity_type="Pollutant", name="臭氧"),
            CandidateEntity(entity_id="ent_b", map_id="map_1", entity_type="Pollutant", name="PM2.5"),
        ],
        candidate_relations=[
            CandidateRelation(
                relation_id="rel_self",
                map_id="map_1",
                source_entity_id="ent_a",
                target_entity_id="ent_a",
                relation_type="affects",
            ),
            CandidateRelation(
                relation_id="rel_1",
                map_id="map_1",
                source_entity_id="ent_a",
                target_entity_id="ent_b",
                relation_type="affects",
            ),
            CandidateRelation(
                relation_id="rel_2",
                map_id="map_1",
                source_entity_id="ent_a",
                target_entity_id="ent_b",
                relation_type="affects",
            ),
        ],
        diagnostics=ExtractionDiagnostic(provider_name="test"),
    )

    cleaned = cognitive_map_routes._clean_extraction_graph(extraction)

    assert [relation.relation_id for relation in cleaned.candidate_relations] == ["rel_1"]


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
