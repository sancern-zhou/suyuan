"""Global singleton for SubagentManager.

Provides tool-level access to the SubagentManager instance.
"""

from typing import Optional

from app.social.subagent_manager import SubagentManager

# Global singleton instance
_subagent_manager: Optional[SubagentManager] = None


def set_subagent_manager(manager: SubagentManager) -> None:
    """
    Set the global SubagentManager instance.

    Args:
        manager: SubagentManager instance
    """
    global _subagent_manager
    _subagent_manager = manager


def get_subagent_manager() -> Optional[SubagentManager]:
    """
    Get the global SubagentManager instance.

    Returns:
        SubagentManager instance or None if not set
    """
    return _subagent_manager
