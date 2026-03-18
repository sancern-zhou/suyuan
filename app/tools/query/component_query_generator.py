"""
组分数据查询问题生成器

为不同组分分析工具生成专门的查询问题，确保API返回正确的数据类型。
API (180.184.91.74:9093) 返回路径：
- resultData: 碳组分 (OC, EC)
- resultOne: 水溶性离子、地壳元素、微量元素

使用示例:
    from app.tools.query.component_query_generator import generate_component_query

    # 水溶性离子查询
    question = generate_component_query("soluble", "清远市", "2025-12-24", "hourly")

    # 碳组分查询
    question = generate_component_query("carbon", "清远市", "2025-12-24", "hourly")

    # 地壳元素查询
    question = generate_component_query("crustal", "清远市", "2025-12-24", "hourly")

    # 微量元素查询
    question = generate_component_query("trace", "清远市", "2025-12-24", "hourly")

    # PMF全组分查询（需要SO4/NO3/NH4/OC/EC）
    question = generate_component_query("pmf", "清远市", "2025-12-24", "hourly")
"""
from typing import Literal


# 各组分工具所需的数据字段
COMPONENT_REQUIREMENTS = {
    "soluble": {
        "name": "水溶性离子",
        "description": "水溶性离子（阴阳离子）",
        "fields": [
            "SO4（硫酸盐）", "NO3（硝酸盐）", "NH4（铵盐）",  # 二次无机盐
            "Cl（氯离子）", "Ca（钙离子）", "Mg（镁离子）",  # 阳离子
            "K（钾离子）", "Na（钠离子）"  # 其他离子
        ],
        "api_path": "resultOne",
    },
    "carbon": {
        "name": "碳组分",
        "description": "碳质组分（OC, EC）",
        "fields": [
            "OC（有机碳）", "EC（元素碳）",
            "POC（一次有机碳）", "SOC（二次有机碳）"
        ],
        "api_path": "resultData",
    },
    "crustal": {
        "name": "地壳元素",
        "description": "地壳元素/氧化物",
        "fields": [
            "Al（铝）", "Si（硅）", "Fe（铁）", "Ca（钙）",  # 基准地壳元素
            "Mg（镁）", "K（钾）", "Na（钠）", "Ti（钛）"  # 扩展地壳元素
        ],
        "api_path": "resultOne",
    },
    "trace": {
        "name": "微量元素",
        "description": "微量元素/重金属",
        "fields": [
            "Pb（铅）", "Zn（锌）", "Cu（铜）", "Cd（镉）",  # 有色金属
            "As（砷）", "Hg（汞）", "Cr（铬）", "Ni（镍）",  # 毒性元素
            "Mn（锰）", "V（钒）", "Co（钴）"  # 过渡金属
        ],
        "api_path": "resultOne",
    },
    "pmf": {
        "name": "PMF源解析组分",
        "description": "PMF源解析所需组分（水溶性离子+碳组分）",
        "fields": [
            # 水溶性离子（必需）
            "SO4（硫酸盐）", "NO3（硝酸盐）", "NH4（铵盐）",
            # 碳组分（必需）
            "OC（有机碳）", "EC（元素碳）",
            # 可选的辅助组分
            "Cl（氯离子）", "Ca（钙离子）", "Mg（镁离子）"
        ],
        "api_path": "resultOne + resultData",
        "note": "PMF需要至少3个有效组分（SO4/NO3/NH4/OC/EC中至少3个）"
    },
    "reconstruction": {
        "name": "7大组分重构",
        "description": "7大组分重构所需全部数据",
        "fields": [
            # 水溶性离子
            "SO4", "NO3", "NH4", "Cl", "Ca", "Mg", "K", "Na",
            # 碳组分
            "OC", "EC",
            # 地壳元素
            "Al", "Si", "Fe", "Ca", "Mg", "K", "Na", "Ti",
            # 微量元素
            "Pb", "Zn", "Cu", "Cd", "As"
        ],
        "api_path": "resultOne + resultData",
    }
}


