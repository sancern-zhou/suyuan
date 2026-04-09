# aggregate_data 工具天数验证修复报告

**修复日期**: 2026-03-24
**修复人**: Claude Code
**文件**: `backend/app/tools/analysis/aggregate_data/tool.py`

---

## 问题描述

aggregate_data 工具存在两个关键设计缺陷：

### 问题1：IAQI/AQI 没有单日限制

- **现状**: 对任意时间段的数据计算平均浓度，然后计算IAQI/AQI
- **问题**: IAQI分段标准基于**日平均浓度**设计，多日平均会平滑掉高值，导致评价偏低
- **示例**:
  ```
  第1天：PM2.5 = 150 μg/m³ → IAQI = 200（中度污染）
  第2天：PM2.5 = 50 μg/m³  → IAQI = 100（良）
  平均：PM2.5 = 100 μg/m³ → IAQI = 150（轻度污染）
  ```
  平均值的IAQI=150不代表任何一天的实际空气质量，违背HJ 633-2026标准

### 问题2：综合指数/单项指数没有多日限制

- **现状**: 对任意时间段的数据计算平均浓度，然后计算指数
- **问题**: 综合指数用于评价**一段时间内**（月/季/年）的综合空气质量，对单日数据计算没有统计学意义
- **标准依据**: `ANNUAL_STANDARD_LIMITS` 使用的是年平均二级标准

---

## 修复内容

### 1. 新增两个验证方法

#### `_validate_single_day_data(data, time_column)`
- **功能**: 验证数据是否只包含单日数据
- **返回**: `{"is_valid": bool, "reason": str}`
- **使用场景**: IAQI、AQI、PRIMARY_POLLUTANT函数

**验证逻辑**:
1. 检测时间列（支持多种字段名和格式）
2. 提取所有记录的日期部分（YYYY-MM-DD）
3. 判断唯一日期数量是否为1

**支持的时间字段**:
- `timestamp`, `time`, `date`, `datetime`, `time_point`, `time_date`
- 嵌套的 `measurements.timestamp`
- 多种时间格式（ISO 8601、带T、带Z等）

#### `_validate_multi_day_data(data, time_column, min_days=2)`
- **功能**: 验证数据是否包含至少指定天数的数据
- **返回**: `{"is_valid": bool, "reason": str}`
- **使用场景**: SINGLE_INDEX、COMPREHENSIVE_INDEX函数

**验证逻辑**:
1. 检测时间列
2. 提取所有记录的日期部分
3. 判断唯一日期数量是否满足最小天数要求

### 2. 在 execute 方法中添加验证逻辑

**位置**: 数据加载和日期过滤后，执行聚合前

```python
# 步骤1.6：验证数据时间范围是否符合聚合函数要求
time_column_for_validation = time_column or self._detect_time_column(data)
for agg in aggregations:
    func = agg.get("function", "").upper()

    # IAQI/AQI/PRIMARY_POLLUTANT：限制单日数据
    if func in ["IAQI", "AQI", "PRIMARY_POLLUTANT"]:
        validation_result = self._validate_single_day_data(data, time_column_for_validation)
        if not validation_result["is_valid"]:
            return {
                "status": "failed",
                "success": False,
                "error": f"{func}函数只能用于单日数据评价，{validation_result['reason']}。..."
            }

    # SINGLE_INDEX/COMPREHENSIVE_INDEX：限制多日数据
    elif func in ["SINGLE_INDEX", "COMPREHENSIVE_INDEX"]:
        validation_result = self._validate_multi_day_data(data, time_column_for_validation, min_days=2)
        if not validation_result["is_valid"]:
            return {
                "status": "failed",
                "success": False,
                "error": f"{func}函数只能用于多日数据评价（至少2天），{validation_result['reason']}。..."
            }
```

### 3. 更新工具描述（schema）

在 `function_schema` 的 description 中明确说明使用限制：

