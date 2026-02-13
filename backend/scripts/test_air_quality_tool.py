"""
测试空气质量查询工具

验证 GetAirQualityTool 是否正常工作
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.tools.query.get_air_quality import GetAirQualityTool
import json

async def test_air_quality_tool():
    """测试空气质量查询工具"""
    print("="*60)
    print("测试空气质量查询工具")
    print("="*60)

    tool = GetAirQualityTool()

    # 测试1: 查询惠州昨日小时空气质量
    print("\n测试1: 惠州昨日小时空气质量")
    print("-"*60)

    result = await tool.execute(
        city="惠州",
        time_range="昨日",
        granularity="小时"
    )

    if result.get("success"):
        print("[OK] 调用成功")
        print(f"   查询: {result['query']['text']}")
        print(f"   城市: {result['query']['city']}")
        print(f"   时间范围: {result['query']['time_range']}")
        print(f"   粒度: {result['query']['granularity']}")
        print(f"   对话ID: {result['conversation_id']}")
        print(f"\n   响应摘要:")
        answer = result.get("raw_answer", "")
        # 显示前300个字符，避免编码问题
        try:
            print(f"   {answer[:300]}...")
        except UnicodeEncodeError:
            print(f"   [响应包含特殊字符，长度: {len(answer)} 字符]")

        # 如果有结构化数据，显示
        if "structured_data" in result:
            print(f"\n   结构化数据:")
            try:
                print(f"   {json.dumps(result['structured_data'], indent=2, ensure_ascii=False)[:500]}...")
            except (UnicodeEncodeError, TypeError):
                print(f"   [结构化数据包含特殊字符]")
    else:
        print(f"[ERROR] 调用失败: {result.get('error')}")

    # 测试2: 查询广州今日小时空气质量
    print("\n" + "="*60)
    print("测试2: 广州今日小时空气质量")
    print("-"*60)

    result2 = await tool.execute(
        city="广州",
        time_range="今日",
        granularity="小时"
    )

    if result2.get("success"):
        print("[OK] 调用成功")
        print(f"   查询: {result2['query']['text']}")
        answer = result2.get("raw_answer", "")
        print(f"   响应长度: {len(answer)} 字符")
    else:
        print(f"[ERROR] 调用失败: {result2.get('error')}")

    # 测试3: 查询深圳本月日空气质量
    print("\n" + "="*60)
    print("测试3: 深圳本月日空气质量")
    print("-"*60)

    result3 = await tool.execute(
        city="深圳",
        time_range="本月",
        granularity="日"
    )

    if result3.get("success"):
        print("[OK] 调用成功")
        print(f"   查询: {result3['query']['text']}")
        answer = result3.get("raw_answer", "")
        print(f"   响应长度: {len(answer)} 字符")
    else:
        print(f"[ERROR] 调用失败: {result3.get('error')}")

    # 测试4: 查询北京去年年空气质量
    print("\n" + "="*60)
    print("测试4: 北京去年年空气质量")
    print("-"*60)

    result4 = await tool.execute(
        city="北京",
        time_range="去年",
        granularity="年"
    )

    if result4.get("success"):
        print("[OK] 调用成功")
        print(f"   查询: {result4['query']['text']}")
        answer = result4.get("raw_answer", "")
        print(f"   响应长度: {len(answer)} 字符")
    else:
        print(f"[ERROR] 调用失败: {result4.get('error')}")

    # 测试5: 获取Function Schema
    print("\n" + "="*60)
    print("测试5: Function Calling Schema")
    print("-"*60)

    schema = tool.get_function_schema()
    print("[OK] Function Schema:")
    print(f"   Name: {schema['name']}")
    print(f"   Description: {schema['description']}")
    print(f"   Parameters: {list(schema['parameters']['properties'].keys())}")
    print(f"   Required: {schema['parameters']['required']}")

    # 测试6: 测试 Dify Client 直接调用
    print("\n" + "="*60)
    print("测试6: Dify Client 直接调用")
    print("-"*60)

    from app.external_apis.dify_client import DifyClient
    client = DifyClient()

    print("   正在调用 Dify API...")
    response = await client.chat_messages(
        query="惠州昨日小时空气质量",
        response_mode="blocking"
    )

    print("[OK] Dify API 直接调用成功")
    print(f"   Conversation ID: {response.get('conversation_id')}")
    print(f"   Message ID: {response.get('id')}")
    answer_text = response.get('answer', '')
    try:
        print(f"   Answer (前200字符): {answer_text[:200]}...")
    except UnicodeEncodeError:
        print(f"   Answer 长度: {len(answer_text)} 字符 [包含特殊字符]")

    print("\n" + "="*60)
    print("测试完成")
    print("="*60)


if __name__ == "__main__":
    asyncio.run(test_air_quality_tool())
