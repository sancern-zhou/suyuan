from pathlib import Path

import pytest

from app.boards.quality import (
    BoardRenderFailed,
    DrawioQualityService,
    evaluate_drawio_quality,
)


OVERLAPPING_XML = """
<mxfile><diagram><mxGraphModel><root>
  <mxCell id="0" />
  <mxCell id="1" parent="0" />
  <mxCell id="a" value="A" vertex="1" parent="1"><mxGeometry x="0" y="0" width="120" height="60" as="geometry" /></mxCell>
  <mxCell id="b" value="B" vertex="1" parent="1"><mxGeometry x="40" y="20" width="120" height="60" as="geometry" /></mxCell>
  <mxCell id="orphan" value="孤立" vertex="1" parent="1"><mxGeometry x="400" y="200" width="120" height="60" as="geometry" /></mxCell>
</root></mxGraphModel></diagram></mxfile>
"""


def test_quality_report_contains_stable_overlap_and_orphan_diagnostics():
    report = evaluate_drawio_quality(OVERLAPPING_XML)

    warning_codes = {issue["code"] for issue in report["warnings"]}
    assert "node_overlap" in warning_codes
    assert "orphan_node" in warning_codes
    assert report["status"] == "warning"
    assert report["metrics"]["vertex_count"] == 3
    assert report["metrics"]["overlap_count"] == 1
    assert report["metrics"]["orphan_count"] == 3


class _Renderer:
    def __init__(self):
        self.calls = 0

    async def render(self, xml: str, output_path: Path):
        self.calls += 1
        output_path.write_bytes(b"png")
        return {"renderer": "fake", "width": 640, "height": 480}


@pytest.mark.asyncio
async def test_quality_service_returns_screenshot_ref_and_report(tmp_path: Path):
    renderer = _Renderer()
    service = DrawioQualityService(renderer=renderer, storage_root=tmp_path)

    result = await service.inspect(OVERLAPPING_XML, board_id="board-1", candidate_id="candidate-1")

    assert renderer.calls == 1
    assert result["quality_report"]["status"] == "warning"
    assert result["screenshot_ref"]["kind"] == "drawio_board_screenshot"
    assert Path(result["screenshot_ref"]["local_path"]).read_bytes() == b"png"


class _FailingRenderer:
    def __init__(self):
        self.calls = 0

    async def render(self, xml: str, output_path: Path):
        self.calls += 1
        raise RuntimeError("renderer unavailable")


@pytest.mark.asyncio
async def test_quality_service_retries_once_then_blocks_delivery(tmp_path: Path):
    renderer = _FailingRenderer()
    service = DrawioQualityService(renderer=renderer, storage_root=tmp_path)

    with pytest.raises(BoardRenderFailed):
        await service.inspect(OVERLAPPING_XML, board_id="board-1", candidate_id="candidate-1")

    assert renderer.calls == 2
