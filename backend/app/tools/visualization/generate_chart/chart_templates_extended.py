"""
ECharts 图表模板扩展库

从 echarts-examples-gh-pages 官方示例中提取的图表模板。

第一批：高频图表（9种）
- bar: 柱状图（32个示例）
- scatter: 散点图（26个示例）
- line: 折线图（23个示例）
- pie: 饼图（14个示例）
- gauge: 仪表盘（11个示例）
- graph: 关系图（10个示例）
- calendar: 日历图（9个示例）
- treemap: 矩形树图（7个示例）
- sankey: 桑基图（7个示例）

模板命名规范：{图表类型}_{用途}_{变体}
"""
from typing import Dict, Any, List
import uuid
import structlog

logger = structlog.get_logger()


# ============================================
# 1. 柱状图模板（Bar Charts）
# ============================================

def bar_stack_negative(data: List[Dict[str, Any]], **kwargs) -> Dict[str, Any]:
    """
    堆叠负值柱状图模板

    适用场景：显示正负值对比，如污染源贡献、收支对比等

    输入数据格式:
    [
        {"category": "类别A", "series1": 10, "series2": -5, "series3": 8},
        {"category": "类别B", "series1": 12, "series2": -3, "series3": 6},
        ...
    ]

    基于：bar-negative.ts, bar-stack.ts
    """
    title = kwargs.get("title", "堆叠柱状图（含负值）")
    stack_by = kwargs.get("stack_by", None)  # 堆叠分组字段
    meta = kwargs.get("meta", {})

    if not data or not isinstance(data, list):
        raise ValueError("bar_stack_negative模板需要列表数据")

    # 提取分类和系列
    categories = []
    series_dict = {}

    for item in data:
        if not isinstance(item, dict):
            continue

        category = item.get("category", item.get("name", "Unknown"))
        if category not in categories:
            categories.append(category)

        # 提取所有数值字段（非category/name字段）
        for key, value in item.items():
            if key not in ["category", "name"] and isinstance(value, (int, float)):
                if key not in series_dict:
                    series_dict[key] = {}
                series_dict[key][category] = value

    # 构建系列数据
    series_list = []
    for series_name, category_values in series_dict.items():
        series_list.append({
            "name": series_name,
            "data": [category_values.get(cat, 0) for cat in categories],
            "stack": "total"  # 堆叠
        })

    chart_dict = {
        "id": f"bar_stack_neg_{uuid.uuid4().hex[:8]}",
        "type": "bar",
        "title": title,
        "data": {
            "x": categories,
            "series": series_list
        },
        "options": {
            "stack": "total",  # 堆叠模式
            "negative": True   # 支持负值
        },
        "meta": {
            **meta,
            "schema_version": "3.1",
            "generator": "template:bar_stack_negative",
            "category_count": len(categories),
            "series_count": len(series_list)
        }
    }

    return chart_dict


def bar_polar_radial(data: List[Dict[str, Any]], **kwargs) -> Dict[str, Any]:
    """
    极坐标径向柱状图模板

    适用场景：周期性数据展示，如24小时浓度变化、12个月份趋势

    输入数据格式:
    [
        {"category": "00:00", "value": 35.2},
        {"category": "01:00", "value": 32.8},
        ...
    ]

    基于：bar-polar-stack-radial.ts
    """
    title = kwargs.get("title", "极坐标柱状图")
    meta = kwargs.get("meta", {})

    if not data or not isinstance(data, list):
        raise ValueError("bar_polar_radial模板需要列表数据")

    categories = []
    values = []

    for item in data:
        if not isinstance(item, dict):
            continue
        category = item.get("category", item.get("name", ""))
        value = item.get("value", 0)
        if category:
            categories.append(category)
            values.append(value)

    chart_dict = {
        "id": f"bar_polar_{uuid.uuid4().hex[:8]}",
        "type": "bar_polar",
        "title": title,
        "data": {
            "categories": categories,
            "values": values
        },
        "options": {
            "coordinate": "polar",  # 极坐标系
            "radial": True          # 径向排列
        },
        "meta": {
            **meta,
            "schema_version": "3.1",
            "generator": "template:bar_polar_radial",
            "record_count": len(data)
        }
    }

    return chart_dict


