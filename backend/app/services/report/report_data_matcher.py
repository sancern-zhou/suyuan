"""
报告数据匹配器

将查询数据与模板占位符进行匹配
"""

from typing import Dict, Any, List, Optional
import structlog

logger = structlog.get_logger()


class ReportDataMatcher:
    """
    报告数据匹配器

    功能：
    - 将数据字段与占位符匹配
    - 生成替换规则
    - 处理时间范围替换
    """

    # 占位符到数据字段的映射规则
    FIELD_MAPPING = {
        # 时间相关
        "start_time": "start_time",
        "end_time": "end_time",
        "开始时间": "start_time",
        "结束时间": "end_time",
        "时间范围": "time_range",

        # 城市相关
        "city": "city",
        "城市": "city",
        "city_name": "city",

        # 站点相关
        "station": "station",
        "站点": "station",
        "station_name": "station",

        # 污染物相关
        "pm25": "pm25",
        "pm2.5": "pm25",
        "pm10": "pm10",
        "o3": "o3",
        "no2": "no2",
        "so2": "so2",
        "co": "co",
        "aqi": "aqi",
    }

    def __init__(self):
        self.logger = logger

    def match_data_to_placeholders(
        self,
        placeholders: List[Dict[str, Any]],
        data: Dict[str, Any],
        time_range: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """
        将数据匹配到占位符

        Args:
            placeholders: 占位符列表
            data: 数据字典
            time_range: 时间范围

        Returns:
            替换规则字典 {placeholder: replacement_value}
        """
        replacements = {}

        # 添加时间范围替换
        if time_range:
            replacements.update({
                "{start_time}": time_range.get("start_time", ""),
                "{end_time}": time_range.get("end_time", ""),
                "{{start_time}}": time_range.get("start_time", ""),
                "{{end_time}}": time_range.get("end_time", ""),
                "${start_time}": time_range.get("start_time", ""),
                "${end_time}": time_range.get("end_time", ""),
            })

        # 匹配占位符
        for ph in placeholders:
            placeholder = ph["placeholder"]
            # 去除包裹符号获取字段名
            field_name = self._extract_field_name(placeholder)

            if field_name in data:
                replacements[placeholder] = str(data[field_name])
            elif field_name in self.FIELD_MAPPING:
                mapped_field = self.FIELD_MAPPING[field_name]
                if mapped_field in data:
                    replacements[placeholder] = str(data[mapped_field])

        self.logger.info(
            "data_matched",
            placeholders_count=len(placeholders),
            replacements_count=len(replacements)
        )

        return replacements

    def _extract_field_name(self, placeholder: str) -> str:
        """
        从占位符中提取字段名

        Examples:
            {start_time} -> start_time
            {{city}} -> city
            ${station} -> station
        """
        # 去除前缀
        for prefix in ["{{", "{", "${", "#", "[", "%"]:
            if placeholder.startswith(prefix):
                placeholder = placeholder[len(prefix):]
                break

        # 去除后缀
        for suffix in ["}}", "}", "}", "#", "]", "%"]:
            if placeholder.endswith(suffix):
                placeholder = placeholder[:-len(suffix)]
                break

        return placeholder.strip()

    def create_table_data(
        self,
        data_records: List[Dict[str, Any]],
        table_structure: Optional[Dict[str, Any]] = None
    ) -> List[List[str]]:
        """
        创建表格数据

        Args:
            data_records: 数据记录列表
            table_structure: 表格结构（可选）

        Returns:
            表格数据（二维列表）
        """
        if not data_records:
            return [["无数据"]]

        # 获取所有字段
        all_fields = set()
        for record in data_records:
            all_fields.update(record.keys())

        # 如果有表头结构，使用指定的字段
        if table_structure and table_structure.get("headers"):
            fields = table_structure["headers"]
        else:
            fields = list(all_fields)

        # 构建表格数据
        table_data = [fields]  # 表头

        for record in data_records:
            row = []
            for field in fields:
                value = record.get(field, "")
                if value is None:
                    value = ""
                elif isinstance(value, (int, float)):
                    value = f"{value:.2f}" if isinstance(value, float) else str(value)
                else:
                    value = str(value)
                row.append(value)
            table_data.append(row)

        return table_data

    def aggregate_statistics(
        self,
        data_records: List[Dict[str, Any]],
        numeric_fields: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        聚合统计数据

        Args:
            data_records: 数据记录列表
            numeric_fields: 数值字段列表（可选）

        Returns:
            统计数据
        """
        if not data_records:
            return {}

        stats = {
            "record_count": len(data_records),
        }

        # 自动检测数值字段
        if numeric_fields is None:
            numeric_fields = []
            first_record = data_records[0]
            for key, value in first_record.items():
                if isinstance(value, (int, float)):
                    numeric_fields.append(key)

        # 计算统计值
        for field in numeric_fields:
            values = [r.get(field) for r in data_records if isinstance(r.get(field), (int, float))]
            if values:
                stats[field] = {
                    "min": min(values),
                    "max": max(values),
                    "avg": sum(values) / len(values),
                    "count": len(values)
                }

        return stats
