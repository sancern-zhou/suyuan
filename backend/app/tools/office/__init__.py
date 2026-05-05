"""
Office Automation Tools

提供跨平台 Office 文档的自动化处理能力。

架构：
- Phase 1: XML 解包/打包工具（已完成）
- Phase 2: Word 高级编辑（已完成）
- Phase 3: 集成测试与文档（待实施）

工具列表：
- UnpackOfficeTool: 解包 Office 文件为 XML
- PackOfficeTool: 打包 XML 为 Office 文件
- AcceptChangesTool: 接受 Word 文档所有修订
- FindReplaceTool: Word 文档查找替换
- ReadPptxTool: 读取 PPTX 内容
- CreatePptxTool: 使用 PptxGenJS 创建 PPTX
- soffice: LibreOffice 沙箱适配（跨平台）

旧版工具（Win32 COM，待废弃）：
- WordWin32Tool, ExcelWin32Tool, PPTWin32Tool
- WordWin32LLMTool, ExcelWin32LLMTool, PPTWin32LLMTool

Excel操作说明：
所有Excel操作（创建、读取、修改、公式重算等）请使用 execute_python 工具，
配合 openpyxl、pandas、xlsxwriter 等库实现。

PPT操作说明：
读取PPT请优先使用 read_pptx；创建PPT请优先使用 create_pptx（PptxGenJS）。
复杂自定义处理可使用 execute_python 配合 python-pptx 库实现。
"""

# Phase 1: 跨平台工具（已完成）
from .unpack_tool import UnpackOfficeTool
from .pack_tool import PackOfficeTool

# Phase 2: Word 高级编辑（已完成）
from .accept_changes_tool import AcceptChangesTool
from .find_replace_tool import FindReplaceTool
from .read_pptx_tool import ReadPptxTool
from .create_pptx_tool import CreatePptxTool


__all__ = [
    # Phase 1: 跨平台工具
    'UnpackOfficeTool',
    'PackOfficeTool',

    # Phase 2: Word 高级编辑
    'AcceptChangesTool',
    'FindReplaceTool',
    'ReadPptxTool',
    'CreatePptxTool',
]
