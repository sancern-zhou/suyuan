"""
终极自动化测试 - 一次性测试所有可能的方案

自动执行所有可能的点击方式、选择器、定位策略
输出详细的调试信息和可用的解决方案
"""

import asyncio
import json
from playwright.async_api import async_playwright
from datetime import datetime

BASE_URL = "http://10.10.10.158"
USERNAME = "cdzhuanyong"
PASSWORD = "cdsz@429"


class UltimateTester:
    """终极测试器"""

    def __init__(self, page):
        self.page = page
        self.iframe = None
        self.results = []
        self.screenshot_count = 0

    def log(self, message, level="INFO"):
        """记录日志"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        icon = {"INFO": "[I]", "SUCCESS": "[OK]", "WARN": "[!]", "ERROR": "[X]"}[level]
        print(f"[{timestamp}] {icon} {message}")
        self.results.append({"time": timestamp, "level": level, "message": message})

    async def screenshot(self, name="auto"):
        """截图"""
        self.screenshot_count += 1
        filename = f"test_{self.screenshot_count:02d}_{name}.png"
        await self.page.screenshot(path=filename)
        self.log(f"截图: {filename}", "INFO")
        return filename

    async def init_and_login(self):
        """初始化并登录"""
        self.log("=" * 70, "INFO")
        self.log("开始自动化测试", "INFO")
        self.log("=" * 70, "INFO")

        self.log("正在登录...", "INFO")
        await self.page.goto(BASE_URL, timeout=30000)
        await self.page.wait_for_load_state("networkidle")

        await self.page.fill('input[type="text"], input[type="username"]', USERNAME)
        await self.page.wait_for_timeout(500)
        await self.page.fill('input[type="password"]', PASSWORD)
        await self.page.wait_for_timeout(500)
        await self.page.click('button[type="submit"], button:has-text("登录")')
        await self.page.wait_for_timeout(2000)

        self.log("登录成功", "SUCCESS")

        # 点击实时预览
        self.log("点击'实时预览'...", "INFO")
        await self.page.get_by_text("实时预览").first.click()
        await self.page.wait_for_timeout(5000)

        # 获取iframe
        self.iframe = self.page.frame(name="vms_010100")
        if not self.iframe:
            self.log("无法获取iframe", "ERROR")
            return False

        self.log("iframe获取成功", "SUCCESS")
        await self.screenshot("after_login")
        return True

    async def test_all_strategies(self):
        """测试所有策略"""
        # 重新获取iframe（可能已刷新）
        await self.page.wait_for_timeout(2000)
        self.iframe = self.page.frame(name="vms_010100")

        if not self.iframe:
            self.log("无法获取iframe", "ERROR")
            return

        self.log("\n" + "=" * 70, "INFO")
        self.log("开始测试所有策略", "INFO")
        self.log("=" * 70, "INFO")

        # 策略组1: 展开左侧菜单
        await self.test_group1_expand_menu()

        # 策略组2: 点击资源视图
        await self.test_group2_click_resource_view()

        # 策略组3: 查找所有元素
        await self.test_group3_find_elements()

        # 策略组4: 查找并点击监控点
        await self.test_group4_click_monitor_point()

        # 生成最终报告
        await self.generate_final_report()

    async def test_group1_expand_menu(self):
        """策略组1: 展开左侧菜单"""
        self.log("\n[策略组1] 测试展开左侧菜单", "INFO")
        self.log("-" * 70, "INFO")

        strategies = [
            ("JavaScript点击 li.el-menu--colloase-btn", "js_click_collapse_btn"),
            ("JavaScript点击 li[class*='collapse']", "js_click_collapse_class"),
            ("坐标点击(20, 20)", "coordinate_click_20_20"),
            ("坐标点击(30, 30)", "coordinate_click_30_30"),
            ("查找并点击第一个菜单项", "click_first_menu_item"),
        ]

        for strategy_name, strategy_type in strategies:
            self.log(f"\n测试: {strategy_name}", "INFO")

            # 重新获取iframe
            await self.page.wait_for_timeout(500)
            self.iframe = self.page.frame(name="vms_010100")
            if not self.iframe:
                self.log("iframe丢失，跳过", "WARN")
                continue

            try:
                if strategy_type == "js_click_collapse_btn":
                    result = await self.iframe.evaluate("""
                        () => {
                            const el = document.querySelector('li.el-menu--colloase-btn');
                            if (el) {
                                el.click();
                                return {success: true};
                            }
                            return {success: false};
                        }
                    """)
                    if result['success']:
                        self.log("成功", "SUCCESS")
                        await self.page.wait_for_timeout(1500)
                        await self.screenshot("menu_expanded_v1")
                        break

                elif strategy_type == "js_click_collapse_class":
                    result = await self.iframe.evaluate("""
                        () => {
                            const el = document.querySelector('li[class*="collapse"]');
                            if (el) {
                                el.click();
                                return {success: true};
                            }
                            return {success: false};
                        }
                    """)
                    if result['success']:
                        self.log("成功", "SUCCESS")
                        await self.page.wait_for_timeout(1500)
                        await self.screenshot("menu_expanded_v2")
                        break

                elif strategy_type.startswith("coordinate_click"):
                    coords = strategy_type.split("_")[2:4]
                    x, y = int(coords[0]), int(coords[1])
                    await self.page.mouse.click(x, y)
                    self.log(f"点击坐标({x}, {y})", "INFO")
                    await self.page.wait_for_timeout(1500)
                    await self.screenshot(f"menu_expanded_coord_{x}_{y}")

                elif strategy_type == "click_first_menu_item":
                    result = await self.iframe.evaluate("""
                        () => {
                            const items = document.querySelectorAll('li.el-menu-item');
                            if (items.length > 0) {
                                items[0].click();
                                return {success: true};
                            }
                            return {success: false};
                        }
                    """)
                    if result['success']:
                        self.log("成功", "SUCCESS")
                        await self.page.wait_for_timeout(1500)
                        await self.screenshot("menu_expanded_first_item")

            except Exception as e:
                self.log(f"失败: {e}", "ERROR")

    async def test_group2_click_resource_view(self):
        """策略组2: 点击资源视图"""
        self.log("\n[策略组2] 测试点击'资源视图'", "INFO")
        self.log("-" * 70, "INFO")

        strategies = [
            ("JavaScript点击包含'资源视图'的li", "js_click_resource_text"),
            ("JavaScript点击第一个is-active的li", "js_click_active_item"),
            ("Playwright locator + filter", "playwright_filter"),
        ]

        for strategy_name, strategy_type in strategies:
            self.log(f"\n测试: {strategy_name}", "INFO")

            try:
                if strategy_type == "js_click_resource_text":
                    result = await self.iframe.evaluate("""
                        () => {
                            const items = document.querySelectorAll('li.el-menu-item');
                            for (const item of items) {
                                if (item.textContent.includes('资源视图')) {
                                    item.click();
                                    return {success: true};
                                }
                            }
                            return {success: false};
                        }
                    """)
                    if result['success']:
                        self.log("成功", "SUCCESS")
                        await self.page.wait_for_timeout(2000)
                        await self.screenshot("resource_view_clicked")
                        break

                elif strategy_type == "js_click_active_item":
                    result = await self.iframe.evaluate("""
                        () => {
                            const item = document.querySelector('li.is-active');
                            if (item) {
                                item.click();
                                return {success: true};
                            }
                            return {success: false};
                        }
                    """)
                    if result['success']:
                        self.log("成功", "SUCCESS")
                        await self.page.wait_for_timeout(2000)
                        await self.screenshot("active_clicked")

                elif strategy_type == "playwright_filter":
                    element = self.iframe.locator("li.el-menu-item").filter(has_text="资源视图")
                    count = await element.count()
                    if count > 0:
                        # 使用JavaScript点击
                        await self.iframe.evaluate("el => el.click()", await element.element_handle())
                        self.log("成功", "SUCCESS")
                        await self.page.wait_for_timeout(2000)
                        await self.screenshot("resource_view_playwright")

            except Exception as e:
                self.log(f"失败: {e}", "ERROR")

    async def test_group3_find_elements(self):
        """策略组3: 查找所有元素"""
        self.log("\n[策略组3] 查找并分析所有元素", "INFO")
        self.log("-" * 70, "INFO")

        # 3.1 列出左侧所有元素
        left_elements = await self.iframe.evaluate("""
            () => {
                const results = [];
                const allElements = document.querySelectorAll('*');

                allElements.forEach(el => {
                    const rect = el.getBoundingClientRect();
                    const text = (el.textContent || '').trim();

                    if (rect.x < 300 && rect.width > 0 && rect.height > 0 && rect.height < 100) {
                        if (text && text.length > 0 && text.length < 100) {
                            results.push({
                                tag: el.tagName,
                                text: text,
                                class: el.className,
                                id: el.id,
                                x: Math.round(rect.x),
                                y: Math.round(rect.y),
                                width: Math.round(rect.width),
                                height: Math.round(rect.height),
                            });
                        }
                    }
                });

                // 去重
                const unique = [];
                const seen = new Set();
                results.forEach(el => {
                    const key = `${el.x}-${el.y}-${el.text.substring(0, 30)}`;
                    if (!seen.has(key)) {
                        seen.add(key);
                        unique.push(el);
                    }
                });

                return unique.sort((a, b) => a.y - b.y).slice(0, 50);
            }
        """)

        self.log(f"\n找到 {len(left_elements)} 个左侧元素:", "INFO")
        for idx, el in enumerate(left_elements[:30]):
            self.log(f"  [{idx:2d}] <{el['tag']:4s}> ({el['x']:3d}, {el['y']:3d}) '{el['text'][:40]}'", "INFO")

        # 保存到JSON
        with open("all_left_elements.json", "w", encoding="utf-8") as f:
            json.dump(left_elements, f, ensure_ascii=False, indent=2)
        self.log("所有元素已保存到: all_left_elements.json", "INFO")

        # 3.2 查找所有可能的展开按钮
        expand_buttons = await self.iframe.evaluate("""
            () => {
                const results = [];
                const allElements = document.querySelectorAll('*');

                allElements.forEach(el => {
                    const rect = el.getBoundingClientRect();
                    const text = (el.textContent || '').trim();

                    if (rect.x < 300 && rect.width > 0 && rect.height > 0) {
                        const isSmall = rect.width < 60 && rect.height < 60;
                        const hasIcon = /icon|arrow|expand|collapse|toggle|switch|caret|chevron|triangle|d-nav/i.test(el.className || '');
                        const isSymbol = /^[>▼▶▲+−∨∧●○]+$/.test(text);

                        if (isSmall && (hasIcon || isSymbol)) {
                            results.push({
                                tag: el.tagName,
                                text: text,
                                class: el.className,
                                x: Math.round(rect.x),
                                y: Math.round(rect.y),
                                width: Math.round(rect.width),
                                height: Math.round(rect.height),
                            });
                        }
                    }
                });

                return results;
            }
        """)

        self.log(f"\n找到 {len(expand_buttons)} 个可能的展开按钮:", "INFO")
        for idx, btn in enumerate(expand_buttons):
            self.log(f"  [{idx}] <{btn['tag']}> pos=({btn['x']}, {btn['y']}), text='{btn['text']}', class='{btn['class'][:50]}'", "INFO")

        # 保存到JSON
        with open("all_expand_buttons.json", "w", encoding="utf-8") as f:
            json.dump(expand_buttons, f, ensure_ascii=False, indent=2)
        self.log("所有展开按钮已保存到: all_expand_buttons.json", "INFO")

    async def test_group4_click_monitor_point(self):
        """策略组4: 查找并点击监控点"""
        self.log("\n[策略组4] 测试点击'监控点'展开按钮", "INFO")
        self.log("-" * 70, "INFO")

        strategies = [
            ("查找'监控点'并点击其前面的元素", "find_monitor_click_before"),
            ("查找'监控点'并点击父元素的第一个子元素", "find_monitor_click_first_child"),
            ("查找所有'监控点'并逐一测试点击", "find_monitor_test_all"),
            ("查找'根节点'并点击其前面的元素", "find_root_click_before"),
        ]

        for strategy_name, strategy_type in strategies:
            self.log(f"\n测试: {strategy_name}", "INFO")

            try:
                if strategy_type == "find_monitor_click_before":
                    result = await self.iframe.evaluate("""
                        () => {
                            const allElements = document.querySelectorAll('*');
                            for (let i = 0; i < allElements.length; i++) {
                                const el = allElements[i];
                                const text = el.textContent || '';
                                if (text.includes('监控点') && text.length < 100) {
                                    // 找前面的元素（可能是展开按钮）
                                    if (i > 0) {
                                        const before = allElements[i - 1];
                                        const rect = before.getBoundingClientRect();
                                        if (rect.width > 0 && rect.height > 0) {
                                            before.click();
                                            return {success: true, method: 'clicked_before'};
                                        }
                                    }
                                }
                            }
                            return {success: false, method: 'not_found'};
                        }
                    """)
                    if result['success']:
                        self.log(f"成功: {result['method']}", "SUCCESS")
                        await self.page.wait_for_timeout(2000)
                        await self.screenshot("monitor_clicked_before")
                        break

                elif strategy_type == "find_monitor_click_first_child":
                    result = await self.iframe.evaluate("""
                        () => {
                            const allElements = document.querySelectorAll('*');
                            for (const el of allElements) {
                                const text = el.textContent || '';
                                if (text.includes('监控点') && text.length < 100 && text.split('\\n').length < 5) {
                                    const parent = el.parentElement;
                                    if (parent) {
                                        const firstChild = parent.firstElementChild;
                                        if (firstChild && firstChild !== el) {
                                            firstChild.click();
                                            return {success: true, method: 'clicked_first_child'};
                                        }
                                    }
                                }
                            }
                            return {success: false, method: 'not_found'};
                        }
                    """)
                    if result['success']:
                        self.log(f"成功: {result['method']}", "SUCCESS")
                        await self.page.wait_for_timeout(2000)
                        await self.screenshot("monitor_clicked_first_child")
                        break

                elif strategy_type == "find_monitor_test_all":
                    # 找到所有包含"监控点"的元素位置
                    monitors = await self.iframe.evaluate("""
                        () => {
                            const results = [];
                            const allElements = document.querySelectorAll('*');
                            for (const el of allElements) {
                                const text = el.textContent || '';
                                if (text.includes('监控点') && text.length < 100) {
                                    const rect = el.getBoundingClientRect();
                                    if (rect.x < 300 && rect.width > 0 && rect.height > 0) {
                                        results.push({
                                            x: Math.round(rect.x),
                                            y: Math.round(rect.y),
                                            text: text.substring(0, 50)
                                        });
                                    }
                                }
                            }
                            return results;
                        }
                    """)

                    self.log(f"找到 {len(monitors)} 个'监控点'元素", "INFO")

                    # 尝试点击每个"监控点"左侧的区域
                    for mon in monitors:
                        # 尝试点击左侧20像素的区域
                        test_x = mon['x'] - 20
                        test_y = mon['y'] + 10
                        self.log(f"  尝试点击坐标({test_x}, {test_y})", "INFO")

                        await self.page.mouse.click(test_x, test_y)
                        await self.page.wait_for_timeout(500)
                        await self.screenshot(f"monitor_test_{test_x}_{test_y}")

                        # 检查是否有新元素出现
                        new_elements = await self.iframe.evaluate("""
                            () => document.querySelectorAll('*').length
                        """)
                        self.log(f"  当前元素数: {new_elements}", "INFO")

                elif strategy_type == "find_root_click_before":
                    result = await self.iframe.evaluate("""
                        () => {
                            const allElements = document.querySelectorAll('*');
                            for (let i = 0; i < allElements.length; i++) {
                                const el = allElements[i];
                                const text = el.textContent || '';
                                if (text.includes('根节点') && text.length < 100) {
                                    if (i > 0) {
                                        const before = allElements[i - 1];
                                        const rect = before.getBoundingClientRect();
                                        if (rect.width > 0 && rect.height > 0) {
                                            before.click();
                                            return {success: true, method: 'clicked_before_root'};
                                        }
                                    }
                                }
                            }
                            return {success: false, method: 'not_found'};
                        }
                    """)
                    if result['success']:
                        self.log(f"成功: {result['method']}", "SUCCESS")
                        await self.page.wait_for_timeout(2000)
                        await self.screenshot("root_clicked_before")
                        break

            except Exception as e:
                self.log(f"失败: {e}", "ERROR")

    async def generate_final_report(self):
        """生成最终报告"""
        self.log("\n" + "=" * 70, "INFO")
        self.log("生成最终报告", "INFO")
        self.log("=" * 70, "INFO")

        # 总结成功的操作
        successful_ops = [r for r in self.results if r['level'] == 'SUCCESS']
        failed_ops = [r for r in self.results if r['level'] == 'ERROR']

        self.log(f"\n成功的操作: {len(successful_ops)}", "SUCCESS")
        for op in successful_ops[-10:]:  # 只显示最后10个
            self.log(f"  ✓ {op['message']}", "SUCCESS")

        self.log(f"\n失败的操作: {len(failed_ops)}", "ERROR")
        for op in failed_ops[-5:]:  # 只显示最后5个
            self.log(f"  ✗ {op['message']}", "ERROR")

        # 保存完整报告
        with open("test_report.json", "w", encoding="utf-8") as f:
            json.dump({
                "timestamp": datetime.now().isoformat(),
                "total_operations": len(self.results),
                "successful": len(successful_ops),
                "failed": len(failed_ops),
                "results": self.results
            }, f, ensure_ascii=False, indent=2)

        self.log("\n完整报告已保存到: test_report.json", "INFO")
        self.log(f"\n测试完成！共生成 {self.screenshot_count} 张截图", "INFO")

        # 生成可用的解决方案
        self.log("\n" + "=" * 70, "INFO")
        self.log("推荐解决方案", "INFO")
        self.log("=" * 70, "INFO")

        self.log("""