def bar_waterfall(data: List[Dict[str, Any]], **kwargs) -> Dict[str, Any]:
    """
    瀑布图模板

    适用场景：显示累积效应，如污染浓度累积变化、增量分析

    输入数据格式:
    [
        {"category": "初始", "value": 100},
        {"category": "增量1", "value": 20},
        {"category": "增量2", "value": -15},
        ...
    ]

    基于：bar-waterfall.ts
    """
    title = kwargs.get("title", "瀑布图")
    meta = kwargs.get("meta", {})

    if not data or not isinstance(data, list):
        raise ValueError("bar_waterfall模板需要列表数据")

    categories = []
    values = []

    for item in data:
        if not isinstance(item, dict):
            continue
        category = item.get("category", item.get("name", ""))
        value = item.get("value", 0)
        if category:
            categories.append(category)
            values.append(value)

    # 计算累积值
    cumulative = 0
    cumulative_values = []
    for value in values:
        cumulative += value
        cumulative_values.append(cumulative)

    chart_dict = {
        "id": f"bar_waterfall_{uuid.uuid4().hex[:8]}",
        "type": "bar",
        "title": title,
        "data": {
            "x": categories,
            "series": [
                {
                    "name": "增量",
                    "data": values
                },
                {
                    "name": "累积",
                    "data": cumulative_values,
                    "type": "line"
                }
            ]
        },
        "options": {
            "waterfall": True
        },
        "meta": {
            **meta,
            "schema_version": "3.1",
            "generator": "template:bar_waterfall",
            "record_count": len(data)
        }
    }

    return chart_dict


# ============================================
# 2. 散点图模板（Scatter Charts）
# ============================================

def scatter_clustering(data: List[Dict[str, Any]], **kwargs) -> Dict[str, Any]:
    """
    聚类散点图模板

    适用场景：多变量关系分析，如污染物浓度相关性分析

    输入数据格式:
    [
        {"x": 10.5, "y": 25.3, "category": "A", "size": 5},
        {"x": 12.8, "y": 28.1, "category": "B", "size": 8},
        ...
    ]

    基于：scatter-clustering.ts
    """
    title = kwargs.get("title", "聚类散点图")
    x_key = kwargs.get("x_key", "x")
    y_key = kwargs.get("y_key", "y")
    category_key = kwargs.get("category_key", "category")
    size_key = kwargs.get("size_key", "size")
    meta = kwargs.get("meta", {})

    if not data or not isinstance(data, list):
        raise ValueError("scatter_clustering模板需要列表数据")

    # 按类别分组
    categories = {}
    for item in data:
        if not isinstance(item, dict):
            continue

        category = item.get(category_key, "Unknown")
        if category not in categories:
            categories[category] = []

        x = item.get(x_key)
        y = item.get(y_key)
        size = item.get(size_key, 5)

        if x is not None and y is not None:
            categories[category].append({
                "x": x,
                "y": y,
                "size": size
            })

    # 构建系列数据
    series_list = []
    for category, points in categories.items():
        series_list.append({
            "name": category,
            "data": points,
            "type": "scatter"
        })

    chart_dict = {
        "id": f"scatter_cluster_{uuid.uuid4().hex[:8]}",
        "type": "scatter",
        "title": title,
        "data": {
            "series": series_list
        },
        "options": {
            "clustering": True
        },
        "meta": {
            **meta,
            "schema_version": "3.1",
            "generator": "template:scatter_clustering",
            "category_count": len(categories),
            "total_points": len(data)
        }
    }

    return chart_dict


def scatter_matrix(data: List[Dict[str, Any]], **kwargs) -> Dict[str, Any]:
    """
    散点矩阵图模板

    适用场景：多变量相关性矩阵分析

    输入数据格式:
    {
        "variables": ["变量A", "变量B", "变量C", "变量D"],
        "data": [
            {"变量A": 10, "变量B": 20, "变量C": 15, "变量D": 25},
            {"变量A": 12, "变量B": 22, "变量C": 18, "变量D": 28},
            ...
        ]
    }

    基于：scatter-matrix.ts
    """
    title = kwargs.get("title", "散点矩阵图")
    meta = kwargs.get("meta", {})

    if not isinstance(data, dict):
        raise ValueError("scatter_matrix模板需要字典数据")

    variables = data.get("variables", [])
    records = data.get("data", [])

    chart_dict = {
        "id": f"scatter_matrix_{uuid.uuid4().hex[:8]}",
        "type": "scatter_matrix",
        "title": title,
        "data": {
            "variables": variables,
            "records": records
        },
        "options": {
            "matrix": True
        },
        "meta": {
            **meta,
            "schema_version": "3.1",
            "generator": "template:scatter_matrix",
            "variable_count": len(variables),
            "record_count": len(records)
        }
    }

    return chart_dict


