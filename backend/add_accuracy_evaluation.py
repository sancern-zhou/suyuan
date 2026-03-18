"""在quick_trace_executor.py中添加空气质量预报准确性评估章节"""
import re

file_path = r"D:\溯源\backend\app\agent\executors\quick_trace_executor.py"

with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

# 查找需要替换的位置
old_text = """*说明*: [如有数据缺失或分析失败，请在此说明]

---

**报告结束**"""

new_text = """*说明*: [如有数据缺失或分析失败，请在此说明]

### 4.3 空气质量预报准确性评估

**气象条件匹配度分析**:
- 扩散条件与AQI预报一致性: [分析边界层高度、风速与空气质量变化趋势是否匹配]
- 降水清除效应: [如有降水，评估对AQI下降的预期影响]
- 综合判断: [一致/基本一致/存在矛盾]

**预报合理性检验**:
- AQI数值合理性: [检查各天AQI值是否与气象条件对应]
- 首要污染物合理性: [评估首要污染物选择是否合理]
- 日变化幅度: [判断AQI日变化是否符合气象条件变化幅度]

**异常值识别**:
- [如有异常，说明具体日期和异常原因]
- [如有数据缺失，说明缺失日期和影响]

**预报可信度评级**: [高/中/低] 可信度
- [评级理由说明]

---

**报告结束**"""

if old_text in content:
    content = content.replace(old_text, new_text)
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)
    print("Success: Added air quality forecast accuracy evaluation section")
else:
    print("Error: Target text not found")
    # 尝试查找相似文本
    if "**报告结束**" in content:
        print("Found '**报告结束**' in file")
        idx = content.find("**报告结束**")
        print(f"Context around '**报告结束**':")
        print(repr(content[max(0, idx-100):idx+50]))
