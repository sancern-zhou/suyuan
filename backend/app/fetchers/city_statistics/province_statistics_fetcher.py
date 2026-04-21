"""
省级空气质量统计数据抓取器（新标准限值版本）

定时从XcAiDb数据库提取数据，计算全国各省级行政区的空气质量评价指标（按HJ663新标准限值），
并将结果缓存回XcAiDb数据库的province_statistics_new_standard表。

核心功能：
- 每天上午8点自动运行
- 计算四种统计类型：
  1. ytd_to_month（年初到某月累计：1-1月、1-2月、...至上月）- 避免"修约→计算→再修约"误差
  2. month_current（当月累计）- 每天
  3. year_to_date（年初至今累计）- 每天
  4. month_complete（完整月统计）- 每月1日从month_current转换
- 按HJ663新标准限值计算综合指数和单项指数
- 支持多城市数据合并统计（包含全国所有地级市、州、盟）
- 自动排名计算

数据示例（4月份时）：
  ytd_to_month + stat_date='2026-01'  → 年初至1月累计
  ytd_to_month + stat_date='2026-02'  → 年初至2月累计
  ytd_to_month + stat_date='2026-03'  → 年初至3月累计
  month_current + stat_date='2026-04' → 4月当月累计
  year_to_date + stat_date='2026'      → 年初至今累计
  month_complete + stat_date='2026-03' → 3月完整月

注意：本抓取器统计范围为全国所有城市，不限于168重点城市。

作者：Claude Code
版本：1.1.0
日期：2026-04-18
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
    WEIGHTS_2013
)

logger = structlog.get_logger()


# =============================================================================
# 云南自治州名称映射（CityDayAQIPublishHistory表中的Area -> bsd_city表中的name）
# 由于CityDayAQIPublishHistory表中云南自治州使用区县级CityCode，需要通过名称匹配
YUNNAN_AUTONOMOUS_PREFECTURE_MAP = {
    '楚雄彝族自治州': '楚雄彝族自治州',
    '红河哈尼族彝族自治州': '红河哈尼族彝族自治州',
    '文山壮族苗族自治州': '文山壮族苗族自治州',
    '西双版纳傣族自治州': '西双版纳傣族自治州',
    '大理白族自治州': '大理白族自治州',
    '德宏傣族景颇族自治州': '德宏傣族景颇族自治州',
    '怒江傈僳族自治州': '怒江傈僳族自治州',
    '迪庆藏族自治州': '迪庆藏族自治州',
}


# =============================================================================
# 省级统计计算函数
# =============================================================================

def calculate_province_rankings(statistics: List[Dict]) -> List[Dict]:
    """
    计算省份排名（按综合指数）- 新标准版本

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