def scatter_regression(data: List[Dict[str, Any]], **kwargs) -> Dict[str, Any]:
    """
    回归散点图模板

    适用场景：趋势分析，如浓度与气象因素的相关性

    输入数据格式:
    [
        {"x": 10.5, "y": 25.3},
        {"x": 12.8, "y": 28.1},
        ...
    ]

    基于：scatter-linear-regression.ts
    """
    title = kwargs.get("title", "回归散点图")
    x_key = kwargs.get("x_key", "x")
    y_key = kwargs.get("y_key", "y")
    regression_type = kwargs.get("regression_type", "linear")  # linear, exponential, logarithmic
    meta = kwargs.get("meta", {})

    if not data or not isinstance(data, list):
        raise ValueError("scatter_regression模板需要列表数据")

    points = []
    for item in data:
        if not isinstance(item, dict):
            continue
        x = item.get(x_key)
        y = item.get(y_key)
        if x is not None and y is not None:
            points.append({"x": x, "y": y})

    # 简单线性回归计算
    if len(points) >= 2:
        x_values = [p["x"] for p in points]
        y_values = [p["y"] for p in points]

        n = len(points)
        sum_x = sum(x_values)
        sum_y = sum(y_values)
        sum_xy = sum(x * y for x, y in zip(x_values, y_values))
        sum_x2 = sum(x ** 2 for x in x_values)

        slope = (n * sum_xy - sum_x * sum_y) / (n * sum_x2 - sum_x ** 2)
        intercept = (sum_y - slope * sum_x) / n

        # 生成回归线数据
        x_min, x_max = min(x_values), max(x_values)
        regression_line = [
            {"x": x_min, "y": slope * x_min + intercept},
            {"x": x_max, "y": slope * x_max + intercept}
        ]
    else:
        regression_line = []

    chart_dict = {
        "id": f"scatter_regress_{uuid.uuid4().hex[:8]}",
        "type": "scatter",
        "title": title,
        "data": {
            "series": [
                {
                    "name": "数据点",
                    "data": points,
                    "type": "scatter"
                },
                {
                    "name": "回归线",
                    "data": regression_line,
                    "type": "line"
                }
            ]
        },
        "options": {
            "regression": regression_type
        },
        "meta": {
            **meta,
            "schema_version": "3.1",
            "generator": "template:scatter_regression",
            "point_count": len(points)
        }
    }

    return chart_dict


# ============================================
# 3. 折线图模板（Line Charts）
# ============================================

def line_area_gradient(data: List[Dict[str, Any]], **kwargs) -> Dict[str, Any]:
    """
    渐变面积折线图模板

    适用场景：趋势展示，如污染物浓度时序变化

    输入数据格式:
    [
        {"time": "2025-01-01 00:00", "value": 35.2},
        {"time": "2025-01-01 01:00", "value": 32.8},
        ...
    ]

    基于：area-stack-gradient.ts
    """
    title = kwargs.get("title", "渐变面积折线图")
    x_key = kwargs.get("x_key", "time")
    y_key = kwargs.get("y_key", "value")
    meta = kwargs.get("meta", {})

    if not data or not isinstance(data, list):
        raise ValueError("line_area_gradient模板需要列表数据")

    x_data = []
    y_data = []

    for item in data:
        if not isinstance(item, dict):
            continue
        x = item.get(x_key)
        y = item.get(y_key)
        if x is not None and y is not None:
            x_data.append(x)
            y_data.append(y)

    chart_dict = {
        "id": f"line_area_grad_{uuid.uuid4().hex[:8]}",
        "type": "line",
        "title": title,
        "data": {
            "x": x_data,
            "series": [
                {
                    "name": "数值",
                    "data": y_data,
                    "area": True,      # 面积图
                    "gradient": True   # 渐变填充
                }
            ]
        },
        "options": {
            "area": True,
            "gradient": True
        },
        "meta": {
            **meta,
            "schema_version": "3.1",
            "generator": "template:line_area_gradient",
            "record_count": len(data)
        }
    }

    return chart_dict


