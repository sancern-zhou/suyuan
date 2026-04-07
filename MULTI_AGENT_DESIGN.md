# 多专家子Agent系统设计方案

## 更新时间
2026-03-29 21:15

## 核心思想

**直接调用子Agent，把相关数据的 data_id 和提示词的 md 文件传递给子Agent**

```
主Agent（调度者）
  ↓ 读取任务清单
  ↓ 执行任务
  ↓ call_sub_agent(
       target_mode="expert",
       task_description="分析气象条件",
       context={
         "expert_prompt_file": "prompts/weather_expert.md",
         "data_ids": ["station_info:xxx"]
       }
     )
  ↓ 子Agent（气象专家）
     ├─ 读取提示词文件
     ├─ 读取数据（通过 data_id）
     ├─ 生成专业分析报告
     └─ 返回结果
  ↓ 继续执行其他任务
```

## 优势分析

### 1. 真正的多专家系统 ✅
- 每个专家有**独立的提示词文件**
- 每个专家有**独立的子Agent**
- 每个专家**专注于自己的领域**
- 避免 Agent 角色混乱

### 2. 分析专业性 ✅
- **气象专家**：专注于气象分析、边界层、扩散条件
- **轨迹专家**：专注于轨迹分析、来源推断、传输过程
- **化学专家**：专注于组分分析、源解析、化学机制
- **报告专家**：专注于汇总分析、综合结论、管控建议

### 3. 数据传递高效 ✅
- 通过 **data_id** 传递数据
- 避免重复查询
- 上下文完整
- 链路清晰

### 4. 用户可见 ✅
- 用户可以看到每个专家的工作
- 用户可以看到专家的分析结果
- 增强信任感

### 5. 易于维护 ✅
- 专家提示词独立存储（md 文件）
- 可以随时调整和优化
- 不需要修改代码

## 架构设计

### 文件结构

```
backend/
├── config/
│   ├── prompts/                    # 专家提示词文件
│   │   ├── weather_expert.md       # 气象专家提示词
│   │   ├── trajectory_expert.md    # 轨迹专家提示词
│   │   ├── chemical_expert.md      # 化学专家提示词
│   │   └── report_expert.md        # 报告专家提示词
│   └── task_lists/                 # 任务清单模板
│       └── quick_trace_standard_multi_agent.md
└── app/
    └── agent/
        ├── react_agent.py          # 主Agent（调度者）
        └── prompts/
            └── expert_prompt.py     # 主Agent提示词
```

### 数据流

```
用户查询
  ↓
主Agent（调度者）
  ↓ 读取任务清单模板
  ↓ 创建任务计划（TodoWrite）
  ↓ 跟用户确认
  ↓ 执行任务1：定位站点
  ├─ get_nearby_stations(...)
  └─ 返回 data_id: "station_info:xxx"
  ↓
  执行任务2：气象数据分析
  ├─ call_sub_agent(
  │    target_mode="expert",
  │    task_description="分析气象条件",
  │    context={
  │      "expert_prompt_file": "prompts/weather_expert.md",
  │      "data_ids": ["station_info:xxx"]
  │    }
  │  )
  └─ 子Agent（气象专家）
     ├─ 读取提示词文件：prompts/weather_expert.md
     ├─ 读取数据：data_id = "station_info:xxx"
     ├─ 调用工具：get_weather_data(...)
     ├─ 生成专业报告（MD格式）
     └─ 返回 data_id: "weather_analysis:xxx"
  ↓
  执行任务3：后向轨迹分析
  ├─ call_sub_agent(...)
  └─ 子Agent（轨迹专家）
     ├─ 读取提示词文件：prompts/trajectory_expert.md
     ├─ 读取数据：data_ids = ["station_info:xxx", "weather_analysis:xxx"]
     ├─ 调用工具：meteorological_trajectory_analysis(...)
     ├─ 生成专业报告（MD格式）
     └─ 返回 data_id: "trajectory_analysis:xxx"
  ↓
  执行任务6：生成综合报告
  ├─ call_sub_agent(...)
  └─ 子Agent（报告专家）
     ├─ 读取提示词文件：prompts/report_expert.md
     ├─ 读取所有数据：所有 data_ids
     ├─ 汇总所有专家的章节
     ├─ 生成综合溯源结论
     ├─ 生成管控建议
     └─ 返回完整报告（MD格式）
  ↓
  返回给用户
```

