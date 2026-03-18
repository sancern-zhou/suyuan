# 正确架构：查询请求生成 vs 分析总结生成

## ✅ 正确的架构分离

### 1. **查询计划生成阶段** (ExpertPlanGenerator)

**文件位置**: `backend/app/agent/core/expert_plan_generator.py`

**职责**: 根据用户查询生成工具调用计划和参数

**使用的提示词**: `TOOL_SPECS` (工具规范定义)

**工作流程**:
```
用户查询 → LLM读取TOOL_SPECS → 生成工具调用计划 → 执行工具
```

**TOOL_SPECS 内容** (已正确添加 query_gd_suncere_city_hour):
```python
TOOL_SPECS = {
    "query_gd_suncere_city_hour": {
        "param_type": "structured",
        "required_params": ["cities", "start_time", "end_time"],
        "priority": 1,  # 最高优先级
        "description": "查询广东省多城市小时空气质量数据...",
        "params_desc": {
            "cities": "城市名称列表，如 ['广州', '深圳', '佛山', '东莞']...",
            "start_time": "开始时间，格式 'YYYY-MM-DD HH:MM:SS'",
            "end_time": "结束时间，格式 'YYYY-MM-DD HH:MM:SS'"
        },
        "example": {
            "cities": ["广州", "深圳", "佛山"],
            "start_time": "2026-02-01 00:00:00",
            "end_time": "2026-02-03 23:59:59"
        }
    },
    "get_jining_regular_stations": {
        "param_type": "natural_language",
        "required_param": "question",
        "priority": 2
    }
}
```

---

### 2. **分析总结生成阶段** (ComponentExecutor._generate_summary)

**文件位置**: `backend/app/agent/experts/component_executor.py`

**职责**: 根据工具执行结果生成专业分析报告

**使用的提示词**: `_get_summary_prompt()` 返回的提示词
- PM_SUMMARY_PROMPT (颗粒物溯源)
- OZONE_SUMMARY_PROMPT (臭氧溯源)
- GENERAL_SUMMARY_PROMPT (通用分析)

**工作流程**:
```
工具执行结果 → LLM读取分析提示词 → 生成专业分析报告
```

**分析提示词内容** (已删除工具说明):
- ✅ 包含：分析框架、化学机制、控制建议、专业术语
- ❌ 不包含：工具调用说明（已移除）

---

## 🔄 完整工作流程

### 用户查询: "分析广州PM2.5污染，对比周边深圳、佛山"

**阶段1: 查询计划生成** (ExpertPlanGenerator)
```python
# LLM读取 TOOL_SPECS，识别到 query_gd_suncere_city_hour
# 生成工具调用计划：
{
    "tool": "query_gd_suncere_city_hour",
    "params": {
        "cities": ["广州", "深圳", "佛山"],
        "start_time": "2026-02-01 00:00:00",
        "end_time": "2026-02-03 23:59:59"
    }
}
```

**阶段2: 工具执行**
```python
# 工具自动处理：
# 1. 城市名称 → 编码映射
# 2. 智能判断数据源
# 3. 调用官方API
# 4. 返回UDF v2.0数据
```

**阶段3: 分析总结生成** (ComponentExecutor._generate_summary)
```python
# LLM读取 PM_SUMMARY_PROMPT
# 基于工具执行结果生成分析报告：
"""
## 区域时序对比分析
广州PM2.5浓度在2月1日12时达到峰值（85 μg/m³），而深圳（70 μg/m³）
和佛山（90 μg/m³）在同一时间段也出现峰值...

成因诊断：本地生成主导（75%）+ 区域传输（25%）
"""
```

---

## ✅ 已完成的修改

### 1. ExpertPlanGenerator (查询阶段) ✅

**文件**: `backend/app/agent/core/expert_plan_generator.py`

**修改内容**:
- ✅ 添加 `query_gd_suncere_city_hour` 到 TOOL_SPECS (第69-90行)
- ✅ 删除 `get_guangdong_regular_stations` 从 TOOL_SPECS
- ✅ 调整优先级: query_gd_suncere (1) > jining (2) > air_quality (3)

