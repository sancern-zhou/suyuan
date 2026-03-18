# 任务清单持久化与断点恢复系统 - 技术方案

## 文档信息

- **版本**: v1.0
- **创建日期**: 2026-02-13
- **状态**: 待评审
- **负责人**: 开发团队

---

## 1. 背景与目标

### 1.1 背景

当前系统已实现：
- ✅ 对话历史持久化与恢复
- ✅ 内存任务管理（TaskList）- 用于前端实时显示
- ✅ ReAct Agent 自主决策架构

存在的问题：
- ❌ 任务清单无法持久化，刷新页面后丢失
- ❌ 长任务中断后无法从断点恢复
- ❌ 任务清单与对话历史分离，恢复时不协同
- ❌ 缺少自动任务规划能力

### 1.2 目标

**核心目标**：实现类似 Claude Code 的任务清单管理能力

1. **自动任务规划** - LLM 自动判断是否需要任务清单，无需用户确认
2. **任务持久化** - 任务清单自动保存，支持断点恢复
3. **协同恢复** - 任务清单与对话历史协同恢复
4. **实时追踪** - 前端实时展示任务进度
5. **无缝集成** - 不破坏现有 ReAct 架构

### 1.3 设计理念

**"LLM 完全自主 + 系统智能适配"**
- LLM 自动判断任务复杂度
- 自动创建任务清单（不需要用户确认）
- 自动保存检查点
- 自动断点恢复
- 用户只需提出需求，系统自动处理

---

## 2. 整体架构设计

### 2.1 架构图

```
┌─────────────────────────────────────────────────────────────────┐
│                         用户查询                                 │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                    ReAct Agent (主入口)                          │
│  - 检测是否有未完成的检查点                                       │
│  - 如果有：自动恢复并继续执行                                     │
│  - 如果没有：调用 AutoTaskPlanner                                │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                  AutoTaskPlanner (自动任务规划器)                │
│  1. LLM 分析查询复杂度                                           │
│  2. 自动判断是否需要任务清单                                      │
│  3. 如果需要：自动生成任务清单                                    │
│  4. 如果不需要：返回 None，使用普通 ReAct 循环                   │
└─────────────────────────────────────────────────────────────────┘
                              ↓
                    ┌─────────┴─────────┐
                    │                   │
            需要任务清单          不需要任务清单
                    │                   │
                    ↓                   ↓
┌──────────────────────────────┐  ┌──────────────────────────┐
│   任务清单执行模式             │  │   普通 ReAct 循环        │
│  - 创建 TaskCheckpointManager │  │  - 直接调用工具          │
│  - 逐个执行任务               │  │  - 无任务清单            │
│  - 每完成一个任务保存检查点    │  └──────────────────────────┘
│  - 实时更新前端进度           │
└──────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────────────────────────┐
│              TaskCheckpointManager (检查点管理器)                │
│  - 任务清单持久化（JSON 文件）                                   │
│  - 检查点保存（before_task / after_task）                       │
│  - 断点恢复                                                      │
│  - 与内存 TaskList 同步                                          │
└─────────────────────────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────────────────────────┐
│                    存储层（文件系统）                             │
│  backend_data_registry/checkpoints/{session_id}/                │
│    - tasks.json (任务清单)                                       │
│    - checkpoint_{timestamp}.json (检查点快照)                    │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 数据流

```
【新对话 - 复杂任务】
用户查询
  → AutoTaskPlanner.auto_plan()
  → LLM 判断：需要任务清单
  → 自动生成任务清单
  → 前端展示任务进度面板
  → 逐个执行任务
  → 每完成一个任务保存检查点
  → 所有任务完成

【新对话 - 简单查询】
用户查询
  → AutoTaskPlanner.auto_plan()
  → LLM 判断：不需要任务清单
  → 返回 None
  → 使用普通 ReAct 循环
  → 直接返回结果

【断点恢复】
用户刷新页面/重新打开
  → ReAct Agent 检测到未完成的检查点
  → 自动加载检查点
  → 恢复任务清单到内存 TaskList
  → 前端展示："从上次中断处继续..."
  → 继续执行未完成的任务
