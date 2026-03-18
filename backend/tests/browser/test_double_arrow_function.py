"""测试双重箭头函数问题

验证execute_js的实现是否会与包含() =>的用户代码冲突
"""
import sys
import os
from urllib.parse import quote

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from playwright.sync_api import sync_playwright


def test_double_arrow_issue():
    """测试双重箭头函数问题"""

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()

        search_query = "广东旭诚科技有限公司"
        search_url = f"https://www.baidu.com/s?wd={quote(search_query)}"
        page.goto(search_url)
        page.wait_for_load_state("domcontentloaded")

        print("="*80)
        print("测试双重箭头函数问题")
        print("="*80)

        # 测试1：用户代码包含() =>（模拟LLM输出）
        print("\n1. 用户代码包含() =>（当前问题）")
        print("-"*80)
        user_code_with_arrow = """() => {
    const results = [];
    document.querySelectorAll('div.result[mu]').forEach(container => {
        const mu = container.getAttribute('mu');
        const h3 = container.querySelector('h3');
        if (mu && h3) {
            results.push({title: h3.textContent.trim(), url: mu});
        }
    });
    return results;
}"""

        # 模拟execute_js的实现
        wrapped_code = f"() => {{ {user_code_with_arrow} }}"
        print(f"包裹后的代码: {wrapped_code[:150]}...")

        try:
            result1 = page.evaluate(wrapped_code)
            print(f"结果类型: {type(result1)}")
            print(f"结果: {result1}")
            if isinstance(result1, list):
                print(f"数组长度: {len(result1)}")
        except Exception as e:
            print(f"错误: {e}")

        # 测试2：用户代码不包含() =>（正确）
        print("\n2. 用户代码不包含() =>（正确格式）")
        print("-"*80)
        user_code_without_arrow = """const results = [];
    document.querySelectorAll('div.result[mu]').forEach(container => {
        const mu = container.getAttribute('mu');
        const h3 = container.querySelector('h3');
        if (mu && h3) {
            results.push({title: h3.textContent.trim(), url: mu});
        }
    });
    return results;"""

        # 模拟execute_js的实现
        wrapped_code2 = f"() => {{ {user_code_without_arrow} }}"
        print(f"包裹后的代码: {wrapped_code2[:150]}...")

        try:
            result2 = page.evaluate(wrapped_code2)
            print(f"结果类型: {type(result2)}")
            print(f"数组长度: {len(result2) if result2 else 0}")
            if result2 and len(result2) > 0:
                print(f"第一个结果: {result2[0]}")
        except Exception as e:
            print(f"错误: {e}")

        # 测试3：直接传递（不包裹）
        print("\n3. 直接传递用户代码（不包裹）")
        print("-"*80)
        try:
            result3 = page.evaluate(user_code_with_arrow)
            print(f"结果类型: {type(result3)}")
            print(f"数组长度: {len(result3) if result3 else 0}")
            if result3 and len(result3) > 0:
                print(f"第一个结果: {result3[0]}")
        except Exception as e:
            print(f"错误: {e}")

        print("\n" + "="*80)
        print("问题分析")
        print("="*80)

        print("\n当前execute_js实现:")
        print("  1. 总是包裹: page.evaluate(f'() => {{ {code} }}')")
        print("  2. 如果用户代码包含() =>，会造成双重箭头函数")

        print("\n双重箭头函数的执行结果:")
        print("  () => { () => { ... } }")
        print("  外层函数执行后，返回内层函数对象")
        print("  不会执行内层函数的代码体")

        print("\n解决方案:")
        print("  1. 检测用户代码是否包含() =>")
        print("  2. 如果包含，直接传递用户代码")
        print("  3. 如果不包含，才进行包裹")

        import time
        time.sleep(3)
        browser.close()


if __name__ == "__main__":
    test_double_arrow_issue()