def line_step(data: List[Dict[str, Any]], **kwargs) -> Dict[str, Any]:
    """
    阶梯折线图模板

    适用场景：离散变化展示，如等级变化、阶梯式限值

    输入数据格式:
    [
        {"time": "2025-01-01 00:00", "value": 35.2},
        {"time": "2025-01-01 01:00", "value": 42.8},
        ...
    ]

    基于：line-step.ts
    """
    title = kwargs.get("title", "阶梯折线图")
    x_key = kwargs.get("x_key", "time")
    y_key = kwargs.get("y_key", "value")
    step_position = kwargs.get("step_position", "start")  # start, middle, end
    meta = kwargs.get("meta", {})

    if not data or not isinstance(data, list):
        raise ValueError("line_step模板需要列表数据")

    x_data = []
    y_data = []

    for item in data:
        if not isinstance(item, dict):
            continue
        x = item.get(x_key)
        y = item.get(y_key)
        if x is not None and y is not None:
            x_data.append(x)
            y_data.append(y)

    chart_dict = {
        "id": f"line_step_{uuid.uuid4().hex[:8]}",
        "type": "line",
        "title": title,
        "data": {
            "x": x_data,
            "series": [
                {
                    "name": "数值",
                    "data": y_data,
                    "step": step_position
                }
            ]
        },
        "options": {
            "step": step_position
        },
        "meta": {
            **meta,
            "schema_version": "3.1",
            "generator": "template:line_step",
            "record_count": len(data)
        }
    }

    return chart_dict


def line_race(data: List[Dict[str, Any]], **kwargs) -> Dict[str, Any]:
    """
    排名竞赛图模板

    适用场景：动态排名变化，如污染物浓度排名变化

    输入数据格式:
    {
        "timestamps": ["2025-01-01", "2025-01-02", "2025-01-03"],
        "categories": ["A", "B", "C"],
        "values": [
            [10, 12, 15],  # A的值
            [8, 15, 12],    # B的值
            [12, 10, 8]     # C的值
        ]
    }

    基于：bar-race.ts（动态版）
    """
    title = kwargs.get("title", "排名竞赛图")
    meta = kwargs.get("meta", {})

    if not isinstance(data, dict):
        raise ValueError("line_race模板需要字典数据")

    timestamps = data.get("timestamps", [])
    categories = data.get("categories", [])
    values = data.get("values", [])

    chart_dict = {
        "id": f"line_race_{uuid.uuid4().hex[:8]}",
        "type": "line_race",
        "title": title,
        "data": {
            "timestamps": timestamps,
            "categories": categories,
            "values": values
        },
        "options": {
            "race": True
        },
        "meta": {
            **meta,
            "schema_version": "3.1",
            "generator": "template:line_race",
            "category_count": len(categories),
            "time_steps": len(timestamps)
        }
    }

    return chart_dict


# ============================================
# 4. 饼图模板（Pie Charts）
# ============================================

def pie_rose_type(data: List[Dict[str, Any]], **kwargs) -> Dict[str, Any]:
    """
    玫瑰饼图模板

    适用场景：占比展示，使用半径区分大小

    输入数据格式:
    [
        {"name": "类别A", "value": 45.2},
        {"name": "类别B", "value": 32.8},
        ...
    ]

    基于：pie-roseType.ts
    """
    title = kwargs.get("title", "玫瑰饼图")
    name_key = kwargs.get("name_key", "name")
    value_key = kwargs.get("value_key", "value")
    rose_type = kwargs.get("rose_type", "radius")  # radius, area
    meta = kwargs.get("meta", {})

    if not data or not isinstance(data, list):
        raise ValueError("pie_rose_type模板需要列表数据")

    items = []
    for item in data:
        if not isinstance(item, dict):
            continue
        name = item.get(name_key)
        value = item.get(value_key)
        if name is not None and value is not None:
            items.append({"name": name, "value": value})

    chart_dict = {
        "id": f"pie_rose_{uuid.uuid4().hex[:8]}",
        "type": "pie",
        "title": title,
        "data": {
            "items": items
        },
        "options": {
            "rose_type": rose_type
        },
        "meta": {
            **meta,
            "schema_version": "3.1",
            "generator": "template:pie_rose_type",
            "item_count": len(items)
        }
    }

    return chart_dict


def pie_nest(data: Dict[str, Any], **kwargs) -> Dict[str, Any]:
    """
    嵌套饼图模板

    适用场景：层级占比展示

    输入数据格式:
    {
        "inner": [
            {"name": "A1", "value": 10},
            {"name": "A2", "value": 15}
        ],
        "outer": [
            {"name": "A", "value": 25},
            {"name": "B", "value": 30}
        ]
    }

    基于：pie-nest.ts
    """
    title = kwargs.get("title", "嵌套饼图")
    meta = kwargs.get("meta", {})

    if not isinstance(data, dict):
        raise ValueError("pie_nest模板需要字典数据")

    inner_items = data.get("inner", [])
    outer_items = data.get("outer", [])

    chart_dict = {
        "id": f"pie_nest_{uuid.uuid4().hex[:8]}",
        "type": "pie",
        "title": title,
        "data": {
            "inner": inner_items,
            "outer": outer_items
        },
        "options": {
            "nest": True
        },
        "meta": {
            **meta,
            "schema_version": "3.1",
            "generator": "template:pie_nest"
        }
    }

    return chart_dict


