"""
Office Automation Tools

提供跨平台 Office 文档的自动化处理能力。

架构：
- Phase 1: XML 解包/打包工具（已完成）
- Phase 2: Word 高级编辑（已完成）
- Phase 3: Excel 公式重算（已完成）
- Phase 4: PPT 幻灯片操作（已完成）
- Phase 5: 集成测试与文档（待实施）

工具列表：
- UnpackOfficeTool: 解包 Office 文件为 XML
- PackOfficeTool: 打包 XML 为 Office 文件
- AcceptChangesTool: 接受 Word 文档所有修订
- FindReplaceTool: Word 文档查找替换
- ExcelRecalcTool: Excel 公式重算
- AddSlideTool: PPT 幻灯片添加
- soffice: LibreOffice 沙箱适配（跨平台）

旧版工具（Win32 COM，待废弃）：
- WordWin32Tool, ExcelWin32Tool, PPTWin32Tool
- WordWin32LLMTool, ExcelWin32LLMTool, PPTWin32LLMTool
"""

# Phase 1: 跨平台工具（已完成）
from .unpack_tool import UnpackOfficeTool
from .pack_tool import PackOfficeTool

# Phase 2: Word 高级编辑（已完成）
from .accept_changes_tool import AcceptChangesTool
from .find_replace_tool import FindReplaceTool

# Phase 3: Excel 公式重算（已完成）
from .excel_recalc_tool import ExcelRecalcTool

# Phase 4: PPT 幻灯片操作（已完成）
from .add_slide_tool import AddSlideTool


__all__ = [
    # Phase 1: 跨平台工具
    'UnpackOfficeTool',
    'PackOfficeTool',

    # Phase 2: Word 高级编辑
    'AcceptChangesTool',
    'FindReplaceTool',

    # Phase 3: Excel 公式重算
    'ExcelRecalcTool',

    # Phase 4: PPT 幻灯片操作
    'AddSlideTool',
]
