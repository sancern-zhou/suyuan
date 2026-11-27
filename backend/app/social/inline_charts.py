"""Restore App reply attachments without borrowing files from unrelated turns."""
from collections.abc import Sequence

from app.agent.resources.chart_placeholders import collect_placeholder_ids


def _message_type(item: dict) -> str:
    return str(item.get("type") or item.get("role") or "").lower()


def reply_chart_ids(history: list) -> set[str]:
    return {
        resource_id
        for item in history
        if isinstance(item, dict) and _message_type(item) in {"assistant", "final"}
        for resource_id in collect_placeholder_ids(str(item.get("content") or ""))
    }


def is_chart_attachment(item: dict) -> bool:
    return (
        str(item.get("mime_type") or "").lower().startswith("image/")
        or (item.get("resource_key") == "chart-spec" and item.get("interactive") is True)
    )


def attach_reply_resources(
    history: list, descriptors: list[dict], *, chart_descriptors: Sequence[dict] = (),
) -> None:
    charts_by_id = {
        value["resource_id"]: value
        for value in (*descriptors, *chart_descriptors)
        if value.get("resource_id") and is_chart_attachment(value)
    }
    preceding_runs, preceding_ids, preceding_groups = set(), set(), set()
    for reply in history:
        if not isinstance(reply, dict):
            continue
        role = _message_type(reply)
        if role == "user":
            preceding_runs, preceding_ids, preceding_groups = set(), set(), set()
            continue
        data = reply.get("data") if isinstance(reply.get("data"), dict) else {}
        result = data.get("result") if isinstance(data.get("result"), dict) else {}
        for payload in (reply, data, result):
            if payload.get("run_id"):
                preceding_runs.add(str(payload["run_id"]))
            preceding_ids.update(str(value) for value in payload.get("resource_ids") or [] if value)
            preceding_runs.update(str(value) for value in payload.get("resource_run_ids") or [] if value)
            preceding_groups.update(str(value) for value in payload.get("resource_group_ids") or [] if value)
        if role not in {"assistant", "final"}:
            continue
        refs = collect_placeholder_ids(str(reply.get("content") or ""))
        charts = [charts_by_id[ref] for ref in sorted(refs) if ref in charts_by_id]
        existing = reply.get("attachments")
        existing = [value for value in existing if isinstance(value, dict)] if isinstance(existing, list) else []
        # An inline reference can belong to an earlier turn. Keep the attachment
        # but do not revive every other file in its run or group.
        preceding_groups.update(
            value["group_id"] for value in existing
            if value.get("group_id") and value.get("resource_id") not in refs
        )
        files = [value for value in descriptors if (
            value.get("file_id") in preceding_ids or value.get("group_id") in preceding_groups
            or value.get("run_id") in preceding_runs
        )]
        current_groups = {value["group_id"] for value in files if value.get("group_id")}
        current_ids = {value["file_id"] for value in files}
        existing = [value for value in existing if (
            value.get("resource_id") in refs or value.get("group_id") not in current_groups
            or value.get("file_id") in current_ids
        )]
        # Current authorized descriptors replace the metadata for that exact
        # chart while ordinary upload IDs (and their display links) stay intact.
        existing = [charts_by_id.get(value["resource_id"], value) if value.get("resource_id") in refs else value for value in existing]
        known = {str(value.get("file_id") or value.get("resource_id") or value.get("url") or "") for value in existing}
        additions = {value["file_id"]: value for value in [*files, *charts] if value["file_id"] not in known}
        reply["attachments"] = existing + list(additions.values())
        preceding_runs, preceding_ids, preceding_groups = set(), set(), set()
