# ReAct Agent 工具返回格式改进总结

## 改进背景

在端到端测试中发现，当数据库中没有历史数据时，`analyze_upwind_enterprises` 工具调用失败。根本原因是：

1. **数据库缺少历史气象数据**（主要问题）
2. **工具返回格式不够明确**，LLM无法正确判断数据可用性
3. **工具schema缺少数据转换指导**，LLM不知道如何构建参数

## 改进内容

### 1. get_weather_data 工具改进 ✅

#### 改进前的问题

**返回格式**：
```python
{
    "success": True,
    "data_type": "observed",
    "records": [],  # 空数组
    "count": 0,
    "message": "未找到数据"  # LLM可能忽略这个字段
}
```

**Schema描述**：
```python
"description": "查询指定位置和时间范围的历史气象数据（ERA5再分析数据或观测站数据）"
# 没有说明返回格式和字段含义
```

#### 改进后

**增强的返回格式**：
```python
# 无数据情况
{
    "success": True,
    "has_data": False,  # ✨ 新增：显式标记数据可用性
    "data_type": "observed",
    "station_id": "广雅中学",
    "records": [],
    "count": 0,
    "summary": "⚠️ 数据库中没有站点 广雅中学 在 2025-10-20 至 2025-10-20 期间的观测气象数据"
    # ✨ 新增：清晰的摘要信息
}

# 有数据情况
{
    "success": True,
    "has_data": True,  # ✨ 明确标记
    "data_type": "observed",
    "records": [...],  # 数据数组
    "count": 24,
    "summary": "✅ 查询到站点 广雅中学 的 24 条观测气象数据（2025-10-20 至 2025-10-20）"
    # ✨ 包含数据量和时间范围
}
```

**增强的Schema描述**：
```python
"description": """查询指定位置和时间范围的历史气象数据（ERA5再分析数据或观测站数据）。

返回数据格式：
{
    "success": bool,              # 查询是否成功
    "has_data": bool,             # 是否有实际数据（重要：用于判断数据是否可用）
    "data_type": "era5|observed", # 数据类型
    "records": [                  # 气象记录数组
        {
            "time": str,                   # ISO 8601格式时间戳
            "temperature_2m": float,       # 2米温度（°C）
            "relative_humidity_2m": float, # 2米相对湿度（%）
            "wind_speed_10m": float,       # 10米风速（m/s）
            "wind_direction_10m": float,   # 10米风向（度，0-360，0=北，90=东，180=南，270=西）
            "surface_pressure": float,     # 地表气压（hPa）
            "precipitation": float,        # 降水量（mm）
            ...                            # 其他气象参数
        }
    ],
    "count": int,                 # 记录数量
    "summary": str                # 结果摘要（包含数据可用性信息）
}

重要提示：
1. 如果 has_data=False 或 count=0，说明数据库中没有该时间段的数据，records将为空数组
2. wind_direction_10m 和 wind_speed_10m 字段可用于风场分析（如需要构建风向风速数组）
3. 数据可能因时间段或地点不存在而返回空结果，这是正常情况
"""
```

**改进要点**：
- ✅ 添加 `has_data` 字段，显式标记数据可用性
- ✅ 改进 `summary` 字段，包含详细的状态描述
- ✅ 在schema中详细说明返回格式和所有字段含义
- ✅ 明确指出风向风速字段（`wind_direction_10m`, `wind_speed_10m`）
- ✅ 说明空数据是正常情况，指导LLM正确处理

### 2. analyze_upwind_enterprises 工具改进 ✅

#### 改进前的问题

**Schema描述**：
```python
"winds": {
    "type": "array",
    "description": "风向风速数据列表",
    # 没有说明如何构建这个参数
}
```

LLM不知道：
- winds参数的具体格式要求
- 如何从get_weather_data的结果中提取数据
- 什么情况下不应该调用此工具

#### 改进后

