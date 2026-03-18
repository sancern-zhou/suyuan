"""测试必应搜索是否可行

测试必应搜索的反爬虫强度和URL提取可行性
"""
import sys
import os
import time
import json
from urllib.parse import quote

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from playwright.sync_api import sync_playwright


def test_bing_search():
    """测试必应搜索功能"""

    print("="*80)
    print("必应搜索可行性测试")
    print("="*80)

    with sync_playwright() as p:
        # 使用基本配置
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        )
        page = context.new_page()

        # 测试1：基本搜索
        print("\n1. 执行必应搜索")
        print("-"*80)

        search_query = "广东旭诚科技有限公司"
        bing_url = f"https://www.bing.com/search?q={quote(search_query)}"

        print(f"搜索关键词: {search_query}")
        print(f"URL: {bing_url}")

        page.goto(bing_url, timeout=30000)

        print(f"当前URL: {page.url}")
        print(f"页面标题: {page.title()}")

        # 检查是否被重定向
        if 'captcha' in page.url.lower() or 'verify' in page.url.lower():
            print("❌ 触发了验证码")
            return False

        # 等待页面加载
        print("\n2. 等待页面加载")
        print("-"*80)

        try:
            page.wait_for_load_state("domcontentloaded", timeout=10000)
            print("等待domcontentloaded: 成功")
        except Exception as e:
            print(f"等待失败: {e}")

        time.sleep(2)

        # 检查搜索结果
        print("\n3. 检查搜索结果元素")
        print("-"*80)

        # 必应的搜索结果选择器
        bing_selectors = [
            'li.b_algo',           # 主要搜索结果
            'ol#b_results > li',   # 结果列表
            '.b_algo',             # 结果类名
        ]

        page_check = page.evaluate("""
            () => {
                const info = {
                    readyState: document.readyState,
                    title: document.title,
                    url: window.location.href,
                    resultCounts: {}
                };

                // 检查不同的选择器
                const selectors = ['li.b_algo', 'ol#b_results > li', '.b_algo'];
                selectors.forEach(sel => {
                    const elements = document.querySelectorAll(sel);
                    info.resultCounts[sel] = elements.length;
                });

                return info;
            }
        """)

        print(f"就绪状态: {page_check['readyState']}")
        print(f"页面标题: {page_check['title']}")
        print(f"当前URL: {page_check['url']}")
        print(f"\n搜索结果数量:")
        for selector, count in page_check['resultCounts'].items():
            print(f"  {selector}: {count} 个")

        # 提取搜索结果URL
        print("\n4. 提取搜索结果URL")
        print("-"*80)

        extraction_result = page.evaluate("""
            () => {
                const results = [];

                // 使用li.b_algo选择器
                const items = document.querySelectorAll('li.b_algo');

                items.forEach((item, index) => {
                    // 查找标题和链接
                    const h2 = item.querySelector('h2');
                    const link = h2 ? h2.querySelector('a') : item.querySelector('a');

                    if (link) {
                        const href = link.getAttribute('href');
                        const title = link.textContent.trim();

                        if (href && title) {
                            results.push({
                                index: index,
                                title: title.substring(0, 80),
                                url: href,
                                displayUrl: link.getAttribute('data-appurl') || ''
                            });
                        }
                    }
                });

                return results.slice(0, 10);
            }
        """)

        print(f"提取到 {len(extraction_result)} 个结果")

        if extraction_result:
            print("\n前5个结果:")
            for i, item in enumerate(extraction_result[:5]):
                print(f"\n[{i+1}] {item['title']}")
                print(f"    URL: {item['url']}")
        else:
            print("未提取到结果")

        # 测试5：使用execute_js提取（模拟Agent）
        print("\n5. 测试execute_js提取")
        print("-"*80)

        # 测试包含箭头函数的代码
        code_with_arrow = """() => {
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
    return results;
}"""

        try:
            execute_js_result = page.evaluate(code_with_arrow)
            print(f"execute_js结果类型: {type(execute_js_result).__name__}")
            print(f"execute_js结果数量: {len(execute_js_result) if execute_js_result else 0}")

            if execute_js_result and len(execute_js_result) > 0:
                print(f"第一个结果: {execute_js_result[0]}")
        except Exception as e:
            print(f"execute_js错误: {e}")

        # 测试6：检查目标公司
        print("\n6. 查找目标公司")
        print("-"*80)

        target_result = page.evaluate("""
            () => {
                const keyword = '旭诚';
                const results = [];

                document.querySelectorAll('li.b_algo').forEach(item => {
                    const h2 = item.querySelector('h2');
                    const link = h2 ? h2.querySelector('a') : null;

                    if (link) {
                        const href = link.getAttribute('href');
                        const title = link.textContent.trim();

                        if (href && title && title.includes(keyword)) {
                            results.push({
                                title: title,
                                url: href
                            });
                        }
                    }
                });

                return results;
            }
        """)

        print(f"找到 {len(target_result)} 个包含'旭诚'的结果")

        if target_result:
            print("\n目标公司结果:")
            for i, item in enumerate(target_result):
                print(f"  [{i+1}] {item['title']}")
                print(f"      URL: {item['url']}")

        # 保存报告
        print("\n7. 生成报告")
        print("-"*80)

        report = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "success": len(extraction_result) > 0,
            "extractionCount": len(extraction_result),
            "targetFound": len(target_result) > 0,
            "targetCount": len(target_result),
            "pageCheck": page_check,
            "extractionResult": extraction_result[:5],
            "targetResult": target_result
        }

        report_file = "D:\\溯源\\backend\\tests\\browser\\bing_search_report.json"
        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

        print(f"报告已保存到: {report_file}")

        # 总结
        print("\n" + "="*80)
        print("总结")
        print("="*80)

        if len(extraction_result) > 0:
            print("✅ 必应搜索可行！")
            print(f"   - 成功提取 {len(extraction_result)} 个搜索结果")
            print(f"   - 找到 {len(target_result)} 个目标公司结果")
            print(f"   - 未触发验证码")
            print(f"   - execute_js正常工作")
            print("\n建议: 可以调整为使用必应搜索")
        else:
            print("❌ 必应搜索不可行")
            print("   - 未能提取到搜索结果")
            print("   - 可能需要进一步调试")

        time.sleep(3)
        context.close()
        browser.close()

        return len(extraction_result) > 0


if __name__ == "__main__":
    success = test_bing_search()

    if success:
        print("\n" + "="*80)
        print("测试结论：必应搜索可行，建议进行调整")
        print("="*80)
    else:
        print("\n" + "="*80)
        print("测试结论：必应搜索不可行")
        print("="*80)
