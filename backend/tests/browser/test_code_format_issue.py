"""诊断代码格式问题

测试不同的代码传递方式
"""
import sys
import os
from urllib.parse import quote

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from playwright.sync_api import sync_playwright


def test_code_formats():
    """测试不同的代码格式"""

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()

        search_query = "广东旭诚科技有限公司"
        search_url = f"https://www.baidu.com/s?wd={quote(search_query)}"

        page.goto(search_url)
        page.wait_for_load_state("domcontentloaded")

        print("="*80)
        print("诊断代码格式问题")
        print("="*80)

        # 方法1：直接字符串（正确）
        print("\n1. 直接字符串格式（推荐）")
        print("-"*80)
        code1 = """() => {
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
        print(f"代码: {code1[:100]}...")
        try:
            result1 = page.evaluate(code1)
            print(f"结果类型: {type(result1)}")
            print(f"结果长度: {len(result1) if result1 else 0}")
            if result1:
                print(f"第一个结果: {result1[0]}")
        except Exception as e:
            print(f"错误: {e}")

        # 方法2：f-string包裹（错误！）
        print("\n2. f-string双重包裹（错误）")
        print("-"*80)
        inner_code = """() => {
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
        wrapped_code = f"() => {{ {inner_code} }}"
        print(f"代码开头: {wrapped_code[:150]}...")
        try:
            result2 = page.evaluate(wrapped_code)
            print(f"结果类型: {type(result2)}")
            print(f"结果长度: {len(result2) if result2 else 0}")
        except Exception as e:
            print(f"错误: {e}")

        # 方法3：模拟execute_js的包裹方式
        print("\n3. 模拟execute_js的包裹方式（当前实现）")
        print("-"*80)
        user_code = """const results = [];
    document.querySelectorAll('div.result[mu]').forEach(container => {
        const mu = container.getAttribute('mu');
        const h3 = container.querySelector('h3');
        if (mu && h3) {
            results.push({title: h3.textContent.trim(), url: mu});
        }
    });
    return results;"""
        wrapped = f"() => {{ {user_code} }}"
        print(f"代码开头: {wrapped[:150]}...")
        try:
            result3 = page.evaluate(wrapped)
            print(f"结果类型: {type(result3)}")
            print(f"结果长度: {len(result3) if result3 else 0}")
            if result3:
                print(f"第一个结果: {result3[0]}")
        except Exception as e:
            print(f"错误: {e}")

        print("\n" + "="*80)
        print("问题分析")
        print("="*80)

        print("\n方法1（直接字符串）:")
        print("  代码: page.evaluate(code)")
        print("  实际执行: () => { ... }")
        print("  状态: 正确")

        print("\n方法2（双重包裹）:")
        print("  代码: page.evaluate(f'() => {{ {code} }}')")
        print("  实际执行: () => { () => { ... } }")
        print("  状态: 错误！双重箭头函数")

        print("\n方法3（execute_js当前实现）:")
        print("  代码: page.evaluate(f'() => {{ {user_code} }}')")
        print("  实际执行: () => { const results = ...; }")
        print("  状态: 正确！用户代码不需要包含() =>")

        print("\n" + "="*80)
        print("结论")
        print("="*80)
        print("execute_js的实现是正确的！")
        print("用户代码应该直接写JavaScript逻辑，不要包含 () =>")
        print("\n正确示例:")
        print('  code="""')
        print('      const results = [];')
        print('      document.querySelectorAll(...).forEach(...)')
        print('      return results;')
        print('  """')
        print("\n错误示例:")
        print('  code="""() => { ... }"""  # 不要包含箭头函数！')

        import time
        time.sleep(3)
        browser.close()


if __name__ == "__main__":
    test_code_formats()
