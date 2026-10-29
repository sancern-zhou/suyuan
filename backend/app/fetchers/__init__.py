"""
Data Fetching Backend

定时从外部API爬取数据，存入云数据库的后台程序
"""

from app.fetchers.base.scheduler import FetcherScheduler


def create_scheduler() -> FetcherScheduler:
    """
    创建并配置Fetcher调度器

    Returns:
        FetcherScheduler实例
    """
    scheduler = FetcherScheduler()

    # Keep manual/API scheduler creation consistent with lifecycle startup.
    from app.project_config.loader import load_project_context
    from app.services.lifecycle_manager import _configured_fetchers
    from config.settings import settings

    context = load_project_context(settings.project_id)
    for fetcher in _configured_fetchers(context):
        scheduler.register(fetcher)

    return scheduler


__all__ = ['create_scheduler', 'FetcherScheduler']
