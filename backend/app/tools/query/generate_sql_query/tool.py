"""
SQL生成与执行工具

将自然语言查询描述转换为SQL并执行，支持本地PostgreSQL/TimescaleDB数据库查询。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List, Optional, Union
import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
import time
import json

from app.tools.base.tool_interface import LLMTool, ToolCategory
from app.utils.sql_builder import SQLBuilder, get_table_schema, list_available_tables
from app.utils.sql_validator import SQLValidator, sanitize_sql_limit
from app.db.database import async_session

if TYPE_CHECKING:
    from app.agent.context import ExecutionContext

logger = structlog.get_logger()


class GenerateSQLQueryTool(LLMTool):
    """SQL生成与执行工具"""

    def __init__(self) -> None:
        function_schema = {
            "name": "generate_sql_query",
            "description": (
                "【SQL生成与执行工具】将自然语言查询描述转换为SQL查询并执行，支持本地PostgreSQL/TimescaleDB数据库。"
                ""
                "**核心功能：**"
                "- 理解自然语言查询意图，自动生成SQL查询语句"
                "- 支持本地数据库表：ERA5气象数据、地面观测数据、空气质量历史、预报数据等"
                "- 自动验证SQL安全性（只允许SELECT查询）"
                "- 支持自定义查询条件、聚合函数、JOIN操作"
                ""
                "**可用数据表：**"
                "- era5_reanalysis_data: ERA5气象再分析数据（温度、湿度、风速、边界层高度等）"
                "- observed_weather_data: 地面观测气象数据（站点观测数据）"
                "- weather_stations: 气象站点元数据"
                "- city_aqi_publish_history: 城市空气质量历史数据（PM2.5、PM10、O3、NO2、SO2、CO、AQI）"
                "- air_quality_forecast: 空气质量预报数据"
                "- fire_hotspots: 火灾热点数据（NASA FIRMS）"
                "- dust_forecasts: 沙尘预报数据（CAMS）"
                "- dust_events: 沙尘事件记录"
                ""
                "**参数说明：**"
                "- query_description: 自然语言查询描述（如"广州2025年1月平均PM2.5"）"
                "- tables: 指定查询的表名（可选，不指定则自动推断）"
                "- output_limit: 返回行数限制（默认1000，最大10000）"
                "- explain_only: 只生成SQL不执行（默认false）"
                ""
                "**安全限制：**"
                "- 只允许SELECT查询"
                "- 最大返回10000条记录"
                "- 自动验证表名白名单"
                "- 自动添加LIMIT子句"
                ""
                "**何时使用：**"
                "- 需要灵活的SQL查询（不受参数化工具限制）"
                "- 需要JOIN多个表"
                "- 需要复杂的WHERE条件"
                "- 参数化工具无法满足需求时"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query_description": {
                        "type": "string",
                        "description": "自然语言查询描述，如'广州2025年1月平均PM2.5'"
                    },
                    "tables": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "指定查询的表名列表（可选），如['city_aqi_publish_history']"
                    },
                    "output_limit": {
                        "type": "integer",
                        "description": "返回行数限制（默认1000，最大10000）",
                        "default": 1000,
                        "minimum": 1,
                        "maximum": 10000
                    },
                    "explain_only": {
                        "type": "boolean",
                        "description": "只生成SQL不执行（默认false）",
                        "default": false
                    }
                },
                "required": ["query_description"]
            }
        }

        super().__init__(
            name="generate_sql_query",
            description="Generate and execute SQL query from natural language description.",
            category=ToolCategory.QUERY,
            function_schema=function_schema,
            requires_context=True,
        )

        self.sql_builder = SQLBuilder()
        self.sql_validator = SQLValidator(max_limit=10000)

    async def execute(
        self,
        context: "ExecutionContext",
        query_description: str,
        tables: Union[List[str], None] = None,
        output_limit: int = 1000,
        explain_only: bool = False,
        **_: Any
    ) -> Dict[str, Any]:
        """执行SQL生成与查询"""

        # 参数验证
        if not query_description or not query_description.strip():
            return {
                "success": False,
                "error": "查询描述不能为空"
            }

        # 限制检查
        if output_limit > 10000:
            output_limit = 10000
        if output_limit < 1:
            output_limit = 1000

        logger.info(
            "sql_query_generation_start",
            description=query_description,
            tables=tables,
            limit=output_limit,
            explain_only=explain_only
        )

        try:
            # 步骤1：构建SQL查询
            sql = self.sql_builder.build(
                query_description=query_description,
                tables=tables,
                limit=output_limit
            )

            # 步骤2：验证SQL安全性
            is_valid, error_msg = self.sql_validator.validate(sql)
            if not is_valid:
                return {
                    "success": False,
                    "error": f"SQL安全验证失败: {error_msg}",
                    "query_description": query_description
                }

            # 步骤3：添加LIMIT（如果没有）
            sql = self.sql_validator.sanitize_limit(sql, default_limit=output_limit)

            logger.info("sql_generated", sql=sql)

            # 如果只是解释，返回SQL
            if explain_only:
                return {
                    "success": True,
                    "sql": sql,
                    "explain_only": True,
                    "summary": f"已生成SQL查询（未执行）：\n{sql}"
                }

            # 步骤4：执行SQL查询
            start_time = time.time()
            result = await self._execute_sql(sql)
            execution_time = (time.time() - start_time) * 1000  # 毫秒

            if not result["success"]:
                return {
                    "success": False,
                    "error": result["error"],
                    "sql": sql,
                    "query_description": query_description
                }

            # 步骤5：保存数据到上下文
            data_ref = None
            data_id = None
            if result["rows"]:
                try:
                    # 将查询结果转换为标准格式
                    records = self._rows_to_records(result["rows"], result["columns"])

                    data_ref = context.save_data(
                        data=records,
                        schema="query_result",
                        metadata={
                            "query_description": query_description,
                            "sql": sql,
                            "row_count": len(records),
                            "column_count": len(result["columns"]),
                            "execution_time_ms": execution_time
                        }
                    )
                    data_id = data_ref["data_id"]
                except Exception as save_error:
                    logger.warning("sql_query_save_failed", error=str(save_error))

            # 步骤6：生成返回结果
            row_count = len(result["rows"])
            sample_rows = result["rows"][:10]  # 前10行

            return {
                "success": True,
                "sql": sql,
                "data_id": data_id,
                "row_count": row_count,
                "execution_time_ms": round(execution_time, 2),
                "columns": result["columns"],
                "data_sample": sample_rows,
                "summary": (
                    f"成功执行SQL查询，返回{row_count}条记录，"
                    f"耗时{round(execution_time, 2)}ms。\n"
                    f"SQL: {sql}"
                ),
                "metadata": {
                    "query_description": query_description,
                    "tables": tables,
                    "execution_time_ms": execution_time
                }
            }

        except ValueError as ve:
            return {
                "success": False,
                "error": str(ve),
                "query_description": query_description
            }
        except Exception as e:
            logger.error("sql_query_failed", error=str(e))
            return {
                "success": False,
                "error": f"查询执行失败: {str(e)}",
                "query_description": query_description
            }

    async def _execute_sql(self, sql: str) -> Dict[str, Any]:
        """
        执行SQL查询

        Args:
            sql: SQL查询语句

        Returns:
            执行结果字典
        """
        try:
            async with async_session() as session:
                # 执行查询
                result = await session.execute(text(sql))
                rows = result.fetchall()
                columns = list(result.keys())

                return {
                    "success": True,
                    "rows": [dict(row._mapping) for row in rows],
                    "columns": columns
                }

        except Exception as e:
            logger.error("sql_execution_failed", sql=sql, error=str(e))
            return {
                "success": False,
                "error": str(e)
            }

    def _rows_to_records(
        self,
        rows: List[Dict[str, Any]],
        columns: List[str]
    ) -> List[Dict[str, Any]]:
        """
        将查询行转换为记录格式

        Args:
            rows: 查询结果行
            columns: 列名列表

        Returns:
            标准化的记录列表
        """
        records = []
        for row in rows:
            record = {}
            for col in columns:
                value = row.get(col)
                # 处理日期时间类型
                if hasattr(value, 'isoformat'):
                    value = value.isoformat()
                record[col] = value
            records.append(record)
        return records


def __init__() -> None:
    return GenerateSQLQueryTool()
