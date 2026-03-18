"""在quick_trace_executor.py中添加空气质量预报准确性评估章节 - 使用UTF-8 BOM"""
file_path = r"D:\溯源\backend\app\agent\executors\quick_trace_executor.py"

# 读取文件（带BOM）
with open(file_path, 'rb') as f:
    content = f.read()

# 解码为字符串
text = content.decode('utf-8')

# 查找并替换
old_pattern = """*说明*: [如有数据缺失或分析失败，请在此说明]

---

**报告结束**"""

new_section = """*说明*: [如有数据缺失或分析失败，请在此说明]

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

if old_pattern in text:
    text = text.replace(old_pattern, new_section)
    # 写回文件
    with open(file_path, 'wb') as f:
        f.write(text.encode('utf-8'))
    print("SUCCESS: Added air quality forecast accuracy evaluation section (4.3)")
else:
    print("ERROR: Target pattern not found")
    # 搜索可能的模式
    if "**报告结束**" in text:
        print("Found '**报告结束**' marker")
        idx = text.find("**报告结束**")
        context = text[max(0, idx-200):idx+50]
        print("\nContext:")
        print(context)
