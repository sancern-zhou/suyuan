"""Per-event immutable packages with an atomic, small manifest commit."""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import shutil
import tempfile
from copy import deepcopy
from pathlib import Path
from uuid import uuid4

from app.utils.path_config import format_agent_path, resolve_agent_path

SCHEMA = "jiangsu_smart_events/v2"
EVIDENCE_INDEX_NAME = "index.json"
EVIDENCE_SOURCES_DIRNAME = "sources"
HEAVY_FIELDS = {"evidence", "evidence_package", "judgment_history", "operation_records"}
EVIDENCE_STUB_FIELDS = {
    "event_id", "schema_version", "package_version", "status", "collected_at",
    "profile", "gaps", "source_status", "missing_sources", "required_sources",
    "detected_clue_tags", "system_assessment",
    "ai_judgment", "judgment_status", "judgment_updated_at", "ai_structured_judgment",
}


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode()


def _fsync_directory(path: Path) -> None:
    # Linux 上 fsync 目录句柄保证 rename 持久化；Windows 没有 O_DIRECTORY 也无法
    # 按目录句柄 fsync，持久性由 os.replace 自身保证，直接跳过。
    if not hasattr(os, "O_DIRECTORY"):
        return
    directory_fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def atomic_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(encoded(value))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(name, path)
        _fsync_directory(path.parent)
    finally:
        Path(name).unlink(missing_ok=True)


def source_file_name(name: str) -> str:
    safe = re.sub(r"[^0-9A-Za-z_.-]", "_", str(name)) or "source"
    return f"{safe}.json"


def split_package(package: dict) -> tuple[dict, dict]:
    """把证据包拆成轻量 index 与按来源分文件的 data 负载。

    每个来源的 `data` 单独落盘，index 只保留 status/summary/record_count/
    metadata 等索引字段，Agent 可先读 index 再按需打开单个来源文件。
    """
    index: dict = {}
    source_data: dict = {}
    for key, value in package.items():
        if key == "sources" and isinstance(value, dict):
            index["sources"] = {}
            for name, source in value.items():
                if isinstance(source, dict) and "data" in source:
                    index["sources"][name] = {k: v for k, v in source.items() if k != "data"}
                    source_data[name] = source["data"]
                else:
                    index["sources"][name] = source
        else:
            index[key] = value
    return index, source_data


def write_package_dir(folder: Path, package: dict) -> Path:
    """Content-addressed evidence directory: index.json + sources/<name>.json."""
    package = dict(package)
    package.pop("persisted_path", None)
    digest = hashlib.sha256(encoded(package)).hexdigest()
    dir_path = folder / f"evidence-{digest}"
    index, source_data = split_package(package)
    index_path = dir_path / EVIDENCE_INDEX_NAME
    index["persisted_path"] = format_agent_path(index_path)
    if not index_path.exists():
        atomic_json(index_path, index)
    for name, data in source_data.items():
        source_path = dir_path / EVIDENCE_SOURCES_DIRNAME / source_file_name(name)
        if not source_path.exists():
            atomic_json(source_path, {
                "event_id": package.get("event_id"),
                "source": name,
                "data": data,
            })
    return index_path


def read_package_file(path: Path) -> dict:
    package = json.loads(path.read_text(encoding="utf-8"))
    if path.name != EVIDENCE_INDEX_NAME:
        return package
    sources_dir = path.parent / EVIDENCE_SOURCES_DIRNAME
    sources = package.get("sources")
    if isinstance(sources, dict) and sources_dir.is_dir():
        for name, source in list(sources.items()):
            if not isinstance(source, dict) or "data" in source:
                continue
            source_path = sources_dir / source_file_name(name)
            if source_path.exists():
                payload = json.loads(source_path.read_text(encoding="utf-8"))
                sources[name] = {**source, "data": payload.get("data")}
    return package


class EventReference(dict):
    """An unselected event: metadata only, retained without reading its package."""
    pass


class StoreSnapshot(dict):
    def __init__(self, value, base):
        super().__init__(value)
        self.base = deepcopy(base)

    def update(self, *args, **kwargs):
        if args and isinstance(args[0], StoreSnapshot):
            self.base = deepcopy(args[0].base)
        super().update(*args, **kwargs)


class EventStoreConflict(RuntimeError):
    pass


