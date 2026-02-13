"""
Data Fetcher Interface

数据获取后台的基础接口
"""
from abc import ABC, abstractmethod
from typing import Optional
from enum import Enum
import structlog

logger = structlog.get_logger()


class FetcherStatus(Enum):
    """Fetcher状态"""
    IDLE = "idle"
    RUNNING = "running"
    DISABLED = "disabled"
    ERROR = "error"


class DataFetcher(ABC):
    """
    数据获取后台基类

    所有定时数据获取任务都应继承此类
    """

    def __init__(
        self,
        name: str,
        description: str,
        schedule: str,  # Cron表达式
        version: str = "1.0.0"
    ):
        self.name = name
        self.description = description
        self.schedule = schedule
        self.version = version
        self.enabled = True
        self.status = FetcherStatus.IDLE

    @abstractmethod
    async def fetch_and_store(self):
        """
        获取数据并存储到数据库

        这是Fetcher的核心方法，每个Fetcher必须实现
        """
        pass

    def is_available(self) -> bool:
        """检查Fetcher是否可用"""
        return self.enabled and self.status != FetcherStatus.ERROR

    def disable(self, reason: str = ""):
        """禁用Fetcher"""
        self.enabled = False
        self.status = FetcherStatus.DISABLED
        logger.info(f"fetcher_disabled", fetcher=self.name, reason=reason)

    def enable(self):
        """启用Fetcher"""
        self.enabled = True
        self.status = FetcherStatus.IDLE
        logger.info(f"fetcher_enabled", fetcher=self.name)

    async def run(self):
        """运行Fetcher（由调度器调用）"""
        if not self.is_available():
            logger.warning(
                "fetcher_not_available",
                fetcher=self.name,
                status=self.status.value
            )
            return

        self.status = FetcherStatus.RUNNING
        logger.info("fetcher_started", fetcher=self.name)

        try:
            await self.fetch_and_store()
            self.status = FetcherStatus.IDLE
            logger.info("fetcher_completed", fetcher=self.name)
        except Exception as e:
            self.status = FetcherStatus.ERROR
            logger.error(
                "fetcher_failed",
                fetcher=self.name,
                error=str(e),
                exc_info=True
            )
