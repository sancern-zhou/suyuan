# LLM请求上下文日志使用指南

## 概述

为了方便调试和分析通用Agent的工作流程，系统现在支持将每次LLM调用的完整请求上下文保存到日志文件中（仅记录发送给LLM的内容，不记录响应）。

**控制台只显示预览，完整内容保存到文件**，避免控制台输出过长影响可读性。

## 功能特性

### 1. 文件日志系统

系统会自动将完整的LLM请求上下文保存到独立的JSON文件中：

- **日志目录**：`backend/logs/llm_context/`
- **文件命名**：`context_{session_id}_iter{iteration}_{timestamp}.json`
- **自动清理**：最多保留100个日志文件，超过后自动删除最旧的文件

### 2. 控制台预览

控制台只显示简洁的预览信息：

- 迭代次数
- Agent模式（expert/assistant）
- 消息数量
- System Prompt 长度和预览（200字符）
- User Conversation 长度和预览（300字符）
- 日志文件路径

### 3. 日志文件内容

每个日志文件包含完整的请求上下文：

```json
{
  "context_id": "session_xxx_iter1_20260316_103015",
  "timestamp": "2026-03-16T10:30:15.123456",
  "session_id": "session_xxx",
  "iteration": 1,
  "mode": "expert",
  "metadata": {
    "query": "分析广州O3污染溯源"
  },
  "system_prompt": "你是大气污染溯源分析系统的ReAct Agent...",
  "system_prompt_length": 3914,
  "user_conversation": "## 对话历史\n\n### 用户 1\n分析广州O3污染溯源...",
  "user_conversation_length": 14309,
  "messages_count": 2,
  "messages": [
    {"role": "system", "content": "..."},
    {"role": "user", "content": "..."}
  ]
}
```

## 使用方法

### 1. 直接运行（自动启用）

直接运行后端，系统会自动记录LLM上下文到文件：

```bash
cd backend
python -m uvicorn app.main:app --reload
```

### 2. 查看日志文件

**日志文件位置**：
```
backend/logs/llm_context/context_{session_id}_iter{iteration}_{timestamp}.json
```

**查看最新日志**：
```bash
# Windows
dir backend\logs\llm_context /O-D

# Linux/Mac
ls -lt backend/logs/llm_context/ | head -n 10
```

**查看特定日志文件**：
```bash
# 使用cat查看（Linux/Mac）
cat backend/logs/llm_context/context_xxx.json

# 使用type查看（Windows）
type backend\logs\llm_context\context_xxx.json

# 使用jq格式化查看（推荐）
cat backend/logs/llm_context/context_xxx.json | jq .
```

## 控制台输出示例

```
2026-03-16 10:30:15 [INFO] llm_request_context_logged
  iteration=1
  mode=expert
  messages_count=2
  system_prompt_length=3914
  user_conversation_length=14309
  system_prompt_preview="你是通用办公助手，帮助用户完成日常办公任务。..."
  user_conversation_preview="## 对话历史\n\n### 用户 1\n找一下广东旭诚科技有限公司..."
  log_file="backend/logs/llm_context/context_session_xxx_iter1_20260316_103015_123456.json"
```

## 适用范围

完整的LLM请求上下文日志会在以下场景自动记录：

1. **主Agent循环**：`app/agent/core/loop.py` → `planner.think_and_action_v2_streaming()`
2. **LLM服务**：`app/services/llm_service.py` → `chat()` 和 `chat_streaming_with_status()`

## 日志管理

### 自动清理

系统会自动清理旧日志文件，保留最新的100个文件。

### 手动清理

```bash
# 清空所有LLM上下文日志
rm -rf backend/logs/llm_context/*

# Windows
rd /s /q backend\logs\llm_context
mkdir backend\logs\llm_context
```

### 调整保留数量

修改 `app/utils/llm_context_logger.py` 中的 `max_files` 参数：

```python
llm_context_logger = LLMContextLogger(
    max_files=200  # 保留200个文件
)
```

## 注意事项

1. **仅记录请求**：系统只记录发送给LLM的请求内容，不记录响应内容
2. **文件存储**：所有日志保存在 `backend/logs/llm_context/` 目录中
3. **自动清理**：系统会自动清理旧日志，避免磁盘占用过多
4. **敏感信息**：日志文件可能包含敏感信息，注意保护

## 高级用法

### 查看特定会话的所有上下文

```python
from app.utils.llm_context_logger import get_llm_context_logger

logger = get_llm_context_logger()
contexts = logger.get_session_contexts("session_xxx")
for context in contexts:
    print(f"Iteration {context['iteration']}: {context['log_file']}")
```

### 实时监控日志文件

```bash
# Linux/Mac - 监控新创建的日志文件
watch -n 1 'ls -lt backend/logs/llm_context/ | head -n 5'

# Windows - 使用PowerShell监控
Get-ChildItem backend\logs\llm_context\ | Sort-Object LastWriteTime -Descending | Select-Object -First 5
```

### 日志分析脚本

创建一个简单的Python脚本分析日志：

```python
import json
from pathlib import Path

log_dir = Path("backend/logs/llm_context")
for log_file in sorted(log_dir.glob("context_*.json")):
    with open(log_file) as f:
        data = json.load(f)
        print(f"Session: {data['session_id']}")
        print(f"Iteration: {data['iteration']}")
        print(f"System Prompt Length: {data['system_prompt_length']}")
        print(f"User Conversation Length: {data['user_conversation_length']}")
        print("---")
```

## 相关文件

- `backend/app/utils/llm_context_logger.py` - LLM上下文日志记录器
- `backend/app/agent/core/planner.py` - Agent规划器LLM调用日志
- `backend/app/services/llm_service.py` - LLM服务日志
- `backend/logs/llm_context/` - 日志文件目录
