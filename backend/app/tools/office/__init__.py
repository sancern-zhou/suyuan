"""
Office Automation Tools

提供当前 Agent 可用的 Office 文档处理能力。

架构：
- PPT 读取、模板分析、生成、编辑和验证
- Word 读取由 read_file/read_docx 负责，助手模式不再暴露 Word 编辑工具
- Excel 操作通过 execute_python 配合 openpyxl/pandas/xlsxwriter 完成

工具列表：
- ReadPptxTool: 读取 PPTX 内容
- CreatePptxWithPptMasterTool: 按 PPT Master 工作流创建生产级 PPTX
- soffice: LibreOffice 沙箱适配（跨平台）

旧版工具（Win32 COM，待废弃）：
- WordWin32Tool, ExcelWin32Tool, PPTWin32Tool
- WordWin32LLMTool, ExcelWin32LLMTool, PPTWin32LLMTool

Excel操作说明：
所有Excel操作（创建、读取、修改、公式重算等）请使用 execute_python 工具，
配合 openpyxl、pandas、xlsxwriter 等库实现。

PPT操作说明：
读取PPT请优先使用 read_pptx。
生成正式或业务型PPT请优先直接调用 create_pptx_with_ppt_master，按目标、大纲、风格、
版式锁定、逐页绘制、QA、导出检查的流程生成。
基于模板生成PPT请使用 create_pptx_from_template。
execute_python 仅用于复杂的局部编辑、特殊兼容处理或前置数据/图片资产生成。
"""

from .read_pptx_tool import ReadPptxTool
from .ppt_master_tool import CreatePptxWithPptMasterTool


__all__ = [
    'ReadPptxTool',
    'CreatePptxWithPptMasterTool',
]
