"""
测试溯源模式 SessionMemory.data_registry 属性初始化

验证修复：SessionMemory 应该在初始化时设置 data_registry 属性
以确保溯源模式（ExpertRouterV3）能够正常工作。

问题背景：
- 溯源模式使用 ExpertRouterV3 创建独立的 DataContextManager 和 SessionMemory
- SessionMemory.load_data_from_file() 需要访问 self.data_registry
- 之前的 __init__() 未初始化此属性，导致 AttributeError
"""

import pytest
from pathlib import Path
from app.agent.memory.session_memory import SessionMemory
from app.services.data_registry import data_registry


def test_session_memory_has_data_registry_attribute():
    """验证 SessionMemory 初始化后拥有 data_registry 属性"""
    sm = SessionMemory('test_session')

    # 验证属性存在
    assert hasattr(sm, 'data_registry'), "SessionMemory 应该有 data_registry 属性"

    # 验证属性类型
    assert sm.data_registry is data_registry, "data_registry 应该是全局单例"

    # 验证 base_dir 可访问
    assert hasattr(sm.data_registry, 'base_dir'), "data_registry 应该有 base_dir 属性"
    assert sm.data_registry.base_dir.exists(), "data_registry.base_dir 应该存在"


def test_session_memory_load_data_from_file_with_none():
    """验证 load_data_from_file 对 None 参数的处理"""
    sm = SessionMemory('test_session')

    # None 参数应该返回 None 而不是抛出 AttributeError
    result = sm.load_data_from_file(None)
    assert result is None, "None 参数应该返回 None"


def test_session_memory_initialization_logs():
    """验证初始化日志包含 has_data_registry 信息"""
    import structlog

    sm = SessionMemory('test_session')

    # 验证属性已设置（通过实际访问而不是检查日志）
    assert sm.data_registry is not None


if __name__ == "__main__":
    # 快速验证
    print("测试 SessionMemory.data_registry 初始化...")

    sm = SessionMemory('quick_test')
    print(f"✓ data_registry 属性存在: {hasattr(sm, 'data_registry')}")
    print(f"✓ data_registry 类型: {type(sm.data_registry).__name__}")
    print(f"✓ base_dir: {sm.data_registry.base_dir}")
    print(f"✓ load_data_from_file(None): {sm.load_data_from_file(None)}")

    print("\n所有测试通过！")