**关键配置**:
```python
"query_gd_suncere_city_hour": {
    "param_type": "structured",  # 结构化参数
    "required_params": ["cities", "start_time", "end_time"],
    "priority": 1,  # 最高优先级
    "params_desc": {详细参数说明},
    "example": {实际使用示例},
    "features": [智能特性列表]
}
```

---

### 2. ComponentExecutor (分析阶段) ✅

**文件**: `backend/app/agent/experts/component_executor.py`

**修改内容**:
- ✅ 工具加载: 添加 `query_gd_suncere_city_hour` (第113-119行)
- ✅ 工具加载: 删除 `get_guangdong_regular_stations` (已移除)
- ✅ 统计提取: 修改工具名称判断 (第1064行)
- ❌ **删除分析提示词中的工具说明** (第695-726, 874-904, 1009-1039行)

**删除的内容** (不应该出现在分析提示词中):
```
【区域对比查询工具】  ← 删除
1. **query_gd_suncere_city_hour** ...  ← 删除
2. **get_jining_regular_stations** ...  ← 删除
```

**保留的内容** (应该出现在分析提示词中):
```
【分析框架】
1. **区域时序对比分析**（判断本地生成vs区域传输）
2. **颗粒物组分诊断**
【颗粒物数据查询工具】（组分查询工具，与区域对比工具不同）
```

---

## 📊 架构对比

| 特性 | 查询计划生成 (ExpertPlanGenerator) | 分析总结生成 (ComponentExecutor) |
|------|-----------------------------------|----------------------------------|
| **文件** | `expert_plan_generator.py` | `component_executor.py` |
| **提示词** | `TOOL_SPECS` | `PM_SUMMARY_PROMPT` 等 |
| **职责** | 生成工具调用计划和参数 | 生成专业分析报告 |
| **输入** | 用户自然语言查询 | 工具执行结果 |
| **输出** | 工具调用计划 (tool + params) | 专业分析报告 (Markdown) |
| **LLM角色** | 参数生成器 | 专家分析师 |
| **是否需要工具说明** | ✅ 是（TOOL_SPECS） | ❌ 否（只需分析框架） |

---

## 🎯 为什么要分离？

### ❌ 错误做法 (混在一起)
```python
PM_SUMMARY_PROMPT = """
你是颗粒物分析专家...

【区域对比查询工具】  ← 错误！分析阶段不需要
1. **query_gd_suncere_city_hour** - 广东省查询...
   参数: cities, start_time, end_time...
"""
```

**问题**:
- LLM在生成分析报告时，不需要知道如何调用工具
- 工具已经执行完毕，只需要分析结果
- 增加无用的token消耗

### ✅ 正确做法 (分离)

**查询阶段** (ExpertPlanGenerator):
```python
TOOL_SPECS = {
    "query_gd_suncere_city_hour": {
        "params_desc": {...},  # 详细参数说明
        "example": {...}       # 实际使用示例
    }
}
```

**分析阶段** (ComponentExecutor):
```python
PM_SUMMARY_PROMPT = """
你是颗粒物分析专家...

【分析框架】
1. **区域时序对比分析**  # 只需要分析方法
2. **颗粒物组分诊断**    # 不需要工具调用说明
"""
```

---

## ✅ 验证清单

- [x] `query_gd_suncere_city_hour` 添加到 ExpertPlanGenerator.TOOL_SPECS
- [x] `get_guangdong_regular_stations` 从 TOOL_SPECS 删除
- [x] `query_gd_suncere_city_hour` 添加到 ComponentExecutor._load_tools()
- [x] `get_guangdong_regular_stations` 从 _load_tools() 删除
- [x] 分析提示词中删除工具调用说明（PM/O3/通用提示词）
- [x] 统计信息提取逻辑更新 (tool_name 判断)

---

## 🚀 结论

**正确的架构**:
1. **查询阶段**: TOOL_SPECS 包含工具调用说明 ✅
2. **分析阶段**: 分析提示词只包含分析框架 ✅

**LLM理解能力**:
- ✅ 查询阶段：LLM通过 TOOL_SPECS 理解如何生成结构化参数
- ✅ 分析阶段：LLM通过分析提示词理解如何生成专业报告

**Token优化**:
- 查询阶段：只需要工具规范（TOOL_SPECS）
- 分析阶段：只需要分析框架（不需要工具说明）

---

**架构已正确分离，修改完成！**
