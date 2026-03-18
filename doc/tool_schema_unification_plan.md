# 工具Schema统一方案

## 问题诊断

### 当前状态：Schema不一致
- **TOOL_DESCRIPTIONS**: 使用结构化参数（location, pollutant, start_time, end_time）
- **实际工具Schema**: 使用自然语言查询（question）
- **结果**: LLM不知道该怎么传参

### 影响范围
检查了14个工具：
- ❌ `get_air_quality` - 只有 question 参数
- ❌ `get_weather_data` - 需要检查
- ✅ `analyze_upwind_enterprises` - 有完整结构化参数
- ❌ 其他工具可能也有类似问题

## 解决方案

### 方案1: 统一为结构化参数（推荐）

**原则**: 让LLM使用结构化参数，便于验证和适配

#### 1. get_air_quality 工具Schema优化
```python
{
  "name": "get_air_quality",
  "description": "查询指定城市的空气质量数据",
  "parameters": {
    "type": "object",
    "properties": {
      "location": {
        "type": "string",
        "description": "监测站点名称（如：广州、天河站、南山站）"
      },
      "pollutant": {
        "type": "string",
        "enum": ["AQI", "PM2.5", "PM10", "O3", "NO2", "SO2", "CO"],
        "description": "污染物类型，枚举值"
      },
      "start_time": {
        "type": "string",
        "description": "开始时间（格式：YYYY-MM-DD 或 YYYY-MM-DD HH:MM:SS）"
      },
      "end_time": {
        "type": "string",
        "description": "结束时间（格式：YYYY-MM-DD 或 YYYY-MM-DD HH:MM:SS）"
      }
    },
    "required": ["location", "pollutant", "start_time", "end_time"]
  }
}
```

#### 2. 工具描述更新
- 更新 `TOOL_DESCRIPTIONS` 与实际Schema一致
- 删除 "支持自然语言查询" 描述
- 明确参数类型和枚举值

#### 3. 内部实现调整
```python
class GetAirQualityTool(LLMTool):
    def __init__(self):
        function_schema = {
            "name": "get_air_quality",
            "description": "查询指定城市的空气质量数据",
            "parameters": {  # 详细的结构化参数定义
                "type": "object",
                "properties": {
                    "location": {"type": "string", "description": "..."},
                    "pollutant": {
                        "type": "string",
                        "enum": ["AQI", "PM2.5", "PM10", "O3", "NO2", "SO2", "CO"],
                        "description": "..."
                    },
                    "start_time": {"type": "string", "description": "..."},
                    "end_time": {"type": "string", "description": "..."}
                },
                "required": ["location", "pollutant", "start_time", "end_time"]
            }
        }
        super().__init__(..., function_schema=function_schema)

    async def execute(self, location: str, pollutant: str, start_time: str, end_time: str):
        # 将自然语言解析逻辑移到这里
        # LLM不需要传自然语言，内部处理
        return self._parse_and_query(location, pollutant, start_time, end_time)
```

### 方案2: 保持自然语言但提供双模式

```python
{
  "name": "get_air_quality",
  "description": "查询指定城市的空气质量数据",
  "parameters": {
    "type": "object",
    "properties": {
      "query_type": {
        "type": "string",
        "enum": ["natural_language", "structured"],
        "description": "查询类型：自然语言或结构化参数"
      },
      "question": {
        "type": "string",
        "description": "自然语言查询（当query_type='natural_language'时使用）"
      },
      "location": {
        "type": "string",
        "description": "监测站点名称（当query_type='structured'时使用）"
      },
      "pollutant": {
        "type": "string",
        "enum": ["AQI", "PM2.5", "PM10", "O3", "NO2", "SO2", "CO"],
        "description": "污染物类型（当query_type='structured'时使用）"
      }
      # ... 其他结构化参数
    },
    "required": ["query_type"]
  }
}
```

## 实施计划

### Phase 1: Schema审计（0.5天）
- [ ] 检查所有14个工具的Schema定义
- [ ] 识别不一致的工具
- [ ] 制定统一方案

### Phase 2: Schema修正（2天）
- [ ] 更新 get_air_quality 为结构化参数
- [ ] 更新 get_weather_data 为结构化参数
- [ ] 更新其他不一致的工具
- [ ] 更新 TOOL_DESCRIPTIONS

### Phase 3: 集成测试（0.5天）
- [ ] 测试Schema生成是否正确
- [ ] 测试LLM能否正确调用工具
- [ ] 验证参数验证是否有效

### Phase 4: 文档更新（0.5天）
- [ ] 更新工具使用文档
- [ ] 编写Schema变更日志
- [ ] 更新示例代码

## 检查清单

### 必须统一的工具
- [ ] get_air_quality - question → location/pollutant/start_time/end_time
- [ ] get_weather_data - 需要检查
- [ ] get_vocs_components - 需要检查
- [ ] get_particulate_components - 需要检查
- [ ] get_nearby_stations - 需要检查
- [ ] generate_chart - 参数是否清晰
- [ ] generate_map - 参数是否清晰

### 已经有清晰Schema的工具
- [x] analyze_upwind_enterprises - 结构化参数完整
- [x] calculate_pmf - 有详细参数定义
- [x] calculate_obm_ofp - 有详细参数定义
- [x] smart_chart_generator - 有data_id参数定义

## 预期收益

1. **明确性**: LLM知道每个工具需要什么参数
2. **验证性**: 可以验证参数类型和枚举值
3. **一致性**: Schema与文档描述一致
4. **可维护性**: 更容易调试和修改

## 关键原则

> **不要让LLM猜** - 所有工具参数必须有明确的类型、枚举值和描述
>
> **结构化优先** - 尽量使用结构化参数而非自然语言
>
> **Schema与文档一致** - TOOL_DESCRIPTIONS必须反映实际Schema
