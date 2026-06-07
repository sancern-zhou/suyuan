"""
月度污染过程与组分数据生成脚本

识别污染过程：至少一天为AQI>100
获取组分数据：VOCs组分 + PM2.5组分（离子/碳/地壳）

数据来源：execute_query_gd_suncere_city_day（城市日报）+ 站点/组分小时数据工具
输出文件：pollution_events_{yyyymm}.csv（仅当存在污染过程时）
"""

import asyncio
import csv
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any, Set

import structlog

from app.tools.query.query_station_standard_report.tool import execute_query_station_standard_report
from app.tools.query.query_gd_suncere.tool import (
    execute_query_gd_suncere_city_day,
    execute_query_gd_suncere_station_hour,
)
from app.tools.query.get_pm25_carbon.tool import GetPM25CarbonTool
from app.tools.query.get_pm25_crustal.tool import GetPM25CrustalTool
from app.tools.query.get_pm25_ionic.tool import GetPM25IonicTool
from app.tools.query.get_vocs_data.tool_api import GetVOCsDataTool
from app.agent.context.data_context_manager import DataContextManager
from app.agent.context.execution_context import ExecutionContext
from app.agent.memory.hybrid_manager import HybridMemoryManager
from app.services.data_registry import data_registry
from app.fetchers.consultation.field_normalizer import CityDayFieldNormalizer

logger = structlog.get_logger()


