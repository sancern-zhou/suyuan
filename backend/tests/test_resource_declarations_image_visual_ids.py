from pathlib import Path

import pytest

from app.agent.resources.contracts import ResourceDeclaration
from app.agent.resources.resource_service import SessionResourceService, inline_chart_path
from app.tools.resource_declarations import generated_file_products


@pytest.mark.asyncio
async def test_generated_image_publication_uses_snapshot_instead_of_visual_id(tmp_path: Path):
    image = tmp_path / "空气 图[1].png"
    image.write_bytes(b"first")
    [declaration] = [
        ResourceDeclaration.model_validate(item)
        for item in generated_file_products([image], tool_name="execute_python")
    ]
    service = SessionResourceService.in_memory(storage_root=tmp_path / "published")

    async def publish(publication_id=None):
        return await service.publish_group(
            "s1", "run", declaration.group_key, [declaration],
            publication_id=publication_id,
        )

    first = await publish("call-1")
    image.write_bytes(b"second")
    retry = await publish("call-1")
    second = await publish("call-2")
    assert retry == first
    first_image, second_image = first.resources[0], second.resources[0]
    assert first_image.resource_key == "primary:png"
    assert first_image.group_id != second_image.group_id
    assert Path(first_image.locator["path"]).read_bytes() == b"first"
    assert Path(second_image.locator["path"]).read_bytes() == b"second"
    assert "visual_id" not in first_image.metadata
    marker_path = inline_chart_path(first_image)
    assert marker_path and "[" not in marker_path and "]" not in marker_path
    assert await service.find_inline_charts_by_path("s1", marker_path) == [first_image]
    assert await service.find_inline_charts_by_path("s2", marker_path) == []
    assert await service.find_inline_charts_by_path("s1", image.name) == []
    assert await service.get_resources_by_ids(
        "s1", [second_image.resource_id, "missing", first_image.resource_id]
    ) == [second_image, first_image]

    fallback_first = await publish()
    image.write_bytes(b"third")
    fallback_second = await publish()
    assert fallback_first.resources[0].group_id != fallback_second.resources[0].group_id
    assert Path(fallback_first.resources[0].locator["path"]).read_bytes() == b"second"
