# LLM API 监控模块

用于监控和统计项目中 LLM API 调用情况的独立模块。

## 功能特性

- ✅ 实时监控 LLM API 调用
- ✅ 统计 token 使用情况（输入/输出）
- ✅ 计算 token 输出速率（tokens/秒）
- ✅ 测量首字延迟（TTFT - Time To First Token）
- ✅ 成本估算
- ✅ 按模型统计
- ✅ 导出 CSV/JSON 报告

## 使用方法

### 1. 在代码中集成监控

#### 流式调用监控

```python
from app.monitoring import get_monitor

monitor = get_monitor()

# 在流式调用中使用
async def stream_llm_call():
    messages = [{"role": "user", "content": "你好"}]
    
    stream = await client.chat.completions.create(
        model="gpt-4",
        messages=messages,
        stream=True
    )
    
    # 使用监控器跟踪
    content = await monitor.track_stream_call(
        model="gpt-4",
        provider="openai",
        messages=messages,
        stream_generator=stream
    )
    
    return content
```

#### 非流式调用监控

```python
from app.monitoring import get_monitor

monitor = get_monitor()

# 在非流式调用中使用
async def non_stream_llm_call():
    messages = [{"role": "user", "content": "你好"}]
    
    response = await client.chat.completions.create(
        model="gpt-4",
        messages=messages
    )
    
    # 使用监控器跟踪
    content = await monitor.track_non_stream_call(
        model="gpt-4",
        provider="openai",
        messages=messages,
        response=response
    )
    
    return content
```

### 2. 查看统计报告

```python
from app.monitoring import print_report, get_statistics, export_to_csv, export_to_json

# 打印控制台报告
print_report()

# 获取统计信息（字典格式）
stats = get_statistics()
print(f"总调用次数: {stats['total_calls']}")
print(f"总 Token: {stats['total_tokens']:,}")

# 导出为 CSV
export_to_csv("llm_stats.csv")

# 导出为 JSON
export_to_json("llm_stats.json")
```

### 3. 集成到现有代码

在 `app/agent/core/planner.py` 中集成：

```python
from app.monitoring import get_monitor

class LLMPlanner:
    def __init__(self):
        self.monitor = get_monitor()
        # ...
    
    async def generate_thought(self, ...):
        # 原有代码...
        response = await self.client.chat.completions.create(...)
        
        # 添加监控
        await self.monitor.track_non_stream_call(
            model=self.config["model"],
            provider=self.provider,
            messages=[...],
            response=response
        )
```

## 统计指标说明

- **输入 Token**: 发送给模型的 token 数量
- **输出 Token**: 模型生成的 token 数量
- **TTFT (Time To First Token)**: 首字延迟，从请求发送到收到第一个 token 的时间
- **输出速率**: 每秒生成的 token 数量
- **成本估算**: 基于模型定价估算的 API 调用成本

## 支持的模型定价

当前支持以下模型的成本估算：
- GPT-4 / GPT-4 Turbo
- GPT-3.5 Turbo
- DeepSeek Chat / Reasoner
- MiniMax M2
- Mimo V2 Flash

其他模型使用 GPT-3.5 的默认定价。

## 输出示例

```
============================================================
LLM API 调用统计报告
============================================================

总调用次数: 150
  - 成功: 148
  - 失败: 2

总 Token 消耗: 45,230
  - 输入 Token: 12,450
  - 输出 Token: 32,780

平均首字延迟 (TTFT): 0.850 秒
平均 Token 输出速率: 45.20 tokens/秒

总成本估算: $2.3456
成功率: 98.7%

按模型统计:
  gpt-4:
    - 调用次数: 100
    - Token: 30,000
    - 成本: $1.8000
  deepseek-chat:
    - 调用次数: 50
    - Token: 15,230
    - 成本: $0.5456
============================================================
```

