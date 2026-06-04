# LLM 监控工具集成指南

本指南说明如何将 LLM 监控工具集成到现有的 LLM 调用代码中。

## 快速开始

### 1. 安装依赖

确保已安装 `tiktoken`：

```bash
pip install tiktoken>=0.5.0
```

### 2. 在 LLMPlanner 中集成

修改 `backend/app/agent/core/planner.py`：

```python
from app.monitoring import get_monitor

class LLMPlanner:
    def __init__(self, tool_registry: Optional[Any] = None):
        # ... 原有代码 ...
        self.monitor = get_monitor()  # 添加监控器
    
    async def generate_thought(self, ...):
        # ... 原有代码 ...
        
        # 在 API 调用后添加监控
        if self.provider in ["openai", "deepseek", "minimax", "mimo", "qwen"]:
            if self.provider == "qwen":
                content = await self._call_qwen_api(prompt, temperature=0.7)
                # TODO: 添加监控
            else:
                response = await self.client.chat.completions.create(**api_params)
                content = response.choices[0].message.content
                
                # 添加监控
                await self.monitor.track_non_stream_call(
                    model=self.config["model"],
                    provider=self.provider,
                    messages=api_params["messages"],
                    response=response
                )
```

### 3. 在流式调用中集成

修改 `stream_user_answer` 方法：

```python
async def stream_user_answer(self, context: str, draft_answer: Optional[str] = None):
    # ... 原有代码 ...
    
    if self.provider in ["openai", "deepseek", "minimax", "mimo", "qwen"]:
        api_params = {
            "model": self.config["model"],
            "messages": [...],
            "stream": True
        }
        
        stream = await self.client.chat.completions.create(**api_params)
        
        # 使用监控器跟踪流式调用
        content = await self.monitor.track_stream_call(
            model=self.config["model"],
            provider=self.provider,
            messages=api_params["messages"],
            stream_generator=stream
        )
        
        # 逐块输出
        for chunk in content:
            yield chunk
```

### 4. 在 LLMService 中集成

修改 `backend/app/services/llm_service.py`：

```python
from app.monitoring import get_monitor

class LLMService:
    def __init__(self):
        # ... 原有代码 ...
        self.monitor = get_monitor()  # 添加监控器
    
    async def chat(self, messages: list, ...):
        # ... 原有代码 ...
        
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
            
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            
            # 添加监控（需要构造响应对象）
            # 注意：httpx 响应需要转换为类似 OpenAI 的响应格式
            # 这里简化处理，直接记录 token
            await self.monitor.record_call(
                model=self.model,
                provider=self.provider,
                input_tokens=self.monitor.token_counter.count_messages(messages),
                output_tokens=self.monitor.token_counter.count_tokens(content),
                ttft=0.5,  # 估算值
                total_time=time.time() - start_time,
                success=True
            )
            
            return content
```

## 查看统计报告

### 方法 1: 在代码中查看

```python
from app.monitoring import print_report, get_statistics

# 打印报告
print_report()

# 获取统计数据
stats = get_statistics()
print(f"总调用次数: {stats['total_calls']}")
print(f"总 Token: {stats['total_tokens']:,}")
```

### 方法 2: 添加 API 端点

在 `backend/app/routers/` 中创建新路由：

```python
from fastapi import APIRouter
from app.monitoring import get_statistics, print_report

router = APIRouter(prefix="/api/monitoring", tags=["monitoring"])

@router.get("/stats")
async def get_llm_stats():
    """获取 LLM 调用统计"""
    return get_statistics()

@router.get("/report")
async def get_llm_report():
    """获取 LLM 调用报告（文本格式）"""
    from io import StringIO
    import sys
    
    old_stdout = sys.stdout
    sys.stdout = buffer = StringIO()
    
    print_report()
    
    sys.stdout = old_stdout
    return {"report": buffer.getvalue()}
```

### 方法 3: 定期导出

创建定时任务或脚本：

```python
from app.monitoring import export_to_csv, export_to_json
from datetime import datetime

# 导出数据
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
export_to_csv(f"llm_stats_{timestamp}.csv")
export_to_json(f"llm_stats_{timestamp}.json")
```

## 注意事项

1. **性能影响**: 监控会略微增加调用开销，但影响很小
2. **内存使用**: 所有调用记录都保存在内存中，长时间运行可能需要定期清理
3. **Token 计算**: 使用 tiktoken 计算 token，对于不支持的模型会使用估算值
4. **成本估算**: 基于公开的模型定价，可能与实际有差异

## 高级用法

### 自定义 Token 计数器

```python
from app.monitoring import TokenCounter

# 为特定模型创建计数器
counter = TokenCounter(model="custom-model")
tokens = counter.count_tokens("Hello, world!")
```

### 清理旧记录

```python
from app.monitoring import get_monitor

monitor = get_monitor()

# 只保留最近 1000 条记录
if len(monitor.records) > 1000:
    monitor.records = monitor.records[-1000:]
```

### 按时间范围统计

```python
from app.monitoring import get_monitor
from datetime import datetime, timedelta

monitor = get_monitor()

# 获取最近 24 小时的记录
cutoff_time = time.time() - 24 * 3600
recent_records = [r for r in monitor.records if r.timestamp > cutoff_time]

# 计算统计
total_tokens = sum(r.total_tokens for r in recent_records)
print(f"最近 24 小时 Token 消耗: {total_tokens:,}")
```

