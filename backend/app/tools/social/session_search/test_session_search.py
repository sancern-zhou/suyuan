"""
Session Search Tool Tests

Test FTS5 index building, Chinese search, English search, and empty results.
"""

import asyncio
import json
import tempfile
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.fixture
def temp_db_path(tmp_path):
    """Temporary database path for testing"""
    return str(tmp_path / "test_session_search.db")


@pytest.fixture
def temp_log_dir(tmp_path):
    """Temporary log directory with sample agent runs"""
    log_dir = tmp_path / "agent_runs"
    log_dir.mkdir()

    # Sample agent runs
    sample_runs = [
        {
            "run_id": "test_001",
            "session_id": "session_test_001",
            "query": "查询中山市空气质量数据",
            "final_answer_preview": "中山市空气质量指数为50，良。",
            "start_time": "2026-03-18T10:00:00",
            "status": "completed",
            "stats": {"duration_ms": 1000}
        },
        {
            "run_id": "test_002",
            "session_id": "session_test_002",
            "query": "Analyze PM2.5 pollution sources",
            "final_answer_preview": "Main sources: vehicle exhaust, industrial emissions.",
            "start_time": "2026-03-18T11:00:00",
            "status": "completed",
            "stats": {"duration_ms": 2000}
        },
        {
            "run_id": "test_003",
            "session_id": "session_test_003",
            "query": "VOCs组分源解析分析",
            "final_answer_preview": "VOCs主要来源包括溶剂使用、工业排放和机动车尾气。",
            "start_time": "2026-03-18T12:00:00",
            "status": "completed",
            "stats": {"duration_ms": 1500}
        }
    ]

    for run in sample_runs:
        log_file = log_dir / f"run_{run['run_id']}.json"
        log_file.write_text(json.dumps(run, ensure_ascii=False), encoding="utf-8")

    return str(log_dir)


class TestAgentRunsFTSIndex:
    """Test FTS index functionality"""

    def test_cjk_detection(self, temp_db_path):
        """Test CJK character detection"""
        from app.tools.social.session_search.fts_index import AgentRunsFTSIndex

        index = AgentRunsFTSIndex(db_path=temp_db_path)

        # Test CJK detection
        assert index._contains_cjk("中文测试") is True
        assert index._contains_cjk("ABC") is False
        assert index._contains_cjk("混合ABC中文") is True

        # Test CJK counting
        assert index._count_cjk("中文测试") == 4
        assert index._count_cjk("ABC") == 0
        assert index._count_cjk("混合ABC中文") == 4

    def test_build_index(self, temp_db_path, temp_log_dir):
        """Test building FTS index from log files"""
        from app.tools.social.session_search.fts_index import AgentRunsFTSIndex

        index = AgentRunsFTSIndex(db_path=temp_db_path)
        count = index.build_index(temp_log_dir)

        assert count == 3
        assert index._initialized is True

        stats = index.get_stats()
        assert stats["total_records"] == 3

    def test_chinese_search(self, temp_db_path, temp_log_dir):
        """Test Chinese search using trigram tokenizer"""
        from app.tools.social.session_search.fts_index import AgentRunsFTSIndex

        index = AgentRunsFTSIndex(db_path=temp_db_path)
        index.build_index(temp_log_dir)

        # Search for Chinese content
        results = index.search("中山市", limit=10)
        assert len(results) >= 1
        assert "中山市" in results[0]["query"] or "中山市" in results[0]["response_preview"]

        # Search for VOCs (mixed Chinese-English content)
        results = index.search("VOCs组分", limit=10)
        assert len(results) >= 1

    def test_english_search(self, temp_db_path, temp_log_dir):
        """Test English search using unicode61 tokenizer"""
        from app.tools.social.session_search.fts_index import AgentRunsFTSIndex

        index = AgentRunsFTSIndex(db_path=temp_db_path)
        index.build_index(temp_log_dir)

        # Search for English content
        results = index.search("pollution", limit=10)
        assert len(results) >= 1
        assert "pollution" in results[0]["query"].lower()

    def test_empty_results(self, temp_db_path, temp_log_dir):
        """Test search with no matching results"""
        from app.tools.social.session_search.fts_index import AgentRunsFTSIndex

        index = AgentRunsFTSIndex(db_path=temp_db_path)
        index.build_index(temp_log_dir)

        # Search for non-existent content
        results = index.search("不存在的内容xyz123", limit=10)
        assert len(results) == 0

    def test_add_record(self, temp_db_path):
        """Test adding a single record to index"""
        from app.tools.social.session_search.fts_index import AgentRunsFTSIndex

        index = AgentRunsFTSIndex(db_path=temp_db_path)
        index.initialize_schema()

        new_record = {
            "run_id": "test_new_001",
            "session_id": "session_new_001",
            "query": "新添加的测试记录",
            "final_answer_preview": "这是一条新添加的测试记录。",
            "start_time": "2026-03-18T15:00:00",
            "status": "completed",
            "stats": {"duration_ms": 500}
        }

        index.add_record(new_record)

        results = index.search("新添加", limit=10)
        assert len(results) == 1
        assert results[0]["run_id"] == "test_new_001"

    def test_social_search_is_scoped_by_owner(self, temp_db_path):
        """Social session search only returns records for the current owner."""
        from app.tools.social.session_search.fts_index import AgentRunsFTSIndex

        index = AgentRunsFTSIndex(db_path=temp_db_path)
        index.initialize_schema()

        index.add_record(
            {
                "run_id": "social_a_001",
                "session_id": "session_a",
                "query": "问号怎么回复",
                "final_answer_preview": "A用户的问号回复策略。",
                "start_time": "2026-06-04T10:00:00",
                "status": "completed",
                "stats": {"duration_ms": 100},
            },
            owner_type="social",
            owner_id="user_a",
        )
        index.add_record(
            {
                "run_id": "social_b_001",
                "session_id": "session_b",
                "query": "问号怎么回复",
                "final_answer_preview": "B用户的问号回复策略。",
                "start_time": "2026-06-04T11:00:00",
                "status": "completed",
                "stats": {"duration_ms": 100},
            },
            owner_type="social",
            owner_id="user_b",
        )

        results = index.search("问号", limit=10, owner_type="social", owner_id="user_a")

        assert [result["run_id"] for result in results] == ["social_a_001"]

    def test_social_incremental_index_is_idempotent_by_run_id(self, temp_db_path):
        """Indexing the same social run twice updates instead of duplicating."""
        from app.tools.social.session_search.fts_index import AgentRunsFTSIndex

        index = AgentRunsFTSIndex(db_path=temp_db_path)
        index.initialize_schema()

        record = {
            "run_id": "social_a_002",
            "session_id": "session_a",
            "query": "增量入库测试",
            "final_answer_preview": "第一次回复。",
            "start_time": "2026-06-04T12:00:00",
            "status": "completed",
            "stats": {"duration_ms": 100},
        }

        index.add_record(record, owner_type="social", owner_id="user_a")
        record["final_answer_preview"] = "第二次回复。"
        index.add_record(record, owner_type="social", owner_id="user_a")

        results = index.search("增量入库测试", limit=10, owner_type="social", owner_id="user_a")

        assert len(results) == 1
        assert results[0]["run_id"] == "social_a_002"
        assert results[0]["response_preview"] == "第二次回复。"


