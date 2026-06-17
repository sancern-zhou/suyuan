# -*- coding: utf-8 -*-
"""Monthly CMA meteorology support package for Guangdong air-quality PPTs."""

from __future__ import annotations

import csv
import json
import os
import re
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib.parse import urlparse

import httpx
import structlog

from app.fetchers.consultation.city_mapping import CITY_CODE_TO_NAME
from app.fetchers.consultation.output_paths import get_monthly_consultation_dir
from app.services.gd_met_bureau_api_client import GDMetBureauAPIClient

logger = structlog.get_logger()


MAP_SOURCE_CONFIG = {
    "temperature_anomaly": {
        "title": "全国近30天平均气温距平图",
        "filename_prefix": "temperature_anomaly_map",
        "env": "CMA_TEMPERATURE_ANOMALY_MAP_URL",
        "page_url": "https://www.nmc.cn/publish/observations/mta-30days.html",
    },
    "precipitation_anomaly_percent": {
        "title": "全国近30天降水距平百分率图",
        "filename_prefix": "precipitation_anomaly_percent_map",
        "env": "CMA_PRECIPITATION_ANOMALY_PERCENT_MAP_URL",
        "page_url": "https://m.nmc.cn/publish/observations/precipitation-30pa.html",
    },
}

METEOROLOGY_YOY_METRICS = [
    {"metric": "气温", "unit": "degC"},
    {"metric": "日照时数", "unit": "h"},
    {"metric": "风速", "unit": "m/s"},
    {"metric": "小风日数", "unit": "d"},
    {"metric": "降水量", "unit": "mm"},
    {"metric": "降水日数", "unit": "d"},
]

YOY_FIELDNAMES = [
    "metric",
    "unit",
    "current_value",
    "last_year_value",
    "yoy_change",
    "yoy_change_pct",
    "available",
    "missing_reason",
    "data_source",
]

PRECIPITATION_DAY_THRESHOLD_MM = 0.1
LOW_WIND_DAY_THRESHOLD_MS = 2.0
AUTO_YOY_DATA_SOURCE = "广东省气象局观测数据（自动抓取计算）"
SUNSHINE_FIELDS = ("sunshineDuration", "sunshineHours", "sunshine", "日照时数")


