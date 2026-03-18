"""
海康API Token参数测试

目标：找到正确的Token参数传递方式
"""

import json
import requests
from datetime import datetime
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def log(message, level="INFO"):
    timestamp = datetime.now().strftime("%H:%M:%S")
    icon = {"INFO": "ℹ️", "SUCCESS": "✅", "WARN": "⚠️", "ERROR": "❌"}[level]
    print(f"[{timestamp}] {icon} {message}")


def load_auth_info():
    """加载认证信息"""
    try:
        with open("haikang_auth.json", "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return None


def test_api_with_params(url, cookies, headers, params=None, method="GET"):
    """测试API并传递参数"""
    log(f"测试: {method} {url}", "INFO")
    if params:
        log(f"参数: {params}", "INFO")

    session = requests.Session()
    session.verify = False
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
                log(f"返回码: {json_data.get('code')}", "INFO")
                log(f"消息: {json_data.get('msg')}", "INFO")

                if json_data.get('data'):
                    log(f"✅ 包含数据!", "SUCCESS")
                    return json_data
                else:
                    log(f"❌ 无数据", "WARN")
                    return json_data

            except Exception as e:
                log(f"JSON解析失败: {e}", "WARN")
                log(f"响应文本: {response.text[:200]}", "INFO")
                return None

        else:
            log(f"请求失败: {response.text[:200]}", "ERROR")
            return None

    except Exception as e:
        log(f"请求异常: {e}", "ERROR")
        return None


def main():
    log("="*70, "INFO")
    log("海康API Token参数测试", "INFO")
    log("="*70, "INFO")

    # 加载认证信息
    auth_info = load_auth_info()
    if auth_info:
        cookies = auth_info.get("cookies", {})
        headers = auth_info.get("headers", {})
        referer = auth_info.get("referer", "http://10.10.10.158")
        headers['Referer'] = referer
    else:
        cookies = {}
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'application/json, text/plain, */*',
            'Referer': 'http://10.10.10.158'
        }

    base_url = "http://10.10.10.158"

    # 测试不同的Token参数组合
    test_cases = [
        # 1. 尝试查询参数中的token
        ("GET", f"{base_url}/vms/api/v5/channelsTree/searches", {"t": int(datetime.now().timestamp() * 1000)}),
        ("GET", f"{base_url}/vms/api/v5/channelsTree/searches", {"token": "test"}),
        ("GET", f"{base_url}/vms/api/v5/channelsTree/searches", {"access_token": "test"}),

        # 2. 尝试Header中的token
        ("GET", f"{base_url}/vms/api/v5/channelsTree/searches", None),

        # 3. 尝试POST请求
        ("POST", f"{base_url}/vms/api/v5/channelsTree/searches", {"search": ""}),
        ("POST", f"{base_url}/vms/api/v5/channelsTree/searches", {}),

        # 4. 尝试其他可能的数据API
        ("GET", f"{base_url}/vms/api/v1/cameras/recLocations/searches", {"page": 1, "size": 10}),
        ("POST", f"{base_url}/vms/api/v1/cameras/recLocations/searches", {"page": 1, "size": 10}),
    ]

    # 测试所有组合
    successful_tests = []

    for idx, (method, url, params) in enumerate(test_cases):
        log(f"\n[{idx+1}/{len(test_cases)}] 测试参数组合", "INFO")

        result = test_api_with_params(url, cookies, headers, params, method)
        if result and isinstance(result, dict):
            code = result.get('code', '')
            msg = result.get('msg', '')
            data = result.get('data')

            # 记录成功的测试
            successful_tests.append({
                'method': method,
                'url': url,
                'params': params,
                'code': code,
                'msg': msg,
                'has_data': data is not None
            })

    # 汇总结果
    log("\n" + "="*70, "SUCCESS")
    log("测试结果汇总", "SUCCESS")
    log("="*70, "SUCCESS")

    log(f"\n成功响应: {len(successful_tests)}/{len(test_cases)}", "INFO")

    # 找出包含数据的测试
    data_tests = [t for t in successful_tests if t['has_data']]

    if data_tests:
        log("\n✅ 包含数据的测试:", "SUCCESS")
        for test in data_tests:
            log(f"  方法: {test['method']}", "INFO")
            log(f"  参数: {test['params']}", "INFO")
            log(f"  返回码: {test['code']}", "INFO")
    else:
        log("\n⚠️ 所有测试都没有返回数据", "WARN")
        log("\n可能的原因:", "INFO")
        log("  1. 需要从页面获取额外的Token", "INFO")
        log("  2. 需要特定的请求头或参数", "INFO")
        log("  3. API路径可能不正确", "INFO")

    # 保存结果
    result = {
        'timestamp': datetime.now().isoformat(),
        'successful_tests': successful_tests,
        'data_tests': data_tests,
    }

    with open("token_test_result.json", "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    log("\n结果已保存到 token_test_result.json", "SUCCESS")

    # 如果没有找到数据，建议下一步
    if not data_tests:
        log("\n" + "="*70, "INFO")
        log("建议下一步", "INFO")
        log("="*70, "INFO")
        log("1. 在浏览器中手动触发监控点树加载", "INFO")
        log("2. 查看网络请求中的完整参数", "INFO")
        log("3. 或者联系海康技术支持获取API文档", "INFO")


if __name__ == "__main__":
    print("""
╔════════════════════════════════════════════════════════════╗
║        海康API Token参数测试工具                         ║
╚════════════════════════════════════════════════════════════╝

测试不同的Token和参数组合

    """)

    main()
