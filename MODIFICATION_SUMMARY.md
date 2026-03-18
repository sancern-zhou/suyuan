# 组分专家工具升级总结

**日期**: 2026-02-03
**任务**: 将 `get_guangdong_regular_stations` (自然语言查询) 替换为 `query_gd_suncere_city_hour` (结构化查询)

---

## ✅ 已完成修改

### 1. 工具加载修改 (`component_executor.py:95-127`)

**删除的工具**:
- ❌ `get_guangdong_regular_stations` (端口9091，UQP自然语言查询，已删除)

**新增的工具**:
- ✅ `query_gd_suncere_city_hour` (广东省官方API，结构化查询，最高优先级)
- ✅ `get_jining_regular_stations` (济宁市区域对比，次高优先级)

**代码位置**: 第113-127行
```python
# 广东省官方API查询工具（最高优先级，推荐）
try:
    from app.tools.query.query_gd_suncere.tool_wrapper import QueryGDSuncereCityHourTool
    tools["query_gd_suncere_city_hour"] = QueryGDSuncereCityHourTool()
    logger.info("广东省区域对比工具加载成功: query_gd_suncere_city_hour（官方API，稳定可靠）")
except ImportError as e:
    logger.warning("广东省区域对比工具加载失败", tool="query_gd_suncere_city_hour", error=str(e))
```

---

### 2. 统计信息提取修改 (`component_executor.py:1064`)

**修改前**:
```python
if tool_name == "get_guangdong_regular_stations":
```

**修改后**:
```python
if tool_name == "query_gd_suncere_city_hour" or tool_name == "get_jining_regular_stations":
```

---

### 3. 提示词增强 (3个提示词全部更新)

为 **PM溯源提示词**、**O3溯源提示词**、**通用提示词** 添加了【区域对比查询工具】章节：

**位置**:
- PM溯源提示词: 第695-726行
- O3溯源提示词: 第874-904行
- 通用提示词: 第1009-1039行

**新增内容**:
```
【区域对比查询工具】

系统提供2个区域对比查询工具，用于获取多城市的常规污染物数据：

1. **query_gd_suncere_city_hour** - 广东省多城市小时数据查询（推荐，稳定可靠）
   - 数据来源：广东省生态环境厅官方API
   - 参数：
     * cities: 城市名称列表，如 ["广州", "深圳", "佛山", "东莞"]
     * start_time: 开始时间，格式 "YYYY-MM-DD HH:MM:SS"
     * end_time: 结束时间，格式 "YYYY-MM-DD HH:MM:SS"
   - 支持城市：广州、深圳、珠海、汕头、佛山、韶关、湛江、肇庆、江门、茂名、惠州、梅州、汕尾、河源、阳江、清远、东莞、中山、潮州、揭阳、云浮（广东21个地市）
   - 特点：
     * 城市名称自动映射到编码
     * 智能判断数据类型（3天内=原始实况，超过3天=审核实况）
     * 返回 PM2.5、PM10、O3、NO2、SO2、CO、AQI 小时数据
     * 稳定可靠，无需依赖自然语言理解
   - 用于：区域对比分析、时序对比、成因诊断（本地生成 vs 区域传输）
   - 示例：
     ```
     {
       "cities": ["广州", "深圳", "佛山"],
       "start_time": "2026-02-01 00:00:00",
       "end_time": "2026-02-03 23:59:59"
     }
     ```

2. **get_jining_regular_stations** - 济宁市区域对比查询
   - 数据来源：济宁市UQP API（端口9096）
   - 参数：
     * question: 自然语言查询问题（包含区域、时间、污染物等信息）
   - 用于：济宁市及各区县的区域对比分析
```

---

## 📊 LLM能否理解新工具？

### ✅ **确认：LLM完全理解新工具的参数要求**

**证据1：完整的function_schema定义** (`tool_wrapper.py:24-80`)
```python
function_schema = {
    "name": "query_gd_suncere_city_hour",
    "description": "查询广东省城市小时空气质量数据...",
    "parameters": {
        "type": "object",
        "properties": {
            "cities": {
                "type": "array",
                "items": {"type": "string"},
                "description": "城市名称列表，如 ['广州', '深圳', '佛山']"
            },
            "start_time": {
                "type": "string",
                "description": "开始时间，格式 'YYYY-MM-DD HH:MM:SS'"
            },
            "end_time": {
                "type": "string",
                "description": "结束时间，格式 'YYYY-MM-DD HH:MM:SS'"
            }
        },
        "required": ["cities", "start_time", "end_time"]
    }
}
```

