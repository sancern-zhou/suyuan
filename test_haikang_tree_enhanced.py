"""
海康视频平台树形控件增强测试脚本

目标：深度测试树形控件的发现和操作

增强策略：
1. 更长的等待时间（懒加载）
2. 隐藏元素扫描
3. 多种DOM结构分析
4. 事件监听和模拟
5. 坐标级精确点击
"""

import asyncio
import json
from datetime import datetime
from playwright.async_api import async_playwright

BASE_URL = "http://10.10.10.158"
USERNAME = "cdzhuanyong"
PASSWORD = "cdsz@429"


class EnhancedTreeTester:
    """增强版树形控件测试器"""

    def __init__(self, page):
        self.page = page
        self.iframe = None
        self.results = []

    def log(self, message, level="INFO"):
        timestamp = datetime.now().strftime("%H:%M:%S")
        icon = {"INFO": "ℹ️", "SUCCESS": "✅", "WARN": "⚠️", "ERROR": "❌"}[level]
        print(f"[{timestamp}] {icon} {message}")

    async def auto_login_and_setup(self):
        """自动登录并设置环境"""
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

        # 获取iframe
        self.iframe = self.page.frame(name="vms_010100")
        if not self.iframe:
            self.log("未找到iframe，尝试其他方式", "WARN")
            for frame in self.page.frames:
                if "vms" in frame.url.lower() or "preview" in frame.url.lower():
                    self.iframe = frame
                    self.log(f"找到iframe: {frame.name}", "SUCCESS")
                    break

        if not self.iframe:
            self.iframe = self.page
            self.log("使用主页面", "WARN")

    async def setup_left_menu(self):
        """设置左侧菜单（展开+点击资源视图）"""
        self.log("展开左侧菜单...", "INFO")

        # 展开左侧菜单
        await self.iframe.evaluate("""
            () => {
                const collapseBtn = document.querySelector('li.el-menu--colloase-btn, li[class*="collapse"], li[class*="expand"]');
                if (collapseBtn) {
                    collapseBtn.click();
                    return {success: true};
                }
                return {success: false};
            }
        """)
        await asyncio.sleep(2)

        # 点击"资源视图"
        await self.iframe.evaluate("""
            () => {
                const menuItems = document.querySelectorAll('li.el-menu-item');
                for (const item of menuItems) {
                    const text = item.textContent || '';
                    if (text.includes('资源视图')) {
                        item.click();
                        return {success: true};
                    }
                }
                return {success: false};
            }
        """)
        await asyncio.sleep(3)
        await self.page.screenshot(path="enhanced_after_resource_view.png")
        self.log("左侧菜单设置完成", "SUCCESS")

    async def test_01_hidden_elements_scan(self):
        """测试1: 扫描隐藏元素"""
        self.log("\n" + "="*70, "INFO")
        self.log("测试1: 扫描所有元素（包括隐藏）", "INFO")
        self.log("="*70, "INFO")

        scan_result = await self.iframe.evaluate("""
            () => {
                const results = {
                    total: 0,
                    visible: 0,
                    hidden: 0,
                    visible_elements: [],
                    hidden_elements: []
                };

                const allElements = document.querySelectorAll('*');
                results.total = allElements.length;

                allElements.forEach(el => {
                    const rect = el.getBoundingClientRect();
                    const style = window.getComputedStyle(el);
                    const isVisible = rect.width > 0 && rect.height > 0 &&
                                     style.display !== 'none' &&
                                     style.visibility !== 'hidden' &&
                                     style.opacity !== '0';

                    if (isVisible) {
                        results.visible++;
                        if (results.visible_elements.length < 30) {
                            results.visible_elements.push({
                                tag: el.tagName,
                                className: el.className,
                                id: el.id,
                                text: (el.textContent || '').trim().substring(0, 30),
                                x: Math.round(rect.x),
                                y: Math.round(rect.y)
                            });
                        }
                    } else {
                        results.hidden++;
                        if (results.hidden_elements.length < 50) {
                            const text = (el.textContent || '').trim().substring(0, 50);
                            // 只记录有意义的隐藏元素
                            if (text && text.length > 2 && text.length < 100) {
                                results.hidden_elements.push({
                                    tag: el.tagName,
                                    className: el.className,
                                    id: el.id,
                                    text: text,
                                    display: style.display,
                                    visibility: style.visibility,
                                    opacity: style.opacity,
                                    hasChildren: el.children.length > 0
                                });
                            }
                        }
                    }
                });

                return results;
            }
        """)

        self.log(f"总元素: {scan_result['total']}", "INFO")
        self.log(f"可见元素: {scan_result['visible']}", "INFO")
        self.log(f"隐藏元素: {scan_result['hidden']}", "INFO")

        self.log("\n可见元素示例:", "INFO")
        for el in scan_result['visible_elements'][:20]:
            self.log(f"  <{el['tag']}> {el['text'][:30]}", "INFO")

        self.log(f"\n隐藏元素（有文本的）: {len(scan_result['hidden_elements'])} 个", "INFO")
        for el in scan_result['hidden_elements'][:30]:
            reason = []
            if el['display'] == 'none': reason.append('display:none')
            if el['visibility'] == 'hidden': reason.append('visibility:hidden')
            if el['opacity'] == '0': reason.append('opacity:0')

            reason_str = ', '.join(reason) if reason else 'unknown'
            self.log(f"  <{el['tag']}> {el['text'][:40]} ({reason_str})", "INFO")

        return scan_result

    async def test_02_dom_tree_analysis(self):
        """测试2: DOM树结构深度分析"""
        self.log("\n" + "="*70, "INFO")
        self.log("测试2: DOM树结构分析", "INFO")
        self.log("="*70, "INFO")

        dom_analysis = await self.iframe.evaluate("""
            () => {
                const results = {
                    left_panel_structure: [],
                    potential_containers: [],
                    text_based_search: []
                };

                // 1. 分析左侧面板结构（x < 250）
                const leftPanelElements = [];
                const allElements = document.querySelectorAll('*');

                allElements.forEach(el => {
                    const rect = el.getBoundingClientRect();
                    if (rect.x >= 0 && rect.x < 250 && rect.width > 0) {
                        const text = (el.textContent || '').trim();
                        if (text && text.length > 0 && text.length < 100) {
                            // 获取元素的完整路径
                            let path = [];
                            let current = el;
                            while (current && current !== document.body) {
                                let selector = current.tagName.toLowerCase();
                                if (current.id) {
                                    selector += '#' + current.id;
                                    path.unshift(selector);
                                    break;
                                }
                                if (current.className) {
                                    const classes = current.className.split(' ').filter(c => c);
                                    if (classes.length > 0) {
                                        selector += '.' + classes[0];
                                    }
                                }
                                path.unshift(selector);
                                current = current.parentElement;
                                if (path.length > 5) break;
                            }

                            leftPanelElements.push({
                                tag: el.tagName,
                                text: text.substring(0, 50),
                                className: el.className,
                                id: el.id,
                                path: path.join(' > '),
                                x: Math.round(rect.x),
                                y: Math.round(rect.y),
                                width: Math.round(rect.width),
                                height: Math.round(rect.height),
                                hasChildren: el.children.length > 0
                            });
                        }
                    }
                });

                // 去重
                const seen = new Set();
                results.left_panel_structure = leftPanelElements.filter(el => {
                    const key = el.text.substring(0, 30);
                    if (seen.has(key)) return false;
                    seen.add(key);
                    return true;
                }).slice(0, 25);

                // 2. 查找可能的容器
                const containerPatterns = ['panel', 'sidebar', 'tree', 'list', 'menu', 'nav'];
                containerPatterns.forEach(pattern => {
                    const selector = `[class*="${pattern}"]`;
                    try {
                        const elements = document.querySelectorAll(selector);
                        elements.forEach(el => {
                            const rect = el.getBoundingClientRect();
                            if (rect.width > 0 && rect.height > 50) {
                                results.potential_containers.push({
                                    pattern: pattern,
                                    className: el.className,
                                    childCount: el.children.length,
                                    textCount: el.textContent.length,
                                    x: Math.round(rect.x),
                                    y: Math.round(rect.y),
                                    width: Math.round(rect.width),
                                    height: Math.round(rect.height)
                                });
                            }
                        });
                    } catch (e) {}
                });

                // 3. 基于文本的搜索（包括隐藏元素）
                const keywords = ['监控', '点', '根', '节点', '树', 'camera', 'video', 'monitor'];
                keywords.forEach(keyword => {
                    const allElements = document.querySelectorAll('*');
                    allElements.forEach(el => {
                        const text = (el.textContent || '').trim();
                        if (text.toLowerCase().includes(keyword.toLowerCase()) &&
                            text.length < 200 && text.length > keyword.length - 1) {
                            const rect = el.getBoundingClientRect();
                            results.text_based_search.push({
                                keyword: keyword,
                                text: text.substring(0, 60),
                                tag: el.tagName,
                                className: el.className,
                                visible: rect.width > 0 && rect.height > 0,
                                x: Math.round(rect.x),
                                y: Math.round(rect.y)
                            });
                        }
                    });
                });

                return results;
            }
        """)

        self.log(f"左侧面板元素: {len(dom_analysis['left_panel_structure'])} 个", "INFO")
        for el in dom_analysis['left_panel_structure']:
            self.log(f"  <{el['tag']}> {el['text'][:40]}", "INFO")

        self.log(f"\n可能的容器: {len(dom_analysis['potential_containers'])} 个", "INFO")
        for container in dom_analysis['potential_containers'][:10]:
            self.log(f"  [{container['pattern']}] {container['className'][:50]}: {container['childCount']} 子元素, {container['textCount']} 字符", "INFO")

        self.log(f"\n文本搜索结果: {len(dom_analysis['text_based_search'])} 个", "INFO")
        for item in dom_analysis['text_based_search'][:20]:
            visibility = "可见" if item['visible'] else "隐藏"
            self.log(f"  [{item['keyword']}] {item['text'][:40]} ({visibility})", "INFO")

        return dom_analysis

    async def test_03_lazy_loading_wait(self):
        """测试3: 懒加载等待测试"""
        self.log("\n" + "="*70, "INFO")
        self.log("测试3: 懒加载等待测试", "INFO")
        self.log("="*70, "INFO")

        wait_times = [1, 3, 5, 10]
        element_counts = []

        for wait_time in wait_times:
            self.log(f"等待 {wait_time} 秒...", "INFO")
            await asyncio.sleep(wait_time)

            count = await self.iframe.evaluate("""
                () => {
                    const all = document.querySelectorAll('*');
                    const visible = Array.from(all).filter(el => {
                        const rect = el.getBoundingClientRect();
                        return rect.width > 0 && rect.height > 0;
                    });
                    return {
                        total: all.length,
                        visible: visible.length
                    };
                }
            """)

            element_counts.append({
                'wait_time': wait_time,
                **count
            })

            self.log(f"  总元素: {count['total']}, 可见: {count['visible']}", "INFO")

            await self.page.screenshot(path=f"lazy_load_wait_{wait_time}s.png")

        # 检查是否有变化
        if len(element_counts) > 1:
            first = element_counts[0]
            last = element_counts[-1]
            if last['total'] != first['total']:
                self.log(f"元素数量变化: {first['total']} -> {last['total']}", "SUCCESS")

        return element_counts

    async def test_04_coordinate_based_clicking(self):
        """测试4: 基于坐标的精确点击"""
        self.log("\n" + "="*70, "INFO")
        self.log("测试4: 坐标级精确点击测试", "INFO")
        self.log("="*70, "INFO")

        # 找到左侧区域的所有可点击位置
        clickable_positions = await self.iframe.evaluate("""
            () => {
                const positions = [];
                const allElements = document.querySelectorAll('*');

                allElements.forEach(el => {
                    const rect = el.getBoundingClientRect();

                    // 左侧区域的小元素（可能是图标/按钮）
                    if (rect.x >= 0 && rect.x < 200 &&
                        rect.width > 5 && rect.width < 50 &&
                        rect.height > 5 && rect.height < 50) {

                        const style = window.getComputedStyle(el);
                        const hasInteraction = el.onclick !== null ||
                                             el.tabIndex >= 0 ||
                                             style.cursor === 'pointer' ||
                                             ['button', 'a'].includes(el.tagName.toLowerCase());

                        if (hasInteraction) {
                            positions.push({
                                x: Math.round(rect.x + rect.width / 2),
                                y: Math.round(rect.y + rect.height / 2),
                                width: Math.round(rect.width),
                                height: Math.round(rect.height),
                                tag: el.tagName,
                                className: el.className,
                                text: (el.textContent || '').trim().substring(0, 20)
                            });
                        }
                    }
                });

                return positions;
            }
        """)

        self.log(f"找到 {len(clickable_positions)} 个左侧可点击位置", "INFO")

        # 按Y坐标排序（从上到下）
        clickable_positions.sort(key=lambda p: p['y'])

        # 尝试点击前10个位置
        for idx, pos in enumerate(clickable_positions[:10]):
            self.log(f"\n点击位置 {idx + 1}: ({pos['x']}, {pos['y']}) - {pos['text'][:30]}", "INFO")

            # 记录点击前的元素数量
            before_count = await self.iframe.evaluate("() => document.querySelectorAll('*').length")

            # 点击
            try:
                await self.iframe.mouse.click(pos['x'], pos['y'])
                await asyncio.sleep(1)

                # 记录点击后的元素数量
                after_count = await self.iframe.evaluate("() => document.querySelectorAll('*').length")
                delta = after_count - before_count

                if delta != 0:
                    self.log(f"  ✅ 元素数量变化: {delta:+d}", "SUCCESS")
                    await self.page.screenshot(path=f"coord_click_{idx + 1}_result.png")
                else:
                    self.log(f"  ⚪ 无变化", "INFO")

            except Exception as e:
                self.log(f"  ❌ 点击失败: {e}", "ERROR")

        return clickable_positions

    async def test_05_element_attribute_analysis(self):
        """测试5: 元素属性深度分析"""
        self.log("\n" + "="*70, "INFO")
        self.log("测试5: 元素属性深度分析", "INFO")
        self.log("="*70, "INFO")

        attribute_analysis = await self.iframe.evaluate("""
            () => {
                const results = {
                    data_attributes: [],
                    event_handlers: [],
                    custom_attributes: []
                };

                const allElements = document.querySelectorAll('*');

                allElements.forEach(el => {
                    const rect = el.getBoundingClientRect();
                    if (rect.width <= 0 || rect.height <= 0) return;

                    // 检查data-*属性
                    for (const attr of el.attributes) {
                        if (attr.name.startsWith('data-')) {
                            const text = (el.textContent || '').trim().substring(0, 30);
                            results.data_attributes.push({
                                attribute: attr.name,
                                value: attr.value,
                                tag: el.tagName,
                                text: text,
                                className: el.className,
                                x: Math.round(rect.x),
                                y: Math.round(rect.y)
                            });
                        }
                    }

                    // 检查事件处理器
                    const hasClick = el.onclick !== null;
                    const hasDblClick = el.ondblclick !== null;
                    const hasMouseOver = el.onmouseover !== null;

                    if (hasClick || hasDblClick || hasMouseOver) {
                        const text = (el.textContent || '').trim().substring(0, 30);
                        results.event_handlers.push({
                            tag: el.tagName,
                            className: el.className,
                            text: text,
                            hasClick: hasClick,
                            hasDblClick: hasDblClick,
                            hasMouseOver: hasMouseOver,
                            tabIndex: el.tabIndex,
                            x: Math.round(rect.x),
                            y: Math.round(rect.y)
                        });
                    }

                    // 检查自定义属性
                    for (const attr of el.attributes) {
                        if (attr.name.includes('-') || attr.name.includes(':')) {
                            results.custom_attributes.push({
                                attribute: attr.name,
                                value: attr.value.substring(0, 50)
                            });
                        }
                    }
                });

                return results;
            }
        """)

        self.log(f"data-* 属性: {len(attribute_analysis['data_attributes'])} 个", "INFO")
        for attr in attribute_analysis['data_attributes'][:15]:
            self.log(f"  {attr['attribute']}={attr['value'][:30]}: {attr['text'][:30]}", "INFO")

        self.log(f"\n事件处理器: {len(attribute_analysis['event_handlers'])} 个", "INFO")
        for handler in attribute_analysis['event_handlers'][:15]:
            events = []
            if handler['hasClick']: events.append('click')
            if handler['hasDblClick']: events.append('dblclick')
            if handler['hasMouseOver']: events.append('mouseover')
            self.log(f"  <{handler['tag']}> {handler['text'][:30]}: {', '.join(events)}", "INFO")

        return attribute_analysis

    async def test_06_network_request_monitoring(self):
        """测试6: 网络请求监控"""
        self.log("\n" + "="*70, "INFO")
        self.log("测试6: 网络请求监控（点击后触发的新请求）", "INFO")
        self.log("="*70, "INFO")

        # 监控网络请求
        requests = []

        def handle_request(request):
            requests.append({
                'url': request.url,
                'method': request.method,
                'resource_type': request.resource_type
            })

        def handle_response(response):
            if response.status >= 400:
                self.log(f"请求失败: {response.url} - {response.status}", "WARN")

        self.page.on("request", handle_request)
        self.page.on("response", handle_response)

        # 清空之前的请求
        requests.clear()

        # 尝试一些操作
        self.log("尝试点击左侧区域...", "INFO")

        await self.iframe.evaluate("""
            () => {
                // 尝试触发一些事件
                const leftElements = Array.from(document.querySelectorAll('*')).filter(el => {
                    const rect = el.getBoundingClientRect();
                    return rect.x >= 0 && rect.x < 200 && rect.width > 0 && rect.height > 0;
                });

                // 按Y坐标排序，点击前5个
                leftElements.sort((a, b) => {
                    const rectA = a.getBoundingClientRect();
                    const rectB = b.getBoundingClientRect();
                    return rectA.y - rectB.y;
                });

                for (let i = 0; i < Math.min(5, leftElements.length); i++) {
                    try {
                        leftElements[i].click();
                    } catch (e) {}
                }

                return {clicked: Math.min(5, leftElements.length)};
            }
        """)

        await asyncio.sleep(3)

        self.log(f"捕获到 {len(requests)} 个请求", "INFO")

        # 分析API请求
        api_requests = [r for r in requests if 'api' in r['url'].lower() or 'vms' in r['url'].lower()]
        self.log(f"API请求: {len(api_requests)} 个", "INFO")

        for req in api_requests[:10]:
            self.log(f"  [{req['method']}] {req['url'][:80]}", "INFO")

        return requests

    async def test_07_css_class_pattern_analysis(self):
        """测试7: CSS class模式分析"""
        self.log("\n" + "="*70, "INFO")
        self.log("测试7: CSS class模式分析", "INFO")
        self.log("="*70, "INFO")

        class_analysis = await self.iframe.evaluate("""
            () => {
                const results = {
                    all_classes: {},
                    left_panel_classes: {}
                };

                const allElements = document.querySelectorAll('*');

                allElements.forEach(el => {
                    const classes = el.className.split(' ').filter(c => c);
                    const rect = el.getBoundingClientRect();

                    classes.forEach(cls => {
                        // 统计所有class
                        if (!results.all_classes[cls]) {
                            results.all_classes[cls] = 0;
                        }
                        results.all_classes[cls]++;

                        // 统计左侧panel的class
                        if (rect.x >= 0 && rect.x < 250 && rect.width > 0 && rect.height > 0) {
                            if (!results.left_panel_classes[cls]) {
                                results.left_panel_classes[cls] = 0;
                            }
                            results.left_panel_classes[cls]++;
                        }
                    });
                });

                // 排序并只保留有意义的（出现次数适中的）
                const sortedAllClasses = Object.entries(results.all_classes)
                    .filter(([cls, count]) => count > 0 && count < 100)
                    .sort((a, b) => b[1] - a[1])
                    .slice(0, 30);

                const sortedLeftClasses = Object.entries(results.left_panel_classes)
                    .filter(([cls, count]) => count > 0 && count < 50)
                    .sort((a, b) => b[1] - a[1])
                    .slice(0, 30);

                return {
                    all_classes: sortedAllClasses,
                    left_panel_classes: sortedLeftClasses
                };
            }
        """)

        self.log("所有页面class（按出现次数）:", "INFO")
        for cls, count in class_analysis['all_classes'][:20]:
            self.log(f"  .{cls}: {count} 次", "INFO")

        self.log("\n左侧面板class（按出现次数）:", "INFO")
        for cls, count in class_analysis['left_panel_classes'][:20]:
            self.log(f"  .{cls}: {count} 次", "INFO")

        return class_analysis

    async def save_results(self, test_name, data):
        """保存测试结果"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"tree_enhanced_{test_name}_{timestamp}.json"

        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        self.log(f"结果已保存: {filename}", "INFO")


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,
            slow_mo=300,
            args=['--ignore-certificate-errors']
        )
        context = await browser.new_context(
            viewport={"width": 1920, "height": 1080},
            ignore_https_errors=True
        )
        page = await context.new_page()

        tester = EnhancedTreeTester(page)

        try:
            # 登录和设置
            await tester.auto_login_and_setup()
            await tester.setup_left_menu()

            # 执行测试
            result1 = await tester.test_01_hidden_elements_scan()
            await tester.save_results("hidden_elements", result1)

            result2 = await tester.test_02_dom_tree_analysis()
            await tester.save_results("dom_tree", result2)

            result3 = await tester.test_03_lazy_loading_wait()
            await tester.save_results("lazy_loading", result3)

            result4 = await tester.test_04_coordinate_based_clicking()
            await tester.save_results("coordinate_click", result4)

            result5 = await tester.test_05_element_attribute_analysis()
            await tester.save_results("attributes", result5)

            result6 = await tester.test_06_network_request_monitoring()
            await tester.save_results("network", result6)

            result7 = await tester.test_07_css_class_pattern_analysis()
            await tester.save_results("css_classes", result7)

            tester.log("\n" + "="*70, "SUCCESS")
            tester.log("增强测试完成！", "SUCCESS")
            tester.log("="*70, "SUCCESS")

            tester.log("\n浏览器保持打开60秒...", "INFO")
            await asyncio.sleep(60)

        except Exception as e:
            tester.log(f"\n测试出错: {e}", "ERROR")
            import traceback
            traceback.print_exc()
            await page.screenshot(path="enhanced_error.png")

        finally:
            await browser.close()


if __name__ == "__main__":
    print("""
╔════════════════════════════════════════════════════════════╗
║        海康树形控件增强测试工具                          ║
╚════════════════════════════════════════════════════════════╝

增强测试：
1. 隐藏元素扫描
2. DOM树结构分析
3. 懒加载等待测试
4. 坐标级精确点击
5. 元素属性深度分析
6. 网络请求监控
7. CSS class模式分析

    """)

    asyncio.run(main())
