from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pathlib import Path
from PIL import Image
import json
import pytest

import app.api.html_artifact_routes as html_artifact_routes
import app.tools.visualization.create_diagram_artifact.tool as diagram_tool_module
from app.services.html_artifact_service import HtmlArtifactService
from app.tools.visualization.create_diagram_artifact.drawio_writer import build_drawio_xml
from app.tools.visualization.create_diagram_artifact.tool import (
    REFERENCE_ROOT,
    diagram_design_reference_paths,
)
from app.tools.visualization.create_diagram_artifact.freeform_exporter import (
    export_freeform_diagram,
)
from app.tools.visualization.create_diagram_artifact.freeform_models import (
    normalize_freeform_diagram,
)
from app.tools.visualization.create_diagram_artifact.freeform_postprocessor import (
    postprocess_freeform_diagram,
)
from app.tools.visualization.create_diagram_artifact.tool import CreateDiagramArtifactTool


def _diagram_with_styles():
    return normalize_freeform_diagram(
        artifact_id="styled_arch",
        title="架构图",
        canvas={"width": 400, "height": 300, "background": "#ffffff"},
        shapes=[
            {
                "id": "visible",
                "type": "rectangle",
                "label": "可见节点",
                "x": 20,
                "y": 30,
                "width": 100,
                "height": 60,
                "style": "fill:#f3e5f5;stroke:#7b1fa2;stroke-width:2",
            },
            {
                "id": "hidden",
                "type": "rectangle",
                "label": "隐藏节点",
                "x": 20,
                "y": 30,
                "width": 100,
                "height": 60,
                "style": "fill:#ffffff;stroke:#424242;hidden:true",
            },
            {
                "id": "target",
                "type": "rectangle",
                "label": "目标节点",
                "x": 180,
                "y": 30,
                "width": 100,
                "height": 60,
                "style": "fill:#ffffff;stroke:#424242",
            },
        ],
        connectors=[
            {
                "id": "arrow",
                "from": "visible",
                "to": "target",
                "type": "arrow",
                "style": "stroke:#1976d2;stroke-width:3;end-arrow:block",
            }
        ],
        groups=[],
        output_formats=["drawio", "png"],
        diagram_intent="test",
    )


def test_drawio_writer_applies_input_style_and_omits_hidden_cells():
    xml = build_drawio_xml(_diagram_with_styles())

    assert "可见节点" in xml
    assert "隐藏节点" not in xml
    assert "fillColor=#f3e5f5" in xml
    assert "strokeColor=#7b1fa2" in xml
    assert "strokeWidth=2" in xml
    assert "strokeColor=#1976d2" in xml
    assert "strokeWidth=3" in xml


def test_freeform_preview_uses_downloadable_relative_drawio_link():
    html = CreateDiagramArtifactTool()._build_freeform_preview_html("架构图", "artifact_a")

    assert 'href="assets/diagram.drawio"' in html
    assert 'href="assets/diagram.drawio.svg"' in html
    assert 'href="/api/html-artifacts/artifact_a/assets/diagram.drawio"' not in html
    assert 'src="assets/diagram.drawio.svg"' in html
    assert "download" in html


def test_freeform_progressive_reference_paths_are_exposed_and_present():
    paths = diagram_design_reference_paths()

    assert paths["freeform_index"] == "create_diagram_artifact/references/freeform-index.md"
    assert paths["freeform_primitives"] == "create_diagram_artifact/references/freeform-primitives.md"
    assert paths["freeform_architecture"] == "create_diagram_artifact/references/freeform-architecture.md"
    assert paths["freeform_checklist"] == "create_diagram_artifact/references/freeform-checklist.md"

    for key in ("freeform_index", "freeform_primitives", "freeform_architecture", "freeform_checklist"):
        relative_path = paths[key].replace("create_diagram_artifact/references/", "")
        content = (REFERENCE_ROOT / relative_path).read_text(encoding="utf-8")
        assert "diagram_mode=\"freeform\"" in content
        assert "canvas/shapes/connectors/groups" in content

    index_content = (REFERENCE_ROOT / "freeform-index.md").read_text(encoding="utf-8")
    architecture_content = (REFERENCE_ROOT / "freeform-architecture.md").read_text(encoding="utf-8")
    checklist_content = (REFERENCE_ROOT / "freeform-checklist.md").read_text(encoding="utf-8")
    primitives_content = (REFERENCE_ROOT / "freeform-primitives.md").read_text(encoding="utf-8")
    assert "freeform-primitives.md" in index_content
    assert "freeform-primitives.md" in architecture_content
    assert "freeform-primitives.md" in checklist_content
    assert "shape.type" in primitives_content
    assert "connector.type" in primitives_content
    assert "布局原语" in primitives_content
    assert "## 架构软约束" in architecture_content
    assert "## 视觉设计理念" in architecture_content
    assert "## 架构取舍策略" in architecture_content


def test_create_diagram_tool_schema_requires_artifact_id_for_all_operations_without_required_title():
    schema = CreateDiagramArtifactTool().get_function_schema()
    properties = schema["parameters"]["properties"]

    assert properties["operation"]["enum"] == ["create", "patch", "validate", "render"]
    assert "output_formats" not in properties
    assert "style_pack" not in properties
    assert "base_plan_path" in properties
    assert "diagram_plan_path" in properties
    assert "diagram_patch" in properties
    assert "diagram_patch_path" in properties
    assert schema["parameters"].get("required", []) == ["artifact_id"]


def test_freeform_exporter_writes_filtered_drawio_and_readable_png(tmp_path):
    result = export_freeform_diagram(_diagram_with_styles(), tmp_path)

    drawio_xml = result.drawio_path.read_text(encoding="utf-8")
    assert "可见节点" in drawio_xml
    assert "隐藏节点" not in drawio_xml
    assert "fillColor=#f3e5f5" in drawio_xml
    assert result.preview_png_path.stat().st_size > 1000

    with Image.open(result.preview_png_path) as image:
        assert image.size == (400, 300)
        assert image.getbbox() is not None


def test_freeform_fallback_svg_suppresses_accidental_overlapping_duplicates(tmp_path):
    diagram = normalize_freeform_diagram(
        artifact_id="overlap_arch",
        title="重叠架构图",
        canvas={"width": 360, "height": 220, "background": "#ffffff"},
        shapes=[
            {
                "id": "primary",
                "type": "rectangle",
                "label": "主节点",
                "x": 40,
                "y": 60,
                "width": 140,
                "height": 80,
                "style": "fillColor=#fff2cc;strokeColor=#d6b656;strokeWidth=2;",
            },
            {
                "id": "duplicate",
                "type": "rectangle",
                "label": "重复节点",
                "x": 45,
                "y": 65,
                "width": 130,
                "height": 70,
                "style": "fillColor=#fff2cc;strokeColor=#d6b656;strokeWidth=2;",
            },
            {
                "id": "target",
                "type": "rectangle",
                "label": "目标节点",
                "x": 220,
                "y": 60,
                "width": 100,
                "height": 80,
                "style": "fillColor=#dae8fc;strokeColor=#6c8ebf;strokeWidth=2;",
            },
        ],
        connectors=[],
        groups=[],
        output_formats=["drawio", "png", "drawio_svg"],
        diagram_intent="architecture",
    )

    result = export_freeform_diagram(diagram, tmp_path)

    svg = result.preview_svg_path.read_text(encoding="utf-8")
    assert "主节点" in svg
    assert "目标节点" in svg
    assert "重复节点" not in svg
    assert "重复节点" in result.drawio_path.read_text(encoding="utf-8")


