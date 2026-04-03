"""
观察结果格式化器模块

提供模块化的工具结果格式化功能，替代 loop.py 中硬编码的格式化逻辑。
"""

from .base import ObservationFormatter
from .registry import FormatterRegistry

# 办公工具格式化器
from .office_formatters import (
    ImageFormatter,
    FileFormatter,
    GrepFormatter,
    GlobFormatter,
    ListDirectoryFormatter,
    BrowserFormatter,
    TodoWriteFormatter,
    ExecutePythonFormatter,
    WebSearchFormatter,
    WebFetchFormatter,
    SearchHistoryFormatter,
)

# 特殊工具格式化器
from .special_formatters import (
    BashFormatter,
    OfficeFormatter,
    ReadDataRegistryFormatter,
    ParsePDFFormatter,
)

# 数据工具格式化器
from .data_formatters import (
    DataQueryFormatter,
    StatisticsFormatter,
    DetailedResultFormatter,
)

__all__ = [
    "ObservationFormatter",
    "FormatterRegistry",
    # 办公工具格式化器
    "ImageFormatter",
    "FileFormatter",
    "GrepFormatter",
    "GlobFormatter",
    "ListDirectoryFormatter",
    "BrowserFormatter",
    "TodoWriteFormatter",
    "ExecutePythonFormatter",
    "WebSearchFormatter",
    "WebFetchFormatter",
    "SearchHistoryFormatter",
    # 特殊工具格式化器
    "BashFormatter",
    "OfficeFormatter",
    "ReadDataRegistryFormatter",
    "ParsePDFFormatter",
    # 数据工具格式化器
    "DataQueryFormatter",
    "StatisticsFormatter",
    "DetailedResultFormatter",
]
