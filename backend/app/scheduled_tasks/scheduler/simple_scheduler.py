"""
简单调度器 - 基于APScheduler
支持预设cron模板和灵活调度（一次性、自定义间隔、自定义时间），最多3个并发任务
"""
import asyncio
import structlog
from datetime import datetime, timedelta
from typing import Callable, Optional, Dict
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.interval import IntervalTrigger

from ..models.task import ScheduledTask, ScheduleType
from ..storage import TaskStorage

logger = structlog.get_logger()


class SimpleScheduler:
    """简单调度器"""

    # 预设cron模板
    CRON_TEMPLATES = {
        ScheduleType.DAILY_8AM: {"hour": 8, "minute": 0},      # 每天早上8点
        ScheduleType.EVERY_2H: {"hour": "*/2", "minute": 0},   # 每2小时
        ScheduleType.EVERY_30MIN: {"minute": "*/30"},          # 每30分钟
    }

    MAX_CONCURRENT_TASKS = 3  # 最多3个并发任务

    def __init__(self, task_storage: TaskStorage):
        self.task_storage = task_storage
        self.scheduler = AsyncIOScheduler()
        self.running_tasks: Dict[str, asyncio.Task] = {}  # task_id -> asyncio.Task
        self.task_callback: Optional[Callable] = None

    def set_task_callback(self, callback: Callable):
        """设置任务执行回调函数"""
        self.task_callback = callback

    def start(self):
        """启动调度器"""
        logger.info("Starting SimpleScheduler...")

        # 加载所有启用的任务
        enabled_tasks = self.task_storage.get_enabled_tasks()
        logger.info(f"Found {len(enabled_tasks)} enabled tasks")

        for task in enabled_tasks:
            self._schedule_task(task)

        # 启动调度器
        self.scheduler.start()
        logger.info("SimpleScheduler started")

    def stop(self):
        """停止调度器"""
        logger.info("Stopping SimpleScheduler...")
        self.scheduler.shutdown(wait=False)
        logger.info("SimpleScheduler stopped")

    def _schedule_task(self, task: ScheduledTask):
        """调度单个任务"""
        trigger = None

        # 根据调度类型选择触发器
        if task.schedule_type in self.CRON_TEMPLATES:
            # 预设cron模板
            cron_config = self.CRON_TEMPLATES[task.schedule_type]
            trigger = CronTrigger(**cron_config)

        elif task.schedule_type == ScheduleType.ONCE:
            # 一次性任务
            if not task.run_at:
                logger.error(f"Task {task.task_id}: schedule_type=once but run_at is not set")
                return
            trigger = DateTrigger(run_date=task.run_at)
            logger.info(f"Scheduled one-time task: {task.name} at {task.run_at}")

        elif task.schedule_type == ScheduleType.INTERVAL:
            # 自定义间隔
            if not task.interval_minutes:
                logger.error(f"Task {task.task_id}: schedule_type=interval but interval_minutes is not set")
                return
            trigger = IntervalTrigger(minutes=task.interval_minutes)
            logger.info(f"Scheduled interval task: {task.name} every {task.interval_minutes} minutes")

        elif task.schedule_type == ScheduleType.DAILY_CUSTOM:
            # 每天自定义时间
            if task.hour is None or task.minute is None:
                logger.error(f"Task {task.task_id}: schedule_type=daily_custom but hour/minute is not set")
                return
            trigger = CronTrigger(hour=task.hour, minute=task.minute)
            logger.info(f"Scheduled daily task: {task.name} at {task.hour:02d}:{task.minute:02d}")

        else:
            logger.error(f"Unknown schedule type: {task.schedule_type}")
            return

        if not trigger:
            logger.error(f"Failed to create trigger for task {task.task_id}")
            return

        # 添加到调度器
        self.scheduler.add_job(
            func=self._execute_task_wrapper,
            trigger=trigger,
            args=[task.task_id],
            id=task.task_id,
            name=task.name,
            replace_existing=True,
            misfire_grace_time=60  # 允许1分钟的延迟
        )

        # 计算下次运行时间
        next_run = trigger.get_next_fire_time(None, datetime.now())
        if next_run:
            task.next_run_at = next_run
            self.task_storage.update(task)

        logger.info(f"Scheduled task: {task.name} ({task.schedule_type}), next run: {next_run}")

    async def _execute_task_wrapper(self, task_id: str):
        """任务执行包装器（检查并发限制）"""
        # 检查并发限制
        if len(self.running_tasks) >= self.MAX_CONCURRENT_TASKS:
            logger.warning(
                f"Max concurrent tasks ({self.MAX_CONCURRENT_TASKS}) reached, "
                f"skipping task {task_id}"
            )
            return

        # 检查任务是否已在运行
        if task_id in self.running_tasks:
            logger.warning(f"Task {task_id} is already running, skipping")
            return

        # 获取任务
        task = self.task_storage.get(task_id)
        if not task:
            logger.error(f"Task {task_id} not found")
            return

        if not task.enabled:
            logger.info(f"Task {task_id} is disabled, skipping")
            return

        # 创建异步任务
        logger.info(f"Starting task execution: {task.name} ({task_id})")
        async_task = asyncio.create_task(self._execute_task(task))
        self.running_tasks[task_id] = async_task

        try:
            await async_task
        finally:
            # 清理
            if task_id in self.running_tasks:
                del self.running_tasks[task_id]

    async def _execute_task(self, task: ScheduledTask):
        """执行任务"""
        try:
            if self.task_callback:
                await self.task_callback(task)
            else:
                logger.warning(f"No task callback set, task {task.task_id} not executed")
        except Exception as e:
            logger.error(f"Error executing task {task.task_id}: {e}", exc_info=True)

    def add_task(self, task: ScheduledTask):
        """添加新任务到调度器"""
        if task.enabled:
            self._schedule_task(task)
            logger.info(f"Added task to scheduler: {task.name}")

    def remove_task(self, task_id: str):
        """从调度器移除任务"""
        try:
            self.scheduler.remove_job(task_id)
            logger.info(f"Removed task from scheduler: {task_id}")
        except Exception as e:
            logger.warning(f"Failed to remove task {task_id}: {e}")

    def update_task(self, task: ScheduledTask):
        """更新任务调度"""
        # 先移除旧的
        self.remove_task(task.task_id)

        # 如果启用，重新添加
        if task.enabled:
            self._schedule_task(task)
            logger.info(f"Updated task in scheduler: {task.name}")

    def get_next_run_time(self, task_id: str) -> Optional[datetime]:
        """获取任务的下次运行时间"""
        job = self.scheduler.get_job(task_id)
        if job:
            return job.next_run_time
        return None

    def is_task_running(self, task_id: str) -> bool:
        """检查任务是否正在运行"""
        return task_id in self.running_tasks

    def get_running_task_count(self) -> int:
        """获取正在运行的任务数量"""
        return len(self.running_tasks)

    def get_scheduled_tasks(self) -> list:
        """获取所有已调度的任务"""
        jobs = self.scheduler.get_jobs()
        return [
            {
                "task_id": job.id,
                "name": job.name,
                "next_run_time": job.next_run_time
            }
            for job in jobs
        ]
