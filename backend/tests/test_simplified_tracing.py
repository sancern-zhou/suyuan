"""
测试简化后的多专家溯源系统

验证普通溯源模式是否正常工作
"""
import asyncio
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.agent.core.structured_query_parser import StructuredQueryParser
from app.agent.core.expert_plan_generator import ExpertPlanGenerator


async def test_query_parsing():
    """测试查询解析"""
    print("=" * 60)
    print("测试1: 查询解析（StructuredQueryParser）")
    print("=" * 60)

    parser = StructuredQueryParser()

    test_queries = [
        "对昨天韶关市进行颗粒物溯源分析",
        "综合分析广州O3污染溯源",
        "分析深圳昨天的PM2.5和PM10污染来源"
    ]

    for query in test_queries:
        print(f"\n查询: {query}")
        result = await parser.parse(query)
        print(f"  位置: {result.location}")
        print(f"  坐标: ({result.lat}, {result.lon})")
        print(f"  时间: {result.start_time} ~ {result.end_time}")
        print(f"  污染物: {result.pollutants}")
        print(f"  置信度: {result.parse_confidence}")
        # 验证没有 analysis_type 字段
        assert not hasattr(result, 'analysis_type'), "不应该有 analysis_type 字段"
        assert not hasattr(result, 'use_deep_tracing'), "不应该有 use_deep_tracing 字段"
        print("  ✓ 字段验证通过")

    print("\n" + "=" * 60)


async def test_plan_generation():
    """测试计划生成"""
    print("\n测试2: 计划生成（ExpertPlanGenerator）")
    print("=" * 60)

    parser = StructuredQueryParser()
    plan_gen = ExpertPlanGenerator()

    # 测试颗粒物溯源
    query = await parser.parse("对昨天韶关市进行颗粒物溯源分析")
    experts = plan_gen.determine_required_experts(query)

    print(f"\n查询: {query.original_query}")
    print(f"污染物: {query.pollutants}")
    print(f"选择的专家: {experts}")

    # 生成专家任务
    tasks = plan_gen.generate(query)
    for expert_type, task in tasks.items():
        print(f"\n专家: {expert_type}")
        print(f"  任务描述: {task.task_description}")
        print(f"  工具数量: {len(task.tool_plan)}")
        for i, tool in enumerate(task.tool_plan):
            print(f"    {i+1}. {tool['tool']}: {tool.get('purpose', '')}")

    print("\n" + "=" * 60)


async def test_ozone_tracing():
    """测试臭氧溯源"""
    print("\n测试3: 臭氧溯源计划")
    print("=" * 60)

    parser = StructuredQueryParser()
    plan_gen = ExpertPlanGenerator()

    query = await parser.parse("综合分析广州O3污染溯源")
    tasks = plan_gen.generate(query)

    component_task = tasks.get("component")
    if component_task:
        print(f"\n组分专家工具计划（臭氧溯源）:")
        for i, tool in enumerate(component_task.tool_plan):
            print(f"  {i+1}. {tool['tool']}")
            print(f"     目的: {tool.get('purpose', '')}")
            depends = tool.get('depends_on', [])
            if depends:
                print(f"     依赖: {depends}")

    print("\n" + "=" * 60)


async def test_pm_tracing():
    """测试颗粒物溯源"""
    print("\n测试4: 颗粒物溯源计划")
    print("=" * 60)

    parser = StructuredQueryParser()
    plan_gen = ExpertPlanGenerator()

    query = await parser.parse("韶关市PM2.5污染溯源分析")
    tasks = plan_gen.generate(query)

    component_task = tasks.get("component")
    if component_task:
        print(f"\n组分专家工具计划（颗粒物溯源）:")
        for i, tool in enumerate(component_task.tool_plan):
            print(f"  {i+1}. {tool['tool']}")
            print(f"     目的: {tool.get('purpose', '')}")
            depends = tool.get('depends_on', [])
            if depends:
                print(f"     依赖: {depends}")

    print("\n" + "=" * 60)


async def main():
    """运行所有测试"""
    try:
        await test_query_parsing()
        await test_plan_generation()
        await test_ozone_tracing()
        await test_pm_tracing()

        print("\n" + "=" * 60)
        print("所有测试通过！")
        print("=" * 60)
        print("\n简化后的系统特性:")
        print("  1. 所有查询统一为普通溯源模式")
        print("  2. 根据污染物类型自动选择工具链")
        print("  3. 气象专家: 基础气象 + 轨迹 + 上风向企业")
        print("  4. 臭氧专家: VOCs + PMF + OBM")
        print("  5. 颗粒物专家: 5种组分 + PMF")
        print("=" * 60)

    except Exception as e:
        print(f"\n测试失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
