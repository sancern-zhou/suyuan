"""
测试API 9096 - 济宁市火炬城站点2026-01-14小时空气质量数据
"""
import asyncio
import json
from app.utils.http_client import http_client


async def test_single_query():
    """测试单个查询"""
    url = "http://180.184.91.74:9096/api/uqp/query"
    question = "查询济宁市火炬城站点2026-01-14的小时空气质量数据"

    print(f"查询问题: {question}")
    print("=" * 60)

    response = await http_client.post(
        url,
        json_data={"question": question},
        timeout=120
    )

    # 保存完整响应
    with open("api_response_single.json", "w", encoding="utf-8") as f:
        json.dump(response, f, ensure_ascii=False, indent=2)
    print("完整响应已保存到: api_response_single.json")

    # 打印响应结构
    print("\n响应结构:")
    print(json.dumps(response, ensure_ascii=False, indent=2)[:3000])

    # 提取数据
    if isinstance(response, dict):
        data = response.get("data", {})
        result = data.get("result", {})
        items = result.get("items", [])

        print(f"\n\n获取到 {len(items)} 条记录")
        if items:
            print("\n第一条记录的所有字段:")
            for k, v in items[0].items():
                print(f"  {k}: {v}")


if __name__ == "__main__":
    asyncio.run(test_single_query())
