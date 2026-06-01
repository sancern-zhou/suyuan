# -*- coding: utf-8 -*-
"""
年度累计会商文件 Fetcher

每月4号生成“年初到上个月月末”的会商 Excel 文件，确保上个月数据完成审核。
"""

import asyncio
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict

import structlog

from app.fetchers.consultation import ConsultationFileFetcher

logger = structlog.get_logger()


class AnnualYtdConsultationFileFetcher(ConsultationFileFetcher):
    """生成年度累计（年初到上个月月末）的会商文件。"""

    def __init__(self):
        super().__init__()
        self.name = "annual_ytd_consultation_file_fetcher"
        self.description = "年度累计会商文件 - 每月4号7点20分生成年初到上个月月末数据"
        self.schedule = "20 7 4 * *"
        self.version = "1.1.0"

    def _calculate_month_to_yesterday(self, full_month: bool = False) -> Dict[str, str]:
        """覆盖父类时间范围：年初到上个月月末。"""
        today = datetime.now()
        last_month = today.replace(day=1) - timedelta(days=1)
        target_year = last_month.year
        month = last_month.month

        start_date = datetime(target_year, 1, 1)

        return {
            "start_date": start_date.strftime("%Y-%m-%d"),
            "end_date": last_month.strftime("%Y-%m-%d"),
            "period_description": f"{target_year}年1-{month}月累计",
            "year": str(target_year),
            "month": f"{month:02d}",
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

    def _get_last_year_same_day(self, time_range: Dict[str, str], full_month: bool = False) -> str:
        """去年同期结束日：去年同月月末（与年度累计时间范围一致）。

        年度累计数据范围是"年初到上个月月末"，因此去年同期应该是：
        "去年1月1日到去年同月月末"，而不是"去年同一天"。
        """
        current_end = datetime.strptime(time_range["end_date"], "%Y-%m-%d")
        last_year = int(time_range["last_year"])

        # 获取去年同月的最后一天
        # 方法：先取去年同月的第一天，然后减去1天得到上个月月末
        last_year_month_start = current_end.replace(day=1, year=last_year)
        last_year_month_end = (last_year_month_start.replace(day=1) + timedelta(days=32)).replace(day=1) - timedelta(days=1)

        return last_year_month_end.strftime("%Y-%m-%d")

    async def fetch_and_store(self, full_month: bool = False):
        logger.info("annual_ytd_consultation_file_fetch_start")
        await super().fetch_and_store(full_month=True)
        logger.info("annual_ytd_consultation_file_fetch_complete")


async def main():
    fetcher = AnnualYtdConsultationFileFetcher()
    await fetcher.fetch_and_store()


if __name__ == "__main__":
    asyncio.run(main())
