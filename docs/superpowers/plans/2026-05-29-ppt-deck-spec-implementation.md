# PPT Deck Spec Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an Agent-friendly PPT generation workflow where the Agent writes a structured deck source file, while code handles layout, templates, rendering, and quality checks.

**Architecture:** Word reports continue to use `report.qmd -> docx/html`. PPT generation adds a parallel source format, `deck.yaml/json`, which is normalized into existing `create_pptx` slide specs or template replacements. The Agent owns business content and narrative; code owns visual constraints, template mapping, rendering, and validation.

**Tech Stack:** Python 3.11 in `/root/miniconda3/envs/backend_py311`, Pydantic or JSON Schema, existing `CreatePptxTool`, `CreatePptxFromTemplateTool`, `AnalyzePptxTemplateTool`, `ValidatePptxTool`, PptxGenJS, python-pptx, pytest.

---

## Context

The current PPT tooling already contains the right lower-level primitives:

- `backend/app/tools/office/create_pptx_tool.py`: accepts structured `slides` and renders through PptxGenJS.
- `backend/app/tools/office/pptxgen_renderer.js`: converts normalized slide specs to editable `.pptx`.
- `backend/app/tools/office/create_pptx_from_template_tool.py`: fills analyzed template slots.
- `backend/app/tools/office/analyze_pptx_template_tool.py`: extracts physical template slots.
- `backend/app/tools/office/validate_pptx_tool.py`: renders and checks PPT quality.
- `backend/tests/test_pptx_design_quality.py`: already covers auto-design and quality gate behavior.

The missing layer is a business-oriented deck source format that reduces LLM burden and prevents text-only PPTs.

## Target Principle

```text
Agent 负责：内容、结构、业务判断、图表/图片引用、讲述顺序
代码负责：版式、字体、颜色、图标、位置、模板槽位、质量校验
```

The Agent should produce this:

```yaml
type: forecast_warning
title: 未来5天臭氧超标风险集中在珠三角中部
risk_level: high
visual:
  kind: map
  asset: assets/maps/o3_forecast_risk.png
metrics:
  - label: 最高O3预测
    value: 182
    unit: ug/m3
insights:
  - 午后高温少云有利于臭氧生成
  - 广佛莞深需关注连续轻度污染风险
actions:
  - 加强VOCs重点行业错峰管控
```

The Agent should not produce low-level layout instructions:

```yaml
x: 0.85
y: 1.45
fontSize: 18
fill: F8FAFC
```

## File Structure

Create the Deck Spec layer under the Office tooling area:

```text
backend/app/tools/office/deck/
  __init__.py
  models.py
  normalizer.py
  visual_rules.py
  template_manifest.py
  deck_tool.py
```

Responsibilities:

- `models.py`: Deck source schema and validation models.
- `normalizer.py`: Convert business slide types to existing `create_pptx` slide specs.
- `visual_rules.py`: Enforce non-text-only presentation rules.
- `template_manifest.py`: Map semantic template slots to physical `s001_slot001` slots.
- `deck_tool.py`: Agent-facing tool that accepts `deck` input and chooses normal render or template render.

Add tests:

```text
backend/tests/test_ppt_deck_spec.py
backend/tests/test_ppt_deck_template_manifest.py
```

Update docs:

```text
backend/app/tools/office/PPT操作指南.md
backend/app/tools/office/office_skills_guide.md
```

---

## Task 1: Define Deck Source Schema

**Files:**
- Create: `backend/app/tools/office/deck/__init__.py`
- Create: `backend/app/tools/office/deck/models.py`
- Test: `backend/tests/test_ppt_deck_spec.py`

- [ ] **Step 1: Write schema tests**

Add tests that prove the deck source format accepts business slides and rejects invalid content-only slides.

```python
from pydantic import ValidationError

from app.tools.office.deck.models import DeckSpec


def test_deck_spec_accepts_business_slide():
    deck = DeckSpec.model_validate(
        {
            "version": "suyuan.deck.v1",
            "title": "广东省空气质量分析汇报",
            "audience": "management",
            "tone": "analytical",
            "slides": [
                {
                    "id": "s01",
                    "type": "metric_dashboard",
                    "title": "全省核心指标概览",
                    "metrics": [
                        {"label": "PM2.5均值", "value": 38, "unit": "ug/m3", "tone": "warning"}
                    ],
                }
            ],
        }
    )

    assert deck.version == "suyuan.deck.v1"
    assert deck.slides[0].type == "metric_dashboard"


def test_deck_spec_requires_slide_id_and_type():
    try:
        DeckSpec.model_validate(
            {
                "version": "suyuan.deck.v1",
                "title": "缺少类型",
                "slides": [{"title": "问题页"}],
            }
        )
    except ValidationError as exc:
        assert "id" in str(exc)
        assert "type" in str(exc)
    else:
        raise AssertionError("Expected ValidationError")
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
conda run -n backend_py311 pytest backend/tests/test_ppt_deck_spec.py -q
```

