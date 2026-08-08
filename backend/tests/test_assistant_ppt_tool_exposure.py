from app.agent.prompts.tool_registry import (
    ASSISTANT_TOOL_NAMES,
    ASSISTANT_TOOL_ORDER,
    PPT_TOOL_NAMES,
    PPT_TOOL_ORDER,
)
from app.agent.prompts.assistant_prompt import build_assistant_prompt
from app.agent.tool_adapter import get_tool_schemas
from app.tools.office.ppt_master_tool import CreatePptxWithPptMasterTool


def test_assistant_mode_exposes_ppt_master_tool_not_deck_or_low_level_renderer():
    assert "create_pptx_with_ppt_master" in ASSISTANT_TOOL_NAMES
    assert "create_pptx_with_ppt_master" in ASSISTANT_TOOL_ORDER
    assert "revise_pptx_with_ppt_master" not in ASSISTANT_TOOL_NAMES
    assert "revise_pptx_with_ppt_master" not in ASSISTANT_TOOL_ORDER
    assert "analyze_pptx_template" not in ASSISTANT_TOOL_NAMES
    assert "analyze_pptx_template" not in ASSISTANT_TOOL_ORDER
    assert "create_pptx_from_template" not in ASSISTANT_TOOL_NAMES
    assert "create_pptx_from_template" not in ASSISTANT_TOOL_ORDER

    assert "create_pptx_from_deck" not in ASSISTANT_TOOL_NAMES
    assert "create_pptx_from_deck" not in ASSISTANT_TOOL_ORDER
    assert "create_pptx" not in ASSISTANT_TOOL_NAMES
    assert "create_pptx" not in ASSISTANT_TOOL_ORDER


def test_assistant_and_ppt_modes_do_not_expose_dedicated_image_analysis_tool():
    assert "analyze_image" not in ASSISTANT_TOOL_NAMES
    assert "analyze_image" not in ASSISTANT_TOOL_ORDER
    assert "analyze_image" not in PPT_TOOL_NAMES
    assert "analyze_image" not in PPT_TOOL_ORDER


def test_assistant_prompt_routes_images_through_native_multimodal_read_file():
    prompt = build_assistant_prompt(["read_file"])

    assert "`analyze_image`" not in prompt
    assert "as_multimodal_attachment=true" in prompt


def test_tool_schema_adapter_never_exposes_dedicated_image_analysis_tool():
    schemas = get_tool_schemas(allowed_tool_names=["analyze_image"])

    assert "analyze_image" not in {schema["name"] for schema in schemas}


def test_assistant_mode_does_not_expose_retired_word_or_office_xml_tools():
    retired_tools = {
        "edit_word_document",
        "word_edit",
        "find_replace_word",
        "accept_word_changes",
        "unpack_office",
        "pack_office",
    }

    assert retired_tools.isdisjoint(ASSISTANT_TOOL_NAMES)
    assert retired_tools.isdisjoint(ASSISTANT_TOOL_ORDER)


def test_assistant_prompt_requires_reading_ppt_guide_before_generation():
    prompt = build_assistant_prompt(["create_pptx_with_ppt_master", "read_file"])

    assert "PPT操作指南.md" in prompt
    assert "生成 PPT 前" in prompt
    assert "必须先阅读" in prompt


def test_ppt_master_schema_requires_reading_ppt_guide_before_generation():
    schema = CreatePptxWithPptMasterTool().get_function_schema()

    serialized = str(schema)
    assert "PPT操作指南.md" in serialized
    assert "生成 PPT 前" in serialized
    assert "必须先阅读" in serialized


def test_ppt_master_schema_exposes_agent_shape_plan():
    schema = CreatePptxWithPptMasterTool().get_function_schema()

    properties = schema["parameters"]["properties"]
    assert "slide_plan" in properties
    assert "slide_plan_path" in properties
    assert "Agent 自行规划" in properties["slide_plan"]["description"]
    assert "shape" in properties["slide_plan"]["description"].lower()


def test_ppt_master_schema_uses_operation_instead_of_global_title_required():
    schema = CreatePptxWithPptMasterTool().get_function_schema()

    properties = schema["parameters"]["properties"]
    assert schema["parameters"]["required"] == []
    assert properties["operation"]["enum"] == ["create", "append", "replace", "patch", "render"]


