"""Integration Test - Browser Tool with Ref Support

完整测试browser工具的ref机制：
1. Snapshot生成refs
2. Act使用ref操作
3. 验证操作成功
"""
import pytest
from playwright.sync_api import sync_playwright

from app.tools.browser.refs.ref_resolver import get_global_resolver, set_global_refs
from app.tools.browser.refs.role_ref import RoleRef


def test_browser_ref_integration():
    """测试browser工具的完整ref集成流程（不使用BrowserTool以避免Playwright冲突）"""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        # 创建测试页面
        page.set_content("""
            <html>
                <head>
                    <title>测试页面</title>
                </head>
                <body>
                    <h1>登录表单</h1>
                    <form>
                        <input type="text" placeholder="请输入用户名" id="username" />
                        <input type="password" placeholder="请输入密码" id="password" />
                        <button id="login-btn">登录</button>
                    </form>
                </body>
            </html>
        """)

        print("\n1. 模拟snapshot生成refs...")
        # 模拟snapshot返回的refs
        mock_refs = {
            "e1": {
                "role": "textbox",
                "name": "请输入用户名",
                "selector": "#username",
                "html_attrs": {"id": "username", "placeholder": "请输入用户名"}
            },
            "e2": {
                "role": "textbox",
                "name": "请输入密码",
                "selector": "#password",
                "html_attrs": {"id": "password", "placeholder": "请输入密码"}
            },
            "e3": {
                "role": "button",
                "name": "登录",
                "selector": "#login-btn",
                "html_attrs": {"id": "login-btn"}
            }
        }

        # 存储refs到全局resolver
        set_global_refs(mock_refs)

        print(f"✅ 模拟snapshot成功，生成{len(mock_refs)}个refs")
        print(f"   Refs: {list(mock_refs.keys())}")

        # 验证refs已存储到全局resolver
        global_resolver = get_global_resolver()
        print("\n2. 验证refs已存储...")
        for ref_id in mock_refs:
            assert global_resolver.has_ref(ref_id)
        print("✅ 所有refs已存储到全局resolver")

        # 使用ref执行操作
        print(f"\n3. 使用ref执行操作...")

        # 输入用户名
        username_locator = global_resolver.resolve(page, "e1")
        username_locator.fill("testuser")
        print("✅ 输入用户名成功: e1")

        # 输入密码
        password_locator = global_resolver.resolve(page, "e2")
        password_locator.fill("testpass")
        print("✅ 输入密码成功: e2")

        # 点击登录按钮
        button_locator = global_resolver.resolve(page, "e3")
        button_locator.click()
        print("✅ 点击登录按钮成功: e3")

        # 验证输入值
        print("\n4. 验证输入值...")
        username_value = page.evaluate('() => document.getElementById("username").value')
        password_value = page.evaluate('() => document.getElementById("password").value')

        assert username_value == "testuser", f"用户名不匹配: {username_value}"
        assert password_value == "testpass", f"密码不匹配: {password_value}"
        print(f"✅ 输入值验证通过")
        print(f"   用户名: {username_value}")
        print(f"   密码: {password_value}")

        browser.close()
        print("\n✅ 所有集成测试通过!")


def test_role_ref_creation():
    """测试RoleRef的完整创建和属性"""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        page.set_content("""
            <html>
                <body>
                    <input type="text" placeholder="用户名" id="user-input" />
                </body>
            </html>
        """)

        print("\n1. 创建RoleRef...")
        element = page.query_selector("input[type='text']")
        ref = RoleRef.from_element("e1", element)

        print(f"✅ RoleRef创建成功")
        print(f"   role: {ref.role}")
        print(f"   name: {ref.name}")
        print(f"   selector: {ref.selector}")
        print(f"   html_attrs: {ref.html_attrs}")

        assert ref.role == "textbox"
        assert ref.name == "用户名"
        assert ref.selector == "#user-input"
        assert "id" in ref.html_attrs
        assert ref.html_attrs["id"] == "user-input"

        browser.close()
        print("✅ RoleRef测试通过!")


if __name__ == "__main__":
    print("=" * 60)
    print("Browser Tool Ref Integration Test")
    print("=" * 60)
    test_browser_ref_integration()
    print("\n" + "=" * 60)
    print("RoleRef Creation Test")
    print("=" * 60)
    test_role_ref_creation()