class JiangsuEventPackages:
    def __init__(self, manifest_path: Path):
        self.path = manifest_path
        self.root = manifest_path.parent

    def read_manifest(self):
        if not self.path.exists():
            return {"schema_version": SCHEMA, "events": [], "tasks": []}
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _package_path(self, reference: str, event_id: str) -> Path:
        path = resolve_agent_path(reference)
        event_root = self.root / "events" / hashlib.sha256(str(event_id).encode()).hexdigest()[:24]
        if not path.resolve().is_relative_to(event_root.resolve()):
            raise ValueError("smart_event_package_outside_event_directory")
        return path

    def read_evidence_package(self, reference: str, event_id: str) -> dict:
        """Read a full evidence package back from its immutable store.

        支持两种布局：分文件目录（index.json + sources/）与旧的单文件 JSON。
        """
        package = read_package_file(self._package_path(reference, event_id))
        if str(package.get("event_id")) != str(event_id):
            raise ValueError("smart_event_evidence_identity_mismatch")
        return package

    def read_event(self, row):
        event_id = str(row["event_id"])
        detail = json.loads(self._package_path(row["_detail_ref"], event_id).read_text(encoding="utf-8"))
        if str(detail.get("event_id")) != event_id:
            raise ValueError("smart_event_detail_identity_mismatch")
        reference = detail.pop("_evidence_ref", None)
        if reference:
            detail["evidence_package"] = self.read_evidence_package(reference, event_id)
        return detail

    def load(self, event_ids=None):
        manifest = self.read_manifest()
        if manifest.get("schema_version") != SCHEMA:
            return manifest
        value = {**manifest, "tasks": deepcopy(manifest.get("tasks", [])), "events": []}
        for row in manifest.get("events", []):
            if event_ids is None or str(row["event_id"]) in event_ids:
                value["events"].append(self.read_event(row))
            else:
                value["events"].append(EventReference(deepcopy(row)))
        return StoreSnapshot(value, manifest)

    def write_event(self, event):
        detail = dict(event)
        detail.pop("_detail_ref", None)
        event_id = str(detail["event_id"])
        folder = self.root / "events" / hashlib.sha256(event_id.encode()).hexdigest()[:24]
        package = detail.pop("evidence_package", None)
        evidence = dict(detail.get("evidence") or {})
        legacy_package = evidence.pop("package", None)
        if "evidence" in detail:
            detail["evidence"] = evidence
        if package is None:
            package = legacy_package
        if package is None:
            package = {"event_id": event_id, "status": "missing", "sources": {},
                       "gaps": [{"source": "collector", "reason": "evidence_not_collected"}]}
        if isinstance(package, dict):
            package = dict(package)
            if package.get("event_id") not in (None, event_id):
                raise ValueError("smart_event_evidence_identity_mismatch")
            package["event_id"] = event_id
            path = write_package_dir(folder, package)
            detail["_evidence_ref"] = format_agent_path(path)
            if isinstance(event.get("evidence_package"), dict):
                event["evidence_package"]["persisted_path"] = format_agent_path(path)
        digest = hashlib.sha256(encoded(detail)).hexdigest()
        path = folder / f"detail-{digest}.json"
        if not path.exists():
            atomic_json(path, detail)
        row = {key: value for key, value in detail.items() if key not in HEAVY_FIELDS | {"_evidence_ref"}}
        row["_detail_ref"] = format_agent_path(path)
        return row

    def write_evidence_only(self, event):
        """Persist the heavy evidence package to its immutable file and replace
        the in-event package with a lightweight stub. Used by DB-primary mode."""
        package = event.get("evidence_package")
        if not isinstance(package, dict):
            return
        if "sources" not in package and package.get("persisted_path"):
            return
        event_id = str(event["event_id"])
        folder = self.root / "events" / hashlib.sha256(event_id.encode()).hexdigest()[:24]
        package = dict(package)
        package.pop("persisted_path", None)
        package.setdefault("event_id", event_id)
        path = write_package_dir(folder, package)
        reference = format_agent_path(path)
        event["evidence_package"] = {
            **{key: package[key] for key in EVIDENCE_STUB_FIELDS if key in package},
            "persisted_path": reference,
        }

    @staticmethod
    def _merge_rows(base_rows, proposed_rows, current_rows, key):
        def identity(row):
            return str(row[key]) if key in row else "unkeyed:" + hashlib.sha256(encoded(row)).hexdigest()
        base = {identity(row): row for row in base_rows}
        proposed = {identity(row): row for row in proposed_rows}
        current = {identity(row): row for row in current_rows}
        for identity in dict.fromkeys([*base, *proposed]):
            old, new = base.get(identity), proposed.get(identity)
            if old == new:
                continue
            if current.get(identity) not in (old, new):
                raise EventStoreConflict(f"concurrent_smart_event_update:{identity}")
            if new is None:
                current.pop(identity, None)
            else:
                current[identity] = new
        return list(current.values())

    def save(self, store):
        self.root.mkdir(parents=True, exist_ok=True)
        rows = []
        for event in store.get("events", []):
            if isinstance(event, EventReference):
                base_row = next((r for r in store.base.get("events", []) if r["event_id"] == event["event_id"]), None)
                if event == base_row:
                    rows.append(dict(event))
                    continue
                detail = self.read_event(base_row)
                detail.update({k: v for k, v in event.items() if k != "_detail_ref"})
                rows.append(self.write_event(detail))
            else:
                rows.append(self.write_event(event))
        proposed = {**store, "schema_version": SCHEMA, "events": rows}
        # Only the small manifest is locked. Packages are immutable and published first.
        with (self.root / ".store.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            current = self.read_manifest()
            if current.get("schema_version") != SCHEMA and self.path.exists():
                backup = self.root / "legacy-backups" / f"store-{uuid4().hex}.json"
                backup.parent.mkdir(exist_ok=True)
                shutil.copy2(self.path, backup)
            if isinstance(store, StoreSnapshot):
                merged = dict(current)
                for key, value in proposed.items():
                    if key not in {"events", "tasks"} and value != store.base.get(key):
                        merged[key] = value
                merged["events"] = self._merge_rows(store.base.get("events", []), rows, current.get("events", []), "event_id")
                merged["tasks"] = self._merge_rows(store.base.get("tasks", []), proposed.get("tasks", []), current.get("tasks", []), "task_id")
                proposed = merged
            atomic_json(self.path, proposed)
            stat = self.path.stat()
            self.last_revision = [stat.st_ino, stat.st_size, stat.st_mtime_ns]
            if isinstance(store, StoreSnapshot):
                saved_rows = {row["event_id"]: row for row in rows}
                local_events = {item["event_id"]: item for item in store.get("events", [])}
                store["events"] = [local_events[row["event_id"]]
                                   if row == saved_rows.get(row["event_id"])
                                   else EventReference(deepcopy(row))
                                   for row in proposed["events"]]
                store["tasks"] = deepcopy(proposed.get("tasks", []))
                store.base = deepcopy(proposed)
            return proposed
