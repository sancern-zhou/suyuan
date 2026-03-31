# ECharts 模板使用指南

## 核心原则

**模板提供样式配置，数据从 data_id 动态加载**

```
模板 (样式) + data_id (数据) = 最终图表
```

## 工作流程

### 1. Agent 搜索模板

```python
# 使用 grep 工具搜索模板
grep("饼图", path="/home/xckj/suyuan/backend/config/chart_templates")
```

### 2. 阅读模板文档

```python
# 使用 read_file 读取模板
template = read_file("/home/xckj/suyuan/backend/config/chart_templates/basic/pie_professional.json")
```

### 3. 从 data_id 加载数据

```python
# 使用 context.get_data() 加载数据
records = context.get_data(data_id)
```

### 4. 数据转换

根据模板的 `data_requirements` 转换数据格式：

```python
# 示例：饼图需要 name 和 value
chart_data = []
for record in records:
    chart_data.append({
        'name': record.component_name,  # 字段映射
        'value': record.concentration   # 字段映射
    })
```

### 5. 生成 Chart v3.1 格式

```python
import uuid

result = {
    'id': f'pie_{uuid.uuid4().hex[:8]}',
    'type': 'pie',
    'title': '污染物组分占比',
    'data': {
        'type': 'pie',
        'data': chart_data
    },
    'meta': {
        'schema_version': '3.1',
        'generator': 'template:pie_professional',
        'original_data_ids': [data_id]
    }
}
```

## 模板字段说明

### data_requirements

定义模板需要的数据格式：

```json
{
  "required_fields": ["name", "value"],
  "optional_fields": ["category"],
  "min_records": 2,
  "example": [
    {"name": "苯", "value": 45.2},
    {"name": "甲苯", "value": 32.8}
  ]
}
```

### echarts_option

ECharts 配置对象（仅样式，不含数据）：
- 使用 `{title}` 等占位符
- `data` 字段标记为 `"{data}"` 占位符

### usage_guide

代码示例，展示如何使用模板

## 常见场景

### 场景 1：简单映射

数据已经是目标格式，直接使用：

```python
# VOCs 数据 → 饼图
records = context.get_data(data_id)
chart_data = [{'name': r.component, 'value': r.concentration} for r in records]
```

### 场景 2：聚合计算

需要先聚合数据：

```python
# 按行业聚合企业数据
from collections import defaultdict
industry_sum = defaultdict(float)
for record in records:
    industry_sum[record.industry] += record.emission

chart_data = [{'name': k, 'value': v} for k, v in industry_sum.items()]
```

### 场景 3：时序数据

多系列时序图：

```python
# 提取时间轴
x_data = [r.time for r in records]

# 提取系列数据
series = [
    {'name': '苯', 'data': [r.benzene for r in records]},
    {'name': '甲苯', 'data': [r.toluene for r in records]}
]

chart_data = {'x': x_data, 'series': series}
```

## 注意事项

1. **不要硬编码数据**：模板中的 `data` 字段应为占位符
2. **字段映射灵活**：根据实际数据字段名调整映射逻辑
3. **保留 data_id**：在 `meta.original_data_ids` 中记录数据来源
4. **返回 Chart v3.1**：统一使用标准格式
