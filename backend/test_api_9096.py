"""
测试API 9096的实际响应格式
"""
import asyncio
import json
from app.utils.http_client import http_client


async def test_api_9096():
    """测试API 9096的响应格式"""

    url = "http://180.184.91.74:9096/api/uqp/query"

    # 测试问题 - 查询济宁市各区县的污染物数据
    test_questions = [
        "查询济宁市各区县2026-01-14的PM2.5、PM10、O3、NO2、SO2、CO、AQI小时数据",
        "查询济宁市火炬城站点2026-01-14的空气质量数据",
        "济宁市各区县空气质量排名，时间2026-01-14",
    ]

    for i, question in enumerate(test_questions):
        print(f"\n{'='*60}")
        print(f"测试问题 {i+1}: {question}")
        print(f"{'='*60}")

        try:
            response = await http_client.post(
                url,
                json_data={"question": question},
                timeout=120
            )

            print(f"\n响应类型: {type(response)}")
            print(f"响应顶层 keys: {response.keys() if isinstance(response, dict) else 'N/A'}")

            # 保存完整响应到文件
            with open(f"api_response_{i+1}.json", "w", encoding="utf-8") as f:
                json.dump(response, f, ensure_ascii=False, indent=2)
            print(f"完整响应已保存到: api_response_{i+1}.json")

            # 分析嵌套结构
            if isinstance(response, dict):
                print("\n嵌套结构分析:")
                _analyze_response(response, indent=0)

            # 打印前3条记录
            records = _extract_records(response)
            if records:
                print(f"\n获取到 {len(records)} 条记录")
                print(f"第一条记录的字段: {list(records[0].keys()) if records else 'N/A'}")

                # 检查是否有species_data
                if records and "species_data" in records[0]:
                    print(f"\nspecies_data 内容:")
                    print(json.dumps(records[0]["species_data"], ensure_ascii=False, indent=2))
            else:
                print("\n未能提取到记录")

        except Exception as e:
            print(f"请求失败: {e}")


def _analyze_response(obj, indent=0):
    """递归分析响应结构"""
    prefix = "  " * indent

    if isinstance(obj, dict):
        for k, v in list(obj.items())[:10]:  # 只显示前10个key
            if isinstance(v, (dict, list)):
                print(f"{prefix}{k}: {type(v).__name__} ({len(v) if isinstance(v, (dict, list)) else 'N/A'})")
                if indent < 3:
                    _analyze_response(v, indent + 1)
            else:
                print(f"{prefix}{k}: {type(v).__name__} = {str(v)[:50]}")
    elif isinstance(obj, list):
        for i, item in enumerate(obj[:3]):  # 只显示前3个元素
            print(f"{prefix}[{i}]: {type(item).__name__}")
            if indent < 3:
                _analyze_response(item, indent + 1)


def _extract_records(payload):
    """从响应中提取记录"""
    if isinstance(payload, list):
        return payload

    if isinstance(payload, dict):
        # 尝试多种路径
        for key in ["result", "data", "results", "list", "dataList"]:
            if key in payload:
                value = payload[key]
                if isinstance(value, list):
                    return value
                elif isinstance(value, dict) and "list" in value:
                    return value["list"]

        # 递归查找
        for value in payload.values():
            if isinstance(value, (dict, list)):
                result = _extract_records(value)
                if result:
                    return result

    return []


if __name__ == "__main__":
    print("测试API 9096响应格式")
    print("="*60)
    asyncio.run(test_api_9096())
