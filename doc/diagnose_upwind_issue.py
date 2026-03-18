"""
诊断上风向企业分析失败的原因
"""
import asyncio
import httpx
import json

async def test_with_minimal_data():
    """使用最少的风向数据测试"""
    url = "http://180.184.91.74:9095/api/external/wind/upwind-and-map"
    
    # 测试1: 单条数据
    print("=" * 60)
    print("测试1: 单条风向数据")
    print("=" * 60)
    
    payload1 = {
        "station_name": "从化天湖",
        "winds": [
            {"time": "2025-08-09 00:00:00", "wd_deg": 175, "ws_ms": 1.4}
        ],
        "search_range_km": 5.0,
        "max_enterprises": 30,
        "top_n": 8,
        "map_type": "normal",
        "mode": "topn_mixed"
    }
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.post(url, json=payload1)
            data = response.json()
            
            print(f"状态码: {response.status_code}")
            print(f"API状态: {data.get('status')}")
            print(f"企业数量: {len(data.get('filtered', []))}")
            print(f"有地图URL: {bool(data.get('public_url'))}")
            
            if len(data.get('filtered', [])) == 0:
                print("⚠️ 警告: 单条数据返回0个企业")
            else:
                print("✅ 单条数据正常返回企业")
                
        except Exception as e:
            print(f"❌ 错误: {e}")
    
    print("\n" + "=" * 60)
    print("测试2: 空风向数据")
    print("=" * 60)
    
    payload2 = {
        "station_name": "从化天湖",
        "winds": [],  # 空数组
        "search_range_km": 5.0,
        "max_enterprises": 30,
        "top_n": 8,
        "map_type": "normal",
        "mode": "topn_mixed"
    }
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.post(url, json=payload2)
            data = response.json()
            
            print(f"状态码: {response.status_code}")
            print(f"API状态: {data.get('status')}")
            print(f"企业数量: {len(data.get('filtered', []))}")
            
            if response.status_code != 200:
                print(f"⚠️ API返回错误: {data}")
            elif len(data.get('filtered', [])) == 0:
                print("⚠️ 空数据返回0个企业（预期行为）")
                
        except Exception as e:
            print(f"❌ 错误: {e}")
    
    print("\n" + "=" * 60)
    print("测试3: 错误的站点名称")
    print("=" * 60)
    
    payload3 = {
        "station_name": "不存在的站点",
        "winds": [
            {"time": "2025-08-09 00:00:00", "wd_deg": 175, "ws_ms": 1.4}
        ],
        "search_range_km": 5.0,
        "max_enterprises": 30,
        "top_n": 8,
        "map_type": "normal",
        "mode": "topn_mixed"
    }
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.post(url, json=payload3)
            data = response.json()
            
            print(f"状态码: {response.status_code}")
            print(f"API状态: {data.get('status')}")
            print(f"企业数量: {len(data.get('filtered', []))}")
            
            if data.get('status') == 'error':
                print(f"⚠️ API返回错误: {data.get('message')}")
            elif len(data.get('filtered', [])) == 0:
                print("⚠️ 错误站点名返回0个企业")
                
        except Exception as e:
            print(f"❌ 错误: {e}")
    
    print("\n" + "=" * 60)
    print("诊断总结")
    print("=" * 60)
    print("""
可能的失败原因：
1. 气象数据为空或格式不正确 → winds数组为空
2. 气象数据被过滤掉 → format_weather_to_winds返回空数组
3. 站点名称不匹配 → API找不到站点坐标
4. 后端捕获了异常但没有正确传递错误信息

建议检查：
1. 查看后端日志中的 upwind_api_request 日志
2. 检查 winds_count 是否为0
3. 检查气象数据的字段名是否正确（windDirection, windSpeed, timePoint）
    """)

if __name__ == "__main__":
    asyncio.run(test_with_minimal_data())

