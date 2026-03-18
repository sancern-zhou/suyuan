from __future__ import annotations

import json
import threading
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence
from uuid import uuid4

import structlog

from app.schemas.common import DataQualityReport, FieldStats
from config.settings import settings

logger = structlog.get_logger()


@dataclass
class DataRegistryEntry:
    data_id: str
    schema: str
    version: str
    record_count: int
    sample_path: Path
    dataset_path: Path
    quality_report: Optional[Dict[str, Any]]
    field_stats: Optional[List[Dict[str, Any]]]
    metadata: Dict[str, Any]
    created_at: datetime

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["created_at"] = self.created_at.isoformat()
        payload["dataset_path"] = str(self.dataset_path)
        payload["sample_path"] = str(self.sample_path)
        return payload


class DataRegistryService:
    """Persistent registry for structured datasets."""

    def __init__(self, base_dir: Optional[str] = None) -> None:
        default_dir = Path(settings.data_registry_dir)
        if not default_dir.is_absolute():
            project_root = Path(__file__).resolve().parents[2]
            default_dir = project_root / default_dir

        base_path = Path(base_dir) if base_dir else default_dir

        self.base_dir = base_path
        self.datasets_dir = self.base_dir / "datasets"
        self.samples_dir = self.base_dir / "samples"
        self.metadata_path = self.base_dir / "registry.jsonl"
        self._lock = threading.Lock()
        self._index: Dict[str, DataRegistryEntry] = {}

        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.datasets_dir.mkdir(parents=True, exist_ok=True)
        self.samples_dir.mkdir(parents=True, exist_ok=True)
        if self.metadata_path.exists():
            self._load_metadata()

        logger.info(
            "data_registry_initialized",
            base_dir=str(self.base_dir),
            entries=len(self._index),
        )

    def register_dataset(
        self,
        schema: str,
        version: str,
        records: Sequence[Dict[str, Any]],
        *,
        quality_report: Optional[DataQualityReport] = None,
        field_stats: Optional[Iterable[FieldStats]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        sample_size: int = 20,
        data_id: Optional[str] = None,
    ) -> DataRegistryEntry:
        """Register a dataset and persist both full data and sampling preview."""

        sample_records = list(records[:sample_size])
        # ✅ 修复：接受外部传入的 data_id，避免重复生成导致 ID 不匹配
        if data_id is None:
            data_id = f"{schema}:{version}:{uuid4().hex}"
        else:
            # ✅ 从 data_id 中提取 schema 和 version（优先使用 data_id 中的）
            parts = data_id.split(":")
            if len(parts) >= 3:
                schema = parts[0]
                version = parts[1]
        safe_id = self._sanitize_identifier(data_id)
        dataset_path = self.datasets_dir / f"{safe_id}.json"
        sample_path = self.samples_dir / f"{safe_id}.json"

        with dataset_path.open("w", encoding="utf-8") as f:
            json.dump(records, f, ensure_ascii=False, indent=2, default=str)

        with sample_path.open("w", encoding="utf-8") as f:
            json.dump(
                {
                    "schema": schema,
                    "version": version,
                    "sample": sample_records,
                },
                f,
                ensure_ascii=False,
                indent=2,
                default=str,
            )

        entry = DataRegistryEntry(
            data_id=data_id,
            schema=schema,
            version=version,
            record_count=len(records),
            dataset_path=dataset_path,
            sample_path=sample_path,
            quality_report=quality_report.dict() if quality_report else None,
            field_stats=[stat.dict() for stat in field_stats]
            if field_stats
            else None,
            metadata=metadata or {},
            created_at=datetime.utcnow(),
        )

        with self._lock:
            self._index[data_id] = entry
            with self.metadata_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(entry.to_dict(), ensure_ascii=False, default=str))
                f.write("\n")

        logger.info(
            "dataset_registered",
            data_id=data_id,
            schema=schema,
            version=version,
            records=len(records),
        )

        return entry

    def get_metadata(self, data_id: str) -> Optional[DataRegistryEntry]:
        return self._index.get(data_id)

    def load_sample(self, data_id: str) -> List[Dict[str, Any]]:
        entry = self._require_entry(data_id)
        with entry.sample_path.open("r", encoding="utf-8") as f:
            payload = json.load(f)
        return payload.get("sample", [])

    def load_dataset(self, data_id: str) -> Sequence[Dict[str, Any]]:
        entry = self._require_entry(data_id)
        with entry.dataset_path.open("r", encoding="utf-8") as f:
            payload = json.load(f)
        return payload.get("records", [])

    def _load_metadata(self) -> None:
        with self.metadata_path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                payload = json.loads(line)
                entry = DataRegistryEntry(
                    data_id=payload["data_id"],
                    schema=payload["schema"],
                    version=payload["version"],
                    record_count=payload["record_count"],
                    dataset_path=Path(payload["dataset_path"]),
                    sample_path=Path(payload["sample_path"]),
                    quality_report=payload.get("quality_report"),
                    field_stats=payload.get("field_stats"),
                    metadata=payload.get("metadata") or {},
                    created_at=datetime.fromisoformat(payload["created_at"]),
                )
                self._index[entry.data_id] = entry

    def _require_entry(self, data_id: str) -> DataRegistryEntry:
        entry = self._index.get(data_id)
        if not entry:
            raise KeyError(f"data_id {data_id} not found in registry")
        return entry

    @staticmethod
    def _sanitize_identifier(identifier: str) -> str:
        """Convert an arbitrary identifier into a filesystem-safe name."""

        unsafe_chars = {":", "/", "\\", "*", "?", "\"", "<", ">", "|"}
        result = []
        for char in identifier:
            if char in unsafe_chars:
                result.append("_")
            else:
                result.append(char)
        return "".join(result)


data_registry = DataRegistryService()

__all__ = ["data_registry", "DataRegistryService", "DataRegistryEntry"]
