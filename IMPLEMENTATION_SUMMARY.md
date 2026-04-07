# 任务清单驱动的快速溯源系统 - 实施总结

## 实施日期
2026-03-29

## 实施概述

成功实现了任务清单驱动的快速溯源系统。该系统采用简化设计，主要依赖 LLM 的原生能力来理解和执行 Markdown 格式的任务清单，最小化代码改动。

## 核心设计原则

1. **LLM 原生能力优先**：不需要专门的解析器和规划器
2. **Markdown 作为 DSL**：用户可读可编辑，Agent 可理解可执行
3. **复用现有工具**：不创建新的管理工具和 API
4. **最小化改动**：主要工作是创建模板和更新提示词

## 实施内容

### 1. 新增文件（5个）

#### 任务清单模板
- `backend/config/task_lists/.gitkeep` - 目录跟踪文件
- `backend/config/task_lists/quick_trace_standard.md` - 标准快速溯源模板（6个任务）
- `backend/config/task_lists/quick_trace_fast.md` - 快速溯源模板（4个任务）

#### 用户模板示例
- `backend_data_registry/task_templates/custom_trace_example.md` - 自定义模板示例

#### 测试文件
- `backend/tests/test_task_list_system.py` - 系统测试脚本（6个测试用例）

#### 文档
- `backend/docs/task_list_system_guide.md` - 使用指南

### 2. 修改文件（2个）

#### 提示词更新
- `backend/app/agent/prompts/expert_prompt.py`
  - 添加"任务清单驱动的分析流程"章节
  - 包含模板路径、执行指南、并行执行提示

- `backend/app/agent/prompts/social_prompt.py`
  - 添加"任务清单功能"章节
  - 说明如何读取模板和委托给专家模式

## 任务清单模板格式

### 标准结构
```markdown
# 任务清单名称

## 说明
简要描述此任务清单的用途和适用场景。

## 全局参数
| 参数 | 说明 | 示例 | 必填 |
|------|------|------|------|

## 任务列表
### 第1步：任务名称
- 工具：`tool_name`
- 参数：参数说明
- 依赖：依赖说明
- 输出变量：变量名
- 可选：是/否
- 说明：任务说明

## Agent 执行指南
指导 Agent 如何执行这些任务的详细说明。
```

### 快速溯源标准版任务（6个）
1. 定位站点 - `get_nearby_stations`
2. 获取气象数据 - `get_weather_data`
3. 后向轨迹分析 - `meteorological_trajectory_analysis`
4. 上风向企业分析 - `analyze_upwind_enterprises`（可选）
5. 污染物组分分析 - `get_vocs_data` 或 `get_pm25_ionic`（可选）
6. 生成可视化图表 - `generate_chart` 或 `smart_chart_generator`

### 快速溯源快速版任务（4个）
1. 定位站点
2. 获取气象数据
3. 后向轨迹分析
4. 生成分析报告

## 系统工作流程

### 专家模式
```
用户请求 → 读取模板 → 创建 TodoWrite → 执行任务 → 更新进度 → 生成报告
```

### 社交模式
```
用户询问 → 读取模板 → 展示内容 → 用户确认 → 委托专家模式 → 返回结果
```

## 测试结果

所有6个测试用例通过：
1. ✓ 模板文件存在性验证
2. ✓ 模板内容格式验证
3. ✓ TodoWrite 工具可用性验证
4. ✓ 提示词文件更新验证
5. ✓ 文件操作工具可用性验证
6. ✓ TodoWrite 工具执行验证

## 复用的现有组件

| 组件 | 用途 |
|------|------|
| `read_file` | 读取任务清单模板 |
| `write_file` | 保存自定义模板 |
| `glob` | 列出可用模板 |
| `TodoWrite` | 显示任务进度 |
| `TaskList` | 状态追踪和 WebSocket 推送 |
| `call_sub_agent` | 社交模式委托专家模式 |
| 现有分析工具 | 执行具体任务 |

## 关键特性

### 1. 任务依赖关系
- 通过"依赖"字段明确定义
- Agent 自动识别并遵守依赖关系

### 2. 可选任务
- 可选任务失败不阻止整体执行
- 适用于可能缺失的数据源

### 3. 并行执行
- 无依赖关系的任务可并行执行
- Agent 自动识别并行机会

### 4. 数据传递
- 通过 `data_id` 在任务之间传递数据
- 支持复杂的数据流

## 与现有系统的区别

| 特性 | 现有工作流工具 | 任务清单系统 |
|------|--------------|-------------|
| 灵活性 | 固定流程 | 用户可自定义 |
| 透明度 | 不透明 | 用户可查看 |
| 可复用性 | 难以复用 | 易于保存和重用 |
| 代码改动 | 需要编码 | 只需编辑 Markdown |
| 实施难度 | 中等 | 简单 |

## 使用示例

### 专家模式
```
用户：执行快速溯源分析，站点：广州天河，污染物：O3

Agent：
1. read_file(path='config/task_lists/quick_trace_standard.md')
2. TodoWrite(items=[...])
3. get_nearby_stations(station_name='广州天河')
4. get_weather_data(...)
5. meteorological_trajectory_analysis(...)
6. analyze_upwind_enterprises(...)
7. generate_chart(...)
```

### 社交模式
```
用户：快速溯源分析包含哪些步骤？

Agent：读取模板并友好展示步骤列表

用户：好的，执行广州天河的O3溯源

Agent：call_sub_agent(target_mode='expert', task_description='...')
```

## 扩展建议

### 未来可能的增强
1. 模板格式自动验证
2. Web 界面可视化编辑
3. 模板导入导出和分享
4. 执行历史记录
5. 智能任务顺序推荐

### 创建新模板
1. 复制现有模板
2. 修改任务定义
3. 测试 Agent 理解能力
4. 保存到适当目录

## 技术优势

1. **简单性**：主要依赖 LLM 原生能力
2. **灵活性**：用户可自由编辑模板
3. **透明性**：流程清晰可见
4. **可维护性**：最小化代码改动
5. **可扩展性**：易于添加新模板

## 文件清单

### 新增文件
```
backend/config/task_lists/.gitkeep
backend/config/task_lists/quick_trace_standard.md
backend/config/task_lists/quick_trace_fast.md
backend_data_registry/task_templates/custom_trace_example.md
backend/tests/test_task_list_system.py
backend/docs/task_list_system_guide.md
```

### 修改文件
```
backend/app/agent/prompts/expert_prompt.py
backend/app/agent/prompts/social_prompt.py
```

## 总结

成功实现了任务清单驱动的快速溯源系统，采用简化设计，主要依赖 LLM 原生能力，最小化代码改动。系统提供了：

- 用户友好的 Markdown 格式
- 灵活的任务定义和依赖管理
- 实时的进度反馈
- 易于扩展和自定义

所有测试通过，系统可以正常使用。
