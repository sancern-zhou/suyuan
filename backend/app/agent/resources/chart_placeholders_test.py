import pytest

from app.agent.resources.chart_placeholders import (
    collect_placeholder_ids,
    normalize_chart_placeholders,
)
from app.agent.resources.contracts import ResourceDeclaration
from app.agent.resources.resource_service import SessionResourceService


def _chart_declaration(group_key: str, resource_key: str, visual_id: str, label: str):
    return ResourceDeclaration.model_validate({
        "kind": "visual",
        "group_key": group_key,
        "resource_key": resource_key,
        "relation": "primary",
        "role": "output",
        "label": label,
        "locator": {"path": f"/tmp/{resource_key}.json"},
        "format": "json",
        "media_type": "application/json",
        "renderer": "chart",
        "metadata": {"type": "image", "visual_id": visual_id, "interactive": False},
        "tool_name": "execute_python",
    })


async def _publish_session(service: SessionResourceService, session_id: str) -> dict[str, str]:
    published = await service.publish_group(
        session_id,
        "run-1",
        "charts:fig2",
        [_chart_declaration("charts:fig2", "chart-spec", "matplotlib_fig2", "图表 fig2")],
    )
    image = await service.publish_group(
        session_id,
        "run-1",
        "charts:fig2-image",
        [_chart_declaration("charts:fig2-image", "chart-image", "matplotlib_fig2", "fig2.png")],
    )
    await service.publish_group(
        session_id,
        "run-1",
        "data:station",
        [ResourceDeclaration.model_validate({
            "kind": "data",
            "group_key": "data:station",
            "resource_key": "primary:data",
            "relation": "primary",
            "role": "source",
            "label": "station data",
            "locator": {"path": "/tmp/station.csv"},
            "format": "csv",
            "media_type": "text/csv",
            "metadata": {},
            "tool_name": "execute_sql_query",
        })],
    )
    spec_id = published.resources[0].resource_id
    image_id = image.resources[0].resource_id
    return {spec_id: "matplotlib_fig2", image_id: "matplotlib_fig2"}


@pytest.mark.asyncio
async def test_resource_id_placeholders_are_rewritten_to_visual_id():
    session_id = "expert_session_test"
    service = SessionResourceService.in_memory()
    id_to_visual = await _publish_session(service, session_id)
    spec_id, image_id = sorted(id_to_visual, key=lambda item: id_to_visual[item])
    text = (
        "结论一：\n\n"
        f"[[chart:{spec_id}]]\n\n"
        "中间文字\n\n"
        f"[[chart:{image_id}]]\n"
    )

    normalized = await normalize_chart_placeholders(text, session_id, service=service)

    assert normalized.count("[[chart:matplotlib_fig2]]") == 2
    assert spec_id not in normalized and image_id not in normalized


@pytest.mark.asyncio
async def test_visual_id_placeholder_is_kept_unchanged():
    session_id = "expert_session_test"
    service = SessionResourceService.in_memory()
    await _publish_session(service, session_id)
    text = "正文\n\n[[chart:matplotlib_fig2]]\n"

    normalized = await normalize_chart_placeholders(text, session_id, service=service)

    assert normalized == text


@pytest.mark.asyncio
async def test_unknown_and_non_chart_ids_are_kept_unchanged():
    session_id = "expert_session_test"
    service = SessionResourceService.in_memory()
    id_to_visual = await _publish_session(service, session_id)
    data_resources = [
        resource for resource in service._state.resources.values()
        if resource.resource_key == "primary:data"
    ]
    data_id = data_resources[0].resource_id
    text = (
        f"未知 [[chart:totally_made_up_id]] 与 "
        f"数据资源 [[chart:{data_id}]] 均不改写"
    )

    normalized = await normalize_chart_placeholders(text, session_id, service=service)

    assert normalized == text


@pytest.mark.asyncio
async def test_lookup_failure_returns_original_text():
    class _BrokenService:
        async def list_resources(self, *args, **kwargs):
            raise RuntimeError("database unavailable")

    text = "正文\n\n[[chart:abcdef01]]\n"

    normalized = await normalize_chart_placeholders(
        text, "expert_session_test", service=_BrokenService()
    )

    assert normalized == text


def test_no_placeholder_short_circuits_without_lookup():
    class _MustNotCall:
        def __getattr__(self, name):
            raise AssertionError("service must not be touched")

    text = "没有占位符的正文"
    assert collect_placeholder_ids(text) == set()
    # 事件循环外直接断言快速路径：session_id 缺失时不做任何查询
    import asyncio

    normalized = asyncio.run(
        normalize_chart_placeholders("[[chart:whatever]]", None, service=_MustNotCall())
    )
    assert normalized == "[[chart:whatever]]"
