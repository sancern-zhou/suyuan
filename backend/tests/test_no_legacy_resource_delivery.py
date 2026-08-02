from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]


def test_backend_runtime_has_no_legacy_preview_delivery_protocol() -> None:
    production_files = [
        BACKEND_ROOT / "app/agent/runtime/event_bus.py",
        BACKEND_ROOT / "app/agent/runtime/observation_processor.py",
        BACKEND_ROOT / "app/api/session_routes.py",
        BACKEND_ROOT / "app/db/migrations/create_session_tables.sql",
    ]
    forbidden = (
        "office_document",
        "html_document",
        "_document_events",
        "office_documents",
        "self.events.result({",
        "def result(self, data",
    )

    violations = []
    for path in production_files:
        source = path.read_text(encoding="utf-8")
        for token in forbidden:
            if token in source:
                violations.append(f"{path.relative_to(BACKEND_ROOT)}: {token}")

    assert violations == []


def test_removed_backend_preview_modules_have_no_source_files() -> None:
    removed = (
        BACKEND_ROOT / "app/api/office_routes.py",
        BACKEND_ROOT / "app/api/html_artifact_routes.py",
    )
    assert [str(path.relative_to(BACKEND_ROOT)) for path in removed if path.exists()] == []


def test_tool_delivery_has_no_legacy_artifact_adapter() -> None:
    production_files = [
        BACKEND_ROOT / "app/tools/artifact_utils.py",
        BACKEND_ROOT / "app/tools/utility/present_artifact_tool.py",
        BACKEND_ROOT / "app/tools/html_artifact/tool.py",
        BACKEND_ROOT / "app/tools/report/report_package/tool.py",
        BACKEND_ROOT / "app/tools/office/ppt_master_tool.py",
        BACKEND_ROOT / "app/tools/office/read_pptx_tool.py",
    ]
    forbidden = (
        "attach_document_artifact",
        "build_document_artifact",
        'result_data["artifact"]',
        '"artifacts": [artifact]',
    )

    violations = []
    for path in production_files:
        source = path.read_text(encoding="utf-8")
        for token in forbidden:
            if token in source:
                violations.append(f"{path.relative_to(BACKEND_ROOT)}: {token}")

    assert violations == []