```

---

## 3. 核心组件设计

### 3.1 AutoTaskPlanner（自动任务规划器）

**文件**: `backend/app/agent/core/task_planner.py`

**职责**:
1. 自动分析查询复杂度
2. 自动判断是否需要任务清单
3. 自动生成任务清单（包含依赖关系）

**核心方法**:

```python
class AutoTaskPlanner:
    async def auto_plan(
        query: str,
        session_id: str
    ) -> Optional[List[Task]]:
        """
        自动规划任务

        Returns:
            如果需要任务清单，返回任务列表；否则返回 None
        """

    async def _analyze_query_complexity(
        query: str
    ) -> Dict:
        """
        分析查询复杂度（LLM 判断）

        Returns:
            {
                "needs_task_plan": bool,
                "reason": str,
                "estimated_steps": int,
                "complexity": "simple/medium/complex",
                "suggested_tasks": List[str]
            }
        """

    async def _generate_task_plan(
        query: str,
        session_id: str,
        analysis: Dict
    ) -> List[Task]:
        """
        生成详细的任务清单

        Returns:
            任务列表（包含依赖关系）
        """
```

**判断标准**:

| 场景 | 是否需要任务清单 | 示例 |
|------|----------------|------|
| 综合分析 | ✅ 需要 | "综合分析广州O3污染溯源" |
| 多步骤分析 | ✅ 需要 | "查询气象数据并分析VOCs组分" |
| 生成报告 | ✅ 需要 | "生成完整的污染溯源报告" |
| 简单查询 | ❌ 不需要 | "查询广州今天的PM2.5数据" |
| 单一工具 | ❌ 不需要 | "生成一个时序图" |
| 探索性提问 | ❌ 不需要 | "什么是PMF源解析？" |

### 3.2 TaskCheckpointManager（检查点管理器）

**文件**: `backend/app/agent/task/checkpoint_manager.py`

**职责**:
1. 任务清单持久化（JSON 文件）
2. 检查点保存与加载
3. 断点恢复
4. 与内存 TaskList 同步

**核心方法**:

```python
class TaskCheckpointManager:
    def __init__(
        session_id: str,
        task_list: TaskList
    ):
        """初始化检查点管理器"""

    async def save_checkpoint(
        checkpoint_type: str = "auto"
    ) -> str:
        """
        保存检查点

        Args:
            checkpoint_type:
                - "plan_created": 任务清单创建后
                - "before_task": 任务开始前
                - "after_task": 任务完成后
                - "auto": 自动保存

        Returns:
            checkpoint_id
        """

    async def load_checkpoint(
        checkpoint_id: str = None
    ) -> Optional[Dict]:
        """
        加载检查点

        Args:
            checkpoint_id: 检查点ID（None 则加载最新）

        Returns:
            检查点数据，如果不存在返回 None
        """

    async def restore_from_checkpoint(
        checkpoint_id: str = None
    ):
        """
        从检查点恢复任务清单

        恢复到内存 TaskList
        """

    async def has_unfinished_tasks(self) -> bool:
        """检查是否有未完成的任务"""

    async def get_unfinished_tasks(self) -> List[Task]:
        """获取未完成的任务列表"""
