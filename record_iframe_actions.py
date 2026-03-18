# -*- coding: utf-8 -*-
"""
增强版录制工具 - 支持iframe录制

改进：
1. 自动登录
2. 在iframe中注入录制脚本
3. 记录iframe内的所有操作
"""

import asyncio
import json
from datetime import datetime
from playwright.async_api import async_playwright

BASE_URL = "http://10.10.10.158"
USERNAME = "cdzhuanyong"
PASSWORD = "cdsz@429"


class EnhancedRecorder:
    """增强型录制器"""

    def __init__(self):
        self.actions = []
        self.iframe_actions = []

    def record_action(self, action_type: str, details: dict, is_iframe=False):
        """记录一个操作"""
        location = "[iframe]" if is_iframe else "[page]"
        action = {
            "timestamp": datetime.now().isoformat(),
            "type": action_type,
            "details": details,
            "location": location
        }
        if is_iframe:
            self.iframe_actions.append(action)
        else:
            self.actions.append(action)
        print(f"[录制] {location} {action_type}: {details.get('text', '')[:30]}")

    async def inject_recorder(self, page, is_iframe=False):
        """注入录制脚本"""
        await page.evaluate("""
            () => {
                // 监听所有点击事件
                document.addEventListener('click', (e) => {
                    const target = e.target;
                    const rect = target.getBoundingClientRect();

                    const info = {
                        tagName: target.tagName,
                        id: target.id || '',
                        className: target.className || '',
                        text: target.textContent?.trim().substring(0, 50) || '',
                        x: Math.round(rect.x),
                        y: Math.round(rect.y),
                        width: Math.round(rect.width),
                        height: Math.round(rect.height),
                        role: target.getAttribute('role') || '',
                        ariaLabel: target.getAttribute('aria-label') || '',
                        title: target.getAttribute('title') || '',
                        href: target.href || '',
                        isButton: target.tagName === 'BUTTON' || target.type === 'submit',
                        isInput: target.tagName === 'INPUT' || target.tagName === 'TEXTAREA',
                        inputType: target.type || '',
                        inputName: target.name || '',
                    };

                    console.log('ACTION:CLICK:' + JSON.stringify(info));
                }, true);

                // 监听输入事件
                document.addEventListener('input', (e) => {
                    const target = e.target;
                    const info = {
                        tagName: target.tagName,
                        type: target.type || '',
                        name: target.name || '',
                        id: target.id || '',
                        className: target.className || '',
                        value: target.value?.substring(0, 50) || '',
                        placeholder: target.placeholder || ''
                    };

                    console.log('ACTION:INPUT:' + JSON.stringify(info));
                }, true);

                console.log('RECORDER_READY');
            }
        """)

    async def setup_console_listener(self, page, is_iframe=False):
        """设置控制台监听"""
        page.on("console", lambda msg: asyncio.create_task(self._handle_console(msg, is_iframe)))

    async def _handle_console(self, msg, is_iframe):
        """处理控制台消息"""
        if msg.type == "log":
            text = msg.text
            if text.startswith("ACTION:"):
                try:
                    parts = text.split(":", 2)
                    action_type = parts[1]
                    details = json.loads(parts[2])
                    self.record_action(action_type, details, is_iframe)
                except Exception as e:
                    pass
            elif text == "RECORDER_READY":
                location = "[iframe]" if is_iframe else "[page]"
                print(f"[录制] {location} 录制器已就绪")


