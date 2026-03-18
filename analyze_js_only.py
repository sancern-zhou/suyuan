"""
海康JavaScript文件分析工具 - 直接分析已保存的文件列表
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
        response = session.get(url, timeout=15)
        if response.status_code == 200:
            return response.text
        return None
    except Exception as e:
        log(f"下载失败 {url.split('/')[-1]}: {str(e)[:50]}", "WARN")
        return None


def analyze_js_code(js_code, filename):
    """分析JavaScript代码"""
    if not js_code or len(js_code) < 100:
        return None

    results = {
        'filename': filename,
        'api_patterns': [],
        'monitor_related': [],
        'possible_endpoints': [],
    }

    # 查找API路径模式
    api_patterns = [
        r'["\']/[a-zA-Z]+/[a-zA-Z]+/[a-zA-Z]+["\']',
        r'["\']/vms/[a-zA-Z]+/[a-zA-Z]+["\']',
        r'["\']/portal/[a-zA-Z]+/[a-zA-Z]+["\']',
        r'["\']/api/[a-zA-Z]+/[a-zA-Z]+["\']',
    ]

    for pattern in api_patterns:
        matches = re.finditer(pattern, js_code)
        for match in matches:
            text = match.group(0)
            # 清理引号
            endpoint = text.strip('"\'').strip()
            if len(endpoint) > 5 and endpoint not in results['possible_endpoints']:
                results['possible_endpoints'].append(endpoint)

    # 查找axios/fetch调用
    call_patterns = [
        (r'axios\.(get|post|put|delete)\(["\']([^"\']+)["\']', 'axios'),
        (r'fetch\(["\']([^"\']+)["\']', 'fetch'),
        (r'\$http\.(get|post)\(["\']([^"\']+)["\']', 'http'),
    ]

    for pattern, method in call_patterns:
        matches = re.finditer(pattern, js_code)
        for match in matches:
            try:
                url = match.group(2) if match.lastindex >= 2 else match.group(1)
                if url and len(url) > 3:
                    results['api_patterns'].append(f"{method}: {url}")
            except:
                continue

    # 查找监控点相关的关键词
    keywords = [
        'monitor', 'camera', 'video', 'preview', 'resource',
        'organization', 'org', 'tree', '点位', '监控', '摄像头'
    ]

    for keyword in keywords:
        # 在URL中查找
        url_pattern = r'["\'][^"\']*' + re.escape(keyword) + r'[^"\']*["\']'
        matches = re.finditer(url_pattern, js_code, re.IGNORECASE)
        for match in matches:
            text = match.group(0)
            if len(text) < 100 and text not in results['monitor_related']:
                results['monitor_related'].append(text)

    return results if any(results.values()) else None


def main():
    log("="*70, "INFO")
    log("海康JavaScript文件分析工具", "INFO")
    log("="*70, "INFO")

    # 加载JavaScript文件列表
    try:
        with open("haikang_js_files.json", "r", encoding="utf-8") as f:
            js_files = json.load(f)
        log(f"加载了 {len(js_files)} 个JavaScript文件", "SUCCESS")
    except Exception as e:
        log(f"无法加载文件列表: {e}", "ERROR")
        return

    # 只分析主要文件（避免vendor文件）
    main_files = [f for f in js_files
                 if any(name in f for name in ['app.', 'main', 'index'])
                 and 'vendor' not in f and 'chunk-vendors' not in f]

    log(f"分析 {len(main_files)} 个主要文件", "INFO")

    all_endpoints = set()
    all_apis = set()
    all_monitor = set()

    # 分析每个文件
    for idx, js_url in enumerate(main_files):
        filename = js_url.split('/')[-1]
        log(f"[{idx+1}/{len(main_files)}] 分析: {filename}", "INFO")

        js_code = download_js_file(js_url)
        if js_code:
            log(f"  文件大小: {len(js_code)} 字符", "INFO")

            result = analyze_js_code(js_code, js_url)
            if result:
                if result['possible_endpoints']:
                    log(f"  找到 {len(result['possible_endpoints'])} 个端点", "SUCCESS")
                    all_endpoints.update(result['possible_endpoints'])

                if result['api_patterns']:
                    log(f"  找到 {len(result['api_patterns'])} 个API调用", "SUCCESS")
                    all_apis.update(result['api_patterns'][:10])

                if result['monitor_related']:
                    log(f"  找到 {len(result['monitor_related'])} 个监控相关", "SUCCESS")
                    all_monitor.update(result['monitor_related'][:5])

    # 显示汇总结果
    log("\n" + "="*70, "SUCCESS")
    log("分析结果汇总", "SUCCESS")
    log("="*70, "SUCCESS")

    log(f"\n发现的API端点: {len(all_endpoints)} 个", "INFO")
    for endpoint in sorted(all_endpoints):
        if any(keyword in endpoint.lower() for keyword in ['vms', 'api', 'tree', 'monitor', 'resource']):
            log(f"  ✅ {endpoint}", "SUCCESS")

    log(f"\nAPI调用模式: {len(all_apis)} 个", "INFO")
    for api in sorted(list(all_apis))[:20]:
        log(f"  - {api}", "INFO")

    log(f"\n监控相关: {len(all_monitor)} 个", "INFO")
    for item in sorted(list(all_monitor))[:15]:
        log(f"  - {item[:80]}", "INFO")

    # 保存结果
    result = {
        'timestamp': datetime.now().isoformat(),
        'endpoints': list(all_endpoints),
        'api_calls': list(all_apis),
        'monitor_related': list(all_monitor),
    }

    with open("js_analysis_result.json", "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    log("\n结果已保存到 js_analysis_result.json", "SUCCESS")


if __name__ == "__main__":
    print("""
╔════════════════════════════════════════════════════════════╗
║        海康JavaScript文件分析工具                       ║
╚════════════════════════════════════════════════════════════╝

使用已保存的JavaScript文件列表进行分析

    """)

    main()
