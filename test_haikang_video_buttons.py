"""
海康视频平台综合调试测试脚本

目标：测试多种方案发现和操作视频站点按钮

测试策略：
1. iframe 内容深度扫描
2. 多种树形控件选择器
3. 不同的展开策略
4. 元素可见性分析
"""

import asyncio
import json
from datetime import datetime
from playwright.async_api import async_playwright

BASE_URL = "http://10.10.10.158"
USERNAME = "cdzhuanyong"
PASSWORD = "cdsz@429"


class HaikangVideoTester:
    """海康视频平台综合测试器"""

    def __init__(self, page):
        self.page = page
        self.iframe = None
        self.results = {
            "timestamp": datetime.now().isoformat(),
            "tests": []
        }

    def log(self, message, level="INFO"):
        """日志输出"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        icon = {"INFO": "ℹ️", "SUCCESS": "✅", "WARN": "⚠️", "ERROR": "❌"}[level]
        print(f"[{timestamp}] {icon} {message}")

    def record_result(self, test_name, success, data):
        """记录测试结果"""
        self.results["tests"].append({
            "name": test_name,
            "success": success,
            "data": data,
            "time": datetime.now().isoformat()
        })

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

        # 等待页面完全加载
        await self.page.wait_for_timeout(3000)

        # 先截图查看页面状态
        await self.page.screenshot(path="before_click_realtime_preview.png")
        self.log("已保存登录后截图", "INFO")

        # 尝试多种方式点击"实时预览"
        click_success = False

        # 方法1: 使用 JavaScript 强制点击（绕过可见性检查）
        try:
            self.log("尝试方法1: JavaScript 点击...", "INFO")
            js_result = await self.page.evaluate("""
                () => {
                    // 查找所有包含"实时预览"的元素
                    const allElements = document.querySelectorAll('*');
                    for (const el of allElements) {
                        const text = el.textContent || '';
                        if (text.includes('实时预览') && text.length < 50) {
                            // 尝试点击
                            el.click();
                            return {success: true, method: 'javascript_click', text: text};
                        }
                    }
                    return {success: false, method: 'not_found'};
                }
            """)

            if js_result['success']:
                self.log(f"JavaScript 点击成功: {js_result['text']}", "SUCCESS")
                click_success = True
            else:
                self.log("JavaScript 点击失败：未找到元素", "WARN")
        except Exception as e:
            self.log(f"JavaScript 点击异常: {e}", "ERROR")

        # 方法2: 如果 JavaScript 失败，尝试等待元素可见后点击
        if not click_success:
            try:
                self.log("尝试方法2: 等待元素可见后点击...", "INFO")
                await self.page.wait_for_timeout(2000)
                await self.page.get_by_text("实时预览").first.click(timeout=10000)
                self.log("等待后点击成功", "SUCCESS")
                click_success = True
            except Exception as e:
                self.log(f"等待后点击失败: {e}", "WARN")

        # 方法3: 尝试通过坐标点击
        if not click_success:
            try:
                self.log("尝试方法3: 通过坐标点击...", "INFO")
                coord_result = await self.page.evaluate("""
                    () => {
                        const allElements = document.querySelectorAll('*');
                        for (const el of allElements) {
                            const text = el.textContent || '';
                            if (text.includes('实时预览') && text.length < 50) {
                                const rect = el.getBoundingClientRect();
                                if (rect.width > 0 && rect.height > 0) {
                                    return {
                                        x: rect.x + rect.width / 2,
                                        y: rect.y + rect.height / 2,
                                        found: true
                                    };
                                }
                            }
                        }
                        return {found: false};
                    }
                """)

                if coord_result['found']:
                    await self.page.mouse.click(coord_result['x'], coord_result['y'])
                    self.log(f"坐标点击成功: ({coord_result['x']}, {coord_result['y']})", "SUCCESS")
                    click_success = True
                else:
                    self.log("坐标点击失败：未找到元素位置", "WARN")
            except Exception as e:
                self.log(f"坐标点击异常: {e}", "WARN")

        if not click_success:
            self.log("所有点击方法都失败了，请手动点击'实时预览'", "ERROR")
            await self.page.screenshot(path="click_failed.png")
            self.log("已保存失败截图，请手动操作然后按回车继续...", "WARN")
            input("按回车键继续...")
        else:
            await self.page.wait_for_timeout(5000)

        # 获取 iframe
        self.log("查找 iframe...", "INFO")
        frames = self.page.frames
        self.log(f"页面共有 {len(frames)} 个 frame", "INFO")

        for idx, frame in enumerate(frames):
            frame_name = frame.name
            frame_url = frame.url
            self.log(f"  Frame[{idx}]: name='{frame_name}', url='{frame_url[:50]}...'", "INFO")

        # 尝试获取目标 iframe
        self.iframe = self.page.frame(name="vms_010100")
        if self.iframe:
            self.log("iframe 获取成功: vms_010100", "SUCCESS")
        else:
            self.log("未找到 vms_010100 iframe，尝试其他方式", "WARN")
            # 尝试按 URL 匹配
            for frame in frames:
                if "vms" in frame.url.lower() or "preview" in frame.url.lower():
                    self.iframe = frame
                    self.log(f"通过 URL 匹配到 iframe: {frame.name}", "SUCCESS")
                    break

        if not self.iframe:
            self.log("无法获取任何 iframe，将测试主页面", "WARN")
            self.iframe = self.page

    async def test_01_iframe_content_analysis(self):
        """测试1: iframe 内容深度分析"""
        self.log("\n" + "="*70, "INFO")
        self.log("测试1: iframe 内容深度分析", "INFO")
        self.log("="*70, "INFO")

        try:
            # 获取页面基本信息
            page_info = await self.iframe.evaluate("""
                () => {
                    return {
                        title: document.title,
                        url: window.location.href,
                        body_classes: document.body.className,
                        all_elements_count: document.querySelectorAll('*').length,
                        visible_elements_count: Array.from(document.querySelectorAll('*')).filter(el => {
                            const rect = el.getBoundingClientRect();
                            return rect.width > 0 && rect.height > 0;
                        }).length
                    };
                }
            """)

            self.log(f"页面标题: {page_info['title']}", "INFO")
            self.log(f"页面URL: {page_info['url']}", "INFO")
            self.log(f"总元素数: {page_info['all_elements_count']}", "INFO")
            self.log(f"可见元素数: {page_info['visible_elements_count']}", "INFO")

            self.record_result("iframe_content_analysis", True, page_info)
            return True

        except Exception as e:
            self.log(f"测试失败: {e}", "ERROR")
            self.record_result("iframe_content_analysis", False, {"error": str(e)})
            return False

    async def test_02_tree_selectors(self):
        """测试2: 多种树形控件选择器"""
        self.log("\n" + "="*70, "INFO")
        self.log("测试2: 测试多种树形控件选择器", "INFO")
        self.log("="*70, "INFO")

        # 定义多种树形控件选择器
        tree_selectors = [
            # Element UI 树形组件
            ".el-tree-node",
            ".el-tree-node__content",
            ".el-tree-node__expand-icon",
            # 通用树形组件
            "[class*='tree']",
            "[class*='Tree']",
            "[class*='node']",
            "[class*='Node']",
            # ARIA 属性
            "[role='tree']",
            "[role='treeitem']",
            "[aria-expanded]",
            "[role='group']",
            # 可能的监控点相关
            "[class*='monitor']",
            "[class*='camera']",
            "[class*='video']",
            "[class*='resource']",
        ]

        results = {}

        for selector in tree_selectors:
            try:
                elements = await self.iframe.query_selector_all(selector)
                visible_count = 0

                for el in elements:
                    is_visible = await el.evaluate("el => { const rect = el.getBoundingClientRect(); return rect.width > 0 && rect.height > 0; }")
                    if is_visible:
                        visible_count += 1

                results[selector] = {
                    "total": len(elements),
                    "visible": visible_count
                }

                if visible_count > 0:
                    self.log(f"  ✅ '{selector}': {visible_count} 个可见元素", "SUCCESS")
                else:
                    self.log(f"  ⚪ '{selector}': {len(elements)} 个元素（0个可见）", "INFO")

            except Exception as e:
                results[selector] = {"error": str(e)}
                self.log(f"  ❌ '{selector}': {e}", "ERROR")

        # 找出最有效的选择器
        best_selector = max(
            [(k, v) for k, v in results.items() if "visible" in v and v["visible"] > 0],
            key=lambda x: x[1]["visible"],
            default=None
        )

        if best_selector:
            self.log(f"\n最佳选择器: '{best_selector[0]}' ({best_selector[1]['visible']} 个可见元素)", "SUCCESS")

        self.record_result("tree_selectors", True, results)
        return results

    async def test_03_expand_button_detection(self):
        """测试3: 展开/折叠按钮检测"""
        self.log("\n" + "="*70, "INFO")
        self.log("测试3: 展开/折叠按钮检测", "INFO")
        self.log("="*70, "INFO")

        # 查找各种可能的展开按钮
        expand_patterns = await self.iframe.evaluate("""
            () => {
                const results = {
                    by_text: [],
                    by_aria: [],
                    by_class: [],
                    by_symbol: [],
                    small_elements: []
                };

                const allElements = document.querySelectorAll('*');

                allElements.forEach(el => {
                    const rect = el.getBoundingClientRect();
                    if (rect.width <= 0 || rect.height <= 0) return;

                    const text = (el.textContent || '').trim();
                    const className = el.className || '';
                    const ariaExpanded = el.getAttribute('aria-expanded');
                    const role = el.getAttribute('role');

                    // 1. 包含展开符号的文本
                    if (['>', '▼', '▶', '▲', '+', '-', '∨', '∧', '◢', '◣', '◥', '◤'].includes(text) && text.length < 3) {
                        results.by_symbol.push({
                            tag: el.tagName,
                            text: text,
                            className: className,
                            x: Math.round(rect.x),
                            y: Math.round(rect.y),
                            width: Math.round(rect.width),
                            height: Math.round(rect.height)
                        });
                    }

                    // 2. aria-expanded 属性
                    if (ariaExpanded !== null) {
                        results.by_aria.push({
                            tag: el.tagName,
                            ariaExpanded: ariaExpanded,
                            role: role,
                            text: text.substring(0, 30),
                            className: className,
                            x: Math.round(rect.x),
                            y: Math.round(rect.y)
                        });
                    }

                    // 3. 包含 expand/collapse 关键词的 class
                    if (/expand|collapse|toggle|switch|arrow|caret|chevron/i.test(className)) {
                        results.by_class.push({
                            tag: el.tagName,
                            className: className,
                            text: text.substring(0, 30),
                            x: Math.round(rect.x),
                            y: Math.round(rect.y)
                        });
                    }

                    // 4. 小尺寸元素（可能是图标按钮）
                    if (rect.width < 30 && rect.height < 30 && rect.width > 5 && rect.height > 5) {
                        // 检查是否在左侧区域（可能是树形控件）
                        if (rect.x < 300) {
                            results.small_elements.push({
                                tag: el.tagName,
                                className: className,
                                text: text,
                                x: Math.round(rect.x),
                                y: Math.round(rect.y),
                                width: Math.round(rect.width),
                                height: Math.round(rect.height)
                            });
                        }
                    }
                });

                return results;
            }
        """)

        self.log(f"找到 {len(expand_patterns['by_symbol'])} 个符号按钮", "INFO")
        for btn in expand_patterns['by_symbol'][:5]:
            self.log(f"  符号 [{btn['text']}]: <{btn['tag']}> at ({btn['x']}, {btn['y']})", "INFO")

        self.log(f"\n找到 {len(expand_patterns['by_aria'])} 个 aria-expanded 元素", "INFO")
        for btn in expand_patterns['by_aria'][:5]:
            self.log(f"  aria-expanded={btn['ariaExpanded']}: {btn['text'][:30]}", "INFO")

        self.log(f"\n找到 {len(expand_patterns['by_class'])} 个包含 expand/collapse 的元素", "INFO")
        for btn in expand_patterns['by_class'][:5]:
            self.log(f"  class={btn['className'][:50]}: {btn['text'][:30]}", "INFO")

        self.log(f"\n找到 {len(expand_patterns['small_elements'])} 个左侧小图标", "INFO")
        for btn in expand_patterns['small_elements'][:10]:
            self.log(f"  <{btn['tag']}> {btn['className'][:30]} at ({btn['x']}, {btn['y']}) size={btn['width']}x{btn['height']}", "INFO")

        self.record_result("expand_button_detection", True, expand_patterns)
        return expand_patterns

    async def test_04_text_based_search(self):
        """测试4: 基于文本的元素搜索"""
        self.log("\n" + "="*70, "INFO")
        self.log("测试4: 基于文本的元素搜索", "INFO")
        self.log("="*70, "INFO")

        # 搜索关键词
        keywords = ["监控点", "根节点", "资源", "视频", "摄像头", "相机", "点位", "区域"]

        search_results = {}

        for keyword in keywords:
            try:
                elements = await self.iframe.get_by_text(keyword).all()
                visible_elements = []

                for el in elements:
                    is_visible = await el.evaluate("el => { const rect = el.getBoundingClientRect(); return rect.width > 0 && rect.height > 0; }")
                    if is_visible:
                        text = await el.evaluate("el => el.textContent")
                        visible_elements.append({
                            "text": text[:100] if text else ""
                        })

                search_results[keyword] = {
                    "total": len(elements),
                    "visible": len(visible_elements),
                    "samples": visible_elements[:3]
                }

                if len(visible_elements) > 0:
                    self.log(f"  ✅ '{keyword}': {len(visible_elements)} 个可见元素", "SUCCESS")
                    for sample in visible_elements[:2]:
                        self.log(f"      {sample['text'][:60]}", "INFO")
                else:
                    self.log(f"  ⚪ '{keyword}': 未找到可见元素", "INFO")

            except Exception as e:
                search_results[keyword] = {"error": str(e)}
                self.log(f"  ❌ '{keyword}': {e}", "ERROR")

        self.record_result("text_based_search", True, search_results)
        return search_results

    async def test_05_tree_structure_analysis(self):
        """测试5: 树形结构深度分析"""
        self.log("\n" + "="*70, "INFO")
        self.log("测试5: 树形结构深度分析", "INFO")
        self.log("="*70, "INFO")

        # 尝试找到左侧树形区域并分析其结构
        tree_structure = await self.iframe.evaluate("""
            () => {
                const result = {
                    left_panel_elements: [],
                    potential_trees: [],
                    nested_structures: []
                };

                // 1. 左侧面板元素
                const allElements = document.querySelectorAll('*');
                allElements.forEach(el => {
                    const rect = el.getBoundingClientRect();
                    if (rect.x < 250 && rect.width > 0 && rect.height > 0) {
                        const text = (el.textContent || '').trim();
                        if (text && text.length > 0 && text.length < 100) {
                            result.left_panel_elements.push({
                                tag: el.tagName,
                                text: text.substring(0, 50),
                                className: el.className,
                                id: el.id,
                                x: Math.round(rect.x),
                                y: Math.round(rect.y),
                                width: Math.round(rect.width),
                                height: Math.round(rect.height),
                                has_children: el.children.length > 0
                            });
                        }
                    }
                });

                // 2. 查找可能的树形容器
                const potentialTrees = [
                    '.el-tree',
                    '[class*="tree"]',
                    '[class*="Tree"]',
                    '[role="tree"]',
                    '.tree-view',
                    '.treeview'
                ];

                potentialTrees.forEach(selector => {
                    try {
                        const elements = document.querySelectorAll(selector);
                        elements.forEach(el => {
                            const rect = el.getBoundingClientRect();
                            if (rect.width > 0 && rect.height > 0) {
                                result.potential_trees.push({
                                    selector: selector,
                                    className: el.className,
                                    child_count: el.children.length,
                                    x: Math.round(rect.x),
                                    y: Math.round(rect.y),
                                    width: Math.round(rect.width),
                                    height: Math.round(rect.height)
                                });
                            }
                        });
                    } catch (e) {
                        // 忽略无效选择器
                    }
                });

                // 3. 分析嵌套结构（可能是树节点）
                allElements.forEach(el => {
                    const text = (el.textContent || '').trim();
                    if (text && text.length < 50 && text.length > 2) {
                        // 检查是否有子元素
                        if (el.children.length > 0 && el.children.length < 10) {
                            const rect = el.getBoundingClientRect();
                            if (rect.x < 300) {
                                result.nested_structures.push({
                                    tag: el.tagName,
                                    text: text,
                                    child_count: el.children.length,
                                    className: el.className,
                                    x: Math.round(rect.x),
                                    y: Math.round(rect.y)
                                });
                            }
                        }
                    }
                });

                return result;
            }
        """)

        self.log(f"左侧面板元素: {len(tree_structure['left_panel_elements'])} 个", "INFO")
        unique_elements = {}
        for el in tree_structure['left_panel_elements']:
            key = f"{el['text'][:30]}"
            if key not in unique_elements:
                unique_elements[key] = el
                if len(unique_elements) <= 20:
                    self.log(f"  <{el['tag']}> {el['text'][:40]}", "INFO")

        self.log(f"\n可能的树形容器: {len(tree_structure['potential_trees'])} 个", "INFO")
        for tree in tree_structure['potential_trees']:
            self.log(f"  {tree['selector']}: {tree['child_count']} 个子元素", "INFO")

        self.log(f"\n嵌套结构: {len(tree_structure['nested_structures'])} 个", "INFO")
        for struct in tree_structure['nested_structures'][:10]:
            self.log(f"  <{struct['tag']}> '{struct['text'][:30]}' ({struct['child_count']} 子元素)", "INFO")

        self.record_result("tree_structure_analysis", True, tree_structure)
        return tree_structure

    async def test_06_click_and_monitor(self):
        """测试6: 点击并监控变化"""
        self.log("\n" + "="*70, "INFO")
        self.log("测试6: 尝试点击展开按钮并监控变化", "INFO")
        self.log("="*70, "INFO")

        # 记录点击前的状态
        before_elements = await self.iframe.evaluate("""
            () => {
                return {
                    visible_text: document.body.innerText.substring(0, 500),
                    element_count: document.querySelectorAll('*').length,
                    tree_nodes: document.querySelectorAll('[class*="tree"], [role="treeitem"]').length
                };
            }
        """)

        self.log(f"点击前: {before_elements['element_count']} 个元素", "INFO")

        # 尝试多种点击策略
        click_strategies = [
            "点击包含'>'符号的元素",
            "点击 aria-expanded=false 的元素",
            "点击左侧第一个小图标",
            "点击包含'监控点'的元素的首个子元素"
        ]

        for idx, strategy in enumerate(click_strategies):
            self.log(f"\n尝试策略 {idx + 1}: {strategy}", "INFO")

            try:
                if idx == 0:
                    # 策略1: 点击包含'>'符号的元素
                    clicked = await self.iframe.evaluate("""
                        () => {
                            const all = document.querySelectorAll('*');
                            for (const el of all) {
                                const text = (el.textContent || '').trim();
                                if (text === '>') {
                                    el.click();
                                    return {success: true, method: 'found_arrow'};
                                }
                            }
                            return {success: false};
                        }
                    """)

                elif idx == 1:
                    # 策略2: 点击 aria-expanded=false 的元素
                    clicked = await self.iframe.evaluate("""
                        () => {
                            const all = document.querySelectorAll('[aria-expanded="false"]');
                            if (all.length > 0) {
                                all[0].click();
                                return {success: true, method: 'aria_expand'};
                            }
                            return {success: false};
                        }
                    """)

                elif idx == 2:
                    # 策略3: 点击左侧第一个小图标
                    clicked = await self.iframe.evaluate("""
                        () => {
                            const all = document.querySelectorAll('*');
                            for (const el of all) {
                                const rect = el.getBoundingClientRect();
                                if (rect.x < 200 && rect.width < 30 && rect.height < 30 && rect.width > 5) {
                                    el.click();
                                    return {success: true, method: 'small_icon', x: rect.x, y: rect.y};
                                }
                            }
                            return {success: false};
                        }
                    """)

                elif idx == 3:
                    # 策略4: 点击包含'监控点'的元素的首个子元素
                    clicked = await self.iframe.evaluate("""
                        () => {
                            const all = document.querySelectorAll('*');
                            for (const el of all) {
                                const text = el.textContent || '';
                                if (text.includes('监控点') && text.length < 100) {
                                    const parent = el.parentElement;
                                    if (parent && parent.firstElementChild) {
                                        parent.firstElementChild.click();
                                        return {success: true, method: 'monitor_expand'};
                                    }
                                }
                            }
                            return {success: false};
                        }
                    """)

                if clicked.get('success'):
                    self.log(f"  ✅ 点击成功: {clicked.get('method')}", "SUCCESS")
                    await asyncio.sleep(1)

                        # 检查点击后的变化
                    after_elements = await self.iframe.evaluate("""
                        () => {
                            return {
                                visible_text: document.body.innerText.substring(0, 500),
                                element_count: document.querySelectorAll('*').length,
                                tree_nodes: document.querySelectorAll('[class*="tree"], [role="treeitem"]').length
                            };
                        }
                    """)

                    element_delta = after_elements['element_count'] - before_elements['element_count']

                    if element_delta != 0:
                        delta_str = f"+{element_delta}" if element_delta > 0 else str(element_delta)
                        self.log(f"  元素数量变化: {delta_str}", "SUCCESS")
                        before_elements = after_elements

                        # 保存截图
                        screenshot_path = f"after_click_strategy_{idx + 1}.png"
                        await self.page.screenshot(path=screenshot_path)
                        self.log(f"  已保存截图: {screenshot_path}", "INFO")

                else:
                    self.log(f"  未找到可点击的元素", "WARN")

            except Exception as e:
                self.log(f"  策略执行失败: {e}", "ERROR")

        self.record_result("click_and_monitor", True, {"strategies_tested": len(click_strategies)})
        return True

    async def test_07_left_menu_expand(self):
        """测试7: 左侧菜单展开（参考用户测试代码）"""
        self.log("\n" + "="*70, "INFO")
        self.log("测试7: 左侧菜单展开", "INFO")
        self.log("="*70, "INFO")

        try:
            # 先尝试展开左侧菜单
            expand_result = await self.iframe.evaluate("""
                () => {
                    const collapseBtn = document.querySelector('li.el-menu--colloase-btn, li[class*="collapse"], li[class*="expand"]');
                    if (collapseBtn) {
                        collapseBtn.click();
                        return {success: true, method: 'javascript_click', found: true};
                    }
                    return {success: false, method: 'not_found', found: false};
                }
            """)

            if expand_result.get('success'):
                self.log("已点击左侧菜单展开按钮", "SUCCESS")
                await asyncio.sleep(2)
                await self.page.screenshot(path="after_left_menu_expand.png")
                self.log("已保存截图: after_left_menu_expand.png", "INFO")

                # 点击"资源视图"
                click_result = await self.iframe.evaluate("""
                    () => {
                        const menuItems = document.querySelectorAll('li.el-menu-item');
                        for (const item of menuItems) {
                            const text = item.textContent || '';
                            if (text.includes('资源视图')) {
                                item.click();
                                return {success: true, method: 'found_and_clicked'};
                            }
                        }
                        return {success: false, method: 'not_found'};
                    }
                """)

                if click_result.get('success'):
                    self.log("已点击'资源视图'", "SUCCESS")
                    await asyncio.sleep(2)
                    await self.page.screenshot(path="after_resource_view.png")
                    self.log("已保存截图: after_resource_view.png", "INFO")
                    return True

            else:
                self.log("未找到左侧菜单展开按钮", "WARN")

        except Exception as e:
            self.log(f"左侧菜单展开失败: {e}", "ERROR")

        self.record_result("left_menu_expand", False, {})
        return False

    async def test_08_comprehensive_element_scan(self):
        """测试8: 全面的元素扫描（包括隐藏元素）"""
        self.log("\n" + "="*70, "INFO")
        self.log("测试8: 全面的元素扫描", "INFO")
        self.log("="*70, "INFO")

        comprehensive_scan = await self.iframe.evaluate("""
            () => {
                const results = {
                    interactive_elements: [],
                    clickable_elements: [],
                    all_buttons: [],
                    tree_related: []
                };

                const allElements = document.querySelectorAll('*');

                allElements.forEach(el => {
                    const rect = el.getBoundingClientRect();
                    const style = window.getComputedStyle(el);
                    const className = el.className || '';
                    const text = (el.textContent || '').trim().substring(0, 50);

                    // 1. 可交互元素（即使隐藏）
                    const hasClickHandler = el.onclick !== null;
                    const hasTabIndex = el.tabIndex !== -1;
                    const isClickable = hasClickHandler || hasTabIndex ||
                                      style.cursor === 'pointer' ||
                                      ['button', 'a', 'input', 'select', 'textarea'].includes(el.tagName.toLowerCase());

                    if (isClickable) {
                        results.clickable_elements.push({
                            tag: el.tagName,
                            className: className,
                            text: text,
                            visible: rect.width > 0 && rect.height > 0 && style.display !== 'none' && style.visibility !== 'hidden',
                            x: Math.round(rect.x),
                            y: Math.round(rect.y),
                            hasClick: hasClickHandler,
                            cursor: style.cursor
                        });
                    }

                    // 2. 所有按钮
                    if (el.tagName.toLowerCase() === 'button' || el.getAttribute('role') === 'button') {
                        results.all_buttons.push({
                            className: className,
                            text: text,
                            visible: rect.width > 0 && rect.height > 0
                        });
                    }

                    // 3. 树相关元素
                    if (/tree|node|expand|collapse|branch|leaf/i.test(className) ||
                        el.getAttribute('role') === 'treeitem' ||
                        el.getAttribute('aria-expanded') !== null) {
                        results.tree_related.push({
                            tag: el.tagName,
                            className: className,
                            role: el.getAttribute('role'),
                            ariaExpanded: el.getAttribute('aria-expanded'),
                            text: text,
                            visible: rect.width > 0 && rect.height > 0
                        });
                    }
                });

                return results;
            }
        """)

        self.log(f"可交互元素: {len(comprehensive_scan['clickable_elements'])} 个", "INFO")
        visible_clickable = [e for e in comprehensive_scan['clickable_elements'] if e['visible']]
        hidden_clickable = [e for e in comprehensive_scan['clickable_elements'] if not e['visible']]
        self.log(f"  可见: {len(visible_clickable)} 个", "INFO")
        self.log(f"  隐藏: {len(hidden_clickable)} 个", "INFO")

        self.log(f"\n所有按钮: {len(comprehensive_scan['all_buttons'])} 个", "INFO")
        visible_buttons = [e for e in comprehensive_scan['all_buttons'] if e['visible']]
        self.log(f"  可见: {len(visible_buttons)} 个", "INFO")

        self.log(f"\n树相关元素: {len(comprehensive_scan['tree_related'])} 个", "INFO")
        visible_tree = [e for e in comprehensive_scan['tree_related'] if e['visible']]
        self.log(f"  可见: {len(visible_tree)} 个", "INFO")
        for el in visible_tree[:10]:
            self.log(f"    <{el['tag']}> {el['text'][:30]} (role={el['role']}, aria-expanded={el['ariaExpanded']})", "INFO")

        self.record_result("comprehensive_element_scan", True, comprehensive_scan)
        return comprehensive_scan

    async def save_results(self):
        """保存测试结果"""
        filename = f"haikang_test_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(self.results, f, ensure_ascii=False, indent=2)
        self.log(f"\n测试结果已保存到: {filename}", "SUCCESS")


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

        tester = HaikangVideoTester(page)

        try:
            # 登录并进入实时预览
            await tester.auto_login_and_enter()

            # 等待页面稳定
            await asyncio.sleep(3)

            # 执行测试序列
            await tester.test_01_iframe_content_analysis()
            await tester.test_02_tree_selectors()
            await tester.test_03_expand_button_detection()
            await tester.test_04_text_based_search()
            await tester.test_05_tree_structure_analysis()
            await tester.test_07_left_menu_expand()
            await tester.test_08_comprehensive_element_scan()
            await tester.test_06_click_and_monitor()

            # 保存结果
            await tester.save_results()

            tester.log("\n" + "="*70, "SUCCESS")
            tester.log("所有测试完成！", "SUCCESS")
            tester.log("="*70, "SUCCESS")

            # 保持浏览器打开，方便手动检查
            tester.log("\n浏览器将保持打开60秒，您可以手动检查页面...", "INFO")
            await asyncio.sleep(60)

        except Exception as e:
            tester.log(f"\n测试执行出错: {e}", "ERROR")
            import traceback
            traceback.print_exc()
            await page.screenshot(path="error_screenshot.png")

        finally:
            await browser.close()


if __name__ == "__main__":
    print("""
╔════════════════════════════════════════════════════════════╗
║        海康视频平台综合调试测试工具                      ║
╚════════════════════════════════════════════════════════════╝

测试内容：
1. iframe 内容深度分析
2. 多种树形控件选择器测试
3. 展开/折叠按钮检测
4. 基于文本的元素搜索
5. 树形结构深度分析
6. 点击并监控变化
7. 左侧菜单展开
8. 全面的元素扫描

登录信息：
URL: http://10.10.10.158
用户名: cdzhuanyong
密码: cdsz@429

    """)

    asyncio.run(main())