def test_freeform_exporter_honors_direct_drawio_style_fields(tmp_path):
    diagram = normalize_freeform_diagram(
        artifact_id="direct_style_arch",
        title="直接样式字段",
        canvas={"width": 420, "height": 240, "background": "#ffffff"},
        shapes=[
            {
                "id": "a",
                "type": "rectangle",
                "label": "应用节点",
                "x": 60,
                "y": 80,
                "width": 120,
                "height": 60,
                "fillColor": "#ffffff",
                "strokeColor": "#4CAF50",
                "strokeWidth": 2,
            }
        ],
        connectors=[],
        groups=[
            {
                "id": "layer_app",
                "label": "应用展示层",
                "x": 30,
                "y": 40,
                "width": 360,
                "height": 130,
                "fillColor": "#E8F5E9",
                "strokeColor": "#4CAF50",
                "strokeWidth": 2,
            }
        ],
        output_formats=["drawio", "png", "drawio_svg"],
        diagram_intent="architecture",
    )

    result = export_freeform_diagram(diagram, tmp_path)

    svg = result.preview_svg_path.read_text(encoding="utf-8")
    drawio_xml = result.drawio_path.read_text(encoding="utf-8")
    assert 'fill="#E8F5E9"' in svg
    assert 'stroke="#4CAF50"' in svg
    assert 'fillColor=#E8F5E9' in drawio_xml
    assert 'strokeColor=#4CAF50' in drawio_xml


def test_freeform_architecture_theme_inherits_container_palette_and_rounded_shapes(tmp_path):
    diagram = normalize_freeform_diagram(
        artifact_id="themed_arch",
        title="主题架构图",
        canvas={"width": 480, "height": 260, "background": "#ffffff"},
        shapes=[
            {
                "id": "a",
                "type": "rectangle",
                "label": "采集服务",
                "x": 80,
                "y": 90,
                "width": 120,
                "height": 54,
            },
            {
                "id": "b",
                "type": "rectangle",
                "label": "标准化服务",
                "x": 280,
                "y": 90,
                "width": 120,
                "height": 54,
            },
        ],
        connectors=[
            {"id": "edge", "from": "a", "to": "b", "type": "arrow"},
        ],
        groups=[
            {
                "id": "layer",
                "label": "数据联网层",
                "x": 40,
                "y": 50,
                "width": 400,
                "height": 130,
                "fillColor": "#EAF4FF",
                "strokeColor": "#1E88E5",
                "children": ["a", "b"],
            }
        ],
        output_formats=["drawio", "png", "drawio_svg"],
        diagram_intent="architecture",
    )

    result = export_freeform_diagram(diagram, tmp_path)

    drawio_xml = result.drawio_path.read_text(encoding="utf-8")
    svg = result.preview_svg_path.read_text(encoding="utf-8")
    assert "strokeColor=#1E88E5" in drawio_xml
    assert "rounded=1" in drawio_xml
    assert "dashed=1" in drawio_xml
    assert 'stroke="#1E88E5"' in svg
    assert 'rx="10"' in svg
    assert 'marker-end="url(#arrowhead)"' in svg
    assert 'data-connector-id="edge"' in svg
    assert '#2563eb' not in svg


def test_freeform_postprocessor_applies_fixed_business_style_without_overriding_explicit_styles():
    diagram = normalize_freeform_diagram(
        artifact_id="style_pack_arch",
        title="风格包",
        canvas={"width": 360, "height": 220, "background": "#ffffff"},
        shapes=[
            {
                "id": "defaulted",
                "type": "rectangle",
                "label": "默认节点",
                "x": 43,
                "y": 57,
                "width": 121,
                "height": 61,
            },
            {
                "id": "explicit",
                "type": "rectangle",
                "label": "显式节点",
                "x": 210,
                "y": 57,
                "width": 120,
                "height": 60,
                "fillColor": "#FFF2CC",
                "strokeColor": "#D6B656",
                "strokeWidth": 3,
            },
        ],
        connectors=[
            {"id": "edge", "from": "defaulted", "to": "explicit", "type": "arrow"}
        ],
        groups=[],
        output_formats=["drawio", "png", "drawio_svg"],
        diagram_intent="architecture",
    )

    result = postprocess_freeform_diagram(diagram, style_pack="research_clean")
    xml = build_drawio_xml(result.diagram)

    assert 'id="defaulted"' in xml
    assert "fillColor=#FFFFFF" in xml
    assert "strokeColor=#2F6F9F" in xml
    assert "fontSize=27" in xml
    assert "fontFamily=FZXiaoBiaoSong-B05S" in xml
    assert "align=center" in xml
    assert "verticalAlign=middle" in xml
    assert "fillColor=#FFF2CC" in xml
    assert "strokeColor=#D6B656" in xml
    assert "strokeWidth=3" in xml
    assert result.style_pack == "business_clean"
    assert "style_pack_applied" in result.quality_warnings
    assert any(action["action"] == "apply_style_pack" for action in result.actions)
    assert any(action["action"] == "scale_font_sizes" for action in result.actions)


def test_freeform_postprocessor_scales_agent_font_sizes_once_for_a4_readability():
    diagram = normalize_freeform_diagram(
        artifact_id="scaled_font_arch",
        title="字号放大",
        canvas={"width": 420, "height": 260, "background": "#ffffff"},
        shapes=[
            {
                "id": "node",
                "type": "rectangle",
                "label": "业务节点",
                "x": 60,
                "y": 80,
                "width": 120,
                "height": 60,
                "style": "fillColor=#D6EAF8;strokeColor=#2E86C1;fontSize=14",
            },
            {
                "id": "already_scaled",
                "type": "rectangle",
                "label": "已放大节点",
                "x": 230,
                "y": 80,
                "width": 120,
                "height": 60,
                "style": "fontSize=24;fillColor=#D5F5E3",
            },
        ],
        connectors=[
            {
                "id": "edge",
                "from": "node",
                "to": "already_scaled",
                "label": "调用",
                "style": "strokeWidth=2;fontSize=12",
            }
        ],
        groups=[
            {
                "id": "group",
                "label": "业务层",
                "children": ["node", "already_scaled"],
                "x": 30,
                "y": 40,
                "width": 360,
                "height": 140,
                "style": "fontSize=18;strokeWidth=2",
            }
        ],
        output_formats=["drawio", "png", "drawio_svg"],
        diagram_intent="architecture",
    )

    result = postprocess_freeform_diagram(diagram, style_pack="business_clean")
    xml = build_drawio_xml(result.diagram)

    assert "fontSize=21" in xml
    assert "fontSize=27" in xml
    assert "fontSize=18" in xml
    assert "fontSize=24" in xml
    assert any(action["action"] == "scale_font_sizes" for action in result.actions)


