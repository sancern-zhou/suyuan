"""Merge current orders/forms with fetched history for cross-order checks.

The history index is shared by rules that compare a form against earlier
records for the same station/table (for example multipoint range continuity),
so it lives outside any single rule implementation.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any


_HISTORY_INDEX_CACHE: dict[
    tuple[int, tuple[Any, ...]],
    tuple[list[dict[str, Any]], dict[str, list[tuple[str, dict[str, Any]]]]],
] = {}
_HISTORY_INDEX_CACHE_LIMIT = 16


def merge_device_history(dataset: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, list[tuple[str, dict[str, Any]]]]]:
    """Return current and historical orders/forms indexed for cross-order checks.

    The merged history index is reused by multiple rule/report paths for the
    same in-memory dataset. A small signature cache avoids rebuilding the
    order/form index repeatedly while keeping the returned containers detached
    from the cached copy.
    """

    cache_key = _history_cache_key(dataset)
    cached = _HISTORY_INDEX_CACHE.get(cache_key)
    if cached:
        return _copy_history_index(cached)

    all_orders = list(dataset.get("orders", []))
    history = dataset.get("device_history") or {}
    seen_codes = {order.get("WORKINGORDERCODE") for order in all_orders if order.get("WORKINGORDERCODE")}
    for order in history.get("orders", []):
        code = order.get("WORKINGORDERCODE")
        if code and code not in seen_codes:
            all_orders.append(order)
            seen_codes.add(code)

    forms_by_code: dict[str, list[tuple[str, dict[str, Any]]]] = defaultdict(list)
    for table, forms in dataset.get("rf_forms", {}).items():
        for form in forms:
            code = form.get("WORKINGORDERCODE")
            if code:
                forms_by_code[str(code)].append((table, form))
    for table, forms in history.get("rf_forms", {}).items():
        for form in forms:
            code = form.get("WORKINGORDERCODE")
            if code:
                forms_by_code[str(code)].append((table, form))
    _remember_history_index(cache_key, all_orders, forms_by_code)
    return all_orders, forms_by_code


def _history_cache_key(dataset: dict[str, Any]) -> tuple[int, tuple[Any, ...]]:
    history = dataset.get("device_history") or {}
    rf_forms = dataset.get("rf_forms", {}) or {}
    history_rf_forms = history.get("rf_forms", {}) or {}
    signature = (
        len(dataset.get("orders", []) or []),
        tuple(sorted((str(table), len(forms or [])) for table, forms in rf_forms.items())),
        len(history.get("orders", []) or []),
        tuple(sorted((str(table), len(forms or [])) for table, forms in history_rf_forms.items())),
    )
    return id(dataset), signature


def _remember_history_index(
    cache_key: tuple[int, tuple[Any, ...]],
    all_orders: list[dict[str, Any]],
    forms_by_code: dict[str, list[tuple[str, dict[str, Any]]]],
) -> None:
    if len(_HISTORY_INDEX_CACHE) >= _HISTORY_INDEX_CACHE_LIMIT:
        _HISTORY_INDEX_CACHE.pop(next(iter(_HISTORY_INDEX_CACHE)))
    _HISTORY_INDEX_CACHE[cache_key] = (
        list(all_orders),
        {code: list(forms) for code, forms in forms_by_code.items()},
    )


def _copy_history_index(
    cached: tuple[list[dict[str, Any]], dict[str, list[tuple[str, dict[str, Any]]]]],
) -> tuple[list[dict[str, Any]], dict[str, list[tuple[str, dict[str, Any]]]]]:
    all_orders, forms_by_code = cached
    return list(all_orders), defaultdict(list, {code: list(forms) for code, forms in forms_by_code.items()})
