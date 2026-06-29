from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path

from app.agent.cognition.models import ExtractionResult


def generate_evaluation_markdown(
    extraction: ExtractionResult,
    sample_size: int = 30,
) -> str:
    entity_count = len(extraction.candidate_entities)
    relation_count = len(extraction.candidate_relations)
    entity_type_counts = Counter(entity.entity_type for entity in extraction.candidate_entities)
    relation_type_counts = Counter(
        relation.relation_type for relation in extraction.candidate_relations
    )

    lines = [
        "# 认知地图抽取评估",
        "",
        "## 总览",
        "",
        f"- 候选实体数量：{entity_count}",
        f"- 候选关系数量：{relation_count}",
        f"- Provider：{extraction.diagnostics.provider_name}",
        f"- Provider 状态：{extraction.diagnostics.status}",
        "",
        "## 实体类型分布",
        "",
    ]
    if entity_type_counts:
        lines.extend(f"- {name}: {count}" for name, count in entity_type_counts.most_common())
    else:
        lines.append("- 无")

    lines.extend(["", "## 关系类型分布", ""])
    if relation_type_counts:
        lines.extend(f"- {name}: {count}" for name, count in relation_type_counts.most_common())
    else:
        lines.append("- 无")

    lines.extend(["", f"## 抽样候选实体（最多 {sample_size} 条）", ""])
    for entity in extraction.candidate_entities[:sample_size]:
        lines.append(f"- [{entity.entity_type}] {entity.name}")
    if not extraction.candidate_entities:
        lines.append("- 无")

    lines.extend(["", f"## 抽样候选关系（最多 {sample_size} 条）", ""])
    entity_name_by_id = {entity.entity_id: entity.name for entity in extraction.candidate_entities}
    for relation in extraction.candidate_relations[:sample_size]:
        source = entity_name_by_id.get(relation.source_entity_id, relation.source_entity_id)
        target = entity_name_by_id.get(relation.target_entity_id, relation.target_entity_id)
        lines.append(f"- {source} --{relation.relation_type}--> {target}")
    if not extraction.candidate_relations:
        lines.append("- 无")

    return "\n".join(lines) + "\n"


def load_extraction(path: Path) -> ExtractionResult:
    return ExtractionResult.model_validate_json(path.read_text(encoding="utf-8"))


def write_evaluation(
    extraction_path: Path,
    output_path: Path,
    sample_size: int = 30,
) -> Path:
    extraction = load_extraction(extraction_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        generate_evaluation_markdown(extraction, sample_size=sample_size),
        encoding="utf-8",
    )
    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate cognitive map extraction JSON")
    parser.add_argument("extraction_path", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--sample-size", type=int, default=30)
    args = parser.parse_args()

    output_path = write_evaluation(
        extraction_path=args.extraction_path,
        output_path=args.output,
        sample_size=args.sample_size,
    )
    print(f"evaluation: {output_path}")


if __name__ == "__main__":
    main()
