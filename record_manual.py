# -*- coding: utf-8 -*-
"""
纯录制工具 - 手动登录后录制操作

使用方法：
1. 手动打开浏览器并登录 http://10.10.10.158
2. 运行此脚本
3. 脚本会附加到已打开的浏览器
4. 在浏览器中操作（从展开菜单开始）
5. 按 Ctrl+C 结束录制
"""

import asyncio
import json
from datetime import datetime
from playwright.async_api import async_playwright


class SimpleRecorder:
    """简化录制器"""

    def __init__(self):
        self.actions = []

    def record_action(self, action_type: str, details: dict):
        """记录一个操作"""
        action = {
            "timestamp": datetime.now().isoformat(),
            "type": action_type,
            "details": details
        }
        self.actions.append(action)
        print(f"[录制] {action_type}: {details.get('text', '')[:30]}")

    async def inject_recorder(self, page):
        """注入录制脚本"""
        await page.evaluate("""
            () => {
                // 监听所有点击事件
                document.addEventListener('click', (e) => {
                    const target = e.target;
                    const rect = target.getBoundingClientRect();

                    // 只记录有意义的点击（不在body背景上的）
                    if (rect.width > 0 && rect.height > 0 && rect.width < 500 && rect.height < 500) {
                        const info = {
                            tagName: target.tagName,
                        id: target.id || '',
                        className: target.className || '',
                        text: target.textContent?.trim().substring(0, 80) || '',
                        x: Math.round(rect.x),
                        y: Math.round(rect.y),
                        width: Math.round(rect.width),
                        height: Math.round(rect.height),
                        role: target.getAttribute('role') || '',
                        ariaLabel: target.getAttribute('aria-label') || '',
                        title: target.getAttribute('title') || '',
                        onclick: target.onclick !== null
                        };

                        console.log('ACTION:' + JSON.stringify(info));
                    }
                }, true);

                console.log('RECORDER_READY');
            }
        """)

    async def setup_console_listener(self, page):
        """设置控制台监听"""
        page.on("console", lambda msg: asyncio.create_task(self._handle_console(msg))

    async def _handle_console(self, msg):
        """处理控制台消息"""
        if msg.type == "log":
            text = msg.text
            if text.startswith("ACTION:"):
                try:
                    parts = text.split(":", 2)
                    action_type = parts[1]
                    details = json.loads(parts[2])
                    self.record_action(action_type, details)
                except Exception as e:
                    pass
            elif text == "RECORDER_READY":
                print("\n[系统] 录制器已就绪，请开始操作...")


async def main():
    recorder = SimpleRecorder()

    print("=" * 70)
    print("  纯录制工具 - 手动登录版")
    print("=" * 70)
    print("\n功能：")
    print("  1. 附加到已打开的浏览器")
    print("  2. 注入操作录制器")
    print("  3. 记录所有点击操作")
    print("  4. 生成自动化代码")
    print("\n使用方法：")
    print("  步骤1: 手动打开Chrome浏览器")
    print("          访问: http://10.10.10.158")
    print("          手动登录")
    print("          等待页面完全加载")
    print("  步骤2: 运行此脚本（python record_manual.py）")
    print("  步骤3: 在浏览器中操作（展开菜单、点击资源视图等）")
    print("  步骤4: 按 Ctrl+C 结束录制")
    print("\n" + "=" * 70)
    print()

    input("准备好后按回车键...")
    print()

    async with async_playwright() as p:
        try:
            # 连接到已打开的浏览器
            print("\n[系统] 正在连接到浏览器...")
            browser = await p.chromium.connect_over_cdp("http://localhost:9222")
            print("[系统] ✓ 已连接到浏览器")

            # 获取当前页面
            contexts = browser.contexts
            if not contexts:
                print("[错误] 没有找到浏览器上下文")
                print("\n请确保：")
                print("  1. Chrome浏览器已打开")
                print("  2. 访问了 http://10.10.10.158")
                print("  3. 使用以下命令启动Chrome：")
                print("     chrome.exe --remote-debugging-port=9222 --ignore-certificate-errors http://10.10.10.158")
                return

            context = contexts[0]
            pages = context.pages

            if not pages:
                print("[错误] 浏览器中没有页面")
                return

            page = pages[0]
            current_url = page.url
            page_title = await page.title()

            print(f"[系统] ✓ 当前页面: {current_url}")
            print(f"[系统] ✓ 页面标题: {page_title}")

            # 等待用户确认
            input("\n按回车键开始注入录制器...")
            print()

            # 注入录制器
            print("[系统] 正在注入录制器...")
            await recorder.inject_recorder(page)
            await recorder.setup_console_listener(page)

            print("[系统] ✓ 录制器已就绪")
            print("\n" + "=" * 70)
            print("  现在请在浏览器中操作")
            print("=" * 70)
            print("\n请执行以下操作（每个操作之间等待1-2秒）：")
            print("")
            print("  1. 展开左侧菜单")
            print("     - 点击左上角的三横线图标（☰）或其他展开按钮")
            print("")
            print("  2. 点击'资源视图'")
            print("")
            print("  3. 展开'监控点'")
            print("     - 点击'监控点'左侧的 '>' 或 '◢' 按钮")
            print("")
            print("  4. 展开'根节点'（如果有的话）")
            print("     - 点击'根节点'左侧的展开按钮")
            print("")
            print("  5. 点击具体站点")
            print("")
            print("  6. 打开视频监控")
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
            print(f"\n共录制了 {len(recorder.actions)} 个操作")

            # 显示所有操作
            print("\n录制的操作:")
            for idx, action in enumerate(recorder.actions):
                details = action['details']
                print(f"\n{idx + 1}. {action['type']}")
                print(f"   位置: ({details.get('x', 0)}, {details.get('y', 0)})")
                print(f"   大小: {details.get('width', 0)} x {details.get('height', 0)}")
                print(f"   文本: {details.get('text', '')[:50]}")
                print(f"   Class: {details.get('className', '')[:50]}")
                print(f"   可点击: {details.get('onclick', False)}")

            # 保存操作记录
            with open("recorded_actions.json", "w", encoding="utf-8") as f:
                json.dump(recorder.actions, f, ensure_ascii=False, indent=2)
            print("\n✓ 操作记录已保存到: recorded_actions.json")

            # 生成代码
            print("\n正在生成自动化代码...")
            code = generate_automation_code(recorder.actions)

            with open("recorded_actions.py", "w", encoding="utf-8") as f:
                f.write(code)
            print("✓ 自动化代码已保存到: recorded_actions.py")

            print("\n" + "=" * 70)
            print("  完成！")
            print("=" * 70)
            print("\n下一步:")
            print("  1. 查看 recorded_actions.json 了解操作细节")
            print("  2. 查看 recorded_actions.py 获取自动化代码")
            print("  3. 如有问题，可以把 recorded_actions.json 发给我分析")
            print("\n" + "=" * 70)

        except Exception as e:
            print(f"\n✗ 错误: {e}")
            import traceback
            traceback.print_exc()

        finally:
            # 断开连接，但保持浏览器打开
            try:
                await browser.close()
            except:
                pass


def generate_automation_code(actions):
    """生成自动化代码"""

    code_lines = []
    code_lines.append("# -*- coding: utf-8 -*-")
    code_lines.append('"""')
    code_lines.append("自动生成的操作代码")
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
    code_lines.append("            print(\"正在打开页面...\")")
    code_lines.append("            await page.goto(BASE_URL)")
    code_lines.append("            print(\"请在浏览器中手动登录...\")")
    code_lines.append("            input(\"登录后按回车继续...\")")
    code_lines.append("            await page.wait_for_timeout(30000)  # 给30秒手动登录时间")
    code_lines.append("\n            print(\"开始执行录制操作...\")")

        for idx, action in enumerate(actions):
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
                onclick = details.get("onclick", False)

                if text and (onclick or len(text) < 50):
                    code_lines.append(f"            # 点击: {text[:40]}")
                    code_lines.append(f"            await page.evaluate(\"\"\"\"")
                    code_lines.append(f"                () => {{")
                    code_lines.append(f"                    const all = document.querySelectorAll('*');")
                    code_lines.append(f"                    for (const el of all) {{")
                    code_lines.append(f"                        const text = el.textContent?.trim() || '';")
                    code_lines.append(f"                        if (text.includes('{text[:40]}')) {{")
                    code_lines.append(f"                            el.click();")
                    code_lines.append(f"                            await asyncio.sleep(1);")
                    code_lines.append(f"                            return true;")
                    code_lines.append(f"                        }}")
                    code_lines.append(f"                    }}")
                    code_lines.append(f"                }}")
                    code_lines.append(f"            \"\"\")")
                else:
                    # 使用坐标点击（最可靠）
                    if x > 0 and y > 0:
                        code_lines.append(f"            # 点击坐标: ({x}, {y})")
                        code_lines.append(f"            await page.mouse.click({x + width // 2}, {y + height // 2})")
                        code_lines.append("            await asyncio.sleep(1)")

        code_lines.append("\n            print(\"所有操作已完成！\")")

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
║              纯录制工具 - 手动登录版                      ║
╚════════════════════════════════════════════════════════════╝

准备步骤：
  1. 打开Chrome浏览器（必须带远程调试）
  2. 使用以下命令启动：
     chrome.exe --remote-debugging-port=9222 --ignore-certificate-errors "http://10.10.10.158"
  3. 手动登录
  4. 等待页面完全加载

然后：
  - 运行此脚本：python record_manual.py
  - 在浏览器中操作
  - 按 Ctrl+C 结束

生成文件：
  - recorded_actions.json（操作记录）
  - recorded_actions.py（自动化代码）

    """)

    asyncio.run(main())
