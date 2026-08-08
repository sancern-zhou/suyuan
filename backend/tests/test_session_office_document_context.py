from app.agent.react_agent import ReActAgent


def test_session_office_document_context_uses_recent_documents_and_paths():
    documents = [
        {
            "file_name": f"old-{index}.pdf",
            "file_path": f"/tmp/old-{index}.pdf",
            "file_type": "pdf",
        }
        for index in range(8)
    ]
    documents.append(
        {
            "file_name": "磋商文件.pdf",
            "file_path": "/home/xckj/suyuan/backend/backend_data_registry/social/weixin/account/media/磋商文件.pdf",
            "file_type": "pdf",
            "summary": "成功读取 PDF 文档",
        }
    )

    context = ReActAgent._build_session_document_context(documents, max_documents=3)

    assert "当前会话可用文档" in context
    assert "磋商文件.pdf" in context
    assert "/home/xckj/suyuan/backend/backend_data_registry/social/weixin/account/media/磋商文件.pdf" in context
    assert "old-0.pdf" not in context
    assert "social/uploads" not in context


def test_trim_office_documents_deduplicates_by_file_path_and_keeps_recent():
    documents = [
        {"file_name": "a-v1.pdf", "file_path": "/tmp/a.pdf", "summary": "old"},
        {"file_name": "b.pdf", "file_path": "/tmp/b.pdf"},
        {"file_name": "a-v2.pdf", "file_path": "/tmp/a.pdf", "summary": "new"},
    ]

    trimmed = ReActAgent._trim_office_documents(documents, max_documents=2)

    assert trimmed == [
        {"file_name": "b.pdf", "file_path": "/tmp/b.pdf"},
        {"file_name": "a-v2.pdf", "file_path": "/tmp/a.pdf", "summary": "new"},
    ]
