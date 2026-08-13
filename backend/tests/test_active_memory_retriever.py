"""
测试 ActiveMemoryRetriever
"""

import pytest
import os
from app.agent.memory.active_memory_retriever import ActiveMemoryRetriever, build_social_memory_context
from app.agent.memory.memory_store import ImprovedMemoryStore


class MockMemoryStore:
    """模拟的记忆存储"""

    def __init__(self, content: str, daily_results=None):
        self._content = content
        self._daily_results = daily_results or {}

    def read_long_term(self) -> str:
        return self._content

    def get_memory_context(self) -> str:
        return f"## 长期记忆\n{self._content}" if self._content.strip() else ""

    def search_daily_notes(self, query: str, limit: int = 10):
        return self._daily_results.get(query, [])[:limit]


@pytest.fixture
def sample_memory():
    """示例记忆内容"""
    return """# 用户偏好

- 用户姓名：张三
- 职业：工程师
- 技术水平：高级
- 喜欢简洁的回答

## 项目信息

- 项目名称：溯源分析系统
- 使用语言：Python
- 主要框架：FastAPI
- 部署环境：生产环境

## 学习历史

- 用户对空气质量分析很感兴趣
- 用户经常查询 PM2.5 数据
- 用户希望图表美观
- 用户不喜欢冗长的解释
"""


@pytest.fixture
def retriever():
    """创建召回器实例"""
    return ActiveMemoryRetriever(
        max_tokens=2000,
        max_facts=20,
        keyword_weight=1.0,
        recency_weight=0.5
    )


class TestActiveMemoryRetriever:
    """测试 ActiveMemoryRetriever"""

    def test_extract_keywords_chinese(self, retriever):
        """测试提取中文关键词"""
        query = "我想查询空气质量数据"
        keywords = retriever._extract_keywords(query)
        # 简单分词会产生 2-4 字的片段
        assert len(keywords) > 0
        assert any("查询" in k for k in keywords)
        assert any("空气质量" in k or "空气" in k for k in keywords)
        assert any("数据" in k for k in keywords)

    def test_extract_keywords_mixed(self, retriever):
        """测试提取中英文混合关键词"""
        query = "帮我分析 FastAPI 框架的性能"
        keywords = retriever._extract_keywords(query)
        assert len(keywords) > 0
        assert any("分析" in k for k in keywords)
        assert "fastapi" in keywords
        assert any("框架" in k for k in keywords)

    def test_search_relevant_facts(self, retriever, sample_memory):
        """测试搜索相关事实"""
        keywords = ["空气质量", "查询", "PM2.5"]
        facts = retriever._search_relevant_facts(sample_memory, keywords)

        assert len(facts) > 0
        # 检查是否包含相关内容
        contents = [f["content"] for f in facts]
        assert any("空气质量" in c for c in contents)
        assert any("PM2.5" in c for c in contents)

    def test_retrieve_searches_daily_notes_only(self, retriever, sample_memory):
        """自动历史召回只搜索 daily notes，不搜索 MEMORY.md。"""
        memory_store = MockMemoryStore(sample_memory)

        query = "我想查询 PM2.5 空气质量数据"
        result = retriever.retrieve(memory_store, query)

        assert result == ""

    def test_retrieve_returns_fact_snippet_source_and_timestamp(self, retriever):
        """daily notes 召回只返回事实型片段和来源元数据，不返回完整助手回复。"""
        memory_store = MockMemoryStore(
            "",
            daily_results={
                "PM2": [
                    {
                        "context": (
                            "**用户**: 昨天查询 PM2.5\n"
                            "**助手**: 好的，以下是完整历史分析回复，包含很多可复读话术。\n"
                            "- 稳定事实：用户关注 PM2.5 趋势"
                        ),
                        "line_number": 3,
                        "source": "memory/2026-06-03.md",
                        "timestamp": "2026-06-03T10:00:00",
                    }
                ],
                "PM2.5": [
                    {
                        "context": (
                            "**用户**: 昨天查询 PM2.5\n"
                            "**助手**: 好的，以下是完整历史分析回复，包含很多可复读话术。\n"
                            "- 稳定事实：用户关注 PM2.5 趋势"
                        ),
                        "line_number": 3,
                        "source": "memory/2026-06-03.md",
                        "timestamp": "2026-06-03T10:00:00",
                    }
                ],
            },
        )

        result = retriever.retrieve(memory_store, "PM2.5")

        assert "## 我想起的过往片段" in result
        assert "snippet:" in result
        assert "source: memory/2026-06-03.md:3" in result
        assert "timestamp: 2026-06-03T10:00:00" in result
        assert "用户关注 PM2.5 趋势" in result
        assert "完整历史分析回复" not in result
        assert "**助手**" not in result
        assert "## 相关记忆" not in result

    def test_retrieve_filters_tool_protocol_from_daily_notes(self, retriever):
        """daily notes 召回进入 prompt 前必须移除内部工具协议。"""
        memory_store = MockMemoryStore(
            "",
            daily_results={
                "记忆": [
                    {
                        "context": "\n".join([
                            "**用户**: 查看长期记忆文件的内容",
                            "{'type': 'tool_use', 'name': 'read_file', 'input': {'path': 'MEMORY.md'}}",
                            "{\"type\":\"tool_result\",\"tool_name\":\"read_file\",\"content\":\"# 长期记忆\"}",
                            "**助手**: 收到，当前状态已了解 ✅",
                            "**用户**: 为什么不回答真实问题",
                        ]),
                        "line_number": 193,
                        "source": "memory/2026-06-13.md",
                    }
                ],
            },
        )

        result = retriever.retrieve(memory_store, "查看长期记忆")

        assert "查看长期记忆文件的内容" in result
        assert "为什么不回答真实问题" in result
        assert "tool_use" not in result
        assert "tool_result" not in result
        assert "tool_name" not in result
        assert "read_file" not in result
        assert "收到，当前状态已了解" not in result

    def test_token_budget_limit(self, retriever, sample_memory):
        """测试 token 预算限制"""
        memory_store = MockMemoryStore(
            sample_memory,
            daily_results={
                "查询": [
                    {
                        "context": "**用户**: 查询所有信息",
                        "line_number": 2,
                        "source": "memory/2026-06-03.md",
                    }
                ]
            },
        )

        # 设置一个很小的预算
        retriever.max_tokens = 50

        query = "查询所有信息"
        result = retriever.retrieve(memory_store, query)

        # 估算结果不超过预算太多
        estimated_tokens = retriever._estimate_tokens(result)
        assert estimated_tokens <= 100  # 允许一些溢出

    def test_no_keywords_returns_empty(self, retriever, sample_memory):
        """测试没有关键词时返回空"""
        memory_store = MockMemoryStore(sample_memory)

        query = "你好"  # 停用词，没有有效关键词
        result = retriever.retrieve(memory_store, query)

        # 应该返回空字符串
        assert result == ""

    def test_empty_memory_returns_empty(self, retriever):
        """测试空记忆返回空"""
        memory_store = MockMemoryStore("")

        query = "查询数据"
        result = retriever.retrieve(memory_store, query)

        assert result == ""

    def test_estimate_tokens(self, retriever):
        """测试 token 估算"""
        # 纯中文
        chinese_text = "这是一个测试"
        tokens = retriever._estimate_tokens(chinese_text)
        assert tokens > 0

        # 纯英文
        english_text = "This is a test"
        tokens = retriever._estimate_tokens(english_text)
        assert tokens > 0

        # 混合
        mixed_text = "这是 Test 测试"
        tokens = retriever._estimate_tokens(mixed_text)
        assert tokens > 0


