"""Evaluate scene graph extraction records against a JSONL gold set."""

from __future__ import annotations

import argparse
import json
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class GraphQualityMetrics:
    entity_precision: float
    entity_recall: float
    entity_f1: float
    relation_precision: float
    relation_recall: float
    relation_f1: float
    type_accuracy: float
    entity_link_accuracy: float
    evidence_support_rate: float
    duplicate_entity_rate: float
    schema_violation_rate: float
    isolated_entity_rate: float


def _ratio(numerator: int, denominator: int, *, empty: float = 1.0) -> float:
    return numerator / denominator if denominator else empty


def _f1(precision: float, recall: float) -> float:
    return 2 * precision * recall / (precision + recall) if precision + recall else 0.0


def calculate_graph_metrics(
    *,
    predicted_entities: set[tuple[str, str]],
    gold_entities: set[tuple[str, str]],
    predicted_relations: set[tuple[str, str, str]],
    gold_relations: set[tuple[str, str, str]],
    evidence_valid: Iterable[bool],
    entity_link_valid: Iterable[bool] = (),
    duplicate_entities: int = 0,
    schema_violations: int = 0,
    isolated_entities: int = 0,
) -> GraphQualityMetrics:
    entity_matches = len(predicted_entities & gold_entities)
    relation_matches = len(predicted_relations & gold_relations)
    entity_precision = _ratio(entity_matches, len(predicted_entities))
    entity_recall = _ratio(entity_matches, len(gold_entities))
    relation_precision = _ratio(relation_matches, len(predicted_relations))
    relation_recall = _ratio(relation_matches, len(gold_relations))

    predicted_by_name = {name: entity_type for entity_type, name in predicted_entities}
    shared_names = {name for _, name in gold_entities} & predicted_by_name.keys()
    correctly_typed = sum(
        predicted_by_name[name] == entity_type
        for entity_type, name in gold_entities
        if name in shared_names
    )
    evidence = list(evidence_valid)
    links = list(entity_link_valid)
    entity_total = len(predicted_entities)
    relation_total = len(predicted_relations)
    return GraphQualityMetrics(
        entity_precision=entity_precision,
        entity_recall=entity_recall,
        entity_f1=_f1(entity_precision, entity_recall),
        relation_precision=relation_precision,
        relation_recall=relation_recall,
        relation_f1=_f1(relation_precision, relation_recall),
        type_accuracy=_ratio(correctly_typed, len(shared_names)),
        entity_link_accuracy=_ratio(sum(links), len(links)),
        evidence_support_rate=_ratio(sum(evidence), len(evidence)),
        duplicate_entity_rate=_ratio(duplicate_entities, entity_total, empty=0.0),
        schema_violation_rate=_ratio(schema_violations, entity_total + relation_total, empty=0.0),
        isolated_entity_rate=_ratio(isolated_entities, entity_total, empty=0.0),
    )


def _tuples(records: Iterable[list[str]], width: int) -> set[tuple]:
    result = set()
    for record in records:
        if not isinstance(record, list) or len(record) != width:
            raise ValueError(f"Expected a {width}-item list, got {record!r}")
        result.add(tuple(record))
    return result


def evaluate_jsonl(path: Path) -> GraphQualityMetrics:
    predicted_entities: set[tuple[str, str]] = set()
    gold_entities: set[tuple[str, str]] = set()
    predicted_relations: set[tuple[str, str, str]] = set()
    gold_relations: set[tuple[str, str, str]] = set()
    evidence_valid: list[bool] = []
    entity_link_valid: list[bool] = []
    duplicate_entities = schema_violations = isolated_entities = 0

    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
            if not record.get("chunk_id"):
                raise ValueError("chunk_id is required")
            predicted_entities |= _tuples(record.get("predicted_entities", []), 2)
            gold_entities |= _tuples(record.get("gold_entities", []), 2)
            predicted_relations |= _tuples(record.get("predicted_relations", []), 3)
            gold_relations |= _tuples(record.get("gold_relations", []), 3)
            evidence_valid.extend(bool(value) for value in record.get("evidence_valid", []))
            entity_link_valid.extend(bool(value) for value in record.get("entity_link_valid", []))
            duplicate_entities += int(record.get("duplicate_entities", 0))
            schema_violations += int(record.get("schema_violations", 0))
            isolated_entities += int(record.get("isolated_entities", 0))
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ValueError(f"Malformed JSONL at line {line_number}: {exc}") from exc

    return calculate_graph_metrics(
        predicted_entities=predicted_entities,
        gold_entities=gold_entities,
        predicted_relations=predicted_relations,
        gold_relations=gold_relations,
        evidence_valid=evidence_valid,
        entity_link_valid=entity_link_valid,
        duplicate_entities=duplicate_entities,
        schema_violations=schema_violations,
        isolated_entities=isolated_entities,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--kb-id", required=True)
    parser.add_argument("--gold-jsonl", required=True, type=Path)
    parser.add_argument("--output-json", required=True, type=Path)
    args = parser.parse_args()
    metrics = evaluate_jsonl(args.gold_jsonl)
    payload = {"kb_id": args.kb_id, "metrics": asdict(metrics)}
    args.output_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