## 专家提示词文件

### 1. 气象专家（weather_expert.md）
- **专业领域**：气象条件分析、大气边界层、扩散条件
- **核心职责**：
  - 气象要素分析（温度、湿度、风速、风向）
  - 大气边界层分析（边界层高度、大气稳定性、逆温层）
  - 污染扩散条件评估（水平扩散、垂直扩散）
  - 气象条件等级评价（优/良/差）
- **专业术语**：
  - 边界层高度（PBL）
  - 大气稳定性
  - 逆温层
  - 风速切变
  - 混合层高度
  - 通风系数

### 2. 轨迹专家（trajectory_expert.md）
- **专业领域**：后向轨迹分析、污染来源推断
- **核心职责**：
  - 轨迹特征分析（路径、高度、速度）
  - 污染来源推断（方向、区域、距离）
  - 传输过程分析（路径、高度、气象条件）
  - 来源贡献评估（区域传输、本地贡献）
- **专业术语**：
  - 后向轨迹（Backward Trajectory）
  - 轨迹高度
  - 轨迹路径
  - 传输距离
  - 轨迹聚类

### 3. 化学专家（chemical_expert.md）
- **专业领域**：污染物组分分析、源解析
- **核心职责**：
  - 组分特征分析（浓度水平、时间变化、组成特征）
  - 关键组分识别（优势组分、活性组分、指示物组分）
  - 源解析（工业源、交通源、天然源、溶剂使用）
  - 化学机制分析（前体物、转化条件、生成机制）
- **专业术语**：
  - VOCs（挥发性有机物）
  - 光化学活性
  - OFV（臭氧生成潜势）
  - 二次有机气溶胶（SOA）
  - 源解析

### 4. 报告专家（report_expert.md）
- **专业领域**：汇总专家分析、综合溯源结论、管控建议
- **核心职责**：
  - 汇总专家分析（汇总所有专家的结果）
  - 综合溯源结论（主要来源、贡献比例、关键因素）
  - 管控建议（近期措施、中长期建议、监测建议）
  - 报告质量检查（逻辑一致性、结论明确性、建议可行性）
- **专业能力**：
  - 综合分析能力
  - 逻辑推理能力
  - 政策理解能力
  - 风险评估能力

## call_sub_agent 调用示例

### 标准格式

```python
call_sub_agent(
    target_mode="expert",
    task_description="分析气象条件对污染扩散的影响",
    context={
        "expert_prompt_file": "backend/config/prompts/weather_expert.md",
        "data_ids": ["station_info:xxx"]
    }
)
```

### 参数说明

#### target_mode
- **值**：`"expert"`
- **说明**：指定调用专家模式的子Agent

#### task_description
- **类型**：字符串
- **说明**：任务描述，子Agent会读取并理解
- **示例**：
  - "分析气象条件对污染扩散的影响"
  - "分析后向轨迹，追溯污染来源"
  - "分析污染物组分，推断污染来源"
  - "汇总所有专家分析，生成综合溯源报告"

#### context
- **类型**：字典
- **说明**：传递给子Agent的上下文信息
- **包含**：
  - `expert_prompt_file`：专家提示词文件路径
  - `data_ids`：需要使用的数据ID列表

### 子Agent工作流程

```python
# 子Agent收到调用后：
1. 读取 expert_prompt_file，了解专家角色和分析要求
2. 读取 data_ids 对应的数据
3. 根据 task_description 执行相应的工具调用
4. 按照提示词要求生成专业分析报告（MD格式）
5. 返回分析结果
```

## 实现步骤

