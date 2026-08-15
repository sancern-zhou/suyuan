from app.api.agent import _append_attachment_text_for_history
from app.api.agent import AgentAnalyzeRequest, AgentQueryRequest
from pydantic import ValidationError
import pytest


def test_append_attachment_text_for_history_includes_attachment_paths():
    content = _append_attachment_text_for_history(
        "请分析这个文件",
        [
            {
                "type": "image",
                "name": "现场照片.png",
                "url": "/api/upload/file_1",
            },
            {
                "type": "file",
                "name": "数据表.xlsx",
                "local_path": "/tmp/uploads/data.xlsx",
                "url": "/api/upload/file_2",
            },
        ],
    )

    assert content.startswith("请分析这个文件")
    assert "**用户上传的附件**" in content
    assert "图片: 现场照片.png" in content
    assert "路径: /api/upload/file_1" in content
    assert "文件: 数据表.xlsx" in content
    assert "路径: /tmp/uploads/data.xlsx" in content


def test_append_attachment_text_for_history_returns_query_without_attachments():
    assert _append_attachment_text_for_history("继续", None) == "继续"


def test_agent_requests_accept_expanded_iteration_limit():
    analyze_request = AgentAnalyzeRequest(query="继续复杂分析", max_iterations=120)
    query_request = AgentQueryRequest(query="继续复杂分析", max_iterations=120)

    assert analyze_request.max_iterations == 120
    assert query_request.max_iterations == 120


def test_agent_requests_reject_iterations_above_safety_cap():
    with pytest.raises(ValidationError):
        AgentAnalyzeRequest(query="继续复杂分析", max_iterations=201)

    with pytest.raises(ValidationError):
        AgentQueryRequest(query="继续复杂分析", max_iterations=201)
