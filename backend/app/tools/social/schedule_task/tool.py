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

    def __init__(self, heartbeat_service=None):
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
                        "description": "目标通道列表（如['weixin', 'qq']）",
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

            # 验证cron表达式
            if not self._validate_cron(schedule):
                return {
                    "status": "failed",
                    "success": False,
                    "summary": f"无效的cron表达式: {schedule}"
                }

            # 添加到HEARTBEAT.md
            if self.heartbeat_service:
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
                    channels=channels or ["weixin"]
                )

            logger.info(
                "task_scheduled",
                task_name=task_name,
                schedule=schedule,
                channels=channels
            )

            return {
                "status": "success",
                "success": True,
                "task_name": task_name,
                "schedule": schedule,
                "channels": channels or ["weixin"],
                "summary": f"已创建定时任务：{task_name}，执行时间：{schedule}"
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
        channels: list
    ) -> None:
        """降级方案：直接写入HEARTBEAT.md文件"""
        workspace = Path("backend_data_registry/social/heartbeat")
        workspace.mkdir(parents=True, exist_ok=True)
        heartbeat_file = workspace / "HEARTBEAT.md"

        new_task = f"""
- name: {task_name}
  schedule: "{schedule}"
  description: {description}
  enabled: true
  channels: {channels}
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
            path=str(heartbeat_file)
        )
