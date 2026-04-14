"""
省级空气质量统计数据抓取器（新标准限值版本）

定时从XcAiDb数据库提取数据，计算31个省级行政区的空气质量评价指标（按HJ663新标准限值），
并将结果缓存回XcAiDb数据库的province_statistics_new_standard表。

核心功能：
- 每天上午8点自动运行
- 计算月度统计、年度累计、当月累计三种统计类型
- 按HJ663新标准限值计算综合指数和单项指数
- 支持多城市数据合并统计
- 自动排名计算

作者：Claude Code
版本：1.0.0
日期：2026-04-09
"""

from typing import List, Dict, Tuple, Optional
from datetime import datetime, timedelta
import structlog
import pyodbc

from app.fetchers.base.fetcher_interface import DataFetcher
from app.fetchers.city_statistics.city_statistics_fetcher import (
    SQLServerClient,
    ALL_168_CITIES,
    safe_round,
    calculate_percentile,
    calculate_statistics,
    WEIGHTS_2026,
    WEIGHTS_2013
)

logger = structlog.get_logger()


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
# 预期城市省份映射表（用于验证）
# =============================================================================

EXPECTED_CITY_PROVINCE_MAP = {
    # 河北省（11个）
    '石家庄': '河北', '唐山': '河北', '秦皇岛': '河北', '邯郸': '河北',
    '邢台': '河北', '保定': '河北', '沧州': '河北', '廊坊': '河北',
    '衡水': '河北', '张家口': '河北', '承德': '河北',
    # 山西省（11个）
    '太原': '山西', '阳泉': '山西', '长治': '山西', '晋城': '山西',
    '晋中': '山西', '运城': '山西', '临汾': '山西', '吕梁': '山西',
    '大同': '山西', '朔州': '山西', '忻州': '山西',
    # 内蒙古自治区（2个）
    '呼和浩特': '内蒙古', '包头': '内蒙古',
    # 辽宁省（5个）
    '沈阳': '辽宁', '大连': '辽宁', '朝阳': '辽宁', '锦州': '辽宁', '葫芦岛': '辽宁',
    # 吉林省（1个）
    '长春': '吉林',
    # 黑龙江省（1个）
    '哈尔滨': '黑龙江',
    # 江苏省（13个）
    '南京': '江苏', '无锡': '江苏', '徐州': '江苏', '常州': '江苏',
    '苏州': '江苏', '南通': '江苏', '连云港': '江苏', '淮安': '江苏',
    '盐城': '江苏', '扬州': '江苏', '镇江': '江苏', '泰州': '江苏', '宿迁': '江苏',
    # 浙江省（11个）
    '杭州': '浙江', '宁波': '浙江', '嘉兴': '浙江', '湖州': '浙江',
    '绍兴': '浙江', '舟山': '浙江', '温州': '浙江', '金华': '浙江',
    '衢州': '浙江', '台州': '浙江', '丽水': '浙江',
    # 安徽省（15个）
    '合肥': '安徽', '芜湖': '安徽', '蚌埠': '安徽', '淮南': '安徽',
    '马鞍山': '安徽', '淮北': '安徽', '滁州': '安徽', '阜阳': '安徽',
    '宿州': '安徽', '六安': '安徽', '亳州': '安徽', '铜陵': '安徽',
    '安庆': '安徽', '黄山': '安徽', '宣城': '安徽', '池州': '安徽',
    # 福建省（2个）
    '福州': '福建', '厦门': '福建',
    # 江西省（5个）
    '南昌': '江西', '萍乡': '江西', '新余': '江西', '宜春': '江西', '九江': '江西',
    # 山东省（14个）
    '济南': '山东', '淄博': '山东', '枣庄': '山东', '东营': '山东',
    '潍坊': '山东', '济宁': '山东', '泰安': '山东', '日照': '山东',
    '临沂': '山东', '德州': '山东', '聊城': '山东', '滨州': '山东',
    '菏泽': '山东', '青岛': '山东',
    # 河南省（17个）
    '郑州': '河南', '开封': '河南', '洛阳': '河南', '平顶山': '河南',
    '安阳': '河南', '鹤壁': '河南', '新乡': '河南', '焦作': '河南',
    '濮阳': '河南', '许昌': '河南', '漯河': '河南', '三门峡': '河南',
    '商丘': '河南', '周口': '河南', '南阳': '河南', '信阳': '河南', '驻马店': '河南',
    # 湖北省（10个）
    '武汉': '湖北', '咸宁': '湖北', '孝感': '湖北', '黄冈': '湖北',
    '黄石': '湖北', '鄂州': '湖北', '襄阳': '湖北', '宜昌': '湖北',
    '荆门': '湖北', '荆州': '湖北', '随州': '湖北',
    # 湖南省（6个）
    '长沙': '湖南', '株洲': '湖南', '湘潭': '湖南', '岳阳': '湖南',
    '常德': '湖南', '益阳': '湖南',
    # 广东省（9个）
    '广州': '广东', '深圳': '广东', '珠海': '广东', '佛山': '广东',
    '江门': '广东', '肇庆': '广东', '惠州': '广东', '东莞': '广东', '中山': '广东',
    # 广西壮族自治区（1个）
    '南宁': '广西',
    # 海南省（1个）
    '海口': '海南',
    # 四川省（14个）
    '成都': '四川', '自贡': '四川', '泸州': '四川', '德阳': '四川',
    '绵阳': '四川', '遂宁': '四川', '内江': '四川', '乐山': '四川',
    '眉山': '四川', '宜宾': '四川', '雅安': '四川', '资阳': '四川',
    '南充': '四川', '广安': '四川', '达州': '四川',
    # 贵州省（1个）
    '贵阳': '贵州',
    # 云南省（1个）
    '昆明': '云南',
    # 西藏自治区（1个）
    '拉萨': '西藏',
    # 陕西省（5个）
    '西安': '陕西', '铜川': '陕西', '宝鸡': '陕西', '咸阳': '陕西', '渭南': '陕西',
    # 甘肃省（1个）
    '兰州': '甘肃',
    # 青海省（1个）
    '西宁': '青海',
    # 宁夏回族自治区（1个）
    '银川': '宁夏',
    # 新疆维吾尔自治区（1个）
    '乌鲁木齐': '新疆',
    # 直辖市（4个）
    '北京': '北京', '天津': '天津', '上海': '上海', '重庆': '重庆'
}

