"""
统一记忆系统测试

测试所有7种模式的记忆功能：
- 模式隔离
- 用户识别（共享 vs 独立记忆）
- 记忆整合触发
- 社交模式向后兼容
"""

import pytest
import asyncio
from pathlib import Path
from datetime import datetime
import tempfile

from app.agent.memory.unified_memory_manager import UnifiedMemoryManager
from app.agent.memory.memory_store import MemoryStore, ImprovedMemoryStore
from app.social.memory_store import MemoryStore as SocialMemoryStore
from app.social.memory_store import ImprovedMemoryStore as SocialImprovedMemoryStore


async def test_manager_initialization():
    """测试管理器初始化"""
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        manager = UnifiedMemoryManager(base_workspace=str(tmp_path))

        assert manager.base_workspace == tmp_path
        assert manager.cache_size == 0
        assert manager._max_cache_size == 100
        print("✓ 管理器初始化测试通过")


async def test_get_user_memory():
    """测试获取用户记忆"""
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        manager = UnifiedMemoryManager(base_workspace=str(tmp_path))

        # 获取用户记忆（expert模式）
        memory = await manager.get_user_memory("test_user", "expert")

        assert isinstance(memory, ImprovedMemoryStore)
        assert memory.user_id == "test_user"
        assert memory.mode == "expert"
        assert memory.workspace == tmp_path / "expert" / "test_user"
        print("✓ 获取用户记忆测试通过")


async def test_memory_caching():
    """测试记忆缓存"""
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        manager = UnifiedMemoryManager(base_workspace=str(tmp_path))

        # 第一次获取
        memory1 = await manager.get_user_memory("test_user", "assistant")
        # 第二次获取（应该从缓存返回）
        memory2 = await manager.get_user_memory("test_user", "assistant")

        assert memory1 is memory2  # 同一个对象
        assert manager.cache_size == 1
        print("✓ 记忆缓存测试通过")


async def test_consolidation_offset():
    """测试整合偏移量"""
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        manager = UnifiedMemoryManager(base_workspace=str(tmp_path))

        # 初始偏移量
        offset = await manager.get_consolidation_offset("test_user")
        assert offset == 0

        # 设置偏移量
        await manager.set_consolidation_offset("test_user", 10)
        offset = await manager.get_consolidation_offset("test_user")
        assert offset == 10
        print("✓ 整合偏移量测试通过")


async def test_cleanup_mode_memory():
    """测试清理模式记忆"""
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        manager = UnifiedMemoryManager(base_workspace=str(tmp_path))

        # 创建多个模式的记忆
        await manager.get_user_memory("user1", "assistant")
        await manager.get_user_memory("user2", "assistant")
        await manager.get_user_memory("user3", "expert")

        assert manager.cache_size == 3

        # 清理assistant模式
        await manager.cleanup_mode_memory("assistant")

        assert manager.cache_size == 1  # 只剩expert模式
        print("✓ 清理模式记忆测试通过")


async def test_memory_store_initialization():
    """测试记忆存储初始化"""
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        memory = MemoryStore(
            user_id="test_user",
            mode="expert",
            workspace=tmp_path
        )

        assert memory.user_id == "test_user"
        assert memory.mode == "expert"
        assert memory.workspace == tmp_path / "expert" / "test_user"
        assert memory.memory_file.exists()
        assert memory.history_file.exists()
        print("✓ 记忆存储初始化测试通过")

async def test_mode_isolation():
    """测试模式隔离"""
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        manager = UnifiedMemoryManager(base_workspace=str(tmp_path))

        # 同一用户在助手模式和专家模式
        memory_assistant = await manager.get_user_memory("assistant:john_doe:shared", "assistant")
        memory_expert = await manager.get_user_memory("expert:john_doe:shared", "expert")

        # 设置不同的记忆
        memory_assistant.remember_fact("喜欢Markdown格式", "用户偏好")
        memory_expert.remember_fact("喜欢新标准HJ 633-2026", "用户偏好")

        # 验证隔离
        context_assistant = memory_assistant.get_memory_context()
        context_expert = memory_expert.get_memory_context()

        assert "Markdown格式" in context_assistant
        assert "Markdown格式" not in context_expert

        assert "新标准HJ 633-2026" in context_expert
        assert "新标准HJ 633-2026" not in context_assistant

        # 验证文件路径隔离（注意：冒号被替换为下划线）
        assert memory_assistant.workspace == tmp_path / "assistant" / "assistant_john_doe_shared"
        assert memory_expert.workspace == tmp_path / "expert" / "expert_john_doe_shared"
        print("✓ 模式隔离测试通过")