def test_freeform_postprocessor_expands_shape_width_before_wrapping_label_text():
    diagram = normalize_freeform_diagram(
        artifact_id="fit_label_arch",
        title="文字适配",
        canvas={"width": 360, "height": 220, "background": "#ffffff"},
        shapes=[
            {
                "id": "long_label",
                "type": "rectangle",
                "label": "智慧环保态势分析",
                "x": 40,
                "y": 40,
                "width": 100,
                "height": 50,
            },
            {
                "id": "short_label",
                "type": "rectangle",
                "label": "预警",
                "x": 200,
                "y": 40,
                "width": 100,
                "height": 50,
            },
        ],
        connectors=[],
        groups=[],
        output_formats=["drawio", "png", "drawio_svg"],
        diagram_intent="architecture",
    )

    result = postprocess_freeform_diagram(diagram, style_pack="business_clean")
    shape_by_id = {shape.id: shape for shape in result.diagram.shapes}

    assert shape_by_id["long_label"].width > 100
    assert shape_by_id["long_label"].x < 40
    assert shape_by_id["long_label"].height >= 50
    assert shape_by_id["short_label"].height >= 50
    assert any(action["action"] == "fit_shape_labels" for action in result.actions)


def test_freeform_postprocessor_expands_shape_height_after_width_limit_for_long_label():
    diagram = normalize_freeform_diagram(
        artifact_id="fit_long_label_arch",
        title="长文字适配",
        canvas={"width": 360, "height": 220, "background": "#ffffff"},
        shapes=[
            {
                "id": "long_label",
                "type": "rectangle",
                "label": "智慧环保综合态势分析与应急联动处置模块",
                "x": 40,
                "y": 40,
                "width": 100,
                "height": 30,
            },
        ],
        connectors=[],
        groups=[],
        output_formats=["drawio", "png", "drawio_svg"],
        diagram_intent="architecture",
    )

    result = postprocess_freeform_diagram(diagram, style_pack="business_clean")
    shape = result.diagram.shapes[0]

    assert shape.width > 100
    assert shape.height > 30
    assert shape.width % 10 == 0
    assert shape.height % 10 == 0
    assert "label_too_long" in result.quality_warnings


def test_drawio_writer_normalizes_safe_subscript_and_superscript_labels():
    diagram = normalize_freeform_diagram(
        artifact_id="rich_text_labels",
        title="上下标标签",
        canvas={"width": 420, "height": 220, "background": "#ffffff"},
        shapes=[
            {
                "id": "sensor",
                "type": "rectangle",
                "label": "SO2 / NO3- 浓度\nμg/m3 <script>alert(1)</script>",
                "x": 40,
                "y": 70,
                "width": 160,
                "height": 70,
            },
            {
                "id": "platform",
                "type": "rectangle",
                "label": "CO₂与PM2_5分析",
                "x": 250,
                "y": 70,
                "width": 130,
                "height": 70,
            },
        ],
        connectors=[
            {"id": "edge", "from": "sensor", "to": "platform", "label": "m3折算"}
        ],
        groups=[],
        output_formats=["drawio", "png", "drawio_svg"],
        diagram_intent="architecture",
    )

    xml = build_drawio_xml(diagram)

    assert "SO&lt;sub&gt;2&lt;/sub&gt;" in xml
    assert "NO&lt;sub&gt;3&lt;/sub&gt;&lt;sup&gt;-&lt;/sup&gt;" in xml
    assert "μg/m&lt;sup&gt;3&lt;/sup&gt;" in xml
    assert "CO&lt;sub&gt;2&lt;/sub&gt;" in xml
    assert "PM&lt;sub&gt;2.5&lt;/sub&gt;" in xml
    assert "m&lt;sup&gt;3&lt;/sup&gt;" in xml
    assert "script" not in xml.lower()


def test_freeform_fallback_svg_renders_mixed_subscript_and_superscript_labels(tmp_path):
    diagram = normalize_freeform_diagram(
        artifact_id="rich_text_svg",
        title="SVG上下标",
        canvas={"width": 420, "height": 220, "background": "#ffffff"},
        shapes=[
            {
                "id": "sensor",
                "type": "rectangle",
                "label": "SO2/NO3- μg/m3",
                "x": 40,
                "y": 70,
                "width": 160,
                "height": 70,
            },
        ],
        connectors=[],
        groups=[
            {
                "id": "layer",
                "label": "CO2监测层",
                "children": ["sensor"],
                "x": 20,
                "y": 30,
                "width": 380,
                "height": 150,
            }
        ],
        output_formats=["drawio", "png", "drawio_svg"],
        diagram_intent="architecture",
    )

    result = export_freeform_diagram(diagram, tmp_path)

    svg = result.preview_svg_path.read_text(encoding="utf-8")
    assert 'font-family="FZXiaoBiaoSong-B05S, Noto Sans CJK SC, Droid Sans Fallback, Arial, sans-serif"' in svg
    assert 'baseline-shift="sub"' in svg
    assert 'baseline-shift="super"' in svg
    assert ">SO<" in svg
    assert "NO" in svg
    assert "μg/m" in svg


def test_freeform_postprocessor_centers_geometric_group_children_without_children_list():
    diagram = normalize_freeform_diagram(
        artifact_id="geometric_center_arch",
        title="几何推断居中",
        canvas={"width": 800, "height": 280, "background": "#ffffff"},
        shapes=[
            {"id": "a", "type": "rectangle", "label": "模块A", "x": 40, "y": 100, "width": 100, "height": 50},
            {"id": "b", "type": "rectangle", "label": "模块B", "x": 160, "y": 100, "width": 100, "height": 50},
            {"id": "c", "type": "rectangle", "label": "模块C", "x": 280, "y": 100, "width": 100, "height": 50},
        ],
        groups=[
            {"id": "grp_app", "label": "应用层", "children": [], "x": 40, "y": 60, "width": 720, "height": 150},
        ],
        connectors=[],
        output_formats=["drawio", "png", "drawio_svg"],
        diagram_intent="architecture",
    )

    result = postprocess_freeform_diagram(
        diagram,
        options={"center_group_children": True, "apply_style_pack": False},
    )

    shape_by_id = {shape.id: shape for shape in result.diagram.shapes}
    assert shape_by_id["a"].x == 230
    assert shape_by_id["b"].x == 350
    assert shape_by_id["c"].x == 470
    assert any(action["action"] == "center_group_children" for action in result.actions)


def test_freeform_postprocessor_hard_layout_vertically_centers_group_children():
    diagram = normalize_freeform_diagram(
        artifact_id="vertical_center_arch",
        title="垂直居中",
        canvas={"width": 640, "height": 320, "background": "#ffffff"},
        shapes=[
            {"id": "a", "type": "rectangle", "label": "模块A", "x": 80, "y": 70, "width": 120, "height": 50},
            {"id": "b", "type": "rectangle", "label": "模块B", "x": 230, "y": 70, "width": 120, "height": 50},
            {"id": "c", "type": "rectangle", "label": "模块C", "x": 380, "y": 70, "width": 120, "height": 50},
        ],
        groups=[
            {"id": "layer", "label": "应用层", "children": ["a", "b", "c"], "x": 40, "y": 40, "width": 560, "height": 220},
        ],
        connectors=[],
        output_formats=["drawio", "png", "drawio_svg"],
        diagram_intent="architecture",
    )

    result = postprocess_freeform_diagram(
        diagram,
        options={"apply_style_pack": False},
    )
    shape_by_id = {shape.id: shape for shape in result.diagram.shapes}

    assert shape_by_id["a"].y == 125
    assert shape_by_id["b"].y == 125
    assert shape_by_id["c"].y == 125
    assert any(action["action"] == "layout_group_children" for action in result.actions)


