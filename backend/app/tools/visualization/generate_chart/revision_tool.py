"""
图表修订工具（v3.1）

独立工具，用于修订已生成的图表配置
"""
from typing import Dict, Any, Optional
import structlog

from app.tools.base.tool_interface import LLMTool, ToolCategory
from app.tools.visualization.generate_chart.tool import GenerateChartTool

logger = structlog.get_logger()


class GenerateChartRevisionTool(LLMTool):
    """
    图表修订工具 - LLM驱动的多轮交互修改

    核心职责：
    1. 修订已有图表配置（支持Chart v3.1全部15种类型）
    2. 支持自然语言修订指令
    3. 版本追踪（revision_count、revision_from）
    4. LLM智能理解修订意图

    使用场景：
    1. 修改图表类型：柱状图 → 饼图
    2. 调整数据范围：仅显示TOP 10
    3. 优化样式：修改标题、颜色、布局
    4. 增加元素：添加趋势线、标注、注释
    5. 多轮迭代：连续修订直到满意

    与 generate_chart 的区别：
    ┌────────────────────────────────────────────────────────┐
    │ revise_chart                    generate_chart        │
    ├────────────────────────────────────────────────────────┤
    │ 修订已有图表（data_id）         生成新图表（原始数据） │
    │ 保留原始配置，增量修改          从零开始生成           │
    │ 版本追踪（revision_count）      无版本概念             │
    │ 输入: chart_id + instruction    输入: raw data         │
    │ LLM理解修改意图                 LLM分析数据结构        │
    └────────────────────────────────────────────────────────┘

    决策规则：
    - 需要修改已有图表 → 使用 revise_chart
    - 需要生成新图表 → 使用 generate_chart
    """

    def __init__(self):
        function_schema = {
            "name": "revise_chart",
            "description": """
修订已生成的图表配置（支持Chart v3.1全部15种类型）。

使用场景：
1. **修改图表类型**: 柱状图改为饼图
2. **调整数据范围**: 仅显示TOP 10
3. **优化样式**: 修改标题、颜色、字体
4. **增加元素**: 添加趋势线、标注
5. **多轮迭代**: 连续修订直到满意

输入要求：
- original_chart_id: 必须是已存储的图表data_id（格式：chart_config:xxx）
- revision_instruction: 自然语言修订指令（尽量具体）

输出格式：UDF v2.0标准格式（含visuals字段）

重要：
- 不能修订不存在的图表（必须先使用generate_chart生成）
- 修订指令需明确具体（"改成饼图"优于"优化一下"）
- 支持版本追踪（每次修订revision_count+1）
            """.strip(),
            "parameters": {
                "type": "object",
                "properties": {
                    "original_chart_id": {
                        "type": "string",
                        "description": """
原始图表的data_id（格式：chart_config:xxx）。

必须是已存储的图表配置ID，可以从：
1. generate_chart返回的metadata.data_id字段获取
2. smart_chart_generator返回的metadata.data_id字段获取
3. 之前revise_chart返回的metadata.data_id字段获取

示例：
- "chart_config:abc123"
- "chart_config:revised_def456"
                        """.strip()
                    },
                    "revision_instruction": {
                        "type": "string",
                        "description": """
修订指令（自然语言），描述需要修改的内容。

建议格式：
- **具体明确**: "将柱状图改为饼图" 优于 "优化一下"
- **单一指令**: 一次修订聚焦一个改动
- **明确参数**: "只显示TOP 10" 优于 "减少数据量"

支持的修订类型：
1. **类型转换**: "改成饼图"、"换成时序图"
2. **数据筛选**: "只显示TOP 10"、"过滤掉小于10的值"
3. **样式调整**: "标题改为'XXX'"、"改用蓝色系"
4. **元素增减**: "添加趋势线"、"标注最大值"
5. **布局优化**: "横向显示"、"增加图例"

示例：
- "将柱状图改为饼图，显示百分比"
- "只保留TOP 10污染源，按降序排列"
- "修改标题为'深圳市PM2.5浓度对比'"
- "添加平均值参考线"
                        """.strip()
                    }
                },
                "required": ["original_chart_id", "revision_instruction"]
            }
        }

        super().__init__(
            name="revise_chart",
            description="Revise existing chart configurations using LLM (Chart v3.1)",
            category=ToolCategory.VISUALIZATION,
            function_schema=function_schema,
            version="1.0.0",
            requires_context=True
        )

        # 复用GenerateChartTool的revise_chart实现
        self._chart_tool = GenerateChartTool()

    async def execute(
        self,
        context: Any,
        original_chart_id: str,
        revision_instruction: str,
        **kwargs
    ) -> Dict[str, Any]:
        """
        执行图表修订

        Args:
            context: 执行上下文
            original_chart_id: 原始图表的data_id
            revision_instruction: 修订指令
            **kwargs: 额外参数

        Returns:
            UDF v2.0格式，包含修订后的图表（visuals字段）
        """
        logger.info(
            "revise_chart_tool_execute",
            original_chart_id=original_chart_id,
            instruction_preview=revision_instruction[:100]
        )

        # 调用GenerateChartTool的revise_chart方法
        return await self._chart_tool.revise_chart(
            context=context,
            original_chart_id=original_chart_id,
            revision_instruction=revision_instruction,
            **kwargs
        )
