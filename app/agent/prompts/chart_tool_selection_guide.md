# 图表工具选择决策指南

## 核心原则

**两个工具职责明确分离：**
- `smart_chart_generator` (智能工具) = 固定格式数据 → 从存储加载
- `generate_chart` (通用工具) = 动态数据 → 直接传入

---

## 决策流程图

```
开始
  ↓
是否有data_id（数据已存储到统一存储）？
  ├─ 是 → 使用 smart_chart_generator
  └─ 否 → 继续判断

数据来源是什么？
  ├─ PMF分析结果 → 使用 smart_chart_generator
  ├─ OBM/OFP分析结果 → 使用 smart_chart_generator
  ├─ 统一存储中的组分数据 → 使用 smart_chart_generator
  └─ 直接传入的原始数据 → 使用 generate_chart
```

---

## 详细使用场景

### ✅ 使用 smart_chart_generator (智能工具)

**适用场景**：
1. **PMF源解析结果** - 数据已通过`calculate_pmf`分析并存储
2. **OBM完整化学机理分析结果** - 数据已通过`calculate_obm_full_chemistry`分析并存储
3. **组分数据** - VOCs/颗粒物组分数据已通过`get_component_data`获取并存储
4. **气象+污染双轴图** - 需要智能推荐图表类型
5. **任何data_id存在的情况** - 数据已在统一存储中

**决策规则**：
```python
if has_data_id or is_pmf_result or is_obm_result or is_stored_component_data:
    use smart_chart_generator
```

**示例调用**（⚠️ 注意：以下是**格式示例**，不是实际可用的ID）：
```python
# PMF结果 - data_id必须是calculate_pmf返回的实际值
smart_chart_generator(
    data_id="[从calculate_pmf返回的data_id]",
    chart_type="auto"  # 智能推荐
)

# OBM结果 - data_id必须是calculate_obm_full_chemistry返回的实际值
smart_chart_generator(
    data_id="[从calculate_obm_full_chemistry返回的data_id]",
    chart_type="auto"
)

# 组分数据 - data_id必须是get_component_data返回的实际值
smart_chart_generator(
    data_id="[从get_component_data返回的data_id]",
    chart_type="pie"
)
```

---

### ✅ 使用 generate_chart (通用工具)

**适用场景**：
1. **直接传入的原始数据** - 未存储到统一存储
2. **LLM需要分析数据特征** - 动态选择图表类型
3. **自定义数据格式** - 特殊场景的图表
4. **多指标时序图** - 需要模板场景
5. **区域对比图** - 需要模板场景
6. **VOCs/PM分析** - 使用预定义场景模板

**决策规则**：
```python
if is_raw_data_directly_passed or needs_llm_analysis or is_custom_scenario:
    use generate_chart
```

**示例调用**：
```python
# 直接数据（无data_id）
generate_chart(
    data=[{"name": "A", "value": 10}, ...],
    scenario="custom"
)

# 预定义场景
generate_chart(
    data={"vocs_data": [...], "enterprise_data": [...]},
    scenario="vocs_analysis"
)

# 多指标时序
generate_chart(
    data={"station_data": [...], "weather_data": [...]},
    scenario="multi_indicator_timeseries",
    pollutant="O3",
    station_name="深圳南山"
)
```

---

## 常见误区

### ❌ 错误做法
```python
# 误区1：有data_id却用generate_chart
pmf_data = get_pmf_result()  # 返回data_id
generate_chart(data=pmf_data)  # ❌ 应该用smart_chart_generator

# 误区2：重复使用两个工具
smart_chart_generator(data_id="pmf:v1:abc123")
generate_chart(data=pmf_data)  # ❌ 重复生成相同图表
```

### ✅ 正确做法
```python
# 正确1：有data_id用smart_chart_generator
pmf_data = get_pmf_result()  # 返回data_id
smart_chart_generator(data_id=pmf_data)  # ✅

# 正确2：无data_id用generate_chart
raw_data = [...]  # 原始数据，无存储
generate_chart(data=raw_data, scenario="custom")  # ✅
```

---

## 工具对比表

| 特征 | smart_chart_generator | generate_chart |
|------|----------------------|----------------|
| **数据来源** | 统一存储（通过data_id） | 直接传入（data参数） |
| **图表类型** | 智能推荐或指定 | 模板+LLM生成 |
| **适用场景** | 固定格式数据 | 动态数据 |
| **数据处理** | 自动转换 | 模板或LLM处理 |
| **性能** | 高（无需LLM） | 中（可能调用LLM） |
| **灵活性** | 中（固定格式） | 高（自适应） |

---

## 实际应用建议

### 1. PMF分析流程
```python
# 步骤1：执行PMF分析
pmf_result = calculate_pmf(component_data=...)

# 步骤2：生成图表（使用smart_chart_generator）
chart = smart_chart_generator(
    data_id=pmf_result,  # data_id来自分析结果
    chart_type="pie"
)
```

### 2. OBM分析流程
```python
# 步骤1：执行OBM分析
obm_result = calculate_obm_full_chemistry(vocs_data_id=...)

# 步骤2：生成图表（使用smart_chart_generator）
chart = smart_chart_generator(
    data_id=obm_result,  # data_id来自分析结果
    chart_type="auto"
)
```

### 3. 动态数据分析流程
```python
# 步骤1：获取原始数据
raw_data = get_air_quality(location="广州")

# 步骤2：生成图表（使用generate_chart）
chart = generate_chart(
    data=raw_data,  # 直接传入数据
    scenario="custom"  # 让LLM分析数据特征
)
```

---

## 总结

**选择工具的黄金法则：**
1. **有data_id → smart_chart_generator**
2. **无data_id但有固定场景 → generate_chart + scenario参数**
3. **无data_id且无固定场景 → generate_chart + custom**
4. **PMF/OBM结果 → smart_chart_generator**
5. **避免重复使用两个工具生成相同图表**

记住：**smart_chart_generator = 智能 + 固定格式，generate_chart = 通用 + 动态数据**
