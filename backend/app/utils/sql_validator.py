"""
SQL安全验证器

用于验证SQL查询的安全性，防止SQL注入和危险操作。
"""

from typing import Tuple, List, Optional
import re
import structlog

logger = structlog.get_logger()


class SQLValidator:
    """SQL安全验证器"""

    # 危险关键词（不允许的操作）
    DANGEROUS_KEYWORDS = [
        'DROP', 'DELETE', 'INSERT', 'UPDATE', 'ALTER',
        'CREATE', 'TRUNCATE', 'EXEC', 'EXECUTE', 'GRANT',
        'REVOKE', 'COMMENT', 'MERGE', 'CALL', 'COPY'
    ]

    # 允许的表前缀（用于验证表名）
    ALLOWED_TABLE_PREFIXES = [
        'era5_', 'observed_', 'weather_', 'fire_', 'dust_',
        'air_quality_', 'city_', 'particulate_'
    ]

    # 允许的表名（白名单）
    ALLOWED_TABLES = [
        'era5_reanalysis_data',
        'observed_weather_data',
        'weather_stations',
        'weather_data_cache',
        'fire_hotspots',
        'dust_forecasts',
        'dust_events',
        'air_quality_forecast',
        'city_aqi_publish_history',
        'working_orders',
        'qc_history',  # 自动质控历史数据表
        'city_168_statistics',  # 168城市空气质量统计预计算表
        # 系统视图（用于动态查询表结构）
        'information_schema.columns',
        'information_schema.tables',
    ]

    def __init__(self, max_limit: int = 10000):
        """
        初始化SQL验证器

        Args:
            max_limit: 允许的最大查询行数
        """
        self.max_limit = max_limit

    def validate(self, sql: str) -> Tuple[bool, str]:
        """
        验证SQL安全性

        Args:
            sql: SQL查询语句

        Returns:
            (is_valid, error_message): 验证结果和错误信息
        """
        if not sql or not sql.strip():
            return False, "SQL语句为空"

        sql_upper = sql.upper().strip()

        # 检查1：必须是SELECT
        if not sql_upper.startswith('SELECT'):
            return False, "只允许SELECT查询"

        # 检查2：危险关键词（使用词边界避免误判，如CREATETIME不匹配CREATE）
        for keyword in self.DANGEROUS_KEYWORDS:
            pattern = r'\b' + keyword + r'\b'
            if re.search(pattern, sql_upper):
                return False, f"包含危险关键词: {keyword}"

        # 检查3：SQL注入模式
        if '--' in sql or '/*' in sql:
            return False, "不能包含SQL注释"

        # 检查4：多条语句
        if ';' in sql.rstrip(';').rstrip():
            return False, "不能执行多条SQL语句"

        # 检查5：验证表名
        table_check_result = self._validate_table_names(sql)
        if not table_check_result[0]:
            return table_check_result

        # 检查6：验证LIMIT
        limit_check_result = self._validate_limit(sql)
        if not limit_check_result[0]:
            return limit_check_result

        return True, ""

    def _validate_table_names(self, sql: str) -> Tuple[bool, str]:
        """
        验证表名是否在白名单中

        Args:
            sql: SQL查询语句

        Returns:
            (is_valid, error_message): 验证结果和错误信息
        """
        # 提取FROM和JOIN后的表名
        # 简化版本：检查是否包含允许的表名
        sql_lower = sql.lower()

        # 检查是否包含任何允许的表名
        has_allowed_table = any(
            f'from {table}' in sql_lower or
            f'join {table}' in sql_lower or
            f'from "{table}"' in sql_lower or
            f'join "{table}"' in sql_lower
            for table in self.ALLOWED_TABLES
        )

        if not has_allowed_table:
            # 检查是否包含其他表名（可能是未授权的表）
            from_match = re.search(r'\bfrom\s+(\w+)', sql_lower)
            join_match = re.search(r'\bjoin\s+(\w+)', sql_lower)

            if from_match or join_match:
                return False, f"表名不在白名单中。允许的表: {', '.join(self.ALLOWED_TABLES[:5])}..."

        return True, ""

    def _validate_limit(self, sql: str) -> Tuple[bool, str]:
        """
        验证LIMIT子句

        Args:
            sql: SQL查询语句

        Returns:
            (is_valid, error_message): 验证结果和错误信息
        """
        sql_lower = sql.lower()

        # 检查是否有LIMIT
        limit_match = re.search(r'\blimit\s+(\d+)', sql_lower)
        if limit_match:
            limit_value = int(limit_match.group(1))
            if limit_value > self.max_limit:
                return False, f"LIMIT超过最大值 {self.max_limit}"
        else:
            # 没有LIMIT，添加默认限制的警告
            logger.warning(
                "sql_query_without_limit",
                message="建议在SQL查询中添加LIMIT子句以限制返回行数"
            )

        return True, ""

    def sanitize_limit(self, sql: str, default_limit: int = 1000) -> str:
        """
        确保SQL查询有LIMIT子句

        Args:
            sql: SQL查询语句
            default_limit: 默认限制行数

        Returns:
            添加了LIMIT的SQL语句
        """
        sql_lower = sql.lower()

        # 检查是否已有LIMIT
        if re.search(r'\blimit\s+(\d+)', sql_lower):
            # 已有LIMIT，但需要检查是否超过最大值
            limit_match = re.search(r'\blimit\s+(\d+)', sql_lower)
            if limit_match:
                limit_value = int(limit_match.group(1))
                if limit_value > self.max_limit:
                    # 替换为最大值
                    sql = re.sub(
                        r'\bLIMIT\s+\d+',
                        f'LIMIT {self.max_limit}',
                        sql,
                        flags=re.IGNORECASE
                    )
            return sql
        else:
            # 添加LIMIT
            return f"{sql.rstrip(' ;')} LIMIT {default_limit}"

    def extract_tables(self, sql: str) -> List[str]:
        """
        从SQL中提取表名

        Args:
            sql: SQL查询语句

        Returns:
            表名列表
        """
        tables = []
        sql_lower = sql.lower()

        # 提取FROM后的表名
        from_match = re.search(r'\bfrom\s+(\w+)', sql_lower)
        if from_match:
            tables.append(from_match.group(1))

        # 提取JOIN后的表名
        for join_match in re.finditer(r'\bjoin\s+(\w+)', sql_lower):
            tables.append(join_match.group(1))

        return list(set(tables))  # 去重


# 全局实例
_default_validator = SQLValidator()


def validate_sql(sql: str, max_limit: int = 10000) -> Tuple[bool, str]:
    """
    验证SQL安全性（便捷函数）

    Args:
        sql: SQL查询语句
        max_limit: 允许的最大查询行数

    Returns:
        (is_valid, error_message): 验证结果和错误信息
    """
    validator = SQLValidator(max_limit=max_limit)
    return validator.validate(sql)


def sanitize_sql_limit(sql: str, default_limit: int = 1000, max_limit: int = 10000) -> str:
    """
    确保SQL查询有LIMIT子句（便捷函数）

    Args:
        sql: SQL查询语句
        default_limit: 默认限制行数
        max_limit: 最大允许行数

    Returns:
        添加了LIMIT的SQL语句
    """
    validator = SQLValidator(max_limit=max_limit)
    return validator.sanitize_limit(sql, default_limit)