def test_freeform_postprocessor_hard_layout_removes_group_child_overlap():
    diagram = normalize_freeform_diagram(
        artifact_id="child_overlap_arch",
        title="子模块叠加",
        canvas={"width": 640, "height": 320, "background": "#ffffff"},
        shapes=[
            {"id": "a", "type": "rectangle", "label": "模块A", "x": 80, "y": 80, "width": 140, "height": 60},
            {"id": "b", "type": "rectangle", "label": "模块B", "x": 90, "y": 85, "width": 140, "height": 60},
            {"id": "c", "type": "rectangle", "label": "模块C", "x": 100, "y": 90, "width": 140, "height": 60},
        ],
        groups=[
            {"id": "layer", "label": "应用层", "children": ["a", "b", "c"], "x": 40, "y": 40, "width": 560, "height": 220},
        ],
        connectors=[],
        output_formats=["drawio", "png", "drawio_svg"],
        diagram_intent="architecture",
    )

    result = postprocess_freeform_diagram(
        diagram,
        options={"apply_style_pack": False},
    )
    children = [shape for shape in result.diagram.shapes if shape.id in {"a", "b", "c"}]

    for index, left in enumerate(children):
        for right in children[index + 1:]:
            assert left.x + left.width + 20 <= right.x or right.x + right.width + 20 <= left.x
    assert "overlap_detected" not in result.quality_warnings


def test_freeform_postprocessor_hard_layout_expands_container_and_canvas_for_children():
    diagram = normalize_freeform_diagram(
        artifact_id="expand_container_arch",
        title="容器扩展",
        canvas={"width": 360, "height": 180, "background": "#ffffff"},
        shapes=[
            {"id": "a", "type": "rectangle", "label": "模块A", "x": 50, "y": 60, "width": 140, "height": 60},
            {"id": "b", "type": "rectangle", "label": "模块B", "x": 60, "y": 70, "width": 140, "height": 60},
            {"id": "c", "type": "rectangle", "label": "模块C", "x": 70, "y": 80, "width": 140, "height": 60},
            {"id": "d", "type": "rectangle", "label": "模块D", "x": 80, "y": 90, "width": 140, "height": 60},
        ],
        groups=[
            {"id": "layer", "label": "应用层", "children": ["a", "b", "c", "d"], "x": 30, "y": 30, "width": 230, "height": 120},
        ],
        connectors=[],
        output_formats=["drawio", "png", "drawio_svg"],
        diagram_intent="architecture",
    )

    result = postprocess_freeform_diagram(
        diagram,
        options={"apply_style_pack": False},
    )
    group = result.diagram.groups[0]
    shape_by_id = {shape.id: shape for shape in result.diagram.shapes}

    assert group.width > 230
    assert group.height > 120
    for shape_id in ("a", "b", "c", "d"):
        shape = shape_by_id[shape_id]
        assert group.x <= shape.x
        assert shape.x + shape.width <= group.x + group.width
        assert group.y <= shape.y
        assert shape.y + shape.height <= group.y + group.height
    assert result.diagram.canvas.width >= group.x + group.width + 40
    assert result.diagram.canvas.height >= group.y + group.height + 40
    assert any(action["action"] == "layout_group_children" for action in result.actions)


def test_freeform_postprocessor_hard_layout_handles_container_shape_children():
    diagram = normalize_freeform_diagram(
        artifact_id="container_shape_arch",
        title="容器节点",
        canvas={"width": 420, "height": 220, "background": "#ffffff"},
        shapes=[
            {
                "id": "domain",
                "type": "container",
                "label": "业务域",
                "x": 30,
                "y": 30,
                "width": 230,
                "height": 120,
                "children": ["a", "b", "c"],
            },
            {"id": "a", "type": "rectangle", "label": "模块A", "x": 50, "y": 60, "width": 140, "height": 60},
            {"id": "b", "type": "rectangle", "label": "模块B", "x": 60, "y": 70, "width": 140, "height": 60},
            {"id": "c", "type": "rectangle", "label": "模块C", "x": 70, "y": 80, "width": 140, "height": 60},
        ],
        groups=[],
        connectors=[],
        output_formats=["drawio", "png", "drawio_svg"],
        diagram_intent="architecture",
    )

    result = postprocess_freeform_diagram(
        diagram,
        options={"apply_style_pack": False},
    )
    shape_by_id = {shape.id: shape for shape in result.diagram.shapes}
    container = shape_by_id["domain"]
    children = [shape_by_id[shape_id] for shape_id in ("a", "b", "c")]

    assert container.width > 230
    assert container.height > 120
    for child in children:
        assert container.x <= child.x
        assert child.x + child.width <= container.x + container.width
        assert container.y <= child.y
        assert child.y + child.height <= container.y + container.height
    for left, right in zip(sorted(children, key=lambda item: item.x), sorted(children, key=lambda item: item.x)[1:]):
        assert left.x + left.width + 20 <= right.x
    assert any(action["action"] == "layout_group_children" for action in result.actions)


def test_freeform_postprocessor_snaps_grid_expands_canvas_and_warns():
    diagram = normalize_freeform_diagram(
        artifact_id="quality_arch",
        title="质量修正",
        canvas={"width": 260, "height": 180, "background": "#ffffff"},
        shapes=[
            {
                "id": "a",
                "type": "rectangle",
                "label": "很长很长很长很长很长很长的节点标签",
                "x": 43,
                "y": 57,
                "width": 121,
                "height": 61,
            },
            {
                "id": "b",
                "type": "rectangle",
                "label": "重叠节点",
                "x": 47,
                "y": 60,
                "width": 120,
                "height": 60,
            },
            {
                "id": "target",
                "type": "rectangle",
                "label": "越界目标",
                "x": 241,
                "y": 171,
                "width": 120,
                "height": 60,
            },
        ],
        connectors=[
            {"id": "ab", "from": "a", "to": "target"},
            {"id": "bb", "from": "b", "to": "target"},
            {"id": "aa", "from": "a", "to": "target"},
            {"id": "ba", "from": "b", "to": "target"},
        ],
        groups=[],
        output_formats=["drawio", "png", "drawio_svg"],
        diagram_intent="architecture",
    )

    result = postprocess_freeform_diagram(diagram, style_pack="business_clean")
    processed = result.diagram
    shape_by_id = {shape.id: shape for shape in processed.shapes}

    assert shape_by_id["a"].x >= 0
    assert shape_by_id["a"].x % 10 == 0
    assert shape_by_id["a"].y == 60
    assert shape_by_id["a"].width >= 120
    assert shape_by_id["a"].width % 10 == 0
    assert shape_by_id["target"].x >= 0
    assert shape_by_id["target"].x % 10 == 0
    assert processed.canvas.width >= 400
    assert processed.canvas.height >= 260
    assert "canvas_expanded" in result.quality_warnings
    assert "overlap_detected" in result.quality_warnings
    assert "high_fan_in" in result.quality_warnings
    assert "label_too_long" in result.quality_warnings


