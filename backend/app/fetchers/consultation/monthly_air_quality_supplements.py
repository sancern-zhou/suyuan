"""
月度空气质量数据补充脚本

生成三个数据文件：
1. 区县排名数据（district_ranking_{yyyymm}.csv）
2. 高值站点数据（station_high_value_{yyyymm}.csv）
3. 污染过程及组分数据（pollution_events_{yyyymm}.json + 组分CSV）

输出路径：/tmp/A会商文件/{YYYY年MM月}/
"""

import asyncio
import csv
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from app.tools.query.query_gd_suncere.tool import (
    execute_query_gd_suncere_district_report,
    execute_query_gd_suncere_city_day,
    execute_query_gd_suncere_station_hour
)
from app.tools.query.query_station_standard_report.tool import execute_query_station_standard_report
from app.tools.query.get_vocs_data.tool_api import GetVOCsDataTool
from app.tools.query.get_particulate_components.tool import GetParticulateComponentsTool
from app.agent.context.data_context_manager import DataContextManager
from app.db.session_repository import SessionRepository


class MonthlyAirQualitySupplements:
    """月度空气质量数据补充生成器"""

    def __init__(self, year: int, month: int):
        """
        初始化

        Args:
            year: 年份，如2026
            month: 月份，如5
        """
        self.year = year
        self.month = month

        # 创建简单的执行上下文（用于数据存储）
        try:
            session_repo = SessionRepository()
            session_id = f"monthly_supplements_{year}_{month:02d}"
            data_manager = DataContextManager(session_repo)
            self.context = type('obj', (object,), {
                'session_id': session_id,
                'iteration': 1,
                'data_manager': data_manager,
                'save_data': data_manager.save_data,
                'get_data': data_manager.get_data,
                'get_handle': data_manager.get_handle,
            })()
        except Exception as e:
            print(f"创建ExecutionContext失败，使用None: {e}")
            self.context = None

        # 初始化异步工具
        self.vocs_tool = GetVOCsDataTool()
        self.component_tool = GetParticulateComponentsTool()

        # 计算日期范围
        self.start_date = datetime(year, month, 1)
        if month == 12:
            self.end_date = datetime(year + 1, 1, 1) - timedelta(days=1)
        else:
            self.end_date = datetime(year, month + 1, 1) - timedelta(days=1)

        # 去年同期（用于同比计算）
        self.last_year_start = datetime(year - 1, month, 1)
        if month == 12:
            self.last_year_end = datetime(year, 1, 1) - timedelta(days=1)
        else:
            self.last_year_end = datetime(year - 1, month + 1, 1) - timedelta(days=1)

        # 输出目录（尝试使用原始路径，如果权限问题则使用备用路径）
        primary_output_dir = Path(f"/tmp/A会商文件/{year}年{month:02d}月")
        backup_output_dir = Path(f"backend_data_registry/月度补充数据/{year}年{month:02d}月")

        try:
            primary_output_dir.mkdir(parents=True, exist_ok=True)
            # 测试写入权限
            test_file = primary_output_dir / ".permission_test"
            test_file.touch()
            test_file.unlink()
            self.output_dir = primary_output_dir
        except (PermissionError, OSError):
            print(f"[权限警告] 无法写入 {primary_output_dir}，使用备用路径 {backup_output_dir}")
            backup_output_dir.mkdir(parents=True, exist_ok=True)
            self.output_dir = backup_output_dir

        # 污染物列表
        self.pollutants = ["pm25", "pm10", "no2", "o3", "aqi", "co", "so2"]

    def _format_date(self, date: datetime) -> str:
        """格式化日期为 YYYY-MM-DD"""
        return date.strftime("%Y-%m-%d")

    def generate_district_ranking(self) -> Path:
        """
        生成区县排名数据

        Returns:
            输出文件路径
        """
        print(f"[区县排名] 查询 {self.year}年{self.month}月 数据...")

        # 查询当月数据（广东省所有城市）
        guangdong_cities = [
            "广州", "深圳", "珠海", "汕头", "佛山", "韶关", "湛江", "肇庆", "江门", "茂名",
            "惠州", "梅州", "汕尾", "河源", "阳江", "清远", "东莞", "中山", "潮州", "揭阳", "云浮"
        ]
        current_result = execute_query_gd_suncere_district_report(
            start_time=self._format_date(self.start_date),
            end_time=self._format_date(self.end_date),
            cities=guangdong_cities,
            max_result_count=100
        )

        # 查询去年同期数据
        last_year_result = execute_query_gd_suncere_district_report(
            start_time=self._format_date(self.last_year_start),
            end_time=self._format_date(self.last_year_end),
            cities=guangdong_cities,
            max_result_count=100
        )

        # 解析数据
        current_data = self._parse_district_data(current_result)
        last_year_data = self._parse_district_data(last_year_result)

        # 计算同比并合并
        merged_data = self._merge_with_yoy(current_data, last_year_data)

        # 排序并输出
        output_file = self.output_dir / f"district_ranking_{self.year}{self.month:02d}.csv"
        self._write_district_csv(merged_data, output_file)

        print(f"[区县排名] 已生成：{output_file}")
        return output_file

    def _parse_district_data(self, result: dict) -> Dict[str, dict]:
        """解析区县数据"""
        data = {}
        if "data" in result and result["data"]:
            for record in result["data"]:
                # 使用实际返回的字段名
                district = record.get("districtName") or record.get("district") or record.get("area") or record.get("name")
                if not district:
                    continue

                # 处理数值字段（可能是字符串或数字）
                def safe_float(value):
                    if value is None or value == "" or value == "—":
                        return None
                    try:
                        return float(value)
                    except (ValueError, TypeError):
                        return None

                data[district] = {
                    "city": record.get("cityName") or record.get("city", ""),
                    "pm25": safe_float(record.get("pM2_5") or record.get("pm25")),
                    "pm10": safe_float(record.get("pM10") or record.get("pm10")),
                    "no2": safe_float(record.get("nO2") or record.get("no2")),
                    "o3": safe_float(record.get("o3_8h") or record.get("o3")),  # 优先使用o3_8h
                    "aqi": None,  # API返回中没有AQI，设为None
                    "co": safe_float(record.get("co")),
                    "so2": safe_float(record.get("sO2") or record.get("so2")),
                }
        return data

    def _safe_float(self, value) -> Optional[float]:
        """安全转换为浮点数"""
        if value is None or value == "":
            return None
        try:
            return float(value)
        except (ValueError, TypeError):
            return None

    def _merge_with_yoy(self, current: Dict[str, dict], last_year: Dict[str, dict]) -> List[dict]:
        """合并当期和去年同期数据，计算同比"""
        merged = []
        for district, curr_vals in current.items():
            last_vals = last_year.get(district, {})

            row = {
                "district": district,
                "city": curr_vals.get("city", ""),
                "pm25": curr_vals.get("pm25"),
                "pm10": curr_vals.get("pm10"),
                "no2": curr_vals.get("no2"),
                "o3": curr_vals.get("o3"),
                "aqi": curr_vals.get("aqi"),
                "co": curr_vals.get("co"),
                "so2": curr_vals.get("so2"),
            }

            # 计算同比
            for pol in self.pollutants:
                curr_val = curr_vals.get(pol)
                last_val = last_vals.get(pol)
                if curr_val is not None and last_val is not None and last_val != 0:
                    yoy = (curr_val - last_val) / last_val * 100
                    row[f"{pol}_yoy"] = round(yoy, 1)
                else:
                    row[f"{pol}_yoy"] = None

            merged.append(row)

        return merged

    def _write_district_csv(self, data: List[dict], output_file: Path):
        """写入区县排名CSV"""
        if not data:
            print("[区县排名] 无数据")
            return

        fieldnames = [
            "district", "city",
            "pm25", "pm25_yoy",
            "pm10", "pm10_yoy",
            "no2", "no2_yoy",
            "o3", "o3_yoy",
            "aqi", "aqi_yoy",
            "co", "co_yoy",
            "so2", "so2_yoy"
        ]

        with open(output_file, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(data)

    def generate_station_high_value(self) -> Path:
        """
        生成高值站点数据

        高值定义：污染物浓度排名前十 OR 同比变差幅度排名前十

        Returns:
            输出文件路径
        """
        print(f"[高值站点] 查询 {self.year}年{self.month}月 数据...")

        # 查询当月站点数据
        current_result = execute_query_station_standard_report(
            start_time=self._format_date(self.start_date),
            end_time=self._format_date(self.end_date)
        )

        # 查询去年同期数据
        last_year_result = execute_query_station_standard_report(
            start_time=self._format_date(self.last_year_start),
            end_time=self._format_date(self.last_year_end)
        )

        # 解析数据
        current_data = self._parse_station_data(current_result)
        last_year_data = self._parse_station_data(last_year_result)

        # 计算同比
        merged_data = self._merge_station_with_yoy(current_data, last_year_data)

        # 识别高值站点
        high_value_stations = self._identify_high_value_stations(merged_data)

        # 输出
        output_file = self.output_dir / f"station_high_value_{self.year}{self.month:02d}.csv"
        self._write_station_csv(high_value_stations, output_file)

        print(f"[高值站点] 已生成：{output_file}")
        return output_file

    def _parse_station_data(self, result: dict) -> Dict[str, dict]:
        """解析站点数据"""
        data = {}
        if "data" in result and result["data"]:
            for record in result["data"]:
                # 使用实际返回的字段名
                station = record.get("站点") or record.get("station") or record.get("station_name") or record.get("name")
                if not station:
                    continue

                # 处理数值字段（可能是字符串或数字）
                def safe_float(value):
                    if value is None or value == "" or value == "—":
                        return None
                    try:
                        return float(value)
                    except (ValueError, TypeError):
                        return None

                # 从城市编码获取城市名称（如果有城市映射的话）
                city_code = record.get("城市编码") or record.get("cityCode") or ""
                # 这里可以添加城市编码到城市名称的映射，暂时使用城市编码

                data[station] = {
                    "city": city_code,  # 暂时使用城市编码
                    "pm25": safe_float(record.get("PM2.5") or record.get("PM2_5") or record.get("pM2_5")),
                    "pm10": safe_float(record.get("PM10") or record.get("pM10")),
                    "no2": safe_float(record.get("NO2") or record.get("nO2")),
                    "o3": safe_float(record.get("O3-8h") or record.get("O3") or record.get("o3_8h")),
                    "aqi": safe_float(record.get("AQI") or record.get("aqi")),
                    "co": safe_float(record.get("CO") or record.get("co")),
                    "so2": safe_float(record.get("SO2") or record.get("sO2")),
                }
        return data

    def _merge_station_with_yoy(self, current: Dict[str, dict], last_year: Dict[str, dict]) -> List[dict]:
        """合并当期和去年同期站点数据，计算同比"""
        merged = []
        for station, curr_vals in current.items():
            last_vals = last_year.get(station, {})

            row = {
                "station": station,
                "city": curr_vals.get("city", ""),
                "pm25": curr_vals.get("pm25"),
                "pm10": curr_vals.get("pm10"),
                "no2": curr_vals.get("no2"),
                "o3": curr_vals.get("o3"),
                "aqi": curr_vals.get("aqi"),
                "co": curr_vals.get("co"),
                "so2": curr_vals.get("so2"),
            }

            # 计算同比
            for pol in self.pollutants:
                curr_val = curr_vals.get(pol)
                last_val = last_vals.get(pol)
                if curr_val is not None and last_val is not None and last_val != 0:
                    yoy = (curr_val - last_val) / last_val * 100
                    row[f"{pol}_yoy"] = round(yoy, 1)
                else:
                    row[f"{pol}_yoy"] = None

            merged.append(row)
        return merged

    def _identify_high_value_stations(self, data: List[dict]) -> List[dict]:
        """识别高值站点"""
        high_value_stations = set()

        # 对每个污染物，找出浓度TOP10和同比变差TOP10
        for pol in self.pollutants:
            # 浓度TOP10（降序）
            by_concentration = sorted(
                [d for d in data if d.get(pol) is not None],
                key=lambda x: x[pol],
                reverse=True
            )[:10]
            for item in by_concentration:
                high_value_stations.add((item["station"], f"{pol}_浓度"))

            # 同比变差TOP10（同比值升序，正值表示变差）
            yoy_field = f"{pol}_yoy"
            by_yoy = sorted(
                [d for d in data if d.get(yoy_field) is not None],
                key=lambda x: x[yoy_field],
                reverse=True
            )[:10]
            for item in by_yoy:
                high_value_stations.add((item["station"], f"{pol}_同比"))

        # 去重并构建结果
        station_names = set()
        result = []
        for station, reason in high_value_stations:
            if station in station_names:
                continue
            station_names.add(station)
            # 找到该站点的完整数据
            station_data = next((d for d in data if d["station"] == station), None)
            if station_data:
                row = station_data.copy()
                row["high_value_reason"] = reason
                result.append(row)

        return result

    def _write_station_csv(self, data: List[dict], output_file: Path):
        """写入高值站点CSV"""
        if not data:
            print("[高值站点] 无高值站点数据")
            return

        fieldnames = [
            "station", "city", "high_value_reason",
            "pm25", "pm25_yoy",
            "pm10", "pm10_yoy",
            "no2", "no2_yoy",
            "o3", "o3_yoy",
            "aqi", "aqi_yoy",
            "co", "co_yoy",
            "so2", "so2_yoy"
        ]

        with open(output_file, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(data)

    def identify_pollution_events(self) -> Tuple[Optional[dict], Optional[Path]]:
        """
        识别污染过程

        污染过程定义：至少一天AQI>100

        Returns:
            (污染过程数据, 输出文件路径) 如果没有污染过程则返回 (None, None)
        """
        print(f"[污染过程识别] 查询 {self.year}年{self.month}月 城市日报数据...")

        # 查询城市日报（广东省21个地级市）
        guangdong_cities = [
            "广州", "深圳", "珠海", "汕头", "佛山", "韶关", "湛江", "肇庆", "江门", "茂名",
            "惠州", "梅州", "汕尾", "河源", "阳江", "清远", "东莞", "中山", "潮州", "揭阳", "云浮"
        ]
        city_day_result = execute_query_gd_suncere_city_day(
            cities=guangdong_cities,
            start_date=self._format_date(self.start_date),
            end_date=self._format_date(self.end_date),
            context=self.context
        )

        # 解析数据
        city_day_data = self._parse_city_day_data(city_day_result)

        # 识别污染过程
        pollution_events = self._extract_pollution_events(city_day_data)

        if not pollution_events:
            print("[污染过程识别] 本月无污染过程（AQI>100），不生成组分数据")
            return None, None

        # 输出污染过程
        output_file = self.output_dir / f"pollution_events_{self.year}{self.month:02d}.json"
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(pollution_events, f, ensure_ascii=False, indent=2)

        print(f"[污染过程识别] 已生成：{output_file}")
        return pollution_events, output_file

    def _parse_city_day_data(self, result: dict) -> List[dict]:
        """解析城市日报数据"""
        data = []
        if "data" in result and result["data"]:
            for record in result["data"]:
                date_str = record.get("date") or record.get("time") or record.get("day")
                if not date_str:
                    continue

                data.append({
                    "date": date_str,
                    "city": record.get("city", ""),
                    "aqi": self._safe_float(record.get("aqi")),
                    "pm25": self._safe_float(record.get("pm25")),
                    "pm10": self._safe_float(record.get("pm10")),
                    "no2": self._safe_float(record.get("no2")),
                    "o3": self._safe_float(record.get("o3")),
                    "primary_pollutant": record.get("primary_pollutant") or record.get("primary"),
                })
        return data

    def _extract_pollution_events(self, city_day_data: List[dict]) -> dict:
        """提取污染过程"""
        if not city_day_data:
            return {}

        # 按日期排序
        sorted_data = sorted(city_day_data, key=lambda x: x["date"])

        # 找出所有AQI>100的日期
        pollution_days = {}
        for record in sorted_data:
            if record.get("aqi") and record["aqi"] > 100:
                date = record["date"]
                if date not in pollution_days:
                    pollution_days[date] = []
                pollution_days[date].append({
                    "city": record["city"],
                    "aqi": record["aqi"],
                    "primary_pollutant": record.get("primary_pollutant"),
                })

        if not pollution_days:
            return {}

        # 聚合为污染过程（连续或相近的日期）
        events = []
        current_event = None

        for date in sorted(pollution_days.keys()):
            cities = pollution_days[date]

            if not current_event:
                current_event = {
                    "start_date": date,
                    "end_date": date,
                    "dates": [date],
                    "cities": set(c["city"] for c in cities),
                    "details": {}
                }
                current_event["details"][date] = cities
            else:
                # 判断是否连续（相差不超过2天）
                from datetime import datetime
                curr_date = datetime.strptime(date, "%Y-%m-%d")
                prev_date = datetime.strptime(current_event["end_date"], "%Y-%m-%d")
                delta = (curr_date - prev_date).days

                if delta <= 2:
                    # 继续当前污染过程
                    current_event["end_date"] = date
                    current_event["dates"].append(date)
                    current_event["cities"].update(c["city"] for c in cities)
                    current_event["details"][date] = cities
                else:
                    # 结束当前过程，开始新过程
                    events.append({
                        "start_date": current_event["start_date"],
                        "end_date": current_event["end_date"],
                        "dates": current_event["dates"],
                        "cities": list(current_event["cities"]),
                        "city_count": len(current_event["cities"]),
                        "details": current_event["details"],
                    })
                    current_event = {
                        "start_date": date,
                        "end_date": date,
                        "dates": [date],
                        "cities": set(c["city"] for c in cities),
                        "details": {}
                    }
                    current_event["details"][date] = cities

        # 添加最后一个过程
        if current_event:
            events.append({
                "start_date": current_event["start_date"],
                "end_date": current_event["end_date"],
                "dates": current_event["dates"],
                "cities": list(current_event["cities"]),
                "city_count": len(current_event["cities"]),
                "details": current_event["details"],
            })

        return {
            "month": f"{self.year}年{self.month}月",
            "pollution_days_count": len(pollution_days),
            "events": events,
            "total_events": len(events)
        }

    def generate_component_data(self, pollution_events: dict) -> List[Path]:
        """
        生成污染过程的组分数据

        Args:
            pollution_events: 污染过程数据

        Returns:
            生成的文件路径列表
        """
        print(f"[组分数据] 为 {len(pollution_events.get('events', []))} 个污染过程生成组分数据...")

        output_files = []

        # 为每个污染过程生成组分数据
        for event in pollution_events.get("events", []):
            start_date = event["start_date"]
            end_date = event["end_date"]
            cities = event["cities"]

            print(f"[组分数据] 污染过程 {start_date} 至 {end_date}，涉及 {len(cities)} 个城市")

            # 1. 常规污染物小时数据
            hourly_file = self._generate_hourly_pollution_data(start_date, end_date, cities)
            if hourly_file:
                output_files.append(hourly_file)

            # 2. VOCs组分数据（仅对有VOCs站点的城市）
            vocs_file = self._generate_vocs_data(start_date, end_date, cities)
            if vocs_file:
                output_files.append(vocs_file)

            # 3. PM2.5组分数据（仅对有组分站点的城市）
            pm25_comp_file = self._generate_pm25_component_data(start_date, end_date, cities)
            if pm25_comp_file:
                output_files.append(pm25_comp_file)

        # 生成组分数据清单
        manifest_file = self._generate_component_manifest(output_files)
        output_files.append(manifest_file)

        print(f"[组分数据] 已生成 {len(output_files)} 个文件")
        return output_files

    def _generate_hourly_pollution_data(self, start_date: str, end_date: str, cities: List[str]) -> Optional[Path]:
        """生成常规污染物小时数据（使用站点小时数据）"""
        print(f"  - 常规污染物小时数据：{start_date} 至 {end_date}")

        try:
            # 转换日期格式为带时间的格式
            start_datetime = f"{start_date} 00:00:00"
            end_datetime = f"{end_date} 23:59:59"

            # 查询站点小时数据（使用同步方法）
            result = execute_query_gd_suncere_station_hour(
                cities=cities,
                start_time=start_datetime,
                end_time=end_datetime,
                context=self.context,
                max_result_count=5000  # 增加限制以获取更多数据
            )

            if not result or "data" not in result or not result["data"]:
                print(f"    无小时数据")
                return None

            # 输出CSV
            filename = f"hourly_pollution_{start_date.replace('-', '')}_{end_date.replace('-', '')}.csv"
            output_file = self.output_dir / filename

            # 写入CSV
            self._write_hourly_csv(result["data"], output_file)

            print(f"    已生成：{output_file}")
            return output_file

        except Exception as e:
            print(f"    生成小时数据失败：{e}")
            return None

    def _write_hourly_csv(self, data: List[dict], output_file: Path):
        """写入小时数据CSV"""
        if not data:
            return

        # 假设数据是字典列表
        fieldnames = list(data[0].keys()) if data else []

        with open(output_file, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(data)

    def _generate_vocs_data(self, start_date: str, end_date: str, cities: List[str]) -> Optional[Path]:
        """生成VOCs组分数据（异步调用）"""
        print(f"  - VOCs组分数据：{start_date} 至 {end_date}")

        try:
            # 转换日期格式为带时间的格式
            start_datetime = f"{start_date} 00:00:00"
            end_datetime = f"{end_date} 23:59:59"

            # 异步调用VOCs工具
            async def fetch_vocs():
                return await self.vocs_tool.execute(
                    context=self.context,
                    start_time=start_datetime,
                    end_time=end_datetime,
                    locations=cities,
                    table_type=1,  # 小时数据
                    data_type=0    # 原始数据
                )

            result = asyncio.run(fetch_vocs())

            if not result or "data" not in result or not result["data"]:
                print(f"    无VOCs数据")
                return None

            # 输出CSV
            filename = f"vocs_components_{start_date.replace('-', '')}_{end_date.replace('-', '')}.csv"
            output_file = self.output_dir / filename

            # 写入CSV
            self._write_vocs_csv(result["data"], output_file)

            print(f"    已生成：{output_file}")
            return output_file

        except Exception as e:
            print(f"    生成VOCs数据失败：{e}")
            return None

    def _write_vocs_csv(self, data: List[dict], output_file: Path):
        """写入VOCs数据CSV"""
        if not data:
            return

        # 展开嵌套的组分字段
        flattened_data = []
        for record in data:
            flat_record = {
                "date": record.get("date") or record.get("time"),
                "city": record.get("city"),
                "station": record.get("station"),
            }

            # 添加组分
            components = record.get("components", {})
            if isinstance(components, dict):
                flat_record.update(components)

            flattened_data.append(flat_record)

        # 获取所有字段名
        fieldnames = []
        if flattened_data:
            fieldnames = list(flattened_data[0].keys())

        with open(output_file, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(flattened_data)

    def _generate_pm25_component_data(self, start_date: str, end_date: str, cities: List[str]) -> Optional[Path]:
        """生成PM2.5组分数据（异步调用）"""
        print(f"  - PM2.5组分数据：{start_date} 至 {end_date}")

        try:
            # 转换日期格式为带时间的格式
            start_datetime = f"{start_date} 00:00:00"
            end_datetime = f"{end_date} 23:59:59"

            # 异步调用PM2.5组分工具
            async def fetch_components():
                return await self.component_tool.execute(
                    context=self.context,
                    start_time=start_datetime,
                    end_time=end_datetime,
                    locations=cities,
                    time_granularity=1,  # 小时数据
                    data_type=0          # 原始数据
                )

            result = asyncio.run(fetch_components())

            if not result or "data" not in result or not result["data"]:
                print(f"    无PM2.5组分数据")
                return None

            # 输出CSV
            filename = f"pm25_components_{start_date.replace('-', '')}_{end_date.replace('-', '')}.csv"
            output_file = self.output_dir / filename

            # 写入CSV
            self._write_component_csv(result["data"], output_file)

            print(f"    已生成：{output_file}")
            return output_file

        except Exception as e:
            print(f"    生成PM2.5组分数据失败：{e}")
            return None

    def _write_component_csv(self, data: List[dict], output_file: Path):
        """写入组分数据CSV"""
        if not data:
            return

        # 展开嵌套的组分字段
        flattened_data = []
        for record in data:
            flat_record = {
                "date": record.get("date") or record.get("time"),
                "city": record.get("city"),
                "station": record.get("station"),
            }

            # 添加组分
            components = record.get("components", {})
            if isinstance(components, dict):
                flat_record.update(components)

            flattened_data.append(flat_record)

        # 获取所有字段名
        fieldnames = []
        if flattened_data:
            fieldnames = list(flattened_data[0].keys())

        with open(output_file, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(flattened_data)

    def _generate_component_manifest(self, output_files: List[Path]) -> Path:
        """生成组分数据清单"""
        manifest = {
            "month": f"{self.year}年{self.month}月",
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "files": [
                {
                    "name": f.name,
                    "type": self._identify_file_type(f.name),
                    "size": f.stat().st_size if f.exists() else 0,
                    "path": str(f)
                }
                for f in output_files
            ],
            "total_files": len(output_files)
        }

        manifest_file = self.output_dir / f"component_data_manifest_{self.year}{self.month:02d}.json"
        with open(manifest_file, "w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)

        print(f"[组分数据] 清单已生成：{manifest_file}")
        return manifest_file

    def _identify_file_type(self, filename: str) -> str:
        """识别文件类型"""
        if "hourly_pollution" in filename:
            return "常规污染物小时数据"
        elif "vocs_components" in filename:
            return "VOCs组分数据"
        elif "pm25_components" in filename:
            return "PM2.5组分数据"
        elif "manifest" in filename:
            return "数据清单"
        else:
            return "未知类型"

    def generate_all(self) -> Dict[str, Optional[Path]]:
        """
        生成所有补充数据

        Returns:
            生成的文件路径字典
        """
        print(f"\n{'='*60}")
        print(f"开始生成 {self.year}年{self.month}月 补充数据")
        print(f"{'='*60}\n")

        results = {}

        # 1. 区县排名
        try:
            results["district_ranking"] = self.generate_district_ranking()
        except Exception as e:
            print(f"[区县排名] 生成失败：{e}")
            results["district_ranking"] = None

        # 2. 高值站点
        try:
            results["station_high_value"] = self.generate_station_high_value()
        except Exception as e:
            print(f"[高值站点] 生成失败：{e}")
            results["station_high_value"] = None

        # 3. 污染过程识别
        try:
            pollution_events, events_file = self.identify_pollution_events()
            results["pollution_events"] = events_file

            # 4. 如果有污染过程，生成组分数据
            if pollution_events:
                component_files = self.generate_component_data(pollution_events)
                results["component_data"] = component_files
            else:
                results["component_data"] = []
        except Exception as e:
            print(f"[污染过程/组分] 生成失败：{e}")
            results["pollution_events"] = None
            results["component_data"] = []

        print(f"\n{'='*60}")
        print(f"生成完成！")
        print(f"输出目录：{self.output_dir}")
        print(f"{'='*60}\n")

        return results


def generate_monthly_supplements(year: int, month: int) -> Dict[str, Optional[Path]]:
    """
    生成月度补充数据的便捷函数

    Args:
        year: 年份，如2026
        month: 月份，如5

    Returns:
        生成的文件路径字典
    """
    generator = MonthlyAirQualitySupplements(year, month)
    return generator.generate_all()


# 测试代码
if __name__ == "__main__":
    # 生成2026年5月的补充数据
    results = generate_monthly_supplements(2026, 5)

    print("\n生成的文件：")
    for key, path in results.items():
        if isinstance(path, list):
            print(f"  {key}: {len(path)} 个文件")
            for p in path:
                print(f"    - {p}")
        elif path:
            print(f"  {key}: {path}")
        else:
            print(f"  {key}: 未生成")
