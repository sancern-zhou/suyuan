# ECharts 扩展模板使用指南

## 快速开始

### 1. 在 Agent 中使用（推荐）

LLM 可以直接调用新的图表类型：

```
用户：生成一个堆叠柱状图，显示各污染源的贡献值

Agent 调用：
generate_chart(
    data=[
        {"category": "源A", "排放": 45, "削减": -10},
        {"category": "源B", "排放": 32, "削减": -8},
        {"category": "源C", "排放": 28, "削减": -5}
    ],
    chart_type="bar_stack_negative",
    title="污染源贡献对比"
)
```

### 2. Python 代码中使用

```python
from app.tools.visualization.generate_chart.chart_templates import get_chart_template_registry

# 获取注册表
registry = get_chart_template_registry()

# 生成图表
chart = registry.generate(
    "bar_stack_negative",
    data=[
        {"category": "源A", "series1": 45, "series2": -10},
        {"category": "源B", "series1": 32, "series2": -8}
    ],
    title="污染源贡献对比"
)

# 输出是 UDF v2.0 格式
print(chart["id"])        # 图表ID
print(chart["type"])      # 图表类型
print(chart["data"])      # 图表数据
print(chart["meta"])      # 元数据
```

## 23个新模板速查表

### 📊 柱状图变体

| 模板ID | 用途 | 数据格式示例 |
|--------|------|--------------|
| `bar_stack_negative` | 堆叠负值柱状图 | `[{"category": "A", "s1": 10, "s2": -5}]` |
| `bar_polar_radial` | 极坐标径向柱状图 | `[{"category": "00:00", "value": 35.2}]` |
| `bar_waterfall` | 瀑布图 | `[{"category": "初始", "value": 100}, {"category": "增量", "value": 20}]` |

### 🔵 散点图变体

| 模板ID | 用途 | 数据格式示例 |
|--------|------|--------------|
| `scatter_clustering` | 聚类散点图 | `[{"x": 10.5, "y": 25.3, "category": "A"}]` |
| `scatter_matrix` | 散点矩阵图 | `{"variables": ["A", "B"], "data": [...]}` |
| `scatter_regression` | 回归散点图 | `[{"x": 10.5, "y": 25.3}]` |

### 📈 折线图变体

| 模板ID | 用途 | 数据格式示例 |
|--------|------|--------------|
| `line_area_gradient` | 渐变面积折线图 | `[{"time": "2025-01-01", "value": 35.2}]` |
| `line_step` | 阶梯折线图 | `[{"time": "2025-01-01", "value": 35.2}]` |
| `line_race` | 排名竞赛图 | `{"timestamps": [...], "categories": [...], "values": [...]}` |

### 🥧 饼图变体

| 模板ID | 用途 | 数据格式示例 |
|--------|------|--------------|
| `pie_rose_type` | 玫瑰饼图 | `[{"name": "类别A", "value": 45.2}]` |
| `pie_nest` | 嵌套饼图 | `{"inner": [...], "outer": [...]}` |
| `pie_doughnut` | 环形图 | `[{"name": "类别A", "value": 45.2}]` |

### ⚡ 仪表盘

| 模板ID | 用途 | 数据格式示例 |
|--------|------|--------------|
| `gauge_progress` | 进度仪表盘 | `{"value": 75, "min": 0, "max": 100}` |
| `gauge_stage` | 分段仪表盘 | `{"value": 85, "stages": [{"max": 60, "color": "#67e0e3"}]}` |
| `gauge_ring` | 环形仪表盘 | `{"indicators": [{"name": "A", "value": 75}]}` |

### 🔗 关系图

| 模板ID | 用途 | 数据格式示例 |
|--------|------|--------------|
| `graph_force` | 力引导关系图 | `{"nodes": [...], "links": [...]}` |
| `graph_circular` | 环形布局关系图 | `{"nodes": [...], "links": [...]}` |

### 📅 日历图

| 模板ID | 用途 | 数据格式示例 |
|--------|------|--------------|
| `calendar_heatmap` | 日历热力图 | `[{"date": "2025-01-01", "value": 35.2}]` |
| `calendar_pie` | 日历饼图 | `[{"date": "2025-01-01", "category": "A", "value": 10}]` |

### 🗂️ 矩形树图