**增强的Schema描述**：
```python
"winds": {
    "type": "array",
    "description": """风向风速数据列表，每个元素包含 wd（风向，度）和 ws（风速，m/s）字段。

数据格式要求：
- 每个元素必须是对象，包含 wd 和 ws 两个数值字段
- wd: 风向角度，0-360 度（0=北，90=东，180=南，270=西）
- ws: 风速，单位 m/s，必须 >= 0

数据来源转换：
如果从 get_weather_data 获取气象数据，需要从其返回的 records 数组中提取：
- 提取字段：wind_direction_10m → wd, wind_speed_10m → ws
- 转换逻辑：遍历 records，为每条记录构建 {wd: <wind_direction_10m>, ws: <wind_speed_10m>}
- 过滤条件：确保 wd 和 ws 都不为 null，且在有效范围内

注意事项：
- 必须提供实际的数组数据，不能使用描述性文本或占位符
- 如果上游工具返回 has_data=False 或 count=0，说明没有可用数据，应告知用户而非继续调用本工具
                """
}
```

**工具级别描述增强**：
```python
"description": """
分析指定站点上风向可能的污染源企业（仅适用于广东省）。

...（原有内容）...

数据转换示例：
如需从其他工具的结果构建winds参数，可参考以下转换模式：
- 如果源数据中包含 wind_direction_* 和 wind_speed_* 字段，提取并重命名为 wd 和 ws
- 如果源数据是记录数组 records[]，遍历数组并提取每条记录的风向风速字段
- 确保 wd 范围在 0-360 度之间，ws 单位为 m/s

示例代码逻辑（供参考）：
winds = [{"wd": record["wind_direction_*"], "ws": record["wind_speed_*"]} for record in records]
"""
```

**改进要点**：
- ✅ 详细说明winds参数的格式要求
- ✅ 提供通用的数据转换指导（不硬编码特定工具）
- ✅ 明确指出字段映射关系（wind_direction_10m → wd）
- ✅ 说明何时不应该调用本工具（has_data=False时）
- ✅ 禁止使用描述性文本代替实际数据

### 3. 数据采集器使用指南 ✅

创建了完整的使用指南文档：`backend/docs/数据采集器使用指南.md`

**内容包括**：
1. 系统架构图（ASCII）
2. 已注册的4个采集器详细说明
3. 5种使用方法：
   - 自动启动（推荐）
   - 禁用自动启动
   - API手动触发
   - Python脚本手动运行
   - 批量回填历史数据
4. 状态监控方法
5. 常见问题解答
6. 扩展开发指南

**创建的脚本**：`backend/run_fetcher_manual.py`

**使用示例**：
```bash
# 运行ERA5采集器（填充历史气象数据）
python run_fetcher_manual.py era5

# 运行观测数据采集器
python run_fetcher_manual.py observed

# 运行所有采集器
python run_fetcher_manual.py all
```

## 改进效果预测

### 改进前的Agent行为

```
迭代1: 调用 get_weather_data
观察: {"success": True, "records": [], "count": 0, "message": "未找到数据"}

迭代2: 调用 analyze_upwind_enterprises
参数: winds='从步骤1获取的风向数据（假设已包含...）'  # ❌ 使用描述性文本
结果: ❌ 失败 - "没有有效的风向风速数据"

迭代3-9: 重复尝试，持续失败
```

### 改进后的预期行为

```
迭代1: 调用 get_weather_data
观察: {
    "success": True,
    "has_data": False,  # ✨ 明确标记
    "records": [],
    "count": 0,
    "summary": "⚠️ 数据库中没有站点 广雅中学 在 2025-10-20 至 2025-10-20 期间的观测气象数据"
}

迭代2: Agent思考
识别: has_data=False, count=0
判断: 数据库中没有所需的历史气象数据
决策:
  - 选项A: 告知用户数据不可用 ✅
  - 选项B: 尝试其他数据源（如 get_observed_weather）
  - 选项C: 建议用户先运行数据采集器

行动: 返回最终答案
"抱歉，数据库中没有广雅中学站点在2025-10-20的历史气象数据。
建议：
1. 运行数据采集器填充历史数据：python run_fetcher_manual.py era5
2. 或使用实时天气数据进行分析"
```

## 改进原则总结

