# 子Agent标准返回格式修复总结

**修复日期**: 2026-05-08
**问题来源**: 技能文档分析发现的问题

## 问题描述

技能文档《昨日污染特征与溯源分析》要求助理子Agent收集query/expert/chart子Agent返回的data_id，但系统存在以下问题：

1. **无标准返回格式**：各模式子Agent没有明确的data_id返回规范
2. **文档不一致**：技能文档要求"在goal中要求返回data_id"，但系统提示词中没有相关指令
3. **提取位置混乱**：call_sub_agent虽然能提取data_id，但子Agent不知道需要明确列出
4. **责任不清**：助理子Agent不知道从哪里获取data_id

## 修复方案

### 1. 创建标准返回格式规范

**文件**: `backend/docs/agent_guide/sub_agent_response_format.md`

**内容**：
- 定义了query/expert/chart/assistant四种子Agent的标准返回格式
- 明确data_id提取规则（从哪些字段提取）
- 提供正确/错误示例
- 说明父Agent收集机制
- 特殊情况处理（无data_id、部分失败）

### 2. 更新系统提示词

#### query_prompt.py
在"数据展示规范"后添加：
```markdown
## ⚠️ 子Agent返回格式规范（CRITICAL）

**当作为子Agent被调用时**，必须在最终回复中明确列出所有data_id：

## 查询结果
[数据展示...]

**数据溯源**：
- data_id: xxx-xxx (数据说明)
- data_id: yyy-yyy (数据说明)
```

#### expert_prompt.py
在"工作流工具"后添加：
```markdown
### ⚠️ 子Agent返回格式规范（CRITICAL）

**当作为子Agent被调用时**，必须在最终回复中明确列出所有data_id：

## 分析结果
[分析内容...]

**数据溯源**：
- data_id: xxx-xxx (查询数据)
- data_id: yyy-yyy (分析结果)
- data_id: zzz-zzz (图表数据)
```

#### chart_prompt.py
在"工作原则"后添加：
```markdown
## ⚠️ 子Agent返回格式规范（CRITICAL）

**当作为子Agent被调用时**，必须在最终回复中明确列出所有data_id：

## 图表生成结果
[图表配置...]

**数据溯源**：
- 输入数据: data_id (原始数据)
- 图表配置: data_id (图表配置，如有)
```

### 3. 增强call_sub_agent机制

**文件**: `backend/app/tools/agent_tools/call_sub_agent.py`

在`_build_child_system_prompt`方法末尾添加：
```python
# ⚠️ 添加data_id返回要求（所有子Agent必须遵守）
parts.append("\n## ⚠️ 子Agent返回格式要求（CRITICAL）\n")
parts.append("**必须在最终回复中明确列出所有data_id**，格式如下：\n")
parts.append("```markdown\n")
parts.append("**数据溯源**：\n")
parts.append("- data_id: xxx-xxx (说明)\n")
parts.append("- data_id: yyy-yyy (说明)\n")
parts.append("```\n\n")
parts.append("**提取规则**：\n")
parts.append("- 从工具返回的 `data_id`、`metadata.data_id`、`data.data_ids` 字段提取\n")
parts.append("- 父Agent依赖此信息收集数据溯源\n")
parts.append("- 即使只有一个data_id也必须列出\n")
```

### 4. 更新技能文档

**文件**: `backend/docs/skills/昨日污染特征与溯源分析.md`

**修改前**：
```markdown
7. **数据溯源（data_id）**：所有query子Agent、expert子Agent、chart子Agent调用时，必须在goal/context_str中要求返回数据对应的data_id。

**data_id获取方式**：
- query子Agent：在goal末尾添加"请返回数据对应的data_id"
- expert子Agent：在goal末尾添加"请返回分析结论对应的data_id"
```

**修改后**：
```markdown
7. **数据溯源（data_id）**：所有子Agent调用时会自动返回data_id（通过call_sub_agent的data_ids字段）。助理子Agent必须从子Agent返回结果中提取data_id并写入report.qmd末尾的"数据溯源"章节，实现每个结论可追溯原始数据。详见《[子Agent标准返回格式规范](../agent_guide/sub_agent_response_format.md)》。

