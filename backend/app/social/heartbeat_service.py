"""
心跳服务：实现呼吸机制

参考：/tmp/nanobot-main/nanobot/heartbeat/service.py

核心功能：
- 定期唤醒Agent（默认30分钟间隔）
- 读取HEARTBEAT.md文件（包含待办任务列表）
- LLM决策是否需要执行任务
- 执行任务后主动推送结果
"""

import asyncio
from pathlib import Path
from typing import Callable, Optional, Dict, Any
import structlog

logger = structlog.get_logger(__name__)


class HeartbeatService:
    """
    心跳服务：定期唤醒Agent，实现主动推送能力

    工作流程：
    1. 每隔 interval_s（默认30分钟）唤醒一次
    2. 读取 HEARTBEAT.md 文件（包含待办任务列表）
    3. 通过LLM决策是否需要执行任务
    4. 如果需要执行，调用 on_execute 回调
    5. 如果需要通知，调用 on_notify 回调
    """

    def __init__(
        self,
        interval_s: int = 30 * 60,  # 30分钟
        workspace: Optional[Path] = None,
        on_execute: Optional[Callable] = None,
        on_notify: Optional[Callable] = None,
        llm_service=None
    ):
        """
        初始化心跳服务

        Args:
            interval_s: 心跳间隔（秒），默认30分钟
            workspace: 工作空间目录，默认 backend_data_registry/social/heartbeat
            on_execute: 执行任务回调函数，签名为 async def tasks: list -> dict
            on_notify: 发送通知回调函数，签名为 async def response: dict -> None
            llm_service: LLM服务（用于决策）
        """
        self.interval_s = interval_s
        self.workspace = workspace or Path("backend_data_registry/social/heartbeat")
        self.workspace.mkdir(parents=True, exist_ok=True)

        self.on_execute = on_execute
        self.on_notify = on_notify
        self.llm_service = llm_service

        self._running = False
        self._heartbeat_task: Optional[asyncio.Task] = None

        # HEARTBEAT.md 文件路径
        self.heartbeat_file = self.workspace / "HEARTBEAT.md"

        # 初始化HEARTBEAT.md
        self._init_heartbeat_file()

        logger.info(
            "heartbeat_service_initialized",
            interval_s=interval_s,
            workspace=str(self.workspace)
        )

    def _init_heartbeat_file(self) -> None:
        """初始化HEARTBEAT.md文件"""
        if not self.heartbeat_file.exists():
            initial_content = """# 心跳任务列表

此文件包含Agent需要定期检查和执行的任务。

## 任务格式

```yaml
- name: 任务名称
  schedule: "cron表达式"
  description: 任务描述
  enabled: true
  channels: ["weixin", "qq"]
  last_run: "最后执行时间"
  next_run: "下次执行时间"
```

## 示例任务

```yaml
- name: 每日空气质量报告
  schedule: "0 9 * * *"  # 每天早上9点
  description: 发送广州空气质量日报
  enabled: true
  channels: ["weixin"]

- name: PM2.5超标监控
  schedule: "*/30 * * * *"  # 每30分钟
  description: 检查PM2.5是否超过75μg/m³
  enabled: false
  channels: ["weixin", "qq"]
```

## 注意事项

- schedule 字段使用标准 cron 表达式
- enabled: false 的任务会被跳过
- HeartbeatService 会定期检查并执行到期的任务
"""
            self.heartbeat_file.write_text(initial_content, encoding="utf-8")
            logger.info("heartbeat_file_created", path=str(self.heartbeat_file))

    async def start(self) -> None:
        """启动心跳循环"""
        if self._running:
            logger.warning("heartbeat_service_already_running")
            return

        self._running = True
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        logger.info(
            "heartbeat_service_started",
            interval_s=self.interval_s
        )

    async def stop(self) -> None:
        """停止心跳服务"""
        self._running = False

        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass

        logger.info("heartbeat_service_stopped")

    async def _heartbeat_loop(self) -> None:
        """心跳循环"""
        while self._running:
            try:
                # 等待指定间隔
                await asyncio.sleep(self.interval_s)

                if not self._running:
                    break

                # 执行一次心跳检查
                await self._tick()

            except asyncio.CancelledError:
                logger.info("heartbeat_loop_cancelled")
                break
            except Exception as e:
                logger.error(
                    "heartbeat_loop_error",
                    error=str(e),
                    exc_info=True
                )
                # 继续运行，不因单次错误而停止

    async def _tick(self) -> None:
        """执行一次心跳检查"""
        try:
            logger.info("heartbeat_tick")

            # 1. 读取HEARTBEAT.md文件
            heartbeat_content = self.heartbeat_file.read_text(encoding="utf-8")

            # 2. 解析任务列表
            tasks = self._parse_tasks(heartbeat_content)

            if not tasks:
                logger.debug("no_tasks_found_in_heartbeat")
                return

            # 3. LLM决策：是否需要执行任务
            should_execute = await self._llm_decide(tasks)

            if not should_execute:
                logger.info("heartbeat_skipped", reason="llm_decided_not_to_execute")
                return

            # 4. 执行任务
            if self.on_execute:
                logger.info("executing_heartbeat_tasks", task_count=len(tasks))
                result = await self.on_execute(tasks)

                # 5. 发送通知（如果需要）
                if self.on_notify and result.get("should_notify", False):
                    await self.on_notify(result)

                logger.info(
                    "heartbeat_completed",
                    tasks_executed=len(tasks),
                    result=result.get("summary", "")
                )

        except Exception as e:
            logger.error(
                "heartbeat_tick_error",
                error=str(e),
                exc_info=True
            )

    def _parse_tasks(self, content: str) -> list[Dict[str, Any]]:
        """
        解析HEARTBEAT.md文件中的任务列表

        Args:
            content: HEARTBEAT.md文件内容

        Returns:
            任务列表
        """
        # 简化实现：使用正则表达式提取任务
        # TODO: 后续可以使用更完善的YAML解析
        import re

        tasks = []
        task_pattern = r'-\s*name:\s*(.+?)\s+schedule:\s*["\'](.+?)["\']\s+description:\s*(.+?)\s+enabled:\s*(true|false)'

        matches = re.findall(task_pattern, content, re.DOTALL)
        for match in matches:
            name, schedule, description, enabled = match
            if enabled.lower() == "true":
                tasks.append({
                    "name": name.strip(),
                    "schedule": schedule.strip(),
                    "description": description.strip(),
                    "enabled": True
                })

        logger.debug("tasks_parsed", count=len(tasks))
        return tasks

    async def _llm_decide(self, tasks: list[Dict[str, Any]]) -> bool:
        """
        LLM决策：是否需要执行任务

        Args:
            tasks: 任务列表

        Returns:
            是否执行任务
        """
        if not self.llm_service:
            # 如果没有LLM服务，默认执行
            return True

        # 简化实现：如果有任务就执行
        # TODO: 可以使用LLM进行更智能的决策
        return len(tasks) > 0

    def add_task(
        self,
        name: str,
        schedule: str,
        description: str,
        channels: list[str] = None
    ) -> None:
        """
        添加新任务到HEARTBEAT.md

        Args:
            name: 任务名称
            schedule: cron表达式
            description: 任务描述
            channels: 目标通道列表
        """
        channels = channels or ["weixin"]

        new_task = f"""
- name: {name}
  schedule: "{schedule}"
  description: {description}
  enabled: true
  channels: {channels}
"""

        # 追加到文件
        content = self.heartbeat_file.read_text(encoding="utf-8")
        content += "\n" + new_task
        self.heartbeat_file.write_text(content, encoding="utf-8")

        logger.info(
            "task_added_to_heartbeat",
            name=name,
            schedule=schedule
        )

    def list_tasks(self) -> list[Dict[str, Any]]:
        """
        列出所有任务

        Returns:
            任务列表
        """
        content = self.heartbeat_file.read_text(encoding="utf-8")
        return self._parse_tasks(content)

    def remove_task(self, task_name: str) -> bool:
        """
        从HEARTBEAT.md中移除任务

        Args:
            task_name: 任务名称

        Returns:
            是否成功移除
        """
        try:
            content = self.heartbeat_file.read_text(encoding="utf-8")

            # 使用正则表达式移除任务
            import re
            pattern = rf'-\s*name:\s*{re.escape(task_name)}.*?(?=-\s*name:|$)'
            new_content = re.sub(pattern, '', content, flags=re.DOTALL)

            self.heartbeat_file.write_text(new_content, encoding="utf-8")

            logger.info("task_removed_from_heartbeat", name=task_name)
            return True

        except Exception as e:
            logger.error(
                "failed_to_remove_task",
                task_name=task_name,
                error=str(e)
            )
            return False
