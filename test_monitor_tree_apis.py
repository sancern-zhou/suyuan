"""
测试海康监控点树API

基于前端JavaScript分析发现的API端点进行测试
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


def test_api(url, method="GET", params=None, data=None, cookies=None, headers=None):
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
            response = session.post(url, json=data, headers=headers, timeout=10)

        log(f"状态码: {response.status_code}", "INFO")

        if response.status_code == 200:
            try:
                json_data = response.json()
                data_str = json.dumps(json_data, ensure_ascii=False)
                log(f"响应长度: {len(data_str)} 字符", "SUCCESS")

                # 保存响应
                timestamp = datetime.now().strftime('%H%M%S')
                filename = f"monitor_tree_api_{timestamp}.json"
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
                            # 显示部分数据
                            if 'list' in data:
                                log(f"列表长度: {len(data.get('list', []))}", "INFO")
                            if 'tree' in data:
                                log(f"包含树数据", "SUCCESS")
                        elif isinstance(data, list):
                            log(f"数据数组长度: {len(data)}", "INFO")
                            if len(data) > 0:
                                log(f"第一个元素: {list(data[0].keys())}", "INFO")

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
    log("海康监控点树API测试", "INFO")
    log("="*70, "INFO")

    # 加载认证信息
    auth_info = load_auth_info()
    if auth_info:
        cookies = auth_info.get("cookies", {})
        headers = auth_info.get("headers", {})
        referer = auth_info.get("referer", "http://10.10.10.158")
        headers['Referer'] = referer
        log(f"已加载认证信息，cookies: {len(cookies)} 个", "SUCCESS")
    else:
        log("未找到认证信息，将使用空cookies", "WARN")
        cookies = {}
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'application/json, text/plain, */*',
            'Referer': 'http://10.10.10.158'
        }

    base_url = "http://10.10.10.158"

    # 关键API端点列表（按优先级排序）
    critical_apis = [
        # 1. 通道树搜索（最有可能）
        ("GET", f"{base_url}/vms/api/v5/channelsTree/searches", None),

        # 2. 区域相关API
        ("GET", f"{base_url}/vms/ui/webPreview/region/fetchRootAppRegions", None),
        ("GET", f"{base_url}/vms/ui/webPreview/region/fetchAppRegionsByParent", None),
        ("GET", f"{base_url}/vms/ui/webPreview/region/fetchAppCamerasByParent", None),
        ("GET", f"{base_url}/vms/ui/webPreview/region/searchAppTree", None),

        # 3. 单位树
        ("GET", f"{base_url}/vms/ui/unit/fetchUnitTreeNodeList", None),

        # 4. 摄像头相关
        ("GET", f"{base_url}/vms/api/v1/cameras/recLocations/searches", None),
        ("GET", f"{base_url}/vms/ui/camera/fetchCameraByEncoderIndexCode", None),

        # 5. 编码器相关
        ("GET", f"{base_url}/vms/ui/encoder/monitorEncoder", None),
        ("GET", f"{base_url}/vms/ui/encoder/addMonitorEncoderList", None),

        # 6. 工具栏树
        ("GET", f"{base_url}/front/toolbar/toolbarTree", None),
    ]

    # 测试每个API
    successful_apis = []
    data_apis = []

    for idx, (method, url, params) in enumerate(critical_apis):
        log(f"\n[{idx+1}/{len(critical_apis)}] 测试API端点", "INFO")

        result = test_api(url, method, params, cookies, headers)

        if result:
            successful_apis.append(url)
            if isinstance(result, dict) and 'data' in result:
                data_apis.append(url)

        print()  # 空行分隔

    # 显示汇总
    log("\n" + "="*70, "SUCCESS")
    log("测试结果汇总", "SUCCESS")
    log("="*70, "SUCCESS")

    log(f"成功响应: {len(successful_apis)}/{len(critical_apis)}", "INFO")
    log(f"包含数据: {len(data_apis)}/{len(critical_apis)}", "INFO")

    log("\n✅ 成功的API:", "INFO")
    for api in successful_apis:
        log(f"  - {api}", "SUCCESS")

    log("\n🎯 包含数据的API:", "SUCCESS")
    for api in data_apis:
        log(f"  - {api}", "SUCCESS")

    # 保存结果
    test_result = {
        'timestamp': datetime.now().isoformat(),
        'successful_apis': successful_apis,
        'data_apis': data_apis,
        'total_tested': len(critical_apis)
    }

    with open("monitor_api_test_result.json", "w", encoding="utf-8") as f:
        json.dump(test_result, f, ensure_ascii=False, indent=2)

    log("\n测试结果已保存到 monitor_api_test_result.json", "SUCCESS")


if __name__ == "__main__":
    print("""
╔════════════════════════════════════════════════════════════╗
║        海康监控点树API测试工具                          ║
╚════════════════════════════════════════════════════════════╝

基于前端JavaScript分析发现的API端点进行测试

    """)

    main()