def pie_doughnut(data: List[Dict[str, Any]], **kwargs) -> Dict[str, Any]:
    """
    环形图模板

    适用场景：占比展示，中心可显示统计信息

    输入数据格式:
    [
        {"name": "类别A", "value": 45.2},
        {"name": "类别B", "value": 32.8},
        ...
    ]

    基于：pie-doughnut.ts
    """
    title = kwargs.get("title", "环形图")
    name_key = kwargs.get("name_key", "name")
    value_key = kwargs.get("value_key", "value")
    inner_radius = kwargs.get("inner_radius", "40%")
    meta = kwargs.get("meta", {})

    if not data or not isinstance(data, list):
        raise ValueError("pie_doughnut模板需要列表数据")

    items = []
    total = 0
    for item in data:
        if not isinstance(item, dict):
            continue
        name = item.get(name_key)
        value = item.get(value_key)
        if name is not None and value is not None:
            items.append({"name": name, "value": value})
            total += value

    chart_dict = {
        "id": f"pie_doughnut_{uuid.uuid4().hex[:8]}",
        "type": "pie",
        "title": title,
        "data": {
            "items": items,
            "center_text": f"总计\n{total}"
        },
        "options": {
            "doughnut": True,
            "inner_radius": inner_radius
        },
        "meta": {
            **meta,
            "schema_version": "3.1",
            "generator": "template:pie_doughnut",
            "item_count": len(items),
            "total": total
        }
    }

    return chart_dict


# ============================================
# 5. 仪表盘模板（Gauge Charts）
# ============================================

def gauge_progress(data: Dict[str, Any], **kwargs) -> Dict[str, Any]:
    """
    进度仪表盘模板

    适用场景：百分比进度展示

    输入数据格式:
    {
        "value": 75.5,           # 当前进度（0-100）
        "min": 0,
        "max": 100,
        "title": "完成率"
    }

    基于：gauge-progress.ts
    """
    title = kwargs.get("title", data.get("title", "进度仪表盘"))
    meta = kwargs.get("meta", {})

    if not isinstance(data, dict):
        raise ValueError("gauge_progress模板需要字典数据")

    value = data.get("value", 0)
    min_val = data.get("min", 0)
    max_val = data.get("max", 100)

    chart_dict = {
        "id": f"gauge_progress_{uuid.uuid4().hex[:8]}",
        "type": "gauge",
        "title": title,
        "data": {
            "value": value,
            "min": min_val,
            "max": max_val,
            "percentage": round((value - min_val) / (max_val - min_val) * 100, 1) if max_val > min_val else 0
        },
        "options": {
            "progress": True
        },
        "meta": {
            **meta,
            "schema_version": "3.1",
            "generator": "template:gauge_progress"
        }
    }

    return chart_dict


def gauge_stage(data: Dict[str, Any], **kwargs) -> Dict[str, Any]:
    """
    分段仪表盘模板

    适用场景：等级展示，如空气质量等级

    输入数据格式:
    {
        "value": 85.5,
        "min": 0,
        "max": 100,
        "stages": [
            {"max": 60, "color": "#67e0e3", "label": "优"},
            {"max": 80, "color": "#e6b600", "label": "良"},
            {"max": 100, "color": "#d9001b", "label": "差"}
        ]
    }

    基于：gauge-stage.ts
    """
    title = kwargs.get("title", "分段仪表盘")
    meta = kwargs.get("meta", {})

    if not isinstance(data, dict):
        raise ValueError("gauge_stage模板需要字典数据")

    value = data.get("value", 0)
    min_val = data.get("min", 0)
    max_val = data.get("max", 100)
    stages = data.get("stages", [])

    chart_dict = {
        "id": f"gauge_stage_{uuid.uuid4().hex[:8]}",
        "type": "gauge",
        "title": title,
        "data": {
            "value": value,
            "min": min_val,
            "max": max_val,
            "stages": stages
        },
        "options": {
            "stage": True
        },
        "meta": {
            **meta,
            "schema_version": "3.1",
            "generator": "template:gauge_stage"
        }
    }

    return chart_dict


