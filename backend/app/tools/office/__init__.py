"""
Office Automation Tools (Win32 COM)

提供 Windows 平台下 Office 文档的自动化处理能力。
"""

from .word_win32_tool import WordWin32Tool
from .excel_win32_tool import ExcelWin32Tool
from .ppt_win32_tool import PPTWin32Tool
from .word_tool import WordWin32LLMTool
from .excel_tool import ExcelWin32LLMTool
from .ppt_tool import PPTWin32LLMTool

__all__ = [
    'WordWin32Tool',
    'ExcelWin32Tool',
    'PPTWin32Tool',
    'WordWin32LLMTool',
    'ExcelWin32LLMTool',
    'PPTWin32LLMTool',
]
