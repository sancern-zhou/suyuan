"""
海康深度前端分析 - 查找监控点树API

目标：深入分析JavaScript代码，查找监控点树的数据获取方式
"""

import json
import re
import requests
from datetime import datetime
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def log(message, level="INFO"):
    timestamp = datetime.now().strftime("%H:%M:%S")
    icon = {"INFO": "ℹ️", "SUCCESS": "✅", "WARN": "⚠️", "ERROR": "❌"}[level]
    print(f"[{timestamp}] {icon} {message}")


def download_js_file(url):
    """下载JavaScript文件"""
    try:
        session = requests.Session()
        session.verify = False
        response = session.get(url, timeout=20)
        if response.status_code == 200:
            return response.text
        return None
    except:
        return None


def deep_analyze_js(js_code, filename):
    """深度分析JavaScript代码"""
    if not js_code or len(js_code) < 100:
        return None

    results = {
        'filename': filename,
        'api_urls': [],
        'tree_apis': [],
        'resource_apis': [],
        'monitor_apis': [],
        'function_calls': [],
    }

    # 1. 查找所有可能的API URL模式
    url_patterns = [
        r'["\']https?://[^"\']+["\']',  # 完整URL
        r'["\']/[a-zA-Z]+/[a-zA-Z]+/[a-zA-Z]+["\']',  # 三级路径
        r'["\']/[a-zA-Z]+/[a-zA-Z]+["\']',  # 二级路径
        r'["\']/api/[^"\']+["\']',  # API路径
        r'["\']/vms/[^"\']+["\']',  # VMS路径
        r'["\']/portal/[^"\']+["\']',  # Portal路径
    ]

    for pattern in url_patterns:
        matches = re.finditer(pattern, js_code)
        for match in matches:
            url = match.group(0).strip('"\'')
            if len(url) > 5 and url not in results['api_urls']:
                results['api_urls'].append(url)

    # 2. 查找树形结构相关的API
    tree_keywords = ['tree', 'Tree', 'TREE', '树', '节点', 'node']
    for keyword in tree_keywords:
        # 查找包含tree关键词的URL
        pattern = r'["\'][^"\']*' + re.escape(keyword) + r'[^"\']*["\']'
        matches = re.finditer(pattern, js_code)
        for match in matches:
            text = match.group(0).strip('"\'')
            if len(text) < 100 and text not in results['tree_apis']:
                results['tree_apis'].append(text)

    # 3. 查找资源相关的API
    resource_keywords = ['resource', 'Resource', 'camera', 'Camera', 'monitor', 'Monitor']
    for keyword in resource_keywords:
        pattern = r'["\'][^"\']*' + re.escape(keyword) + r'[^"\']*["\']'
        matches = re.finditer(pattern, js_code)
        for match in matches:
            text = match.group(0).strip('"\'')
            if len(text) < 100 and text not in results['resource_apis']:
                results['resource_apis'].append(text)

    # 4. 查找监控点相关的API
    monitor_keywords = ['preview', 'Preview', 'point', 'Point', 'organization', 'org']
    for keyword in monitor_keywords:
        pattern = r'["\'][^"\']*' + re.escape(keyword) + r'[^"\']*["\']'
        matches = re.finditer(pattern, js_code)
        for match in matches:
            text = match.group(0).strip('"\'')
            if len(text) < 100 and text not in results['monitor_apis']:
                results['monitor_apis'].append(text)

    # 5. 查找函数调用（可能包含API调用）
    function_patterns = [
        r'(axios|fetch|\$http|request)\.[a-zA-Z]+\(["\']([^"\']+)["\']',
        r'[a-zA-Z_$]\w*\.[a-zA-Z]+\(["\']/?[a-zA-Z/]+["\']',
    ]

    for pattern in function_patterns:
        matches = re.finditer(pattern, js_code)
        for match in matches:
            call = match.group(0)
            if len(call) < 100 and call not in results['function_calls']:
                results['function_calls'].append(call)

    return results


