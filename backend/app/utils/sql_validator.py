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
        # 空气质量历史数据表（XcAiDb数据库）
        'CityDayAQIPublishHistory',  # 城市日空气质量发布历史（24小时均值）
        'CityAQIPublishHistory',  # 城市小时空气质量发布历史
        'CurrentAirQuality',  # 当前空气质量
        'dat_station_day',  # 站点日数据
        'dat_station_hour',  # 站点小时数据
        'dat_weather_hour',  # 气象小时数据
        'WeatherForecast7Day',  # 7天空气质量预报数据（全国319个城市，包含AQI范围、首要污染物、气象条件等）
        'city_168_statistics_new_standard',  # 168城市空气质量统计表（新标准 HJ 633-2026）
        'city_168_statistics_old_standard',  # 168城市空气质量统计表（旧标准 HJ 633-2013）
        'province_statistics_new_standard',  # 省级空气质量统计表（新标准 HJ 633-2026）
        'province_statistics_old_standard',  # 省级空气质量统计表（旧标准 HJ 633-2013）
        'noise_city_compliance_monthly',  # 城市噪声昼夜达标率月汇总表
        'noise_city_compliance_daily',  # 城市噪声昼夜达标率逐日明细表
        # 质控和分析数据表（AirPollutionAnalysis数据库）
        'qc_history',  # 自动质控历史数据表（13551条记录）
        'quality_control_records',  # 质控例行检查记录
        'working_orders',  # 运维工单
        'working_order_details',  # 运维工单详情
        'base_station',  # 站点基础信息
        'base_station_sup',  # 上级站点基础信息
        'base_device',  # 设备基础信息
        'base_user_station',  # 用户-站点关联
        'base_department_station',  # 部门-站点关联
        'base_contract_station',  # 合同-站点关联
        'analysis_history',  # 分析历史记录
        'BSD_STATION',  # 站点信息表（包含站点ID、名称、代码、区域、经纬度、地址等信息）
        # 系统视图（用于动态查询表结构）
        'information_schema.columns',
        'information_schema.tables',
    ]

    def __init__(
        self,
        max_limit: int = 10000,
        allowed_tables: Optional[List[str]] = None,
        allowed_table_prefixes: Optional[List[str]] = None,
    ):
        """
        初始化SQL验证器

        Args:
            max_limit: 允许的最大查询行数
            allowed_tables: 实例级表名白名单；为空时使用类默认白名单
            allowed_table_prefixes: 实例级表名前缀白名单；为空时使用类默认前缀
        """
        self.max_limit = max_limit
        self.ALLOWED_TABLES = list(allowed_tables) if allowed_tables is not None else list(type(self).ALLOWED_TABLES)
        self.ALLOWED_TABLE_PREFIXES = (
            list(allowed_table_prefixes)
            if allowed_table_prefixes is not None
            else list(type(self).ALLOWED_TABLE_PREFIXES)
        )

    def validate(self, sql: str) -> Tuple[bool, str]:
        """
        验证SQL安全性

        Args:
            sql: SQL查询语句

        Returns:
            (is_valid, error_message): 验证结果和错误信息
        """
        sql = self.normalize_sql(sql)

        if not sql or not sql.strip():
            return False, "SQL语句为空"

        sql_upper = sql.upper().strip()

        # 检查1：必须是SELECT或CTE（WITH...SELECT）
        if not (sql_upper.startswith('SELECT') or sql_upper.startswith('WITH')):
            return False, "只允许SELECT查询（支持CTE/WITH子句）"

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

    def normalize_sql(self, sql: str) -> str:
        """
        归一化LLM常见输出格式，避免合法只读SQL因包装格式被误拒。

        只移除外层展示包装，不改变SQL主体语义：
        - Markdown代码块 ```sql ... ```
        - 单层包裹整个查询的外层括号
        - 首尾空白
        """
        if sql is None:
            return ""

        normalized = sql.strip()
        normalized = self._strip_markdown_code_fence(normalized)
        normalized = self._strip_single_outer_parentheses(normalized)
        return normalized.strip()

    def _strip_markdown_code_fence(self, sql: str) -> str:
        """移除包裹整段SQL的Markdown代码块。"""
        fence_match = re.fullmatch(r"```(?:sql|tsql|mssql)?\s*\n?(.*?)\n?```", sql, re.IGNORECASE | re.DOTALL)
        if fence_match:
            return fence_match.group(1).strip()
        return sql

    def _strip_single_outer_parentheses(self, sql: str) -> str:
        """如果整段SQL只被一层外部括号包裹，则去掉这一层。"""
        if not (sql.startswith("(") and sql.endswith(")")):
            return sql

        depth = 0
        in_single_quote = False
        in_bracket_identifier = False
        index = 0
        length = len(sql)

        while index < length:
            char = sql[index]
            next_char = sql[index + 1] if index + 1 < length else ""

            if in_single_quote:
                if char == "'" and next_char == "'":
                    index += 2
                    continue
                if char == "'":
                    in_single_quote = False
                index += 1
                continue

            if in_bracket_identifier:
                if char == "]":
                    in_bracket_identifier = False
                index += 1
                continue

            if char == "'":
                in_single_quote = True
            elif char == "[":
                in_bracket_identifier = True
            elif char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
                if depth == 0 and index != length - 1:
                    return sql
                if depth < 0:
                    return sql

            index += 1

        if depth == 0:
            return sql[1:-1].strip()
        return sql

    def _validate_table_names(self, sql: str) -> Tuple[bool, str]:
        """
        验证表名是否在白名单中

        Args:
            sql: SQL查询语句

        Returns:
            (is_valid, error_message): 验证结果和错误信息
        """
        sql = self.normalize_sql(sql)
        referenced_tables = self.extract_tables(sql)
        if not referenced_tables:
            return True, ""

        allowed_tables = {table.lower() for table in self.ALLOWED_TABLES}
        cte_names = {
            match.group(1).lower()
            for match in re.finditer(r'(?:\bwith|,)\s+([a-zA-Z_]\w*)\s+as\s*\(', sql, re.IGNORECASE)
        }

        disallowed_tables = []
        for table in referenced_tables:
            table_lower = table.lower()
            if table_lower in cte_names:
                continue
            if table_lower not in allowed_tables:
                disallowed_tables.append(table)

        if disallowed_tables:
            return False, (
                f"表名不在白名单中: {', '.join(disallowed_tables)}。"
                f"允许的表: {', '.join(self.ALLOWED_TABLES)}"
            )

        return True, ""

    def _validate_limit(self, sql: str) -> Tuple[bool, str]:
        """
        验证LIMIT子句

        Args:
            sql: SQL查询语句

        Returns:
            (is_valid, error_message): 验证结果和错误信息
        """
        sql = self.normalize_sql(sql)
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
        sql = self.normalize_sql(sql)
        tables = []
        pattern = r'\b(?:from|join)\s+(?!\()(\[?\w+\]?(?:\s*\.\s*\[?\w+\]?)?)'

        for match in re.finditer(pattern, sql, re.IGNORECASE):
            raw_table = match.group(1)
            parts = [
                part.strip().strip("[]").lower()
                for part in raw_table.split(".")
                if part.strip()
            ]
            if not parts:
                continue

            if len(parts) >= 2 and parts[-2] == "information_schema":
                tables.append(f"information_schema.{parts[-1]}")
            else:
                tables.append(parts[-1])

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
