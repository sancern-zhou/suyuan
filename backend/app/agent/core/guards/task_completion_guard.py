"""
任务完成守卫

在任务结束前检查是否有未完成任务，确保任务管理的完整性。
"""

from typing import Dict, Any, List
import structlog


logger = structlog.get_logger()


class TaskCompletionGuard:
    """任务完成守卫"""

    def __init__(self, memory_manager):
        """初始化守卫

        Args:
            memory_manager: 混合记忆管理器
        """
        self.memory = memory_manager

    async def check(self, session_id: str) -> Dict[str, Any]:
        """
        检查会话中是否有未完成任务

        Args:
            session_id: 会话 ID

        Returns:
            守卫检查结果：
            {
                "has_incomplete": bool,
                "incomplete_count": int,
                "incomplete_tasks": List[Dict],
                "warning_message": str
            }
        """
        try:
            # 获取任务列表
            from app.agent.context.execution_context import ExecutionContext
            from app.agent.context.data_context_manager import DataContextManager

            # 创建临时的 DataContextManager（用于访问 TaskList）
            data_manager = DataContextManager(memory_manager=self.memory)

            # 创建 ExecutionContext（iteration 参数在此场景下不使用，传入 0）
            context = ExecutionContext(
                session_id=session_id,
                iteration=0,
                data_manager=data_manager
            )
            task_list = context.get_task_list()

            if not task_list:
                return {
                    "has_incomplete": False,
                    "incomplete_count": 0,
                    "incomplete_tasks": [],
                    "warning_message": ""
                }

            # 检查未完成任务
            incomplete_tasks = []
            for task in task_list.get_tasks().values():
                if task.status.value in ["pending", "in_progress"]:
                    incomplete_tasks.append({
                        "id": task.id,
                        "subject": task.subject,
                        "status": task.status.value,
                        "progress": task.progress
                    })

            # 按状态排序（in_progress 优先）
            incomplete_tasks.sort(key=lambda t: 0 if t["status"] == "in_progress" else 1)

            has_incomplete = len(incomplete_tasks) > 0

            if has_incomplete:
                # 生成警告消息
                task_list_str = "\n".join(
                    f"- [{t['status']}] {t['subject']} (ID: {t['id']})"
                    for t in incomplete_tasks
                )

                warning_message = f"""
## ⚠️ 任务未完成警告

检测到你有 {len(incomplete_tasks)} 个任务尚未完成：

{task_list_str}

## 必须执行的操作

根据任务清单管理规范，你必须：

1. **标记任务完成**：对每个 in_progress 任务调用
   ```json
   {{"tool": "update_task", "args": {{"task_id": "任务ID", "status": "completed"}}}}
   ```

2. **确认所有任务**：调用 list_tasks 查看任务状态
   ```json
   {{"tool": "list_tasks", "args": {{}}}}
   ```

3. **然后才能结束**：所有任务完成后才能调用 FINISH

禁止创建任务后就不再管理状态！
"""
                logger.warning(
                    "task_guard_incomplete_found",
                    session_id=session_id,
                    incomplete_count=len(incomplete_tasks),
                    task_ids=[t["id"] for t in incomplete_tasks]
                )
            else:
                warning_message = ""
                logger.info(
                    "task_guard_all_completed",
                    session_id=session_id
                )

            return {
                "has_incomplete": has_incomplete,
                "incomplete_count": len(incomplete_tasks),
                "incomplete_tasks": incomplete_tasks,
                "warning_message": warning_message
            }

        except Exception as e:
            logger.error(
                "task_guard_check_failed",
                session_id=session_id,
                error=str(e),
                exc_info=True
            )
            # 守卫检查失败不影响主流程
            return {
                "has_incomplete": False,
                "incomplete_count": 0,
                "incomplete_tasks": [],
                "warning_message": ""
            }
