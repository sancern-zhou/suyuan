"""
测试本地LLM调用修复
"""
import asyncio
import os
import httpx

async def test_local_llm():
    """测试本地LLM API调用"""
    base_url = os.getenv("QWEN_BASE_URL", "https://public-1960182902053687299-iaaa.ksai.scnet.cn:58043/v1")
    model = os.getenv("QWEN_MODEL", "qwen3")

    print(f"Testing local LLM endpoint...")
    print(f"Base URL: {base_url}")
    print(f"Model: {model}")
    print(f"Full endpoint: {base_url}/chat/completions")
    print("-" * 50)

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{base_url}/chat/completions",
                headers={"Content-Type": "application/json"},
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": "你是测试助手。"},
                        {"role": "user", "content": "请简单回复：测试成功"}
                    ],
                    "max_tokens": 50,
                    "temperature": 0.1
                }
            )
            response.raise_for_status()
            result = response.json()

            content = result["choices"][0]["message"]["content"]
            print(f"Status: SUCCESS (200)")
            print(f"Response: {content}")
            print("-" * 50)
            print("本地LLM调用修复成功！")
            return True

    except httpx.HTTPStatusError as e:
        print(f"Status: FAILED ({e.response.status_code})")
        print(f"Error: {e.response.text}")
        return False
    except Exception as e:
        print(f"Status: ERROR")
        print(f"Error: {e}")
        return False

if __name__ == "__main__":
    # 加载环境变量
    from dotenv import load_dotenv
    load_dotenv()

    result = asyncio.run(test_local_llm())
    exit(0 if result else 1)