def test_create_ppt_master_schema_exposes_create_revision_and_render_parameters():
    schema = CreatePptxWithPptMasterTool().get_function_schema()

    properties = schema["parameters"]["properties"]
    assert "title" in properties
    assert "outline" in properties
    assert "slide_plan" in properties
    assert "slide_plan_path" in properties
    assert "base_plan_path" in properties
    assert "base_project_dir" in properties
    assert "plan_patch" in properties
    assert "plan_patch_path" in properties
    assert "batch_slides" in properties
    assert "after_slide" in properties
    assert "replace_slides" in properties
    assert "insert_slide_after" in properties
    assert "file_path" in properties


def test_create_ppt_master_append_operation_normalizes_batch_slides_to_plan_patch():
    patch = CreatePptxWithPptMasterTool()._normalize_operation_patch(
        operation="append",
        plan_patch=None,
        after_slide=3,
        batch_slides=[{"title": "新增页", "shapes": []}],
        replace_slides=None,
        insert_slide_after=None,
    )

    assert patch == {
        "insert_slide_after": [
            {
                "after_slide": 3,
                "slides": [{"title": "新增页", "shapes": []}],
            }
        ]
    }


def test_create_ppt_master_loads_slide_plan_from_path(tmp_path):
    import asyncio
    import json

    slide_plan_path = tmp_path / "slide_plan.json"
    slide_plan_path.write_text(
        json.dumps([{"title": "路径输入页", "shapes": []}], ensure_ascii=False),
        encoding="utf-8",
    )

    result = asyncio.run(
        CreatePptxWithPptMasterTool().execute(
            title="路径输入测试",
            slide_plan_path=str(slide_plan_path),
            output_file=str(tmp_path / "path_input.pptx"),
            project_dir=str(tmp_path / "project"),
            enable_preview=False,
            run_validation=False,
        )
    )

    assert result["success"] is True
    titles = [page["title"] for page in result["data"]["page_plan"]]
    assert "路径输入页" in titles


def test_create_ppt_master_loads_plan_patch_from_path(monkeypatch, tmp_path):
    import asyncio
    import json

    base_plan_path = tmp_path / "slide_plan.v1.json"
    base_plan_path.write_text(
        json.dumps(
            [
                {"slide": 1, "layout": "cover_statement", "title": "封面", "points": []},
                {"slide": 2, "layout": "agent_shape_plan", "title": "原页面", "shapes": []},
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    patch_path = tmp_path / "plan_patch.json"
    patch_path.write_text(
        json.dumps(
            {
                "insert_slide_after": [
                    {
                        "after_slide": 1,
                        "slides": [{"title": "文件补丁页", "shapes": []}],
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    def fake_render_pptx(self, output_path, title, page_plan, palette):
        output_path.write_bytes(b"fake pptx")

    monkeypatch.setattr(CreatePptxWithPptMasterTool, "_render_pptx", fake_render_pptx)

    result = asyncio.run(
        CreatePptxWithPptMasterTool().execute(
            operation="patch",
            base_plan_path=str(base_plan_path),
            plan_patch_path=str(patch_path),
            output_file=str(tmp_path / "patched.pptx"),
            project_dir=str(tmp_path / "project"),
            enable_preview=False,
            run_validation=False,
            quality="draft",
        )
    )

    assert result["success"] is True
    assert [page["title"] for page in result["data"]["page_plan"]] == ["封面", "文件补丁页", "原页面"]
    assert result["data"]["next_revision_base_plan_path"] == result["data"]["slide_plan_path"]


def test_ppt_master_plan_patch_insert_slide_after_accepts_multiple_slides():
    tool = CreatePptxWithPptMasterTool()

    page_plan = [
        {"slide": 1, "title": "封面", "layout": "cover"},
        {"slide": 2, "title": "原页面", "layout": "content"},
    ]
    patched = tool._apply_plan_patch(
        page_plan,
        {
            "insert_slide_after": [
                {
                    "after_slide": 1,
                    "slides": [
                        {"title": "新增一", "shapes": []},
                        {"title": "新增二", "shapes": []},
                    ],
                }
            ]
        },
    )

    assert [page["title"] for page in patched] == ["封面", "新增一", "新增二", "原页面"]
    assert [page["slide"] for page in patched] == [1, 2, 3, 4]
