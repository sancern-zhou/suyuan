from pathlib import Path

import pytest

from app.project_config.loader import ProjectConfigError, load_project_context

REPO_ROOT = Path(__file__).resolve().parents[3]


def test_default_project_loads_legacy_module():
    context = load_project_context("default", repo_root=REPO_ROOT)

    assert context.manifest.project == "default"
    assert context.enabled_modules == frozenset({"core", "legacy"})
    assert context.manifest.frontend.theme == "default"


def test_unknown_module_fails_closed(tmp_path: Path):
    (tmp_path / "projects" / "broken").mkdir(parents=True)
    (tmp_path / "modules").mkdir()
    (tmp_path / "projects" / "broken" / "project.yaml").write_text(
        "schema_version: 1\nproject: broken\nmodules: [missing]\n",
        encoding="utf-8",
    )

    with pytest.raises(ProjectConfigError, match="unknown module: missing"):
        load_project_context("broken", repo_root=tmp_path)


def test_missing_dependency_fails_closed(tmp_path: Path):
    (tmp_path / "projects" / "demo").mkdir(parents=True)
    (tmp_path / "modules" / "noise").mkdir(parents=True)
    (tmp_path / "projects" / "demo" / "project.yaml").write_text(
        "schema_version: 1\nproject: demo\nmodules: [noise]\n",
        encoding="utf-8",
    )
    (tmp_path / "modules" / "noise" / "module.yaml").write_text(
        "schema_version: 1\nmodule: noise\ndependencies: [atmosphere]\n",
        encoding="utf-8",
    )

    with pytest.raises(ProjectConfigError, match="noise requires atmosphere"):
        load_project_context("demo", repo_root=tmp_path)


@pytest.mark.parametrize("project_id", ["../secret", "a/b", "", "UPPER CASE"])
def test_unsafe_project_identifier_is_rejected(project_id: str, tmp_path: Path):
    with pytest.raises(ProjectConfigError, match="invalid project identifier"):
        load_project_context(project_id, repo_root=tmp_path)
