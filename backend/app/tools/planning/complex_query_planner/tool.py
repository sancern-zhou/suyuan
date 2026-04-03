"""
复杂查询计划工具

通过单次LLM调用注入广东省相关结构化查询工具的详细 function_schema，
生成工具查询调用计划返回给主Agent执行。

支持模式：仅支持问数模式（query）和报告模式（report）
触发机制：主Agent的LLM根据工具描述自主决定是否调用
"""

import json
import structlog
from typing import Dict, Any, List

from app.tools.base.tool_interface import LLMTool, ToolCategory

logger = structlog.get_logger()


# 广东省查询工具的完整 function_schema 定义
GUANGDONG_QUERY_TOOLS_SCHEMAS = {
    "query_gd_suncere_city_day_new": {
        "name": "query_gd_suncere_city_day_new",
        "description": "查询广东省城市日空气质量数据（新标准 HJ 633-2024，返回每日六参数、AQI、首要污染物）",
        "parameters": {
            "type": "object",
            "properties": {
                "cities": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "城市列表，如 ['广州', '深圳', '珠海']"
                },
                "start_date": {
                    "type": "string",
                    "description": "开始日期，格式 YYYY-MM-DD"
                },
                "end_date": {
                    "type": "string",
                    "description": "结束日期，格式 YYYY-MM-DD"
                }
            },
            "required": ["cities", "start_date", "end_date"]
        }
    },
    "query_new_standard_report": {
        "name": "query_new_standard_report",
        "description": "查询HJ 633-2024新标准空气质量统计报表（综合指数、超标天数、达标率、六参数统计浓度）",
        "parameters": {
            "type": "object",
            "properties": {
                "cities": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "城市列表，如 ['广州', '深圳']"
                },
                "start_date": {
                    "type": "string",
                    "description": "开始日期，格式 YYYY-MM-DD"
                },
                "end_date": {
                    "type": "string",
                    "description": "结束日期，格式 YYYY-MM-DD"
                },
                "enable_sand_deduction": {
                    "type": "boolean",
                    "description": "是否启用扣沙处理（默认true）"
                }
            },
            "required": ["cities", "start_date", "end_date"]
        }
    },
    "query_old_standard_report": {
        "name": "query_old_standard_report",
        "description": "查询HJ 633-2011旧标准空气质量统计报表（综合指数、超标天数、达标率、六参数统计浓度）",
        "parameters": {
            "type": "object",
            "properties": {
                "cities": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "城市列表，如 ['广州', '深圳']"
                },
                "start_date": {
                    "type": "string",
                    "description": "开始日期，格式 YYYY-MM-DD"
                },
                "end_date": {
                    "type": "string",
                    "description": "结束日期，格式 YYYY-MM-DD"
                },
                "enable_sand_deduction": {
                    "type": "boolean",
                    "description": "是否启用扣沙处理（默认true）"
                }
            },
            "required": ["cities", "start_date", "end_date"]
        }
    },
    "query_standard_comparison": {
        "name": "query_standard_comparison",
        "description": "新旧标准对比统计查询（返回综合指数、超标天数、达标率等统计指标）",
        "parameters": {
            "type": "object",
            "properties": {
                "cities": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "城市列表"
                },
                "start_date": {
                    "type": "string",
                    "description": "开始日期，格式 YYYY-MM-DD"
                },
                "end_date": {
                    "type": "string",
                    "description": "结束日期，格式 YYYY-MM-DD"
                },
                "enable_sand_deduction": {
                    "type": "boolean",
                    "description": "是否启用扣沙处理（默认true）"
                }
            },
            "required": ["cities", "start_date", "end_date"]
        }
    },
    "compare_standard_reports": {
        "name": "compare_standard_reports",
        "description": "新标准报表对比分析（对比两个时间段的综合指数、超标天数、达标率、六参数统计、单项质量指数、首要污染物统计等全部指标）",
        "parameters": {
            "type": "object",
            "properties": {
                "cities": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "城市列表"
                },
                "query_period": {
                    "type": "object",
                    "properties": {
                        "start_date": {"type": "string", "description": "查询期开始日期，格式 YYYY-MM-DD"},
                        "end_date": {"type": "string", "description": "查询期结束日期，格式 YYYY-MM-DD"}
                    },
                    "required": ["start_date", "end_date"],
                    "description": "查询时间段"
                },
                "comparison_period": {
                    "type": "object",
                    "properties": {
                        "start_date": {"type": "string", "description": "对比期开始日期，格式 YYYY-MM-DD"},
                        "end_date": {"type": "string", "description": "对比期结束日期，格式 YYYY-MM-DD"}
                    },
                    "required": ["start_date", "end_date"],
                    "description": "对比时间段（同比/环比）"
                },
                "enable_sand_deduction": {
                    "type": "boolean",
                    "description": "是否启用扣沙处理（默认true）"
                }
            },
            "required": ["cities", "query_period", "comparison_period"]
        }
    },
    "query_xcai_city_history": {
        "name": "query_xcai_city_history",
        "description": "查询全国城市历史空气质量数据（SQL Server XcAiDb数据库，支持773个城市，包含广东省）",
        "parameters": {
            "type": "object",
            "properties": {
                "cities": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "城市名称列表，如 ['广州市', '深圳市']（需带'市'字）"
                },
                "data_type": {
                    "type": "string",
                    "enum": ["hour", "day"],
                    "description": "数据类型：hour=小时数据（2017年至今），day=日数据（2021年至今）"
                },
                "start_time": {
                    "type": "string",
                    "description": "开始时间，格式 YYYY-MM-DD HH:MM:SS"
                },
                "end_time": {
                    "type": "string",
                    "description": "结束时间，格式 YYYY-MM-DD HH:MM:SS"
                }
            },
            "required": ["cities", "data_type", "start_time", "end_time"]
        }
    },
    # 仅问数模式
    "execute_sql_query": {
        "name": "execute_sql_query",
        "description": "通用SQL执行工具，支持查看表结构和执行SQL查询（二选一）",
        "parameters": {
            "type": "object",
            "properties": {
                "describe_table": {
                    "type": "string",
                    "description": "查看表结构：输入目标表名如 'qc_history' 或 'working_orders'"
                },
                "sql": {
                    "type": "string",
                    "description": "执行SQL查询语句（中文字符串必须使用N前缀，如 WHERE StationName LIKE N'%增城%'）"
                },
                "limit": {
                    "type": "integer",
                    "description": "返回记录数限制（默认1000，最大10000）"
                }
            }
        }
    },
    "query_gd_suncere_city_day": {
        "name": "query_gd_suncere_city_day",
        "description": "查询广东省城市日空气质量数据（旧标准，返回每日六参数、AQI、首要污染物）",
        "parameters": {
            "type": "object",
            "properties": {
                "cities": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "城市列表"
                },
                "start_date": {
                    "type": "string",
                    "description": "开始日期，格式 YYYY-MM-DD"
                },
                "end_date": {
                    "type": "string",
                    "description": "结束日期，格式 YYYY-MM-DD"
                }
            },
            "required": ["cities", "start_date", "end_date"]
        }
    }
}

