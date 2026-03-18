"""调试百度搜索结果页面结构

这个脚本帮助诊断：
1. 百度搜索结果的DOM结构
2. mu属性的存在情况
3. 可能的替代属性
4. 页面加载状态
"""
import sys
import os
import time
import json
from urllib.parse import quote

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from playwright.sync_api import sync_playwright


def print_section(title):
    """打印分节标题"""
    print("\n" + "="*80)
    print(f" {title}")
    print("="*80)


def debug_baidu_page():
    """调试百度搜索结果页面"""

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()

        # 导航到百度搜索
        search_query = "广东旭诚科技有限公司"
        search_url = f"https://www.baidu.com/s?wd={quote(search_query)}"

        print_section("1. 导航到百度搜索")
        print(f"URL: {search_url}")
        page.goto(search_url)

        print("\n等待页面加载...")
        page.wait_for_load_state("domcontentloaded")
        time.sleep(2)  # 额外等待动态内容

        print_section("2. 页面基本信息")
        page_info = page.evaluate("""
            () => {
                return {
                    title: document.title,
                    url: window.location.href,
                    readyState: document.readyState,
                    body_classes: document.body.className,
                    document_element_height: document.documentElement.scrollHeight,
                    viewport_height: window.innerHeight
                };
            }
        """)
        print(f"标题: {page_info['title']}")
        print(f"URL: {page_info['url']}")
        print(f"就绪状态: {page_info['readyState']}")
        print(f"页面高度: {page_info['document_element_height']}px")
        print(f"视口高度: {page_info['viewport_height']}px")

        print_section("3. 搜索结果容器分析")

        # 尝试不同的选择器
        selectors = [
            'div.result',
            'div.result[mu]',
            'div[tpl]',
            'div.c-container',
            'div[class*="result"]',
            'div[class*="container"]',
        ]

        for selector in selectors:
            try:
                count = page.locator(selector).count()
                print(f"\n选择器: '{selector}'")
                print(f"  找到元素: {count} 个")

                if count > 0:
                    # 获取第一个元素的详细信息
                    first = page.locator(selector).first
                    html = first.evaluate("el => el.outerHTML.substring(0, 200)")
                    print(f"  第一个元素HTML预览: {html}...")
            except Exception as e:
                print(f"  错误: {e}")

        print_section("4. mu属性详细分析")

        mu_info = page.evaluate("""
            () => {
                const info = {
                    total_results: 0,
                    with_mu: 0,
                    without_mu: 0,
                    mu_values: [],
                    sample_structure: []
                };

                // 查找所有可能的结果容器
                const containers = document.querySelectorAll('div.result');

                info.total_results = containers.length;

                containers.forEach((container, index) => {
                    const mu = container.getAttribute('mu');
                    const h3 = container.querySelector('h3');
                    const a = container.querySelector('a');

                    if (mu) {
                        info.with_mu++;
                        info.mu_values.push({
                            index: index,
                            mu: mu.substring(0, 80),
                            title: h3 ? h3.textContent.trim().substring(0, 50) : 'N/A'
                        });

                        if (info.mu_values.length <= 3) {
                            info.sample_structure.push({
                                index: index,
                                has_mu: true,
                                mu_value: mu,
                                classes: container.className,
                                id: container.id,
                                attributes: Array.from(container.attributes).map(attr => ({
                                    name: attr.name,
                                    value: attr.value.substring(0, 50)
                                }))
                            });
                        }
                    } else {
                        info.without_mu++;
                    }
                });

                return info;
            }
        """)

        print(f"总结果数: {mu_info['total_results']}")
        print(f"有mu属性: {mu_info['with_mu']}")
        print(f"无mu属性: {mu_info['without_mu']}")

        if mu_info['mu_values']:
            print(f"\nmu属性值示例 (前5个):")
            for item in mu_info['mu_values'][:5]:
                print(f"  [{item['index']}] {item['title']}")
                print(f"      mu: {item['mu']}")

        print_section("5. 结果容器结构样本")

        if mu_info['sample_structure']:
            for sample in mu_info['sample_structure'][:2]:
                print(f"\n样本 #{sample['index']}:")
                print(f"  类名: {sample['classes']}")
                print(f"  ID: {sample['id']}")
                print(f"  mu值: {sample['mu_value']}")
                print(f"  所有属性:")
                for attr in sample['attributes']:
                    print(f"    - {attr['name']}: {attr['value']}")

        print_section("6. 替代方法：查找链接")

        links_info = page.evaluate("""
            () => {
                const info = {
                    total_links: 0,
                    external_links: [],
                    baidu_links: []
                };

                // 查找结果区域的所有链接
                const results = document.querySelectorAll('div.result');

                results.forEach((container, idx) => {
                    const links = container.querySelectorAll('a');
                    const h3 = container.querySelector('h3');

                    links.forEach(link => {
                        const href = link.getAttribute('href');
                        if (href) {
                            info.total_links++;

                            const link_info = {
                                container_index: idx,
                                title: h3 ? h3.textContent.trim().substring(0, 30) : 'N/A',
                                href: href.substring(0, 80),
                                text: link.textContent.trim().substring(0, 30),
                                has_data_click: link.hasAttribute('data-click')
                            };

                            if (href.includes('baidu.com')) {
                                info.baidu_links.push(link_info);
                            } else {
                                info.external_links.push(link_info);
                            }
                        }
                    });
                });

                // 限制数量
                info.external_links = info.external_links.slice(0, 10);
                info.baidu_links = info.baidu_links.slice(0, 5);

                return info;
            }
        """)

        print(f"总链接数: {links_info['total_links']}")
        print(f"外部链接: {len(links_info['external_links'])}")

        if links_info['external_links']:
            print(f"\n外部链接示例:")
            for link in links_info['external_links'][:5]:
                print(f"  [{link['container_index']}] {link['title']}")
                print(f"      href: {link['href']}")
                print(f"      text: {link['text']}")

        print_section("7. 推荐的选择器和提取方法")

        recommendations = []

        if mu_info['with_mu'] > 0:
            recommendations.append({
                method: "mu属性",
                selector: "div.result[mu]",
                confidence: "高",
                code: """document.querySelectorAll('div.result[mu]').forEach(container => {
    const mu = container.getAttribute('mu');
    // 使用mu值
})"""
            })

        # 检查data-link属性
        data_link_count = page.locator('div.result a[data-link]').count()
        if data_link_count > 0:
            recommendations.append({
                method: "data-link属性",
                selector: "div.result a[data-link]",
                confidence: "中",
                note: f"找到{data_link_count}个data-link链接"
            })

        # 检查其他可能的属性
        other_attrs = page.evaluate("""
            () => {
                const attrs = new Set();
                document.querySelectorAll('div.result').forEach(container => {
                    Array.from(container.attributes).forEach(attr => {
                        if (attr.name.startsWith('data-') || attr.name === 'mu' || attr.name === 'tpl') {
                            attrs.add(attr.name);
                        }
                    });
                });
                return Array.from(attrs);
            }
        """)

        print("\n找到的数据属性:")
        for attr in other_attrs:
            print(f"  - {attr}")

        print("\n推荐提取方法:")
        if recommendations:
            for i, rec in enumerate(recommendations, 1):
                print(f"\n{i}. {rec['method']} (置信度: {rec['confidence']})")
                print(f"   选择器: {rec['selector']}")
                if 'code' in rec:
                    print(f"   代码示例:")
                    for line in rec['code'].split('\n'):
                        print(f"     {line}")
                if 'note' in rec:
                    print(f"   说明: {rec['note']}")
        else:
            print("\n未找到可靠的提取方法，可能需要:")
            print("1. 等待更长时间让页面完全加载")
            print("2. 检查是否需要滚动页面触发懒加载")
            print("3. 使用快照获取refs")

        print_section("8. 实际提取测试")

        # 测试实际提取
        test_result = page.evaluate("""
            () => {
                const results = [];

                // 方法1：mu属性
                document.querySelectorAll('div.result[mu]').forEach(container => {
                    const mu = container.getAttribute('mu');
                    const h3 = container.querySelector('h3');
                    if (mu && h3) {
                        results.push({
                            method: 'mu',
                            title: h3.textContent.trim(),
                            url: mu
                        });
                    }
                });

                // 方法2：如果没有mu，尝试第一个链接
                if (results.length === 0) {
                    document.querySelectorAll('div.result').forEach(container => {
                        const h3 = container.querySelector('h3');
                        const link = h3?.querySelector('a');
                        if (link) {
                            const href = link.getAttribute('href');
                            if (href && !href.includes('baidu.com')) {
                                results.push({
                                    method: 'first_link',
                                    title: h3.textContent.trim(),
                                    url: href
                                });
                            }
                        }
                    });
                }

                return results.slice(0, 5);
            }
        """)

        print(f"提取结果: {len(test_result)} 个")
        for i, item in enumerate(test_result):
            print(f"\n[{i+1}] 方法: {item['method']}")
            print(f"    标题: {item['title'][:60]}...")
            print(f"    URL: {item['url']}")

        print_section("调试完成")

        print("\n建议的execute_js代码:\n")

        if mu_info['with_mu'] > 0:
            print("# 使用mu属性（推荐）")
            print('''browser(action="execute_js", code="""
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
""")''')
        else:
            print("# 使用第一个链接（备用）")
            print('''browser(action="execute_js", code="""
    () => {
        const results = [];
        document.querySelectorAll('div.result').forEach(container => {
            const h3 = container.querySelector('h3');
            const link = h3?.querySelector('a');
            if (link) {
                const href = link.getAttribute('href');
                if (href && !href.includes('baidu.com')) {
                    results.push({
                        title: h3.textContent.trim(),
                        url: href
                    });
                }
            }
        });
        return results;
    }
""")''')

        # 保存完整报告
        report = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "page_info": page_info,
            "selector_analysis": {s: page.locator(s).count() for s in selectors},
            "mu_analysis": mu_info,
            "links_analysis": links_info,
            "test_result": test_result,
            "recommendations": recommendations
        }

        report_file = "D:\\溯源\\backend\\tests\\browser\\baidu_debug_report.json"
        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

        print(f"\n完整报告已保存到: {report_file}")

        print("\n等待5秒后关闭浏览器...")
        time.sleep(5)

        browser.close()


if __name__ == "__main__":
    print("百度搜索结果页面调试工具")
    print("="*80)
    print("这个工具将:")
    print("1. 打开百度搜索页面")
    print("2. 分析页面DOM结构")
    print("3. 检查mu属性是否存在")
    print("4. 提供推荐的提取方法")
    print("\n开始调试...\n")

    debug_baidu_page()
