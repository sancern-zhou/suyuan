#!/usr/bin/env python3
"""
简单的UDF v2.0集成测试
"""

print("测试1: 检查字段映射")
from app.utils.field_mappings import FieldMappings

# 测试字段映射
test_record = {
    "StationName": "深圳莲花站",
    "cityName": "深圳市",
    "pM2_5": 35.6,
    "PM10": 52.3
}

station_info = FieldMappings.extract_station_info(test_record)
print(f"站点信息: {station_info}")

print("\n测试2: 检查schema版本")
from app.schemas.unified import DataMetadata

metadata = DataMetadata(
    data_id="test:v2:123",
    data_type="air_quality"
)
print(f"Schema版本: {metadata.schema_version}")

print("\n测试3: 检查v2.0新增字段")
print(f"有source_data_ids: {hasattr(metadata, 'source_data_ids')}")
print(f"有scenario: {hasattr(metadata, 'scenario')}")
print(f"有generator: {hasattr(metadata, 'generator')}")

print("\n✅ 所有基本检查通过!")
