# AgentLogger 简化总结

## 改动概述

参考 OpenClaw 设计，将 `agent_logger.py` 从 **526行** 简化到 **313行**（-40%代码量）

**核心原则**: 只保留核心指标，移除未使用的复杂追踪

## 移除的功能

### 1. 删除的方法（从未使用）
- ❌ `log_llm_request()` - 记录LLM请求详情
- ❌ `log_llm_response()` - 记录LLM响应详情
- ❌ `log_tool_call()` - 记录工具调用开始
- ❌ `log_tool_result()` - 记录工具执行结果
- ❌ `log_iteration()` - 记录完整迭代

### 2. 删除的数据结构
- ❌ `iterations` 数组 - 迭代详情追踪
- ❌ `llm_calls` 数组 - LLM调用详情
- ❌ `tool_calls` 数组 - 工具调用详情
- ❌ `message_summary` - 消息摘要
- ❌ `tool_call_summary` - 工具调用摘要
- ❌ `total_llm_calls` - LLM调用次数统计
- ❌ `total_tool_calls` - 工具调用次数统计

## 保留的功能（核心指标）

### 1. 新增方法
- ✅ `record_usage(input_tokens, output_tokens)` - 记录Token使用

### 2. 保留方法
- ✅ `start_new_run()` - 开始新的运行记录
- ✅ `end_run()` - 结束运行记录
- ✅ `log_error()` - 记录错误（用于调试）
- ✅ `get_current_stats()` - 获取当前统计
- ✅ `get_run_summary()` - 获取运行摘要

### 3. 保留数据结构
```python
{
    "run_id": "...",
    "session_id": "...",
    "start_time": "...",
    "end_time": "...",
    "status": "completed",
    "query": "...",
    "metadata": {},

    # 核心统计指标（参考 OpenClaw）
    "stats": {
        "duration_ms": 1234,           # 运行时长
        "usage": {
            "input_tokens": 100,        # 输入token数
            "output_tokens": 200,       # 输出token数
            "total_tokens": 300         # 总token数
        }
    },

    # 错误记录（用于调试）
    "errors": []
}
```

## 日志输出对比

### 旧版本（复杂，未使用）
```
agent_run_ended iterations=0 llm_calls=0 tool_calls=0 duration_ms=7083
```
**问题**: `iterations`、`llm_calls`、`tool_calls` 始终为0，因为没有调用 `log_iteration()`

### 新版本（简洁，准确）
```
agent_run_ended duration_ms=259 input_tokens=150 output_tokens=300 total_tokens=450 errors_count=0
```
**改进**: 只显示有意义的指标

## 与 OpenClaw 对比

| 指标 | OpenClaw | 简化前 | 简化后 |
|------|----------|--------|--------|
| **duration_ms** | ✅ | ✅ | ✅ |
| **usage.tokens** | ✅ | ✅ | ✅ |
| **iterations** | ❌ | ✅ (空) | ❌ |
| **llm_calls** | ❌ | ✅ (空) | ❌ |
| **tool_calls** | ❌ | ✅ (空) | ❌ |
| **errors** | ❌ | ✅ | ✅ (增强) |

**结论**: 简化后的设计更接近 OpenClaw，同时保留了错误记录用于调试

## 使用示例

### 基本用法
```python
from app.utils.agent_logger import AgentLogger

logger = AgentLogger(log_dir="./logs/agent_runs")

# 开始运行
run_id = logger.start_new_run(
    session_id="session_123",
    query="分析广州O3污染"
)

# 记录Token使用
logger.record_usage(input_tokens=1000, output_tokens=500)

# 记录错误（可选）
logger.log_error(
    error="工具调用失败",
    error_type="tool_error",
    context={"tool_name": "get_weather_data"}
)

# 结束运行
logger.end_run(status="completed", final_answer="分析完成")

# 获取摘要
summary = logger.get_run_summary()
print(summary)
# {
#     "run_id": "...",
#     "status": "completed",
#     "duration_ms": 1234,
#     "input_tokens": 1000,
#     "output_tokens": 500,
#     "total_tokens": 1500,
#     "errors_count": 0
# }
```

## 兼容性

### 现有代码无需修改
- `loop.py` 中的调用保持不变
- 只使用 `start_new_run()`、`end_run()`、`log_error()`、`get_run_summary()`
- 这些方法在简化后仍然存在且功能一致

### 如需记录Token使用
在 LLM 服务调用后添加：
```python
if self.agent_logger and usage:
    self.agent_logger.record_usage(
        input_tokens=usage.get("input_tokens", 0),
        output_tokens=usage.get("output_tokens", 0)
    )
```

## 测试验证

运行测试：
```bash
cd backend
python tests/test_agent_logger_simplified.py
```

测试覆盖：
- ✅ 基本日志记录
- ✅ Token使用统计
- ✅ 错误记录
- ✅ 无当前运行时的行为
- ✅ 数据结构验证
- ✅ 文件日志保存

## 文件变化

- **删除**: 0 个文件
- **修改**: 1 个文件
  - `app/utils/agent_logger.py` (526行 → 313行)
- **新增**: 1 个测试文件
  - `tests/test_agent_logger_simplified.py`

## 后续建议

1. **集成Token统计**: 在 LLM 服务返回 `usage` 时自动调用 `record_usage()`
2. **监控告警**: 基于 `duration_ms` 和 `total_tokens` 设置告警阈值
3. **性能分析**: 定期分析日志文件，找出耗时最长的查询

## 参考

- OpenClaw Agent Logger: `src/agents/pi-embedded-runner/types.ts`
- OpenClaw 嵌入式 Agent: `src/agents/pi-embedded-runner/run.ts`
