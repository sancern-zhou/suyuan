"""Cross-source conversation ownership API."""

from .dependencies import get_conversation_catalog
from .schemas import ConversationCatalogRecord, ConversationSource
from .service import ConversationCatalogService

__all__ = [
    "ConversationCatalogRecord",
    "ConversationCatalogService",
    "ConversationSource",
    "get_conversation_catalog",
]