async def test_shared_memory_by_user():
    """测试同一用户跨session共享记忆"""
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        manager = UnifiedMemoryManager(base_workspace=str(tmp_path))

        # 同一用户的不同session（共享记忆）
        memory1 = await manager.get_user_memory("assistant:john_doe:shared", "assistant")
        memory2 = await manager.get_user_memory("assistant:john_doe:shared", "assistant")

        # 在第一个session设置记忆
        memory1.remember_fact("喜欢Python编程", "用户偏好")

        # 在第二个session读取记忆
        context2 = memory2.get_memory_context()

        # 验证共享
        assert "Python编程" in context2

        # 验证是同一个对象（缓存）
        assert memory1 is memory2
        print("✓ 共享记忆测试通过")


async def test_unique_memory_by_session():
    """测试不同session独立记忆"""
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        manager = UnifiedMemoryManager(base_workspace=str(tmp_path))

        # 不同session（独立记忆）
        memory1 = await manager.get_user_memory("assistant:session_1:unique", "assistant")
        memory2 = await manager.get_user_memory("assistant:session_2:unique", "assistant")

        # 在第一个session设置记忆
        memory1.remember_fact("Session 1的偏好", "用户偏好")

        # 在第二个session读取记忆
        context2 = memory2.get_memory_context()

        # 验证独立（不应该包含Session 1的记忆）
        assert "Session 1的偏好" not in context2

        # 验证是不同的对象
        assert memory1 is not memory2
        print("✓ 独立记忆测试通过")


async def test_social_memory_store_compatibility():
    """测试社交模式MemoryStore兼容性"""
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        # 使用社交模式的MemoryStore
        memory = SocialMemoryStore(
            user_id="weixin:bot_abc:123456",
            workspace=tmp_path
        )

        # 验证模式正确设置为social
        assert memory.mode == "social"
        assert memory.user_id == "weixin:bot_abc:123456"

        # 验证工作空间路径（向后兼容）
        # 社交模式使用特殊的路径格式：{workspace}/{safe_user_id}/
        # 其中 safe_user_id = user_id.replace(":", "_")
        expected_path = tmp_path / "weixin_bot_abc_123456"
        print(f"  实际路径: {memory.workspace}")
        print(f"  期望路径: {expected_path}")
        assert memory.workspace == expected_path

        # 测试记住事实
        success = memory.remember_fact("社交模式用户偏好", "用户偏好")
        assert success

        # 验证记忆内容
        context = memory.get_memory_context()
        assert "社交模式用户偏好" in context
        print("✓ 社交模式MemoryStore兼容性测试通过")


async def test_social_memory_format():
    """测试社交模式记忆格式（向后兼容）"""
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        memory = SocialMemoryStore(
            user_id="weixin:bot_test:user123",
            workspace=tmp_path
        )

        # 添加记忆
        memory.remember_fact("喜欢使用新标准", "用户偏好")
        memory.remember_fact("分析结论：O3浓度上升", "历史结论")

        # 读取记忆文件
        memory_content = memory.memory_file.read_text(encoding="utf-8")

        # 验证格式（向后兼容）
        assert "# 长期记忆 (MEMORY.md)" in memory_content
        assert "## 用户偏好" in memory_content
        assert "## 历史结论" in memory_content
        assert "喜欢使用新标准" in memory_content
        assert "O3浓度上升" in memory_content
        print("✓ 社交模式记忆格式测试通过")


async def test_cache_stats():
    """测试缓存统计"""
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        manager = UnifiedMemoryManager(base_workspace=str(tmp_path))

        # 创建不同模式的记忆
        await manager.get_user_memory("user1", "assistant")
        await manager.get_user_memory("user2", "assistant")
        await manager.get_user_memory("user3", "expert")
        await manager.get_user_memory("user4", "query")

        # 获取统计信息
        stats = await manager.get_cache_stats()

        assert stats["total_cache_size"] == 4
        assert stats["max_cache_size"] == 100
        assert stats["mode_counts"]["assistant"] == 2
        assert stats["mode_counts"]["expert"] == 1
        assert stats["mode_counts"]["query"] == 1
        print("✓ 缓存统计测试通过")


async def test_all():
    """运行所有测试"""
    print("\n" + "="*80)
    print("统一记忆系统测试")
    print("="*80 + "\n")

    await test_manager_initialization()
    await test_get_user_memory()
    await test_memory_caching()
    await test_consolidation_offset()
    await test_cleanup_mode_memory()
    await test_memory_store_initialization()
    await test_mode_isolation()
    await test_shared_memory_by_user()
    await test_unique_memory_by_session()
    await test_social_memory_store_compatibility()
    await test_social_memory_format()
    await test_cache_stats()

    print("\n" + "="*80)
    print("✅ 所有测试通过！")
    print("="*80 + "\n")


if __name__ == "__main__":
    # 运行所有测试
    asyncio.run(test_all())
