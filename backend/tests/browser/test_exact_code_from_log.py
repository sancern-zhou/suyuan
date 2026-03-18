"""使用日志中的精确代码进行测试

对比：
1. 日志中的代码格式
2. 推荐的代码格式
"""
import sys
import os
from urllib.parse import quote

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from playwright.sync_api import sync_playwright


def test_exact_code():
    """测试精确代码"""

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()

        search_query = "广东旭诚科技有限公司"
        search_url = f"https://www.baidu.com/s?wd={quote(search_query)}"

        page.goto(search_url)

        print("="*80)
        print("测试代码对比")
        print("="*80)

        # 代码1：日志中的代码（可能有问题）
        code1 = """() => {
    const results = [];
    // 直接查询所有包含mu属性的搜索结果
    document.querySelectorAll('div.result[mu]').forEach(container => {
        const mu = container.getAttribute('mu');
        const h3 = container.querySelector('h3');
        if (mu && h3) {
            results.push({
                title: h3.textContent.trim(),
                url: mu
            });
        }
    });
    return results;
}"""

        print("\n1. 日志中的代码")
        print("-"*80)
        try:
            result1 = page.evaluate(f"() => {{ {code1} }}")
            print(f"结果: {result1}")
            print(f"类型: {type(result1)}")
            print(f"长度: {len(result1) if result1 else 0}")
        except Exception as e:
            print(f"错误: {e}")

        # 代码2：推荐的格式
        code2 = """() => {
    const results = [];
    document.querySelectorAll('div.result[mu]').forEach(container => {
        const mu = container.getAttribute('mu');
        const h3 = container.querySelector('h3');
        if (mu && h3) {
            results.push({
                title: h3.textContent.trim(),
                url: mu
            });
        }
    });
    return results;
}"""

        print("\n2. 推荐格式（无注释）")
        print("-"*80)
        try:
            result2 = page.evaluate(f"() => {{ {code2} }}")
            print(f"结果: {result2}")
            print(f"类型: {type(result2)}")
            print(f"长度: {len(result2) if result2 else 0}")
        except Exception as e:
            print(f"错误: {e}")

        # 代码3：最简格式
        print("\n3. 最简格式（压缩）")
        print("-"*80)
        try:
            result3 = page.evaluate("""
                () => {
                    const results = [];
                    document.querySelectorAll('div.result[mu]').forEach(container => {
                        const mu = container.getAttribute('mu');
                        const h3 = container.querySelector('h3');
                        if (mu && h3) {
                            results.push({title: h3.textContent.trim(), url: mu});
                        }
                    });
                    return results;
                }
            """)
            print(f"结果: {result3}")
            print(f"类型: {type(result3)}")
            print(f"长度: {len(result3) if result3 else 0}")
        except Exception as e:
            print(f"错误: {e}")

        print("\n" + "="*80)
        print("总结")
        print("="*80)

        if result1 and len(result1) > 0:
            print("✅ 代码1（日志格式）成功")
        else:
            print("❌ 代码1（日志格式）失败")

        if result2 and len(result2) > 0:
            print("✅ 代码2（推荐格式）成功")
        else:
            print("❌ 代码2（推荐格式）失败")

        if result3 and len(result3) > 0:
            print("✅ 代码3（最简格式）成功")
        else:
            print("❌ 代码3（最简格式）失败")

        # 检查是否有特殊字符问题
        print("\n" + "="*80)
        print("代码分析")
        print("="*80)

        print(f"\n代码1长度: {len(code1)} 字符")
        print(f"代码1包含注释: {'是' if '//' in code1 else '否'}")
        print(f"代码1包含中文注释: {'是' if '直接查询' in code1 else '否'}")

        import time
        time.sleep(3)
        browser.close()


if __name__ == "__main__":
    test_exact_code()
