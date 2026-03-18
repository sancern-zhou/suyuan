"""Snapshot Generation System

Provides intelligent page snapshot generation with multiple formats:
- AI Format: LLM-optimized text representation with role-based refs
- ARIA Format: ARIA attribute-based snapshot
- Text Format: Plain text snapshot (backward compatible)
"""

from .generator import SnapshotGenerator

__all__ = ["SnapshotGenerator"]