def test_freeform_fallback_svg_connectors_use_shape_edge_ports(tmp_path):
    diagram = normalize_freeform_diagram(
        artifact_id="edge_ports",
        title="边缘端口",
        canvas={"width": 420, "height": 200, "background": "#ffffff"},
        shapes=[
            {
                "id": "left",
                "type": "rectangle",
                "label": "左节点",
                "x": 60,
                "y": 70,
                "width": 100,
                "height": 50,
                "strokeColor": "#EF6C00",
            },
            {
                "id": "right",
                "type": "rectangle",
                "label": "右节点",
                "x": 260,
                "y": 70,
                "width": 100,
                "height": 50,
                "strokeColor": "#EF6C00",
            },
        ],
        connectors=[{"id": "edge", "from": "left", "to": "right", "type": "arrow"}],
        groups=[],
        output_formats=["drawio", "png", "drawio_svg"],
        diagram_intent="architecture",
    )

    result = export_freeform_diagram(diagram, tmp_path)

    svg = result.preview_svg_path.read_text(encoding="utf-8")
    assert 'x1="160" y1="95" x2="260" y2="95"' in svg
    assert 'x1="110" y1="95" x2="310" y2="95"' not in svg


def test_freeform_normalizer_generates_stable_ids_for_connectors_without_id(tmp_path):
    diagram = normalize_freeform_diagram(
        artifact_id="connector_id_fallback",
        title="缺省连线ID",
        canvas={"width": 360, "height": 180, "background": "#ffffff"},
        shapes=[
            {
                "id": "source",
                "type": "rounded_rect",
                "label": "源节点",
                "x": 40,
                "y": 60,
                "width": 100,
                "height": 50,
            },
            {
                "id": "target",
                "type": "rounded_rect",
                "label": "目标节点",
                "x": 220,
                "y": 60,
                "width": 100,
                "height": 50,
            },
        ],
        connectors=[
            {
                "from": "source",
                "to": "target",
                "style": "dashed",
                "strokeColor": "#999999",
                "label": "数据上报",
            }
        ],
        groups=[],
        output_formats=["drawio", "png", "drawio_svg"],
        diagram_intent="architecture",
    )

    result = export_freeform_diagram(diagram, tmp_path)

    drawio_xml = result.drawio_path.read_text(encoding="utf-8")
    svg = result.preview_svg_path.read_text(encoding="utf-8")
    assert 'id="edge_1"' in drawio_xml
    assert 'data-connector-id="edge_1"' in svg
    assert "数据上报" in drawio_xml


def test_freeform_normalizer_avoids_generated_connector_id_collisions():
    diagram = normalize_freeform_diagram(
        artifact_id="connector_id_collision",
        title="缺省连线ID冲突",
        canvas={"width": 360, "height": 180, "background": "#ffffff"},
        shapes=[
            {
                "id": "edge_1",
                "type": "rounded_rect",
                "label": "源节点",
                "x": 40,
                "y": 60,
                "width": 100,
                "height": 50,
            },
            {
                "id": "target",
                "type": "rounded_rect",
                "label": "目标节点",
                "x": 220,
                "y": 60,
                "width": 100,
                "height": 50,
            },
        ],
        connectors=[
            {"from": "edge_1", "to": "target"},
            {"id": "edge_2", "from": "target", "to": "edge_1"},
            {"from": "edge_1", "to": "target"},
        ],
        groups=[],
        output_formats=["drawio", "png", "drawio_svg"],
        diagram_intent="architecture",
    )

    assert [connector.id for connector in diagram.connectors] == ["edge_3", "edge_2", "edge_4"]


def test_freeform_fallback_svg_bundles_high_fan_in_connectors(tmp_path):
    shapes = [
        {
            "id": "target",
            "type": "rectangle",
            "label": "数据采集",
            "x": 160,
            "y": 60,
            "width": 120,
            "height": 60,
            "fillColor": "#ffffff",
            "strokeColor": "#9C27B0",
        }
    ]
    connectors = []
    for index in range(6):
        shapes.append(
            {
                "id": f"sensor_{index}",
                "type": "rectangle",
                "label": f"设备{index}",
                "x": 40 + index * 70,
                "y": 180,
                "width": 60,
                "height": 40,
                "fillColor": "#ffffff",
                "strokeColor": "#607D8B",
            }
        )
        connectors.append(
            {
                "id": f"edge_{index}",
                "from": f"sensor_{index}",
                "to": "target",
                "type": "solid",
                "strokeColor": "#607D8B",
            }
        )

    diagram = normalize_freeform_diagram(
        artifact_id="fanin_arch",
        title="高扇入架构图",
        canvas={"width": 520, "height": 280, "background": "#ffffff"},
        shapes=shapes,
        connectors=connectors,
        groups=[],
        output_formats=["drawio", "png", "drawio_svg"],
        diagram_intent="architecture",
    )

    result = export_freeform_diagram(diagram, tmp_path)

    svg = result.preview_svg_path.read_text(encoding="utf-8")
    assert 'data-connector-bundle="target"' in svg
    assert svg.count('data-connector-id="edge_') == 0


def test_freeform_fallback_svg_routes_individual_connectors_orthogonally(tmp_path):
    diagram = normalize_freeform_diagram(
        artifact_id="orthogonal_arch",
        title="正交连线",
        canvas={"width": 320, "height": 260, "background": "#ffffff"},
        shapes=[
            {
                "id": "a",
                "type": "rectangle",
                "label": "上游",
                "x": 40,
                "y": 40,
                "width": 80,
                "height": 50,
                "strokeColor": "#2196F3",
            },
            {
                "id": "b",
                "type": "rectangle",
                "label": "下游",
                "x": 200,
                "y": 170,
                "width": 80,
                "height": 50,
                "strokeColor": "#4CAF50",
            },
        ],
        connectors=[
            {
                "id": "ab",
                "from": "a",
                "to": "b",
                "type": "solid",
                "strokeColor": "#607D8B",
            }
        ],
        groups=[],
        output_formats=["drawio", "png", "drawio_svg"],
        diagram_intent="architecture",
    )

    result = export_freeform_diagram(diagram, tmp_path)

    svg = result.preview_svg_path.read_text(encoding="utf-8")
    assert 'data-connector-id="ab"' in svg
    assert "<polyline" in svg
    assert '<line data-connector-id="ab"' not in svg


def test_html_artifact_asset_route_serves_drawio_with_filename(tmp_path, monkeypatch):
    artifact_root = tmp_path / "html_artifacts"
    artifact_dir = artifact_root / "artifact_a"
    assets_dir = artifact_dir / "assets"
    assets_dir.mkdir(parents=True)
    (artifact_dir / "index.html").write_text("<!doctype html>", encoding="utf-8")
    (assets_dir / "diagram.drawio").write_text("<mxfile></mxfile>", encoding="utf-8")

    monkeypatch.setattr(
        html_artifact_routes,
        "html_artifact_service",
        HtmlArtifactService(root=artifact_root),
    )

    app = FastAPI()
    app.include_router(html_artifact_routes.router)
    response = TestClient(app).get("/api/html-artifacts/artifact_a/assets/diagram.drawio")

    assert response.status_code == 200
    assert response.content == b"<mxfile></mxfile>"
    assert "diagram.drawio" in response.headers["content-disposition"]


