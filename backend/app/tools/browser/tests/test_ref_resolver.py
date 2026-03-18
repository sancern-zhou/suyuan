"""Test Ref Resolver - 验证ref到locator的自动解析

测试新的ref机制是否正确工作：
1. refs存储和检索
2. ref到locator的转换
3. nth索引处理
4. 错误处理
"""
import pytest
from playwright.sync_api import sync_playwright

from app.tools.browser.refs.ref_resolver import RefResolver, get_global_resolver, set_global_refs


def test_ref_resolver_basic():
    """测试基本的ref解析功能"""
    resolver = RefResolver()

    # 设置测试refs
    refs = {
        "e1": {"role": "textbox", "name": "用户名"},
        "e2": {"role": "textbox", "name": "密码"},
        "e3": {"role": "button", "name": "登录"}
    }
    resolver.set_refs(refs)

    # 验证ref存在
    assert resolver.has_ref("e1")
    assert resolver.has_ref("e2")
    assert not resolver.has_ref("e999")


def test_ref_resolver_with_nth():
    """测试nth索引支持"""
    resolver = RefResolver()

    # 设置带nth的refs（重复元素）
    refs = {
        "e1": {"role": "button", "name": "登录", "nth": 0},
        "e2": {"role": "button", "name": "登录", "nth": 1},  # 第2个登录按钮
    }
    resolver.set_refs(refs)

    # 验证nth信息
    info1 = resolver.get_ref_info("e1")
    assert info1["nth"] == 0

    info2 = resolver.get_ref_info("e2")
    assert info2["nth"] == 1


def test_global_resolver():
    """测试全局resolver实例"""
    # 清空全局resolver
    set_global_refs({})

    # 设置refs
    test_refs = {
        "e1": {"role": "textbox", "name": "测试"},
    }
    set_global_refs(test_refs)

    # 验证全局resolver可以访问
    global_resolver = get_global_resolver()
    assert global_resolver.has_ref("e1")


def test_ref_normalization():
    """测试ref格式规范化"""
    resolver = RefResolver()
    resolver.set_refs({"e1": {"role": "button"}})

    # 测试各种ref格式
    assert resolver.has_ref("e1")      # 标准格式
    assert resolver.has_ref("@e1")     # 带@前缀
    assert resolver.has_ref("ref=e1")   # 带ref=前缀


def test_playwright_locator_conversion():
    """测试ref到Playwright Locator的转换（需要真实浏览器）"""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        # 创建测试HTML
        page.set_content("""
            <html>
                <body>
                    <input type="text" placeholder="用户名" />
                    <input type="password" placeholder="密码" />
                    <button id="login-btn">登录</button>
                </body>
            </html>
        """)

        # 设置refs
        resolver = RefResolver()
        refs = {
            "e1": {"role": "textbox", "name": "用户名"},
            "e2": {"role": "textbox", "name": "密码"},
            "e3": {"role": "button", "name": "登录"}
        }
        resolver.set_refs(refs)

        # 测试locator转换
        try:
            # 用户名输入框
            locator1 = resolver.resolve(page, "e1")
            locator1.fill("testuser")

            # 密码输入框
            locator2 = resolver.resolve(page, "e2")
            locator2.fill("testpass")

            # 登录按钮
            locator3 = resolver.resolve(page, "e3")
            locator3.click()

            print("✅ 所有locator转换成功")

        except Exception as e:
            print(f"❌ Locator转换失败: {e}")
            raise

        browser.close()


if __name__ == "__main__":
    print("运行Ref Resolver测试...")
    print("\n1. 基本ref解析测试...")
    test_ref_resolver_basic()
    print("✅ 通过")

    print("\n2. nth索引测试...")
    test_ref_resolver_with_nth()
    print("✅ 通过")

    print("\n3. 全局resolver测试...")
    test_global_resolver()
    print("✅ 通过")

    print("\n4. ref格式规范化测试...")
    test_ref_normalization()
    print("✅ 通过")

    print("\n5. Playwright Locator转换测试...")
    test_playwright_locator_conversion()
    print("✅ 通过")

    print("\n所有测试通过!")
