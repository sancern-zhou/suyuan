from __future__ import annotations

import argparse
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from app.agent.cognition.evaluation import write_evaluation
from app.agent.cognition.llm_factory import create_llamaindex_llm
from app.agent.cognition.models import CognitiveMapQuery, CognitiveSchema, ExtractionResult, SourceFile
from app.agent.cognition.provider_factory import create_extractor_provider, create_parser_provider
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
    parser_provider: str = "text",
    extractor_provider: str = "local",
    llm_provider: str | None = None,
    evaluation_output: Path | None = None,
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
    parser = create_parser_provider(parser_provider)
    llm = create_llamaindex_llm(llm_provider) if extractor_provider == "llamaindex" else None
    extractor = create_extractor_provider(extractor_provider, llm=llm)
    chunks = await parser.parse(source_file)
    extraction = await extractor.extract(chunks, schema)
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
    if evaluation_output is not None:
        write_evaluation(extraction_path=extraction_path, output_path=evaluation_output)
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
    parser.add_argument("--parser-provider", default="text", choices=["text", "markitdown"])
    parser.add_argument("--extractor-provider", default="local", choices=["local", "llamaindex"])
    parser.add_argument("--llm-provider", default=None, choices=["project", "none"])
    parser.add_argument("--evaluation-output", type=Path, default=None)
    args = parser.parse_args()

    import asyncio

    result = asyncio.run(
        run_local_spike(
            source_path=args.source_path,
            output_dir=args.output_dir,
            task=args.task,
            entity_hints=args.hint,
            parser_provider=args.parser_provider,
            extractor_provider=args.extractor_provider,
            llm_provider=args.llm_provider,
            evaluation_output=args.evaluation_output,
        )
    )
    print(f"extraction: {result.extraction_path}")
    print(f"map_view: {result.view_path}")


if __name__ == "__main__":
    main()
