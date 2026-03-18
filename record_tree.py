# -*- coding: utf-8 -*-
"""
录制树形控件操作脚本

使用方法：
1. 运行此脚本：python record_tree.py
2. 在打开的浏览器中手动操作（登录、点击实时预览、展开菜单、点击资源视图、展开监控点）
3. 操作完成后，按 Ctrl+C 结束
"""

from playwright.sync_api import sync_playwright, Playwright
import sys

def run(playwright: Playwright):
    print("=" * 70)
    print("  树形控件录制工具")
    print("=" * 70)
    print("\n正在启动浏览器...\n")

    browser = playwright.chromium.launch(
        headless=False,  # 有头模式，可以看到浏览器
        slow_mo=500,     # 每步操作延迟500ms，方便观察
        args=['--ignore-certificate-errors', '--start-maximized']  # 忽略证书，最大化窗口
    )

    context = browser.new_context(
        viewport={"width": 1920, "height": 1080},
        ignore_https_errors=True  # 忽略HTTPS错误
    )

    page = context.new_page()

    # 导航到网站
    print("正在访问网站...")
    page.goto("http://10.10.10.158/")

    print("\n" + "=" * 70)
    print("  浏览器已就绪！")
    print("=" * 70)
    print("\n请在浏览器中进行以下操作：")
    print("")
    print("步骤 1: 输入用户名和密码")
    print("        - 用户名: cdzhuanyong")
    print("        - 密码: cdsz@429")
    print("")
    print("步骤 2: 点击登录按钮")
    print("")
    print("步骤 3: 等待页面加载完成")
    print("")
    print("步骤 4: 点击'实时预览'菜单项")
    print("")
    print("步骤 5: 等待页面加载（可能会看到监控画面）")
    print("")
    print("步骤 6: 点击左侧的菜单展开按钮（左上角的三横线图标☰）")
    print("")
    print("步骤 7: 等待菜单展开（应该显示'资源视图'、'轮巡分组'等文字）")
    print("")
    print("步骤 8: 点击'资源视图'")
    print("")
    print("步骤 9: 查找并点击'监控点'左侧的展开按钮（> 或 ◢ 符号）")
    print("")
    print("步骤 10: 如果还有'根节点'，也点击其展开按钮")
    print("")
    print("完成后，按 Ctrl+C 结束录制")
    print("\n" + "=" * 70)
    print("")

    try:
        # page.pause() 会保持浏览器打开，等待你的操作
        page.pause()

    except KeyboardInterrupt:
        print("\n" + "=" * 70)
        print("  录制结束")
        print("=" * 70)
        print("\n请告诉我你执行了哪些操作，我会帮你生成对应的自动化代码！")
        print("\n你可以：")
        print("1. 截图保存，然后给我看")
        print("2. 告诉我每一步是如何操作的")
        print("3. 告诉我遇到了什么问题")
        print("")

    finally:
        print("\n正在关闭浏览器...")
        context.close()
        browser.close()

if __name__ == "__main__":
    print("""
╔════════════════════════════════════════════════════════════╗
║            树形控件操作录制工具                         ║
╚════════════════════════════════════════════════════════════╝

使用说明：
1. 脚本会自动打开Chrome浏览器
2. 你在浏览器中手动操作整个流程
3. 操作完成后按 Ctrl+C
4. 告诉我你的操作，我帮你生成自动化代码

注意事项：
- 浏览器会保持打开状态
- 每个操作之间请等待1-2秒，确保页面加载完成
- 如果某个操作失败，请告诉我在哪一步

    """)

    with sync_playwright() as playwright:
        run(playwright)
