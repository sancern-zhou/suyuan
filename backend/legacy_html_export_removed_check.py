from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_legacy_export_router_removed():
    assert not (PROJECT_ROOT / "app" / "routers" / "export.py").exists()
    assert not (PROJECT_ROOT / "app" / "services" / "report_exporter.py").exists()

    app_main = (PROJECT_ROOT / "app" / "main.py").read_text(encoding="utf-8")
    assert "export_router" not in app_main
    assert "app.routers import export" not in app_main


def test_execute_python_has_no_html_artifact_compatibility():
    source = (
        PROJECT_ROOT
        / "backend"
        / "app"
        / "tools"
        / "utility"
        / "execute_python_tool.py"
    ).read_text(encoding="utf-8")

    assert "_standardize_html_report" not in source
    assert "execute_python_html_artifact_standardized" not in source
    assert "html_artifacts" not in source
    assert "create_html_artifact" not in source
    assert "save_html_report" not in source
    assert "HTML_REPORT_SAVED" not in source
    assert "Office/HTML" not in source


def test_execute_python_manual_has_no_html_artifact_guidance():
    manual = (
        PROJECT_ROOT
        / "backend"
        / "app"
        / "tools"
        / "utility"
        / "execute_python_manual.md"
    ).read_text(encoding="utf-8")

    assert "save_html_report" not in manual
    assert "create_html_artifact" not in manual
    assert "HTML" not in manual
    assert "html" not in manual


def test_notebook_product_surface_removed():
    removed_paths = [
        PROJECT_ROOT / "backend" / "app" / "api" / "notebook_routes.py",
        PROJECT_ROOT / "backend" / "app" / "services" / "notebook_converter.py",
        PROJECT_ROOT / "backend" / "app" / "tools" / "utility" / "notebook_edit_tool.py",
        PROJECT_ROOT / "backend" / "app" / "tools" / "utility" / "generate_shareable_notebook",
        PROJECT_ROOT / "backend" / "app" / "tools" / "assistant" / "notebook_edit.py",
        PROJECT_ROOT / "backend" / "app" / "tools" / "analysis" / "notebook_edit",
        PROJECT_ROOT / "frontend" / "src" / "components" / "NotebookPanel.vue",
        PROJECT_ROOT / "frontend" / "src" / "components" / "NotebookRenderer.vue",
    ]
    for path in removed_paths:
        assert not path.exists(), f"Notebook surface still exists: {path}"

    scanned_files = [
        PROJECT_ROOT / "backend" / "app" / "core" / "routing.py",
        PROJECT_ROOT / "backend" / "app" / "tools" / "__init__.py",
        PROJECT_ROOT / "backend" / "app" / "agent" / "prompts" / "tool_registry.py",
        PROJECT_ROOT / "backend" / "app" / "tools" / "utility" / "read_file_tool.py",
        PROJECT_ROOT / "backend" / "app" / "tools" / "utility" / "execute_python_tool.py",
        PROJECT_ROOT / "backend" / "app" / "tools" / "assistant" / "__init__.py",
        PROJECT_ROOT / "frontend" / "src" / "components" / "OfficeDocumentPanel.vue",
        PROJECT_ROOT / "frontend" / "src" / "components" / "reactAnalysis" / "RightPanelContainer.vue",
        PROJECT_ROOT / "frontend" / "src" / "stores" / "reactStore.js",
    ]
    forbidden = [
        "notebook",
        "Notebook",
        "ipynb",
        "jupyter",
        "Jupyter",
        "generate_shareable_notebook",
    ]
    for file_path in scanned_files:
        content = file_path.read_text(encoding="utf-8")
        for token in forbidden:
            assert token not in content, f"{token!r} still present in {file_path}"
