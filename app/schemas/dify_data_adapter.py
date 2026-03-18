"""
Dify API 数据适配器

专门处理Dify API返回的格式不稳定问题
支持多种数据格式解析，确保数据完整性
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime
import json
import re
import structlog
from html import unescape

from app.schemas.unified import (
    UnifiedData, DataType, DataStatus, DataMetadata, UnifiedDataRecord
)

logger = structlog.get_logger()


class DifyDataAdapter:
    """
    Dify API数据适配器

    专门处理Dify工作流返回的空气质量数据
    支持格式不稳定的JSON和表格数据
    """

    @staticmethod
    def parse_dify_response(response: Dict[str, Any]) -> UnifiedData:
        """
        解析Dify API响应

        Args:
            response: Dify API原始响应

        Returns:
            UnifiedData: 统一格式数据
        """
        try:
            # 提取基础信息
            conversation_id = response.get("conversation_id")
            answer = response.get("answer", "")
            query = response.get("query", "")

            # 解析answer中的数据
            data_list = []

            # 策略1: 尝试JSON格式
            json_data = DifyDataAdapter._parse_json_from_answer(answer)
            if json_data:
                data_list = DifyDataAdapter._parse_json_data(json_data)

            # 策略2: 尝试Markdown表格
            if not data_list:
                data_list = DifyDataAdapter._parse_markdown_table(answer, query)

            # 策略3: 尝试HTML表格
            if not data_list:
                data_list = DifyDataAdapter._parse_html_table(answer, query)

            # 构建统一数据格式
            return DifyDataAdapter._build_unified_data(
                data_list=data_list,
                conversation_id=conversation_id,
                query=query,
                answer=answer,
                response=response
            )

        except Exception as e:
            logger.error("dify_data_parse_failed", error=str(e), exc_info=True)
            return DifyDataAdapter._build_error_response(
                error_msg=f"Dify数据解析失败: {str(e)}",
                conversation_id=response.get("conversation_id"),
                query=response.get("query", "")
            )

    @staticmethod
    def _parse_json_from_answer(answer: str) -> Optional[Dict[str, Any]]:
        """从answer中提取JSON数据"""
        try:
            # 清理HTML实体
            answer = unescape(answer)

            # 尝试多种JSON提取模式
            patterns = [
                # JSON数组
                r'\[[\s\S]*\]',
                # 包含数据的JSON
                r'\{[^}]*"data"[^}]*\[[\s\S]*\][^}]*\}',
                # 完整JSON对象
                r'\{[\s\S]*\}',
            ]

            for pattern_idx, pattern in enumerate(patterns):
                match = re.search(pattern, answer)
                if match:
                    json_str = match.group(0)
                    try:
                        data = json.loads(json_str)
                        # 验证是否包含有效数据
                        if isinstance(data, (list, dict)) and len(str(data)) > 10:
                            logger.info("json_parsed_successfully", data_type=type(data).__name__, data_length=len(data))
                            return data
                    except json.JSONDecodeError as e:
                        logger.info("json_parse_failed", pattern_index=pattern_idx, error=str(e))
                        # 继续尝试下一个模式
                        continue

            logger.info("no_json_pattern_matched")
            return None

        except Exception as e:
            logger.warning("json_extraction_failed", error=str(e))
            return None

    @staticmethod
    def _fix_truncated_json(json_str: str) -> Optional[str]:
        """修复截断的JSON数组"""
        try:
            # 如果不是以[开头或不是以]结尾，这不是一个截断的数组
            if not json_str.startswith('[') or json_str.rstrip().endswith(']'):
                return None

            # 方法1: 先尝试直接添加]看是否是完整记录
            test_json = json_str.rstrip() + ']'
            try:
                json.loads(test_json)
                # 如果成功，说明只是缺少]
                return test_json
            except json.JSONDecodeError:
                pass

            # 方法2: 使用自定义JSON解析器逐步解析
            # 找到最后一个完整的对象
            decoder = json.JSONDecoder()
            max_position = 0

            # 尝试从不同位置解析
            for i in range(len(json_str), 0, -100):
                try:
                    # 截取前i个字符
                    partial = json_str[:i]
                    # 确保以]结尾
                    if not partial.rstrip().endswith(']'):
                        partial = partial.rstrip() + ']'

                    # 尝试解析
                    data = decoder.decode(partial)
                    if isinstance(data, list) and len(data) > 0:
                        # 验证数据是否有效
                        max_position = i
                        break
                except (json.JSONDecodeError, UnicodeDecodeError):
                    continue

            if max_position > 0:
                # 找到有效位置，截取并添加]
                fixed_json = json_str[:max_position]
                if not fixed_json.rstrip().endswith(']'):
                    fixed_json = fixed_json.rstrip() + ']'

                # 最终验证
                try:
                    data = json.loads(fixed_json)
                    if isinstance(data, list) and len(data) > 0:
                        return fixed_json
                except json.JSONDecodeError:
                    pass

            return None

        except Exception as e:
            logger.warning("fix_truncated_json_failed", error=str(e))
            return None

    @staticmethod
    def _parse_json_data(data: Any) -> List[UnifiedDataRecord]:
        """解析JSON数据"""
        records = []

        try:
            # 如果是列表，直接处理
            if isinstance(data, list):
                for item in data:
                    record = DifyDataAdapter._convert_item_to_record(item)
                    if record:
                        records.append(record)
                    else:
                        logger.info("convert_item_to_record_failed", item_keys=list(item.keys())[:5])

            # 如果是字典，尝试提取数据列表
            elif isinstance(data, dict):
                # 常见的数据字段名
                data_fields = ["data", "results", "records", "list", "items"]
                for field in data_fields:
                    if field in data and isinstance(data[field], list):
                        for item in data[field]:
                            record = DifyDataAdapter._convert_item_to_record(item)
                            if record:
                                records.append(record)
                        break

                # 如果没有找到数据字段，尝试将整个字典作为单条记录
                if not records and data:
                    record = DifyDataAdapter._convert_item_to_record(data)
                    if record:
                        records.append(record)

        except Exception as e:
            logger.warning("json_data_parse_failed", error=str(e))

        logger.info("parse_json_data_complete", record_count=len(records))
        return records

    @staticmethod
    def _convert_item_to_record(item: Dict[str, Any]) -> Optional[UnifiedDataRecord]:
        """将单个数据项转换为UnifiedDataRecord"""
        try:
            # 提取时间戳 - 尝试所有可能的字段名
            timestamp_str = ""
            time_keys = ["time", "timestamp", "时间", "时间点", "data_time", "TimePoint"]
            for key in time_keys:
                if key in item and item[key]:
                    timestamp_str = str(item[key])
                    break

            # 如果没找到，尝试从所有字段中查找包含时间格式的值
            if not timestamp_str:
                for key, value in item.items():
                    if isinstance(value, str) and re.search(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}', value):
                        timestamp_str = value
                        break

            try:
                if isinstance(timestamp_str, str):
                    # 尝试多种时间格式
                    for fmt in ["%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"]:
                        try:
                            timestamp = datetime.strptime(timestamp_str, fmt)
                            break
                        except ValueError:
                            continue
                    else:
                        timestamp = datetime.now()
                else:
                    timestamp = timestamp_str
            except (ValueError, TypeError):
                timestamp = datetime.now()

            # 提取地理信息 - 尝试所有可能的字段名
            station_name = ""
            city_keys = ["station_name", "城市名称", "市区名称", "城市", "cityname", "name"]
            for key in city_keys:
                if key in item and item[key]:
                    station_name = str(item[key])
                    break

            # 如果没找到，尝试从所有字段中查找
            if not station_name:
                for key, value in item.items():
                    if isinstance(value, str) and len(value) > 1 and not re.search(r'^\d+(\.\d+)?$', value):
                        # 跳过看起来像数字的值
                        continue
                    if isinstance(value, str) and '市' in value or '区' in value or '县' in value:
                        station_name = value
                        break

            # 提取坐标
            lat = item.get("lat", item.get("latitude"))
            lon = item.get("lon", item.get("longitude"))

            # 提取测量值 - 转换字段名为标准名称
            measurements = {}
            # 非测量字段列表
            non_measurement_keys = set([
                "time", "timestamp", "station_name", "lat", "lon",
                "城市名称", "市区名称", "城市", "latitude", "longitude", "城市编码",
                "首要污染物", "空气质量等级", "省内排名", "cityname", "city_code",
                "name", "id", "station_id", "data_time", "TimePoint", "时间点", "时间"
            ])

            for key, value in item.items():
                # 跳过非测量字段
                if key in non_measurement_keys:
                    continue

                # 跳过看起来像时间或地点的值
                if isinstance(value, str):
                    if re.search(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}', value):
                        continue
                    if '市' in value or '区' in value or '县' in value:
                        continue

                # 转换字段名为标准名称
                standard_key = DifyDataAdapter._convert_to_standard_name(key)

                # 尝试转换为数值
                try:
                    if isinstance(value, (int, float)):
                        measurements[standard_key] = float(value)
                    elif isinstance(value, str) and value.replace('.', '').replace('-', '').replace('+', '').isdigit():
                        measurements[standard_key] = float(value)
                except (ValueError, TypeError):
                    continue

            if measurements:
                return UnifiedDataRecord(
                    timestamp=timestamp,
                    station_name=station_name,
                    lat=lat,
                    lon=lon,
                    measurements=measurements
                )

        except Exception as e:
            logger.warning("item_conversion_failed", error=str(e))

        return None

    @staticmethod
    def _parse_markdown_table(answer: str, query: str) -> List[UnifiedDataRecord]:
        """解析Markdown表格数据"""
        records = []

        try:
            # 清理HTML实体
            answer = unescape(answer)

            # 匹配Markdown表格
            table_pattern = r'\|.*\|.*\|(?:\n\|.*\|.*\|)+'
            table_match = re.search(table_pattern, answer)

            if not table_match:
                return records

            table_text = table_match.group(0)

            # 提取表格行
            lines = [line.strip() for line in table_text.split('\n') if line.strip().startswith('|')]
            if len(lines) < 2:
                return records

            # 解析表头
            header_line = lines[0]
            headers = [cell.strip() for cell in header_line.split('|')[1:-1]]

            # 构建字段映射
            field_mapping = DifyDataAdapter._build_field_mapping(headers)

            # 解析数据行
            for line in lines[2:]:  # 跳过分隔行
                cells = [cell.strip() for cell in line.split('|')[1:-1]]
                if len(cells) != len(headers):
                    continue

                # 构建记录
                record_data = {}
                for i, (header, value) in enumerate(zip(headers, cells)):
                    if not value or value in ["—", "", "N/A", "null", "None", "—"]:
                        continue

                    standard_field = field_mapping.get(header, header)
                    record_data[standard_field] = value

                # 转换为UnifiedDataRecord
                record = DifyDataAdapter._convert_dict_to_record(record_data)
                if record:
                    records.append(record)

        except Exception as e:
            logger.warning("markdown_table_parse_failed", error=str(e))

        return records

    @staticmethod
    def _parse_html_table(answer: str, query: str) -> List[UnifiedDataRecord]:
        """解析HTML表格数据"""
        records = []

        try:
            from bs4 import BeautifulSoup

            # 清理HTML实体
            answer = unescape(answer)

            # 解析HTML
            soup = BeautifulSoup(answer, 'html.parser')
            table = soup.find('table')

            if not table:
                return records

            # 提取表头
            headers = []
            header_row = table.find('tr')
            if header_row:
                for th in header_row.find_all(['th', 'td']):
                    headers.append(th.get_text(strip=True))

            if len(headers) < 2:
                return records

            # 构建字段映射
            field_mapping = DifyDataAdapter._build_field_mapping(headers)

            # 解析数据行
            for row in table.find_all('tr')[1:]:
                cells = row.find_all(['td', 'th'])
                if len(cells) != len(headers):
                    continue

                # 构建记录
                record_data = {}
                for i, cell in enumerate(cells):
                    value = cell.get_text(strip=True)
                    if value and value not in ["—", "", "N/A", "null", "None"]:
                        header = headers[i]
                        standard_field = field_mapping.get(header, header)
                        record_data[standard_field] = value

                # 转换为UnifiedDataRecord
                record = DifyDataAdapter._convert_dict_to_record(record_data)
                if record:
                    records.append(record)

        except ImportError:
            logger.warning("beautifulsoup4 not installed, skip html table parsing")
        except Exception as e:
            logger.warning("html_table_parse_failed", error=str(e))

        return records

    @staticmethod
    def _build_field_mapping(headers: List[str]) -> Dict[str, str]:
        """构建字段映射表"""
        field_mapping = {}

        for header in headers:
            header_lower = header.lower().strip()

            # 特殊字段
            if header_lower in ["citycode", "city_code", "城市编码"]:
                field_mapping[header] = "city_code"
                continue
            if header_lower in ["id", "station_id"]:
                field_mapping[header] = "id"
                continue

            # 时间字段
            if any(keyword in header or keyword in header_lower for keyword in [
                "时间", "时间点", "timestamp", "Time", "timepoint", "data_time", "TimePoint"
            ]):
                field_mapping[header] = "time"
                continue

            # 地点字段
            if any(keyword in header or keyword in header_lower for keyword in [
                "城市", "地区", "站点", "城市名称", "市区名称", "area", "cityname", "name", "cityname"
            ]):
                field_mapping[header] = "station_name"
                continue

            # 坐标字段
            if any(keyword in header or keyword in header_lower for keyword in [
                "纬度", "lat", "latitude"
            ]):
                field_mapping[header] = "lat"
                continue
            if any(keyword in header or keyword in header_lower for keyword in [
                "经度", "lon", "longitude"
            ]):
                field_mapping[header] = "lon"
                continue

            # 首要污染物
            if any(keyword in header or keyword in header_lower for keyword in [
                "首要污染物", "primarypollutant", "pollutant"
            ]):
                field_mapping[header] = "primary_pollutant"
                continue

            # 空气质量等级
            if any(keyword in header or keyword in header_lower for keyword in [
                "空气质量等级", "quality", "aqi_level", "level"
            ]):
                field_mapping[header] = "air_quality_level"
                continue

            # 污染字段
            field_mapping[header] = DifyDataAdapter._convert_to_standard_name(header)

        return field_mapping

    @staticmethod
    def _convert_to_standard_name(field_name: str) -> str:
        """
        使用统一的data_standardizer转换为标准字段名

        遵循数据规范：所有字段映射统一使用data_standardizer，工具内部不做独立映射
        """
        from app.utils.data_standardizer import get_data_standardizer

        # 提取括号内容（用于特殊字段如"臭氧(O₃)"）
        bracket_match = re.search(r'[(（]([^)）]+)[)）]', field_name)
        if bracket_match:
            bracket_content = bracket_match.group(1)
            # 先尝试映射括号内容
            standardizer = get_data_standardizer()
            mapped = standardizer._get_standard_field_name(bracket_content)
            if mapped:
                return mapped

        # 使用全局标准化器映射字段名
        standardizer = get_data_standardizer()
        mapped = standardizer._get_standard_field_name(field_name)
        if mapped:
            return mapped

        # 如果无法映射，清理字段名后返回
        # 清理特殊字符，转换为下划线
        clean_name = re.sub(r'[^a-zA-Z0-9_]', '_', field_name.strip())
        # 避免全下划线
        if clean_name and clean_name != '_' * len(clean_name):
            return clean_name

        # 提取字母数字组合
        alphanumeric = re.findall(r'[a-zA-Z0-9]+', field_name)
        if alphanumeric:
            return ''.join(alphanumeric)

        return field_name

    @staticmethod
    def _convert_dict_to_record(data: Dict[str, Any]) -> Optional[UnifiedDataRecord]:
        """将字典数据转换为UnifiedDataRecord"""
        try:
            # 解析时间
            timestamp_str = data.get("time", "")
            try:
                for fmt in ["%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"]:
                    try:
                        timestamp = datetime.strptime(timestamp_str, fmt)
                        break
                    except ValueError:
                        continue
                else:
                    timestamp = datetime.now()
            except (ValueError, TypeError):
                timestamp = datetime.now()

            # 提取地理信息
            station_name = data.get("station_name")
            lat = data.get("lat")
            lon = data.get("lon")

            # 提取测量值
            measurements = {}
            for key, value in data.items():
                if key in ["time", "timestamp", "station_name", "lat", "lon", "city_code", "id",
                          "primary_pollutant", "air_quality_level", "时间点", "时间", "城市名称"]:
                    continue

                try:
                    if isinstance(value, str) and ',' in value:
                        value = value.replace(',', '')

                    num_value = float(value)
                    measurements[key] = num_value
                except (ValueError, TypeError):
                    continue

            if measurements and timestamp:
                return UnifiedDataRecord(
                    timestamp=timestamp,
                    station_name=station_name,
                    lat=lat,
                    lon=lon,
                    measurements=measurements
                )

        except Exception as e:
            logger.warning("dict_to_record_failed", error=str(e))

        return None

    @staticmethod
    def _build_unified_data(
        data_list: List[UnifiedDataRecord],
        conversation_id: str,
        query: str,
        answer: str,
        response: Dict[str, Any]
    ) -> UnifiedData:
        """构建统一数据格式"""

        # 计算质量评分
        quality_score = 0.0
        if data_list:
            # 基于数据完整性和一致性评分
            valid_records = sum(1 for r in data_list if r.measurements)
            completeness = valid_records / len(data_list)

            # 字段一致性评分
            if data_list:
                first_fields = set(data_list[0].measurements.keys())
                consistent = all(set(r.measurements.keys()) == first_fields for r in data_list)
                consistency = 1.0 if consistent else 0.5

                quality_score = (completeness + consistency) / 2
            else:
                quality_score = 0.0

        # 提取站点信息
        station_name = None
        unique_stations = set()
        if data_list:
            # 收集所有唯一站点
            for record in data_list:
                if record.station_name:
                    unique_stations.add(record.station_name)
            # 使用第一个站点作为主要站点
            station_name = data_list[0].station_name

        # 构建元数据
        metadata = DataMetadata(
            data_id=f"air_quality:{conversation_id or 'unknown'}",
            data_type=DataType.AIR_QUALITY,
            record_count=len(data_list),
            station_name=station_name,
            source="dify_api",
            quality_score=quality_score,
            parameters={"question": query}
        )

        # 构建摘要（增强版：显示所有站点）
        summary = f"[OK] 获取到 {len(data_list)} 条空气质量数据"

        if unique_stations:
            station_count = len(unique_stations)
            if station_count == 1:
                summary += f"（{list(unique_stations)[0]}）"
            else:
                # 多站点：显示前3个站点 + "等X个城市"
                station_list = sorted(list(unique_stations))
                if station_count <= 3:
                    stations_str = "、".join(station_list)
                else:
                    stations_str = "、".join(station_list[:3]) + f"等{station_count}个城市"
                summary += f"（{stations_str}）"

        # 确定状态
        if data_list:
            status = DataStatus.SUCCESS
            success = True
        else:
            status = DataStatus.EMPTY
            success = False

        return UnifiedData(
            status=status,
            success=success,
            data=data_list,
            metadata=metadata,
            summary=summary,
            legacy_fields={
                "conversation_id": conversation_id,
                "answer": answer,
                "raw_response": response
            }
        )

    @staticmethod
    def _build_error_response(error_msg: str, conversation_id: str, query: str) -> UnifiedData:
        """构建错误响应"""
        return UnifiedData(
            status=DataStatus.FAILED,
            success=False,
            error=error_msg,
            data=[],
            metadata=DataMetadata(
                data_id=f"air_quality_error:{id(error_msg)}",
                data_type=DataType.AIR_QUALITY,
                source="dify_api",
                parameters={"question": query}
            ),
            summary=f"[ERROR] {error_msg}"
        )


# ============================================================================
# 便利函数
# ============================================================================

def parse_dify_air_quality_data(response: Dict[str, Any]) -> UnifiedData:
    """解析Dify空气质量数据"""
    return DifyDataAdapter.parse_dify_response(response)


# ============================================================================
# 示例用法
# ============================================================================

"""
示例1: 解析Dify API响应
```python
from app.schemas.dify_data_adapter import parse_dify_air_quality_data

# 模拟Dify API响应
response = {
    "conversation_id": "abc123",
    "answer": "[{\"时间点\":\"2025-11-08T10:00:00\",\"城市名称\":\"广州市\",\"SO2\":8,\"PM2.5\":18}]",
    "query": "查询广州今日空气质量"
}

# 解析为统一格式
unified_data = parse_dify_air_quality_data(response)
print(f"解析成功: {unified_data.success}")
print(f"数据记录数: {len(unified_data.data)}")
```

示例2: 处理表格格式
```python
answer = '''
| 时间点 | 城市名称 | SO2 | PM2.5 |
|--------|----------|-----|-------|
| 2025-11-08 10:00 | 广州市 | 8 | 18 |
'''

response = {
    "conversation_id": "def456",
    "answer": answer,
    "query": "查询广州空气质量"
}

unified_data = parse_dify_air_quality_data(response)
```
"""
