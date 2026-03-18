"""百度反检测测试

测试不同的反检测策略来避免验证码
"""
import sys
import os
import time
from urllib.parse import quote

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from playwright.sync_api import sync_playwright


def test_with_anti_detection():
    """使用反检测策略进行测试"""

    print("="*80)
    print("百度反检测测试")
    print("="*80)

    with sync_playwright() as p:
        # 使用更多反检测选项
        browser = p.chromium.launch(
            headless=False,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--disable-dev-shm-usage',
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-web-security',
                '--disable-features=IsolateOrigins,site-per-process'
            ]
        )

        # 创建上下文时设置更多用户信息
        context = browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            locale='zh-CN',
            timezone_id='Asia/Shanghai',
            permissions=['geolocation', 'notifications']
        )

        page = context.new_page()

        # 添加初始化脚本来隐藏自动化特征
        page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
            Object.defineProperty(navigator, 'plugins', {
                get: () => [1, 2, 3, 4, 5]
            });
            Object.defineProperty(navigator, 'languages', {
                get: () => ['zh-CN', 'zh', 'en']
            });
            window.chrome = {
                runtime: {}
            };
        """)

        print("\n1. 导航到百度")
        search_query = "广东旭诚科技有限公司"
        search_url = f"https://www.baidu.com/s?wd={quote(search_query)}"

        print(f"URL: {search_url}")
        page.goto(search_url, timeout=30000)

        print(f"初始URL: {page.url}")
        print(f"页面标题: {page.title()}")

        # 检查是否被重定向到验证码页面
        if 'captcha' in page.url or 'verify' in page.url:
            print("\n⚠️ 仍然触发了验证码")
            print("这是百度严格的反爬虫机制")

            # 尝试手动操作提示
            print("\n建议:")
            print("1. 手动完成验证码")
            print("2. 或者使用其他数据源")
            print("3. 或者使用API接口获取数据")

            print("\n按Enter键继续（完成验证码后）...")
            # input()  # 移除自动运行

            time.sleep(5)

        # 等待页面加载
        print("\n2. 等待页面加载")
        try:
            page.wait_for_load_state("domcontentloaded", timeout=10000)
            print("等待domcontentloaded: 成功")
        except:
            print("等待超时")

        # 检查页面状态
        print("\n3. 检查页面状态")
        page_check = page.evaluate("""
            () => {
                return {
                    readyState: document.readyState,
                    resultCount: document.querySelectorAll('div.result').length,
                    muResultCount: document.querySelectorAll('div.result[mu]').length,
                    title: document.title,
                    url: window.location.href
                };
            }
        """)

        print(f"就绪状态: {page_check['readyState']}")
        print(f"结果元素数: {page_check['resultCount']}")
        print(f"有mu属性的结果: {page_check['muResultCount']}")
        print(f"页面标题: {page_check['title']}")
        print(f"当前URL: {page_check['url']}")

        # 如果到达了搜索结果页面，尝试提取
        if page_check['muResultCount'] > 0:
            print("\n4. 成功到达搜索结果页面！")

            # 测试execute_js
            result = page.evaluate("""
                () => {
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
                }
            """)

            print(f"提取结果: {len(result)} 个")
            if result:
                for i, item in enumerate(result[:3]):
                    print(f"  [{i+1}] {item['title'][:50]}...")
                    print(f"      URL: {item['url']}")
        else:
            print("\n4. 未到达搜索结果页面")

            # 检查页面内容
            content = page.evaluate("""
                () => {
                    return {
                        bodyText: document.body.textContent.substring(0, 500),
                        hasForm: document.querySelectorAll('form').length > 0,
                        hasInput: document.querySelectorAll('input').length > 0
                    };
                }
            """)

            print(f"页面内容: {content['bodyText'][:200]}...")
            print(f"有表单: {content['hasForm']}")
            print(f"有输入框: {content['hasInput']}")

        print("\n" + "="*80)
        print("总结")
        print("="*80)

        if page_check['muResultCount'] > 0:
            print("状态: 成功！反检测策略有效")
            print("execute_js应该能正常工作")
        else:
            print("状态: 失败 - 百度反爬虫拦截")
            print("\n建议:")
            print("1. 使用百度API接口（如果有权限）")
            print("2. 使用其他搜索引擎的数据源")
            print("3. 添加更复杂的反检测策略")
            print("4. 使用代理IP池")

        time.sleep(3)
        context.close()
        browser.close()


if __name__ == "__main__":
    test_with_anti_detection()
