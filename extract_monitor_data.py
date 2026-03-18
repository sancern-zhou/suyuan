"""
海康监控点数据直接提取工具

目标：直接从浏览器页面的JavaScript环境中提取监控点数据

策略：
1. 登录并进入实时预览页面
2. 在页面中执行JavaScript查找全局变量
3. 查找可能的监控点数据存储
4. 尝试触发数据加载并提取
"""

import asyncio
import json
from datetime import datetime
from playwright.async_api import async_playwright

BASE_URL = "http://10.10.10.158"
USERNAME = "cdzhuanyong"
PASSWORD = "cdsz@429"


class DataExtractor:
    """数据提取器"""

    def __init__(self):
        self.results = []

    def log(self, message, level="INFO"):
        timestamp = datetime.now().strftime("%H:%M:%S")
        icon = {"INFO": "ℹ️", "SUCCESS": "✅", "WARN": "⚠️", "ERROR": "❌"}[level]
        print(f"[{timestamp}] {icon} {message}")

    async def extract_data(self):
        """提取监控点数据"""
        self.log("启动数据提取...", "INFO")

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=False, slow_mo=500)
            context = await browser.new_context(
                ignore_https_errors=True,
                viewport={"width": 1920, "height": 1080}
            )
            page = await context.new_page()

            try:
                # 登录流程
                self.log("访问登录页...", "INFO")
                await page.goto(BASE_URL, timeout=30000)
                await asyncio.sleep(2)

                await page.fill('input[type="text"]', USERNAME)
                await asyncio.sleep(500)
                await page.fill('input[type="password"]', PASSWORD)
                await asyncio.sleep(500)
                await page.click('button[type="submit"]')
                await asyncio.sleep(3)

                self.log("点击实时预览...", "INFO")
                await page.evaluate("""
                    () => {
                        const allElements = document.querySelectorAll('*');
                        for (const el of allElements) {
                            const text = el.textContent || '';
                            if (text.includes('实时预览') && text.length < 50) {
                                el.click();
                                return true;
                            }
                        }
                        return false;
                    }
                """)
                await asyncio.sleep(8)

                # 获取iframe
                self.log("查找iframe...", "INFO")
                frames = page.frames
                vms_frame = None

                for frame in frames:
                    if 'vms' in frame.url.lower() or 'preview' in frame.url.lower():
                        vms_frame = frame
                        self.log(f"找到iframe: {frame.name}", "SUCCESS")
                        break

                if not vms_frame:
                    self.log("未找到vms iframe，使用主页面", "WARN")
                    vms_frame = page

                # 在iframe中执行JavaScript提取数据
                self.log("\n开始提取数据...", "INFO")

                # 1. 查找全局变量中的数据
                self.log("步骤1: 查找全局变量", "INFO")
                global_vars = await vms_frame.evaluate("""
                    () => {
                        const results = {};

                        // 常见的数据存储位置
                        const possibleVars = [
                            'window.treeData',
                            'window.monitorPoints',
                            'window.cameras',
                            'window.resourceData',
                            'window.appData',
                            'window.$store',
                            'window.__INITIAL_STATE__',
                            'window.VUEX_STORE',
                            'window.monitorData',
                            'window.regionData',
                        ];

                        possibleVars.forEach(varName => {
                            try {
                                const parts = varName.split('.');
                                let data = window;
                                for (const part of parts) {
                                    data = data[part];
                                    if (data === undefined) break;
                                }
                                if (data !== undefined) {
                                    results[varName] = typeof data;
                                }
                            } catch (e) {}
                        });

                        // 查找Vue实例
                        if (typeof window !== 'undefined' && window.$root) {
                            results['$root'] = 'found';
                        }

                        return results;
                    }
                """)
                self.log(f"全局变量: {list(global_vars.keys())}", "INFO")

                # 2. 查找Vue实例中的数据
                self.log("\n步骤2: 查找Vue实例数据", "INFO")
                vue_data = await vms_frame.evaluate("""
                    () => {
                        const results = {};

                        // 查找根Vue实例
                        const app = document.querySelector('#app');
                        if (app && app.__vue__) {
                            results['rootVue'] = 'found';

                            // 获取Vue实例的数据
                            try {
                                const data = app.__vue__.$data;
                                if (data) {
                                    results['rootVueDataKeys'] = Object.keys(data);
                                }
                            } catch (e) {}

                            // 获取Vuex store
                            try {
                                const store = app.__vue__.$store;
                                if (store && store.state) {
                                    results['storeStateKeys'] = Object.keys(store.state);
                                    results['hasStore'] = true;
                                }
                            } catch (e) {}
                        }

                        // 查找所有Vue实例
                        const allElements = document.querySelectorAll('*');
                        const vueInstances = [];

                        allElements.forEach(el => {
                            if (el.__vue__) {
                                const instance = el.__vue__;
                                const data = instance.$data;
                                if (data && Object.keys(data).length > 0 && Object.keys(data).length < 20) {
                                    vueInstances.push({
                                        tag: el.tagName,
                                        className: el.className,
                                        dataKeys: Object.keys(data)
                                    });
                                }
                            }
                        });

                        results['vueInstances'] = vueInstances.slice(0, 10);

                        return results;
                    }
                """)
                self.log(f"找到 {len(vue_data.get('vueInstances', []))} 个Vue实例", "INFO")

                # 3. 查找特定的监控点数据API调用
                self.log("\n步骤3: 查找API调用", "INFO")
                api_info = await vms_frame.evaluate("""
                    () => {
                        const results = {};

                        // 尝试查找axios实例
                        if (typeof window.axios !== 'undefined') {
                            results['hasAxios'] = true;

                            // 获取axios的默认配置
                            if (window.axios.defaults) {
                                results['axiosDefaults'] = Object.keys(window.axios.defaults);
                            }
                        }

                        // 查找可能的监控点数据API
                        // 从JavaScript代码分析中找到的关键API
                        const possibleApis = [
                            '/vms/api/v5/channelsTree/searches',
                            '/vms/ui/webPreview/region/fetchRootAppRegions',
                            '/vms/ui/webPreview/region/fetchAppCamerasByParent',
                        ];

                        results['possibleApis'] = possibleApis;

                        return results;
                    }
                """)
                self.log(f"API信息: {api_info}", "INFO")

                # 4. 尝试查找页面的数据获取函数
                self.log("\n步骤4: 查找数据获取函数", "INFO")
                function_info = await vms_frame.evaluate("""
                    () => {
                        const results = {
                            foundFunctions: [],
                            windowFunctions: []
                        };

                        // 查找可能的数据获取函数
                        const functionNames = [
                            'fetchMonitorPoints',
                            'getCameras',
                            'getTreeData',
                            'loadRegions',
                            'searchChannels',
                            'fetchResources'
                        ];

                        functionNames.forEach(funcName => {
                            if (typeof window[funcName] === 'function') {
                                results['windowFunctions'].push(funcName);
                            }
                        });

                        // 查找Vue组件中的方法
                        const app = document.querySelector('#app');
                        if (app && app.__vue__) {
                            const methods = app.__vue__.$options?.methods || {};
                            results['vueMethods'] = Object.keys(methods);
                        }

                        return results;
                    }
                """)
                self.log(f"函数信息: {function_info}", "INFO")

                # 5. 查看当前页面的data属性
                self.log("\n步骤5: 查看页面数据属性", "INFO")
                page_data = await vms_frame.evaluate("""
                    () => {
                        const results = {};

                        // 查找所有有data属性的元素
                        const elementsWithData = document.querySelectorAll('[data-*]');
                        results['dataElementsCount'] = elementsWithData.length;

                        // 显示前10个data属性
                        const dataAttrs = [];
                        for (let i = 0; i < Math.min(10, elementsWithData.length); i++) {
                            const el = elementsWithData[i];
                            const attrs = {};
                            for (const attr of el.attributes) {
                                if (attr.name.startsWith('data-')) {
                                    attrs[attr.name] = attr.value;
                                }
                            }
                            if (Object.keys(attrs).length > 0 && Object.keys(attrs).length < 10) {
                                dataAttrs.push({
                                    tag: el.tagName,
                                    attrs: attrs
                                });
                            }
                        }
                        results['dataAttrsSample'] = dataAttrs;

                        return results;
                    }
                """)
                self.log(f"页面data属性: {page_data.get('dataElementsCount')} 个", "INFO")

                # 保存结果
                extraction_result = {
                    'timestamp': datetime.now().isoformat(),
                    'global_vars': global_vars,
                    'vue_data': vue_data,
                    'api_info': api_info,
                    'function_info': function_info,
                    'page_data': page_data
                }

                with open("extraction_result.json", "w", encoding="utf-8") as f:
                    json.dump(extraction_result, f, ensure_ascii=False, indent=2)

                self.log("\n结果已保存到 extraction_result.json", "SUCCESS")

                # 保持浏览器打开观察
                self.log("\n浏览器保持打开30秒，请手动检查页面...", "INFO")
                await page.screenshot(path="extraction_page.png")
                await asyncio.sleep(30000)

                return extraction_result

            except Exception as e:
                self.log(f"\n提取出错: {e}", "ERROR")
                import traceback
                traceback.print_exc()
                await page.screenshot(path="extraction_error.png")
                raise

            finally:
                await browser.close()


async def main():
    extractor = DataExtractor()

    try:
        result = await extractor.extract_data()

        extractor.log("\n" + "="*70, "SUCCESS")
        extractor.log("数据提取完成！", "SUCCESS")
        extractor.log("="*70, "SUCCESS")

    except Exception as e:
        extractor.log(f"\n执行出错: {e}", "ERROR")


if __name__ == "__main__":
    print("""
╔════════════════════════════════════════════════════════════╗
║        海康监控点数据直接提取工具                        ║
╚════════════════════════════════════════════════════════════╝

直接从浏览器页面JavaScript环境中提取监控点数据

    """)

    asyncio.run(main())
