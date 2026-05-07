"""
VOCs data query tool module.

结构化VOCs数据查询工具 - 直接调用广东超站API
替换原自然语言API工具（tool.py，已失效）
"""

from app.tools.query.get_vocs_data.tool_api import GetVOCsDataTool

__all__ = ["GetVOCsDataTool"]
