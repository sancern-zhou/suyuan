from types import SimpleNamespace

import pytest

from app.agent.resources.chart_placeholders import (
    CHART_UNAVAILABLE,
    ChartDraftFilter,
    collect_placeholder_ids,
    normalize_chart_placeholders,
    redact_chart_paths,
)
from app.agent.resources.resource_service import normalize_chart_path
from app.agent.runtime.event_bus import RuntimeEventBus
from app.agent.runtime.finalizer import Finalizer
from app.agent.runtime.types import RunState

IMAGE = "a" * 32
SPEC = "b" * 32
IMAGE_PATH = "backend/snapshots/浓度 趋势.png"
SPEC_PATH = "backend/snapshots/交互趋势.json"


def marker(value):
    return f"[[chart:{value}]]"


class Catalog:
    async def find_inline_charts_by_paths(self, session_id, paths):
        assert session_id == "owned"
        image = SimpleNamespace(resource_id=IMAGE)
        spec = SimpleNamespace(resource_id=SPEC)
        known = {
            normalize_chart_path(IMAGE_PATH): [image],
            normalize_chart_path(SPEC_PATH): [spec],
            normalize_chart_path("backend/ambiguous.png"): [image, spec],
        }
        return {normalize_chart_path(path): known.get(normalize_chart_path(path), []) for path in paths}

    async def get_resources_by_ids(self, session_id, ids):
        assert session_id == "owned"
        return []


@pytest.mark.asyncio
async def test_path_marker_resolves_static_and_interactive_resources_in_order():
    text = f"趋势\n{marker(IMAGE_PATH)}\n交互\n{marker(SPEC_PATH)}"
    expected = f"趋势\n{marker(IMAGE)}\n交互\n{marker(SPEC)}"
    assert await normalize_chart_placeholders(text, "owned", Catalog()) == expected


@pytest.mark.asyncio
async def test_unresolved_paths_and_unowned_ids_render_as_plain_text():
    values = ["backend/other-session.png", "backend/ambiguous.png", "https://example.com/p.png", "chart_0", IMAGE]
    text = " ".join(map(marker, values))
    assert await normalize_chart_placeholders(text, "owned", Catalog()) == " ".join([CHART_UNAVAILABLE] * len(values))
    assert await normalize_chart_placeholders(marker(IMAGE_PATH), None, Catalog()) == CHART_UNAVAILABLE


def test_code_examples_and_escaped_markers_are_not_chart_references():
    code = f"示例 `{marker(IMAGE)}`\n\n```text\n{marker(IMAGE)}\n```\n\n\\{marker(IMAGE)}"
    assert collect_placeholder_ids(f"{code}\n\n{marker(SPEC)}") == {SPEC}
    assert redact_chart_paths(f"{code}\n\n{marker(IMAGE_PATH)}") == f"{code}\n\n{CHART_UNAVAILABLE}"


def test_quoted_fences_and_indented_examples_remain_literal():
    code = f"> ~~~text\n> {marker(IMAGE)}\n> ~~~\n\n    {marker(IMAGE)}"
    assert collect_placeholder_ids(f"{code}\n\n{marker(SPEC)}") == {SPEC}
    unclosed_quote = f"> ```\n> {marker(IMAGE)}\n\n{marker(SPEC)}"
    assert collect_placeholder_ids(unclosed_quote) == {SPEC}


@pytest.mark.parametrize("chunk_size", [1, 3, 5, 31, 4096])
def test_draft_filter_buffers_chart_delimiters_and_redacts_incomplete_paths(chunk_size):
    filter_ = ChartDraftFilter()
    answer = f"前文 {marker(IMAGE_PATH)} 中间 [[chart:backend/private.png\n后文"
    visible = "".join(filter_.append(answer[i:i + chunk_size]) for i in range(0, len(answer), chunk_size))
    assert visible + filter_.flush() == f"前文 {CHART_UNAVAILABLE} 中间 {CHART_UNAVAILABLE}\n后文"


@pytest.mark.asyncio
async def test_finalizer_uses_same_resolved_text_for_iteration_persistence_and_terminal_events(monkeypatch):
    monkeypatch.setattr("app.agent.resources.chart_placeholders.SessionResourceService.database", lambda: Catalog())
    entries = {}
    writer = SimpleNamespace(
        add_iteration=lambda thought, action, observation: entries.update(iteration=action["answer"]),
        add_final_assistant_message=lambda state, planner_result, thought: entries.update(saved=state.response_text),
    )
    state = RunState(session_id="owned", user_query="画图", mode="expert", response_streamed=True)
    events = [event async for event in Finalizer(writer, RuntimeEventBus()).complete(
        state, f"图\n{marker(IMAGE_PATH)}", completion_action={"type": "PLAIN_TEXT_REPLY"}
    )]
    assert entries == {"iteration": f"图\n{marker(IMAGE)}", "saved": f"图\n{marker(IMAGE)}"}
    assert [event["type"] for event in events] == ["agent_finish", "complete"]
    assert events[0]["answer"] == events[1]["data"]["answer"] == events[1]["data"]["response"] == entries["saved"]
