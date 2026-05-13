# -*- coding: utf-8 -*-
"""
会商文件批量更新 Fetcher

每天早上7点自动生成"当月累积（截至昨日）"的会商Excel文件

功能：
- 每月自动创建子文件夹（如 /tmp/会商文件/2026年1月/）
- 每天早上7点更新数据（覆盖历史文件）
- 使用用户提供的Excel模板，脚本仅填充原始数据，保留模板图表和公式
- 数据范围：本月1号 → 昨天
- 自动数据验证

调度周期：每天早上7点 (Cron: 0 7 * * *)
数据来源：全国/全省空气质量API
输出目录：/tmp/会商文件/{年月}/
模板目录：/tmp/会商文件/模板/

author: Claude
date: 2026-05-08
"""

import shutil
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, List, Tuple
import structlog

from app.fetchers.base.fetcher_interface import DataFetcher

logger = structlog.get_logger()


# 污染物配置
POLLUTANTS_CONFIG = {
    "PM2.5": {"unit": "μg/m³", "normal_range": (5, 150)},
    "PM10": {"unit": "μg/m³", "normal_range": (10, 300)},
    "NO2": {"unit": "μg/m³", "normal_range": (5, 100)},
    "O3": {"unit": "μg/m³", "normal_range": (10, 160)},
    "AQI": {"unit": "", "normal_range": (80, 100), "is_rate": True}
}


# Sheet 填充配置：定义每个sheet的数据区域、列映射和表头更新规则
SHEET_CONFIG = {
    # ========== 全国污染物 sheet ==========
    "全国PM2.5": {
        "scope": "national",
        "pollutant": "PM2.5",
        "data_rows": (2, 32),
        "name_col": "A",
        "current_col": "B",
        "last_year_col": "D",
        "sort_copies": [
            {
                "source_name_col": "A",
                "source_value_col": "B",
                "target_name_col": "M",
                "target_value_col": "N",
                "sort_ascending": True,
                "calculate_diff": True,  # N列计算同比差值
            },
            {
                "source_name_col": "A",
                "source_value_col": "D",
                "target_name_col": "W",
                "target_value_col": "X",
                "sort_ascending": True,  # 按D列（去年数据）升序
            }
        ],
        "headers": {
            "B1": "{year}{month:02d}",
            "D1": "{last_year}{month:02d}",
        }
    },
    "全国PM10": {
        "scope": "national",
        "pollutant": "PM10",
        "data_rows": (2, 32),
        "name_col": "A",
        "current_col": "B",
        "last_year_col": "D",
        "sort_copies": [
            {
                "source_name_col": "A",
                "source_value_col": "B",
                "target_name_col": "M",
                "target_value_col": "N",
                "sort_ascending": True,
                "calculate_diff": True,  # N列计算同比差值
            },
            {
                "source_name_col": "A",
                "source_value_col": "D",
                "target_name_col": "W",
                "target_value_col": "X",
                "sort_ascending": True,  # 按D列（去年数据）升序
            }
        ],
        "headers": {
            "B1": "{year}{month:02d}",
            "D1": "{last_year}{month:02d}",
        }
    },
    "全国NO2": {
        "scope": "national",
        "pollutant": "NO2",
        "data_rows": (2, 32),
        "name_col": "A",
        "current_col": "B",
        "last_year_col": "D",
        "sort_copies": [
            {
                "source_name_col": "A",
                "source_value_col": "B",
                "target_name_col": "M",
                "target_value_col": "N",
                "sort_ascending": True,
                "calculate_diff": True,  # N列计算同比差值
            },
            {
                "source_name_col": "A",
                "source_value_col": "D",
                "target_name_col": "W",
                "target_value_col": "X",
                "sort_ascending": True,  # 按D列（去年数据）升序
            }
        ],
        "headers": {
            "B1": "{year}{month:02d}",
            "D1": "{last_year}{month:02d}",
        }
    },
    "全国O3": {
        "scope": "national",
        "pollutant": "O3",
        "data_rows": (2, 32),
        "name_col": "A",
        "current_col": "B",
        "last_year_col": "D",
        "sort_copies": [
            {
                "source_name_col": "A",
                "source_value_col": "B",
                "target_name_col": "M",
                "target_value_col": "N",
                "sort_ascending": True,
                "calculate_diff": True,  # N列计算同比差值
            },
            {
                "source_name_col": "A",
                "source_value_col": "D",
                "target_name_col": "W",
                "target_value_col": "X",
                "sort_ascending": True,  # 按D列（去年数据）升序
            }
        ],
        "headers": {
            "B1": "{year}{month:02d}",
            "D1": "{last_year}{month:02d}",
        }
    },
    "全国AQI": {
        "scope": "national",
        "pollutant": "AQI",
        "data_rows": (2, 32),
        "name_col": "A",
        "current_col": "B",
        "last_year_col": "D",
        "sort_copies": [
            {
                "source_name_col": "A",
                "source_value_col": "B",
                "target_name_col": "I",
                "target_value_col": "K",
                "extra_targets": [
                    {"col": "J", "data_source": "last_year"},
                    {"col": "L", "data_source": "diff_pct"},
                ],
                "sort_ascending": False,  # AQI达标率越高越好，降序
            },
            {
                "source_name_col": "A",
                "source_value_col": "D",
                "target_name_col": "W",
                "target_value_col": "X",
                "sort_ascending": True,  # 按D列（去年数据）升序
            }
        ],
        "headers": {
            "B1": "过渡期达标率",
            "J1": "{last_year}年过渡期达标率",
            "K1": "{year}年过渡期达标率",
        }
    },
    # ========== 全省污染物 sheet ==========
    "全省PM2.5": {
        "scope": "provincial",
        "pollutant": "PM2.5",
        "data_rows": (2, 22),
        "name_col": "A",
        "current_col": "B",
        "last_year_col": "D",
        "sort_copies": [
            {
                "source_name_col": "A",
                "source_value_col": "B",
                "target_name_col": "M",
                "target_value_col": "N",
                "sort_ascending": True,
                "calculate_diff": True,  # 计算同比差值
            },
            {
                "source_name_col": "A",
                "source_value_col": "D",
                "target_name_col": "W",
                "target_value_col": "X",
                "sort_ascending": True,  # 按D列（去年数据）升序
            }
        ],
        "headers": {
            "B1": "{year}浓度",
        }
    },
    "全省PM10": {
        "scope": "provincial",
        "pollutant": "PM10",
        "data_rows": (2, 22),
        "name_col": "A",
        "current_col": "B",
        "last_year_col": "D",
        "sort_copies": [
            {
                "source_name_col": "A",
                "source_value_col": "B",
                "target_name_col": "M",
                "target_value_col": "N",
                "sort_ascending": True,
                "calculate_diff": True,  # N列计算同比差值
            },
            {
                "source_name_col": "A",
                "source_value_col": "D",
                "target_name_col": "W",
                "target_value_col": "X",
                "sort_ascending": True,  # 按D列（去年数据）升序
            }
        ],
        "headers": {
            "B1": "{year}年{month}月达标率",
        }
    },
    "全省NO2": {
        "scope": "provincial",
        "pollutant": "NO2",
        "data_rows": (2, 22),
        "name_col": "A",
        "current_col": "B",
        "last_year_col": "D",
        "sort_copies": [
            {
                "source_name_col": "A",
                "source_value_col": "B",
                "target_name_col": "M",
                "target_value_col": "N",
                "sort_ascending": True,
                "calculate_diff": True,  # 计算同比差值
            },
            {
                "source_name_col": "A",
                "source_value_col": "D",
                "target_name_col": "W",
                "target_value_col": "X",
                "sort_ascending": True,  # 按D列（去年数据）升序
            }
        ],
        "headers": {
            "B1": "{year}浓度",
        }
    },
    "全省O3": {
        "scope": "provincial",
        "pollutant": "O3",
        "data_rows": (2, 22),
        "name_col": "A",
        "current_col": "B",
        "last_year_col": "D",
        "sort_copies": [
            {
                "source_name_col": "A",
                "source_value_col": "B",
                "target_name_col": "M",
                "target_value_col": "N",
                "sort_ascending": True,
                "calculate_diff": True,  # 计算同比差值
            },
            {
                "source_name_col": "A",
                "source_value_col": "D",
                "target_name_col": "W",
                "target_value_col": "X",
                "sort_ascending": True,  # 按D列（去年数据）升序
            }
        ],
        "headers": {
            "B1": "{year}浓度",
        }
    },
    "全省AQI": {
        "scope": "provincial",
        "pollutant": "AQI",
        "data_rows": (2, 22),
        "name_col": "A",
        "current_col": "B",
        "last_year_col": "D",
        "sort_copies": [
            {
                "source_name_col": "A",
                "source_value_col": "B",
                "target_name_col": "G",
                "target_value_col": None,
                "extra_targets": [
                    {"col": "H", "data_source": "diff_pct"},
                ],
                "sort_ascending": False,  # 达标率越高越好
            },
            {
                "source_name_col": "A",
                "source_value_col": "D",
                "target_name_col": "W",
                "target_value_col": "X",
                "sort_ascending": True,  # 按D列（去年数据）升序
            }
        ],
        "headers": {
            "B1": "{year}年{month}月达标率",
        }
    },
}

