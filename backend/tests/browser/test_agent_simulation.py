"""完整Agent操作模拟测试

模拟Agent的完整操作流程：
1. 启动浏览器
2. 导航到百度搜索
3. 等待页面加载
4. 执行execute_js提取mu属性
5. 分析每个步骤的结果
"""
import sys
import os
import time
import json
from urllib.parse import quote

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from playwright.sync_api import sync_playwright


def print_section(title):
    print("\n" + "="*80)
    print(f" {title}")
    print("="*80)


def simulate_agent_workflow():
    """模拟Agent的完整工作流程"""

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()

        print_section("AGENT工作流程模拟")
        print("模拟LLM使用浏览器工具提取百度mu属性")

        # 步骤1：导航
        print_section("步骤1: 导航到搜索页面")
        search_query = "广东旭诚科技有限公司"
        search_url = f"https://www.baidu.com/s?wd={quote(search_query)}"

        print(f"URL: {search_url}")
        page.goto(search_url)

        print(f"页面标题: {page.title()}")
        print(f"当前URL: {page.url}")

        # 步骤2：等待页面加载
        print_section("步骤2: 等待页面加载")

        try:
            page.wait_for_load_state("domcontentloaded", timeout=10000)
            print("等待domcontentloaded: 成功")
        except Exception as e:
            print(f"等待domcontentloaded: 失败 - {e}")

        time.sleep(1)  # 额外等待

        # 步骤3：检查页面状态
        print_section("步骤3: 检查页面状态")

        page_check = page.evaluate("""
            () => {
                return {
                    readyState: document.readyState,
                    resultCount: document.querySelectorAll('div.result').length,
                    muResultCount: document.querySelectorAll('div.result[mu]').length,
                    bodyClasses: document.body.className
                };
            }
        """)

        print(f"就绪状态: {page_check['readyState']}")
        print(f"结果元素数: {page_check['resultCount']}")
        print(f"有mu属性的结果: {page_check['muResultCount']}")

        if page_check['muResultCount'] == 0:
            print("\n警告：没有找到mu属性！可能原因:")
            print("1. 百度反爬虫检测")
            print("2. 页面结构变化")
            print("3. 页面未完全加载")

        # 步骤4：执行execute_js（模拟LLM代码）
        print_section("步骤4: 执行execute_js")

        # 模拟LLM可能生成的两种代码格式
        test_cases = [
            {
                "name": "格式1: 包含箭头函数",
                "code": """() => {
    const keyword = '旭诚科技';
    const results = [];
    document.querySelectorAll('div.result[mu]').forEach(container => {
        const mu = container.getAttribute('mu');
        const h3 = container.querySelector('h3');
        const title = h3 ? h3.textContent.trim() : '';
        if (mu && title.includes(keyword)) {
            results.push({title: title, url: mu});
        }
    });
    return results[0] || null;
}"""
            },
            {
                "name": "格式2: 不包含箭头函数",
                "code": """const keyword = '旭诚科技';
const results = [];
document.querySelectorAll('div.result[mu]').forEach(container => {
    const mu = container.getAttribute('mu');
    const h3 = container.querySelector('h3');
    const title = h3 ? h3.textContent.trim() : '';
    if (mu && title.includes(keyword)) {
        results.push({title: title, url: mu});
    }
});
return results[0] || null;"""
            }
        ]

        for i, test_case in enumerate(test_cases):
            print(f"\n测试 {i+1}: {test_case['name']}")
            print("-" * 80)

            # 模拟execute_js的检测和处理
            import re

            code = test_case['code']
            stripped = code.lstrip()
            has_arrow = bool(re.match(r'^\(\s*\)\s*=>\s*{', stripped))

            print(f"检测箭头函数: {has_arrow}")

            if has_arrow:
                # 直接执行（v2.2方式）
                print("执行方式: 直接传递代码")
                try:
                    result = page.evaluate(code)
                    print(f"结果类型: {type(result).__name__}")
                    print(f"结果: {result}")
                except Exception as e:
                    print(f"执行错误: {e}")
            else:
                # 包裹箭头函数
                print("执行方式: 包裹箭头函数")
                wrapped = f"() => {{ {code} }}"
                try:
                    result = page.evaluate(wrapped)
                    print(f"结果类型: {type(result).__name__}")
                    print(f"结果: {result}")
                except Exception as e:
                    print(f"执行错误: {e}")

        # 步骤5：直接测试（不通过execute_js）
        print_section("步骤5: 直接测试（不通过execute_js）")

        print("\n直接执行提取代码:")
        direct_result = page.evaluate("""
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

        print(f"结果类型: {type(direct_result)}")
        if direct_result:
            print(f"结果数量: {len(direct_result)}")
            if len(direct_result) > 0:
                print(f"第一个结果: {direct_result[0]}")
        else:
            print("结果为空或null")

        # 步骤6：调试信息
        print_section("步骤6: 调试信息")

        # 检查可能的百度拦截
        bot_check = page.evaluate("""
            () => {
                // 检查常见的反爬虫迹象
                return {
                    hasNoscript: document.querySelectorAll('noscript').length > 0,
                    hasIframe: document.querySelectorAll('iframe').length > 0,
                    bodyContent: document.body.textContent.substring(0, 200),
                    resultElements: Array.from(document.querySelectorAll('div.result')).slice(0, 2).map(el => ({
                        className: el.className,
                        hasMu: el.hasAttribute('mu'),
                        muValue: el.getAttribute('mu'),
                        innerHTML: el.innerHTML.substring(0, 200)
                    }))
                };
            }
        """)

        print(f"noscript标签: {bot_check['hasNoscript']}")
        print(f"iframe标签: {bot_check['hasIframe']}")
        print(f"页面内容预览: {bot_check['bodyContent'][:100]}...")
        print(f"\n结果元素详情:")
        for i, elem in enumerate(bot_check['resultElements']):
            print(f"  元素{i+1}:")
            print(f"    className: {elem['className']}")
            print(f"    hasMu: {elem['hasMu']}")
            print(f"    muValue: {elem['muValue']}")

        # 总结
        print_section("总结")

        success = direct_result and len(direct_result) > 0

        if success:
            print("状态: 成功提取mu属性")
            print(f"提取到 {len(direct_result)} 个结果")
        else:
            print("状态: 提取失败")
            print("\n可能原因:")
            print("1. 百度反爬虫拦截")
            print("2. 页面结构变化")
            print("3. execute_js实现问题")
            print("4. 页面加载时机问题")

        # 保存报告
        report = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "success": success,
            "resultCount": len(direct_result) if direct_result else 0,
            "pageCheck": page_check,
            "botCheck": bot_check,
            "directResult": direct_result if direct_result else None
        }

        report_file = "D:\\溯源\\backend\\tests\\browser\\agent_simulation_report.json"
        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

        print(f"\n完整报告已保存到: {report_file}")

        print("\n等待3秒后关闭浏览器...")
        time.sleep(3)

        browser.close()


if __name__ == "__main__":
    print("Agent工作流程模拟测试")
    print("="*80)
    print("这个测试将:")
    print("1. 模拟LLM使用浏览器工具")
    print("2. 测试不同的execute_js代码格式")
    print("3. 分析mu属性提取失败的原因")
    print("\n开始测试...\n")

    simulate_agent_workflow()
