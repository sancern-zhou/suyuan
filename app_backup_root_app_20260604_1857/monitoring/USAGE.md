# LLM 监控工具使用指南

## 使用方式

### 方式 1: 命令行脚本（推荐）

使用提供的命令行脚本查看统计：

```bash
# 进入后端目录
cd backend

# 打印统计报告
python scripts/view_llm_stats.py

# 导出为 CSV
python scripts/view_llm_stats.py --csv

# 导出为 JSON
python scripts/view_llm_stats.py --json

# 打印报告并导出所有格式
python scripts/view_llm_stats.py --all

# 指定输出目录
python scripts/view_llm_stats.py --csv --output-dir ./logs
```

### 方式 2: Python 交互式使用

在 Python 交互式环境中使用：

```python
# 进入后端目录
cd backend

# 启动 Python
python

# 导入监控模块
from app.monitoring import print_report, get_statistics, export_to_csv

# 打印报告
print_report()

# 获取统计数据（字典格式）
stats = get_statistics()
print(f"总调用次数: {stats['total_calls']}")
print(f"总 Token: {stats['total_tokens']:,}")
print(f"总成本: ${stats['total_cost']:.4f}")

# 导出数据
export_to_csv("llm_stats.csv")
```

### 方式 3: API 端点（Web 界面）

启动后端服务后，可以通过 API 访问：

```bash
# 启动服务
cd backend
uvicorn app.main:app --reload --port 8000
```

然后访问：

1. **获取统计信息（JSON）**
   ```
   GET http://localhost:8000/api/monitoring/stats
   ```

2. **获取文本报告**
   ```
   GET http://localhost:8000/api/monitoring/report
   ```

3. **导出 CSV**
   ```
   POST http://localhost:8000/api/monitoring/export/csv
   ```

4. **导出 JSON**
   ```
   POST http://localhost:8000/api/monitoring/export/json
   ```

5. **重置统计（清空记录）**
   ```
   DELETE http://localhost:8000/api/monitoring/reset
   ```

### 方式 4: 在代码中直接使用

在任何 Python 文件中使用：

```python
# 在您的代码文件中
from app.monitoring import print_report, get_statistics

# 在某个函数或方法中
def check_llm_usage():
    stats = get_statistics()
    if stats['total_tokens'] > 100000:
        print("警告：Token 使用量已超过 10 万")
    print_report()
```

## 使用场景示例

### 场景 1: 定期检查使用情况

创建一个定时任务脚本：

```python
# scripts/check_llm_usage.py
from app.monitoring import get_statistics, export_to_csv
from datetime import datetime

stats = get_statistics()
if stats['total_calls'] > 0:
    # 导出每日报告
    timestamp = datetime.now().strftime("%Y%m%d")
    export_to_csv(f"daily_report_{timestamp}.csv")
    print(f"今日 LLM 调用: {stats['total_calls']} 次")
    print(f"Token 消耗: {stats['total_tokens']:,}")
```

### 场景 2: 在 Agent 运行后查看统计

```python
# 在 Agent 分析完成后
from app.monitoring import print_report

# 执行 Agent 分析
# ... agent.analyze(...) ...

# 查看统计
print_report()
```

### 场景 3: 集成到日志系统

```python
# 在应用启动时记录初始状态
from app.monitoring import get_statistics
import structlog

logger = structlog.get_logger()

def log_llm_usage():
    stats = get_statistics()
    logger.info(
        "llm_usage_summary",
        total_calls=stats['total_calls'],
        total_tokens=stats['total_tokens'],
        total_cost=stats['total_cost']
    )
```

## 快速参考

### 常用命令

```bash
# 查看统计（最简单）
python scripts/view_llm_stats.py

# 导出并查看
python scripts/view_llm_stats.py --all

# 在 Python 中
python -c "from app.monitoring import print_report; print_report()"
```

### API 快速测试

```bash
# 使用 curl
curl http://localhost:8000/api/monitoring/stats

# 使用 PowerShell
Invoke-RestMethod -Uri http://localhost:8000/api/monitoring/stats
```

## 注意事项

1. **路径问题**: 确保在 `backend` 目录下运行脚本，或正确设置 Python 路径
2. **数据持久化**: 当前所有数据保存在内存中，重启服务会清空
3. **性能影响**: 监控对性能影响很小，可以放心使用

## 推荐使用方式

- **开发调试**: 使用命令行脚本 `python scripts/view_llm_stats.py`
- **生产环境**: 使用 API 端点 `/api/monitoring/stats`
- **数据分析**: 导出 CSV/JSON 后使用 Excel 或 Python 分析

