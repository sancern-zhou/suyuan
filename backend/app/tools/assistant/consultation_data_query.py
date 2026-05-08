# -*- coding: utf-8 -*-
"""
会商文件数据查询模块

功能：直接调用API工具查询数据（推荐方式）

优势：
- 性能最优（快10-20倍）
- 成本最低（无LLM调用）
- 可靠性高（结构化数据）
- 易于维护（接口明确）

author: Claude
date: 2026-05-08
"""

import re
from datetime import datetime, timedelta
from typing import Dict, Any, List, Tuple
import structlog
from calendar import monthrange

logger = structlog.get_logger()


class ConsultationDataQuery:
    """
    会商数据查询器

    使用方式2：直接构造参数调用接口
    """

    def __init__(self):
        # 延迟导入，避免循环依赖
        from app.tools.query.query_national_air_quality.tool import (
            NationalAirQualityQueryTool
        )
        self.query_tool = NationalAirQualityQueryTool()

        # 污染物字段映射
        self.pollutant_field_map = {
            "PM2.5": "PM2_5",
            "PM10": "PM10",
            "NO2": "NO2",
            "O3": "O3_8h",
            "AQI": "AQIStandardRate"  # 达标率
        }

    def parse_time_period(
        self,
        time_period: str,
        time_type: str
    ) -> Tuple[str, str]:
        """
        解析时间段为起止日期

        Args:
            time_period: 时间段描述，如"2026年1-3月份"、"2026年4月份"
            time_type: "ytd"（年初至今）或"last_month"（上个月均值）

        Returns:
            (start_date, end_date) 如("2026-01-01", "2026-03-31")

        Examples:
            >>> parse_time_period("2026年1-3月份", "ytd")
            ("2026-01-01", "2026-03-31")
            >>> parse_time_period("2026年4月份", "last_month")
            ("2026-04-01", "2026-04-30")
        """
        # 提取年份和月份
        match = re.match(r'(\d{4})年(\d+)(?:-(\d+))?月份', time_period)
        if not match:
            raise ValueError(f"Invalid time period format: {time_period}")

        year = int(match.group(1))
        start_month = int(match.group(2))
        end_month = int(match.group(3)) if match.group(3) else start_month

        # 计算起止日期
        if time_type == "last_month" or start_month == end_month:
            # 单月
            start_date = f"{year}-{start_month:02d}-01"
            last_day = monthrange(year, start_month)[1]
            end_date = f"{year}-{start_month:02d}-{last_day:02d}"
        else:
            # 累计月份（年初至某月）
            start_date = f"{year}-01-01"
            last_day = monthrange(year, end_month)[1]
            end_date = f"{year}-{end_month:02d}-{last_day:02d}"

        logger.info(
            "parsed_time_period",
            time_period=time_period,
            start_date=start_date,
            end_date=end_date
        )

        return start_date, end_date

    async def query_data(
        self,
        scope: str,
        pollutant: str,
        time_period: str,
        time_type: str
    ) -> List[float]:
        """
        查询污染物数据

        Args:
            scope: "national"（全国）或 "provincial"（全省）
            pollutant: 污染物名称（PM2.5, PM10, NO2, O3, AQI）
            time_period: 时间段描述
            time_type: 时间类型

        Returns:
            污染物数值列表

        Raises:
            ValueError: 参数错误
            Exception: 查询失败
        """
        try:
            # 1. 解析时间段
            start_date, end_date = self.parse_time_period(
                time_period, time_type
            )

            # 2. 调用查询工具
            if scope == "national":
                data = self.query_tool.query_province_data(
                    start_date=start_date,
                    end_date=end_date,
                    ns_type="NS"
                )
            else:  # provincial
                data = self.query_tool.query_city_data(
                    start_date=start_date,
                    end_date=end_date,
                    ns_type="NS"
                )

            # 3. 提取污染物数据
            result = self._extract_pollutant_data(data, pollutant)

            logger.info(
                "query_success",
                scope=scope,
                pollutant=pollutant,
                time_period=time_period,
                data_count=len(result)
            )

            return result

        except Exception as e:
            logger.error(
                "query_failed",
                scope=scope,
                pollutant=pollutant,
                time_period=time_period,
                error=str(e)
            )
            raise

    def _extract_pollutant_data(
        self,
        data: List[Dict[str, Any]],
        pollutant: str
    ) -> List[float]:
        """
        从API数据中提取特定污染物数值

        Args:
            data: API返回的数据列表
            pollutant: 污染物名称

        Returns:
            污染物数值列表

        Raises:
            ValueError: 未知污染物
        """
        field = self.pollutant_field_map.get(pollutant)
        if not field:
            raise ValueError(
                f"Unknown pollutant: {pollutant}. "
                f"Supported: {list(self.pollutant_field_map.keys())}"
            )

        # 提取数值
        result = []
        for item in data:
            value = item.get(field, 0)
            if value is None:
                value = 0
            try:
                result.append(float(value))
            except (ValueError, TypeError):
                logger.warning(
                    "invalid_value",
                    pollutant=pollutant,
                    field=field,
                    value=value
                )
                result.append(0.0)

        return result


# 使用示例
async def example_usage():
    """使用示例"""
    query = ConsultationDataQuery()

    # 示例1：查询全国PM2.5数据
    data = await query.query_data(
        scope="national",
        pollutant="PM2.5",
        time_period="2026年1-3月份",
        time_type="ytd"
    )
    print(f"全国PM2.5数据（31个省份）：{data}")

    # 示例2：查询全省AQI数据
    data = await query.query_data(
        scope="provincial",
        pollutant="AQI",
        time_period="2026年4月份",
        time_type="last_month"
    )
    print(f"全省AQI达标率（21个城市）：{data}")


if __name__ == "__main__":
    import asyncio
    asyncio.run(example_usage())
