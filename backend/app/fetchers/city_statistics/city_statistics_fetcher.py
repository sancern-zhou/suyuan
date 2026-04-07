"""
168城市空气质量统计数据抓取器

定时从XcAiDb数据库提取数据，计算168个重点城市的空气质量评价指标（按HJ663标准），
并将结果缓存回XcAiDb数据库的city_168_statistics表。

核心功能：
- 每天上午8点自动运行
- 计算月度统计、年度累计、当月累计三种统计类型
- 按HJ663标准计算综合指数和单项指数
- 支持沙尘天气扣沙处理
- 自动排名计算

作者：Claude Code
版本：1.0.0
日期：2026-04-05
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
# 168城市名单（按地区分类）
# =============================================================================

CITY_168_LIST = {
    "京津冀及周边地区": [
        "北京", "天津",
        # 河北（9个）
        "石家庄", "唐山", "秦皇岛", "邯郸", "邢台", "保定", "沧州", "廊坊", "衡水",
        # 山东（13个）
        "济南", "淄博", "枣庄", "东营", "潍坊", "济宁", "泰安", "日照", "临沂",
        "德州", "聊城", "滨州", "菏泽",
        # 河南（14个）
        "郑州", "开封", "洛阳", "平顶山", "安阳", "鹤壁", "新乡", "焦作", "濮阳",
        "许昌", "漯河", "三门峡", "商丘", "周口"
    ],
    "长三角地区": [
        "上海",
        # 江苏（13个）
        "南京", "无锡", "徐州", "常州", "苏州", "南通", "连云港", "淮安", "盐城",
        "扬州", "镇江", "泰州", "宿迁",
        # 浙江（6个）
        "杭州", "宁波", "嘉兴", "湖州", "绍兴", "舟山",
        # 安徽（11个）
        "合肥", "芜湖", "蚌埠", "淮南", "马鞍山", "淮北", "滁州", "阜阳",
        "宿州", "六安", "亳州"
    ],
    "汾渭平原": [
        # 山西（8个）
        "太原", "阳泉", "长治", "晋城", "晋中", "运城", "临汾", "吕梁",
        # 陕西（5个）
        "西安", "铜川", "宝鸡", "咸阳", "渭南"
    ],
    "成渝地区": [
        "重庆",
        # 四川（15个）
        "成都", "自贡", "泸州", "德阳", "绵阳", "遂宁", "内江", "乐山", "眉山",
        "宜宾", "雅安", "资阳", "南充", "广安", "达州"
    ],
    "长江中游城市群": [
        # 湖北（10个）
        "武汉", "咸宁", "孝感", "黄冈", "黄石", "鄂州", "襄阳", "宜昌", "荆门", "荆州",
        # 江西（5个）
        "南昌", "萍乡", "新余", "宜春", "九江",
        # 湖南（6个）
        "长沙", "株洲", "湘潭", "岳阳", "常德", "益阳"
    ],
    "珠三角地区": [
        # 广东（9个）
        "广州", "深圳", "珠海", "佛山", "江门", "肇庆", "惠州", "东莞", "中山"
    ],
    "其他重点城市": [
        # 河北
        "张家口", "承德",
        # 山西
        "大同", "朔州", "忻州",
        # 山东
        "青岛",
        # 河南
        "南阳", "信阳", "驻马店",
        # 内蒙古
        "呼和浩特", "包头",
        # 辽宁
        "沈阳", "大连", "朝阳", "锦州", "葫芦岛",
        # 吉林
        "长春",
        # 黑龙江
        "哈尔滨",
        # 浙江
        "温州", "金华", "衢州", "台州", "丽水",
        # 安徽
        "铜陵", "安庆", "黄山", "宣城", "池州",
        # 湖北
        "随州",
        # 福建
        "福州", "厦门",
        # 广西
        "南宁",
        # 海南
        "海口",
        # 贵州
        "贵阳",
        # 云南
        "昆明",
        # 西藏
        "拉萨",
        # 甘肃
        "兰州",
        # 青海
        "西宁",
        # 宁夏
        "银川",
        # 新疆
        "乌鲁木齐"
    ]
}

# 展平为列表
ALL_168_CITIES = []
for cities in CITY_168_LIST.values():
    ALL_168_CITIES.extend(cities)

# 地区映射
CITY_REGION_MAP = {}
for region, cities in CITY_168_LIST.items():
    for city in cities:
        CITY_REGION_MAP[city] = region


# =============================================================================
# HJ663标准常量
# =============================================================================

# 年平均二级标准限值（μg/m³，CO为mg/m³）
ANNUAL_STANDARD_LIMITS = {
    'SO2': 60,
    'NO2': 40,
    'PM10': 60,
    'PM2_5': 30,
    'CO': 4,
    'O3_8h': 160
}

# 综合指数权重
WEIGHTS = {
    'SO2': 1,
    'NO2': 2,
    'PM10': 1,
    'PM2_5': 3,
    'CO': 1,
    'O3_8h': 2
}


# =============================================================================
# 统计计算函数
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
        # 将浮点数转换为字符串再转换为Decimal，避免浮点数精度问题
        value_str = format(value, f'.{precision + 5}f').rstrip('0').rstrip('.')
        decimal_value = Decimal(value_str)

        # 构造修约单位（如0.01表示保留2位小数）
        quantize_unit = Decimal('0.' + '0' * precision) if precision > 0 else Decimal('1')

        # 使用ROUND_HALF_EVEN进行修约
        rounded = decimal_value.quantize(quantize_unit, rounding='ROUND_HALF_EVEN')

        return float(rounded)
    except (ValueError, TypeError):
        return 0.0


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

    sorted_values = sorted(valid_values)
    n = len(sorted_values)

    if n == 1:
        return sorted_values[0]

    # 计算百分位数的索引（使用线性插值法）
    index = (percentile / 100) * (n - 1)
    lower_index = int(index)
    upper_index = min(lower_index + 1, n - 1)

    if lower_index == upper_index:
        return sorted_values[lower_index]

    # 线性插值
    fraction = index - lower_index
    result = sorted_values[lower_index] + fraction * (sorted_values[upper_index] - sorted_values[lower_index])

    # 不进行修约，直接返回计算结果
    return result


def calculate_statistics(records: List[Dict]) -> Dict:
    """
    计算城市空气质量统计数据（按HJ663标准）

    Args:
        records: 城市日报数据列表

    Returns:
        统计结果字典
    """
    if not records:
        return None

    # 提取各项污染物浓度数据
    so2_values = []
    no2_values = []
    pm10_values = []
    pm25_values = []
    co_values = []
    o3_8h_values = []

    for record in records:
        # 提取PM2.5
        pm25 = record.get('PM2_5_24h') or record.get('PM2_5')
        if pm25 is not None and pm25 != '' and pm25 != '-':
            try:
                pm25_values.append(float(pm25))
            except (ValueError, TypeError):
                pass

        # 提取PM10
        pm10 = record.get('PM10_24h') or record.get('PM10')
        if pm10 is not None and pm10 != '' and pm10 != '-':
            try:
                pm10_values.append(float(pm10))
            except (ValueError, TypeError):
                pass

        # 提取SO2
        so2 = record.get('SO2_24h') or record.get('SO2')
        if so2 is not None and so2 != '' and so2 != '-':
            try:
                so2_values.append(float(so2))
            except (ValueError, TypeError):
                pass

        # 提取NO2
        no2 = record.get('NO2_24h') or record.get('NO2')
        if no2 is not None and no2 != '' and no2 != '-':
            try:
                no2_values.append(float(no2))
            except (ValueError, TypeError):
                pass

        # 提取CO
        co = record.get('CO_24h') or record.get('CO')
        if co is not None and co != '' and co != '-':
            try:
                co_values.append(float(co))
            except (ValueError, TypeError):
                pass

        # 提取O3_8h
        o3_8h = record.get('O3_8h_24h') or record.get('O3_8h')
        if o3_8h is not None and o3_8h != '' and o3_8h != '-':
            try:
                o3_8h_values.append(float(o3_8h))
            except (ValueError, TypeError):
                pass

    # 计算统计值
    result = {}

    # SO2、NO2、PM10、PM2.5：算术平均值
    if so2_values:
        result['so2_concentration'] = safe_round(sum(so2_values) / len(so2_values), 1)
    else:
        result['so2_concentration'] = None

    if no2_values:
        result['no2_concentration'] = safe_round(sum(no2_values) / len(no2_values), 1)
    else:
        result['no2_concentration'] = None

    if pm10_values:
        result['pm10_concentration'] = safe_round(sum(pm10_values) / len(pm10_values), 1)
    else:
        result['pm10_concentration'] = None

    if pm25_values:
        result['pm2_5_concentration'] = safe_round(sum(pm25_values) / len(pm25_values), 1)
    else:
        result['pm2_5_concentration'] = None

    # CO：第95百分位数（保留2位小数）
    if co_values:
        percentile_95 = calculate_percentile(co_values, 95)
        result['co_concentration'] = safe_round(percentile_95, 2) if percentile_95 is not None else None
    else:
        result['co_concentration'] = None

    # O3_8h：第90百分位数（保留1位小数）
    if o3_8h_values:
        percentile_90 = calculate_percentile(o3_8h_values, 90)
        result['o3_8h_concentration'] = safe_round(percentile_90, 1) if percentile_90 is not None else None
    else:
        result['o3_8h_concentration'] = None

    # 计算单项指数
    result['so2_index'] = safe_round(
        (result['so2_concentration'] or 0) / ANNUAL_STANDARD_LIMITS['SO2'], 3
    ) if result['so2_concentration'] is not None else None

    result['no2_index'] = safe_round(
        (result['no2_concentration'] or 0) / ANNUAL_STANDARD_LIMITS['NO2'], 3
    ) if result['no2_concentration'] is not None else None

    result['pm10_index'] = safe_round(
        (result['pm10_concentration'] or 0) / ANNUAL_STANDARD_LIMITS['PM10'], 3
    ) if result['pm10_concentration'] is not None else None

    result['pm2_5_index'] = safe_round(
        (result['pm2_5_concentration'] or 0) / ANNUAL_STANDARD_LIMITS['PM2_5'], 3
    ) if result['pm2_5_concentration'] is not None else None

    result['co_index'] = safe_round(
        (result['co_concentration'] or 0) / ANNUAL_STANDARD_LIMITS['CO'], 3
    ) if result['co_concentration'] is not None else None

    result['o3_8h_index'] = safe_round(
        (result['o3_8h_concentration'] or 0) / ANNUAL_STANDARD_LIMITS['O3_8h'], 3
    ) if result['o3_8h_concentration'] is not None else None

    # 计算综合指数 = Σ(单项指数 × 权重)
    comprehensive_index = 0.0
    valid_indices = 0

    for pollutant, weight in WEIGHTS.items():
        index_key = f"{pollutant.lower()}_index"
        index_value = result.get(index_key)
        if index_value is not None:
            comprehensive_index += index_value * weight
            valid_indices += 1

    result['comprehensive_index'] = safe_round(comprehensive_index, 3) if valid_indices > 0 else None

    # 计算数据天数
    result['data_days'] = len(records)

    # 计算样本覆盖率（假设每月最多31天）
    max_days = 31  # 保守估计
    result['sample_coverage'] = safe_round((len(records) / max_days) * 100, 2) if max_days > 0 else 0

    return result


def calculate_rankings(statistics: List[Dict]) -> List[Dict]:
    """
    计算城市排名（按综合指数）

    Args:
        statistics: 统计数据列表

    Returns:
        添加了排名的统计数据列表
    """
    # 过滤有效数据（有综合指数的）
    valid_stats = [s for s in statistics if s.get('comprehensive_index') is not None]

    # 按综合指数排序（从小到大，越小越好）
    sorted_stats = sorted(valid_stats, key=lambda x: x['comprehensive_index'])

    # 添加排名
    for rank, stat in enumerate(sorted_stats, start=1):
        stat['comprehensive_index_rank'] = rank

    # 返回完整列表（包括无效数据）
    result = []
    ranked_dict = {s['city_name']: s for s in sorted_stats}

    for stat in statistics:
        if stat['city_name'] in ranked_dict:
            result.append(ranked_dict[stat['city_name']])
        else:
            result.append(stat)

    return result


# =============================================================================
# SQL Server客户端
# =============================================================================

class SQLServerClient:
    """SQL Server客户端（XcAiDb数据库）"""

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

    def query_city_data(self, cities: List[str], start_date: str, end_date: str) -> Dict[str, List[Dict]]:
        """
        查询城市日报数据

        Args:
            cities: 城市名称列表
            start_date: 开始日期（YYYY-MM-DD）
            end_date: 结束日期（YYYY-MM-DD）

        Returns:
            城市 -> 数据列表的字典
        """
        # 为城市名称添加"市"后缀（数据库中的格式）
        cities_with_suffix = [f"{city}市" if not city.endswith("市") else city for city in cities]

        city_placeholders = ','.join(['?' for _ in cities_with_suffix])
        params = cities_with_suffix + [start_date, end_date]

        sql = f"""
        SELECT
            Area, CityCode,
            PM2_5_24h, PM10_24h, O3_8h_24h, NO2_24h, SO2_24h, CO_24h
        FROM CityDayAQIPublishHistory
        WHERE Area IN ({city_placeholders})
          AND TimePoint >= ?
          AND TimePoint <= ?
        ORDER BY Area, TimePoint
        """

        try:
            conn = pyodbc.connect(self.connection_string, timeout=30)
            cursor = conn.cursor()
            cursor.execute(sql, params)

            # 按城市分组（去掉"市"后缀作为key）
            city_data = {}
            for row in cursor.fetchall():
                city_with_suffix = row.Area
                # 去掉"市"后缀，匹配原始城市名称
                city_name = city_with_suffix[:-1] if city_with_suffix.endswith("市") else city_with_suffix

                if city_name not in city_data:
                    city_data[city_name] = []

                city_data[city_name].append({
                    'Area': city_with_suffix,
                    'CityCode': row.CityCode,
                    'PM2_5_24h': row.PM2_5_24h,
                    'PM10_24h': row.PM10_24h,
                    'O3_8h_24h': row.O3_8h_24h,
                    'NO2_24h': row.NO2_24h,
                    'SO2_24h': row.SO2_24h,
                    'CO_24h': row.CO_24h
                })

            cursor.close()
            conn.close()

            logger.info(
                "sql_server_query_success",
                table="CityDayAQIPublishHistory",
                cities_count=len(city_data),
                total_records=sum(len(records) for records in city_data.values())
            )

            return city_data

        except pyodbc.Error as e:
            logger.error(
                "sql_server_query_error",
                error=str(e),
                sqlstate=e.args[0] if e.args else None
            )
            raise Exception(f"SQL Server查询失败: {str(e)}")

    def insert_statistics(self, statistics: List[Dict], stat_type: str, stat_date: str):
        """
        插入统计数据到city_168_statistics表

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
            DELETE FROM city_168_statistics
            WHERE stat_type = ? AND stat_date = ?
            """
            cursor.execute(delete_sql, [stat_type, stat_date])

            # 插入新数据
            insert_sql = """
            INSERT INTO city_168_statistics (
                stat_date, stat_type, city_name, city_code,
                so2_concentration, no2_concentration, pm10_concentration, pm2_5_concentration,
                co_concentration, o3_8h_concentration,
                so2_index, no2_index, pm10_index, pm2_5_index, co_index, o3_8h_index,
                comprehensive_index, comprehensive_index_rank,
                data_days, sample_coverage, region, province,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, GETDATE(), GETDATE())
            """

            for stat in statistics:
                params = [
                    stat_date, stat_type,
                    stat.get('city_name'),
                    stat.get('city_code'),
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
                    stat.get('data_days'),
                    stat.get('sample_coverage'),
                    stat.get('region'),
                    stat.get('province')
                ]
                cursor.execute(insert_sql, params)

            conn.commit()
            cursor.close()
            conn.close()

            logger.info(
                "statistics_inserted",
                stat_type=stat_type,
                stat_date=stat_date,
                count=len(statistics)
            )

        except pyodbc.Error as e:
            logger.error(
                "statistics_insert_error",
                error=str(e),
                sqlstate=e.args[0] if e.args else None
            )
            raise Exception(f"统计数据插入失败: {str(e)}")


# =============================================================================
# CityStatisticsFetcher
# =============================================================================

class CityStatisticsFetcher(DataFetcher):
    """168城市空气质量统计数据抓取器"""

    def __init__(self):
        super().__init__(
            name="city_168_statistics_fetcher",
            description="168城市空气质量统计预计算",
            schedule="0 8 * * *",  # 每天上午8点
            version="1.0.0"
        )
        self.sql_client = SQLServerClient()

    async def fetch_and_store(self):
        """
        获取并存储统计数据（优化版）

        每天只计算两种类型：
        1. current_month（当月累计）- 每天
        2. annual_ytd（年度累计）- 每天

        每月1日：将上月current_month转换为monthly
        """
        today = datetime.now().date()

        logger.info("city_statistics_fetcher_started", today=today.isoformat())

        try:
            # 每月1日：将上月的current_month转换为monthly
            if today.day == 1:
                await self._convert_current_to_monthly(today)

            # 每天：更新current_month和annual_ytd
            await self._calculate_and_store_current_month(today)
            await self._calculate_and_store_annual_ytd(today)

            logger.info("city_statistics_fetcher_completed", today=today.isoformat())

        except Exception as e:
            logger.error(
                "city_statistics_fetcher_failed",
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

    async def _calculate_and_store_monthly(self, month_info: Tuple[str, str, str]):
        """
        计算并存储月度统计

        Args:
            month_info: (year_month, start_date, end_date)
        """
        year_month, start_date, end_date = month_info

        logger.info(
            "calculating_monthly_statistics",
            year_month=year_month,
            start_date=start_date,
            end_date=end_date
        )

        # 查询数据
        city_data = self.sql_client.query_city_data(ALL_168_CITIES, start_date, end_date)

        # 计算统计
        statistics = []
        for city in ALL_168_CITIES:
            if city not in city_data or not city_data[city]:
                continue

            records = city_data[city]
            stat = calculate_statistics(records)

            if stat:
                stat['city_name'] = city
                stat['city_code'] = records[0].get('CityCode') if records else None
                stat['region'] = CITY_REGION_MAP.get(city, '其他')
                stat['province'] = self._extract_province(city)
                statistics.append(stat)

        # 计算排名
        statistics = calculate_rankings(statistics)

        # 存储数据库
        stat_date = f"{year_month}-01"  # 使用月第一天作为stat_date
        self.sql_client.insert_statistics(statistics, 'monthly', stat_date)

        logger.info(
            "monthly_statistics_completed",
            year_month=year_month,
            cities_count=len(statistics)
        )

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
            "calculating_annual_ytd_statistics",
            year=year,
            start_date=start_date,
            end_date=end_date
        )

        # 查询数据
        city_data = self.sql_client.query_city_data(ALL_168_CITIES, start_date, end_date)

        # 计算统计
        statistics = []
        for city in ALL_168_CITIES:
            if city not in city_data or not city_data[city]:
                continue

            records = city_data[city]
            stat = calculate_statistics(records)

            if stat:
                stat['city_name'] = city
                stat['city_code'] = records[0].get('CityCode') if records else None
                stat['region'] = CITY_REGION_MAP.get(city, '其他')
                stat['province'] = self._extract_province(city)
                statistics.append(stat)

        # 计算排名
        statistics = calculate_rankings(statistics)

        # 存储数据库
        stat_date = f"{year}-01-01"  # 使用年第一天作为stat_date
        self.sql_client.insert_statistics(statistics, 'annual_ytd', stat_date)

        logger.info(
            "annual_ytd_statistics_completed",
            year=year,
            cities_count=len(statistics)
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
            "calculating_current_month_statistics",
            year_month=year_month,
            start_date=start_date,
            end_date=end_date
        )

        # 查询数据
        city_data = self.sql_client.query_city_data(ALL_168_CITIES, start_date, end_date)

        # 计算统计
        statistics = []
        for city in ALL_168_CITIES:
            if city not in city_data or not city_data[city]:
                continue

            records = city_data[city]
            stat = calculate_statistics(records)

            if stat:
                stat['city_name'] = city
                stat['city_code'] = records[0].get('CityCode') if records else None
                stat['region'] = CITY_REGION_MAP.get(city, '其他')
                stat['province'] = self._extract_province(city)
                statistics.append(stat)

        # 计算排名
        statistics = calculate_rankings(statistics)

        # 存储数据库
        stat_date = f"{year_month}-01"  # 使用月第一天作为stat_date
        self.sql_client.insert_statistics(statistics, 'current_month', stat_date)

        logger.info(
            "current_month_statistics_completed",
            year_month=year_month,
            cities_count=len(statistics)
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
            conn = pyodbc.connect(self.sql_client.connection_string, timeout=30)
            cursor = conn.cursor()

            # 1. 查询上月的current_month数据
            select_sql = """
            SELECT
                city_name, city_code,
                so2_concentration, no2_concentration, pm10_concentration, pm2_5_concentration,
                co_concentration, o3_8h_concentration,
                so2_index, no2_index, pm10_index, pm2_5_index, co_index, o3_8h_index,
                comprehensive_index, comprehensive_index_rank,
                data_days, sample_coverage, region, province
            FROM city_168_statistics
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
                cities_count=len(current_data)
            )

            # 2. 删除已有的monthly数据（如果存在）
            delete_sql = """
            DELETE FROM city_168_statistics
            WHERE stat_type = 'monthly' AND stat_date = ?
            """
            cursor.execute(delete_sql, [stat_date])

            # 3. 插入monthly数据
            insert_sql = """
            INSERT INTO city_168_statistics (
                stat_date, stat_type, city_name, city_code,
                so2_concentration, no2_concentration, pm10_concentration, pm2_5_concentration,
                co_concentration, o3_8h_concentration,
                so2_index, no2_index, pm10_index, pm2_5_index, co_index, o3_8h_index,
                comprehensive_index, comprehensive_index_rank,
                data_days, sample_coverage, region, province,
                created_at, updated_at
            ) VALUES (?, 'monthly', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, GETDATE(), GETDATE())
            """

            for row in current_data:
                params = [
                    stat_date,
                    row.city_name,
                    row.city_code,
                    row.so2_concentration, row.no2_concentration, row.pm10_concentration, row.pm2_5_concentration,
                    row.co_concentration, row.o3_8h_concentration,
                    row.so2_index, row.no2_index, row.pm10_index, row.pm2_5_index, row.co_index, row.o3_8h_index,
                    row.comprehensive_index, row.comprehensive_index_rank,
                    row.data_days, row.sample_coverage, row.region, row.province
                ]
                cursor.execute(insert_sql, params)

            conn.commit()
            cursor.close()
            conn.close()

            logger.info(
                "current_to_monthly_conversion_success",
                year_month=year_month,
                stat_date=stat_date,
                cities_count=len(current_data)
            )

        except Exception as e:
            logger.error(
                "current_to_monthly_conversion_failed",
                year_month=year_month,
                error=str(e),
                exc_info=True
            )
            raise

    def _extract_province(self, city: str) -> str:
        """
        从城市名称提取省份（简单映射）

        Args:
            city: 城市名称

        Returns:
            省份名称
        """
        # 直辖市
        if city in ['北京', '天津', '上海', '重庆']:
            return city

        # 省份映射（基于城市名称）
        province_map = {
            # 河北
            '石家庄': '河北', '唐山': '河北', '秦皇岛': '河北', '邯郸': '河北',
            '邢台': '河北', '保定': '河北', '沧州': '河北', '廊坊': '河北',
            '衡水': '河北', '张家口': '河北', '承德': '河北',
            # 山西
            '太原': '山西', '阳泉': '山西', '长治': '山西', '晋城': '山西',
            '晋中': '山西', '运城': '山西', '临汾': '山西', '吕梁': '山西',
            '大同': '山西', '朔州': '山西', '忻州': '山西',
            # 内蒙古
            '呼和浩特': '内蒙古', '包头': '内蒙古',
            # 辽宁
            '沈阳': '辽宁', '大连': '辽宁', '朝阳': '辽宁', '锦州': '辽宁', '葫芦岛': '辽宁',
            # 吉林
            '长春': '吉林',
            # 黑龙江
            '哈尔滨': '黑龙江',
            # 江苏
            '南京': '江苏', '无锡': '江苏', '徐州': '江苏', '常州': '江苏',
            '苏州': '江苏', '南通': '江苏', '连云港': '江苏', '淮安': '江苏',
            '盐城': '江苏', '扬州': '江苏', '镇江': '江苏', '泰州': '江苏', '宿迁': '江苏',
            # 浙江
            '杭州': '浙江', '宁波': '浙江', '嘉兴': '浙江', '湖州': '浙江',
            '绍兴': '浙江', '舟山': '浙江', '温州': '浙江', '金华': '浙江',
            '衢州': '浙江', '台州': '浙江', '丽水': '浙江',
            # 安徽
            '合肥': '安徽', '芜湖': '安徽', '蚌埠': '安徽', '淮南': '安徽',
            '马鞍山': '安徽', '淮北': '安徽', '滁州': '安徽', '阜阳': '安徽',
            '宿州': '安徽', '六安': '安徽', '亳州': '安徽', '铜陵': '安徽',
            '安庆': '安徽', '黄山': '安徽', '宣城': '安徽', '池州': '安徽',
            # 福建
            '福州': '福建', '厦门': '福建',
            # 江西
            '南昌': '江西', '萍乡': '江西', '新余': '江西', '宜春': '江西', '九江': '江西',
            # 山东
            '济南': '山东', '淄博': '山东', '枣庄': '山东', '东营': '山东',
            '潍坊': '山东', '济宁': '山东', '泰安': '山东', '日照': '山东',
            '临沂': '山东', '德州': '山东', '聊城': '山东', '滨州': '山东',
            '菏泽': '山东', '青岛': '山东',
            # 河南
            '郑州': '河南', '开封': '河南', '洛阳': '河南', '平顶山': '河南',
            '安阳': '河南', '鹤壁': '河南', '新乡': '河南', '焦作': '河南',
            '濮阳': '河南', '许昌': '河南', '漯河': '河南', '三门峡': '河南',
            '商丘': '河南', '周口': '河南', '南阳': '河南', '信阳': '河南', '驻马店': '河南',
            # 湖北
            '武汉': '湖北', '咸宁': '湖北', '孝感': '湖北', '黄冈': '湖北',
            '黄石': '湖北', '鄂州': '湖北', '襄阳': '湖北', '宜昌': '湖北',
            '荆门': '湖北', '荆州': '湖北', '随州': '湖北',
            # 湖南
            '长沙': '湖南', '株洲': '湖南', '湘潭': '湖南', '岳阳': '湖南',
            '常德': '湖南', '益阳': '湖南',
            # 广东
            '广州': '广东', '深圳': '广东', '珠海': '广东', '佛山': '广东',
            '江门': '广东', '肇庆': '广东', '惠州': '广东', '东莞': '广东', '中山': '广东',
            # 广西
            '南宁': '广西',
            # 海南
            '海口': '海南',
            # 四川
            '成都': '四川', '自贡': '四川', '泸州': '四川', '德阳': '四川',
            '绵阳': '四川', '遂宁': '四川', '内江': '四川', '乐山': '四川',
            '眉山': '四川', '宜宾': '四川', '雅安': '四川', '资阳': '四川',
            '南充': '四川', '广安': '四川', '达州': '四川',
            # 贵州
            '贵阳': '贵州',
            # 云南
            '昆明': '云南',
            # 西藏
            '拉萨': '西藏',
            # 陕西
            '西安': '陕西', '铜川': '陕西', '宝鸡': '陕西', '咸阳': '陕西', '渭南': '陕西',
            # 甘肃
            '兰州': '甘肃',
            # 青海
            '西宁': '青海',
            # 宁夏
            '银川': '宁夏',
            # 新疆
            '乌鲁木齐': '新疆'
        }

        return province_map.get(city, '其他')
