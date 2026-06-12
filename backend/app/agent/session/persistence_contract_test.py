from dataclasses import dataclass

from app.agent.react_agent import ReActAgent
from app.agent.session.conversation_persistence import ConversationPersistenceService
from app.agent.session.models import Session


def _messages(count: int, *, final_content: str = "old final"):
    messages = [
        {
            "type": "user",
            "content": f"message {index}",
            "timestamp": f"2026-06-04T00:00:{index:02d}",
        }
        for index in range(count - 1)
    ]
    messages.append(
        {
            "type": "final",
            "content": final_content,
            "timestamp": "2026-06-04T00:01:00",
        }
    )
    return messages


def test_complete_conversation_persistence_uses_display_history_as_truth():
    session = Session(
        session_id="assistant_session_existing",
        query="old query",
        conversation_history=_messages(
            62,
            final_content="分析任务较复杂，在限定步骤内未完成，是否继续？",
        ),
    )
    complete_history = _messages(74, final_content="这是新的截图回复")

    ConversationPersistenceService().apply_complete(
        session,
        display_history=complete_history,
        collected_data_ids=["data_a", "data_a", "data_b"],
        collected_visuals=[{"id": "visual_a"}, {"id": "visual_b"}, {"title": "legacy"}],
        office_documents=[{"file_path": "/tmp/report.docx"}],
    )

    assert len(session.conversation_history) == 74
    assert session.conversation_history[-1]["content"] == "这是新的截图回复"
    assert session.data_ids == ["data_a", "data_b"]
    assert session.visual_ids == ["visual_a", "visual_b"]
    assert session.office_documents == [{"file_path": "/tmp/report.docx"}]
    assert session.metadata["visualizations"] == [
        {"id": "visual_a"},
        {"id": "visual_b"},
        {"title": "legacy"},
    ]


def test_capture_office_document_updates_existing_report_preview():
    agent = ReActAgent.__new__(ReActAgent)
    agent._session_store = {}
    session_id = "assistant_session_existing"
    file_path = "/tmp/reports/ops_audit/report.qmd"

    agent._capture_office_document(
        session_id,
        {
            "type": "office_document",
            "data": {
                "file_path": file_path,
                "file_type": "report",
                "generator": "create_report_package",
                "html_preview": {
                    "html_id": "ops_audit",
                    "html_url": "/api/reports/ops_audit/html",
                    "file_type": "report",
                    "preview_version": "old",
                },
            },
        },
    )
    agent._capture_office_document(
        session_id,
        {
            "type": "office_document",
            "data": {
                "file_path": file_path,
                "file_type": "report",
                "generator": "edit_file",
                "html_preview": {
                    "html_id": "ops_audit",
                    "html_url": "/api/reports/ops_audit/html",
                    "file_type": "report",
                    "preview_version": "new",
                },
            },
        },
    )

    office_documents = agent._session_store[session_id]["office_documents"]
    assert len(office_documents) == 1
    assert office_documents[0]["generator"] == "edit_file"
    assert office_documents[0]["html_preview"]["preview_version"] == "new"


def test_capture_office_document_preserves_html_artifact_related_files():
    agent = ReActAgent.__new__(ReActAgent)
    agent._session_store = {}
    session_id = "assistant_session_diagram"
    related_files = [
        {
            "path": "/tmp/html_artifacts/diagram/assets/diagram.drawio",
            "relative_path": "assets/diagram.drawio",
            "url": "/api/html-artifacts/diagram/assets/diagram.drawio",
            "format": "drawio",
        },
        {
            "path": "/tmp/html_artifacts/diagram/assets/diagram.drawio.svg",
            "relative_path": "assets/diagram.drawio.svg",
            "url": "/api/html-artifacts/diagram/assets/diagram.drawio.svg",
            "format": "drawio_svg",
        },
    ]

    agent._capture_office_document(
        session_id,
        {
            "type": "html_document",
            "data": {
                "file_path": "/tmp/html_artifacts/diagram/index.html",
                "file_type": "html_artifact",
                "generator": "create_diagram_artifact",
                "html_preview": {
                    "html_id": "diagram",
                    "html_url": "/api/html-artifacts/diagram/html",
                    "file_type": "html_artifact",
                },
                "related_files": related_files,
                "artifacts": [{"format": "png", "file_path": "/tmp/html_artifacts/diagram/assets/diagram.png"}],
            },
        },
    )

    office_documents = agent._session_store[session_id]["office_documents"]
    assert office_documents[0]["related_files"] == related_files
    assert office_documents[0]["artifacts"][0]["format"] == "png"


