import inspect

from app.api.knowledge_base_routes import router
from app.knowledge_base.schemas import DocumentResponse


def test_upload_route_keeps_multipart_contract_and_response_model():
    route = next(
        route
        for route in router.routes
        if route.path == "/knowledge-base/{kb_id}/documents" and "POST" in route.methods
    )
    parameters = inspect.signature(route.endpoint).parameters

    assert list(parameters)[:7] == [
        "kb_id",
        "file",
        "metadata",
        "chunking_strategy",
        "chunk_size",
        "chunk_overlap",
        "llm_mode",
    ]
    assert route.response_model is DocumentResponse
    assert {
        "id",
        "filename",
        "file_type",
        "file_size",
        "status",
        "chunk_count",
        "error_message",
        "extra_metadata",
        "created_at",
        "processed_at",
    } <= set(DocumentResponse.model_fields)
