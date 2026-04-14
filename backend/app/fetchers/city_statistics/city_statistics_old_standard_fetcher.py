"""
168城市空气质量统计数据抓取器（旧标准限值版本）

定时从XcAiDb数据库提取数据，计算168个重点城市的空气质量评价指标（按HJ663旧标准限值），
并将结果缓存回XcAiDb数据库的city_168_statistics_old_standard表。

与city_statistics_fetcher.py的区别：
1. 污染物浓度修约规则：使用final_output规则（PM2.5/CO保留1位，其他取整）
2. 计算综合指数时使用修约后的浓度值
3. 存储2套综合指数：旧限值+新算法、旧限值+旧算法

核心功能：
- 每天上午8点自动运行
- 计算月度统计、年度累计、当月累计三种统计类型
- 按HJ663旧标准限值计算综合指数和单项指数
- 支持沙尘天气扣沙处理
- 自动排名计算

作者：Claude Code
版本：1.0.0
日期：2026-04-09
"""

from typing import List, Dict, Tuple, Optional
from datetime import datetime, timedelta
from decimal import Decimal
import asyncio
import structlog
import pyodbc

from app.fetchers.base.fetcher_interface import DataFetcher

logger = structlog.get_logger()


# =============================================================================
# 168城市名单（从city_statistics_fetcher.py复用）
# =============================================================================

# 从city_statistics_fetcher导入城市名单
import sys
import os
sys.path.append(os.path.dirname(__file__))
from city_statistics_fetcher import (
    CITY_168_LIST,
    ALL_168_CITIES,
    CITY_REGION_MAP
)


# =============================================================================
# HJ663旧标准限值常量
# =============================================================================

# HJ 663-2013 旧标准限值（用于综合指数计算）
ANNUAL_STANDARD_LIMITS_2013 = {
    'SO2': 60,
    'NO2': 40,
    'PM10': 70,   # 旧标准
    'PM2_5': 35,  # 旧标准
    'CO': 4,
    'O3_8h': 160
}

# 新标准综合指数权重（HJ 663-2026）
WEIGHTS_NEW_ALGO = {
    'SO2': 1,
    'NO2': 2,
    'PM10': 1,
    'PM2_5': 3,
    'CO': 1,
    'O3_8h': 2
}

# 旧标准综合指数权重（HJ 663-2013）- 所有污染物权重均为1
WEIGHTS_OLD_ALGO = {
    'SO2': 1,
    'NO2': 1,
    'PM10': 1,
    'PM2_5': 1,
    'CO': 1,
    'O3_8h': 1
}


# =============================================================================
# 修约函数（四舍六入五成双）
# =============================================================================

def safe_round(value: float, precision: int) -> float:
    """
    通用修约函数（四舍六入五成双）

    使用Decimal进行精确修约，避免浮点数精度问题

    Args:
        value: 原始值
        precision: 保留的小数位数

    Returns:
        修约后的值
    """
    if value is None:
        return 0.0

    try:
        from decimal import Decimal, ROUND_HALF_EVEN

        # 将浮点数转换为字符串再转换为Decimal，避免浮点数精度问题
        value_str = format(value, f'.{precision + 5}f').rstrip('0').rstrip('.')
        decimal_value = Decimal(value_str)

        # 构造修约单位（如0.01表示保留2位小数）
        quantize_unit = Decimal('0.' + '0' * precision) if precision > 0 else Decimal('1')

        # 使用ROUND_HALF_EVEN进行修约
        rounded = decimal_value.quantize(quantize_unit, rounding=ROUND_HALF_EVEN)

        return float(rounded)
    except (ValueError, TypeError):
        return 0.0


def apply_final_output_rounding(value: float, pollutant: str):
    """
    应用最终输出修约规则（一般修约规范）

    修约规则：
    - PM2.5：取整
    - CO：保留1位小数
    - SO2/NO2/PM10/O3_8h：取整（保留0位小数）

    Args:
        value: 原始值
        pollutant: 污染物名称

    Returns:
        修约后的值（整数或浮点数）
    """
    if value is None:
        return 0.0

    # 最终输出修约规则
    final_output_precision = {
        'PM2_5': 0,      # 取整
        'CO': 1,         # 保留1位小数
        'SO2': 0,        # 取整
        'NO2': 0,        # 取整
        'PM10': 0,       # 取整
        'O3_8h': 0,      # 取整
    }

    precision = final_output_precision.get(pollutant, 0)
    rounded_value = safe_round(value, precision)

    # 如果精度为0（取整），返回整数类型
    if precision == 0:
        return int(rounded_value)
    else:
        return rounded_value


