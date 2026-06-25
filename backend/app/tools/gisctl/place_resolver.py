from __future__ import annotations

from dataclasses import dataclass

from app.services.pollution_evidence_package import CITY_COORDS


@dataclass(frozen=True)
class ResolvedPlace:
    name: str
    center: list[float]
    zoom: float | int
    scope: str
    cities: list[str]


REGION_TARGETS: tuple[ResolvedPlace, ...] = (
    ResolvedPlace(
        name="广东",
        center=[113.2665, 23.1322],
        zoom=7,
        scope="province",
        cities=[],
    ),
    ResolvedPlace(
        name="珠三角",
        center=[113.5, 22.8],
        zoom=8,
        scope="region",
        cities=[],
    ),
)


def resolve_place(value: str) -> ResolvedPlace | None:
    """Resolve a known place name to map view metadata.

    This intentionally does not classify natural-language operations. Agent intent
    selection happens through tool calling; this resolver only turns an explicit
    place argument such as "佛山" into coordinates.
    """
    normalized = (value or "").strip()
    if not normalized:
        return None

    for target in REGION_TARGETS:
        aliases = (target.name, f"{target.name}省") if target.name == "广东" else (target.name, "珠江三角洲")
        if normalized in aliases:
            return target

    for city in sorted(CITY_COORDS.keys(), key=len, reverse=True):
        if normalized in (city, f"{city}市"):
            lat, lon = CITY_COORDS[city]
            return ResolvedPlace(
                name=city,
                center=[lon, lat],
                zoom=10,
                scope="city",
                cities=[city],
            )

    return None
