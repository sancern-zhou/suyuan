"""
省级空气质量统计数据抓取器（旧标准限值版本）

定时从XcAiDb数据库提取数据，计算31个省级行政区的空气质量评价指标（按HJ663旧标准限值），
并将结果缓存回XcAiDb数据库的province_statistics_old_standard表。

核心功能：
- 每天上午9点自动运行（在新标准统计之后）
- 计算月度统计、年度累计、当月累计三种统计类型
- 按HJ663旧标准限值计算综合指数和单项指数
- 污染物浓度使用final_output规则修约（PM2.5/CO保留1位，其他取整）
- 支持多城市数据合并统计
- 自动排名计算

作者：Claude Code
版本：1.0.0
日期：2026-04-09
"""

from typing import List, Dict, Tuple, Optional
from datetime import datetime, timedelta
from decimal import Decimal
import structlog
import pyodbc

from app.fetchers.base.fetcher_interface import DataFetcher
from app.fetchers.city_statistics.city_statistics_fetcher import (
    SQLServerClient,
    ALL_168_CITIES,
    safe_round,
    calculate_percentile
)
from app.fetchers.city_statistics.city_statistics_old_standard_fetcher import (
    apply_final_output_rounding,
    ANNUAL_STANDARD_LIMITS_2013,
    WEIGHTS_NEW_ALGO,
    WEIGHTS_OLD_ALGO
)

logger = structlog.get_logger()


# =============================================================================
# 省级统计计算函数（旧标准限值版本）
# =============================================================================

def calculate_province_rankings_old_standard(statistics: List[Dict]) -> List[Dict]:
    """
    计算省份排名（按综合指数）- 旧标准版本

    同时计算2套标准组合的排名：
    - 旧限值+新算法
    - 旧限值+旧算法

    Args:
        statistics: 统计数据列表

    Returns:
        添加了排名的统计数据列表
    """
    # 计算旧限值+新算法排名
    valid_stats_new_algo = [s for s in statistics if s.get('comprehensive_index_new_algo') is not None]
    sorted_stats_new_algo = sorted(valid_stats_new_algo, key=lambda x: x['comprehensive_index_new_algo'])

    for rank, stat in enumerate(sorted_stats_new_algo, start=1):
        stat['comprehensive_index_rank_new_algo'] = rank

    # 计算旧限值+旧算法排名
    valid_stats_old_algo = [s for s in statistics if s.get('comprehensive_index_old_algo') is not None]
    sorted_stats_old_algo = sorted(valid_stats_old_algo, key=lambda x: x['comprehensive_index_old_algo'])

    for rank, stat in enumerate(sorted_stats_old_algo, start=1):
        stat['comprehensive_index_rank_old_algo'] = rank

    # 返回完整列表（包括无效数据）
    result = []
    ranked_dict = {s['province_name']: s for s in sorted_stats_new_algo}

    for stat in statistics:
        if stat['province_name'] in ranked_dict:
            result.append(ranked_dict[stat['province_name']])
        else:
            result.append(stat)

    return result


def calculate_province_statistics_old_standard(city_records: Dict[str, List[Dict]]) -> Optional[Dict]:
    """
    计算省级空气质量统计数据（旧标准限值版本）

    关键区别：
    1. 污染物浓度使用final_output规则修约（PM2.5/CO保留1位，其他取整）
    2. 计算综合指数时使用修约后的浓度值
    3. 使用旧标准限值（PM10=70, PM2.5=35）

    Args:
        city_records: 省内各城市的数据字典 {城市名: [数据记录]}

    Returns:
        统计结果字典，如果输入为空则返回None
    """
    if not city_records:
        return None

    # 合并省内所有城市的数据
    all_records = []
    city_names = []

    for city_name, records in city_records.items():
        if records:
            all_records.extend(records)
            city_names.append(city_name)

    if not all_records:
        return None

    result = {}

    # 提取各污染物的日浓度值
    so2_values = []
    no2_values = []
    pm10_values = []
    pm25_values = []
    co_values = []
    o3_8h_values = []

    for record in all_records:
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

        so2 = safe_get(record, ['SO2', 'so2', 'SO2_24h', 'so2_24h'])
        no2 = safe_get(record, ['NO2', 'no2', 'NO2_24h', 'no2_24h'])
        pm10 = safe_get(record, ['PM10', 'pm10', 'PM10_24h', 'pm10_24h'])
        pm25 = safe_get(record, ['PM2_5', 'pm2_5', 'PM2_5_24h', 'pm2_5_24h'])
        co = safe_get(record, ['CO', 'co', 'CO_24h', 'co_24h'])
        o3_8h = safe_get(record, ['O3_8h', 'o3_8h', 'O3_8h_24h', 'o3_8h_24h'])

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

    # 添加元数据
    result['city_count'] = len(city_names)
    result['city_names'] = ','.join(sorted(city_names))
    result['data_days'] = len(all_records)

    return result


# =============================================================================
# SQLServerClient扩展
# =============================================================================