Expected: import failure for `app.tools.office.deck.models`.

- [ ] **Step 3: Implement schema models**

Create `backend/app/tools/office/deck/__init__.py`:

```python
"""Business deck source format for Agent-generated PPTs."""
```

Create `backend/app/tools/office/deck/models.py`:

```python
from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


SlideType = Literal[
    "cover",
    "toc",
    "section",
    "executive_summary",
    "metric_dashboard",
    "map_insight",
    "chart_insight",
    "city_ranking",
    "pollution_process",
    "forecast_warning",
    "evidence_table",
    "conclusion_actions",
]


class MetricSpec(BaseModel):
    label: str
    value: Any
    unit: Optional[str] = None
    delta: Optional[str] = None
    tone: Optional[str] = None


class VisualSpec(BaseModel):
    kind: Literal["map", "chart", "image", "icon_group", "timeline", "table"]
    asset: Optional[str] = None
    caption: Optional[str] = None
    data: Optional[Dict[str, Any]] = None


class DeckSlideSpec(BaseModel):
    id: str
    type: SlideType
    title: str
    subtitle: Optional[str] = None
    message: Optional[str] = None
    visual: Optional[VisualSpec] = None
    metrics: List[MetricSpec] = Field(default_factory=list)
    insights: List[str] = Field(default_factory=list)
    actions: List[str] = Field(default_factory=list)
    table: Optional[Any] = None
    chart: Optional[Dict[str, Any]] = None
    items: List[Any] = Field(default_factory=list)
    risk_level: Optional[str] = None
    notes: Optional[str] = None


class DeckSpec(BaseModel):
    version: Literal["suyuan.deck.v1"]
    title: str
    audience: str = "management"
    tone: str = "professional, evidence-led, concise"
    theme: Optional[Dict[str, Any]] = None
    narrative: List[Dict[str, Any]] = Field(default_factory=list)
    slides: List[DeckSlideSpec]
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
conda run -n backend_py311 pytest backend/tests/test_ppt_deck_spec.py -q
```

Expected: both tests pass.

---

## Task 2: Add Visual Rules

**Files:**
- Create: `backend/app/tools/office/deck/visual_rules.py`
- Modify: `backend/tests/test_ppt_deck_spec.py`

- [ ] **Step 1: Add failing visual rule tests**

Append:

```python
from app.tools.office.deck.visual_rules import validate_visual_rules


def test_visual_rules_reject_text_only_business_slide():
    deck = DeckSpec.model_validate(
        {
            "version": "suyuan.deck.v1",
            "title": "纯文字风险",
            "slides": [
                {
                    "id": "s02",
                    "type": "map_insight",
                    "title": "珠三角污染分析",
                    "insights": ["污染累积明显", "扩散条件较差"],
                }
            ],
        }
    )

    issues = validate_visual_rules(deck)

    assert issues
    assert issues[0]["type"] == "missing_visual_evidence"
    assert issues[0]["slide_id"] == "s02"


def test_visual_rules_allow_section_without_visual():
    deck = DeckSpec.model_validate(
        {
            "version": "suyuan.deck.v1",
            "title": "章节页",
            "slides": [{"id": "s01", "type": "section", "title": "一、总体情况"}],
        }
    )

    assert validate_visual_rules(deck) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
conda run -n backend_py311 pytest backend/tests/test_ppt_deck_spec.py -q
```

Expected: import failure for `visual_rules`.

- [ ] **Step 3: Implement visual rules**

Create `backend/app/tools/office/deck/visual_rules.py`:

