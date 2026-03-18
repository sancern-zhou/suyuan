"""
create_scheduled_task工具
通过自然语言创建定时任务
"""
import json
import structlog
from typing import Dict, Any, Optional
from datetime import datetime

from app.tools.base import LLMTool, ToolCategory
from app.scheduled_tasks import (
    ScheduledTask,
    TaskStep,
    ScheduleType,
    get_scheduled_task_service
)
from app.services.llm_service import LLMService

logger = structlog.get_logger()


class CreateScheduledTaskTool(LLMTool):
    """创建定时任务工具"""

    def __init__(self):
        function_schema = {
            "type": "function",
            "function": {
                "name": "create_scheduled_task",
                "description": (
                    "通过自然语言创建定时任务。支持6种调度类型：\n"
                    "预设类型：\n"
                    "1. daily_8am - 每天早上8点执行\n"
                    "2. every_2h - 每2小时执行一次\n"
                    "3. every_30min - 每30分钟执行一次\n\n"
                    "灵活类型：\n"
                    "4. once - 一次性任务（指定具体时间执行一次）\n"
                    "5. interval - 自定义间隔（每N分钟执行）\n"
                    "6. daily_custom - 每天自定义时间执行\n\n"
                    "示例：\n"
                    "- '每天早上8点分析广州昨天的O3污染'\n"
                    "- '每2小时检查PM2.5浓度变化'\n"
                    "- '1分钟后执行臭氧报告分析'\n"
                    "- '每5分钟更新空气质量数据'\n"
                    "- '每天下午3点半生成污染分析报告'"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "user_request": {
                            "type": "string",
                            "description": "用户的自然语言请求，描述要创建的定时任务"
                        }
                    },
                    "required": ["user_request"]
                }
            }
        }
        super().__init__(
            name="create_scheduled_task",
            description="通过自然语言创建定时任务",
            category=ToolCategory.QUERY,
            function_schema=function_schema,
            version="1.0.0",
            requires_context=False
        )

    async def execute(
        self,
        user_request: str,
        **kwargs
    ) -> Dict[str, Any]:
        """执行工具"""
        try:
            # 使用LLM解析用户意图
            task_config = await self._parse_user_request(user_request)

            if not task_config:
                return {
                    "success": False,
                    "data": {"error": "无法解析任务配置"},
                    "summary": "任务配置解析失败，请提供更清晰的描述"
                }

            # 创建任务
            service = get_scheduled_task_service()

            # 生成任务ID
            import uuid
            task_id = f"task_{uuid.uuid4().hex[:8]}"

            # 构建任务对象
            task_kwargs = {
                "task_id": task_id,
                "name": task_config["name"],
                "description": task_config["description"],
                "schedule_type": ScheduleType(task_config["schedule_type"]),
                "enabled": True,
                "steps": [
                    TaskStep(
                        step_id=f"step_{i+1}",
                        description=step["description"],
                        agent_prompt=step["agent_prompt"],
                        timeout_seconds=step.get("timeout_seconds", 300),
                        retry_on_failure=step.get("retry_on_failure", False)
                    )
                    for i, step in enumerate(task_config["steps"])
                ],
                "tags": task_config.get("tags", [])
            }

            # 添加灵活调度参数
            schedule_type = task_config["schedule_type"]
            if schedule_type == "once":
                # 解析run_at字符串为datetime
                from datetime import datetime
                run_at_str = task_config["run_at"]
                task_kwargs["run_at"] = datetime.strptime(run_at_str, "%Y-%m-%d %H:%M:%S")
            elif schedule_type == "interval":
                task_kwargs["interval_minutes"] = task_config["interval_minutes"]
            elif schedule_type == "daily_custom":
                task_kwargs["hour"] = task_config["hour"]
                task_kwargs["minute"] = task_config["minute"]

            task = ScheduledTask(**task_kwargs)

            # 创建任务
            created_task = service.create_task(task)

            return {
                "success": True,
                "data": {
                    "task_id": created_task.task_id,
                    "name": created_task.name,
                    "description": created_task.description,
                    "schedule_type": created_task.schedule_type.value,
                    "steps_count": len(created_task.steps),
                    "next_run_at": str(created_task.next_run_at) if created_task.next_run_at else None
                },
                "summary": (
                    f"已创建定时任务：{created_task.name}\n"
                    f"调度类型：{created_task.schedule_type.value}\n"
                    f"步骤数量：{len(created_task.steps)}\n"
                    f"任务ID：{created_task.task_id}"
                )
            }

        except Exception as e:
            logger.error(f"Failed to create scheduled task: {e}", exc_info=True)
            return {
                "success": False,
                "data": {"error": str(e)},
                "summary": f"创建定时任务失败：{str(e)}"
            }

    async def _parse_user_request(self, user_request: str) -> Optional[Dict[str, Any]]:
        """使用LLM解析用户请求"""
        llm_service = LLMService()

        prompt = f"""你是一个定时任务配置助手。请根据用户的自然语言请求，生成定时任务配置。

用户请求：{user_request}
当前时间：{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

⚠️ 重要提示：
1. 如果用户说"N分钟后"、"N小时后"，请基于当前时间计算具体的执行时间
2. 文档路径中的日期（如"2025年7月8日臭氧垂直.docx"）仅用于识别文档，与任务执行时间无关
3. 只有用户明确指定"明天"、"后天"或具体日期时，才使用那个日期

请分析用户请求，生成JSON格式的任务配置。配置必须包含以下字段：

1. name: 任务名称（简短，10字以内）
2. description: 任务描述（详细说明任务目的）
3. schedule_type: 调度类型，支持以下类型：
   预设类型：
   - "daily_8am": 每天早上8点
   - "every_2h": 每2小时
   - "every_30min": 每30分钟

   灵活类型：
   - "once": 一次性任务（需额外提供run_at字段，格式："2026-02-13 14:30:00"）
   - "interval": 自定义间隔（需额外提供interval_minutes字段，如5表示每5分钟）
   - "daily_custom": 每天自定义时间（需额外提供hour和minute字段，如hour:9, minute:30表示每天9:30）

4. 灵活调度参数（根据schedule_type选择）：
   - run_at: 一次性任务的执行时间（schedule_type=once时必填，格式："2026-02-13 14:30:00"）
   - interval_minutes: 间隔分钟数（schedule_type=interval时必填，如5表示每5分钟）
   - hour: 每天执行的小时（schedule_type=daily_custom时必填，0-23）
   - minute: 每天执行的分钟（schedule_type=daily_custom时必填，0-59）

5. steps: 任务步骤列表，每个步骤包含：
   - description: 步骤描述
   - agent_prompt: 发送给Agent的提示词（详细、具体）
   - timeout_seconds: 超时时间（秒，默认300）
   - retry_on_failure: 失败时是否重试（默认false）

6. tags: 标签列表（可选）

示例1（预设类型）：
{{
  "name": "每日O3污染分析",
  "description": "每天早上8点分析广州昨天的O3污染情况",
  "schedule_type": "daily_8am",
  "steps": [
    {{
      "description": "获取昨日O3数据",
      "agent_prompt": "查询广州昨天的O3浓度数据，包括小时值和日均值",
      "timeout_seconds": 300,
      "retry_on_failure": false
    }}
  ],
  "tags": ["O3", "广州", "日报"]
}}

示例2（一次性任务）：
{{
  "name": "臭氧报告分析",
  "description": "分析指定文档的臭氧数据",
  "schedule_type": "once",
  "run_at": "2026-02-13 14:30:00",
  "steps": [
    {{
      "description": "读取文档表格",
      "agent_prompt": "读取D:\\\\报告\\\\2025年7月8日臭氧垂直.docx的表格内容并分析",
      "timeout_seconds": 600,
      "retry_on_failure": false
    }}
  ],
  "tags": ["臭氧", "报告"]
}}

示例3（自定义间隔）：
{{
  "name": "PM2.5监测",
  "description": "每5分钟检查PM2.5浓度",
  "schedule_type": "interval",
  "interval_minutes": 5,
  "steps": [
    {{
      "description": "查询PM2.5数据",
      "agent_prompt": "查询最新的PM2.5浓度数据",
      "timeout_seconds": 120,
      "retry_on_failure": true
    }}
  ],
  "tags": ["PM2.5", "监测"]
}}

示例4（每天自定义时间）：
{{
  "name": "下午污染分析",
  "description": "每天下午3点半分析污染情况",
  "schedule_type": "daily_custom",
  "hour": 15,
  "minute": 30,
  "steps": [
    {{
      "description": "分析污染数据",
      "agent_prompt": "分析当天的污染情况",
      "timeout_seconds": 300,
      "retry_on_failure": false
    }}
  ],
  "tags": ["污染分析"]
}}

请直接返回JSON，不要包含任何其他文字。"""

        try:
            # ✅ 定时任务配置LLM调用上下文日志
            logger.info(
                "scheduled_task_config_llm_call",
                user_request=user_request[:100] if len(user_request) > 100 else user_request,
                prompt_length=len(prompt),
            )

            response = await llm_service.chat(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=2000
            )

            content = response

            # 提取JSON
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()

            # 解析JSON
            config = json.loads(content)

            # 验证必需字段
            required_fields = ["name", "description", "schedule_type", "steps"]
            if not all(field in config for field in required_fields):
                logger.error(f"Missing required fields in config: {config}")
                return None

            # 验证schedule_type
            valid_schedules = ["daily_8am", "every_2h", "every_30min", "once", "interval", "daily_custom"]
            if config["schedule_type"] not in valid_schedules:
                logger.error(f"Invalid schedule_type: {config['schedule_type']}")
                return None

            # 验证灵活调度参数
            schedule_type = config["schedule_type"]
            if schedule_type == "once" and "run_at" not in config:
                logger.error("schedule_type=once but run_at is missing")
                return None
            if schedule_type == "interval" and "interval_minutes" not in config:
                logger.error("schedule_type=interval but interval_minutes is missing")
                return None
            if schedule_type == "daily_custom" and ("hour" not in config or "minute" not in config):
                logger.error("schedule_type=daily_custom but hour/minute is missing")
                return None

            return config

        except Exception as e:
            logger.error(f"Failed to parse user request: {e}", exc_info=True)
            return None


# 工具实例
create_scheduled_task_tool = CreateScheduledTaskTool()
