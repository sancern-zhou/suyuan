import json
from pathlib import Path

import pytest

from app.tools.office.editable_ppt.project_service import (
    EditablePptProjectService,
    RevisionConflictError,
)


REVISED = """window.slideDataMap.set(1, {
  schemaVersion: "1.0", id: "cover", type: "cover", intent: "revised",
  layoutMode: "freeform", html: `<section data-pptx-id="root"><h1 data-pptx-id="title">新版</h1></section>`,
  nativeElements: [], speakerNotes: []
});
"""


def test_managed_edit_changes_only_dependent_slide(tmp_path):
    service = EditablePptProjectService(tmp_path)
    project = service.create_project(title="年度报告", theme="government")
    result = service.edit_source(
        project.project_dir, "slides/slide-001.js", REVISED, project.revision
    )
    assert result.revision == project.revision + 1
    assert result.dirty_slides == ["cover"]
    assert Path(project.project_dir, "slides/slide-001.js").read_text() == REVISED


def test_direct_document_edit_is_reconciled_without_rewriting_source(tmp_path):
    service = EditablePptProjectService(tmp_path)
    project = service.create_project(title="年度报告")
    slide = Path(project.project_dir, "slides/slide-001.js")
    slide.write_text(REVISED, encoding="utf-8")
    state = service.inspect(project.project_dir)
    assert state.revision == project.revision + 1
    assert state.dirty_slides == ["cover"]
    assert state.changes[-1].source == "direct_document_edit"
    assert slide.read_text(encoding="utf-8") == REVISED


def test_rejects_path_escape_and_stale_revision_without_writes(tmp_path):
    service = EditablePptProjectService(tmp_path)
    project = service.create_project(title="年度报告")
    with pytest.raises(ValueError, match="outside project root"):
        service.edit_source(project.project_dir, "../outside.js", "bad", project.revision)
    with pytest.raises(ValueError, match="outside editable source scope"):
        service.edit_source(project.project_dir, "build/presentation.pptx", b"bad", project.revision)
    with pytest.raises(RevisionConflictError):
        service.edit_source(project.project_dir, "theme.json", "{}", project.revision - 1)
    assert json.loads(Path(project.project_dir, "theme.json").read_text())["fontTitle"]


def test_theme_edit_dirties_all_slides_and_restore_recovers_source(tmp_path):
    service = EditablePptProjectService(tmp_path)
    project = service.create_project(title="年度报告")
    theme_path = Path(project.project_dir, "theme.json")
    original = theme_path.read_text(encoding="utf-8")
    changed = original.replace("Microsoft YaHei", "Noto Sans CJK SC")
    edited = service.edit_source(project.project_dir, "theme.json", changed, project.revision)
    assert edited.dirty_slides == ["cover"]
    restored = service.restore_revision(project.project_dir, project.revision, edited.revision)
    assert restored.revision == edited.revision + 1
    assert theme_path.read_text(encoding="utf-8") == original


def test_asset_edit_dirties_only_consumers(tmp_path):
    service = EditablePptProjectService(tmp_path)
    project = service.create_project(title="年度报告")
    root = Path(project.project_dir)
    state = service.edit_source(root, "assets/hero.png", b"before", project.revision)
    slide = (root / "slides" / "slide-001.js").read_text(encoding="utf-8")
    state = service.edit_source(
        root, "slides/slide-001.js", slide.replace("</section>", '<img src="assets/hero.png"></section>'), state.revision
    )
    result = service.edit_source(root, "assets/hero.png", b"after", state.revision)
    assert result.dirty_slides == ["cover"]


def test_project_title_is_safe_inside_javascript_template(tmp_path):
    service = EditablePptProjectService(tmp_path)
    project = service.create_project(title='`${globalThis.process}` <script>')
    source = Path(project.project_dir, "slides/slide-001.js").read_text(encoding="utf-8")
    assert "\\`\\${globalThis.process}\\`" in source
    assert "&lt;script&gt;" in source


def test_new_project_uses_the_available_cjk_sans_font(tmp_path):
    service = EditablePptProjectService(tmp_path)
    project = service.create_project(title="字体基线")
    theme = json.loads(Path(project.project_dir, "theme.json").read_text(encoding="utf-8"))
    assert theme["fontTitle"] == "Noto Sans CJK SC"
    assert theme["fontBody"] == "Noto Sans CJK SC"
    assert theme["pptFontTitle"] == "Microsoft YaHei"
    assert theme["pptFontBody"] == "Microsoft YaHei"


def test_invalid_managed_deck_edit_does_not_replace_source(tmp_path):
    service = EditablePptProjectService(tmp_path)
    project = service.create_project(title="年度报告")
    deck = Path(project.project_dir, "deck.json")
    before = deck.read_text(encoding="utf-8")
    with pytest.raises(ValueError, match="source validation failed"):
        service.edit_source(project.project_dir, "deck.json", "{bad", project.revision)
    assert deck.read_text(encoding="utf-8") == before
    assert service.inspect(project.project_dir).revision == project.revision
