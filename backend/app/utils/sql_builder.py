"""
SQL查询构建器

用于将自然语言查询描述转换为SQL查询语句。
"""

from typing import Dict, Any, List, Optional, Tuple
import re
import structlog

logger = structlog.get_logger()


class TableSchema:
    """数据库表结构信息"""

    # 表结构定义
    TABLE_SCHEMAS = {
        'era5_reanalysis_data': {
            'description': 'ERA5气象再分析数据',
            'columns': {
                'time': 'DateTime',
                'lat': 'Float',
                'lon': 'Float',
                'temperature_2m': 'Float',
                'relative_humidity_2m': 'Float',
                'dew_point_2m': 'Float',
                'wind_speed_10m': 'Float',
                'wind_direction_10m': 'Float',
                'wind_gusts_10m': 'Float',
                'surface_pressure': 'Float',
                'precipitation': 'Float',
                'cloud_cover': 'Float',
                'shortwave_radiation': 'Float',
                'visibility': 'Float',
                'boundary_layer_height': 'Float',
            },
            'primary_key': ['time', 'lat', 'lon'],
        },
        'observed_weather_data': {
            'description': '地面观测气象数据',
            'columns': {
                'time': 'DateTime',
                'station_id': 'String',
                'station_name': 'String',
                'lat': 'Float',
                'lon': 'Float',
                'temperature_2m': 'Float',
                'relative_humidity_2m': 'Float',
                'dew_point_2m': 'Float',
                'wind_speed_10m': 'Float',
                'wind_direction_10m': 'Float',
                'surface_pressure': 'Float',
                'precipitation': 'Float',
                'cloud_cover': 'Float',
                'visibility': 'Float',
            },
            'primary_key': ['time', 'station_id'],
        },
        'weather_stations': {
            'description': '气象站点元数据',
            'columns': {
                'station_id': 'String',
                'station_name': 'String',
                'lat': 'Float',
                'lon': 'Float',
                'elevation': 'Float',
                'province': 'String',
                'city': 'String',
                'station_type': 'String',
                'has_pbl_observation': 'Boolean',
                'has_upper_air': 'Boolean',
                'data_provider': 'String',
                'is_active': 'Boolean',
            },
            'primary_key': ['station_id'],
        },
        'fire_hotspots': {
            'description': '火灾热点数据',
            'columns': {
                'id': 'Integer',
                'lat': 'Float',
                'lon': 'Float',
                'brightness': 'Float',
                'frp': 'Float',
                'confidence': 'Integer',
                'acq_datetime': 'DateTime',
                'satellite': 'String',
                'daynight': 'String',
            },
            'primary_key': ['id'],
        },
        'dust_forecasts': {
            'description': '沙尘预报数据',
            'columns': {
                'id': 'Integer',
                'lat': 'Float',
                'lon': 'Float',
                'forecast_time': 'DateTime',
                'valid_time': 'DateTime',
                'leadtime_hour': 'Integer',
                'dust_aod_550nm': 'Float',
                'total_aod_550nm': 'Float',
                'dust_surface_concentration': 'Float',
                'pm10_concentration': 'Float',
            },
            'primary_key': ['id'],
        },
        'dust_events': {
            'description': '沙尘事件记录',
            'columns': {
                'id': 'Integer',
                'event_name': 'String',
                'event_date': 'DateTime',
                'event_duration_hours': 'Integer',
                'intensity_level': 'String',
                'max_dust_aod': 'Float',
                'max_pm10_concentration': 'Float',
                'source_region': 'String',
                'transport_direction': 'String',
            },
            'primary_key': ['id'],
        },
        'air_quality_forecast': {
            'description': '空气质量预报数据',
            'columns': {
                'id': 'Integer',
                'forecast_date': 'Date',
                'source': 'String',
                'calculated_aqi': 'Integer',
                'calculated_aqi_level': 'String',
                'calculated_primary_pollutant': 'String',
                'aqi': 'Integer',
                'aqi_level': 'String',
                'primary_pollutant': 'String',
                'pollutants': 'JSON',
            },
            'primary_key': ['id'],
        },
        'city_aqi_publish_history': {
            'description': '城市空气质量历史数据',
            'columns': {
                'id': 'Integer',
                'time_point': 'DateTime',
                'area': 'String',
                'city_code': 'Integer',
                'co': 'Float',
                'no2': 'Float',
                'o3': 'Float',
                'pm10': 'Float',
                'pm2_5': 'Float',
                'so2': 'Float',
                'aqi': 'Integer',
                'primary_pollutant': 'String',
                'quality': 'String',
            },
            'primary_key': ['id'],
        },
    }


