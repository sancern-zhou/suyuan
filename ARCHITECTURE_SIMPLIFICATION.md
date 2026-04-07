# 架构简化总结

## 删除的复杂组件（约 2300+ 行代码）

### 工作流工具（2个）
- ❌ `standard_analysis_workflow.py` - 标准分析工作流（使用 ExpertRouterV3）
- ❌ `quick_tracing_workflow.py` - 快速追踪工作流（继承 StandardAnalysisWorkflow）

### 专家路由器（1个）
- ❌ `expert_router_v3.py` - 复杂的专家路由器（约1000+行）
  - 多专家调度系统
  - 并行执行管理
  - 健康监控系统
  - WebSocket 实时推送

### 任务管理组件（4个）
- ❌ `task/task_list.py` - 任务列表管理器（339行）
  - 任务创建与状态管理
  - 依赖关系追踪
  - 进度计算
  - WebSocket 实时推送

- ❌ `task/models.py` - 任务数据模型（193行）
  - Task、TaskStatus、TaskTree
  - 复杂的依赖关系

- ❌ `task/checkpoint_manager.py` - 检查点管理器（402行）
  - 断点恢复
  - 任务持久化

- ❌ `task_planning_mixin.py` - 任务规划混合类（约200行）
  - 任务规划逻辑

- ❌ `react_agent_extended.py` - 扩展的 ReAct Agent（约150行）
  - 增强的任务管理功能

## 新的简化架构

### 核心流程
```
用户查询 → Agent 读取 md 模板
         ↓
    TodoWrite 创建任务计划
         ↓
      跟用户确认 ⚠️
         ↓
    ReAct 循环执行
         ↓
      生成综合报告
```

### 保留的核心组件

#### 1. 任务清单模板文件（2个）
- ✅ `config/task_lists/quick_trace_fast.md` - 快速溯源模板（18秒）
  - 4个核心任务
  - 严格顺序执行
  - 超时保护

- ✅ `config/task_lists/quick_trace_standard.md` - 标准溯源模板（3分钟）
  - 7个完整任务
  - 支持并行执行
  - 完整溯源流程

#### 2. TodoWrite 工具
- ✅ `task/todo_models.py` - TodoList 类
  - 简化的任务管理
  - 完整替换模式
  - 约束规则（最多20项、同时只能1个 in_progress）

#### 3. 提示词
- ✅ `expert_prompt.py` - 已更新为任务清单驱动流程
  - 原则性指导（不含具体示例）
  - 强调"跟用户确认"步骤

#### 4. 保留的工作流工具（3个）
- ✅ `quick_trace_workflow.py` - 告警响应快速溯源
  - 基于结构化参数（city、alert_time、pollutant、alert_value）
  - 用于系统自动触发的告警响应

- ✅ `deep_trace_workflow.py` - PMF+OBM深度分析
  - 深度源解析

- ✅ `knowledge_qa_workflow.py` - 知识问答
  - 基于知识库的专业问答

## 优势对比

### 旧架构（复杂）
```
用户查询 → ExpertRouterV3
         ↓
    自动创建任务列表（用户不可见）
         ↓
    多专家并行执行
         ↓
    WebSocket 推送状态
         ↓
      生成报告

复杂度：
- 2300+ 行代码
- 用户不可见任务规划过程
- 难以调整和扩展
```

### 新架构（简化）
```
用户查询 → Agent 读取 md 模板
         ↓
    TodoWrite 创建任务计划（用户可见）
         ↓
      跟用户确认
         ↓
    ReAct 循环执行
         ↓
      生成报告

复杂度：
- 2 个 md 模板文件
- 用户全程可见
- 易于调整和扩展
```

## 代码统计

| 组件 | 旧架构 | 新架构 | 减少 |
|------|--------|--------|------|
| 工作流工具 | 2个（复杂） | 0个 | -2个 |
| 专家路由器 | 1个（1000+行） | 0个 | -1000+行 |
| 任务管理 | 5个文件（1300+行） | 1个文件（180行） | -1100+行 |
| 模板文件 | 0个 | 2个（md） | +2个 |
| **总计** | **约2300+行** | **约180行** | **-2100+行** |

## 工作流程示例

### 快速溯源（18秒）
```python
# 用户输入
用户: 分析广州天河站今天O3高值来源

# Agent 执行流程
1. read_file(path='backend/config/task_lists/quick_trace_fast.md')
2. TodoWrite(items=[
     {'content': '定位站点：广州天河', 'status': 'pending'},
     {'content': '获取气象数据', 'status': 'pending'},
     {'content': '后向轨迹分析', 'status': 'pending'},
     {'content': '生成分析报告', 'status': 'pending'}
   ])
3. 展示任务计划，跟用户确认
4. 逐步执行，每完成一个任务更新 TodoWrite 状态
5. 生成综合报告
```

### 标准溯源（3分钟）
```python
# 用户输入
用户: 做一个完整的O3污染溯源分析，站点是广州天河

# Agent 执行流程
1. read_file(path='backend/config/task_lists/quick_trace_standard.md')
2. TodoWrite(items=[...])  # 7个任务
3. 展示任务计划，跟用户确认
4. 按依赖关系执行（支持并行）
5. 生成综合报告（包含图表）
```

## 测试验证

✅ ReActAgent 导入成功
✅ TodoWrite 工具正常工作
✅ 工作流工具正常注册：
  - quick_trace_workflow
  - deep_trace_workflow
  - knowledge_qa_workflow
✅ 共 70 个工具成功加载
✅ 无遗留引用

## 下一步

1. **测试新流程**：
   - 发送查询："分析广州天河站今天O3高值来源"
   - 观察 Agent 是否读取 md 模板
   - 检查 TodoWrite 任务计划
   - 验证用户确认步骤

2. **调整模板**（如需要）：
   - 编辑 `quick_trace_fast.md` 或 `quick_trace_standard.md`
   - 添加新的任务步骤
   - 调整依赖关系

3. **监控运行**：
   - 观察任务执行顺序
   - 检查并行执行是否正确
   - 验证超时保护机制

## 关键文件位置

### 任务清单模板
- `/backend/config/task_lists/quick_trace_fast.md`
- `/backend/config/task_lists/quick_trace_standard.md`

### 提示词
- `/backend/app/agent/prompts/expert_prompt.py`

### TodoWrite 工具
- `/backend/app/tools/task_management/todo_write.py`
- `/backend/app/agent/task/todo_models.py`

### 工作流工具
- `/backend/app/tools/workflow/quick_trace_workflow.py` - 告警响应
- `/backend/app/tools/workflow/deep_trace_workflow.py` - 深度分析
- `/backend/app/tools/workflow/knowledge_qa_workflow.py` - 知识问答
