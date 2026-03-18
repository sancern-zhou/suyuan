"""
iframe 树形控件调试脚本

针对特定问题：树形控件在 iframe 里
"""

import asyncio
import json
from playwright.async_api import async_playwright
from datetime import datetime

BASE_URL = "http://10.10.10.158"
USERNAME = "cdzhuanyong"
PASSWORD = "cdsz@429"


class IframeTreeDebugger:
    """iframe 树形控件调试器"""

    def __init__(self, page):
        self.page = page
        self.iframe = None
        self.target_iframe_name = "vms_010100"  # 从调试结果得知

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
        await page.click('button[type="submit"], button:has-text("登录"), button:has-text("登 录")')
        await self.page.wait_for_load_state("networkidle", timeout=10000)
        await self.page.wait_for_timeout(2000)

        self.log("点击'实时预览'...", "INFO")
        await self.page.get_by_text("实时预览").first.click()

        self.log("等待iframe内容加载（可能需要10-30秒）...", "INFO")

        # 等待策略：等待iframe内有内容出现
        max_wait = 30000  # 最多等30秒
        check_interval = 1000  # 每秒检查一次
        waited = 0

        iframe_loaded = False
        while waited < max_wait:
            await self.page.wait_for_timeout(check_interval)
            waited += check_interval

            # 检查iframe是否有内容了
            try:
                iframe = self.page.frame(name=self.target_iframe_name)
                if iframe:
                    # 检查iframe内是否有可交互元素（除了下载控件链接）
                    element_count = await iframe.evaluate("""
                        () => {
                            const all = document.querySelectorAll('*');
                            let count = 0;
                            all.forEach(el => {
                                const text = el.textContent || '';
                                if (text && !text.includes('下载安装浏览器控件') && text.trim().length > 0) {
                                    count++;
                                }
                            });
                            return count;
                        }
                    """)

                    if element_count > 10:  # 如果有超过10个元素，说明加载了
                        self.log(f"✓ iframe内容已加载（{element_count}个元素，耗时{waited/1000}秒）", "SUCCESS")
                        iframe_loaded = True
                        break
            except:
                pass

            # 显示进度
            if waited % 5000 == 0:
                self.log(f"  已等待 {waited/1000} 秒...", "INFO")

        if not iframe_loaded:
            self.log("等待超时，但继续尝试分析...", "WARN")

        self.log("登录完成", "SUCCESS")

    async def get_target_iframe(self):
        """获取目标iframe"""
        self.log("=" * 60)
        self.log("查找目标 iframe", "INFO")
        self.log("=" * 60)

        # 等待iframe加载
        try:
            await self.page.wait_for_selector(f"iframe[name='{self.target_iframe_name}']", timeout=10000)
            self.log(f"找到目标 iframe: {self.target_iframe_name}", "SUCCESS")
        except:
            self.log(f"未找到 iframe[name='{self.target_iframe_name}']", "WARN")
            # 列出所有iframe
            frames = await self.page.query_selector_all("iframe")
            self.log(f"页面中有 {len(frames)} 个 iframe:", "INFO")
            for idx, frame in enumerate(frames):
                name = await frame.get_attribute("name") or await frame.get_attribute("id")
                src = await frame.get_attribute("src")
                self.log(f"  [{idx}] name='{name}', src='{src}'", "INFO")

            return None

        # 获取iframe对象
        self.iframe = self.page.frame(name=self.target_iframe_name)
        if not self.iframe:
            self.log("无法获取iframe对象，尝试备用方案...", "WARN")
            # 备用：通过element_handle
            iframe_element = await self.page.query_selector(f"iframe[name='{self.target_iframe_name}']")
            if iframe_element:
                self.iframe = await iframe_element.content_frame()
                self.log("通过 content_frame() 获取iframe成功", "SUCCESS")

        if self.iframe:
            self.log("iframe 对象获取成功", "SUCCESS")
            return self.iframe

        return None

    async def analyze_iframe_content(self):
        """分析iframe内部内容"""
        if not self.iframe:
            self.log("没有可用的iframe对象", "ERROR")
            return

        self.log("=" * 60)
        self.log("分析 iframe 内部结构", "INFO")
        self.log("=" * 60)

        # 0. 先检查iframe内有多少元素
        self.log("\n[0] iframe内容概览:", "INFO")
        overview = await self.iframe.evaluate("""
            () => {
                const all = document.querySelectorAll('*');
                const textElements = Array.from(all).filter(el => {
                    const text = el.textContent || '';
                    return text && text.trim().length > 0 && text.length < 100;
                });

                return {
                    totalElements: all.length,
                    textElements: textElements.length,
                    sampleTexts: textElements.slice(0, 10).map(el => ({
                        tag: el.tagName,
                        text: el.textContent.trim().substring(0, 50)
                    }))
                };
            }
        """)
        self.log(f"iframe内总元素数: {overview['totalElements']}", "INFO")
        self.log(f"有文本内容的元素: {overview['textElements']}", "INFO")

        if overview['sampleTexts']:
            self.log("前10个文本元素示例:", "INFO")
            for idx, sample in enumerate(overview['sampleTexts']):
                self.log(f"  [{idx}] <{sample['tag']}> {sample['text']}", "INFO")

        # 1. 检查iframe标题
        try:
            title = await self.iframe.title()
            self.log(f"\niframe 标题: {title}", "INFO")
        except:
            self.log("\n无法获取iframe标题", "WARN")

        # 2. 检查iframe URL
        try:
            url = self.iframe.url
            self.log(f"iframe URL: {url}", "INFO")
        except:
            self.log("无法获取iframe URL", "WARN")

        # 3. 检查 treeitem
        self.log("\n[1] 检查 iframe 内的 treeitem:", "INFO")
        treeitems = await self.iframe.query_selector_all('[role="treeitem"]')
        if treeitems:
            self.log(f"找到 {len(treeitems)} 个 treeitem 元素", "SUCCESS")
            for idx, item in enumerate(treeitems[:5]):
                text = await item.text_content()
                visible = await item.is_visible()
                aria_expanded = await item.get_attribute("aria-expanded")
                info = f"[{idx}] 文本='{text[:30]}', 可见={visible}"
                if aria_expanded:
                    info += f", 展开状态={aria_expanded}"
                self.log(info, "INFO")
        else:
            self.log("iframe内未找到 treeitem", "WARN")

        # 4. 检查树形相关class
        self.log("\n[2] 检查 iframe 内的树形class:", "INFO")
        tree_classes = await self.iframe.query_selector_all('[class*="tree"], [class*="Tree"]')
        if tree_classes:
            self.log(f"找到 {len(tree_classes)} 个包含'tree'的元素", "SUCCESS")
            for idx, el in enumerate(tree_classes[:3]):
                class_name = await el.get_attribute("class")
                text = await el.text_content()
                self.log(f"[{idx}] class='{class_name}', text='{text[:30]}'", "INFO")
        else:
            self.log("iframe内未找到包含'tree'的class", "WARN")

        # 5. 搜索包含"根"的元素
        self.log("\n[3] 在iframe内搜索包含'根'的元素:", "INFO")
        root_elements = await self.iframe.evaluate("""
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
                            });
                        }
                    }
                });

                return results.slice(0, 5);
            }
        """)

        if root_elements:
            self.log(f"找到 {len(root_elements)} 个包含'根'的元素", "SUCCESS")
            for el in root_elements:
                self.log(f"{json.dumps(el, ensure_ascii=False)}", "INFO")
        else:
            self.log("iframe内未找到包含'根'的元素", "WARN")

        # 6. 检查是否有嵌套iframe
        self.log("\n[4] 检查iframe内是否有嵌套iframe:", "INFO")
        nested_iframes = await self.iframe.query_selector_all("iframe")
        if nested_iframes:
            self.log(f"iframe内有 {len(nested_iframes)} 个嵌套iframe", "INFO")
        else:
            self.log("iframe内没有嵌套iframe", "INFO")

    async def test_click_in_iframe(self):
        """在iframe内测试点击"""
        if not self.iframe:
            self.log("没有可用的iframe对象", "ERROR")
            return

        self.log("=" * 60)
        self.log("测试在 iframe 内点击", "INFO")
        self.log("=" * 60)

        # 策略1: 点击第一个treeitem
        self.log("\n策略1: 尝试点击第一个 treeitem", "INFO")
        try:
            first_treeitem = await self.iframe.query_selector('[role="treeitem"]')  # 添加await
            if first_treeitem:
                await first_treeitem.click()
                self.log("✓ 成功点击第一个treeitem", "SUCCESS")
                await self.page.wait_for_timeout(1000)
            else:
                self.log("未找到treeitem", "WARN")
        except Exception as e:
            self.log(f"点击失败: {e}", "ERROR")

        # 截图看效果
        await self.page.screenshot(path="screenshot_after_click.png")
        self.log("已保存截图: screenshot_after_click.png", "INFO")

    async def build_iframe_ref_mapping(self):
        """为iframe内的元素构建引用映射"""
        if not self.iframe:
            return

        self.log("=" * 60)
        self.log("构建 iframe 内元素引用映射", "INFO")
        self.log("=" * 60)

        refs = await self.iframe.evaluate("""
            () => {
                const results = [];
                let refId = 1;

                const interactiveRoles = [
                    'button', 'link', 'textbox', 'checkbox', 'radio',
                    'combobox', 'listbox', 'menuitem', 'treeitem', 'tab'
                ];

                document.querySelectorAll('*').forEach(el => {
                    const role = el.getAttribute('role');
                    const tagName = el.tagName.toLowerCase();

                    let isInteractive = interactiveRoles.includes(role);
                    if (!isInteractive) {
                        if (['button', 'a', 'input', 'select', 'textarea'].includes(tagName)) {
                            isInteractive = true;
                        }
                    }

                    if (isInteractive) {
                        const text = el.textContent?.trim().substring(0, 50) || '';
                        const ariaLabel = el.getAttribute('aria-label') || '';
                        const title = el.getAttribute('title') || '';

                        if (text || ariaLabel || title) {
                            results.push({
                                ref: `e${refId++}`,
                                role: role || tagName,
                                name: ariaLabel || title || text,
                                tagName: tagName,
                                visible: el.offsetParent !== null,
                            });
                        }
                    }
                });

                return results.slice(0, 30);
            }
        """)

        if refs:
            self.log(f"捕获了 {len(refs)} 个可交互元素", "SUCCESS")
            print("\n引用映射表 (iframe内):")
            print("-" * 70)
            for ref_el in refs:
                visible = "✓" if ref_el['visible'] else "✗"
                print(f"{visible} {ref_el['ref']:>4} = role='{ref_el['role']}', name='{ref_el['name'][:40]}'")

            # 保存
            with open("iframe_ref_mapping.json", "w", encoding="utf-8") as f:
                json.dump(refs, f, ensure_ascii=False, indent=2)
            self.log("\n已保存到: iframe_ref_mapping.json", "INFO")

            # 特别标注
            print("\n★ 包含'根'或'预览'的元素:")
            for ref_el in refs:
                if '根' in ref_el['name'] or '预览' in ref_el['name']:
                    print(f"   {ref_el['ref']} → {ref_el['name']}")
        else:
            self.log("未捕获到可交互元素", "WARN")


