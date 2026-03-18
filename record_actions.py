# -*- coding: utf-8 -*-
"""
操作录制工具 - 记录你的手动操作并生成代码

使用方法：
1. 运行此脚本
2. 在浏览器中手动操作（登录、点击、展开等）
3. 按 Ctrl+C 结束录制
4. 脚本会自动生成对应的自动化代码

生成的代码会保存到: recorded_actions.py
"""

import asyncio
import json
from datetime import datetime
from playwright.async_api import async_playwright
from typing import Dict, List

BASE_URL = "http://10.10.10.158"
USERNAME = "cdzhuanyong"
PASSWORD = "cdsz@429"


class ActionRecorder:
    """操作录制器"""

    def __init__(self):
        self.actions = []
        self.start_time = None

    def record_action(self, action_type: str, details: dict):
        """记录一个操作"""
        action = {
            "timestamp": datetime.now().isoformat(),
            "type": action_type,
            "details": details
        }
        self.actions.append(action)
        print(f"[录制] {action_type}: {details}")

    async def setup_recording(self, page):
        """设置录制监听器"""

        # 监听所有点击事件
        await page.evaluate("""
            () => {
                // 记录所有点击
                document.addEventListener('click', (e) => {
                    const target = e.target;
                    const rect = target.getBoundingClientRect();

                    // 获取元素的定位信息
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

                    // 通过 console.log 发送信息
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

                // 监听提交事件
                document.addEventListener('submit', (e) => {
                    const target = e.target;
                    const info = {
                        tagName: target.tagName,
                        action: target.action || '',
                        method: target.method || '',
                        className: target.className || ''
                    };

                    console.log('ACTION:SUBMIT:' + JSON.stringify(info));
                }, true);

                console.log('RECORDING:READY');
            }
        """)

    async def capture_actions(self, page):
        """捕获所有操作"""

        # 设置控制台监听
        page.on("console", lambda msg: asyncio.create_task(self._handle_console(msg)))

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
                except:
                    pass
            elif text == "RECORDING:READY":
                print("\n[录制] 录制器已就绪，请开始操作...")

    def generate_code(self):
        """生成自动化代码"""

        code_lines = []
        code_lines.append("# -*- coding: utf-8 -*-")
        code_lines.append('"""')
        code_lines.append("自动生成的操作代码")
        code_lines.append('"""')
        code_lines.append("\nimport asyncio")
        code_lines.append("from playwright.async_api import async_playwright\n")
        code_lines.append("BASE_URL = \"http://10.10.10.158\"\n")
        code_lines.append("async def run_actions():")
        code_lines.append("    async with async_playwright() as p:")
        code_lines.append("        browser = await p.chromium.launch(headless=False, slow_mo=500)")
        code_lines.append("        context = await browser.new_context(")
        code_lines.append("            viewport={\"width\": 1920, \"height\": 1080},")
        code_lines.append("            ignore_https_errors=True")
        code_lines.append("        )")
        code_lines.append("        page = await context.new_page()\n")
        code_lines.append("        try:")

        # 分析操作序列
        for idx, action in enumerate(self.actions):
            action_type = action["type"]
            details = action["details"]

            code_lines.append(f"\n            # 操作 {idx + 1}: {action_type}")
            code_lines.append(f"            # 时间: {action['timestamp']}")

            if action_type == "CLICK":
                # 生成点击代码
                if details.get("isButton"):
                    code_lines.append(f"            # 点击按钮: {details.get('text', '')[:30]}")
                    code_lines.append(f"            await page.evaluate(\"\"\"")
                    code_lines.append(f"                () => {{")
                    code_lines.append(f"                    const btn = document.querySelector('button');")
                    code_lines.append(f"                    if (btn) btn.click();")
                    code_lines.append(f"                }}")
                    code_lines.append(f"            \"\"\")")

                elif details.get("role") == "treeitem":
                    code_lines.append(f"            # 点击树形节点: {details.get('text', '')[:30]}")
                    code_lines.append(f"            await page.get_by_role(\"treeitem\", name=\"{details.get('text', '')}\").click()")

                elif details.get("x", 0) < 300 and details.get("y", 0) < 600:
                    # 左侧区域的点击
                    code_lines.append(f"            # 点击左侧元素: {details.get('text', '')[:30]}")
                    code_lines.append(f"            await page.mouse.click({details['x'] + details['width']//2}, {details['y'] + details['height']//2})")

                else:
                    code_lines.append(f"            # 点击: {details.get('text', '')[:30]}")
                    code_lines.append(f"            await page.evaluate(\"\"\"")
                    code_lines.append(f"                () => {{")
                    code_lines.append(f"                    const all = document.querySelectorAll('*');")
                    code_lines.append(f"                    for (const el of all) {{")
                    code_lines.append(f"                        if (el.textContent.includes('{details.get('text', '')[:30]}')) {{")
                    code_lines.append(f"                            el.click();")
                    code_lines.append(f"                            return true;")
                    code_lines.append(f"                        }}")
                    code_lines.append(f"                    }}")
                    code_lines.append(f"                }}")
                    code_lines.append(f"            \"\"\")")

                code_lines.append(f"            await page.wait_for_timeout(1000)")

            elif action_type == "INPUT":
                code_lines.append(f"\n            # 输入: {details.get('placeholder', '')}")
                if details.get("inputType") == "password":
                    code_lines.append(f"            await page.fill('input[type=\"password\"]', '{PASSWORD}')")
                else:
                    code_lines.append(f"            await page.fill('input[type=\"text\"]', '{USERNAME}')")
                code_lines.append(f"            await page.wait_for_timeout(500)")

        code_lines.append("\n            print(\"所有操作已完成！\")")
        code_lines.append("            await page.wait_for_timeout(3000)")

        code_lines.append("\n        except Exception as e:")
        code_lines.append("            print(f\"错误: {e}\")")
        code_lines.append("            import traceback")
        code_lines.append("            traceback.print_exc_exc()")

        code_lines.append("\n        finally:")
        code_lines.append("            await context.close()")
        code_lines.append("            await browser.close()")
        code_lines.append("\n")
        code_lines.append("if __name__ == '__main__':")
        code_lines.append("    asyncio.run(run_actions())")

        return "\n".join(code_lines)