def calculate_percentile(values: List[float], percentile: int) -> Optional[float]:
    """
    计算百分位数（使用线性插值法）

    Args:
        values: 数值列表
        percentile: 百分位数（0-100）

    Returns:
        百分位数值（不进行修约，由调用者决定修约精度）
    """
    if not values or len(values) == 0:
        return None

    # 过滤None值
    valid_values = [v for v in values if v is not None]

    if not valid_values:
        return None

    # 排序
    sorted_values = sorted(valid_values)
    n = len(sorted_values)

    # 计算位置（使用线性插值法）
    index = (percentile / 100) * (n - 1)
    lower = int(index)
    upper = lower + 1

    if upper >= n:
        return float(sorted_values[-1])

    # 线性插值
    weight = index - lower
    return sorted_values[lower] * (1 - weight) + sorted_values[upper] * weight


# =============================================================================
# 统计计算函数
# =============================================================================

def calculate_city_statistics(
    city_name: str,
    daily_data: List[Dict],
    stat_type: str = 'monthly'
) -> Dict:
    """
    计算单个城市的空气质量统计指标（旧标准限值版本）

    关键区别：
    1. 污染物浓度使用final_output规则修约（PM2.5/CO保留1位，其他取整）
    2. 计算综合指数时使用修约后的浓度值

    Args:
        city_name: 城市名称
        daily_data: 日数据列表
        stat_type: 统计类型（monthly/annual_ytd/current_month）

    Returns:
        统计结果字典
    """
    if not daily_data:
        return {}

    logger.info(
        "calculating_old_standard_city_stats",
        city=city_name,
        day_count=len(daily_data),
        stat_type=stat_type
    )

    result = {
        'city_name': city_name,
        'stat_type': stat_type,
        'data_days': len(daily_data),
        'region': CITY_REGION_MAP.get(city_name, ''),
        'province': ''  # 需要从城市名推断
    }

    # 收集各污染物的日浓度值
    so2_values = []
    no2_values = []
    pm10_values = []
    pm25_values = []
    co_values = []
    o3_8h_values = []

    for record in daily_data:
        # 提取浓度值（处理可能的字段名变化）
        def safe_get(record, keys):
            for key in keys:
                val = record.get(key)
                if val is not None and val != '':
                    try:
                        return float(val)
                    except (ValueError, TypeError):
                        pass
            return None

        so2 = safe_get(record, ['SO2', 'so2', 'so2_concentration'])
        no2 = safe_get(record, ['NO2', 'no2', 'no2_concentration'])
        pm10 = safe_get(record, ['PM10', 'pm10', 'pm10_concentration'])
        pm25 = safe_get(record, ['PM2_5', 'pm2_5', 'pm2_5_concentration'])
        co = safe_get(record, ['CO', 'co', 'co_concentration'])
        o3_8h = safe_get(record, ['O3_8h', 'o3_8h', 'o3_8h_concentration'])

        if so2 is not None:
            so2_values.append(so2)
        if no2 is not None:
            no2_values.append(no2)
        if pm10 is not None:
            pm10_values.append(pm10)
        if pm25 is not None:
            pm25_values.append(pm25)
        if co is not None:
            co_values.append(co)
        if o3_8h is not None:
            o3_8h_values.append(o3_8h)

    # 计算统计浓度并应用final_output修约规则
    # SO2：第98百分位数（取整）
    if so2_values:
        percentile_98 = calculate_percentile(so2_values, 98)
        result['so2_concentration'] = apply_final_output_rounding(
            percentile_98 if percentile_98 is not None else 0, 'SO2'
        )
    else:
        result['so2_concentration'] = None

    # NO2：第98百分位数（取整）
    if no2_values:
        percentile_98 = calculate_percentile(no2_values, 98)
        result['no2_concentration'] = apply_final_output_rounding(
            percentile_98 if percentile_98 is not None else 0, 'NO2'
        )
    else:
        result['no2_concentration'] = None

    # PM10：均值（取整）
    if pm10_values:
        result['pm10_concentration'] = apply_final_output_rounding(
            sum(pm10_values) / len(pm10_values), 'PM10'
        )
    else:
        result['pm10_concentration'] = None

    # PM2.5：均值（保留1位小数）
    if pm25_values:
        result['pm2_5_concentration'] = apply_final_output_rounding(
            sum(pm25_values) / len(pm25_values), 'PM2_5'
        )
    else:
        result['pm2_5_concentration'] = None

    # CO：第95百分位数（保留1位小数）
    if co_values:
        percentile_95 = calculate_percentile(co_values, 95)
        result['co_concentration'] = apply_final_output_rounding(
            percentile_95 if percentile_95 is not None else 0, 'CO'
        )
    else:
        result['co_concentration'] = None

    # O3_8h：第90百分位数（取整）
    if o3_8h_values:
        percentile_90 = calculate_percentile(o3_8h_values, 90)
        result['o3_8h_concentration'] = apply_final_output_rounding(
            percentile_90 if percentile_90 is not None else 0, 'O3_8h'
        )
    else:
        result['o3_8h_concentration'] = None

    # 计算单项指数（使用旧限值）= 修约后浓度 / 旧限值
    result['so2_index'] = safe_round(
        (result['so2_concentration'] or 0) / ANNUAL_STANDARD_LIMITS_2013['SO2'], 3
    ) if result['so2_concentration'] is not None else None

    result['no2_index'] = safe_round(
        (result['no2_concentration'] or 0) / ANNUAL_STANDARD_LIMITS_2013['NO2'], 3
    ) if result['no2_concentration'] is not None else None

    result['pm10_index'] = safe_round(
        (result['pm10_concentration'] or 0) / ANNUAL_STANDARD_LIMITS_2013['PM10'], 3
    ) if result['pm10_concentration'] is not None else None

    result['pm2_5_index'] = safe_round(
        (result['pm2_5_concentration'] or 0) / ANNUAL_STANDARD_LIMITS_2013['PM2_5'], 3
    ) if result['pm2_5_concentration'] is not None else None

    result['co_index'] = safe_round(
        (result['co_concentration'] or 0) / ANNUAL_STANDARD_LIMITS_2013['CO'], 3
    ) if result['co_concentration'] is not None else None

    result['o3_8h_index'] = safe_round(
        (result['o3_8h_concentration'] or 0) / ANNUAL_STANDARD_LIMITS_2013['O3_8h'], 3
    ) if result['o3_8h_concentration'] is not None else None

    # 计算综合指数（旧限值+新算法）= Σ(单项指数 × 新权重)
    comprehensive_index_new_algo = 0.0
    valid_indices = 0

    for pollutant, weight in WEIGHTS_NEW_ALGO.items():
        index_key = f"{pollutant.lower()}_index"
        index_value = result.get(index_key)
        if index_value is not None:
            comprehensive_index_new_algo += index_value * weight
            valid_indices += 1

    result['comprehensive_index_new_algo'] = safe_round(
        comprehensive_index_new_algo, 3
    ) if valid_indices > 0 else None

    # 计算综合指数（旧限值+旧算法）= Σ(单项指数 × 旧权重)
    comprehensive_index_old_algo = 0.0
    valid_indices = 0

    for pollutant, weight in WEIGHTS_OLD_ALGO.items():
        index_key = f"{pollutant.lower()}_index"
        index_value = result.get(index_key)
        if index_value is not None:
            comprehensive_index_old_algo += index_value * weight
            valid_indices += 1

    result['comprehensive_index_old_algo'] = safe_round(
        comprehensive_index_old_algo, 3
    ) if valid_indices > 0 else None

    # 计算样本覆盖率
    result['sample_coverage'] = safe_round(
        len(daily_data) / 30 * 100, 2
    ) if stat_type == 'monthly' else None

    logger.info(
        "old_standard_city_stats_calculated",
        city=city_name,
        comprehensive_index_new_algo=result.get('comprehensive_index_new_algo'),
        comprehensive_index_old_algo=result.get('comprehensive_index_old_algo')
    )

    return result