```

**存储格式**:

```json
// backend_data_registry/checkpoints/{session_id}/tasks.json
{
  "session_id": "session_xxx",
  "created_at": "2026-02-13T10:00:00",
  "updated_at": "2026-02-13T10:15:00",
  "query": "综合分析广州O3污染溯源",
  "tasks": [
    {
      "id": "task_001",
      "subject": "获取气象数据",
      "description": "获取广州2024年O3污染期间的气象数据",
      "status": "completed",
      "progress": 100,
      "depends_on": [],
      "expert_type": "weather",
      "result_data_id": "weather_data:xxx",
      "created_at": "2026-02-13T10:00:00",
      "started_at": "2026-02-13T10:00:05",
      "completed_at": "2026-02-13T10:05:00",
      "metadata": {
        "estimated_duration": 30,
        "actual_duration": 295,
        "auto_generated": true
      }
    },
    {
      "id": "task_002",
      "subject": "分析VOCs组分",
      "description": "分析VOCs组分特征，识别主要污染物",
      "status": "in_progress",
      "progress": 60,
      "depends_on": ["task_001"],
      "expert_type": "component",
      "created_at": "2026-02-13T10:05:00",
      "started_at": "2026-02-13T10:05:30",
      "metadata": {
        "estimated_duration": 45,
        "auto_generated": true
      }
    }
  ],
  "checkpoints": [
    {
      "checkpoint_id": "ckpt_001",
      "timestamp": "2026-02-13T10:05:00",
      "type": "after_task",
      "completed_tasks": ["task_001"],
      "current_task": "task_002",
      "pending_tasks": ["task_003", "task_004", "task_005"]
    }
  ]
}
```

### 3.3 ReAct Agent 集成

**文件**: `backend/app/agent/react_agent.py`

**修改点**:

```python
async def analyze(
    user_query: str,
    session_id: Optional[str] = None,
    **kwargs
):
    """分析用户查询（集成任务规划）"""

    # 1. 初始化组件
    task_planner = AutoTaskPlanner(...)
    checkpoint_manager = TaskCheckpointManager(...)

    # 2. 检查是否有未完成的检查点
    if await checkpoint_manager.has_unfinished_tasks():
        # 自动恢复并继续执行
        yield {"type": "checkpoint_restored", ...}
        async for event in self._execute_task_plan(...):
            yield event
        return

    # 3. 自动判断是否需要任务清单
    tasks = await task_planner.auto_plan(user_query, session_id)

    if tasks:
        # 4. 创建了任务清单 - 执行任务模式
        yield {"type": "task_plan_created", ...}
        await checkpoint_manager.save_checkpoint("plan_created")
        async for event in self._execute_task_plan(...):
            yield event
    else:
        # 5. 简单查询 - 普通 ReAct 循环
        async for event in self._execute_react_loop(...):
            yield event
