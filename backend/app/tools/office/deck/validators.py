from __future__ import annotations

from typing import Dict, List

from app.tools.office.deck.models import DeckSlideSpec, DeckSpec


TEXT_ONLY_ALLOWED = {"cover", "agenda", "section_divider", "appendix"}
MAX_TITLE_CHARS = 24


def _has_content_items(slide: DeckSlideSpec) -> bool:
    return bool(
        slide.content.items
        or slide.content.columns
        or slide.content.steps
        or slide.content.bullets
    )


def has_visual_evidence(slide: DeckSlideSpec) -> bool:
    return bool(
        slide.visual
        or slide.metrics
        or slide.chart
        or slide.table is not None
        or _has_content_items(slide)
        or slide.archetype
        in {
            "timeline",
            "roadmap",
            "gantt_plan",
            "process_flow",
            "architecture_overview",
            "data_flow",
            "comparison_matrix",
            "risk_matrix",
            "budget_breakdown",
            "implementation_plan",
            "responsibility_matrix",
        }
    )


def validate_deck_design(deck: DeckSpec) -> List[Dict[str, object]]:
    issues: List[Dict[str, object]] = []
    for index, slide in enumerate(deck.slides, start=1):
        if len(slide.title) > MAX_TITLE_CHARS:
            issues.append(
                {
                    "type": "slide_title_too_long",
                    "slide": index,
                    "slide_id": slide.id,
                    "message": "PPT页面标题应控制在24个中文字符以内，请压缩为判断句或结论句。",
                }
            )

        if slide.archetype in TEXT_ONLY_ALLOWED:
            continue
        if not has_visual_evidence(slide):
            issues.append(
                {
                    "type": "content_slide_without_visual_evidence",
                    "slide": index,
                    "slide_id": slide.id,
                    "message": "内容页不能只有标题或长段文字，请提供 content.items、metrics、chart、table 或 visual。",
                    "suggested_archetypes": [
                        "three_column_points",
                        "process_flow",
                        "evidence_table",
                        "implementation_plan",
                    ],
                }
            )
    return issues