def test_capture_office_document_preserves_svg_preview_for_diagram():
    agent = ReActAgent.__new__(ReActAgent)
    agent._session_store = {}
    session_id = "assistant_session_diagram_svg"
    svg_preview = {
        "svg_path": "/tmp/html_artifacts/diagram/assets/diagram.drawio.svg",
        "svg_url": "/api/html-artifacts/diagram/assets/diagram.drawio.svg",
        "file_type": "drawio_svg",
        "format": "drawio_svg",
    }

    agent._capture_office_document(
        session_id,
        {
            "type": "office_document",
            "data": {
                "file_path": "/tmp/html_artifacts/diagram/assets/diagram.drawio",
                "file_type": "drawio",
                "generator": "create_diagram_artifact",
                "svg_preview": svg_preview,
            },
        },
    )

    office_documents = agent._session_store[session_id]["office_documents"]
    assert office_documents[0]["svg_preview"] == svg_preview
    assert office_documents[0]["file_type"] == "drawio"


def test_terminal_persistence_preserves_display_history_and_adds_status():
    session = Session(
        session_id="assistant_session_existing",
        query="old query",
        conversation_history=_messages(10, final_content="old final"),
    )
    display_history = _messages(15, final_content="last visible answer")
    terminal_message = {
        "type": "interrupted",
        "content": "用户已暂停本轮分析",
        "timestamp": "2026-06-04T00:03:00",
    }

    ConversationPersistenceService().apply_terminal(
        session,
        display_history=display_history,
        terminal_message=terminal_message,
        collected_data_ids=["data_a"],
        collected_visuals=[{"id": "visual_a"}],
    )

    assert len(session.conversation_history) == 16
    assert session.conversation_history[:15] == display_history
    assert session.conversation_history[-1] == terminal_message
    assert session.data_ids == ["data_a"]
    assert session.visual_ids == ["visual_a"]


@dataclass
class _Turn:
    role: str
    content: str
    timestamp: str
    type: str | None = None
    thought: str | None = None
    data: dict | None = None
    tool_use_id: str | None = None
    is_error: bool | None = None


class _MemorySession:
    def __init__(self, count: int):
        self.conversation_history = [
            _Turn(
                role="user",
                content=f"runtime message {index}",
                timestamp=f"2026-06-04T00:02:{index:02d}",
                type="user",
            )
            for index in range(count)
        ]


class _MemoryManager:
    def __init__(self, count: int):
        self.session = _MemorySession(count)


def test_agent_metadata_persistence_does_not_shrink_existing_db_history():
    session = Session(
        session_id="assistant_session_existing",
        query="old query",
        conversation_history=_messages(62, final_content="old final"),
    )
    entry = {
        "memory": _MemoryManager(38),
        "collected_data_ids": ["data_a"],
        "collected_visuals": [{"id": "visual_a"}],
    }

    ReActAgent._apply_session_store_entry_for_persistence(session, entry)

    assert len(session.conversation_history) == 62
    assert session.conversation_history[-1]["content"] == "old final"
    assert session.data_ids == ["data_a"]
    assert session.visual_ids == ["visual_a"]


def test_agent_metadata_persistence_does_not_overwrite_existing_db_history_with_longer_runtime():
    session = Session(
        session_id="assistant_session_existing",
        query="old query",
        conversation_history=_messages(62, final_content="old final"),
    )
    entry = {
        "memory": _MemoryManager(80),
        "collected_data_ids": ["data_a"],
    }

    ReActAgent._apply_session_store_entry_for_persistence(session, entry)

    assert len(session.conversation_history) == 62
    assert session.conversation_history[-1]["content"] == "old final"
    assert session.data_ids == ["data_a"]


def test_agent_does_not_overwrite_route_persisted_display_history():
    session = Session(
        session_id="assistant_session_existing",
        query="old query",
        conversation_history=_messages(74, final_content="route final"),
    )
    entry = {
        "memory": _MemoryManager(80),
        "display_history_persisted": True,
    }

    ReActAgent._apply_session_store_entry_for_persistence(session, entry)

    assert len(session.conversation_history) == 74
    assert session.conversation_history[-1]["content"] == "route final"
