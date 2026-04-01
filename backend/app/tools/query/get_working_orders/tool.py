"""
运维工单查询工具

从 SQL Server 数据库获取运维工单数据，
支持多维度查询和统计分析。
"""

from typing import Optional, List, Dict, Any
from datetime import datetime
import pyodbc
import structlog

from app.tools.base.tool_interface import LLMTool, ToolCategory


logger = structlog.get_logger()


class GetWorkingOrdersTool(LLMTool):
    """
    查询运维工单记录

    使用场景：
    - 查询指定站点/设备的运维工单
    - 查询特定类型工单（维护、质控、故障等）
    - 按时间范围筛选
    - 按工单状态筛选
    - 聚合统计（按站点/工单类型/状态/运维单位）

    返回：简化的结果字典，直接供 LLM 理解

    示例：
    1. "查询广州站昨天的运维工单"
       → city="广州市", start_date="2026-03-30"

    2. "查询未完成的工单"
       → status="Doing"

    3. "统计各站点工单数量"
       → aggregate_by="station"
    """

    # 默认返回记录数限制
    DEFAULT_LIMIT = 50

    def __init__(self):
        """初始化工具"""

        function_schema = {
            "name": "get_working_orders",
            "description": """
查询运维工单记录。

支持查询：
- 指定城市/站点的运维工单
- 按工单类型筛选（SupCheck巡检/Check检查/Fault故障/QCBlackOut质控等）
- 按紧急程度筛选（Urgent紧急/Middle中等/Normal普通）
- 按工单状态筛选（Finish完成/Doing进行中/Wait待办/ToAssign待分配）
- 按时间范围筛选（创建时间/完成时间）
- 按维护周期筛选（Day/Week/Month/Quarter/HalfYear）
- 聚合统计（按站点/工单类型/状态/紧急程度）

查询示例：
- "查询广州市所有工单" → city="广州市"
- "查询广州站昨天的工单" → city="广州市", start_date="2026-03-30"
- "查询未完成的工单" → status="Doing"
- "查询故障工单" → order_type="Fault"
- "统计各站点工单数量" → aggregate_by="station"
- "查询质控工单" → order_type="QCBlackOut"

参数说明：
- city: 城市名称（如："广州市"）
- station_id: 站点ID（如："1"、"21"）
- device_id: 设备ID（如："2"、"3"）
- order_type: 工单类型（SupCheck/Check/Fault/QCBlackOut/SupPowerFailure等）
- urgency_type: 紧急程度（Urgent/Middle/Normal）
- status: 工单状态（Finish/Doing/Wait/ToAssign）
- maintenance_type: 维护周期（Day/Week/Month/Quarter/HalfYear）
- start_date: 开始日期（如："2026-03-23"）
- end_date: 结束日期（如："2026-03-30"）
- time_field: 时间字段（"createtime"创建时间/"finishtime"完成时间，默认createtime）
- only_abnormal: 仅返回异常/未完成记录（True/False）
- aggregate_by: 聚合统计（"station_id"/"order_type"/"status"/"urgency_type"）
- limit: 返回记录数限制（默认50，最大500）
- order_by: 排序字段（默认："createtime DESC"）

返回格式：
{
    "success": True,
    "data": [...],  # 记录列表或聚合结果
    "summary": "查询到 50 条工单"
}
            """.strip(),
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {
                        "type": "string",
                        "description": "城市名称（如：'广州市'）"
                    },
                    "station_id": {
                        "type": "string",
                        "description": "站点ID（如：'1'、'21'）"
                    },
                    "device_id": {
                        "type": "string",
                        "description": "设备ID（如：'2'、'3'）"
                    },
                    "order_type": {
                        "type": "string",
                        "description": "工单类型（SupCheck/Check/Fault/QCBlackOut/SupPowerFailure等）"
                    },
                    "urgency_type": {
                        "type": "string",
                        "description": "紧急程度（Urgent/Middle/Normal）",
                        "enum": ["Urgent", "Middle", "Normal"]
                    },
                    "status": {
                        "type": "string",
                        "description": "工单状态（Finish/Doing/Wait/ToAssign）",
                        "enum": ["Finish", "Doing", "Wait", "ToAssign"]
                    },
                    "maintenance_type": {
                        "type": "string",
                        "description": "维护周期（Day/Week/Month/Quarter/HalfYear）",
                        "enum": ["Day", "Week", "Month", "Quarter", "HalfYear"]
                    },
                    "start_date": {
                        "type": "string",
                        "description": "开始日期（如：'2026-03-23' 或 '2026-03-23 00:00:00'）"
                    },
                    "end_date": {
                        "type": "string",
                        "description": "结束日期（如：'2026-03-30' 或 '2026-03-30 23:59:59'）"
                    },
                    "time_field": {
                        "type": "string",
                        "description": "时间字段（createtime创建时间/finishtime完成时间）",
                        "enum": ["createtime", "finishtime"],
                        "default": "createtime"
                    },
                    "only_abnormal": {
                        "type": "boolean",
                        "description": "仅返回异常/未完成记录（True/False）"
                    },
                    "aggregate_by": {
                        "type": "string",
                        "description": "聚合统计（'station_id'/'order_type'/'status'/'urgency_type'）",
                        "enum": ["station_id", "order_type", "status", "urgency_type", "maintenance_type"]
                    },
                    "limit": {
                        "type": "integer",
                        "description": "返回记录数限制（默认50，最大500）"
                    },
                    "order_by": {
                        "type": "string",
                        "description": "排序字段（默认：'createtime DESC'）"
                    }
                }
            }
        }

        super().__init__(
            name="get_working_orders",
            description="Query working orders from SQL Server",
            category=ToolCategory.QUERY,
            function_schema=function_schema,
            version="1.0.0",
            requires_context=False
        )

    async def execute(self, **kwargs) -> Dict[str, Any]:
        """
        执行运维工单查询

        返回格式：
        {
            "success": True,
            "data": [...],
            "summary": "查询到 50 条工单"
        }
        """

        try:
            # 1. 解析参数
            city = kwargs.get("city")
            station_id = kwargs.get("station_id")
            device_id = kwargs.get("device_id")
            order_type = kwargs.get("order_type")
            urgency_type = kwargs.get("urgency_type")
            status = kwargs.get("status")
            maintenance_type = kwargs.get("maintenance_type")
            start_date = kwargs.get("start_date")
            end_date = kwargs.get("end_date")
            time_field = kwargs.get("time_field", "createtime")
            only_abnormal = kwargs.get("only_abnormal", False)
            aggregate_by = kwargs.get("aggregate_by")
            limit = min(kwargs.get("limit", self.DEFAULT_LIMIT), 500)
            order_by = kwargs.get("order_by", "createtime DESC")

            logger.info(
                "工单查询开始",
                city=city,
                station_id=station_id,
                order_type=order_type,
                status=status,
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
                    city, station_id, device_id, order_type,
                    urgency_type, status, maintenance_type,
                    start_date, end_date, time_field, only_abnormal
                )
                summary = self._generate_aggregate_summary(results, aggregate_by)
            else:
                # 明细查询
                results = self._execute_detail_query(
                    connection_string,
                    city, station_id, device_id, order_type,
                    urgency_type, status, maintenance_type,
                    start_date, end_date, time_field, only_abnormal,
                    limit, order_by
                )
                summary = f"查询到 {len(results)} 条工单"

            logger.info(
                "工单查询成功",
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
                "工单查询失败",
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
        station_id: Optional[str],
        device_id: Optional[str],
        order_type: Optional[str],
        urgency_type: Optional[str],
        status: Optional[str],
        maintenance_type: Optional[str],
        start_date: Optional[str],
        end_date: Optional[str],
        time_field: str,
        only_abnormal: bool,
        limit: int,
        order_by: str
    ) -> List[Dict[str, Any]]:
        """执行明细查询"""

        conn = pyodbc.connect(connection_string, timeout=30)
        cursor = conn.cursor()

        # 构建 SQL（使用大写列名匹配数据库表结构）
        sql = f"""
            SELECT TOP ({limit})
                WORKINGORDERID, STATIONID, DEVICEID, WORKINGORDERCODE,
                CREATETIME, UPDATETIME, FINISHTIME,
                DDORDERCREATETYPE, DDWORKINGORDERTYPE, DDURGENCYTYPE, DDWORKINGORDERSTATUS,
                ORDERTITLE, ORDERCONTENT,
                CURRENTWORKFLOWSTATUS, CURRENTWORKFLOWPOINT,
                MAINTENANCETYPE, PLANFINISHTIME,
                TOTALOVERTIME, TOTALEXPENSE
            FROM working_orders
            WHERE 1=1
        """

        params = []

        # 添加筛选条件（使用大写列名）
        if city:
            # 注意：如果表中有city字段则使用，否则需要关联站点表
            sql += " AND STATIONID = ?"
            params.append(station_id)

        if station_id:
            sql += " AND STATIONID = ?"
            params.append(station_id)

        if device_id:
            sql += " AND DEVICEID LIKE ?"
            params.append(f"%{device_id}%")

        if order_type:
            sql += " AND DDWORKINGORDERTYPE = ?"
            params.append(order_type)

        if urgency_type:
            sql += " AND DDURGENCYTYPE = ?"
            params.append(urgency_type)

        if status:
            sql += " AND DDWORKINGORDERSTATUS = ?"
            params.append(status)

        if maintenance_type:
            sql += " AND MAINTENANCETYPE = ?"
            params.append(maintenance_type)

        if only_abnormal:
            # 异常定义为：未完成或超时
            sql += " AND (DDWORKINGORDERSTATUS != N'Finish' OR TOTALOVERTIME > 0)"

        if start_date:
            sql += f" AND {time_field} >= ?"
            params.append(start_date)

        if end_date:
            sql += f" AND {time_field} <= ?"
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

            # 转换 datetime 为字符串（使用大写键名）
            for key in ['CREATETIME', 'UPDATETIME', 'FINISHTIME', 'PLANFINISHTIME']:
                if isinstance(record.get(key), datetime):
                    record[key] = record[key].strftime('%Y-%m-%d %H:%M:%S')

            records.append(record)

        cursor.close()
        conn.close()

        return records

    def _execute_aggregate_query(
        self,
        connection_string: str,
        aggregate_by: str,
        city: Optional[str],
        station_id: Optional[str],
        device_id: Optional[str],
        order_type: Optional[str],
        urgency_type: Optional[str],
        status: Optional[str],
        maintenance_type: Optional[str],
        start_date: Optional[str],
        end_date: Optional[str],
        time_field: str,
        only_abnormal: bool
    ) -> List[Dict[str, Any]]:
        """执行聚合查询"""

        conn = pyodbc.connect(connection_string, timeout=30)
        cursor = conn.cursor()

        # 验证聚合字段
        valid_aggregates = ["station_id", "order_type", "status", "urgency_type", "maintenance_type"]
        if aggregate_by not in valid_aggregates:
            raise ValueError(f"不支持的聚合字段: {aggregate_by}，支持的字段: {valid_aggregates}")

        # 映射聚合字段到数据库字段（使用大写列名）
        field_mapping = {
            "station_id": "STATIONID",
            "order_type": "DDWORKINGORDERTYPE",
            "status": "DDWORKINGORDERSTATUS",
            "urgency_type": "DDURGENCYTYPE",
            "maintenance_type": "MAINTENANCETYPE"
        }
        db_field = field_mapping[aggregate_by]

        # 构建 SQL（使用大写列名）
        sql = f"""
            SELECT
                {db_field} as group_field,
                COUNT(*) as total_count,
                SUM(CASE WHEN DDWORKINGORDERSTATUS = N'Finish' THEN 1 ELSE 0 END) as finish_count,
                SUM(CASE WHEN DDWORKINGORDERSTATUS != N'Finish' THEN 1 ELSE 0 END) as pending_count,
                SUM(CASE WHEN TOTALOVERTIME > 0 THEN 1 ELSE 0 END) as overtime_count
            FROM working_orders
            WHERE 1=1
        """

        params = []

        # 添加筛选条件（使用大写列名）
        if station_id:
            sql += " AND STATIONID = ?"
            params.append(station_id)

        if device_id:
            sql += " AND DEVICEID LIKE ?"
            params.append(f"%{device_id}%")

        if order_type:
            sql += " AND DDWORKINGORDERTYPE = ?"
            params.append(order_type)

        if urgency_type:
            sql += " AND DDURGENCYTYPE = ?"
            params.append(urgency_type)

        if status:
            sql += " AND DDWORKINGORDERSTATUS = ?"
            params.append(status)

        if maintenance_type:
            sql += " AND MAINTENANCETYPE = ?"
            params.append(maintenance_type)

        if only_abnormal:
            sql += " AND (DDWORKINGORDERSTATUS != N'Finish' OR TOTALOVERTIME > 0)"

        if start_date:
            sql += f" AND {time_field} >= ?"
            params.append(start_date)

        if end_date:
            sql += f" AND {time_field} <= ?"
            params.append(end_date)

        # 分组和排序
        sql += f" GROUP BY {db_field} ORDER BY total_count DESC"

        logger.debug("执行聚合查询", sql=sql, param_count=len(params))

        # 执行查询
        cursor.execute(sql, params)

        # 转换为字典列表
        columns = [column[0] for column in cursor.description]
        records = []
        for row in cursor.fetchall():
            record = dict(zip(columns, row))

            # 计算完成率
            if record['total_count'] > 0:
                record['finish_rate'] = round(record['finish_count'] / record['total_count'] * 100, 2)
            else:
                record['finish_rate'] = 0.0

            records.append(record)

        cursor.close()
        conn.close()

        return records

    def _generate_aggregate_summary(self, results: List[Dict[str, Any]], aggregate_by: str) -> str:
        """生成聚合查询的摘要"""

        if not results:
            return f"未找到聚合结果（按 {aggregate_by}）"

        total_count = sum(r['total_count'] for r in results)
        total_finish = sum(r.get('finish_count', 0) for r in results)
        total_overtime = sum(r.get('overtime_count', 0) for r in results)

        # 计算总体完成率
        overall_finish_rate = round(total_finish / total_count * 100, 2) if total_count > 0 else 0

        return f"按 {aggregate_by} 聚合统计，共 {len(results)} 个分组，总计 {total_count} 条工单（完成 {total_finish} 条，完成率 {overall_finish_rate}%，超时 {total_overtime} 条）"