class SQLBuilder:
    """SQL查询构建器"""

    def __init__(self):
        """初始化SQL构建器"""
        self.table_schemas = TableSchema.TABLE_SCHEMAS

    def build(
        self,
        query_description: str,
        tables: Optional[List[str]] = None,
        limit: int = 1000
    ) -> str:
        """
        根据查询描述构建SQL查询

        Args:
            query_description: 自然语言查询描述
            tables: 指定的表名列表（如果为None，自动推断）
            limit: 返回行数限制

        Returns:
            SQL查询语句
        """
        # 1. 解析查询意图
        intent = self._parse_intent(query_description)

        # 2. 确定查询表
        if tables:
            query_tables = tables
        else:
            query_tables = self._infer_tables(query_description, intent)

        if not query_tables:
            raise ValueError("无法确定查询的表，请明确指定tables参数")

        # 3. 构建SQL查询
        if len(query_tables) == 1:
            sql = self._build_single_table_query(query_tables[0], intent, limit)
        else:
            sql = self._build_multi_table_query(query_tables, intent, limit)

        logger.info(
            "sql_built",
            description=query_description,
            tables=query_tables,
            sql=sql
        )

        return sql

    def _parse_intent(self, description: str) -> Dict[str, Any]:
        """
        解析查询意图

        Args:
            description: 查询描述

        Returns:
            意图字典
        """
        intent = {
            'columns': [],  # 要查询的列
            'conditions': [],  # WHERE条件
            'aggregations': [],  # 聚合函数
            'group_by': [],  # GROUP BY字段
            'order_by': [],  # ORDER BY字段
            'time_range': {},  # 时间范围
            'location': {},  # 位置信息
        }

        desc_lower = description.lower()

        # 解析时间范围
        time_patterns = {
            '今天': 'today',
            '昨天': 'yesterday',
            '最近7天': 'last_7_days',
            '最近30天': 'last_30_days',
            '本月': 'this_month',
            '上月': 'last_month',
            '今年': 'this_year',
            '去年': 'last_year',
        }

        for pattern, key in time_patterns.items():
            if pattern in desc_lower:
                intent['time_range']['type'] = key

        # 解析城市/地区
        city_patterns = [
            r'(?:北京|上海|广州|深圳|成都|杭州|武汉|西安|南京|重庆|天津|苏州|长沙|郑州|东莞|青岛|沈阳|宁波|昆明)',
        ]
        for pattern in city_patterns:
            match = re.search(pattern, description)
            if match:
                intent['location']['city'] = match.group(0)

        # 解析聚合需求
        if any(word in desc_lower for word in ['平均', '均值', 'avg', 'average']):
            intent['aggregations'].append('AVG')

        if any(word in desc_lower for word in ['最大', '最高', 'max', 'maximum']):
            intent['aggregations'].append('MAX')

        if any(word in desc_lower for word in ['最小', '最低', 'min', 'minimum']):
            intent['aggregations'].append('MIN')

        if any(word in desc_lower for word in ['总和', '总计', 'sum', 'total']):
            intent['aggregations'].append('SUM')

        if any(word in desc_lower for word in ['数量', '个数', 'count']):
            intent['aggregations'].append('COUNT')

        # 解析污染物
        pollutant_map = {
            'pm2.5': 'pm2_5',
            'pm2_5': 'pm2_5',
            'pm10': 'pm10',
            'o3': 'o3',
            'no2': 'no2',
            'so2': 'so2',
            'co': 'co',
            'aqi': 'aqi',
        }

        for name, col in pollutant_map.items():
            if name in desc_lower:
                intent['columns'].append(col)

        return intent

    def _infer_tables(
        self,
        description: str,
        intent: Dict[str, Any]
    ) -> List[str]:
        """
        根据描述推断要查询的表

        Args:
            description: 查询描述
            intent: 解析的意图

        Returns:
            表名列表
        """
        desc_lower = description.lower()

        # 关键词到表的映射
        table_keywords = {
            'era5_reanalysis_data': ['era5', '再分析', '气象', '边界层', '辐射'],
            'observed_weather_data': ['观测', '地面', '站点'],
            'weather_stations': ['站点', '气象站', 'station'],
            'city_aqi_publish_history': ['aqi', '空气质量', 'pm2.5', 'pm10', 'o3', 'no2', 'so2', 'co', '污染物'],
            'air_quality_forecast': ['预报', '预测'],
            'fire_hotspots': ['火点', '火灾', 'fire'],
            'dust_forecasts': ['沙尘', 'dust'],
            'dust_events': ['沙尘事件', '沙尘暴'],
        }

        # 计算每个表的相关性得分
        table_scores = {}
        for table, keywords in table_keywords.items():
            score = sum(1 for kw in keywords if kw in desc_lower)
            if score > 0:
                table_scores[table] = score

        # 返回得分最高的表
        if table_scores:
            return [max(table_scores, key=table_scores.get)]

        return []

    def _build_single_table_query(
        self,
        table: str,
        intent: Dict[str, Any],
        limit: int
    ) -> str:
        """
        构建单表查询

        Args:
            table: 表名
            intent: 查询意图
            limit: 返回行数限制

        Returns:
            SQL查询语句
        """
        # 获取表结构
        if table not in self.table_schemas:
            raise ValueError(f"未知的表: {table}")

        table_schema = self.table_schemas[table]

        # 构建SELECT子句
        if intent['aggregations'] and intent['columns']:
            # 有聚合函数
            select_parts = []
            for agg in intent['aggregations']:
                for col in intent['columns']:
                    if col in table_schema['columns']:
                        select_parts.append(f"{agg}({col}) AS {agg}_{col}")
            select_clause = ', '.join(select_parts) if select_parts else '*'

            # 如果有聚合，需要GROUP BY
            if intent['group_by']:
                group_by_clause = ', '.join(intent['group_by'])
            else:
                group_by_clause = None
        else:
            # 普通查询
            if intent['columns']:
                # 选择指定列
                valid_columns = [
                    col for col in intent['columns']
                    if col in table_schema['columns']
                ]
                select_clause = ', '.join(valid_columns) if valid_columns else '*'
            else:
                select_clause = '*'
            group_by_clause = None

        # 构建WHERE子句
        where_parts = []

        # 时间条件
        if intent['time_range']:
            time_col = self._get_time_column(table)
            if time_col:
                time_condition = self._build_time_condition(
                    time_col,
                    intent['time_range']['type']
                )
                if time_condition:
                    where_parts.append(time_condition)

        # 位置条件
        if intent['location'].get('city'):
            if 'area' in table_schema['columns']:
                where_parts.append(f"area = '{intent['location']['city']}'")
            elif 'city' in table_schema['columns']:
                where_parts.append(f"city = '{intent['location']['city']}'")

        where_clause = ' AND '.join(where_parts) if where_parts else None

        # 组装SQL
        sql_parts = [f"SELECT {select_clause}", f"FROM {table}"]

        if where_clause:
            sql_parts.append(f"WHERE {where_clause}")

        if group_by_clause:
            sql_parts.append(f"GROUP BY {group_by_clause}")

        sql_parts.append(f"LIMIT {limit}")

        return '\n'.join(sql_parts)

    def _build_multi_table_query(
        self,
        tables: List[str],
        intent: Dict[str, Any],
        limit: int
    ) -> str:
        """
        构建多表JOIN查询

        Args:
            tables: 表名列表
            intent: 查询意图
            limit: 返回行数限制

        Returns:
            SQL查询语句
        """
        # 简化版本：只支持第一个表的查询
        # 完整版本需要支持JOIN逻辑
        return self._build_single_table_query(tables[0], intent, limit)

    def _get_time_column(self, table: str) -> Optional[str]:
        """
        获取表的时间列名

        Args:
            table: 表名

        Returns:
            时间列名
        """
        if table in self.table_schemas:
            columns = self.table_schemas[table]['columns']
            for time_col in ['time', 'time_point', 'acq_datetime', 'event_date']:
                if time_col in columns:
                    return time_col
        return None

    def _build_time_condition(self, time_col: str, time_type: str) -> Optional[str]:
        """
        构建时间条件

        Args:
            time_col: 时间列名
            time_type: 时间类型

        Returns:
            时间条件SQL
        """
        # 简化版本，实际应该使用数据库特定函数
        time_conditions = {
            'today': f"DATE({time_col}) = CURRENT_DATE",
            'yesterday': f"DATE({time_col}) = CURRENT_DATE - INTERVAL '1 day'",
            'last_7_days': f"{time_col} >= CURRENT_DATE - INTERVAL '7 days'",
            'last_30_days': f"{time_col} >= CURRENT_DATE - INTERVAL '30 days'",
        }

        return time_conditions.get(time_type)


# 全局实例
_default_builder = SQLBuilder()


def build_sql_query(
    query_description: str,
    tables: Optional[List[str]] = None,
    limit: int = 1000
) -> str:
    """
    构建SQL查询（便捷函数）

    Args:
        query_description: 自然语言查询描述
        tables: 指定的表名列表
        limit: 返回行数限制

    Returns:
        SQL查询语句
    """
    builder = SQLBuilder()
    return builder.build(query_description, tables, limit)


def get_table_schema(table_name: str) -> Optional[Dict[str, Any]]:
    """
    获取表结构信息（便捷函数）

    Args:
        table_name: 表名

    Returns:
        表结构字典
    """
    return TableSchema.TABLE_SCHEMAS.get(table_name)


def list_available_tables() -> List[str]:
    """
    列出所有可用的表（便捷函数）

    Returns:
        表名列表
    """
    return list(TableSchema.TABLE_SCHEMAS.keys())
