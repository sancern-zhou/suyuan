"""
全局单例：存储 MessageBus 实例和当前 chat_id 和 channel

用于在工具执行时获取 MessageBus、chat_id 和 channel（特别是 social 模式）
"""

_message_bus_instance = None
_current_chat_id = None
_current_channel = None  # ✅ 当前渠道名称（如 weixin:auto_mn8k8rry）


def set_message_bus(message_bus):
    """设置全局 MessageBus 实例"""
    global _message_bus_instance
    _message_bus_instance = message_bus


def get_message_bus():
    """获取全局 MessageBus 实例"""
    return _message_bus_instance


def set_current_chat_id(chat_id: str):
    """设置当前 chat_id（用于 social 模式）"""
    global _current_chat_id
    _current_chat_id = chat_id


def get_current_chat_id():
    """获取当前 chat_id"""
    return _current_chat_id


def set_current_channel(channel: str):
    """设置当前 channel（用于 social 模式）"""
    global _current_channel
    _current_channel = channel


def get_current_channel():
    """获取当前 channel"""
    return _current_channel


def clear_message_bus():
    """清除全局 MessageBus 实例"""
    global _message_bus_instance, _current_chat_id, _current_channel
    _message_bus_instance = None
    _current_chat_id = None
    _current_channel = None
