"""企业运输管控平台（Big_Data SQL Server）只读查询工具。

数据来源：大数据局对接的企业运输管控平台库（安车检测），存放企业道闸
进出场车辆通行与违规数据。表结构见 docs/2026-05数据字典-大数据对接V1.3.doc。
"""

from __future__ import annotations

import re
from typing import Dict, Optional

import structlog

from app.tools.query.execute_sql_query.tool import BaseSQLQueryTool


logger = structlog.get_logger()


# 仅开放字典 V1.3 中的新式表；旧表（Violation/Online/Offline/Basic/Regulation/records）
# 为历史遗留，不在白名单内。
BIGDATA_SQL_TABLES = [
    'Violation1',
    'Online1',
    'Offline1',
    'Basic1',
    'Regulation1',
    'Records1',
]

SCHEMA_DESCRIPTION = (
    "企业运输管控平台（Big_Data）只读 SQL 查询工具：许昌市重点企业道闸/厂区门口"
    "货运车辆通行、违规通行与企业在线状态数据，来源于大数据局对接库。"
    "支持 describe_table 查看表结构（含一条最新样例），或 sql 执行 SELECT 查询，二者必须二选一。"
    f"仅允许白名单表：{', '.join(BIGDATA_SQL_TABLES)}；database 参数固定为 'Big_Data'。"
    "只允许 SELECT，禁止 INSERT/UPDATE/DELETE/DDL 和多语句；"
    "分页必须用 TOP（SQL Server 不支持 LIMIT），未写 TOP 时自动加 TOP 50，最大 1000。"
    "企业名称/车牌等含中文的值用 N'' 前缀（如 qymc LIKE N'%水泥%'）。"
    "状态类字段（通过状态/摆杆状态/企业状态等）直接是中文文本，无需翻译映射。"
    "旧表（Violation、Online、Offline、Basic、Regulation、records，不带1后缀）不在白名单，"
    "一律使用带 1 后缀的新式表。"
    "\n\n表说明："
    "\n- Violation1（新违规行为表，车辆进出场违规通行记录）：id(UUID主键)、"
    "qymc 企业名称、cphm 车牌号码（如冀C3TEST）、cpys 车牌颜色、pfjd 排放阶段、"
    "rylx 燃油类型、tgsjq 通过时间起、tgsjz 通过时间止、tgzt 通过大门状态、"
    "bgzt 摆杆状态、createdate 接收时间；时间筛选用 createdate 或 tgsjq。"
    "示例：SELECT TOP 50 qymc, cphm, pfjd, tgsjq, tgsjz, tgzt FROM Violation1 "
    "WHERE createdate >= '2026-09-01' ORDER BY createdate DESC。"
    "\n- Online1（新在线情况表，约每2分钟全量刷新，只反映当前时刻）："
    "qymc 企业名称、qybh 企业编号、dzzt 挡车器状态、vlpzt 号牌识别机状态、"
    "qyzt 企业状态（在线/离线）、lastdate 最后在线时间、popedom 辖区、createtime 创建时间。"
    "\n- Offline1（新每日离线企业表）：qymc、qybh、qydj 企业等级、qyzt 企业状态、"
    "pdyj 判定依据、createtime 创建时间、district 辖区。"
    "\n- Basic1（新企业信息和道闸表，企业主档）：qybh 企业编号、qymc、qydz 企业地址、"
    "xkzh 许可证号、frdb 法人代表、lxr 负责人、lxdh 联系电话、dzs 道闸数、"
    "hylx 行业类型、district 辖区、lng 经度、lat 纬度。"
    "\n- Regulation1（新季节调控表，管控信息全量刷新）：qymc、gklx 企业管控类型、"
    "gkdj 管控等级、gkcs 管控措施、kssj 开始时间、jssj 结束时间、notes 备注消息、"
    "writeTime 写入时间。"
    "\n- Records1（新通行记录表，全部进出车辆）：qymc、qybh、cphm 号牌号码、"
    "cpys 车牌颜色、txsjq 通行时间起、jczt 进出场状态、bgzt 摆杆状态、"
    "pfjd 排放阶段、ryzl 燃油种类、jssj 接收时间。"
    "\n\n常用关联：Basic1 是企业主档（qybh 编号、经纬度），"
    "可与其他表按 qymc 或 qybh 关联统计各企业违规/通行量。"
    "示例：SELECT TOP 100 qymc, COUNT(*) cnt FROM Violation1 "
    "WHERE tgsjq >= '2026-08-01' GROUP BY qymc ORDER BY cnt DESC。"
)


class ExecuteBigDataSQLQueryTool(BaseSQLQueryTool):
    """查询企业运输管控平台 Big_Data 库（独立 SQL Server 实例）。"""

    def __init__(self):
        super().__init__(
            tool_name="execute_bigdata_sql_query",
            tool_description=(
                "Execute read-only SQL queries against the Big_Data transport-control "
                "SQL Server (enterprise gate violation/online/records tables)"
            ),
            schema_description=SCHEMA_DESCRIPTION,
            allowed_tables=BIGDATA_SQL_TABLES,
            default_database="Big_Data",
            allowed_databases=["Big_Data"],
            allow_information_schema_sql=False,
        )

    def _get_connection_string(self, database: str) -> str:
        """Big_Data 位于独立 SQL Server 实例，不走 XcAi 连接配置。"""
        from config.settings import Settings

        settings = Settings()
        conn_str = settings.bigdata_sqlserver_connection_string
        if database != settings.bigdata_sqlserver_database:
            conn_str = re.sub(
                r'DATABASE=\w+',
                f'DATABASE={database}',
                conn_str,
                flags=re.IGNORECASE,
            )
        return conn_str
