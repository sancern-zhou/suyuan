"""
Error Classifier - 智能错误分类和恢复策略

Phase 4: 错误分类器，自动检测错误类型并应用恢复策略
"""

from enum import Enum
from typing import Dict, Any
import structlog

logger = structlog.get_logger()


class ErrorType(Enum):
    """错误类型分类（用于恢复策略）

    每种错误类型都有对应的恢复策略：
    - TIMEOUT: 超时错误 → 重试（指数退避）
    - NETWORK: 网络错误 → 重试（线性退避）
    - VALIDATION: 参数验证错误 → 提供提示
    - PERMISSION: 权限错误 → 失败
    - RATE_LIMIT: 速率限制 → 等待后重试
    - UNKNOWN: 未知错误 → 失败
    """
    TIMEOUT = "timeout"
    NETWORK = "network"
    VALIDATION = "validation"
    PERMISSION = "permission"
    RATE_LIMIT = "rate_limit"
    UNKNOWN = "unknown"


class ErrorClassifier:
    """错误分类器：智能错误恢复

    自动检测错误类型并应用相应的恢复策略。
    """

    def classify(self, error: Exception) -> ErrorType:
        """将错误分类为可恢复的类别

        Args:
            error: 异常对象

        Returns:
            错误类型
        """
        error_msg = str(error).lower()

        if "timeout" in error_msg or "timed out" in error_msg:
            return ErrorType.TIMEOUT
        elif "connection" in error_msg or "network" in error_msg:
            return ErrorType.NETWORK
        elif "validation" in error_msg or "invalid" in error_msg:
            return ErrorType.VALIDATION
        elif "permission" in error_msg or "unauthorized" in error_msg:
            return ErrorType.PERMISSION
        elif "rate limit" in error_msg or "429" in error_msg:
            return ErrorType.RATE_LIMIT
        else:
            return ErrorType.UNKNOWN

    def get_recovery_strategy(self, error_type: ErrorType) -> Dict[str, Any]:
        """获取错误类型的恢复策略

        Args:
            error_type: 错误类型

        Returns:
            恢复策略配置
        """
        strategies = {
            ErrorType.TIMEOUT: {
                "action": "retry",
                "max_retries": 3,
                "backoff": "exponential"
            },
            ErrorType.NETWORK: {
                "action": "retry",
                "max_retries": 2,
                "backoff": "linear"
            },
            ErrorType.VALIDATION: {
                "action": "hint",
                "provide_hint": True
            },
            ErrorType.PERMISSION: {
                "action": "fail",
                "message": "Permission denied"
            },
            ErrorType.RATE_LIMIT: {
                "action": "wait",
                "wait_seconds": 60
            },
            ErrorType.UNKNOWN: {
                "action": "fail",
                "message": "Unknown error"
            }
        }
        return strategies.get(error_type, {"action": "fail"})
