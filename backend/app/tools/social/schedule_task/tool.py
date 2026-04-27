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
from pathlib import Path

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
    - 写入HEARTBEAT.md文件
    - HeartbeatService定期读取并执行
    """

    def __init__(self, heartbeat_service=None, user_heartbeat_manager=None):
        # 定义 function_schema
        function_schema = {
            "name": "schedule_task",
            "description": "创建定时任务，系统会定期执行并主动推送结果",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_description": {
                        "type": "string",
                        "description": "任务描述（清晰说明需要执行什么任务）"
                    },
                    "schedule": {
                        "type": "string",
                        "description": "cron表达式（如'0 9 * * *'表示每天早上9点，'*/30 * * * *'表示每30分钟）"
                    },
                    "channels": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "目标通道列表（支持: 'weixin'(微信)|'qq'(QQ)|'dingtalk'(钉钉)|'wecom'(企业微信)，默认['weixin']）",
                        "default": ["weixin"]
                    }
                },
                "required": ["task_description", "schedule"]
            }
        }

        # 初始化基类
        super().__init__(
            name="schedule_task",
            description="创建定时任务，系统会定期执行并主动推送结果",
            category=ToolCategory.QUERY,
            function_schema=function_schema,
            version="1.0.0"
        )

        self.heartbeat_service = heartbeat_service
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
                "task_name": "任务名称",
                "schedule": "cron表达式",
                "summary": "简要总结"
            }
        """
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
            return {
                "status": "failed",
                "success": False,
                "summary": "缺少任务描述"
            }

        if not schedule:
            return {
                "status": "failed",
                "success": False,
                "summary": "缺少cron表达式"
            }

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
                # 企业微信
                "企业微信": "wecom",
                "企微": "wecom",
                "wecom": "wecom",        # 标准写法
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
                return {
                    "status": "failed",
                    "success": False,
                    "summary": f"无效的cron表达式: {schedule}"
                }

            # 获取当前用户ID（用于用户专属任务）
            user_id = "global"
            if self.user_heartbeat_manager:
                try:
                    from app.social.message_bus_singleton import get_current_chat_id, get_current_channel
                    current_chat_id = get_current_chat_id()
                    current_channel = get_current_channel()

                    if current_chat_id and current_channel:
                        user_id = f"{current_channel}:default:{current_chat_id}"
                        logger.debug("using_user_context_for_task", user_id=user_id, channel=current_channel, chat_id=current_chat_id)
                except Exception as e:
                    logger.debug("failed_to_get_user_context", error=str(e))
                    user_id = "global"

            # 添加到HEARTBEAT.md
            if self.user_heartbeat_manager and user_id != "global":
                # 使用用户专属 HeartbeatService
                heartbeat = await self.user_heartbeat_manager.get_user_heartbeat(user_id)
                heartbeat.add_task(
                    name=task_name,
                    schedule=schedule,
                    description=task_description,
                    channels=channels or ["weixin"]
                )
            elif self.heartbeat_service:
                # 降级：使用全局 HeartbeatService
                self.heartbeat_service.add_task(
                    name=task_name,
                    schedule=schedule,
                    description=task_description,
                    channels=channels or ["weixin"]
                )
            else:
                # 降级：直接写入文件
                self._write_to_heartbeat_file(
                    task_name=task_name,
                    schedule=schedule,
                    description=task_description,
                    channels=channels or ["weixin"],
                    user_id=user_id
                )

            logger.info(
                "task_scheduled",
                task_name=task_name,
                schedule=schedule,
                channels=channels,
                user_id=user_id
            )

            return {
                "status": "success",
                "success": True,
                "task_name": task_name,
                "schedule": schedule,
                "channels": channels or ["weixin"],
                "user_id": user_id,
                "summary": f"已创建定时任务：{task_name}，执行时间：{schedule}，用户：{user_id}"
            }

        except Exception as e:
            logger.error(
                "failed_to_schedule_task",
                error=str(e),
                exc_info=True
            )
            return {
                "status": "failed",
                "success": False,
                "summary": f"创建定时任务失败：{str(e)}"
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
        parts = schedule.split()
        if len(parts) != 5:
            return False

        # 简单验证：每个部分应该是数字或通配符
        for part in parts:
            if part not in ["*", "*/*", "*/"] and not part.replace("/", "").replace("*", "").replace(",", "").replace("-", "").isdigit():
                return False

        return True

    def _write_to_heartbeat_file(
        self,
        task_name: str,
        schedule: str,
        description: str,
        channels: list,
        user_id: str = "global"
    ) -> None:
        """降级方案：直接写入HEARTBEAT.md文件"""
        # ✅ 使用 backend 目录下的 backend_data_registry
        import os
        from datetime import datetime
        from zoneinfo import ZoneInfo

        current_dir = Path(os.getcwd())

        # 如果当前在 backend 目录，直接使用
        if current_dir.name == "backend":
            workspace = current_dir / "backend_data_registry/social/heartbeat"
        else:
            # 否则假设在项目根目录
            workspace = current_dir / "backend" / "backend_data_registry/social/heartbeat"

        # 如果是用户专属任务，使用用户专属目录
        if user_id and user_id != "global":
            safe_user_id = user_id.replace(":", "_")
            workspace = workspace / safe_user_id

        workspace.mkdir(parents=True, exist_ok=True)
        heartbeat_file = workspace / "HEARTBEAT.md"

        # ✅ 处理多行 description：替换换行符为空格
        clean_description = description.replace("\n", " ").replace("\r", "").strip()

        # ✅ 计算 next_run_at（使用 croniter）
        try:
            from croniter import croniter
            current_time = datetime.now(ZoneInfo("Asia/Shanghai"))
            cron = croniter(schedule, current_time)
            next_run = cron.get_next(datetime)
            next_run_at_str = next_run.isoformat()
        except Exception as e:
            logger.warning("compute_next_run_failed", schedule=schedule, error=str(e))
            next_run_at_str = ""

        new_task = f"""
- name: {task_name}
  schedule: "{schedule}"
  description: {clean_description}
  enabled: true
  channels: {channels}
  next_run_at: "{next_run_at_str}"
"""

        # 追加到文件
        if heartbeat_file.exists():
            content = heartbeat_file.read_text(encoding="utf-8")
            content += "\n" + new_task
        else:
            content = "# 心跳任务列表\n\n" + new_task

        heartbeat_file.write_text(content, encoding="utf-8")

        logger.info(
            "task_written_to_heartbeat_file",
            task_name=task_name,
            schedule=schedule,
            next_run_at=next_run_at_str,
            path=str(heartbeat_file),
            user_id=user_id
        )
