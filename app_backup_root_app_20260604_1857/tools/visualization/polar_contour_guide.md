# 极坐标热力型污染玫瑰图完整指南

## 图表定义
极坐标热力型污染玫瑰图是传统堆叠式污染玫瑰图的进阶可视化形式，用于精细化展示风向、风速与污染物浓度的三维关联特征，适合大气污染溯源分析。

## 两种技术方案

### 方案1：Matplotlib（平滑优先，推荐）

**适用场景**：
- 报告生成
- 导出图片
- 打印输出
- 需要完全平滑的等值线图

**快速开始**：
```python
from app.tools.visualization.polar_contour_generator import generate_pollution_rose_contour
import tempfile, base64

# 默认模式：使用数据自带的气象字段
img_base64 = generate_pollution_rose_contour(
    data_id="{data_id}",              # 数据ID
    pollutant_name="PM10",             # 污染物名称
    time_resolution="hour",            # 时间分辨率：5min/hour/day
    title="PM10浓度极坐标热力型污染玫瑰图（广雅中学，2026-03-01）"
)

# 保存到临时文件（触发自动缓存）
with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
    f.write(base64.b64decode(img_base64))
    print(f"CHART_SAVED:{f.name}")
```

**气象局模式（推荐，数据更准确）**：
```python
img_base64 = generate_pollution_rose_contour(
    data_id="{data_id}",
    pollutant_name="PM10",
    use_gd_met_bureau_weather=True,   # ⭐ 启用气象局数据
    title="PM10浓度极坐标热力型污染玫瑰图（气象局数据）"
)

with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
    f.write(base64.b64decode(img_base64))
    print(f"CHART_SAVED:{f.name}")
```

**参数说明**：
- `data_id`：数据ID（必需）
- `pollutant_name`：污染物名称（必需），如 PM10、PM2.5、O3
- `time_resolution`：时间分辨率（可选，默认"hour"）
  - `"5min"`：使用原始5分钟数据（数据点多，分布散）
  - `"hour"`（默认）：按小时聚合（风向矢量平均，风速/浓度算术平均）
  - `"day"`：按日聚合（长期趋势分析）
- `use_gd_met_bureau_weather`：是否使用气象局气象数据（默认False）
  - False：使用数据自带气象字段，快速分析
  - True：使用气象局数据，精确分析（推荐）
- `title`：图表标题（可选）

**⚠️ 重要提示**：
- Matplotlib 方案必须输出 `CHART_SAVED:/path/to/file.png` 触发缓存
- 建议使用 hour 或 day 聚合，避免5分钟数据过于分散
- 风向采用矢量平均（分解u/v分量），确保统计准确性

---

### 方案2：ECharts（交互优先）

**适用场景**：
- 数据探索
- 在线分析
- 实时查看
- 需要交互功能（缩放、工具提示）

**快速开始**：
```python
from app.tools.visualization.polar_contour_generator import generate_pollution_rose_echarts
import json

# 从 data_id 加载数据
data = get_raw_data('{data_id}')

wind_dirs = [record['WD'] for record in data]
wind_speeds = [record['WS'] for record in data]
concentrations = [record['PM10'] for record in data]

# 生成交互式图表
echarts_option = generate_pollution_rose_echarts(
    wind_directions=wind_dirs,
    wind_speeds=wind_speeds,
    concentrations=concentrations,
    title="PM10浓度极坐标热力型污染玫瑰图（交互式）",
    color_range=(31, 49),        # 浓度范围
    grid_angles=360,             # 角度网格数
    grid_radii=50,               # 半径网格数
    blur=10                      # 模糊度
)

# 输出 ECharts 配置（系统自动识别）
print(json.dumps(echarts_option, ensure_ascii=False))
```

**参数说明**：
- `wind_directions`：风向列表（度数，0-360）
- `wind_speeds`：风速列表
- `concentrations`：污染物浓度列表
- `title`：图表标题
- `color_range`：颜色范围（最小值，最大值）
- `grid_angles`：角度网格数量（默认360）
- `grid_radii`：半径网格数量（默认50）
- `blur`：高斯模糊度（默认10）

**⚠️ 重要提示**：
- ECharts 方案必须直接输出 JSON 配置（包含 series 字段）
- 支持缩放和工具提示交互

---

## LLM 决策流程（优先级从高到低）

### 1. 显式关键词
- **选择 Matplotlib**：「平滑」「渐变」「无扇区」「报告」「导出」「打印」
- **选择 ECharts**：「交互」「可缩放」「可操作」「探索」「在线」

### 2. 场景推断
- **选择 Matplotlib**：「生成报告」「导出图片」「打印」「存档」
- **选择 ECharts**：「探索数据」「在线分析」「实时查看」

### 3. 用户记忆
检查 MEMORY.md 中的「图表交互偏好」条目

### 4. 默认策略
极坐标图默认使用 matplotlib（平滑优先）

---

## 6色阶模式

6色阶模式默认启用（`use_six_level=True`），基于新标准日平均浓度限值自动分级。

**使用方法**：
```python
from app.tools.visualization.polar_contour_generator import generate_pollution_rose_contour
import tempfile, base64

# 6色阶模式：内部固定参数，简化调用
img_base64 = generate_pollution_rose_contour(
    data_id="{data_id}",
    pollutant_name="PM2.5",
    time_resolution="hour",
    title="PM2.5浓度6色阶污染玫瑰图（广雅中学）"
    # use_six_level=True 默认启用
)

with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
    f.write(base64.b64decode(img_base64))
    print(f"CHART_SAVED:{f.name}")
```

**⚠️ 6色阶模式注意事项**：
- 参数内部固定（value_range、color_map、grid_resolution、interpolation_method、dpi）
- 强制显示完整图例，即使数据未覆盖所有浓度范围
- 建议使用 hour 或 day 聚合，避免5分钟数据过于分散

---

## 性能说明

- **matplotlib contourf**：可处理 100-10000 个数据点
- **时间分辨率推荐**：
  - 5分钟数据点密集（~3000点/天），建议使用 `time_resolution="hour"` 聚合（~72点/天）
  - 小时/日聚合可大幅减少数据点，提升绘图性能和可视化效果

---

## 常见问题

**Q1：什么时候使用气象局模式？**
A：需要精确气象数据时使用气象局模式（`use_gd_met_bureau_weather=True`），数据更准确。

**Q2：如何选择时间分辨率？**
A：
- 5分钟：数据点密集，适合短期精确分析
- hour（推荐）：平衡性能和精度
- day：长期趋势分析

**Q3：两种方案输出格式有什么区别？**
A：
- Matplotlib：输出 `CHART_SAVED:/path/to/file.png`（base64编码的图片）
- ECharts：输出 JSON 配置（包含 series 字段）
