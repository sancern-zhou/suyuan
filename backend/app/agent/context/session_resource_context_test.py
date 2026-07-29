from unittest.mock import Mock, patch

import pytest

from app.agent.context.context_builder import SimplifiedContextBuilder


MODES = [
    "assistant", "expert", "query", "report", "social", "chart", "ops", "graph",
    "memory_consolidator", "deliberation_meteorology", "deliberation_monitoring",
    "deliberation_chemistry", "deliberation_reviewer",
]


@pytest.mark.parametrize("mode", MODES)
def test_session_resource_context_is_injected_once_for_every_mode(mode):
    builder = SimplifiedContextBuilder(Mock(), Mock(), {})
    builder.current_mode = mode
    builder.session_resource_context = "resource-ref-marker"
    with patch(
        "app.agent.prompts.prompt_builder.build_react_system_prompt",
        return_value="mode prompt",
    ):
        prompt = builder._build_system_prompt()
    assert prompt.count("resource-ref-marker") == 1
    assert "<session_resources>" in prompt
