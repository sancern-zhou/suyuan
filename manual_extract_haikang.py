"""
海康监控点数据手动提取工具

使用方法：
1. 手动打开浏览器并登录海康平台
2. 进入"实时预览"页面
3. 在页面中按F12打开开发者工具
4. 复制下面的JavaScript代码到控制台执行
5. 将控制台输出的结果保存为JSON文件
"""

import asyncio
import json
from datetime import datetime
from playwright.async_api import async_playwright

BASE_URL = "http://10.10.10.158"


def log(message, level="INFO"):
    timestamp = datetime.now().strftime("%H:%M:%S")
    icon = {"INFO": "ℹ️", "SUCCESS": "✅", "WARN": "⚠️", "ERROR": "❌"}[level]
    print(f"[{timestamp}] {icon} {message}")


async def manual_extract():
    """手动模式数据提取"""
    log("启动手动提取模式...", "INFO")

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,
            slow_mo=500
        )
        context = await browser.new_context(
            ignore_https_errors=True,
            viewport={"width": 1920, "height": 1080}
        )
        page = await context.new_page()

        try:
            # 只打开页面，不自动登录
            log("打开登录页...", "INFO")
            await page.goto(BASE_URL, timeout=30000)

            log("\n" + "="*70, "INFO")
            log("请手动执行以下步骤：", "INFO")
            log("="*70, "INFO")
            log("1. 在浏览器中手动输入账号密码并登录", "INFO")
            log("2. 点击'实时预览'进入预览页面", "INFO")
            log("3. 等待页面完全加载", "INFO")
            log("4. 按F12打开开发者工具", "INFO")
            log("5. 切换到Console（控制台）标签", "INFO")
            log("6. 复制下面的JavaScript代码并粘贴到控制台执行", "INFO")
            log("7. 将控制台输出的结果发送给我", "INFO")

            # 生成JavaScript代码供用户手动执行
            js_code = """
// 海康监控点数据提取脚本
(function() {
    console.log("开始提取监控点数据...");

    const results = {
        timestamp: new Date().toISOString(),
        data: []
    };

    // 1. 查找Vue实例数据
    const app = document.querySelector('#app');
    if (app && app.__vue__) {
        console.log("✅ 找到Vue根实例");

        const vue = app.__vue__;

        // 获取根实例数据
        if (vue.$data) {
            results.data.push({
                source: 'root_vue_data',
                keys: Object.keys(vue.$data)
            });
            console.log("  根实例数据字段:", Object.keys(vue.$data));
        }

        // 获取Vuex store
        if (vue.$store && vue.$store.state) {
            results.data.push({
                source: 'vuex_state',
                keys: Object.keys(vue.$store.state)
            });
            console.log("  Vuex状态字段:", Object.keys(vue.$store.state));

            // 尝试查找监控点相关数据
            for (const key of Object.keys(vue.$store.state)) {
                if (key.toLowerCase().includes('monitor') ||
                    key.toLowerCase().includes('camera') ||
                    key.toLowerCase().includes('tree') ||
                    key.toLowerCase().includes('region')) {
                    console.log(`  🎯 发现相关数据: ${key}`, vue.$store.state[key]);
                    results.data.push({
                        source: 'vuex_state',
                        key: key,
                        data: vue.$store.state[key]
                    });
                }
            }
        }

        // 获取子组件
        if (vue.$children) {
            console.log(`  子组件数量: ${vue.$children.length}`);

            vue.$children.forEach((child, index) => {
                if (child.$data) {
                    const keys = Object.keys(child.$data);
                    if (keys.length > 0 && keys.length < 20) {
                        results.data.push({
                            source: `child_${index}`,
                            keys: keys,
                            className: child.$options.name || child.$options._componentTag
                        });
                        console.log(`  子组件[${index}]:`, child.$options.name || child.$options._componentTag, "字段:", keys);
                    }
                }
            });
        }
    }

    // 2. 查找全局变量
    console.log("\\n查找全局变量...");
    const globalDataKeys = ['treeData', 'monitorPoints', 'cameras', 'resourceData', 'monitorData'];

    globalDataKeys.forEach(key => {
        if (window[key]) {
            console.log(`  ✅ 找到 window.${key}`);
            results.data.push({
                source: 'global',
                key: key,
                data: window[key]
            });
        }
    });

    // 3. 查找所有data-属性
    console.log("\\n查找data属性...");
    const dataElements = document.querySelectorAll('[data-camera], [data-monitor], [data-region], [data-tree]');
    console.log(`  找到 ${dataElements.length} 个data属性元素`);

    // 4. 查找可能的API调用结果
    console.log("\\n查找API相关数据...");
    const possibleApis = [
        '/vms/api/v5/channelsTree',
        '/vms/ui/webPreview/region',
        '/monitoringAids'
    ];

    // 5. 尝试查找监控点列表（通过DOM查找）
    console.log("\\n查找监控点DOM元素...");
    const monitorElements = document.querySelectorAll('[class*="monitor"], [class*="camera"], [class*="tree"]');
    console.log(`  找到 ${monitorElements.length} 个可能的监控点元素`);

    // 显示结果
    console.log("\\n========== 提取完成 ==========");
    console.log("请将以下结果复制并发送:");

    // 将结果转换为JSON字符串
    const resultJson = JSON.stringify(results, null, 2);
    console.log(resultJson);

    // 同时返回结果
    return results;
})();
"""

            # 保存JavaScript代码到文件
            with open("haikang_extract_code.js", "w", encoding="utf-8") as f:
                f.write(js_code)

            log("\nJavaScript代码已保存到: haikang_extract_code.js", "INFO")

            log("\n" + "="*70, "INFO")
            log("等待您手动操作...", "INFO")
            log("="*70, "INFO")
            log("浏览器保持打开60秒，请在此期间完成上述步骤", "INFO")
            log("完成后按Ctrl+C退出，或等待超时", "INFO")

            # 保持浏览器打开
            await asyncio.sleep(60000)

        except Exception as e:
            log(f"\n执行出错: {e}", "ERROR")
            import traceback
            traceback.print_exc()

        finally:
            await browser.close()


