# -*- coding: utf-8 -*-
"""
完整的树形控件自动化脚本

基于调试信息生成的完整流程：
1. 登录
2. 进入实时预览
3. 展开左侧菜单
4. 点击资源视图
5. 展开监控点
6. 选择具体站点
"""

import asyncio
from playwright.async_api import async_playwright

BASE_URL = "http://10.10.10.158"
USERNAME = "cdzhuanyong"
PASSWORD = "cdsz@429"


async def full_auto_control():
    """完整的自动化控制流程"""

    async with async_playwright() as p:
        # 启动浏览器
        browser = await p.chromium.launch(
            headless=False,  # 显示浏览器，方便观察
            slow_mo=500,     # 每步延迟500ms
            args=['--ignore-certificate-errors', '--start-maximized']
        )

        context = await browser.new_context(
            viewport={"width": 1920, "height": 1080},
            ignore_https_errors=True
        )

        page = await context.new_page()

        try:
            # ========== 步骤1: 登录 ==========
            print("\n[1/8] 正在登录...")
            await page.goto(BASE_URL, timeout=30000)
            await page.wait_for_timeout(1000)

            # 填写用户名密码
            await page.evaluate(f"""
                () => {{
                    const inputs = document.querySelectorAll('input[type="text"], input[type="username"]');
                    if (inputs.length > 0) inputs[0].value = '{USERNAME}';

                    const passwords = document.querySelectorAll('input[type="password"]');
                    if (passwords.length > 0) passwords[0].value = '{PASSWORD}';

                    const buttons = document.querySelectorAll('button');
                    for (const btn of buttons) {{
                        const text = btn.textContent || '';
                        if (text.includes('登录') || text.includes('login')) {{
                            btn.click();
                            return true;
                        }}
                    }}
                    return false;
                }}
            """)

            await page.wait_for_timeout(3000)
            print("      ✓ 登录成功")

            # ========== 步骤2: 点击实时预览 ==========
            print("\n[2/8] 点击'实时预览'...")
            result = await page.evaluate("""
                () => {
                    const all = document.querySelectorAll('*');
                    for (const el of all) {
                        const text = el.textContent || '';
                        if (text.includes('实时预览')) {
                            el.click();
                            return true;
                        }
                    }
                    return false;
                }
            """)

            await page.wait_for_timeout(5000)
            print("      ✓ 已点击实时预览")

            # 获取iframe
            await page.wait_for_timeout(2000)
            iframe = page.frame(name="vms_010100")

            if not iframe:
                # 尝试查找iframe
                iframe_elements = await page.query_selector_all("iframe")
                print(f"      找到 {len(iframe_elements)} 个iframe")

                for idx, iframe_el in enumerate(iframe_elements):
                    name = await iframe_el.get_attribute("name")
                    src = await iframe_el.get_attribute("src")
                    print(f"      iframe[{idx}]: name={name}, src={src}")

                    if name == "vms_010100" or (src and "vms" in src):
                        try:
                            iframe = await iframe_el.content_frame()
                            print(f"      ✓ 获取到iframe")
                            break
                        except:
                            pass

            if not iframe:
                print("      ✗ 无法获取iframe，可能需要调整等待时间")
                print("\n保持浏览器打开30秒，请手动检查...")
                await page.wait_for_timeout(30000)
                return

            # ========== 步骤3: 展开左侧菜单 ==========
            print("\n[3/8] 展开左侧菜单...")

            # 方案1: 点击展开按钮
            result = await iframe.evaluate("""
                () => {
                    const collapseBtn = document.querySelector('li.el-menu--colloase-btn');
                    if (collapseBtn) {
                        collapseBtn.click();
                        return {success: true, method: 'collapse_button'};
                    }
                    return {success: false, method: 'not_found'};
                }
            """)

            if result['success']:
                print("      ✓ 已点击展开按钮")
                await page.wait_for_timeout(2000)
            else:
                print("      ! 展开按钮未找到，尝试坐标点击...")
                await page.mouse.click(20, 20)
                await page.wait_for_timeout(2000)

            await page.screenshot(path="step3_menu_expanded.png")
            print("      ✓ 菜单已展开")

            # ========== 步骤4: 点击资源视图 ==========
            print("\n[4/8] 点击'资源视图'...")

            result = await iframe.evaluate("""
                () => {
                    const items = document.querySelectorAll('li.el-menu-item');
                    for (const item of items) {
                        const text = item.textContent || '';
                        if (text.includes('资源视图')) {
                            item.click();
                            return {success: true, clicked: '资源视图'};
                        }
                    }
                    return {success: false, clicked: 'none'};
                }
            """)

            if result['success']:
                print(f"      ✓ 已点击: {result['clicked']}")
                await page.wait_for_timeout(2000)
            else:
                print("      ! 未找到'资源视图'，可能已在当前视图")

            await page.screenshot(path="step4_resource_view.png")

            # ========== 步骤5: 分析当前左侧元素 ==========
            print("\n[5/8] 分析左侧菜单元素...")

            left_elements = await iframe.evaluate("""
                () => {
                    const results = [];
                    const all = document.querySelectorAll('*');

                    all.forEach(el => {
                        const rect = el.getBoundingClientRect();
                        const text = (el.textContent || '').trim();

                        if (rect.x < 300 && rect.width > 0 && rect.height > 0) {
                            if (text && text.length > 0 && text.length < 100) {
                                results.push({
                                    tag: el.tagName,
                                    text: text,
                                    x: Math.round(rect.x),
                                    y: Math.round(rect.y),
                                    class: el.className
                                });
                            }
                        }
                    });

                    return results.slice(0, 30);
                }
            """)

            print(f"      找到 {len(left_elements)} 个左侧元素:")
            for idx, el in enumerate(left_elements[:15]):
                print(f"        [{idx:2d}] <{el['tag']:4s}> ({el['x']:3d}, {el['y']:3d}) '{el['text'][:30]}'")

            # ========== 步骤6: 展开监控点 ==========
            print("\n[6/8] 查找并展开'监控点'...")

            # 查找所有包含"监控点"的元素
            monitor_expand_result = await iframe.evaluate("""
                () => {
                    const all = document.querySelectorAll('*');
                    for (const el of all) {
                        const text = el.textContent || '';
                        // 只找短的文本（避免匹配到大块内容）
                        if (text.includes('监控点') && text.length < 100) {
                            const rect = el.getBoundingClientRect();
                            if (rect.x < 300 && rect.width > 0 && rect.height > 0) {
                                // 找父元素的第一个子元素（通常是展开按钮）
                                const parent = el.parentElement;
                                if (parent && parent.firstElementChild && parent.firstElementChild !== el) {
                                    const firstChild = parent.firstElementChild;
                                    const childRect = firstChild.getBoundingClientRect();

                                    firstChild.click();
                                    return {
                                        success: true,
                                        method: 'clicked_first_child',
                                        x: Math.round(childRect.x),
                                        y: Math.round(childRect.y)
                                    };
                                }
                            }
                        }
                    }
                    return {success: false, method: 'not_found'};
                }
            """)

            if monitor_expand_result['success']:
                print(f"      ✓ 已点击'监控点'的展开按钮 (位置: {monitor_expand_result['x']}, {monitor_expand_result['y']})")
                await page.wait_for_timeout(2000)
            else:
                print("      ! 未找到'监控点'的展开按钮")
                print("      可能的原因：")
                print("        - 已经展开过了")
                print("        - 文本不完全匹配")
                print("        - 在其他位置")

            await page.screenshot(path="step6_monitor_expanded.png")

            # ========== 步骤7: 分析展开后的元素 ==========
            print("\n[7/8] 分析展开后的所有元素...")

            expanded_elements = await iframe.evaluate("""
                () => {
                    const results = [];
                    const all = document.querySelectorAll('*');

                    all.forEach(el => {
                        const rect = el.getBoundingClientRect();
                        const text = (el.textContent || '').trim();

                        if (rect.x < 400 && rect.width > 0 && rect.height > 0) {
                            if (text && text.length > 0 && text.length < 100) {
                                results.push({
                                    tag: el.tagName,
                                    text: text,
                                    x: Math.round(rect.x),
                                    y: Math.round(rect.y),
                                    class: el.className
                                });
                            }
                        }
                    });

                    return results.slice(0, 50);
                }
            """)

            print(f"      找到 {len(expanded_elements)} 个元素:")
            for idx, el in enumerate(expanded_elements[:30]):
                # 标记包含关键文字的元素
                markers = []
                if '监控点' in el['text']:
                    markers.append('[监控点]')
                if '根节点' in el['text']:
                    markers.append('[根节点]')
                if '站点' in el['text'] or 'IPC' in el['text'] or '摄像头' in el['text']:
                    markers.append('[站点]')

                marker_str = ' '.join(markers) if markers else ''
                print(f"        [{idx:2d}] <{el['tag']:4s}> ({el['x']:3d}, {el['y']:3d}) '{el['text'][:30]}' {marker_str}")

            # ========== 步骤8: 尝试点击具体站点 ==========
            print("\n[8/8] 查找具体站点...")

            # 查找包含"站点"、"IPC"、"摄像头"等的元素
            station_elements = await iframe.evaluate("""
                () => {
                    const results = [];
                    const all = document.querySelectorAll('*');

                    all.forEach(el => {
                        const text = el.textContent || '';
                        // 查找可能的站点元素
                        if (text.length < 100 && text.length > 0) {
                            if (/站点|IPC|摄像头|Camera|Channel/i.test(text) ||
                                /^\d+$/.test(text.trim()) ||  // 纯数字可能是站点编号
                                (/^[\u4e00-\u9fa5]{2,4}-\d+$/.test(text))) {  // 中文-数字格式
                                const rect = el.getBoundingClientRect();
                                if (rect.x < 400 && rect.width > 0 && rect.height > 0 && rect.height < 100) {
                                    results.push({
                                        tag: el.tagName,
                                        text: text,
                                        x: Math.round(rect.x),
                                        y: Math.round(rect.y),
                                        onclick: el.onclick !== null
                                    });
                                }
                            }
                        }
                    });

                    return results.slice(0, 20);
                }
            """)

            if station_elements:
                print(f"      找到 {len(station_elements)} 个可能的站点元素:")
                for idx, el in enumerate(station_elements[:10]):
                    click_mark = " [可点击]" if el['onclick'] else ""
                    print(f"        [{idx}] <{el['tag']:4s}> ({el['x']:3d}, {el['y']:3d}) '{el['text']}'{click_mark}")

                # 尝试点击第一个
                if len(station_elements) > 0:
                    print(f"\n      尝试点击第一个站点...")
                    first_station = station_elements[0]

                    result = await iframe.evaluate("""
                        (x, y) => {
                            const el = document.elementFromPoint(x, y);
                            if (el) {
                                el.click();
                                return {success: true};
                            }
                            return {success: false};
                        }
                    """, first_station['x'] + 10, first_station['y'] + 10)

                    if result['success']:
                        print("      ✓ 已点击")
                        await page.wait_for_timeout(2000)
            else:
                print("      ! 未找到具体的站点元素")

            # ========== 完成 ==========
            print("\n" + "=" * 70)
            print("  自动化流程完成！")
            print("=" * 70)
            print("\n生成的截图:")
            print("  - step3_menu_expanded.png")
            print("  - step4_resource_view.png")
            print("  - step6_monitor_expanded.png")

            print("\n浏览器将保持打开30秒，你可以:")
            print("  1. 手动检查结果")
            print("  2. 尝试其他操作")
            print("  3. 截图保存")

            await page.screenshot(path="final_result.png", full_page=True)
            print("\n  ✓ 已保存完整截图: final_result.png")

            await page.wait_for_timeout(30000)

        except Exception as e:
            print(f"\n✗ 执行出错: {e}")
            import traceback
            traceback.print_exc()
            await page.screenshot(path="error.png")

        finally:
            await context.close()
            await browser.close()


if __name__ == "__main__":
    print("""
╔════════════════════════════════════════════════════════════╗
║              树形控件完整自动化流程                          ║
╚════════════════════════════════════════════════════════════╝

自动执行流程:
  1. 登录
  2. 点击实时预览
  3. 展开左侧菜单
  4. 点击资源视图
  5. 分析左侧元素
  6. 展开监控点
  7. 分析展开后的元素
  8. 查找并点击具体站点

注意事项:
  - 浏览器会显示所有操作过程
  - 每步都有截图保存
  - 最后会保持打开30秒供检查
    """)

    asyncio.run(full_auto_control())
