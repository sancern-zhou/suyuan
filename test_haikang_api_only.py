"""
海康API直接测试 - 使用已保存的认证信息
"""

import json
import requests
from datetime import datetime

BASE_URL = "http://10.10.10.158"

# 禁用SSL警告
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def log(message, level="INFO"):
    timestamp = datetime.now().strftime("%H:%M:%S")
    icon = {"INFO": "ℹ️", "SUCCESS": "✅", "WARN": "⚠️", "ERROR": "❌"}[level]
    print(f"[{timestamp}] {icon} {message}")

def test_api(url, method="GET", params=None, cookies=None, headers=None):
    """测试API调用"""
    log(f"测试: {method} {url}", "INFO")

    session = requests.Session()
    session.verify = False

    if cookies:
        session.cookies.update(cookies)

    try:
        if method == "GET":
            response = session.get(url, params=params, headers=headers, timeout=10)
        else:
            response = session.post(url, json=params, headers=headers, timeout=10)

        log(f"状态码: {response.status_code}", "INFO")

        if response.status_code == 200:
            try:
                json_data = response.json()
                data_str = json.dumps(json_data, ensure_ascii=False)
                log(f"响应长度: {len(data_str)} 字符", "SUCCESS")

                # 保存响应
                timestamp = datetime.now().strftime('%H%M%S')
                filename = f"api_response_{timestamp}.json"
                with open(filename, "w", encoding="utf-8") as f:
                    json.dump(json_data, f, ensure_ascii=False, indent=2)
                log(f"已保存: {filename}", "SUCCESS")

                # 显示响应结构
                if isinstance(json_data, dict):
                    log(f"响应字段: {list(json_data.keys())}", "INFO")
                    if 'code' in json_data:
                        log(f"返回码: {json_data['code']}", "INFO")
                    if 'msg' in json_data:
                        log(f"消息: {json_data['msg']}", "INFO")
                    if 'data' in json_data:
                        data = json_data['data']
                        if isinstance(data, dict):
                            log(f"数据字段: {list(data.keys())}", "INFO")
                        elif isinstance(data, list):
                            log(f"数据数组长度: {len(data)}", "INFO")

                return json_data

            except Exception as e:
                log(f"JSON解析失败: {e}", "WARN")
                log(f"响应文本: {response.text[:200]}", "INFO")
                return response.text
        else:
            log(f"请求失败: {response.text[:200]}", "ERROR")
            return None

    except Exception as e:
        log(f"请求异常: {e}", "ERROR")
        return None

def main():
    log("="*70, "INFO")
    log("海康API直接测试工具", "INFO")
    log("="*70, "INFO")

    # 尝试加载保存的认证信息
    try:
        with open("haikang_auth.json", "r", encoding="utf-8") as f:
            auth_info = json.load(f)
        log("已加载保存的认证信息", "SUCCESS")
    except:
        log("未找到保存的认证信息，使用默认值", "WARN")
        auth_info = {
            "cookies": {},
            "headers": {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Accept': 'application/json, text/plain, */*',
            },
            "referer": BASE_URL
        }

    cookies = auth_info.get("cookies", {})
    headers = auth_info.get("headers", {})
    referer = auth_info.get("referer", BASE_URL)

    log(f"使用referer: {referer}", "INFO")
    log(f"Cookies数量: {len(cookies)}", "INFO")

    if 'Referer' not in headers and referer:
        headers['Referer'] = referer

    # API测试列表
    api_tests = [
        # 监控点树相关
        ("GET", f"{BASE_URL}/vms/ui/preview/monitor/tree", None),
        ("GET", f"{BASE_URL}/vms/ui/preview/resource/tree", None),
        ("GET", f"{BASE_URL}/vms/ui/resource/monitor/tree", None),
        ("GET", f"{BASE_URL}/vms/ui/preview/camera/tree", None),

        # 组织机构相关
        ("GET", f"{BASE_URL}/vms/ui/org/tree", None),
        ("GET", f"{BASE_URL}/vms/ui/organization/tree", None),

        # 资源相关
        ("GET", f"{BASE_URL}/vms/ui/resource/root", None),
        ("GET", f"{BASE_URL}/vms/ui/preview/resource/root", None),

        # 工具栏
        ("GET", f"{BASE_URL}/portal/front/toolbar/toolbarTree", None),

        # 带时间戳的请求
        ("GET", f"{BASE_URL}/vms/ui/preview/tree", {"t": int(datetime.now().timestamp() * 1000)}),
    ]

    results = []
    for method, url, params in api_tests:
        result = test_api(url, method, params, cookies, headers)
        results.append({
            "url": url,
            "success": result is not None,
            "has_data": isinstance(result, dict) and 'data' in result
        })
        print()  # 空行分隔

    # 显示测试结果汇总
    log("\n" + "="*70, "SUCCESS")
    log("测试结果汇总", "SUCCESS")
    log("="*70, "SUCCESS")

    success_count = sum(1 for r in results if r['success'])
    data_count = sum(1 for r in results if r['has_data'])

    log(f"成功请求: {success_count}/{len(results)}", "INFO")
    log(f"包含数据: {data_count}/{len(results)}", "INFO")

    for r in results:
        status = "✅" if r['success'] else "❌"
        data_mark = " [有数据]" if r['has_data'] else ""
        log(f"{status} {r['url']}{data_mark}", "INFO")

    log("\n所有响应已保存到 api_response_*.json 文件", "INFO")

if __name__ == "__main__":
    print("""
╔════════════════════════════════════════════════════════════╗
║        海康API直接测试工具                              ║
╚════════════════════════════════════════════════════════════╝

使用已保存的认证信息测试API端点

    """)

    main()