@pytest.mark.asyncio
async def test_create_diagram_tool_execute_freeform_creates_downloadable_artifacts(
    tmp_path,
    monkeypatch,
):
    artifact_root = tmp_path / "html_artifacts"
    monkeypatch.setattr(
        diagram_tool_module,
        "html_artifact_service",
        HtmlArtifactService(root=artifact_root),
    )

    result = await CreateDiagramArtifactTool().execute(
        artifact_id="tool_e2e",
        title="工具端到端",
        diagram_mode="freeform",
        canvas={"width": 400, "height": 300, "background": "#ffffff"},
        shapes=[
            {
                "id": "a",
                "type": "rectangle",
                "label": "节点A",
                "x": 40,
                "y": 40,
                "width": 100,
                "height": 60,
                "style": "fill:#ffffff;stroke:#424242",
            },
            {
                "id": "hidden",
                "type": "rectangle",
                "label": "隐藏节点",
                "x": 40,
                "y": 40,
                "width": 100,
                "height": 60,
                "style": "fill:#ffffff;stroke:#424242;hidden:true",
            },
            {
                "id": "b",
                "type": "rectangle",
                "label": "节点B",
                "x": 220,
                "y": 40,
                "width": 100,
                "height": 60,
                "style": "fill:#f3e5f5;stroke:#7b1fa2;stroke-width:2",
            },
        ],
        connectors=[
            {
                "id": "ab",
                "from": "a",
                "to": "b",
                "type": "arrow",
                "style": "stroke:#1976d2;stroke-width:3;end-arrow:block",
            }
        ],
        output_formats=["drawio", "png", "drawio_svg"],
    )

    assert result["success"] is True
    data = result["data"]
    drawio_path = artifact_root / "tool_e2e" / "assets" / "diagram.drawio"
    png_path = artifact_root / "tool_e2e" / "assets" / "diagram.png"
    svg_path = artifact_root / "tool_e2e" / "assets" / "diagram.drawio.svg"

    assert not (artifact_root / "tool_e2e" / "index.html").exists()
    assert drawio_path.exists()
    assert png_path.exists()
    assert svg_path.exists()
    assert "visuals" not in result
    assert result["file_type"] == "drawio"
    assert result["file_path"] == str(drawio_path)
    assert result.get("html_preview") is None
    assert data.get("html_preview") is None
    assert data.get("download_url") is None
    assert data.get("share_endpoint") is None
    assert data["file_type"] == "drawio"
    assert data["file_path"] == str(drawio_path)
    assert data["preview_svg_path"] == str(svg_path)
    assert data["preview_svg_url"] == "/api/html-artifacts/tool_e2e/assets/diagram.drawio.svg"
    assert data["svg_preview"] == {
        "svg_path": str(svg_path),
        "svg_url": "/api/html-artifacts/tool_e2e/assets/diagram.drawio.svg",
        "file_type": "drawio_svg",
        "format": "drawio_svg",
    }
    assert data["visuals"][0]["format"] == "svg"
    assert data["visuals"][0]["image_url"] == "/api/html-artifacts/tool_e2e/assets/diagram.drawio.svg"
    assert data["drawio_url"] == "/api/html-artifacts/tool_e2e/assets/diagram.drawio"
    assert result["artifact"]["format"] == "drawio"
    assert result["artifact"]["file_path"] == str(drawio_path)
    assert any(file["format"] == "drawio" for file in data["related_files"])
    assert any(file["format"] == "drawio_svg" for file in data["related_files"])
    assert "隐藏节点" not in drawio_path.read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_create_diagram_tool_freeform_writes_iterative_plan_contract(
    tmp_path,
    monkeypatch,
):
    artifact_root = tmp_path / "html_artifacts"
    monkeypatch.setattr(
        diagram_tool_module,
        "html_artifact_service",
        HtmlArtifactService(root=artifact_root),
    )

    result = await CreateDiagramArtifactTool().execute(
        artifact_id="iterative_contract",
        title="迭代图表",
        diagram_mode="freeform",
        diagram_intent="architecture",
        canvas={"width": 420, "height": 260, "background": "#ffffff"},
        shapes=[
            {"id": "a", "type": "rectangle", "label": "节点A", "x": 40, "y": 60, "width": 120, "height": 60},
            {"id": "b", "type": "rectangle", "label": "节点B", "x": 240, "y": 60, "width": 120, "height": 60},
        ],
        connectors=[{"id": "ab", "from": "a", "to": "b"}],
        output_formats=["drawio", "png", "drawio_svg"],
    )

    assert result["success"] is True
    data = result["data"]
    plan_path = Path(data["diagram_plan_path"])
    assert plan_path.name == "diagram_plan.v1.json"
    assert plan_path.exists()
    assert data["next_revision_base_plan_path"] == str(plan_path)
    assert Path(data["design_spec_path"]).exists()
    assert Path(data["qa_report_path"]).exists()
    assert data["qa_status"] in {"passed", "needs_revision"}
    assert data["quality_gate"]["status"] in {"passed", "needs_revision"}
    assert data["drawio_path"].endswith("diagram.drawio")
    assert data["preview_svg_path"].endswith("diagram.drawio.svg")
    plan = plan_path.read_text(encoding="utf-8")
    assert '"diagram_mode": "freeform"' in plan
    assert '"artifact_id": "iterative_contract"' in plan


@pytest.mark.asyncio
async def test_create_diagram_tool_patch_updates_plan_and_exports_drawio_svg(
    tmp_path,
    monkeypatch,
):
    artifact_root = tmp_path / "html_artifacts"
    monkeypatch.setattr(
        diagram_tool_module,
        "html_artifact_service",
        HtmlArtifactService(root=artifact_root),
    )
    tool = CreateDiagramArtifactTool()
    base = await tool.execute(
        artifact_id="patch_contract",
        title="补丁图表",
        diagram_mode="freeform",
        diagram_intent="architecture",
        canvas={"width": 420, "height": 260, "background": "#ffffff"},
        shapes=[
            {"id": "a", "type": "rectangle", "label": "节点A", "x": 40, "y": 60, "width": 120, "height": 60},
            {"id": "b", "type": "rectangle", "label": "节点B", "x": 240, "y": 60, "width": 120, "height": 60},
        ],
        connectors=[{"id": "ab", "from": "a", "to": "b"}],
        output_formats=["drawio", "png", "drawio_svg"],
    )

    result = await tool.execute(
        operation="patch",
        artifact_id="patch_contract",
        base_plan_path=base["data"]["diagram_plan_path"],
        diagram_patch={
            "replace_shapes": [
                {"id": "a", "type": "database", "label": "更新节点", "x": 40, "y": 60, "width": 120, "height": 60}
            ]
        },
        output_formats=["drawio", "png", "drawio_svg"],
    )

    assert result["success"] is True
    data = result["data"]
    assert data["operation"] == "patch"
    assert Path(data["diagram_plan_path"]).name == "diagram_plan.v2.json"
    assert Path(data["preview_svg_path"]).exists()
    drawio_text = Path(data["drawio_path"]).read_text(encoding="utf-8")
    assert "更新节点" in drawio_text
    assert "shape=cylinder" in drawio_text


