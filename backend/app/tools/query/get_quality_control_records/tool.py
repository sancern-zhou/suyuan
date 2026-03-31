"""
质控例行检查记录查询工具

轻量级查询工具，直接从 SQL Server 数据库获取质控数据，
无需本地存储，适合 Agent 问数模式。
"""

from typing import Optional, List, Dict, Any
from datetime import datetime
import pyodbc
import structlog

from app.tools.base.tool_interface import LLMTool, ToolCategory


logger = structlog.get_logger()


class GetQualityControlRecordsTool(LLMTool):
    """
    查询质控例行检查记录（轻量级，无本地存储）

    使用场景：
    - 查询指定城市/站点的质控记录
    - 查询异常记录（超控制限、超警告限等）
    - 按时间范围筛选
    - 按质控项目筛选
    - 按运维单位筛选
    - 聚合统计（按城市/站点/质控项目/运维单位）

    返回：简化的结果字典，直接供 LLM 理解

    示例：
    1. "广州站昨天有哪些异常记录？"
       → city="广州市", start_date="2026-03-30", only_abnormal=True

    2. "钼转换效率偏低的站点有哪些？"
       → qc_result="钼转换效率偏低"

    3. "统计各城市的质控记录数"
       → aggregate_by="city"
    """

    # 默认返回记录数限制
    DEFAULT_LIMIT = 50

    def __init__(self):
        """初始化工具"""

        function_schema = {
            "name": "get_quality_control_records",
            "description": """
查询质控例行检查记录（轻量级，无本地存储）。

支持查询：
- 指定城市/站点的质控记录
- 异常记录查询（超控制限、超警告限、钼转换效率偏低等）
- 按时间范围筛选
- 按质控项目筛选（NO/CO/O3/SO2的零点/跨度/精度检查）
- 按运维单位筛选
- 聚合统计（按城市/站点/质控项目/运维单位）

查询示例：
- "查询广州市所有质控记录" → city="广州市"
- "广州站昨天有哪些异常记录？" → city="广州市", start_date="2026-03-30", only_abnormal=True
- "钼转换效率偏低的站点有哪些？" → qc_result="钼转换效率偏低"
- "统计各城市的质控合格率" → aggregate_by="city"
- "查询NO_零点检查的记录" → qc_item="NO_零点检查"

参数说明：
- city: 城市名称（如："广州市"）
- station: 站点名称（如："东澳岛"）
- qc_item: 质控项目（如："NO_零点检查"、"O3_跨度检查"）
- qc_result: 质控结果（如："超控制限"、"超警告限"、"钼转换效率偏低"）
- start_date: 开始日期（如："2026-03-23"）
- end_date: 结束日期（如："2026-03-30"）
- operation_unit: 运维单位
- only_abnormal: 仅返回异常记录（True/False）
- aggregate_by: 聚合统计（"city"/"station"/"qc_item"/"operation_unit"）
- limit: 返回记录数限制（默认50，最大500）
- order_by: 排序字段（默认："start_time DESC"）

返回格式：
{
    "success": True,
    "data": [...],  # 记录列表或聚合结果
    "summary": "查询到 50 条质控记录"
}
            """.strip(),
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {
                        "type": "string",
                        "description": "城市名称（如：'广州市'）"
                    },
                    "station": {
                        "type": "string",
                        "description": "站点名称（如：'东澳岛'）"
                    },
                    "qc_item": {
                        "type": "string",
                        "description": "质控项目（如：'NO_零点检查'、'O3_跨度检查'）"
                    },
                    "qc_result": {
                        "type": "string",
                        "description": "质控结果（如：'超控制限'、'超警告限'、'钼转换效率偏低'）"
                    },
                    "start_date": {
                        "type": "string",
                        "description": "开始日期（如：'2026-03-23' 或 '2026-03-23 00:00:00'）"
                    },
                    "end_date": {
                        "type": "string",
                        "description": "结束日期（如：'2026-03-30' 或 '2026-03-30 23:59:59'）"
                    },
                    "operation_unit": {
                        "type": "string",
                        "description": "运维单位（如：'广州华粤科技有限公司'）"
                    },
                    "only_abnormal": {
                        "type": "boolean",
                        "description": "仅返回异常记录（True/False）"
                    },
                    "aggregate_by": {
                        "type": "string",
                        "description": "聚合统计（'city'/'station'/'qc_item'/'operation_unit'）",
                        "enum": ["city", "station", "qc_item", "operation_unit"]
                    },
                    "limit": {
                        "type": "integer",
                        "description": "返回记录数限制（默认50，最大500）"
                    },
                    "order_by": {
                        "type": "string",
                        "description": "排序字段（默认：'start_time DESC'）"
                    }
                }
            }
        }

        super().__init__(
            name="get_quality_control_records",
            description="Query quality control records from SQL Server (lightweight, no local storage)",
            category=ToolCategory.QUERY,
            function_schema=function_schema,
            version="1.0.0",
            requires_context=False  # 不需要 Context（无本地存储）
        )

    async def execute(self, **kwargs) -> Dict[str, Any]:
        """
        执行质控记录查询

        参数说明：
        - city: 城市名称（如："广州市"）
        - station: 站点名称（如："东澳岛"）
        - qc_item: 质控项目（如："NO_零点检查"、"O3_跨度检查"）
        - qc_result: 质控结果（如："超控制限"、"超警告限"、"钼转换效率偏低"）
        - start_date: 开始日期（如："2026-03-23" 或 "2026-03-23 00:00:00"）
        - end_date: 结束日期（如："2026-03-30" 或 "2026-03-30 23:59:59"）
        - operation_unit: 运维单位（如："广州华粤科技有限公司"）
        - only_abnormal: 仅返回异常记录（True/False）
        - aggregate_by: 聚合统计（"city"/"station"/"qc_item"/"operation_unit"）
        - limit: 返回记录数限制（默认50，最大500）
        - order_by: 排序字段（默认："start_time DESC"）

        返回格式：
        {
            "success": True,
            "data": [...],  # 记录列表或聚合结果
            "summary": "查询到 50 条质控记录"
        }
        """

        try:
            # 1. 解析参数
            city = kwargs.get("city")
            station = kwargs.get("station")
            qc_item = kwargs.get("qc_item")
            qc_result = kwargs.get("qc_result")
            start_date = kwargs.get("start_date")
            end_date = kwargs.get("end_date")
            operation_unit = kwargs.get("operation_unit")
            only_abnormal = kwargs.get("only_abnormal", False)
            aggregate_by = kwargs.get("aggregate_by")
            limit = min(kwargs.get("limit", self.DEFAULT_LIMIT), 500)  # 最大500条
            order_by = kwargs.get("order_by", "start_time DESC")

            logger.info(
                "质控查询开始",
                city=city,
                station=station,
                qc_item=qc_item,
                qc_result=qc_result,
                only_abnormal=only_abnormal,
                aggregate_by=aggregate_by,
                limit=limit
            )

            # 2. 获取数据库连接
            connection_string = self._get_connection_string()

            # 3. 构建并执行 SQL
            if aggregate_by:
                # 聚合查询
                results = self._execute_aggregate_query(
                    connection_string,
                    aggregate_by,
                    city, station, qc_item, qc_result,
                    start_date, end_date, operation_unit, only_abnormal
                )
                summary = self._generate_aggregate_summary(results, aggregate_by)
            else:
                # 明细查询
                results = self._execute_detail_query(
                    connection_string,
                    city, station, qc_item, qc_result,
                    start_date, end_date, operation_unit, only_abnormal,
                    limit, order_by
                )
                summary = f"查询到 {len(results)} 条质控记录"

            logger.info(
                "质控查询成功",
                result_count=len(results),
                aggregate_by=aggregate_by
            )

            # 4. 返回简化结果
            return {
                "success": True,
                "data": results,
                "summary": summary
            }

        except Exception as e:
            logger.error(
                "质控查询失败",
                error=str(e),
                error_type=type(e).__name__
            )
            return {
                "success": False,
                "data": [],
                "summary": f"查询失败: {str(e)}"
            }

    def _get_connection_string(self) -> str:
        """获取 SQL Server 连接字符串"""
        # 复用现有的 SQL Server 配置
        try:
            from config.settings import Settings
            settings = Settings()
            return settings.sqlserver_connection_string
        except Exception as e:
            logger.error("获取数据库配置失败", error=str(e))
            raise

    def _execute_detail_query(
        self,
        connection_string: str,
        city: Optional[str],
        station: Optional[str],
        qc_item: Optional[str],
        qc_result: Optional[str],
        start_date: Optional[str],
        end_date: Optional[str],
        operation_unit: Optional[str],
        only_abnormal: bool,
        limit: int,
        order_by: str
    ) -> List[Dict[str, Any]]:
        """执行明细查询"""

        conn = pyodbc.connect(connection_string, timeout=30)
        cursor = conn.cursor()

        # 构建 SQL
        sql = f"""
            SELECT TOP ({limit})
                id, province, city, operation_unit, station,
                start_time, end_time, task_group, qc_item, qc_result,
                response_value, target_value, error_value,
                molybdenum_efficiency, warning_limit, control_limit
            FROM quality_control_records
            WHERE 1=1
        """

        params = []

        # 添加筛选条件（使用 COLLATE 强制 Unicode 比较）
        if city:
            sql += " AND city COLLATE Chinese_PRC_CI_AS = ?"
            params.append(city)

        if station:
            sql += " AND station COLLATE Chinese_PRC_CI_AS = ?"
            params.append(station)

        if qc_item:
            sql += " AND qc_item COLLATE Chinese_PRC_CI_AS = ?"
            params.append(qc_item)

        if qc_result:
            sql += " AND qc_result COLLATE Chinese_PRC_CI_AS = ?"
            params.append(qc_result)
        elif only_abnormal:
            sql += " AND qc_result COLLATE Chinese_PRC_CI_AS != N'合格'"

        if operation_unit:
            sql += " AND operation_unit COLLATE Chinese_PRC_CI_AS = ?"
            params.append(operation_unit)

        if start_date:
            sql += " AND start_time >= ?"
            params.append(start_date)

        if end_date:
            sql += " AND start_time <= ?"
            params.append(end_date)

        # 排序
        sql += f" ORDER BY {order_by}"

        logger.debug("执行明细查询", sql=sql, param_count=len(params))

        # 执行查询
        cursor.execute(sql, params)

        # 转换为字典列表
        columns = [column[0] for column in cursor.description]
        records = []
        for row in cursor.fetchall():
            record = dict(zip(columns, row))

            # 转换 datetime 为字符串
            if isinstance(record.get('start_time'), datetime):
                record['start_time'] = record['start_time'].strftime('%Y-%m-%d %H:%M:%S')
            if isinstance(record.get('end_time'), datetime):
                record['end_time'] = record['end_time'].strftime('%Y-%m-%d %H:%M:%S')

            records.append(record)

        cursor.close()
        conn.close()

        return records

    def _execute_aggregate_query(
        self,
        connection_string: str,
        aggregate_by: str,
        city: Optional[str],
        station: Optional[str],
        qc_item: Optional[str],
        qc_result: Optional[str],
        start_date: Optional[str],
        end_date: Optional[str],
        operation_unit: Optional[str],
        only_abnormal: bool
    ) -> List[Dict[str, Any]]:
        """执行聚合查询"""

        conn = pyodbc.connect(connection_string, timeout=30)
        cursor = conn.cursor()

        # 验证聚合字段
        valid_aggregates = ["city", "station", "qc_item", "operation_unit"]
        if aggregate_by not in valid_aggregates:
            raise ValueError(f"不支持的聚合字段: {aggregate_by}，支持的字段: {valid_aggregates}")

        # 构建 SQL
        sql = f"""
            SELECT
                {aggregate_by},
                COUNT(*) as total_count,
                SUM(CASE WHEN qc_result COLLATE Chinese_PRC_CI_AS = N'合格' THEN 1 ELSE 0 END) as pass_count,
                SUM(CASE WHEN qc_result COLLATE Chinese_PRC_CI_AS != N'合格' THEN 1 ELSE 0 END) as fail_count
            FROM quality_control_records
            WHERE 1=1
        """

        params = []

        # 添加筛选条件（使用 COLLATE 强制 Unicode 比较）
        if city:
            sql += " AND city COLLATE Chinese_PRC_CI_AS = ?"
            params.append(city)

        if station:
            sql += " AND station COLLATE Chinese_PRC_CI_AS = ?"
            params.append(station)

        if qc_item:
            sql += " AND qc_item COLLATE Chinese_PRC_CI_AS = ?"
            params.append(qc_item)

        if qc_result:
            sql += " AND qc_result COLLATE Chinese_PRC_CI_AS = ?"
            params.append(qc_result)
        elif only_abnormal:
            sql += " AND qc_result COLLATE Chinese_PRC_CI_AS != N'合格'"

        if operation_unit:
            sql += " AND operation_unit COLLATE Chinese_PRC_CI_AS = ?"
            params.append(operation_unit)

        if start_date:
            sql += " AND start_time >= ?"
            params.append(start_date)

        if end_date:
            sql += " AND start_time <= ?"
            params.append(end_date)

        # 分组和排序
        sql += f" GROUP BY {aggregate_by} ORDER BY total_count DESC"

        logger.debug("执行聚合查询", sql=sql, param_count=len(params))

        # 执行查询
        cursor.execute(sql, params)

        # 转换为字典列表
        columns = [column[0] for column in cursor.description]
        records = []
        for row in cursor.fetchall():
            record = dict(zip(columns, row))

            # 计算合格率
            if record['total_count'] > 0:
                record['pass_rate'] = round(record['pass_count'] / record['total_count'] * 100, 2)
            else:
                record['pass_rate'] = 0.0

            records.append(record)

        cursor.close()
        conn.close()

        return records

    def _generate_aggregate_summary(self, results: List[Dict[str, Any]], aggregate_by: str) -> str:
        """生成聚合查询的摘要"""

        if not results:
            return f"未找到聚合结果（按 {aggregate_by}）"

        total_count = sum(r['total_count'] for r in results)
        total_pass = sum(r.get('pass_count', 0) for r in results)

        # 计算总体合格率
        overall_pass_rate = round(total_pass / total_count * 100, 2) if total_count > 0 else 0

        return f"按 {aggregate_by} 聚合统计，共 {len(results)} 个分组，总计 {total_count} 条记录（合格 {total_pass} 条，合格率 {overall_pass_rate}%）"
