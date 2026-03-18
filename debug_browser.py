"""
内网页面调试脚本 - 分析树形控件定位问题

运行方式：
    python debug_browser.py

输出：
    console日志 + debug_screenshot.png
"""

import asyncio
import json
from playwright.async_api import async_playwright
from datetime import datetime

# 配置
BASE_URL = "http://10.10.10.158"
USERNAME = "cdzhuanyong"
PASSWORD = "cdsz@429"


class PageDebugger:
    """页面调试器"""

    def __init__(self, page):
        self.page = page
        self.logs = []

    def log(self, message, level="INFO"):
        """记录日志"""
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        log_entry = f"[{timestamp}] [{level}] {message}"
        print(log_entry)
        self.logs.append(log_entry)

    async def screenshot(self, filename="debug_screenshot.png"):
        """截图"""
        await self.page.screenshot(path=filename, full_page=True)
        self.log("INFO", f"截图保存: {filename}")

    async def analyze_tree_structure(self):
        """分析树形控件结构 - 核心调试方法"""
        self.log("=" * 60)
        self.log("开始分析树形控件结构")
        self.log("=" * 60)

        # 1. 检查是否有 treeitem 角色元素
        self.log("\n[1] 检查 ARIA treeitem 元素:")
        treeitems = await self.page.evaluate("""
            () => {
                const items = [];
                document.querySelectorAll('[role="treeitem"]').forEach((el, idx) => {
                    items.push({
                        index: idx,
                        text: el.textContent?.trim().substring(0, 50),
                        ariaExpanded: el.getAttribute('aria-expanded'),
                        ariaSelected: el.getAttribute('aria-selected'),
                        ariaLevel: el.getAttribute('aria-level'),
                        visible: el.offsetParent !== null,
                        display: window.getComputedStyle(el).display,
                        class: el.className,
                    });
                });
                return items;
            }
        """)

        if treeitems:
            self.log(f"INFO", f"找到 {len(treeitems)} 个 treeitem 元素")
            for item in treeitems[:5]:  # 只显示前5个
                self.log("DEBUG", json.dumps(item, ensure_ascii=False, indent=2))
        else:
            self.log("WARN", "未找到 [role='treeitem'] 元素")

        # 2. 检查树形相关的类名
        self.log("\n[2] 检查常见树形控件类名:")
        tree_classes = await self.page.evaluate("""
            () => {
                const selectors = [
                    '.tree-node', '.tree-item', '.tree-item-title',
                    '.el-tree-node', '.ant-tree-node',
                    '.vue-tree-node', '.node-content',
                    '[class*="tree"]', '[class*="Tree"]'
                ];

                const results = {};
                selectors.forEach(sel => {
                    const elements = document.querySelectorAll(sel);
                    if (elements.length > 0) {
                        results[sel] = {
                            count: elements.length,
                            samples: Array.from(elements).slice(0, 3).map(el => ({
                                text: el.textContent?.trim().substring(0, 30),
                                visible: el.offsetParent !== null,
                            }))
                        };
                    }
                });
                return results;
            }
        """)

        if tree_classes:
            self.log("INFO", f"找到 {len(tree_classes)} 类树形元素")
            for selector, info in tree_classes.items():
                self.log("DEBUG", f"{selector}: {info['count']}个")
                for sample in info['samples']:
                    self.log("DEBUG", f"  - {sample}")
        else:
            self.log("WARN", "未找到常见树形控件类名")

        # 3. 检查所有可点击的元素（找"根节点"）
        self.log("\n[3] 搜索包含'根'字的元素:")
        root_elements = await self.page.evaluate("""
            () => {
                const results = [];
                const walker = document.createTreeWalker(
                    document.body,
                    NodeFilter.SHOW_ELEMENT,
                    {
                        acceptNode: (node) => {
                            const text = node.textContent || '';
                            return text.includes('根') ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_REJECT;
                        }
                    }
                );

                let node;
                let count = 0;
                while ((node = walker.nextNode()) && count < 10) {
                    const rect = node.getBoundingClientRect();
                    results.push({
                        tagName: node.tagName,
                        text: node.textContent?.trim().substring(0, 50),
                        id: node.id,
                        className: node.className,
                        role: node.getAttribute('role'),
                        ariaLabel: node.getAttribute('aria-label'),
                        title: node.getAttribute('title'),
                        visible: rect.width > 0 && rect.height > 0,
                        rect: {x: rect.x, y: rect.y, width: rect.width, height: rect.height},
                    });
                    count++;
                }
                return results;
            }
        """)

        if root_elements:
            self.log("INFO", f"找到 {len(root_elements)} 个包含'根'的元素")
            for el in root_elements:
                self.log("DEBUG", json.dumps(el, ensure_ascii=False, indent=2))
        else:
            self.log("WARN", "未找到包含'根'字的元素")

        # 4. 检查 Shadow DOM
        self.log("\n[4] 检查 Shadow DOM:")
        shadow_count = await self.page.evaluate("""
            () => {
                let count = 0;
                const walker = document.createTreeWalker(
                    document.body,
                    NodeFilter.SHOW_ELEMENT
                );

                let node;
                while ((node = walker.nextNode())) {
                    if (node.shadowRoot) {
                        count++;
                        // 可以深入检查 shadowRoot 内部
                    }
                }
                return count;
            }
        """)
        self.log("INFO", f"页面中有 {shadow_count} 个元素包含 Shadow DOM")

        # 5. 检查 iframe
        self.log("\n[5] 检查 iframe:")
        iframes = await self.page.evaluate("""
            () => {
                const frames = Array.from(document.querySelectorAll('iframe'));
                return frames.map(f => ({
                    id: f.id,
                    name: f.name,
                    src: f.src,
                    width: f.width,
                    height: f.height,
                }));
            }
        """)
        if iframes:
            self.log("INFO", f"找到 {len(iframes)} 个 iframe")
            for idx, frame in enumerate(iframes):
                self.log("DEBUG", f"iframe[{idx}]: {frame}")
        else:
            self.log("INFO", "页面中没有 iframe")

        # 6. 尝试获取所有可交互元素的 aria-ref（Playwright 特性）
        self.log("\n[6] 检查 Playwright aria-ref 属性:")
        aria_refs = await self.page.evaluate("""
            () => {
                const results = [];
                document.querySelectorAll('[aria-ref]').forEach((el, idx) => {
                    results.push({
                        index: idx,
                        ariaRef: el.getAttribute('aria-ref'),
                        text: el.textContent?.trim().substring(0, 30),
                    });
                });
                return results.slice(0, 10);
            }
        """)
        if aria_refs:
            self.log("INFO", f"找到 {len(aria_refs)} 个 aria-ref 元素")
            for ref in aria_refs:
                self.log("DEBUG", json.dumps(ref, ensure_ascii=False))
        else:
            self.log("INFO", "页面中没有 aria-ref 属性（需要用其他方式）")

        self.log("\n" + "=" * 60)
        self.log("树形结构分析完成")
        self.log("=" * 60)

    async def test_strategies(self):
        """测试多种定位策略"""
        self.log("\n" + "=" * 60)
        self.log("开始测试定位策略")
        self.log("=" * 60)

        strategies = [
            ("策略1: getByRole(treeitem)", "role"),
            ("策略2: getByText('实时预览')", "text"),
            ("策略3: getByText('根节点')", "text_root"),
            ("策略4: locator('[title*=\\'预览\\']')", "title_attr"),
            ("策略5: locator('[class*=\\'tree\\']')", "tree_class"),
        ]

        results = {}

        for strategy_name, strategy_type in strategies:
            self.log(f"\n测试 {strategy_name}:")

            try:
                if strategy_type == "role":
                    # 尝试找到所有 treeitem
                    elements = await self.page.query_selector_all('[role="treeitem"]')
                    if elements:
                        self.log("SUCCESS", f"找到 {len(elements)} 个 treeitem")
                        for i, el in enumerate(elements[:3]):
                            text = await el.text_content()
                            self.log("DEBUG", f"  [{i}] {text[:50]}")
                        results[strategy_name] = {"status": "found", "count": len(elements)}
                    else:
                        self.log("FAIL", "未找到 treeitem 元素")
                        results[strategy_name] = {"status": "not_found"}

                elif strategy_type == "text":
                    element = self.page.get_by_text("实时预览")
                    count = await element.count()
                    if count > 0:
                        self.log("SUCCESS", f"找到 {count} 个'实时预览'")
                        text = await element.first.text_content()
                        self.log("DEBUG", f"  内容: {text[:100]}")
                        results[strategy_name] = {"status": "found", "count": count}
                    else:
                        self.log("FAIL", "未找到'实时预览'文本")
                        results[strategy_name] = {"status": "not_found"}

                elif strategy_type == "text_root":
                    element = self.page.get_by_text("根节点", exact=True)
                    count = await element.count()
                    if count > 0:
                        self.log("SUCCESS", f"找到 {count} 个'根节点'")
                        results[strategy_name] = {"status": "found", "count": count}
                    else:
                        self.log("FAIL", "未找到'根节点'文本")
                        results[strategy_name] = {"status": "not_found"}

                elif strategy_type == "title_attr":
                    element = self.page.locator('[title*="预览"]')
                    count = await element.count()
                    if count > 0:
                        self.log("SUCCESS", f"找到 {count} 个title包含'预览'的元素")
                        results[strategy_name] = {"status": "found", "count": count}
                    else:
                        self.log("FAIL", "未找到title属性")
                        results[strategy_name] = {"status": "not_found"}

                elif strategy_type == "tree_class":
                    elements = await self.page.query_selector_all('[class*="tree"], [class*="Tree"]')
                    if elements:
                        self.log("SUCCESS", f"找到 {len(elements)} 个包含'tree'的class")
                        results[strategy_name] = {"status": "found", "count": len(elements)}
                    else:
                        self.log("FAIL", "未找到包含'tree'的class")
                        results[strategy_name] = {"status": "not_found"}

            except Exception as e:
                self.log("ERROR", f"策略执行失败: {str(e)}")
                results[strategy_name] = {"status": "error", "message": str(e)}

        self.log("\n" + "=" * 60)
        self.log("策略测试总结:")
        for strategy, result in results.items():
            status = result.get("status", "unknown")
            self.log("INFO", f"  {strategy}: {status}")
        self.log("=" * 60)

        return results


