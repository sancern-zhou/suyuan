"""
SQL Server客户端（XcAiDb数据库）

封装pyodbc连接，提供参数化查询能力
"""
from typing import List, Dict, Any
import pyodbc
import structlog
from datetime import datetime


logger = structlog.get_logger()


class SQLServerClient:
    """SQL Server客户端（XcAiDb数据库）"""

    def __init__(self, host: str = "180.184.30.94", port: int = 1433,
                 database: str = "XcAiDb", user: str = "sa", password: str = None):
        """
        初始化SQL Server客户端

        Args:
            host: SQL Server主机地址
            port: SQL Server端口
            database: 数据库名称
            user: 用户名
            password: 密码
        """
        self.host = host
        self.port = port
        self.database = database
        self.user = user
        self.password = password or "#Ph981,6J2bOkWYT7p?5slH$I~g_0itR"
        self.connection_string = self._build_connection_string()

    def _build_connection_string(self) -> str:
        """
        构建ODBC连接字符串

        注意：密码用大括号包裹，处理特殊字符（# ? $等）
        """
        return (
            f"DRIVER={{ODBC Driver 17 for SQL Server}};"
            f"SERVER={self.host},{self.port};"
            f"DATABASE={self.database};"
            f"UID={self.user};"
            f"PWD={{{self.password}}};"
            f"TrustServerCertificate=yes;"
        )

    def query(self, cities: List[str], start_time: str, end_time: str,
              table: str) -> List[Dict[str, Any]]:
        """
        执行参数化查询

        Args:
            cities: 城市名称列表
            start_time: 开始时间（字符串格式）
            end_time: 结束时间（字符串格式）
            table: 表名（CityAQIPublishHistory 或 CityDayAQIPublishHistory）

        Returns:
            原始记录列表（字典格式）

        Raises:
            Exception: 查询失败时抛出异常
        """
        logger.info(
            "sql_server_query_start",
            cities=cities,
            start_time=start_time,
            end_time=end_time,
            table=table
        )

        try:
            # 构建参数化SQL
            city_placeholders = ','.join(['?' for _ in cities])
            params = cities + [start_time, end_time]

            if table == "CityAQIPublishHistory":
                sql = f"""
                SELECT
                    TimePoint, Area, CityCode,
                    PM2_5, PM10, O3, NO2, SO2, CO,
                    AQI, PrimaryPollutant, Quality
                FROM CityAQIPublishHistory
                WHERE Area IN ({city_placeholders})
                  AND TimePoint >= ?
                  AND TimePoint <= ?
                ORDER BY TimePoint, Area
                """
            elif table == "CityDayAQIPublishHistory":
                sql = f"""
                SELECT
                    TimePoint, Area, CityCode,
                    PM2_5_24h, PM10_24h, O3_8h_24h, NO2_24h, SO2_24h, CO_24h,
                    AQI, PrimaryPollutant, Quality
                FROM CityDayAQIPublishHistory
                WHERE Area IN ({city_placeholders})
                  AND TimePoint >= ?
                  AND TimePoint <= ?
                ORDER BY TimePoint, Area
                """
            else:
                raise ValueError(f"不支持的表名: {table}")

            logger.debug(
                "sql_server_query_sql",
                sql=sql,
                param_count=len(params)
            )

            # 执行查询
            conn = pyodbc.connect(self.connection_string, timeout=30)
            cursor = conn.cursor()
            cursor.execute(sql, params)

            # 转换为字典列表
            columns = [column[0] for column in cursor.description]
            records = []
            for row in cursor.fetchall():
                record = dict(zip(columns, row))
                records.append(record)

            cursor.close()
            conn.close()

            logger.info(
                "sql_server_query_success",
                table=table,
                record_count=len(records),
                cities_queried=cities
            )

            return records

        except pyodbc.Error as e:
            logger.error(
                "sql_server_query_error",
                error=str(e),
                sqlstate=e.args[0] if e.args else None,
                table=table
            )
            raise Exception(f"SQL Server查询失败: {str(e)}")

        except Exception as e:
            logger.error(
                "sql_server_query_unexpected_error",
                error=str(e),
                error_type=type(e).__name__
            )
            raise

    def test_connection(self) -> bool:
        """
        测试数据库连接

        Returns:
            连接成功返回True，失败返回False
        """
        try:
            conn = pyodbc.connect(self.connection_string, timeout=10)
            cursor = conn.cursor()
            cursor.execute("SELECT @@VERSION")
            version = cursor.fetchone()
            cursor.close()
            conn.close()

            logger.info(
                "sql_server_connection_test_success",
                version=version[0] if version else None
            )
            return True

        except Exception as e:
            logger.error(
                "sql_server_connection_test_failed",
                error=str(e)
            )
            return False

    def get_available_cities(self, table: str = "CityAQIPublishHistory") -> List[str]:
        """
        获取可用的城市列表

        Args:
            table: 表名

        Returns:
            城市名称列表
        """
        try:
            conn = pyodbc.connect(self.connection_string, timeout=10)
            cursor = conn.cursor()

            sql = f"SELECT DISTINCT Area FROM {table} ORDER BY Area"
            cursor.execute(sql)

            cities = [row[0] for row in cursor.fetchall()]

            cursor.close()
            conn.close()

            logger.info(
                "sql_server_get_cities_success",
                table=table,
                city_count=len(cities)
            )

            return cities

        except Exception as e:
            logger.error(
                "sql_server_get_cities_failed",
                error=str(e)
            )
            return []


# 全局客户端实例（懒加载）
_client_instance = None


def get_sql_server_client() -> SQLServerClient:
    """
    获取SQL Server客户端实例（单例模式）

    Returns:
        SQLServerClient实例
    """
    global _client_instance
    if _client_instance is None:
        _client_instance = SQLServerClient()
    return _client_instance
