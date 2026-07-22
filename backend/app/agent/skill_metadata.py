"""Metadata for selectable, tool-backed Agent scenarios."""

SKILL_METADATA = {
    "editable_ppt_generation": {
        "name": "高质量可编辑 PPT 生成",
        "description": "从源码项目生成并多轮完善原生可编辑 PPTX",
        "entry_reference": "app/tools/office/editable_ppt/references/index.md",
        "required_tools": ["manage_editable_ppt", "read_file", "edit_file", "validate_pptx"],
    }
}
