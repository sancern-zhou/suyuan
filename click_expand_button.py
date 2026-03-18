"""
最终方案：点击树形控件的展开按钮

步骤：
1. 登录
2. 进入实时预览
3. 点击左侧菜单的展开按钮（让菜单从图标展开成文字）
4. 找到"根节点"的">"按钮
5. 点击展开
"""

import asyncio
from playwright.async_api import async_playwright

BASE_URL = "http://10.10.10.158"
USERNAME = "cdzhuanyong"
PASSWORD = "cdsz@429"


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False, slow_mo=800)
        context = await browser.new_context(viewport={"width": 1920, "height": 1080}, ignore_https_errors=True)
        page = await context.new_page()

        print("=" * 70)
        print("  点击树形控件展开按钮 - 最终方案")
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
            await page.wait_for_timeout(5000)
            print("✓ 已进入实时预览")

            # 获取iframe
            iframe = page.frame(name="vms_010100")
            if not iframe:
                print("✗ 无法获取iframe")
                return

            print("✓ iframe获取成功")

            # 等待内容加载
            await page.wait_for_timeout(3000)

            # ========== 步骤3: 展开左侧菜单（关键！）==========
            print("\n[步骤3] 展开左侧菜单...")

            # 使用 JavaScript 直接点击，绕过覆盖层
            print("  使用 JavaScript 点击展开按钮...")

            try:
                # 方法1: 使用 JavaScript 点击展开按钮
                expand_result = await iframe.evaluate("""
                    () => {
                        // 查找展开按钮
                        const collapseBtn = document.querySelector('li.el-menu--colloase-btn, li[class*="collapse"], li[class*="expand"]');

                        if (collapseBtn) {
                            // 直接触发点击事件
                            collapseBtn.click();
                            return {success: true, method: 'javascript_click'};
                        }

                        return {success: false, method: 'not_found'};
                    }
                """)

                if expand_result['success']:
                    print(f"  ✓ 已通过 JavaScript 点击展开按钮")
                    await page.wait_for_timeout(2000)  # 等待动画
                else:
                    print("  未找到展开按钮，尝试备用方案...")

                    # 方法2: 通过坐标点击（iframe内的坐标）
                    print("  尝试通过坐标点击...")
                    await iframe.mouse.click(20, 20)
                    print("  ✓ 已点击坐标(20, 20)")
                    await page.wait_for_timeout(2000)

            except Exception as e:
                print(f"  ✗ 点击展开按钮失败: {e}")

            await page.screenshot(path="after_left_menu_expand.png")
            print("  已保存截图: after_left_menu_expand.png")

            # ========== 步骤3.5: 点击"资源视图" ==========
            print("\n[步骤3.5] 点击'资源视图'菜单项...")

            try:
                # 使用 JavaScript 直接点击，绕过覆盖层
                click_result = await iframe.evaluate("""
                    () => {
                        // 查找所有菜单项
                        const menuItems = document.querySelectorAll('li.el-menu-item');

                        for (const item of menuItems) {
                            const text = item.textContent || '';
                            if (text.includes('资源视图')) {
                                // 直接触发点击
                                item.click();
                                return {success: true, method: 'found_and_clicked'};
                            }
                        }

                        return {success: false, method: 'not_found'};
                    }
                """)

                if click_result['success']:
                    print("  ✓ 已通过 JavaScript 点击'资源视图'")
                    await page.wait_for_timeout(2000)  # 等待加载
                else:
                    print("  未找到'资源视图'菜单项")

                await page.screenshot(path="after_click_resource_view.png")
                print("  已保存截图: after_click_resource_view.png")

            except Exception as e:
                print(f"  ✗ 点击'资源视图'失败: {e}")

            # ========== 步骤4: 现在分析展开后的菜单 ==========
            print("\n[步骤4] 分析展开后的菜单结构...")

            # 查找所有左侧元素
            left_elements = await iframe.evaluate("""
                () => {
                    const results = [];
                    const allElements = document.querySelectorAll('*');

                    allElements.forEach(el => {
                        const rect = el.getBoundingClientRect();
                        const text = (el.textContent || '').trim();

                        // 左侧区域（x < 250），可见
                        if (rect.x < 250 && rect.width > 0 && rect.height > 0) {
                            if (text && text.length > 0 && text.length < 100) {
                                results.push({
                                    tagName: el.tagName,
                                    text: text,
                                    className: el.className,
                                    id: el.id,
                                    x: Math.round(rect.x),
                                    y: Math.round(rect.y),
                                    width: Math.round(rect.width),
                                    height: Math.round(rect.height),
                                });
                            }
                        }
                    });

                    // 去重并排序
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
            for idx, el in enumerate(left_elements[:20]):
                print(f"  [{idx:2d}] <{el['tagName']:4s}> pos=({el['x']:3d}, {el['y']:3d}), "
                      f"text='{el['text'][:40]}'")

            # ========== 步骤5: 查找"监控点"的展开按钮 ==========
            print("\n[步骤5] 查找'监控点'的展开按钮...")

            expand_buttons = await iframe.evaluate("""
                () => {
                    const results = [];
                    const allElements = document.querySelectorAll('*');

                    allElements.forEach(el => {
                        const rect = el.getBoundingClientRect();
                        const text = (el.textContent || '').trim();

                        // 查找可能的展开按钮
                        // 1. 小尺寸元素
                        // 2. 在左侧区域
                        // 3. 可能包含特殊字符或图标
                        const isSmall = rect.width < 50 && rect.height < 50;
                        const inLeftArea = rect.x < 250;
                        const isVisible = rect.width > 0 && rect.height > 0;

                        // 检查各种可能的特征
                        const hasExpandClass = /expand|collapse|arrow|caret|chevron|triangle|toggle|switch/i.test(el.className || '');
                        const hasIconClass = /icon|d-|nav-/i.test(el.className || '');
                        const textIsSymbol = /^[>▼▶▲+−∨∧✓✗●○]+$/.test(text);

                        // 检查父元素是否包含"监控点"或"根节点"等关键词
                        let parentHasTarget = false;
                        let parentTargetText = '';
                        let parent = el.parentElement;
                        for (let i = 0; i < 5 && parent; i++) {
                            const parentText = (parent.textContent || '').trim();
                            // 优先查找"监控点"
                            if (parentText.includes('监控点') && parentText.length < 100) {
                                parentHasTarget = true;
                                parentTargetText = '监控点';
                                break;
                            }
                            // 其次查找"根节点"
                            if (parentText.includes('根节点') && parentText.length < 100) {
                                parentHasTarget = true;
                                parentTargetText = '根节点';
                                break;
                            }
                            parent = parent.parentElement;
                        }

                        if (isVisible && inLeftArea && isSmall) {
                            if (hasExpandClass || (hasIconClass && textIsSymbol) || parentHasTarget) {
                                results.push({
                                    tagName: el.tagName,
                                    text: text,
                                    className: el.className,
                                    x: Math.round(rect.x),
                                    y: Math.round(rect.y),
                                    width: Math.round(rect.width),
                                    height: Math.round(rect.height),
                                    parentHasTarget: parentHasTarget,
                                    parentTargetText: parentTargetText,
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
                    target_mark = f" ← 关联'{btn['parentTargetText']}'" if btn['parentHasTarget'] else ""
                    print(f"  [{idx}] <{btn['tagName']}> pos=({btn['x']}, {btn['y']}), "
                          f"text='{btn['text']}', class='{btn['className'][:40]}'{target_mark}")

                # 优先找关联"监控点"的按钮
                monitor_buttons = [btn for btn in expand_buttons if btn['parentTargetText'] == '监控点']
                root_buttons = [btn for btn in expand_buttons if btn['parentTargetText'] == '根节点']

                if monitor_buttons:
                    print(f"\n✓ 找到 {len(monitor_buttons)} 个关联'监控点'的按钮")

                    # 使用 JavaScript 点击，绕过覆盖层
                    print(f"\n[步骤6] 点击'监控点'的展开按钮...")

                    click_result = await iframe.evaluate("""
                        () => {
                            // 查找包含"监控点"的元素
                            const allElements = document.querySelectorAll('*');
                            for (const el of allElements) {
                                const text = el.textContent || '';
                                if (text.includes('监控点') && text.length < 100 && text.split('\n').length < 5) {
                                    // 找到其父元素
                                    const parent = el.parentElement;
                                    if (parent) {
                                        // 查找父元素的第一个子元素（通常是展开按钮）
                                        const firstChild = parent.firstElementChild;
                                        if (firstChild && firstChild !== el) {
                                            // 点击展开按钮
                                            firstChild.click();
                                            return {success: true, method: 'clicked_expand_button'};
                                        }
                                    }
                                }
                            }
                            return {success: false, method: 'not_found'};
                        }
                    """)

                    if click_result['success']:
                        print("✓ 已通过 JavaScript 点击'监控点'展开按钮")
                    else:
                        print("✗ JavaScript 点击失败")

                    await page.wait_for_timeout(2000)
                    await page.screenshot(path="after_expand_monitor.png")
                    print("✓ 已保存截图: after_expand_monitor.png")

                    # 展开监控点后，再查找"根节点"
                    print("\n[步骤7] 查找展开后的'根节点'...")

                    await page.wait_for_timeout(1000)

                    # 重新分析左侧元素
                    left_elements_after = await iframe.evaluate("""
                        () => {
                            const results = [];
                            const allElements = document.querySelectorAll('*');

                            allElements.forEach(el => {
                                const rect = el.getBoundingClientRect();
                                const text = (el.textContent || '').trim();

                                if (rect.x < 250 && rect.width > 0 && rect.height > 0) {
                                    if (text && text.length > 0 && text.length < 100) {
                                        results.push({
                                            tagName: el.tagName,
                                            text: text,
                                            className: el.className,
                                            x: Math.round(rect.x),
                                            y: Math.round(rect.y),
                                        });
                                    }
                                }
                            });

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

                    print(f"\n展开后找到 {len(left_elements_after)} 个左侧元素:")
                    for idx, el in enumerate(left_elements_after[:20]):
                        print(f"  [{idx:2d}] <{el['tagName']:4s}> pos=({el['x']:3d}, {el['y']:3d}), "
                              f"text='{el['text'][:40]}'")

                elif root_buttons:
                    print(f"\n⚠ 未找到'监控点'，但找到 {len(root_buttons)} 个关联'根节点'的按钮")
                    print("  直接点击'根节点'的展开按钮...")

                    target = root_buttons[0]
                    print(f"\n[步骤6] 点击'根节点'的展开按钮 (pos={target['x']}, {target['y']})...")

                    # 使用 JavaScript 点击
                    click_result = await iframe.evaluate(f"""
                        (x, y) => {{
                            const element = document.elementFromPoint(x, y);
                            if (element) {{
                                element.click();
                                return {{success: true}};
                            }}
                            return {{success: false}};
                        }}
                    """, target['x'] + target['width'] // 2, target['y'] + target['height'] // 2)

                    if click_result['success']:
                        print("✓ 已通过 JavaScript 点击")
                    else:
                        print("✗ 点击失败")

                    await page.wait_for_timeout(2000)
                    await page.screenshot(path="after_expand_root.png")
                    print("✓ 已保存截图: after_expand_root.png")

            else:
                print("\n未找到展开按钮")
                print("\n尝试备用方案：查找'监控点'元素并点击其展开按钮...")

                try:
                    # 备用方案：查找包含"监控点"的元素，然后找其第一个子元素（展开按钮）
                    monitor_element = iframe.get_by_text("监控点")
                    count = await monitor_element.count()

                    if count > 0:
                        print(f"  找到 {count} 个包含'监控点'的元素")

                        # 使用 JavaScript 找到展开按钮
                        expand_btn = await iframe.evaluate("""
                            () => {
                                const allElements = document.querySelectorAll('*');
                                for (const el of allElements) {
                                    const text = el.textContent || '';
                                    if (text.includes('监控点') && text.length < 100 && text.split('\\n').length < 5) {
                                        // 找到这个元素的父元素
                                        const parent = el.parentElement;
                                        if (parent) {
                                            // 查找父元素的第一个子元素（通常是展开按钮）
                                            const firstChild = parent.firstElementChild;
                                            if (firstChild && firstChild !== el) {
                                                const rect = firstChild.getBoundingClientRect();
                                                if (rect.width > 0 && rect.height > 0) {
                                                    return {
                                                        x: Math.round(rect.x + rect.width / 2),
                                                        y: Math.round(rect.y + rect.height / 2),
                                                        tagName: firstChild.tagName,
                                                        className: firstChild.className,
                                                        text: (firstChild.textContent || '').trim(),
                                                    };
                                                }
                                            }
                                        }
                                    }
                                }
                                return null;
                            }
                        """)

                        if expand_btn:
                            print(f"  找到展开按钮: <{expand_btn['tagName']}> class='{expand_btn['className']}', pos=({expand_btn['x']}, {expand_btn['y']})")

                            # 使用 JavaScript 点击
                            click_result = await iframe.evaluate(f"""
                                (x, y) => {{
                                    // 在指定坐标找到元素并点击
                                    const element = document.elementFromPoint(x, y);
                                    if (element) {{
                                        element.click();
                                        return {{success: true}};
                                    }}
                                    return {{success: false}};
                                }}
                            """, expand_btn['x'], expand_btn['y'])

                            if click_result['success']:
                                print("  ✓ 已通过 JavaScript 点击")
                            else:
                                print("  ✗ 点击失败")

                            await page.wait_for_timeout(2000)
                            await page.screenshot(path="after_expand_monitor_v2.png")
                            print("  ✓ 已保存截图: after_expand_monitor_v2.png")
                        else:
                            print("  未找到展开按钮")
                    else:
                        print("  未找到'监控点'元素")

                except Exception as e:
                    print(f"  备用方案失败: {e}")

            # ========== 完成 ==========
            print("\n" + "=" * 70)
            print("完成！浏览器保持打开30秒，你可以手动检查...")
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
