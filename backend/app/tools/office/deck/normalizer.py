from __future__ import annotations

from typing import Any, Dict

from app.tools.office.deck.archetypes import render_slide_to_create_pptx
from app.tools.office.deck.models import DeckSpec


def normalize_deck_for_create_pptx(deck: DeckSpec) -> Dict[str, Any]:
    return {
        "title": deck.title,
        "theme": deck.theme or {},
        "design_brief": {
            "audience": deck.audience,
            "tone": deck.tone,
            "deck_type": deck.deck_type,
            "style": "Proposal Deck V2",
            "content_density": "dense",
            "rules": [
                "one core message per slide",
                "choose mature slide archetypes before rendering",
                "content slides must include visual evidence or structured content",
                "prefer metrics, charts, tables, timelines, process flows, maps, and architecture visuals over paragraphs",
            ],
        },
        "slides": [render_slide_to_create_pptx(slide) for slide in deck.slides],
    }
