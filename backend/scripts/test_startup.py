"""
测试服务启动和系统状态

快速验证服务是否正常启动
"""
import asyncio
import httpx

async def test_startup():
    """测试服务启动"""
    print("="*60)
    print("测试服务启动")
    print("="*60)

    # 等待服务启动
    print("\n等待服务启动...")
    await asyncio.sleep(3)

    async with httpx.AsyncClient() as client:
        # 1. 测试健康检查
        print("\n1. 健康检查 (GET /health)")
        try:
            response = await client.get("http://localhost:8000/health", timeout=5.0)
            print(f"   状态码: {response.status_code}")
            print(f"   响应: {response.json()}")
        except Exception as e:
            print(f"   错误: {e}")

        # 2. 测试系统状态
        print("\n2. 系统状态 (GET /api/system/status)")
        try:
            response = await client.get("http://localhost:8000/api/system/status", timeout=5.0)
            print(f"   状态码: {response.status_code}")
            data = response.json()

            print(f"\n   数据库: {data.get('database', {}).get('enabled')}")

            fetchers = data.get('fetchers', {})
            print(f"   Fetchers运行: {fetchers.get('scheduler_running')}")
            print(f"   已注册Fetchers: {list(fetchers.get('fetchers', {}).keys())}")

            tools = data.get('llm_tools', {})
            print(f"   LLM工具数量: {tools.get('count')}")
            print(f"   已注册工具: {tools.get('registered')}")

        except Exception as e:
            print(f"   错误: {e}")

        # 3. 测试根端点
        print("\n3. 根端点 (GET /)")
        try:
            response = await client.get("http://localhost:8000/", timeout=5.0)
            print(f"   状态码: {response.status_code}")
            data = response.json()
            print(f"   服务: {data.get('service')}")
            print(f"   版本: {data.get('version')}")
            print(f"   端点数: {len(data.get('endpoints', {}))}")
        except Exception as e:
            print(f"   错误: {e}")

    print("\n" + "="*60)
    print("测试完成")
    print("="*60)

if __name__ == "__main__":
    print("\n请先在另一个终端运行:")
    print("  cd backend")
    print("  python -m uvicorn app.main:app --reload")
    print("\n然后按回车继续测试...")
    input()

    asyncio.run(test_startup())