### 1. 显式优于隐式
- ❌ `"message": "未找到数据"` （LLM可能忽略）
- ✅ `"has_data": False` （明确的布尔值）

### 2. 摘要信息详细化
- ❌ `"summary": "查询成功"`
- ✅ `"summary": "⚠️ 数据库中没有站点 XX 在 YY 期间的观测气象数据"`

### 3. Schema包含完整的上下文
- ❌ 只说明参数类型
- ✅ 说明返回格式、字段含义、使用场景、注意事项

### 4. 提供通用的转换指导
- ❌ 硬编码："从get_weather_data的records中提取wind_direction_10m"
- ✅ 通用模式："如果源数据包含 wind_direction_* 字段，提取并重命名为 wd"

### 5. 明确失败条件
- ❌ LLM猜测何时不应该调用工具
- ✅ 在schema中明确说明："如果上游工具返回 has_data=False，不应调用本工具"

## 文件变更清单

### 修改的文件

1. **app/tools/query/get_weather_data/tool.py**
   - ✅ 增强function_schema描述（32-58行）
   - ✅ 添加has_data字段到返回格式（3处）
   - ✅ 改进summary字段（3处）

2. **app/tools/analysis/analyze_upwind_enterprises/tool.py**
   - ✅ 增强工具级别描述（50-58行）
   - ✅ 增强winds参数描述（66-84行）

### 新增的文件

3. **backend/docs/数据采集器使用指南.md**
   - ✅ 完整的使用指南文档
   - ✅ 系统架构说明
   - ✅ 5种使用方法
   - ✅ 故障排查指南

4. **backend/run_fetcher_manual.py**
   - ✅ 手动运行采集器的Python脚本
   - ✅ 支持单个或全部采集器
   - ✅ 完整的日志输出

## 后续建议

### 短期（本周）

1. **验证改进效果**
   - 重新运行 test_new_tools_e2e.py
   - 观察Agent在无数据情况下的行为
   - 确认LLM能正确识别 has_data=False

2. **填充测试数据**
   ```bash
   # 配置数据库连接
   export DATABASE_URL="postgresql+asyncpg://..."

   # 运行ERA5采集器（填充昨天的数据）
   python run_fetcher_manual.py era5

   # 运行观测数据采集器
   python run_fetcher_manual.py observed
   ```

3. **测试完整工作流**
   - 确保数据库有数据
   - 测试Agent能正确提取winds参数
   - 验证analyze_upwind_enterprises成功调用

### 中期（本月）

1. **扩展到其他工具**
   - 应用相同的改进原则到其他查询工具
   - 确保所有工具返回格式一致
   - 添加 has_data 和详细 summary

2. **增强数据转换层**
   - 考虑创建通用的数据转换工具
   - 提供参数构建辅助函数
   - 减少LLM的数据转换负担

3. **监控和优化**
   - 收集Agent调用失败的案例
   - 分析常见的参数构建错误
   - 持续优化schema描述

### 长期（下季度）

1. **数据治理**
   - 建立数据回填SOP
   - 自动化历史数据补充
   - 定期数据质量检查

2. **工具生态扩展**
   - 开发更多分析工具
   - 建立工具测试框架
   - 创建工具开发最佳实践

3. **Agent智能化**
   - 训练Agent处理数据缺失场景
   - 自动选择备用数据源
   - 智能推荐数据回填策略

## 总结

本次改进聚焦于**提高工具返回格式的可解释性**和**增强schema的指导性**，核心目标是让LLM能够：

1. ✅ **正确判断数据可用性**（has_data字段）
2. ✅ **理解空数据是正常情况**（summary说明）
3. ✅ **知道如何构建参数**（数据转换指导）
4. ✅ **知道何时不应该调用工具**（失败条件说明）

通过这些改进，即使数据库中暂时没有历史数据，Agent也能优雅地处理并给用户明确的反馈，而不是陷入重复失败的循环。

同时，提供了数据采集器使用指南和脚本，让用户可以轻松填充历史数据，从根本上解决数据缺失问题。

---

**改进日期**: 2025-11-02
**改进人**: Claude Code
**测试状态**: 待验证（需要实际运行测试）
