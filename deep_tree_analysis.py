"""
深度分析树形控件结构

针对"资源视图"、"轮巡分组"等文本
找出真正的DOM结构和可点击元素
"""

import asyncio
import json
from playwright.async_api import async_playwright
from datetime import datetime

BASE_URL = "http://10.10.10.158"
USERNAME = "cdzhuanyong"
PASSWORD = "cdsz@429"


class DeepTreeAnalyzer:
    """深度树形分析器"""

    def __init__(self, page):
        self.page = page
        self.iframe = None

    def log(self, message, level="INFO"):
        """记录日志"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        icon = {"INFO": "ℹ", "SUCCESS": "✓", "WARN": "⚠", "ERROR": "✗"}[level]
        print(f"[{timestamp}] {icon} {message}")

    async def auto_login_and_enter(self):
        """自动登录并进入实时预览"""
        self.log("访问登录页...", "INFO")
        await self.page.goto(BASE_URL, timeout=30000)
        await self.page.wait_for_load_state("networkidle")

        self.log("输入账号密码...", "INFO")
        await self.page.fill('input[type="text"], input[type="username"]', USERNAME)
        await self.page.wait_for_timeout(500)
        await self.page.fill('input[type="password"]', PASSWORD)
        await self.page.wait_for_timeout(500)

        self.log("点击登录按钮...", "INFO")
        await self.page.click('button[type="submit"], button:has-text("登录"), button:has-text("登 录")')
        await self.page.wait_for_load_state("networkidle", timeout=10000)
        await self.page.wait_for_timeout(2000)

        self.log("点击'实时预览'...", "INFO")
        await self.page.get_by_text("实时预览").first.click()

        self.log("等待iframe内容加载...", "INFO")
        await self.page.wait_for_timeout(5000)  # 等待5秒

    async def get_iframe(self):
        """获取iframe"""
        self.iframe = self.page.frame(name="vms_010100")
        if self.iframe:
            self.log("iframe获取成功", "SUCCESS")
        else:
            self.log("无法获取iframe", "ERROR")

    async def deep_analyze_tree_structure(self):
        """深度分析树形结构"""
        if not self.iframe:
            return

        self.log("=" * 70)
        self.log("深度分析树形控件结构", "INFO")
        self.log("=" * 70)

        # 1. 找到包含"资源视图"的所有元素及其父级
        self.log("\n[1] 分析'资源视图'元素的DOM结构:", "INFO")
        resource_view = await self.iframe.evaluate("""
            () => {
                const results = [];
                const allElements = document.querySelectorAll('*');

                allElements.forEach(el => {
                    const text = el.textContent || '';
                    if (text.includes('资源视图') && text.length < 200) {
                        // 获取完整的路径信息
                        const path = [];
                        let current = el;
                        while (current && current !== document.body) {
                            const tagName = current.tagName;
                            const id = current.id ? `#${current.id}` : '';
                            const className = current.className ? `.${current.className.split(' ')[0]}` : '';
                            path.unshift(`${tagName}${id}${className}`);

                            // 只取前5层
                            if (path.length >= 5) break;
                            current = current.parentElement;
                        }

                        results.push({
                            tagName: el.tagName,
                            text: text.trim().substring(0, 50),
                            id: el.id,
                            className: el.className,
                            role: el.getAttribute('role'),
                            onclick: el.getAttribute('onclick') ? '有' : '无',
                            path: path.join(' > '),  // 修复：使用JavaScript的join
                            hasChildren: el.children.length > 0,
                            childCount: el.children.length,
                        });
                    }
                });

                return results.slice(0, 5);
            }
        """)

        for idx, el in enumerate(resource_view):
            self.log(f"\n  元素[{idx}]:", "INFO")
            self.log(f"    标签: {el['tagName']}", "INFO")
            self.log(f"    文本: {el['text']}", "INFO")
            self.log(f"    ID: {el['id']}", "INFO")
            self.log(f"    Class: {el['className'][:80] if el['className'] else '无'}", "INFO")
            self.log(f"    Role: {el['role']}", "INFO")
            self.log(f"    点击事件: {el['onclick']}", "INFO")
            self.log(f"    子元素数: {el['childCount']}", "INFO")
            self.log(f"    DOM路径: {el['path']}", "INFO")

        # 2. 分析所有有 onclick 或 cursor: pointer 的元素
        self.log("\n[2] 查找可点击元素 (有onclick或cursor:pointer):", "INFO")
        clickable_elements = await self.iframe.evaluate("""
            () => {
                const results = [];
                const allElements = document.querySelectorAll('*');

                allElements.forEach(el => {
                    const hasOnclick = el.getAttribute('onclick') !== null;
                    const style = window.getComputedStyle(el);
                    const hasPointer = style.cursor === 'pointer';

                    if (hasOnclick || hasPointer) {
                        const text = el.textContent?.trim().substring(0, 50) || '';
                        if (text && text.length > 0 && text.length < 100) {
                            results.push({
                                tagName: el.tagName,
                                text: text,
                                id: el.id,
                                className: el.className,
                                hasOnclick: hasOnclick,
                                hasPointer: hasPointer,
                                visible: el.offsetParent !== null,
                            });
                        }
                    }
                });

                return results.slice(0, 15);
            }
        """)

        if clickable_elements:
            self.log(f"找到 {len(clickable_elements)} 个可点击元素", "SUCCESS")
            for idx, el in enumerate(clickable_elements):
                visible = "✓" if el['visible'] else "✗"
                click_type = []
                if el['hasOnclick']:
                    click_type.append("onclick")
                if el['hasPointer']:
                    click_type.append("cursor:pointer")
                self.log(f"\n  [{visible}] 元素[{idx}]: {el['text']}", "INFO")
                self.log(f"      标签: {el['tagName']}, Class: {el['className'][:60] if el['className'] else '无'}", "INFO")
                self.log(f"      点击类型: {', '.join(click_type)}", "INFO")
        else:
            self.log("未找到可点击元素", "WARN")

        # 3. 分析包含"轮巡分组"的元素
        self.log("\n[3] 分析'轮巡分组'元素:", "INFO")
        lunxun_elements = await self.iframe.evaluate("""
            () => {
                const results = [];
                const allElements = document.querySelectorAll('*');

                allElements.forEach(el => {
                    const text = el.textContent || '';
                    if (text.includes('轮巡分组') && text.length < 100) {
                        const rect = el.getBoundingClientRect();
                        if (rect.width > 0 && rect.height > 0) {
                            results.push({
                                tagName: el.tagName,
                                text: text.trim(),
                                id: el.id,
                                className: el.className,
                                parentTag: el.parentElement?.tagName,
                                parentClass: el.parentElement?.className,
                            });
                        }
                    }
                });

                return results.slice(0, 3);
            }
        """)

        for el in lunxun_elements:
            self.log(f"  标签: {el['tagName']}, 文本: {el['text']}", "INFO")
            self.log(f"  父元素: {el['parentTag']}, class: {el['parentClass'][:60] if el['parentClass'] else '无'}", "INFO")

        # 4. 查找所有 class 包含特定关键词的元素
        self.log("\n[4] 查找特定class模式的元素:", "INFO")
        class_patterns = await self.iframe.evaluate("""
            () => {
                const results = {};
                const patterns = ['node', 'item', 'view', 'group', 'tree', 'nav', 'menu'];

                patterns.forEach(pattern => {
                    const selector = `[class*="${pattern}"]`;
                    const elements = document.querySelectorAll(selector);
                    if (elements.length > 0) {
                        results[pattern] = {
                            count: elements.length,
                            samples: Array.from(elements).slice(0, 2).map(el => ({
                                tag: el.tagName,
                                class: el.className,
                                text: (el.textContent || '').trim().substring(0, 30)
                            }))
                        };
                    }
                });

                return results;
            }
        """)

        if class_patterns:
            self.log(f"找到 {len(class_patterns)} 种class模式", "SUCCESS")
            for pattern, info in class_patterns.items():
                self.log(f"\n  模式 '{pattern}': {info['count']}个元素", "INFO")
                for sample in info['samples']:
                    self.log(f"    <{sample['tag']}> class='{sample['class'][:60]}' → '{sample['text']}'", "INFO")

        # 5. 导出完整的HTML片段（包含"资源视图"的元素及其周围）
        self.log("\n[5] 导出关键HTML片段:", "INFO")
        html_fragment = await self.iframe.evaluate("""
            () => {
                // 找到包含"资源视图"的元素
                const allElements = document.querySelectorAll('*');
                for (const el of allElements) {
                    const text = el.textContent || '';
                    if (text.includes('资源视图') && text.length < 200) {
                        // 获取其父元素（用于看上下文）
                        const parent = el.parentElement;
                        if (parent) {
                            return parent.outerHTML.substring(0, 1000);
                        }
                    }
                }
                return '未找到';
            }
        """)
        print("\n" + "=" * 70)
        print("HTML片段:")
        print("=" * 70)
        print(html_fragment)
        print("=" * 70)

    async def test_click_strategies(self):
        """测试点击策略"""
        if not self.iframe:
            return

        self.log("\n" + "=" * 70)
        self.log("测试点击策略", "INFO")
        self.log("=" * 70)

        strategies = [
            ("文本匹配: 资源视图", "get_by_text"),
            ("文本匹配: 轮巡分组", "get_by_text_lx"),
            ("坐标点击（视觉）", "coordinates"),
        ]

        for strategy_name, strategy_type in strategies:
            self.log(f"\n测试: {strategy_name}", "INFO")

            if strategy_type == "get_by_text":
                try:
                    element = self.iframe.get_by_text("资源视图")
                    count = await element.count()
                    if count > 0:
                        self.log(f"找到 {count} 个元素", "SUCCESS")
                        await element.first.highlight()
                        await self.page.wait_for_timeout(500)
                        # 尝试点击
                        await element.first.click()
                        self.log("点击成功", "SUCCESS")
                        await self.page.wait_for_timeout(1000)
                    else:
                        self.log("未找到元素", "FAIL")
                except Exception as e:
                    self.log(f"失败: {e}", "ERROR")

            elif strategy_type == "get_by_text_lx":
                try:
                    element = self.iframe.get_by_text("轮巡分组")
                    count = await element.count()
                    if count > 0:
                        self.log(f"找到 {count} 个元素", "SUCCESS")
                        await element.first.highlight()
                        await self.page.wait_for_timeout(500)
                        await element.first.click()
                        self.log("点击成功", "SUCCESS")
                        await self.page.wait_for_timeout(1000)
                    else:
                        self.log("未找到元素", "FAIL")
                except Exception as e:
                    self.log(f"失败: {e}", "ERROR")

        await self.page.screenshot(path="screenshot_after_test_clicks.png")
        self.log("已保存截图: screenshot_after_test_clicks.png", "INFO")


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False, slow_mo=500)
        context = await browser.new_context(viewport={"width": 1920, "height": 1080}, ignore_https_errors=True)
        page = await context.new_page()

        analyzer = DeepTreeAnalyzer(page)

        try:
            await analyzer.auto_login_and_enter()
            await analyzer.get_iframe()
            await analyzer.deep_analyze_tree_structure()
            await analyzer.test_click_strategies()

            analyzer.log("\n分析完成！", "SUCCESS")
            print("\n浏览器保持打开30秒...")
            await page.wait_for_timeout(30000)

        except Exception as e:
            analyzer.log(f"执行出错: {e}", "ERROR")
            import traceback
            traceback.print_exc()
            await page.screenshot(path="screenshot_error.png")

        finally:
            await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
