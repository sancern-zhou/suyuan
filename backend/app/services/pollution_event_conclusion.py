from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


TZ_SHANGHAI = ZoneInfo("Asia/Shanghai")


class EventConclusionClassification(StrEnum):
    NORMAL_POLLUTION = "normal_pollution"
    SUSPECTED_DEVICE_OR_DATA_FAULT = "suspected_device_or_data_fault"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


@dataclass
class EventConclusion:
    event_id: str
    city: str
    main_pollutant: str
    time_range: dict[str, Any]
    classification: EventConclusionClassification
    classification_confidence: str
    reason_codes: list[str]
    summary: str
    evidence_refs: list[dict[str, Any]]
    downstream: dict[str, Any]
    source_evidence_pack: str
    created_at: str = field(default_factory=lambda: datetime.now(TZ_SHANGHAI).isoformat())

    def to_payload(self) -> dict[str, Any]:
        return {
            "schema_version": "pollution_event_conclusion/v1",
            "event_id": self.event_id,
            "city": self.city,
            "main_pollutant": self.main_pollutant,
            "time_range": self.time_range,
            "classification": self.classification.value,
            "classification_confidence": self.classification_confidence,
            "reason_codes": self.reason_codes,
            "summary": self.summary,
            "evidence_refs": self.evidence_refs,
            "downstream": self.downstream,
            "source_evidence_pack": self.source_evidence_pack,
            "created_at": self.created_at,
        }


