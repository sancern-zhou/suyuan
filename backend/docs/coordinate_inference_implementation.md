# 坐标推断功能实现总结

## 问题背景

`meteorological_trajectory_analysis` 工具在Agent调用时频繁失败，原因是LLM通常只提供站点名称（如"广州"），但工具要求必须提供 `lat` 和 `lon` 参数。

## 根本原因

工具在 `input_adapter.py` 的 `TOOL_RULES` 中没有配置，导致无法从 `location_name` 推断出经纬度坐标。

## 解决方案

采用硬编码城市坐标映射表的方式，实现坐标自动推断。

## 实施内容

### 1. 添加工具配置 (input_adapter.py:284-329)

在 `TOOL_RULES` 字典中添加 `meteorological_trajectory_analysis` 配置：

```python
"meteorological_trajectory_analysis": {
    "required_fields": ["lat", "lon"],  # 只需要这两个
    "optional_fields": ["start_time", "hours", "heights", "direction", "meteo_source"],
    "field_mapping": {
        "latitude": "lat",
        "经度": "lon",
        "longitude": "lon",
        "纬度": "lat",
        "开始时间": "start_time",
        "起始时间": "start_time",
        "小时数": "hours",
        "回溯小时": "hours",
        "高度层": "heights",
        "方向": "direction",
        "轨迹方向": "direction",
        "气象数据源": "meteo_source"
    },
    "normalizers": {},
    "inferencers": {
        "lat": "infer_lat_from_location",
        "lon": "infer_lon_from_location"
    },
    "examples": {
        "with_station_name": {
            "location_name": "广州",
            "hours": 72,
            "direction": "Backward"
        },
        "with_coordinates": {
            "lat": 23.13,
            "lon": 113.26,
            "start_time": "2025-01-15T00:00:00Z",
            "hours": 72,
            "heights": [10, 500, 1000],
            "direction": "Backward",
            "meteo_source": "gdas1"
        },
        "minimal": {
            "lat": 23.13,
            "lon": 113.26
        }
    }
}
```

**重要修正**：
- ✅ 工具真实参数只需要 `lat` 和 `lon`（必需）
- ✅ 使用 `hours` 而非 `end_time` 来控制轨迹长度
- ✅ 支持从城市名称自动推断坐标

### 2. 扩展城市坐标映射表 (input_adapter.py:973-1105)

在 `_infer_lat_from_location()` 和 `_infer_lon_from_location()` 方法中扩展 `CITY_COORDS` 映射表：

#### 广东省21个地级市

| 城市 | 纬度 | 经度 |
|------|------|------|
| 广州 | 23.13 | 113.26 |
| 深圳 | 22.54 | 114.06 |
| 珠海 | 22.27 | 113.58 |
| 汕头 | 23.35 | 116.68 |
| 佛山 | 23.03 | 113.12 |
| 韶关 | 24.81 | 113.60 |
| 湛江 | 21.27 | 110.36 |
| 肇庆 | 23.05 | 112.47 |
| 江门 | 22.58 | 113.08 |
| 茂名 | 21.66 | 110.92 |
| 惠州 | 23.11 | 114.42 |
| 梅州 | 24.29 | 116.12 |
| 汕尾 | 22.79 | 115.37 |
| 河源 | 23.74 | 114.70 |
| 阳江 | 21.86 | 111.98 |
| 清远 | 23.68 | 113.06 |
| 东莞 | 23.02 | 113.75 |
| 中山 | 22.52 | 113.39 |
| 潮州 | 23.66 | 116.62 |
| 揭阳 | 23.55 | 116.37 |
| 云浮 | 22.92 | 112.04 |

#### 济宁市及辖区县

| 地区 | 纬度 | 经度 |
|------|------|------|
| 济宁 | 35.42 | 116.59 |
| 任城区 | 35.42 | 116.59 |
| 兖州区 | 35.55 | 116.83 |
| 微山县 | 34.81 | 117.13 |
| 鱼台县 | 35.01 | 116.65 |
| 金乡县 | 35.07 | 116.31 |
| 嘉祥县 | 35.41 | 116.34 |
| 汶上县 | 35.71 | 116.49 |
| 泗水县 | 35.66 | 117.27 |
| 梁山县 | 35.80 | 116.10 |

### 3. 坐标数据来源

数据来源：全国省市县乡四级政府驻地经纬度坐标
http://gaohr.win/site/blogs/2022/2022-03-29-location-of-gov.html

### 4. 修改后的推断逻辑

修改前：
```python
if data_type == "era5" and location_name and location_name in CITY_COORDS:
    lat, _ = CITY_COORDS[location_name]
    return lat
```