def analyze_manual_result():
    """分析手动输入的结果"""
    log("="*70, "INFO")
    log("如果您已经手动执行了提取代码", "INFO")
    log("="*70, "INFO")

    log("\n请将控制台输出的JSON结果粘贴到这里", "INFO")
    log("粘贴后按Enter键结束输入，按Ctrl+Z (Windows) 或 Ctrl+D (Unix/Mac) 结束:", "INFO")

    json_lines = []
    try:
        while True:
            line = input()
            if line.strip():
                json_lines.append(line)
    except EOFError:
        pass

    if json_lines:
        json_text = '\n'.join(json_lines)
        try:
            result = json.loads(json_text)
            log("\n✅ 成功解析JSON结果", "SUCCESS")

            # 分析结果
            log(f"数据源数量: {len(result.get('data', []))}", "INFO")

            for item in result.get('data', []):
                source = item.get('source', '')
                log(f"\n数据源: {source}", "INFO")
                if 'keys' in item:
                    log(f"  字段: {item['keys']}", "INFO")
                if 'key' in item:
                    log(f"  关键字: {item['key']}", "INFO")

            # 保存分析结果
            with open("manual_extract_result.json", "w", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False, indent=2)

            log("\n结果已保存到 manual_extract_result.json", "SUCCESS")

        except json.JSONDecodeError as e:
            log(f"JSON解析失败: {e}", "ERROR")
            log("\n请确保粘贴的是完整的JSON格式", "WARN")


if __name__ == "__main__":
    print("""
╔════════════════════════════════════════════════════════════╗
║        海康监控点数据手动提取工具                        ║
╚════════════════════════════════════════════════════════════╝

两种使用方式：

方式1：自动模式（推荐）
  - 运行脚本后手动登录浏览器
  - 使用生成的JavaScript代码提取数据

方式2：手动模式
  - 已经手动执行了提取代码
  - 将结果粘贴回来进行分析

    """)

    import sys

    if len(sys.argv) > 1 and sys.argv[1] == '--manual':
        analyze_manual_result()
    else:
        asyncio.run(manual_extract())
