# aggregate_data 工具 IAQI 计算修复 - 实施确认

## 问题总结

### 原始问题
- `aggregate_data` 工具计算 2026-01-17 的 PM2_5_IAQI = 87（旧标准）
- `query_standard_comparison` 工具计算 PM2_5_IAQI = 107（新标准）
- 两个工具结果不一致

### 根本原因
1. **数据存储结构**：`query_standard_comparison` 存储的数据包含旧标准 IAQI 字段
   ```json
   {
     "measurements": {
       "PM2_5": 64.0,
       "PM2_5_IAQI": 87.0,  // API 返回的旧标准 IAQI
       "NO2": 91.0,
       "NO2_IAQI": 106.0
     }
   }
   ```

2. **错误的调用方式**：LLM 生成的参数使用了已存储的 IAQI 字段
   ```json
   {
     "column": "measurements.PM2_5_IAQI",  // ❌ 错误：使用旧标准 IAQI
     "function": "AVG"
   }
   ```

3. **字段映射问题**：`POLLUTANT_COLUMN_MAP` 缺少嵌套字段名（已修复）

## 实施的修复

### 修复1：更新字段映射表 ✅
**文件**：`backend/app/tools/analysis/aggregate_data/tool.py`（第74-81行）

**修改内容**：添加嵌套字段名支持
```python
POLLUTANT_COLUMN_MAP = {
    'PM2_5': [..., 'measurements.PM2_5', 'measurements.PM2.5', ...],
    'NO2': [..., 'measurements.NO2', ...],
    # 其他污染物类似
}
```

### 修复2：更新工具描述 ✅
**文件**：`backend/app/tools/analysis/aggregate_data/tool.py`（第210-223行）

**修改内容**：明确说明 IAQI 函数的正确使用方式
- 在工具描述中添加 IAQI 函数使用注意事项
- 强调应使用浓度字段（measurements.PM2_5）而不是 IAQI 字段（measurements.PM2_5_IAQI）
- 提供正确示例

### 修复3：添加调试日志 ✅
**文件**：`backend/app/tools/analysis/aggregate_data/tool.py`

**添加位置**：
- 第369-398行：数据加载调试日志
- 第793-840行：字段查找调试日志
- 第854-896行：IAQI 计算调试日志

## 正确的调用方式

### ❌ 错误方式
```json
{
  "column": "measurements.PM2_5_IAQI",
  "function": "AVG",
  "pollutant": "PM2_5",
  "alias": "PM2_5_IAQI"
}
```

### ✅ 正确方式
```json
{
  "column": "measurements.PM2_5",
  "function": "IAQI",
  "pollutant": "PM2_5",
  "alias": "PM2_5_IAQI"
}
```

## 预期结果

使用正确调用方式后，2026-01-17 的结果应该是：
```
PM2_5 浓度: 64.0 μg/m³ → IAQI = 107（新标准）
NO2 浓度: 91.0 μg/m³ → IAQI = 106
首要污染物: PM2.5 ✓
```

## 影响范围

### 已修改文件
1. `backend/app/tools/analysis/aggregate_data/tool.py`
   - 字段映射表更新（第74-81行）
   - 工具描述更新（第210-223行）
   - 调试日志添加（第369-896行）

### 不需要修改
- ✅ `query_standard_comparison` 工具：计算逻辑正确
- ✅ `query_new_standard_report` 工具：计算逻辑正确
- ✅ 数据存储格式：保持不变

## 验证步骤

1. 重启后端服务
2. 重新运行查询，LLM 应该生成正确的调用参数
3. 验证 2026-01-17 的结果：
   - PM2_5_IAQI = 107（不是87）
   - NO2_IAQI = 106
   - 首要污染物 = PM2.5

## 技术说明

### IAQI 计算逻辑
`aggregate_data` 工具的 IAQI 函数使用新标准（HJ 633-2024）：
- PM2.5 断点：IAQI=100 对应 60 μg/m³（旧标准75）
- PM10 断点：IAQI=100 对应 120 μg/m³（旧标准150）
- 计算函数：`calculate_iaqi_for_aggregate()`

### 关键代码
```python
# 第613-620行
elif func == "IAQI":
    # 计算IAQI（空气质量分指数）
    if not pollutant:
        logger.warning("iaqi_missing_pollutant", column=column)
        continue
    agg_values = grouped[column].apply(
        lambda x: calculate_iaqi_for_aggregate(x, pollutant) if pd.notna(x) else 0
    )
```

## 状态
✅ **修复已完成**，等待重启后端服务验证
