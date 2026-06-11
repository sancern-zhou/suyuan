"""
月度区县污染物排名数据生成脚本

生成全区县所有污染物（PM2.5、PM10、NO2、O3、AQI、CO、SO2）的排名和同比数据。

数据来源：execute_query_gd_suncere_district_report
输出文件：district_ranking_{yyyymm}.csv
"""

import csv
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any

import structlog

from app.tools.query.query_gd_suncere.tool import execute_query_gd_suncere_district_report
from app.agent.context.data_context_manager import DataContextManager
from app.db.session_repository import SessionRepository
from app.fetchers.consultation.city_mapping import normalize_city_identity
from app.fetchers.consultation.field_normalizer import DistrictFieldNormalizer
from app.fetchers.consultation.output_paths import get_monthly_consultation_dir

logger = structlog.get_logger()


class MonthlyDistrictPollutantRanking:
    """月度区县污染物排名生成器"""

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

        # 广东省21个地级市
        self.guangdong_cities = [
            "广州", "深圳", "珠海", "汕头", "佛山", "韶关", "湛江", "肇庆", "江门", "茂名",
            "惠州", "梅州", "汕尾", "河源", "阳江", "清远", "东莞", "中山", "潮州", "揭阳", "云浮"
        ]

    def _format_date(self, date: datetime) -> str:
        """格式化日期为 YYYY-MM-DD"""
        return date.strftime("%Y-%m-%d")

    def fetch_full_district_data(self, start_date: datetime, end_date: datetime) -> List[Dict[str, Any]]:
        """
        获取完整的区县数据

        API已支持分页获取全量数据，直接调用即可。

        Args:
            start_date: 开始日期
            end_date: 结束日期

        Returns:
            完整的区县数据列表
        """
        logger.info("fetch_district_data_start",
                   start_date=self._format_date(start_date),
                   end_date=self._format_date(end_date))

        try:
            # 调用API获取数据（使用return_all=True获取全量数据）
            result = execute_query_gd_suncere_district_report(
                start_time=self._format_date(start_date),
                end_time=self._format_date(end_date),
                cities=self.guangdong_cities,
                return_all=True  # 获取全量数据
            )

            # 检查返回结果
            if not result or result.get("status") != "success":
                logger.error("fetch_district_data_failed",
                           error=result.get("error"),
                           summary=result.get("summary"))
                return []

            # 获取数据
            data = result.get("data", [])
            if data:
                logger.info("fetch_district_data_success", record_count=len(data))
                return data
            else:
                logger.error("no_data_available")
                return []

        except Exception as e:
            logger.error("fetch_district_data_exception", error=str(e))
            return []

    def generate(self) -> Optional[Path]:
        """
        生成区县排名数据

        Returns:
            输出文件路径，失败返回None
        """
        print(f"[区县排名] 开始生成 {self.year}年{self.month}月 数据...")

        # 查询当月数据
        print(f"[区县排名] 查询当月数据...")
        current_data = self.fetch_full_district_data(self.start_date, self.end_date)

        # 查询去年同期数据
        print(f"[区县排名] 查询去年同期数据...")
        last_year_data = self.fetch_full_district_data(self.last_year_start, self.last_year_end)

        if not current_data:
            print(f"[区县排名] 当月数据为空，无法生成")
            return None

        # 解析数据
        current_parsed = self._parse_district_data(current_data)
        last_year_parsed = self._parse_district_data(last_year_data)

        print(f"[区县排名] 当月数据：{len(current_parsed)} 个区县")
        print(f"[区县排名] 去年同期数据：{len(last_year_parsed)} 个区县")

        # 计算同比并合并
        merged_data = self._merge_with_yoy(current_parsed, last_year_parsed)

        # 排序并输出
        output_file = self.output_dir / f"district_ranking_{self.year}{self.month:02d}.csv"
        self._write_district_csv(merged_data, output_file)

        print(f"[区县排名] 已生成：{output_file}")
        print(f"[区县排名] 区县数量：{len(merged_data)}")
        return output_file

    def _parse_district_data(self, data: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        """
        解析区县数据

        Args:
            data: API返回的原始数据列表

        Returns:
            区县名 -> 规范化数据的字典
        """
        parsed = {}

        for record in data:
            # 使用规范化器提取字段
            district = DistrictFieldNormalizer.extract_district(record)
            if not district:
                continue

            # 规范化记录
            normalized = DistrictFieldNormalizer.normalize_record(record)

            # 添加城市信息
            normalized["city"] = DistrictFieldNormalizer.extract_city(record)

            parsed[district] = normalized

        return parsed

    def _merge_with_yoy(self, current: Dict[str, Dict[str, Any]],
                       last_year: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        合并当期和去年同期数据，计算同比

        Args:
            current: 当期数据
            last_year: 去年同期数据

        Returns:
            合并后的数据列表
        """
        merged = []

        for district, curr_vals in current.items():
            last_vals = last_year.get(district, {})

            row = {
                "district": district,
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

    def _write_district_csv(self, data: List[Dict[str, Any]], output_file: Path):
        """
        写入区县排名CSV

        Args:
            data: 数据列表
            output_file: 输出文件路径
        """
        if not data:
            print(f"[区县排名] 数据为空，不生成文件")
            return

        # 构建字段名
        fieldnames = ["district", "city", "city_code"]
        for pollutant in self.POLLUTANTS:
            fieldnames.extend([pollutant, f"{pollutant}_yoy"])

        with open(output_file, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(data)


def generate_district_ranking(year: int, month: int) -> Optional[Path]:
    """
    生成月度区县污染物排名数据的便捷函数

    Args:
        year: 年份，如2026
        month: 月份，如5

    Returns:
        输出文件路径，失败返回None
    """
    generator = MonthlyDistrictPollutantRanking(year, month)
    return generator.generate()


def generate_district_pollutant_ranking(year: int, month: int) -> Optional[Path]:
    """Backward-compatible entry point used by tests and callers."""
    return generate_district_ranking(year, month)


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

    result = generate_district_ranking(year, month)
    if result:
        print(f"\n✓ 成功生成：{result}")
        sys.exit(0)
    else:
        print(f"\n✗ 生成失败")
        sys.exit(1)
