"""
月度高值站点数据生成脚本

识别高值站点：污染物浓度排名前十 OR 同比变差幅度排名前十

数据来源：execute_query_station_standard_report
输出文件：station_high_value_{yyyymm}.csv
"""

import csv
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any, Set, Tuple

import structlog

from app.tools.query.query_station_standard_report.tool import execute_query_station_standard_report
from app.fetchers.consultation.city_mapping import normalize_city_identity
from app.fetchers.consultation.field_normalizer import StationFieldNormalizer
from app.fetchers.consultation.output_paths import get_monthly_consultation_dir

logger = structlog.get_logger()


class MonthlyStationHighValues:
    """月度高值站点生成器"""

    # 污染物列表
    POLLUTANTS = ["pm25", "pm10", "no2", "o3", "aqi", "co", "so2"]

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

        # 去年同期（用于同比计算）
        self.last_year_start = datetime(year - 1, month, 1)
        if month == 12:
            self.last_year_end = datetime(year, 1, 1) - timedelta(days=1)
        else:
            self.last_year_end = datetime(year - 1, month + 1, 1) - timedelta(days=1)

        # 输出目录
        self.output_dir = get_monthly_consultation_dir(year, month)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def _format_date(self, date: datetime) -> str:
        """格式化日期为 YYYY-MM-DD"""
        return date.strftime("%Y-%m-%d")

    def fetch_full_station_data(self, start_date: datetime, end_date: datetime) -> List[Dict[str, Any]]:
        """
        获取完整的站点数据

        站点API返回结构：
        - result["data"]: 前5条预览数据
        - result["result"]: 完整数据（1589条）
        - result["report_data_id"]: 外部化存储ID

        Args:
            start_date: 开始日期
            end_date: 结束日期

        Returns:
            完整的站点数据列表
        """
        logger.info("fetch_station_data_start",
                   start_date=self._format_date(start_date),
                   end_date=self._format_date(end_date))

        try:
            # 调用API获取数据
            result = execute_query_station_standard_report(
                start_time=self._format_date(start_date),
                end_time=self._format_date(end_date),
                max_result_count=10000  # 设置较大的限制
            )

            # 检查返回结果
            if not result or result.get("status") != "success":
                logger.error("fetch_station_data_failed",
                           error=result.get("error"),
                           summary=result.get("summary"))
                return []

            # 优先从 result["result"] 获取完整数据（1589条）
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
                    # 使用 data_registry 读取完整数据包
                    from app.services.data_registry import data_registry

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

    def generate(self) -> Optional[Path]:
        """
        生成高值站点数据

        Returns:
            输出文件路径，失败返回None
        """
        print(f"[高值站点] 开始生成 {self.year}年{self.month}月 数据...")

        # 查询当月数据
        print(f"[高值站点] 查询当月数据...")
        current_data = self.fetch_full_station_data(self.start_date, self.end_date)

        # 查询去年同期数据
        print(f"[高值站点] 查询去年同期数据...")
        last_year_data = self.fetch_full_station_data(self.last_year_start, self.last_year_end)

        if not current_data:
            print(f"[高值站点] 当月数据为空，无法生成")
            return None

        # 解析数据
        current_parsed = self._parse_station_data(current_data)
        last_year_parsed = self._parse_station_data(last_year_data)

        print(f"[高值站点] 当月数据：{len(current_parsed)} 个站点")
        print(f"[高值站点] 去年同期数据：{len(last_year_parsed)} 个站点")

        # 计算同比并合并
        merged_data = self._merge_station_with_yoy(current_parsed, last_year_parsed)

        # 识别高值站点
        high_value_stations = self._identify_high_value_stations(merged_data)

        if not high_value_stations:
            print(f"[高值站点] 未识别到高值站点")
            return None

        # 排序并输出
        output_file = self.output_dir / f"station_high_value_{self.year}{self.month:02d}.csv"
        self._write_station_csv(high_value_stations, output_file)

        print(f"[高值站点] 已生成：{output_file}")
        print(f"[高值站点] 高值站点数量：{len(high_value_stations)}")
        return output_file

    def _parse_station_data(self, data: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        """
        解析站点数据

        Args:
            data: API返回的原始数据列表

        Returns:
            站点名 -> 规范化数据的字典
        """
        parsed = {}

        for record in data:
            # 使用规范化器提取字段
            station = StationFieldNormalizer.extract_station(record)
            if not station:
                continue

            # 规范化记录
            normalized = StationFieldNormalizer.normalize_record(record)

            # 添加城市信息
            normalized["city"] = StationFieldNormalizer.extract_city(record)

            parsed[station] = normalized

        return parsed

    def _merge_station_with_yoy(self, current: Dict[str, Dict[str, Any]],
                                last_year: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        合并当期和去年同期站点数据，计算同比

        Args:
            current: 当期数据
            last_year: 去年同期数据

        Returns:
            合并后的数据列表
        """
        merged = []

        for station, curr_vals in current.items():
            last_vals = last_year.get(station, {})

            row = {
                "station": station,
            }
            city_name, city_code = normalize_city_identity(
                curr_vals.get("city") or curr_vals.get("city_code") or last_vals.get("city") or last_vals.get("city_code")
            )
            row["city"] = city_name
            row["city_code"] = city_code

            # 添加污染物浓度和同比
            for pollutant in self.POLLUTANTS:
                curr_val = curr_vals.get(pollutant)
                last_val = last_vals.get(pollutant)

                row[pollutant] = curr_val

                # 计算同比
                if curr_val is not None and last_val is not None and last_val != 0:
                    yoy = (curr_val - last_val) / last_val * 100
                    row[f"{pollutant}_yoy"] = round(yoy, 1)
                else:
                    row[f"{pollutant}_yoy"] = None

            merged.append(row)

        return merged

    def _identify_high_value_stations(self, data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        识别高值站点

        高值定义：污染物浓度排名前十 OR 同比变差幅度排名前十

        Args:
            data: 站点数据列表

        Returns:
            高值站点列表
        """
        high_value_station_set: Set[Tuple[str, str]] = set()

        # 对每个污染物，找出浓度TOP10和同比变差TOP10
        for pollutant in self.POLLUTANTS:
            # 浓度TOP10（降序，值越高越差）
            by_concentration = sorted(
                [d for d in data if d.get(pollutant) is not None],
                key=lambda x: x[pollutant],
                reverse=True
            )[:10]
            for item in by_concentration:
                reason = f"{pollutant}_浓度"
                high_value_station_set.add((item["station"], reason))

            # 同比变差TOP10（同比值升序，正值越大越差）
            yoy_field = f"{pollutant}_yoy"
            by_yoy = sorted(
                [d for d in data if d.get(yoy_field) is not None],
                key=lambda x: x[yoy_field],
                reverse=True
            )[:10]
            for item in by_yoy:
                reason = f"{pollutant}_同比"
                high_value_station_set.add((item["station"], reason))

        # 去重并构建结果
        station_names: Set[str] = set()
        result = []

        for station_name, reason in high_value_station_set:
            if station_name in station_names:
                continue

            station_names.add(station_name)

            # 找到该站点的完整数据
            station_data = next((d for d in data if d["station"] == station_name), None)
            if station_data:
                row = station_data.copy()
                row["high_value_reason"] = reason
                result.append(row)

        # 按高值原因排序
        result.sort(key=lambda x: x["high_value_reason"])

        return result

    def _write_station_csv(self, data: List[Dict[str, Any]], output_file: Path):
        """
        写入高值站点CSV

        Args:
            data: 数据列表
            output_file: 输出文件路径
        """
        if not data:
            print(f"[高值站点] 数据为空，不生成文件")
            return

        # 构建字段名
        fieldnames = ["station", "city", "city_code", "high_value_reason"]
        for pollutant in self.POLLUTANTS:
            fieldnames.extend([pollutant, f"{pollutant}_yoy"])

        with open(output_file, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(data)


def generate_station_high_values(year: int, month: int) -> Optional[Path]:
    """
    生成月度高值站点数据的便捷函数

    Args:
        year: 年份，如2026
        month: 月份，如5

    Returns:
        输出文件路径，失败返回None
    """
    generator = MonthlyStationHighValues(year, month)
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

    result = generate_station_high_values(year, month)
    if result:
        print(f"\n✓ 成功生成：{result}")
        sys.exit(0)
    else:
        print(f"\n✗ 生成失败")
        sys.exit(1)
