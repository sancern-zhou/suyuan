# UDF v2.0数据格式修复报告

## 问题描述

**问题**: 区域时序对比分析中，LLM无法收到污染物浓度数据

**根本原因**:
1. DataStandardizer输出扁平格式（PM2_5、PM10等字段在顶层）
2. UnifiedDataRecord期望嵌套格式（污染物在measurements字段中）
3. Pydantic反序列化时，污染物数据丢失到extra字段（被忽略）

**影响范围**:
- `regional_city_comparison` schema
- `regional_station_comparison` schema
- `guangdong_stations` schema
- 所有使用UnifiedDataRecord的空气质量数据

## 修复方案

### 修复位置1: DataStandardizer (主要修复)

**文件**: `backend/app/utils/data_standardizer.py`

**修改内容**:
1. 添加 `_convert_to_udf_v2_format()` 方法（行1456-1545）
2. 在 `_standardize_record()` 末尾调用转换（行1450-1452）

**转换逻辑**:
```python
def _convert_to_udf_v2_format(self, record: Dict[str, Any]) -> Dict[str, Any]:
    """
    将扁平结构转换为UnifiedDataRecord期望的嵌套结构:
    - 污染物字段 → measurements
    - 元数据字段 → 保留在顶层
    - 原始字段 → original_fields (备份)
    """
    TOP_LEVEL_FIELDS = {
        'timestamp', 'station_name', 'station_code', 'city', ...
    }

    POLLUTANT_FIELDS = {
        'PM2_5', 'PM10', 'O3', 'NO2', 'SO2', 'CO', ...
    }

    measurements = {}
    top_level_data = {}

    for field, value in record.items():
        if field in TOP_LEVEL_FIELDS:
            top_level_data[field] = value
        elif field in POLLUTANT_FIELDS:
            measurements[field] = value
        else:
            top_level_data[field] = value

    v2_record = {**top_level_data, 'measurements': measurements}
    return v2_record
```

**输出示例**:
```python
# 输入（扁平格式）
{
    "station_name": "广州",
    "PM2_5": 45.2,
    "PM10": 68.5,
    "AQI": 85
}

# 输出（嵌套格式）
{
    "station_name": "广州",
    "measurements": {
        "PM2_5": 45.2,
        "PM10": 68.5,
        "AQI": 85
    }
}
```

### 修复位置2: UnifiedDataRecord (向后兼容)

**文件**: `backend/app/schemas/unified.py`

**修改内容**:
1. 导入 `root_validator`（行19）
2. 添加 `populate_measurements_from_flat_fields()` validator（行194-234）

**功能**: 自动检测扁平格式并转换为嵌套格式（双重保障）

```python
@root_validator(pre=True)
def populate_measurements_from_flat_fields(cls, values):
    """自动填充measurements字段（向后兼容扁平格式）"""
    measurements = values.get('measurements', {})
    if measurements:
        return values  # 已经是v2.0格式

    # 检测扁平的污染物字段并聚合到measurements
    flat_pollutants = {}
    for field in POLLUTANT_FIELDS:
        if field in values and values[field] is not None:
            flat_pollutants[field] = values[field]

    if flat_pollutants:
        values['measurements'] = flat_pollutants
        # 移除顶层字段避免重复
        for field in flat_pollutants.keys():
            values.pop(field, None)

    return values
```

### 修复位置3: expert_executor (LLM数据提取)

**文件**: `backend/app/agent/experts/expert_executor.py`

**修改内容**: 在 `_extract_tool_data_for_llm()` 中展开measurements字段（行1157-1178）

**功能**: 将嵌套的measurements展开到顶层，便于LLM读取

```python
# 展开measurements字段
if isinstance(data, list) and data:
    first_record = data[0]
    if isinstance(first_record, dict) and "measurements" in first_record:
        expanded_data = []
        for record in data:
            expanded_record = {**record}
            measurements = record.pop("measurements", {})
            expanded_record.update(measurements)
            expanded_data.append(expanded_record)
        data = expanded_data
```

## 修复效果

### 修复前

```json
{
    "station_code": 440100,
    "station_name": "广州",
    "timestamp": "2026-02-01 00:00:00",
    "city_code": 440100
    // ❌ PM2_5、PM10等污染物数据丢失
}
```

### 修复后

```json
{
    "station_code": 440100,
    "station_name": "广州",
    "timestamp": "2026-02-01 00:00:00",
    "city_code": 440100,
    "measurements": {
        "PM2_5": 45.2,
        "PM10": 68.5,
        "O3": 52.3,
        "AQI": 85
    }
}
```

**LLM接收到的数据**（展开后）:
```json
{
    "station_code": 440100,
    "station_name": "广州",
    "timestamp": "2026-02-01 00:00:00",
    "city_code": 440100,
    "PM2_5": 45.2,
    "PM10": 68.5,
    "O3": 52.3,
    "AQI": 85
}
```

## 测试验证

### 测试文件

**文件**: `backend/tests/test_udf_v2_fix.py`

### 测试结果

```
测试1: DataStandardizer格式转换
  udf_v2_measurements_created measurement_fields=['PM2_5', 'PM10', 'O3', 'AQI']
  [PASS] measurements字段存在
  measurements: {'PM2_5': 45.2, 'PM10': 68.5, 'O3': 52.3, 'AQI': 85}

测试2: UnifiedDataRecord反序列化
  [PASS] UnifiedDataRecord反序列化成功
  PM2_5: 45.2

测试3: 向后兼容性
  [PASS] 扁平格式自动转换
  [PASS] 数据完整，已正确聚合到measurements

测试4: LLM数据提取
  [PASS] 污染物数据已展开到顶层
  PM2_5: 45.2
```

**结论**: ✅ 所有测试通过，修复成功！

## 影响分析

### 受益功能

1. **区域时序对比分析** ✅
   - LLM能收到完整的PM2.5/PM10时序数据
   - 可以进行本地生成vs区域传输判断
   - 可以分析峰值时间差

2. **数据可视化** ✅
   - 图表生成工具能获取完整数据
   - 支持多城市时序对比图

3. **数据完整性** ✅
   - 所有使用UnifiedDataRecord的schema统一格式
   - 符合UDF v2.0规范

### 兼容性

1. **向后兼容** ✅
   - 扁平格式数据自动转换
   - 不影响现有代码

2. **向前兼容** ✅
   - 新数据使用嵌套格式
   - 保留original_fields备份

## 后续建议

1. **监控日志**
   - 关注 `udf_v2_measurements_created` 日志
   - 验证measurements_count是否符合预期

2. **性能优化**
   - 如果original_fields占用空间过大，可以按需备份
   - 当前实现只在有extra字段时才备份

3. **文档更新**
   - 更新CLAUDE.md中的数据规范说明
   - 添加UDF v2.0格式示例

## 修改文件清单

1. `backend/app/utils/data_standardizer.py` - 添加格式转换逻辑
2. `backend/app/schemas/unified.py` - 添加向后兼容validator
3. `backend/app/agent/experts/expert_executor.py` - 展开measurements字段
4. `backend/tests/test_udf_v2_fix.py` - 验证测试

## 部署建议

1. **逐步部署**: 先在测试环境验证
2. **监控日志**: 关注measurements创建日志
3. **回滚方案**: 保留代码版本控制，如有问题可快速回滚