修改后：
```python
can_infer = (
    (data_type == "era5" and location_name) or  # ERA5气象数据
    location_name  # 任何工具提供location_name时都支持推断
)

if can_infer and location_name in CITY_COORDS:
    lat, _ = CITY_COORDS[location_name]
    return lat
```

## 测试验证

创建了测试脚本 `tests/test_coordinate_inference.py`，验证：

1. **坐标推断测试**
   - 广东省21个地级市：成功 21/21
   - 济宁市及辖区县：成功 10/10

2. **字段映射测试**
   - 中文参数（纬度/经度）：通过
   - 英文别名（latitude/longitude）：通过
   - 混合参数：通过

## 使用示例

### 示例1：使用站点名称（推荐）

```python
# LLM输出（无需手动提供经纬度）
raw_args = {
    "location_name": "广州",
    "hours": 72,
    "direction": "Backward"
}

# Input Adapter自动推断后
normalized_args = {
    "lat": 23.13,        # 自动推断
    "lon": 113.26,       # 自动推断
    "hours": 72,
    "direction": "Backward"
}
```

### 示例2：直接提供经纬度

```python
# LLM输出（直接提供坐标）
raw_args = {
    "lat": 23.13,
    "lon": 113.26,
    "hours": 72,
    "direction": "Backward"
}

# 无需推断，直接使用
```

### 示例3：最简参数（仅经纬度）

```python
# LLM输出（最简形式）
raw_args = {
    "lat": 23.13,
    "lon": 113.26
}

# 工具将使用默认值：hours=72, direction="Backward"
```

## 支持的参数变体

工具支持以下参数名称变体：

| 标准字段 | 支持的变体 |
|----------|-----------|
| lat | latitude, 纬度 |
| lon | longitude, 经度 |
| start_time | 开始时间, 起始时间 |
| hours | 小时数, 回溯小时 |
| heights | 高度层 |
| direction | 方向, 轨迹方向 |
| meteo_source | 气象数据源 |

## 工具真实参数说明

`meteorological_trajectory_analysis` 使用NOAA HYSPLIT API，真实参数如下：

- **lat** (必需): 起始纬度
- **lon** (必需): 起始经度
- **start_time** (可选): 起始时间，默认当前UTC时间
- **hours** (可选): 回溯/预测小时数（24-168），默认72
- **heights** (可选): 高度层列表（米AGL），默认[10, 500, 1000]
- **direction** (可选): "Backward"反向或"Forward"正向，默认"Backward"
- **meteo_source** (可选): 气象数据源，默认"gdas1"

## 影响范围

1. **meteorological_trajectory_analysis 工具**
   - 现在可以从城市名称自动推断坐标
   - 支持31个城市/地区的坐标查询
   - 减少Agent调用失败率
   - 修正参数结构：使用 `hours` 而非 `end_time`

2. **get_weather_data 工具**
   - 同时受益于扩展的城市坐标映射表
   - 现在支持更多城市的ERA5气象数据查询

## 修复记录

### 第一次实现 (2026-02-05 上午)
- ✅ 添加工具配置到 `TOOL_RULES`
- ✅ 扩展城市坐标映射表（31个城市）
- ✅ 更新坐标推断逻辑

### 问题发现 (2026-02-05 上午)
- ❌ 初始配置错误：要求 `start_time` + `end_time`
- ✅ 工具实际需要：`start_time` + `hours`

### 第二次修复 (2026-02-05 上午)
- ✅ 修正 `required_fields`：只保留 `["lat", "lon"]`
- ✅ 更新 `optional_fields`：添加 `hours`，移除 `end_time`
- ✅ 扩展字段映射：支持中英文参数变体
- ✅ 更新测试脚本：使用正确的参数结构
- ✅ 测试验证：所有测试通过（31/31城市，4/4字段映射）

## 后续优化建议

1. **动态API查询**：当硬编码映射表不足时，可以调用 `station_api.get_station_by_name()` 动态查询站点坐标

2. **上下文提取**：从历史数据中提取站点坐标信息

3. **模糊匹配**：支持城市别名的模糊匹配（如"穗"→"广州"）

4. **坐标缓存**：将查询过的站点坐标缓存到内存，避免重复查询

## 相关文件

- `backend/app/agent/input_adapter.py` - 主要修改文件
- `backend/tests/test_coordinate_inference.py` - 测试脚本
- `backend/app/tools/analysis/meteorological_trajectory_analysis/tool.py` - 轨迹分析工具

## 修改时间

2026-02-05

## 修改人

Claude Code (基于用户需求)
