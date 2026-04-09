"""
更新city_168_statistics表中历史数据的旧标准综合指数

由于修正了旧标准综合指数的计算逻辑（所有权重改为1），
需要重新计算并更新所有历史记录。

作者：Claude Code
日期：2026-04-09
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from datetime import datetime
from decimal import Decimal
import pyodbc
import structlog

# 直接从本文件定义常量，避免模块导入问题
ANNUAL_STANDARD_LIMITS_2013 = {
    'SO2': 60,
    'NO2': 40,
    'PM10': 70,
    'PM2_5': 35,
    'CO': 4,
    'O3_8h': 160
}

WEIGHTS_2013 = {
    'SO2': 1,
    'NO2': 1,
    'PM10': 1,
    'PM2_5': 1,
    'CO': 1,
    'O3_8h': 1
}

def safe_round(value: float, precision: int) -> float:
    """
    通用修约函数（四舍六入五成双）

    使用Decimal进行精确修约，避免浮点数精度问题
    """
    if value is None:
        return 0.0

    try:
        value_str = format(value, f'.{precision + 5}f').rstrip('0').rstrip('.')
        decimal_value = Decimal(value_str)
        quantize_unit = Decimal('0.' + '0' * precision) if precision > 0 else Decimal('1')
        rounded = decimal_value.quantize(quantize_unit, rounding='ROUND_HALF_EVEN')
        return float(rounded)
    except (ValueError, TypeError):
        return 0.0

logger = structlog.get_logger()


class OldStandardIndexUpdater:
    """旧标准综合指数更新器"""

    def __init__(self, host: str = "180.184.30.94", port: int = 1433,
                 database: str = "XcAiDb", user: str = "sa", password: str = None):
        self.host = host
        self.port = port
        self.database = database
        self.user = user
        self.password = password or "#Ph981,6J2bOkWYT7p?5slH$I~g_0itR"
        self.connection_string = self._build_connection_string()

    def _build_connection_string(self) -> str:
        """构建ODBC连接字符串"""
        return (
            f"DRIVER={{ODBC Driver 17 for SQL Server}};"
            f"SERVER={self.host},{self.port};"
            f"DATABASE={self.database};"
            f"UID={self.user};"
            f"PWD={{{self.password}}};"
            f"TrustServerCertificate=yes;"
        )

    def test_connection(self) -> bool:
        """测试数据库连接"""
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

    def fetch_all_statistics(self) -> list:
        """
        获取所有统计数据

        Returns:
            统计数据列表
        """
        sql = """
        SELECT
            id, stat_date, stat_type, city_name,
            so2_concentration, no2_concentration, pm10_concentration, pm2_5_concentration,
            co_concentration, o3_8h_concentration,
            so2_index, no2_index, pm10_index, pm2_5_index, co_index, o3_8h_index
        FROM city_168_statistics
        ORDER BY stat_date DESC, stat_type, city_name
        """

        try:
            conn = pyodbc.connect(self.connection_string, timeout=30)
            cursor = conn.cursor()
            cursor.execute(sql)

            statistics = []
            for row in cursor.fetchall():
                statistics.append({
                    'id': row.id,
                    'stat_date': row.stat_date.strftime('%Y-%m-%d') if row.stat_date else None,
                    'stat_type': row.stat_type,
                    'city_name': row.city_name,
                    'so2_concentration': row.so2_concentration,
                    'no2_concentration': row.no2_concentration,
                    'pm10_concentration': row.pm10_concentration,
                    'pm2_5_concentration': row.pm2_5_concentration,
                    'co_concentration': row.co_concentration,
                    'o3_8h_concentration': row.o3_8h_concentration,
                    'so2_index': row.so2_index,
                    'no2_index': row.no2_index,
                    'pm10_index': row.pm10_index,
                    'pm2_5_index': row.pm2_5_index,
                    'co_index': row.co_index,
                    'o3_8h_index': row.o3_8h_index
                })

            cursor.close()
            conn.close()

            logger.info(
                "statistics_fetched",
                count=len(statistics)
            )

            return statistics

        except Exception as e:
            logger.error(
                "fetch_statistics_failed",
                error=str(e)
            )
            raise

    def calculate_old_standard_indices(self, record: dict) -> dict:
        """
        计算旧标准的单项指数和综合指数

        Args:
            record: 统计记录

        Returns:
            包含旧标准指数的字典
        """
        result = {}

        # 计算旧标准单项指数（HJ 663-2013）
        # PM10和PM2.5使用旧标准限值，其他污染物使用新标准限值
        result['pm10_index_old'] = safe_round(
            (record['pm10_concentration'] or 0) / ANNUAL_STANDARD_LIMITS_2013['PM10'], 3
        ) if record['pm10_concentration'] is not None else None

        result['pm2_5_index_old'] = safe_round(
            (record['pm2_5_concentration'] or 0) / ANNUAL_STANDARD_LIMITS_2013['PM2_5'], 3
        ) if record['pm2_5_concentration'] is not None else None

        # 计算旧标准综合指数（所有权重均为1）
        comprehensive_index_old = 0.0
        valid_indices_old = 0

        # SO2
        if record['so2_index'] is not None:
            comprehensive_index_old += float(record['so2_index']) * float(WEIGHTS_2013['SO2'])
            valid_indices_old += 1

        # NO2
        if record['no2_index'] is not None:
            comprehensive_index_old += float(record['no2_index']) * float(WEIGHTS_2013['NO2'])
            valid_indices_old += 1

        # PM10（使用旧标准指数）
        if result['pm10_index_old'] is not None:
            comprehensive_index_old += float(result['pm10_index_old']) * float(WEIGHTS_2013['PM10'])
            valid_indices_old += 1

        # PM2.5（使用旧标准指数）
        if result['pm2_5_index_old'] is not None:
            comprehensive_index_old += float(result['pm2_5_index_old']) * float(WEIGHTS_2013['PM2_5'])
            valid_indices_old += 1

        # CO
        if record['co_index'] is not None:
            comprehensive_index_old += float(record['co_index']) * float(WEIGHTS_2013['CO'])
            valid_indices_old += 1

        # O3_8h
        if record['o3_8h_index'] is not None:
            comprehensive_index_old += float(record['o3_8h_index']) * float(WEIGHTS_2013['O3_8h'])
            valid_indices_old += 1

        result['comprehensive_index_old'] = safe_round(
            comprehensive_index_old, 3
        ) if valid_indices_old > 0 else None

        return result

    def update_database(self, updates: list):
        """
        更新数据库中的旧标准综合指数

        Args:
            updates: 更新数据列表 [(id, pm10_index_old, pm2_5_index_old, comprehensive_index_old), ...]
        """
        if not updates:
            logger.info("no_updates_needed")
            return

        try:
            conn = pyodbc.connect(self.connection_string, timeout=30)
            cursor = conn.cursor()

            update_sql = """
            UPDATE city_168_statistics
            SET pm10_index_old = ?,
                pm2_5_index_old = ?,
                comprehensive_index_old = ?
            WHERE id = ?
            """

            batch_size = 100
            for i in range(0, len(updates), batch_size):
                batch = updates[i:i + batch_size]
                for update_data in batch:
                    record_id, pm10_old, pm25_old, comp_old = update_data
                    cursor.execute(update_sql, [pm10_old, pm25_old, comp_old, record_id])

                conn.commit()
                logger.info(
                    "batch_updated",
                    batch_end=min(i + batch_size, len(updates)),
                    total=len(updates)
                )

            cursor.close()
            conn.close()

            logger.info(
                "database_update_completed",
                total_updated=len(updates)
            )

        except Exception as e:
            logger.error(
                "database_update_failed",
                error=str(e)
            )
            raise

    def calculate_and_update_rankings(self):
        """
        计算并更新所有统计类型的旧标准排名

        按照stat_date和stat_type分组计算排名
        """
        try:
            conn = pyodbc.connect(self.connection_string, timeout=30)
            cursor = conn.cursor()

            # 获取所有需要计算排名的分组
            groups_sql = """
            SELECT DISTINCT stat_date, stat_type
            FROM city_168_statistics
            WHERE comprehensive_index_old IS NOT NULL
            ORDER BY stat_date DESC, stat_type
            """

            cursor.execute(groups_sql)
            groups = cursor.fetchall()

            logger.info(
                "ranking_groups_found",
                count=len(groups)
            )

            # 对每个分组计算排名
            for group in groups:
                stat_date = group.stat_date.strftime('%Y-%m-%d') if group.stat_date else None
                stat_type = group.stat_type

                # 获取该分组的所有记录
                records_sql = """
                SELECT id, city_name, comprehensive_index_old
                FROM city_168_statistics
                WHERE stat_date = ? AND stat_type = ?
                  AND comprehensive_index_old IS NOT NULL
                ORDER BY comprehensive_index_old
                """

                cursor.execute(records_sql, [stat_date, stat_type])
                records = cursor.fetchall()

                # 计算排名（综合指数越小，排名越好）
                for rank, record in enumerate(records, start=1):
                    update_rank_sql = """
                    UPDATE city_168_statistics
                    SET comprehensive_index_rank_old = ?
                    WHERE id = ?
                    """
                    cursor.execute(update_rank_sql, [rank, record.id])

                conn.commit()

                logger.info(
                    "ranking_updated",
                    stat_date=stat_date,
                    stat_type=stat_type,
                    cities_count=len(records)
                )

            cursor.close()
            conn.close()

            logger.info("ranking_update_completed")

        except Exception as e:
            logger.error(
                "ranking_update_failed",
                error=str(e)
            )
            raise

    def run(self):
        """执行更新流程"""
        logger.info("update_started")

        # 测试连接
        if not self.test_connection():
            logger.error("connection_test_failed")
            return

        # 获取所有统计数据
        statistics = self.fetch_all_statistics()

        if not statistics:
            logger.info("no_statistics_found")
            return

        # 计算旧标准指数
        updates = []
        for stat in statistics:
            old_indices = self.calculate_old_standard_indices(stat)

            updates.append((
                stat['id'],
                old_indices['pm10_index_old'],
                old_indices['pm2_5_index_old'],
                old_indices['comprehensive_index_old']
            ))

        # 更新数据库
        self.update_database(updates)

        # 重新计算排名
        self.calculate_and_update_rankings()

        logger.info(
            "update_completed",
            total_updated=len(updates)
        )


def main():
    """主函数"""
    updater = OldStandardIndexUpdater()
    updater.run()


if __name__ == "__main__":
    main()
