"""
轻量级页面调试脚本 - 分析树形控件

使用方式：
1. 手动打开浏览器，登录并进入"实时预览"页面
2. 运行此脚本：python debug_tree.py
3. 脚本会连接到已打开的浏览器进行调试
"""

import asyncio
import json
from playwright.async_api import async_playwright
from datetime import datetime

# 调试端口（Chrome需要用这个端口启动）
DEBUG_PORT = 9222


class TreeAnalyzer:
    """树形控件分析器"""

    def __init__(self, page):
        self.page = page
        self.results = {}

    def print_section(self, title):
        """打印分节标题"""
        print("\n" + "=" * 70)
        print(f"  {title}")
        print("=" * 70)

    def print_result(self, status, message):
        """打印结果"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        icon = "✓" if status == "SUCCESS" else "✗" if status == "FAIL" else "ℹ"
        print(f"[{timestamp}] {icon} {message}")

    async def analyze_all(self):
        """执行所有分析"""
        self.print_section("开始分析树形控件结构")

        # 分析1: ARIA 角色
        await self.check_aria_roles()

        # 分析2: 常见树形类名
        await self.check_tree_classes()

        # 分析3: 查找"根节点"
        await self.find_root_nodes()

        # 分析4: 检查 Shadow DOM 和 iframe
        await self.check_special_contexts()

        # 分析5: 尝试构建引用映射（OpenClaw 方式）
        await self.build_ref_mapping()

        # 总结
        self.print_summary()

    async def check_aria_roles(self):
        """检查 ARIA 角色元素"""
        self.print_section("[1] 检查 ARIA 角色")

        roles_to_check = ["treeitem", "tree", "button", "link", "textbox"]

        for role in roles_to_check:
            try:
                elements = await self.page.query_selector_all(f'[role="{role}"]')
                if elements:
                    self.print_result("SUCCESS", f"找到 {len(elements):3d} 个 role='{role}' 元素")

                    # 显示前3个示例
                    if len(elements) <= 10:
                        for idx, el in enumerate(elements[:3]):
                            text = await el.text_content()
                            visible = await el.is_visible()
                            aria_expanded = await el.get_attribute("aria-expanded")
                            info = f"文本: {text[:30]}, 可见: {visible}"
                            if aria_expanded:
                                info += f", 展开: {aria_expanded}"
                            print(f"       [{idx}] {info}")
                else:
                    self.print_result("FAIL", f"未找到 role='{role}' 元素")
            except Exception as e:
                self.print_result("ERROR", f"检查 role='{role}' 时出错: {e}")

    async def check_tree_classes(self):
        """检查常见树形控件类名"""
        self.print_section("[2] 检查树形控件类名")

        tree_selectors = [
            ".tree-node",
            ".tree-item",
            ".tree-item-title",
            ".el-tree-node",
            ".el-tree-node__content",
            ".ant-tree-node",
            ".ant-tree-node-content-wrapper",
            ".ant-tree-title",
            ".vue-tree-node",
            ".node-content",
            "[class*='tree']",
            "[class*='Tree']",
        ]

        found_any = False
        for selector in tree_selectors:
            try:
                elements = await self.page.query_selector_all(selector)
                if elements:
                    found_any = True
                    self.print_result("SUCCESS", f"{selector}: {len(elements)} 个")

                    # 显示第一个元素的信息
                    if elements:
                        el = elements[0]
                        text = await el.text_content()
                        class_name = await el.get_attribute("class")
                        print(f"       示例: class='{class_name}', 文本='{text[:30]}'")
            except:
                pass

        if not found_any:
            self.print_result("FAIL", "未找到常见树形控件类名")

    async def find_root_nodes(self):
        """查找包含"根"的元素"""
        self.print_section("[3] 搜索包含'根'字的元素")

        root_elements = await self.page.evaluate("""
            () => {
                const results = [];
                const allElements = document.querySelectorAll('*');

                allElements.forEach(el => {
                    const text = el.textContent || '';
                    if (text.includes('根') && text.length < 100) {
                        const rect = el.getBoundingClientRect();
                        if (rect.width > 0 && rect.height > 0) {
                            results.push({
                                tagName: el.tagName,
                                text: text.trim().substring(0, 50),
                                id: el.id,
                                className: el.className,
                                role: el.getAttribute('role'),
                                ariaLabel: el.getAttribute('aria-label'),
                                title: el.getAttribute('title'),
                                dataAttrs: Array.from(el.attributes)
                                    .filter(a => a.name.startsWith('data-'))
                                    .map(a => `${a.name}="${a.value}"`)
                                    .join(' '),
                                rect: {x: Math.round(rect.x), y: Math.round(rect.y),
                                       width: Math.round(rect.width), height: Math.round(rect.height)},
                            });
                        }
                    }
                });

                return results.slice(0, 10);  // 最多返回10个
            }
        """)

        if root_elements:
            self.print_result("SUCCESS", f"找到 {len(root_elements)} 个包含'根'的可见元素")
            for idx, el in enumerate(root_elements):
                print(f"\n   [{idx}] {el['tagName']}")
                print(f"       文本: {el['text']}")
                print(f"       属性: role={el['role']}, id={el['id']}, title={el['title']}")
                print(f"       类名: {el['className'][:80] if el['className'] else '无'}")
                if el['dataAttrs']:
                    print(f"       data属性: {el['dataAttrs'][:100]}")
                print(f"       位置: x={el['rect']['x']}, y={el['rect']['y']}, "
                      f"size={el['rect']['width']}x{el['rect']['height']}")
        else:
            self.print_result("FAIL", "未找到包含'根'字的可见元素")

    async def check_special_contexts(self):
        """检查 Shadow DOM 和 iframe"""
        self.print_section("[4] 检查特殊上下文 (Shadow DOM / iframe)")

        # 检查 Shadow DOM
        shadow_count = await self.page.evaluate("""
            () => {
                let count = 0;
                const allElements = document.querySelectorAll('*');
                allElements.forEach(el => {
                    if (el.shadowRoot) count++;
                });
                return count;
            }
        """)
        if shadow_count > 0:
            self.print_result("SUCCESS", f"找到 {shadow_count} 个包含 Shadow DOM 的元素")
        else:
            self.print_result("INFO", "页面中没有 Shadow DOM")

        # 检查 iframe
        iframes = await self.page.query_selector_all("iframe")
        if iframes:
            self.print_result("SUCCESS", f"找到 {len(iframes)} 个 iframe")
            for idx, frame in enumerate(iframes):
                src = await frame.get_attribute("src")
                name = await frame.get_attribute("name")
                print(f"   [{idx}] name='{name}', src='{src[:60] if src else 'about:blank'}'")
        else:
            self.print_result("INFO", "页面中没有 iframe")

    async def build_ref_mapping(self):
        """构建引用映射（OpenClaw 方式）"""
        self.print_section("[5] 构建引用映射 (OpenClaw 风格)")

        # 捕获所有可交互元素
        interactive_elements = await self.page.evaluate("""
            () => {
                const refs = [];
                let refId = 1;

                // 定义可交互的角色
                const interactiveRoles = [
                    'button', 'link', 'textbox', 'checkbox', 'radio',
                    'combobox', 'listbox', 'menuitem', 'treeitem', 'tab'
                ];

                document.querySelectorAll('*').forEach(el => {
                    const role = el.getAttribute('role');
                    const tagName = el.tagName.toLowerCase();

                    // 判断是否可交互
                    let isInteractive = interactiveRoles.includes(role);

                    // 检查常见可交互标签
                    if (!isInteractive) {
                        if (['button', 'a', 'input', 'select', 'textarea'].includes(tagName)) {
                            isInteractive = true;
                        }
                    }

                    if (isInteractive) {
                        const text = el.textContent?.trim().substring(0, 50) || '';
                        const ariaLabel = el.getAttribute('aria-label') || '';
                        const title = el.getAttribute('title') || '';
                        const name = el.getAttribute('name') || '';

                        // 只添加有内容的元素
                        if (text || ariaLabel || title || name) {
                            refs.push({
                                ref: `e${refId++}`,
                                role: role || tagName,
                                name: ariaLabel || title || text || name,
                                tagName: tagName,
                                visible: el.offsetParent !== null,
                            });
                        }
                    }
                });

                return refs.slice(0, 20);  // 最多返回20个
            }
        """)

        if interactive_elements:
            self.print_result("SUCCESS", f"捕获了 {len(interactive_elements)} 个可交互元素")

            print("\n   引用映射表 (前20个):")
            print("   " + "-" * 70)
            for ref_el in interactive_elements:
                visible_mark = "✓" if ref_el['visible'] else "✗"
                print(f"   {visible_mark} {ref_el['ref']:>4} = role='{ref_el['role']}', "
                      f"name='{ref_el['name'][:30]}'")

            # 保存到文件
            with open("ref_mapping.json", "w", encoding="utf-8") as f:
                json.dump(interactive_elements, f, ensure_ascii=False, indent=2)
            print("\n   完整映射已保存到: ref_mapping.json")

            # 特别标注包含"根"或"预览"的元素
            print("\n   ★ 包含'根'或'预览'的元素:")
            for ref_el in interactive_elements:
                name = ref_el['name']
                if '根' in name or '预览' in name:
                    print(f"       {ref_el['ref']} → {name[:50]}")
        else:
            self.print_result("FAIL", "未捕获到可交互元素")

    async def test_click_strategies(self):
        """测试点击策略"""
        self.print_section("[6] 测试点击策略")

        # 找一个目标元素（包含"根"或第一个treeitem）
        target = await self.page.evaluate("""
            () => {
                // 策略1: 找包含"根"的元素
                const rootElements = Array.from(document.querySelectorAll('*'))
                    .filter(el => el.textContent && el.textContent.includes('根'))
                    .filter(el => el.offsetParent !== null);

                if (rootElements.length > 0) {
                    return {
                        found: true,
                        strategy: 'text_contains_root',
                        element: rootElements[0].outerHTML.substring(0, 200)
                    };
                }

                // 策略2: 找第一个treeitem
                const treeitem = document.querySelector('[role="treeitem"]');
                if (treeitem) {
                    return {
                        found: true,
                        strategy: 'first_treeitem',
                        element: treeitem.outerHTML.substring(0, 200)
                    };
                }

                return {found: false};
            }
        """)

        if target['found']:
            self.print_result("SUCCESS", f"找到目标元素 (策略: {target['strategy']})")
            print(f"\n   元素HTML:\n   {target['element']}")

            # 询问是否测试点击
            print("\n   是否尝试点击此元素？(在浏览器中手动操作以观察)")
        else:
            self.print_result("FAIL", "未找到可点击的目标元素")

    def print_summary(self):
        """打印分析总结"""
        self.print_section("分析完成")

        print("""
