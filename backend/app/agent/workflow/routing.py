"""Deterministic, persisted routing decisions over dependency results."""

from collections.abc import Mapping
from typing import Any


def validate_condition(condition: Mapping[str, Any], dependencies: tuple[str, ...], depth: int = 0) -> None:
    if not isinstance(condition, Mapping) or depth > 8:
        raise ValueError("invalid or excessively nested workflow condition")
    composites = set(condition) & {"all", "any", "not"}
    if composites:
        if len(condition) != 1:
            raise ValueError("condition must use one logical operator")
        key = next(iter(composites))
        children = [condition[key]] if key == "not" else condition[key]
        if not isinstance(children, list) or not 1 <= len(children) <= 32:
            raise ValueError("condition requires 1..32 clauses")
        for child in children:
            validate_condition(child, dependencies, depth + 1)
        return
    if set(condition) - {"source_task_id", "path", "op", "value"}:
        raise ValueError("unknown workflow condition field")
    if condition.get("source_task_id") not in dependencies:
        raise ValueError("condition source_task_id must be a direct dependency")
    path = condition.get("path")
    if not isinstance(path, str) or not path or any(not item for item in path.split(".")):
        raise ValueError("condition requires a dotted result path")
    if condition.get("op") not in {"eq", "ne", "gt", "ge", "lt", "le", "contains", "nonempty", "exists"}:
        raise ValueError("unsupported workflow condition operator")
    if condition["op"] not in {"nonempty", "exists"} and "value" not in condition:
        raise ValueError("condition comparison value is required")


def evaluate_condition(condition: Mapping[str, Any], results: Mapping[str, Any]) -> bool:
    # Evaluate every clause: missing evidence cannot hide behind short-circuiting.
    if "all" in condition:
        return all([evaluate_condition(child, results) for child in condition["all"]])
    if "any" in condition:
        return any([evaluate_condition(child, results) for child in condition["any"]])
    if "not" in condition:
        return not evaluate_condition(condition["not"], results)
    missing = object()
    value = results.get(condition["source_task_id"], missing)
    for key in condition["path"].split("."):
        if isinstance(value, Mapping):
            value = value.get(key, missing)
        elif isinstance(value, list) and key.isdigit() and int(key) < len(value):
            value = value[int(key)]
        else:
            value = missing
            break
    op = condition["op"]
    if op == "exists":
        return value is not missing
    if value is missing:
        raise ValueError(f"condition evidence missing: {condition['source_task_id']}.{condition['path']}")
    expected = condition.get("value")
    if op == "nonempty":
        return bool(value)
    if op in {"gt", "ge", "lt", "le"}:
        import math
        if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in (value, expected)):
            raise ValueError("numeric condition requires finite numeric evidence")
        return {"gt": value > expected, "ge": value >= expected, "lt": value < expected, "le": value <= expected}[op]
    if op == "contains":
        if not isinstance(value, (list, str, dict)):
            raise ValueError("contains condition requires a collection")
        try:
            return expected in value
        except TypeError as exc:
            raise ValueError("invalid contains comparison") from exc
    numeric = all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in (value, expected))
    equal = (type(value) is type(expected) or numeric) and value == expected
    return equal if op == "eq" else not equal