async def main():
    """主流程"""
    async with async_playwright() as p:
        # 启动浏览器（使用有头模式方便观察）
        browser = await p.chromium.launch(
            headless=False,  # 有头模式，你可以看到操作过程
            slow_mo=500,     # 每步操作间隔500ms，方便观察
        )

        context = await browser.new_context(
            viewport={"width": 1920, "height": 1080},
            ignore_https_errors=True,
        )

        page = await context.new_page()
        debugger = PageDebugger(page)

        try:
            # ========== 步骤1: 访问登录页 ==========
            debugger.log("=" * 60)
            debugger.log("步骤1: 访问登录页")
            debugger.log("=" * 60)

            await page.goto(BASE_URL, timeout=30000)
            await page.wait_for_load_state("networkidle")
            debugger.log("INFO", f"已访问: {BASE_URL}")
            await debugger.screenshot("screenshot_01_login.png")

            # ========== 步骤2: 登录 ==========
            debugger.log("\n" + "=" * 60)
            debugger.log("步骤2: 登录")
            debugger.log("=" * 60)

            # 等待登录表单
            await page.wait_for_selector('input[type="text"], input[type="username"], input[name*="user"], input[id*="user"]', timeout=5000)

            # 输入用户名
            try:
                await page.fill('input[type="text"], input[type="username"]', USERNAME)
                debugger.log("INFO", f"已输入用户名: {USERNAME}")
            except:
                # 尝试其他选择器
                await page.fill('input[placeholder*="用户"], input[placeholder*="账号"]', USERNAME)
                debugger.log("INFO", f"已输入用户名（备用选择器）: {USERNAME}")

            await page.wait_for_timeout(500)

            # 输入密码
            try:
                await page.fill('input[type="password"]', PASSWORD)
                debugger.log("INFO", "已输入密码: ********")
            except:
                debugger.log("WARN", "未找到密码输入框")

            await page.wait_for_timeout(500)

            # 截图
            await debugger.screenshot("screenshot_02_filled.png")

            # 点击登录按钮
            try:
                await page.click('button[type="submit"], button:has-text("登录"), button:has-text("登 录")')
                debugger.log("INFO", "已点击登录按钮")
            except:
                debugger.log("WARN", "未找到登录按钮，尝试回车")
                await page.keyboard.press("Enter")

            # 等待登录完成
            await page.wait_for_load_state("networkidle", timeout=10000)
            await page.wait_for_timeout(2000)
            await debugger.screenshot("screenshot_03_logged_in.png")
            debugger.log("INFO", "登录完成")

            # ========== 步骤3: 寻找"实时预览" ==========
            debugger.log("\n" + "=" * 60)
            debugger.log("步骤3: 寻找'实时预览'按钮/链接")
            debugger.log("=" * 60)

            # 测试多种策略找"实时预览"
            preview_found = False

            # 策略1: 文本匹配
            try:
                preview_element = page.get_by_text("实时预览")
                count = await preview_element.count()
                if count > 0:
                    debugger.log("SUCCESS", f"通过文本找到 {count} 个'实时预览'")
                    await preview_element.first.highlight()
                    await page.wait_for_timeout(1000)
                    preview_found = True
            except Exception as e:
                debugger.log("WARN", f"文本查找失败: {e}")

            # 策略2: 查找侧边栏/菜单
            if not preview_found:
                try:
                    menu_items = await page.query_selector_all('.menu-item, .nav-item, [role="menuitem"]')
                    debugger.log("INFO", f"找到 {len(menu_items)} 个菜单项")
                    for idx, item in enumerate(menu_items):
                        text = await item.text_content()
                        if "实时预览" in text or "预览" in text:
                            debugger.log("DEBUG", f"菜单项[{idx}]: {text[:50]}")
                except Exception as e:
                    debugger.log("WARN", f"菜单查找失败: {e}")

            await debugger.screenshot("screenshot_04_preview_search.png")

            # ========== 步骤4: 点击"实时预览" ==========
            debugger.log("\n" + "=" * 60)
            debugger.log("步骤4: 点击'实时预览'")
            debugger.log("=" * 60)

            try:
                await page.get_by_text("实时预览").first.click()
                debugger.log("INFO", "已点击'实时预览'")
                await page.wait_for_timeout(2000)
                await debugger.screenshot("screenshot_05_after_preview.png")
            except Exception as e:
                debugger.log("ERROR", f"点击失败: {e}")

            # ========== 步骤5: 分析树形控件 ==========
            debugger.log("\n" + "=" * 60)
            debugger.log("步骤5: 分析树形控件结构")
            debugger.log("=" * 60)

            await page.wait_for_timeout(1000)
            await debugger.analyze_tree_structure()
            await debugger.screenshot("screenshot_06_tree_structure.png")

            # ========== 步骤6: 测试定位策略 ==========
            debugger.log("\n" + "=" * 60)
            debugger.log("步骤6: 测试多种定位策略")
            debugger.log("=" * 60)

            test_results = await debugger.test_strategies()

            # ========== 步骤7: 输出HTML结构 ==========
            debugger.log("\n" + "=" * 60)
            debugger.log("步骤7: 导出页面HTML结构（前5000字符）")
            debugger.log("=" * 60)

            html_content = await page.evaluate("""
                () => {
                    return document.body.innerHTML.substring(0, 5000);
                }
            """)
            print("\n" + "=" * 60)
            print("HTML结构预览:")
            print("=" * 60)
            print(html_content)
            print("=" * 60)

            # 保存完整HTML
            full_html = await page.evaluate("() => document.body.outerHTML")
            with open("page_structure.html", "w", encoding="utf-8") as f:
                f.write(full_html)
            debugger.log("INFO", "完整HTML已保存到: page_structure.html")

            # ========== 完成 ==========
            debugger.log("\n" + "=" * 60)
            debugger.log("调试完成！")
            debugger.log("=" * 60)
            debugger.log("INFO", "请查看以下文件:")
            debugger.log("INFO", "  - screenshot_*.png (截图)")
            debugger.log("INFO", "  - page_structure.html (完整HTML)")
            debugger.log("INFO", "\n请把这些内容发送给开发者分析")

            # 保持浏览器打开，方便手动检查
            debugger.log("\n浏览器将保持打开30秒，你可以手动检查...")
            await page.wait_for_timeout(30000)

        except Exception as e:
            debugger.log("ERROR", f"执行出错: {str(e)}")
            import traceback
            traceback.print_exc()
            await debugger.screenshot("screenshot_error.png")

        finally:
            await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
