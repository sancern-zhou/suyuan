"""必应搜索简化测试

验证必应搜索是否可行
"""
import sys
import os
import time
from urllib.parse import quote

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from playwright.sync_api import sync_playwright


def test_bing_simple():
    """简化版必应测试"""

    print("必应搜索简化测试")
    print("="*80)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()

        # 搜索旭诚科技
        print("\n1. 搜索旭诚科技")
        search_url = f"https://www.bing.com/search?q={quote('旭诚科技 环境监测 广东')}"
        page.goto(search_url, timeout=30000)

        print(f"URL: {page.url}")
        print(f"标题: {page.title()}")

        # 检查是否触发验证码
        if 'captcha' in page.url.lower():
            print("触发验证码")
            return

        # 等待页面加载
        try:
            page.wait_for_load_state("domcontentloaded", timeout=10000)
        except:
            pass

        time.sleep(3)

        # 检查搜索结果
        result_count = page.evaluate("document.querySelectorAll('li.b_algo').length")
        print(f"搜索结果数量: {result_count}")

        if result_count > 0:
            # 提取前5个结果
            results = page.evaluate("""
                () => {
                    const results = [];
                    document.querySelectorAll('li.b_algo').forEach(item => {
                        const link = item.querySelector('a');
                        if (link) {
                            results.push({
                                title: link.textContent.trim().substring(0, 60),
                                url: link.getAttribute('href')
                            });
                        }
                    });
                    return results.slice(0, 5);
                }
            """)

            print("\n前5个结果:")
            for i, r in enumerate(results):
                print(f"{i+1}. {r['title']}")
                print(f"   {r['url']}")

            # 检查是否找到目标网站
            found_target = False
            for r in results:
                if 'suncereltd' in r['url'].lower() or '旭诚' in r['title']:
                    print(f"\n找到目标: {r['title']}")
                    print(f"URL: {r['url']}")
                    found_target = True
                    break

            if not found_target:
                print("\n未找到旭诚科技官网")
                print("但搜索功能正常")

        time.sleep(3)
        browser.close()


if __name__ == "__main__":
    test_bing_simple()