```python
from __future__ import annotations

from typing import Dict, List

from app.tools.office.deck.models import DeckSpec, DeckSlideSpec


TEXT_ONLY_ALLOWED = {"cover", "toc", "section"}


def has_visual_evidence(slide: DeckSlideSpec) -> bool:
    return bool(
        slide.visual
        or slide.metrics
        or slide.table is not None
        or slide.chart
        or slide.type in {"pollution_process", "city_ranking"}
    )


def validate_visual_rules(deck: DeckSpec) -> List[Dict[str, object]]:
    issues: List[Dict[str, object]] = []
    for index, slide in enumerate(deck.slides, start=1):
        if slide.type in TEXT_ONLY_ALLOWED:
            continue
        if not has_visual_evidence(slide):
            issues.append(
                {
                    "type": "missing_visual_evidence",
                    "slide": index,
                    "slide_id": slide.id,
                    "message": "内容页必须包含 visual、metrics、table、chart 或业务可视化结构，避免纯文字页。",
                }
            )
    return issues
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
conda run -n backend_py311 pytest backend/tests/test_ppt_deck_spec.py -q
```

Expected: all tests pass.

---

## Task 3: Normalize Business Slides to Existing `create_pptx` Slides

**Files:**
- Create: `backend/app/tools/office/deck/normalizer.py`
- Modify: `backend/tests/test_ppt_deck_spec.py`

- [ ] **Step 1: Add normalizer tests**

Append:

```python
from app.tools.office.deck.normalizer import normalize_deck_for_create_pptx


def test_normalize_metric_dashboard_to_metrics_slide():
    deck = DeckSpec.model_validate(
        {
            "version": "suyuan.deck.v1",
            "title": "指标页",
            "slides": [
                {
                    "id": "s01",
                    "type": "metric_dashboard",
                    "title": "核心指标",
                    "metrics": [{"label": "AQI", "value": 85}],
                }
            ],
        }
    )

    result = normalize_deck_for_create_pptx(deck)

    assert result["title"] == "指标页"
    assert result["slides"][0]["type"] == "metrics"
    assert result["slides"][0]["metrics"][0]["label"] == "AQI"


def test_normalize_map_insight_to_image_text_slide():
    deck = DeckSpec.model_validate(
        {
            "version": "suyuan.deck.v1",
            "title": "地图页",
            "slides": [
                {
                    "id": "s02",
                    "type": "map_insight",
                    "title": "污染空间分布",
                    "visual": {"kind": "map", "asset": "assets/maps/pm25.png"},
                    "insights": ["北部污染较高", "沿海扩散较好"],
                }
            ],
        }
    )

    result = normalize_deck_for_create_pptx(deck)

    slide = result["slides"][0]
    assert slide["type"] == "image_text"
    assert slide["image"]["path"] == "assets/maps/pm25.png"
    assert slide["bullets"] == ["北部污染较高", "沿海扩散较好"]
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
conda run -n backend_py311 pytest backend/tests/test_ppt_deck_spec.py -q
```

Expected: import failure for `normalizer`.

- [ ] **Step 3: Implement normalizer**

Create `backend/app/tools/office/deck/normalizer.py`:

