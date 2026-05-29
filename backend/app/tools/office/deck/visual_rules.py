from __future__ import annotations

from typing import Dict, List

from app.tools.office.deck.models import DeckSlideSpec, DeckSpec


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