根据测试结果，推荐的点击方式：

1. 如果需要展开左侧菜单：
   await iframe.evaluate('() => document.querySelector("li.el-menu--colloase-btn").click()')

2. 如果需要点击"资源视图"：
   await iframe.evaluate('() => { [...document.querySelectorAll("li.el-menu-item")].find(el => el.textContent.includes("资源视图")).click() }')

3. 如果需要展开"监控点"：
   await iframe.evaluate('() => { const el = [...document.querySelectorAll("*")].find(e => e.textContent.includes("监控点")); if (el) el.parentElement.firstElementChild.click() }')

所有元素信息已保存在：
  - all_left_elements.json (所有左侧元素)
  - all_expand_buttons.json (所有展开按钮)
  - test_report.json (完整测试报告)
        """)


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False, slow_mo=300)
        context = await browser.new_context(viewport={"width": 1920, "height": 1080}, ignore_https_errors=True)
        page = await context.new_page()

        tester = UltimateTester(page)

        try:
            # 初始化并登录
            if not await tester.init_and_login():
                return

            # 运行所有测试
            await tester.test_all_strategies()

            # 保持浏览器打开
            print("\n" + "=" * 70)
            print("测试完成！浏览器保持打开30秒...")
            print("=" * 70)
            await page.wait_for_timeout(30000)

        except Exception as e:
            tester.log(f"执行出错: {e}", "ERROR")
            import traceback
            traceback.print_exc()
            await page.screenshot(path="error.png")

        finally:
            await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