```python
from __future__ import annotations

from typing import Any, Dict, List

from app.tools.office.deck.models import DeckSpec, DeckSlideSpec


def normalize_deck_for_create_pptx(deck: DeckSpec) -> Dict[str, Any]:
    return {
        "title": deck.title,
        "theme": deck.theme or {},
        "design_brief": {
            "audience": deck.audience,
            "tone": deck.tone,
            "style": "Sharp & Compact",
            "content_density": "dense",
            "rules": [
                "one core message per slide",
                "content slides must include visual evidence",
                "prefer maps, charts, metrics, tables, and process cards over dense paragraphs",
            ],
        },
        "slides": [_normalize_slide(slide) for slide in deck.slides],
    }


def _normalize_slide(slide: DeckSlideSpec) -> Dict[str, Any]:
    if slide.type == "cover":
        return {"type": "title", "title": slide.title, "subtitle": slide.subtitle or ""}
    if slide.type == "toc":
        return {"type": "toc", "title": slide.title, "items": slide.items}
    if slide.type == "section":
        return {"type": "section", "title": slide.title, "subtitle": slide.subtitle or ""}
    if slide.type in {"executive_summary", "conclusion_actions"}:
        return {
            "type": "summary",
            "title": slide.title,
            "items": _items_from_text(slide.insights + slide.actions),
        }
    if slide.type == "metric_dashboard":
        return {"type": "metrics", "title": slide.title, "metrics": [m.model_dump() for m in slide.metrics]}
    if slide.type == "map_insight":
        return {
            "type": "image_text",
            "title": slide.title,
            "image": _image_from_visual(slide),
            "bullets": slide.insights or slide.actions,
        }
    if slide.type == "chart_insight":
        return {
            "type": "data_story",
            "title": slide.title,
            "chart": slide.chart,
            "items": _items_from_text(slide.insights),
        }
    if slide.type == "city_ranking":
        return {"type": "table", "title": slide.title, "table": slide.table or slide.items}
    if slide.type == "pollution_process":
        return {"type": "process", "title": slide.title, "items": slide.items or _items_from_text(slide.insights)}
    if slide.type == "forecast_warning":
        return {
            "type": "key_message",
            "title": slide.title,
            "message": slide.message or _risk_message(slide),
            "items": _items_from_text(slide.insights + slide.actions),
        }
    if slide.type == "evidence_table":
        return {"type": "table", "title": slide.title, "table": slide.table or []}
    return {"type": "key_message", "title": slide.title, "message": slide.message or "", "items": slide.items}


def _image_from_visual(slide: DeckSlideSpec) -> Dict[str, str]:
    if not slide.visual or not slide.visual.asset:
        return {}
    return {"path": slide.visual.asset}


def _items_from_text(items: List[str]) -> List[Dict[str, str]]:
    return [{"title": f"要点 {idx}", "body": text} for idx, text in enumerate(items, start=1)]


def _risk_message(slide: DeckSlideSpec) -> str:
    if slide.risk_level:
        return f"风险等级：{slide.risk_level}"
    if slide.insights:
        return slide.insights[0]
    return slide.title
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
conda run -n backend_py311 pytest backend/tests/test_ppt_deck_spec.py -q
```

Expected: all deck spec tests pass.

---

## Task 4: Create Agent-Facing Deck Tool

**Files:**
- Create: `backend/app/tools/office/deck/deck_tool.py`
- Modify: `backend/app/tools/__init__.py`
- Test: `backend/tests/test_ppt_deck_spec.py`

- [ ] **Step 1: Add tool behavior test with monkeypatch**

Append:

```python
import pytest

from app.tools.office.deck.deck_tool import CreatePptxFromDeckTool


@pytest.mark.asyncio
async def test_create_pptx_from_deck_rejects_missing_visual():
    tool = CreatePptxFromDeckTool()

    result = await tool.execute(
        deck={
            "version": "suyuan.deck.v1",
            "title": "非法纯文字",
            "slides": [
                {
                    "id": "s01",
                    "type": "map_insight",
                    "title": "空间分布",
                    "insights": ["只有文字"],
                }
            ],
        }
    )

    assert result["success"] is False
    assert "missing_visual_evidence" in result["summary"]
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
conda run -n backend_py311 pytest backend/tests/test_ppt_deck_spec.py -q
```

Expected: import failure for `deck_tool`.

- [ ] **Step 3: Implement tool wrapper**

Create `backend/app/tools/office/deck/deck_tool.py`:

```python
from __future__ import annotations

from typing import Any, Dict, Optional

from app.tools.base.tool_interface import LLMTool, ToolCategory
from app.tools.office.create_pptx_tool import CreatePptxTool
from app.tools.office.deck.models import DeckSpec
from app.tools.office.deck.normalizer import normalize_deck_for_create_pptx
from app.tools.office.deck.visual_rules import validate_visual_rules


class CreatePptxFromDeckTool(LLMTool):
    def __init__(self):
        super().__init__(
            name="create_pptx_from_deck",
            description=(
                "从 Agent 友好的 deck.yaml/json 业务结构生成 PPTX。"
                "Agent 只描述业务页面意图，工具负责转换为 create_pptx 可渲染结构。"
            ),
            category=ToolCategory.QUERY,
            version="1.0.0",
            requires_context=False,
        )

    async def execute(
        self,
        deck: Dict[str, Any],
        output_file: Optional[str] = None,
        quality: str = "standard",
        run_validation: bool = True,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        spec = DeckSpec.model_validate(deck)
        issues = validate_visual_rules(spec)
        if issues:
            return {
                "success": False,
                "data": {"issues": issues},
                "summary": f"Deck 视觉规则校验失败：{issues[0]['type']}",
            }

        normalized = normalize_deck_for_create_pptx(spec)
        return await CreatePptxTool().execute(
            title=normalized["title"],
            slides=normalized["slides"],
            output_file=output_file,
            theme=normalized.get("theme"),
            design_brief=normalized.get("design_brief"),
            quality=quality,
            run_validation=run_validation,
            **kwargs,
        )

    def get_function_schema(self) -> Dict[str, Any]:
        return {
            "name": "create_pptx_from_deck",
            "description": "从 deck.yaml/json 业务结构生成可编辑 PPTX。",
            "parameters": {
                "type": "object",
                "properties": {
                    "deck": {"type": "object", "description": "符合 suyuan.deck.v1 的业务 deck spec"},
                    "output_file": {"type": "string", "description": "输出 PPTX 路径，可选"},
                    "quality": {"type": "string", "enum": ["draft", "standard", "strict"], "default": "standard"},
                    "run_validation": {"type": "boolean", "default": True},
                },
                "required": ["deck"],
            },
        }
```