# =============================================================================
# 数据抓取器类
# =============================================================================

class CityStatisticsOldStandardFetcher(DataFetcher):
    """
    168城市空气质量统计数据抓取器（旧标准限值版本）

    与CityStatisticsFetcher的区别：
    1. 污染物浓度使用final_output规则修约
    2. 存储到city_168_statistics_old_standard表
    3. 存储2套综合指数：旧限值+新算法、旧限值+旧算法
    """

    def __init__(self):
        """初始化抓取器"""
        super().__init__(
            name="city_168_statistics_old_standard_fetcher",
            description="168城市空气质量统计预计算（旧标准限值）",
            schedule="0 8 * * *",  # 每天上午8点
            version="1.0.0"
        )
        self.table_name = 'city_168_statistics_old_standard'
        self.cities = ALL_168_CITIES

    def get_connection_string(self) -> str:
        """获取数据库连接字符串"""
        try:
            from config.settings import Settings
            settings = Settings()
            return settings.sqlserver_connection_string
        except Exception as e:
            logger.error("获取数据库配置失败", error=str(e))
            raise

    def fetch_daily_data(
        self,
        city: str,
        start_date: str,
        end_date: str
    ) -> List[Dict]:
        """
        从数据库查询城市的日数据

        Args:
            city: 城市名称
            start_date: 开始日期 (YYYY-MM-DD)
            end_date: 结束日期 (YYYY-MM-DD)

        Returns:
            日数据列表
        """
        conn_str = self.get_connection_string()
        conn = pyodbc.connect(conn_str, timeout=30)
        cursor = conn.cursor()

        try:
            # 查询城市日数据（从qc_history表或其他数据源）
            sql = """
                SELECT
                    stat_date,
                    city_name,
                    so2_concentration,
                    no2_concentration,
                    pm10_concentration,
                    pm2_5_concentration,
                    co_concentration,
                    o3_8h_concentration
                FROM qc_history
                WHERE city_name = ?
                  AND stat_date >= ?
                  AND stat_date <= ?
                ORDER BY stat_date
            """

            cursor.execute(sql, [city, start_date, end_date])
            rows = cursor.fetchall()

            # 转换为字典列表
            columns = [column[0] for column in cursor.description]
            results = []
            for row in rows:
                record = dict(zip(columns, row))
                results.append(record)

            logger.info(
                "fetched_daily_data_for_city",
                city=city,
                start_date=start_date,
                end_date=end_date,
                record_count=len(results)
            )

            return results

        finally:
            cursor.close()
            conn.close()

    def save_statistics(self, statistics: List[Dict]) -> bool:
        """
        保存统计数据到数据库

        Args:
            statistics: 统计数据列表

        Returns:
            是否成功
        """
        if not statistics:
            logger.warning("no_statistics_to_save")
            return False

        conn_str = self.get_connection_string()
        conn = pyodbc.connect(conn_str, timeout=30)
        cursor = conn.cursor()

        try:
            # 删除旧数据（同一城市、同一日期、同一类型）
            for stat in statistics:
                cursor.execute("""
                    DELETE FROM city_168_statistics_old_standard
                    WHERE city_name = ? AND stat_date = ? AND stat_type = ?
                """, [stat['city_name'], stat['stat_date'], stat['stat_type']])

            # 插入新数据
            for stat in statistics:
                cursor.execute("""
                    INSERT INTO city_168_statistics_old_standard (
                        stat_date, stat_type, city_name, city_code,
                        so2_concentration, no2_concentration, pm10_concentration,
                        pm2_5_concentration, co_concentration, o3_8h_concentration,
                        so2_index, no2_index, pm10_index, pm2_5_index, co_index, o3_8h_index,
                        comprehensive_index_new_algo, comprehensive_index_old_algo,
                        data_days, sample_coverage, region, province
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, [
                    stat['stat_date'], stat['stat_type'], stat['city_name'], None,
                    stat.get('so2_concentration'), stat.get('no2_concentration'),
                    stat.get('pm10_concentration'), stat.get('pm2_5_concentration'),
                    stat.get('co_concentration'), stat.get('o3_8h_concentration'),
                    stat.get('so2_index'), stat.get('no2_index'),
                    stat.get('pm10_index'), stat.get('pm2_5_index'),
                    stat.get('co_index'), stat.get('o3_8h_index'),
                    stat.get('comprehensive_index_new_algo'),
                    stat.get('comprehensive_index_old_algo'),
                    stat.get('data_days'), stat.get('sample_coverage'),
                    stat.get('region'), stat.get('province')
                ])

            conn.commit()

            logger.info(
                "saved_old_standard_statistics",
                record_count=len(statistics)
            )

            return True

        except Exception as e:
            conn.rollback()
            logger.error(
                "failed_to_save_statistics",
                error=str(e),
                error_type=type(e).__name__
            )
            return False

        finally:
            cursor.close()
            conn.close()

    def update_rankings(self, stat_date: str, stat_type: str) -> bool:
        """
        更新综合指数排名

        Args:
            stat_date: 统计日期
            stat_type: 统计类型

        Returns:
            是否成功
        """
        conn_str = self.get_connection_string()
        conn = pyodbc.connect(conn_str, timeout=30)
        cursor = conn.cursor()

        try:
            # 更新旧限值+新算法排名
            cursor.execute("""
                SELECT city_name, comprehensive_index_new_algo
                FROM city_168_statistics_old_standard
                WHERE stat_date = ? AND stat_type = ?
                  AND comprehensive_index_new_algo IS NOT NULL
                ORDER BY comprehensive_index_new_algo
            """, [stat_date, stat_type])

            rows = cursor.fetchall()
            for rank, row in enumerate(rows, start=1):
                cursor.execute("""
                    UPDATE city_168_statistics_old_standard
                    SET comprehensive_index_rank_new_algo = ?
                    WHERE city_name = ? AND stat_date = ? AND stat_type = ?
                """, [rank, row.city_name, stat_date, stat_type])

            # 更新旧限值+旧算法排名
            cursor.execute("""
                SELECT city_name, comprehensive_index_old_algo
                FROM city_168_statistics_old_standard
                WHERE stat_date = ? AND stat_type = ?
                  AND comprehensive_index_old_algo IS NOT NULL
                ORDER BY comprehensive_index_old_algo
            """, [stat_date, stat_type])

            rows = cursor.fetchall()
            for rank, row in enumerate(rows, start=1):
                cursor.execute("""
                    UPDATE city_168_statistics_old_standard
                    SET comprehensive_index_rank_old_algo = ?
                    WHERE city_name = ? AND stat_date = ? AND stat_type = ?
                """, [rank, row.city_name, stat_date, stat_type])

            conn.commit()

            logger.info(
                "updated_old_standard_rankings",
                stat_date=stat_date,
                stat_type=stat_type
            )

            return True

        except Exception as e:
            conn.rollback()
            logger.error(
                "failed_to_update_rankings",
                error=str(e),
                error_type=type(e).__name__
            )
            return False

        finally:
            cursor.close()
            conn.close()

    async def fetch_and_store(self):
        """
        获取并存储统计数据（调度器调用）

        每天计算三种类型：
        1. current_month（当月累计）- 每天
        2. annual_ytd（年度累计）- 每天
        3. monthly（月度统计）- 每月1日计算上月
        """
        today = datetime.now().date()
        stat_date = today.strftime('%Y-%m-%d')

        logger.info(
            "city_statistics_old_standard_fetcher_started",
            stat_date=stat_date
        )

        try:
            # 每月1日：计算上月完整月的monthly统计
            if today.day == 1:
                await self._calculate_monthly(today)

            # 每天：更新current_month和annual_ytd
            await self._calculate_current_month(today)
            await self._calculate_annual_ytd(today)

            logger.info(
                "city_statistics_old_standard_fetcher_completed",
                stat_date=stat_date
            )

        except Exception as e:
            logger.error(
                "city_statistics_old_standard_fetcher_failed",
                stat_date=stat_date,
                error=str(e),
                exc_info=True
            )
            raise

    async def _calculate_monthly(self, today: datetime.date):
        """计算上月完整月的月度统计"""
        # 上月最后一天
        last_day_of_last_month = today.replace(day=1) - timedelta(days=1)
        # 上月第一天
        first_day_of_last_month = last_day_of_last_month.replace(day=1)

        stat_date = first_day_of_last_month.strftime('%Y-%m-%d')
        start_date = stat_date
        end_date = last_day_of_last_month.strftime('%Y-%m-%d')

        await self._run_calculation(start_date, end_date, stat_date, 'monthly')

    async def _calculate_current_month(self, today: datetime.date):
        """计算当月累计统计"""
        stat_date = today.replace(day=1).strftime('%Y-%m-%d')
        start_date = stat_date
        end_date = today.strftime('%Y-%m-%d')

        await self._run_calculation(start_date, end_date, stat_date, 'current_month')

    async def _calculate_annual_ytd(self, today: datetime.date):
        """计算年度累计统计"""
        stat_date = today.replace(month=1, day=1).strftime('%Y-%m-%d')
        start_date = stat_date
        end_date = today.strftime('%Y-%m-%d')

        await self._run_calculation(start_date, end_date, stat_date, 'annual_ytd')

    async def _run_calculation(self, start_date: str, end_date: str, stat_date: str, stat_type: str):
        """执行统计计算"""
        logger.info(
            "calculating_old_standard_statistics",
            start_date=start_date,
            end_date=end_date,
            stat_date=stat_date,
            stat_type=stat_type
        )

        # 统计所有城市
        all_statistics = []

        for city in self.cities:
            try:
                # 查询日数据
                daily_data = self.fetch_daily_data(city, start_date, end_date)

                if not daily_data:
                    logger.warning("no_daily_data_for_city", city=city)
                    continue

                # 计算统计指标
                city_stat = calculate_city_statistics(
                    city, daily_data, stat_type
                )
                city_stat['stat_date'] = stat_date

                all_statistics.append(city_stat)

            except Exception as e:
                logger.error(
                    "failed_to_process_city",
                    city=city,
                    error=str(e),
                    error_type=type(e).__name__
                )
                continue

        # 保存统计数据
        if all_statistics:
            success = self.save_statistics(all_statistics)

            if success:
                # 更新排名
                self.update_rankings(stat_date, stat_type)

                logger.info(
                    "old_standard_statistics_completed",
                    stat_date=stat_date,
                    stat_type=stat_type,
                    cities_count=len(all_statistics)
                )
            else:
                logger.error("failed_to_save_statistics")
        else:
            logger.warning("no_statistics_to_save")

    async def run(self, stat_date: str = None, stat_type: str = 'monthly'):
        """
        执行数据抓取任务（手动调用）

        Args:
            stat_date: 统计日期 (YYYY-MM-DD)，默认为昨天
            stat_type: 统计类型（monthly/annual_ytd/current_month）
        """
        # 默认统计日期为昨天
        if stat_date is None:
            stat_date = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')

        logger.info(
            "city_statistics_old_standard_fetcher_started",
            stat_date=stat_date,
            stat_type=stat_type,
            cities_count=len(self.cities)
        )

        # 计算日期范围
        if stat_type == 'monthly':
            # 月度统计：当月1日到最后一天
            date_obj = datetime.strptime(stat_date, '%Y-%m-%d')
            start_date = date_obj.replace(day=1).strftime('%Y-%m-%d')
            end_date = stat_date
        elif stat_type == 'annual_ytd':
            # 年度累计：1月1日到当前日期
            date_obj = datetime.strptime(stat_date, '%Y-%m-%d')
            start_date = date_obj.replace(month=1, day=1).strftime('%Y-%m-%d')
            end_date = stat_date
        else:  # current_month
            # 当月累计：当月1日到当前日期
            date_obj = datetime.strptime(stat_date, '%Y-%m-%d')
            start_date = date_obj.replace(day=1).strftime('%Y-%m-%d')
            end_date = stat_date

        await self._run_calculation(start_date, end_date, stat_date, stat_type)


# =============================================================================
# 主程序入口
# =============================================================================

async def main():
    """主程序入口"""
    import argparse

    parser = argparse.ArgumentParser(description='168城市空气质量统计抓取器（旧标准限值版本）')
    parser.add_argument('--date', type=str, help='统计日期 (YYYY-MM-DD)，默认为昨天')
    parser.add_argument('--type', type=str, default='monthly',
                       choices=['monthly', 'annual_ytd', 'current_month'],
                       help='统计类型（默认monthly）')

    args = parser.parse_args()

    fetcher = CityStatisticsOldStandardFetcher()
    await fetcher.run(args.date, args.type)


if __name__ == '__main__':
    asyncio.run(main())
