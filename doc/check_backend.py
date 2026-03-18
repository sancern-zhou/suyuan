import requests
try:
    r = requests.get('http://localhost:8000/health', timeout=3)
    print(f"✅ 后端正常: {r.json()}")
except Exception as e:
    print(f"❌ 后端异常: {e}")

