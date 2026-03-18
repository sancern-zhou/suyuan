# 新方法：替换_parse_markdown_table
def _parse_markdown_table(self, answer: str, question: str) -> list:
    """
    动态解析Markdown表格格式的空气质量数据
    智能识别字段类型，自动转换为中国标准污染物名称
    一次解析，处处使用，符合统一数据格式规范

    Args:
        answer: Dify API返回的表格文本
        question: 查询问题

    Returns:
        UnifiedDataRecord列表
    """
    from app.schemas.unified import UnifiedDataRecord
    import re

    data_list = []

    # 匹配Markdown表格
    table_pattern = r'\|.*\|.*\|(?:\n\|.*\|.*\|)+'
    table_match = re.search(table_pattern, answer)

    if not table_match:
        logger.warning("no_markdown_table_found")
        return data_list

    table_text = table_match.group(0)

    # 提取表格行
    lines = [line.strip() for line in table_text.split('\n') if line.strip().startswith('|')]
    if len(lines) < 2:
        return data_list

    # 解析表头
    header_line = lines[0]
    headers = [cell.strip() for cell in header_line.split('|')[1:-1]]

    # 智能字段识别和转换
    field_mapping = self._build_field_mapping(headers)

    # 解析数据行
    for line in lines[2:]:  # 跳过分隔行
        cells = [cell.strip() for cell in line.split('|')[1:-1]]
        if len(cells) != len(headers):
            continue

        # 构建记录字典
        timestamp = None
        station_name = None
        lat = None
        lon = None
        measurements = {}

        for i, (header, value) in enumerate(zip(headers, cells)):
            if not value or value in ["—", "", "N/A", "null", "None", "—"]:
                continue

            # 获取标准字段名
            standard_field = field_mapping.get(header, header)

            # 动态解析字段
            if standard_field == "time":
                # 解析时间格式
                for fmt in ["%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"]:
                    try:
                        timestamp = datetime.strptime(value, fmt)
                        break
                    except ValueError:
                        continue
            elif standard_field == "station_name":
                station_name = value
            elif standard_field == "lat":
                try:
                    lat = float(value)
                except (ValueError, TypeError):
                    pass
            elif standard_field == "lon":
                try:
                    lon = float(value)
                except (ValueError, TypeError):
                    pass
            else:
                # 测量值 - 尝试转换为数值
                try:
                    # 处理中文逗号分隔的数值
                    if isinstance(value, str) and ',' in value:
                        value = value.replace(',', '')

                    # 转换为浮点数
                    num_value = float(value)
                    measurements[standard_field] = num_value
                except (ValueError, TypeError):
                    # 如果转换失败，跳过该字段
                    continue

        # 构建UnifiedDataRecord
        if measurements and timestamp:  # 至少需要时间和测量值
            data_list.append(UnifiedDataRecord(
                timestamp=timestamp,
                station_name=station_name,
                lat=lat,
                lon=lon,
                measurements=measurements
            ))

    logger.info("air_quality_table_parsed", rows=len(data_list))
    return data_list

def _build_field_mapping(self, headers: list) -> dict:
    """
    动态构建字段映射表
    智能识别中文污染物名称并转换为中国标准

    Args:
        headers: 表头列表

    Returns:
        字段映射字典
    """
    # 动态构建字段映射
    field_mapping = {}

    for header in headers:
        # 时间字段
        if any(keyword in header for keyword in ["时间", "时间点", "timestamp", "Time"]):
            field_mapping[header] = "time"
            continue

        # 地点字段
        if any(keyword in header for keyword in ["城市", "地区", "站点", "城市名称"]):
            field_mapping[header] = "station_name"
            continue

        # 坐标字段
        if "纬度" in header or "lat" in header.lower():
            field_mapping[header] = "lat"
            continue
        if "经度" in header or "lon" in header.lower():
            field_mapping[header] = "lon"
            continue

        # 污染字段 - 智能转换为中国标准名称
        standard_name = self._convert_to_standard_name(header)
        field_mapping[header] = standard_name

    return field_mapping

def _convert_to_standard_name(self, field_name: str) -> str:
    """
    将字段名转换为中国标准污染物名称

    Args:
        field_name: 原始字段名

    Returns:
        标准字段名
    """
    # 清理字段名
    clean_name = field_name.replace('(', '').replace(')', '').replace('₃', '3').strip()

    # 标准污染物名称映射
    standard_mapping = {
        # AQI相关
        "aqi": "AQI",
        "空气质量指数": "AQI",
        "AQI": "AQI",

        # 二氧化硫
        "二氧化硫": "SO2",
        "so2": "SO2",
        "SO2": "SO2",

        # 一氧化碳
        "一氧化碳": "CO",
        "co": "CO",
        "CO": "CO",

        # 二氧化氮
        "二氧化氮": "NO2",
        "no2": "NO2",
        "NO2": "NO2",

        # 臭氧
        "臭氧": "O3",
        "o3": "O3",
        "O3": "O3",
        "臭氧(O3)": "O3",

        # PM10
        "可吸入颗粒物": "PM10",
        "pm10": "PM10",
        "PM10": "PM10",

        # PM2.5
        "细颗粒物": "PM2.5",
        "pm2.5": "PM2.5",
        "PM2.5": "PM2.5",

        # 氮氧化物
        "氮氧化物": "NOx",
        "nox": "NOx",
        "NOx": "NOx",

        # 其他常见字段
        "首要污染物": "primary_pollutant",
        "空气质量等级": "air_quality_level"
    }

    # 查找映射
    for key, value in standard_mapping.items():
        if key in field_name or key in clean_name:
            return value

    # 如果没有匹配，返回清理后的原始名称
    # 确保只包含字母、数字和下划线
    import re
    clean_name = re.sub(r'[^a-zA-Z0-9_]', '_', clean_name)
    return clean_name if clean_name else field_name