# 各模式可用的工具名称
MODE_TOOLS = {
    "query": [
        "query_gd_suncere_city_day_new",
        "query_new_standard_report",
        "query_old_standard_report",
        "query_standard_comparison",
        "compare_standard_reports",
        "query_xcai_city_history",
        "execute_sql_query",
        "query_gd_suncere_city_day",
    ],
    "report": [
        "query_gd_suncere_city_day_new",
        "query_new_standard_report",
        "query_old_standard_report",
        "query_standard_comparison",
        "compare_standard_reports",
        "query_xcai_city_history",
    ]
}

PLANNING_PROMPT_TEMPLATE = """你是数据查询规划专家。请根据用户需求生成工具调用计划。

## 用户需求
{query_description}

## 当前模式
{mode}模式

## 可用工具及完整参数定义
{tools_schemas}

## 输出要求
生成JSON格式的查询计划，包含：
1. plan_steps: 步骤列表，每步包含 step(int), tool(str), params(dict), reasoning(str), dependencies(list[int])
2. execution_strategy: 执行策略，包含 parallel_groups(list[list[int]]), estimated_steps(int)

## 约束条件
- 只能从可用工具列表中选择工具
- 必需参数不能缺失
- 无依赖关系的步骤应放入同一并发组
- 时间范围保持一致
- 如果需求信息不足（如缺少时间范围），在 plan_steps 中说明并返回 error 字段

## 示例输出
{{
    "plan_steps": [
        {{
            "step": 1,
            "tool": "query_new_standard_report",
            "params": {{"cities": ["广州", "深圳"], "start_date": "2025-01-01", "end_date": "2025-01-31"}},
            "reasoning": "查询新标准空气质量统计报表",
            "dependencies": []
        }},
        {{
            "step": 2,
            "tool": "compare_standard_reports",
            "params": {{"cities": ["广州", "深圳"], "query_period": {{"start_date": "2025-01-01", "end_date": "2025-01-31"}}, "comparison_period": {{"start_date": "2024-01-01", "end_date": "2024-01-31"}}}},
            "reasoning": "同比分析2025年1月与2024年1月的空气质量",
            "dependencies": []
        }}
    ],
    "execution_strategy": {{
        "parallel_groups": [[1, 2]],
        "estimated_steps": 2
    }}
}}

请直接输出JSON，不要包含其他内容。"""


