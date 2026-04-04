"""
会话持久化模块

提供会话状态保存、恢复、管理等功能。

使用数据库存储（SessionManagerDB），由 PostgreSQL 驱动。
文件存储（SessionManager）保留用于向后兼容。
"""

from .models import Session, SessionInfo
from .session_manager import SessionManager, get_session_manager as _get_file_session_manager

# 数据库版本（默认）
try:
    from .session_manager_db import SessionManagerDB, get_session_manager_db
    DB_AVAILABLE = True
except ImportError:
    DB_AVAILABLE = False

# 默认使用数据库版本
if DB_AVAILABLE:
    get_session_manager = get_session_manager_db
else:
    get_session_manager = _get_file_session_manager

__all__ = [
    "Session",
    "SessionInfo",
    "SessionManager",
    "get_session_manager",
    "DB_AVAILABLE",
]

if DB_AVAILABLE:
    __all__.extend([
        "SessionManagerDB",
        "get_session_manager_db"
    ])
