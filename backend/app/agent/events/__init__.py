"""
Agent Events Package

包含事件系统相关的模块：
- tool_lifecycle: 工具生命周期状态机
- error_classifier: 错误分类器（Phase 4）
- metrics: 指标收集器（Phase 3）
"""

# 避免类型提示问题，使用延迟导入
def __getattr__(name):
    if name == "ToolState":
        from app.agent.events.tool_lifecycle import ToolState
        return ToolState
    elif name == "ToolExecution":
        from app.agent.events.tool_lifecycle import ToolExecution
        return ToolExecution
    elif name == "ErrorClassifier":
        from app.agent.events.error_classifier import ErrorClassifier
        return ErrorClassifier
    elif name == "ErrorType":
        from app.agent.events.error_classifier import ErrorType
        return ErrorType
    elif name == "MetricsCollector":
        from app.agent.events.metrics import MetricsCollector
        return MetricsCollector
    elif name == "ToolMetric":
        from app.agent.events.metrics import ToolMetric
        return ToolMetric
    raise AttributeError(f"module {__name__} has no attribute {name}")

__all__ = [
    "ToolState",
    "ToolExecution",
    "ErrorClassifier",
    "ErrorType",
    "MetricsCollector",
    "ToolMetric",
]