@pytest.mark.asyncio
async def test_create_diagram_tool_validate_reports_architecture_quality_without_export(
    tmp_path,
    monkeypatch,
):
    artifact_root = tmp_path / "html_artifacts"
    monkeypatch.setattr(
        diagram_tool_module,
        "html_artifact_service",
        HtmlArtifactService(root=artifact_root),
    )

    result = await CreateDiagramArtifactTool().execute(
        operation="validate",
        artifact_id="validate_contract",
        title="待验证架构",
        diagram_mode="freeform",
        diagram_intent="architecture",
        canvas={"width": 800, "height": 520, "background": "#ffffff"},
        shapes=[
            {"id": "layer", "type": "container", "label": "业务层", "x": 30, "y": 30, "width": 720, "height": 160},
            {"id": "a", "type": "rectangle", "label": "模块A", "x": 70, "y": 80, "width": 100, "height": 50},
            {"id": "b", "type": "rectangle", "label": "模块B", "x": 210, "y": 80, "width": 100, "height": 50},
            {"id": "c", "type": "rectangle", "label": "模块C", "x": 350, "y": 80, "width": 100, "height": 50},
            {"id": "d", "type": "rectangle", "label": "模块D", "x": 490, "y": 80, "width": 100, "height": 50},
            {"id": "target", "type": "rectangle", "label": "数据采集", "x": 350, "y": 300, "width": 120, "height": 60},
            {"id": "s1", "type": "rectangle", "label": "设备1", "x": 80, "y": 420, "width": 80, "height": 40},
            {"id": "s2", "type": "rectangle", "label": "设备2", "x": 200, "y": 420, "width": 80, "height": 40},
            {"id": "s3", "type": "rectangle", "label": "设备3", "x": 320, "y": 420, "width": 80, "height": 40},
            {"id": "s4", "type": "rectangle", "label": "设备4", "x": 440, "y": 420, "width": 80, "height": 40},
        ],
        groups=[{"id": "business_layer", "label": "业务层", "children": ["a", "b", "c", "d"], "x": 30, "y": 30, "width": 720, "height": 160}],
        connectors=[
            {"id": "ab", "from": "a", "to": "b"},
            {"id": "bc", "from": "b", "to": "c"},
            {"id": "cd", "from": "c", "to": "d"},
            {"id": "s1t", "from": "s1", "to": "target"},
            {"id": "s2t", "from": "s2", "to": "target"},
            {"id": "s3t", "from": "s3", "to": "target"},
            {"id": "s4t", "from": "s4", "to": "target"},
        ],
        output_formats=["drawio", "png", "drawio_svg"],
    )

    assert result["success"] is True
    data = result["data"]
    assert data["operation"] == "validate"
    assert data["qa_status"] == "needs_revision"
    issue_codes = {issue["code"] for issue in data["quality_gate"]["issues"]}
    assert "high_fan_in" in issue_codes
    assert "layer_internal_long_chain" in issue_codes
    assert "architecture_shape_level_connectors" in issue_codes
    assert data["revision_tasks"]
    assert data.get("drawio_path") is None
    assert not (artifact_root / "validate_contract" / "assets" / "diagram.drawio").exists()


@pytest.mark.asyncio
async def test_create_diagram_tool_blocks_architecture_shape_level_delivery(
    tmp_path,
    monkeypatch,
):
    artifact_root = tmp_path / "html_artifacts"
    monkeypatch.setattr(
        diagram_tool_module,
        "html_artifact_service",
        HtmlArtifactService(root=artifact_root),
    )

    result = await CreateDiagramArtifactTool().execute(
        artifact_id="blocked_arch",
        title="节点级连线架构",
        diagram_mode="freeform",
        diagram_intent="architecture",
        canvas={"width": 720, "height": 420, "background": "#ffffff"},
        shapes=[
            {"id": "layer_a", "type": "container", "label": "感知层", "x": 40, "y": 240, "width": 640, "height": 120},
            {"id": "layer_b", "type": "container", "label": "平台层", "x": 40, "y": 80, "width": 640, "height": 120},
            {"id": "sensor", "type": "rectangle", "label": "监测设备", "x": 100, "y": 280, "width": 120, "height": 50},
            {"id": "gateway", "type": "rectangle", "label": "接入网关", "x": 300, "y": 280, "width": 120, "height": 50},
            {"id": "platform", "type": "rectangle", "label": "分析平台", "x": 300, "y": 120, "width": 120, "height": 50},
        ],
        groups=[
            {"id": "grp_perception", "label": "感知层", "children": ["sensor", "gateway"], "x": 40, "y": 240, "width": 640, "height": 120},
            {"id": "grp_platform", "label": "平台层", "children": ["platform"], "x": 40, "y": 80, "width": 640, "height": 120},
        ],
        connectors=[
            {"id": "sensor_gateway", "from": "sensor", "to": "gateway"},
            {"id": "gateway_platform", "from": "gateway", "to": "platform"},
        ],
        output_formats=["drawio", "png", "drawio_svg"],
    )

    assert result["success"] is True
    data = result["data"]
    assert data["qa_status"] == "blocked"
    assert data["quality_gate"]["status"] == "blocked"
    assert data["delivery_blocked"] is True
    assert data["drawio_path"] is None
    assert not (artifact_root / "blocked_arch" / "assets" / "diagram.drawio").exists()


@pytest.mark.asyncio
async def test_create_diagram_tool_centers_group_children_when_requested(
    tmp_path,
    monkeypatch,
):
    artifact_root = tmp_path / "html_artifacts"
    monkeypatch.setattr(
        diagram_tool_module,
        "html_artifact_service",
        HtmlArtifactService(root=artifact_root),
    )

    result = await CreateDiagramArtifactTool().execute(
        artifact_id="centered_arch",
        title="居中架构",
        diagram_mode="freeform",
        diagram_intent="architecture",
        postprocess={"enabled": True, "center_group_children": True},
        canvas={"width": 800, "height": 360, "background": "#ffffff"},
        shapes=[
            {"id": "a", "type": "rectangle", "label": "模块A", "x": 40, "y": 100, "width": 100, "height": 50},
            {"id": "b", "type": "rectangle", "label": "模块B", "x": 160, "y": 100, "width": 100, "height": 50},
            {"id": "c", "type": "rectangle", "label": "模块C", "x": 280, "y": 100, "width": 100, "height": 50},
        ],
        groups=[
            {"id": "grp_app", "label": "应用层", "children": ["a", "b", "c"], "x": 40, "y": 60, "width": 720, "height": 150},
        ],
        connectors=[],
        output_formats=["drawio", "png", "drawio_svg"],
    )

    assert result["success"] is True
    plan = json.loads(Path(result["data"]["diagram_plan_path"]).read_text(encoding="utf-8"))
    shapes = sorted(plan["shapes"], key=lambda item: item["x"])
    group = plan["groups"][0]
    row_width = sum(shape["width"] for shape in shapes) + 20 * (len(shapes) - 1)
    assert shapes[0]["x"] == group["x"] + round((group["width"] - row_width) / 2 / 10) * 10
    assert any(
        action["action"] == "center_group_children"
        for action in result["metadata"]["postprocess_actions"]
    )