### 第一步：创建专家提示词文件 ✅
- ✅ weather_expert.md
- ✅ trajectory_expert.md
- ✅ chemical_expert.md
- ✅ report_expert.md

### 第二步：创建任务清单模板 ✅
- ✅ quick_trace_standard_multi_agent.md

### 第三步：更新主Agent提示词
需要在 `expert_prompt.py` 中添加多专家子Agent调用说明：

```python
## 多专家子Agent系统

当执行复杂分析任务时，可以使用多专家子Agent系统：

### 调用方式
使用 `call_sub_agent` 工具调用专家子Agent：

```python
call_sub_agent(
    target_mode="expert",
    task_description="任务描述",
    context={
        "expert_prompt_file": "提示词文件路径",
        "data_ids": ["数据ID列表"]
    }
)
```

### 可用专家
- **气象专家**：prompts/weather_expert.md
- **轨迹专家**：prompts/trajectory_expert.md
- **化学专家**：prompts/chemical_expert.md
- **报告专家**：prompts/report_expert.md

### 数据传递
- 每个任务完成后返回 data_id
- 后续任务通过 data_id 引用前面的数据
- 确保数据链路完整
```

### 第四步：测试验证
1. 测试专家提示词文件是否正确
2. 测试 call_sub_agent 调用是否成功
3. 测试 data_id 传递是否正确
4. 测试子Agent是否生成专业报告

### 第五步：优化调整
根据测试结果优化：
- 专家提示词内容
- 任务清单流程
- 数据传递方式

## 并行执行策略

### 可并行的任务
- 任务2（气象分析）和任务5（组分分析）可并行
- 任务3（轨迹分析）和任务5（组分分析）可并行

### 必须顺序的任务
- 任务1 → 任务2
- 任务2 → 任务3
- 任务3 → 任务4
- 所有任务 → 任务6

### 专家复用
- 轨迹专家可以执行任务3和任务4
- 减少专家切换开销

## 文件位置

### 专家提示词文件
- `/backend/config/prompts/weather_expert.md`
- `/backend/config/prompts/trajectory_expert.md`
- `/backend/config/prompts/chemical_expert.md`
- `/backend/config/prompts/report_expert.md`

### 任务清单模板
- `/backend/config/task_lists/quick_trace_standard_multi_agent.md`

### 备份文件
- `/tmp/quick_trace_standard_multi_agent.md`

## 优势总结

### 与之前复杂架构的对比

| 对比项 | ExpertRouterV3（复杂） | 多专家子Agent（简洁） |
|--------|------------------------|---------------------|
| 代码量 | 1000+ 行 | 4个md文件 |
| 复杂度 | 高（路由、调度、健康监控） | 低（直接调用） |
| 维护性 | 难（修改代码） | 易（修改md文件） |
| 专业性 | 高（多专家） | 高（多专家） |
| 用户可见 | 否（内部调度） | 是（专家工作可见） |
| 数据传递 | 复杂（对象引用） | 简单（data_id） |
| 并行执行 | 支持 | 支持 |

### 关键优势

1. **真正的多专家系统**：每个专家有独立的提示词和子Agent
2. **实现简洁**：不需要复杂的路由和调度系统
3. **易于维护**：专家提示词存储在独立的md文件中
4. **用户可见**：用户可以看到每个专家的工作过程
5. **数据高效**：通过data_id传递，避免重复查询

## 下一步

1. **更新主Agent提示词**：在 expert_prompt.py 中添加多专家子Agent调用说明
2. **测试验证**：测试多专家子Agent调用流程
3. **优化调整**：根据测试结果优化专家提示词和任务清单
4. **推广到其他场景**：将多专家子Agent系统推广到其他分析场景

## 总结

✅ **优雅的多专家系统实现**
- 真正的多专家（独立提示词、独立子Agent）
- 实现简洁（4个md文件 + call_sub_agent）
- 易于维护（修改md文件即可）
- 用户可见（专家工作过程透明）
- 数据高效（data_id传递）

这是一个**真正优雅的多专家系统实现**！🎉
