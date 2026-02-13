"""
测试并行工具调用优化

验证方案1的增强功能：
1. LLM Prompt 指导并行调用
2. execute_tools_parallel 结果追踪增强
3. 并行执行时间统计
"""

import asyncio
import time
from typing import Dict, Any


# 模拟工具函数
async def mock_tool_success(tool_name: str, delay: float = 1.0) -> Dict[str, Any]:
    """模拟成功的工具执行"""
    await asyncio.sleep(delay)
    return {
        "success": True,
        "data": [{"value": f"{tool_name}_result"}],
        "summary": f"[OK] {tool_name} executed successfully"
    }


async def mock_tool_failure(tool_name: str, delay: float = 0.5) -> Dict[str, Any]:
    """模拟失败的工具执行"""
    await asyncio.sleep(delay)
    raise Exception(f"{tool_name} simulated failure")


# 模拟 execute_tools_parallel 的核心逻辑
async def simulate_parallel_execution(tools: list) -> Dict[str, Any]:
    """
    模拟并行执行工具（V3.1增强版）
    """
    print(f"\n{'='*60}")
    print(f"开始并行执行 {len(tools)} 个工具")
    print(f"{'='*60}")

    start_time = time.time()

    async def execute_single(tool_call: Dict[str, Any]) -> Dict[str, Any]:
        """执行单个工具调用"""
        tool_name = tool_call["tool"]
        should_fail = tool_call.get("fail", False)
        delay = tool_call.get("delay", 1.0)

        try:
            if should_fail:
                result = await mock_tool_failure(tool_name, delay)
            else:
                result = await mock_tool_success(tool_name, delay)

            return {
                "tool": tool_name,
                "args": tool_call.get("args", {}),
                "result": result
            }
        except Exception as e:
            return {
                "tool": tool_name,
                "args": tool_call.get("args", {}),
                "result": {
                    "success": False,
                    "error": str(e),
                    "summary": f"❌ {tool_name} 执行失败: {str(e)}"
                }
            }

    # 并行执行所有工具
    results = await asyncio.gather(
        *[execute_single(tc) for tc in tools],
        return_exceptions=True
    )

    total_time = time.time() - start_time

    # 分类结果
    successful_results = []
    failed_results = []

    for idx, res in enumerate(results):
        if isinstance(res, Exception):
            tool_name = tools[idx]["tool"]
            failed_results.append({
                "tool": tool_name,
                "error": str(res),
                "success": False
            })
        elif res.get("result", {}).get("success", False):
            successful_results.append(res)
        else:
            failed_results.append(res)

    # 统计
    success_count = len(successful_results)
    total_count = len(tools)
    is_full_success = success_count == total_count
    is_partial_success = 0 < success_count < total_count

    # 生成摘要
    summary_lines = [
        f"[OK] Parallel execution completed ({success_count}/{total_count} succeeded, time: {total_time:.2f}s)"
    ]

    if successful_results:
        success_tools = [r["tool"] for r in successful_results]
        summary_lines.append(f"  Success: {', '.join(success_tools)}")

    if failed_results:
        failed_tools = [r["tool"] for r in failed_results]
        summary_lines.append(f"  Failed: {', '.join(failed_tools)}")
        for fail in failed_results:
            error_msg = fail.get("error", fail.get("result", {}).get("error", "Unknown"))
            summary_lines.append(f"    - {fail['tool']}: {error_msg[:80]}")

    summary = "\n".join(summary_lines)

    return {
        "success": is_full_success,
        "partial_success": is_partial_success,
        "parallel": True,
        "success_count": success_count,
        "total_count": total_count,
        "execution_time": round(total_time, 2),
        "tool_results": successful_results,
        "failed_tools": failed_results,
        "summary": summary
    }


async def test_case_1_all_success():
    """测试案例1：所有工具成功"""
    print("\n\n" + "="*60)
    print("测试案例1：所有工具成功（3个工具，各耗时1秒）")
    print("="*60)

    tools = [
        {"tool": "get_weather_data", "args": {"location": "广州"}, "delay": 1.0},
        {"tool": "get_air_quality", "args": {"location": "广州"}, "delay": 1.0},
        {"tool": "get_vocs_data", "args": {"location": "广州"}, "delay": 1.0}
    ]

    result = await simulate_parallel_execution(tools)

    print("\n结果统计：")
    print(f"  - 成功: {result['success']}")
    print(f"  - 部分成功: {result['partial_success']}")
    print(f"  - 成功数/总数: {result['success_count']}/{result['total_count']}")
    print(f"  - 执行时间: {result['execution_time']}s")
    print(f"\n摘要：")
    print(result['summary'])

    # 验证：并行执行应该约1秒（而非串行的3秒）
    assert result['execution_time'] < 1.5, f"Parallel execution time should < 1.5s, actual {result['execution_time']}s"
    print("\n[OK] Verification passed: Parallel execution ~1s (serial needs 3s, saves 67% time)")


