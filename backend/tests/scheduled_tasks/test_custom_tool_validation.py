import pytest

from app.scheduled_tasks.custom_agent import (
    CustomToolValidationError,
    build_custom_tool_registry,
    validate_custom_tool_names,
)


class FakeRegistry:
    statuses = {"alpha": "enabled", "beta": "enabled", "disabled": "disabled"}

    def get_tool_status(self, name):
        return self.statuses.get(name)


def test_validation_reports_unknown_and_disabled_tools_together():
    with pytest.raises(CustomToolValidationError) as error:
        validate_custom_tool_names(["missing", "disabled"], FakeRegistry())

    assert error.value.items == [
        {"name": "missing", "reason": "not_found"},
        {"name": "disabled", "reason": "disabled"},
    ]


def test_filtered_runtime_registry_is_exact_and_ordered():
    result = build_custom_tool_registry(
        ["beta", "alpha"],
        FakeRegistry(),
        {"alpha": "A", "beta": "B", "extra": "X"},
    )

    assert list(result) == ["beta", "alpha"]
    assert result == {"beta": "B", "alpha": "A"}


def test_validation_rejects_a_tool_outside_the_callers_authorized_set():
    with pytest.raises(CustomToolValidationError) as error:
        validate_custom_tool_names(["alpha", "beta"], FakeRegistry(), {"alpha"})

    assert error.value.items == [{"name": "beta", "reason": "forbidden"}]
