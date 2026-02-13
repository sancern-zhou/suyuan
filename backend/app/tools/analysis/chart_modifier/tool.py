"""
图表动态修改工具 - 基于自然语言的图表配置修改

核心功能：
1. 解析用户的修改需求（如"改成柱状图"、"只显示前5个"）
2. 保留原有数据，只修改展示配置
3. 支持增量修改

参考：docs/可视化增强方案.md 阶段3任务3.2
"""

from typing import Dict, Any, Optional
import json
import structlog

from abc import ABC, abstractmethod

logger = structlog.get_logger()


class ChartModifier:
    """
    图表动态修改工具 - 基于自然语言的图表配置修改

    支持用户通过自然语言修改现有图表的配置
    """

    async def execute(
        self,
        context: Any,
        modification_request: str,
        current_chart: Dict[str, Any],
        data_id: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        根据修改需求更新图表配置

        Args:
            context: 执行上下文
            modification_request: 用户的修改需求（如"改成柱状图"、"只显示前5个"）
            current_chart: 当前图表配置
            data_id: 数据引用ID（可选，用于重新生成数据）

        Returns:
            {
                "status": "success",
                "success": true,
                "data": {
                    "modified_chart": {...},
                    "changes_applied": ["chart_type", "top_n"]
                },
                "summary": "已将图表改为柱状图并限制显示前5个数据"
            }
        """
        logger.info(
            "chart_modifier_start",
            modification_request=modification_request,
            current_chart_type=current_chart.get("type")
        )

        try:
            # Step 1: 使用LLM解析修改需求
            modification = await self._parse_modification_request(
                modification_request=modification_request,
                current_chart=current_chart
            )

            # Step 2: 应用修改
            modified_chart = self._apply_modification(
                current_chart=current_chart,
                modification=modification
            )

            # Step 3: 重新生成数据（如果需要）
            if data_id and modification.get("regenerate_data"):
                logger.info("regenerating_chart_data", data_id=data_id)
                # 这里可以重新调用数据转换器

            result = {
                "status": "success",
                "success": True,
                "data": {
                    "modified_chart": modified_chart,
                    "changes_applied": modification.get("changes_applied", []),
                    "reasoning": modification.get("reasoning", "")
                },
                "metadata": {
                    "tool_name": "chart_modifier",
                    "original_chart_type": current_chart.get("type"),
                    "modified_chart_type": modified_chart.get("type")
                },
                "summary": f"已应用修改：{modification.get('summary', '无')}"
            }

            logger.info(
                "chart_modifier_complete",
                changes_count=len(result["data"]["changes_applied"])
            )

            return result

        except Exception as e:
            logger.error("chart_modifier_error", error=str(e))
            return {
                "status": "failed",
                "success": False,
                "error": str(e),
                "metadata": {
                    "tool_name": "chart_modifier"
                }
            }

    async def _parse_modification_request(
        self,
        modification_request: str,
        current_chart: Dict[str, Any]
    ) -> Dict[str, Any]:
        """解析修改需求"""
        prompt = f"""你是一个图表配置专家。请分析用户的修改需求并生成修改指令。

当前图表：
类型: {current_chart.get('type')}
标题: {current_chart.get('title')}

修改需求：
{modification_request}

请生成JSON格式的修改指令：
{{
    "modification_type": "chart_type|filter|sort|aggregate|title|color",
    "new_value": "修改后的值",
    "changes_applied": ["变化的字段列表"],
    "reasoning": "修改理由",
    "regenerate_data": true/false,
    "summary": "修改摘要"
}}

支持的修改类型：
- chart_type: 图表类型（bar, line, pie, timeseries, scatter, heatmap, wind_rose）
- filter: 过滤数据（如"只显示前5个" -> {{"type": "top_n", "value": 5}}）
- sort: 排序（如"按浓度从高到低" -> {{"field": "value", "order": "desc"}}）
- aggregate: 聚合方式（mean, sum, count）
- title: 图表标题
- color: 颜色配置

示例：
输入: "改成柱状图"
输出: {{
    "modification_type": "chart_type",
    "new_value": "bar",
    "changes_applied": ["type", "data.type"],
    "reasoning": "用户明确要求使用柱状图",
    "regenerate_data": false,
    "summary": "将图表改为柱状图"
}}

输入: "只显示前5个站点"
输出: {{
    "modification_type": "filter",
    "new_value": {{"type": "top_n", "field": "category", "value": 5}},
    "changes_applied": ["data"],
    "reasoning": "用户要求限制显示数量",
    "regenerate_data": true,
    "summary": "限制显示前5个站点"
}}

输入: "按浓度从高到低排序"
输出: {{
    "modification_type": "sort",
    "new_value": {{"field": "value", "order": "desc"}},
    "changes_applied": ["data"],
    "reasoning": "用户要求按浓度降序排列",
    "regenerate_data": true,
    "summary": "按浓度从高到低排序"
}}
"""
        try:
            from app.external_apis.dify_client import DifyClient
            dify_client = DifyClient()

            response = await dify_client.chat(
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"}
            )

            content = response.get("content", "{}")
            if isinstance(content, str):
                modification = json.loads(content)
            else:
                modification = content

            logger.info("modification_parsed", modification_type=modification.get("modification_type"))
            return modification

        except Exception as e:
            logger.error("llm_parsing_failed", error=str(e))
            # 降级到基于关键词的简单解析
            return self._parse_modification_keyword_based(modification_request, current_chart)

    def _parse_modification_keyword_based(
        self,
        modification_request: str,
        current_chart: Dict[str, Any]
    ) -> Dict[str, Any]:
        """基于关键词的简单解析（降级方案）"""
        request_lower = modification_request.lower()

        # 图表类型修改
        if any(keyword in request_lower for keyword in ["改成", "改为", "换"]):
            if "柱状图" in request_lower or "bar" in request_lower:
                return {
                    "modification_type": "chart_type",
                    "new_value": "bar",
                    "changes_applied": ["type"],
                    "reasoning": "用户要求改为柱状图",
                    "regenerate_data": False,
                    "summary": "将图表改为柱状图"
                }
            elif "饼图" in request_lower or "pie" in request_lower:
                return {
                    "modification_type": "chart_type",
                    "new_value": "pie",
                    "changes_applied": ["type"],
                    "reasoning": "用户要求改为饼图",
                    "regenerate_data": True,
                    "summary": "将图表改为饼图"
                }
            elif "折线图" in request_lower or "line" in request_lower:
                return {
                    "modification_type": "chart_type",
                    "new_value": "line",
                    "changes_applied": ["type"],
                    "reasoning": "用户要求改为折线图",
                    "regenerate_data": False,
                    "summary": "将图表改为折线图"
                }
            elif "时序图" in request_lower or "timeseries" in request_lower:
                return {
                    "modification_type": "chart_type",
                    "new_value": "timeseries",
                    "changes_applied": ["type"],
                    "reasoning": "用户要求改为时序图",
                    "regenerate_data": False,
                    "summary": "将图表改为时序图"
                }

        # 数量限制
        if "前" in request_lower and "个" in request_lower:
            import re
            match = re.search(r"前(\d+)个", request_lower)
            if match:
                count = int(match.group(1))
                return {
                    "modification_type": "filter",
                    "new_value": {"type": "top_n", "value": count},
                    "changes_applied": ["data"],
                    "reasoning": f"用户要求限制显示前{count}个",
                    "regenerate_data": True,
                    "summary": f"限制显示前{count}个"
                }

        # 排序
        if "排序" in request_lower or "从高到低" in request_lower or "从低到高" in request_lower:
            order = "desc" if "从高到低" in request_lower else "asc"
            return {
                "modification_type": "sort",
                "new_value": {"order": order},
                "changes_applied": ["data"],
                "reasoning": f"用户要求{order}排序",
                "regenerate_data": True,
                "summary": f"按{order}排序"
            }

        # 标题修改
        if any(keyword in request_lower for keyword in ["标题", "改为", "改成"]):
            # 提取新标题（简化处理）
            new_title = request_lower.split("标题")[1].strip() if "标题" in request_lower else "新标题"
            return {
                "modification_type": "title",
                "new_value": new_title,
                "changes_applied": ["title"],
                "reasoning": "用户要求修改标题",
                "regenerate_data": False,
                "summary": "修改图表标题"
            }

        # 默认：无法解析
        return {
            "modification_type": "none",
            "new_value": None,
            "changes_applied": [],
            "reasoning": "无法解析修改需求",
            "regenerate_data": False,
            "summary": "未应用任何修改"
        }

    def _apply_modification(
        self,
        current_chart: Dict[str, Any],
        modification: Dict[str, Any]
    ) -> Dict[str, Any]:
        """应用修改"""
        modified_chart = current_chart.copy()
        modification_type = modification.get("modification_type")

        if modification_type == "chart_type":
            # 修改图表类型
            new_type = modification.get("new_value")
            modified_chart["type"] = new_type
            modified_chart["data"]["type"] = new_type
            modified_chart["id"] = f"{new_type}_modified"

        elif modification_type == "title":
            # 修改标题
            new_title = modification.get("new_value")
            modified_chart["title"] = new_title

        elif modification_type == "filter":
            # 过滤数据
            filter_config = modification.get("new_value", {})
            if filter_config.get("type") == "top_n":
                modified_chart = self._apply_top_n_filter(modified_chart, filter_config.get("value", 10))

        elif modification_type == "sort":
            # 排序数据
            sort_config = modification.get("new_value", {})
            modified_chart = self._apply_sort(modified_chart, sort_config)

        elif modification_type == "aggregate":
            # 聚合
            agg_config = modification.get("new_value", {})
            modified_chart = self._apply_aggregate(modified_chart, agg_config)

        return modified_chart

    def _apply_top_n_filter(self, chart: Dict[str, Any], top_n: int) -> Dict[str, Any]:
        """应用Top-N过滤"""
        modified_chart = chart.copy()
        chart_type = chart.get("type")

        if chart_type == "pie" and "data" in chart:
            # 饼图：限制数据项数量
            pie_data = modified_chart["data"]["data"]
            if isinstance(pie_data, list):
                modified_chart["data"]["data"] = pie_data[:top_n]

        elif chart_type == "bar" and "data" in chart:
            # 柱状图：限制数据点数量
            bar_data = modified_chart["data"]["data"]
            if isinstance(bar_data, dict) and "x" in bar_data and "y" in bar_data:
                x = bar_data["x"][:top_n]
                y = bar_data["y"][:top_n]
                modified_chart["data"]["data"] = {"x": x, "y": y}

        return modified_chart

    def _apply_sort(self, chart: Dict[str, Any], sort_config: Dict[str, Any]) -> Dict[str, Any]:
        """应用排序"""
        modified_chart = chart.copy()
        order = sort_config.get("order", "desc")

        if modified_chart.get("type") == "pie" and "data" in modified_chart:
            # 饼图：按值排序
            pie_data = modified_chart["data"]["data"]
            if isinstance(pie_data, list):
                pie_data.sort(key=lambda x: x.get("value", 0), reverse=(order == "desc"))
                modified_chart["data"]["data"] = pie_data

        elif modified_chart.get("type") == "bar" and "data" in modified_chart:
            # 柱状图：按y值排序
            bar_data = modified_chart["data"]["data"]
            if isinstance(bar_data, dict) and "x" in bar_data and "y" in bar_data:
                combined = list(zip(bar_data["x"], bar_data["y"]))
                combined.sort(key=lambda x: x[1], reverse=(order == "desc"))
                modified_chart["data"]["data"] = {
                    "x": [x[0] for x in combined],
                    "y": [x[1] for x in combined]
                }

        return modified_chart

    def _apply_aggregate(self, chart: Dict[str, Any], agg_config: Dict[str, Any]) -> Dict[str, Any]:
        """应用聚合（简化实现）"""
        # 这里可以添加更复杂的聚合逻辑
        # 目前主要是标记需要重新生成数据
        logger.info("aggregate_applied", agg_config=agg_config)
        return chart


# ============================================
# 便捷函数
# ============================================

async def modify_chart(
    context: Any,
    modification_request: str,
    current_chart: Dict[str, Any],
    data_id: Optional[str] = None,
    **kwargs
) -> Dict[str, Any]:
    """
    快速修改图表

    Args:
        context: 执行上下文
        modification_request: 修改需求
        current_chart: 当前图表
        data_id: 数据ID（可选）

    Returns:
        修改后的图表
    """
    modifier = ChartModifier()
    return await modifier.execute(context, modification_request, current_chart, data_id, **kwargs)


# ============================================
# 示例用法
# ============================================

if __name__ == "__main__":
    import asyncio

    async def example():
        """示例：用户修改图表"""
        current_chart = {
            "id": "pie_chart",
            "type": "pie",
            "title": "站点PM2.5浓度占比",
            "data": {
                "type": "pie",
                "data": [
                    {"name": "广州", "value": 35.2},
                    {"name": "深圳", "value": 28.5},
                    {"name": "北京", "value": 45.8},
                    {"name": "上海", "value": 38.2}
                ]
            }
        }

        # 模拟context
        class MockContext:
            def __init__(self):
                self.requires_context = False

        context = MockContext()

        # 修改1：改成柱状图
        result1 = await modify_chart(
            context=context,
            modification_request="改成柱状图",
            current_chart=current_chart
        )

        print("=== 修改1：改成柱状图 ===")
        print(f"原始类型: {current_chart['type']}")
        print(f"修改后类型: {result1['data']['modified_chart']['type']}")
        print(f"应用的变化: {result1['data']['changes_applied']}")
        print()

        # 修改2：只显示前3个
        result2 = await modify_chart(
            context=context,
            modification_request="只显示前3个站点",
            current_chart=current_chart
        )

        print("=== 修改2：限制数量 ===")
        print(f"原始数据项数: {len(current_chart['data']['data'])}")
        print(f"修改后数据项数: {len(result2['data']['modified_chart']['data']['data'])}")
        print(f"应用的变化: {result2['data']['changes_applied']}")
        print()

        # 修改3：按浓度从高到低排序
        result3 = await modify_chart(
            context=context,
            modification_request="按浓度从高到低排序",
            current_chart=current_chart
        )

        print("=== 修改3：排序 ===")
        print(f"排序后数据: {result3['data']['modified_chart']['data']['data']}")

    asyncio.run(example())