class ProvinceOldStandardSQLServerClient(SQLServerClient):
    """扩展的SQL Server客户端，支持省级旧标准统计数据插入"""

    def insert_province_statistics_old_standard(self, statistics: List[Dict], stat_type: str, stat_date: str):
        """
        插入省级旧标准统计数据到province_statistics_old_standard表

        Args:
            statistics: 统计数据列表
            stat_type: 统计类型（monthly/annual_ytd/current_month）
            stat_date: 统计日期
        """
        if not statistics:
            return

        try:
            conn = pyodbc.connect(self.connection_string, timeout=30)
            cursor = conn.cursor()

            # 删除旧数据（如果存在）
            delete_sql = """
            DELETE FROM province_statistics_old_standard
            WHERE stat_type = ? AND stat_date = ?
            """
            cursor.execute(delete_sql, [stat_type, stat_date])

            # 插入新数据
            insert_sql = """
            INSERT INTO province_statistics_old_standard (
                stat_date, stat_type, province_name,
                so2_concentration, no2_concentration, pm10_concentration, pm2_5_concentration,
                co_concentration, o3_8h_concentration,
                so2_index, no2_index, pm10_index, pm2_5_index, co_index, o3_8h_index,
                comprehensive_index_new_algo, comprehensive_index_rank_new_algo,
                comprehensive_index_old_algo, comprehensive_index_rank_old_algo,
                data_days, sample_coverage, city_count, city_names,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, GETDATE(), GETDATE())
            """

            for stat in statistics:
                # 计算样本覆盖率
                max_days = 365 if len(statistics) > 150 else 31
                sample_coverage = safe_round((stat.get('data_days', 0) / max_days) * 100, 2) if max_days > 0 else 0

                params = [
                    stat_date, stat_type,
                    stat.get('province_name'),
                    stat.get('so2_concentration'),
                    stat.get('no2_concentration'),
                    stat.get('pm10_concentration'),
                    stat.get('pm2_5_concentration'),
                    stat.get('co_concentration'),
                    stat.get('o3_8h_concentration'),
                    stat.get('so2_index'),
                    stat.get('no2_index'),
                    stat.get('pm10_index'),
                    stat.get('pm2_5_index'),
                    stat.get('co_index'),
                    stat.get('o3_8h_index'),
                    stat.get('comprehensive_index_new_algo'),
                    stat.get('comprehensive_index_rank_new_algo'),
                    stat.get('comprehensive_index_old_algo'),
                    stat.get('comprehensive_index_rank_old_algo'),
                    stat.get('data_days'),
                    sample_coverage,
                    stat.get('city_count'),
                    stat.get('city_names')
                ]
                cursor.execute(insert_sql, params)

            conn.commit()
            cursor.close()
            conn.close()

            logger.info(
                "province_statistics_old_standard_inserted",
                stat_type=stat_type,
                stat_date=stat_date,
                count=len(statistics)
            )

        except pyodbc.Error as e:
            logger.error(
                "province_statistics_old_standard_insert_error",
                error=str(e),
                sqlstate=e.args[0] if e.args else None
            )
            raise Exception(f"省级旧标准统计数据插入失败: {str(e)}")


# =============================================================================
# ProvinceStatisticsOldStandardFetcher
# =============================================================================

class ProvinceStatisticsOldStandardFetcher(DataFetcher):
    """省级空气质量统计数据抓取器（旧标准限值版本）"""

    def __init__(self):
        super().__init__(
            name="province_statistics_old_standard_fetcher",
            description="省级空气质量统计预计算（旧标准限值）",
            schedule="0 9 * * *",  # 每天上午9点（在新标准统计之后）
            version="1.0.0"
        )
        self.sql_client = ProvinceOldStandardSQLServerClient()
        self.city_fetcher = None  # 延迟初始化，避免循环导入

    def _get_city_fetcher(self):
        """延迟初始化CityStatisticsFetcher"""
        if self.city_fetcher is None:
            from app.fetchers.city_statistics.city_statistics_fetcher import CityStatisticsFetcher
            self.city_fetcher = CityStatisticsFetcher()
        return self.city_fetcher

    async def fetch_and_store(self):
        """
        获取并存储省级旧标准统计数据

        每天计算三种类型：
        1. current_month（当月累计）- 每天
        2. annual_ytd（年度累计）- 每天
        3. monthly（月度统计）- 每月1日计算上月
        """
        today = datetime.now().date()
        stat_date = today.strftime('%Y-%m-%d')

        logger.info(
            "province_statistics_old_standard_fetcher_started",
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
                "province_statistics_old_standard_fetcher_completed",
                stat_date=stat_date
            )

        except Exception as e:
            logger.error(
                "province_statistics_old_standard_fetcher_failed",
                stat_date=stat_date,
                error=str(e),
                exc_info=True
            )
            raise

    def _group_by_province(self, city_data: Dict[str, List[Dict]]) -> Dict[str, Dict[str, List[Dict]]]:
        """
        将城市数据按省份分组

        Args:
            city_data: 城市数据字典

        Returns:
            省份分组数据
        """
        province_groups = {}
        city_fetcher = self._get_city_fetcher()

        for city_name, records in city_data.items():
            if not records:
                continue

            province = city_fetcher._extract_province(city_name)

            if province == '其他':
                logger.warning("city_skipped_no_province", city=city_name)
                continue

            if province not in province_groups:
                province_groups[province] = {}

            province_groups[province][city_name] = records

        return province_groups

    async def _calculate_monthly(self, today: datetime.date):
        """计算上月完整月的月度统计"""
        last_day_of_last_month = today.replace(day=1) - timedelta(days=1)
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
            "calculating_province_old_standard_statistics",
            start_date=start_date,
            end_date=end_date,
            stat_date=stat_date,
            stat_type=stat_type
        )

        # 查询数据
        city_data = self.sql_client.query_city_data(ALL_168_CITIES, start_date, end_date)

        # 按省份分组
        province_groups = self._group_by_province(city_data)

        # 计算统计
        statistics = []
        for province, cities in province_groups.items():
            stat = calculate_province_statistics_old_standard(cities)

            if stat:
                stat['province_name'] = province
                statistics.append(stat)

        # 计算排名
        statistics = calculate_province_rankings_old_standard(statistics)

        # 存储数据库
        self.sql_client.insert_province_statistics_old_standard(statistics, stat_type, stat_date)

        logger.info(
            "province_old_standard_statistics_completed",
            stat_date=stat_date,
            stat_type=stat_type,
            provinces_count=len(statistics)
        )
