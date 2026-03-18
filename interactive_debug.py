"""
交互式调试 - 不用写脚本，直接在控制台测试

运行方式：
    python -i interactive_debug.py

然后你可以在控制台直接输入命令测试！
"""

from playwright.async_api import async_playwright
import asyncio

# 配置
BASE_URL = "http://10.10.10.158"
USERNAME = "cdzhuanyong"
PASSWORD = "cdsz@429"

# 全局变量
browser = None
page = None
iframe = None


async def init():
    """初始化浏览器并登录"""
    global browser, page, iframe

    p = await async_playwright().start()
    browser = await p.chromium.launch(headless=False, slow_mo=500)
    context = await browser.new_context(viewport={"width": 1920, "height": 1080})
    page = await context.new_page()

    # 登录
    await page.goto(BASE_URL)
    await page.wait_for_timeout(1000)
    await page.fill('input[type="text"]', USERNAME)
    await page.wait_for_timeout(500)
    await page.fill('input[type="password"]', PASSWORD)
    await page.wait_for_timeout(500)
    await page.click('button[type="submit"]')
    await page.wait_for_timeout(2000)

    # 点击实时预览
    await page.get_by_text("实时预览").first.click()
    await page.wait_for_timeout(3000)

    # 获取iframe
    iframe = page.frame(name="vms_010100")

    print("✓ 初始化完成！")
    print("\n可用的命令：")
    print("  await screenshot()           # 截图")
    print("  await test_selector('xxx')   # 测试选择器")
    print("  await click_text('xxx')       # 点击文本")
    print("  await list_left_elements()    # 列出左侧元素")
    print("  await js_click('selector')    # JavaScript点击")
    print("  await find_expand_buttons()   # 查找展开按钮")
    print("\n示例：")
    print("  await test_selector('li.el-menu-item')")
    print("  await click_text('资源视图')")
    print("  await js_click('li.el-menu--colloase-btn')")


async def screenshot(filename="debug.png"):
    """截图"""
    await page.screenshot(path=filename)
    print(f"✓ 已保存: {filename}")


async def test_selector(selector):
    """测试选择器"""
    if not iframe:
        print("✗ iframe 未初始化")
        return

    try:
        count = await iframe.locator(selector).count()
        print(f"✓ 找到 {count} 个元素: '{selector}'")

        if count > 0:
            # 显示前3个元素的信息
            for i in range(min(count, 3)):
                el = iframe.locator(selector).nth(i)
                text = await el.text_content()
                visible = await el.is_visible()
                print(f"  [{i}] text='{text[:50]}', visible={visible}")
    except Exception as e:
        print(f"✗ 错误: {e}")


async def click_text(text):
    """点击包含文本的元素"""
    if not iframe:
        print("✗ iframe 未初始化")
        return

    try:
        result = await iframe.evaluate(f"""
            (text) => {{
                const allElements = document.querySelectorAll('*');
                for (const el of allElements) {{
                    if (el.textContent.includes(text)) {{
                        el.click();
                        return {{success: true, clicked: true}};
                    }}
                }}
                return {{success: false, clicked: false}};
            }}
        """, text)

        if result['success']:
            print(f"✓ 已点击包含'{text}'的元素")
        else:
            print(f"✗ 未找到包含'{text}'的元素")
    except Exception as e:
        print(f"✗ 错误: {e}")


async def list_left_elements():
    """列出左侧所有元素"""
    if not iframe:
        print("✗ iframe 未初始化")
        return

    elements = await iframe.evaluate("""
        () => {
            const results = [];
            const allElements = document.querySelectorAll('*');

            allElements.forEach(el => {
                const rect = el.getBoundingClientRect();
                const text = (el.textContent || '').trim();

                if (rect.x < 250 && rect.width > 0 && rect.height > 0) {
                    if (text && text.length > 0 && text.length < 80) {
                        results.push({
                            tag: el.tagName,
                            text: text,
                            class: el.className,
                            x: Math.round(rect.x),
                            y: Math.round(rect.y),
                        });
                    }
                }
            });

            return results.slice(0, 20);
        }
    """)

    print(f"\n找到 {len(elements)} 个左侧元素:")
    for idx, el in enumerate(elements):
        print(f"  [{idx:2d}] <{el['tag']:4s}> ({el['x']:3d}, {el['y']:3d}) '{el['text'][:40]}'")


async def js_click(selector):
    """JavaScript 点击"""
    if not iframe:
        print("✗ iframe 未初始化")
        return

    try:
        result = await iframe.evaluate(f"""
            (selector) => {{
                const el = document.querySelector(selector);
                if (el) {{
                    el.click();
                    return {{success: true}};
                }}
                return {{success: false}};
            }}
        """, selector)

        if result['success']:
            print(f"✓ 已点击: {selector}")
        else:
            print(f"✗ 未找到: {selector}")
    except Exception as e:
        print(f"✗ 错误: {e}")


async def find_expand_buttons():
    """查找展开按钮"""
    if not iframe:
        print("✗ iframe 未初始化")
        return

    buttons = await iframe.evaluate("""
        () => {
            const results = [];
            const allElements = document.querySelectorAll('*');

            allElements.forEach(el => {
                const rect = el.getBoundingClientRect();
                const text = (el.textContent || '').trim();

                if (rect.x < 250 && rect.width > 0 && rect.height > 0) {
                    const isSmall = rect.width < 50 && rect.height < 50;
                    const hasIcon = /icon|arrow|expand|collapse|toggle|switch|caret|chevron/i.test(el.className || '');
                    const isSymbol = /^[>▼▶▲+−∨∧]+$/.test(text);

                    if (isSmall && (hasIcon || isSymbol)) {
                        results.push({
                            tag: el.tagName,
                            text: text,
                            class: el.className,
                            x: Math.round(rect.x),
                            y: Math.round(rect.y),
                        });
                    }
                }
            });

            return results;
        }
    """)

    print(f"\n找到 {len(buttons)} 个可能的展开按钮:")
    for idx, btn in enumerate(buttons):
        print(f"  [{idx}] <{btn['tag']}> ({btn['x']}, {btn['y']}) '{btn['text']}' class='{btn['class'][:40]}'")


async def auto_play():
    """自动执行完整流程"""
    print("\n开始自动执行...")

    # 1. 展开左侧菜单
    print("\n[1] 尝试展开左侧菜单...")
    await js_click('li.el-menu--colloase-btn')
    await page.wait_for_timeout(2000)
    await screenshot("step1_menu_expanded.png")

    # 2. 点击资源视图
    print("\n[2] 点击'资源视图'...")
    await click_text('资源视图')
    await page.wait_for_timeout(2000)
    await screenshot("step2_resource_view.png")

    # 3. 列出左侧元素
    print("\n[3] 列出左侧元素...")
    await list_left_elements()

    # 4. 查找展开按钮
    print("\n[4] 查找展开按钮...")
    await find_expand_buttons()

    print("\n✓ 自动执行完成！")


# 初始化并进入交互模式
async def main():
    await init()
    print("\n" + "=" * 60)
    print("  进入交互式调试模式")
    print("=" * 60)
    print("\n现在你可以直接输入命令测试！")
    print("例如: await screenshot()")
    print("\n输入 help() 查看所有可用命令")


# 启动
if __name__ == "__main__":
    asyncio.run(main())

    # 保持浏览器打开
    print("\n浏览器保持打开。按 Ctrl+C 退出...")
    try:
        asyncio.get_event_loop().run_forever()
    except KeyboardInterrupt:
        print("\n退出...")