# 额外sheet配置
EXTRA_SHEET_CONFIG = {
    "X月全国排名": {
        "data_rows": (3, 32),  # 从第3行开始填充数据（第1行标题，第2行表头）
        "columns": [
            {"pollutant": "PM2.5", "name_col": "A", "value_col": "B", "rank_col": "C", "sort_ascending": True},
            {"pollutant": "PM10", "name_col": "D", "value_col": "E", "rank_col": "F", "sort_ascending": True},
            {"pollutant": "NO2", "name_col": "G", "value_col": "H", "rank_col": "I", "sort_ascending": True},
            {"pollutant": "O3", "name_col": "J", "value_col": "K", "rank_col": "L", "sort_ascending": True},
            {"pollutant": "AQI", "name_col": "M", "value_col": "N", "rank_col": "O", "sort_ascending": False},
        ]
    },
    "全省同比": {
        "data_rows": (3, 9),
        "mapping": {
            3: "PM2.5",
            4: "PM10",
            5: "NO2",
            6: "O3",
            7: "AQI",
            8: "AQI",
            9: "AQI",
        },
        "last_year_col": "B",
        "current_col": "C",
        "transition_col": "D",  # 仅第7行
        "headers": {
            "B2": "{last_year}年{month}月",
            "C2": "{year}年{month}月",
        }
    },
    "历年1-2月浓度": {
        "data_rows": (2, 14),  # 2014-2026年（13年数据）
        "columns": [
            {"pollutant": "AQI", "col": "B", "field": "compliance_rate"},
            {"pollutant": "PM2.5", "col": "C", "field": "PM2_5"},
            {"pollutant": "PM10", "col": "D", "field": "PM10"},
            {"pollutant": "NO2", "col": "E", "field": "NO2"},
            {"pollutant": "O3", "col": "F", "field": "O3_8h_P90"},
            {"pollutant": "SO2", "col": "G", "field": "SO2"},
            {"pollutant": "CO", "col": "H", "field": "CO_P95"},
        ],
        "year_col": "A",  # 年份列
        "start_year": 2014,  # 起始年份
    },
}