def calculate_province_statistics(city_records: Dict[str, List[Dict]]) -> Optional[Dict]:
    """
    计算省级空气质量统计数据

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

    # 直接复用 calculate_statistics（已实现正确的统计方法）
    result = calculate_statistics(all_records)

    if result:
        result['city_count'] = len(city_names)
        result['city_names'] = ','.join(sorted(city_names))

        # 修正 sample_coverage：省级统计应该计算所有城市的平均样本覆盖率
        # 而不是用总记录数除以365（因为总记录数 = 城市数 * 365）
        # 正确做法：先计算每个城市的样本覆盖率，再求平均
        city_coverages = []
        for city_name, records in city_records.items():
            if records:
                # 每个城市的期望天数是365（年度统计）
                city_coverage = (len(records) / 365) * 100
                city_coverages.append(city_coverage)

        # 取所有城市的平均样本覆盖率
        if city_coverages:
            result['sample_coverage'] = safe_round(sum(city_coverages) / len(city_coverages), 2)

    return result


def normalize_city_name(city_name: str) -> str:
    """
    标准化城市名称，移除"市"、"省"等后缀

    Args:
        city_name: 原始城市名称

    Returns:
        标准化后的城市名称
    """
    suffixes = ['市', '省', '自治区', '地区', '盟', '州']
    normalized = city_name
    for suffix in suffixes:
        if normalized.endswith(suffix):
            normalized = normalized[:-len(suffix)]
            break  # 只移除一个后缀
    return normalized



# =============================================================================
# 验证函数（使用bsd_city表动态查询）
# =============================================================================

def validate_province_mapping(city_data: Dict[str, List[Dict]]) -> List[str]:
    """验证所有城市都能正确映射到省份（使用bsd_city表）"""
    warnings = []

    try:
        from app.fetchers.city_statistics.province_statistics_fetcher import ProvinceSQLServerClient
        sql_client = ProvinceSQLServerClient()

        conn = pyodbc.connect(sql_client.connection_string, timeout=30)
        cursor = conn.cursor()

        # 从bsd_city表获取所有地级市的映射（省份使用level=1的简称）
        cursor.execute("""
            SELECT c.name as city_name, p.name as province_name
            FROM bsd_city c
            INNER JOIN bsd_city p ON c.parentid = p.code AND p.level = '1'
            WHERE c.level = '2'
        """)

        city_to_province_map = {row.city_name: row.province_name for row in cursor}

        cursor.close()
        conn.close()

        # 验证所有城市都能找到映射
        for city_name in city_data.keys():
            if city_name not in city_to_province_map:
                warnings.append(f"城市 '{city_name}' 在bsd_city表中未找到")

    except pyodbc.Error as e:
        warnings.append(f"查询bsd_city表失败: {str(e)}")

    return warnings


def validate_city_count(statistics: List[Dict]) -> List[str]:
    """验证每个省份报告的城市数量（从bsd_city表查询预期数量）"""
    warnings = []

    try:
        from app.fetchers.city_statistics.province_statistics_fetcher import ProvinceSQLServerClient
        sql_client = ProvinceSQLServerClient()

        conn = pyodbc.connect(sql_client.connection_string, timeout=30)
        cursor = conn.cursor()

        # 从bsd_city表统计每个省份的地级市数量（省份使用level=1的简称）
        cursor.execute("""
            SELECT p.name as province_name, COUNT(*) as city_count
            FROM bsd_city c
            INNER JOIN bsd_city p ON c.parentid = p.code AND p.level = '1'
            WHERE c.level = '2'
            GROUP BY p.name
        """)

        expected_counts = {row.province_name: row.city_count for row in cursor}

        cursor.close()
        conn.close()

        # 验证报告的城市数量
        for stat in statistics:
            province = stat['province_name']
            reported_count = stat.get('city_count', 0)
            expected_count = expected_counts.get(province, 0)

            if expected_count > 0 and reported_count != expected_count:
                warnings.append(
                    f"{province}: 预期{expected_count}个城市，报告{reported_count}个"
                )

    except pyodbc.Error as e:
        warnings.append(f"查询bsd_city表失败: {str(e)}")

    return warnings


def validate_city_names_field(statistics: List[Dict], city_data: Dict) -> List[str]:
    """验证 city_names 字段是否包含所有城市（使用bsd_city表）"""
    warnings = []

    try:
        from app.fetchers.city_statistics.province_statistics_fetcher import ProvinceSQLServerClient
        sql_client = ProvinceSQLServerClient()

        conn = pyodbc.connect(sql_client.connection_string, timeout=30)
        cursor = conn.cursor()

        # 从bsd_city表获取城市-省份映射（省份使用level=1的简称）
        cursor.execute("""
            SELECT c.name as city_name, p.name as province_name
            FROM bsd_city c
            INNER JOIN bsd_city p ON c.parentid = p.code AND p.level = '1'
            WHERE c.level = '2'
        """)

        city_to_province_map = {row.city_name: row.province_name for row in cursor}

        cursor.close()
        conn.close()

        # 验证每个省份的city_names字段
        for stat in statistics:
            province = stat['province_name']
            reported_cities = set(stat.get('city_names', '').split(',')) if stat.get('city_names') else set()

            # 从原始数据中提取该省份的实际城市列表
            actual_cities = set()
            for city_name in city_data.keys():
                if city_to_province_map.get(city_name) == province:
                    actual_cities.add(city_name)

            if reported_cities != actual_cities:
                missing = actual_cities - reported_cities
                if missing:
                    warnings.append(
                        f"{province}: city_names缺失 {len(missing)}个城市"
                    )

    except pyodbc.Error as e:
        warnings.append(f"查询bsd_city表失败: {str(e)}")

    return warnings


def validate_sample_coverage(statistics: List[Dict]) -> List[str]:
    """验证样本覆盖率（应该 > 80%）"""
    warnings = []

    for stat in statistics:
        coverage = stat.get('sample_coverage', 0)
        if coverage < 80:
            warnings.append(
                f"{stat['province_name']}: 样本覆盖率仅 {coverage}%，低于80%"
            )

    return warnings


def validate_ranking_continuity(statistics: List[Dict]) -> List[str]:
    """验证排名连续性"""
    warnings = []

    ranks = sorted([s['comprehensive_index_rank'] for s in statistics
                   if s.get('comprehensive_index_rank') is not None])
    expected_ranks = list(range(1, len(ranks) + 1))

    if ranks != expected_ranks:
        warnings.append(f"排名不连续: {ranks}")

    return warnings


def validate_province_statistics(
    city_data: Dict[str, List[Dict]],
    statistics: List[Dict],
    stat_date: str
) -> Tuple[List[Dict], List[str]]:
    """
    综合验证省级统计数据

    Args:
        city_data: 原始城市数据
        statistics: 统计结果
        stat_date: 统计日期

    Returns:
        (验证通过的统计数据, 警告信息列表)
    """
    all_warnings = []

    # 执行所有验证
    all_warnings.extend(validate_province_mapping(city_data))
    all_warnings.extend(validate_city_count(statistics))
    all_warnings.extend(validate_city_names_field(statistics, city_data))
    all_warnings.extend(validate_sample_coverage(statistics))
    all_warnings.extend(validate_ranking_continuity(statistics))

    # 记录验证报告
    logger.info(
        "province_statistics_validation_report",
        stat_date=stat_date,
        total_warnings=len(all_warnings),
        warnings=all_warnings[:10]  # 记录前10个
    )

    # 发送告警（如果有严重警告）
    critical_warnings = [w for w in all_warnings if '缺失' in w or '错误' in w]
    if critical_warnings:
        logger.error("critical_validation_warnings", warnings=critical_warnings)

    return statistics, all_warnings


# =============================================================================
# SQLServerClient扩展
# =============================================================================

class ProvinceSQLServerClient(SQLServerClient):
    """扩展的SQL Server客户端，支持省级新标准统计数据插入"""

    def insert_province_statistics(self, statistics: List[Dict], stat_type: str, stat_date: str):
        """
        插入省级新标准统计数据到province_statistics_new_standard表

        Args:
            statistics: 统计数据列表
            stat_type: 统计类型（monthly/annual_ytd/current_month/cumulative_month）
            stat_date: 统计日期
        """
        if not statistics:
            return

        try:
            conn = pyodbc.connect(self.connection_string, timeout=30)
            cursor = conn.cursor()

            # 删除旧数据（如果存在）
            delete_sql = """
            DELETE FROM province_statistics_new_standard
            WHERE stat_type = ? AND stat_date = ?
            """
            cursor.execute(delete_sql, [stat_type, stat_date])

            # 插入新数据
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
                exceed_days, valid_days, compliance_rate, exceed_rate,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, GETDATE(), GETDATE())
            """

            import math

            for stat in statistics:
                # 清理数值，确保没有inf或nan，并进行最终修约
                def clean_and_round(v, decimals=None):
                    """清理数值并进行最终修约"""
                    if v is None:
                        return None
                    if isinstance(v, (int, float)):
                        if math.isinf(v) or math.isnan(v):
                            return None
                        # 进行最终修约
                        if decimals is not None:
                            rounded = safe_round(v, decimals)
                            if rounded is None:
                                return None
                            # 保留0位小数时转换为整数，避免存储为25.00
                            return int(rounded) if decimals == 0 else rounded
                    return v

                params = [
                    stat_date, stat_type,
                    stat.get('province_name'),
                    clean_and_round(stat.get('so2_concentration'), 0),      # SO2：整数
                    clean_and_round(stat.get('no2_concentration'), 0),      # NO2：整数
                    clean_and_round(stat.get('pm10_concentration'), 0),     # PM10：整数
                    clean_and_round(stat.get('pm2_5_concentration'), 1),    # PM2.5：1位小数
                    clean_and_round(stat.get('co_concentration'), 1),       # CO：1位小数
                    clean_and_round(stat.get('o3_8h_concentration'), 0),    # O3-8h：整数
                    clean_and_round(stat.get('so2_index')),                 # 指数：保持3位小数（不传decimals）
                    clean_and_round(stat.get('no2_index')),
                    clean_and_round(stat.get('pm10_index')),
                    clean_and_round(stat.get('pm2_5_index')),
                    clean_and_round(stat.get('co_index')),
                    clean_and_round(stat.get('o3_8h_index')),
                    clean_and_round(stat.get('comprehensive_index')),       # 综合指数：保持3位小数
                    clean_and_round(stat.get('comprehensive_index_rank')),
                    clean_and_round(stat.get('comprehensive_index_new_limit_old_algo')),
                    clean_and_round(stat.get('comprehensive_index_rank_new_limit_old_algo')),
                    'HJ663-2026',
                    stat.get('data_days'),
                    stat.get('sample_coverage'),
                    stat.get('city_count'),
                    stat.get('city_names'),
                    stat.get('exceed_days'),                               # 超标天数：整数
                    stat.get('valid_days'),                                # 有效天数：整数
                    clean_and_round(stat.get('compliance_rate'), 1),        # 达标率：1位小数
                    clean_and_round(stat.get('exceed_rate'), 1)             # 超标率：1位小数
                ]
                cursor.execute(insert_sql, params)

            conn.commit()
            cursor.close()
            conn.close()

            logger.info(
                "province_statistics_new_standard_inserted",
                stat_type=stat_type,
                stat_date=stat_date,
                count=len(statistics)
            )

        except pyodbc.Error as e:
            logger.error(
                "province_statistics_new_standard_insert_error",
                error=str(e),
                sqlstate=e.args[0] if e.args else None
            )
            raise Exception(f"省级新标准统计数据插入失败: {str(e)}")


