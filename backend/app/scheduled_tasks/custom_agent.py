from typing import Any, Dict, Iterable, List, Mapping


class CustomToolValidationError(ValueError):
    def __init__(self, items: List[Dict[str, str]]):
        self.items = items
        super().__init__("Invalid custom task tools")


def authorized_tool_names_for_user(user: Any, registry: Any) -> set[str]:
    """Apply the platform's current tool ACL: authenticated users share enabled tools.

    The project has no per-role tool grants. Keeping this policy explicit makes the
    authorization boundary reusable if fine-grained grants are introduced later.
    """
    if not getattr(user, "id", ""):
        return set()
    return {
        name for name in registry.list_tools()
        if registry.get_tool_status(name) == "enabled"
    }


def validate_custom_tool_names(
    tool_names: Iterable[str],
    registry: Any,
    authorized_tool_names: set[str] | None = None,
) -> List[str]:
    names = list(dict.fromkeys(tool_names))
    invalid: List[Dict[str, str]] = []
    for name in names:
        status = registry.get_tool_status(name)
        if status is None:
            invalid.append({"name": name, "reason": "not_found"})
        elif status != "enabled":
            invalid.append({"name": name, "reason": "disabled"})
        elif authorized_tool_names is not None and name not in authorized_tool_names:
            invalid.append({"name": name, "reason": "forbidden"})
    if invalid:
        raise CustomToolValidationError(invalid)
    return names


def build_custom_tool_registry(
    tool_names: Iterable[str],
    source_registry: Any,
    react_registry: Mapping[str, Any],
) -> Dict[str, Any]:
    names = validate_custom_tool_names(tool_names, source_registry)
    unavailable = [
        {"name": name, "reason": "runtime_unavailable"}
        for name in names
        if name not in react_registry
    ]
    if unavailable:
        raise CustomToolValidationError(unavailable)
    return {name: react_registry[name] for name in names}
