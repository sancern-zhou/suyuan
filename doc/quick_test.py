#!/usr/bin/env python3
"""快速测试前后端连接"""

import requests
import json

print("\n" + "="*60)
print("  快速测试前后端连接")
print("="*60)

# 测试后端
print("\n1. 测试后端健康检查...")
try:
    r = requests.get("http://localhost:8000/health", timeout=5)
    print(f"   ✅ 后端正常: {r.json()['service']}")
except Exception as e:
    print(f"   ❌ 后端异常: {e}")
    exit(1)

# 测试分析接口
print("\n2. 测试分析接口...")
query = "2025年8月9日广州从化天湖站点臭氧超标原因分析"
print(f"   查询: {query}")

try:
    r = requests.post(
        "http://localhost:8000/api/analyze",
        json={"query": query},
        timeout=120
    )
    
    if r.status_code == 200:
        data = r.json()
        print(f"   ✅ 请求成功")
        
        # 保存完整响应
        with open('latest_response.json', 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"   [object Object] latest_response.json")
        
        # 检查响应结构
        if data.get('success'):
            print(f"   ✅ 分析成功")
            
            analysis = data.get('data', {})
            
            # 打印所有顶层键
            print(f"\n   📋 响应包含的键: {list(analysis.keys())}")
            
            # 检查各模块
            modules = {
                'weather_analysis': '气象分析',
                'regional_analysis': '区域对比',
                'voc_analysis': 'VOCs分析',
                'particulate_analysis': '颗粒物分析',
                'comprehensive_analysis': '综合分析'
            }
            
            print("\n   📊 模块检查:")
            for key, name in modules.items():
                module = analysis.get(key)
                if module and isinstance(module, dict):
                    content = module.get('content', '')
                    content_len = len(content) if content else 0
                    visuals = module.get('visuals', [])
                    confidence = module.get('confidence', 'N/A')
                    
                    print(f"      ✅ {name}:")
                    print(f"         - 内容: {content_len}字符")
                    print(f"         - 可视化: {len(visuals)}个")
                    print(f"         - 置信度: {confidence}")
                    
                    # 检查可视化详情
                    for idx, v in enumerate(visuals, 1):
                        v_type = v.get('type', 'N/A')
                        v_title = v.get('title', 'N/A')
                        v_mode = v.get('mode', 'N/A')
                        has_payload = 'payload' in v
                        print(f"         - 可视化{idx}: {v_type} ({v_mode}) - {v_title} [payload: {has_payload}]")
                    
                    # 打印内容预览
                    if content:
                        preview = content[:100].replace('\n', ' ')
                        print(f"         - 内容预览: {preview}...")
                        
                elif module is None:
                    print(f"      ⚠️  {name}: None (未生成)")
                else:
                    print(f"      ⚠️  {name}: {type(module)}")
            
            # 检查KPI摘要
            kpi = analysis.get('kpi_summary')
            if kpi:
                print(f"\n   📈 KPI摘要:")
                print(f"      - 峰值: {kpi.get('peak_value')} {kpi.get('unit')}")
                print(f"      - 平均: {kpi.get('avg_value')} {kpi.get('unit')}")
                print(f"      - 主导风向: {kpi.get('main_wind_sector')}")
                print(f"      - 主要来源: {kpi.get('top_sources')}")
            
        else:
            print(f"   ❌ 分析失败: {data.get('message')}")
    else:
        print(f"   ❌ HTTP {r.status_code}: {r.text[:200]}")
        
except Exception as e:
    print(f"   ❌ 请求失败: {e}")
    import traceback
    traceback.print_exc()
    exit(1)

print("\n" + "="*60)
print("  ✅ 测试完成！")
print("  📂 查看 latest_response.json 了解完整响应")
print("  🌐 在浏览器中打开 http://localhost:5173 测试前端")
print("="*60 + "\n")