class MonthlyMeteorologySupport:
    """Generate monthly meteorology support files from CMA sources."""

    def __init__(
        self,
        year: int,
        month: int,
        output_dir: Optional[Path] = None,
        map_sources: Optional[Dict[str, str]] = None,
        reference_date: Optional[date] = None,
        weather_client=None,
        city_names: Optional[List[str]] = None,
    ):
        self.year = year
        self.month = month
        self.yyyymm = f"{year}{month:02d}"
        self.period = f"{year}年{month:02d}月"
        self.target_product_date = self._next_month_first_day()
        self.reference_date = reference_date or date.today()
        self.output_dir = output_dir or get_monthly_consultation_dir(year, month)
        self.map_sources = map_sources or self._load_map_sources_from_env()
        self.weather_client = weather_client or GDMetBureauAPIClient
        self.city_names = city_names or list(CITY_CODE_TO_NAME.values())

    def generate(self) -> Path:
        """Generate map manifest and six-item meteorology YoY table."""
        self.output_dir.mkdir(parents=True, exist_ok=True)

        maps = self._generate_maps()
        stats_path, stats_available = self._generate_yoy_stats()
        manifest_path = self.output_dir / f"meteorology_support_{self.yyyymm}.json"

        manifest = {
            "year": self.year,
            "month": self.month,
            "period": self.period,
            "target_product_date": self.target_product_date.isoformat(),
            "coverage_note": f"近30天产品，按{self.target_product_date.isoformat()}发布日抓取，用于覆盖{self.period}月末完整窗口",
            "source": "中央气象台/中国气象局",
            "maps": maps,
            "yoy_stats": {
                "file": stats_path.name,
                "available": stats_available,
                "metrics": [metric["metric"] for metric in METEOROLOGY_YOY_METRICS],
                "data_source": AUTO_YOY_DATA_SOURCE,
                "statistical_scope": "广东省全省口径，21个地市城市月值平均",
                "calculation_notes": {
                    "temperature": "气温为城市月平均气温的全省平均",
                    "wind_speed": "风速为城市月平均风速的全省平均",
                    "low_wind_days": f"小风日数按日均风速 < {LOW_WIND_DAY_THRESHOLD_MS:.1f} m/s 统计",
                    "precipitation": "降水量为城市月累计降水量的全省平均",
                    "precipitation_days": f"降水日数按日降水量 >= {PRECIPITATION_DAY_THRESHOLD_MM:.1f} mm 统计",
                    "sunshine_hours": "日照时数暂不自动估算；接口无日照字段时标记为不可用",
                },
                "usage": "广东省气象条件同比变化图表页",
            },
            "usage": {
                "maps": "全国/区域气象背景页",
                "yoy_stats": "广东省气象条件同比变化图表页",
            },
        }
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)

        logger.info(
            "monthly_meteorology_support_generated",
            year=self.year,
            month=self.month,
            output_dir=str(self.output_dir),
            manifest=str(manifest_path),
        )
        return manifest_path

    def _load_map_sources_from_env(self) -> Dict[str, str]:
        sources = {}
        for key, config in MAP_SOURCE_CONFIG.items():
            url = os.getenv(config["env"])
            if url:
                sources[key] = url
        return sources

    def _generate_maps(self) -> Dict[str, Dict[str, object]]:
        maps: Dict[str, Dict[str, object]] = {}
        for key, config in MAP_SOURCE_CONFIG.items():
            url = self._resolve_map_source_url(key, config)
            item = {
                "title": config["title"],
                "source_page": config["page_url"],
                "source_url": url,
                "available": False,
                "file": None,
                "missing_reason": None,
            }
            if not url:
                item["missing_reason"] = self._missing_map_reason(key, config)
                self._remove_stale_map_files(config)
                maps[key] = item
                continue

            suffix = self._infer_image_suffix(url)
            output_path = self.output_dir / f"{config['filename_prefix']}_{self.yyyymm}{suffix}"
            success, error = self._download_image(url, output_path)
            if success:
                item["available"] = True
                item["file"] = output_path.name
            else:
                item["missing_reason"] = error or "图片下载失败"
                self._remove_stale_map_files(config)
            maps[key] = item
        return maps

    def _remove_stale_map_files(self, config: Dict[str, str]) -> None:
        pattern = f"{config['filename_prefix']}_{self.yyyymm}.*"
        for path in self.output_dir.glob(pattern):
            try:
                path.unlink()
            except OSError as exc:
                logger.warning(
                    "monthly_meteorology_stale_map_remove_failed",
                    path=str(path),
                    error=str(exc),
                )

    def _resolve_map_source_url(self, key: str, config: Dict[str, str]) -> Optional[str]:
        configured_url = self.map_sources.get(key)
        if configured_url:
            return configured_url
        return self._resolve_source_url_from_page(config["page_url"])

    def _missing_map_reason(self, key: str, config: Dict[str, str]) -> str:
        if key in self.map_sources:
            return "图片下载失败"
        return f"未配置{config['env']}且官方页面未解析到图片"

    def _next_month_first_day(self) -> date:
        if self.month == 12:
            return date(self.year + 1, 1, 1)
        return date(self.year, self.month + 1, 1)

    def _generate_yoy_stats(self) -> Tuple[Path, bool]:
        source_path = os.getenv("CMA_METEOROLOGY_YOY_STATS_FILE")
        output_path = self.output_dir / f"meteorology_yoy_stats_{self.yyyymm}.csv"
        if source_path and Path(source_path).exists():
            rows, available = self._read_yoy_stats_from_csv(Path(source_path))
        elif os.getenv("CMA_METEOROLOGY_DISABLE_AUTO_YOY", "").lower() == "true":
            rows = self._build_unavailable_yoy_rows(
                "已禁用气象同比自动抓取计算"
            )
            available = False
        else:
            rows, available = self._fetch_and_calculate_yoy_stats()

        with open(output_path, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=YOY_FIELDNAMES)
            writer.writeheader()
            writer.writerows(rows)
        return output_path, available

    def _fetch_and_calculate_yoy_stats(self) -> Tuple[list, bool]:
        current_start, current_end = self._month_date_range(self.year, self.month)
        previous_start, previous_end = self._month_date_range(self.year - 1, self.month)

        current_records = self._fetch_weather_records(current_start, current_end)
        previous_records = self._fetch_weather_records(previous_start, previous_end)
        if not current_records or not previous_records:
            reason = "气象观测接口未返回当月或去年同期数据"
            return self._build_unavailable_yoy_rows(reason), False

        current_stats = self._calculate_monthly_weather_stats(current_records)
        previous_stats = self._calculate_monthly_weather_stats(previous_records)

        rows = []
        all_available = True
        metric_keys = {
            "气温": "temperature",
            "日照时数": "sunshine_hours",
            "风速": "wind_speed",
            "小风日数": "low_wind_days",
            "降水量": "precipitation",
            "降水日数": "precipitation_days",
        }
        for metric in METEOROLOGY_YOY_METRICS:
            name = metric["metric"]
            key = metric_keys[name]
            current_value = current_stats.get(key)
            previous_value = previous_stats.get(key)
            if current_value is None or previous_value is None:
                rows.append(self._unavailable_yoy_row(metric, self._missing_stat_reason(name)))
                all_available = False
                continue

            change = current_value - previous_value
            change_pct = None if previous_value == 0 else change / previous_value * 100
            rows.append({
                "metric": name,
                "unit": metric["unit"],
                "current_value": self._format_number(current_value),
                "last_year_value": self._format_number(previous_value),
                "yoy_change": self._format_number(change),
                "yoy_change_pct": "" if change_pct is None else self._format_number(change_pct),
                "available": "true",
                "missing_reason": "",
                "data_source": AUTO_YOY_DATA_SOURCE,
            })
        return rows, all_available

    def _fetch_weather_records(self, start_date: date, end_date: date) -> List[Dict[str, Any]]:
        records: List[Dict[str, Any]] = []
        begin_time = start_date.isoformat()
        end_time = end_date.isoformat()
        for city_name in self.city_names:
            try:
                city_records = self.weather_client.query_weather(city_name, begin_time, end_time)
            except Exception as exc:
                logger.warning(
                    "monthly_meteorology_weather_query_failed",
                    city=city_name,
                    begin_time=begin_time,
                    end_time=end_time,
                    error=str(exc),
                )
                city_records = []
            records.extend(city_records or [])
        return records

    def _calculate_monthly_weather_stats(self, records: Iterable[Dict[str, Any]]) -> Dict[str, Optional[float]]:
        city_day_records: Dict[Tuple[str, date], list] = defaultdict(list)
        for record in records:
            record_date = self._parse_record_date(record.get("timePoint"))
            if not record_date:
                continue
            city = str(record.get("cityName") or record.get("city") or "广东省")
            city_day_records[(city, record_date)].append(record)

        city_daily = defaultdict(list)
        for (city, day), day_records in city_day_records.items():
            station_groups = defaultdict(list)
            for record in day_records:
                station_groups[str(record.get("stationCode") or "default")].append(record)

            station_precip = []
            station_sunshine = []
            for station_records in station_groups.values():
                precip_values = [self._as_float(item.get("precipitation1h")) for item in station_records]
                precip_values = [value for value in precip_values if value is not None]
                if precip_values:
                    station_precip.append(sum(precip_values))

                sunshine_values = [self._extract_sunshine(item) for item in station_records]
                sunshine_values = [value for value in sunshine_values if value is not None]
                if sunshine_values:
                    station_sunshine.append(sum(sunshine_values))

            temperatures = [self._as_float(item.get("temperature")) for item in day_records]
            winds = [self._as_float(item.get("windSpeed")) for item in day_records]
            daily = {
                "temperature": self._mean(value for value in temperatures if value is not None),
                "wind_speed": self._mean(value for value in winds if value is not None),
                "precipitation": self._mean(station_precip),
                "sunshine_hours": self._mean(station_sunshine),
            }
            city_daily[city].append(daily)

        city_monthly = []
        for daily_values in city_daily.values():
            temps = [item["temperature"] for item in daily_values if item["temperature"] is not None]
            winds = [item["wind_speed"] for item in daily_values if item["wind_speed"] is not None]
            precip = [item["precipitation"] for item in daily_values if item["precipitation"] is not None]
            sunshine = [item["sunshine_hours"] for item in daily_values if item["sunshine_hours"] is not None]
            city_monthly.append({
                "temperature": self._mean(temps),
                "wind_speed": self._mean(winds),
                "precipitation": sum(precip) if precip else None,
                "sunshine_hours": sum(sunshine) if sunshine else None,
                "low_wind_days": sum(
                    1 for item in daily_values
                    if item["wind_speed"] is not None and item["wind_speed"] < LOW_WIND_DAY_THRESHOLD_MS
                ) if winds else None,
                "precipitation_days": sum(
                    1 for item in daily_values
                    if item["precipitation"] is not None and item["precipitation"] >= PRECIPITATION_DAY_THRESHOLD_MM
                ) if precip else None,
            })

        return {
            "temperature": self._mean(item["temperature"] for item in city_monthly if item["temperature"] is not None),
            "wind_speed": self._mean(item["wind_speed"] for item in city_monthly if item["wind_speed"] is not None),
            "precipitation": self._mean(item["precipitation"] for item in city_monthly if item["precipitation"] is not None),
            "sunshine_hours": self._mean(item["sunshine_hours"] for item in city_monthly if item["sunshine_hours"] is not None),
            "low_wind_days": self._mean(item["low_wind_days"] for item in city_monthly if item["low_wind_days"] is not None),
            "precipitation_days": self._mean(item["precipitation_days"] for item in city_monthly if item["precipitation_days"] is not None),
        }

    def _month_date_range(self, year: int, month: int) -> Tuple[date, date]:
        start = date(year, month, 1)
        if month == 12:
            return start, date(year + 1, 1, 1)
        return start, date(year, month + 1, 1)

    def _parse_record_date(self, value: Any) -> Optional[date]:
        if not value:
            return None
        text = str(value).strip()
        try:
            return datetime.fromisoformat(text).date()
        except ValueError:
            pass
        for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                return datetime.strptime(text, fmt).date()
            except ValueError:
                continue
        return None

    def _extract_sunshine(self, record: Dict[str, Any]) -> Optional[float]:
        for field in SUNSHINE_FIELDS:
            value = self._as_float(record.get(field))
            if value is not None:
                return value
        return None

    def _missing_stat_reason(self, metric: str) -> str:
        if metric == "日照时数":
            return "气象观测接口未返回日照时数字段"
        return "气象观测接口缺少该指标所需字段或去年同期数据"

    def _as_float(self, value: Any) -> Optional[float]:
        if value is None or value == "":
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _mean(self, values: Iterable[float]) -> Optional[float]:
        data = list(values)
        if not data:
            return None
        return sum(data) / len(data)

    def _format_number(self, value: float) -> str:
        rounded = round(value, 2)
        if rounded == int(rounded):
            return str(int(rounded))
        return f"{rounded:.2f}".rstrip("0").rstrip(".")

    def _read_yoy_stats_from_csv(self, source_path: Path) -> Tuple[list, bool]:
        rows_by_metric = {}
        with open(source_path, "r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                metric = row.get("metric")
                if metric:
                    rows_by_metric[metric] = row

        rows = []
        all_available = True
        for metric in METEOROLOGY_YOY_METRICS:
            source_row = rows_by_metric.get(metric["metric"])
            if not source_row:
                rows.append(self._unavailable_yoy_row(metric, "源文件缺少该指标"))
                all_available = False
                continue
            row = {field: source_row.get(field, "") for field in YOY_FIELDNAMES}
            row["metric"] = metric["metric"]
            row["unit"] = row.get("unit") or metric["unit"]
            row["available"] = str(row.get("available", "true")).lower()
            row["data_source"] = row.get("data_source") or "中央气象台/中国气象局"
            rows.append(row)
            if row["available"] != "true":
                all_available = False
        return rows, all_available

    def _build_unavailable_yoy_rows(self, reason: str) -> list:
        return [self._unavailable_yoy_row(metric, reason) for metric in METEOROLOGY_YOY_METRICS]

    def _unavailable_yoy_row(self, metric: Dict[str, str], reason: str) -> Dict[str, str]:
        return {
            "metric": metric["metric"],
            "unit": metric["unit"],
            "current_value": "",
            "last_year_value": "",
            "yoy_change": "",
            "yoy_change_pct": "",
            "available": "false",
            "missing_reason": reason,
            "data_source": "中央气象台/中国气象局",
        }

    def _download_image(self, url: str, output_path: Path) -> Tuple[bool, Optional[str]]:
        try:
            with httpx.Client(timeout=30.0, follow_redirects=True) as client:
                response = client.get(url)
                response.raise_for_status()
                content_type = response.headers.get("content-type", "")
                if "image" not in content_type and not self._looks_like_image_url(url):
                    return False, f"响应不是图片: {content_type or 'unknown'}"
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_bytes(response.content)
            return True, None
        except Exception as exc:
            logger.warning(
                "monthly_meteorology_map_download_failed",
                url=url,
                output_path=str(output_path),
                error=str(exc),
            )
            return False, str(exc)

    def _resolve_source_url_from_page(self, page_url: str) -> Optional[str]:
        html = self._fetch_page(page_url)
        if not html:
            return None

        patterns = [
            r'data-src=["\']([^"\']+\.(?:png|jpg|jpeg|webp)(?:\?[^"\']*)?)["\']',
            r'data-img=["\']([^"\']+\.(?:png|jpg|jpeg|webp)(?:\?[^"\']*)?)["\']',
            r'data-rel=["\']([^"\']+\.(?:png|jpg|jpeg|webp)(?:\?[^"\']*)?)["\']',
            r'src=["\']([^"\']+\.(?:png|jpg|jpeg|webp)(?:\?[^"\']*)?)["\']',
        ]
        candidates = []
        for pattern in patterns:
            candidates.extend(self._absolute_url(match) for match in re.findall(pattern, html, flags=re.IGNORECASE))
        if not candidates:
            return None
        product_candidates = [url for url in candidates if "/product/" in url]
        if product_candidates:
            candidates = product_candidates
        return max(candidates, key=self._source_url_sort_key)

    def _source_url_sort_key(self, url: str) -> str:
        match = re.search(r"_PB_(\d{8,14})", url)
        if match:
            return match.group(1)
        return url

    def _fetch_page(self, url: str) -> Optional[str]:
        try:
            with httpx.Client(timeout=20.0, follow_redirects=True) as client:
                response = client.get(url)
                response.raise_for_status()
                return response.text
        except Exception as exc:
            logger.warning(
                "monthly_meteorology_source_page_fetch_failed",
                url=url,
                error=str(exc),
            )
            return None

    def _infer_image_suffix(self, url: str) -> str:
        suffix = Path(urlparse(url).path).suffix.lower()
        if suffix in {".png", ".jpg", ".jpeg", ".webp"}:
            return suffix
        return ".png"

    def _looks_like_image_url(self, url: str) -> bool:
        return self._infer_image_suffix(url) in {".png", ".jpg", ".jpeg", ".webp"}

    def _absolute_url(self, url: str) -> str:
        if url.startswith("//"):
            return f"https:{url}"
        if url.startswith("/"):
            return f"https://www.nmc.cn{url}"
        return url


def generate_meteorology_support(year: int, month: int) -> Path:
    """Convenience entrypoint for scripts and scheduled fetchers."""
    return MonthlyMeteorologySupport(year, month).generate()
