"""Restore chart resources at their referenced assistant turns, without exposing paths."""
import re

_CHART_REFERENCE = re.compile(r"\[\[chart:([A-Za-z0-9_-]{1,100})\]\]")


def attach_reply_resources(history: list, descriptors: list[dict]) -> None:
    replies = [item for item in history if isinstance(item, dict)
               and str(item.get("role") or item.get("type") or "").lower() in {"assistant", "final"}]
    if not replies:
        return
    by_id = {str(value[key]): value for value in descriptors
             for key in ("visual_id", "file_id") if value.get(key)}
    claimed = set()

    def attach(reply, resources):
        existing = reply.get("attachments") if isinstance(reply.get("attachments"), list) else []
        known = {str(value.get("file_id") or value.get("resource_id") or value.get("url") or "")
                 for value in existing if isinstance(value, dict)}
        additions = {value["file_id"]: value for value in resources if value["file_id"] not in known}
        reply["attachments"] = existing + list(additions.values())

    for reply in replies:
        resources = [by_id[ref] for ref in _CHART_REFERENCE.findall(str(reply.get("content") or ""))
                     if ref in by_id]
        attach(reply, resources)
        claimed.update(value["file_id"] for value in resources)
    # Preserve legacy attachment behavior for files and replies without explicit references.
    attach(replies[-1], [value for value in descriptors if value["file_id"] not in claimed])
