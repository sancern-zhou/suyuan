"""
展开左侧菜单并查找树形控件

步骤：
1. 点击左侧的展开按钮（从折叠状态展开）
2. 等待菜单展开动画完成
3. 分析展开后的菜单结构
4. 找到树形控件的展开按钮
"""

import asyncio
from playwright.async_api import async_playwright
from datetime import datetime

BASE_URL = "http://10.10.10.158"
USERNAME = "cdzhuanyong"
PASSWORD = "cdsz@429"


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False, slow_mo=500)
        context = await browser.new_context(viewport={"width": 1920, "height": 1080}, ignore_https_errors=True)
        page = await context.new_page()

        print("=" * 70)
        print("  展开左侧菜单并查找树形控件")
        print("=" * 70)

        try:
            # 登录
            print("\n[1] 登录...")
            await page.goto(BASE_URL, timeout=30000)
            await page.fill('input[type="text"], input[type="username"]', USERNAME)
            await page.wait_for_timeout(500)
            await page.fill('input[type="password"]', PASSWORD)
            await page.wait_for_timeout(500)
            await page.click('button[type="submit"], button:has-text("登录")')
            await page.wait_for_timeout(2000)

            # 点击实时预览
            print("[2] 点击'实时预览'...")
            await page.get_by_text("实时预览").first.click()
            await page.wait_for_timeout(5000)

            # 获取 iframe
            print("[3] 进入 iframe...")
            iframe = page.frame(name="vms_010100")
            if not iframe:
                print("✗ 无法获取iframe")
                return

            print("✓ iframe 获取成功")

            # ========== 关键：展开左侧菜单 ==========
            print("\n" + "=" * 70)
            print("步骤1: 展开左侧菜单")
            print("=" * 70)

            # 查找展开按钮（可能是 ☰ 或类似图标）
            print("\n查找左侧菜单展开按钮...")

            # 尝试1: 查找汉堡菜单图标
            try:
                # Element UI的展开按钮通常在菜单顶部
                expand_button = iframe.locator("li.el-menu--colloase-btn, .el-menu--collapse-btn, [class*='expand']")
                count = await expand_button.count()
                print(f"找到 {count} 个可能的展开按钮")

                if count > 0:
                    print("点击展开按钮...")
                    await expand_button.first.click()
                    print("✓ 已点击展开按钮")
                    await page.wait_for_timeout(2000)  # 等待动画
                else:
                    print("未找到展开按钮，尝试其他方式...")

                    # 尝试2: 点击菜单栏边缘
                    await page.mouse.click(30, 100)  # 点击左侧边缘
                    await page.wait_for_timeout(2000)

            except Exception as e:
                print(f"点击展开按钮失败: {e}")

            # 截图看效果
            await page.screenshot(path="after_menu_expand.png")
            print("\n已保存截图: after_menu_expand.png")

            # ========== 步骤2: 分析展开后的菜单 ==========
            print("\n" + "=" * 70)
            print("步骤2: 分析展开后的菜单结构")
            print("=" * 70)

            # 查找所有可见的菜单项
            menu_items = await iframe.evaluate("""
                () => {
                    const results = [];
                    const allElements = document.querySelectorAll('*');

                    allElements.forEach(el => {
                        const rect = el.getBoundingClientRect();
                        const text = (el.textContent || '').trim();

                        // 只看左侧区域（x < 200）的可见元素
                        if (rect.x < 200 && rect.width > 0 && rect.height > 0) {
                            if (text && text.length > 0 && text.length < 100) {
                                // 只取文本在前面的元素
                                if (el.children.length < 3) {
                                    results.push({
                                        tagName: el.tagName,
                                        text: text,
                                        className: el.className,
                                        id: el.id,
                                        x: Math.round(rect.x),
                                        y: Math.round(rect.y),
                                        width: Math.round(rect.width),
                                        height: Math.round(rect.height),
                                        hasChildren: el.children.length > 0,
                                    });
                                }
                            }
                        }
                    });

                    // 去重并排序（按y坐标）
                    const unique = [];
                    const seen = new Set();
                    results.forEach(el => {
                        const key = `${el.x}-${el.y}-${el.text}`;
                        if (!seen.has(key) && el.text.length < 50) {
                            seen.add(key);
                            unique.push(el);
                        }
                    });

                    return unique.sort((a, b) => a.y - b.y).slice(0, 20);
                }
            """)

            print(f"\n找到 {len(menu_items)} 个左侧菜单元素:")
            for idx, item in enumerate(menu_items):
                print(f"  [{idx}] <{item['tagName']}> pos=({item['x']}, {item['y']}), "
                      f"text='{item['text'][:40]}'")

            # ========== 步骤3: 查找展开/折叠按钮 ==========
            print("\n" + "=" * 70)
            print("步骤3: 查找树形展开按钮（>符号等）")
            print("=" * 70)

            # 在左侧区域查找
            expand_buttons = await iframe.evaluate("""
                () => {
                    const results = [];
                    const allElements = document.querySelectorAll('*');

                    allElements.forEach(el => {
                        const rect = el.getBoundingClientRect();

                        // 只看左侧区域
                        if (rect.x < 200 && rect.width > 0 && rect.height > 0) {
                            // 查找可能作为展开按钮的特征
                            const hasIconClass = /icon|arrow|expand|collapse|toggle|switch/i.test(el.className || '');
                            const text = (el.textContent || '').trim();
                            const isSymbol = text.length <= 3 && /^[>▼▶▲+−∨∧◢◣]+$/.test(text);
                            const hasAriaExpanded = el.hasAttribute('aria-expanded');

                            if (hasIconClass || isSymbol || hasAriaExpanded) {
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
                print(f"\n找到 {len(expand_buttons)} 个可能的展开按钮:")
                for idx, btn in enumerate(expand_buttons):
                    aria = btn.get('ariaExpanded') or ''
                    print(f"  [{idx}] <{btn['tagName']}> pos=({btn['x']}, {btn['y']}), "
                          f"text='{btn['text']}', class='{btn['className'][:40]}', aria-expanded={aria}")
            else:
                print("\n未找到明显的展开按钮")

            # ========== 步骤4: 导出左侧菜单HTML ==========
            print("\n" + "=" * 70)
            print("步骤4: 导出左侧菜单HTML")
            print("=" * 70)

            left_menu_html = await iframe.evaluate("""
                () => {
                    // 找到左侧菜单容器
                    const menu = document.querySelector('.h-page-menu, nav[class*="menu"], [class*="sidebar"]');
                    if (menu) {
                        return menu.outerHTML.substring(0, 3000);
                    }
                    return '未找到菜单容器';
                }
            """)

            print("\n左侧菜单HTML:")
            print("-" * 70)
            print(left_menu_html)
            print("-" * 70)

            with open("left_menu_html.html", "w", encoding="utf-8") as f:
                f.write(left_menu_html)
            print("\n已保存到: left_menu_html.html")

            print("\n" + "=" * 70)
            print("分析完成！浏览器保持打开30秒...")
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
