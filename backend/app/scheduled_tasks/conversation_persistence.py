"""Persist scheduled Agent runs, then publish them as web conversations."""

from app.agent.session import Session, get_session_manager
from app.agent.session.conversation_persistence import ConversationPersistenceService
from app.conversations.dependencies import get_conversation_catalog
from app.conversations.schemas import ConversationSource

from .models import ScheduledTask, TaskExecution


class ScheduledTaskConversationPersistence:
    """Keep transcript storage private until a scheduled execution is terminal."""

    def __init__(self, session_manager=None, catalog=None):
        self.session_manager = session_manager or get_session_manager()
        self.catalog = catalog or get_conversation_catalog()
        self.transcript_persistence = ConversationPersistenceService()

    async def persist_agent_session(
        self,
        *,
        agent,
        task: ScheduledTask,
        execution: TaskExecution,
        display_history: list[dict],
    ) -> bool:
        export = getattr(agent, "export_runtime_session", None)
        if not callable(export):
            return False

        session = export(
            execution.session_id,
            query=task.description,
            mode=task.execution_mode,
        )
        if session is None:
            return False

        session.created_at = execution.started_at
        session.metadata.update({
            "mode": task.execution_mode,
            "scheduled_task_id": task.task_id,
            "scheduled_execution_id": execution.execution_id,
            "scheduled_task_name": task.name,
        })

        existing = await self.session_manager.load_session(session.session_id)
        if existing is not None:
            session.created_at = existing.created_at
            session.conversation_history = list(existing.conversation_history)
            self.transcript_persistence.append_complete(
                session,
                display_history=display_history,
                collected_visuals=session.metadata.get("visualizations", []),
                office_documents=session.office_documents,
            )
        else:
            self.transcript_persistence.apply_complete(
                session,
                display_history=display_history,
                collected_visuals=session.metadata.get("visualizations", []),
                office_documents=session.office_documents,
            )

        saved = await self.session_manager.save_session(session)
        if not saved:
            raise RuntimeError("scheduled_session_persistence_failed")

        persisted = await self.session_manager.load_session(session.session_id)
        if persisted is None or not self._same_transcript(
            session.conversation_history,
            persisted.conversation_history,
        ):
            raise RuntimeError("scheduled_session_transcript_verification_failed")

        return True

    async def publish_conversation(
        self,
        *,
        task: ScheduledTask,
        execution: TaskExecution,
    ) -> bool:
        """Expose a fully persisted terminal execution through the catalog."""
        if not execution.session_id:
            raise RuntimeError("scheduled_session_id_missing")
        if await self.session_manager.load_session(execution.session_id) is None:
            raise RuntimeError("scheduled_session_not_persisted")

        try:
            await self.catalog.register_identity(
                session_id=execution.session_id,
                owner_user_id=task.owner_user_id,
                owner_username=task.owner_username,
                owner_display_name=task.owner_display_name,
                source=ConversationSource.WEB,
                mode=task.execution_mode,
                title=task.name,
                read_only_on_web=False,
            )
        except Exception:
            # register_identity may commit successfully and fail while reading
            # the committed row back. Resolve that ambiguous outcome before
            # reporting a publication failure.
            record = await self.catalog.find(execution.session_id)
            if (
                record is not None
                and record.owner_user_id == task.owner_user_id
                and record.source == ConversationSource.WEB
            ):
                return True
            raise

        return True

    async def ensure_terminal_session(
        self,
        *,
        task: ScheduledTask,
        execution: TaskExecution,
    ) -> bool:
        """Create a recoverable fallback when Agent runtime export is unavailable."""
        if not execution.session_id:
            raise RuntimeError("scheduled_session_id_missing")
        if await self.session_manager.load_session(execution.session_id) is not None:
            return True

        history: list[dict] = []
        for step in execution.steps:
            if step.agent_prompt:
                history.append({"type": "user", "content": step.agent_prompt})
            if step.agent_response:
                history.append({
                    "type": "final",
                    "role": "assistant",
                    "content": step.agent_response,
                    "data": {"answer": step.agent_response},
                })
            elif step.error_message:
                history.append({"type": "error", "content": step.error_message})

        if not history:
            history = [
                {"type": "user", "content": task.description},
                {
                    "type": "error" if execution.error_message else "final",
                    "role": "assistant",
                    "content": execution.error_message or "定时任务执行完成（无执行步骤）",
                },
            ]

        session = Session(
            session_id=execution.session_id,
            query=task.description,
            created_at=execution.started_at,
            conversation_history=history,
            metadata={
                "mode": task.execution_mode,
                "scheduled_task_id": task.task_id,
                "scheduled_execution_id": execution.execution_id,
                "scheduled_task_name": task.name,
            },
        )
        if not await self.session_manager.save_session(session):
            raise RuntimeError("scheduled_terminal_session_persistence_failed")
        persisted = await self.session_manager.load_session(session.session_id)
        if persisted is None or not self._same_transcript(history, persisted.conversation_history):
            raise RuntimeError("scheduled_terminal_transcript_verification_failed")
        return True

    @staticmethod
    def _same_transcript(expected: list[dict], actual: list[dict]) -> bool:
        if len(expected) != len(actual):
            return False

        def stable(message: dict) -> tuple:
            return (
                message.get("type"),
                message.get("content"),
            )

        return all(stable(left) == stable(right) for left, right in zip(expected, actual))
