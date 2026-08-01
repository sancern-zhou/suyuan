from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[1] / "app"
FORBIDDEN = (
    "_extract_visualizations_from_messages",
    "_extract_office_documents_from_messages",
    "session_resource_manifests",
    'get("office_documents"',
    'metadata.get("visualizations"',
    'session_data.get("data_ids")',
    'session_data.get("visual_ids")',
    "SessionDB.data_ids",
    "SessionDB.visual_ids",
    "saved_visualizations",
    "collected_visuals",
    '@router.get("/file/{file_path:path}")',
    '@router.post("/download-word")',
    '@router.post("/download-ppt")',
    '@router.post("/download-excel")',
    "/api/file/",
    "/api/office/download-word",
    "/api/office/download-ppt",
    "/api/office/download-excel",
    "resource_manifest_service",
    "app.agent.resources.models",
    "SessionResourceRef",
    "app.api.office_routes",
    'lazy_artifacts: bool = False',
)


def test_production_sources_have_no_legacy_resource_mechanisms():
    violations: list[str] = []
    for path in APP_ROOT.rglob("*.py"):
        if path.name.endswith("_test.py") or path.name.endswith("_spec.py"):
            continue
        source = path.read_text(encoding="utf-8")
        for marker in FORBIDDEN:
            if marker in source:
                violations.append(f"{path.relative_to(APP_ROOT)}: {marker}")
    assert violations == []


def test_openapi_has_no_path_download_or_typed_office_download_routes():
    routing = (APP_ROOT / "core" / "routing.py").read_text(encoding="utf-8")
    assert "app.api.office_routes" not in routing
    assert not (APP_ROOT / "api" / "office_routes.py").exists()