EXPECTED_PROVINCE_CITY_COUNT = {}
for city, province in EXPECTED_CITY_PROVINCE_MAP.items():
    EXPECTED_PROVINCE_CITY_COUNT[province] = EXPECTED_PROVINCE_CITY_COUNT.get(province, 0) + 1


# =============================================================================
# 验证函数
# =============================================================================

def validate_province_mapping(city_data: Dict[str, List[Dict]]) -> List[str]:
    """验证所有城市都能正确映射到省份"""
    warnings = []

    from app.fetchers.city_statistics.city_statistics_fetcher import CityStatisticsFetcher
    city_fetcher = CityStatisticsFetcher()

    for city_name in city_data.keys():
        province = city_fetcher._extract_province(city_name)
        if province == '其他':
            warnings.append(f"城市 '{city_name}' 无法映射到省份")

    return warnings


def validate_city_count(statistics: List[Dict]) -> List[str]:
    """验证每个省份报告的城市数量是否正确"""
    warnings = []

    for stat in statistics:
        province = stat['province_name']
        reported_count = stat.get('city_count', 0)
        expected_count = EXPECTED_PROVINCE_CITY_COUNT.get(province, 0)

        if expected_count > 0 and reported_count != expected_count:
            warnings.append(
                f"{province}: 预期{expected_count}个城市，报告{reported_count}个"
            )

    return warnings


def validate_city_names_field(statistics: List[Dict], city_data: Dict) -> List[str]:
    """验证 city_names 字段是否包含所有城市"""
    warnings = []

    from app.fetchers.city_statistics.city_statistics_fetcher import CityStatisticsFetcher
    city_fetcher = CityStatisticsFetcher()

    for stat in statistics:
        province = stat['province_name']
        reported_cities = set(stat.get('city_names', '').split(','))

        # 从原始数据中提取该省份的实际城市列表
        actual_cities = set()
        for city_name in city_data.keys():
            if city_fetcher._extract_province(city_name) == province:
                actual_cities.add(city_name)

        if reported_cities != actual_cities:
            missing = actual_cities - reported_cities
            if missing:
                warnings.append(
                    f"{province}: city_names缺失 {len(missing)}个城市"
                )

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
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, GETDATE(), GETDATE())
            """

            for stat in statistics:
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
                    stat.get('comprehensive_index'),
                    stat.get('comprehensive_index_rank'),
                    stat.get('comprehensive_index_new_limit_old_algo'),
                    stat.get('comprehensive_index_rank_new_limit_old_algo'),
                    'HJ663-2026',
                    stat.get('data_days'),
                    stat.get('sample_coverage'),
                    stat.get('city_count'),
                    stat.get('city_names')
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

        每天只计算两种类型：
        1. current_month（当月累计）- 每天
        2. annual_ytd（年度累计）- 每天

        每月1日：将上月current_month转换为monthly
        """
        today = datetime.now().date()

        logger.info("province_statistics_fetcher_started", today=today.isoformat())

        try:
            # 每月1日：将上月的current_month转换为monthly
            if today.day == 1:
                await self._convert_current_to_monthly(today)

            # 每天：更新current_month和annual_ytd
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

        Args:
            city_data: 城市数据字典

        Returns:
            (省份分组数据, 警告信息列表)
        """
        province_groups = {}
        warnings = []

        city_fetcher = self._get_city_fetcher()

        for city_name, records in city_data.items():
            if not records:
                continue

            province = city_fetcher._extract_province(city_name)

            if province == '其他':
                warnings.append(f"城市 '{city_name}' 无法映射到省份，已跳过")
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

        # 查询数据
        city_data = self.sql_client.query_city_data(ALL_168_CITIES, start_date, end_date)

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
        stat_date = f"{year}-01-01"
        statistics, validation_warnings = validate_province_statistics(
            city_data, statistics, stat_date
        )

        # 存储数据库
        self.sql_client.insert_province_statistics(statistics, 'annual_ytd', stat_date)

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

        # 查询数据
        city_data = self.sql_client.query_city_data(ALL_168_CITIES, start_date, end_date)

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
        stat_date = f"{year_month}-01"
        statistics, validation_warnings = validate_province_statistics(
            city_data, statistics, stat_date
        )

        # 存储数据库
        self.sql_client.insert_province_statistics(statistics, 'current_month', stat_date)

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
        stat_date = f"{year_month}-01"

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

            logger.info(
                "current_month_data_found",
                year_month=year_month,
                provinces_count=len(current_data)
            )

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
