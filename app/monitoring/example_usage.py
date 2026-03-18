"""
LLM 监控工具使用示例

展示如何在实际代码中集成监控功能
"""

import asyncio
from openai import AsyncOpenAI
from app.monitoring import get_monitor, print_report, export_to_csv

# 初始化 OpenAI 客户端（示例）
# client = AsyncOpenAI(api_key="your-key")


async def example_stream_call():
    """流式调用示例"""
    monitor = get_monitor()
    
    messages = [
        {"role": "system", "content": "你是一个专业的助手。"},
        {"role": "user", "content": "请介绍一下 Python 编程语言"}
    ]
    
    # 模拟流式调用
    # stream = await client.chat.completions.create(
    #     model="gpt-4",
    #     messages=messages,
    #     stream=True
    # )
    
    # 使用监控器跟踪
    # content = await monitor.track_stream_call(
    #     model="gpt-4",
    #     provider="openai",
    #     messages=messages,
    #     stream_generator=stream
    # )
    
    print("流式调用示例（已注释，需要配置 API key）")


async def example_non_stream_call():
    """非流式调用示例"""
    monitor = get_monitor()
    
    messages = [
        {"role": "system", "content": "你是一个专业的助手。"},
        {"role": "user", "content": "请介绍一下 Python 编程语言"}
    ]
    
    # 模拟非流式调用
    # response = await client.chat.completions.create(
    #     model="gpt-4",
    #     messages=messages
    # )
    
    # 使用监控器跟踪
    # content = await monitor.track_non_stream_call(
    #     model="gpt-4",
    #     provider="openai",
    #     messages=messages,
    #     response=response
    # )
    
    print("非流式调用示例（已注释，需要配置 API key）")


async def example_manual_record():
    """手动记录调用示例"""
    monitor = get_monitor()
    
    # 手动记录一次调用
    await monitor.record_call(
        model="gpt-4",
        provider="openai",
        input_tokens=100,
        output_tokens=200,
        ttft=0.5,  # 首字延迟 0.5 秒
        total_time=5.0,  # 总耗时 5 秒
        success=True,
        stream_mode=False
    )
    
    print("手动记录调用完成")


async def main():
    """主函数"""
    print("=" * 60)
    print("LLM 监控工具使用示例")
    print("=" * 60)
    
    # 示例 1: 手动记录
    await example_manual_record()
    
    # 示例 2: 流式调用（需要配置 API key）
    # await example_stream_call()
    
    # 示例 3: 非流式调用（需要配置 API key）
    # await example_non_stream_call()
    
    # 打印统计报告
    print("\n" + "=" * 60)
    print("统计报告")
    print("=" * 60)
    print_report()
    
    # 导出数据
    export_to_csv("llm_stats_example.csv")
    print("\n数据已导出到: llm_stats_example.csv")


if __name__ == "__main__":
    asyncio.run(main())