async def main():
    recorder = ActionRecorder()

    print("=" * 70)
    print("  操作录制工具")
    print("=" * 70)
    print("\n功能：")
    print("  1. 打开浏览器并导航到网页")
    print("  2. 监听你的所有操作（点击、输入等）")
    print("  3. 记录操作细节（位置、文本、属性等）")
    print("  4. 自动生成可复用的Python代码")
    print("\n使用方法：")
    print("  1. 运行此脚本")
    print("  2. 在浏览器中手动操作整个流程")
    print("  3. 按 Ctrl+C 结束录制")
    print("  4. 查看生成的 recorded_actions.py")
    print("\n" + "=" * 70)
    print()
    print("脚本即将启动，请准备登录...")
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

        # 设置录制
        await recorder.capture_actions(page)

        # 导航到网页
        print("正在打开网页...")
        await page.goto(BASE_URL)

        print("\n" + "=" * 70)
        print("  浏览器已就绪")
        print("=" * 70)
        print("\n请在浏览器中手动登录：")
        print("  - 用户名: cdzhuanyong")
        print("  - 密码: cdsz@429")
        print("\n等待60秒供你手动登录...")
        print("登录完成后脚本会自动开始录制")

        # 等待60秒供用户手动登录
        await page.wait_for_timeout(60000)

        # 注入录制脚本
        await recorder.setup_recording(page)

        print("\n" + "=" * 70)
        print("  录制已开始！")
        print("=" * 70)
        print("\n请在浏览器中执行以下操作：")
        print("")
        print("步骤 1: 点击'实时预览'")
        print("")
        print("步骤 2: 等待页面加载完成")
        print("")
        print("步骤 3: 展开左侧菜单（如果未展开）")
        print("")
        print("步骤 4: 点击'资源视图'")
        print("")
        print("步骤 5: 展开'监控点'")
        print("")
        print("步骤 6: 展开'根节点'（如果有的话）")
        print("")
        print("步骤 7: 点击具体站点")
        print("")
        print("步骤 8: 打开视频监控")
        print("")
        print("操作完成后，按 Ctrl+C 结束录制")
        print("\n" + "=" * 70)
        print()

        try:
            # 保持浏览器打开，等待用户操作
            await page.wait_for_timeout(300000)  # 5分钟超时

        except KeyboardInterrupt:
            print("\n" + "=" * 70)
            print("  录制结束")
            print("=" * 70)
            print(f"\n共记录了 {len(recorder.actions)} 个操作")

            # 保存操作记录
            with open("recorded_actions.json", "w", encoding="utf-8") as f:
                json.dump(recorder.actions, f, ensure_ascii=False, indent=2)
            print("\n操作记录已保存到: recorded_actions.json")

            # 显示所有操作
            print("\n记录的操作:")
            for idx, action in enumerate(recorder.actions):
                print(f"\n{idx + 1}. {action['type']}")
                for key, value in action['details'].items():
                    if value:
                        print(f"   {key}: {value}")

            # 生成代码
            print("\n正在生成自动化代码...")
            code = recorder.generate_code()

            with open("recorded_actions.py", "w", encoding="utf-8") as f:
                f.write(code)
            print("\n✓ 自动化代码已保存到: recorded_actions.py")

            print("\n" + "=" * 70)
            print("  下一步")
            print("=" * 70)
            print("\n1. 查看 recorded_actions.json 了解操作细节")
            print("2. 查看 recorded_actions.py 获取自动化代码")
            print("3. 运行 python recorded_actions.py 测试自动化代码")
            print("\n" + "=" * 70)

        finally:
            await context.close()
            await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
