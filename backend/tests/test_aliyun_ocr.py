import base64
import json

import httpx
import pytest

from app.services.aliyun_ocr import call_aliyun_ocr


@pytest.mark.asyncio
async def test_call_aliyun_ocr_posts_expected_payload_and_reconstructs_text():
    captured = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["authorization"] = request.headers.get("authorization")
        captured["json"] = json.loads(request.content.decode("utf-8"))
        return httpx.Response(
            200,
            request=request,
            json={
                "content": "",
                "prism_wordsInfo": [
                    {"word": "A1", "x": 10, "y": 10, "height": 10},
                    {"word": "B1", "x": 60, "y": 10, "height": 10},
                ],
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        text, response_data = await call_aliyun_ocr(
            b"abc",
            app_code="test-appcode",
            client=client,
        )

    assert captured["authorization"] == "APPCODE test-appcode"
    assert captured["json"]["img"] == base64.b64encode(b"abc").decode("ascii")
    assert captured["json"]["NeedRotate"] is True
    assert captured["json"]["NeedSortPage"] is True
    assert captured["json"]["OutputTable"] is True
    assert text == "A1 B1"
    assert response_data["prism_wordsInfo"][0]["word"] == "A1"
