#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
生成4月会商文件脚本
"""
import asyncio
import shutil
from datetime import datetime
from pathlib import Path
import openpyxl
import sys
import structlog

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from app.fetchers.consultation import (
    ConsultationFileFetcher,
    SHEET_CONFIG,
    EXTRA_SHEET_CONFIG
)

logger = structlog.get_logger()

async def generate_april_file():
    """手动生成4月会商文件"""
    fetcher = ConsultationFileFetcher()

    # 手动设置4月时间范围
    time_range = {
        "start_date": "2026-04-01",
        "end_date": "2026-04-30",
        "period_description": "2026年4月份",
        "year": "2026",
        "month": "4",
        "last_year": "2025"
    }

    # 获取输出目录
    consultation_root = Path("/tmp/会商文件")
    month_dir = consultation_root / "2026年4月"
    month_dir.mkdir(parents=True, exist_ok=True)

    # 获取模板路径
    template_path = fetcher.template_dir / "月度会商模板（2026年1-2月）.xlsx"

    # 获取输出路径
    today_str = datetime.now().strftime("%Y%m%d")
    output_path = month_dir / f"月度会商模板（2026年4月）{today_str}.xlsx"

    print(f"生成4月会商文件: {output_path}")

    # 复制模板
    shutil.copy2(str(template_path), str(output_path))

    # 打开并填充数据
    wb = openpyxl.load_workbook(str(output_path))

    # 填充数据
    await fetcher._fill_pollutant_sheets(wb, time_range)
    await fetcher._fill_extra_sheets(wb, time_range)

    # 保存
    wb.save(str(output_path))
    wb.close()

    # 使用LibreOffice重新保存以保留图表
    print("使用LibreOffice重新保存以保留图表...")
    result = fetcher._resave_with_libreoffice(output_path)

    if result:
        print("✓ LibreOffice重新保存成功")
    else:
        print("⚠ LibreOffice重新保存失败，仅使用openpyxl保存")

    print(f"\n文件已生成: {output_path}")
    print("请检查文件中的历年1-2月浓度sheet的图表是否正常显示")

if __name__ == "__main__":
    asyncio.run(generate_april_file())