class ComplexQueryPlannerTool(LLMTool):
    """
    复杂查询计划工具

    通过单次LLM调用注入广东省相关结构化查询工具的详细 function_schema，
    生成工具查询调用计划返回给主Agent执行。

    仅支持问数模式（query）和报告模式（report）。
    """

    def __init__(self):
        super().__init__(
            name="complex_query_planner",
            description="复杂查询计划工具（多数据源查询规划）。当需要同时查询多组数据、或不确定应使用哪个查询工具时调用。⚠️ 必需参数: query_description(str, 详细描述查询需求), mode(str, 当前模式: query或report)",
            category=ToolCategory.PLANNING,
            requires_context=False
        )

    def get_function_schema(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {
                    "query_description": {
                        "type": "string",
                        "description": "详细描述查询需求，包括城市、时间范围、需要的指标等"
                    },
                    "mode": {
                        "type": "string",
                        "enum": ["query", "report"],
                        "description": "当前Agent模式，query=问数模式，report=报告模式"
                    }
                },
                "required": ["query_description", "mode"]
            }
        }

    async def execute(
        self,
        query_description: str,
        mode: str,
        **kwargs
    ) -> Dict[str, Any]:
        """
        生成查询计划

        Args:
            query_description: 详细的查询需求描述
            mode: 当前模式，仅接受 "query" 或 "report"

        Returns:
            包含 plan_steps 和 execution_strategy 的查询计划
        """
        logger.info(
            "complex_query_planner_start",
            mode=mode,
            query_length=len(query_description)
        )

        if mode not in ["query", "report"]:
            return {
                "success": False,
                "error": f"不支持的模式: {mode}，仅支持 query 和 report",
                "summary": f"模式参数错误: {mode}"
            }

        tools_schemas = self._get_available_tools_schemas(mode)
        prompt = self._build_planning_prompt(query_description, mode, tools_schemas)

        try:
            plan = await self._generate_plan_with_llm(prompt)
        except Exception as e:
            logger.error("complex_query_planner_llm_failed", error=str(e))
            return {
                "success": False,
                "error": f"LLM调用失败: {str(e)}",
                "summary": "查询计划生成失败"
            }

        validated_plan = self._validate_plan(plan, tools_schemas)

        step_count = len(validated_plan.get("plan_steps", []))
        logger.info("complex_query_planner_done", steps=step_count, mode=mode)

        return {
            "success": True,
            "data": {"plan": validated_plan},
            "summary": f"生成了{step_count}步查询计划"
        }

    def _get_available_tools_schemas(self, mode: str) -> Dict[str, Any]:
        """获取该模式下可用工具的完整 schema"""
        tool_names = MODE_TOOLS.get(mode, [])
        return {
            name: GUANGDONG_QUERY_TOOLS_SCHEMAS[name]
            for name in tool_names
            if name in GUANGDONG_QUERY_TOOLS_SCHEMAS
        }

    def _format_tools_schemas(self, tools_schemas: Dict[str, Any]) -> str:
        """将工具 schema 格式化为可读文本"""
        parts = []
        for name, schema in tools_schemas.items():
            parts.append(json.dumps(schema, ensure_ascii=False, indent=2))
        return "\n\n".join(parts)

    def _build_planning_prompt(
        self,
        query_description: str,
        mode: str,
        tools_schemas: Dict[str, Any]
    ) -> str:
        return PLANNING_PROMPT_TEMPLATE.format(
            query_description=query_description,
            mode=mode,
            tools_schemas=self._format_tools_schemas(tools_schemas)
        )

    async def _generate_plan_with_llm(self, prompt: str) -> Dict[str, Any]:
        """调用LLM生成查询计划"""
        from app.services.llm_service import llm_service
        from app.utils.llm_response_parser import LLMResponseParser

        raw_response = await llm_service.call_llm_with_json_response(prompt)

        # call_llm_with_json_response 已经返回解析后的 dict
        if isinstance(raw_response, dict):
            return raw_response

        # 如果返回字符串，尝试解析
        parser = LLMResponseParser()
        parsed = parser.parse(str(raw_response))
        if parsed:
            return parsed

        raise ValueError(f"无法解析LLM响应: {str(raw_response)[:200]}")

    def _validate_plan(
        self,
        plan: Dict[str, Any],
        tools_schemas: Dict[str, Any]
    ) -> Dict[str, Any]:
        """验证计划的工具存在性和必需参数完整性"""
        if not isinstance(plan, dict):
            return {"plan_steps": [], "execution_strategy": {"parallel_groups": [], "estimated_steps": 0}, "error": "计划格式无效"}

        plan_steps = plan.get("plan_steps", [])
        valid_steps = []
        warnings = []

        for step in plan_steps:
            if not isinstance(step, dict):
                continue

            tool_name = step.get("tool", "")
            params = step.get("params", {})

            # 检查工具是否存在
            if tool_name not in tools_schemas:
                warnings.append(f"步骤{step.get('step', '?')}: 工具 '{tool_name}' 不在可用列表中，已跳过")
                continue

            # 检查必需参数
            schema = tools_schemas[tool_name]
            required_params = schema.get("parameters", {}).get("required", [])
            missing = [p for p in required_params if p not in params]
            if missing:
                warnings.append(f"步骤{step.get('step', '?')}: 工具 '{tool_name}' 缺少必需参数 {missing}")
                # 仍然保留该步骤，让主Agent决定如何处理

            valid_steps.append(step)

        result = {
            "plan_steps": valid_steps,
            "execution_strategy": plan.get("execution_strategy", {
                "parallel_groups": [],
                "estimated_steps": len(valid_steps)
            })
        }

        if warnings:
            result["warnings"] = warnings

        return result
