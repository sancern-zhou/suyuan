"""
省级空气质量统计数据抓取器（新标准限值版本）- 修复版

修复问题：
1. 省级统计使用全省所有城市，而不是仅168城市
2. 数据天数直接根据查询数据计算，不需要硬编码月份天数

作者：Claude Code
版本：2.0.0
日期：2026-04-16
"""

from typing import List, Dict, Tuple, Optional
from datetime import datetime, timedelta
import structlog
import pyodbc

from app.fetchers.base.fetcher_interface import DataFetcher
from app.fetchers.city_statistics.city_statistics_fetcher import (
    SQLServerClient,
    safe_round,
    calculate_percentile,
    calculate_statistics,
    WEIGHTS_2026,
    WEIGHTS_2012
)

logger = structlog.get_logger()


# =============================================================================
# 省级统计计算函数（修复版）
# =============================================================================

def calculate_province_statistics_v2(city_records: Dict[str, List[Dict]]) -> Optional[Dict]:
    """
    计算省级空气质量统计数据（修复版）

    修复说明：
    1. 直接复用 calculate_statistics，合并所有城市数据
    2. 数学上等价于：先算各城市均值，再求平均
    3. 数据天数直接使用查询到的实际数据条数

    Args:
        city_records: 省内各城市的数据字典 {城市名: [数据记录]}

    Returns:
        统计结果字典
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

    # 直接复用 calculate_statistics
    result = calculate_statistics(all_records)

    if result:
        result['city_count'] = len(city_names)
        result['city_names'] = ','.join(sorted(city_names))

    return result


# =============================================================================
# 扩展的SQL Server客户端（修复版）
# =============================================================================

class ProvinceSQLServerClientV2(SQLServerClient):
    """扩展的SQL Server客户端，支持查询所有城市"""

    def get_all_cities_grouped_by_province(self) -> Dict[str, List[str]]:
        """
        从数据库查询所有城市，按省份分组

        Returns:
            {省份名: [城市列表]}
        """
        try:
            conn = pyodbc.connect(self.connection_string, timeout=30)
            cursor = conn.cursor()

            # 查询所有不重复的城市名称
            sql = """
            SELECT DISTINCT Area
            FROM CityDayAQIPublishHistory
            WHERE Area IS NOT NULL
              AND LEN(Area) > 0
            ORDER BY Area
            """

            cursor.execute(sql)
            rows = cursor.fetchall()

            cursor.close()
            conn.close()

            # 按省份分组
            from app.fetchers.city_statistics.city_statistics_fetcher import CityStatisticsFetcher
            city_fetcher = CityStatisticsFetcher()

            province_cities = {}
            for row in rows:
                city_with_suffix = row.Area
                # 去掉"市"后缀
                city_name = city_with_suffix[:-1] if city_with_suffix.endswith("市") else city_with_suffix

                # 提取省份
                province = city_fetcher._extract_province(city_name)

                if province == '其他':
                    continue

                if province not in province_cities:
                    province_cities[province] = []

                if city_name not in province_cities[province]:
                    province_cities[province].append(city_name)

            logger.info(
                "get_all_cities_grouped_by_province_success",
                provinces_count=len(province_cities),
                total_cities=sum(len(cities) for cities in province_cities.values())
            )

            return province_cities

        except pyodbc.Error as e:
            logger.error(
                "get_all_cities_grouped_by_province_failed",
                error=str(e),
                sqlstate=e.args[0] if e.args else None
            )
            raise Exception(f"获取所有城市失败: {str(e)}")

    def query_province_data(self, province: str, cities: List[str], start_date: str, end_date: str) -> Dict[str, List[Dict]]:
        """
        查询指定省份所有城市的数据

        Args:
            province: 省份名称
            cities: 城市名称列表
            start_date: 开始日期
            end_date: 结束日期

        Returns:
            城市 -> 数据列表的字典
        """
        # 复用父类的 query_city_data 方法
        return self.query_city_data(cities, start_date, end_date)


# =============================================================================
# 省级排名计算（保持不变）
# =============================================================================

def calculate_province_rankings(statistics: List[Dict]) -> List[Dict]:
    """
    计算省份排名（按综合指数）

    同时计算2套标准组合的排名：
    - 新限值+新算法
    - 新限值+旧算法

    Args:
        statistics: 统计数据列表

    Returns:
        添加了排名的统计数据列表
    """
    # 计算新限值+新算法排名
    valid_stats_new_algo = [s for s in statistics if s.get('comprehensive_index') is not None]
    sorted_stats_new_algo = sorted(valid_stats_new_algo, key=lambda x: x['comprehensive_index'])

    for rank, stat in enumerate(sorted_stats_new_algo, start=1):
        stat['comprehensive_index_rank'] = rank

    # 计算新限值+旧算法排名
    valid_stats_old_algo = [s for s in statistics if s.get('comprehensive_index_new_limit_old_algo') is not None]
    sorted_stats_old_algo = sorted(valid_stats_old_algo, key=lambda x: x['comprehensive_index_new_limit_old_algo'])

    for rank, stat in enumerate(sorted_stats_old_algo, start=1):
        stat['comprehensive_index_rank_new_limit_old_algo'] = rank

    # 返回完整列表（包括无效数据）
    result = []
    ranked_dict = {s['province_name']: s for s in sorted_stats_new_algo}

    for stat in statistics:
        if stat['province_name'] in ranked_dict:
            result.append(ranked_dict[stat['province_name']])
        else:
            result.append(stat)

    return result


# =============================================================================
# 省级统计抓取器（修复版）
# =============================================================================

class ProvinceStatisticsFetcherV2(DataFetcher):
    """省级空气质量统计数据抓取器（修复版 - 使用全省所有城市）"""

    def __init__(self):
        super().__init__(
            name="province_statistics_new_standard_fetcher_v2",
            description="省级空气质量统计预计算（新标准限值，使用全省所有城市）",
            schedule="0 8 * * *",  # 每天上午8点
            version="2.0.0"
        )
        self.sql_client = ProvinceSQLServerClientV2()
        self.city_fetcher = None  # 延迟初始化
        self._province_city_cache = None  # 省份城市缓存

    def _get_city_fetcher(self):
        """延迟初始化CityStatisticsFetcher"""
        if self.city_fetcher is None:
            from app.fetchers.city_statistics.city_statistics_fetcher import CityStatisticsFetcher
            self.city_fetcher = CityStatisticsFetcher()
        return self.city_fetcher

    def _get_all_cities_by_province(self) -> Dict[str, List[str]]:
        """
        获取所有城市按省份分组（带缓存）

        Returns:
            {省份名: [城市列表]}
        """
        if self._province_city_cache is None:
            self._province_city_cache = self.sql_client.get_all_cities_grouped_by_province()

        return self._province_city_cache

    async def fetch_and_store(self):
        """
        获取并存储省级统计数据（优化版）

        每天只计算两种类型：
        1. current_month（当月累计）- 每天
        2. annual_ytd（年度累计）- 每天

        每月1日：将上月current_month转换为monthly
        """
        today = datetime.now().date()

        logger.info("province_statistics_fetcher_v2_started", today=today.isoformat())

        try:
            # 每月1日：将上月的current_month转换为monthly
            if today.day == 1:
                await self._convert_current_to_monthly(today)

            # 每天：更新current_month和annual_ytd
            await self._calculate_and_store_current_month(today)
            await self._calculate_and_store_annual_ytd(today)

            logger.info("province_statistics_fetcher_v2_completed", today=today.isoformat())

        except Exception as e:
            logger.error(
                "province_statistics_fetcher_v2_failed",
                today=today.isoformat(),
                error=str(e),
                exc_info=True
            )
            raise

    async def _calculate_and_store_annual_ytd(self, today: datetime.date):
        """
        计算并存储年度累计统计（修复版）

        修复：使用全省所有城市，而不是仅168城市

        Args:
            today: 今天日期
        """
        year = today.year
        start_date = f"{year}-01-01"
        end_date = today.strftime('%Y-%m-%d')

        logger.info(
            "calculating_province_annual_ytd_statistics_v2",
            year=year,
            start_date=start_date,
            end_date=end_date
        )

        # 获取所有城市按省份分组
        province_cities = self._get_all_cities_by_province()

        # 计算统计
        statistics = []
        for province, cities in province_cities.items():
            # 查询该省所有城市的数据
            city_data = self.sql_client.query_province_data(province, cities, start_date, end_date)

            if not city_data:
                logger.warning(f"no_data_for_province", province=province)
                continue

            # 计算省级统计
            stat = calculate_province_statistics_v2(city_data)

            if stat:
                stat['province_name'] = province
                statistics.append(stat)

        # 计算排名
        statistics = calculate_province_rankings(statistics)

        # 存储数据库
        stat_date = f"{year}-01-01"
        self.sql_client.insert_province_statistics(statistics, 'annual_ytd', stat_date)

        logger.info(
            "province_annual_ytd_statistics_v2_completed",
            year=year,
            provinces_count=len(statistics)
        )

    async def _calculate_and_store_current_month(self, today: datetime.date):
        """
        计算并存储当月累计统计（修复版）

        修复：使用全省所有城市，而不是仅168城市

        Args:
            today: 今天日期
        """
        year_month = today.strftime('%Y-%m')
        start_date = f"{year_month}-01"
        end_date = today.strftime('%Y-%m-%d')

        logger.info(
            "calculating_province_current_month_statistics_v2",
            year_month=year_month,
            start_date=start_date,
            end_date=end_date
        )

        # 获取所有城市按省份分组
        province_cities = self._get_all_cities_by_province()

        # 计算统计
        statistics = []
        for province, cities in province_cities.items():
            # 查询该省所有城市的数据
            city_data = self.sql_client.query_province_data(province, cities, start_date, end_date)

            if not city_data:
                logger.warning(f"no_data_for_province", province=province)
                continue

            # 计算省级统计
            stat = calculate_province_statistics_v2(city_data)

            if stat:
                stat['province_name'] = province
                statistics.append(stat)

        # 计算排名
        statistics = calculate_province_rankings(statistics)

        # 存储数据库
        self.sql_client.insert_province_statistics(statistics, 'current_month', start_date)

        logger.info(
            "province_current_month_statistics_v2_completed",
            year_month=year_month,
            provinces_count=len(statistics)
        )

    async def _convert_current_to_monthly(self, today: datetime.date):
        """
        将上月的current_month数据转换为monthly

        Args:
            today: 今天日期（应该是每月1日）
        """
        # 获取上月完整月的日期
        last_day_of_last_month = today.replace(day=1) - timedelta(days=1)
        first_day_of_last_month = last_day_of_last_month.replace(day=1)

        year_month = first_day_of_last_month.strftime('%Y-%m')
        stat_date = f"{year_month}-01"

        logger.info(
            "converting_current_to_monthly_v2",
            year_month=year_month,
            stat_date=stat_date
        )

        try:
            conn = pyodbc.connect(self.sql_client.connection_string, timeout=30)
            cursor = conn.cursor()

            # 1. 查询上月的current_month数据
            select_sql = """
            SELECT
                province_name,
                so2_concentration, no2_concentration, pm10_concentration, pm2_5_concentration,
                co_concentration, o3_8h_concentration,
                so2_index, no2_index, pm10_index, pm2_5_index, co_index, o3_8h_index,
                comprehensive_index, comprehensive_index_rank,
                comprehensive_index_new_limit_old_algo, comprehensive_index_rank_new_limit_old_algo,
                data_days, sample_coverage, city_count, city_names
            FROM province_statistics_new_standard
            WHERE stat_type = 'current_month' AND stat_date = ?
            """

            cursor.execute(select_sql, [stat_date])
            current_data = cursor.fetchall()

            if not current_data:
                logger.warning(
                    "no_current_month_data_found",
                    year_month=year_month,
                    message="未找到当月累计数据，无法转换"
                )
                cursor.close()
                conn.close()
                return

            # 2. 删除已有的monthly数据（如果存在）
            delete_sql = """
            DELETE FROM province_statistics_new_standard
            WHERE stat_type = 'monthly' AND stat_date = ?
            """
            cursor.execute(delete_sql, [stat_date])

            # 3. 插入monthly数据
            insert_sql = """
            INSERT INTO province_statistics_new_standard (
                stat_date, stat_type, province_name,
                so2_concentration, no2_concentration, pm10_concentration, pm2_5_concentration,
                co_concentration, o3_8h_concentration,
                so2_index, no2_index, pm10_index, pm2_5_index, co_index, o3_8h_index,
                comprehensive_index, comprehensive_index_rank,
                comprehensive_index_new_limit_old_algo, comprehensive_index_rank_new_limit_old_algo,
                standard_version,
                data_days, sample_coverage, city_count, city_names,
                created_at, updated_at
            ) VALUES (?, 'monthly', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, GETDATE(), GETDATE())
            """

            for row in current_data:
                params = [
                    stat_date,
                    row.province_name,
                    row.so2_concentration, row.no2_concentration, row.pm10_concentration, row.pm2_5_concentration,
                    row.co_concentration, row.o3_8h_concentration,
                    row.so2_index, row.no2_index, row.pm10_index, row.pm2_5_index, row.co_index, row.o3_8h_index,
                    row.comprehensive_index, row.comprehensive_index_rank,
                    row.comprehensive_index_new_limit_old_algo, row.comprehensive_index_rank_new_limit_old_algo,
                    'HJ663-2026',
                    row.data_days, row.sample_coverage, row.city_count, row.city_names
                ]
                cursor.execute(insert_sql, params)

            conn.commit()
            cursor.close()
            conn.close()

            logger.info(
                "current_to_monthly_conversion_success_v2",
                year_month=year_month,
                stat_date=stat_date,
                provinces_count=len(current_data)
            )

        except Exception as e:
            logger.error(
                "current_to_monthly_conversion_failed",
                year_month=year_month,
                error=str(e),
                exc_info=True
            )
            raise
