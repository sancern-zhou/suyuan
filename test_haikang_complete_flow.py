"""
海康视频平台完整流程API测试

目标：模拟完整的用户操作流程，然后调用API获取数据

流程：
1. 登录
2. 进入实时预览页面
3. 等待页面完全加载
4. 从浏览器获取完整的cookies和headers
5. 调用API获取监控点数据
"""

import asyncio
import json
import requests
from datetime import datetime
from playwright.async_api import async_playwright

BASE_URL = "http://10.10.10.158"
USERNAME = "cdzhuanyong"
PASSWORD = "cdsz@429"


class CompleteFlowAPITester:
    """完整流程API测试器"""

    def __init__(self):
        self.session = requests.Session()
        self.session.verify = False
        self.cookies = {}
        self.headers = {}

    def log(self, message, level="INFO"):
        timestamp = datetime.now().strftime("%H:%M:%S")
        icon = {"INFO": "ℹ️", "SUCCESS": "✅", "WARN": "⚠️", "ERROR": "❌"}[level]
        print(f"[{timestamp}] {icon} {message}")

    async def complete_browser_flow(self):
        """完整的浏览器操作流程"""
        self.log("启动完整浏览器流程...", "INFO")

        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=False,
                slow_mo=500
            )
            context = await browser.new_context(
                ignore_https_errors=True,
                accept_downloads=True,
                viewport={"width": 1920, "height": 1080}
            )
            page = await context.new_page()

            try:
                # 步骤1: 访问登录页
                self.log("步骤1: 访问登录页", "INFO")
                await page.goto(BASE_URL, timeout=30000)
                await page.wait_for_load_state("networkidle")

                # 步骤2: 输入账号密码
                self.log("步骤2: 输入账号密码", "INFO")
                await page.fill('input[type="text"], input[type="username"]', USERNAME)
                await page.wait_for_timeout(500)
                await page.fill('input[type="password"]', PASSWORD)
                await page.wait_for_timeout(500)

                # 步骤3: 点击登录
                self.log("步骤3: 点击登录", "INFO")
                await page.click('button[type="submit"], button:has-text("登录")')
                await page.wait_for_timeout(3000)

                # 步骤4: JavaScript点击"实时预览"
                self.log("步骤4: JavaScript点击'实时预览'", "INFO")
                await page.evaluate("""
                    () => {
                        const allElements = document.querySelectorAll('*');
                        for (const el of allElements) {
                            const text = el.textContent || '';
                            if (text.includes('实时预览') && text.length < 50) {
                                el.click();
                                return {success: true};
                            }
                        }
                        return {success: false};
                    }
                """)
                await page.wait_for_timeout(5000)

                # 步骤5: 等待页面完全加载
                self.log("步骤5: 等待页面完全加载", "INFO")
                try:
                    await page.wait_for_load_state("domcontentloaded", timeout=10000)
                except:
                    self.log("domcontentloaded超时，继续执行", "WARN")

                await page.wait_for_timeout(3000)

                # 步骤6: 获取完整的cookies和headers
                self.log("步骤6: 获取cookies和headers", "INFO")
                cookies = await context.cookies()
                self.log(f"获取到 {len(cookies)} 个cookies", "SUCCESS")

                # 转换cookies
                for cookie in cookies:
                    self.cookies[cookie['name']] = cookie['value']

                # 获取当前页面的URL作为referer
                current_url = page.url
                self.log(f"当前页面URL: {current_url}", "INFO")

                # 设置headers（包含referer）
                self.headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    'Referer': current_url,
                    'Accept': 'application/json, text/plain, */*',
                    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
                    'Content-Type': 'application/json;charset=UTF-8',
                    'Origin': BASE_URL,
                }

                # 保存认证信息
                auth_info = {
                    'cookies': self.cookies,
                    'headers': self.headers,
                    'current_url': current_url,
                    'timestamp': datetime.now().isoformat()
                }

                with open("haikang_auth_info.json", "w", encoding="utf-8") as f:
                    json.dump(auth_info, f, ensure_ascii=False, indent=2)
                self.log("认证信息已保存", "SUCCESS")

                # 步骤7: 尝试通过浏览器获取更多信息
                self.log("步骤7: 通过浏览器执行JavaScript获取数据", "INFO")

                # 检查是否有iframe
                frames = page.frames
                self.log(f"页面有 {len(frames)} 个frame", "INFO")

                for idx, frame in enumerate(frames):
                    frame_name = frame.name
                    frame_url = frame.url
                    self.log(f"  Frame[{idx}]: name='{frame_name}', url='{frame_url[:80]}...'", "INFO")

                # 尝试从iframe获取数据
                vms_frame = page.frame(name="vms_010100")
                if vms_frame:
                    self.log("找到VMS iframe，尝试获取数据...", "INFO")

                    # 尝试在iframe中执行JavaScript获取监控点数据
                    iframe_data = await vms_frame.evaluate("""
                        () => {
                            const result = {
                                page_text: document.body.innerText.substring(0, 2000),
                                all_elements_count: document.querySelectorAll('*').length,
                                visible_elements_count: 0,
                                left_panel_text: '',
                                tree_data: null
                            };

                            // 计算可见元素
                            const allElements = document.querySelectorAll('*');
                            allElements.forEach(el => {
                                const rect = el.getBoundingClientRect();
                                if (rect.width > 0 && rect.height > 0) {
                                    result.visible_elements_count++;
                                }
                            });

                            // 获取左侧面板文本
                            const leftElements = Array.from(document.querySelectorAll('*')).filter(el => {
                                const rect = el.getBoundingClientRect();
                                return rect.x >= 0 && rect.x < 250 && rect.width > 0;
                            });

                            const leftTexts = leftElements.map(el => (el.textContent || '').trim()).filter(t => t);
                            result.left_panel_text = leftTexts.join('\n').substring(0, 1000);

                            // 尝试查找window对象中的数据
                            if (window.__INITIAL_STATE__) {
                                result.tree_data = {initial_state: 'found'};
                            }

                            if (window.$store) {
                                result.tree_data = {vuex_store: 'found'};
                            }

                            // 尝试查找可能的API调用
                            const scripts = Array.from(document.querySelectorAll('script'));
                            const apiScripts = scripts.filter(s => {
                                const text = s.textContent || '';
                                return text.includes('api') || text.includes('tree') || text.includes('monitor');
                            });

                            result.api_script_count = apiScripts.length;

                            return result;
                        }
                    """)

                    self.log(f"iframe可见元素: {iframe_data['visible_elements_count']}", "INFO")
                    self.log(f"左侧面板文本: {iframe_data['left_panel_text'][:200]}", "INFO")

                    # 保存iframe数据
                    with open("haikang_iframe_data.json", "w", encoding="utf-8") as f:
                        json.dump(iframe_data, f, ensure_ascii=False, indent=2)
                    self.log("iframe数据已保存", "SUCCESS")

                # 保持浏览器打开，方便观察
                self.log("\n浏览器将保持打开30秒，请观察页面状态...", "INFO")
                await page.screenshot(path="final_page_state.png")
                self.log("已保存最终页面截图", "INFO")

                await asyncio.sleep(30000)

                return auth_info

            finally:
                await browser.close()

    def test_api_with_auth(self, url, method="GET", params=None, data=None):
        """使用完整的认证信息测试API"""
        self.log(f"\n测试API: {method} {url}", "INFO")

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
                    json=data,
                    headers=self.headers,
                    timeout=10
                )

            self.log(f"状态码: {response.status_code}", "INFO")

            if response.status_code == 200:
                try:
                    json_data = response.json()
                    self.log(f"响应数据长度: {len(json.dumps(json_data))} 字符", "SUCCESS")

                    # 保存响应
                    filename = f"api_with_auth_{datetime.now().strftime('%H%M%S')}.json"
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

    async def run_tests(self):
        """运行完整测试"""
        # 步骤1: 完整的浏览器流程
        auth_info = await self.complete_browser_flow()

        # 步骤2: 使用认证信息测试API
        self.log("\n" + "="*70, "SUCCESS")
        self.log("开始使用认证信息测试API", "SUCCESS")
        self.log("="*70, "SUCCESS")

        # 测试各种可能的API端点
        api_endpoints = [
            # 监控点相关
            f"{BASE_URL}/vms/ui/preview/monitor/tree",
            f"{BASE_URL}/vms/ui/preview/resource/tree",
            f"{BASE_URL}/vms/ui/resource/monitor/tree",
            f"{BASE_URL}/vms/ui/camera/monitor/tree",

            # 工具栏树
            f"{BASE_URL}/portal/front/toolbar/toolbarTree",

            # 组织机构
            f"{BASE_URL}/vms/ui/org/tree",
            f"{BASE_URL}/vms/ui/organization/tree",

            # 资源相关
            f"{BASE_URL}/vms/ui/resource/root",
            f"{BASE_URL}/vms/ui/preview/resource/root",
        ]

        for api_url in api_endpoints:
            result = self.test_api_with_auth(api_url)
            if result and isinstance(result, dict):
                # 检查是否包含数据
                if 'data' in result:
                    self.log(f"✅ API返回数据结构: {list(result.keys())}", "SUCCESS")
                elif 'code' in result:
                    self.log(f"API返回码: {result.get('code')}, 消息: {result.get('msg')}", "INFO")

        return auth_info


async def main():
    tester = CompleteFlowAPITester()

    try:
        result = await tester.run_tests()

        tester.log("\n" + "="*70, "SUCCESS")
        tester.log("完整流程测试完成！", "SUCCESS")
        tester.log("="*70, "SUCCESS")

    except Exception as e:
        tester.log(f"\n测试出错: {e}", "ERROR")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    print("""
╔════════════════════════════════════════════════════════════╗
║        海康完整流程API测试工具                           ║
╚════════════════════════════════════════════════════════════╝

完整流程：
1. 登录系统
2. 进入实时预览页面
3. 等待页面完全加载
4. 获取完整的cookies和headers（包括referer）
5. 测试多个API端点获取监控点数据

    """)

    asyncio.run(main())
