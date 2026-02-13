"""
测试快速溯源API
"""
import asyncio
import sys
import os

# 添加项目路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.agent.executors.quick_trace_executor import QuickTraceExecutor
import structlog

# 配置日志
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.dev.ConsoleRenderer(colors=True)
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
)

logger = structlog.get_logger()


async def test_quick_trace():
    """测试快速溯源"""
    executor = QuickTraceExecutor()

    logger.info("开始测试快速溯源API")

    try:
        result = await executor.execute(
            city="济宁市",
            alert_time="2026-02-03 00:30:00",
            pollutant="PM2.5",
            alert_value=130.0
        )

        logger.info(
            "测试完成",
            has_trajectory=result.get("has_trajectory"),
            warning=result.get("warning_message")
        )

        # 保存报告到文件以避免控制台编码问题
        output_file = "quick_trace_test_output.md"
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(result["summary_text"])

        print(f"\n报告已保存到: {output_file}")
        print(f"包含轨迹分析: {result.get('has_trajectory')}")
        print(f"警告信息: {result.get('warning_message')}")

    except Exception as e:
        logger.error("测试失败", error=str(e), exc_info=True)


if __name__ == "__main__":
    asyncio.run(test_quick_trace())