- [ ] **Step 4: Register the tool**

In `backend/app/tools/__init__.py`, add near the PPT tool registrations:

```python
    try:
        from app.tools.office.deck.deck_tool import CreatePptxFromDeckTool
        registry.register(CreatePptxFromDeckTool(), priority=351)
        logger.info("tool_loaded", tool="create_pptx_from_deck")
    except ImportError as e:
        logger.warning("tool_import_failed", tool="create_pptx_from_deck", error=str(e))
```

- [ ] **Step 5: Run tests**

Run:

```bash
conda run -n backend_py311 pytest backend/tests/test_ppt_deck_spec.py backend/tests/test_pptx_design_quality.py -q
```

Expected: tests pass.

---

## Task 5: Add Template Semantic Manifest

**Files:**
- Create: `backend/app/tools/office/deck/template_manifest.py`
- Create: `backend/tests/test_ppt_deck_template_manifest.py`

- [ ] **Step 1: Write semantic slot mapping tests**

Create `backend/tests/test_ppt_deck_template_manifest.py`:

```python
from app.tools.office.deck.template_manifest import TemplateManifest


def test_template_manifest_maps_semantic_slots_to_physical_slots():
    manifest = TemplateManifest.model_validate(
        {
            "template": "gov_air_quality_monthly",
            "slots": {
                "cover.title": "s001_slot001",
                "map_insight.main_map": "s004_slot002",
                "map_insight.key_findings": "s004_slot005",
            },
        }
    )

    replacements = manifest.to_physical_replacements(
        {
            "cover.title": "广东省3月空气质量分析汇报",
            "map_insight.main_map": "assets/maps/pm25.png",
        }
    )

    assert replacements == {
        "s001_slot001": "广东省3月空气质量分析汇报",
        "s004_slot002": "assets/maps/pm25.png",
    }


def test_template_manifest_reports_unknown_semantic_slots():
    manifest = TemplateManifest.model_validate(
        {"template": "demo", "slots": {"cover.title": "s001_slot001"}}
    )

    unknown = manifest.unknown_semantic_slots({"cover.title": "标题", "missing.slot": "内容"})

    assert unknown == ["missing.slot"]
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
conda run -n backend_py311 pytest backend/tests/test_ppt_deck_template_manifest.py -q
```

Expected: import failure for `template_manifest`.

- [ ] **Step 3: Implement manifest model**

Create `backend/app/tools/office/deck/template_manifest.py`:

```python
from __future__ import annotations

from typing import Any, Dict, List

from pydantic import BaseModel, Field


class TemplateManifest(BaseModel):
    template: str
    slots: Dict[str, str] = Field(default_factory=dict)

    def to_physical_replacements(self, semantic_values: Dict[str, Any]) -> Dict[str, Any]:
        replacements: Dict[str, Any] = {}
        for semantic_slot, value in semantic_values.items():
            physical_slot = self.slots.get(semantic_slot)
            if physical_slot:
                replacements[physical_slot] = value
        return replacements

    def unknown_semantic_slots(self, semantic_values: Dict[str, Any]) -> List[str]:
        return [slot for slot in semantic_values if slot not in self.slots]
```

- [ ] **Step 4: Run manifest tests**

Run:

```bash
conda run -n backend_py311 pytest backend/tests/test_ppt_deck_template_manifest.py -q
```

Expected: tests pass.

---

## Task 6: Add Template Render Path to Deck Tool

**Files:**
- Modify: `backend/app/tools/office/deck/deck_tool.py`
- Modify: `backend/tests/test_ppt_deck_template_manifest.py`

- [ ] **Step 1: Add conversion helper test**

Append:

