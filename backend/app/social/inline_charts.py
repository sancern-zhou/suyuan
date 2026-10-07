"""Restore chart resources at their referenced assistant turns, without exposing paths."""
import re

_CHART_REFERENCE = re.compile(r"\[\[chart:([A-Za-z0-9_-]{1,100})\]\]")


def attach_reply_resources(history: list, descriptors: list[dict]) -> None:
    replies = [item for item in history if isinstance(item, dict)
               and str(item.get("type") or item.get("role") or "").lower() in {"assistant", "final"}]
    if not replies:
        return
    # Specs and image renditions share a visual ID. Prefer the renderable image
    # for static charts, and the interactive spec for ECharts, independent of order.
    def priority(value):
        if value.get("resource_key") == "chart-spec" and value.get("interactive") is True:
            return 2
        if str(value.get("mime_type") or "").startswith("image/"):
            return 1
        return 0

    by_id = {str(value[key]): value for value in sorted(descriptors, key=priority)
             for key in ("visual_id", "file_id") if value.get(key)}

    def attach(reply, resources):
        existing = reply.get("attachments") if isinstance(reply.get("attachments"), list) else []
        known = {str(value.get("file_id") or value.get("resource_id") or value.get("url") or "")
                 for value in existing if isinstance(value, dict)}
        additions = {value["file_id"]: value for value in resources if value["file_id"] not in known}
        reply["attachments"] = existing + list(additions.values())

    preceding_runs, preceding_ids = set(), set()
    for reply in history:
        if not isinstance(reply, dict):
            continue
        role = str(reply.get("type") or reply.get("role") or "").lower()
        if role == "user":
            preceding_runs, preceding_ids = set(), set()
            continue
        data = reply.get("data") if isinstance(reply.get("data"), dict) else {}
        result = data.get("result") if isinstance(data.get("result"), dict) else {}
        for payload in (reply, data, result):
            if payload.get("run_id"):
                preceding_runs.add(str(payload["run_id"]))
            preceding_ids.update(str(value) for value in payload.get("resource_ids", []) if value)
            preceding_runs.update(str(value) for value in payload.get("resource_run_ids", []) if value)
        if role not in {"assistant", "final"}:
            continue
        resources = [by_id[ref] for ref in _CHART_REFERENCE.findall(str(reply.get("content") or ""))
                     if ref in by_id]
        resources += [value for value in descriptors if value.get("file_id") in preceding_ids
                      or (value.get("run_id") and value["run_id"] in preceding_runs)]
        attach(reply, resources)
        preceding_runs, preceding_ids = set(), set()
    # Unattributed legacy resources remain in the session catalog. Never assign
    # them to an unrelated final reply merely because it is the latest one.