def gauge_ring(data: Dict[str, Any], **kwargs) -> Dict[str, Any]:
    """
    环形仪表盘模板

    适用场景：多指标仪表盘

    输入数据格式:
    {
        "indicators": [
            {"name": "指标A", "value": 75, "max": 100},
            {"name": "指标B", "value": 60, "max": 100}
        ]
    }

    基于：gauge-ring.ts
    """
    title = kwargs.get("title", "环形仪表盘")
    meta = kwargs.get("meta", {})

    if not isinstance(data, dict):
        raise ValueError("gauge_ring模板需要字典数据")

    indicators = data.get("indicators", [])

    chart_dict = {
        "id": f"gauge_ring_{uuid.uuid4().hex[:8]}",
        "type": "gauge",
        "title": title,
        "data": {
            "indicators": indicators
        },
        "options": {
            "ring": True
        },
        "meta": {
            **meta,
            "schema_version": "3.1",
            "generator": "template:gauge_ring",
            "indicator_count": len(indicators)
        }
    }

    return chart_dict


# ============================================
# 6. 关系图模板（Graph Charts）
# ============================================

def graph_force(data: Dict[str, Any], **kwargs) -> Dict[str, Any]:
    """
    力引导关系图模板

    适用场景：网络关系展示，如污染源关系网络

    输入数据格式:
    {
        "nodes": [
            {"id": "A", "name": "节点A", "category": 0},
            {"id": "B", "name": "节点B", "category": 1}
        ],
        "links": [
            {"source": "A", "target": "B", "value": 10},
            {"source": "B", "target": "C", "value": 15}
        ],
        "categories": [
            {"name": "类别A"},
            {"name": "类别B"}
        ]
    }

    基于：graph-force.ts
    """
    title = kwargs.get("title", "力引导关系图")
    meta = kwargs.get("meta", {})

    if not isinstance(data, dict):
        raise ValueError("graph_force模板需要字典数据")

    nodes = data.get("nodes", [])
    links = data.get("links", [])
    categories = data.get("categories", [])

    chart_dict = {
        "id": f"graph_force_{uuid.uuid4().hex[:8]}",
        "type": "graph",
        "title": title,
        "data": {
            "nodes": nodes,
            "links": links,
            "categories": categories
        },
        "options": {
            "layout": "force"
        },
        "meta": {
            **meta,
            "schema_version": "3.1",
            "generator": "template:graph_force",
            "node_count": len(nodes),
            "link_count": len(links)
        }
    }

    return chart_dict


def graph_circular(data: Dict[str, Any], **kwargs) -> Dict[str, Any]:
    """
    环形布局关系图模板

    适用场景：循环关系展示

    输入数据格式:
    {
        "nodes": [...],
        "links": [...],
        "categories": [...]
    }

    基于：graph-circular-layout.ts
    """
    title = kwargs.get("title", "环形关系图")
    meta = kwargs.get("meta", {})

    if not isinstance(data, dict):
        raise ValueError("graph_circular模板需要字典数据")

    nodes = data.get("nodes", [])
    links = data.get("links", [])
    categories = data.get("categories", [])

    chart_dict = {
        "id": f"graph_circular_{uuid.uuid4().hex[:8]}",
        "type": "graph",
        "title": title,
        "data": {
            "nodes": nodes,
            "links": links,
            "categories": categories
        },
        "options": {
            "layout": "circular"
        },
        "meta": {
            **meta,
            "schema_version": "3.1",
            "generator": "template:graph_circular",
            "node_count": len(nodes),
            "link_count": len(links)
        }
    }

    return chart_dict


# ============================================
# 7. 日历图模板（Calendar Charts）
# ============================================

def calendar_heatmap(data: List[Dict[str, Any]], **kwargs) -> Dict[str, Any]:
    """
    日历热力图模板

    适用场景：时间序列日历展示，如每日污染浓度

    输入数据格式:
    [
        {"date": "2025-01-01", "value": 35.2},
        {"date": "2025-01-02", "value": 42.8},
        ...
    ]

    基于：calendar-heatmap.ts
    """
    title = kwargs.get("title", "日历热力图")
    date_key = kwargs.get("date_key", "date")
    value_key = kwargs.get("value_key", "value")
    meta = kwargs.get("meta", {})

    if not data or not isinstance(data, list):
        raise ValueError("calendar_heatmap模板需要列表数据")

    items = []
    for item in data:
        if not isinstance(item, dict):
            continue
        date = item.get(date_key)
        value = item.get(value_key)
        if date is not None and value is not None:
            items.append({"date": date, "value": value})

    chart_dict = {
        "id": f"calendar_heat_{uuid.uuid4().hex[:8]}",
        "type": "calendar",
        "title": title,
        "data": {
            "items": items
        },
        "options": {
            "heatmap": True
        },
        "meta": {
            **meta,
            "schema_version": "3.1",
            "generator": "template:calendar_heatmap",
            "day_count": len(items)
        }
    }

    return chart_dict


