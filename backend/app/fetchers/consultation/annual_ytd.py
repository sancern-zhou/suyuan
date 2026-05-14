# -*- coding: utf-8 -*-
"""
年度累计会商文件生成脚本

生成时间范围为“今年1月1日到昨天”的会商 Excel 文件。
不注册到现有调度器，可按需手动运行。
"""

import asyncio
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict
from unittest.mock import patch

import structlog

from app.fetchers.consultation import ConsultationFileFetcher

logger = structlog.get_logger()


class AnnualYtdConsultationFileFetcher(ConsultationFileFetcher):
    """生成年度累计（年初到昨天）的会商文件。"""

    def __init__(self):
        super().__init__()
        self.name = "annual_ytd_consultation_file_fetcher"
        self.description = "会商文件年度累计生成 - 生成今年1月1日到昨天的数据"
        self.schedule = ""
        self.version = "1.0.0"

    def _calculate_month_to_yesterday(self) -> Dict[str, str]:
        """覆盖父类时间范围：今年1月1日到昨天。"""
        today = datetime.now()
        yesterday = today - timedelta(days=1)

        if today.day == 1 and today.month == 1:
            target_year = today.year - 1
            yesterday = datetime(target_year, 12, 31)
        else:
            target_year = today.year

        start_date = datetime(target_year, 1, 1)
        month = yesterday.month

        return {
            "start_date": start_date.strftime("%Y-%m-%d"),
            "end_date": yesterday.strftime("%Y-%m-%d"),
            "period_description": f"{target_year}年1-{month}月累计（截至{month}月{yesterday.day}日）",
            "year": str(target_year),
            "month": str(month),
            "last_year": str(target_year - 1),
        }

    def _get_month_dir(self) -> Path:
        """年度累计文件单独放到当年目录下。"""
        time_range = self._calculate_month_to_yesterday()
        year = time_range["year"]
        return self.consultation_root / f"{year}年年度累计"

    def _get_template_path(self, time_range: Dict[str, str]) -> Path:
        """年度累计优先使用 1-当前月 累计模板。"""
        month = int(time_range["month"])

        cumulative_template = self.template_dir / f"月度会商模板（1-{month}月）.xlsx"
        if cumulative_template.exists():
            return cumulative_template

        return super()._get_template_path(time_range)

    def _get_output_path(self, time_range: Dict[str, str], month_dir: Path) -> Path:
        """年度累计输出文件名。"""
        year = time_range["year"]
        month = int(time_range["month"])
        today_str = datetime.now().strftime("%Y%m%d")
        return month_dir / f"年度累计会商文件（{year}年1-{month}月）{today_str}.xlsx"

    def _get_last_year_same_day(self, time_range: Dict[str, str]) -> str:
        """去年同期结束日：去年1月1日到去年同日。"""
        current_end = datetime.strptime(time_range["end_date"], "%Y-%m-%d")
        last_year = int(time_range["last_year"])

        try:
            last_year_date = current_end.replace(year=last_year)
        except ValueError:
            last_year_date = current_end.replace(year=last_year, day=28)

        return last_year_date.strftime("%Y-%m-%d")

    @contextmanager
    def _annual_ytd_datetime_context(self, time_range: Dict[str, str]):
        """
        父类部分额外 sheet 方法内部用 datetime.now() 和 month 计算去年起点。
        这里临时把该模块内的 datetime.now() 固定到“end_date 的后一天”，
        让父类计算逻辑与本脚本的年初累计时间范围一致。
        """
        fake_today = datetime.strptime(time_range["end_date"], "%Y-%m-%d") + timedelta(days=1)

        class FixedDatetime(datetime):
            @classmethod
            def now(cls, tz=None):
                if tz is not None:
                    return fake_today.replace(tzinfo=tz)
                return fake_today

        with patch("app.fetchers.consultation.datetime", FixedDatetime):
            yield

    async def _fill_pollutant_sheets(self, wb, time_range: Dict[str, str]):
        with self._annual_ytd_datetime_context(time_range):
            await super()._fill_pollutant_sheets(wb, time_range)

    async def _fill_extra_sheets(self, wb, time_range: Dict[str, str]):
        with self._annual_ytd_datetime_context(time_range):
            await super()._fill_extra_sheets(wb, time_range)

    async def fetch_and_store(self):
        logger.info("annual_ytd_consultation_file_fetch_start")
        await super().fetch_and_store()
        logger.info("annual_ytd_consultation_file_fetch_complete")


async def main():
    fetcher = AnnualYtdConsultationFileFetcher()
    await fetcher.fetch_and_store()


if __name__ == "__main__":
    asyncio.run(main())