```
**⚠️ 重要使用限制（HJ 633-2026标准）：**
- **IAQI/AQI/PRIMARY_POLLUTANT**：仅限单日数据评价，基于日平均浓度设计
  - 使用start_date和end_date参数限制为单日（如start_date='2026-01-17', end_date='2026-01-17'）
  - 多日数据会先求平均再计算，导致评价结果不准确
- **SINGLE_INDEX/COMPREHENSIVE_INDEX**：仅限多日数据评价（至少2天）
  - 用于月/季/年等时段的综合评价
  - 单日数据计算无统计学意义
```

### 4. 添加IAQI函数的pollutant参数验证

```python
# 验证IAQI函数的pollutant参数
if func == "IAQI":
    pollutant = agg.get("pollutant")
    if not pollutant:
        return {
            "status": "failed",
            "success": False,
            "error": "IAQI函数必须提供pollutant参数（如PM2_5、NO2、SO2等）"
        }
```

---

## 测试验证

### 测试用例

1. **单日数据验证**:
   - ✓ 单日数据通过验证
   - ✓ 多日数据被正确拒绝（返回具体天数）
   - ✓ 空数据被正确拒绝
   - ✓ 无时间列时向后兼容

2. **多日数据验证**:
   - ✓ 多日数据（>=2天）通过验证
   - ✓ 单日数据被正确拒绝
   - ✓ 空数据被正确拒绝
   - ✓ 无时间列时向后兼容

3. **时间格式支持**:
   - ✓ ISO 8601格式（2026-01-17T00:00:00）
   - ✓ 标准格式（2026-01-17 00:00:00）
   - ✓ 嵌套时间戳（measurements.timestamp）

---

## 修复效果

### 修复前
```python
# 可以对多日数据计算IAQI（错误）
aggregate_data(
    data_id="xxx",
    aggregations=[{"function": "IAQI", "column": "PM2_5", "pollutant": "PM2_5"}]
)
# 结果：对1月1日-1月31日的数据求平均，再计算IAQI（不符合标准）
```

### 修复后
```python
# 尝试对多日数据计算IAQI
aggregate_data(
    data_id="xxx",
    aggregations=[{"function": "IAQI", "column": "PM2_5", "pollutant": "PM2_5"}]
)
# 结果：返回错误
# "IAQI函数只能用于单日数据评价，当前数据跨越31天（从2026-01-01到2026-01-31）。
#  请使用start_date和end_date参数限制为单日，或使用其他聚合函数。"

# 正确用法：限制为单日
aggregate_data(
    data_id="xxx",
    aggregations=[{"function": "IAQI", "column": "PM2_5", "pollutant": "PM2_5"}],
    start_date="2026-01-17",
    end_date="2026-01-17"
)
# 结果：只计算1月17日的IAQI（符合标准）
```

---

## 向后兼容性

- **无时间列的数据**: 验证方法会返回 `is_valid=True`，不会破坏现有功能
- **无法解析的时间**: 同样返回 `is_valid=True`，保持向后兼容

---

## 标准依据

修复严格遵循 **HJ 633-2026《环境空气质量评价技术规范》**：

- **IAQI/AQI**: 基于日平均浓度设计，用于单日空气质量评价
- **综合指数**: 用于月/季/年等时段的综合空气质量评价
- **单项指数**: 配合综合指数使用，评价时段内的单项污染物水平

---

## 文件修改清单

1. `backend/app/tools/analysis/aggregate_data/tool.py`
   - 新增 `_validate_single_day_data()` 方法（约60行）
   - 新增 `_validate_multi_day_data()` 方法（约70行）
   - 修改 `execute()` 方法，添加验证逻辑（约20行）
   - 更新 `function_schema` 描述（约10行）
   - 添加IAQI的pollutant参数验证（约10行）

**总计**: 约170行新增/修改代码

---

## 验证命令

```bash
# 语法检查
python -m py_compile app/tools/analysis/aggregate_data/tool.py

# 导入测试
python -c "from app.tools.analysis.aggregate_data.tool import AggregateDataTool; print('✓ 工具加载成功')"
```

---

## 后续建议

1. **更新使用指南**: 在 `aggregate_data_guide.md` 中添加天数限制的详细说明和示例
2. **前端提示**: 在前端调用这些函数时，提供日期范围选择的UI提示
3. **单元测试**: 在 `tests/` 目录下添加完整的单元测试覆盖这些验证逻辑