```

### 3.4 前端组件

**文件**: `frontend/src/components/TaskProgressPanel.vue`

**功能**:
1. 自动展示任务进度（无需用户操作）
2. 实时更新任务状态（WebSocket）
3. 支持展开/折叠
4. 显示整体进度

**UI 设计**:

```
┌─────────────────────────────────────────┐
│ 📋 任务进度              3/5 已完成      │
├─────────────────────────────────────────┤
│ ████████████░░░░░░░░░░░░░░░░░░  60%    │
├─────────────────────────────────────────┤
│ ✅ task_001: 获取气象数据                │
│ ✅ task_002: 分析VOCs组分                │
│ ⏳ task_003: 计算PMF源解析  [执行中 60%] │
│ ⏸️ task_004: 生成可视化图表  [等待中]    │
│ ⏸️ task_005: 生成综合报告    [等待中]    │
└─────────────────────────────────────────┘
```

---

## 4. 分阶段实施计划

### 阶段 1：基础设施搭建（1-2天）

**目标**: 搭建任务持久化基础设施

**任务清单**:
- [ ] 创建 `TaskCheckpointManager` 类
  - [ ] 实现 `save_checkpoint()` 方法
  - [ ] 实现 `load_checkpoint()` 方法
  - [ ] 实现 `restore_from_checkpoint()` 方法
  - [ ] 实现文件存储逻辑
- [ ] 创建存储目录结构
  - [ ] `backend_data_registry/checkpoints/{session_id}/`
- [ ] 编写单元测试
  - [ ] 测试检查点保存
  - [ ] 测试检查点加载
  - [ ] 测试断点恢复

**验收标准**:
- ✅ 任务清单可以保存到 JSON 文件
- ✅ 可以从 JSON 文件加载任务清单
- ✅ 可以恢复任务清单到内存 TaskList
- ✅ 单元测试通过率 100%

**风险**:
- 低风险：纯新增功能，不影响现有代码

---

### 阶段 2：自动任务规划器（2-3天）

**目标**: 实现 LLM 自动判断和任务规划

**任务清单**:
- [ ] 创建 `AutoTaskPlanner` 类
  - [ ] 实现 `auto_plan()` 方法
  - [ ] 实现 `_analyze_query_complexity()` 方法
  - [ ] 实现 `_generate_task_plan()` 方法
- [ ] 设计 LLM Prompt
  - [ ] 复杂度判断 Prompt
  - [ ] 任务拆解 Prompt
- [ ] 编写测试用例
  - [ ] 测试简单查询（不创建任务清单）
  - [ ] 测试复杂任务（创建任务清单）
  - [ ] 测试任务依赖关系生成

**验收标准**:
- ✅ LLM 能正确判断查询复杂度
- ✅ 复杂任务自动生成任务清单
- ✅ 简单查询不生成任务清单
- ✅ 任务依赖关系正确

**风险**:
- 中风险：LLM 判断可能不准确
- 缓解措施：
  - 提供详细的判断标准
  - 收集测试用例，持续优化 Prompt
  - 添加人工审核机制（可选）

---

### 阶段 3：ReAct Agent 集成（2-3天）

**目标**: 将任务规划集成到 ReAct Agent

**任务清单**:
- [ ] 修改 `ReActAgent.analyze()` 方法
  - [ ] 添加检查点检测逻辑
  - [ ] 添加自动恢复逻辑
  - [ ] 添加任务规划调用
  - [ ] 添加任务执行循环
- [ ] 实现 `_execute_task_plan()` 方法
  - [ ] 任务状态管理
  - [ ] 检查点保存
  - [ ] 事件流式输出
- [ ] 实现 `_execute_with_expert()` 方法
  - [ ] 根据 expert_type 调用专家
- [ ] 向后兼容性测试
  - [ ] 确保不影响现有功能

**验收标准**:
- ✅ 复杂任务自动创建任务清单并执行
- ✅ 简单查询使用普通 ReAct 循环
- ✅ 断点恢复功能正常
- ✅ 现有功能不受影响

**风险**:
- 高风险：可能影响现有 ReAct 循环
- 缓解措施：
  - 充分的单元测试和集成测试
  - 灰度发布（先在测试环境验证）
  - 保留回滚方案

---

### 阶段 4：前端展示（1-2天）

**目标**: 实现任务进度前端展示

**任务清单**:
- [ ] 创建 `TaskProgressPanel.vue` 组件
  - [ ] 任务列表展示
  - [ ] 整体进度条
  - [ ] 实时状态更新
- [ ] 集成到主界面
  - [ ] 自动展示/隐藏
  - [ ] 响应式布局
- [ ] WebSocket 事件监听
  - [ ] `task_plan_created` 事件
  - [ ] `task_started` 事件
  - [ ] `task_completed` 事件
  - [ ] `checkpoint_restored` 事件

**验收标准**:
- ✅ 任务进度面板自动展示
- ✅ 任务状态实时更新
- ✅ UI 美观，用户体验良好

**风险**:
- 低风险：纯前端展示，不影响后端逻辑

---

### 阶段 5：测试与优化（2-3天）

**目标**: 全面测试和性能优化

**任务清单**:
- [ ] 端到端测试
  - [ ] 复杂任务完整流程测试
  - [ ] 断点恢复测试
  - [ ] 并发任务测试
- [ ] 性能测试
  - [ ] 检查点保存性能
  - [ ] 大量任务场景测试
- [ ] 边界情况测试
  - [ ] 任务失败处理
  - [ ] 网络中断恢复
  - [ ] 存储空间不足
- [ ] 用户体验优化
  - [ ] 优化 LLM Prompt
  - [ ] 优化前端交互
  - [ ] 添加错误提示

**验收标准**:
- ✅ 所有测试用例通过
- ✅ 性能满足要求（检查点保存 < 100ms）
- ✅ 边界情况处理正确
- ✅ 用户体验良好

---

## 5. 风险评估与缓解

### 5.1 技术风险

| 风险 | 等级 | 影响 | 缓解措施 |
|------|------|------|---------|
| LLM 判断不准确 | 中 | 可能创建不必要的任务清单 | 优化 Prompt，收集测试用例 |
| 影响现有 ReAct 循环 | 高 | 可能破坏现有功能 | 充分测试，灰度发布 |
| 检查点文件损坏 | 中 | 无法恢复任务 | 添加文件校验，多版本备份 |
| 并发任务冲突 | 低 | 任务状态不一致 | 添加锁机制 |

### 5.2 业务风险

| 风险 | 等级 | 影响 | 缓解措施 |
|------|------|------|---------|
| 用户不习惯自动任务清单 | 低 | 用户体验下降 | 提供关闭选项 |
| 存储空间占用 | 低 | 磁盘空间不足 | 定期清理过期检查点 |

---

## 6. 测试策略

### 6.1 单元测试

**覆盖率目标**: 80%

**测试用例**:
- `TaskCheckpointManager`
  - 保存检查点
  - 加载检查点
  - 恢复任务清单
  - 文件不存在处理
  - 文件损坏处理
- `AutoTaskPlanner`
  - 简单查询判断
  - 复杂任务判断
  - 任务拆解
  - 依赖关系生成

### 6.2 集成测试

**测试场景**:
1. 复杂任务完整流程
   - 用户输入 → 自动创建任务清单 → 执行任务 → 保存检查点 → 完成
2. 简单查询流程
   - 用户输入 → 判断不需要任务清单 → 直接执行 → 返回结果
3. 断点恢复流程
   - 执行到一半 → 中断 → 重新启动 → 自动恢复 → 继续执行
4. 任务失败处理
   - 任务执行失败 → 标记失败 → 继续执行其他任务

### 6.3 性能测试

**性能指标**:
- 检查点保存时间: < 100ms
- 检查点加载时间: < 50ms
- LLM 判断时间: < 2s
- 任务规划生成时间: < 5s

---

## 7. 回滚方案

### 7.1 回滚触发条件

- 严重 Bug 导致系统不可用
- 性能严重下降（响应时间 > 10s）
- 数据丢失或损坏

### 7.2 回滚步骤

1. **代码回滚**
   ```bash
   git revert <commit_hash>
   git push origin main
   ```

2. **数据库回滚**（如果有数据库变更）
   ```bash
   # 执行回滚脚本
   python scripts/rollback_db.py
   ```

3. **清理检查点文件**
   ```bash
   # 备份现有检查点
   mv backend_data_registry/checkpoints backend_data_registry/checkpoints_backup
   ```

4. **重启服务**
   ```bash
   ./restart.sh
   ```

### 7.3 数据保护

- 所有检查点文件在回滚前备份
- 保留最近 7 天的检查点文件
- 提供手动恢复工具

---

## 8. 上线计划

### 8.1 灰度发布

**阶段 1**: 内部测试（1-2天）
- 开发团队内部测试
- 修复发现的 Bug

**阶段 2**: 小范围测试（2-3天）
- 10% 用户启用新功能
- 收集用户反馈
- 监控性能指标

**阶段 3**: 全量发布（1天）
- 100% 用户启用新功能
- 持续监控

### 8.2 监控指标

- 任务清单创建率
- 任务完成率
- 断点恢复成功率
- 检查点保存失败率
- 用户反馈

---

## 9. 后续优化方向

### 9.1 短期优化（1-2周）

- [ ] 任务清单可视化优化（甘特图）
- [ ] 任务依赖关系图展示
- [ ] 任务执行时间预估优化
- [ ] 支持手动修改任务清单

### 9.2 中期优化（1-2个月）

- [ ] 任务清单模板系统
- [ ] 任务执行历史统计
- [ ] 任务性能分析
- [ ] 支持任务优先级调整

### 9.3 长期优化（3-6个月）

- [ ] 多用户协同任务
- [ ] 任务调度优化（并行执行）
- [ ] 任务执行结果缓存
- [ ] 智能任务推荐

---

## 10. 总结

### 10.1 核心价值

1. **提升用户体验** - 自动任务规划，无需用户干预
2. **增强可靠性** - 断点恢复，长任务不丢失
3. **提高透明度** - 实时进度展示，用户清楚系统在做什么
4. **保持架构优雅** - 无缝集成，不破坏现有架构

### 10.2 实施时间表

| 阶段 | 时间 | 人力 |
|------|------|------|
| 阶段 1：基础设施 | 1-2天 | 1人 |
| 阶段 2：任务规划器 | 2-3天 | 1人 |
| 阶段 3：ReAct 集成 | 2-3天 | 1人 |
| 阶段 4：前端展示 | 1-2天 | 1人 |
| 阶段 5：测试优化 | 2-3天 | 1-2人 |
| **总计** | **8-13天** | **1-2人** |

### 10.3 成功标准

- ✅ 复杂任务自动创建任务清单
- ✅ 简单查询不创建任务清单
- ✅ 断点恢复成功率 > 95%
- ✅ 检查点保存时间 < 100ms
- ✅ 用户满意度 > 90%
- ✅ 现有功能不受影响

---

## 附录

### A. 相关文档

- [ReAct Agent 架构文档](./react_agent_architecture.md)
- [任务管理系统设计](./task_management_design.md)
- [数据持久化规范](./data_persistence_spec.md)

### B. 参考实现

- Claude Code 任务清单系统
- GitHub Copilot Workspace
- Cursor AI Agent

---

**文档结束**
