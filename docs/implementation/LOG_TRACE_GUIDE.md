# 关键日志追踪指南

## 问题定位

需要确认数据在哪个环节丢失了污染物浓度。

## 数据流程关键节点

### 节点1: API返回原始数据
**日志位置**: `get_guangdong_regular_stations/tool.py`

**查找日志**:
```
raw_record_0_debug
raw_data_sample
```

**预期输出**:
```
first_record_keys=['aqi', 'co', 'nO2', 'o3', 'pM10', 'pM2_5']
sample_raw_values={'pM2_5': 45.2, 'pM10': 68.5}
```

**检查点**: ✅ API返回了污染物数据

---

### 节点2: DataStandardizer标准化开始
**日志位置**: `data_standardizer.py:148-156`

**查找日志**:
```
regional_comparison_standardization_start
```

**预期输出**:
```
raw_count=120
first_raw_keys=['aqi', 'cityOrder', 'co', 'code', ..., 'pM10', 'pM2_5']
sample_raw_values={'pM2_5': 45.2, 'pM10': 68.5, 'o3': 52.3}
```

**检查点**: ✅ 数据进入标准化器时污染物存在

---

### 节点3: UDF v2.0格式转换开始
**日志位置**: `data_standardizer.py:1452-1458`

**查找日志**:
```
udf_v2_conversion_start
```

**预期输出**:
```
input_fields=['station_name', 'station_code', 'PM2_5', 'PM10', 'O3', ...]
has_PM2_5=true
has_PM10=true
has_measurements=false
```

**检查点**: ⚠️ 这一步很关键，确认转换前污染物字段存在

---

### 节点4: 字段分类详情
**日志位置**: `data_standardizer.py:1534-1546`

**查找日志** (DEBUG级别):
```
udf_v2_field_to_measurements
```

**预期输出**:
```
field=PM2_5 value=45.2
field=PM10 value=68.5
field=O3 value=52.3
```

**检查点**: ⚠️ 确认污染物字段被识别并放入measurements

---

### 节点5: UDF v2.0格式转换完成
**日志位置**: `data_standardizer.py:1461-1467`

**查找日志**:
```
udf_v2_conversion_complete
```

**预期输出**:
```
output_fields=['station_name', 'station_code', 'timestamp', 'measurements']
has_measurements=true
measurements_count=6
measurement_fields=['PM2_5', 'PM10', 'O3', 'NO2', 'SO2', 'CO']
```

**检查点**: ✅ 这一步最关键，确认measurements字段已创建

---

### 节点6: 标准化完成
**日志位置**: `get_guangdong_regular_stations/tool.py:160-171`

**查找日志**:
```
regional_comparison_data_standardized
```

**预期输出**:
```
raw_count=120
standardized_count=120
first_standardized_keys=['station_name', 'station_code', 'timestamp', 'measurements']
has_measurements=true
measurements_content={
    'station_name': '广州',
    'timestamp': '2026-02-01 00:00:00',
    'measurements': {'PM2_5': 45.2, 'PM10': 68.5}
}
```

**检查点**: ✅ 确认工具层收到的数据有measurements字段

---

### 节点7: DataContextManager保存
**日志位置**: `data_context_manager.py:329-336`

**查找日志**:
```
data_standardization_skipped
data_saved_with_id
```

**预期输出**:
```
data_standardization_skipped
reason=field_mapping_applied_already_set
first_data_keys=['station_name', 'station_code', 'timestamp', 'measurements']
has_measurements=true
```

**检查点**: ⚠️ 如果跳过标准化，数据应该已经有measurements字段

---

### 节点8: LLM数据提取检查
**日志位置**: `expert_executor.py:1161-1168`

**查找日志**:
```
llm_data_extraction_check
```

**预期输出**:
```
tool=get_guangdong_regular_stations
record_count=120
first_record_keys=['station_name', 'station_code', 'timestamp', 'measurements']
has_measurements=true
measurements_sample={'PM2_5': 45.2, 'PM10': 68.5, 'O3': 52.3}
```

**检查点**: ✅ 确认数据从存储层加载时有measurements

---

### 节点9: Measurements字段展开
**日志位置**: `expert_executor.py:1185-1193`

**查找日志**:
```
measurements_field_expanded
```

**预期输出**:
```
tool=get_guangdong_regular_stations
total_records=20 (截断后)
expanded_records=20
expanded_sample_keys=['station_name', 'timestamp', 'PM2_5', 'PM10', 'O3']
has_PM2_5=true
has_PM10=true
```

**检查点**: ✅ 确认measurements已展开到顶层

---

## 故障排查检查清单

### 如果在节点3发现问题

**现象**: `udf_v2_conversion_start` 显示 `has_PM2_5=false`

**原因**: 标准化过程中污染物字段丢失

**检查**:
1. 查看 `pollutant_standardized_success` 日志
2. 确认 `_standardize_record` 方法中污染物字段映射成功

---

### 如果在节点5发现问题

**现象**: `udf_v2_conversion_complete` 显示 `has_measurements=false`

**原因**: `_convert_to_udf_v2_format` 方法未执行或执行失败

**检查**:
1. 确认代码版本是否包含修复
2. 重启服务加载新代码
3. 检查是否有异常抛出

---

### 如果在节点7发现问题

**现象**: `data_standardization_skipped` 但 `has_measurements=false`

**原因**: 工具层设置 `field_mapping_applied=true` 但数据未转换

**检查**:
1. 确认工具层调用的是否是新代码
2. 检查 `get_guangdong_regular_stations` 是否调用了标准化

---

### 如果在节点8发现问题

**现象**: `llm_data_extraction_check` 显示 `has_measurements=false`

**原因**: 数据从存储层加载时格式错误

**检查**:
1. 查看存储的JSON文件内容
2. 确认 `UnifiedDataRecord` 反序列化是否正确

---

## 快速验证命令

```bash
# 1. 查找完整的转换流程
grep -E "udf_v2_conversion_start|udf_v2_conversion_complete" 后端日志.md

# 2. 查找measurements字段创建
grep "udf_v2_measurements_created.*PM2_5.*PM10" 后端日志.md

# 3. 查找区域对比数据标准化
grep "regional_comparison_data_standardized" 后端日志.md

# 4. 查找LLM数据提取
grep -E "llm_data_extraction_check|measurements_field_expanded" 后端日志.md
```

## 预期完整日志链

```
[1] API返回: pM2_5: 45.2 ✅
    ↓
[2] standardization_start: sample_raw_values={'pM2_5': 45.2} ✅
    ↓
[3] udv_v2_conversion_start: has_PM2_5=true ✅
    ↓
[4] udv_v2_field_to_measurements: field=PM2_5 value=45.2 ✅
    ↓
[5] udv_v2_conversion_complete: measurements_count=6 ✅
    ↓
[6] regional_data_standardized: has_measurements=true ✅
    ↓
[7] data_standardization_skipped: has_measurements=true ✅
    ↓
[8] llm_data_extraction_check: has_measurements=true ✅
    ↓
[9] measurements_field_expanded: has_PM2_5=true ✅
```

如果任何一环失败，可以立即定位问题。
