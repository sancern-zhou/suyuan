"""
任务完成守卫

在任务结束前检查是否有未完成任务，确保任务管理的完整性。
"""

from typing import Dict, Any, List
import structlog


logger = structlog.get_logger()


class TaskCompletionGuard:
    """任务完成守卫"""

    def __init__(self, memory_manager, task_list=None):
        """初始化守卫

        Args:
            memory_manager: 混合记忆管理器
            task_list: 当前 ReAct runtime 共享的 TaskList 实例
        """
        self.memory = memory_manager
        self.task_list = task_list

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
            task_list = self.task_list

            if not task_list:
                return {
                    "has_incomplete": False,
                    "incomplete_count": 0,
                    "incomplete_tasks": [],
                    "warning_message": ""
                }

            incomplete_tasks = []
            if hasattr(task_list, "to_dict_list"):
                for idx, item in enumerate(task_list.to_dict_list()):
                    status = item.get("status")
                    if status in ["pending", "in_progress"]:
                        incomplete_tasks.append({
                            "id": str(idx + 1),
                            "subject": item.get("content", ""),
                            "status": status,
                            "progress": None,
                        })
            elif hasattr(task_list, "get_tasks"):
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

根据任务清单管理规范，你必须先完成实际业务动作。只有任务真实完成后，才能调用 TaskUpdate
把对应任务标记为 completed。

注意：
- TaskUpdate 是状态管理工具，不是业务进展工具。
- 不要为了消除警告而重复提交无变化更新。
- 如果仍有 pending/in_progress 任务，应优先继续执行对应业务工具。
- 如果所有任务已经真实完成，更新一次 TaskUpdate 后直接给出最终回答。
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
