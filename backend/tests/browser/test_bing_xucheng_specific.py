"""测试必应搜索旭诚科技

使用更具体的搜索词来验证必应能否找到目标公司
"""
import sys
import os
import time
from urllib.parse import quote

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from playwright.sync_api import sync_playwright


def test_bing_search_xucheng():
    """测试必应搜索旭诚科技"""

    print("="*80)
    print("必应搜索旭诚科技测试")
    print("="*80)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        )
        page = context.new_page()

        # 测试多个搜索词
        search_queries = [
            "旭诚科技 环境监测",
            "广东旭诚科技有限公司 官网",
            "suncereltd 旭诚",
            "旭诚科技 广东"
        ]

        for query in search_queries:
            print(f"\n搜索词: {query}")
            print("-"*80)

            bing_url = f"https://www.bing.com/search?q={quote(query)}"
            page.goto(bing_url, timeout=30000)
            page.wait_for_load_state("domcontentloaded")
            time.sleep(2)

            # 提取结果
            results = page.evaluate("""
                () => {
                    const results = [];
                    document.querySelectorAll('li.b_algo').forEach(item => {
                        const h2 = item.querySelector('h2');
                        const link = h2 ? h2.querySelector('a') : null;
                        if (link) {
                            const href = link.getAttribute('href');
                            const title = link.textContent.trim();
                            if (href && title) {
                                results.push({title: title, url: href});
                            }
                        }
                    });
                    return results.slice(0, 5);
                }
            """)

            print(f"找到 {len(results)} 个结果:")
            for i, r in enumerate(results):
                print(f"  [{i+1}] {r['title'][:60]}...")
                if 'suncereltd' in r['url'].lower() or '旭诚' in r['title']:
                    print(f"       URL: {r['url']} ← 目标网站!")
                else:
                    print(f"       URL: {r['url'][:60]}...")

        # 测试旭诚科技官网URL
        print("\n" + "="*80)
        print("直接访问旭诚科技官网")
        print("="*80)

        page.goto("https://www.suncereltd.com/", timeout=30000)
        print(f"页面标题: {page.title()}")
        print(f"当前URL: {page.url}")

        page_info = page.evaluate("""
            () => {
                return {
                    hasH1: !!document.querySelector('h1'),
                    h1Text: document.querySelector('h1')?.textContent || '',
                    bodyText: document.body.textContent.substring(0, 300)
                };
            }
        """)

        print(f"H1标题: {page_info['h1Text']}")
        print(f"页面内容: {page_info['bodyText'][:150]}...")

        time.sleep(3)
        context.close()
        browser.close()


if __name__ == "__main__":
    test_bing_search_xucheng()
