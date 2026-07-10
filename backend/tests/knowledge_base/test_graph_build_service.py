"""Contract tests for graph build executor."""
import pytest

from app.knowledge_base.graph_build_service import GraphBuildService


def test_service_exposes_lifecycle_api():
    service = GraphBuildService(lambda: None, extractor=object())
    for name in ("create_task", "get_status", "run", "retry", "cancel", "reset_graph"):
        assert callable(getattr(service, name))


@pytest.mark.asyncio
async def test_retry_missing_task_is_rejected():
    service = GraphBuildService(lambda: None)
    service.get_status = lambda **kw: _none()
    with pytest.raises(ValueError):
        await service.retry(task_id="missing")


async def _none():
    return None