class ConsultationFileFetcher(DataFetcher):
    """
    会商文件批量更新数据获取器

    功能：
    - 每天早上7点自动更新会商Excel文件
    - 使用用户提供的Excel模板
    - 脚本仅填充原始数据（地区名、去年数据、今年数据）
    - 保留模板中的图表、公式和格式
    - 数据范围：本月1号 → 昨天
    """

    def __init__(self):
        super().__init__(
            name="consultation_file_fetcher",
            description="会商文件批量更新 - 每天7点生成当月累积数据（截至昨日）",
            schedule="0 7 * * *",
            version="2.0.0"
        )

        # 会商文件根目录
        self.consultation_root = Path("/tmp/会商文件")
        self.consultation_root.mkdir(parents=True, exist_ok=True)

        # 模板目录
        self.template_dir = self.consultation_root / "模板"
        self.template_dir.mkdir(parents=True, exist_ok=True)

    async def fetch_and_store(self):
        """
        获取并存储会商数据

        流程：
        1. 计算时间范围（本月1号 → 昨天）
        2. 创建当月子目录
        3. 复制模板到输出目录
        4. 查询全国/全省空气质量数据
        5. 填充模板各sheet（保留图表和公式）
        6. 保存文件
        """
        try:
            logger.info("consultation_file_fetch_start")

            # 计算时间范围
            time_range = self._calculate_month_to_yesterday()
            logger.info(
                "consultation_file_time_range",
                start_date=time_range["start_date"],
                end_date=time_range["end_date"],
                period_description=time_range["period_description"]
            )

            # 创建当月子目录
            month_dir = self._get_month_dir()
            month_dir.mkdir(parents=True, exist_ok=True)
            logger.info("consultation_file_month_dir", month_dir=str(month_dir))

            # 复制模板到输出目录
            template_path = self._get_template_path(time_range)
            output_path = self._get_output_path(time_range, month_dir)

            if not template_path.exists():
                logger.error("template_not_found", template_path=str(template_path))
                raise FileNotFoundError(f"模板文件不存在: {template_path}")

            shutil.copy2(str(template_path), str(output_path))
            logger.info("template_copied", template=str(template_path), output=str(output_path))

            # 打开工作簿并填充数据
            import openpyxl
            wb = openpyxl.load_workbook(str(output_path))

            # 填充10个污染物sheet
            await self._fill_pollutant_sheets(wb, time_range)

            # 填充额外sheet
            await self._fill_extra_sheets(wb, time_range)

            # 保存
            wb.save(str(output_path))
            wb.close()

            # 使用LibreOffice重新保存以正确保留图表渲染
            self._resave_with_libreoffice(output_path)

            logger.info(
                "consultation_file_fetch_complete",
                output_path=str(output_path),
                sheets_updated=len(SHEET_CONFIG) + len(EXTRA_SHEET_CONFIG)
            )

        except Exception as e:
            logger.error("consultation_file_fetch_failed", error=str(e), exc_info=True)
            raise

    def _get_template_path(self, time_range: Dict[str, str]) -> Path:
        """
        获取模板文件路径

        模板命名规则：
        - 单月模板：月度会商模板（某月）.xlsx
        - 累计模板：月度会商模板（1-某月）.xlsx
        """
        year = time_range["year"]
        month = int(time_range["month"])

        # 尝试单月模板
        single_template = self.template_dir / f"月度会商模板（{year}年{month}月）.xlsx"
        if single_template.exists():
            return single_template

        # 尝试累计模板
        cumulative_template = self.template_dir / f"月度会商模板（1-{month}月）.xlsx"
        if cumulative_template.exists():
            return cumulative_template

        # 回退：查找任意匹配的模板
        for f in self.template_dir.glob("月度会商模板*.xlsx"):
            return f

        return single_template

    def _get_output_path(self, time_range: Dict[str, str], month_dir: Path) -> Path:
        """获取输出文件路径"""
        year = time_range["year"]
        month = int(time_range["month"])
        today_str = datetime.now().strftime("%Y%m%d")
        return month_dir / f"月度会商模板（{year}年{month}月）{today_str}.xlsx"

    def _calculate_month_to_yesterday(self) -> Dict[str, str]:
        """
        计算本月1号到昨天的时间范围

        Returns:
            {
                "start_date": "2026-01-01",
                "end_date": "2026-01-15",
                "period_description": "2026年1月份累计（截至1月15日）",
                "year": "2026",
                "month": "1",
                "last_year": "2025"
            }
        """
        today = datetime.now()
        yesterday = today - timedelta(days=1)

        # 本月1号
        first_day_of_month = today.replace(day=1)

        # 昨天（如果今天是1号，则昨天是上个月最后一天）
        if today.day == 1:
            last_month = today.replace(day=1) - timedelta(days=1)
            first_day_of_month = last_month.replace(day=1)
            yesterday = last_month
            year = str(last_month.year)
            month = str(last_month.month)
        else:
            year = str(today.year)
            month = str(today.month)

        start_date = first_day_of_month.strftime("%Y-%m-%d")
        end_date = yesterday.strftime("%Y-%m-%d")

        # 生成时间段描述
        if first_day_of_month.month == yesterday.month:
            if yesterday.day == first_day_of_month.day:
                period_description = f"{year}年{month}月份累计（截至{month}月1日）"
            else:
                period_description = f"{year}年{month}月份累计（截至{month}月{yesterday.day}日）"
        else:
            period_description = f"{year}年{month}月份"

        return {
            "start_date": start_date,
            "end_date": end_date,
            "period_description": period_description,
            "year": year,
            "month": month,
            "last_year": str(int(year) - 1),
        }

    def _get_month_dir(self) -> Path:
        """获取当月子目录路径"""
        today = datetime.now()
        if today.day == 1:
            last_month = today.replace(day=1) - timedelta(days=1)
            year = last_month.year
            month = last_month.month
        else:
            year = today.year
            month = today.month
        month_dir_name = f"{year}年{month}月"
        return self.consultation_root / month_dir_name

    def _get_last_day_of_month(self, year: int, month: int) -> str:
        """获取指定月份的最后一天"""
        from calendar import monthrange
        last_day = monthrange(year, month)[1]
        return f"{year}-{month:02d}-{last_day:02d}"

    def _get_last_year_same_day(self, time_range: Dict[str, str]) -> str:
        """
        计算去年同日的日期

        用于查询去年同期累积数据（截至去年同日）。

        Args:
            time_range: 时间范围字典，包含 year、month 等字段

        Returns:
            去年同日的日期字符串（格式：YYYY-MM-DD）

        Examples:
            今天是2026-05-13 → 返回 "2025-05-12"
            今天是2026-03-01 → 返回 "2025-02-28"（上月最后一天）
        """
        current_date = datetime.now()

        if current_date.day == 1:
            # 如果今天是1号，则昨天是上个月最后一天
            yesterday = current_date.replace(day=1) - timedelta(days=1)
            last_year_date = datetime(
                int(time_range["last_year"]),
                yesterday.month,
                yesterday.day
            )
        else:
            # 正常情况：去年同月同日（昨天对应去年的日期）
            last_year_date = datetime(
                int(time_range["last_year"]),
                int(time_range["month"]),
                current_date.day - 1  # 昨天对应去年的日期
            )

        # 处理闰年2月29日的情况（如果去年不是闰年，则取2月28日）
        if last_year_date.month == 2 and last_year_date.day == 29:
            if not self._is_leap_year(last_year_date.year):
                last_year_date = last_year_date.replace(day=28)

        return last_year_date.strftime("%Y-%m-%d")

    def _resave_with_libreoffice(self, file_path: Path) -> bool:
        """
        使用LibreOffice重新保存Excel文件以正确保留图表渲染

        openpyxl只能保留图表元数据，但无法正确保存图表渲染信息。
        使用LibreOffice重新保存可以完整保留所有图表和格式。

        Args:
            file_path: Excel文件路径

        Returns:
            bool: 是否成功
        """
        try:
            # 检查LibreOffice是否可用
            soffice_result = subprocess.run(
                ["which", "soffice"],
                capture_output=True,
                text=True
            )

            if soffice_result.returncode != 0:
                logger.warning("libreoffice_not_found", file=str(file_path))
                return False

            # 创建临时目录用于LibreOffice输出
            import tempfile
            with tempfile.TemporaryDirectory() as temp_dir:
                temp_path = Path(temp_dir)

                # 使用LibreOffice转换为xlsx（会重新保存文件）
                env = {
                    "SAL_USE_VCLPLUGIN": "svp",
                    **dict(subprocess.os.environ)
                }

                result = subprocess.run(
                    [
                        "soffice",
                        "--headless",
                        "--convert-to", "xlsx",
                        "--outdir", str(temp_path),
                        str(file_path)
                    ],
                    env=env,
                    capture_output=True,
                    text=True,
                    timeout=60
                )

                if result.returncode == 0:
                    # 查找生成的文件
                    converted_files = list(temp_path.glob("*.xlsx"))
                    if converted_files:
                        # 用LibreOffice重新保存的文件替换原文件
                        shutil.move(str(converted_files[0]), str(file_path))
                        logger.info("libreoffice_resave_success", file=str(file_path))
                        return True
                    else:
                        logger.warning("libreoffice_resave_no_output", file=str(file_path))
                        return False
                else:
                    logger.warning(
                        "libreoffice_resave_failed",
                        file=str(file_path),
                        stderr=result.stderr
                    )
                    return False

        except subprocess.TimeoutExpired:
            logger.warning("libreoffice_resave_timeout", file=str(file_path))
            return False
        except Exception as e:
            logger.warning("libreoffice_resave_error", file=str(file_path), error=str(e))
            return False

    async def _fill_pollutant_sheets(self, wb, time_range: Dict[str, str]):
        """填充10个污染物sheet"""
        for sheet_name, config in SHEET_CONFIG.items():
            if sheet_name not in wb.sheetnames:
                logger.warning("sheet_not_found", sheet=sheet_name)
                continue

            try:
                await self._fill_single_sheet(wb, sheet_name, config, time_range)
                logger.info("sheet_filled", sheet=sheet_name)
            except Exception as e:
                logger.error("sheet_fill_failed", sheet=sheet_name, error=str(e))

    async def _fill_single_sheet(
        self,
        wb,
        sheet_name: str,
        config: Dict[str, Any],
        time_range: Dict[str, str]
    ):
        """填充单个sheet"""
        ws = wb[sheet_name]
        scope = config["scope"]
        pollutant = config["pollutant"]
        start_row, end_row = config["data_rows"]

        # 查询今年数据
        area_names, current_data = await self._query_with_date_range(
            scope=scope,
            pollutant=pollutant,
            start_date=time_range["start_date"],
            end_date=time_range["end_date"]
        )

        # 查询去年数据（去年同期累积：去年同月1号 → 去年同日）
        last_year_start = f"{time_range['last_year']}-{time_range['month']}-01"
        last_year_end = self._get_last_year_same_day(time_range)
        _, last_year_data = await self._query_with_date_range(
            scope=scope,
            pollutant=pollutant,
            start_date=last_year_start,
            end_date=last_year_end
        )

        # 确保数据长度匹配
        data_len = min(len(area_names), len(current_data), len(last_year_data))
        area_names = area_names[:data_len]
        current_data = current_data[:data_len]
        last_year_data = last_year_data[:data_len]

        # 替换广东省数据（全国sheet需要用审核后的全省数据替换）
        if scope == "national" and "广东" in area_names:
            try:
                logger.info("guangdong_data_replace_start", pollutant=pollutant)

                # 获取广东省的审核后数据
                guangdong_data = await self._get_guangdong_province_data(
                    pollutant=pollutant,
                    current_start=time_range["start_date"],
                    current_end=time_range["end_date"],
                    last_year_start=last_year_start,
                    last_year_end=last_year_end
                )

                if guangdong_data:
                    # 找到广东在列表中的索引
                    guangdong_index = area_names.index("广东")

                    # 记录原始数据
                    original_current = current_data[guangdong_index]
                    original_last_year = last_year_data[guangdong_index]

                    # 替换广东数据
                    current_data[guangdong_index] = guangdong_data["current"]
                    last_year_data[guangdong_index] = guangdong_data["last_year"]

                    logger.info(
                        "guangdong_data_replaced",
                        pollutant=pollutant,
                        original_current=original_current,
                        new_current=guangdong_data["current"],
                        original_last_year=original_last_year,
                        new_last_year=guangdong_data["last_year"]
                    )
                else:
                    logger.warning("guangdong_data_is_none", pollutant=pollutant)

            except Exception as e:
                logger.error("guangdong_data_replace_failed", pollutant=pollutant, error=str(e), exc_info=True)

        # 主数据区按B列（今年数据）升序排序
        paired_data = list(zip(area_names, current_data, last_year_data))
        paired_data.sort(key=lambda x: x[1])  # 按今年数据升序
        area_names = [item[0] for item in paired_data]
        current_data = [item[1] for item in paired_data]
        last_year_data = [item[2] for item in paired_data]

        # 填充主数据区
        name_col = config.get("name_col")
        current_col = config.get("current_col")
        last_year_col = config.get("last_year_col")

        for i in range(data_len):
            row = start_row + i
            if name_col:
                ws[f"{name_col}{row}"] = area_names[i]
            if current_col:
                ws[f"{current_col}{row}"] = round(current_data[i], 2)
            if last_year_col:
                ws[f"{last_year_col}{row}"] = round(last_year_data[i], 2)

        # 构建名称到数据的映射（用于排序副本的额外列填充）
        name_to_current = dict(zip(area_names, current_data))
        name_to_last_year = dict(zip(area_names, last_year_data))

        # 填充排序副本
        for copy_config in config.get("sort_copies", []):
            source_name_col = copy_config["source_name_col"]
            source_value_col = copy_config["source_value_col"]
            target_name_col = copy_config["target_name_col"]
            target_value_col = copy_config.get("target_value_col")
            sort_ascending = copy_config.get("sort_ascending", True)
            calculate_diff = copy_config.get("calculate_diff", False)

            # 读取源数据
            names = []
            values = []
            for i in range(data_len):
                row = start_row + i
                n = ws[f"{source_name_col}{row}"].value
                v = ws[f"{source_value_col}{row}"].value
                if n is not None and v is not None:
                    names.append(n)
                    try:
                        if calculate_diff:
                            # 需要计算同比差值
                            current_val = name_to_current.get(n, 0)
                            last_year_val = name_to_last_year.get(n, 0)
                            diff_val = current_val - last_year_val
                            values.append(diff_val)
                        else:
                            # 直接使用源列的值
                            values.append(float(v))
                    except (ValueError, TypeError):
                        values.append(0.0)

            # 排序
            paired = list(zip(names, values))
            paired.sort(key=lambda x: x[1], reverse=not sort_ascending)

            # 填充目标区域
            for i, (name, value) in enumerate(paired):
                row = start_row + i
                ws[f"{target_name_col}{row}"] = name
                if target_value_col:
                    ws[f"{target_value_col}{row}"] = round(value, 2)
                # 填充额外列
                for extra in copy_config.get("extra_targets", []):
                    extra_col = extra["col"]
                    data_source = extra["data_source"]
                    if data_source == "diff_pct":
                        if name in name_to_current and name in name_to_last_year:
                            diff = name_to_current[name] - name_to_last_year[name]
                            ws[f"{extra_col}{row}"] = round(diff, 2)
                    else:
                        source_map = name_to_current if data_source == "current" else name_to_last_year
                        if name in source_map:
                            ws[f"{extra_col}{row}"] = round(source_map[name], 2)

        # 更新表头
        for cell_ref, template in config.get("headers", {}).items():
            header_value = template.format(
                year=time_range["year"],
                month=int(time_range["month"]),
                last_year=time_range["last_year"],
            )
            ws[cell_ref] = header_value

    async def _fill_extra_sheets(self, wb, time_range: Dict[str, str]):
        """填充额外sheet（X月全国排名、全省同比、历年当月累积浓度）"""
        month = int(time_range["month"])

        # 查找并填充全国排名sheet（处理可能的名称变体：末尾空格、月份前缀等）
        ranking_sheet = None
        for sheet_name in wb.sheetnames:
            if "全国排名" in sheet_name:
                ranking_sheet = wb[sheet_name]
                # 重命名为标准格式
                new_name = f"{month}月全国排名"
                if sheet_name != new_name:
                    ranking_sheet.title = new_name
                break

        if ranking_sheet:
            try:
                await self._fill_national_ranking_sheet(wb, time_range, ranking_sheet.title)
                logger.info("sheet_filled", sheet=ranking_sheet.title)
            except Exception as e:
                logger.error("sheet_fill_failed", sheet=ranking_sheet.title, error=str(e))

        # 填充全省同比
        if "全省同比" in wb.sheetnames and "全省同比" in EXTRA_SHEET_CONFIG:
            try:
                await self._fill_provincial_summary_sheet(wb, time_range)
                logger.info("sheet_filled", sheet="全省同比")
            except Exception as e:
                logger.error("sheet_fill_failed", sheet="全省同比", error=str(e))

        # 查找并填充历年对比sheet（处理可能的名称变体）
        historical_sheet = None
        for sheet_name in wb.sheetnames:
            if "历年" in sheet_name and "浓度" in sheet_name:
                historical_sheet = wb[sheet_name]
                # 重命名为标准格式
                new_name = f"历年1-{month}月浓度"
                if sheet_name != new_name:
                    historical_sheet.title = new_name
                break

        if historical_sheet:
            try:
                await self._fill_historical_comparison_sheet(wb, time_range, historical_sheet.title)
                logger.info("sheet_filled", sheet=historical_sheet.title)
            except Exception as e:
                logger.error("sheet_fill_failed", sheet=historical_sheet.title, error=str(e))

    async def _fill_national_ranking_sheet(self, wb, time_range: Dict[str, str], sheet_name: str):
        """
        填充X月全国排名sheet

        功能：
        1. 查询今年和去年的全国数据
        2. 分别排序获得排名
        3. 填充三列：省份、指标值、排名
        4. 对广东添加排名变化标记（↑X/↓X/-）
        """
        ws = wb[sheet_name]
        config = EXTRA_SHEET_CONFIG["X月全国排名"]
        start_row, end_row = config["data_rows"]

        # 计算去年同月的时间范围（去年同期累积：去年同月1号 → 去年同日）
        last_year_start = f"{time_range['last_year']}-{time_range['month']}-01"
        last_year_end = self._get_last_year_same_day(time_range)

        for col_config in config["columns"]:
            pollutant = col_config["pollutant"]
            name_col = col_config["name_col"]
            value_col = col_config["value_col"]
            rank_col = col_config["rank_col"]
            sort_ascending = col_config["sort_ascending"]

            # 查询今年数据
            current_names, current_data = await self._query_with_date_range(
                scope="national",
                pollutant=pollutant,
                start_date=time_range["start_date"],
                end_date=time_range["end_date"]
            )

            # 查询去年数据
            last_names, last_data = await self._query_with_date_range(
                scope="national",
                pollutant=pollutant,
                start_date=last_year_start,
                end_date=last_year_end
            )

            # 今年排序获得排名
            current_paired = list(zip(current_names, current_data))
            current_paired.sort(key=lambda x: x[1], reverse=not sort_ascending)
            current_ranking = {name: i + 1 for i, (name, _) in enumerate(current_paired)}

            # 去年排序获得排名
            last_paired = list(zip(last_names, last_data))
            last_paired.sort(key=lambda x: x[1], reverse=not sort_ascending)
            last_ranking = {name: i + 1 for i, (name, _) in enumerate(last_paired)}

            # 填充数据（省份、指标、排名）
            data_len = min(len(current_paired), end_row - start_row + 1)
            for i in range(data_len):
                row = start_row + i
                province_name = current_paired[i][0]
                province_value = current_paired[i][1]
                current_rank = i + 1

                # 填充省份
                ws[f"{name_col}{row}"] = province_name

                # 填充指标值
                # 注意：AQI数据API返回的已经是百分比值（如69.4、100），不需要再乘以100
                display_value = round(province_value, 2)
                ws[f"{value_col}{row}"] = display_value

                # 填充排名（如果是广东，添加变化标记）
                rank_display = str(current_rank)

                if province_name == "广东" and province_name in last_ranking:
                    last_rank = last_ranking[province_name]
                    rank_change = last_rank - current_rank  # 正数=上升，负数=下降

                    if rank_change > 0:
                        rank_display = f"{current_rank}（↑{rank_change}）"
                    elif rank_change < 0:
                        rank_display = f"{current_rank}（↓{abs(rank_change)}）"
                    else:
                        rank_display = f"{current_rank}（-）"

                ws[f"{rank_col}{row}"] = rank_display

        logger.info(
            "national_ranking_filled",
            sheet=sheet_name,
            pollutants_count=len(config["columns"]),
            data_range=f"{start_row}-{end_row}"
        )

    async def _fill_provincial_summary_sheet(self, wb, time_range: Dict[str, str]):
        """
        填充全省同比sheet

        功能：
        1. 查询今年和去年同期的全省数据（如今年1-5月 vs 去年1-5月）
        2. 使用QueryNewStandardReportTool（与历年对比一致）
        3. 直接使用API返回的全省均值，不计算

        数据源：QueryNewStandardReportTool（审核数据）
        """
        from app.tools.query.query_new_standard_report.tool import QueryNewStandardReportTool

        ws = wb["全省同比"]
        config = EXTRA_SHEET_CONFIG["全省同比"]
        start_row, end_row = config["data_rows"]
        mapping = config["mapping"]

        # 广东省21个地级市
        guangdong_cities = [
            "广州", "深圳", "珠海", "佛山", "惠州", "东莞", "中山", "江门", "肇庆",
            "汕头", "汕尾", "潮州", "揭阳",
            "湛江", "茂名", "阳江",
            "韶关", "河源", "梅州", "清远", "云浮"
        ]

        query_tool = QueryNewStandardReportTool()

        # 污染物字段映射
        field_map = {
            "PM2.5": "PM2_5",
            "PM10": "PM10",
            "NO2": "NO2",
            "O3": "O3_8h_P90",
            "AQI": "compliance_rate"
        }

        # 查询全省各污染物数据
        for row, pollutant in mapping.items():
            if row > end_row:
                continue

            field = field_map.get(pollutant)
            if not field:
                logger.warning("unknown_pollutant", pollutant=pollutant, row=row)
                continue

            try:
                # 今年数据：本月1号 → 昨天
                current_start = time_range["start_date"]
                current_end = time_range["end_date"]

                # 去年数据：去年同期时段（去年同月1号 → 去年同日）
                # 例如：今年5月1-12日 vs 去年5月1-12日
                last_year_start = f"{time_range['last_year']}-{time_range['month']}-01"

                # 计算去年同日（处理闰年等情况）
                current_date = datetime.now()
                if current_date.day == 1:
                    # 如果今天是1号，则昨天是上个月最后一天
                    yesterday = current_date.replace(day=1) - timedelta(days=1)
                    last_year_date = datetime(
                        int(time_range["last_year"]),
                        yesterday.month,
                        yesterday.day
                    )
                else:
                    # 正常情况：去年同月同日
                    last_year_date = datetime(
                        int(time_range["last_year"]),
                        int(time_range["month"]),
                        current_date.day - 1  # 昨天对应去年的日期
                    )

                # 处理闰年2月29日的情况（如果去年不是闰年，则取2月28日）
                if last_year_date.month == 2 and last_year_date.day == 29:
                    if not self._is_leap_year(last_year_date.year):
                        last_year_date = last_year_date.replace(day=28)

                last_year_end = last_year_date.strftime("%Y-%m-%d")

                logger.info(
                    "provincial_comparison_query",
                    pollutant=pollutant,
                    current_period=f"{current_start} → {current_end}",
                    last_year_period=f"{last_year_start} → {last_year_end}"
                )

                # 查询今年数据
                current_result = await query_tool.execute(
                    context=None,
                    cities=guangdong_cities,
                    start_date=current_start,
                    end_date=current_end,
                    enable_sand_deduction=False
                )

                # 查询去年数据
                last_year_result = await query_tool.execute(
                    context=None,
                    cities=guangdong_cities,
                    start_date=last_year_start,
                    end_date=last_year_end,
                    enable_sand_deduction=False
                )

                # 提取全省数据
                current_province_data = None
                last_year_province_data = None

                if current_result and current_result.get("success"):
                    current_stats = current_result.get("result", {})
                    if isinstance(current_stats, dict):
                        current_province_data = current_stats.get("regional_stats", {}).get("全省", {})

                if last_year_result and last_year_result.get("success"):
                    last_year_stats = last_year_result.get("result", {})
                    if isinstance(last_year_stats, dict):
                        last_year_province_data = last_year_stats.get("regional_stats", {}).get("全省", {})

                # 提取污染物数值
                current_value = current_province_data.get(field, 0) if current_province_data else 0
                last_year_value = last_year_province_data.get(field, 0) if last_year_province_data else 0

                if current_value is None:
                    current_value = 0
                if last_year_value is None:
                    last_year_value = 0

                # 填充单元格（直接使用API返回的全省均值，不计算）
                ws[f"{config['current_col']}{row}"] = round(current_value, 2)
                ws[f"{config['last_year_col']}{row}"] = round(last_year_value, 2)

                logger.info(
                    "provincial_comparison_filled",
                    pollutant=pollutant,
                    row=row,
                    current_value=current_value,
                    last_year_value=last_year_value
                )

            except Exception as e:
                logger.error("provincial_comparison_failed", pollutant=pollutant, row=row, error=str(e), exc_info=True)
                # 填充0值
                ws[f"{config['current_col']}{row}"] = 0
                ws[f"{config['last_year_col']}{row}"] = 0

        # 更新表头
        for cell_ref, template in config.get("headers", {}).items():
            header_value = template.format(
                year=time_range["year"],
                month=int(time_range["month"]),
                last_year=time_range["last_year"],
            )
            ws[cell_ref] = header_value

    async def _query_with_date_range(
        self,
        scope: str,
        pollutant: str,
        start_date: str,
        end_date: str
    ) -> Tuple[List[str], List[float]]:
        """
        使用自定义日期范围查询数据

        数据源：
        - scope="national": 使用 NationalAirQualityQueryTool 查询全国各省数据
        - scope="provincial": 使用 QueryNewStandardReportTool 查询广东21个地级市数据

        Args:
            scope: "national" 或 "provincial"
            pollutant: 污染物名称
            start_date: 开始日期 (YYYY-MM-DD)
            end_date: 结束日期 (YYYY-MM-DD)

        Returns:
            Tuple[List[str], List[float]]: (地区名称列表, 污染物数值列表)
        """
        area_names = []
        result = []

        if scope == "national":
            # 全国数据：使用 NationalAirQualityQueryTool
            from app.tools.query.query_national_air_quality.tool import (
                NationalAirQualityQueryTool
            )

            query_tool = NationalAirQualityQueryTool()

            field_map = {
                "PM2.5": "PM2_5",
                "PM10": "PM10",
                "NO2": "NO2",
                "O3": "O3_8h",
                "AQI": "AQIStandardRate"
            }
            field = field_map.get(pollutant)
            if not field:
                raise ValueError(f"Unknown pollutant: {pollutant}")

            data = query_tool.query_province_data(
                start_date=start_date,
                end_date=end_date,
                ns_type="NS"
            )

            for item in data:
                area_name = item.get("AreaName", "")
                area_names.append(area_name)

                value = item.get(field, 0)
                if value is None:
                    value = 0
                try:
                    result.append(float(value))
                except (ValueError, TypeError):
                    logger.warning("invalid_value", pollutant=pollutant, field=field, value=value)
                    result.append(0.0)

        elif scope == "provincial":
            # 全省数据：使用 QueryNewStandardReportTool（审核数据）
            from app.tools.query.query_new_standard_report.tool import QueryNewStandardReportTool

            # 广东省21个地级市
            guangdong_cities = [
                "广州", "深圳", "珠海", "佛山", "惠州", "东莞", "中山", "江门", "肇庆",
                "汕头", "汕尾", "潮州", "揭阳",
                "湛江", "茂名", "阳江",
                "韶关", "河源", "梅州", "清远", "云浮"
            ]

            query_tool = QueryNewStandardReportTool()

            # 污染物字段映射（与 QueryNewStandardReportTool 返回字段一致）
            field_map = {
                "PM2.5": "PM2_5",
                "PM10": "PM10",
                "NO2": "NO2",
                "O3": "O3_8h_P90",
                "AQI": "compliance_rate"
            }
            field = field_map.get(pollutant)
            if not field:
                raise ValueError(f"Unknown pollutant: {pollutant}")

            # 查询广东21个地级市数据
            query_result = await query_tool.execute(
                context=None,
                cities=guangdong_cities,
                start_date=start_date,
                end_date=end_date,
                enable_sand_deduction=False
            )

            # 提取各城市数据
            if query_result and "result" in query_result:
                stats = query_result["result"]
                if isinstance(stats, dict) and "city_stats" in stats:
                    city_stats = stats["city_stats"]

                    # 按照原始城市列表顺序提取数据
                    for city in guangdong_cities:
                        if city in city_stats:
                            city_data = city_stats[city]
                            area_names.append(city)

                            value = city_data.get(field, 0)
                            if value is None:
                                value = 0
                            try:
                                result.append(float(value))
                            except (ValueError, TypeError):
                                logger.warning("invalid_city_value", pollutant=pollutant, city=city, field=field, value=value)
                                result.append(0.0)
                        else:
                            # 城市数据缺失
                            logger.warning("city_data_missing", city=city)
                            area_names.append(city)
                            result.append(0.0)
                else:
                    logger.error("provincial_query_no_city_stats", result_type=type(stats).__name__)
                    raise ValueError("Provincial query result missing city_stats")
            else:
                logger.error("provincial_query_failed", has_result=bool(query_result))
                raise ValueError("Provincial query failed or returned empty result")
        else:
            raise ValueError(f"Unknown scope: {scope}")

        logger.info(
            "query_with_date_range_success",
            scope=scope,
            pollutant=pollutant,
            start_date=start_date,
            end_date=end_date,
            area_count=len(area_names),
        )

        return area_names, result

    async def _get_guangdong_province_data(
        self,
        pollutant: str,
        current_start: str,
        current_end: str,
        last_year_start: str,
        last_year_end: str
    ) -> Dict[str, float]:
        """
        获取广东省的全省数据（用于替换全国sheet中的广东数据）

        使用 NationalAirQualityQueryTool 查询广东省21个地级市数据，
        计算全省均值，确保与全国其他省份使用相同的字段和统计方法。

        Args:
            pollutant: 污染物名称（PM2.5、PM10、NO2、O3、AQI）
            current_start: 今年开始日期
            current_end: 今年结束日期
            last_year_start: 去年开始日期
            last_year_end: 去年结束日期

        Returns:
            {"current": 今年数值, "last_year": 去年数值}
        """
        from app.tools.query.query_national_air_quality.tool import (
            NationalAirQualityQueryTool
        )

        query_tool = NationalAirQualityQueryTool()

        # 污染物字段映射（与全国其他省份保持一致）
        field_map = {
            "PM2.5": "PM2_5",
            "PM10": "PM10",
            "NO2": "NO2",
            "O3": "O3_8h",  # 使用O3_8h均值，与全国其他省份一致
            "AQI": "AQIStandardRate"
        }

        field = field_map.get(pollutant)
        if not field:
            logger.warning("unknown_pollutant_for_guangdong", pollutant=pollutant)
            return None

        try:
            # 查询今年广东省21个地级市数据
            logger.info("query_guangdong_current_start", pollutant=pollutant, start=current_start, end=current_end)
            current_data = query_tool.query_city_data(
                start_date=current_start,
                end_date=current_end,
                province_code="44",
                ns_type="NS"
            )

            # 查询去年广东省21个地级市数据
            logger.info("query_guangdong_last_year_start", pollutant=pollutant, start=last_year_start, end=last_year_end)
            last_year_data = query_tool.query_city_data(
                start_date=last_year_start,
                end_date=last_year_end,
                province_code="44",
                ns_type="NS"
            )

            # 计算全省均值（21个地级市的平均值）
            def calculate_province_mean(data_list, field):
                """计算全省均值"""
                values = []
                for item in data_list:
                    value = item.get(field, 0)
                    if value is not None:
                        try:
                            values.append(float(value))
                        except (ValueError, TypeError):
                            logger.warning("invalid_city_value", city=item.get("AreaName"), field=field, value=value)

                if not values:
                    return 0.0
                return sum(values) / len(values)

            current_value = calculate_province_mean(current_data, field)
            last_year_value = calculate_province_mean(last_year_data, field)

            logger.info(
                "pollutant_value_calculated",
                pollutant=pollutant,
                field=field,
                current_value=current_value,
                last_year_value=last_year_value,
                current_city_count=len(current_data),
                last_year_city_count=len(last_year_data)
            )

            return {
                "current": float(current_value),
                "last_year": float(last_year_value)
            }

        except Exception as e:
            logger.error("guangdong_data_query_failed", pollutant=pollutant, error=str(e), exc_info=True)
            return None

    async def _fill_historical_comparison_sheet(self, wb, time_range: Dict[str, str], sheet_name: str):
        """
        填充历年当月累积浓度sheet

        功能：
        1. 查询2014-当前年份每年1-{当前月}的全省数据
        2. 填充7个指标：AQI达标率、PM2.5、PM10、NO2、O3、SO2、CO
        3. 数据来源：广东省审核数据接口（query_new_standard_report）

        示例：
        - 当前为5月13日，则查询每年1-5月的累积数据
        - 历史年份查询完整1-5月，当前年份查询1-5月（截至昨日）

        Args:
            wb: 工作簿对象
            time_range: 时间范围字典
            sheet_name: sheet名称（动态生成，如"历年1-5月浓度"）
        """
        ws = wb[sheet_name]
        config = EXTRA_SHEET_CONFIG["历年1-2月浓度"]  # 配置key保持不变
        start_row, end_row = config["data_rows"]
        year_col = config["year_col"]
        start_year = config["start_year"]

        # 当前年份和月份
        current_year = int(time_range["year"])
        current_month = int(time_range["month"])

        # 广东省21个地级市
        guangdong_cities = [
            "广州", "深圳", "珠海", "佛山", "惠州", "东莞", "中山", "江门", "肇庆",
            "汕头", "汕尾", "潮州", "揭阳",
            "湛江", "茂名", "阳江",
            "韶关", "河源", "梅州", "清远", "云浮"
        ]

        from app.tools.query.query_new_standard_report.tool import QueryNewStandardReportTool
        query_tool = QueryNewStandardReportTool()

        # 遍历每一年（2014-当前年份）
        for year_offset in range(end_row - start_row + 1):
            year = start_year + year_offset
            row = start_row + year_offset

            # 填充年份
            ws[f"{year_col}{row}"] = year

            # 计算该年份1-{当前月}的起止日期
            year_start = f"{year}-01-01"

            # 历史年份：查询完整月份；当前年份：查询截至昨日
            if year < current_year:
                # 历史年份：查询完整的1-{当前月}数据
                year_end = self._get_last_day_of_month(year, current_month)
                period_desc = f"{year}年1-{current_month}月完整"
            elif year == current_year:
                # 当前年份：查询1-{当前月}（截至昨日）
                year_end = time_range["end_date"]
                period_desc = f"{year}年1-{current_month}月（截至昨日）"
            else:
                # 未来年份：跳过
                logger.info("future_year_skip", year=year)
                continue

            try:
                # 查询该年1-{当前月}全省数据
                logger.info("query_historical_year_start", year=year, start=year_start, end=year_end, period=period_desc)

                result = await query_tool.execute(
                    context=None,
                    cities=guangdong_cities,
                    start_date=year_start,
                    end_date=year_end,
                    enable_sand_deduction=False
                )

                # 提取全省数据
                if result and "result" in result:
                    stats = result["result"]
                    if isinstance(stats, dict) and "regional_stats" in stats:
                        province_data = stats["regional_stats"].get("全省", {})

                        # 填充各列数据
                        for col_config in config["columns"]:
                            col = col_config["col"]
                            field = col_config["field"]
                            value = province_data.get(field, 0)

                            if value is None:
                                value = 0

                            # 填充单元格
                            ws[f"{col}{row}"] = round(value, 2)

                        logger.info("historical_year_filled", year=year)
                    else:
                        logger.warning("historical_year_no_regional_stats", year=year)
                        # 填充0值
                        for col_config in config["columns"]:
                            col = col_config["col"]
                            ws[f"{col}{row}"] = 0
                else:
                    logger.warning("historical_year_no_result", year=year)
                    # 填充0值
                    for col_config in config["columns"]:
                        col = col_config["col"]
                        ws[f"{col}{row}"] = 0

            except Exception as e:
                logger.error("historical_year_query_failed", year=year, error=str(e), exc_info=True)
                # 填充0值
                for col_config in config["columns"]:
                    col = col_config["col"]
                    ws[f"{col}{row}"] = 0

        logger.info(
            "historical_comparison_filled",
            current_month=current_month,
            period=f"1-{current_month}月",
            start_year=start_year,
            end_year=current_year,
            years_count=current_year - start_year + 1
        )

    def _is_leap_year(self, year: int) -> bool:
        """
        判断是否为闰年

        Args:
            year: 年份

        Returns:
            True表示闰年，False表示平年
        """
        if year % 4 != 0:
            return False
        elif year % 100 != 0:
            return True
        else:
            return year % 400 == 0


# 导出
__all__ = ["ConsultationFileFetcher"]
