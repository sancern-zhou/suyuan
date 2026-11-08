"""
Office Automation Tools

提供当前 Agent 可用的 Office 文档处理能力。

架构：
- PPT 读取、PPT Master 生成/续改/渲染和验证
- Word 读取由 read_file/read_docx 负责，助手模式不再暴露 Word 编辑工具
- Excel 操作通过 execute_python 配合 openpyxl/pandas/xlsxwriter 完成
- 企业微信能力通过官方 wecom-cli 调用（WeComCliTool）

工具列表：
- ReadPptxTool: 读取 PPTX 内容
- WeComCliTool: 官方企业微信 CLI 包装工具
- soffice: LibreOffice 沙箱适配（跨平台）

Excel操作说明：
所有Excel操作（创建、读取、修改、公式重算等）请使用 execute_python 工具，
配合 openpyxl、pandas、xlsxwriter 等库实现。

PPT操作说明：
读取既有 PPTX 用 read_pptx。
生成与多轮修改走技能路线：view_skill: pptx_authoring → execute_python 生成/迭代 →
validate_pptx 渲染验收 + 视觉自评，双过后交付。
"""

from .read_pptx_tool import ReadPptxTool
from .wecom_cli import WeComCliTool


__all__ = [
    'ReadPptxTool',
    'WeComCliTool',
]