**data_id获取方式**（自动机制，无需在goal中特别要求）：
- ✅ **自动提取**：call_sub_agent工具自动从子Agent事件流中提取data_id，返回给父Agent
- ✅ **标准格式**：所有子Agent（query/expert/chart）都会按标准格式返回data_id（在系统提示词中已强制要求）
- ✅ **双重保障**：子Agent在回复中明确列出 + call_sub_agent自动提取

**data_id收集方式**（助理子Agent从调用结果中提取）：
result = call_sub_agent(target_mode="query", goal="查询全省21市昨日AQI数据")
data_ids = result["data"]["data_ids"]  # 自动提取的data_id列表
```

## 双重保障机制

为确保data_id不会丢失，采用双重保障：

### 1. 子Agent层面
在最终回复中明确列出data_id（LLM可见）

### 2. 父Agent层面
call_sub_agent自动从事件流中提取data_id（程序保障）

**提取逻辑**（已存在于`_extract_data_ids`方法）：
- 从`event["data_id"]`提取
- 从`event["data"]["data_id"]`提取
- 从`event["data"]["data_ids"]`提取
- 从`event["data"]["metadata"]["data_id"]`提取

## 修改文件清单

1. ✅ `backend/docs/agent_guide/sub_agent_response_format.md` - 新建
2. ✅ `backend/app/agent/prompts/query_prompt.py` - 修改
3. ✅ `backend/app/agent/prompts/expert_prompt.py` - 修改
4. ✅ `backend/app/agent/prompts/chart_prompt.py` - 修改
5. ✅ `backend/app/tools/agent_tools/call_sub_agent.py` - 修改
6. ✅ `backend/docs/skills/昨日污染特征与溯源分析.md` - 修改

## 验证方法

### 1. 检查系统提示词
```bash
grep "子Agent返回格式" backend/app/agent/prompts/*.py
```

预期输出：
- query_prompt.py: 包含"子Agent返回格式规范"
- expert_prompt.py: 包含"子Agent返回格式规范"
- chart_prompt.py: 包含"子Agent返回格式规范"

### 2. 检查call_sub_agent
```bash
grep -A 5 "子Agent返回格式要求" backend/app/tools/agent_tools/call_sub_agent.py
```

预期输出：包含data_id返回要求的代码块

### 3. 检查规范文档
```bash
ls -lh backend/docs/agent_guide/sub_agent_response_format.md
```

预期输出：文件存在且大小>0

## 使用示例

### 助理子Agent收集data_id

```python
# 调用query子Agent
result = call_sub_agent(
    target_mode="query",
    goal="查询全省21市昨日AQI数据",
    context_str="目标日期：2026-05-07"
)

# 提取data_id（call_sub_agent已自动提取）
data_ids = result["data"]["data_ids"]  # 列表，如['air_quality_5min:v1:abc...', ...]

# 写入report.qmd
edit_file(
    path="report.qmd",
    old_string="<!-- DATA_TRACE_START -->",
    new_string=f"""<!-- DATA_TRACE_START -->
| 任务 | data_id | 来源 |
|:---|:---:|:---:|
| 任务1：全省21市昨日日数据 | `{data_ids[0]}` | 问数模式 |
"""
)
```

### query子Agent返回data_id

```markdown
## 查询结果

| 城市 | AQI | PM2.5 | PM10 | O3 | NO2 | SO2 | CO |
|:---|---:|---:|---:|---:|---:|---:|---:|
| 广州 | 85 | 45 | 62 | 78 | 32 | 12 | 0.8 |
| 深圳 | 72 | 38 | 55 | 65 | 28 | 10 | 0.7 |
...（共21个城市）

---

**数据溯源**：
- data_id: air_quality_5min:v1:20260508_abc123... (昨日全省AQI数据)
```

## 后续建议

1. **P0（已完成）**：定义所有子Agent的标准返回格式 ✅
2. **P1（下一步）**：删除"并行调用"要求，改为串行
3. **P1（下一步）**：提供图表生成的具体模板/工具
4. **P1（下一步）**：明确TOP3城市的具体判断字段和逻辑
5. **P2（优化）**：统一使用绝对路径
6. **P2（优化）**：改进task_manifest.json的维护机制

## 相关文档

- [子Agent标准返回格式规范](backend/docs/agent_guide/sub_agent_response_format.md)
- [昨日污染特征与溯源分析技能](backend/docs/skills/昨日污染特征与溯源分析.md)
- [call_sub_agent工具](backend/app/tools/agent_tools/call_sub_agent.py)