async def main():
    """主流程"""
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,
            slow_mo=500,
        )

        context = await browser.new_context(
            viewport={"width": 1920, "height": 1080},
            ignore_https_errors=True,
        )

        global page
        page = await context.new_page()
        debugger = IframeTreeDebugger(page)

        try:
            # 步骤1: 自动登录并进入
            await debugger.auto_login_and_enter()

            # 步骤2: 获取iframe
            iframe = await debugger.get_target_iframe()

            if not iframe:
                debugger.log("无法获取iframe，退出", "ERROR")
                await browser.close()
                return

            # 步骤3: 分析iframe内容
            await debugger.analyze_iframe_content()

            # 步骤4: 构建引用映射
            await debugger.build_iframe_ref_mapping()

            # 步骤5: 测试点击
            await debugger.test_click_in_iframe()

            # 完成
            debugger.log("\n" + "=" * 60, "INFO")
            debugger.log("分析完成！", "SUCCESS")
            debugger.log("=" * 60, "INFO")
            debugger.log("\n请查看:", "INFO")
            debugger.log("  - screenshot_after_click.png (点击后的截图)", "INFO")
            debugger.log("  - iframe_ref_mapping.json (iframe内元素引用)", "INFO")

            print("\n浏览器将保持打开30秒，你可以手动检查...")
            await page.wait_for_timeout(30000)

        except Exception as e:
            debugger.log(f"执行出错: {e}", "ERROR")
            import traceback
            traceback.print_exc()
            await page.screenshot(path="screenshot_error.png")

        finally:
            await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