class MonthlyPollutionEventsComponents:
    """月度污染过程与组分数据生成器"""

    def __init__(self, year: int, month: int):
        """
        初始化

        Args:
            year: 年份，如2026
            month: 月份，如5
        """
        self.year = year
        self.month = month

        # 计算日期范围
        self.start_date = datetime(year, month, 1)
        if month == 12:
            self.end_date = datetime(year + 1, 1, 1) - timedelta(days=1)
        else:
            self.end_date = datetime(year, month + 1, 1) - timedelta(days=1)

        # 输出目录
        self.output_dir = Path(f"backend_data_registry/月度补充数据/{year}年{month:02d}月")
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.context = self._create_context()
        self.vocs_tool = GetVOCsDataTool()
        self.pm25_ionic_tool = GetPM25IonicTool()
        self.pm25_carbon_tool = GetPM25CarbonTool()
        self.pm25_crustal_tool = GetPM25CrustalTool()
        self.guangdong_cities = [
            "广州", "深圳", "珠海", "汕头", "佛山", "韶关", "湛江", "肇庆", "江门", "茂名",
            "惠州", "梅州", "汕尾", "河源", "阳江", "清远", "东莞", "中山", "潮州", "揭阳", "云浮"
        ]

    def _create_context(self) -> Optional[Any]:
        """Create the lightweight context required by query tools."""
        try:
            session_id = f"monthly_pollution_components_{self.year}_{self.month:02d}"
            memory = HybridMemoryManager(session_id=session_id)
            data_manager = DataContextManager(memory)
            return ExecutionContext(session_id=session_id, iteration=1, data_manager=data_manager)
        except Exception as exc:
            logger.warning("monthly_pollution_context_create_failed", error=str(exc))
            return None

    def _format_date(self, date: datetime) -> str:
        """格式化日期为 YYYY-MM-DD"""
        return date.strftime("%Y-%m-%d")

    def fetch_station_data(self) -> List[Dict[str, Any]]:
        """
        获取站点数据

        Returns:
            站点数据列表
        """
        logger.info("fetch_station_data_start",
                   start_date=self._format_date(self.start_date),
                   end_date=self._format_date(self.end_date))

        try:
            # 调用API获取站点数据
            result = execute_query_station_standard_report(
                start_time=self._format_date(self.start_date),
                end_time=self._format_date(self.end_date),
                max_result_count=10000  # 设置较大限制
            )

            if not result or result.get("status") != "success":
                logger.error("fetch_station_data_failed",
                           error=result.get("error"),
                           summary=result.get("summary"))
                return []

            # 优先从 result["result"] 获取完整数据
            full_data = result.get("result", [])
            if full_data:
                logger.info("fetch_station_data_from_result",
                           record_count=len(full_data))
                return full_data

            # 备用：尝试从 report_data_id 读取数据包
            report_data_id = result.get("report_data_id")
            if report_data_id:
                logger.info("fetch_station_data_from_data_id",
                           data_id=report_data_id)
                try:
                    package = data_registry.load_dataset(report_data_id)

                    # 数据包结构：{"views": {"result": [...]}}
                    if isinstance(package, dict) and "views" in package:
                        views = package["views"]
                        # 优先使用 result，其次 stations，再次 raw
                        package_data = views.get("result") or views.get("stations") or views.get("raw", [])
                        if isinstance(package_data, list) and package_data:
                            logger.info("fetch_station_data_from_data_id_success",
                                       record_count=len(package_data))
                            return package_data
                    elif isinstance(package, list) and package:
                        # 直接是列表格式
                        logger.info("fetch_station_data_from_data_id_success",
                                   record_count=len(package))
                        return package
                except Exception as e:
                    logger.warning("fetch_station_data_from_data_id_failed",
                                  data_id=report_data_id,
                                  error=str(e))

            # 最后备用：使用 data 中的预览数据
            data = result.get("data", [])
            if data:
                logger.warning("fetch_station_data_using_preview",
                               record_count=len(data))
                return data
            else:
                logger.error("no_station_data_available")
                return []

        except Exception as e:
            logger.error("fetch_station_data_exception", error=str(e))
            return []

    def fetch_city_day_data(self) -> List[Dict[str, Any]]:
        """获取城市日报数据，用于识别 AQI>100 污染过程。"""
        if self.context is None:
            return []

        logger.info(
            "fetch_city_day_data_start",
            start_date=self._format_date(self.start_date),
            end_date=self._format_date(self.end_date),
        )

        try:
            result = execute_query_gd_suncere_city_day(
                cities=self.guangdong_cities,
                start_date=self._format_date(self.start_date),
                end_date=self._format_date(self.end_date),
                context=self.context,
                max_result_count=5000,
            )
            if not result or result.get("status") not in {"success", "empty"}:
                logger.error(
                    "fetch_city_day_data_failed",
                    error=result.get("error") if isinstance(result, dict) else None,
                    summary=result.get("summary") if isinstance(result, dict) else None,
                )
                return []
            return self._extract_records(result)
        except Exception as exc:
            logger.error("fetch_city_day_data_exception", error=str(exc))
            return []

    def identify_pollution_events(self, station_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        识别污染过程（AQI>100）

        Args:
            station_data: 站点数据列表

        Returns:
            污染过程列表（包含城市、日期、AQI等信息）
        """
        pollution_events = []

        for record in station_data:
            normalized = CityDayFieldNormalizer.normalize_record(record)

            # 提取AQI值。城市日报标准化结果可能把 AQI 放在顶层或 measurements 中。
            aqi = normalized.get("aqi")
            measurements = record.get("measurements", {})
            if aqi is None and isinstance(measurements, dict):
                for field in ["AQI", "aqi", "AQI_Decimal", "aqi_Decimal"]:
                    value = measurements.get(field)
                    if value is not None and value != "" and value != "—":
                        try:
                            aqi = float(value)
                            break
                        except (ValueError, TypeError):
                            continue
            if aqi is None:
                for field in ["AQI", "aqi", "AQI_Decimal", "aqi_Decimal"]:
                    value = record.get(field)
                    if value is not None and value != "" and value != "—":
                        try:
                            aqi = float(value)
                            break
                        except (ValueError, TypeError):
                            continue

            # 判断是否为污染过程（AQI>100）
            if aqi and aqi > 100:
                # 提取城市和站点信息
                city = ""
                for field in ["cityName", "city", "城市", "name"]:
                    value = record.get(field)
                    if value:
                        city = str(value).strip()
                        break
                city = city or normalized.get("city", "")

                station = ""
                for field in ["stationName", "station", "站点"]:
                    value = record.get(field)
                    if value:
                        station = str(value).strip()
                        break
                station = station or city

                date = ""
                for field in ["timePoint", "time", "date", "day"]:
                    value = record.get(field)
                    if value:
                        date_str = str(value).strip()
                        # 处理日期范围 "2026-05-01~ 2026-05-31"
                        if "~" in date_str:
                            date_str = date_str.split("~")[0].strip()
                        date = date_str
                        break
                date = date or str(record.get("timestamp") or normalized.get("date") or "").split(" ")[0]

                if city and station and date:
                    pollution_events.append({
                        "city": city,
                        "station": station,
                        "date": date,
                        "aqi": aqi,
                        "primary_pollutant": record.get("primaryPollutant")
                        or record.get("primary_pollutant")
                        or record.get("首要污染物")
                        or "",
                    })

        logger.info("pollution_events_identified", event_count=len(pollution_events))
        return pollution_events

    def generate_pollution_events_file(self, pollution_events: List[Dict[str, Any]]) -> Optional[Path]:
        """
        生成污染过程文件

        Args:
            pollution_events: 污染过程列表

        Returns:
            输出文件路径，无污染过程时返回None
        """
        if not pollution_events:
            print(f"[污染过程] 未发现AQI>100的污染过程，不生成文件")
            return None

        # 按城市、日期、站点排序
        pollution_events.sort(key=lambda x: (x["city"], x["date"], x["station"]))

        # 输出文件
        output_file = self.output_dir / f"pollution_events_{self.year}{self.month:02d}.csv"

        with open(output_file, "w", newline="", encoding="utf-8-sig") as f:
            fieldnames = ["city", "station", "date", "aqi", "primary_pollutant"]
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(pollution_events)

        print(f"[污染过程] 已生成：{output_file}")
        print(f"[污染过程] 污染过程记录数：{len(pollution_events)}")

        # 统计污染城市分布
        city_distribution: Dict[str, int] = {}
        for event in pollution_events:
            city = event["city"]
            city_distribution[city] = city_distribution.get(city, 0) + 1

        print(f"[污染过程] 涉及城市数：{len(city_distribution)}")
        for city, count in sorted(city_distribution.items(), key=lambda x: x[1], reverse=True):
            print(f"  - {city}: {count}天")

        return output_file

    def _event_range(self, event: Dict[str, Any]) -> tuple[str, str]:
        date = str(event["date"]).split(" ")[0]
        return f"{date} 00:00:00", f"{date} 23:59:59"

    def _event_slug(self, event: Dict[str, Any]) -> str:
        date = str(event["date"]).split(" ")[0].replace("-", "")
        city = str(event["city"]).replace("/", "_").replace(" ", "")
        station = str(event["station"]).replace("/", "_").replace(" ", "")
        return f"{date}_{city}_{station}"

    def _extract_records(self, result: Dict[str, Any]) -> List[Dict[str, Any]]:
        if not result:
            return []
        data = result.get("data")
        if isinstance(data, list) and data:
            return data
        data_id = result.get("data_id") or result.get("report_data_id")
        if data_id:
            try:
                loaded = data_registry.load_dataset(data_id)
                if isinstance(loaded, list):
                    return loaded
                if isinstance(loaded, dict):
                    for key in ("data", "result", "records"):
                        value = loaded.get(key)
                        if isinstance(value, list):
                            return value
                    views = loaded.get("views")
                    if isinstance(views, dict):
                        for key in ("result", "records", "raw", "reporting"):
                            value = views.get(key)
                            if isinstance(value, list):
                                return value
            except Exception as exc:
                logger.warning("component_data_id_load_failed", data_id=data_id, error=str(exc))
        return []

    def _write_csv(self, rows: List[Dict[str, Any]], output_file: Path) -> Optional[Path]:
        if not rows:
            return None

        fieldnames: List[str] = []
        for row in rows:
            for key in row:
                if key not in fieldnames:
                    fieldnames.append(key)

        with open(output_file, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)
        return output_file

    def fetch_hourly_pollutants(self, event: Dict[str, Any]) -> List[Dict[str, Any]]:
        if self.context is None:
            return []
        start_time, end_time = self._event_range(event)
        result = execute_query_gd_suncere_station_hour(
            cities=[event["city"]],
            start_time=start_time,
            end_time=end_time,
            context=self.context,
            include_weather=True,
            max_result_count=5000,
        )
        return self._extract_records(result)

    def fetch_component_dataset(self, event: Dict[str, Any], component_type: str) -> List[Dict[str, Any]]:
        if self.context is None:
            return []

        start_time, end_time = self._event_range(event)
        locations = [event["city"], event["station"]]

        async def _run() -> Dict[str, Any]:
            if component_type == "vocs":
                return await self.vocs_tool.execute(
                    context=self.context,
                    start_time=start_time,
                    end_time=end_time,
                    locations=locations,
                    table_type=1,
                    data_type=0,
                )
            if component_type == "pm25_ionic":
                return await self.pm25_ionic_tool.execute(
                    context=self.context,
                    start_time=start_time,
                    end_time=end_time,
                    locations=locations,
                    time_type=1,
                    data_type=0,
                )
            if component_type == "pm25_carbon":
                return await self.pm25_carbon_tool.execute(
                    context=self.context,
                    start_time=start_time,
                    end_time=end_time,
                    locations=locations,
                    time_granularity=1,
                    data_type=0,
                )
            if component_type == "pm25_crustal":
                return await self.pm25_crustal_tool.execute(
                    context=self.context,
                    start_time=start_time,
                    end_time=end_time,
                    locations=locations,
                    time_granularity=0,
                    data_type=1,
                )
            return {"success": False, "error": f"unknown component type: {component_type}"}

        try:
            return self._extract_records(asyncio.run(_run()))
        except RuntimeError:
            loop = asyncio.new_event_loop()
            try:
                return self._extract_records(loop.run_until_complete(_run()))
            finally:
                loop.close()

    def generate_component_files(self, pollution_events: List[Dict[str, Any]]) -> Path:
        manifest: Dict[str, Any] = {
            "year": self.year,
            "month": self.month,
            "event_count": len(pollution_events),
            "files": [],
            "errors": [],
        }
        component_types = ["vocs", "pm25_ionic", "pm25_carbon", "pm25_crustal"]

        for event in pollution_events:
            slug = self._event_slug(event)

            try:
                hourly_rows = self.fetch_hourly_pollutants(event)
                hourly_file = self._write_csv(
                    hourly_rows,
                    self.output_dir / f"hourly_pollution_{slug}.csv",
                )
                if hourly_file:
                    manifest["files"].append({
                        "type": "hourly_pollution",
                        "path": str(hourly_file),
                        "records": len(hourly_rows),
                        "event": event,
                    })
            except Exception as exc:
                manifest["errors"].append({"type": "hourly_pollution", "event": event, "error": str(exc)})

            for component_type in component_types:
                try:
                    rows = self.fetch_component_dataset(event, component_type)
                    component_file = self._write_csv(
                        rows,
                        self.output_dir / f"{component_type}_components_{slug}.csv",
                    )
                    if component_file:
                        manifest["files"].append({
                            "type": component_type,
                            "path": str(component_file),
                            "records": len(rows),
                            "event": event,
                        })
                except Exception as exc:
                    manifest["errors"].append({"type": component_type, "event": event, "error": str(exc)})

        manifest_file = self.output_dir / f"component_data_manifest_{self.year}{self.month:02d}.json"
        with open(manifest_file, "w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)
        print(f"[组分数据] 已生成清单：{manifest_file}")
        return manifest_file

    def generate(self) -> Optional[Path]:
        """
        生成污染过程数据

        Returns:
            输出文件路径，无污染过程时返回None
        """
        print(f"[污染过程] 开始分析 {self.year}年{self.month}月 数据...")

        # 获取站点数据
        print(f"[污染过程] 查询城市日报数据...")
        station_data = self.fetch_city_day_data()

        if not station_data:
            print(f"[污染过程] 站点数据为空，无法分析")
            return None

        # 识别污染过程
        pollution_events = self.identify_pollution_events(station_data)

        if not pollution_events:
            print(f"[污染过程] 未发现AQI>100的污染过程")
            return None

        # 生成污染过程文件
        output_file = self.generate_pollution_events_file(pollution_events)
        self.generate_component_files(pollution_events)

        return output_file


def generate_pollution_events_components(year: int, month: int) -> Optional[Path]:
    """
    生成月度污染过程与组分数据的便捷函数

    Args:
        year: 年份，如2026
        month: 月份，如5

    Returns:
        输出文件路径，无污染过程时返回None
    """
    generator = MonthlyPollutionEventsComponents(year, month)
    return generator.generate()


# 命令行入口
if __name__ == "__main__":
    import sys

    if len(sys.argv) >= 3:
        year = int(sys.argv[1])
        month = int(sys.argv[2])
    else:
        # 默认生成2026年5月
        year = 2026
        month = 5

    result = generate_pollution_events_components(year, month)
    if result:
        print(f"\n✓ 成功生成：{result}")
        sys.exit(0)
    else:
        print(f"\n✗ 无污染过程数据")
        sys.exit(0)  # 无污染过程不是错误，正常退出