def main():
    log("="*70, "INFO")
    log("海康深度前端分析", "INFO")
    log("="*70, "INFO")

    # 加载JavaScript文件列表
    try:
        with open("haikang_js_files.json", "r", encoding="utf-8") as f:
            js_files = json.load(f)
        log(f"加载了 {len(js_files)} 个JavaScript文件", "SUCCESS")
    except Exception as e:
        log(f"无法加载文件列表: {e}", "ERROR")
        return

    # 分析所有文件
    all_tree_apis = set()
    all_resource_apis = set()
    all_monitor_apis = set()
    all_api_urls = set()

    for idx, js_url in enumerate(js_files):
        filename = js_url.split('/')[-1]
        log(f"[{idx+1}/{len(js_files)}] 分析: {filename}", "INFO")

        js_code = download_js_file(js_url)
        if js_code:
            result = deep_analyze_js(js_code, js_url)
            if result:
                all_tree_apis.update(result['tree_apis'])
                all_resource_apis.update(result['resource_apis'])
                all_monitor_apis.update(result['monitor_apis'])
                all_api_urls.update(result['api_urls'])

                # 显示重要发现
                if result['tree_apis']:
                    log(f"  ✅ 发现树相关: {len(result['tree_apis'])} 个", "SUCCESS")
                if result['resource_apis']:
                    log(f"  ✅ 发现资源相关: {len(result['resource_apis'])} 个", "SUCCESS")
                if result['monitor_apis']:
                    log(f"  ✅ 发现监控相关: {len(result['monitor_apis'])} 个", "SUCCESS")

    # 显示汇总结果
    log("\n" + "="*70, "SUCCESS")
    log("深度分析结果", "SUCCESS")
    log("="*70, "SUCCESS")

    log(f"\n树形相关API: {len(all_tree_apis)} 个", "INFO")
    for api in sorted(all_tree_apis):
        if '/' in api and len(api) < 80:
            log(f"  ✅ {api}", "SUCCESS")

    log(f"\n资源相关API: {len(all_resource_apis)} 个", "INFO")
    for api in sorted(all_resource_apis):
        if '/' in api and len(api) < 80:
            log(f"  ✅ {api}", "SUCCESS")

    log(f"\n监控相关API: {len(all_monitor_apis)} 个", "INFO")
    for api in sorted(all_monitor_apis):
        if '/' in api and len(api) < 80:
            log(f"  ✅ {api}", "SUCCESS")

    # 查找可能的数据API
    log("\n" + "="*70, "INFO")
    log("可能的监控点数据API", "INFO")
    log("="*70, "INFO")

    possible_apis = []

    # 从所有API中筛选可能包含监控点数据的
    all_api_list = list(all_api_urls)
    for api in all_api_list:
        api_lower = api.lower()
        # 查找包含关键词的API
        if any(keyword in api_lower for keyword in ['tree', 'resource', 'monitor', 'camera', 'preview', 'org']):
            # 排除静态资源
            if not any(ext in api for ext in ['.css', '.js', '.png', '.jpg', '.woff']):
                possible_apis.append(api)

    for api in sorted(set(possible_apis)):
        log(f"  🎯 {api}", "SUCCESS")

    # 保存结果
    result = {
        'timestamp': datetime.now().isoformat(),
        'tree_apis': list(all_tree_apis),
        'resource_apis': list(all_resource_apis),
        'monitor_apis': list(all_monitor_apis),
        'possible_data_apis': list(set(possible_apis)),
    }

    with open("deep_analysis_result.json", "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    log("\n结果已保存到 deep_analysis_result.json", "SUCCESS")

    # 生成测试建议
    log("\n" + "="*70, "INFO")
    log("建议测试的API端点", "INFO")
    log("="*70, "INFO")

    if possible_apis:
        log("基于分析结果，建议测试以下API端点：", "INFO")
        for api in sorted(set(possible_apis))[:10]:
            # 补全完整URL
            if api.startswith('/'):
                full_url = f"http://10.10.10.158{api}"
            else:
                full_url = api
            log(f"  curl '{full_url}'", "INFO")


if __name__ == "__main__":
    print("""
╔════════════════════════════════════════════════════════════╗
║        海康深度前端分析工具                             ║
╚════════════════════════════════════════════════════════════╝

深度分析JavaScript代码，查找监控点数据API

    """)

    main()