def calendar_pie(data: List[Dict[str, Any]], **kwargs) -> Dict[str, Any]:
    """
    日历饼图模板

    适用场景：日历上显示分类占比

    输入数据格式:
    [
        {"date": "2025-01-01", "category": "A", "value": 10},
        {"date": "2025-01-02", "category": "B", "value": 15},
        ...
    ]

    基于：calendar-pie.ts
    """
    title = kwargs.get("title", "日历饼图")
    date_key = kwargs.get("date_key", "date")
    category_key = kwargs.get("category_key", "category")
    value_key = kwargs.get("value_key", "value")
    meta = kwargs.get("meta", {})

    if not data or not isinstance(data, list):
        raise ValueError("calendar_pie模板需要列表数据")

    items = []
    for item in data:
        if not isinstance(item, dict):
            continue
        date = item.get(date_key)
        category = item.get(category_key)
        value = item.get(value_key)
        if date is not None and category is not None and value is not None:
            items.append({"date": date, "category": category, "value": value})

    chart_dict = {
        "id": f"calendar_pie_{uuid.uuid4().hex[:8]}",
        "type": "calendar",
        "title": title,
        "data": {
            "items": items
        },
        "options": {
            "pie": True
        },
        "meta": {
            **meta,
            "schema_version": "3.1",
            "generator": "template:calendar_pie",
            "day_count": len(items)
        }
    }

    return chart_dict


# ============================================
# 8. 矩形树图模板（Treemap Charts）
# ============================================

def treemap_simple(data: List[Dict[str, Any]], **kwargs) -> Dict[str, Any]:
    """
    简单矩形树图模板

    适用场景：层级占比展示

    输入数据格式:
    [
        {"name": "类别A", "value": 45.2, "category": "一类"},
        {"name": "类别B", "value": 32.8, "category": "一类"},
        ...
    ]

    基于：treemap-simple.ts
    """
    title = kwargs.get("title", "矩形树图")
    name_key = kwargs.get("name_key", "name")
    value_key = kwargs.get("value_key", "value")
    category_key = kwargs.get("category_key", "category")
    meta = kwargs.get("meta", {})

    if not data or not isinstance(data, list):
        raise ValueError("treemap_simple模板需要列表数据")

    items = []
    for item in data:
        if not isinstance(item, dict):
            continue
        name = item.get(name_key)
        value = item.get(value_key)
        category = item.get(category_key, "默认")
        if name is not None and value is not None:
            items.append({
                "name": name,
                "value": value,
                "category": category
            })

    chart_dict = {
        "id": f"treemap_{uuid.uuid4().hex[:8]}",
        "type": "treemap",
        "title": title,
        "data": {
            "items": items
        },
        "options": {
            "simple": True
        },
        "meta": {
            **meta,
            "schema_version": "3.1",
            "generator": "template:treemap_simple",
            "item_count": len(items)
        }
    }

    return chart_dict


def treemap_drill_down(data: Dict[str, Any], **kwargs) -> Dict[str, Any]:
    """
    下钻矩形树图模板

    适用场景：多层级数据展示

    输入数据格式:
    {
        "name": "根节点",
        "children": [
            {
                "name": "子节点A",
                "value": 100,
                "children": [
                    {"name": "叶子A1", "value": 30},
                    {"name": "叶子A2", "value": 70}
                ]
            }
        ]
    }

    基于：treemap-drill-down.ts
    """
    title = kwargs.get("title", "下钻矩形树图")
    meta = kwargs.get("meta", {})

    if not isinstance(data, dict):
        raise ValueError("treemap_drill_down模板需要字典数据")

    chart_dict = {
        "id": f"treemap_drill_{uuid.uuid4().hex[:8]}",
        "type": "treemap",
        "title": title,
        "data": data,
        "options": {
            "drill_down": True
        },
        "meta": {
            **meta,
            "schema_version": "3.1",
            "generator": "template:treemap_drill_down"
        }
    }

    return chart_dict


