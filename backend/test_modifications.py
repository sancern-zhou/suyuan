"""
测试修改后的功能：
1. 未来7天预报数据（包含今天，共计7条）
2. LLM提示词包含空气质量预报准确性评估
"""
import asyncio
import sys
sys.path.insert(0, 'D:\\溯源\\backend')

from app.agent.executors.quick_trace_executor import QuickTraceExecutor
from datetime import date


async def test_modifications():
    """测试两个修改点"""
    executor = QuickTraceExecutor()

    print("=" * 80)
    print("测试修改1: 未来7天预报数据（包含今天）")
    print("=" * 80)

    # 测试空气质量数据查询
    city = "济宁市"
    result = await executor._get_air_quality_from_db(city)

    print(f"\n查询结果:")
    print(f"  状态: {result['status']}")
    print(f"  数据条数: {len(result.get('data', []))}")

    # 统计预报数据
    forecast_count = 0
    history_count = 0
    forecast_dates = []

    for record in result.get('data', []):
        data_type = record.get('metadata', {}).get('data_type', '')
        if data_type == 'forecast':
            forecast_count += 1
            forecast_dates.append(record.get('timestamp', ''))
        elif data_type == 'history':
            history_count += 1

    print(f"\n预报数据: {forecast_count} 条")
    if forecast_dates:
        print(f"  预报日期: {', '.join(forecast_dates)}")

    print(f"\n历史数据: {history_count} 条")

    # 检查是否包含今天
    today_str = date.today().strftime("%Y-%m-%d")
    if today_str in forecast_dates:
        print(f"\n[OK] 包含今天({today_str})的预报数据")
    else:
        print(f"\n[WARNING] 不包含今天({today_str})的预报数据")

    if forecast_count >= 7:
        print(f"[OK] 预报数据条数正确: {forecast_count} 条 (>= 7)")
    else:
        print(f"[WARNING] 预报数据条数不足: {forecast_count} 条 (< 7)")

    print("\n" + "=" * 80)
    print("测试修改2: LLM提示词包含空气质量预报准确性评估")
    print("=" * 80)

    # 获取LLM提示词模板
    prompt = executor._build_prompt(
        city=city,
        pollutant="PM2.5",
        alert_value=115.0,
        alert_time="2026-02-03 12:00:00",
        summaries={}
    )

    # 检查是否包含关键内容
    checks = {
        "包含'4.3 空气质量预报准确性评估'": "4.3 空气质量预报准确性评估" in prompt,
        "包含'气象条件匹配度分析'": "气象条件匹配度分析" in prompt,
        "包含'预报合理性检验'": "预报合理性检验" in prompt,
        "包含'异常值识别'": "异常值识别" in prompt,
        "包含'预报可信度评级'": "预报可信度评级" in prompt,
    }

    all_passed = True
    for check_name, result in checks.items():
        status = "[OK]" if result else "[FAIL]"
        print(f"{status} {check_name}")
        if not result:
            all_passed = False

    # 显示相关章节
    if "### 4.3 空气质量预报准确性评估" in prompt:
        idx = prompt.find("### 4.3")
        section = prompt[idx:idx+500]
        print(f"\n新增章节内容预览:")
        print("-" * 80)
        print(section[:300] + "...")
        print("-" * 80)

    print("\n" + "=" * 80)
    print("总结")
    print("=" * 80)

    if forecast_count >= 7 and today_str in forecast_dates and all_passed:
        print("[SUCCESS] 所有修改成功!")
        print(f"  1. 未来7天预报数据: {forecast_count} 条 (包含今天)")
        print(f"  2. LLM提示词: 包含空气质量预报准确性评估章节")
    else:
        print("[PARTIAL] 部分修改成功")
        if forecast_count < 7 or today_str not in forecast_dates:
            print(f"  [X] 预报数据查询需要调整")
        if not all_passed:
            print(f"  [X] LLM提示词修改可能不完整")


if __name__ == "__main__":
    asyncio.run(test_modifications())
