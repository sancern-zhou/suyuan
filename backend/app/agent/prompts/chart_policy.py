"""Mode-specific chart priorities shared by default and project prompts."""


def chart_policy_for_mode(mode: str | None) -> str:
    if mode == "query":
        return (
            "## 绘图工具优先级（共享模式约定）\n"
            "问数模式以 `execute_echarts_python`（ECharts 交互图）为主要绘图工具；"
            "风玫瑰、污染日历、气象时序等特定业务图型或固定模板使用 `create_business_chart` 辅助。"
            "`execute_python` 用于计算、数据整理，以及前述工具无法准确表达的自定义静态图。"
            "不要把问数常规趋势、比较或分布图默认转成 Python 静态图。\n"
            "只调用本轮可用工具，参数以 tool schema 为准；本约定决定模式内的绘图优先级。"
        )
    if mode in {"assistant", "expert", "report", "chart", "ppt", "ops", "social"}:
        return (
            "## 绘图工具优先级（共享模式约定）\n"
            "本模式的数据分析绘图以 `execute_python`（Matplotlib/Seaborn）为主要绘图工具，"
            "先确定分析问题，再自主设计图型、分面和多子图，遵守 execute_python_manual.md 的共享报告风格。"
            "`create_business_chart` 辅助绘制特定业务图型或固定模板；"
            "`execute_echarts_python` 辅助需要交互探索的场景，已有图表图片优先复用。\n"
            "只调用本轮可用工具，参数以 tool schema 为准；本约定决定模式内的绘图优先级。"
        )
    return ""