# ============================================
# 9. 桑基图模板（Sankey Charts）
# ============================================

def sankey_simple(data: Dict[str, Any], **kwargs) -> Dict[str, Any]:
    """
    简单桑基图模板

    适用场景：流向关系展示，如污染源→受体

    输入数据格式:
    {
        "nodes": ["源A", "源B", "受体C", "受体D"],
        "links": [
            {"source": "源A", "target": "受体C", "value": 45},
            {"source": "源B", "target": "受体C", "value": 32},
            {"source": "源B", "target": "受体D", "value": 18}
        ]
    }

    基于：sankey-simple.ts
    """
    title = kwargs.get("title", "桑基图")
    meta = kwargs.get("meta", {})

    if not isinstance(data, dict):
        raise ValueError("sankey_simple模板需要字典数据")

    nodes = data.get("nodes", [])
    links = data.get("links", [])

    chart_dict = {
        "id": f"sankey_{uuid.uuid4().hex[:8]}",
        "type": "sankey",
        "title": title,
        "data": {
            "nodes": nodes,
            "links": links
        },
        "options": {
            "simple": True
        },
        "meta": {
            **meta,
            "schema_version": "3.1",
            "generator": "template:sankey_simple",
            "node_count": len(nodes),
            "link_count": len(links)
        }
    }

    return chart_dict


def sankey_vertical(data: Dict[str, Any], **kwargs) -> Dict[str, Any]:
    """
    垂直桑基图模板

    适用场景：垂直流向展示

    输入数据格式:
    {
        "nodes": [...],
        "links": [...]
    }

    基于：sankey-vertical.ts
    """
    title = kwargs.get("title", "垂直桑基图")
    meta = kwargs.get("meta", {})

    if not isinstance(data, dict):
        raise ValueError("sankey_vertical模板需要字典数据")

    nodes = data.get("nodes", [])
    links = data.get("links", [])

    chart_dict = {
        "id": f"sankey_vert_{uuid.uuid4().hex[:8]}",
        "type": "sankey",
        "title": title,
        "data": {
            "nodes": nodes,
            "links": links
        },
        "options": {
            "orientation": "vertical"
        },
        "meta": {
            **meta,
            "schema_version": "3.1",
            "generator": "template:sankey_vertical",
            "node_count": len(nodes),
            "link_count": len(links)
        }
    }

    return chart_dict


# ============================================
# 模板导出字典（用于注册）
# ============================================

ECHARTS_EXTENDED_TEMPLATES = {
    # 柱状图
    "bar_stack_negative": bar_stack_negative,
    "bar_polar_radial": bar_polar_radial,
    "bar_waterfall": bar_waterfall,

    # 散点图
    "scatter_clustering": scatter_clustering,
    "scatter_matrix": scatter_matrix,
    "scatter_regression": scatter_regression,

    # 折线图
    "line_area_gradient": line_area_gradient,
    "line_step": line_step,
    "line_race": line_race,

    # 饼图
    "pie_rose_type": pie_rose_type,
    "pie_nest": pie_nest,
    "pie_doughnut": pie_doughnut,

    # 仪表盘
    "gauge_progress": gauge_progress,
    "gauge_stage": gauge_stage,
    "gauge_ring": gauge_ring,

    # 关系图
    "graph_force": graph_force,
    "graph_circular": graph_circular,

    # 日历图
    "calendar_heatmap": calendar_heatmap,
    "calendar_pie": calendar_pie,

    # 矩形树图
    "treemap_simple": treemap_simple,
    "treemap_drill_down": treemap_drill_down,

    # 桑基图
    "sankey_simple": sankey_simple,
    "sankey_vertical": sankey_vertical,
}


def get_template_info() -> Dict[str, Any]:
    """获取扩展模板信息"""
    return {
        "total_templates": len(ECHARTS_EXTENDED_TEMPLATES),
        "categories": {
            "bar": 3,
            "scatter": 3,
            "line": 3,
            "pie": 3,
            "gauge": 3,
            "graph": 2,
            "calendar": 2,
            "treemap": 2,
            "sankey": 2
        },
        "templates": list(ECHARTS_EXTENDED_TEMPLATES.keys())
    }


if __name__ == "__main__":
    # 测试模板信息
    info = get_template_info()
    print(f"ECharts扩展模板库: {info['total_templates']}个模板")
    print(f"分类: {info['categories']}")
    print(f"模板列表: {info['templates']}")
