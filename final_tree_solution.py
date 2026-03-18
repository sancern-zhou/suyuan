"""
最终解决方案：针对 Element UI Menu 的点击脚本

关键发现：
1. 树形控件是 Element UI 的 Menu 组件
2. 菜单折叠时，文本隐藏，只有图标可见
3. 正确做法：点击 li 元素，而不是内部的 span
"""

import asyncio
from playwright.async_api import async_playwright

BASE_URL = "http://10.10.10.158"
USERNAME = "cdzhuanyong"
PASSWORD = "cdsz@429"


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False, slow_mo=500)
        context = await browser.new_context(viewport={"width": 1920, "height": 1080}, ignore_https_errors=True)
        page = await context.new_page()

        print("=" * 70)
        print("  树形控件点击测试 - 最终方案")
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

            # ========== 方案1: 点击 li 元素（推荐） ==========
            print("\n" + "=" * 70)
            print("方案1: 点击 li.el-menu-item 元素")
            print("=" * 70)

            # 点击"轮巡分组"
            print("\n尝试点击: 轮巡分组")

            # 策略A: 使用CSS选择器直接点击 li
            try:
                # 方式1: 通过索引（第二个菜单项）
                await iframe.locator("li.el-menu-item").nth(1).click()
                print("✓ 成功点击第2个菜单项（通过索引）")
                await page.wait_for_timeout(2000)
            except Exception as e:
                print(f"✗ 失败: {e}")

            # 截图
            await page.screenshot(path="solution1_test.png")
            print("已保存: solution1_test.png")

            # ========== 方案2: 使用 force 强制点击 ==========
            print("\n" + "=" * 70)
            print("方案2: 强制点击隐藏的文本元素")
            print("=" * 70)

            try:
                # 即使不可见也强制点击
                await iframe.get_by_text("轮巡分组").click(force=True)
                print("✓ 成功强制点击")
                await page.wait_for_timeout(2000)
            except Exception as e:
                print(f"✗ 失败: {e}")

            # ========== 方案3: 点击父元素 li ==========
            print("\n" + "=" * 70)
            print("方案3: 点击文本的父元素 li")
            print("=" * 70)

            try:
                # 找到包含"轮巡分组"的元素，然后找到它的父 li
                text_element = iframe.get_by_text("轮巡分组")
                # 使用 XPath 找父元素
                await iframe.locator("//*[contains(text(), '轮巡分组')]/ancestor::li").click()
                print("✓ 成功点击父元素 li")
                await page.wait_for_timeout(2000)
            except Exception as e:
                print(f"✗ 失败: {e}")

            # ========== 方案4: 通过图标点击 ==========
            print("\n" + "=" * 70)
            print("方案4: 点击图标元素")
            print("=" * 70)

            try:
                # 点击轮巡分组的图标
                await iframe.locator("i.d-nav-inspection_group").click()
                print("✓ 成功点击图标")
                await page.wait_for_timeout(2000)
            except Exception as e:
                print(f"✗ 失败: {e}")

            # ========== 最终推荐方案 ==========
            print("\n" + "=" * 70)
            print("最终推荐方案")
            print("=" * 70)

            print("""
推荐方案（按优先级）:

方案A（最稳定）:
    iframe.locator("li.el-menu-item").nth(1).click()
    优点: 通过索引，不依赖文本
    缺点: 需要知道菜单项的索引

方案B（语义化）:
    iframe.locator("li.el-menu-item").filter(has_text="轮巡分组").click()
    优点: 通过文本过滤，语义清晰
    缺点: 需要确保文本唯一

方案C（通过图标）:
    iframe.locator("i.d-nav-inspection_group").click()
    优点: 图标通常唯一且可见
    缺点: 需要提前知道图标的 class

方案D（强制点击）:
    iframe.get_by_text("轮巡分组").click(force=True)
    优点: 简单直接
    缺点: 可能触发意外的UI行为
            """)

            # 测试推荐方案
            print("\n测试方案B（推荐）:")
            try:
                await iframe.locator("li.el-menu-item").filter(has_text="轮巡分组").click()
                print("✓ 成功！使用 filter + has_text 策略")
                await page.wait_for_timeout(2000)
            except Exception as e:
                print(f"✗ 失败: {e}")

            await page.screenshot(path="final_solution_test.png")
            print("\n已保存: final_solution_test.png")

            print("\n" + "=" * 70)
            print("测试完成！浏览器保持打开30秒...")
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
