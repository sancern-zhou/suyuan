"""
海康视频平台 H5 模式测试脚本

目标：绕过 OCX 控件，使用内置 H5 播放器访问监控数据

测试策略：
1. 检测 OCX 控件状态
2. 尝试切换到 H5 模式
3. 监控 H5 模式下的 API 请求
4. 分析 H5 模式的数据加载方式
"""

import asyncio
import json
from datetime import datetime
from playwright.async_api import async_playwright

BASE_URL = "http://10.10.10.158"
USERNAME = "cdzhuanyong"
PASSWORD = "cdsz@429"


class H5ModeTester:
    """H5 模式测试器"""

    def __init__(self, page):
        self.page = page
        self.iframe = None
        self.api_requests = []

    def log(self, message, level="INFO"):
        timestamp = datetime.now().strftime("%H:%M:%S")
        icon = {"INFO": "ℹ️", "SUCCESS": "✅", "WARN": "⚠️", "ERROR": "❌"}[level]
        print(f"[{timestamp}] {icon} {message}")

    async def setup_request_monitoring(self):
        """设置请求监控"""
        def log_request(request):
            url = request.url
            method = request.method
            resource_type = request.resource_type

            # 只记录 API 请求
            if any(keyword in url.lower() for keyword in ['api', 'vms', 'camera', 'monitor', 'tree', 'resource']):
                self.api_requests.append({
                    'url': url,
                    'method': method,
                    'type': resource_type,
                    'timestamp': datetime.now().isoformat()
                })
                self.log(f"[API] {method} {url[:80]}", "INFO")

        def log_response(response):
            if response.status >= 400:
                self.log(f"[ERROR] {response.status} {response.url[:60]}", "ERROR")
            elif 'api' in response.url.lower() or 'vms' in response.url.lower():
                self.log(f"[OK] {response.status} {response.url[:80]}", "SUCCESS")

        self.page.on("request", log_request)
        self.page.on("response", log_response)

    async def auto_login(self):
        """自动登录"""
        self.log("访问登录页...", "INFO")
        await self.page.goto(BASE_URL, timeout=30000)
        await self.page.wait_for_load_state("networkidle")

        self.log("输入账号密码...", "INFO")
        await self.page.fill('input[type="text"], input[type="username"]', USERNAME)
        await self.page.wait_for_timeout(500)
        await self.page.fill('input[type="password"]', PASSWORD)
        await self.page.wait_for_timeout(500)

        self.log("点击登录按钮...", "INFO")
        await self.page.click('button[type="submit"], button:has-text("登录")')
        await self.page.wait_for_timeout(3000)

        self.log("JavaScript点击'实时预览'...", "INFO")
        await self.page.evaluate("""
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
        await self.page.wait_for_timeout(5000)

    async def test_01_detect_ocx_status(self):
        """测试1: 检测 OCX 控件状态"""
        self.log("\n" + "="*70, "INFO")
        self.log("测试1: 检测 OCX 控件和 H5 播放器状态", "INFO")
        self.log("="*70, "INFO")

        status = await self.page.evaluate("""
            () => {
                const result = {
                    ocx_messages: [],
                    h5_available: false,
                    page_text: document.body.innerText.substring(0, 1000),
                    has_object_tag: false,
                    has_embed_tag: false,
                    active_x_enabled: false
                };

                // 检查页面文本中的关键信息
                if (result.page_text.includes('OCX') || result.page_text.includes('控件')) {
                    result.ocx_messages.push('Found OCX references in page text');
                }

                if (result.page_text.includes('内置H5播放器') || result.page_text.includes('H5')) {
                    result.h5_available = true;
                }

                if (result.page_text.includes('控件未安装') || result.page_text.includes('加载失败')) {
                    result.ocx_messages.push('Control not installed or failed to load');
                }

                // 检查 OBJECT 和 EMBED 标签（OCX 控件）
                const objects = document.querySelectorAll('object, embed');
                result.has_object_tag = objects.length > 0;
                result.active_x_enabled = result.has_object_tag;

                // 检查是否有 H5 相关的元素
                const videoElements = document.querySelectorAll('video, canvas');
                result.has_h5_elements = videoElements.length > 0;

                // 查找所有可能的控件相关元素
                const allElements = document.querySelectorAll('*');
                const controlRelated = [];
                allElements.forEach(el => {
                    const text = (el.textContent || '').trim();
                    if (text.includes('下载安装') || text.includes('控件') ||
                        text.includes('H5播放器') || text.includes('内置')) {
                        if (text.length < 200 && text.length > 10) {
                            controlRelated.push({
                                tag: el.tagName,
                                text: text.substring(0, 100),
                                className: el.className
                            });
                        }
                    }
                });

                result.control_elements = controlRelated.slice(0, 10);

                return result;
            }
        """)

        self.log(f"OCX 控件状态: {'已检测到' if status['has_object_tag'] else '未检测到'}", "INFO")
        self.log(f"H5 播放器: {'可用' if status['h5_available'] else '未找到'}", "INFO")

        if status['ocx_messages']:
            self.log("OCX 相关消息:", "WARN")
            for msg in status['ocx_messages']:
                self.log(f"  - {msg}", "WARN")

        if status['control_elements']:
            self.log("控件相关元素:", "INFO")
            for el in status['control_elements']:
                self.log(f"  <{el['tag']}> {el['text'][:80]}", "INFO")

        await self.page.screenshot(path="ocx_status_check.png")
        return status

    async def test_02_switch_to_h5_mode(self):
        """测试2: 尝试切换到 H5 模式"""
        self.log("\n" + "="*70, "INFO")
        self.log("测试2: 尝试切换到 H5 模式", "INFO")
        self.log("="*70, "INFO")

        # 查找并点击 H5 播放器选项
        switch_result = await self.page.evaluate("""
            () => {
                const result = {
                    found_h5_option: false,
                    clicked: false,
                    method: ''
                };

                // 方法1: 查找包含"H5播放器"或"内置H5"的元素
                const allElements = document.querySelectorAll('*');
                for (const el of allElements) {
                    const text = el.textContent || '';
                    if ((text.includes('H5播放器') || text.includes('内置H5')) &&
                        text.length < 100) {
                        result.found_h5_option = true;
                        // 尝试点击
                        try {
                            el.click();
                            result.clicked = true;
                            result.method = 'direct_click';
                            return result;
                        } catch (e) {}
                    }
                }

                // 方法2: 查找可能的按钮或链接
                const buttons = document.querySelectorAll('button, a, div[onclick], div[class*="btn"]');
                for (const btn of buttons) {
                    const text = btn.textContent || '';
                    if (text.includes('内置H5') || text.includes('H5播放器')) {
                        result.found_h5_option = true;
                        try {
                            btn.click();
                            result.clicked = true;
                            result.method = 'button_click';
                            return result;
                        } catch (e) {}
                    }
                }

                // 方法3: 查找包含播放器选项的对话框
                const dialogs = document.querySelectorAll('[role="dialog"], .modal, .el-dialog');
                for (const dialog of dialogs) {
                    const text = dialog.textContent || '';
                    if (text.includes('H5')) {
                        result.found_h5_option = true;
                        result.found_in_dialog = true;

                        // 在对话框中查找 H5 选项
                        const clickable = dialog.querySelectorAll('button, a, div[onclick]');
                        for (const item of clickable) {
                            const itemText = item.textContent || '';
                            if (itemText.includes('内置H5') || itemText.includes('H5播放器')) {
                                try {
                                    item.click();
                                    result.clicked = true;
                                    result.method = 'dialog_click';
                                    return result;
                                } catch (e) {}
                            }
                        }
                    }
                }

                return result;
            }
        """)

        if switch_result['found_h5_option']:
            self.log(f"找到 H5 选项: {switch_result['method']}", "SUCCESS")
            if switch_result['clicked']:
                self.log("已点击 H5 选项", "SUCCESS")
                await asyncio.sleep(3)
                await self.page.screenshot(path="after_h5_switch.png")
            else:
                self.log("点击失败", "WARN")
        else:
            self.log("未找到 H5 选项", "WARN")

        return switch_result

    async def test_03_analyze_h5_page_structure(self):
        """测试3: 分析 H5 模式下的页面结构"""
        self.log("\n" + "="*70, "INFO")
        self.log("测试3: 分析 H5 模式页面结构", "INFO")
        self.log("="*70, "INFO")

        # 获取 iframe
        self.iframe = self.page.frame(name="vms_010100")
        if not self.iframe:
            self.log("未找到iframe", "WARN")
            return {}

        structure = await self.iframe.evaluate("""
            () => {
                const result = {
                    total_elements: 0,
                    visible_elements: 0,
                    iframe_text: document.body.innerText.substring(0, 2000),
                    left_panel_elements: [],
                    api_indicators: [],
                    data_elements: []
                };

                const allElements = document.querySelectorAll('*');
                result.total_elements = allElements.length;

                allElements.forEach(el => {
                    const rect = el.getBoundingClientRect();
                    const isVisible = rect.width > 0 && rect.height > 0;

                    if (isVisible) {
                        result.visible_elements++;

                        // 左侧面板元素
                        if (rect.x < 250) {
                            const text = (el.textContent || '').trim().substring(0, 50);
                            if (text && text.length > 2 && text.length < 100) {
                                result.left_panel_elements.push({
                                    tag: el.tagName,
                                    text: text,
                                    className: el.className,
                                    x: Math.round(rect.x),
                                    y: Math.round(rect.y)
                                });
                            }
                        }
                    }
                });

                // 查找可能的 API 指示器
                const scripts = document.querySelectorAll('script');
                scripts.forEach(script => {
                    const src = script.src || '';
                    const text = script.textContent || '';
                    if (src.includes('api') || text.includes('ajax') ||
                        text.includes('fetch') || text.includes('axios')) {
                        result.api_indicators.push({
                            type: 'script',
                            src: src.substring(0, 100),
                            has_ajax: text.includes('ajax') || text.includes('fetch')
                        });
                    }
                });

                // 查找可能包含数据的元素
                const dataAttrs = document.querySelectorAll('[data-*]');
                result.has_data_attributes = dataAttrs.length > 0;

                return result;
            }
        """)

        self.log(f"iframe 总元素: {structure['total_elements']}", "INFO")
        self.log(f"可见元素: {structure['visible_elements']}", "INFO")
        self.log(f"左侧面板元素: {len(structure['left_panel_elements'])} 个", "INFO")

        for el in structure['left_panel_elements'][:20]:
            self.log(f"  <{el['tag']}> {el['text'][:40]}", "INFO")

        if structure['api_indicators']:
            self.log(f"API 指示器: {len(structure['api_indicators'])} 个", "INFO")

        await self.page.screenshot(path="h5_page_structure.png")
        return structure

    async def test_04_monitor_api_requests(self):
        """测试4: 监控 API 请求"""
        self.log("\n" + "="*70, "INFO")
        self.log("测试4: 尝试触发并监控 API 请求", "INFO")
        self.log("="*70, "INFO")

        # 清空之前的请求记录
        before_count = len(self.api_requests)
        self.log(f"当前 API 请求: {before_count} 个", "INFO")

        # 尝试触发 API 请求
        if self.iframe:
            await self.iframe.evaluate("""
                () => {
                    // 尝试点击左侧面板的所有可点击元素
                    const leftElements = Array.from(document.querySelectorAll('*')).filter(el => {
                        const rect = el.getBoundingClientRect();
                        return rect.x >= 0 && rect.x < 200 && rect.width > 0 && rect.height > 0;
                    });

                    // 按Y坐标排序
                    leftElements.sort((a, b) => {
                        const rectA = a.getBoundingClientRect();
                        const rectB = b.getBoundingClientRect();
                        return rectA.y - rectB.y;
                    });

                    // 点击前10个
                    for (let i = 0; i < Math.min(10, leftElements.length); i++) {
                        try {
                            leftElements[i].click();
                        } catch (e) {}
                    }

                    return {clicked: Math.min(10, leftElements.length)};
                }
            """)

            await asyncio.sleep(3)

        after_count = len(self.api_requests)
        new_requests = after_count - before_count

        self.log(f"新增 API 请求: {new_requests} 个", "INFO")

        if new_requests > 0:
            self.log("新增的 API 请求:", "SUCCESS")
            for req in self.api_requests[before_count:]:
                self.log(f"  [{req['method']}] {req['url'][:80]}", "INFO")

        return self.api_requests

    async def test_05_network_tab_analysis(self):
        """测试5: 网络标签分析"""
        self.log("\n" + "="*70, "INFO")
        self.log("测试5: 分析网络请求和响应", "INFO")
        self.log("="*70, "INFO")

        # 尝试通过 CDP (Chrome DevTools Protocol) 获取网络日志
        try:
            # 获取所有网络请求
            network_log = await self.page.evaluate("""
                () => {
                    // 这个方法可能不工作，因为浏览器安全限制
                    // 但我们试试看能否获取一些性能数据
                    if (window.performance && window.performance.getEntries) {
                        const entries = window.performance.getEntries();
                        return entries.filter(e => e.entryType === 'resource')
                            .map(e => ({
                                name: e.name.substring(0, 100),
                                type: e.initiatorType,
                                duration: Math.round(e.duration)
                            }))
                            .slice(0, 20);
                    }
                    return [];
                }
            """)

            if network_log:
                self.log(f"性能日志: {len(network_log)} 条", "INFO")
                for entry in network_log:
                    self.log(f"  [{entry['type']}] {entry['name'][:60]} ({entry['duration']}ms)", "INFO")

        except Exception as e:
            self.log(f"无法获取性能日志: {e}", "WARN")

        return network_log if network_log else []

    async def save_results(self):
        """保存测试结果"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"h5_mode_test_{timestamp}.json"

        results = {
            'timestamp': timestamp,
            'api_requests': self.api_requests,
            'total_api_count': len(self.api_requests)
        }

        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2)

        self.log(f"结果已保存: {filename}", "INFO")


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,
            slow_mo=500,
            args=['--ignore-certificate-errors']
        )
        context = await browser.new_context(
            viewport={"width": 1920, "height": 1080},
            ignore_https_errors=True
        )
        page = await context.new_page()

        tester = H5ModeTester(page)

        try:
            # 设置请求监控
            await tester.setup_request_monitoring()

            # 登录
            await tester.auto_login()

            # 执行测试
            await tester.test_01_detect_ocx_status()
            await tester.test_02_switch_to_h5_mode()
            await tester.test_03_analyze_h5_page_structure()
            await tester.test_04_monitor_api_requests()
            await tester.test_05_network_tab_analysis()

            # 保存结果
            await tester.save_results()

            tester.log("\n" + "="*70, "SUCCESS")
            tester.log("H5 模式测试完成！", "SUCCESS")
            tester.log("="*70, "SUCCESS")

            tester.log("\n浏览器保持打开60秒，请手动检查...", "INFO")
            await asyncio.sleep(60)

        except Exception as e:
            tester.log(f"\n测试出错: {e}", "ERROR")
            import traceback
            traceback.print_exc()
            await page.screenshot(path="h5_error.png")

        finally:
            await browser.close()


if __name__ == "__main__":
    print("""
╔════════════════════════════════════════════════════════════╗
║        海康H5模式测试工具                                 ║
╚════════════════════════════════════════════════════════════╝

测试目标：
1. 检测 OCX 控件状态
2. 尝试切换到 H5 模式
3. 分析 H5 模式页面结构
4. 监控 API 请求
5. 网络请求分析

    """)

    asyncio.run(main())
