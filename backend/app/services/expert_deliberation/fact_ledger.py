"""Fact ledger for deliberation."""

from __future__ import annotations

from collections import defaultdict
from typing import Iterable

from .schemas import FactRecord


class FactLedger:
    def __init__(self) -> None:
        self._facts: list[FactRecord] = []
        self._seen: set[str] = set()

    def add(self, fact: FactRecord) -> FactRecord:
        key = f"{fact.source_type}|{fact.statement}"
        if key in self._seen:
            return fact
        self._seen.add(key)
        self._facts.append(fact)
        return fact

    def extend(self, facts: Iterable[FactRecord]) -> None:
        for fact in facts:
            self.add(fact)

    def all(self) -> list[FactRecord]:
        return list(self._facts)

    def search_by_tags(self, tags_any: list[str], limit: int = 12) -> list[FactRecord]:
        if not tags_any:
            return self.all()[:limit]

        scored: list[tuple[int, FactRecord]] = []
        lowered_tags = [tag.lower() for tag in tags_any]
        for fact in self._facts:
            haystack = " ".join([fact.statement, " ".join(fact.tags), fact.pollutant or ""]).lower()
            score = sum(1 for tag in lowered_tags if tag.lower() in haystack)
            if score:
                scored.append((score, fact))

        scored.sort(key=lambda item: (-item[0], item[1].fact_id))
        return [fact for _, fact in scored[:limit]]

    def summary_by_source(self) -> dict[str, int]:
        counts: dict[str, int] = defaultdict(int)
        for fact in self._facts:
            counts[fact.source_type] += 1
        return dict(counts)