async def main():
    recorder = EnhancedRecorder()

    print("=" * 70)
    print("  增强版录制工具 - 自动登录+iframe录制")
    print("=" * 70)
    print("\n功能：")
    print("  1. 自动登录")
    print("  2. 自动进入实时预览")
    print("  3. 在iframe中注入录制器")
    print("  4. 记录你的所有手动操作")
    print("  5. 生成自动化代码")
    print("\n使用方法：")
    print("  1. 运行此脚本")
    print("  2. 等待自动登录完成")
    print("  3. 在浏览器中手动操作（从点击实时预览开始）")
    print("  4. 按 Ctrl+C 结束录制")
    print("\n" + "=" * 70)
    print()

    input("按回车键开始...")
    print()

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,
            slow_mo=300,
            args=['--ignore-certificate-errors', '--start-maximized']
        )

        context = await browser.new_context(
            viewport={"width": 1920, "height": 1080},
            ignore_https_errors=True
        )

        page = await context.new_page()

        try:
            # ========== 步骤1: 自动登录 ==========
            print("\n[自动操作] 正在登录...")
            await page.goto(BASE_URL, timeout=30000)
            await page.wait_for_timeout(1000)

            # 使用JavaScript登录（绕过覆盖层）
            await page.evaluate(f"""
                () => {{
                    const inputs = document.querySelectorAll('input[type="text"], input[type="username"]');
                    if (inputs.length > 0) inputs[0].value = '{USERNAME}';

                    const passwords = document.querySelectorAll('input[type="password"]');
                    if (passwords.length > 0) passwords[0].value = '{PASSWORD}';

                    const buttons = document.querySelectorAll('button');
                    for (const btn of buttons) {{
                        const text = btn.textContent || '';
                        if (text.includes('登录') || text.toLowerCase().includes('login')) {{
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
            print("\n[自动操作] 点击'实时预览'...")
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

            # ========== 步骤3: 获取iframe并注入录制器 ==========
            print("\n[自动操作] 获取iframe并注入录制器...")

            # 等待iframe加载
            await page.wait_for_timeout(3000)

            # 获取iframe
            iframe = page.frame(name="vms_010100")

            if not iframe:
                print("      ! 尝试查找iframe...")
                iframe_elements = await page.query_selector_all("iframe")
                print(f"      找到 {len(iframe_elements)} 个iframe")

                for idx, iframe_el in enumerate(iframe_elements):
                    name = await iframe_el.get_attribute("name")
                    src = await iframe_el.get_attribute("src")
                    print(f"        [{idx}] name={name}, src={src[:60] if src else ''}")

                    if name == "vms_010100" or (src and "vms" in src):
                        try:
                            iframe = await iframe_el.content_frame()
                            print(f"      ✓ 使用iframe[{idx}]")
                            break
                        except Exception as e:
                            print(f"        ! 无法获取content_frame: {e}")

            if not iframe:
                print("      ✗ 无法获取iframe")
                print("\n保持浏览器打开30秒，请手动检查...")
                await page.wait_for_timeout(30000)
                return

            # 在iframe中注入录制器
            print("\n[自动操作] 在iframe中注入录制器...")
            await recorder.inject_recorder(iframe, is_iframe=True)
            await recorder.setup_console_listener(iframe, is_iframe=True)
            await page.wait_for_timeout(1000)
            print("      ✓ iframe录制器已就绪")

            # 在主页面也注入（以防万一）
            await recorder.inject_recorder(page, is_iframe=False)
            await recorder.setup_console_listener(page, is_iframe=False)

            # ========== 步骤4: 等待用户手动操作 ==========
            print("\n" + "=" * 70)
            print("  现在请在浏览器中手动操作")
            print("=" * 70)
            print("\n请执行以下操作：")
            print("")
            print("步骤 1: 展开左侧菜单")
            print("        - 点击左上角的展开按钮（☰ 三横线图标）")
            print("")
            print("步骤 2: 点击'资源视图'")
            print("")
            print("步骤 3: 展开'监控点'")
            print("        - 点击'监控点'左侧的 '>' 或 '◢' 按钮")
            print("")
            print("步骤 4: 展开'根节点'（如果有的话）")
            print("")
            print("步骤 5: 点击具体站点")
            print("")
            print("步骤 6: 打开视频监控")
            print("")
            print("⚠️  注意：")
            print("  - 每个操作之间等待1-2秒")
            print("  - 确保操作完成了再进行下一步")
            print("  - 如果某个操作没反应，请告诉我")
            print("")
            print("完成后按 Ctrl+C 结束录制")
            print("\n" + "=" * 70)
            print("  开始录制...")
            print("=" * 70)
            print()

            # 保持浏览器打开，等待用户操作
            await page.wait_for_timeout(300000)  # 5分钟超时

        except KeyboardInterrupt:
            print("\n" + "=" * 70)
            print("  录制结束")
            print("=" * 70)

            all_actions = recorder.actions + recorder.iframe_actions

            print(f"\n共录制了 {len(all_actions)} 个操作:")
            print(f"  - 主页面: {len(recorder.actions)} 个")
            print(f"  - iframe内: {len(recorder.iframe_actions)} 个")

            # 显示所有操作
            for idx, action in enumerate(all_actions):
                print(f"\n{idx + 1}. {action['location']} {action['type']}")
                details = action['details']
                for key, value in details.items():
                    if value and key not in ['text', 'className', 'ariaLabel']:
                        print(f"      {key}: {value}")

            # 保存操作记录
            with open("recorded_actions.json", "w", encoding="utf-8") as f:
                json.dump(all_actions, f, ensure_ascii=False, indent=2)
            print("\n✓ 操作记录已保存到: recorded_actions.json")

            # 生成代码
            print("\n正在生成自动化代码...")
            code = generate_automation_code(all_actions)

            with open("recorded_actions.py", "w", encoding="utf-8") as f:
                f.write(code)
            print("✓ 自动化代码已保存到: recorded_actions.py")

            print("\n" + "=" * 70)
            print("  完成！")
            print("=" * 70)
            print("\n下一步:")
            print("  1. 查看 recorded_actions.json 了解操作细节")
            print("  2. 查看 recorded_actions.py 获取自动化代码")
            print("  3. 运行 python recorded_actions.py 测试代码")
            print("\n" + "=" * 70)

            await page.screenshot(path="recording_final.png")
            print("\n✓ 已保存截图: recording_final.png")

            await page.wait_for_timeout(30000)

        except Exception as e:
            print(f"\n✗ 执行出错: {e}")
            import traceback
            traceback.print_exc()
            await page.screenshot(path="error.png")

        finally:
            await context.close()
            await browser.close()


def generate_automation_code(actions):
    """生成自动化代码"""

    code_lines = []
    code_lines.append("# -*- coding: utf-8 -*-")
    code_lines.append('"""')
    code_lines.append("自动生成的操作代码 - 基于录制结果")
    code_lines.append('"""')
    code_lines.append("\nimport asyncio")
    code_lines.append("from playwright.async_api import async_playwright\n")
    code_lines.append("BASE_URL = \"http://10.10.10.158\"\n")
    code_lines.append("async def run_recorded_actions():")
    code_lines.append("    async with async_playwright() as p:")
    code_lines.append("        browser = await p.chromium.launch(")
    code_lines.append("            headless=False,")
    code_lines.append("            slow_mo=500,")
    code_lines.append("            args=['--ignore-certificate-errors']")
    code_lines.append("        )")
    code_lines.append("        context = await browser.new_context(")
    code_lines.append("            viewport={\"width\": 1920, \"height\": 1080},")
    code_lines.append("            ignore_https_errors=True")
    code_lines.append("        )")
    code_lines.append("        page = await context.new_page()\n")
    code_lines.append("        try:")
    code_lines.append("            # ========== 自动登录 ==========")
    code_lines.append("            print(\"正在登录...\")")
    code_lines.append("            await page.goto(BASE_URL)")
    code_lines.append("            await page.wait_for_timeout(1000)")
    code_lines.append("            await page.evaluate('\"\"\"")
    code_lines.append(f"                () => {{")
    code_lines.append(f"                    const inputs = document.querySelectorAll('input[type=\"text\"], input[type=\"username\"]');")
    code_lines.append(f"                    if (inputs.length > 0) inputs[0].value = '{USERNAME}';")
    code_lines.append(f"                    const passwords = document.querySelectorAll('input[type=\"password\"]');")
    code_lines.append(f"                    if (passwords.length > 0) passwords[0].value = '{PASSWORD}';")
    code_lines.append(f"                    const buttons = document.querySelectorAll('button');")
    code_lines.append(f"                    for (const btn of buttons) {{")
    code_lines.append(f"                        if (btn.textContent.includes('登录') || btn.textContent.toLowerCase().includes('login')) {{")
    code_lines.append(f"                            btn.click();")
    code_lines.append(f"                            return true;")
    code_lines.append(f"                        }}")
    code_lines.append(f"                    }}")
    code_lines.append(f"                }}")
    code_lines.append("            \"\"\")")
    code_lines.append("            await page.wait_for_timeout(3000)")
    code_lines.append("            print(\"登录成功\")")
    code_lines.append("")

    # 分析iframe操作
    iframe_actions = [a for a in actions if a.get("location") == "[iframe]"]

    if iframe_actions:
        code_lines.append("            # ========== 进入实时预览 ==========")
        code_lines.append("            print(\"点击实时预览...\")")
        code_lines.append("            result = await page.evaluate(\"\"\"\"")
        code_lines.append("                () => {")
        code_lines.append("                    const all = document.querySelectorAll('*');")
        code_lines.append("                    for (const el of all) {")
        code_lines.append("                        if (el.textContent.includes('实时预览')) {")
        code_lines.append("                            el.click();")
        code_lines.append("                            return true;")
        code_lines.append("                        }")
        code_lines.append("                    }")
        code_lines.append("                    return false;")
        code_lines.append("                }")
        code_lines.append("            \"\"\")")
        code_lines.append("            )")
        code_lines.append("            await page.wait_for_timeout(5000)")
        code_lines.append("            print(\"已进入实时预览\")")
        code_lines.append("")

        code_lines.append("            # ========== 获取iframe ==========")
        code_lines.append("            print(\"获取iframe...\")")
        code_lines.append("            await page.wait_for_timeout(2000)")
        code_lines.append("            iframe = page.frame(name='vms_010100')")
        code_lines.append("            if not iframe:")
        code_lines.append("                print(\"无法获取iframe，尝试查找...\")")
        code_lines.append("                iframe_elements = await page.query_selector_all('iframe')")
        code_lines.append("                for iframe_el in iframe_elements:")
        code_lines.append("                    if await iframe_el.get_attribute('name') == 'vms_010100':")
        code_lines.append("                        iframe = await iframe_el.content_frame()")
        code_lines.append("                        break")
        code_lines.append("            print(\"iframe获取成功\")")
        code_lines.append("            await page.wait_for_timeout(2000)")
        code_lines.append("")

        code_lines.append("            # ========== 执行录制的操作 ==========")
        code_lines.append("            print(\"执行录制的操作...\")")

        for idx, action in enumerate(iframe_actions):
            action_type = action["type"]
            details = action["details"]

            code_lines.append(f"\n            # 操作 {idx + 1}: {action_type}")
            code_lines.append(f"            # 时间: {action['timestamp']}")

            if action_type == "CLICK":
                text = details.get("text", "")
                x = details.get("x", 0)
                y = details.get("y", 0)
                width = details.get("width", 0)
                height = details.get("height", 0)
                class_name = details.get("className", "")

                # 使用坐标点击（最可靠）
                if x > 0 and y > 0:
                    code_lines.append(f"            # 点击: {text[:30] if text else '(无文本)'}")
                    code_lines.append(f"            await iframe.mouse.click({x + width // 2}, {y + height // 2})")
                    code_lines.append("            await asyncio.sleep(1)")
                else:
                    # 备用：使用选择器
                    if class_name:
                        code_lines.append(f"            await iframe.locator('.{class_name.split()[0]}').click()")
                    else:
                        code_lines.append(f"            # 点击文本: {text}")
                        code_lines.append(f"            await iframe.evaluate(\"\"\"")
                        code_lines.append(f"                () => {{")
                        code_lines.append(f"                    const all = document.querySelectorAll('*');")
                        code_lines.append(f"                    for (const el of all) {{")
                        code_lines.append(f"                        if (el.textContent.includes('{text}')) {{")
                        code_lines.append(f"                            el.click();")
                        code_lines.append(f"                            return true;")
                        code_lines.append(f"                        }}")
                        code_lines.append(f"                    }}")
                        code_lines.append(f"                }}")
                        code_lines.append(f"            \"\"\")")
                        code_lines.append("            await asyncio.sleep(1)")

        code_lines.append("\n            print(\"所有操作已完成！\")")
        code_lines.append("            await asyncio.sleep(3)")

        code_lines.append("\n        except Exception as e:")
        code_lines.append("            print(f\"错误: {e}\")")
        code_lines.append("            import traceback")
        code_lines.append("            traceback.print_exc_exc()")

        code_lines.append("\n        finally:")
        code_lines.append("            await context.close()")
        code_lines.append("            await browser.close()")
        code_lines.append("\n")
        code_lines.append("if __name__ == '__main__':")
        code_lines.append("    asyncio.run(run_recorded_actions())")

        return "\n".join(code_lines)


if __name__ == "__main__":
    print("""
╔════════════════════════════════════════════════════════════╗
║          增强版录制工具 - 自动登录+iframe录制                ║
╚════════════════════════════════════════════════════════════╝

特点：
  ✓ 自动登录
  ✓ 自动进入实时预览
  ✓ 在iframe中注入录制器
  ✓ 记录所有操作
  ✓ 生成可运行的代码

使用方法：
  1. 运行此脚本
  2. 等待自动登录完成
  3. 在浏览器中手动操作（从点击实时预览后开始）
  4. 按 Ctrl+C 结束录制
  5. 查看生成的代码

    """)

    asyncio.run(main())
