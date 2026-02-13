"""
Excel Win32 Tool - LLM Tool 包装器

将 ExcelWin32Tool 包装为符合 LLMTool 接口的工具
支持分页读取，LLM可以指定读取范围
"""

from typing import Dict, Any
from app.tools.base.tool_interface import LLMTool, ToolCategory
from app.tools.office.excel_win32_tool import ExcelWin32Tool
import structlog

logger = structlog.get_logger()


class ExcelWin32LLMTool(LLMTool):
    """
    Excel 自动化工具（LLM Tool 接口）

    支持：
    - 分页读取工作表数据
    - 读取/写入单元格
    - 读取/写入范围
    - 列出工作表
    - 获取工作簿统计

    分页读取设计：
    - sheet_name: 指定工作表
    - start_row: 起始行号（从0开始）
    - end_row: 结束行号（不包含）
    - max_rows: 最大读取行数（用于分页）
    """

    # 默认配置
    DEFAULT_MAX_ROWS = 100  # 默认每次读取100行

    def __init__(self):
        super().__init__(
            name="excel_processor",
            description="读取和编辑 Excel 工作簿（仅 Windows）。支持分页读取、读取/写入单元格、列出工作表、获取统计信息。",
            category=ToolCategory.QUERY,
            version="2.0.0",
            requires_context=False  # 不需要Context，直接读取文件
        )
        self._excel_tool = None

    def _get_tool(self):
        """获取 Excel 工具实例（延迟初始化）"""
        if self._excel_tool is None:
            self._excel_tool = ExcelWin32Tool(visible=False)
        return self._excel_tool

    async def execute(
        self,
        file_path: str,
        operation: str = "list_sheets",
        sheet_name: str = None,
        start_row: int = 0,
        end_row: int = None,
        max_rows: int = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        执行 Excel 操作

        Args:
            file_path: Excel 文件路径
            operation: 操作类型
                - list_sheets: 列出工作表
                - read_range: 读取范围（支持分页）
                - write_range: 写入范围
                - stats: 获取统计信息
            sheet_name: 工作表名称
            start_row: 起始行号（用于分页读取，从0开始）
            end_row: 结束行号（用于分页读取，不包含）
            max_rows: 最大读取行数（用于分页读取）
            **kwargs: 其他参数
                - range_address: 范围地址（如 A1:C10）
                - value: 写入的值
                - data: 写入的数据（二维列表）
                - save_as: 保存路径（可选）

        Returns:
            操作结果字典（UDF v2.0 格式）

        分页读取示例：
            读取前100行:
                operation="read_range", sheet_name="Sheet1", start_row=0, max_rows=100
            从第100行开始读50行:
                operation="read_range", sheet_name="Sheet1", start_row=100, max_rows=50
        """
        try:
            excel = self._get_tool()

            # 特殊处理 read_range 操作，支持分页
            if operation == "read_range" and (start_row > 0 or end_row is not None or max_rows is not None):
                result = await self._read_range_with_pagination(
                    excel,
                    file_path,
                    sheet_name,
                    start_row,
                    end_row,
                    max_rows
                )
                # ✅ 每次操作后关闭 Excel 实例
                excel.close_app()
                return result
            else:
                # 其他操作直接调用底层工具
                result = excel.process_file(file_path, operation=operation, **kwargs)
                formatted_result = self._to_udf_v2_format(result, file_path, operation)
                # ✅ 每次操作后关闭 Excel 实例
                excel.close_app()
                return formatted_result

        except Exception as e:
            logger.error("excel_tool_failed", path=file_path, operation=operation, error=str(e))
            # ✅ 发生错误时也要尝试关闭 Excel
            if 'excel' in locals() and excel:
                try:
                    excel.close_app()
                except:
                    pass
            return {
                "status": "failed",
                "success": False,
                "data": None,
                "metadata": {
                    "schema_version": "v2.0",
                    "generator": "excel_processor",
                    "file_path": file_path,
                    "operation": operation,
                    "error_type": type(e).__name__
                },
                "summary": f"Excel 操作失败: {str(e)[:50]}"
            }

    async def _read_range_with_pagination(
        self,
        excel: ExcelWin32Tool,
        file_path: str,
        sheet_name: str,
        start_row: int,
        end_row: int,
        max_rows: int
    ) -> Dict[str, Any]:
        """
        分页读取 Excel 工作表

        通过读取整个范围然后切片实现分页

        Returns:
            {
                "status": "success",
                "success": true,
                "data": {
                    "file_path": "...",
                    "sheet_name": "Sheet1",
                    "data": [[...], ...],  # 二维数组
                    "range": {
                        "start": 0,
                        "end": 100,
                        "total": 1000
                    },
                    "has_more": true,
                    "next_start": 100,
                    "stats": {...}
                },
                "metadata": {...},
                "summary": "读取第1-100行（共1000行）"
            }
        """
        import time
        start_time = time.time()

        # 先读取整个工作表（如果需要）
        # 这里使用已使用的范围
        doc = excel.open_document(file_path, read_only=True)
        if not doc:
            return {
                "status": "failed",
                "success": False,
                "data": None,
                "metadata": {
                    "schema_version": "v2.0",
                    "generator": "excel_processor",
                    "file_path": file_path,
                    "operation": "read_range"
                },
                "summary": "无法打开Excel文档"
            }

        try:
            # 选择工作表
            if sheet_name:
                sheet = doc.Sheets(sheet_name)
            else:
                sheet = doc.ActiveSheet

            # 获取已使用的范围
            used_range = sheet.UsedRange
            total_rows = used_range.Rows.Count
            total_cols = used_range.Columns.Count

            # 确定读取范围
            if end_row is None:
                if max_rows:
                    end_row = min(start_row + max_rows, total_rows)
                else:
                    end_row = total_rows

            # 边界检查
            start_row = max(0, min(start_row, total_rows))
            end_row = max(start_row, min(end_row, total_rows))

            # 读取指定范围的单元格
            row_count = end_row - start_row
            if row_count <= 0:
                return {
                    "status": "failed",
                    "success": False,
                    "data": None,
                    "metadata": {
                        "schema_version": "v2.0",
                        "generator": "excel_processor",
                        "file_path": file_path,
                        "operation": "read_range"
                    },
                    "summary": f"无效的行范围: {start_row}-{end_row}"
                }

            # 读取数据
            data = []
            for i in range(1, row_count + 1):
                row_data = []
                for j in range(1, total_cols + 1):
                    cell = sheet.Cells(start_row + i, j)
                    value = cell.Value if cell.Value else ""
                    row_data.append(str(value))
                data.append(row_data)

            # 检查是否还有更多内容
            has_more = end_row < total_rows
            next_start = end_row if has_more else None

            execution_time = time.time() - start_time

            # 关闭文档
            doc.Close(SaveChanges=False)

            return {
                "status": "success",
                "success": True,
                "data": {
                    "file_path": file_path,
                    "sheet_name": sheet_name or sheet.Name,
                    "data": data,
                    "range": {
                        "start": start_row,
                        "end": end_row,
                        "total": total_rows
                    },
                    "has_more": has_more,
                    "next_start": next_start,
                    "stats": {
                        "rows_read": row_count,
                        "cols_read": total_cols,
                        "total_rows": total_rows,
                        "total_cols": total_cols
                    }
                },
                "metadata": {
                    "schema_version": "v2.0",
                    "generator": "excel_processor",
                    "file_path": file_path,
                    "operation": "read_range",
                    "execution_time": execution_time
                },
                "summary": self._generate_read_summary(
                    start_row,
                    end_row,
                    total_rows,
                    has_more
                )
            }

        except Exception as e:
            doc.Close(SaveChanges=False)
            raise

    def _generate_read_summary(
        self,
        start: int,
        end: int,
        total: int,
        has_more: bool
    ) -> str:
        """生成读取操作的摘要信息"""
        summary = f"读取第{start+1}-{end}行（共{total}行）"
        if has_more:
            summary += f"，还有{total-end}行未读取"
        return summary

    def _to_udf_v2_format(
        self,
        result: Dict[str, Any],
        file_path: str,
        operation: str
    ) -> Dict[str, Any]:
        """将底层工具的返回结果转换为 UDF v2.0 格式"""
        status = result.get("status", "failed")
        success = status == "success"

        # 构建标准格式
        standard_result = {
            "status": status,
            "success": success,
            "data": None,
            "metadata": {
                "schema_version": "v2.0",
                "generator": "excel_processor",
                "file_path": file_path,
                "operation": operation
            },
            "summary": result.get("summary", f"Excel {operation} 操作完成")
        }

        # 处理成功情况
        if success:
            # 保留原始数据（根据操作类型不同）
            if operation == "stats":
                standard_result["data"] = result.get("stats", {})
            elif operation == "list_sheets":
                standard_result["data"] = result.get("sheets", [])
            elif operation == "read_range":
                standard_result["data"] = result.get("data", [])
            elif operation == "write_range" or operation == "write_cell":
                standard_result["data"] = {
                    "success": True,
                    "message": "数据已写入"
                }

        # 处理失败情况
        if "error" in result:
            standard_result["data"] = None
            standard_result["metadata"]["error"] = result["error"]
            standard_result["metadata"]["error_type"] = "ToolExecutionError"

        # 添加执行时间（如果有）
        if "execution_time" in result:
            standard_result["metadata"]["execution_time"] = result["execution_time"]

        return standard_result

    def get_function_schema(self) -> Dict[str, Any]:
        """获取 Function Calling Schema"""
        return {
            "name": "excel_processor",
            "description": self.description + "\n\n**常用操作示例**：\n" +
                "- 列出工作表：{\"file_path\": \"D:\\\\docs\\\\data.xlsx\", \"operation\": \"list_sheets\"}\n" +
                "- 读取前100行：{\"file_path\": \"D:\\\\docs\\\\data.xlsx\", \"operation\": \"read_range\", \"sheet_name\": \"Sheet1\", \"start_row\": 0, \"max_rows\": 100}\n" +
                "- 读取指定范围：{\"file_path\": \"D:\\\\docs\\\\data.xlsx\", \"operation\": \"read_range\", \"sheet_name\": \"Sheet1\", \"range_address\": \"A1:C10\"}\n" +
                "- 写入单元格：{\"file_path\": \"D:\\\\docs\\\\data.xlsx\", \"operation\": \"write_range\", \"sheet_name\": \"Sheet1\", \"range_address\": \"A1\", \"data\": [[\"新值\"]]}",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Excel 文件的完整路径（如 D:\\\\docs\\\\data.xlsx）"
                    },
                    "operation": {
                        "type": "string",
                        "enum": ["list_sheets", "read_range", "write_range", "stats"],
                        "description": "操作类型：list_sheets=列出工作表, read_range=读取范围（支持分页）, write_range=写入范围, stats=统计信息"
                    },
                    "sheet_name": {
                        "type": "string",
                        "description": "工作表名称（如 Sheet1）。如果不指定，使用活动工作表"
                    },
                    "start_row": {
                        "type": "integer",
                        "description": "起始行号（从0开始），用于分页读取。例如：start_row=0 表示从第一行开始"
                    },
                    "end_row": {
                        "type": "integer",
                        "description": "结束行号（不包含），用于分页读取。例如：end_row=100 表示读取到第100行（不含）。如果不指定，读取到工作表结尾或达到max_rows限制"
                    },
                    "max_rows": {
                        "type": "integer",
                        "description": "最大读取行数（用于分页读取），默认100。当指定此参数时，end_row会被自动计算"
                    },
                    "range_address": {
                        "type": "string",
                        "description": "单元格范围（如 A1:C10），用于读取或写入"
                    },
                    "data": {
                        "type": "array",
                        "description": "要写入的数据（二维数组）",
                        "items": {
                            "type": "array",
                            "items": {"type": "string"}
                        }
                    },
                    "save_as": {
                        "type": "string",
                        "description": "保存为新文件的路径（可选）"
                    }
                },
                "required": ["file_path", "operation"]
            }
        }

    def is_available(self) -> bool:
        """检查工具是否可用（仅 Windows）"""
        import os
        return os.name == 'nt'  # Windows 系统
