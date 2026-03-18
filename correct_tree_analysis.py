"""
完整的自动化流程：登录 → 选择播放器 → 查找树形控件

1. 登录
2. 进入实时预览
3. 选择"内置H5播放器"
4. 等待进入监控界面
5. 分析并找到树形控件
"""

import asyncio
from playwright.async_api import async_playwright
from datetime import datetime

BASE_URL = "http://10.10.10.158"
USERNAME = "cdzhuanyong"
PASSWORD = "cdsz@429"


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False, slow_mo=800)
        context = await browser.new_context(viewport={"width": 1920, "height": 1080}, ignore_https_errors=True)
        page = await context.new_page()

        print("=" * 70)
        print("  完整流程：登录 → 选择播放器 → 查找树形控件")
        print("=" * 70)

        try:
            # ========== 步骤1: 登录 ==========
            print("\n[步骤1] 登录...")
            await page.goto(BASE_URL, timeout=30000)
            await page.wait_for_load_state("networkidle")

            await page.fill('input[type="text"], input[type="username"]', USERNAME)
            await page.wait_for_timeout(500)
            await page.fill('input[type="password"]', PASSWORD)
            await page.wait_for_timeout(500)
            await page.click('button[type="submit"], button:has-text("登录")')
            await page.wait_for_timeout(2000)
            print("✓ 登录成功")

            # ========== 步骤2: 进入实时预览 ==========
            print("\n[步骤2] 进入'实时预览'...")
            await page.get_by_text("实时预览").first.click()
            await page.wait_for_timeout(3000)
            print("✓ 已点击'实时预览'")

            # 截图看当前状态
            await page.screenshot(path="step2_after_preview.png")

            # ========== 步骤3: 选择播放器（如果出现选择界面） ==========
            print("\n[步骤3] 检查是否需要选择播放器...")

            # 等待一下，看看是否有播放器选择界面
            await page.wait_for_timeout(2000)

            # 检查是否有播放器选择界面
            has_player_selector = False

            try:
                # 检查是否有"内置H5播放器"的选项
                h5_player = page.get_by_text("内置H5播放器")
                count = await h5_player.count()

                if count > 0:
                    has_player_selector = True
                    print("⚠ 检测到播放器选择界面")
                    print("→ 点击'内置H5播放器'...")

                    # 点击内置H5播放器
                    await h5_player.first.click()
                    await page.wait_for_timeout(2000)

                    # 可能还需要点击"确认"或"使用H5"之类的按钮
                    confirm_button = page.get_by_text("使用H5", "确认", "立即使用")
                    confirm_count = await confirm_button.count()

                    if confirm_count > 0:
                        await confirm_button.first.click()
                        print("✓ 已确认使用H5播放器")

                    # 等待监控界面加载
                    print("等待监控界面加载（可能需要10-20秒）...")
                    await page.wait_for_timeout(10000)

            except Exception as e:
                print(f"检查播放器选择时出错: {e}")

            if not has_player_selector:
                print("✓ 直接进入监控界面（无需选择播放器）")

            await page.screenshot(path="step3_after_player.png")

            # ========== 步骤4: 进入iframe并分析 ==========
            print("\n[步骤4] 进入iframe并分析...")
            iframe = page.frame(name="vms_010100")

            if not iframe:
                print("✗ 无法获取iframe")
                print("\n可能的原因：")
                print("1. iframe还未加载完成，请等待")
                print("2. iframe的name不是'vms_010100'")
                print("\n当前页面URL:", page.url)

                # 列出所有iframe
                print("\n尝试查找所有iframe:")
                iframes = await page.query_selector_all("iframe")
                print(f"找到 {len(iframes)} 个iframe")
                for idx, f in enumerate(iframes):
                    name = await f.get_attribute("name") or ""
                    id_attr = await f.get_attribute("id") or ""
                    src = await f.get_attribute("src") or ""
                    print(f"  [{idx}] name='{name}', id='{id_attr}', src='{src[:60]}'")

                await page.wait_for_timeout(30000)
                return

            print("✓ iframe获取成功")

            # 等待iframe内容加载
            print("等待iframe内容加载...")
            await page.wait_for_timeout(5000)

            # ========== 步骤5: 全面分析iframe内容 ==========
            print("\n[步骤5] 全面分析iframe内容...")

            # 5.1 检查页面标题和基本信息
            page_info = await iframe.evaluate("""
                () => {
                    return {
                        title: document.title,
                        url: window.location.href,
                        bodyClass: document.body.className,
                        totalElements: document.querySelectorAll('*').length,
                    };
                }
            """)

            print(f"\n页面信息:")
            print(f"  标题: {page_info['title']}")
            print(f"  URL: {page_info['url']}")
            print(f"  总元素数: {page_info['totalElements']}")

            # 5.2 查找左侧区域的所有可见元素
            print("\n左侧区域元素 (x < 250):")
            left_elements = await iframe.evaluate("""
                () => {
                    const results = [];
                    const allElements = document.querySelectorAll('*');

                    allElements.forEach(el => {
                        const rect = el.getBoundingClientRect();
                        const text = (el.textContent || '').trim();

                        // 左侧区域，可见，有文本
                        if (rect.x < 250 && rect.width > 0 && rect.height > 0 && rect.height < 100) {
                            if (text && text.length > 0 && text.length < 80 && el.children.length < 5) {
                                results.push({
                                    tagName: el.tagName,
                                    text: text,
                                    className: el.className,
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
                        const key = `${el.x}-${el.y}-${el.text.substring(0, 20)}`;
                        if (!seen.has(key)) {
                            seen.add(key);
                            unique.push(el);
                        }
                    });

                    return unique.sort((a, b) => a.y - b.y).slice(0, 30);
                }
            """)

            print(f"\n找到 {len(left_elements)} 个左侧元素:")
            for idx, el in enumerate(left_elements):
                print(f"  [{idx:2d}] <{el['tagName']:4s}> pos=({el['x']:3d}, {el['y']:3d}), "
                      f"text='{el['text'][:30]}'")

            # 5.3 查找可能的展开按钮
            print("\n可能的展开按钮:")
            expand_buttons = await iframe.evaluate("""
                () => {
                    const results = [];
                    const allElements = document.querySelectorAll('*');

                    allElements.forEach(el => {
                        const rect = el.getBoundingClientRect();
                        const text = (el.textContent || '').trim();

                        // 左侧区域
                        if (rect.x < 250 && rect.width > 0 && rect.height > 0) {
                            // 查找特征
                            const hasIconClass = /icon|arrow|expand|collapse|toggle|switch|caret|triangle|chevron/i.test(el.className || '');
                            const isSymbol = text.length <= 3 && /^[>▼▶▲+−∨∧◢◣✓✗]+$/.test(text);
                            const hasAriaExpanded = el.hasAttribute('aria-expanded');
                            const isSmallElement = rect.width < 30 && rect.height < 30;

                            if ((hasIconClass || isSymbol || hasAriaExpanded) && isSmallElement) {
                                results.push({
                                    tagName: el.tagName,
                                    text: text,
                                    className: el.className,
                                    ariaExpanded: el.getAttribute('aria-expanded'),
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

            if expand_buttons:
                print(f"找到 {len(expand_buttons)} 个可能的展开按钮:")
                for idx, btn in enumerate(expand_buttons):
                    aria = btn.get('ariaExpanded') or 'N/A'
                    print(f"  [{idx}] <{btn['tagName']}> pos=({btn['x']}, {btn['y']}), "
                          f"text='{btn['text']}', aria-expanded={aria}, "
                          f"class='{btn['className'][:40]}'")
            else:
                print("未找到明显的展开按钮")

            # 5.4 导出左侧区域的HTML
            print("\n导出左侧区域HTML...")
            left_html = await iframe.evaluate("""
                () => {
                    // 找到左侧容器
                    const candidates = [
                        document.querySelector('.h-page-menu'),
                        document.querySelector('nav'),
                        document.querySelector('[class*="sidebar"]'),
                        document.querySelector('[class*="left"]'),
                        document.querySelector('[class*="tree"]'),
                    ];

                    for (const candidate of candidates) {
                        if (candidate) {
                            return {
                                html: candidate.outerHTML.substring(0, 5000),
                                className: candidate.className,
                                tagName: candidate.tagName,
                            };
                        }
                    }

                    return {html: '未找到左侧容器', className: '', tagName: ''};
                }
            """)

            print(f"\n左侧容器: <{left_html['tagName']}> class='{left_html['className']}'")

            with open("final_left_menu.html", "w", encoding="utf-8") as f:
                f.write(left_html['html'])
            print("已保存: final_left_menu.html")

            # ========== 完成截图 ==========
            await page.screenshot(path="final_screenshot.png", full_page=True)
            print("\n✓ 已保存完整页面截图: final_screenshot.png")

            print("\n" + "=" * 70)
            print("分析完成！浏览器保持打开30秒，你可以手动检查...")
            print("=" * 70)
            await page.wait_for_timeout(30000)

        except Exception as e:
            print(f"\n✗ 执行出错: {e}")
            import traceback
            traceback.print_exc()
            await page.screenshot(path="error.png")

        finally:
            await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
