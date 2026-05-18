# -*- coding: utf-8 -*-
"""
月度完整会商文件 Fetcher

每月4号早上7点10分生成上个月完整会商文件（1号-月末），确保数据审核完成。

author: Claude
date: 2026-05-16
"""

from app.fetchers.consultation import ConsultationFileFetcher


class MonthlyConsultationFileFetcher(ConsultationFileFetcher):
    """
    月度完整会商文件数据获取器（继承自 ConsultationFileFetcher）

    功能：
    - 每月4号早上7点10分生成上个月完整会商文件（1号-月末）
    - 确保上个月数据完成审核
    - 使用用户提供的Excel模板
    - 脚本仅填充原始数据（地区名、去年数据、今年数据）
    - 保留模板中的图表、公式和格式

    调度周期：
    - 每月4号早上7点10分自动生成 (Cron: 10 7 4 * *)
    - 手动触发 consultation_file_fetcher 时级联触发

    数据来源：全国/全省空气质量API
    输出目录：/tmp/A会商文件/{年月}/
    模板目录：/tmp/A会商文件/模板/
    """

    def __init__(self):
        # 调用父类 __init__，但覆盖部分属性
        super().__init__()
        self.name = "monthly_consultation_file_fetcher"
        self.description = "月度完整会商文件 - 每月4号7点10分生成上个月完整数据（1号-月末）"
        self.schedule = "10 7 4 * *"  # 每月4号早上7点10分

    def _calculate_month_to_yesterday(self, full_month: bool = False):
        """
        重写父类方法：总是返回上个月的完整时间范围

        Args:
            full_month: 忽略此参数，总是返回上个月完整数据

        Returns:
            上个月完整时间范围
        """
        from datetime import datetime, timedelta
        from calendar import monthrange

        today = datetime.now()
        # 计算上个月
        last_month = today.replace(day=1) - timedelta(days=1)

        year = last_month.year
        month = last_month.month
        last_day = monthrange(year, month)[1]

        return {
            "start_date": f"{year}-{month:02d}-01",
            "end_date": f"{year}-{month:02d}-{last_day}",
            "period_description": f"{year}年{int(month):02d}月份",
            "year": str(year),
            "month": f"{int(month):02d}",
            "last_year": str(year - 1),
        }

    def _get_month_dir(self):
        """
        重写父类方法：上个月的文件放在上个月的目录中
        """
        from pathlib import Path
        time_range = self._calculate_month_to_yesterday()
        year = time_range["year"]
        month = time_range["month"]
        return self.consultation_root / f"{year}年{month}月"

    async def fetch_and_store(self, full_month: bool = False):
        """
        重写父类方法：强制使用完整月份模式

        Args:
            full_month: 忽略此参数，总是使用完整月份模式
        """
        # 强制设置 full_month=True，确保去年同期也是整月数据
        return await super().fetch_and_store(full_month=True)


# 导出
__all__ = ["MonthlyConsultationFileFetcher"]