@pytest.mark.asyncio
async def test_create_diagram_tool_centers_architecture_group_children_by_default(
    tmp_path,
    monkeypatch,
):
    artifact_root = tmp_path / "html_artifacts"
    monkeypatch.setattr(
        diagram_tool_module,
        "html_artifact_service",
        HtmlArtifactService(root=artifact_root),
    )

    result = await CreateDiagramArtifactTool().execute(
        artifact_id="auto_centered_arch",
        title="默认居中架构",
        diagram_mode="freeform",
        diagram_intent="architecture",
        canvas={"width": 800, "height": 360, "background": "#ffffff"},
        shapes=[
            {"id": "a", "type": "rectangle", "label": "模块A", "x": 40, "y": 100, "width": 100, "height": 50},
            {"id": "b", "type": "rectangle", "label": "模块B", "x": 160, "y": 100, "width": 100, "height": 50},
            {"id": "c", "type": "rectangle", "label": "模块C", "x": 280, "y": 100, "width": 100, "height": 50},
        ],
        groups=[
            {"id": "grp_app", "label": "应用层", "children": ["a", "b", "c"], "x": 40, "y": 60, "width": 720, "height": 150},
        ],
        connectors=[],
        output_formats=["drawio", "png", "drawio_svg"],
    )

    assert result["success"] is True
    plan = json.loads(Path(result["data"]["diagram_plan_path"]).read_text(encoding="utf-8"))
    shapes = sorted(plan["shapes"], key=lambda item: item["x"])
    group = plan["groups"][0]
    row_width = sum(shape["width"] for shape in shapes) + 20 * (len(shapes) - 1)
    assert shapes[0]["x"] == group["x"] + round((group["width"] - row_width) / 2 / 10) * 10
    assert any(
        action["action"] == "center_group_children"
        for action in result["metadata"]["postprocess_actions"]
    )


@pytest.mark.asyncio
async def test_create_diagram_tool_can_disable_architecture_group_centering(
    tmp_path,
    monkeypatch,
):
    artifact_root = tmp_path / "html_artifacts"
    monkeypatch.setattr(
        diagram_tool_module,
        "html_artifact_service",
        HtmlArtifactService(root=artifact_root),
    )

    result = await CreateDiagramArtifactTool().execute(
        artifact_id="manual_position_arch",
        title="手动布局架构",
        diagram_mode="freeform",
        diagram_intent="architecture",
        postprocess={"center_group_children": False},
        canvas={"width": 800, "height": 360, "background": "#ffffff"},
        shapes=[
            {"id": "a", "type": "rectangle", "label": "模块A", "x": 40, "y": 100, "width": 100, "height": 50},
            {"id": "b", "type": "rectangle", "label": "模块B", "x": 160, "y": 100, "width": 100, "height": 50},
            {"id": "c", "type": "rectangle", "label": "模块C", "x": 280, "y": 100, "width": 100, "height": 50},
        ],
        groups=[
            {"id": "grp_app", "label": "应用层", "children": ["a", "b", "c"], "x": 40, "y": 60, "width": 720, "height": 150},
        ],
        connectors=[],
        output_formats=["drawio", "png", "drawio_svg"],
    )

    assert result["success"] is True
    plan = json.loads(Path(result["data"]["diagram_plan_path"]).read_text(encoding="utf-8"))
    shapes = sorted(plan["shapes"], key=lambda item: item["id"])
    for left, right in zip(sorted(shapes, key=lambda item: item["x"]), sorted(shapes, key=lambda item: item["x"])[1:]):
        assert left["x"] + left["width"] + 20 <= right["x"]
    assert not any(
        action["action"] == "center_group_children"
        for action in result["metadata"]["postprocess_actions"]
    )
    assert any(
        action["action"] == "layout_group_children"
        for action in result["metadata"]["postprocess_actions"]
    )


@pytest.mark.asyncio
async def test_create_diagram_tool_render_refreshes_existing_plan_exports_drawio_svg(
    tmp_path,
    monkeypatch,
):
    artifact_root = tmp_path / "html_artifacts"
    monkeypatch.setattr(
        diagram_tool_module,
        "html_artifact_service",
        HtmlArtifactService(root=artifact_root),
    )
    tool = CreateDiagramArtifactTool()
    base = await tool.execute(
        artifact_id="render_contract",
        title="渲染图表",
        diagram_mode="freeform",
        diagram_intent="architecture",
        canvas={"width": 420, "height": 260, "background": "#ffffff"},
        shapes=[
            {"id": "db", "type": "database", "label": "业务库", "x": 60, "y": 80, "width": 120, "height": 70},
            {"id": "app", "type": "rectangle", "label": "应用服务", "x": 240, "y": 80, "width": 120, "height": 60},
        ],
        connectors=[{"id": "edge", "from": "app", "to": "db"}],
        output_formats=["drawio", "png", "drawio_svg"],
    )

    result = await tool.execute(
        operation="render",
        artifact_id="render_contract",
        base_plan_path=base["data"]["diagram_plan_path"],
    )

    assert result["success"] is True
    data = result["data"]
    assert data["operation"] == "render"
    assert Path(data["drawio_path"]).exists()
    assert Path(data["preview_svg_path"]).exists()
    assert "业务库" in Path(data["drawio_path"]).read_text(encoding="utf-8")
    assert Path(data["diagram_plan_path"]).exists()


@pytest.mark.asyncio
async def test_create_diagram_tool_execute_freeform_applies_postprocess_metadata(
    tmp_path,
    monkeypatch,
):
    artifact_root = tmp_path / "html_artifacts"
    monkeypatch.setattr(
        diagram_tool_module,
        "html_artifact_service",
        HtmlArtifactService(root=artifact_root),
    )

    result = await CreateDiagramArtifactTool().execute(
        artifact_id="tool_quality",
        title="质量后处理",
        diagram_mode="freeform",
        postprocess={"enabled": True, "snap_to_grid": True, "expand_canvas": True},
        canvas={"width": 240, "height": 160, "background": "#ffffff"},
        shapes=[
            {
                "id": "a",
                "type": "rectangle",
                "label": "节点A",
                "x": 43,
                "y": 57,
                "width": 121,
                "height": 61,
            },
            {
                "id": "target",
                "type": "rectangle",
                "label": "越界目标",
                "x": 221,
                "y": 141,
                "width": 120,
                "height": 60,
            },
        ],
        connectors=[{"id": "edge", "from": "a", "to": "target"}],
    )

    assert result["success"] is True
    metadata = result["metadata"]
    drawio_path = artifact_root / "tool_quality" / "assets" / "diagram.drawio"
    drawio_xml = drawio_path.read_text(encoding="utf-8")

    assert metadata["style_pack"] == "business_clean"
    assert metadata["output_targets"] == ["drawio", "png", "drawio_svg"]
    assert "canvas_expanded" in metadata["quality_warnings"]
    assert any(action["action"] == "snap_to_grid" for action in metadata["postprocess_actions"])
    assert "fillColor=#FFFFFF" in drawio_xml
    assert 'x="40"' in drawio_xml
    assert 'pageWidth="390"' in drawio_xml
