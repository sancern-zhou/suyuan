"""
Fetcher Scheduler

管理所有数据获取后台的调度器
"""
from typing import List, Dict, Optional
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
import structlog

from app.fetchers.base.fetcher_interface import DataFetcher, FetcherStatus

logger = structlog.get_logger()


class FetcherScheduler:
    """
    Fetcher调度器

    功能：
    - 注册所有Fetchers
    - 根据Cron表达式调度运行
    - 监控运行状态
    - 提供统一的启动/停止接口
    """

    def __init__(self):
        self.scheduler = AsyncIOScheduler()
        self.fetchers: Dict[str, DataFetcher] = {}
        self._running = False

    def register(self, fetcher: DataFetcher):
        """
        注册一个Fetcher

        Args:
            fetcher: DataFetcher实例
        """
        if fetcher.name in self.fetchers:
            logger.warning(
                "fetcher_already_registered",
                fetcher=fetcher.name,
                action="replacing"
            )

        self.fetchers[fetcher.name] = fetcher

        # 添加到调度器
        self.scheduler.add_job(
            fetcher.run,
            CronTrigger.from_crontab(fetcher.schedule),
            id=fetcher.name,
            name=fetcher.description,
            replace_existing=True
        )

        logger.info(
            "fetcher_registered",
            fetcher=fetcher.name,
            schedule=fetcher.schedule,
            description=fetcher.description
        )

    def unregister(self, fetcher_name: str):
        """
        注销一个Fetcher

        Args:
            fetcher_name: Fetcher名称
        """
        if fetcher_name in self.fetchers:
            # 从调度器移除
            self.scheduler.remove_job(fetcher_name)
            # 从字典移除
            del self.fetchers[fetcher_name]

            logger.info("fetcher_unregistered", fetcher=fetcher_name)
        else:
            logger.warning("fetcher_not_found", fetcher=fetcher_name)

    def start(self):
        """启动调度器"""
        if self._running:
            logger.warning("scheduler_already_running")
            return

        logger.info(
            "scheduler_starting",
            fetchers=list(self.fetchers.keys()),
            count=len(self.fetchers)
        )

        self.scheduler.start()
        self._running = True

        logger.info("scheduler_started")

    def stop(self):
        """停止调度器"""
        if not self._running:
            logger.warning("scheduler_not_running")
            return

        logger.info("scheduler_stopping")

        self.scheduler.shutdown(wait=True)
        self._running = False

        logger.info("scheduler_stopped")

    def pause(self, fetcher_name: str):
        """
        暂停指定Fetcher

        Args:
            fetcher_name: Fetcher名称
        """
        if fetcher_name in self.fetchers:
            self.scheduler.pause_job(fetcher_name)
            self.fetchers[fetcher_name].enabled = False

            logger.info("fetcher_paused", fetcher=fetcher_name)
        else:
            logger.warning("fetcher_not_found", fetcher=fetcher_name)

    def resume(self, fetcher_name: str):
        """
        恢复指定Fetcher

        Args:
            fetcher_name: Fetcher名称
        """
        if fetcher_name in self.fetchers:
            self.scheduler.resume_job(fetcher_name)
            self.fetchers[fetcher_name].enabled = True

            logger.info("fetcher_resumed", fetcher=fetcher_name)
        else:
            logger.warning("fetcher_not_found", fetcher=fetcher_name)

    def get_status(self) -> Dict[str, Dict]:
        """
        获取所有Fetchers的状态

        Returns:
            Dict: 状态字典
        """
        status = {
            "scheduler_running": self._running,
            "fetchers": {}
        }

        for name, fetcher in self.fetchers.items():
            status["fetchers"][name] = {
                "name": name,
                "description": fetcher.description,
                "schedule": fetcher.schedule,
                "enabled": fetcher.enabled,
                "status": fetcher.status.value,
                "version": fetcher.version
            }

        return status

    def get_fetcher(self, fetcher_name: str) -> Optional[DataFetcher]:
        """
        获取指定Fetcher

        Args:
            fetcher_name: Fetcher名称

        Returns:
            DataFetcher: Fetcher实例，不存在时返回None
        """
        return self.fetchers.get(fetcher_name)

    def list_fetchers(self) -> List[str]:
        """
        列出所有已注册的Fetchers

        Returns:
            List[str]: Fetcher名称列表
        """
        return list(self.fetchers.keys())

    async def run_now(self, fetcher_name: str):
        """
        立即运行指定Fetcher（不等待调度时间）

        Args:
            fetcher_name: Fetcher名称
        """
        fetcher = self.get_fetcher(fetcher_name)

        if not fetcher:
            logger.error("fetcher_not_found", fetcher=fetcher_name)
            return

        logger.info("fetcher_manual_run", fetcher=fetcher_name)

        try:
            await fetcher.run()
        except Exception as e:
            logger.error(
                "fetcher_manual_run_failed",
                fetcher=fetcher_name,
                error=str(e),
                exc_info=True
            )

    def is_running(self) -> bool:
        """
        检查调度器是否正在运行

        Returns:
            bool: 是否运行中
        """
        return self._running