# =============================================================================
# ProvinceStatisticsFetcher
# =============================================================================

class ProvinceStatisticsFetcher(DataFetcher):
    """省级空气质量统计数据抓取器（新标准限值版本）"""

    def __init__(self):
        super().__init__(
            name="province_statistics_new_standard_fetcher",
            description="省级空气质量统计预计算（新标准限值）",
            schedule="0 8 * * *",  # 每天上午8点
            version="1.0.0"
        )
        self.sql_client = ProvinceSQLServerClient()
        self.city_fetcher = None  # 延迟初始化，避免循环导入

    def _get_city_fetcher(self):
        """延迟初始化CityStatisticsFetcher"""
        if self.city_fetcher is None:
            from app.fetchers.city_statistics.city_statistics_fetcher import CityStatisticsFetcher
            self.city_fetcher = CityStatisticsFetcher()
        return self.city_fetcher

    async def fetch_and_store(self):
        """
        获取并存储省级统计数据（优化版）

        每天计算四种类型：
        1. cumulative_month（月度累计：1-1月、1-2月、...、至上月）- 每天
        2. current_month（当月累计）- 每天
        3. annual_ytd（年度累计）- 每天

        每月1日：将上月current_month转换为monthly
        """
        today = datetime.now().date()

        logger.info("province_statistics_fetcher_started", today=today.isoformat())

        try:
            # 每月1日：将上月的current_month转换为monthly
            if today.day == 1:
                await self._convert_current_to_monthly(today)

            # 每天：更新cumulative_month、current_month和annual_ytd
            await self._calculate_and_store_cumulative_months(today)
            await self._calculate_and_store_current_month(today)
            await self._calculate_and_store_annual_ytd(today)

            logger.info("province_statistics_fetcher_completed", today=today.isoformat())

        except Exception as e:
            logger.error(
                "province_statistics_fetcher_failed",
                today=today.isoformat(),
                error=str(e),
                exc_info=True
            )
            raise

    def _get_last_month_complete(self, today: datetime.date) -> Tuple[str, str, str]:
        """
        获取上月完整月的日期范围

        Args:
            today: 今天日期

        Returns:
            (year_month, start_date, end_date)
        """
        # 上月最后一天
        last_day_of_last_month = today.replace(day=1) - timedelta(days=1)
        # 上月第一天
        first_day_of_last_month = last_day_of_last_month.replace(day=1)

        year_month = first_day_of_last_month.strftime('%Y-%m')
        start_date = first_day_of_last_month.strftime('%Y-%m-%d')
        end_date = last_day_of_last_month.strftime('%Y-%m-%d')

        return year_month, start_date, end_date

    def _group_by_province_enhanced(self, city_data: Dict[str, List[Dict]]) -> Tuple[Dict[str, Dict[str, List[Dict]]], List[str]]:
        """
        将城市数据按省份分组（增强版，带验证）

        数据查询时已通过citycode与bsd_city表关联，直接使用记录中的province_name

        Args:
            city_data: 城市数据字典，每个记录包含province_name字段

        Returns:
            (省份分组数据, 警告信息列表)
        """
        province_groups = {}
        warnings = []

        # 按省份分组（使用数据记录中已关联的省份信息）
        for city_name, records in city_data.items():
            if not records:
                continue

            # 从第一条记录获取省份名称（所有记录应该属于同一省份）
            province = records[0].get('province_name')

            if not province:
                warnings.append(f"城市 '{city_name}' 没有省份信息，已跳过")
                continue

            if province not in province_groups:
                province_groups[province] = {}

            province_groups[province][city_name] = records

            logger.debug(
                "city_assigned_to_province",
                city=city_name,
                province=province,
                records_count=len(records)
            )

        # 记录分组结果
        logger.info(
            "province_grouping_result",
            total_provinces=len(province_groups),
            total_cities=sum(len(cities) for cities in province_groups.values()),
            provinces=list(province_groups.keys())
        )

        return province_groups, warnings

    async def _calculate_and_store_annual_ytd(self, today: datetime.date):
        """
        计算并存储年度累计统计

        Args:
            today: 今天日期
        """
        year = today.year
        start_date = f"{year}-01-01"
        end_date = today.strftime('%Y-%m-%d')

        logger.info(
            "calculating_province_annual_ytd_statistics",
            year=year,
            start_date=start_date,
            end_date=end_date
        )

        # 查询数据（使用所有城市，不限制168城市）
        city_data = self.sql_client.query_all_city_data(start_date, end_date)

        # 按省份分组
        province_groups, grouping_warnings = self._group_by_province_enhanced(city_data)

        # 计算统计
        statistics = []
        for province, cities in province_groups.items():
            stat = calculate_province_statistics(cities)

            if stat:
                stat['province_name'] = province
                statistics.append(stat)

        # 计算排名
        statistics = calculate_province_rankings(statistics)

        # 验证
        stat_date = str(year)  # 格式：2026（年，表示年初至今）
        statistics, validation_warnings = validate_province_statistics(
            city_data, statistics, stat_date
        )

        # 存储数据库
        self.sql_client.insert_province_statistics(statistics, 'year_to_date', stat_date)

        logger.info(
            "province_annual_ytd_statistics_completed",
            year=year,
            provinces_count=len(statistics),
            grouping_warnings=len(grouping_warnings),
            validation_warnings=len(validation_warnings)
        )

    async def _calculate_and_store_current_month(self, today: datetime.date):
        """
        计算并存储当月累计统计

        Args:
            today: 今天日期
        """
        year_month = today.strftime('%Y-%m')
        start_date = f"{year_month}-01"
        end_date = today.strftime('%Y-%m-%d')

        logger.info(
            "calculating_province_current_month_statistics",
            year_month=year_month,
            start_date=start_date,
            end_date=end_date
        )

        # 查询数据（使用所有城市，不限制168城市）
        city_data = self.sql_client.query_all_city_data(start_date, end_date)

        # 按省份分组
        province_groups, grouping_warnings = self._group_by_province_enhanced(city_data)

        # 计算统计
        statistics = []
        for province, cities in province_groups.items():
            stat = calculate_province_statistics(cities)

            if stat:
                stat['province_name'] = province
                statistics.append(stat)

        # 计算排名
        statistics = calculate_province_rankings(statistics)

        # 验证
        stat_date = year_month  # 格式：2026-01（年-月）
        statistics, validation_warnings = validate_province_statistics(
            city_data, statistics, stat_date
        )

        # 存储数据库
        self.sql_client.insert_province_statistics(statistics, 'month_current', stat_date)

        logger.info(
            "province_current_month_statistics_completed",
            year_month=year_month,
            provinces_count=len(statistics),
            grouping_warnings=len(grouping_warnings),
            validation_warnings=len(validation_warnings)
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
        stat_date = year_month  # 格式：2026-01（年-月，表示全月数据）

        logger.info(
            "converting_current_to_monthly",
            year_month=year_month,
            stat_date=stat_date
        )

        try:
            import pyodbc
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
                data_days, sample_coverage, city_count, city_names,
                exceed_days, valid_days, compliance_rate, exceed_rate
            FROM province_statistics_new_standard
            WHERE stat_type = 'month_current' AND stat_date = ?
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

            logger.info(
                "current_month_data_found",
                year_month=year_month,
                provinces_count=len(current_data)
            )

            # 2. 删除已有的monthly数据（如果存在）
            delete_sql = """
            DELETE FROM province_statistics_new_standard
            WHERE stat_type = 'month_complete' AND stat_date = ?
            """
            cursor.execute(delete_sql, [stat_date])

            # 3. 插入monthly数据（使用与insert_province_statistics相同的SQL结构）
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
                exceed_days, valid_days, compliance_rate, exceed_rate,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, GETDATE(), GETDATE())
            """

            for row in current_data:
                params = [
                    stat_date, 'month_complete',
                    row.province_name,
                    row.so2_concentration, row.no2_concentration, row.pm10_concentration, row.pm2_5_concentration,
                    row.co_concentration, row.o3_8h_concentration,
                    row.so2_index, row.no2_index, row.pm10_index, row.pm2_5_index, row.co_index, row.o3_8h_index,
                    row.comprehensive_index, row.comprehensive_index_rank,
                    row.comprehensive_index_new_limit_old_algo, row.comprehensive_index_rank_new_limit_old_algo,
                    'HJ663-2026',
                    row.data_days, row.sample_coverage, row.city_count, row.city_names,
                    row.exceed_days, row.valid_days, row.compliance_rate, row.exceed_rate
                ]
                cursor.execute(insert_sql, params)

            conn.commit()
            cursor.close()
            conn.close()

            logger.info(
                "current_to_monthly_conversion_success",
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

    async def _calculate_and_store_cumulative_months(self, today: datetime.date):
        """
        计算并存储月度累计统计（从年初到各月份的累计）

        例如4月份时，计算并存储：
        - 1月累计（stat_date='2026-01'）
        - 1-2月累计（stat_date='2026-02'）
        - 1-3月累计（stat_date='2026-03'）

        Args:
            today: 今天日期
        """
        year = today.year
        current_month = today.month

        logger.info(
            "calculating_province_cumulative_months_statistics",
            year=year,
            current_month=current_month
        )

        # 如果是1月份，没有累计月份需要计算
        if current_month == 1:
            logger.info("no_cumulative_months_to_calculate", message="1月份无需计算累计")
            return

        # 计算从1月到上个月的每一个累计月份
        for end_month in range(1, current_month):
            # 1月到end_month的累计
            stat_date = f"{year}-{end_month:02d}"  # 格式：2026-01, 2026-02, ...
            start_date = f"{year}-01-01"
            # 最后一天是该月的最后一天
            if end_month == 12:
                end_date = f"{year}-12-31"
            else:
                # 下个月1号减1天
                first_day_next_month = datetime(year, end_month + 1, 1).date()
                last_day_of_month = first_day_next_month - timedelta(days=1)
                end_date = last_day_of_month.strftime('%Y-%m-%d')

            logger.debug(
                "calculating_cumulative_month",
                stat_date=stat_date,
                start_date=start_date,
                end_date=end_date
            )

            # 查询数据
            city_data = self.sql_client.query_all_city_data(start_date, end_date)

            # 按省份分组
            province_groups, grouping_warnings = self._group_by_province_enhanced(city_data)

            # 计算统计
            statistics = []
            for province, cities in province_groups.items():
                stat = calculate_province_statistics(cities)

                if stat:
                    stat['province_name'] = province
                    statistics.append(stat)

            # 计算排名
            statistics = calculate_province_rankings(statistics)

            # 验证
            statistics, validation_warnings = validate_province_statistics(
                city_data, statistics, stat_date
            )

            # 存储数据库（使用cumulative_month类型）
            self.sql_client.insert_province_statistics(statistics, 'ytd_to_month', stat_date)

            logger.debug(
                "cumulative_month_completed",
                stat_date=stat_date,
                provinces_count=len(statistics)
            )

        logger.info(
            "province_cumulative_months_statistics_completed",
            year=year,
            calculated_months=list(range(1, current_month))
        )
