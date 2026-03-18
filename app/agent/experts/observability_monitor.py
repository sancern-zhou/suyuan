"""
多专家协同系统 - 可观测性与监控

提供全方位的系统监控和可观测性功能：
- 执行链路追踪与可视化
- 专家健康状态监控
- 性能指标统计
- 告警与异常检测
- 实时监控面板数据
"""

from typing import Dict, Any, List, Optional, Union
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from enum import Enum
import structlog
import asyncio
from collections import defaultdict, deque
import json

logger = structlog.get_logger()


class MetricType(Enum):
    """指标类型枚举"""
    COUNTER = "counter"          # 计数器
    GAUGE = "gauge"              # 仪表盘
    HISTOGRAM = "histogram"      # 直方图
    TIMER = "timer"              # 计时器


class AlertSeverity(Enum):
    """告警级别"""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class AlertStatus(Enum):
    """告警状态"""
    ACTIVE = "active"
    RESOLVED = "resolved"
    SUPPRESSED = "suppressed"


@dataclass
class ExecutionTrace:
    """执行链路追踪记录"""
    trace_id: str                           # 追踪ID
    parent_trace_id: Optional[str]          # 父追踪ID
    operation_name: str                     # 操作名称
    operation_type: str                     # 操作类型 (expert/router/tool)
    status: str                            # 状态 (success/failed/partial)
    start_time: datetime                   # 开始时间
    end_time: Optional[datetime] = None    # 结束时间
    duration_ms: Optional[float] = None    # 执行时长(毫秒)
    expert_name: Optional[str] = None      # 专家名称
    input_params: Dict[str, Any] = field(default_factory=dict)    # 输入参数
    output_result: Dict[str, Any] = field(default_factory=dict)   # 输出结果
    error_message: Optional[str] = None    # 错误信息
    metadata: Dict[str, Any] = field(default_factory=dict)        # 元数据
    child_traces: List['ExecutionTrace'] = field(default_factory=list)  # 子追踪


@dataclass
class PerformanceMetric:
    """性能指标记录"""
    metric_name: str                        # 指标名称
    metric_type: MetricType                # 指标类型
    value: Union[int, float]               # 指标值
    labels: Dict[str, str] = field(default_factory=dict)  # 标签
    timestamp: datetime = field(default_factory=datetime.utcnow)  # 时间戳


@dataclass
class HealthMetric:
    """健康指标记录"""
    expert_name: str                       # 专家名称
    timestamp: datetime = field(default_factory=datetime.utcnow)
    total_executions: int = 0              # 总执行次数
    successful_executions: int = 0         # 成功次数
    failed_executions: int = 0             # 失败次数
    avg_response_time_ms: float = 0.0      # 平均响应时间
    error_types: Dict[str, int] = field(default_factory=dict)  # 错误类型统计
    last_success_time: Optional[datetime] = None  # 最后成功时间
    last_failure_time: Optional[datetime] = None   # 最后失败时间


