"""
海康视频平台简化API测试

目标：模拟完整的用户操作流程，然后调用API获取数据

流程：
1. 登录
2. 进入实时预览页面
3. 获取cookies和headers
4. 调用API获取监控点数据
"""

import asyncio
import json
import requests
from datetime import datetime
from playwright.async_api import async_playwright

BASE_URL = "http://10.10.10.158"
USERNAME = "cdzhuanyong"
PASSWORD = "cdsz@429"


class SimplifiedAPITester:
    """简化API测试器"""

    def __init__(self):
        self.session = requests.Session()
        self.session.verify = False
        self.cookies = {}
        self.headers = {}
        self.referer = ""

    def log(self, message, level="INFO"):
        timestamp = datetime.now().strftime("%H:%M:%S")
        icon = {"INFO": "ℹ️", "SUCCESS": "✅", "WARN": "⚠️", "ERROR": "❌"}[level]
        print(f"[{timestamp}] {icon} {message}")

    async def get_auth_from_browser(self):
        """从浏览器获取认证信息"""
        self.log("启动浏览器获取认证信息...", "INFO")

        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=False,
                slow_mo=800  # 增加延迟，更慢的操作
            )
            context = await browser.new_context(
                ignore_https_errors=True,
                viewport={"width": 1920, "height": 1080}
            )
            page = await context.new_page()

            try:
                # 步骤1: 访问登录页
                self.log("访问登录页", "INFO")
                await page.goto(BASE_URL, timeout=30000)
                self.log("页面加载完成，等待稳定...", "INFO")
                await asyncio.sleep(3)

                # 步骤2: 查找输入框
                self.log("查找用户名输入框...", "INFO")

                # 尝试多种选择器
                username_selectors = [
                    'input[type="text"]',
                    'input[type="username"]',
                    'input[name="username"]',
                    'input[placeholder*="用户"]',
                    'input[placeholder*="账号"]',
                    '#username',
                ]

                username_input = None
                for selector in username_selectors:
                    try:
                        username_input = await page.query_selector(selector)
                        if username_input:
                            self.log(f"找到用户名输入框: {selector}", "SUCCESS")
                            break
                    except:
                        continue

                if not username_input:
                    self.log("未找到用户名输入框，尝试截图...", "ERROR")
                    await page.screenshot(path="login_page_debug.png")
                    raise Exception("无法找到用户名输入框")

                # 输入用户名
                self.log("输入用户名...", "INFO")
                await username_input.fill(USERNAME)
                await asyncio.sleep(1)

                # 步骤3: 查找密码输入框
                self.log("查找密码输入框...", "INFO")

                password_selectors = [
                    'input[type="password"]',
                    'input[name="password"]',
                    'input[placeholder*="密码"]',
                    '#password',
                ]

                password_input = None
                for selector in password_selectors:
                    try:
                        password_input = await page.query_selector(selector)
                        if password_input:
                            self.log(f"找到密码输入框: {selector}", "SUCCESS")
                            break
                    except:
                        continue

                if not password_input:
                    self.log("未找到密码输入框...", "ERROR")
                    await page.screenshot(path="password_input_debug.png")
                    raise Exception("无法找到密码输入框")

                # 输入密码
                self.log("输入密码...", "INFO")
                await password_input.fill(PASSWORD)
                await asyncio.sleep(1)

                # 步骤4: 查找并点击登录按钮
                self.log("查找登录按钮...", "INFO")

                login_button_selectors = [
                    'button[type="submit"]',
                    'button:has-text("登录")',
                    'button:has-text("Login")',
                    'input[type="submit"]',
                    '[class*="login"]',
                    '[class*="submit"]',
                ]

                login_clicked = False
                for selector in login_button_selectors:
                    try:
                        button = await page.query_selector(selector)
                        if button:
                            self.log(f"找到登录按钮: {selector}，点击...", "INFO")
                            await button.click()
                            login_clicked = True
                            await asyncio.sleep(3)
                            break
                    except:
                        continue

                if not login_clicked:
                    self.log("无法点击登录按钮，尝试按回车键...", "WARN")
                    await page.keyboard.press("Enter")
                    await asyncio.sleep(3)

                self.log("等待登录完成...", "INFO")
                await asyncio.sleep(5)

                # 步骤5: 点击"实时预览"
                self.log("查找实时预览按钮...", "INFO")

                preview_clicked = await page.evaluate("""
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

                if preview_clicked:
                    self.log("已点击实时预览", "SUCCESS")
                else:
                    self.log("未找到实时预览按钮", "WARN")

                await asyncio.sleep(5)

                # 步骤6: 获取cookies和当前URL
                self.log("获取认证信息...", "INFO")
                cookies = await context.cookies()
                current_url = page.url

                self.log(f"当前URL: {current_url}", "INFO")
                self.log(f"获取到 {len(cookies)} 个cookies", "SUCCESS")

                # 转换cookies
                cookie_dict = {}
                for cookie in cookies:
                    cookie_dict[cookie['name']] = cookie['value']

                self.cookies = cookie_dict
                self.referer = current_url

                # 设置headers
                self.headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                    'Referer': current_url,
                    'Accept': 'application/json, text/plain, */*',
                    'Accept-Language': 'zh-CN,zh;q=0.9',
                    'Content-Type': 'application/json',
                }

                # 保存认证信息
                auth_info = {
                    'cookies': self.cookies,
                    'headers': self.headers,
                    'referer': self.referer,
                    'timestamp': datetime.now().isoformat()
                }

                with open("haikang_auth.json", "w", encoding="utf-8") as f:
                    json.dump(auth_info, f, ensure_ascii=False, indent=2)

                self.log("认证信息已保存到 haikang_auth.json", "SUCCESS")

                # 保持浏览器打开一段时间
                self.log("浏览器保持打开15秒，请观察页面...", "INFO")
                await page.screenshot(path="auth_page.png")
                await asyncio.sleep(15000)

                return auth_info

            except Exception as e:
                self.log(f"浏览器操作出错: {e}", "ERROR")
                import traceback
                traceback.print_exc()

                # 尝试截图以便调试
                try:
                    await page.screenshot(path="error_debug.png")
                    self.log("已保存错误截图: error_debug.png", "INFO")
                except:
                    pass

                raise

            finally:
                await browser.close()

    def test_api(self, url, method="GET", params=None):
        """测试API调用"""
        self.log(f"测试: {method} {url}", "INFO")

        # 设置cookies
        self.session.cookies.update(self.cookies)

        try:
            if method == "GET":
                response = self.session.get(
                    url,
                    params=params,
                    headers=self.headers,
                    timeout=10
                )
            else:
                response = self.session.post(
                    url,
                    json=params,
                    headers=self.headers,
                    timeout=10
                )

            self.log(f"状态码: {response.status_code}", "INFO")

            if response.status_code == 200:
                try:
                    json_data = response.json()
                    data_str = json.dumps(json_data, ensure_ascii=False)
                    self.log(f"响应长度: {len(data_str)} 字符", "SUCCESS")

                    # 保存响应
                    timestamp = datetime.now().strftime('%H%M%S')
                    filename = f"api_response_{timestamp}.json"
                    with open(filename, "w", encoding="utf-8") as f:
                        json.dump(json_data, f, ensure_ascii=False, indent=2)
                    self.log(f"已保存: {filename}", "SUCCESS")

                    # 显示响应结构
                    if isinstance(json_data, dict):
                        self.log(f"响应字段: {list(json_data.keys())}", "INFO")
                        if 'code' in json_data:
                            self.log(f"返回码: {json_data['code']}", "INFO")
                        if 'msg' in json_data:
                            self.log(f"消息: {json_data['msg']}", "INFO")
                        if 'data' in json_data:
                            data = json_data['data']
                            if isinstance(data, dict):
                                self.log(f"数据字段: {list(data.keys())}", "INFO")
                            elif isinstance(data, list):
                                self.log(f"数据数组长度: {len(data)}", "INFO")

                    return json_data

                except Exception as e:
                    self.log(f"JSON解析失败: {e}", "WARN")
                    self.log(f"响应文本: {response.text[:200]}", "INFO")
                    return response.text
            else:
                self.log(f"请求失败: {response.text[:200]}", "ERROR")
                return None

        except Exception as e:
            self.log(f"请求异常: {e}", "ERROR")
            return None

    async def run_tests(self):
        """运行所有测试"""
        # 获取认证信息
        await self.get_auth_from_browser()

        # 测试API端点
        self.log("\n" + "="*70, "SUCCESS")
        self.log("开始测试API端点", "SUCCESS")
        self.log("="*70, "SUCCESS")

        # 测试列表
        api_tests = [
            # 监控点树相关
            ("GET", f"{BASE_URL}/vms/ui/preview/monitor/tree", None),
            ("GET", f"{BASE_URL}/vms/ui/preview/resource/tree", None),
            ("GET", f"{BASE_URL}/vms/ui/resource/monitor/tree", None),

            # 组织机构相关
            ("GET", f"{BASE_URL}/vms/ui/org/tree", None),
            ("GET", f"{BASE_URL}/vms/ui/organization/tree", None),

            # 资源相关
            ("GET", f"{BASE_URL}/vms/ui/resource/root", None),

            # 工具栏
            ("GET", f"{BASE_URL}/portal/front/toolbar/toolbarTree", None),
        ]

        for method, url, params in api_tests:
            result = self.test_api(url, method, params)
            await asyncio.sleep(1)  # 避免请求过快

        # 尝试更多可能的API
        self.log("\n尝试发现更多API...", "INFO")

        # 带时间戳的请求
        timestamp = int(datetime.now().timestamp() * 1000)
        additional_tests = [
            ("GET", f"{BASE_URL}/vms/ui/preview/tree", {"t": timestamp}),
            ("GET", f"{BASE_URL}/vms/ui/preview/camera/tree", {"t": timestamp}),
            ("GET", f"{BASE_URL}/vms/ui/preview/org/tree", {"t": timestamp}),
        ]

        for method, url, params in additional_tests:
            result = self.test_api(url, method, params)
            await asyncio.sleep(1)


async def main():
    tester = SimplifiedAPITester()

    try:
        await tester.run_tests()

        tester.log("\n" + "="*70, "SUCCESS")
        tester.log("测试完成！", "SUCCESS")
        tester.log("="*70, "SUCCESS")

        # 显示保存的文件
        tester.log("\n保存的文件:", "INFO")
        tester.log("  - haikang_auth.json (认证信息)", "INFO")
        tester.log("  - auth_page.png (页面截图)", "INFO")
        tester.log("  - api_response_*.json (API响应)", "INFO")

    except Exception as e:
        tester.log(f"\n测试出错: {e}", "ERROR")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    print("""
╔════════════════════════════════════════════════════════════╗
║        海康简化API测试工具                              ║
╚════════════════════════════════════════════════════════════╝

测试流程：
1. 登录并进入实时预览页面
2. 获取完整的cookies和headers
3. 测试多个API端点获取监控点数据

    """)

    asyncio.run(main())