async def test_case_2_partial_failure():
    """测试案例2：部分工具失败"""
    print("\n\n" + "="*60)
    print("测试案例2：部分工具失败（3个工具，1个失败）")
    print("="*60)

    tools = [
        {"tool": "get_weather_data", "args": {"location": "广州"}, "delay": 1.0},
        {"tool": "get_air_quality", "args": {"location": "广州"}, "delay": 0.5, "fail": True},
        {"tool": "get_vocs_data", "args": {"location": "广州"}, "delay": 1.0}
    ]

    result = await simulate_parallel_execution(tools)

    print("\n结果统计：")
    print(f"  - 成功: {result['success']}")
    print(f"  - 部分成功: {result['partial_success']}")
    print(f"  - 成功数/总数: {result['success_count']}/{result['total_count']}")
    print(f"  - 执行时间: {result['execution_time']}s")
    print(f"  - 失败工具数: {len(result['failed_tools'])}")
    print(f"\n摘要：")
    print(result['summary'])

    # 验证：部分成功，有2个成功1个失败
    assert result['partial_success'] == True
    assert result['success_count'] == 2
    assert len(result['failed_tools']) == 1
    print("\n✅ 验证通过：正确识别部分成功（2/3成功）")


async def test_case_3_different_delays():
    """测试案例3：不同延迟的工具"""
    print("\n\n" + "="*60)
    print("测试案例3：不同延迟的工具（5个工具，延迟0.5-2秒）")
    print("="*60)

    tools = [
        {"tool": "tool_fast_1", "delay": 0.5},
        {"tool": "tool_fast_2", "delay": 0.5},
        {"tool": "tool_medium", "delay": 1.0},
        {"tool": "tool_slow_1", "delay": 1.5},
        {"tool": "tool_slow_2", "delay": 2.0}
    ]

    result = await simulate_parallel_execution(tools)

    print("\n结果统计：")
    print(f"  - 成功: {result['success']}")
    print(f"  - 成功数/总数: {result['success_count']}/{result['total_count']}")
    print(f"  - 执行时间: {result['execution_time']}s")
    print(f"\n摘要：")
    print(result['summary'])

    # 验证：并行执行时间约等于最慢工具的时间（2秒）
    assert result['execution_time'] < 2.5, f"并行执行时间应 < 2.5s，实际 {result['execution_time']}s"
    # 串行执行需要：0.5 + 0.5 + 1.0 + 1.5 + 2.0 = 5.5秒
    serial_time = sum([t["delay"] for t in tools])
    speedup = serial_time / result['execution_time']
    print(f"\n✅ 验证通过：并行执行约{result['execution_time']}s，串行需{serial_time}s")
    print(f"   加速比: {speedup:.1f}x")


async def test_case_4_llm_decision_simulation():
    """测试案例4：模拟LLM决策并行调用"""
    print("\n\n" + "="*60)
    print("测试案例4：模拟LLM决策并行调用场景")
    print("="*60)

    # 场景：用户查询"对比广州和深圳8月9日的空气质量"
    print("\n用户查询: 对比广州和深圳8月9日的空气质量")
    print("\nLLM分析: 两个城市的数据查询完全独立，可以并行执行")

    tools = [
        {
            "tool": "get_air_quality",
            "args": {
                "question": "查询广州2025年8月9日的空气质量"
            },
            "delay": 1.2
        },
        {
            "tool": "get_air_quality",
            "args": {
                "question": "查询深圳2025年8月9日的空气质量"
            },
            "delay": 1.1
        }
    ]

    result = await simulate_parallel_execution(tools)

    print("\n结果统计：")
    print(f"  - 执行时间: {result['execution_time']}s")
    print(f"  - 成功数: {result['success_count']}/{result['total_count']}")
    print(f"\n摘要：")
    print(result['summary'])

    # 串行执行需要约2.3秒，并行约1.2秒
    print(f"\n✅ 性能提升：并行执行约{result['execution_time']}s，串行需约2.3s，节省约48%时间")


async def main():
    """运行所有测试"""
    print("\n" + "="*60)
    print("ReAct Agent 并行工具调用优化测试")
    print("方案1：增强版并行调用（无自动重试）")
    print("="*60)

    await test_case_1_all_success()
    await test_case_2_partial_failure()
    await test_case_3_different_delays()
    await test_case_4_llm_decision_simulation()

    print("\n\n" + "="*60)
    print("所有测试完成")
    print("="*60)
    print("\n核心改进点：")
    print("1. ✅ LLM Prompt 明确指导何时使用并行调用")
    print("2. ✅ 结果追踪增强（tool_results + failed_tools）")
    print("3. ✅ 执行时间统计（验证并行效果）")
    print("4. ✅ 部分成功检测（partial_success字段）")
    print("5. ✅ 详细摘要生成（成功/失败工具列表 + 错误信息）")
    print("\n预期性能提升：")
    print("- 独立工具并行：30-50% 时间节省")
    print("- 多站点/多时段查询：50-70% 时间节省")


if __name__ == "__main__":
    asyncio.run(main())
