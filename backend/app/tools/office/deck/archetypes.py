from __future__ import annotations

from typing import Any, Callable, Dict, List

from app.tools.office.deck.models import ContentItemSpec, DeckSlideSpec


Renderer = Callable[[DeckSlideSpec], Dict[str, Any]]


def _items(items: List[ContentItemSpec]) -> List[Dict[str, str]]:
    return [
        {
            "title": item.title,
            "body": item.body or item.detail or "",
        }
        for item in items
    ]


def _bullets(slide: DeckSlideSpec) -> List[str]:
    if slide.content.bullets:
        return slide.content.bullets
    return [
        item.body or item.detail or item.title
        for item in slide.content.items
        if item.body or item.detail or item.title
    ]


def _image(slide: DeckSlideSpec) -> Dict[str, str]:
    if slide.visual and slide.visual.asset:
        return {"path": slide.visual.asset}
    return {}


def render_cover(slide: DeckSlideSpec) -> Dict[str, Any]:
    return {"type": "title", "title": slide.title, "subtitle": slide.subtitle or ""}


def render_agenda(slide: DeckSlideSpec) -> Dict[str, Any]:
    return {"type": "toc", "title": slide.title, "items": [item.title for item in slide.content.items]}


def render_section_divider(slide: DeckSlideSpec) -> Dict[str, Any]:
    return {"type": "section", "title": slide.title, "subtitle": slide.subtitle or ""}


def render_summary(slide: DeckSlideSpec) -> Dict[str, Any]:
    if slide.visual and slide.visual.asset:
        return {
            "type": "image_text",
            "title": slide.title,
            "image": _image(slide),
            "text": slide.message or "",
            "bullets": _bullets(slide),
        }
    return {"type": "summary", "title": slide.title, "items": _items(slide.content.items)}


def render_key_message(slide: DeckSlideSpec) -> Dict[str, Any]:
    return {
        "type": "key_message",
        "title": slide.title,
        "message": slide.message or slide.subtitle or slide.title,
        "items": _items(slide.content.items),
    }


def render_metrics(slide: DeckSlideSpec) -> Dict[str, Any]:
    return {"type": "metrics", "title": slide.title, "metrics": [metric.model_dump() for metric in slide.metrics]}


def render_table(slide: DeckSlideSpec) -> Dict[str, Any]:
    return {"type": "table", "title": slide.title, "table": slide.table or [[item.title, item.body or ""] for item in slide.content.items]}


def render_chart_story(slide: DeckSlideSpec) -> Dict[str, Any]:
    if slide.chart:
        return {
            "type": "data_story",
            "title": slide.title,
            "chart": slide.chart,
            "message": slide.message or "",
            "items": _items(slide.content.items),
        }
    return {
        "type": "image_text",
        "title": slide.title,
        "image": _image(slide),
        "text": slide.message or "",
        "bullets": _bullets(slide),
    }


def render_image_story(slide: DeckSlideSpec) -> Dict[str, Any]:
    return {
        "type": "image_text",
        "title": slide.title,
        "image": _image(slide),
        "text": slide.message or "",
        "bullets": _bullets(slide),
    }


def render_process(slide: DeckSlideSpec) -> Dict[str, Any]:
    return {"type": "process", "title": slide.title, "items": _items(slide.content.steps or slide.content.items)}


ARCHETYPE_RENDERERS: Dict[str, Renderer] = {
    "cover": render_cover,
    "agenda": render_agenda,
    "section_divider": render_section_divider,
    "executive_summary": render_summary,
    "three_column_points": render_summary,
    "closing_actions": render_summary,
    "key_message": render_key_message,
    "metric_dashboard": render_metrics,
    "evidence_table": render_table,
    "comparison_matrix": render_table,
    "risk_matrix": render_table,
    "budget_breakdown": render_table,
    "responsibility_matrix": render_table,
    "chart_story": render_chart_story,
    "map_story": render_image_story,
    "timeline": render_process,
    "roadmap": render_process,
    "gantt_plan": render_process,
    "process_flow": render_process,
    "implementation_plan": render_process,
    "architecture_overview": render_image_story,
    "data_flow": render_image_story,
    "before_after": render_table,
    "appendix": render_summary,
}


def render_slide_to_create_pptx(slide: DeckSlideSpec) -> Dict[str, Any]:
    renderer = ARCHETYPE_RENDERERS[slide.archetype]
    return renderer(slide)
