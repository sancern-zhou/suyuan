"""
进程级 MessageBus 单例，以及当前 social 执行上下文。

MessageBus 本身是进程共享服务；current chat/channel/bot_account 是一次
agent/tool 执行的上下文，必须用 ContextVar 做异步隔离，避免并发请求串线。
"""

from contextvars import ContextVar
from typing import Any, Optional, Tuple

_message_bus_instance = None
_current_chat_id: ContextVar[Optional[str]] = ContextVar("social_current_chat_id", default=None)
_current_channel: ContextVar[Optional[str]] = ContextVar("social_current_channel", default=None)
_current_bot_account: ContextVar[Optional[str]] = ContextVar("social_current_bot_account", default=None)


def set_message_bus(message_bus):
    """设置全局 MessageBus 实例"""
    global _message_bus_instance
    _message_bus_instance = message_bus


def get_message_bus():
    """获取全局 MessageBus 实例"""
    return _message_bus_instance


def set_current_chat_id(chat_id: str):
    """设置当前 chat_id（用于 social 模式）"""
    return _current_chat_id.set(chat_id)


def get_current_chat_id():
    """获取当前 chat_id"""
    return _current_chat_id.get()


def set_current_channel(channel: str):
    """设置当前 channel（用于 social 模式）"""
    return _current_channel.set(channel)


def get_current_channel():
    """获取当前 channel"""
    return _current_channel.get()


def set_current_bot_account(bot_account: str):
    """设置当前 bot_account（用于 social 模式）"""
    return _current_bot_account.set(bot_account)


def get_current_bot_account():
    """获取当前 bot_account"""
    return _current_bot_account.get()


ContextTokens = Tuple[Any, Any, Any]


def set_current_context(
    *,
    channel: Optional[str],
    chat_id: Optional[str],
    bot_account: Optional[str],
) -> ContextTokens:
    """设置本次 agent/tool 执行的 social 上下文，并返回可恢复 token。"""
    return (
        _current_channel.set(channel),
        _current_chat_id.set(chat_id),
        _current_bot_account.set(bot_account),
    )


def reset_current_context(tokens: ContextTokens) -> None:
    """恢复 set_current_context 前的 social 上下文。"""
    channel_token, chat_id_token, bot_account_token = tokens
    _current_bot_account.reset(bot_account_token)
    _current_chat_id.reset(chat_id_token)
    _current_channel.reset(channel_token)


def clear_message_bus():
    """清除全局 MessageBus 实例和上下文"""
    global _message_bus_instance
    _message_bus_instance = None
    _current_chat_id.set(None)
    _current_channel.set(None)
    _current_bot_account.set(None)
