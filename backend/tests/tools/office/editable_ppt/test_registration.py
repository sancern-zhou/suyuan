from pathlib import Path

from app.agent.prompts.tool_registry import ASSISTANT_TOOL_NAMES
from app.tools import create_global_tool_registry


def test_editable_ppt_tool_is_registered_and_exposed():
    registry = create_global_tool_registry()
    assert registry.get_tool("manage_editable_ppt") is not None
    assert "manage_editable_ppt" in ASSISTANT_TOOL_NAMES
    assert "create_pptx_with_ppt_master" in ASSISTANT_TOOL_NAMES


def test_workflow_declares_direct_file_edit_and_strict_gate():
    guide = Path("app/tools/office/editable_ppt/references/workflow.md").read_text(encoding="utf-8")
    assert "edit_file" in guide
    assert "3–5" in guide
    assert "strict" in guide
    assert "无需重新生成" in guide
