"""Pure ranking helpers for graph-augmented knowledge retrieval."""

from __future__ import annotations

from pydantic import BaseModel, Field


class FusedChunkRank(BaseModel):
    chunk_id: str
    score: float
    sources: list[str] = Field(default_factory=list)


def reciprocal_rank_fusion(
    rankings: dict[str, list[str]],
    *,
    weights: dict[str, float] | None = None,
    k: float = 60.0,
) -> list[FusedChunkRank]:
    weights = weights or {}
    scores: dict[str, float] = {}
    sources: dict[str, list[str]] = {}
    for source, chunk_ids in rankings.items():
        weight = max(float(weights.get(source, 1.0)), 0.0)
        for rank, chunk_id in enumerate(dict.fromkeys(chunk_ids), start=1):
            scores[chunk_id] = scores.get(chunk_id, 0.0) + weight / (k + rank)
            sources.setdefault(chunk_id, []).append(source)
    return sorted(
        (
            FusedChunkRank(chunk_id=chunk_id, score=score, sources=sources[chunk_id])
            for chunk_id, score in scores.items()
        ),
        key=lambda item: (-item.score, item.chunk_id),
    )