```python
from app.tools.office.deck.deck_tool import build_semantic_values_from_deck
from app.tools.office.deck.models import DeckSpec


def test_build_semantic_values_from_deck():
    deck = DeckSpec.model_validate(
        {
            "version": "suyuan.deck.v1",
            "title": "模板填充",
            "slides": [
                {"id": "cover", "type": "cover", "title": "标题", "subtitle": "副标题"},
                {
                    "id": "map",
                    "type": "map_insight",
                    "title": "地图页",
                    "visual": {"kind": "map", "asset": "assets/maps/pm25.png"},
                    "insights": ["发现一", "发现二"],
                },
            ],
        }
    )

    values = build_semantic_values_from_deck(deck)

    assert values["cover.title"] == "标题"
    assert values["cover.subtitle"] == "副标题"
    assert values["map_insight.title"] == "地图页"
    assert values["map_insight.main_map"] == "assets/maps/pm25.png"
    assert values["map_insight.key_findings"] == "发现一\n发现二"
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
conda run -n backend_py311 pytest backend/tests/test_ppt_deck_template_manifest.py -q
```

Expected: import failure for `build_semantic_values_from_deck`.

- [ ] **Step 3: Implement semantic extraction**

Add to `backend/app/tools/office/deck/deck_tool.py`:

```python
from app.tools.office.deck.template_manifest import TemplateManifest
from app.tools.office.create_pptx_from_template_tool import CreatePptxFromTemplateTool


def build_semantic_values_from_deck(deck: DeckSpec) -> Dict[str, Any]:
    values: Dict[str, Any] = {}
    for slide in deck.slides:
        prefix = slide.type
        if slide.type == "cover":
            values["cover.title"] = slide.title
            if slide.subtitle:
                values["cover.subtitle"] = slide.subtitle
            continue
        values[f"{prefix}.title"] = slide.title
        if slide.message:
            values[f"{prefix}.message"] = slide.message
        if slide.visual and slide.visual.asset:
            key = "main_map" if slide.visual.kind == "map" else "main_visual"
            values[f"{prefix}.{key}"] = slide.visual.asset
        if slide.insights:
            values[f"{prefix}.key_findings"] = "\n".join(slide.insights)
        if slide.actions:
            values[f"{prefix}.actions"] = "\n".join(slide.actions)
        if slide.metrics:
            values[f"{prefix}.metrics"] = "\n".join(
                f"{metric.label}: {metric.value}{metric.unit or ''}" for metric in slide.metrics
            )
    return values
```

Extend `CreatePptxFromDeckTool.execute` with optional parameters:

```python
        template_path: Optional[str] = None,
        template_manifest: Optional[Dict[str, Any]] = None,
```

Before the normal `CreatePptxTool` path, add:

```python
        if template_path and template_manifest:
            manifest = TemplateManifest.model_validate(template_manifest)
            semantic_values = build_semantic_values_from_deck(spec)
            unknown = manifest.unknown_semantic_slots(semantic_values)
            replacements = manifest.to_physical_replacements(semantic_values)
            result = await CreatePptxFromTemplateTool().execute(
                template_path=template_path,
                replacements=replacements,
                output_file=output_file,
                quality=quality,
                run_validation=run_validation,
            )
            if isinstance(result.get("data"), dict):
                result["data"]["semantic_unknown_slots"] = unknown
                result["data"]["semantic_replacement_count"] = len(replacements)
            return result
```

Update `get_function_schema` to include:

```python
                    "template_path": {"type": "string", "description": "可选 PPTX 模板路径"},
                    "template_manifest": {"type": "object", "description": "可选语义槽位到物理 slot_id 的映射"},
```

- [ ] **Step 4: Run tests**

Run:

```bash
conda run -n backend_py311 pytest backend/tests/test_ppt_deck_spec.py backend/tests/test_ppt_deck_template_manifest.py -q
```

Expected: tests pass.

---

## Task 7: Update Agent Guidance

**Files:**
- Modify: `backend/app/tools/office/PPT操作指南.md`
- Modify: `backend/app/tools/office/office_skills_guide.md`

- [ ] **Step 1: Add PPT generation policy**

Add this policy near the PPT creation section:

