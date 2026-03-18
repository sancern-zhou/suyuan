"""测试mu属性提取的时机问题

测试不同等待策略对mu属性提取的影响
"""
import sys
import os
import time
from urllib.parse import quote

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from playwright.sync_api import sync_playwright


def test_extraction_timing():
    """测试不同等待时机下的提取结果"""

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()

        search_query = "广东旭诚科技有限公司"
        search_url = f"https://www.baidu.com/s?wd={quote(search_query)}"

        print("="*80)
        print("测试不同等待策略对mu属性提取的影响")
        print("="*80)

        # 测试1：立即提取
        print("\n1. 立即提取（不等待）")
        page.goto(search_url)
        result1 = page.evaluate("""
            () => {
                const results = [];
                document.querySelectorAll('div.result[mu]').forEach(container => {
                    const mu = container.getAttribute('mu');
                    const h3 = container.querySelector('h3');
                    if (mu && h3) {
                        results.push({
                            title: h3.textContent.trim().substring(0, 30),
                            url: mu
                        });
                    }
                });
                return results;
            }
        """)
        print(f"   结果: {len(result1)} 个")
        if result1:
            print(f"   示例: {result1[0]}")

        # 测试2：domcontentloaded
        print("\n2. 等待domcontentloaded")
        page.goto(search_url)
        page.wait_for_load_state("domcontentloaded")
        result2 = page.evaluate("""
            () => {
                const results = [];
                document.querySelectorAll('div.result[mu]').forEach(container => {
                    const mu = container.getAttribute('mu');
                    const h3 = container.querySelector('h3');
                    if (mu && h3) {
                        results.push({
                            title: h3.textContent.trim().substring(0, 30),
                            url: mu
                        });
                    }
                });
                return results;
            }
        """)
        print(f"   结果: {len(result2)} 个")
        if result2:
            print(f"   示例: {result2[0]}")

        # 测试3：networkidle
        print("\n3. 等待networkidle")
        page.goto(search_url)
        page.wait_for_load_state("networkidle")
        result3 = page.evaluate("""
            () => {
                const results = [];
                document.querySelectorAll('div.result[mu]').forEach(container => {
                    const mu = container.getAttribute('mu');
                    const h3 = container.querySelector('h3');
                    if (mu && h3) {
                        results.push({
                            title: h3.textContent.trim().substring(0, 30),
                            url: mu
                        });
                    }
                });
                return results;
            }
        """)
        print(f"   结果: {len(result3)} 个")
        if result3:
            print(f"   示例: {result3[0]}")

        # 测试4：networkidle + 固定延迟
        print("\n4. 等待networkidle + 2秒延迟")
        page.goto(search_url)
        page.wait_for_load_state("networkidle")
        time.sleep(2)
        result4 = page.evaluate("""
            () => {
                const results = [];
                document.querySelectorAll('div.result[mu]').forEach(container => {
                    const mu = container.getAttribute('mu');
                    const h3 = container.querySelector('h3');
                    if (mu && h3) {
                        results.push({
                            title: h3.textContent.trim().substring(0, 30),
                            url: mu
                        });
                    }
                });
                return results;
            }
        """)
        print(f"   结果: {len(result4)} 个")
        if result4:
            print(f"   示例: {result4[0]}")

        # 测试5：等待特定元素
        print("\n5. 等待特定元素(div.result)")
        page.goto(search_url)
        try:
            page.wait_for_selector("div.result[mu]", timeout=10000)
            print("   元素已就绪")
        except:
            print("   等待超时")
        result5 = page.evaluate("""
            () => {
                const results = [];
                document.querySelectorAll('div.result[mu]').forEach(container => {
                    const mu = container.getAttribute('mu');
                    const h3 = container.querySelector('h3');
                    if (mu && h3) {
                        results.push({
                            title: h3.textContent.trim().substring(0, 30),
                            url: mu
                        });
                    }
                });
                return results;
            }
        """)
        print(f"   结果: {len(result5)} 个")
        if result5:
            print(f"   示例: {result5[0]}")

        # 总结
        print("\n" + "="*80)
        print("总结")
        print("="*80)
        print(f"1. 立即提取:              {len(result1)} 个结果")
        print(f"2. domcontentloaded:      {len(result2)} 个结果")
        print(f"3. networkidle:           {len(result3)} 个结果")
        print(f"4. networkidle + 延迟:    {len(result4)} 个结果")
        print(f"5. 等待特定元素:          {len(result5)} 个结果")

        best = max(enumerate([len(result1), len(result2), len(result3), len(result4), len(result5)], start=1), key=lambda x: x[1])
        print(f"\n推荐方法: 方法{best[0]} ({best[1]} 个结果)")

        # 保存详细结果
        report = {
            "method_1_immediate": result1,
            "method_2_domcontentloaded": result2,
            "method_3_networkidle": result3,
            "method_4_networkidle_with_delay": result4,
            "method_5_wait_for_selector": result5,
        }

        import json
        with open("D:\\溯源\\backend\\tests\\browser\\timing_test_report.json", "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

        print("\n详细报告已保存到: timing_test_report.json")

        time.sleep(3)
        browser.close()


if __name__ == "__main__":
    test_extraction_timing()
