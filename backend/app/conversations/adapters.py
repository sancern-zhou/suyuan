"""Read adapters for conversation stores with different schemas."""

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.agent.session import get_session_manager
from app.db.database import async_session
from app.knowledge_base.models import ConversationSession
from app.agent.session.session_resolver import load_session_for_mode

from .schemas import ConversationCatalogRecord, ConversationSource


def knowledge_session_to_payload(session, row: ConversationCatalogRecord) -> dict:
    messages = []
    for turn in session.turns or []:
        message = {
            "type": "user" if turn.role == "user" else "final",
            "role": turn.role,
            "content": turn.content,
            "timestamp": turn.created_at.isoformat() if turn.created_at else None,
        }
        if turn.sources:
            message["data"] = {
                "sources": turn.sources,
                "sources_count": turn.sources_count,
            }
        messages.append(message)

    return {
        "session_id": session.id,
        "query": session.title,
        "created_at": session.created_at.isoformat() if session.created_at else None,
        "updated_at": session.updated_at.isoformat() if session.updated_at else None,
        "conversation_history": messages,
        "execution_context": {},
        "data_ids": [],
        "visual_ids": [],
        "office_documents": [],
        "metadata": {"mode": "knowledge_qa"},
        "error": None,
        "has_more_messages": False,
        "total_message_count": len(messages),
        "oldest_sequence": 0 if messages else None,
        **row.model_dump(mode="json"),
    }


class WebConversationAdapter:
    async def get(self, row: ConversationCatalogRecord) -> dict | None:
        session = await get_session_manager().get_session(row.session_id)
        if not session:
            return None
        return {**session.model_dump(mode="json"), **row.model_dump(mode="json")}

    async def restore(
        self,
        row: ConversationCatalogRecord,
        *,
        message_limit: int,
        lazy_artifacts: bool,
    ):
        return await get_session_manager().load_session_with_pagination(
            row.session_id,
            message_limit,
            include_artifacts=not lazy_artifacts,
        )

    async def delete(self, row: ConversationCatalogRecord) -> bool:
        return await get_session_manager().delete_session(row.session_id)


class KnowledgeQAConversationAdapter:
    async def _load(self, session_id: str):
        async with async_session() as db:
            statement = (
                select(ConversationSession)
                .where(ConversationSession.id == session_id)
                .options(selectinload(ConversationSession.turns))
            )
            return (await db.execute(statement)).scalar_one_or_none()

    async def get(self, row: ConversationCatalogRecord) -> dict | None:
        session = await self._load(row.session_id)
        return knowledge_session_to_payload(session, row) if session else None

    async def restore(
        self,
        row: ConversationCatalogRecord,
        *,
        message_limit: int,
        lazy_artifacts: bool,
    ):
        session = await self._load(row.session_id)
        if not session:
            return None
        payload = knowledge_session_to_payload(session, row)
        if message_limit > 0:
            payload["conversation_history"] = payload["conversation_history"][
                -message_limit:
            ]
        return {"normalized_session": payload}

    async def delete(self, row: ConversationCatalogRecord) -> bool:
        async with async_session() as db:
            session = await db.get(ConversationSession, row.session_id)
            if session is None:
                return False
            await db.delete(session)
            await db.commit()
            return True


class SocialConversationAdapter:
    """Read-only adapter for file-backed social transcripts."""

    async def _load(self, session_id: str):
        return await load_session_for_mode(session_id, mode="social")

    @staticmethod
    def _payload(session, row: ConversationCatalogRecord, message_limit: int | None = None):
        payload = session.model_dump(mode="json")
        all_messages = list(payload.get("conversation_history") or [])
        messages = all_messages[-message_limit:] if message_limit and message_limit > 0 else all_messages
        payload.update(row.model_dump(mode="json"))
        payload["conversation_history"] = messages
        payload["source"] = ConversationSource.SOCIAL.value
        payload["read_only_on_web"] = True
        payload["has_more_messages"] = len(all_messages) > len(messages)
        payload["total_message_count"] = len(all_messages)
        payload["oldest_sequence"] = None
        payload["has_lazy_visualizations"] = False
        payload["has_lazy_office_documents"] = False
        payload["has_lazy_drawio_board"] = False
        return payload

    async def get(self, row: ConversationCatalogRecord) -> dict | None:
        session = await self._load(row.session_id)
        return self._payload(session, row) if session else None

    async def restore(
        self,
        row: ConversationCatalogRecord,
        *,
        message_limit: int,
        lazy_artifacts: bool,
    ):
        session = await self._load(row.session_id)
        if not session:
            return None
        return {"normalized_session": self._payload(session, row, message_limit)}


class ConversationAdapterRegistry:
    def __init__(self):
        self._adapters = {
            ConversationSource.WEB: WebConversationAdapter(),
            ConversationSource.KNOWLEDGE_QA: KnowledgeQAConversationAdapter(),
            ConversationSource.SOCIAL: SocialConversationAdapter(),
        }

    def get(self, source: ConversationSource):
        adapter = self._adapters.get(source)
        if adapter is None:
            raise RuntimeError(f"unsupported_conversation_source:{source.value}")
        return adapter


_registry = ConversationAdapterRegistry()


def get_conversation_adapters() -> ConversationAdapterRegistry:
    return _registry
