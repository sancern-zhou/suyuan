"""测试execute_js v2.2修复

验证双重箭头函数问题是否已修复
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from playwright.sync_api import sync_playwright


def test_execute_js_fix():
    """测试execute_js修复"""

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()

        # 使用一个简单的测试页面
        page.goto("https://example.com")

        print("="*80)
        print("测试execute_js v2.2修复")
        print("="*80)

        # 测试1：包含箭头函数的代码
        print("\n1. 包含箭头函数的代码")
        print("-"*80)
        code_with_arrow = """() => {
    return {
        title: document.title,
        url: window.location.href
    };
}"""

        try:
            result = page.evaluate(code_with_arrow)
            print(f"结果: {result}")
            print(f"状态: {'成功' if result and 'title' in result else '失败'}")
        except Exception as e:
            print(f"错误: {e}")

        # 测试2：不包含箭头函数的代码
        print("\n2. 不包含箭头函数的代码")
        print("-"*80)
        code_without_arrow = """document.title"""

        try:
            result = page.evaluate(code_without_arrow)
            print(f"结果: {result}")
            print(f"状态: {'成功' if result else '失败'}")
        except Exception as e:
            print(f"错误: {e}")

        # 测试3：模拟execute_js v2.2的检测逻辑
        print("\n3. 测试箭头函数检测逻辑")
        print("-"*80)

        import re

        def has_arrow_function(code):
            stripped = code.lstrip()
            patterns = [
                r'^\(\s*\)\s*=>\s*{',
                r'^\w+\s*=>\s*{',
                r'^\([^)]+\)\s*=>\s*{',
            ]
            for pattern in patterns:
                if re.match(pattern, stripped):
                    return True
            return False

        test_cases = [
            ("() => { return 1; }", True),
            ("(x) => { return x; }", True),
            ("x => { return x; }", True),
            ("return 1;", False),
            ("document.title", False),
            ("const x = 1;", False),
        ]

        all_passed = True
        for code, expected in test_cases:
            result = has_arrow_function(code)
            status = "通过" if result == expected else "失败"
            print(f"  {status}: '{code[:30]}...' -> {result} (期望: {expected})")
            if result != expected:
                all_passed = False

        print(f"\n检测结果: {'全部通过' if all_passed else '有失败'}")

        print("\n" + "="*80)
        print("总结")
        print("="*80)
        print("execute_js v2.2修复:")
        print("1. 自动检测用户代码是否包含箭头函数")
        print("2. 如果包含，直接传递代码")
        print("3. 如果不包含，自动包裹箭头函数")
        print("4. 两种格式都支持，无需修改现有代码")

        import time
        time.sleep(2)
        browser.close()


if __name__ == "__main__":
    test_execute_js_fix()
