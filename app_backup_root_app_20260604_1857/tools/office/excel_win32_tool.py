"""
Excel Win32 COM 工具

提供 Excel 工作簿的自动化处理能力：
- 读取/写入单元格
- 操作工作表
- 公式计算
- 图表操作
"""

import os
from typing import Dict, Any, List, Optional, Any
import structlog

from .base_win32 import Win32Base

logger = structlog.get_logger()


class ExcelWin32Tool(Win32Base):
    """
    Excel 自动化工具

    支持的操作：
    - 读取/写入单元格
    - 读取/写入工作表
    - 公式计算
    - 创建图表
    - 数据透视表
    """

    def __init__(self, visible: bool = False):
        """
        初始化 Excel 工具

        Args:
            visible: 是否显示 Excel 窗口
        """
        super().__init__(
            app_name=self.APP_EXCEL,
            visible=visible,
            display_alerts=False
        )

    def open_workbook(
        self,
        file_path: str,
        read_only: bool = True,
        update_links: bool = False
    ):
        """
        打开 Excel 工作簿

        Args:
            file_path: 工作簿路径
            read_only: 是否以只读方式打开
            update_links: 是否更新外部链接

        Returns:
            Workbook 对象
        """
        try:
            self.ensure_initialized()

            abs_path = self.get_absolute_path(file_path)

            if not self.check_file_exists(abs_path):
                return None

            # 打开工作簿
            workbook = self.app.Workbooks.Open(
                FileName=abs_path,
                ReadOnly=read_only,
                UpdateLinks=0 if not update_links else 3
            )

            logger.info(
                "excel_workbook_opened",
                path=file_path,
                read_only=read_only
            )

            return workbook

        except Exception as e:
            logger.error(
                "excel_open_failed",
                path=file_path,
                error=str(e)
            )
            return None

    def save_workbook(self, workbook, file_path: str):
        """
        保存 Excel 工作簿

        Args:
            workbook: Workbook 对象
            file_path: 保存路径
        """
        try:
            abs_path = self.get_absolute_path(file_path)

            # 确保目录存在
            os.makedirs(os.path.dirname(abs_path), exist_ok=True)

            # 保存工作簿
            workbook.SaveAs(FileName=abs_path)

            logger.info(
                "excel_workbook_saved",
                path=file_path
            )

            return True

        except Exception as e:
            logger.error(
                "excel_save_failed",
                path=file_path,
                error=str(e)
            )
            return False

    def close_workbook(self, workbook, save_changes: bool = False):
        """
        关闭 Excel 工作簿

        Args:
            workbook: Workbook 对象
            save_changes: 是否保存更改
        """
        try:
            workbook.Close(SaveChanges=save_changes)
            logger.debug("excel_workbook_closed")
        except Exception as e:
            logger.warning("excel_close_warning", error=str(e))

    def read_cell(
        self,
        file_path: str,
        sheet_name: str,
        cell_address: str
    ) -> Dict[str, Any]:
        """
        读取单元格数据

        Args:
            file_path: 工作簿路径
            sheet_name: 工作表名称
            cell_address: 单元格地址（如 "A1"）

        Returns:
            {
                "status": "success" | "failed",
                "value": "单元格值",
                "formula": "公式（如果有）",
                "cell_address": "单元格地址"
            }
        """
        try:
            workbook = self.open_workbook(file_path, read_only=True)

            if not workbook:
                return {
                    "status": "failed",
                    "error": "无法打开工作簿"
                }

            # 获取工作表
            sheet = workbook.Worksheets(sheet_name)

            # 获取单元格
            cell = sheet.Range(cell_address)

            # 读取值和公式
            value = cell.Value
            formula = cell.Formula if cell.Formula and cell.Formula != value else None

            # 关闭工作簿
            self.close_workbook(workbook)

            return {
                "status": "success",
                "value": value,
                "formula": formula,
                "cell_address": cell_address,
                "sheet_name": sheet_name,
                "summary": "读取成功"
            }

        except Exception as e:
            logger.error(
                "excel_read_cell_failed",
                path=file_path,
                sheet=sheet_name,
                cell=cell_address,
                error=str(e)
            )
            return {
                "status": "failed",
                "error": str(e),
                "summary": "操作失败"
            }

    def write_cell(
        self,
        file_path: str,
        sheet_name: str,
        cell_address: str,
        value: Any,
        save_as: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        写入单元格数据

        Args:
            file_path: 工作簿路径
            sheet_name: 工作表名称
            cell_address: 单元格地址（如 "A1"）
            value: 要写入的值
            save_as: 保存为新文件（可选）

        Returns:
            {
                "status": "success" | "failed",
                "cell_address": "单元格地址",
                "value": "写入的值",
                "output_file": "输出文件路径"
            }
        """
        try:
            workbook = self.open_workbook(file_path, read_only=False)

            if not workbook:
                return {
                    "status": "failed",
                    "error": "无法打开工作簿"
                }

            # 获取工作表
            sheet = workbook.Worksheets(sheet_name)

            # 写入值
            sheet.Range(cell_address).Value = value

            # 保存工作簿
            output_file = save_as or file_path
            self.save_workbook(workbook, output_file)

            # 关闭工作簿
            self.close_workbook(workbook, save_changes=True)

            return {
                "status": "success",
                "cell_address": cell_address,
                "value": value,
                "sheet_name": sheet_name,
                "output_file": output_file,
                "summary": "写入成功"
            }

        except Exception as e:
            logger.error(
                "excel_write_cell_failed",
                path=file_path,
                sheet=sheet_name,
                cell=cell_address,
                error=str(e)
            )
            return {
                "status": "failed",
                "error": str(e),
                "summary": "操作失败"
            }

    def read_range(
        self,
        file_path: str,
        sheet_name: str,
        range_address: str
    ) -> Dict[str, Any]:
        """
        读取单元格范围数据

        Args:
            file_path: 工作簿路径
            sheet_name: 工作表名称
            range_address: 范围地址（如 "A1:C10"）

        Returns:
            {
                "status": "success" | "failed",
                "data": [[值1, 值2, ...], ...],
                "rows": 行数,
                "cols": 列数
            }
        """
        try:
            workbook = self.open_workbook(file_path, read_only=True)

            if not workbook:
                return {
                    "status": "failed",
                    "error": "无法打开工作簿"
                }

            # 获取工作表
            sheet = workbook.Worksheets(sheet_name)

            # 获取范围
            range_obj = sheet.Range(range_address)

            # 读取数据
            data = range_obj.Value

            # 转换为二维列表
            if data:
                rows = len(data)
                cols = len(data[0]) if isinstance(data[0], (list, tuple)) else 1

                if cols == 1:
                    # 单列
                    data_list = [[item] if not isinstance(item, (list, tuple)) else list(item) for item in data]
                else:
                    # 多列
                    data_list = [list(row) for row in data]
            else:
                data_list = []
                rows = 0
                cols = 0

            # 关闭工作簿
            self.close_workbook(workbook)

            return {
                "status": "success",
                "data": data_list,
                "rows": rows,
                "cols": cols,
                "summary": "读取成功"
            }

        except Exception as e:
            logger.error(
                "excel_read_range_failed",
                path=file_path,
                sheet=sheet_name,
                range=range_address,
                error=str(e)
            )
            return {
                "status": "failed",
                "error": str(e),
                "summary": "操作失败"
            }

    def write_range(
        self,
        file_path: str,
        sheet_name: str,
        range_address: str,
        data: List[List[Any]],
        save_as: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        写入单元格范围数据

        Args:
            file_path: 工作簿路径
            sheet_name: 工作表名称
            range_address: 范围地址（如 "A1:C10"）
            data: 二维数据
            save_as: 保存为新文件（可选）

        Returns:
            {
                "status": "success" | "failed",
                "cells_written": 写入的单元格数量,
                "output_file": "输出文件路径"
            }
        """
        try:
            workbook = self.open_workbook(file_path, read_only=False)

            if not workbook:
                return {
                    "status": "failed",
                    "error": "无法打开工作簿"
                }

            # 获取工作表
            sheet = workbook.Worksheets(sheet_name)

            # 写入数据
            range_obj = sheet.Range(range_address)
            range_obj.Value = data

            # 计算写入的单元格数量
            cells_written = len(data) * len(data[0]) if data else 0

            # 保存工作簿
            output_file = save_as or file_path
            self.save_workbook(workbook, output_file)

            # 关闭工作簿
            self.close_workbook(workbook, save_changes=True)

            return {
                "status": "success",
                "cells_written": cells_written,
                "output_file": output_file,
                "summary": "写入成功"
            }

        except Exception as e:
            logger.error(
                "excel_write_range_failed",
                path=file_path,
                sheet=sheet_name,
                range=range_address,
                error=str(e)
            )
            return {
                "status": "failed",
                "error": str(e),
                "summary": "操作失败"
            }

    def list_sheets(self, file_path: str) -> Dict[str, Any]:
        """
        列出工作簿中的所有工作表

        Args:
            file_path: 工作簿路径

        Returns:
            {
                "status": "success" | "failed",
                "sheets": ["工作表1", "工作表2", ...],
                "sheet_count": 工作表数量
            }
        """
        try:
            workbook = self.open_workbook(file_path, read_only=True)

            if not workbook:
                return {
                    "status": "failed",
                    "error": "无法打开工作簿"
                }

            # 获取所有工作表名称
            sheets = []
            for sheet in workbook.Worksheets:
                sheets.append(sheet.Name)

            # 关闭工作簿
            self.close_workbook(workbook)

            return {
                "status": "success",
                "sheets": sheets,
                "sheet_count": len(sheets),
                "summary": "读取成功"
            }

        except Exception as e:
            logger.error(
                "excel_list_sheets_failed",
                path=file_path,
                error=str(e)
            )
            return {
                "status": "failed",
                "error": str(e),
                "summary": "操作失败"
            }

    def get_workbook_stats(self, file_path: str) -> Dict[str, Any]:
        """
        获取工作簿统计信息

        Args:
            file_path: 工作簿路径

        Returns:
            {
                "status": "success" | "failed",
                "stats": {
                    "sheets": 工作表数量,
                    "calculation_mode": "计算模式"
                }
            }
        """
        try:
            workbook = self.open_workbook(file_path, read_only=True)

            if not workbook:
                return {
                    "status": "failed",
                    "error": "无法打开工作簿"
                }

            stats = {
                "sheets": workbook.Worksheets.Count,
                "calculation_mode": workbook.CalculationVersion
            }

            # 关闭工作簿
            self.close_workbook(workbook)

            return {
                "status": "success",
                "stats": stats,
                "summary": "读取成功"
            }

        except Exception as e:
            logger.error(
                "excel_stats_failed",
                path=file_path,
                error=str(e)
            )
            return {
                "status": "failed",
                "error": str(e),
                "summary": "操作失败"
            }

    def process_file(self, file_path: str, **kwargs) -> Dict[str, Any]:
        """
        统一的文件处理接口（集成到工具系统）

        Args:
            file_path: 文件路径
            **kwargs: 操作参数
                - operation: 操作类型 (read_cell/write_cell/read_range/write_range/list_sheets/stats)
                - 其他参数根据 operation 不同而不同

        Returns:
            操作结果
        """
        operation = kwargs.get("operation", "list_sheets")

        if operation == "read_cell":
            return self.read_cell(
                file_path,
                sheet_name=kwargs.get("sheet_name"),
                cell_address=kwargs.get("cell_address")
            )
        elif operation == "write_cell":
            return self.write_cell(
                file_path,
                sheet_name=kwargs.get("sheet_name"),
                cell_address=kwargs.get("cell_address"),
                value=kwargs.get("value"),
                save_as=kwargs.get("save_as")
            )
        elif operation == "read_range":
            return self.read_range(
                file_path,
                sheet_name=kwargs.get("sheet_name"),
                range_address=kwargs.get("range_address")
            )
        elif operation == "write_range":
            return self.write_range(
                file_path,
                sheet_name=kwargs.get("sheet_name"),
                range_address=kwargs.get("range_address"),
                data=kwargs.get("data"),
                save_as=kwargs.get("save_as")
            )
        elif operation == "list_sheets":
            return self.list_sheets(file_path)
        elif operation == "stats":
            return self.get_workbook_stats(file_path)
        else:
            return {
                "status": "failed",
                "error": f"未知操作: {operation}"
            }