def test_environment_variable_config():
    """测试环境变量配置"""
    # 设置环境变量
    os.environ["ACTIVE_MEMORY_MAX_TOKENS"] = "5000"

    retriever = ActiveMemoryRetriever()
    assert retriever.max_tokens == 5000

    # 清理
    del os.environ["ACTIVE_MEMORY_MAX_TOKENS"]


def test_format_memory_context(retriever):
    """测试格式化历史会话记忆上下文"""
    facts = [
        {
            "content": "用户姓名：张三",
            "score": 2.0,
            "line_number": 2,
            "source": "memory/2026-06-03.md",
            "timestamp": "2026-06-03T10:00:00",
        },
        {
            "content": "职业：工程师",
            "score": 1.0,
            "line_number": 3,
            "source": "memory/2026-06-03.md",
            "timestamp": "2026-06-03T10:05:00",
        }
    ]

    result = retriever._format_memory_context(facts)

    assert "我想起的过往片段" in result
    assert "我会以用户此刻说的话为准" in result
    assert "snippet: 用户姓名：张三" in result
    assert "source: memory/2026-06-03.md:2" in result
    assert "timestamp: 2026-06-03T10:00:00" in result
    assert "snippet: 职业：工程师" in result
    assert result.startswith("##")


def test_build_social_memory_context_uses_long_term_memory_without_daily_notes_by_default():
    """社交上下文默认只注入 MEMORY.md，不自动召回 daily notes。"""
    memory_store = MockMemoryStore(
        "- 长期偏好：回复简洁\n- 用户关注：臭氧分析",
        daily_results={
            "臭氧": [
                {
                    "context": "**用户**: 上次问过臭氧来源",
                    "line_number": 4,
                    "source": "memory/2026-06-01.md",
                }
            ]
        },
    )

    context = build_social_memory_context(memory_store, "臭氧怎么分析")

    assert context.startswith("## 长期记忆")
    assert "- 长期偏好：回复简洁" in context
    assert "## 我想起的过往片段" not in context
    assert "上次问过臭氧来源" not in context