class TestSessionSearchTool:
    """Test SessionSearchTool"""

    @pytest.mark.asyncio
    async def test_basic_search(self, temp_db_path, temp_log_dir):
        """Test basic search functionality"""
        from app.tools.social.session_search.tool import SessionSearchTool
        from app.tools.social.session_search.fts_index import AgentRunsFTSIndex

        # Initialize index
        index = AgentRunsFTSIndex(db_path=temp_db_path)
        index.build_index(temp_log_dir)

        # Create tool with mocked index
        tool = SessionSearchTool()
        tool._fts_index = index

        result = await tool.execute(query="中山市", limit=5)

        assert result["success"] is True
        assert result["status"] == "success"
        assert result["count"] >= 1
        assert len(result["results"]) >= 1

    @pytest.mark.asyncio
    async def test_missing_query(self, temp_db_path):
        """Test with missing query parameter"""
        from app.tools.social.session_search.tool import SessionSearchTool

        tool = SessionSearchTool()
        result = await tool.execute(query="")

        assert result["success"] is False
        assert result["status"] == "failed"
        assert "缺少搜索关键词" in result["summary"]

    @pytest.mark.asyncio
    async def test_limit_clamping(self, temp_db_path, temp_log_dir):
        """Test that limit is properly clamped"""
        from app.tools.social.session_search.tool import SessionSearchTool
        from app.tools.social.session_search.fts_index import AgentRunsFTSIndex

        index = AgentRunsFTSIndex(db_path=temp_db_path)
        index.build_index(temp_log_dir)

        tool = SessionSearchTool()
        tool._fts_index = index

        # Test maximum limit
        result = await tool.execute(query="空气", limit=100)
        assert result["success"] is True

        # Test minimum limit
        result = await tool.execute(query="空气", limit=0)
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_social_tool_search_uses_context_owner(self, temp_db_path):
        """Social mode tool searches only the current user scope."""
        from app.tools.social.session_search.tool import SessionSearchTool
        from app.tools.social.session_search.fts_index import AgentRunsFTSIndex

        index = AgentRunsFTSIndex(db_path=temp_db_path)
        index.initialize_schema()
        index.add_record(
            {
                "run_id": "tool_social_a",
                "session_id": "session_a",
                "query": "问号",
                "final_answer_preview": "A用户结果",
                "start_time": "2026-06-04T10:00:00",
                "status": "completed",
                "stats": {"duration_ms": 100},
            },
            owner_type="social",
            owner_id="user_a",
        )
        index.add_record(
            {
                "run_id": "tool_social_b",
                "session_id": "session_b",
                "query": "问号",
                "final_answer_preview": "B用户结果",
                "start_time": "2026-06-04T11:00:00",
                "status": "completed",
                "stats": {"duration_ms": 100},
            },
            owner_type="social",
            owner_id="user_b",
        )

        tool = SessionSearchTool()
        tool._fts_index = index
        context = SimpleNamespace(runtime_mode="social", user_identifier="user_a")

        result = await tool.execute(context, query="问号", limit=5)

        assert result["success"] is True
        assert result["data"]["results"][0]["run_id"] == "tool_social_a"
        assert result["data"]["count"] == 1

    @pytest.mark.asyncio
    async def test_social_tool_search_logs_owner_scope(self, temp_db_path, monkeypatch):
        """Search logs include social owner scope for diagnostics."""
        import app.tools.social.session_search.tool as session_search_tool
        from app.tools.social.session_search.tool import SessionSearchTool
        from app.tools.social.session_search.fts_index import AgentRunsFTSIndex

        index = AgentRunsFTSIndex(db_path=temp_db_path)
        index.initialize_schema()
        index.add_record(
            {
                "run_id": "tool_social_log",
                "session_id": "session_log",
                "query": "日志检索",
                "final_answer_preview": "日志 owner 字段。",
                "start_time": "2026-06-04T10:00:00",
                "status": "completed",
                "stats": {"duration_ms": 100},
            },
            owner_type="social",
            owner_id="user_log",
        )

        tool = SessionSearchTool()
        tool._fts_index = index
        context = SimpleNamespace(runtime_mode="social", user_identifier="user_log")
        logged_events = []

        class FakeLogger:
            def info(self, event, **kwargs):
                logged_events.append((event, kwargs))

            def error(self, *args, **kwargs):
                pass

        monkeypatch.setattr(session_search_tool, "logger", FakeLogger())

        await tool.execute(context, query="日志", limit=5)

        matching_events = [
            fields for event, fields in logged_events if event == "session_searched"
        ]
        assert matching_events
        assert matching_events[-1]["owner_type"] == "social"
        assert matching_events[-1]["owner_id"] == "user_log"
        assert matching_events[-1]["runtime_mode"] == "social"

    @pytest.mark.asyncio
    async def test_social_tool_search_requires_user_identifier(self, temp_db_path):
        """Social mode search fails closed when no user identifier is available."""
        from app.tools.social.session_search.tool import SessionSearchTool
        from app.tools.social.session_search.fts_index import AgentRunsFTSIndex

        index = AgentRunsFTSIndex(db_path=temp_db_path)
        index.initialize_schema()

        tool = SessionSearchTool()
        tool._fts_index = index
        context = SimpleNamespace(runtime_mode="social", user_identifier=None)

        result = await tool.execute(context, query="问号", limit=5)

        assert result["success"] is False
        assert result["status"] == "failed"
        assert "用户标识" in result["summary"]


class TestSocialSessionIndexing:
    """Test automatic indexing for newly completed social runs."""

    def test_agent_logger_indexes_completed_social_run(self, tmp_path, temp_db_path, monkeypatch):
        from app.tools.social.session_search.fts_index import AgentRunsFTSIndex
        from app.utils.agent_logger import AgentLogger

        index = AgentRunsFTSIndex(db_path=temp_db_path)
        index.initialize_schema()
        monkeypatch.setattr(
            "app.tools.social.session_search.fts_index.get_fts_index",
            lambda: index,
        )

        logger = AgentLogger(log_dir=str(tmp_path / "agent_runs"))
        logger.start_new_run(
            session_id="session_a",
            query="新的问号会话",
            metadata={
                "runtime_mode": "social",
                "user_identifier": "user_a",
            },
        )
        logger.end_run(status="completed", response="这是新的社交用户回复。")

        results = index.search("问号", limit=5, owner_type="social", owner_id="user_a")

        assert len(results) == 1
        assert results[0]["session_id"] == "session_a"
        assert results[0]["response_preview"] == "这是新的社交用户回复。"


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v"])
