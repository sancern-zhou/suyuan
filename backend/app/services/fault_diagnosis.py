from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import structlog


logger = structlog.get_logger()


TZ_SHANGHAI = ZoneInfo("Asia/Shanghai")


@dataclass(frozen=True)
class PendingFaultConclusion:
    event_id: str
    conclusion_path: Path
    evidence_pack_path: Path
    event_dir: Path


class FaultDiagnosisService:
    def __init__(self, output_root: str | Path | None = None) -> None:
        self.output_root = Path(output_root or self._default_output_root()).resolve()

    def run(self, *, limit: int = 20) -> dict[str, Any]:
        pending = self.discover_pending(limit=limit)
        results = [self.process_conclusion(item.conclusion_path) for item in pending]
        return {
            "success": True,
            "processed_count": len(results),
            "pending_count": len(pending),
            "items": results,
            "output_root": str(self.output_root),
        }

    def discover_pending(self, *, limit: int | None = None) -> list[PendingFaultConclusion]:
        if not self.output_root.exists():
            return []

        items: list[PendingFaultConclusion] = []
        for conclusion_path in sorted(self.output_root.rglob("event_conclusion.json")):
            conclusion = self._read_json(conclusion_path)
            if not self._requires_fault_diagnosis(conclusion):
                continue
            event_dir = conclusion_path.parent
            if self._is_processed(event_dir, conclusion_path):
                continue
            evidence_pack_path = self._evidence_pack_path(conclusion, event_dir)
            if not evidence_pack_path.exists():
                continue
            items.append(
                PendingFaultConclusion(
                    event_id=str(conclusion.get("event_id") or event_dir.name),
                    conclusion_path=conclusion_path,
                    evidence_pack_path=evidence_pack_path,
                    event_dir=event_dir,
                )
            )
            if limit is not None and len(items) >= limit:
                break
        return items

    def process_conclusion(self, conclusion_path: str | Path) -> dict[str, Any]:
        path = Path(conclusion_path).resolve()
        conclusion = self._read_json(path)
        event_dir = path.parent
        evidence_pack_path = self._evidence_pack_path(conclusion, event_dir)
        evidence_pack = self._read_json(evidence_pack_path) if evidence_pack_path.exists() else {}
        output_dir = event_dir / "fault_diagnosis"
        output_dir.mkdir(parents=True, exist_ok=True)

        cognitive_guidance = self._cognitive_guidance(conclusion, evidence_pack)
        diagnosis = self._build_diagnosis(conclusion, evidence_pack, evidence_pack_path, cognitive_guidance)
        evidence_output = self._build_fault_evidence_pack(conclusion, evidence_pack, diagnosis, evidence_pack_path)
        self._write_json(output_dir / "fault_diagnosis.json", diagnosis)
        self._write_json(output_dir / "fault_evidence_pack.json", evidence_output)
        (output_dir / "fault_diagnosis.md").write_text(self._markdown(diagnosis), encoding="utf-8")
        self._mark_processed(path)
        manifest = {
            "schema_version": "fault_diagnosis_manifest/v1",
            "event_id": diagnosis["event_id"],
            "source_event_conclusion": str(path),
            "source_checksum": self._sha256(path),
            "fault_diagnosis": str(output_dir / "fault_diagnosis.json"),
            "fault_evidence_pack": str(output_dir / "fault_evidence_pack.json"),
            "fault_diagnosis_md": str(output_dir / "fault_diagnosis.md"),
            "created_at": diagnosis["created_at"],
        }
        self._write_json(output_dir / "diagnosis_manifest.json", manifest)
        return diagnosis

    def _build_diagnosis(
        self,
        conclusion: dict[str, Any],
        evidence_pack: dict[str, Any],
        evidence_pack_path: Path,
        cognitive_guidance: dict[str, Any],
    ) -> dict[str, Any]:
        event = evidence_pack.get("event") if isinstance(evidence_pack.get("event"), dict) else {}
        reason_codes = list(conclusion.get("reason_codes") or [])
        event_id = str(conclusion.get("event_id") or event.get("event_id") or "")
        time_range = dict(conclusion.get("time_range") or event.get("time_range") or {})
        cause = self._ranked_cause(reason_codes, evidence_pack)
        created_at = datetime.now(TZ_SHANGHAI).isoformat()
        return {
            "schema_version": "fault_diagnosis/v1",
            "source_event_conclusion": str(Path(evidence_pack_path).with_name("event_conclusion.json")),
            "event_id": event_id,
            "diagnosis_status": "completed",
            "diagnosis_window": time_range,
            "cognitive_map": cognitive_guidance,
            "most_likely_causes": [cause],
            "queried_data": self._queried_data(evidence_pack, cognitive_guidance),
            "summary": self._diagnosis_summary(cause),
            "created_at": created_at,
        }

    def _build_fault_evidence_pack(
        self,
        conclusion: dict[str, Any],
        evidence_pack: dict[str, Any],
        diagnosis: dict[str, Any],
        evidence_pack_path: Path,
    ) -> dict[str, Any]:
        return {
            "schema_version": "fault_evidence_pack/v1",
            "event_id": diagnosis["event_id"],
            "source_evidence_pack": str(evidence_pack_path),
            "source_event_conclusion": str(evidence_pack_path.with_name("event_conclusion.json")),
            "classification_reason_codes": conclusion.get("reason_codes", []),
            "event_summary": evidence_pack.get("event_summary", {}),
            "observed_signal_summary": evidence_pack.get("observed_signal_summary", {}),
            "fetch_errors": evidence_pack.get("fetch_errors", []),
            "diagnosis_summary": diagnosis.get("summary"),
            "created_at": diagnosis["created_at"],
        }

    def _ranked_cause(self, reason_codes: list[str], evidence_pack: dict[str, Any]) -> dict[str, Any]:
        codes = set(reason_codes)
        supporting: list[str] = []
        missing: list[str] = []
        cause = "站点数据链路异常"
        cause_type = "data_quality"
        action = "核查站点小时数据、数采状态和同城站点对比。"

        if "pm_cochange_weak" in codes:
            cause = "采样系统或颗粒物监测链路异常"
            cause_type = "device_or_facility"
            supporting.append("PM2.5 与 PM10 协同关系偏弱")
            missing.append("采样流量、切割头、采样管路和颗粒物仪器维护记录")
            action = "优先核查采样流量、采样管路、切割头和颗粒物监测仪运行状态。"
        if "single_station_dominant" in codes:
            supporting.append("污染事件由单站或少数站点主导")
        if "peer_trend_inconsistent" in codes:
            supporting.append("同城站点未出现同步变化")
        if "no2_o3_pattern_weak" in codes:
            cause = "气态分析仪或校准链路异常"
            cause_type = "device_or_facility"
            supporting.append("NO2 与 O3 关系不符合常见反向变化特征")
            missing.append("气态分析仪校准、零跨检查和质控记录")
            action = "核查气态分析仪状态、校准记录、零跨检查和采样系统。"

        if not supporting:
            supporting.append("一级结论已标记为疑似设备或数据故障")
        if not missing:
            missing.append("近期运维工单、质控记录和设备状态")

        return {
            "cause": cause,
            "cause_type": cause_type,
            "confidence": "medium" if len(supporting) >= 2 else "low",
            "supporting_evidence": supporting,
            "contradicting_evidence": [],
            "missing_evidence": missing,
            "recommended_action": action,
        }

    def _queried_data(self, evidence_pack: dict[str, Any], cognitive_guidance: dict[str, Any]) -> list[dict[str, Any]]:
        data_files = evidence_pack.get("data_files") if isinstance(evidence_pack.get("data_files"), dict) else {}
        queried = []
        for name, path in sorted(data_files.items()):
            queried.append({"name": name, "status": "referenced", "path": path})
        for requirement in cognitive_guidance.get("data_requirements", []) or []:
            queried.append(
                {
                    "name": requirement.get("data_name") or requirement.get("name") or "cognitive_map_requirement",
                    "status": "required_by_cognitive_map",
                    "path": "",
                    "reason": requirement.get("reason", ""),
                }
            )
        return queried

    def _entity_hints(self, conclusion: dict[str, Any], evidence_pack: dict[str, Any]) -> list[str]:
        event = evidence_pack.get("event") if isinstance(evidence_pack.get("event"), dict) else {}
        hints = [
            conclusion.get("city") or evidence_pack.get("city"),
            conclusion.get("main_pollutant") or event.get("main_pollutant"),
        ]
        signal = evidence_pack.get("observed_signal_summary")
        if isinstance(signal, dict):
            hints.extend(signal.get("dominant_station_names") or [])
        return [str(hint) for hint in hints if hint]

    def _diagnosis_summary(self, cause: dict[str, Any]) -> str:
        return f"疑似故障首要原因：{cause['cause']}；建议：{cause['recommended_action']}"

    def _cognitive_guidance(self, conclusion: dict[str, Any], evidence_pack: dict[str, Any]) -> dict[str, Any]:
        hints = self._entity_hints(conclusion, evidence_pack)
        fallback = {
            "used": False,
            "map_ids": [],
            "entity_hints": hints,
            "analysis_directions": [],
            "data_requirements": [],
            "suggested_tools": [],
        }
        try:
            from app.api.cognitive_map_routes import (
                CognitiveMapGraphQueryRequest,
                _build_graph_query_view,
                _enabled_binding_map_ids,
                _load_json,
                _meta_path,
            )
            from app.tools.analysis.cognitive_map_guidance.tool import build_guidance_from_views
        except Exception as exc:
            logger.warning("fault_diagnosis_cognitive_import_failed", error=str(exc))
            fallback["fallback_reason"] = "cognitive_map_import_failed"
            return fallback

        map_ids = _enabled_binding_map_ids("ops")
        if not map_ids:
            fallback["fallback_reason"] = "no_enabled_ops_cognitive_map"
            return fallback

        views: list[dict[str, Any]] = []
        sources: dict[str, str] = {}
        task = "污染告警疑似设备或数据故障原因诊断"
        for map_id in map_ids[:5]:
            try:
                payload = CognitiveMapGraphQueryRequest(
                    task=task,
                    agent_mode="ops",
                    entity_hints=hints,
                    depth=2,
                    limit=30,
                    max_entities=30,
                    max_relations=50,
                )
                view, source = _build_graph_query_view(map_id, payload)
            except Exception as exc:
                logger.warning("fault_diagnosis_cognitive_view_failed", map_id=map_id, error=str(exc))
                continue
            item = view.model_dump(mode="json")
            meta = _load_json(_meta_path(map_id), {})
            item["map_name"] = meta.get("name") or map_id
            item["source"] = source
            views.append(item)
            sources[map_id] = source

        guidance = build_guidance_from_views(views=views, task=task, agent_mode="ops")
        return {
            "used": bool(guidance.get("matched")),
            "map_ids": map_ids,
            "entity_hints": hints,
            "analysis_directions": guidance.get("analysis_directions", []),
            "data_requirements": guidance.get("data_requirements", []),
            "suggested_tools": guidance.get("suggested_tools", []),
            "sources": sources,
            "fallback_reason": "" if guidance.get("matched") else "no_graph_matches",
        }

    def _requires_fault_diagnosis(self, conclusion: dict[str, Any]) -> bool:
        downstream = conclusion.get("downstream") if isinstance(conclusion.get("downstream"), dict) else {}
        return (
            conclusion.get("classification") == "suspected_device_or_data_fault"
            and downstream.get("requires_fault_diagnosis") is True
        )

    def _is_processed(self, event_dir: Path, conclusion_path: Path) -> bool:
        manifest_path = event_dir / "fault_diagnosis" / "diagnosis_manifest.json"
        if not manifest_path.exists():
            return False
        manifest = self._read_json(manifest_path)
        checksum = manifest.get("source_checksum")
        if not checksum:
            return True
        return checksum == self._sha256(conclusion_path)

    def _mark_processed(self, conclusion_path: Path) -> None:
        conclusion = self._read_json(conclusion_path)
        downstream = conclusion.setdefault("downstream", {})
        if isinstance(downstream, dict):
            downstream["processed_by_fault_diagnosis"] = True
            downstream["processed_at"] = datetime.now(TZ_SHANGHAI).isoformat()
        self._write_json(conclusion_path, conclusion)

    def _evidence_pack_path(self, conclusion: dict[str, Any], event_dir: Path) -> Path:
        raw = conclusion.get("source_evidence_pack")
        if raw:
            return Path(str(raw)).expanduser().resolve()
        return event_dir / "evidence_pack.json"

    def _markdown(self, diagnosis: dict[str, Any]) -> str:
        lines = [
            "# 疑似故障原因诊断",
            "",
            f"- 事件ID：{diagnosis.get('event_id', '')}",
            f"- 诊断状态：{diagnosis.get('diagnosis_status', '')}",
            f"- 结论摘要：{diagnosis.get('summary', '')}",
            "",
            "## 可能原因",
            "",
        ]
        for item in diagnosis.get("most_likely_causes", []):
            lines.append(f"- {item.get('cause')}（置信度：{item.get('confidence')}）")
            lines.append(f"  - 建议：{item.get('recommended_action')}")
        return "\n".join(lines) + "\n"

    def _read_json(self, path: Path) -> dict[str, Any]:
        return json.loads(path.read_text(encoding="utf-8"))

    def _write_json(self, path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _sha256(self, path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def _default_output_root(self) -> Path:
        return Path(__file__).resolve().parents[2] / "backend_data_registry" / "pollution_process_events"