总结:

1. 请查看上面的分析结果，找出：
   - 树形控件使用的是哪种结构 (role="treeitem" / class="xxx" / 其他)
   - 元素是否在 Shadow DOM 或 iframe 中
   - 元素有哪些可用的属性 (role, aria-label, title, data-* 等)

2. 推荐的定位策略 (按优先级):
   - 策略A: page.get_by_role("treeitem", name="节点名")
   - 策略B: page.get_by_text("节点名")
   - 策略C: page.locator(".tree-node").filter(has_text="节点名")
   - 策略D: 使用 ref_mapping.json 中的引用 (e1, e2...)

3. 下一步:
   - 把 ref_mapping.json 和控制台输出发送给开发者
   - 开发者会根据结果给出最佳实现方案

文件输出:
   - ref_mapping.json: 引用映射表
   - 可以手动截图树形控件发给我
        """)


async def connect_and_analyze():
    """连接到已打开的浏览器并分析"""
    print("=" * 70)
    print("  轻量级树形控件调试工具")
    print("=" * 70)
    print("\n使用步骤:")
    print("1. 确保已打开 Chrome 浏览器")
    print("2. 手动登录并进入'实时预览'页面")
    print("3. 保持页面打开，按回车继续...")
    input()

    async with async_playwright() as p:
        try:
            # 尝试连接到现有的 Chrome
            print("\n正在连接到浏览器...")
            browser = await p.chromium.connect_over_cdp(f"http://localhost:{DEBUG_PORT}")
            print("✓ 已连接到浏览器")

            # 获取当前页面
            contexts = browser.contexts
            if contexts and contexts[0].pages:
                page = contexts[0].pages[0]
                print(f"✓ 当前页面: {await page.title()}")
            else:
                print("✗ 未找到活动页面")
                return

            # 创建分析器
            analyzer = TreeAnalyzer(page)

            # 执行分析
            await analyzer.analyze_all()

            # 测试点击
            await analyzer.test_click_strategies()

            # 截图
            screenshot_path = "debug_tree_screenshot.png"
            await page.screenshot(path=screenshot_path, full_page=True)
            print(f"\n✓ 已保存截图: {screenshot_path}")

            print("\n分析完成！浏览器保持连接状态...")

        except Exception as e:
            print(f"\n✗ 连接失败: {e}")
            print("\n请使用以下方式启动 Chrome:")
            print(f'   chrome.exe --remote-debugging-port={DEBUG_PORT}')
            print("\n或者运行下面的替代方案脚本")


async def standalone_analyze():
    """独立模式：启动新浏览器分析"""
    print("\n" + "=" * 70)
    print("  独立模式 - 需要手动登录")
    print("=" * 70)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False, slow_mo=500)
        context = await browser.new_context(viewport={"width": 1920, "height": 1080})
        page = await context.new_page()

        print("\n请在打开的浏览器中:")
        print("1. 访问: http://10.10.10.158")
        print("2. 输入账号密码登录")
        print("3. 点击'实时预览'")
        print("4. 完成后，回到这里按回车继续分析...")
        input()

        analyzer = TreeAnalyzer(page)
        await analyzer.analyze_all()
        await analyzer.test_click_strategies()

        await page.screenshot(path="debug_tree_screenshot.png")
        print("\n✓ 分析完成！截图已保存")

        print("\n浏览器将保持打开30秒...")
        await page.wait_for_timeout(30000)
        await browser.close()


if __name__ == "__main__":
    import sys

    print("""
╔═══════════════════════════════════════════════════════════════════╗
║                     树形控件调试工具                               ║
╚═══════════════════════════════════════════════════════════════════╝
""")

    # 检查命令行参数
    if len(sys.argv) > 1 and sys.argv[1] == "--standalone":
        asyncio.run(standalone_analyze())
    else:
        try:
            asyncio.run(connect_and_analyze())
        except:
            print("\n连接失败，启动独立模式...")
            asyncio.run(standalone_analyze())