@dataclass
class SystemAlert:
    """系统告警"""
    alert_id: str                          # 告警ID
    severity: AlertSeverity               # 告警级别
    title: str                            # 告警标题
    description: str                      # 告警描述
    source: str                           # 告警来源
    timestamp: datetime = field(default_factory=datetime.utcnow)
    status: AlertStatus = AlertStatus.ACTIVE
    resolved_at: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class ObservabilityMonitor:
    """可观测性监控器"""

    def __init__(self, max_trace_history: int = 10000, max_metrics_history: int = 50000):
        """
        初始化监控器

        Args:
            max_trace_history: 最大追踪记录数
            max_metrics_history: 最大指标记录数
        """
        # 执行追踪存储
        self.traces: Dict[str, ExecutionTrace] = {}
        self.trace_history = deque(maxlen=max_trace_history)

        # 性能指标存储
        self.metrics: Dict[str, List[PerformanceMetric]] = defaultdict(lambda: deque(maxlen=1000))
        self.metrics_history = deque(maxlen=max_metrics_history)

        # 健康指标存储
        self.health_metrics: Dict[str, deque] = defaultdict(lambda: deque(maxlen=100))

        # 告警存储
        self.alerts: Dict[str, SystemAlert] = {}
        self.alert_history = deque(maxlen=1000)

        # 实时统计
        self.real_time_stats = {
            "total_traces": 0,
            "active_traces": 0,
            "total_executions": 0,
            "successful_executions": 0,
            "failed_executions": 0,
            "avg_response_time": 0.0
        }

        # 告警阈值配置
        self.alert_thresholds = {
            "expert_success_rate_min": 0.5,      # 专家最小成功率
            "expert_avg_response_time_max": 5000,  # 专家最大平均响应时间(ms)
            "pipeline_failure_rate_max": 0.3,     # Pipeline最大失败率
            "error_rate_max": 0.1                 # 最大错误率
        }

        logger.info("observability_monitor_initialized", max_trace_history=max_trace_history)

    # ==================== 执行链路追踪 ====================

    def start_trace(
        self,
        trace_id: str,
        operation_name: str,
        operation_type: str,
        expert_name: Optional[str] = None,
        parent_trace_id: Optional[str] = None,
        input_params: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        开始执行追踪

        Args:
            trace_id: 追踪ID
            operation_name: 操作名称
            operation_type: 操作类型
            expert_name: 专家名称
            parent_trace_id: 父追踪ID
            input_params: 输入参数
            metadata: 元数据

        Returns:
            追踪ID字符串
        """
        trace = ExecutionTrace(
            trace_id=trace_id,
            parent_trace_id=parent_trace_id,
            operation_name=operation_name,
            operation_type=operation_type,
            status="running",
            start_time=datetime.utcnow(),
            expert_name=expert_name,
            input_params=input_params or {},
            metadata=metadata or {}
        )

        self.traces[trace_id] = trace
        self.real_time_stats["total_traces"] += 1
        self.real_time_stats["active_traces"] += 1

        logger.debug(
            "trace_started",
            trace_id=trace_id,
            operation=operation_name,
            expert=expert_name,
            parent=parent_trace_id
        )

        return trace_id

    def finish_trace(
        self,
        trace_id: str,
        status: str,
        output_result: Optional[Dict[str, Any]] = None,
        error_message: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Optional[ExecutionTrace]:
        """
        完成执行追踪

        Args:
            trace_id: 追踪ID
            status: 状态
            output_result: 输出结果
            error_message: 错误信息
            metadata: 元数据

        Returns:
            完成的追踪对象
        """
        if trace_id not in self.traces:
            logger.warning("trace_not_found", trace_id=trace_id)
            return None

        trace = self.traces[trace_id]

        trace.end_time = datetime.utcnow()
        trace.duration_ms = (trace.end_time - trace.start_time).total_seconds() * 1000
        trace.status = status
        trace.output_result = output_result or {}
        trace.error_message = error_message
        if metadata:
            trace.metadata.update(metadata)

        # 更新实时统计
        self.real_time_stats["active_traces"] -= 1
        self.real_time_stats["total_executions"] += 1

        if status == "success":
            self.real_time_stats["successful_executions"] += 1
        elif status == "failed":
            self.real_time_stats["failed_executions"] += 1

        # 记录性能指标
        self.record_metric(
            f"{trace.operation_type}.duration",
            MetricType.HISTOGRAM,
            trace.duration_ms,
            labels={
                "operation": trace.operation_name,
                "expert": trace.expert_name or "unknown",
                "status": status
            }
        )

        # 移动到历史记录
        self.trace_history.append(trace)

        # 从活动追踪中移除
        del self.traces[trace_id]

        logger.debug(
            "trace_finished",
            trace_id=trace_id,
            status=status,
            duration_ms=trace.duration_ms
        )

        return trace

    def get_trace_tree(self, trace_id: str) -> Optional[ExecutionTrace]:
        """
        获取完整的追踪树

        Args:
            trace_id: 根追踪ID

        Returns:
            追踪树
        """
        def build_tree(trace: ExecutionTrace) -> ExecutionTrace:
            """递归构建追踪树"""
            children = [
                build_tree(t) for t in self.traces.values()
                if t.parent_trace_id == trace.trace_id
            ]
            trace.child_traces = children
            return trace

        root_trace = self.traces.get(trace_id)
        if root_trace:
            return build_tree(root_trace)
        return None

    # ==================== 性能指标 ====================

    def record_metric(
        self,
        metric_name: str,
        metric_type: Union[MetricType, str],
        value: Union[int, float],
        labels: Optional[Dict[str, str]] = None
    ):
        """
        记录性能指标

        Args:
            metric_name: 指标名称
            metric_type: 指标类型 (MetricType枚举或字符串)
            value: 指标值
            labels: 标签
        """
        # 处理字符串类型的metric_type
        if isinstance(metric_type, str):
            try:
                metric_type = MetricType(metric_type)
            except ValueError:
                metric_type = MetricType.COUNTER  # 默认类型

        metric = PerformanceMetric(
            metric_name=metric_name,
            metric_type=metric_type,
            value=value,
            labels=labels or {}
        )

        self.metrics[metric_name].append(metric)
        self.metrics_history.append(metric)

        logger.debug(
            "metric_recorded",
            name=metric_name,
            type=metric_type.value,
            value=value,
            labels=labels
        )

    def get_metric_series(
        self,
        metric_name: str,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        labels_filter: Optional[Dict[str, str]] = None
    ) -> List[PerformanceMetric]:
        """
        获取指标时间序列

        Args:
            metric_name: 指标名称
            start_time: 开始时间
            end_time: 结束时间
            labels_filter: 标签过滤器

        Returns:
            指标列表
        """
        if metric_name not in self.metrics:
            return []

        filtered_metrics = list(self.metrics[metric_name])

        # 时间过滤
        if start_time:
            filtered_metrics = [m for m in filtered_metrics if m.timestamp >= start_time]
        if end_time:
            filtered_metrics = [m for m in filtered_metrics if m.timestamp <= end_time]

        # 标签过滤
        if labels_filter:
            filtered_metrics = [
                m for m in filtered_metrics
                if all(m.labels.get(k) == v for k, v in labels_filter.items())
            ]

        return filtered_metrics

    # ==================== 健康监控 ====================

    def update_health_metric(
        self,
        expert_name: str,
        execution_time_ms: float,
        success: bool,
        error_type: Optional[str] = None
    ):
        """
        更新专家健康指标

        Args:
            expert_name: 专家名称
            execution_time_ms: 执行时间(毫秒)
            success: 是否成功
            error_type: 错误类型
        """
        health_metrics = self.health_metrics[expert_name]

        if health_metrics:
            last_metric = health_metrics[-1]
            metric = HealthMetric(
                expert_name=expert_name,
                total_executions=last_metric.total_executions + 1,
                successful_executions=last_metric.successful_executions + (1 if success else 0),
                failed_executions=last_metric.failed_executions + (0 if success else 1),
                avg_response_time_ms=(
                    (last_metric.avg_response_time_ms * last_metric.total_executions + execution_time_ms)
                    / (last_metric.total_executions + 1)
                ),
                error_types=last_metric.error_types.copy(),
                last_success_time=datetime.utcnow() if success else last_metric.last_success_time,
                last_failure_time=datetime.utcnow() if not success else last_metric.last_failure_time
            )

            # 更新错误类型统计
            if not success and error_type:
                metric.error_types[error_type] = metric.error_types.get(error_type, 0) + 1
        else:
            metric = HealthMetric(
                expert_name=expert_name,
                total_executions=1,
                successful_executions=1 if success else 0,
                failed_executions=0 if success else 1,
                avg_response_time_ms=execution_time_ms,
                error_types={error_type: 1} if not success and error_type else {},
                last_success_time=datetime.utcnow() if success else None,
                last_failure_time=datetime.utcnow() if not success else None
            )

        health_metrics.append(metric)

        # 检查告警条件
        self._check_health_alerts(metric)

        logger.debug(
            "health_metric_updated",
            expert=expert_name,
            success=success,
            duration_ms=execution_time_ms
        )

    def get_expert_health(
        self,
        expert_name: str,
        lookback_minutes: int = 60
    ) -> Optional[HealthMetric]:
        """
        获取专家健康状态

        Args:
            expert_name: 专家名称
            lookback_minutes: 回看分钟数

        Returns:
            健康指标
        """
        health_metrics = self.health_metrics.get(expert_name)
        if not health_metrics:
            return None

        cutoff_time = datetime.utcnow() - timedelta(minutes=lookback_minutes)
        recent_metrics = [m for m in health_metrics if m.timestamp >= cutoff_time]

        if not recent_metrics:
            return health_metrics[-1] if health_metrics else None

        # 聚合最近指标
        latest = recent_metrics[-1]
        return HealthMetric(
            expert_name=expert_name,
            total_executions=sum(m.total_executions for m in recent_metrics),
            successful_executions=sum(m.successful_executions for m in recent_metrics),
            failed_executions=sum(m.failed_executions for m in recent_metrics),
            avg_response_time_ms=sum(m.avg_response_time_ms for m in recent_metrics) / len(recent_metrics),
            error_types=latest.error_types,
            last_success_time=latest.last_success_time,
            last_failure_time=latest.last_failure_time
        )

    # ==================== 告警系统 ====================

    def create_alert(
        self,
        severity: AlertSeverity,
        title: str,
        description: str,
        source: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> SystemAlert:
        """
        创建告警

        Args:
            severity: 告警级别
            title: 告警标题
            description: 告警描述
            source: 告警来源
            metadata: 元数据

        Returns:
            系统告警
        """
        alert_id = f"alert_{datetime.utcnow().strftime('%Y%m%d_%H%M%S_%f')}"

        alert = SystemAlert(
            alert_id=alert_id,
            severity=severity,
            title=title,
            description=description,
            source=source,
            metadata=metadata or {}
        )

        self.alerts[alert_id] = alert
        self.alert_history.append(alert)

        logger.warning(
            "alert_created",
            alert_id=alert_id,
            severity=severity.value,
            title=title,
            source=source
        )

        return alert

    def resolve_alert(self, alert_id: str):
        """解决告警"""
        alert = self.alerts.get(alert_id)
        if alert and alert.status == AlertStatus.ACTIVE:
            alert.status = AlertStatus.RESOLVED
            alert.resolved_at = datetime.utcnow()

            logger.info("alert_resolved", alert_id=alert_id)

    def get_active_alerts(self, severity: Optional[AlertSeverity] = None) -> List[SystemAlert]:
        """
        获取活跃告警

        Args:
            severity: 告警级别过滤

        Returns:
            告警列表
        """
        alerts = [a for a in self.alerts.values() if a.status == AlertStatus.ACTIVE]

        if severity:
            alerts = [a for a in alerts if a.severity == severity]

        return sorted(alerts, key=lambda a: a.timestamp, reverse=True)

    def _check_health_alerts(self, metric: HealthMetric):
        """检查健康告警条件"""
        # 检查成功率
        if metric.total_executions > 0:
            success_rate = metric.successful_executions / metric.total_executions
            if success_rate < self.alert_thresholds["expert_success_rate_min"]:
                self.create_alert(
                    AlertSeverity.WARNING,
                    f"专家 {metric.expert_name} 成功率过低",
                    f"成功率: {success_rate:.1%}, 阈值: {self.alert_thresholds['expert_success_rate_min']:.1%}",
                    f"expert:{metric.expert_name}",
                    {
                        "expert_name": metric.expert_name,
                        "success_rate": success_rate,
                        "threshold": self.alert_thresholds["expert_success_rate_min"]
                    }
                )

        # 检查响应时间
        if metric.avg_response_time_ms > self.alert_thresholds["expert_avg_response_time_max"]:
            self.create_alert(
                AlertSeverity.WARNING,
                f"专家 {metric.expert_name} 响应时间过长",
                f"平均响应时间: {metric.avg_response_time_ms:.0f}ms, 阈值: {self.alert_thresholds['expert_avg_response_time_max']}ms",
                f"expert:{metric.expert_name}",
                {
                    "expert_name": metric.expert_name,
                    "avg_response_time": metric.avg_response_time_ms,
                    "threshold": self.alert_thresholds["expert_avg_response_time_max"]
                }
            )

    # ==================== 实时监控面板 ====================

    def get_dashboard_data(self) -> Dict[str, Any]:
        """
        获取监控面板数据

        Returns:
            监控面板数据
        """
        # 计算当前错误率
        total = self.real_time_stats["total_executions"]
        failed = self.real_time_stats["failed_executions"]
        error_rate = failed / total if total > 0 else 0.0

        # 计算平均响应时间
        response_time_metrics = [
            m for m in self.metrics_history
            if m.metric_name.endswith(".duration") and m.metric_type == MetricType.HISTOGRAM
        ]
        avg_response_time = (
            sum(m.value for m in response_time_metrics) / len(response_time_metrics)
            if response_time_metrics else 0.0
        )

        # 获取各专家健康状态
        expert_health = {}
        for expert_name in self.health_metrics.keys():
            health = self.get_expert_health(expert_name)
            if health:
                success_rate = health.successful_executions / health.total_executions if health.total_executions > 0 else 0.0
                expert_health[expert_name] = {
                    "total_executions": health.total_executions,
                    "successful_executions": health.successful_executions,
                    "failed_executions": health.failed_executions,
                    "success_rate": success_rate,
                    "avg_response_time_ms": health.avg_response_time_ms,
                    "error_types": health.error_types
                }

        return {
            "timestamp": datetime.utcnow().isoformat(),
            "real_time_stats": {
                "total_traces": self.real_time_stats["total_traces"],
                "active_traces": self.real_time_stats["active_traces"],
                "total_executions": self.real_time_stats["total_executions"],
                "successful_executions": self.real_time_stats["successful_executions"],
                "failed_executions": self.real_time_stats["failed_executions"],
                "error_rate": error_rate,
                "avg_response_time_ms": avg_response_time
            },
            "expert_health": expert_health,
            "active_alerts": {
                "info": len(self.get_active_alerts(AlertSeverity.INFO)),
                "warning": len(self.get_active_alerts(AlertSeverity.WARNING)),
                "error": len(self.get_active_alerts(AlertSeverity.ERROR)),
                "critical": len(self.get_active_alerts(AlertSeverity.CRITICAL))
            },
            "recent_traces_count": len([t for t in self.trace_history if t.start_time >= datetime.utcnow() - timedelta(minutes=5)]),
            "recent_metrics_count": len([m for m in self.metrics_history if m.timestamp >= datetime.utcnow() - timedelta(minutes=5)])
        }

    # ==================== 系统状态摘要 ====================

    def get_system_summary(self) -> Dict[str, Any]:
        """获取系统状态摘要"""
        dashboard_data = self.get_dashboard_data()

        # 系统健康评分 (0-100)
        health_score = 100.0
        health_score -= dashboard_data["real_time_stats"]["error_rate"] * 50  # 错误率扣分
        health_score -= dashboard_data["active_alerts"]["warning"] * 5       # 警告扣分
        health_score -= dashboard_data["active_alerts"]["error"] * 10        # 错误扣分
        health_score -= dashboard_data["active_alerts"]["critical"] * 20     # 严重错误扣分
        health_score = max(0.0, health_score)

        # 系统状态等级
        if health_score >= 90:
            status_level = "excellent"
        elif health_score >= 70:
            status_level = "good"
        elif health_score >= 50:
            status_level = "fair"
        elif health_score >= 30:
            status_level = "poor"
        else:
            status_level = "critical"

        return {
            "timestamp": dashboard_data["timestamp"],
            "health_score": health_score,
            "status_level": status_level,
            "total_executions": dashboard_data["real_time_stats"]["total_executions"],
            "error_rate": dashboard_data["real_time_stats"]["error_rate"],
            "avg_response_time_ms": dashboard_data["real_time_stats"]["avg_response_time_ms"],
            "active_experts": len(dashboard_data["expert_health"]),
            "total_alerts": sum(dashboard_data["active_alerts"].values()),
            "system_status": "healthy" if health_score >= 70 else "degraded"
        }


# 全局监控实例
_global_monitor = None


def get_global_monitor() -> ObservabilityMonitor:
    """获取全局监控实例"""
    global _global_monitor
    if _global_monitor is None:
        _global_monitor = ObservabilityMonitor()
    return _global_monitor
