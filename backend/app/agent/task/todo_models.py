"""
Todo Models - Simple task management system

Replaces the complex Task system with a simple 2-field Todo approach:
- content: Task description
- status: pending | in_progress | completed

Design principles:
- Complete replacement mode (not incremental)
- Max 20 items constraint
- Only one in_progress at a time
- Simple text rendering output
"""

from typing import List, Dict, Optional
from enum import Enum
import structlog

logger = structlog.get_logger()


class TodoStatus(str, Enum):
    """Todo status enumeration"""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"


class TodoItem:
    """Single todo item"""

    def __init__(self, content: str, status: TodoStatus):
        """
        Initialize a todo item

        Args:
            content: Task description
            status: Task status
        """
        if not content or not content.strip():
            raise ValueError("content cannot be empty")

        self.content = content.strip()
        self.status = status

    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return {
            "content": self.content,
            "status": self.status.value
        }

    @classmethod
    def from_dict(cls, data: Dict) -> 'TodoItem':
        """Create from dictionary"""
        return cls(
            content=data["content"],
            status=TodoStatus(data["status"])
        )


class TodoList:
    """Todo list manager with simple replacement mode"""

    MAX_ITEMS = 20

    def __init__(self):
        """Initialize todo list"""
        self.items: List[TodoItem] = []

    def update(self, items_data: List[Dict]) -> str:
        """
        Validate and update the entire todo list (complete replacement mode)

        Args:
            items_data: List of todo item dictionaries

        Returns:
            Rendered text output

        Raises:
            ValueError: If validation fails
        """
        # Validate max items
        if len(items_data) > self.MAX_ITEMS:
            raise ValueError(f"Too many items. Maximum {self.MAX_ITEMS} items allowed, got {len(items_data)}")

        # Validate required fields
        for idx, item_data in enumerate(items_data):
            if "content" not in item_data:
                raise ValueError(f"Item {idx}: missing 'content' field")
            if "status" not in item_data:
                raise ValueError(f"Item {idx}: missing 'status' field")

            # Validate status value
            status_str = item_data["status"]
            if status_str not in [s.value for s in TodoStatus]:
                raise ValueError(
                    f"Item {idx}: invalid status '{status_str}'. "
                    f"Must be one of: pending, in_progress, completed"
                )

        # Convert to TodoItem objects
        new_items = []
        for item_data in items_data:
            new_items.append(TodoItem.from_dict(item_data))

        # Validate constraint: only one in_progress at a time
        in_progress_count = sum(1 for item in new_items if item.status == TodoStatus.IN_PROGRESS)
        if in_progress_count > 1:
            raise ValueError(
                f"Only one task can be in_progress at a time. "
                f"Found {in_progress_count} tasks with in_progress status"
            )

        # Replace entire list
        self.items = new_items

        logger.info(
            "todo_list_updated",
            total_items=len(self.items),
            in_progress=in_progress_count,
            completed=sum(1 for i in self.items if i.status == TodoStatus.COMPLETED)
        )

        # Return rendered text
        return self.render()

    def render(self) -> str:
        """
        Render todo list as readable text

        Format:
            [x] Completed task
            [>] In progress task
            [ ] Pending task

            (1/3 completed)
        """
        if not self.items:
            return "No tasks"

        lines = []

        # Separate by status
        completed = [i for i in self.items if i.status == TodoStatus.COMPLETED]
        in_progress = [i for i in self.items if i.status == TodoStatus.IN_PROGRESS]
        pending = [i for i in self.items if i.status == TodoStatus.PENDING]

        # Render completed first
        for item in completed:
            lines.append(f"[x] {item.content}")

        # Render in progress
        for item in in_progress:
            lines.append(f"[>] {item.content}")

        # Render pending
        for item in pending:
            lines.append(f"[ ] {item.content}")

        # Add summary
        total = len(self.items)
        completed_count = len(completed)
        lines.append(f"\n({completed_count}/{total} completed)")

        return "\n".join(lines)

    def get_items(self) -> List[TodoItem]:
        """Get all todo items"""
        return self.items.copy()

    def clear(self):
        """Clear all items"""
        self.items = []
        logger.info("todo_list_cleared")

    def to_dict_list(self) -> List[Dict]:
        """Convert to list of dictionaries for persistence"""
        return [item.to_dict() for item in self.items]