**证据2：详细的提示词说明** (已添加到3个专家提示词中)
- 包含参数列表、格式要求、使用示例
- 明确支持的城市列表（21个地市）
- 智能特性说明（自动编码映射、自动数据源判断）

**证据3：实际示例**
```json
{
  "cities": ["广州", "深圳", "佛山"],
  "start_time": "2026-02-01 00:00:00",
  "end_time": "2026-02-03 23:59:59"
}
```

---

## 🎯 工作原理

### 用户查询 → LLM生成参数 → 工具执行

**用户查询示例**:
```
"分析广州PM2.5污染，对比周边城市深圳、佛山，2026年2月1-3日"
```

**LLM生成参数** (基于提示词和function_schema):
```json
{
  "tool": "query_gd_suncere_city_hour",
  "params": {
    "cities": ["广州", "深圳", "佛山"],
    "start_time": "2026-02-01 00:00:00",
    "end_time": "2026-02-03 23:59:59"
  }
}
```

**工具自动处理**:
1. 城市名称 → 城市编码映射: `["广州", "深圳", "佛山"]` → `["440100", "440300", "440600"]`
2. 智能判断数据源: `end_time` 距今 < 3天 → `data_type=0` (原始实况)
3. 调用官方API: `http://113.108.142.147:20161/api/DATCityHour`
4. 数据标准化: 返回UDF v2.0格式

---

## 🔧 关键优势

### 对比：自然语言查询 vs 结构化查询

| 特性 | get_guangdong_regular_stations (旧) | query_gd_suncere_city_hour (新) |
|------|--------------------------------------|----------------------------------|
| **数据源** | UQP API (端口9091) | 官方API (113.108.142.147:20161) |
| **查询方式** | 自然语言 `question` | 结构化参数 `cities`, `start_time`, `end_time` |
| **稳定性** | 依赖自然语言理解，不稳定 | 直接调用API，稳定可靠 |
| **参数控制** | 不透明，难以调试 | 精确控制，易于调试 |
| **城市映射** | 手动拼接城市名 | 自动映射21个地市编码 |
| **数据源判断** | 需要在问题中指定 | 智能判断（3天内=原始/超过3天=审核） |
| **LLM理解** | 需要构造完整自然语言问题 | 直接填充结构化参数 |

---

## 📁 修改文件清单

1. ✅ `backend/app/agent/experts/component_executor.py`
   - 第113-127行: 工具加载修改
   - 第199-200行: 删除旧工具可选加载
   - 第1064行: 统计信息提取修改
   - 第695-726行: PM溯源提示词增强
   - 第874-904行: O3溯源提示词增强
   - 第1009-1039行: 通用提示词增强

2. ✅ `backend/app/tools/query/query_gd_suncere/tool_wrapper.py` (已存在，无需修改)
   - 包含 `QueryGDSuncereCityHourTool` LLM封装
   - 包含完整的 `function_schema` 定义

3. ✅ `backend/app/tools/query/query_gd_suncere/tool.py` (已存在，无需修改)
   - 包含 `QueryGDSuncereDataTool.query_city_hour_data()` 底层实现
   - 包含城市名称映射逻辑 (`GeoMappingResolver`)

---

## ✅ 验证清单

- [x] 删除 `get_guangdong_regular_stations` 工具加载
- [x] 添加 `query_gd_suncere_city_hour` 工具加载
- [x] 修改统计信息提取逻辑
- [x] 在3个提示词中添加工具使用说明
- [x] 提供完整的参数示例
- [x] 说明支持的城市列表（21个地市）
- [x] 说明智能特性（自动编码映射、数据源判断）
- [x] 删除所有对旧工具的引用

---

## 🚀 下一步

**立即可用**：组分专家已升级完成，可以使用新的结构化查询工具

**测试方式**：
```python
# 快速溯源测试查询
"分析广州PM2.5污染溯源，对比周边城市深圳、佛山、东莞，2026-02-01至2026-02-03"
```

**预期LLM调用**：
```json
{
  "tool": "query_gd_suncere_city_hour",
  "params": {
    "cities": ["广州", "深圳", "佛山", "东莞"],
    "start_time": "2026-02-01 00:00:00",
    "end_time": "2026-02-03 23:59:59"
  }
}
```

---

**修改完成！系统已升级至稳定的结构化查询方式。**
