"""
会话持久化模块

提供会话状态保存、恢复、管理等功能。

支持两种存储方式：
1. 文件存储（SessionManager）- 默认，向后兼容
2. 数据库存储（SessionManagerDB）- 推荐，性能更好
"""

from .models import Session, SessionInfo, SessionState
from .session_manager import SessionManager, get_session_manager

# 数据库版本（需要先运行 setup_session_db.sh 初始化）
try:
    from .session_manager_db import SessionManagerDB, get_session_manager_db
    DB_AVAILABLE = True
except ImportError:
    DB_AVAILABLE = False

__all__ = [
    "Session",
    "SessionInfo",
    "SessionState",
    "SessionManager",
    "get_session_manager",
]

if DB_AVAILABLE:
    __all__.extend([
        "SessionManagerDB",
        "get_session_manager_db"
    ])
