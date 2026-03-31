# ECharts 图表模板库

本目录包含专业的 ECharts 图表模板，供 Agent 搜索和使用。

## 目录结构

```
chart_templates/
├── README.md                    # 本文件（模板库索引）
├── basic/                       # 基础图表模板
│   ├── pie_professional.json    # 专业饼图
│   ├── bar_gradient.json        # 渐变柱状图
│   ├── line_smooth.json         # 平滑折线图
│   └── timeseries_multi.json    # 多系列时序图
├── meteorology/                 # 气象专业模板
│   ├── wind_rose_advanced.json  # 高级风向玫瑰图
│   ├── weather_dashboard.json   # 气象仪表盘
│   └── profile_gradient.json    # 渐变廓线图
├── pollution/                   # 污染分析模板
│   ├── vocs_heatmap.json        # VOCs热力图
│   ├── pmf_source_pie.json      # PMF源解析饼图
│   └── aqi_timeseries.json      # AQI时序图
└── spatial/                     # 空间分析模板
    ├── map_cluster.json         # 聚类地图
    └── heatmap_interpolation.json # 插值热力图
```

## 使用方式

### Agent 工作流程

1. **搜索模板**：使用 `read_file` 或 `grep` 工具搜索本目录
2. **阅读模板**：读取匹配的模板文件
3. **生成代码**：基于模板生成 Python 代码
4. **执行代码**：使用 `execute_python_tool` 执行生成图表

### 模板格式说明

每个模板文件包含：
- `template_id`: 模板唯一标识
- `name`: 模板名称
- `category`: 分类（basic/meteorology/pollution/spatial）
- `description`: 详细描述
- `data_requirements`: 数据要求
- `echarts_option`: 完整的 ECharts 配置对象
- `python_code_template`: Python 代码模板（可选）

### 示例：搜索风向玫瑰图模板

```python
# 1. Agent 搜索模板
grep("wind_rose", path="/home/xckj/suyuan/backend/config/chart_templates")

# 2. 读取模板
template = read_file("/home/xckj/suyuan/backend/config/chart_templates/meteorology/wind_rose_advanced.json")

# 3. 基于模板生成代码并执行
```

## 模板列表

### 基础图表 (basic/)
- **pie_professional.json** - 专业饼图，带标签线、百分比显示
- **bar_gradient.json** - 渐变柱状图，现代配色
- **line_smooth.json** - 平滑折线图，带阴影区域
- **timeseries_multi.json** - 多系列时序图，支持图例联动

### 气象图表 (meteorology/)
- **wind_rose_advanced.json** - 高级风向玫瑰图，8方位+风速分级
- **weather_dashboard.json** - 气象仪表盘，多要素组合
- **profile_gradient.json** - 边界层廓线图，渐变填充

### 污染分析 (pollution/)
- **vocs_heatmap.json** - VOCs热力图，时间×组分
- **pmf_source_pie.json** - PMF源解析饼图，专业配色
- **aqi_timeseries.json** - AQI时序图，分级着色

### 空间分析 (spatial/)
- **map_cluster.json** - 聚类地图，高德地图集成
- **heatmap_interpolation.json** - 插值热力图，空间分布

## 添加新模板

1. 在对应分类目录创建 `.json` 文件
2. 遵循模板格式规范
3. 更新本 README.md 的模板列表
