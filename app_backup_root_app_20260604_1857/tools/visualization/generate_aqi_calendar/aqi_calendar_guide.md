# AQI日历热力图完整指南

## 图表定义
AQI日历热力图用于展示多城市×日期的AQI矩阵，通过颜色深浅直观反映空气质量状况，适合月度/季度空气质量回顾分析。

## 快速开始

```python
from app.tools.visualization.generate_aqi_calendar.calendar_renderer import generate_calendar_from_data_id
import tempfile, base64

# 生成AQI日历图
img = generate_calendar_from_data_id(
    data_id="{data_id}",    # 数据ID（必需）
    year=2026,              # 年份（必需）
    month=3,                # 月份（必需）
    pollutant="AQI"         # 污染物名称（可选，默认"AQI"）
)

# 保存到临时文件（触发自动缓存）
with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
    f.write(base64.b64decode(img))
    print(f"CHART_SAVED:{f.name}")
```

## 参数说明

- `data_id`：数据ID（必需），从数据查询工具获取
- `year`：年份（必需），如 2026
- `month`：月份（必需），1-12
- `pollutant`：污染物名称（可选，默认"AQI"）
  - 支持的污染物：AQI、PM2.5、PM10、O3、NO2、SO2、CO

## 使用时机

当用户提到以下关键词时，使用AQI日历图：
- "AQI日历"
- "日历热力图"
- "月度日历"
- "月度回顾"
- "多城市×日期"
- "空气质量矩阵"

## 数据要求

- 数据必须包含以下字段：
  - `city`：城市名称
  - `time`：时间字段（日期或时间戳）
  - `AQI`（或指定的污染物）：浓度值
- 建议使用日数据或月数据

## 输出格式

必须输出以下格式触发缓存：
```
CHART_SAVED:/tmp/xxx.png
```

## 完整示例

```python
# 场景：用户需要查看2026年3月广州、深圳、珠海的AQI日历图

# 1. 先查询数据（使用 query_gd_suncere_city_day_new）
# 2. 获得 data_id
# 3. 生成日历图

from app.tools.visualization.generate_aqi_calendar.calendar_renderer import generate_calendar_from_data_id
import tempfile, base64

img = generate_calendar_from_data_id(
    data_id="query_gd_suncere_city_day_new:v1:xxx",
    year=2026,
    month=3,
    pollutant="AQI"
)

with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
    f.write(base64.b64decode(img))
    print(f"CHART_SAVED:{f.name}")
```

## 颜色说明

日历图使用标准AQI颜色：
- 绿色（0-50）：优
- 黄色（51-100）：良
- 橙色（101-150）：轻度污染
- 红色（151-200）：中度污染
- 紫色（201-300）：重度污染
- 褐红色（>300）：严重污染

## 常见问题

**Q1：支持单城市日历吗？**
A：支持，data_id 包含单城市数据即可。

**Q2：可以显示其他污染物吗？**
A：可以，设置 `pollutant` 参数为 PM2.5、PM10、O3 等。

**Q3：时间范围必须是单月吗？**
A：是的，当前版本仅支持单月日历图。如需多月，请分别生成。
