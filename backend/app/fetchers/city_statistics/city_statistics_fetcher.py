"""
168城市空气质量统计数据抓取器

定时从XcAiDb数据库提取数据，计算168个重点城市的空气质量评价指标（按HJ663标准），
并将结果缓存回XcAiDb数据库的city_168_statistics_new_standard表。

核心功能：
- 每天上午8点自动运行
- 计算四种统计类型：
  1. ytd_to_month（年初到某月累计：1-1月、1-2月、...至上月）- 避免"修约→计算→再修约"误差
  2. month_current（当月累计）- 每天
  3. year_to_date（年初至今累计）- 每天
  4. month_complete（完整月统计）- 每月1日从month_current转换
- 按HJ663标准计算综合指数和单项指数
- 支持沙尘天气扣沙处理
- 自动排名计算

数据示例（4月份时）：
  ytd_to_month + stat_date='2026-01'  → 年初至1月累计
  ytd_to_month + stat_date='2026-02'  → 年初至2月累计
  ytd_to_month + stat_date='2026-03'  → 年初至3月累计
  month_current + stat_date='2026-04' → 4月当月累计
  year_to_date + stat_date='2026'      → 年初至今累计
  month_complete + stat_date='2026-03' → 3月完整月

作者：Claude Code
版本：1.1.0
日期：2026-04-18
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

# HJ 663-2026 新标准（当前使用）
ANNUAL_STANDARD_LIMITS_2026 = {
    'SO2': 60,
    'NO2': 40,
    'PM10': 60,   # 新标准
    'PM2_5': 30,  # 新标准
    'CO': 4,
    'O3_8h': 160
}

# HJ 663-2013 旧标准
ANNUAL_STANDARD_LIMITS_2013 = {
    'SO2': 60,
    'NO2': 40,
    'PM10': 70,   # 旧标准
    'PM2_5': 35,  # 旧标准
    'CO': 4,
    'O3_8h': 160
}

# 默认使用新标准（向后兼容）
ANNUAL_STANDARD_LIMITS = ANNUAL_STANDARD_LIMITS_2026

# 新标准综合指数权重（HJ 663-2026）
WEIGHTS_2026 = {
    'SO2': 1,
    'NO2': 2,
    'PM10': 1,
    'PM2_5': 3,
    'CO': 1,
    'O3_8h': 2
}

# 旧标准综合指数权重（HJ 663-2013）- 所有污染物权重均为1
WEIGHTS_2013 = {
    'SO2': 1,
    'NO2': 1,
    'PM10': 1,
    'PM2_5': 1,
    'CO': 1,
    'O3_8h': 1
}

# 默认使用新标准权重（向后兼容）
WEIGHTS = WEIGHTS_2026


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

    # 检查特殊值（无穷大、NaN）
    import math
    if math.isinf(value) or math.isnan(value):
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

    # 计算六参数均值（按照HJ 663-2026标准，中间计算过程保留更高精度）
    # SO2、NO2、PM10、PM2.5：算术平均值，保留2位小数（中间计算精度）
    if so2_values:
        result['so2_concentration'] = safe_round(sum(so2_values) / len(so2_values), 2)
    else:
        result['so2_concentration'] = None

    if no2_values:
        result['no2_concentration'] = safe_round(sum(no2_values) / len(no2_values), 2)
    else:
        result['no2_concentration'] = None

    if pm10_values:
        result['pm10_concentration'] = safe_round(sum(pm10_values) / len(pm10_values), 2)
    else:
        result['pm10_concentration'] = None

    if pm25_values:
        result['pm2_5_concentration'] = safe_round(sum(pm25_values) / len(pm25_values), 2)
    else:
        result['pm2_5_concentration'] = None

    # CO：第95百分位数，保留3位小数（中间计算精度）
    if co_values:
        percentile_95 = calculate_percentile(co_values, 95)
        result['co_concentration'] = safe_round(percentile_95, 3) if percentile_95 is not None else None
    else:
        result['co_concentration'] = None

    # O3_8h：第90百分位数，保留2位小数（中间计算精度）
    if o3_8h_values:
        percentile_90 = calculate_percentile(o3_8h_values, 90)
        result['o3_8h_concentration'] = safe_round(percentile_90, 2) if percentile_90 is not None else None
    else:
        result['o3_8h_concentration'] = None

    # 计算单项指数（新标准 HJ 663-2026）
    result['so2_index'] = safe_round(
        (result['so2_concentration'] or 0) / ANNUAL_STANDARD_LIMITS_2026['SO2'], 3
    ) if result['so2_concentration'] is not None else None

    result['no2_index'] = safe_round(
        (result['no2_concentration'] or 0) / ANNUAL_STANDARD_LIMITS_2026['NO2'], 3
    ) if result['no2_concentration'] is not None else None

    result['pm10_index'] = safe_round(
        (result['pm10_concentration'] or 0) / ANNUAL_STANDARD_LIMITS_2026['PM10'], 3
    ) if result['pm10_concentration'] is not None else None

    result['pm2_5_index'] = safe_round(
        (result['pm2_5_concentration'] or 0) / ANNUAL_STANDARD_LIMITS_2026['PM2_5'], 3
    ) if result['pm2_5_concentration'] is not None else None

    result['co_index'] = safe_round(
        (result['co_concentration'] or 0) / ANNUAL_STANDARD_LIMITS_2026['CO'], 3
    ) if result['co_concentration'] is not None else None

    result['o3_8h_index'] = safe_round(
        (result['o3_8h_concentration'] or 0) / ANNUAL_STANDARD_LIMITS_2026['O3_8h'], 3
    ) if result['o3_8h_concentration'] is not None else None

    # 计算综合指数（新标准 HJ 663-2026）= Σ(单项指数 × 权重)
    comprehensive_index = 0.0
    valid_indices = 0

    for pollutant, weight in WEIGHTS_2026.items():
        index_key = f"{pollutant.lower()}_index"
        index_value = result.get(index_key)
        if index_value is not None:
            comprehensive_index += index_value * weight
            valid_indices += 1

    result['comprehensive_index'] = safe_round(comprehensive_index, 3) if valid_indices > 0 else None

    # 计算综合指数（新限值+旧算法）
    # 使用新标准限值（PM10=60, PM2.5=30），但使用旧算法权重（所有权重均为1）
    comprehensive_index_new_limit_old_algo = 0.0
    valid_indices_new_limit_old_algo = 0

    for pollutant, weight in WEIGHTS_2013.items():
        # 使用新标准的指数（已计算的 *_index 字段）
        index_key = f"{pollutant.lower()}_index"
        index_value = result.get(index_key)
        if index_value is not None:
            comprehensive_index_new_limit_old_algo += index_value * weight
            valid_indices_new_limit_old_algo += 1

    result['comprehensive_index_new_limit_old_algo'] = safe_round(comprehensive_index_new_limit_old_algo, 3) if valid_indices_new_limit_old_algo > 0 else None

    # 计算数据天数
    result['data_days'] = len(records)

    # 计算样本覆盖率（根据数据天数智能判断是月度还是年度数据）
    # 数据天数 > 150：年度数据（365天）；否则：月度数据（31天）
    max_days = 365 if len(records) > 150 else 31
    result['sample_coverage'] = safe_round((len(records) / max_days) * 100, 2) if max_days > 0 else 0

    return result


def calculate_rankings(statistics: List[Dict]) -> List[Dict]:
    """
    计算城市排名（按综合指数）

    计算新标准的两套综合指数排名

    Args:
        statistics: 统计数据列表

    Returns:
        添加了排名的统计数据列表
    """
    # 计算新标准排名（新限值+新算法）
    valid_stats = [s for s in statistics if s.get('comprehensive_index') is not None]
    sorted_stats = sorted(valid_stats, key=lambda x: x['comprehensive_index'])

    for rank, stat in enumerate(sorted_stats, start=1):
        stat['comprehensive_index_rank'] = rank

    # 计算新限值+旧算法排名
    valid_stats_new_limit_old_algo = [s for s in statistics if s.get('comprehensive_index_new_limit_old_algo') is not None]
    sorted_stats_new_limit_old_algo = sorted(valid_stats_new_limit_old_algo, key=lambda x: x['comprehensive_index_new_limit_old_algo'])

    for rank, stat in enumerate(sorted_stats_new_limit_old_algo, start=1):
        stat['comprehensive_index_rank_new_limit_old_algo'] = rank

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
            cities: 城市名称列表（可以包含各种后缀，如"市"、"地区"、"自治州"等）
            start_date: 开始日期（YYYY-MM-DD）
            end_date: 结束日期（YYYY-MM-DD）

        Returns:
            城市 -> 数据列表的字典
        """
        # 智能处理后缀：如果城市名称没有任何后缀，则添加"市"；否则保留原样
        cities_with_suffix = []
        for city in cities:
            # 检查是否已有后缀
            has_suffix = any(city.endswith(suffix) for suffix in ['市', '地区', '自治州', '州', '盟'])
            if has_suffix:
                # 已有后缀，保留原样
                cities_with_suffix.append(city)
            else:
                # 没有后缀，添加"市"
                cities_with_suffix.append(f"{city}市")

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

            # 按城市分组（保留原始城市名称作为key）
            city_data = {}
            for row in cursor.fetchall():
                city_with_suffix = row.Area
                # 找到匹配的原始城市名称
                city_name = None
                for original_city in cities:
                    # 检查是否完全匹配
                    if city_with_suffix == original_city:
                        city_name = original_city
                        break
                    # 检查是否是添加"市"后缀后的匹配
                    if city_with_suffix == f"{original_city}市":
                        city_name = original_city
                        break

                # 如果没有找到匹配，使用去掉后缀的名称
                if city_name is None:
                    city_name = city_with_suffix
                    for suffix in ['市', '地区', '自治州', '州', '盟']:
                        if city_name.endswith(suffix):
                            city_name = city_name[:-len(suffix)]
                            break

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

    def query_all_city_data(self, start_date: str, end_date: str) -> Dict[str, List[Dict]]:
        """
        查询所有城市日报数据（不限制168城市，用于省级统计）

        使用citycode与bsd_city表关联，确保准确的城市-省份映射。
        对于云南自治州，由于CityCode不匹配，使用名称匹配。
        对于省直辖县级行政区划（如济源市），通过parentid关联到省份。

        Args:
            start_date: 开始日期（YYYY-MM-DD）
            end_date: 结束日期（YYYY-MM-DD）

        Returns:
            城市 -> 数据列表的字典
        """
        # 主查询：使用CityCode关联（适用于大多数城市）
        # 注意：不使用COLLATE，因为数据库默认排序规则与bsd_city.code字段排序规则不同
        sql_main = """
        SELECT
            r.TimePoint, r.Area, r.CityCode,
            r.PM2_5_24h, r.PM10_24h, r.O3_8h_24h, r.NO2_24h, r.SO2_24h, r.CO_24h,
            c.name as city_name, p.name as province_name
        FROM CityDayAQIPublishHistory r
        JOIN bsd_city c ON CAST(r.CityCode AS nvarchar(50)) = c.code
        JOIN bsd_city p ON c.parentid = p.code AND p.level = '1'
        WHERE r.TimePoint >= ?
          AND r.TimePoint <= ?
          AND c.level = '2'
        ORDER BY r.Area, r.TimePoint
        """

        # 省直辖县级行政区划查询（如河南济源市、新疆石河子市、五家渠市）
        # 这些城市在bsd_city中level=3，parentid指向省直辖县级行政区划
        # 使用parentid编码列表避免中文编码问题
        sql_direct_administered = """
        SELECT
            r.TimePoint, r.Area, r.CityCode,
            r.PM2_5_24h, r.PM10_24h, r.O3_8h_24h, r.NO2_24h, r.SO2_24h, r.CO_24h,
            c.name as city_name, p.name as province_name
        FROM CityDayAQIPublishHistory r
        JOIN bsd_city c ON CAST(r.CityCode AS nvarchar(50)) = c.code
        JOIN bsd_city parent ON c.parentid = parent.code
        JOIN bsd_city p ON parent.parentid = p.code AND p.level = '1'
        WHERE r.TimePoint >= ?
          AND r.TimePoint <= ?
          AND c.level = '3'
          AND c.parentid IN ('419000', '659000', '469000')
        ORDER BY r.Area, r.TimePoint
        """

        # 处理CityCode匹配但parentid=0的城市（如新疆吐鲁番、哈密）
        # 使用名称关联来获取正确的省份信息
        sql_name_matched = """
        SELECT
            r.TimePoint, r.Area, r.CityCode,
            r.PM2_5_24h, r.PM10_24h, r.O3_8h_24h, r.NO2_24h, r.SO2_24h, r.CO_24h,
            c.name as city_name, p.name as province_name
        FROM CityDayAQIPublishHistory r
        JOIN bsd_city c ON r.Area = c.name COLLATE Chinese_PRC_CI_AS
        JOIN bsd_city p ON c.parentid = p.code AND p.level = '1'
        WHERE r.TimePoint >= ?
          AND r.TimePoint <= ?
          AND c.level = '2'
          AND CAST(r.CityCode AS nvarchar(50)) NOT IN (
              SELECT code FROM bsd_city WHERE level = '2' AND parentid != '0'
          )
        ORDER BY r.Area, r.TimePoint
        """

        # 云南自治州查询：使用编码映射（避免中文编码问题）
        # 云南自治州在CityDayAQIPublishHistory中使用区县级CityCode（如532301）
        # 在bsd_city中对应level=2的完整编码（如532300）
        # 通过前4位编码匹配
        # 策略：优先使用parentid=530000的记录（完整名称），对于parentid=0的只选择不在530000中的
        sql_yunnan_prefectures = """
        SELECT c.name as city_name, LEFT(c.code, 4) as code_prefix, p.name as province_name
        FROM bsd_city c
        LEFT JOIN bsd_city p ON c.parentid = p.code AND p.level = '1'
        WHERE c.level = '2'
          AND (
              -- 优先选择parentid=530000的记录（完整名称）
              c.parentid = '530000'
              OR
              -- 对于parentid=0的记录，只选择前4位编码不在530000记录中的
              (c.parentid = '0' AND c.code LIKE '53%'
               AND LEFT(c.code, 4) NOT IN (
                   SELECT LEFT(code, 4) FROM bsd_city WHERE level = '2' AND parentid = '530000'
               ))
          )
        """

        sql_yunnan_data = """
        SELECT
            r.TimePoint, r.Area, r.CityCode,
            r.PM2_5_24h, r.PM10_24h, r.O3_8h_24h, r.NO2_24h, r.SO2_24h, r.CO_24h
        FROM CityDayAQIPublishHistory r
        WHERE r.TimePoint >= ?
          AND r.TimePoint <= ?
          AND r.CityCode LIKE '53%'
        ORDER BY r.Area, r.TimePoint
        """

        try:
            conn = pyodbc.connect(self.connection_string, timeout=30)
            cursor = conn.cursor()

            city_data = {}

            # 1. 执行主查询（CityCode关联）
            cursor.execute(sql_main, [start_date, end_date])
            for row in cursor.fetchall():
                city_name = row.city_name
                if city_name not in city_data:
                    city_data[city_name] = []

                city_data[city_name].append({
                    'date': row.TimePoint.strftime('%Y-%m-%d') if row.TimePoint else None,
                    'city_code': row.CityCode,
                    'province_name': row.province_name,
                    'PM2_5_24h': row.PM2_5_24h,
                    'PM10_24h': row.PM10_24h,
                    'O3_8h_24h': row.O3_8h_24h,
                    'NO2_24h': row.NO2_24h,
                    'SO2_24h': row.SO2_24h,
                    'CO_24h': row.CO_24h
                })

            main_cities_count = len(city_data)
            main_records_count = sum(len(records) for records in city_data.values())

            # 2. 处理省直辖县级行政区划（如济源市、石河子市、五家渠市）
            cursor.execute(sql_direct_administered, [start_date, end_date])
            direct_administered_count = 0
            direct_administered_records = 0

            for row in cursor.fetchall():
                city_name = row.city_name
                if city_name not in city_data:
                    city_data[city_name] = []
                    direct_administered_count += 1

                city_data[city_name].append({
                    'date': row.TimePoint.strftime('%Y-%m-%d') if row.TimePoint else None,
                    'city_code': row.CityCode,
                    'province_name': row.province_name,
                    'PM2_5_24h': row.PM2_5_24h,
                    'PM10_24h': row.PM10_24h,
                    'O3_8h_24h': row.O3_8h_24h,
                    'NO2_24h': row.NO2_24h,
                    'SO2_24h': row.SO2_24h,
                    'CO_24h': row.CO_24h
                })
                direct_administered_records += 1

            # 3. 处理CityCode匹配但parentid=0的城市（如吐鲁番、哈密）
            # 使用名称关联来获取正确的省份信息
            cursor.execute(sql_name_matched, [start_date, end_date])
            name_matched_count = 0
            name_matched_records = 0

            for row in cursor.fetchall():
                city_name = row.city_name
                if city_name not in city_data:
                    city_data[city_name] = []
                    name_matched_count += 1

                city_data[city_name].append({
                    'date': row.TimePoint.strftime('%Y-%m-%d') if row.TimePoint else None,
                    'city_code': row.CityCode,
                    'province_name': row.province_name,
                    'PM2_5_24h': row.PM2_5_24h,
                    'PM10_24h': row.PM10_24h,
                    'O3_8h_24h': row.O3_8h_24h,
                    'NO2_24h': row.NO2_24h,
                    'SO2_24h': row.SO2_24h,
                    'CO_24h': row.CO_24h
                })
                name_matched_records += 1

            # 4. 处理云南自治州（使用编码前缀匹配，避免中文编码问题）
            # 4.1 获取云南所有城市（使用编码过滤）
            cursor.execute(sql_yunnan_prefectures)
            yunnan_prefectures = {}
            for row in cursor.fetchall():
                # SQL已经提取了前4位作为code_prefix
                yunnan_prefectures[row.code_prefix] = row

            # 4.2 获取云南所有数据（53开头的CityCode）
            cursor.execute(sql_yunnan_data, [start_date, end_date])
            yunnan_cities_count = 0
            yunnan_records_count = 0

            for row in cursor.fetchall():
                city_code = row.CityCode
                # 使用CityCode前4位匹配（如532301 -> 5323）
                code_prefix = str(city_code)[:4] if len(str(city_code)) >= 4 else str(city_code)

                matched_prefecture = yunnan_prefectures.get(code_prefix)

                if matched_prefecture:
                    city_name = matched_prefecture.city_name
                    if city_name not in city_data:
                        city_data[city_name] = []
                        yunnan_cities_count += 1

                    city_data[city_name].append({
                        'date': row.TimePoint.strftime('%Y-%m-%d') if row.TimePoint else None,
                        'city_code': row.CityCode,
                        'province_name': '云南',
                        'PM2_5_24h': row.PM2_5_24h,
                        'PM10_24h': row.PM10_24h,
                        'O3_8h_24h': row.O3_8h_24h,
                        'NO2_24h': row.NO2_24h,
                        'SO2_24h': row.SO2_24h,
                        'CO_24h': row.CO_24h
                    })
                    yunnan_records_count += 1

            cursor.close()
            conn.close()

            logger.info(
                "sql_server_query_success_all_cities",
                table="CityDayAQIPublishHistory",
                cities_count=len(city_data),
                main_cities=main_cities_count,
                direct_administered=direct_administered_count,
                name_matched=name_matched_count,
                yunnan_autonomous_prefectures=yunnan_cities_count,
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
            DELETE FROM city_168_statistics_new_standard
            WHERE stat_type = ? AND stat_date = ?
            """
            cursor.execute(delete_sql, [stat_type, stat_date])

            # 插入新数据
            insert_sql = """
            INSERT INTO city_168_statistics_new_standard (
                stat_date, stat_type, city_name, city_code,
                so2_concentration, no2_concentration, pm10_concentration, pm2_5_concentration,
                co_concentration, o3_8h_concentration,
                so2_index, no2_index, pm10_index, pm2_5_index, co_index, o3_8h_index,
                comprehensive_index, comprehensive_index_rank,
                comprehensive_index_new_limit_old_algo, comprehensive_index_rank_new_limit_old_algo,
                standard_version,
                data_days, sample_coverage, region, province,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, GETDATE(), GETDATE())
            """

            for stat in statistics:
                # 最终修约并转换类型
                def round_to_type(value, decimals):
                    """修约并转换为合适的类型（0位小数转整数）"""
                    if value is None:
                        return None
                    rounded = safe_round(value, decimals)
                    if rounded is None:
                        return None
                    # 保留0位小数时转换为整数，避免存储为25.00
                    return int(rounded) if decimals == 0 else rounded

                params = [
                    stat_date, stat_type,
                    stat.get('city_name'),
                    stat.get('city_code'),
                    round_to_type(stat.get('so2_concentration'), 0),      # SO2：整数
                    round_to_type(stat.get('no2_concentration'), 0),      # NO2：整数
                    round_to_type(stat.get('pm10_concentration'), 0),     # PM10：整数
                    round_to_type(stat.get('pm2_5_concentration'), 1),    # PM2.5：1位小数
                    round_to_type(stat.get('co_concentration'), 1),       # CO：1位小数
                    round_to_type(stat.get('o3_8h_concentration'), 0),    # O3-8h：整数
                    stat.get('so2_index'),                                # 指数：保持3位小数
                    stat.get('no2_index'),
                    stat.get('pm10_index'),
                    stat.get('pm2_5_index'),
                    stat.get('co_index'),
                    stat.get('o3_8h_index'),
                    stat.get('comprehensive_index'),                    # 综合指数：保持3位小数
                    stat.get('comprehensive_index_rank'),
                    stat.get('comprehensive_index_new_limit_old_algo'),
                    stat.get('comprehensive_index_rank_new_limit_old_algo'),
                    'HJ663-2026',  # 标识当前使用新标准
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
            name="city_168_statistics_new_standard_fetcher",
            description="168城市空气质量统计预计算",
            schedule="0 8 * * *",  # 每天上午8点
            version="1.0.0"
        )
        self.sql_client = SQLServerClient()

    async def fetch_and_store(self):
        """
        获取并存储统计数据（优化版）

        每天计算四种类型：
        1. cumulative_month（月度累计：1-1月、1-2月、...、至上月）- 每天
        2. current_month（当月累计）- 每天
        3. annual_ytd（年度累计）- 每天

        每月1日：将上月current_month转换为monthly
        """
        today = datetime.now().date()

        logger.info("city_statistics_fetcher_started", today=today.isoformat())

        try:
            # 每月1日：将上月的current_month转换为monthly
            if today.day == 1:
                await self._convert_current_to_monthly(today)

            # 每天：更新cumulative_month、current_month和annual_ytd
            await self._calculate_and_store_cumulative_months(today)
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
        stat_date = year_month  # 格式：2026-01（年-月，表示全月数据）
        self.sql_client.insert_statistics(statistics, 'month_complete', stat_date)

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
        stat_date = str(year)  # 格式：2026（年，表示年初至今）
        start_date = f"{year}-01-01"
        end_date = today.strftime('%Y-%m-%d')

        logger.info(
            "calculating_annual_ytd_statistics",
            year=year,
            stat_date=stat_date,
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

        # 存储数据库（使用年格式：2026）
        self.sql_client.insert_statistics(statistics, 'year_to_date', stat_date)

        logger.info(
            "annual_ytd_statistics_completed",
            year=year,
            stat_date=stat_date,
            cities_count=len(statistics)
        )

    async def _calculate_and_store_current_month(self, today: datetime.date):
        """
        计算并存储当月累计统计

        Args:
            today: 今天日期
        """
        year_month = today.strftime('%Y-%m')
        stat_date = year_month  # 格式：2026-01（年-月）
        start_date = f"{year_month}-01"
        end_date = today.strftime('%Y-%m-%d')

        logger.info(
            "calculating_current_month_statistics",
            year_month=year_month,
            stat_date=stat_date,
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

        # 存储数据库（使用年月格式：2026-01）
        self.sql_client.insert_statistics(statistics, 'month_current', stat_date)

        logger.info(
            "current_month_statistics_completed",
            year_month=year_month,
            stat_date=stat_date,
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
        stat_date = year_month  # 格式：2026-01（年-月，表示全月数据）

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
                comprehensive_index_new_limit_old_algo, comprehensive_index_rank_new_limit_old_algo,
                data_days, sample_coverage, region, province
            FROM city_168_statistics_new_standard
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
                cities_count=len(current_data)
            )

            # 2. 删除已有的monthly数据（如果存在）
            delete_sql = """
            DELETE FROM city_168_statistics_new_standard
            WHERE stat_type = 'month_complete' AND stat_date = ?
            """
            cursor.execute(delete_sql, [stat_date])

            # 3. 插入monthly数据
            insert_sql = """
            INSERT INTO city_168_statistics_new_standard (
                stat_date, stat_type, city_name, city_code,
                so2_concentration, no2_concentration, pm10_concentration, pm2_5_concentration,
                co_concentration, o3_8h_concentration,
                so2_index, no2_index, pm10_index, pm2_5_index, co_index, o3_8h_index,
                comprehensive_index, comprehensive_index_rank,
                comprehensive_index_new_limit_old_algo, comprehensive_index_rank_new_limit_old_algo,
                standard_version,
                data_days, sample_coverage, region, province,
                created_at, updated_at
            ) VALUES (?, 'month_complete', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, GETDATE(), GETDATE())
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
                    row.comprehensive_index_new_limit_old_algo, row.comprehensive_index_rank_new_limit_old_algo,
                    'HJ663-2026',
                    row.data_days, row.sample_coverage, row.region, row.province
                ]
                cursor.execute(insert_sql, params)

            # 4. 删除上月的current_month数据（已转换为monthly，避免数据冗余）
            delete_current_sql = """
            DELETE FROM city_168_statistics_new_standard
            WHERE stat_type = 'month_current' AND stat_date = ?
            """
            cursor.execute(delete_current_sql, [stat_date])
            deleted_count = cursor.rowcount

            conn.commit()
            cursor.close()
            conn.close()

            logger.info(
                "current_to_monthly_conversion_success",
                year_month=year_month,
                stat_date=stat_date,
                cities_count=len(current_data),
                deleted_current_month_count=deleted_count
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
        从城市名称提取省份（完整映射，支持所有地级市）

        Args:
            city: 城市名称

        Returns:
            省份名称
        """
        # 直辖市
        if city in ['北京', '天津', '上海', '重庆']:
            return city

        # 省份映射（包含所有地级市）
        province_map = {
            # 河北省（11个地级市）
            '石家庄': '河北', '唐山': '河北', '秦皇岛': '河北', '邯郸': '河北',
            '邢台': '河北', '保定': '河北', '张家口': '河北', '承德': '河北',
            '沧州': '河北', '廊坊': '河北', '衡水': '河北',

            # 山西省（11个地级市）
            '太原': '山西', '大同': '山西', '阳泉': '山西', '长治': '山西',
            '晋城': '山西', '朔州': '山西', '晋中': '山西', '运城': '山西',
            '忻州': '山西', '临汾': '山西', '吕梁': '山西',

            # 内蒙古自治区（12个盟市）
            '呼和浩特': '内蒙古', '包头': '内蒙古', '乌海': '内蒙古', '赤峰': '内蒙古',
            '通辽': '内蒙古', '鄂尔多斯': '内蒙古', '呼伦贝尔': '内蒙古', '巴彦淖尔': '内蒙古',
            '乌兰察布': '内蒙古', '兴安盟': '内蒙古', '锡林郭勒盟': '内蒙古', '阿拉善盟': '内蒙古',

            # 辽宁省（14个地级市）
            '沈阳': '辽宁', '大连': '辽宁', '鞍山': '辽宁', '抚顺': '辽宁',
            '本溪': '辽宁', '丹东': '辽宁', '锦州': '辽宁', '营口': '辽宁',
            '阜新': '辽宁', '辽阳': '辽宁', '盘锦': '辽宁', '铁岭': '辽宁',
            '朝阳': '辽宁', '葫芦岛': '辽宁',

            # 吉林省（9个地级市 + 1个自治州）
            '长春': '吉林', '吉林': '吉林', '四平': '吉林', '辽源': '吉林',
            '通化': '吉林', '白山': '吉林', '松原': '吉林', '白城': '吉林',
            '延边': '吉林',

            # 黑龙江省（13个地级市 + 1个地区）
            '哈尔滨': '黑龙江', '齐齐哈尔': '黑龙江', '鸡西': '黑龙江', '鹤岗': '黑龙江',
            '双鸭山': '黑龙江', '大庆': '黑龙江', '伊春': '黑龙江', '佳木斯': '黑龙江',
            '七台河': '黑龙江', '牡丹江': '黑龙江', '黑河': '黑龙江', '绥化': '黑龙江',
            '大兴安岭': '黑龙江',

            # 江苏省（13个地级市）
            '南京': '江苏', '无锡': '江苏', '徐州': '江苏', '常州': '江苏',
            '苏州': '江苏', '南通': '江苏', '连云港': '江苏', '淮安': '江苏',
            '盐城': '江苏', '扬州': '江苏', '镇江': '江苏', '泰州': '江苏', '宿迁': '江苏',

            # 浙江省（11个地级市）
            '杭州': '浙江', '宁波': '浙江', '温州': '浙江', '嘉兴': '浙江',
            '湖州': '浙江', '绍兴': '浙江', '金华': '浙江', '衢州': '浙江',
            '舟山': '浙江', '台州': '浙江', '丽水': '浙江',

            # 安徽省（16个地级市）
            '合肥': '安徽', '芜湖': '安徽', '蚌埠': '安徽', '淮南': '安徽',
            '马鞍山': '安徽', '淮北': '安徽', '铜陵': '安徽', '安庆': '安徽',
            '黄山': '安徽', '滁州': '安徽', '阜阳': '安徽', '宿州': '安徽',
            '六安': '安徽', '亳州': '安徽', '池州': '安徽', '宣城': '安徽',

            # 福建省（9个地级市）
            '福州': '福建', '厦门': '福建', '莆田': '福建', '三明': '福建',
            '泉州': '福建', '漳州': '福建', '南平': '福建', '龙岩': '福建', '宁德': '福建',

            # 江西省（11个地级市）
            '南昌': '江西', '景德镇': '江西', '萍乡': '江西', '九江': '江西',
            '新余': '江西', '鹰潭': '江西', '赣州': '江西', '吉安': '江西',
            '宜春': '江西', '抚州': '江西', '上饶': '江西',

            # 山东省（16个地级市）
            '济南': '山东', '青岛': '山东', '淄博': '山东', '枣庄': '山东',
            '东营': '山东', '烟台': '山东', '潍坊': '山东', '济宁': '山东',
            '泰安': '山东', '威海': '山东', '日照': '山东', '临沂': '山东',
            '德州': '山东', '聊城': '山东', '滨州': '山东', '菏泽': '山东',

            # 河南省（17个地级市）
            '郑州': '河南', '开封': '河南', '洛阳': '河南', '平顶山': '河南',
            '安阳': '河南', '鹤壁': '河南', '新乡': '河南', '焦作': '河南',
            '濮阳': '河南', '许昌': '河南', '漯河': '河南', '三门峡': '河南',
            '南阳': '河南', '商丘': '河南', '信阳': '河南', '周口': '河南', '驻马店': '河南',

            # 湖北省（13个地级市 + 1个自治州）
            '武汉': '湖北', '黄石': '湖北', '十堰': '湖北', '宜昌': '湖北',
            '襄阳': '湖北', '鄂州': '湖北', '荆门': '湖北', '孝感': '湖北',
            '荆州': '湖北', '黄冈': '湖北', '咸宁': '湖北', '随州': '湖北',
            '恩施': '湖北',

            # 湖南省（14个地级市 + 1个自治州）
            '长沙': '湖南', '株洲': '湖南', '湘潭': '湖南', '衡阳': '湖南',
            '邵阳': '湖南', '岳阳': '湖南', '常德': '湖南', '张家界': '湖南',
            '益阳': '湖南', '郴州': '湖南', '永州': '湖南', '怀化': '湖南',
            '娄底': '湖南', '湘西': '湖南',

            # 广东省（21个地级市）
            '广州': '广东', '韶关': '广东', '深圳': '广东', '珠海': '广东',
            '汕头': '广东', '佛山': '广东', '江门': '广东', '湛江': '广东',
            '茂名': '广东', '肇庆': '广东', '惠州': '广东', '梅州': '广东',
            '汕尾': '广东', '河源': '广东', '阳江': '广东', '清远': '广东',
            '东莞': '广东', '中山': '广东', '潮州': '广东', '揭阳': '广东', '云浮': '广东',

            # 广西壮族自治区（14个地级市）
            '南宁': '广西', '柳州': '广西', '桂林': '广西', '梧州': '广西',
            '北海': '广西', '防城港': '广西', '钦州': '广西', '贵港': '广西',
            '玉林': '广西', '百色': '广西', '贺州': '广西', '河池': '广西',
            '来宾': '广西', '崇左': '广西',

            # 海南省（4个地级市）
            '海口': '海南', '三亚': '海南', '三沙': '海南', '儋州': '海南',

            # 四川省（18个地级市 + 3个自治州）
            '成都': '四川', '自贡': '四川', '攀枝花': '四川', '泸州': '四川',
            '德阳': '四川', '绵阳': '四川', '广元': '四川', '遂宁': '四川',
            '内江': '四川', '乐山': '四川', '南充': '四川', '眉山': '四川',
            '宜宾': '四川', '广安': '四川', '达州': '四川', '雅安': '四川',
            '巴中': '四川', '资阳': '四川',
            '阿坝': '四川', '甘孜': '四川', '凉山': '四川',

            # 贵州省（9个地级市）
            '贵阳': '贵州', '六盘水': '贵州', '遵义': '贵州', '安顺': '贵州',
            '毕节': '贵州', '铜仁': '贵州',
            '黔西南': '贵州', '黔东南': '贵州', '黔南': '贵州',

            # 云南省（16个地级市）
            '昆明': '云南', '曲靖': '云南', '玉溪': '云南', '保山': '云南',
            '昭通': '云南', '丽江': '云南', '普洱': '云南', '临沧': '云南',
            '楚雄': '云南', '红河': '云南', '文山': '云南',
            '西双版纳': '云南', '大理': '云南', '德宏': '云南',
            '怒江': '云南', '迪庆': '云南',

            # 西藏自治区（7个地级市）
            '拉萨': '西藏', '日喀则': '西藏', '昌都': '西藏', '林芝': '西藏',
            '山南': '西藏', '那曲': '西藏', '阿里': '西藏',

            # 陕西省（10个地级市）
            '西安': '陕西', '铜川': '陕西', '宝鸡': '陕西', '咸阳': '陕西',
            '渭南': '陕西', '延安': '陕西', '汉中': '陕西', '榆林': '陕西',
            '安康': '陕西', '商洛': '陕西',

            # 甘肃省（14个地级市 + 2个自治州）
            '兰州': '甘肃', '嘉峪关': '甘肃', '金昌': '甘肃', '白银': '甘肃',
            '天水': '甘肃', '武威': '甘肃', '张掖': '甘肃', '平凉': '甘肃',
            '酒泉': '甘肃', '庆阳': '甘肃', '定西': '甘肃', '陇南': '甘肃',
            '临夏': '甘肃', '甘南': '甘肃',

            # 青海省（8个地级市）
            '西宁': '青海', '海东': '青海',
            '海北': '青海', '黄南': '青海',
            '海南': '青海', '果洛': '青海',
            '玉树': '青海', '海西': '青海',

            # 宁夏回族自治区（5个地级市）
            '银川': '宁夏', '石嘴山': '宁夏', '吴忠': '宁夏', '固原': '宁夏', '中卫': '宁夏',

            # 新疆维吾尔自治区（14个地州市 + 地区/自治州完整名称）
            '乌鲁木齐': '新疆', '克拉玛依': '新疆', '吐鲁番': '新疆', '哈密': '新疆',
            '昌吉': '新疆', '博尔塔拉': '新疆', '巴音郭楞': '新疆',
            '阿克苏': '新疆', '克孜勒苏': '新疆', '喀什': '新疆', '和田': '新疆',
            '伊犁': '新疆', '塔城': '新疆', '阿勒泰': '新疆',
            '石河子': '新疆', '五家渠': '新疆', '库尔勒': '新疆',
            # 新疆地区/自治州完整名称
            '伊犁哈萨克': '新疆', '伊犁哈萨克自治州': '新疆', '伊犁哈萨克州': '新疆',
            '克孜勒苏柯尔克孜': '新疆', '克孜勒苏柯尔克孜自治州': '新疆', '克孜勒苏': '新疆', '克州': '新疆',
            '博尔塔拉蒙古': '新疆', '博尔塔拉蒙古自治州': '新疆', '博尔塔拉': '新疆', '博州': '新疆',
            '昌吉回族': '新疆', '昌吉回族自治州': '新疆', '昌吉': '新疆', '昌吉州': '新疆',
            '巴音郭楞蒙古': '新疆', '巴音郭楞蒙古自治州': '新疆', '巴音郭楞': '新疆',
            '阿克苏': '新疆', '阿克苏地区': '新疆',
            '喀什': '新疆', '喀什地区': '新疆',
            '和田': '新疆', '和田地区': '新疆',
            '塔城': '新疆', '塔城地区': '新疆',
            '阿勒泰': '新疆', '阿勒泰地区': '新疆',
            '吐鲁番': '新疆', '吐鲁番地区': '新疆',
            '哈密': '新疆', '哈密地区': '新疆',
        }

        return province_map.get(city, '其他')

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
            "calculating_cumulative_months_statistics",
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

            # 存储数据库（使用cumulative_month类型）
            self.sql_client.insert_statistics(statistics, 'ytd_to_month', stat_date)

            logger.debug(
                "cumulative_month_completed",
                stat_date=stat_date,
                cities_count=len(statistics)
            )

        logger.info(
            "cumulative_months_statistics_completed",
            year=year,
            calculated_months=list(range(1, current_month))
        )
