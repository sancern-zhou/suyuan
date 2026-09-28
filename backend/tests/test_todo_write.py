"""
Tests for TodoWrite tool and TodoList models

Test scenarios:
1. Create task list
2. Update task status
3. Constraint validation (max 20 items, one in_progress)
4. Render output format
"""

import pytest
from app.agent.task.todo_models import TodoItem, TodoList, TodoStatus
from app.tools.task_management.todo_write import todo_write_tool


class TestTodoItem:
    """Test TodoItem model"""

    def test_create_todo_item(self):
        """Test creating a todo item"""
        item = TodoItem(
            content="读取Excel文件",
            status=TodoStatus.PENDING
        )
        assert item.content == "读取Excel文件"
        assert item.status == TodoStatus.PENDING

    def test_todo_item_to_dict(self):
        """Test converting todo item to dictionary"""
        item = TodoItem(
            content="分析数据",
            status=TodoStatus.IN_PROGRESS
        )
        data = item.to_dict()
        assert data["content"] == "分析数据"
        assert data["status"] == "in_progress"

    def test_todo_item_from_dict(self):
        """Test creating todo item from dictionary"""
        data = {
            "content": "生成报告",
            "status": "completed"
        }
        item = TodoItem.from_dict(data)
        assert item.content == "生成报告"
        assert item.status == TodoStatus.COMPLETED

    def test_empty_content_raises_error(self):
        """Test that empty content raises ValueError"""
        with pytest.raises(ValueError, match="content cannot be empty"):
            TodoItem(
                content="",
                status=TodoStatus.PENDING
            )


class TestTodoList:
    """Test TodoList model"""

    def test_create_todo_list(self):
        """Test creating an empty todo list"""
        todo_list = TodoList()
        assert len(todo_list.items) == 0

    def test_update_todo_list(self):
        """Test updating todo list"""
        todo_list = TodoList()
        items = [
            {
                "content": "读取Excel文件",
                "status": "completed"
            },
            {
                "content": "分析数据",
                "status": "in_progress"
            },
            {
                "content": "生成报告",
                "status": "pending"
            }
        ]
        rendered = todo_list.update(items)

        assert len(todo_list.items) == 3
        assert todo_list.items[0].status == TodoStatus.COMPLETED
        assert todo_list.items[1].status == TodoStatus.IN_PROGRESS
        assert todo_list.items[2].status == TodoStatus.PENDING

    def test_max_items_constraint(self):
        """Test that max items constraint is enforced"""
        todo_list = TodoList()
        items = [
            {
                "content": f"任务{i}",
                "status": "pending"
            }
            for i in range(21)  # 21 items,超过限制
        ]

        with pytest.raises(ValueError, match="Too many items"):
            todo_list.update(items)

    def test_one_in_progress_constraint(self):
        """Test that only one in_progress task is allowed"""
        todo_list = TodoList()
        items = [
            {
                "content": "任务1",
                "status": "in_progress"
            },
            {
                "content": "任务2",
                "status": "in_progress"
            }
        ]

        with pytest.raises(ValueError, match="Only one task can be in_progress"):
            todo_list.update(items)

    def test_missing_status_field_raises_error(self):
        """Test that missing status field raises error"""
        todo_list = TodoList()
        items = [
            {
                "content": "任务1"
                # Missing status
            }
        ]

        with pytest.raises(ValueError, match="missing 'status' field"):
            todo_list.update(items)

    def test_invalid_status_raises_error(self):
        """Test that invalid status raises error"""
        todo_list = TodoList()
        items = [
            {
                "content": "任务1",
                "status": "invalid_status"
            }
        ]

        with pytest.raises(ValueError, match="invalid status 'invalid_status'"):
            todo_list.update(items)

    def test_render_output(self):
        """Test render output format"""
        todo_list = TodoList()
        items = [
            {
                "content": "读取Excel文件",
                "status": "completed"
            },
            {
                "content": "分析数据",
                "status": "in_progress"
            },
            {
                "content": "生成报告",
                "status": "pending"
            }
        ]
        todo_list.update(items)
        rendered = todo_list.render()

        assert "[x] 读取Excel文件" in rendered
        assert "[>] 分析数据" in rendered
        assert "[ ] 生成报告" in rendered
        assert "(1/3 completed)" in rendered

    def test_render_empty_list(self):
        """Test rendering empty list"""
        todo_list = TodoList()
        rendered = todo_list.render()
        assert rendered == "No tasks"

    def test_get_items(self):
        """Test getting items"""
        todo_list = TodoList()
        items = [
            {
                "content": "任务1",
                "status": "pending"
            }
        ]
        todo_list.update(items)

        retrieved_items = todo_list.get_items()
        assert len(retrieved_items) == 1
        assert retrieved_items[0].content == "任务1"

    def test_clear(self):
        """Test clearing the list"""
        todo_list = TodoList()
        items = [
            {
                "content": "任务1",
                "status": "pending"
            }
        ]
        todo_list.update(items)
        assert len(todo_list.items) == 1

        todo_list.clear()
        assert len(todo_list.items) == 0


class TestTodoWriteTool:
    """Test TodoWrite tool"""

    @pytest.mark.asyncio
    async def test_tool_execution(self):
        """Test tool execution"""
        from app.agent.context.execution_context import ExecutionContext
        from app.agent.context.data_context_manager import DataContextManager
        from app.agent.memory.hybrid_manager import HybridMemoryManager

        # Create minimal dependencies
        memory_manager = HybridMemoryManager(session_id="test_session")
        data_manager = DataContextManager(memory_manager)
        todo_list = TodoList()

        # Create execution context
        context = ExecutionContext(
            session_id="test_session",
            iteration=1,
            data_manager=data_manager,
            task_list=todo_list
        )

        # Execute tool
        items = [
            {
                "content": "测试任务",
                "status": "pending"
            }
        ]

        result = await todo_write_tool.execute(context, items)

        assert result["success"] is True
        assert "rendered" in result["data"]
        assert result["summary"] == "任务清单已更新 (1 个任务)"

    @pytest.mark.asyncio
    async def test_tool_validation_error(self):
        """Test tool validation error"""
        from app.agent.context.execution_context import ExecutionContext
        from app.agent.context.data_context_manager import DataContextManager
        from app.agent.memory.hybrid_manager import HybridMemoryManager

        # Create minimal dependencies
        memory_manager = HybridMemoryManager(session_id="test_session")
        data_manager = DataContextManager(memory_manager)
        todo_list = TodoList()

        # Create execution context
        context = ExecutionContext(
            session_id="test_session",
            iteration=1,
            data_manager=data_manager,
            task_list=todo_list
        )

        # Execute tool with validation error (21 items)
        items = [
            {
                "content": f"任务{i}",
                "status": "pending"
            }
            for i in range(21)
        ]

        result = await todo_write_tool.execute(context, items)

        assert result["success"] is False
        assert "Too many items" in result["summary"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
