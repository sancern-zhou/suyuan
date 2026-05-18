# Anthropic 格式迁移 - 快速参考

## 功能开关

```bash
# 启用/禁用功能（编辑 backend/.env）
USE_ANTHROPIC_FORMAT=true          # 启用Anthropic格式
ENABLE_TOOL_LIFECYCLE_EVENTS=true  # 启用工具生命周期事件
ENABLE_INTELLIGENT_RETRY=true      # 启用智能重试
```

## 监控命令

```bash
# 查看工具执行事件
tail -f backend_data_registry/logs/agent.log | grep "tool_execution"

# 查看错误重试日志
tail -f backend_data_registry/logs/agent.log | grep "tool_retry"

# 查看状态转换日志
tail -f backend_data_registry/logs/agent.log | grep "tool_state_transition"

# 查看 V3 规划器调用
tail -f backend_data_registry/logs/agent.log | grep "using_anthropic_format_v3"
```

## 核心文件

| 文件 | 用途 |
|------|------|
| `app/agent/events/tool_lifecycle.py` | 工具生命周期状态机 |
| `app/agent/events/error_classifier.py` | 错误分类器 |
| `app/agent/events/metrics.py` | 指标收集器 |
| `app/agent/core/planner.py` | V3 规划器（think_and_action_v3） |
| `app/services/llm_service.py` | chat_anthropic 方法 |
| `app/agent/core/executor.py` | execute_tool_with_events/retry |
| `app/scheduled_tasks/event_bus.py` | 工具生命周期事件 |

## 验证脚本

```bash
# 快速验证
python test_anthropic_system_fix.py

# 单元测试
python tests/test_anthropic_format_migration.py

# 集成测试
python tests/test_anthropic_integration.py
```

## 回滚方案

### 快速回滚
```bash
# 编辑 backend/.env
USE_ANTHROPIC_FORMAT=false
```

### 分级回滚
1. `USE_ANTHROPIC_FORMAT=false` - 禁用Anthropic格式
2. `ENABLE_TOOL_LIFECYCLE_EVENTS=false` - 禁用事件追踪
3. `ENABLE_INTELLIGENT_RETRY=false` - 禁用智能重试

## 常见问题

### Q: V3 规划器自动降级到 V2？
**A**: 检查日志中的错误信息：
- `unknown variant 'system'` → system参数问题（已修复）
- `Anthropic client not initialized` → 检查 anthropic 包是否安装

### Q: 工具执行没有事件？
**A**: 检查功能开关：
```bash
# 应该都是 true
echo $USE_ANTHROPIC_FORMAT
echo $ENABLE_TOOL_LIFECYCLE_EVENTS
```

### Q: 如何查看工具性能指标？
**A**: 目前指标在内存中，可以通过 MetricsCollector 获取：
```python
from app.agent.events.metrics import MetricsCollector
from app.scheduled_tasks.event_bus import get_event_bus

event_bus = get_event_bus()
metrics_collector = MetricsCollector(event_bus)
all_metrics = metrics_collector.get_all_metrics()
```

## 技术支持

- **详细报告**: ANTHROPIC_FORMAT_MIGRATION_COMPLETE.md
- **实施总结**: ANTHROPIC_FORMAT_MIGRATION_SUMMARY.md
- **测试报告**: tests/test_anthropic_format_migration.py
