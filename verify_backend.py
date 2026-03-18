"""
验证后端启动后的工具加载情况
在后端重启后运行此脚本
"""
import requests
import json

print("=" * 80)
print("Backend Tool Verification")
print("=" * 80)

try:
    # 检查后端健康状态
    print("\n[Step 1] Checking backend health...")
    response = requests.get("http://localhost:8000/health", timeout=5)
    if response.status_code == 200:
        print("  [OK] Backend is running")
    else:
        print(f"  [ERROR] Backend returned status {response.status_code}")
        exit(1)

except requests.exceptions.ConnectionError:
    print("  [ERROR] Cannot connect to backend. Is it running on port 8000?")
    exit(1)

# 检查系统状态
print("\n[Step 2] Checking system status...")
try:
    response = requests.get("http://localhost:8000/system/status", timeout=5)
    if response.status_code == 200:
        status = response.json()
        print(f"  [OK] System status retrieved")
        if 'tools' in status:
            tools = status['tools']
            print(f"  Total tools: {tools.get('total', 'N/A')}")
            if 'list' in tools:
                tool_list = tools['list']
                print(f"  Has 'unpack_office': {'unpack_office' in tool_list}")
                print(f"  Has 'pack_office': {'pack_office' in tool_list}")
    else:
        print(f"  [WARN] Status endpoint returned {response.status_code}")
except Exception as e:
    print(f"  [WARN] Could not get system status: {e}")

# 发送测试请求
print("\n[Step 3] Sending test analysis request...")
test_query = "查看报告模板目录下的文件"

try:
    response = requests.post(
        "http://localhost:8000/api/agent/analyze",
        json={
            "query": test_query,
            "session_id": None,
            "max_iterations": 3,
            "debug_mode": True
        },
        timeout=30,
        stream=True
    )

    print("  [INFO] Waiting for response...")

    tool_calls = []
    for line in response.iter_lines():
        if line:
            line_str = line.decode('utf-8')
            if line_str.startswith('data: '):
                try:
                    data = json.loads(line_str[6:])
                    if data.get('type') == 'action' and data.get('data', {}).get('type') == 'TOOL_CALL':
                        tool_name = data['data']['tool']
                        tool_calls.append(tool_name)
                        print(f"  [ACTION] Tool called: {tool_name}")
                    elif data.get('type') == 'observation':
                        obs_data = data.get('data', {})
                        if 'error' in obs_data and 'unpack_office' in obs_data.get('error', ''):
                            print(f"  [ERROR] unpack_office not found!")
                            print(f"  Available tools: {obs_data.get('available_tools', [])[:10]}...")
                            break
                    elif data.get('type') in ['complete', 'error', 'fatal_error']:
                        break
                except:
                    pass

    if 'unpack_office' in tool_calls:
        print("\n  [SUCCESS] unpack_office was successfully called!")
    elif any('不存在' in str(tc) or 'not found' in str(tc) for tc in tool_calls):
        print("\n  [FAILURE] unpack_office is still missing!")
    else:
        print("\n  [INFO] Test completed (tool may not have been needed)")

except Exception as e:
    print(f"  [ERROR] Request failed: {e}")

print("\n" + "=" * 80)
print("Verification completed!")
print("=" * 80)
