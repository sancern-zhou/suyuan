"""Convert user supplied tables, reports, and data ids into facts."""

from __future__ import annotations

import re
from typing import Any

from .fact_ledger import FactLedger
from .schemas import DeliberationRequest, FactQuality, FactRecord, TimeRange


KEYWORD_TAGS = {
    "PM2.5": ["PM2.5", "颗粒物", "细颗粒物"],
    "O3": ["O3", "臭氧"],
    "气象": ["气象", "风速", "风向", "降水", "湿度", "温度", "边界层", "静稳", "扩散"],
    "传输": ["传输", "轨迹", "上风向", "区域", "外来", "HYSPLIT"],
    "组分": ["组分", "VOCs", "NOx", "硝酸盐", "硫酸盐", "OC", "EC", "二次生成"],
    "源解析": ["PMF", "源解析", "贡献", "工业", "交通", "扬尘", "燃烧", "排放"],
    "监测": ["监测", "浓度", "同比", "环比", "排名", "AQI", "污染过程"],
}


class FactIngestor:
    def build(self, request: DeliberationRequest) -> FactLedger:
        ledger = FactLedger()
        self._ingest_tables(ledger, request)
        self._ingest_report_text(ledger, request, request.monthly_report_text, "monthly_trace_report")
        self._ingest_report_text(ledger, request, request.stage5_report_text, "stage5_analysis")
        self._ingest_data_ids(ledger, request)
        return ledger

    def _ingest_tables(self, ledger: FactLedger, request: DeliberationRequest) -> None:
        seq = 1
        for table in request.consultation_tables:
            for row_index, row in enumerate(table.rows, start=1):
                statement = self._row_to_statement(row)
                if not statement:
                    continue
                fact = FactRecord(
                    fact_id=f"fact_table_{seq:04d}",
                    source_type=table.source_type or "consultation_table",
                    source_ref={"table": table.name, "row": row_index},
                    time_range=request.time_range,
                    region=request.region,
                    city=self._pick(row, ["city", "城市", "站点"]),
                    pollutant=self._pick(row, ["pollutant", "污染物", "指标"]),
                    fact_type="observation",
                    statement=statement,
                    metrics=self._numeric_metrics(row),
                    method=f"会商表格汇总：{table.name}",
                    quality=FactQuality(completeness="high", temporal_coverage=request.time_range.display or "unknown", confidence=0.85),
                    tags=self._infer_tags(statement),
                )
                ledger.add(fact)
                seq += 1

    def _ingest_report_text(self, ledger: FactLedger, request: DeliberationRequest, text: str, source_type: str) -> None:
        if not text.strip():
            return

        paragraphs = self._split_findings(text)
        start_index = len(ledger.all()) + 1
        for offset, paragraph in enumerate(paragraphs[:80], start=0):
            fact = FactRecord(
                fact_id=f"fact_{source_type}_{start_index + offset:04d}",
                source_type=source_type,
                source_ref={"paragraph_index": offset + 1},
                time_range=request.time_range,
                region=request.region,
                pollutant=self._detect_pollutant(paragraph, request.pollutants),
                fact_type="report_finding",
                statement=paragraph,
                method="报告成果抽取",
                quality=FactQuality(completeness="medium", temporal_coverage=request.time_range.display or "unknown", confidence=0.72),
                tags=self._infer_tags(paragraph),
            )
            ledger.add(fact)

    def _ingest_data_ids(self, ledger: FactLedger, request: DeliberationRequest) -> None:
        start_index = len(ledger.all()) + 1
        for offset, data_id in enumerate(request.data_ids, start=0):
            schema = data_id.split(":")[0] if ":" in data_id else "data"
            statement = f"已有数据资产 {data_id} 可用于会商补充核查，数据类型为 {schema}。"
            fact = FactRecord(
                fact_id=f"fact_data_id_{start_index + offset:04d}",
                source_type="data_id",
                source_ref={"data_id": data_id, "schema": schema},
                time_range=request.time_range,
                region=request.region,
                fact_type="data_asset",
                statement=statement,
                method="DataContext数据引用",
                quality=FactQuality(completeness="medium", temporal_coverage=request.time_range.display or "unknown", confidence=0.8),
                tags=self._infer_tags(statement + " " + schema),
            )
            ledger.add(fact)

    def _row_to_statement(self, row: dict[str, Any]) -> str:
        parts = []
        for key, value in row.items():
            if value is None or value == "":
                continue
            parts.append(f"{key}={value}")
        return "；".join(parts)

    def _numeric_metrics(self, row: dict[str, Any]) -> dict[str, Any]:
        metrics = {}
        for key, value in row.items():
            if isinstance(value, (int, float)):
                metrics[str(key)] = value
                continue
            if isinstance(value, str):
                cleaned = value.strip().replace("%", "")
                try:
                    metrics[str(key)] = float(cleaned)
                except ValueError:
                    pass
        return metrics

    def _split_findings(self, text: str) -> list[str]:
        raw_parts = re.split(r"(?:\n\s*\n|。|\n[-*]\s+)", text)
        findings = []
        for part in raw_parts:
            item = re.sub(r"\s+", " ", part).strip(" #\t\r\n")
            if len(item) < 12:
                continue
            if len(item) > 220:
                item = item[:220] + "..."
            findings.append(item)
        return findings

    def _infer_tags(self, text: str) -> list[str]:
        tags = []
        for tag, keywords in KEYWORD_TAGS.items():
            if any(keyword.lower() in text.lower() for keyword in keywords):
                tags.append(tag)
        return tags or ["通用事实"]

    def _detect_pollutant(self, text: str, pollutants: list[str]) -> str | None:
        for pollutant in pollutants:
            if pollutant and pollutant.lower() in text.lower():
                return pollutant
        if "pm2.5" in text.lower() or "颗粒物" in text:
            return "PM2.5"
        if "o3" in text.lower() or "臭氧" in text:
            return "O3"
        return None

    def _pick(self, row: dict[str, Any], keys: list[str]) -> str | None:
        for key in keys:
            if key in row and row[key] not in (None, ""):
                return str(row[key])
        return None

