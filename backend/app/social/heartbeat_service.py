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
import time
from pathlib import Path
from typing import Callable, Optional, Dict, Any, List
import structlog
from datetime import datetime
from zoneinfo import ZoneInfo

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
        llm_service=None,
        user_id: Optional[str] = None
    ):
        """
        初始化心跳服务

        Args:
            interval_s: 心跳间隔（秒），默认30分钟
            workspace: 工作空间目录，默认 backend_data_registry/social/heartbeat
            on_execute: 执行任务回调函数，签名为 async def tasks: list -> dict
            on_notify: 发送通知回调函数，签名为 async def response: dict -> None
            llm_service: LLM服务（用于决策）
            user_id: 用户ID（用于多用户隔离），默认为 "global"
        """
        self.interval_s = interval_s
        self.workspace = workspace or Path("backend_data_registry/social/heartbeat")
        self.workspace.mkdir(parents=True, exist_ok=True)

        self.on_execute = on_execute
        self.on_notify = on_notify
        self.llm_service = llm_service
        self.user_id = user_id or "global"
        self.timezone = ZoneInfo("Asia/Shanghai")  # ✅ 使用北京时区

        self._running = False
        self._heartbeat_task: Optional[asyncio.Task] = None

        # HEARTBEAT.md 文件路径
        self.heartbeat_file = self.workspace / "HEARTBEAT.md"

        # 初始化HEARTBEAT.md
        self._init_heartbeat_file()

        logger.info(
            "heartbeat_service_initialized",
            interval_s=interval_s,
            workspace=str(self.workspace),
            user_id=self.user_id
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
        """心跳循环（动态调度器）"""
        while self._running:
            try:
                # 1. 读取任务列表
                if not self.heartbeat_file.exists():
                    logger.debug("heartbeat_file_not_exist")
                    await asyncio.sleep(60)  # 文件不存在，等待1分钟
                    continue

                heartbeat_content = self.heartbeat_file.read_text(encoding="utf-8")
                all_tasks = self._parse_tasks(heartbeat_content)

                if not all_tasks:
                    logger.debug("no_tasks_found")
                    await asyncio.sleep(self.interval_s)  # 没有任务，使用默认间隔
                    continue

                # 2. 计算最近的唤醒时间
                next_wake_ms = self._get_next_wake_ms(all_tasks)

                logger.debug(
                    "heartbeat_loop_checking_tasks",
                    total_tasks=len(all_tasks),
                    next_wake_ms=next_wake_ms,
                    next_wake_time=datetime.fromtimestamp(next_wake_ms / 1000, tz=self.timezone).strftime("%Y-%m-%d %H:%M:%S") if next_wake_ms else None
                )

                if next_wake_ms is None:
                    # 没有即将执行的任务，使用默认间隔
                    logger.debug("no_upcoming_tasks", interval_s=self.interval_s)
                    await asyncio.sleep(self.interval_s)
                    continue

                # 3. 精确等待到下次执行时间
                now_ms = int(time.time() * 1000)
                delay_ms = max(0, next_wake_ms - now_ms)
                delay_s = delay_ms / 1000

                logger.info(
                    "dynamic_scheduling",
                    next_wake=datetime.fromtimestamp(next_wake_ms / 1000, tz=self.timezone).strftime("%Y-%m-%d %H:%M:%S"),
                    delay_s=delay_s,
                    user_id=self.user_id
                )

                await asyncio.sleep(delay_s)

                if not self._running:
                    break

                # 4. 执行一次心跳检查
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
                # 出错后等待一段时间再重试
                await asyncio.sleep(60)

    async def _tick(self) -> None:
        """执行一次心跳检查"""
        try:
            logger.info("heartbeat_tick")

            # 1. 读取HEARTBEAT.md文件
            heartbeat_content = self.heartbeat_file.read_text(encoding="utf-8")

            # 2. 解析任务列表
            all_tasks = self._parse_tasks(heartbeat_content)

            if not all_tasks:
                logger.debug("no_tasks_found_in_heartbeat")
                return

            # 3. 筛选到期的任务（简单比较时间戳）
            current_time = datetime.now(self.timezone)
            current_time_ms = int(current_time.timestamp() * 1000)

            due_tasks = []
            updated_tasks = []

            for task in all_tasks:
                next_run_str = task.get("next_run_at")
                schedule = task.get("schedule", "")

                if not schedule:
                    continue

                try:
                    # 如果没有next_run_at，先计算
                    if not next_run_str:
                        next_run = self._compute_next_run(schedule, current_time)
                        if next_run:
                            task["next_run_at"] = next_run.isoformat()
                            next_run_str = next_run.isoformat()

                    # 检查是否到期
                    if next_run_str:
                        next_run = datetime.fromisoformat(next_run_str.replace("Z", "+00:00"))
                        next_run_ms = int(next_run.timestamp() * 1000)

                        # 如果当前时间 >= 下次运行时间，则执行
                        if current_time_ms >= next_run_ms:
                            due_tasks.append(task)
                            logger.info(
                                "task_is_due",
                                task_name=task.get("name"),
                                schedule=schedule,
                                next_run_at=next_run.strftime("%Y-%m-%d %H:%M:%S")
                            )

                    # 重新计算下次运行时间
                    next_run = self._compute_next_run(schedule, current_time)
                    if next_run:
                        task["next_run_at"] = next_run.isoformat()
                        updated_tasks.append(task)

                except Exception as e:
                    logger.warning(
                        "task_check_failed",
                        task_name=task.get("name"),
                        error=str(e)
                    )

            # 4. 更新HEARTBEAT.md中的next_run_at字段
            if updated_tasks:
                self._update_task_next_runs(updated_tasks)

            if not due_tasks:
                logger.debug(
                    "no_due_tasks",
                    total_tasks=len(all_tasks),
                    current_time=current_time.strftime("%Y-%m-%d %H:%M:%S %Z")
                )
                return

            logger.info(
                "tasks_due_for_execution",
                due_count=len(due_tasks),
                total_count=len(all_tasks),
                current_time=current_time.strftime("%Y-%m-%d %H:%M:%S %Z")
            )

            # 5. 执行到期的任务
            if self.on_execute:
                logger.info("executing_heartbeat_tasks", task_count=len(due_tasks), user_id=self.user_id)
                result = await self.on_execute(due_tasks)

                # 6. 发送通知（如果需要）
                if self.on_notify and result.get("should_notify", False):
                    # 将 user_id 添加到结果中
                    result_with_user = {**result, "user_id": self.user_id}
                    await self.on_notify(result_with_user)

                logger.info(
                    "heartbeat_completed",
                    tasks_executed=len(due_tasks),
                    result=result.get("summary", ""),
                    user_id=self.user_id
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
            任务列表（包含next_run_at字段）
        """
        # 简化实现：使用正则表达式提取任务
        # TODO: 后续可以使用更完善的YAML解析
        import re

        tasks = []
        # 修复：支持多行description（使用[\s\S]+?代替.+?）
        # 修复：允许enabled和next_run_at之间有其他字段（如channels）
        task_pattern = r'-\s*name:\s*(.+?)\s+schedule:\s*["\'](.+?)["\'].*?description:\s*([\s\S]+?)\s+enabled:\s*(true|false)(?:[\s\S]*?next_run_at:\s*["\'](.+?)["\'])?'

        matches = re.findall(task_pattern, content, re.DOTALL)
        for match in matches:
            name, schedule, description, enabled, next_run_at = match
            if enabled.lower() == "true":
                task = {
                    "name": name.strip(),
                    "schedule": schedule.strip(),
                    "description": description.strip(),
                    "enabled": True
                }
                # 如果文件中有next_run_at，使用它；否则稍后计算
                if next_run_at:
                    task["next_run_at"] = next_run_at.strip()
                    logger.debug(
                        "task_parsed_with_next_run",
                        name=name.strip()[:50],
                        schedule=schedule,
                        next_run_at=next_run_at.strip()
                    )
                else:
                    logger.debug(
                        "task_parsed_without_next_run",
                        name=name.strip()[:50],
                        schedule=schedule
                    )

                tasks.append(task)

        logger.info("tasks_parsed", count=len(tasks), with_next_run=sum(1 for t in tasks if t.get("next_run_at")))
        return tasks

    def _filter_due_tasks(self, tasks: List[Dict[str, Any]], current_time: datetime) -> List[Dict[str, Any]]:
        """
        根据cron表达式筛选到期的任务

        Args:
            tasks: 所有启用的任务列表
            current_time: 当前时间（时区感知）

        Returns:
            到期需要执行的任务列表
        """
        due_tasks = []

        for task in tasks:
            schedule = task.get("schedule", "")
            if not schedule:
                logger.warning("task_no_schedule", task_name=task.get("name"))
                continue

            try:
                # 检查cron表达式是否匹配当前时间
                if self._should_run_now(schedule, current_time):
                    due_tasks.append(task)
                    logger.debug(
                        "task_is_due",
                        task_name=task.get("name"),
                        schedule=schedule,
                        current_time=current_time.strftime("%H:%M")
                    )
            except Exception as e:
                logger.warning(
                    "task_schedule_check_failed",
                    task_name=task.get("name"),
                    schedule=schedule,
                    error=str(e)
                )

        return due_tasks

    def _compute_next_run(self, cron_expr: str, current_time: datetime) -> Optional[datetime]:
        """
        计算任务的下一次运行时间（使用croniter）

        Args:
            cron_expr: cron表达式
            current_time: 当前时间（时区感知）

        Returns:
            下次运行时间（时区感知），如果无法计算则返回None
        """
        try:
            from croniter import croniter

            # 使用croniter计算下次执行时间
            cron = croniter(cron_expr, current_time)
            next_run = cron.get_next(datetime)

            logger.debug(
                "computed_next_run",
                cron_expr=cron_expr,
                current_time=current_time.strftime("%Y-%m-%d %H:%M:%S"),
                next_run=next_run.strftime("%Y-%m-%d %H:%M:%S")
            )

            return next_run

        except Exception as e:
            logger.warning("compute_next_run_failed", cron_expr=cron_expr, error=str(e))
            return None

    def _get_next_wake_ms(self, tasks: List[Dict[str, Any]]) -> Optional[int]:
        """
        获取所有任务中最近的下次唤醒时间（毫秒时间戳）

        Args:
            tasks: 任务列表（包含next_run_at字段）

        Returns:
            最近的唤醒时间（毫秒），如果没有任务则返回None
        """
        now_ms = int(time.time() * 1000)
        wake_times = []

        for task in tasks:
            next_run_str = task.get("next_run_at")
            if not next_run_str:
                continue

            try:
                # 解析ISO格式时间字符串
                next_run = datetime.fromisoformat(next_run_str.replace("Z", "+00:00"))
                next_run_ms = int(next_run.timestamp() * 1000)

                # 只考虑未来的任务
                if next_run_ms > now_ms:
                    wake_times.append(next_run_ms)
            except Exception as e:
                logger.warning("parse_next_run_failed", task=task.get("name"), error=str(e))

        return min(wake_times) if wake_times else None

    async def _llm_decide(self, tasks: list[Dict[str, Any]]) -> bool:
        """
        LLM决策：是否需要执行任务（已废弃，保留用于兼容）

        Args:
            tasks: 任务列表

        Returns:
            是否执行任务
        """
        # ✅ 不再使用LLM决策，改为基于cron表达式判断
        # 这个方法保留用于向后兼容
        return len(tasks) > 0

    def _update_task_next_runs(self, tasks: List[Dict[str, Any]]) -> None:
        """
        更新HEARTBEAT.md文件中任务的next_run_at字段

        Args:
            tasks: 包含更新后next_run_at的任务列表
        """
        try:
            # 读取文件内容
            content = self.heartbeat_file.read_text(encoding="utf-8")

            # 更新每个任务的next_run_at字段
            for task in tasks:
                task_name = task.get("name")
                next_run_at = task.get("next_run_at")

                if not task_name or not next_run_at:
                    continue

                # 使用正则表达式替换
                import re
                # 匹配任务块并添加/更新next_run_at字段
                pattern = rf'(- name: {re.escape(task_name)}.*?schedule: ".*?".*?)\n(  description:.*?\n)'
                replacement = rf'\1  next_run_at: "{next_run_at}"\n\2'

                content = re.sub(pattern, replacement, content, flags=re.DOTALL)

            # 写回文件
            self.heartbeat_file.write_text(content, encoding="utf-8")

            logger.debug(
                "updated_task_next_runs",
                count=len(tasks)
            )

        except Exception as e:
            logger.warning(
                "update_task_next_runs_failed",
                error=str(e)
            )

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

        # 计算下次运行时间
        current_time = datetime.now(self.timezone)
        next_run = self._compute_next_run(schedule, current_time)
        next_run_at_str = next_run.isoformat() if next_run else ""

        new_task = f"""
- name: {name}
  schedule: "{schedule}"
  description: {description}
  enabled: true
  channels: {channels}
  next_run_at: "{next_run_at_str}"
"""

        # 追加到文件
        content = self.heartbeat_file.read_text(encoding="utf-8")
        content += "\n" + new_task
        self.heartbeat_file.write_text(content, encoding="utf-8")

        logger.info(
            "task_added_to_heartbeat",
            name=name,
            schedule=schedule,
            next_run_at=next_run_at_str
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