class PollutionEventConclusionService:
    def write_conclusion(self, evidence_pack_path: str | Path) -> EventConclusion:
        path = Path(evidence_pack_path).resolve()
        pack = json.loads(path.read_text(encoding="utf-8"))
        conclusion = self.classify(pack, source_evidence_pack=str(path))
        output_path = path.with_name("event_conclusion.json")
        output_path.write_text(
            json.dumps(conclusion.to_payload(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return conclusion

    def classify(self, evidence_pack: dict[str, Any], *, source_evidence_pack: str = "") -> EventConclusion:
        event = evidence_pack.get("event") or {}
        reason_codes = self._reason_codes(evidence_pack)
        classification = self._classification(reason_codes)
        confidence = self._confidence(classification, reason_codes)
        requires_fault = classification == EventConclusionClassification.SUSPECTED_DEVICE_OR_DATA_FAULT
        return EventConclusion(
            event_id=str(event.get("event_id") or evidence_pack.get("event_id") or ""),
            city=str(evidence_pack.get("city") or event.get("city") or ""),
            main_pollutant=str(event.get("main_pollutant") or evidence_pack.get("main_pollutant") or ""),
            time_range=dict(event.get("time_range") or evidence_pack.get("time_range") or {}),
            classification=classification,
            classification_confidence=confidence,
            reason_codes=reason_codes,
            summary=self._summary(classification, reason_codes, evidence_pack),
            evidence_refs=[
                {
                    "type": "file",
                    "path": source_evidence_pack or "evidence_pack.json",
                    "description": "污染事件原始证据包",
                }
            ],
            downstream={
                "requires_fault_diagnosis": requires_fault,
                "processed_by_fault_diagnosis": False,
            },
            source_evidence_pack=source_evidence_pack,
        )

    def _reason_codes(self, pack: dict[str, Any]) -> list[str]:
        event_summary = pack.get("event_summary") if isinstance(pack.get("event_summary"), dict) else {}
        signal = pack.get("observed_signal_summary") if isinstance(pack.get("observed_signal_summary"), dict) else {}
        quality_gate = pack.get("quality_gate") if isinstance(pack.get("quality_gate"), dict) else {}
        data_quality = pack.get("data_quality") if isinstance(pack.get("data_quality"), dict) else {}
        fetch_errors = pack.get("fetch_errors") if isinstance(pack.get("fetch_errors"), list) else []
        event = pack.get("event") if isinstance(pack.get("event"), dict) else {}
        main_pollutant = str(
            event.get("main_pollutant")
            or event_summary.get("main_pollutant")
            or signal.get("main_pollutant")
            or ""
        )
        codes: list[str] = []

        station_count = self._as_int(event_summary.get("station_count"))
        station_peaks = self._as_list(event_summary.get("station_peaks") or signal.get("top_station_peaks"))
        if station_count is None and station_peaks:
            station_count = len(station_peaks)
        record_counts = event_summary.get("record_counts") if isinstance(event_summary.get("record_counts"), dict) else {}
        if station_count is None and self._as_int(record_counts.get("station_hour")) == 0:
            station_count = 0
        if station_count is not None and station_count < 3:
            codes.append("station_hour_missing" if station_count == 0 else "too_few_peer_stations")

        if any(str(error.get("source")) == "station_hour" for error in fetch_errors if isinstance(error, dict)):
            codes.append("station_hour_missing")

        dominant = self._as_int(event_summary.get("dominant_station_count"))
        if dominant is None and station_peaks:
            dominant = self._dominant_station_count(station_peaks)
        if dominant == 1:
            codes.append("single_station_dominant")

        if event_summary.get("peer_trend_consistent") is False:
            codes.append("peer_trend_inconsistent")

        relationships = signal.get("pollutant_relationships") if isinstance(signal.get("pollutant_relationships"), dict) else {}
        if relationships.get("pm_cochange") == "weak":
            codes.append("pm_cochange_weak")
        if relationships.get("no2_o3_inverse") == "weak":
            codes.append("no2_o3_pattern_weak")
        cochange = self._as_list(event_summary.get("cochange") or signal.get("cochange"))
        codes.extend(self._cochange_reason_codes(main_pollutant, cochange))

        if quality_gate.get("status") in {"failed", "limited"} or self._as_int(quality_gate.get("high_issue_count")):
            codes.append("quality_gate_limited")
        if self._has_main_pollutant_constant_issue(main_pollutant, quality_gate, data_quality, event, pack):
            codes.append("main_pollutant_constant_streak")
        if self._has_issue_type(quality_gate, data_quality, "weather_missing"):
            codes.append("weather_missing")

        if signal.get("meteorology_supports_accumulation") is True:
            codes.append("meteorology_supports_pollution")
        if signal.get("regional_signal") == "coherent":
            codes.append("regional_signal_coherent")
        if dominant is not None and dominant >= 2:
            codes.append("multi_station_coherent")

        return sorted(set(codes))

    def _classification(self, reason_codes: list[str]) -> EventConclusionClassification:
        codes = set(reason_codes)
        fault = {
            "peer_trend_inconsistent",
            "pm_cochange_weak",
            "main_pollutant_constant_streak",
        }
        normal = {
            "multi_station_coherent",
            "meteorology_supports_pollution",
            "regional_signal_coherent",
            "pm_cochange_supported",
            "no2_o3_inverse_supported",
        }
        if "station_hour_missing" in codes:
            return EventConclusionClassification.INSUFFICIENT_EVIDENCE
        if codes & fault:
            return EventConclusionClassification.SUSPECTED_DEVICE_OR_DATA_FAULT
        if codes & normal:
            return EventConclusionClassification.NORMAL_POLLUTION
        if "no2_o3_pattern_weak" in codes:
            return EventConclusionClassification.INSUFFICIENT_EVIDENCE
        return EventConclusionClassification.INSUFFICIENT_EVIDENCE

    def _confidence(self, classification: EventConclusionClassification, reason_codes: list[str]) -> str:
        if classification == EventConclusionClassification.INSUFFICIENT_EVIDENCE:
            return "low"
        return "medium" if len(reason_codes) >= 2 else "low"

    def _summary(
        self,
        classification: EventConclusionClassification,
        reason_codes: list[str],
        pack: dict[str, Any],
    ) -> str:
        city = str(pack.get("city") or "")
        event = pack.get("event") or {}
        pollutant = str(event.get("main_pollutant") or "")
        prefix = f"{city}{pollutant}污染告警"
        if classification == EventConclusionClassification.SUSPECTED_DEVICE_OR_DATA_FAULT:
            return f"{prefix}存在疑似设备或数据异常信号：{', '.join(reason_codes)}，需进入故障诊断。"
        if classification == EventConclusionClassification.NORMAL_POLLUTION:
            return f"{prefix}表现为多站或区域一致变化，初步归类为正常污染过程。"
        return f"{prefix}证据不足，暂不能稳定区分真实污染与设备/数据异常。"

    def _as_int(self, value: Any) -> int | None:
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def _as_float(self, value: Any) -> float | None:
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _as_list(self, value: Any) -> list[Any]:
        return value if isinstance(value, list) else []

    def _dominant_station_count(self, station_peaks: list[Any]) -> int | None:
        peak_values = [
            self._as_float(item.get("peak_value"))
            for item in station_peaks
            if isinstance(item, dict)
        ]
        peak_values = [value for value in peak_values if value is not None]
        if not peak_values:
            return None
        top = max(peak_values)
        if top <= 0:
            return None
        return sum(1 for value in peak_values if value >= top * 0.8)

    def _cochange_reason_codes(self, main_pollutant: str, cochange: list[Any]) -> list[str]:
        correlations = {
            str(item.get("pollutant")): self._as_float(item.get("correlation"))
            for item in cochange
            if isinstance(item, dict)
        }
        codes: list[str] = []

        if main_pollutant in {"PM2_5", "PM10"}:
            peer = "PM10" if main_pollutant == "PM2_5" else "PM2_5"
            corr = correlations.get(peer)
            if corr is not None and corr < 0.4:
                codes.append("pm_cochange_weak")
            elif corr is not None and corr >= 0.7:
                codes.append("pm_cochange_supported")

        if main_pollutant in {"NO2", "O3_8h"}:
            peer = "O3_8h" if main_pollutant == "NO2" else "NO2"
            corr = correlations.get(peer)
            if corr is not None and corr > -0.2:
                codes.append("no2_o3_pattern_weak")
            elif corr is not None and corr <= -0.4:
                codes.append("no2_o3_inverse_supported")

        return codes

    def _has_main_pollutant_constant_issue(
        self,
        main_pollutant: str,
        quality_gate: dict[str, Any],
        data_quality: dict[str, Any],
        event: dict[str, Any],
        pack: dict[str, Any],
    ) -> bool:
        if not main_pollutant:
            return False
        has_issue = any(
            issue.get("issue_type") == "long_constant_value"
            and issue.get("pollutant") == main_pollutant
            for issue in self._quality_issues(quality_gate, data_quality)
        )
        if not has_issue:
            return False
        data_files = pack.get("data_files") if isinstance(pack.get("data_files"), dict) else {}
        city_hour_path = data_files.get("city_hour_monitoring")
        if not city_hour_path:
            return True
        return self._constant_streak_overlaps_event(main_pollutant, city_hour_path, event.get("time_range") or {})

    def _constant_streak_overlaps_event(
        self,
        pollutant: str,
        city_hour_path: Any,
        time_range: dict[str, Any],
    ) -> bool:
        start = self._parse_time(time_range.get("start"))
        end = self._parse_time(time_range.get("end"))
        if start is None or end is None:
            return True
        try:
            records = json.loads(Path(str(city_hour_path)).read_text(encoding="utf-8")).get("records", [])
        except Exception:
            return True
        streak: list[datetime] = []
        previous = object()
        for record in sorted(records, key=lambda item: str(item.get("timestamp", "")) if isinstance(item, dict) else ""):
            if not isinstance(record, dict):
                continue
            timestamp = self._parse_time(record.get("timestamp"))
            measurements = record.get("measurements") if isinstance(record.get("measurements"), dict) else record
            value = measurements.get(pollutant)
            if timestamp is None or value is None:
                continue
            if value == previous:
                streak.append(timestamp)
            else:
                if self._streak_overlaps(streak, start, end):
                    return True
                streak = [timestamp]
                previous = value
        return self._streak_overlaps(streak, start, end)

    def _streak_overlaps(self, streak: list[datetime], start: datetime, end: datetime) -> bool:
        if len(streak) < 3:
            return False
        return min(streak) <= end and max(streak) >= start

    def _parse_time(self, value: Any) -> datetime | None:
        if not value:
            return None
        text = str(value).replace("T", " ").split("+", 1)[0]
        try:
            return datetime.fromisoformat(text)
        except ValueError:
            return None
        return False

    def _has_issue_type(
        self,
        quality_gate: dict[str, Any],
        data_quality: dict[str, Any],
        issue_type: str,
    ) -> bool:
        return any(issue.get("issue_type") == issue_type for issue in self._quality_issues(quality_gate, data_quality))

    def _quality_issues(
        self,
        quality_gate: dict[str, Any],
        data_quality: dict[str, Any],
    ) -> list[dict[str, Any]]:
        issues = []
        for item in self._as_list(quality_gate.get("interpretation_limits")):
            if isinstance(item, dict):
                issues.append(item)
        for item in self._as_list(data_quality.get("issues")):
            if isinstance(item, dict):
                issues.append(item)
        return issues
