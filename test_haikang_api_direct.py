"""
海康视频平台 API 直接调用测试

目标：绕过 UI，直接调用 API 获取监控点数据

发现的重要 API：
- /portal/front/toolbar/toolbarTree - 工具栏树结构
- /vms/ui/current/userinfo - 用户信息
- /vms/ui/widget/startupParam - 启动参数
"""

import asyncio
import json
import requests
from datetime import datetime
from playwright.async_api import async_playwright

BASE_URL = "http://10.10.10.158"
USERNAME = "cdzhuanyong"
PASSWORD = "cdsz@429"


class APITester:
    """API 直接调用测试器"""

    def __init__(self):
        self.session = requests.Session()
        self.session.verify = False  # 忽略 SSL 证书
        self.cookies = {}

    def log(self, message, level="INFO"):
        timestamp = datetime.now().strftime("%H:%M:%S")
        icon = {"INFO": "ℹ️", "SUCCESS": "✅", "WARN": "⚠️", "ERROR": "❌"}[level]
        print(f"[{timestamp}] {icon} {message}")

    async def get_cookies_from_browser(self):
        """从浏览器获取登录后的 cookies"""
        self.log("启动浏览器获取登录cookies...", "INFO")

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=False)
            context = await browser.new_context(
                ignore_https_errors=True,  # 忽略HTTPS证书错误
                accept_downloads=True
            )
            page = await context.new_page()

            try:
                # 访问登录页
                await page.goto(BASE_URL, timeout=30000)
                await page.wait_for_load_state("networkidle")

                # 输入账号密码
                await page.fill('input[type="text"], input[type="username"]', USERNAME)
                await page.wait_for_timeout(500)
                await page.fill('input[type="password"]', PASSWORD)
                await page.wait_for_timeout(500)

                # 点击登录
                await page.click('button[type="submit"], button:has-text("登录")')
                await page.wait_for_timeout(3000)

                # 获取cookies
                cookies = await context.cookies()
                self.log(f"获取到 {len(cookies)} 个cookies", "SUCCESS")

                # 转换为requests格式
                for cookie in cookies:
                    self.cookies[cookie['name']] = cookie['value']

                self.log(f"Cookies: {list(self.cookies.keys())}", "INFO")

                # 保存cookies到文件
                with open("haikang_cookies.json", "w") as f:
                    json.dump(self.cookies, f, indent=2)
                self.log("Cookies已保存到 haikang_cookies.json", "SUCCESS")

                return self.cookies

            finally:
                await browser.close()

    def test_api_call(self, url, method="GET", params=None, data=None):
        """测试API调用"""
        self.log(f"\n测试API: {method} {url}", "INFO")

        # 设置cookies
        self.session.cookies.update(self.cookies)

        try:
            if method == "GET":
                response = self.session.get(url, params=params, timeout=10)
            else:
                response = self.session.post(url, json=data, timeout=10)

            self.log(f"状态码: {response.status_code}", "INFO")

            if response.status_code == 200:
                try:
                    json_data = response.json()
                    self.log(f"响应数据长度: {len(json.dumps(json_data))} 字符", "SUCCESS")

                    # 保存响应数据
                    filename = f"api_response_{datetime.now().strftime('%H%M%S')}.json"
                    with open(filename, "w", encoding="utf-8") as f:
                        json.dump(json_data, f, ensure_ascii=False, indent=2)
                    self.log(f"响应已保存: {filename}", "SUCCESS")

                    return json_data
                except:
                    self.log(f"响应不是JSON格式: {response.text[:200]}", "WARN")
                    return response.text
            else:
                self.log(f"请求失败: {response.text[:200]}", "ERROR")
                return None

        except Exception as e:
            self.log(f"请求异常: {e}", "ERROR")
            return None

    async def test_all_apis(self):
        """测试所有发现的API"""
        # 先获取cookies
        await self.get_cookies_from_browser()

        self.log("\n" + "="*70, "SUCCESS")
        self.log("开始测试API调用", "SUCCESS")
        self.log("="*70, "SUCCESS")

        # 测试1: 工具栏树结构
        self.log("\n测试1: 工具栏树结构API", "INFO")
        result1 = self.test_api_call(
            f"{BASE_URL}/portal/front/toolbar/toolbarTree",
            params={"t": int(datetime.now().timestamp() * 1000)}
        )

        # 测试2: 用户信息
        self.log("\n测试2: 用户信息API", "INFO")
        result2 = self.test_api_call(
            f"{BASE_URL}/vms/ui/current/userinfo"
        )

        # 测试3: 启动参数
        self.log("\n测试3: 启动参数API", "INFO")
        result3 = self.test_api_call(
            f"{BASE_URL}/vms/ui/widget/startupParam",
            params={
                "moduleIndex": 0,
                "scheme": "https",
                "enable": "true"
            }
        )

        # 尝试发现更多API
        self.log("\n" + "="*70, "INFO")
        self.log("尝试发现更多API端点...", "INFO")
        self.log("="*70, "INFO")

        # 常见的海康API端点
        potential_apis = [
            "/vms/ui/resource/tree",           # 资源树
            "/vms/ui/monitor/point/tree",      # 监控点树
            "/vms/ui/camera/tree",             # 摄像头树
            "/vms/ui/video/monitor/tree",      # 视频监控树
            "/vms/ui/org/tree",                # 组织机构树
            "/api/resource/tree",              # 资源树API
            "/api/camera/list",                # 摄像头列表
            "/api/monitor/point/list",         # 监控点列表
        ]

        for api_path in potential_apis:
            self.log(f"\n尝试: {api_path}", "INFO")
            result = self.test_api_call(f"{BASE_URL}{api_path}")
            if result:
                self.log(f"✅ API可用: {api_path}", "SUCCESS")
            else:
                self.log(f"❌ API不可用: {api_path}", "ERROR")

        return {
            "toolbar_tree": result1,
            "userinfo": result2,
            "startup_param": result3
        }

    def analyze_api_response(self, data):
        """分析API响应数据"""
        if not data or not isinstance(data, dict):
            return

        self.log("\nAPI响应分析:", "INFO")

        # 递归分析JSON结构
        def analyze_json(obj, path="", depth=0):
            if depth > 3:
                return

            indent = "  " * depth

            if isinstance(obj, dict):
                for key, value in obj.items():
                    current_path = f"{path}.{key}" if path else key

                    if isinstance(value, dict):
                        self.log(f"{indent}{key}: {{对象}}", "INFO")
                        analyze_json(value, current_path, depth + 1)
                    elif isinstance(value, list):
                        self.log(f"{indent}{key}: [{len(value)} 项]", "INFO")
                        if len(value) > 0:
                            analyze_json(value[0], current_path, depth + 1)
                    else:
                        value_str = str(value)[:50]
                        self.log(f"{indent}{key}: {value_str}", "INFO")

            elif isinstance(obj, list):
                if len(obj) > 0:
                    analyze_json(obj[0], path, depth)

        analyze_json(data)


async def main():
    tester = APITester()

    try:
        results = await tester.test_all_apis()

        tester.log("\n" + "="*70, "SUCCESS")
        tester.log("API测试完成！", "SUCCESS")
        tester.log("="*70, "SUCCESS")

        # 分析结果
        if results.get("toolbar_tree"):
            tester.log("\n分析工具栏树结构响应:", "INFO")
            tester.analyze_api_response(results["toolbar_tree"])

    except Exception as e:
        tester.log(f"\n测试出错: {e}", "ERROR")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    print("""
╔════════════════════════════════════════════════════════════╗
║        海康视频平台API直接调用测试工具                   ║
╚════════════════════════════════════════════════════════════╝

测试目标：
1. 从浏览器获取登录cookies
2. 直接调用API获取监控点数据
3. 分析API响应结构

发现的API：
- /portal/front/toolbar/toolbarTree - 工具栏树结构
- /vms/ui/current/userinfo - 用户信息
- /vms/ui/widget/startupParam - 启动参数

    """)

    asyncio.run(main())