```markdown
### Deck Spec 优先原则

生成正式或业务型 PPT 时，优先使用 `create_pptx_from_deck`，不要让 Agent 直接从零构造低层 PPT 元素。

Agent 应输出 `suyuan.deck.v1` 业务结构：

- `cover`
- `toc`
- `section`
- `executive_summary`
- `metric_dashboard`
- `map_insight`
- `chart_insight`
- `city_ranking`
- `pollution_process`
- `forecast_warning`
- `evidence_table`
- `conclusion_actions`

除 `cover`、`toc`、`section` 外，每页必须包含至少一种视觉证据：`visual`、`metrics`、`table`、`chart` 或业务可视化结构。

使用现成模板时，提供 `template_path` 和 `template_manifest`，由工具将语义槽位转换为模板物理 slot。
```

- [ ] **Step 2: Add one full deck example**

Add this fenced JSON example:

```json
{
  "deck": {
    "version": "suyuan.deck.v1",
    "title": "广东省3月空气质量分析汇报",
    "audience": "management",
    "tone": "professional, evidence-led, concise",
    "slides": [
      {
        "id": "s01",
        "type": "cover",
        "title": "广东省3月空气质量分析汇报",
        "subtitle": "污染特征与管控建议"
      },
      {
        "id": "s02",
        "type": "metric_dashboard",
        "title": "全省核心指标概览",
        "metrics": [
          {"label": "PM2.5均值", "value": 38, "unit": "ug/m3", "tone": "warning"},
          {"label": "O3最大8小时", "value": 172, "unit": "ug/m3", "tone": "danger"}
        ]
      },
      {
        "id": "s03",
        "type": "map_insight",
        "title": "珠三角北部污染累积明显",
        "visual": {"kind": "map", "asset": "assets/maps/pm25_map.png"},
        "insights": ["夜间静稳导致污染累积", "区域传输贡献明显"]
      }
    ]
  },
  "quality": "standard",
  "run_validation": true
}
```

- [ ] **Step 3: Run documentation grep**

Run:

```bash
rg -n "create_pptx_from_deck|suyuan.deck.v1|Deck Spec" backend/app/tools/office/PPT操作指南.md backend/app/tools/office/office_skills_guide.md
```

Expected: both docs mention the new tool and deck format.

---

## Task 8: Full Verification

**Files:**
- No new files.

- [ ] **Step 1: Run focused tests**

Run:

```bash
conda run -n backend_py311 pytest backend/tests/test_ppt_deck_spec.py backend/tests/test_ppt_deck_template_manifest.py backend/tests/test_pptx_design_quality.py -q
```

Expected: all tests pass.

- [ ] **Step 2: Run registry import smoke test**

Run:

```bash
conda run -n backend_py311 python - <<'PY'
from app.tools.office.deck.deck_tool import CreatePptxFromDeckTool

tool = CreatePptxFromDeckTool()
schema = tool.get_function_schema()
assert schema["name"] == "create_pptx_from_deck"
assert "deck" in schema["parameters"]["required"]
print("create_pptx_from_deck schema ok")
PY
```

Expected:

```text
create_pptx_from_deck schema ok
```

- [ ] **Step 3: Run existing PPT quality tests**

Run:

```bash
conda run -n backend_py311 pytest backend/tests/test_pptx_design_quality.py -q
```

Expected: existing PPT design quality tests still pass.

---

## Rollout Plan

1. Implement Tasks 1-4 first. This gives a usable `deck -> create_pptx` path without templates.
2. Use it on one internal air-quality deck and inspect the generated QA montage.
3. Implement Tasks 5-6 only after one real template is chosen.
4. Update Agent prompts and docs in Task 7.
5. Keep `create_pptx` available for low-level fallback, but guide Agents toward `create_pptx_from_deck`.

## Acceptance Criteria

- Agents can generate PPT from `suyuan.deck.v1` without writing x/y/w/h layout fields.
- Non-section content slides cannot pass validation if they are pure text.
- Business slide types are normalized into existing `create_pptx` slide types.
- Template rendering can use semantic slots instead of raw `s001_slot001` identifiers.
- Existing PPT generation and quality tests still pass.
- Documentation clearly says `create_pptx_from_deck` is preferred for business PPT generation.

## Deferred Work

These are intentionally not part of the first implementation:

- Splitting `pptxgen_renderer.js` into multiple modules.
- Adding custom-rendered business slide layouts directly in JS.
- Building a visual template marketplace.
- Adding automatic LLM rewrite loops after `quality_gate.rewrite_required`.
- Importing Presenton, slidegen-pptx, or OPF as runtime dependencies.

The first implementation should reuse the existing renderer and only add the missing Agent-friendly Deck Spec layer.
