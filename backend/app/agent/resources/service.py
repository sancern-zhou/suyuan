"""Mode-independent access to the canonical session resource manifest."""
from __future__ import annotations

from pydantic import BaseModel, Field

from .models import SessionResourceRef


class SessionResourceManifest(BaseModel):
    session_id: str
    refs: list[SessionResourceRef] = Field(default_factory=list)
    version: int = Field(default=0, ge=0)


class ManifestPersistenceError(RuntimeError):
    """Raised when canonical manifest durability could not be guaranteed."""


class SessionResourceManifestService:
    def __init__(self, repository) -> None:
        self.repository = repository

    @staticmethod
    def _validate_session_id(session_id: str) -> str:
        if not isinstance(session_id, str) or not session_id.strip():
            raise ValueError("session_id must be a non-empty string")
        if len(session_id) > 255:
            raise ValueError("session_id exceeds 255 characters")
        return session_id

    async def load(self, session_id: str) -> SessionResourceManifest:
        session_id = self._validate_session_id(session_id)
        try:
            return SessionResourceManifest.model_validate(await self.repository.load(session_id))
        except ManifestPersistenceError:
            raise
        except Exception as exc:
            raise ManifestPersistenceError(f"failed to load session resource manifest: {exc}") from exc

    async def merge(
        self, session_id: str, incoming: list[SessionResourceRef]
    ) -> SessionResourceManifest:
        session_id = self._validate_session_id(session_id)
        validated = [SessionResourceRef.model_validate(ref) for ref in incoming]
        try:
            return SessionResourceManifest.model_validate(
                await self.repository.merge(session_id, validated)
            )
        except ManifestPersistenceError:
            raise
        except Exception as exc:
            raise ManifestPersistenceError(f"failed to merge session resource manifest: {exc}") from exc

    async def delete(self, session_id: str) -> bool:
        session_id = self._validate_session_id(session_id)
        try:
            return bool(await self.repository.delete(session_id))
        except ManifestPersistenceError:
            raise
        except Exception as exc:
            raise ManifestPersistenceError(f"failed to delete session resource manifest: {exc}") from exc


_default_service: SessionResourceManifestService | None = None


def get_session_resource_manifest_service() -> SessionResourceManifestService:
    global _default_service
    if _default_service is None:
        from app.db.session_resource_repository import SessionResourceRepository

        _default_service = SessionResourceManifestService(SessionResourceRepository())
    return _default_service
