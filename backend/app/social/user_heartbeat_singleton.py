"""
全局单例：存储 UserHeartbeatManager 实例

用于在工具执行时获取 UserHeartbeatManager（特别是 social 模式的定时任务工具）
"""

_user_heartbeat_manager_instance = None


def set_user_heartbeat_manager(user_heartbeat_manager):
    """设置全局 UserHeartbeatManager 实例"""
    global _user_heartbeat_manager_instance
    _user_heartbeat_manager_instance = user_heartbeat_manager


def get_user_heartbeat_manager():
    """获取全局 UserHeartbeatManager 实例"""
    return _user_heartbeat_manager_instance


def clear_user_heartbeat_manager():
    """清除全局 UserHeartbeatManager 实例"""
    global _user_heartbeat_manager_instance
    _user_heartbeat_manager_instance = None
