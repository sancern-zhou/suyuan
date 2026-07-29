from app.knowledge_base.graph_extraction import (
    GraphDocumentChunk,
    GraphExtractionResult,
    GraphExtractionSchema,
    GraphSourceFile,
)
from app.knowledge_base.graph_extraction.providers.base import (
    DocumentParserProvider,
    GraphExtractorProvider,
)
from app.knowledge_base.graph_extraction.provider_factory import (
    create_extractor_provider,
    create_parser_provider,
)


def test_graph_extraction_exports_neutral_knowledge_graph_contracts():
    schema = GraphExtractionSchema(
        allowed_entity_types=["Device"],
        allowed_relation_types=["measures"],
    )
    chunk = GraphDocumentChunk(
        chunk_id="chunk-1",
        knowledge_base_id="kb-1",
        source_file_id="doc-1",
        chunk_index=0,
        text="设备监测噪声。",
        location="page:1",
    )

    assert schema.allowed_entity_types == ["Device"]
    assert chunk.knowledge_base_id == "kb-1"
    assert GraphSourceFile is not None
    assert GraphExtractionResult is not None
    assert DocumentParserProvider is not None
    assert GraphExtractorProvider is not None


def test_legacy_query_and_view_are_not_part_of_new_contract():
    import app.knowledge_base.graph_extraction as extraction

    assert not hasattr(extraction, "CognitiveMapQuery")
    assert not hasattr(extraction, "CognitiveMapView")


def test_graph_extraction_factory_builds_local_provider():
    provider = create_extractor_provider("local")
    assert provider.provider_name == "local_rule_based"


def test_graph_extraction_factory_builds_text_parser():
    parser = create_parser_provider("text")
    assert parser.__class__.__name__ == "TextParserProvider"
