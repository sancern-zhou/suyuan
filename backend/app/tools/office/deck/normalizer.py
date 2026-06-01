from __future__ import annotations

from typing import Any, Dict, List

from app.tools.office.deck.models import DeckSlideSpec, DeckSpec


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


def _visual_image(slide: DeckSlideSpec) -> Dict[str, str]:
    if not slide.visual or not slide.visual.asset:
        return {}
    return {"path": slide.visual.asset}


def _normalize_slide(slide: DeckSlideSpec) -> Dict[str, Any]:
    if slide.type == "cover":
        return {"type": "title", "title": slide.title, "subtitle": slide.subtitle or ""}
    if slide.type == "toc":
        return {"type": "toc", "title": slide.title, "items": slide.items}
    if slide.type == "section":
        return {"type": "section", "title": slide.title, "subtitle": slide.subtitle or ""}
    if slide.type in {"executive_summary", "conclusion_actions"}:
        if slide.visual and slide.visual.asset:
            return {
                "type": "image_text",
                "title": slide.title,
                "image": _visual_image(slide),
                "bullets": slide.insights + slide.actions,
                "text": slide.message or "",
            }
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
            "image": _visual_image(slide),
            "bullets": slide.insights or slide.actions,
        }
    if slide.type == "chart_insight":
        if slide.chart:
            return {
                "type": "data_story",
                "title": slide.title,
                "chart": slide.chart,
                "message": slide.message or "",
                "items": _items_from_text(slide.insights or slide.actions),
            }
        if slide.visual and slide.visual.asset:
            return {
                "type": "image_text",
                "title": slide.title,
                "image": _visual_image(slide),
                "bullets": slide.insights or slide.actions,
                "text": slide.message or "",
            }
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
    return _visual_image(slide)


def _items_from_text(items: List[str]) -> List[Dict[str, str]]:
    return [{"title": f"要点 {idx}", "body": text} for idx, text in enumerate(items, start=1)]


def _risk_message(slide: DeckSlideSpec) -> str:
    if slide.risk_level:
        return f"风险等级：{slide.risk_level}"
    if slide.insights:
        return slide.insights[0]
    return slide.title
