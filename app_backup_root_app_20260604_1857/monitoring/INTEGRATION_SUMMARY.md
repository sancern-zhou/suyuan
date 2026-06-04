# LLM 监控集成总结

## 已完成的集成

### 1. LLMPlanner 类 (`app/agent/core/planner.py`)

✅ **初始化监控器**
- 在 `__init__` 方法中初始化 `self.monitor = get_monitor()`

✅ **generate_thought 方法**
- 监控思考生成调用
- 支持 OpenAI 兼容的 provider 和 Anthropic

✅ **decide_action / _decide_action_with_retry 方法**
- 监控行动决策调用
- 支持所有 provider

✅ **_reask_action 方法**
- 监控重试调用

✅ **generate_partial_answer 方法**
- 监控部分答案生成调用

✅ **stream_user_answer 方法**
- 监控流式输出调用
- 实时记录首字延迟和输出速率

✅ **_call_qwen_api 方法**
- 监控 Qwen API 调用
- 支持 chat completions 和 completions 两种 API

### 2. 监控覆盖范围

- ✅ 所有非流式 LLM 调用
- ✅ 所有流式 LLM 调用
- ✅ 所有 provider（OpenAI, DeepSeek, MiniMax, Mimo, Qwen, Anthropic）
- ✅ 成功和失败的调用

## 监控指标

每次 LLM 调用都会记录：

1. **Token 统计**
   - 输入 Token 数量
   - 输出 Token 数量
   - 总 Token 数量

2. **性能指标**
   - 首字延迟 (TTFT)
   - Token 输出速率 (tokens/秒)
   - 总耗时

3. **其他信息**
   - 模型名称
   - Provider 名称
   - 是否成功
   - 错误信息（如果有）
   - 是否为流式调用
   - 成本估算

## 使用方法

### 查看统计报告

```python
from app.monitoring import print_report, get_statistics

# 打印控制台报告
print_report()

# 获取统计数据
stats = get_statistics()
print(f"总调用次数: {stats['total_calls']}")
print(f"总 Token: {stats['total_tokens']:,}")
print(f"总成本: ${stats['total_cost']:.4f}")
```

### 导出数据

```python
from app.monitoring import export_to_csv, export_to_json

# 导出为 CSV
export_to_csv("llm_stats.csv")

# 导出为 JSON
export_to_json("llm_stats.json")
```

### 添加 API 端点（可选）

可以在 `app/routers/` 中添加监控相关的 API 端点：

```python
from fastapi import APIRouter
from app.monitoring import get_statistics, print_report

router = APIRouter(prefix="/api/monitoring", tags=["monitoring"])

@router.get("/stats")
async def get_llm_stats():
    """获取 LLM 调用统计"""
    return get_statistics()
```

## 注意事项

1. **性能影响**: 监控会略微增加调用开销，但影响很小（主要是 token 计算）
2. **内存使用**: 所有调用记录都保存在内存中，长时间运行可能需要定期清理
3. **Token 计算**: 使用 tiktoken 计算 token，对于不支持的模型会使用估算值
4. **成本估算**: 基于公开的模型定价，可能与实际有差异

## 下一步

1. ✅ 监控已集成到所有 LLM 调用中
2. 可以开始使用 Agent 功能，监控会自动记录所有调用
3. 定期查看统计报告，了解 LLM 使用情况
4. 根据需要导出数据进行分析