| 模板ID | 用途 | 数据格式示例 |
|--------|------|--------------|
| `treemap_simple` | 简单矩形树图 | `[{"name": "A", "value": 45.2, "category": "一类"}]` |
| `treemap_drill_down` | 下钻矩形树图 | `{"name": "根", "children": [...]}` |

### 🌊 桑基图

| 模板ID | 用途 | 数据格式示例 |
|--------|------|--------------|
| `sankey_simple` | 简单桑基图 | `{"nodes": [...], "links": [...]}` |
| `sankey_vertical` | 垂直桑基图 | `{"nodes": [...], "links": [...]}` |

## 实际应用示例

### 示例1：污染源贡献对比（堆叠负值柱状图）

```python
generate_chart(
    data=[
        {"category": "工业源", "排放": 45.2, "削减": -12.5},
        {"category": "交通源", "排放": 32.8, "削减": -8.3},
        {"category": "生活源", "排放": 18.5, "削减": -4.2}
    ],
    chart_type="bar_stack_negative",
    title="污染源排放与削减对比"
)
```

### 示例2：污染物浓度相关性分析（回归散点图）

```python
generate_chart(
    data=[
        {"x": 25.3, "y": 42.8},  # O3 vs 温度
        {"x": 28.1, "y": 55.2},
        {"x": 30.5, "y": 68.7}
    ],
    chart_type="scatter_regression",
    title="臭氧浓度与温度相关性",
    x_key="temperature",
    y_key="o3"
)
```

### 示例3：源解析贡献（玫瑰饼图）

```python
generate_chart(
    data=[
        {"name": "机动车", "value": 35.2},
        {"name": "工业排放", "value": 28.5},
        {"name": "溶剂使用", "value": 18.3},
        {"name": "其他", "value": 18.0}
    ],
    chart_type="pie_rose_type",
    title="VOCs源解析贡献"
)
```

### 示例4：空气质量达标率（分段仪表盘）

```python
generate_chart(
    data={
        "value": 78.5,
        "min": 0,
        "max": 100,
        "title": "优良天数比例"
    },
    chart_type="gauge_stage",
    stages=[
        {"max": 60, "color": "#d9001b", "label": "差"},
        {"max": 80, "color": "#e6b600", "label": "良"},
        {"max": 100, "color": "#67e0e3", "label": "优"}
    ]
)
```

### 示例5：污染源→受体流向（桑基图）

```python
generate_chart(
    data={
        "nodes": ["工业区A", "工业区B", "监测点1", "监测点2"],
        "links": [
            {"source": "工业区A", "target": "监测点1", "value": 45},
            {"source": "工业区A", "target": "监测点2", "value": 20},
            {"source": "工业区B", "target": "监测点1", "value": 15},
            {"source": "工业区B", "target": "监测点2", "value": 35}
        ]
    },
    chart_type="sankey_simple",
    title="污染源输送路径"
)
```

## 检索更多 ECharts 示例

如果需要更多图表变体，可以使用以下工具检索 echarts-examples 官方示例：

```python
# 1. 查找所有柱状图示例
search_files(
    pattern="bar-*.ts",
    path="/tmp/echarts-examples-gh-pages/public/examples/ts"
)

# 2. 搜索简单示例（难度0）
grep(
    pattern="difficulty: 0",
    type="ts",
    path="/tmp/echarts-examples-gh-pages/public/examples/ts"
)

# 3. 读取具体示例
read_file(
    file_path="/tmp/echarts-examples-gh-pages/public/examples/ts/bar-simple.ts"
)

# 4. 查看所有可用图表类型
list_directory(
    path="/tmp/echarts-examples-gh-pages/public/examples/ts"
)
```

## 注意事项

1. **数据格式**：确保数据格式与模板要求匹配
2. **字段名称**：使用标准字段名称（如 `name`, `value`, `category`, `time`）
3. **图表类型**：使用准确的 `chart_type` 参数（参考上面的速查表）
4. **向后兼容**：所有原有模板仍可正常使用

## 技术支持

- 实施总结：`ECHARTS_TEMPLATES_IMPLEMENTATION_SUMMARY.md`
- 模板源码：`backend/app/tools/visualization/generate_chart/chart_templates_extended.py`
- ECharts示例：`/tmp/echarts-examples-gh-pages/public/examples/ts`

---

**版本**: v3.3
**更新日期**: 2026-04-02
**模板总数**: 37个（原有14个 + 新增23个）
