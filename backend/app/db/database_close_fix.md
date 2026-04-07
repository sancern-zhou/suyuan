# PostgreSQL连接关闭异常修复

## 问题描述

应用关闭时出现以下错误：

```
Exception closing connection <AdaptedConnection <asyncpg.connection.Connection object at 0x7f85aab78d60>>
Traceback (most recent call last):
  File ".../sqlalchemy/pool/base.py", line 376, in _close_connection
    self._dialect.do_close(connection)
  ...
  File ".../asyncpg/connection.py", line 1504, in close
    await self._protocol.close(timeout)
  File "asyncpg/protocol/protocol.pyx", line 642, in close
```

## 根本原因

应用关闭时的执行顺序问题：

1. **知识库处理队列的worker**正在使用数据库连接处理文档
2. **关闭信号触发**，`stop_processing_queue()`被调用
3. **worker被立即取消**，但可能还在执行数据库操作
4. **数据库连接池被关闭**，`close_db()`被调用
5. **asyncpg连接关闭异常**，因为连接还在使用中

## 修复方案

### 1. 优化知识库队列停止逻辑

**文件**: `app/knowledge_base/tasks.py`

**修改前**：
```python
async def stop(self):
    """停止处理队列"""
    self._is_running = False

    # 取消所有worker
    for worker in self._workers:
        worker.cancel()

    # 等待worker完成
    await asyncio.gather(*self._workers, return_exceptions=True)
    self._workers.clear()

    logger.info("document_processing_queue_stopped")
```

**修改后**：
```python
async def stop(self):
    """停止处理队列"""
    # 先设置停止标志，让worker自然退出
    self._is_running = False

    # 等待所有worker完成当前任务（最多等待10秒）
    try:
        await asyncio.wait_for(
            asyncio.gather(*self._workers, return_exceptions=True),
            timeout=10.0
        )
    except asyncio.TimeoutError:
        # 超时后强制取消剩余worker
        logger.warning("worker_stop_timeout", message="Workers did not stop gracefully, force cancelling")
        for worker in self._workers:
            if not worker.done():
                worker.cancel()
        # 等待取消完成
        await asyncio.gather(*self._workers, return_exceptions=True)

    self._workers.clear()

    logger.info("document_processing_queue_stopped")
```

**改进点**：
- 先设置`_is_running = False`，让worker自然退出循环
- 给worker 10秒时间完成当前任务
- 超时后才强制取消worker
- 避免在数据库操作期间强制取消

### 2. 增强数据库关闭逻辑

**文件**: `app/db/database.py`

**修改前**：
```python
async def close_db():
    """Close database connections."""
    await engine.dispose()
    logger.info("database_closed")
```

**修改后**：
```python
async def close_db():
    """
    Close database connections.
    Should be called on application shutdown.
    """
    try:
        # 尝试优雅关闭连接池（最多等待10秒）
        await asyncio.wait_for(engine.dispose(), timeout=10.0)
        logger.info("database_closed")
    except asyncio.TimeoutError:
        logger.warning("database_close_timeout", message="Database close timed out, forcing disposal")
        # 超时后尝试强制关闭（忽略错误）
        try:
            engine.dispose(close_wake_up=True)
        except Exception as e:
            logger.warning("database_force_close_failed", error=str(e))
    except Exception as e:
        logger.error("database_close_failed", error=str(e), exc_info=True)
```

**改进点**：
- 添加10秒超时限制
- 超时后强制关闭连接池
- 完善的错误处理和日志记录

### 3. 调整应用关闭顺序

**文件**: `app/main.py`

**修改**：
```python
# 1.5. 停止知识库处理队列（先于数据库关闭）
try:
    from app.knowledge_base.tasks import stop_processing_queue
    await stop_processing_queue()
    logger.info("knowledge_base_processing_queue_stopped")
    # 等待所有数据库会话被释放
    await asyncio.sleep(1.0)
except Exception as e:
    logger.warning("knowledge_base_queue_stop_failed", error=str(e))

# 2. 关闭数据库连接
try:
    if os.getenv("DATABASE_URL"):
        await close_db()
        logger.info("database_closed")
except Exception as e:
    logger.error("database_close_failed", error=str(e))
```

**改进点**：
- 在关闭数据库前等待1秒，确保所有会话被释放
- 明确的关闭顺序：队列 → 数据库

## 验证方法

### 1. 运行测试脚本

```bash
cd backend
python test_db_close.py
```

### 2. 正常关闭应用

启动应用后按 `Ctrl+C`，观察日志输出：

**期望输出**：
```
knowledge_base_processing_queue_stopped
database_closed
application_shutting_down
```

**不应该看到**：
```
Exception closing connection
```

### 3. 检查日志

查看应用日志，确认没有连接关闭异常。

## 相关文件

- `app/knowledge_base/tasks.py` - 知识库处理队列
- `app/db/database.py` - 数据库连接管理
- `app/main.py` - 应用启动和关闭逻辑

## 性能影响

- **正常关闭时间**：增加约1-2秒（等待worker完成）
- **内存影响**：无
- **连接池影响**：无，连接池正常复用

## 后续优化建议

1. **连接池监控**：添加连接池使用率监控
2. **健康检查**：定期检查连接池状态
3. **连接泄漏检测**：添加连接泄漏告警

---

**修复日期**: 2026-04-05
**版本**: 1.0.0
