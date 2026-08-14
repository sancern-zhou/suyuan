"""
创建定时任务工具

参考：/tmp/nanobot-main/nanobot/agent/tools/cron.py

核心功能：
- 创建定时任务（支持cron表达式）
- 写入HEARTBEAT.md文件
- 支持每日报告、数据监控、智能建议
"""

from typing import Dict, Any, Optional
import structlog

from app.tools.base.tool_interface import LLMTool, ToolCategory

logger = structlog.get_logger(__name__)


class ScheduleTaskTool(LLMTool):
    """
    创建定时任务工具

    支持：
    - 每日报告：schedule="0 9 * * *"（每天9点）
    - 数据监控：持续监控数据变化
    - 智能建议：基于用户行为的主动建议

    实现：
    - 写入用户专属 HEARTBEAT.md 文件
    - UserHeartbeatManager 定期读取并执行
    - ✅ 不再支持全局路径，所有任务都必须关联用户
    """

    def __init__(self, user_heartbeat_manager=None):
        # 定义 function_schema
        function_schema = {
            "name": "schedule_task",
            "description": "管理当前社交用户的定时任务：创建、查询、启用、禁用或删除任务（仅支持社交模式）",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["create", "list", "enable", "disable", "delete"],
                        "description": "操作类型：create 创建任务；list 查询当前用户的全部任务（含已禁用任务）；enable 启用任务；disable 禁用任务；delete 删除任务。省略时默认 create。",
                        "default": "create"
                    },
                    "task_name": {
                        "type": "string",
                        "description": "enable、disable、delete 时必填：要管理的任务名称，必须来自当前用户的任务列表"
                    },
                    "task_description": {
                        "type": "string",
                        "description": "创建任务时必填：任务描述（清晰说明需要执行什么任务）"
                    },
                    "schedule": {
                        "type": "string",
                        "description": "创建任务时必填：cron表达式（如'0 9 * * *'表示每天早上9点，'*/30 * * * *'表示每30分钟）"
                    },
                    "channels": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "目标通道列表（支持: 'weixin'(微信)|'qq'(QQ)|'dingtalk'(钉钉)，默认['weixin']）",
                        "default": ["weixin"]
                    }
                },
                "required": []
            }
        }

        # 初始化基类
        super().__init__(
            name="schedule_task",
            description="管理当前社交用户的定时任务：创建、查询、启用、禁用或删除任务（仅支持社交模式）",
            category=ToolCategory.TASK_MANAGEMENT,
            function_schema=function_schema,
            version="1.3.0",
            requires_context=True,
        )

        self.user_heartbeat_manager = user_heartbeat_manager

        # 如果没有传入 user_heartbeat_manager，尝试从全局单例获取
        if not self.user_heartbeat_manager:
            try:
                from app.social.user_heartbeat_singleton import get_user_heartbeat_manager
                self.user_heartbeat_manager = get_user_heartbeat_manager()
                if self.user_heartbeat_manager:
                    logger.debug("user_heartbeat_manager_loaded_from_singleton")
            except Exception as e:
                logger.debug("failed_to_load_user_heartbeat_manager_from_singleton", error=str(e))

    async def execute(
        self,
        context=None,
        action: str = "create",
        task_name: str = None,
        task_description: str = None,
        schedule: str = None,
        channels: Optional[list] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        执行创建定时任务

        Args:
            task_description: 任务描述
            schedule: cron表达式
            channels: 目标通道列表

        Returns:
            {
                "status": "success" | "failed",
                "success": true|false,
                "data": {...},
                "metadata": {...},
                "summary": "简要总结"
            }
        """
        action = (action or "create").strip().lower()
        if action == "list":
            return self._list_tasks()
        if action in {"enable", "disable", "delete"}:
            return self._manage_existing_task(action, task_name)
        if action not in {"create"}:
            return self._tool_result(
                status="failed",
                success=False,
                action=action,
                data={"action": action},
                summary=f"不支持的定时任务操作: {action}",
            )

        # ✅ 延迟获取依赖（解决时序问题）
        if not self.user_heartbeat_manager:
            try:
                from app.social.user_heartbeat_singleton import get_user_heartbeat_manager
                self.user_heartbeat_manager = get_user_heartbeat_manager()
                logger.debug("user_heartbeat_manager_loaded_at_runtime")
            except Exception as e:
                logger.debug("failed_to_load_user_heartbeat_manager_at_runtime", error=str(e))

        # 参数验证
        if not task_description:
            return self._tool_result("failed", False, "create", {}, "缺少任务描述")

        if not schedule:
            return self._tool_result("failed", False, "create", {}, "缺少cron表达式")

        try:
            # 生成任务名称（从描述中提取关键词）
            task_name = self._generate_task_name(task_description)

            # ✅ 如果没有指定 channels，使用当前 channel
            if not channels:
                try:
                    from app.social.message_bus_singleton import get_current_channel
                    current_channel = get_current_channel()
                    if current_channel:
                        channels = [current_channel]
                        logger.debug("using_current_channel_as_default", channel=current_channel)
                    else:
                        channels = ["weixin"]  # 默认微信
                except Exception:
                    channels = ["weixin"]  # 默认微信

            # ✅ 通道名称映射（支持中文、英文变体、常见错误写法 → 标准英文key）
            CHANNEL_NAME_MAP = {
                # 微信
                "微信": "weixin",
                "wechat": "weixin",      # 常见错误
                "weixin": "weixin",      # 标准写法
                # QQ
                "QQ": "qq",
                "qq": "qq",              # 标准写法
                # 钉钉
                "钉钉": "dingtalk",
                "dingtalk": "dingtalk",  # 标准写法
            }

            # 标准化通道名称
            if channels:
                normalized_channels = []
                for ch in channels:
                    normalized_ch = CHANNEL_NAME_MAP.get(ch, ch)
                    normalized_channels.append(normalized_ch)
                channels = normalized_channels

            # 验证cron表达式
            if not self._validate_cron(schedule):
                return self._tool_result(
                    "failed",
                    False,
                    "create",
                    {"schedule": schedule},
                    f"无效的cron表达式: {schedule}",
                )

            # ✅ 修复：强制获取用户上下文，不允许使用全局路径
            if not self.user_heartbeat_manager:
                return self._tool_result("failed", False, "create", {}, "定时任务功能需要用户登录才能使用")

            try:
                from app.social.message_bus_singleton import get_current_chat_id, get_current_channel, get_current_bot_account
                current_chat_id = get_current_chat_id()
                current_channel = get_current_channel()
                current_bot_account = get_current_bot_account()

                if not current_chat_id or not current_channel:
                    return self._tool_result(
                        "failed",
                        False,
                        "create",
                        {},
                        "无法获取用户上下文，请确保在社交模式下使用此功能",
                    )

                # ✅ 构造 user_id：使用真实 bot_account
                user_id = f"{current_channel}:{current_bot_account or 'default'}:{current_chat_id}"
                logger.debug(
                    "using_user_context_for_task",
                    user_id=user_id,
                    channel=current_channel,
                    bot_account=current_bot_account,
                    chat_id=current_chat_id
                )

                # ✅ 使用用户专属 HeartbeatService（不允许降级到全局路径）
                heartbeat = await self.user_heartbeat_manager.get_user_heartbeat(user_id)
                add_task_kwargs = dict(
                    name=task_name,
                    schedule=schedule,
                    description=task_description,
                    channels=channels or ["weixin"],
                )
                heartbeat.add_task(**add_task_kwargs)

            except Exception as e:
                logger.error("failed_to_schedule_user_task", error=str(e), exc_info=True)
                return self._tool_result(
                    "failed",
                    False,
                    "create",
                    {"error": str(e)},
                    f"创建定时任务失败：{str(e)}",
                )

            logger.info(
                "task_scheduled",
                task_name=task_name,
                schedule=schedule,
                channels=channels,
                user_id=user_id
            )

            return self._tool_result(
                "success",
                True,
                "create",
                {
                    "task_name": task_name,
                    "schedule": schedule,
                    "channels": channels or ["weixin"],
                    "user_id": user_id,
                },
                f"已创建定时任务：{task_name}，执行时间：{schedule}，用户：{user_id}",
            )

        except Exception as e:
            logger.error(
                "failed_to_schedule_task",
                error=str(e),
                exc_info=True
            )
            return self._tool_result(
                "failed",
                False,
                "create",
                {"error": str(e)},
                f"创建定时任务失败：{str(e)}",
            )

    def _current_social_user_id(self) -> Optional[str]:
        """Resolve the current social user id from ContextVars."""
        try:
            from app.social.message_bus_singleton import (
                get_current_bot_account,
                get_current_channel,
                get_current_chat_id,
            )

            current_chat_id = get_current_chat_id()
            current_channel = get_current_channel()
            current_bot_account = get_current_bot_account()
        except Exception:
            return None

        if not current_chat_id or not current_channel:
            return None
        return f"{current_channel}:{current_bot_account or 'default'}:{current_chat_id}"

    def _list_tasks(self) -> Dict[str, Any]:
        """Return structured scheduled task data for the current social user."""
        user_id = self._current_social_user_id()
        if not user_id:
            return self._tool_result(
                "failed",
                False,
                "list",
                {},
                "无法获取用户上下文，请确保在社交模式下查询定时任务",
            )

        try:
            from app.social.heartbeat_service import HeartbeatService
            from app.social.user_preferences import UserPreferences

            preferences = UserPreferences(user_id)
            heartbeat_file = preferences.heartbeat_file
            if not heartbeat_file.exists():
                data = {
                    "user_id": user_id,
                    "enabled_count": 0,
                    "disabled_count": 0,
                    "total_count": 0,
                    "tasks": [],
                }
                return self._tool_result("success", True, "list", data, "当前用户没有定时任务")

            service = HeartbeatService(workspace=preferences.heartbeat_path, user_id=user_id)
            content = heartbeat_file.read_text(encoding="utf-8")
            tasks = service.parse_all_tasks(content, include_computed_next_run=True)
            enabled_count = sum(1 for task in tasks if task.get("enabled"))
            disabled_count = len(tasks) - enabled_count
            task_lines = [
                f"{idx}. {task['name']} ({'enabled' if task.get('enabled') else 'disabled'}, {task.get('manual_mode') or 'social'}, {task.get('schedule')})"
                for idx, task in enumerate(tasks, start=1)
            ]
            summary = (
                f"当前用户共有 {len(tasks)} 个定时任务：启用 {enabled_count} 个，禁用 {disabled_count} 个。"
            )
            if task_lines:
                summary += "\n" + "\n".join(task_lines)

            data = {
                "user_id": user_id,
                "enabled_count": enabled_count,
                "disabled_count": disabled_count,
                "total_count": len(tasks),
                "tasks": tasks,
            }
            return self._tool_result("success", True, "list", data, summary)
        except Exception as e:
            logger.error("failed_to_list_scheduled_tasks", user_id=user_id, error=str(e), exc_info=True)
            return self._tool_result(
                "failed",
                False,
                "list",
                {"user_id": user_id, "error": str(e)},
                f"查询定时任务失败：{str(e)}",
            )

    def _manage_existing_task(self, action: str, task_name: Optional[str]) -> Dict[str, Any]:
        task_name = (task_name or "").strip()
        if not task_name:
            return self._tool_result(
                "failed",
                False,
                action,
                {},
                f"{action} 操作需要提供任务名称",
            )

        user_id = self._current_social_user_id()
        if not user_id:
            return self._tool_result(
                "failed",
                False,
                action,
                {"task_name": task_name},
                "无法获取用户上下文，请确保在社交模式下管理定时任务",
            )

        try:
            from app.social.heartbeat_service import HeartbeatService
            from app.social.user_preferences import UserPreferences

            preferences = UserPreferences(user_id)
            heartbeat_file = preferences.heartbeat_file
            if not heartbeat_file.exists():
                return self._tool_result(
                    "failed",
                    False,
                    action,
                    {"user_id": user_id, "task_name": task_name},
                    "当前用户没有定时任务",
                )

            service = HeartbeatService(workspace=preferences.heartbeat_path, user_id=user_id)
            if action == "delete":
                updated = service.remove_task(task_name)
                enabled = None
                summary_action = "删除"
            else:
                enabled = action == "enable"
                updated = service.set_task_enabled(task_name, enabled)
                summary_action = "启用" if enabled else "禁用"

            data = {
                "user_id": user_id,
                "task_name": task_name,
                "action": action,
            }
            if enabled is not None:
                data["enabled"] = enabled

            if not updated:
                return self._tool_result(
                    "failed",
                    False,
                    action,
                    data,
                    f"未找到定时任务：{task_name}",
                )

            return self._tool_result(
                "success",
                True,
                action,
                data,
                f"已{summary_action}定时任务：{task_name}",
            )
        except Exception as e:
            logger.error("failed_to_manage_scheduled_task", action=action, task_name=task_name, error=str(e), exc_info=True)
            return self._tool_result(
                "failed",
                False,
                action,
                {"user_id": user_id, "task_name": task_name, "error": str(e)},
                f"管理定时任务失败：{str(e)}",
            )

    def _tool_result(
        self,
        status: str,
        success: bool,
        action: str,
        data: Dict[str, Any],
        summary: str,
    ) -> Dict[str, Any]:
        return {
            "status": status,
            "success": success,
            "data": data,
            "metadata": self._result_metadata(action),
            "summary": summary,
        }

    def _result_metadata(self, action: str) -> Dict[str, Any]:
        return {
            "schema_version": "v1.0",
            "tool_name": self.name,
            "action": action,
        }

    def _generate_task_name(self, description: str) -> str:
        """从描述中生成任务名称"""
        # 简化实现：提取前10个字符作为名称
        # TODO: 可以使用LLM生成更合适的名称
        name = description[:20].replace("\n", " ").strip()
        return name if name else "未命名任务"

    def _validate_cron(self, schedule: str) -> bool:
        """
        验证cron表达式格式

        Args:
            schedule: cron表达式

        Returns:
            是否有效
        """
        try:
            from apscheduler.triggers.cron import CronTrigger

            CronTrigger.from_crontab(schedule)
            return True
        except Exception as e:
            logger.warning("invalid_cron_expression", schedule=schedule, error=str(e))
            return False