def generate_component_query(
    component_type: Literal["soluble", "carbon", "crustal", "trace", "pmf", "reconstruction"],
    location: str,
    time_range: str,
    time_granularity: str = "小时",
    include_concurrent: bool = True,
) -> str:
    """生成针对特定组分类型的查询问题。

    Args:
        component_type: 组分类型（soluble/carbon/crustal/trace/pmf/reconstruction）
        location: 地点（城市/站点名）
        time_range: 时间范围（如 "2025-12-24" 或 "2025-12-20到25"）
        time_granularity: 时间粒度（小时/日均）
        include_concurrent: 是否包含"并发查询"关键词

    Returns:
        生成的查询问题字符串
    """
    if component_type not in COMPONENT_REQUIREMENTS:
        raise ValueError(f"未知的组分类型: {component_type}，可选值: {list(COMPONENT_REQUIREMENTS.keys())}")

    req = COMPONENT_REQUIREMENTS[component_type]
    fields_str = "、".join(req["fields"])

    # 构建查询问题
    query_parts = []

    # 地点
    query_parts.append(f"{location}")

    # 时间范围
    query_parts.append(time_range)

    # 时间粒度
    if time_granularity in ["小时", "hourly"]:
        query_parts.append("时间粒度为小时")
    elif time_granularity in ["日均", "daily"]:
        query_parts.append("日均值")

    # PM2.5/PM10
    if component_type in ["pmf", "reconstruction", "soluble"]:
        query_parts.append("PM2.5组分数据")
    elif component_type == "crustal":
        query_parts.append("PM2.5地壳元素数据")
    elif component_type == "trace":
        query_parts.append("PM2.5微量元素数据")
    elif component_type == "carbon":
        query_parts.append("PM2.5碳组分数据")

    # 并发查询（增加返回完整数据的机会）
    if include_concurrent:
        query_parts.append("要求并发查询")

    # 明确列出需要的组分字段
    query_parts.append(f"要求包含 {fields_str}")

    return "，".join(query_parts)


def generate_multi_component_query(
    location: str,
    time_range: str,
    component_types: list,
    time_granularity: str = "小时",
) -> str:
    """生成包含多种组分的查询问题（单一查询，返回多种数据）。

    注意：此函数生成的查询可能返回混合数据，建议使用generate_component_query进行拆分查询。

    Args:
        location: 地点
        time_range: 时间范围
        component_types: 组分类型列表
        time_granularity: 时间粒度

    Returns:
        生成的查询问题字符串
    """
    all_fields = []
    for ct in component_types:
        if ct in COMPONENT_REQUIREMENTS:
            all_fields.extend(COMPONENT_REQUIREMENTS[ct]["fields"])

    # 去重
    unique_fields = list(dict.fromkeys(all_fields))
    fields_str = "、".join(unique_fields)

    query_parts = [
        f"{location}",
        time_range,
        f"时间粒度为{time_granularity}" if time_granularity in ["小时", "日均"] else time_granularity,
        "PM2.5组分数据",
        "要求并发查询",
        f"要求包含 {fields_str}"
    ]

    return "，".join(query_parts)


def get_query_for_tool(tool_name: str, location: str, time_range: str, time_granularity: str = "小时") -> str:
    """根据分析工具名称生成对应的查询问题。

    Args:
        tool_name: 工具名称（calculate_soluble/calculate_carbon/calculate_crustal/calculate_trace/calculate_pmf）
        location: 地点
        time_range: 时间范围
        time_granularity: 时间粒度

    Returns:
        生成的查询问题字符串
    """
    tool_to_component = {
        "calculate_soluble": "soluble",
        "calculate_carbon": "carbon",
        "calculate_crustal": "crustal",
        "calculate_trace": "trace",
        "calculate_pmf": "pmf",
        "calculate_reconstruction": "reconstruction",
    }

    component_type = tool_to_component.get(tool_name)
    if component_type is None:
        # 默认返回PMF查询（最完整的组分数据）
        component_type = "pmf"

    return generate_component_query(
        component_type=component_type,
        location=location,
        time_range=time_range,
        time_granularity=time_granularity,
    )


def explain_component_requirements() -> dict:
    """返回各组分工具的数据需求说明（用于LLM提示）。"""
    return {
        tool_name: {
            "query_template": generate_component_query(ct, "{location}", "{time_range}", "小时"),
            "required_fields": req["fields"],
            "api_path": req["api_path"],
            "description": req["description"],
        }
        for tool_name, ct in {
            "calculate_soluble": "soluble",
            "calculate_carbon": "carbon",
            "calculate_crustal": "crustal",
            "calculate_trace": "trace",
            "calculate_pmf": "pmf",
            "calculate_reconstruction": "reconstruction",
        }.items()
        for req in [COMPONENT_REQUIREMENTS[ct]]
    }
