"""
启动快速溯源分析定时任务调度器

Start Quick Trace Analysis Scheduler

每天8:30自动生成报告
"""
import asyncio
import signal
import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from app.agent.executors.quick_trace_executor import DailyQuickTraceScheduler
import structlog

logger = structlog.get_logger()


async def health_check(scheduler_instance, check_interval: int = 300):
    """
    健康检查任务：定期检查调度器是否正常运行

    Args:
        scheduler_instance: APScheduler 实例
        check_interval: 检查间隔（秒），默认300秒（5分钟）
    """
    import time
    while True:
        try:
            await asyncio.sleep(check_interval)

            # 检查调度器状态
            if scheduler_instance is None:
                logger.error("scheduler_instance_is_none")
                continue

            if not scheduler_instance.running:
                logger.error("scheduler_not_running")
                continue

            # 检查任务是否存在
            job = scheduler_instance.get_job("daily_quick_trace")
            if job is None:
                logger.error("job_not_found", job_id="daily_quick_trace")
                continue

            # 打印健康状态
            timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
            logger.info(
                "scheduler_health_check",
                timestamp=timestamp,
                next_run=job.next_run_time,
                status="healthy"
            )

        except asyncio.CancelledError:
            logger.info("health_check_cancelled")
            break
        except Exception as e:
            logger.error("health_check_failed", error=str(e), exc_info=True)


async def async_main():
    """异步主函数"""
    print("=" * 80)
    print("快速溯源分析定时任务调度器")
    print("=" * 80)
    print()
    print("任务配置:")
    print("  - 执行时间: 每天 8:30 (北京时间)")
    print("  - 城市: 济宁市")
    print("  - 污染物: 从实时监测数据自动选择")
    print("  - 浓度: 从实时监测数据自动读取")
    print()
    print("数据保存:")
    print("  - 本地文件: backend_data_registry/quick_trace_reports/")
    print("  - 数据库: weather_db.quick_trace_analysis 表")
    print()
    print("按 Ctrl+C 停止调度器")
    print("=" * 80)
    print()

    # 创建调度器
    scheduler_obj = DailyQuickTraceScheduler()

    # 异步启动调度器
    scheduler_instance = await scheduler_obj.start_scheduler_async()

    if scheduler_instance is None:
        print("❌ 调度器启动失败")
        return

    print("✓ 调度器启动成功")
    print()

    # 显示下次运行时间
    try:
        job = scheduler_instance.get_job("daily_quick_trace")
        if job:
            print(f"下次运行时间: {job.next_run_time}")
            print()
    except Exception as e:
        logger.warning("failed_to_get_next_run_time", error=str(e))

    # 创建健康检查任务
    health_task = asyncio.create_task(health_check(scheduler_instance, check_interval=300))

    # 保持运行
    try:
        print("调度器正在运行，等待下次执行...")
        print("(健康检查: 每5分钟检查一次调度器状态)")
        print()

        # 定期打印心跳信息
        import time
        while True:
            await asyncio.sleep(3600)  # 每小时打印一次
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 调度器运行中...")

    except asyncio.CancelledError:
        print("\n\n收到取消信号，正在关闭调度器...")
        health_task.cancel()
        try:
            await health_task
        except asyncio.CancelledError:
            pass
        scheduler_obj.stop_scheduler()
        print("调度器已停止")


def main():
    """主函数"""
    try:
        asyncio.run(async_main())
    except KeyboardInterrupt:
        print("\n\n收到键盘中断，退出程序")


if __name__ == "__main__":
    main()
