# query_city_standard_report 全省数据修复方案

## 问题描述

用户查询 `["全省"]` 时，工具返回21条城市数据，不包含全省汇总记录。

## 根本原因

API的StationCode参数行为：
- **不传StationCode** → 返回27条（1全省+6区域+21城市）
- **传StationCode** → 只返回指定的城市数据，不包含区域汇总

原代码在请求"全省"时：
1. 展开为21个城市
2. 构建城市编码
3. **传了StationCode**
4. API只返回21个城市，无全省汇总

## 解决方案

### 核心逻辑

```python
# 判断是否需要传StationCode
has_region_alias = any(city in REGION_ALIASES for city in requested_cities)
is_all_cities = set(expanded_cities) == set(ALL_CITIES)
should_send_station_code = city_codes and not has_region_alias and not is_all_cities

if should_send_station_code:
    payload["StationCode"] = city_codes
```

### 传参规则

| 场景 | has_region_alias | is_all_cities | StationCode | 返回结果 |
|------|-----------------|---------------|------------|---------|
| 查询全省/珠三角等区域 | ✅ True | - | ❌ 不传 | 27条（含区域汇总） |
| 查询全部21个城市 | ❌ False | ✅ True | ❌ 不传 | 27条（含区域汇总） |
| 查询部分城市 | ❌ False | ❌ False | ✅ 传 | N条（仅指定城市） |

### 测试场景

✅ 全部13个场景测试通过：

1. `["全省"]` → 返回27条（含全省汇总）
2. `["广东省"]` → 返回27条（含全省汇总）
3. `["珠三角"]` → 返回27条（含珠三角汇总）
4. `["非珠三角"]` → 返回27条（含非珠三角汇总）
5. `["粤东"]` → 返回27条（含粤东汇总）
6. `["粤西"]` → 返回27条（含粤西汇总）
7. `["粤北"]` → 返回27条（含粤北汇总）
8. `["粤东西北"]` → 返回27条（含粤东西北汇总）
9. `["广州"]` → 返回1条（广州）
10. `["广州", "深圳"]` → 返回2条（广州、深圳）
11. `["珠三角", "粤东"]` → 返回27条（含区域汇总）
12. `["全部21个城市"]` → 返回27条（含区域汇总）
13. `["广州", "珠三角"]` → 返回27条（含区域汇总）

## 修改内容

### 文件：`backend/app/tools/query/query_city_standard_report/tool.py`

1. **新增常量**（第50-53行）：
```python
REGION_ALIASES = ["全省", "广东省", "珠三角", "非珠三角", "粤东", "粤西", "粤北", "粤东西北"]
ALL_CITIES = GUANGDONG_REGIONS["全省"]
```

2. **修改payload构建逻辑**（第200-215行）：
```python
# 判断是否需要传StationCode
has_region_alias = any(city in REGION_ALIASES for city in requested_cities)
is_all_cities = set(expanded_cities) == set(ALL_CITIES)
should_send_station_code = city_codes and not has_region_alias and not is_all_cities

if should_send_station_code:
    payload["StationCode"] = city_codes
```

3. **增强日志输出**（第220-228行）：
```python
logger.info(
    "query_city_standard_report_start",
    requested_cities=requested_cities,
    cities=expanded_cities,
    city_codes=city_codes,
    has_region_alias=has_region_alias,
    is_all_cities=is_all_cities,
    should_send_station_code=should_send_station_code,
    ...
)
```

4. **同比报表同样修改**（第415-425行）

## 优势

1. **简单直接**：改20行代码，逻辑清晰
2. **零风险**：利用API原生能力，无客户端聚合
3. **用户友好**：返回完整数据，用户可自行筛选
4. **全覆盖**：所有查询场景都正确处理

## API返回的27条记录结构

1. 全省（1条）
2. 珠三角（1条）
3. 非珠三角（1条）
4. 粤东（1条）
5. 粤西（1条）
6. 粤北（1条）
7. 粤东西北（1条，可能重复）
8. 21个城市（21条）

## 日期

2026-05-16
