"""
触发快速溯源分析报告生成

Trigger Quick Trace Analysis Report Generation
"""
import asyncio
import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from app.agent.executors.quick_trace_executor import QuickTraceExecutor
from datetime import datetime
import structlog

logger = structlog.get_logger()


async def main():
    """主函数"""
    logger.info("=" * 80)
    logger.info("快速溯源分析报告生成")
    logger.info("=" * 80)

    # 创建执行器
    executor = QuickTraceExecutor()

    # 获取当前时间
    alert_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 默认参数
    city = "济宁市"
    pollutant = "PM2.5"
    alert_value = 85.0

    logger.info(
        "quick_trace_manual_trigger",
        city=city,
        pollutant=pollutant,
        alert_value=alert_value,
        alert_time=alert_time
    )

    try:
        # 执行分析
        result = await executor.execute(
            city=city,
            alert_time=alert_time,
            pollutant=pollutant,
            alert_value=alert_value
        )

        # 保存报告
        if result.get("summary_text"):
            save_result = await executor.save_report(
                summary_text=result["summary_text"],
                city=city,
                alert_time=alert_time,
                pollutant=pollutant,
                alert_value=alert_value,
                visuals=result.get("visuals", []),
                execution_time_seconds=result.get("execution_time_seconds"),
                has_trajectory=result.get("has_trajectory", False),
                warning_message=result.get("warning_message"),
            )

            logger.info(
                "report_saved",
                filepath=save_result.get("filepath"),
                db_id=save_result.get("db_id")
            )

            print(f"\n{'='*60}")
            print(f"✓ 报告生成成功！")
            print(f"{'='*60}")
            print(f"文件路径: {save_result.get('filepath')}")
            print(f"数据库ID: {save_result.get('db_id')}")
            print(f"包含轨迹分析: {result.get('has_trajectory', False)}")

            if result.get("warning_message"):
                print(f"⚠️  警告: {result.get('warning_message')}")

            print(f"\n报告预览 (前500字符):")
            print(f"{'-'*60}")
            preview = result["summary_text"][:500] + "..." if len(result["summary_text"]) > 500 else result["summary_text"]
            print(preview)
            print(f"{'-'*60}\n")

        else:
            logger.error("report_generation_failed", error="No summary text generated")
            print("❌ 报告生成失败：未生成摘要文本")

    except Exception as e:
        logger.error(
            "quick_trace_execution_failed",
            error=str(e),
            exc_info=True
        )
        print(f"❌ 执行失败: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
