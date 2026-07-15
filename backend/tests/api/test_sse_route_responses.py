from sse_starlette import EventSourceResponse

from app.routers.expert_deliberation import run_deliberation_stream
from app.routers.report_generation import _stream_template_report_agent
from app.services.expert_deliberation.schemas import DeliberationRequest
from config.settings import settings


def _assert_system_sse_response(response):
    assert isinstance(response, EventSourceResponse)
    assert response.media_type == "text/event-stream"
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["connection"] == "keep-alive"
    assert response.headers["x-accel-buffering"] == "no"
    assert response.ping_interval == settings.sse_heartbeat_interval_seconds
    assert response.send_timeout == settings.sse_send_timeout_seconds


def test_report_generation_uses_system_sse_response():
    response = _stream_template_report_agent(
        template_content="# Template",
        target_time_range={"start": "2026-07-01", "end": "2026-07-15"},
    )

    _assert_system_sse_response(response)


async def test_expert_deliberation_uses_system_sse_response():
    response = await run_deliberation_stream(DeliberationRequest())

    _assert_system_sse_response(response)
