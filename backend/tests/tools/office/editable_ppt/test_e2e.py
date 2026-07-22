import shutil
from pathlib import Path

import pytest

from app.tools.office.editable_ppt.compiler_client import EditablePptCompilerClient
from app.tools.office.editable_ppt.project_service import EditablePptProjectService
from app.tools.office.editable_ppt.tool import ManageEditablePptTool


RUNTIME = Path("app/tools/office/editable_ppt_runtime").resolve()
REPRESENTATIVE = RUNTIME / "fixtures" / "representative"


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.browser
@pytest.mark.slow
async def test_real_ten_slide_compile_and_single_slide_incremental_recompile(tmp_path):
    service = EditablePptProjectService(tmp_path)
    tool = ManageEditablePptTool(
        project_service=service,
        compiler_client=EditablePptCompilerClient(timeout_seconds=90),
    )
    created = await tool.execute(operation="create", title="代表性验收稿")
    project_dir = Path(created["data"]["project_dir"])
    shutil.copytree(REPRESENTATIVE, project_dir, dirs_exist_ok=True)
    reconciled = await tool.execute(operation="inspect", project_dir=str(project_dir))
    assert reconciled["data"]["dirty_slides"] == [
        "agenda", "city-story", "cover", "delivery-process", "ending",
        "growth-chart", "kpi", "policy-context", "project-table", "roadmap",
    ]
    first = await tool.execute(operation="compile", project_dir=str(project_dir))
    assert first["success"] is True
    assert first["data"]["report"]["slideCount"] == 10
    assert first["data"]["report"]["measurement"]["cache"] == {"enabled": True, "hits": 0, "misses": 10}

    slide = project_dir / "slides" / "slide-003.js"
    slide.write_text(slide.read_text(encoding="utf-8").replace("政策牵引", "政策驱动"), encoding="utf-8")
    inspected = await tool.execute(operation="inspect", project_dir=str(project_dir))
    assert inspected["data"]["dirty_slides"] == ["policy-context"]
    second = await tool.execute(operation="compile", project_dir=str(project_dir))
    assert second["success"] is True
    assert second["data"]["report"]["measurement"]["cache"] == {"enabled": True, "hits": 9, "misses": 1}
    assert Path(second["data"]["pptxPath"]).stat().st_size > 0
