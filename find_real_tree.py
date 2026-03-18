"""
寻找真正的树形控件 - 带 ">" 展开按钮的那个

目标：找到类似这样的结构：
└─ 监控点
   └─ 根节点 [>]  ← 点击这个展开
      └─ 子节点
"""

import asyncio
import json
from playwright.async_api import async_playwright
from datetime import datetime

BASE_URL = "http://10.10.10.158"
USERNAME = "cdzhuanyong"
PASSWORD = "cdsz@429"


class RealTreeFinder:
    """真正的树形控件查找器"""

    def __init__(self, page):
        self.page = page
        self.iframe = None

    def log(self, message, level="INFO"):
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
        await self.page.click('button[type="submit"], button:has-text("登录")')
        await self.page.wait_for_load_state("networkidle", timeout=10000)
        await self.page.wait_for_timeout(2000)

        self.log("点击'实时预览'...", "INFO")
        await self.page.get_by_text("实时预览").first.click()
        await self.page.wait_for_timeout(5000)

        self.iframe = self.page.frame(name="vms_010100")
        if self.iframe:
            self.log("iframe获取成功", "SUCCESS")
        else:
            self.log("无法获取iframe", "ERROR")

    async def find_expand_buttons(self):
        """查找展开/折叠按钮"""
        if not self.iframe:
            return

        self.log("=" * 70)
        self.log("查找树形展开按钮（>, +, ▶ 等符号）", "INFO")
        self.log("=" * 70)

        # 1. 查找包含特殊字符的元素
        self.log("\n[1] 查找包含 '>', '▼', '▶', '+', '-' 的元素:", "INFO")

        expand_chars = ['>', '▼', '▶', '▲', '∨', '∧', '+', '-', '◢', '◣']
        found_buttons = []

        for char in expand_chars:
            elements = await self.iframe.evaluate(f"""
                (char) => {{
                    const results = [];
                    const allElements = document.querySelectorAll('*');

                    allElements.forEach(el => {{
                        const text = el.textContent || '';
                        // 只查找纯文本或单个字符的元素
                        if (text.trim() === char && text.length < 5) {{
                            const rect = el.getBoundingClientRect();
                            if (rect.width > 0 && rect.height > 0) {{
                                results.push({{
                                    tagName: el.tagName,
                                    text: text.trim(),
                                    className: el.className,
                                    id: el.id,
                                    role: el.getAttribute('role'),
                                    ariaExpanded: el.getAttribute('aria-expanded'),
                                    x: Math.round(rect.x),
                                    y: Math.round(rect.y),
                                    width: Math.round(rect.width),
                                    height: Math.round(rect.height),
                                }});
                            }}
                        }}
                    }});

                    return results;
                }}
            """, char)

            if elements:
                self.log(f"  找到 {len(elements)} 个包含 '{char}' 的元素", "SUCCESS")
                found_buttons.extend(elements)

                for idx, el in enumerate(elements[:3]):  # 只显示前3个
                    self.log(f"    [{idx}] <{el['tagName']}> class='{el['className'][:50]}', "
                           f"pos=({el['x']}, {el['y']}), size={el['width']}x{el['height']}", "INFO")

        # 2. 查找 aria-expanded 属性（标准树形控件属性）
        self.log("\n[2] 查找 aria-expanded 属性的元素:", "INFO")

        aria_elements = await self.iframe.evaluate("""
            () => {
                const results = [];
                const allElements = document.querySelectorAll('[aria-expanded]');

                allElements.forEach(el => {
                    const rect = el.getBoundingClientRect();
                    if (rect.width > 0 && rect.height > 0) {
                        results.push({
                            tagName: el.tagName,
                            text: (el.textContent || '').trim().substring(0, 30),
                            className: el.className,
                            id: el.id,
                            ariaExpanded: el.getAttribute('aria-expanded'),
                            role: el.getAttribute('role'),
                            x: Math.round(rect.x),
                            y: Math.round(rect.y),
                        });
                    }
                });

                return results.slice(0, 10);
            }
        """)

        if aria_elements:
            self.log(f"找到 {len(aria_elements)} 个 aria-expanded 元素", "SUCCESS")
            for el in aria_elements:
                self.log(f"  <{el['tagName']}> text='{el['text']}', "
                       f"aria-expanded={el['ariaExpanded']}, pos=({el['x']}, {el['y']})", "INFO")
        else:
            self.log("未找到 aria-expanded 元素", "WARN")

        # 3. 查找包含"监控点"或"根节点"的区域
        self.log("\n[3] 查找包含'监控点'的元素及其父级:", "INFO")

        monitor_elements = await self.iframe.evaluate("""
            () => {
                const results = [];
                const allElements = document.querySelectorAll('*');

                allElements.forEach(el => {
                    const text = el.textContent || '';
                    if (text.includes('监控点') && text.length < 200) {
                        // 找到这个元素和它的父级
                        let current = el;
                        let path = [];
                        for (let i = 0; i < 3 && current; i++) {
                            const rect = current.getBoundingClientRect();
                            path.push({
                                tagName: current.tagName,
                                className: current.className,
                                id: current.id,
                                text: (current.textContent || '').trim().substring(0, 30),
                                visible: rect.width > 0 && rect.height > 0,
                            });
                            current = current.parentElement;
                        }
                        results.push(path);
                    }
                });

                return results.slice(0, 2);
            }
        """)

        if monitor_elements:
            self.log(f"找到 {len(monitor_elements)} 个相关区域", "SUCCESS")
            for idx, path in enumerate(monitor_elements):
                self.log(f"\n  区域[{idx}]:", "INFO")
                for level, el in enumerate(path):
                    visible = "✓" if el['visible'] else "✗"
                    self.log(f"    [{visible}] L{level}: <{el['tagName']}> "
                           f"text='{el['text']}', class='{el['className'][:40]}'", "INFO")
        else:
            self.log("未找到'监控点'相关元素", "WARN")

        # 4. 查找特定class模式（可能的树形控件）
        self.log("\n[4] 查找可能的树形控件class:", "INFO")

        tree_classes = await self.iframe.evaluate("""
            () => {
                const patterns = [
                    'tree', 'node', 'branch', 'leaf', 'expand', 'collapse',
                    'toggle', 'switch', 'folder', 'file', 'arrow', 'caret'
                ];
                const results = {};

                patterns.forEach(pattern => {
                    const selector = `[class*="${pattern}"]`;
                    const elements = document.querySelectorAll(selector);

                    // 只统计可见元素
                    const visibleElements = Array.from(elements).filter(el => {
                        const rect = el.getBoundingClientRect();
                        return rect.width > 0 && rect.height > 0;
                    });

                    if (visibleElements.length > 0 && visibleElements.length < 50) {
                        results[pattern] = {
                            count: visibleElements.length,
                            samples: Array.from(visibleElements).slice(0, 3).map(el => ({
                                tag: el.tagName,
                                class: el.className,
                                text: (el.textContent || '').trim().substring(0, 30),
                                hasChildren: el.children.length > 0,
                            }))
                        };
                    }
                });

                return results;
            }
        """)

        if tree_classes:
            self.log(f"找到 {len(tree_classes)} 种可能的树形class", "SUCCESS")
            for pattern, info in tree_classes.items():
                self.log(f"\n  模式 '{pattern}': {info['count']}个元素", "INFO")
                for sample in info['samples'][:2]:
                    self.log(f"    <{sample['tag']}> class='{sample['class'][:60]}', "
                           f"text='{sample['text']}'", "INFO")
        else:
            self.log("未找到明显的树形控件class", "WARN")

        # 5. 导出关键区域HTML
        self.log("\n[5] 导出'监控点'区域的HTML:", "INFO")

        html_fragment = await self.iframe.evaluate("""
            () => {
                // 找到包含"监控点"的元素
                const allElements = document.querySelectorAll('*');
                for (const el of allElements) {
                    const text = el.textContent || '';
                    if (text.includes('监控点') && text.length < 200) {
                        // 获取其祖父元素（包含整个树形结构）
                        let grandParent = el.parentElement?.parentElement;
                        if (grandParent) {
                            return grandParent.outerHTML.substring(0, 2000);
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

        # 保存到文件
        with open("monitor_point_html.html", "w", encoding="utf-8") as f:
            f.write(html_fragment)
        self.log("\nHTML已保存到: monitor_point_html.html", "INFO")

    async def test_click_expand_button(self):
        """测试点击展开按钮"""
        if not self.iframe:
            return

        self.log("\n" + "=" * 70)
        self.log("测试点击展开按钮", "INFO")
        self.log("=" * 70)

        # 尝试多种方式点击">"符号
        strategies = [
            ("包含'>'的元素", "text_arrow"),
            ("aria-expanded=false的元素", "aria_not_expanded"),
            ("class包含'expand'的元素", "class_expand"),
            ("class包含'tree'的元素", "class_tree"),
        ]

        for strategy_name, strategy_type in strategies:
            self.log(f"\n测试: {strategy_name}", "INFO")

            try:
                if strategy_type == "text_arrow":
                    # 找包含">"的元素
                    elements = await self.iframe.locator("text='>'").all()
                    if elements:
                        self.log(f"  找到 {len(elements)} 个元素", "SUCCESS")
                        for el in elements[:3]:
                            try:
                                await el.click()
                                self.log("  ✓ 点击成功", "SUCCESS")
                                await self.page.wait_for_timeout(1000)
                                break
                            except:
                                pass

                elif strategy_type == "aria_not_expanded":
                    # 找未展开的元素
                    elements = await self.iframe.locator('[aria-expanded="false"]').all()
                    if elements:
                        self.log(f"  找到 {len(elements)} 个元素", "SUCCESS")
                        for el in elements[:2]:
                            try:
                                await el.click()
                                self.log("  ✓ 点击成功", "SUCCESS")
                                await self.page.wait_for_timeout(1000)
                                break
                            except:
                                pass

                elif strategy_type == "class_expand":
                    # 找包含expand的class
                    elements = await self.iframe.locator('[class*="expand"]').all()
                    if elements:
                        self.log(f"  找到 {len(elements)} 个元素", "SUCCESS")
                        for el in elements[:2]:
                            try:
                                await el.click()
                                self.log("  ✓ 点击成功", "SUCCESS")
                                await self.page.wait_for_timeout(1000)
                                break
                            except:
                                pass

                elif strategy_type == "class_tree":
                    # 找包含tree的class
                    elements = await self.iframe.locator('[class*="tree"]').all()
                    if elements:
                        self.log(f"  找到 {len(elements)} 个元素", "SUCCESS")
                        for el in elements[:3]:
                            try:
                                await el.click()
                                self.log("  ✓ 点击成功", "SUCCESS")
                                await self.page.wait_for_timeout(1000)
                                break
                            except:
                                pass

            except Exception as e:
                self.log(f"  ✗ 失败: {e}", "ERROR")

        await self.page.screenshot(path="after_expand_test.png")
        self.log("\n已保存截图: after_expand_test.png", "INFO")


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False, slow_mo=500)
        context = await browser.new_context(viewport={"width": 1920, "height": 1080}, ignore_https_errors=True)
        page = await context.new_page()

        finder = RealTreeFinder(page)

        try:
            await finder.auto_login_and_enter()
            await finder.find_expand_buttons()
            await finder.test_click_expand_button()

            finder.log("\n分析完成！", "SUCCESS")
            print("\n浏览器保持打开30秒...")
            await page.wait_for_timeout(30000)

        except Exception as e:
            finder.log(f"执行出错: {e}", "ERROR")
            import traceback
            traceback.print_exc()
            await page.screenshot(path="error.png")

        finally:
            await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
