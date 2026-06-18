from __future__ import annotations

import argparse
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from app.agent.cognition.models import CognitiveMapQuery, CognitiveSchema, ExtractionResult, SourceFile
from app.agent.cognition.providers.local_extractor import LocalRuleBasedExtractorProvider
from app.agent.cognition.providers.text_parser import TextParserProvider
from app.agent.cognition.view_builder import CognitiveMapViewBuilder


class SpikeRunResult(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    extraction: ExtractionResult
    view: object
    extraction_path: Path
    view_path: Path


async def run_local_spike(
    source_path: Path,
    output_dir: Path,
    task: str,
    entity_hints: list[str] | None = None,
    map_id: str = "spike_map",
    file_id: str = "spike_file",
) -> SpikeRunResult:
    source_path = Path(source_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    source_file = SourceFile(
        file_id=file_id,
        map_id=map_id,
        filename=source_path.name,
        content_type="text/plain",
        storage_path=str(source_path),
    )
    schema = CognitiveSchema.default_air_quality_schema()
    chunks = await TextParserProvider().parse(source_file)
    extraction = await LocalRuleBasedExtractorProvider().extract(chunks, schema)
    query = CognitiveMapQuery(
        task=task,
        agent_mode="expert",
        agent_role="spike",
        map_ids=[map_id],
        entity_hints=entity_hints or [],
    )
    view = CognitiveMapViewBuilder().build_from_extraction(query, extraction)

    extraction_path = output_dir / "extraction.json"
    view_path = output_dir / "map_view.json"
    extraction_path.write_text(
        extraction.model_dump_json(indent=2),
        encoding="utf-8",
    )
    view_path.write_text(
        view.model_dump_json(indent=2),
        encoding="utf-8",
    )
    return SpikeRunResult(
        extraction=extraction,
        view=view,
        extraction_path=extraction_path,
        view_path=view_path,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run local cognitive map spike extraction")
    parser.add_argument("source_path", type=Path, help="Plain text source file")
    parser.add_argument("--output-dir", type=Path, required=True, help="Directory for JSON outputs")
    parser.add_argument("--task", default="构建认知地图", help="Task text for CognitiveMapView")
    parser.add_argument("--hint", action="append", default=[], help="Entity hint, can be repeated")
    args = parser.parse_args()

    import asyncio

    result = asyncio.run(
        run_local_spike(
            source_path=args.source_path,
            output_dir=args.output_dir,
            task=args.task,
            entity_hints=args.hint,
        )
    )
    print(f"extraction: {result.extraction_path}")
    print(f"map_view: {result.view_path}")


if __name__ == "__main__":
    main()
