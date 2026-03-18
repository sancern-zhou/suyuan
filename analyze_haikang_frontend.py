"""
海康视频平台前端JavaScript分析工具

目标：获取并分析前端JavaScript代码，查找监控点数据API

流程：
1. 登录并进入实时预览页面
2. 获取所有JavaScript文件
3. 分析JavaScript代码中的API调用
4. 查找监控点相关的数据获取方式
"""

import asyncio
import json
import re
from datetime import datetime
from playwright.async_api import async_playwright
import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

BASE_URL = "http://10.10.10.158"
USERNAME = "cdzhuanyong"
PASSWORD = "cdsz@429"


class FrontendAnalyzer:
    """前端代码分析器"""

    def __init__(self):
        self.js_files = []
        self.api_endpoints = []
        self.monitor_keywords = [
            'monitor', 'camera', 'video', 'resource', 'tree',
            'preview', 'organization', 'org', '点位', '监控',
            '摄像头', '资源', '根节点'
        ]

    def log(self, message, level="INFO"):
        timestamp = datetime.now().strftime("%H:%M:%S")
        icon = {"INFO": "ℹ️", "SUCCESS": "✅", "WARN": "⚠️", "ERROR": "❌"}[level]
        print(f"[{timestamp}] {icon} {message}")

    async def get_js_files_from_browser(self):
        """从浏览器获取JavaScript文件列表"""
        self.log("启动浏览器获取JavaScript文件...", "INFO")

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=False, slow_mo=500)
            context = await browser.new_context(ignore_https_errors=True)
            page = await context.new_page()

            try:
                # 监控网络请求
                js_files = set()

                def log_request(request):
                    if request.resource_type == "script":
                        js_files.add(request.url)

                page.on("request", log_request)

                # 登录流程
                self.log("访问登录页...", "INFO")
                await page.goto(BASE_URL, timeout=30000)
                await asyncio.sleep(3)

                self.log("查找用户名输入框...", "INFO")
                username_input = await page.query_selector('input[type="text"]')
                if not username_input:
                    username_input = await page.query_selector('input[name="username"]')

                if username_input:
                    self.log("输入用户名...", "INFO")
                    await username_input.fill(USERNAME)
                    await asyncio.sleep(1)
                else:
                    self.log("未找到用户名输入框", "WARN")

                self.log("查找密码输入框...", "INFO")
                password_input = await page.query_selector('input[type="password"]')
                if not password_input:
                    password_input = await page.query_selector('input[name="password"]')

                if password_input:
                    self.log("输入密码...", "INFO")
                    await password_input.fill(PASSWORD)
                    await asyncio.sleep(1)
                else:
                    self.log("未找到密码输入框", "WARN")
                    await page.screenshot(path="login_debug.png")
                    raise Exception("无法找到密码输入框")

                self.log("查找登录按钮...", "INFO")
                login_button = await page.query_selector('button[type="submit"]')
                if not login_button:
                    login_button = await page.query_selector('button:has-text("登录")')

                if login_button:
                    self.log("点击登录...", "INFO")
                    await login_button.click()
                    await asyncio.sleep(3)
                else:
                    self.log("未找到登录按钮，尝试回车", "WARN")
                    await page.keyboard.press("Enter")
                    await asyncio.sleep(3)

                # 点击实时预览
                await page.evaluate("""
                    () => {
                        const allElements = document.querySelectorAll('*');
                        for (const el of allElements) {
                            const text = el.textContent || '';
                            if (text.includes('实时预览') && text.length < 50) {
                                el.click();
                                return true;
                            }
                        }
                        return false;
                    }
                """)
                await asyncio.sleep(8)  # 等待所有JS加载

                self.log(f"捕获到 {len(js_files)} 个JavaScript文件", "SUCCESS")
                self.js_files = list(js_files)

                # 保存文件列表
                with open("haikang_js_files.json", "w", encoding="utf-8") as f:
                    json.dump(self.js_files, f, ensure_ascii=False, indent=2)

                self.log("JavaScript文件列表已保存", "SUCCESS")

                # 保持浏览器打开
                await asyncio.sleep(10000)

                return self.js_files

            finally:
                await browser.close()

    def download_js_file(self, url):
        """下载JavaScript文件"""
        try:
            session = requests.Session()
            session.verify = False

            response = session.get(url, timeout=10)
            if response.status_code == 200:
                return response.text
            return None
        except Exception as e:
            self.log(f"下载失败 {url}: {e}", "WARN")
            return None

    def analyze_js_code(self, js_code, filename):
        """分析JavaScript代码中的API调用"""
        if not js_code or len(js_code) < 100:
            return {}

        results = {
            'filename': filename,
            'api_calls': [],
            'monitor_apis': [],
            'data_endpoints': [],
            'functions': [],
        }

        # 查找API调用模式
        api_patterns = [
            # axios/fetch调用
            r'axios\.(get|post|put|delete)\(["\']([^"\']+)["\']',
            r'fetch\(["\']([^"\']+)["\']',

            # API路径
            r'["\']/(api|vms|portal)/[^"\']+["\']',
            r'url:\s*["\']([^"\']+)["\']',

            # 接口定义
            r'/[a-zA-Z]+/[a-zA-Z]+/[a-zA-Z]+',
        ]

        for pattern in api_patterns:
            matches = re.finditer(pattern, js_code)
            for match in matches:
                try:
                    if match.lastindex >= 2:
                        api_url = match.group(2) if match.lastindex >= 2 else match.group(1)
                        if api_url and len(api_url) > 5 and api_url not in results['api_calls']:
                            results['api_calls'].append(api_url)
                except:
                    continue

        # 查找监控点相关的API
        for keyword in self.monitor_keywords:
            pattern = f'["\'][^"\']*{keyword}[^"\']*["\']'
            matches = re.finditer(pattern, js_code, re.IGNORECASE)
            for match in matches:
                text = match.group(0)
                if len(text) < 200 and text not in results['monitor_apis']:
                    results['monitor_apis'].append(text)

        # 查找可能的数据端点
        endpoint_patterns = [
            r'["\']/[a-zA-Z]+/[a-zA-Z]+/[a-zA-Z]+["\']',
            r'endpoint:\s*["\']([^"\']+)["\']',
            r'apiPath:\s*["\']([^"\']+)["\']',
            r'requestUrl:\s*["\']([^"\']+)["\']',
        ]

        for pattern in endpoint_patterns:
            matches = re.finditer(pattern, js_code)
            for match in matches:
                try:
                    endpoint = match.group(1) if match.lastindex >= 1 else match.group(0)
                    if endpoint and len(endpoint) < 100 and endpoint not in results['data_endpoints']:
                        results['data_endpoints'].append(endpoint.strip('"\''))
                except:
                    continue

        # 查找函数定义
        function_patterns = [
            r'(async\s+)?function\s+([a-zA-Z_]\w*)\s*\(',
            r'(const|let|var)\s+([a-zA-Z_]\w*)\s*=\s*(?:async\s+)?\([^)]*\)\s*=>',
        ]

        for pattern in function_patterns:
            matches = re.finditer(pattern, js_code)
            for match in matches:
                func_name = match.group(2) if match.lastindex >= 2 else match.group(3)
                if func_name and len(func_name) < 50:
                    results['functions'].append(func_name)

        return results

    async def analyze_frontend(self):
        """分析前端代码"""
        # 步骤1: 获取JavaScript文件列表
        await self.get_js_files_from_browser()

        if not self.js_files:
            self.log("未找到JavaScript文件", "ERROR")
            return

        # 步骤2: 下载和分析JavaScript文件
        self.log("\n" + "="*70, "SUCCESS")
        self.log("开始分析JavaScript文件", "SUCCESS")
        self.log("="*70, "SUCCESS")

        all_results = []

        # 只分析主应用文件（避免vendor文件）
        main_js_files = [f for f in self.js_files
                        if 'app.' in f or 'chunk-' in f or 'main' in f
                        and 'vendor' not in f and 'chunk-vendors' not in f]

        self.log(f"分析 {len(main_js_files)} 个主要JavaScript文件", "INFO")

        for idx, js_url in enumerate(main_js_files[:15]):  # 只分析前15个文件
            self.log(f"\n[{idx+1}/{len(main_js_files)}] 分析: {js_url.split('/')[-1]}", "INFO")

            js_code = self.download_js_file(js_url)
            if js_code:
                results = self.analyze_js_code(js_code, js_url)

                if results['api_calls']:
                    self.log(f"  找到 {len(results['api_calls'])} 个API调用", "SUCCESS")
                    for api in results['api_calls'][:5]:
                        self.log(f"    - {api}", "INFO")

                if results['monitor_apis']:
                    self.log(f"  找到 {len(results['monitor_apis'])} 个监控相关", "SUCCESS")
                    for api in results['monitor_apis'][:3]:
                        self.log(f"    - {api[:80]}", "INFO")

                if results['data_endpoints']:
                    self.log(f"  找到 {len(results['data_endpoints'])} 个数据端点", "SUCCESS")
                    for endpoint in results['data_endpoints'][:3]:
                        self.log(f"    - {endpoint}", "INFO")

                all_results.append(results)

        # 步骤3: 汇总分析结果
        self.log("\n" + "="*70, "SUCCESS")
        self.log("分析结果汇总", "SUCCESS")
        self.log("="*70, "SUCCESS")

        # 收集所有API端点
        all_apis = set()
        all_endpoints = set()
        all_monitor_apis = set()

        for result in all_results:
            all_apis.update(result['api_calls'])
            all_endpoints.update(result['data_endpoints'])
            all_monitor_apis.update(result['monitor_apis'])

        self.log(f"\n发现的所有API调用: {len(all_apis)} 个", "INFO")
        for api in sorted(all_apis):
            if any(keyword in api.lower() for keyword in ['api', 'vms', 'tree', 'monitor', 'resource']):
                self.log(f"  - {api}", "SUCCESS")

        self.log(f"\n发现的数据端点: {len(all_endpoints)} 个", "INFO")
        for endpoint in sorted(all_endpoints):
            if len(endpoint) > 5:
                self.log(f"  - {endpoint}", "INFO")

        self.log(f"\n监控相关API: {len(all_monitor_apis)} 个", "INFO")
        for api in sorted(list(all_monitor_apis))[:20]:
            self.log(f"  - {api[:100]}", "INFO")

        # 保存分析结果
        analysis_result = {
            'timestamp': datetime.now().isoformat(),
            'js_files_count': len(self.js_files),
            'api_calls': list(all_apis),
            'data_endpoints': list(all_endpoints),
            'monitor_apis': list(all_monitor_apis),
            'detailed_results': all_results
        }

        with open("frontend_analysis.json", "w", encoding="utf-8") as f:
            json.dump(analysis_result, f, ensure_ascii=False, indent=2)

        self.log("\n分析结果已保存到 frontend_analysis.json", "SUCCESS")

        return analysis_result


async def main():
    analyzer = FrontendAnalyzer()

    try:
        result = await analyzer.analyze_frontend()

        analyzer.log("\n" + "="*70, "SUCCESS")
        analyzer.log("前端分析完成！", "SUCCESS")
        analyzer.log("="*70, "SUCCESS")

    except Exception as e:
        analyzer.log(f"\n分析出错: {e}", "ERROR")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    print("""
╔════════════════════════════════════════════════════════════╗
║        海康前端JavaScript分析工具                      ║
╚════════════════════════════════════════════════════════════╝

分析流程：
1. 登录并进入实时预览页面
2. 捕获所有JavaScript文件URL
3. 下载并分析JavaScript代码
4. 查找API调用和数据端点

    """)

    asyncio.run(main())
