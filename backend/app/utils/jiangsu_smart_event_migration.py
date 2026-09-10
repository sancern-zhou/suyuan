"""Migrate a stopped deployment to independent event packages and verify every event.

Example (run from the project root with backend on PYTHONPATH):
python -m app.utils.jiangsu_smart_event_migration --data-root backend/backend_data_registry_jiangsu_ops
"""
from __future__ import annotations

import argparse
import json
from copy import deepcopy

from app.services.jiangsu_smart_event_store import JiangsuEventPackages, SCHEMA
from app.utils.path_config import resolve_agent_path, format_agent_path


def normalized(event):
    value = deepcopy(event)
    package = value.get("evidence_package")
    evidence = value.get("evidence")
    if isinstance(evidence, dict):
        duplicate = evidence.pop("package", None)
        if package is None:
            package = duplicate
        elif duplicate is not None and duplicate != package:
            raise ValueError(f"conflicting_legacy_evidence:{event['event_id']}")
    if package is None:
        package = {"event_id": event["event_id"], "status": "missing", "sources": {},
                   "gaps": [{"source": "collector", "reason": "evidence_not_collected"}]}
    package = deepcopy(package)
    package.pop("persisted_path", None)
    package.setdefault("event_id", event["event_id"])
    value["evidence_package"] = package
    return value


def migrate(data_root):
    packages = JiangsuEventPackages(resolve_agent_path(data_root) / "jiangsu_smart_events" / "store.json")
    original = packages.load()
    before = {str(event["event_id"]): normalized(event) for event in original.get("events", [])}
    old_size = packages.path.stat().st_size
    if original.get("schema_version") != SCHEMA:
        packages.save(original)
    after = packages.load()
    assert before == {str(event["event_id"]): normalized(event) for event in after.get("events", [])}, "event_migration_verification_failed"
    assert original.get("tasks", []) == after.get("tasks", []), "task_migration_verification_failed"
    for key, value in original.items():
        if key not in {"schema_version", "events", "tasks"}:
            assert after.get(key) == value, f"metadata_migration_verification_failed:{key}"
    # The UI index remains a derived projection of the small manifest.
    from app.services.jiangsu_smart_event import JiangsuSmartEventService
    service = JiangsuSmartEventService(data_root=resolve_agent_path(data_root))
    service._write_list_index(packages.read_manifest(), service._store_revision())
    return {"events_verified": len(before), "tasks_verified": len(after.get("tasks", [])),
            "old_manifest_bytes": old_size, "new_manifest_bytes": packages.path.stat().st_size,
            "backups": [format_agent_path(path) for path in (packages.root / "legacy-backups").glob("*.json")]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", required=True)
    args = parser.parse_args()
    print(json.dumps(migrate(args.data_root), ensure_ascii=False))
