from app.agent.memory.active_memory_retriever import (
    ActiveMemoryRetriever,
    build_social_memory_context,
)


class FakeMemoryStore:
    def __init__(self, memory: str, daily_results=None):
        self.memory = memory
        self.daily_results = daily_results or {}

    def get_memory_context(self) -> str:
        return f"## 长期记忆\n{self.memory}" if self.memory.strip() else ""

    def search_daily_notes(self, query: str, limit: int = 10):
        return self.daily_results.get(query, [])[:limit]


def test_social_memory_context_does_not_auto_recall_daily_notes():
    store = FakeMemoryStore(
        "- 长期偏好：回复简洁",
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

    context = build_social_memory_context(store, "臭氧怎么分析")

    assert "## 长期记忆" in context
    assert "- 长期偏好：回复简洁" in context
    assert "## 我想起的过往片段" not in context
    assert "上次问过臭氧来源" not in context


def test_daily_note_recall_formats_fact_snippets_without_assistant_reply():
    retriever = ActiveMemoryRetriever()
    store = FakeMemoryStore(
        "",
        daily_results={
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
            ]
        },
    )

    context = retriever.retrieve(store, "PM2.5")

    assert "snippet:" in context
    assert "source: memory/2026-06-03.md:3" in context
    assert "timestamp: 2026-06-03T10:00:00" in context
    assert "用户关注 PM2.5 趋势" in context
    assert "完整历史分析回复" not in context
    assert "**助手**" not in context
