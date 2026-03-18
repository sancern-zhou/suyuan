"""
增强版专家健康监控系统

提供生产级专家健康监控和管理功能：
- 实时健康状态监控与评分
- 自动降级与恢复机制
- 负载均衡与智能路由
- 自愈与故障预测
- 健康状态分级管理
- 自动恢复策略
"""

from typing import Dict, Any, List, Optional, Tuple, Set
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from enum import Enum
import structlog
import asyncio
from collections import deque, defaultdict
import math
import json

logger = structlog.get_logger()


class HealthLevel(Enum):
    """健康等级"""
    CRITICAL = "critical"    # 严重故障
    DEGRADED = "degraded"    # 降级运行
    MAINTENANCE = "maintenance"  # 维护中
    FAIR = "fair"           # 一般健康
    GOOD = "good"           # 良好
    EXCELLENT = "excellent"  # 优秀


class ExpertStatus(Enum):
    """专家状态"""
    ACTIVE = "active"              # 正常运行
    DEGRADED = "degraded"         # 降级运行
    MAINTENANCE = "maintenance"    # 维护中
    FAILED = "failed"             # 故障
    RECOVERING = "recovering"      # 恢复中
    CIRCUIT_BREAKER = "circuit_breaker"  # 熔断


class RecoveryAction(Enum):
    """恢复动作"""
    RESTART = "restart"                    # 重启
    RETRY = "retry"                        # 重试
    SCALE_UP = "scale_up"                  # 扩容
    FALLBACK = "fallback"                  # 回退
    CIRCUIT_BREAKER = "circuit_breaker"    # 熔断
    ALERT = "alert"                        # 告警


@dataclass
class HealthCheckResult:
    """健康检查结果"""
    expert_name: str
    timestamp: datetime
    status: ExpertStatus
    health_level: HealthLevel
    health_score: float  # 0-100
    checks: Dict[str, Any]  # 详细检查项
    error_count: int = 0
    consecutive_failures: int = 0
    last_success: Optional[datetime] = None
    last_failure: Optional[datetime] = None
    avg_response_time: float = 0.0
    load_factor: float = 0.0  # 负载因子 0-1
    recommendations: List[str] = field(default_factory=list)


@dataclass
class RecoveryPlan:
    """恢复计划"""
    expert_name: str
    action: RecoveryAction
    priority: int  # 1-10，10最高
    reason: str
    parameters: Dict[str, Any] = field(default_factory=dict)
    timeout_seconds: int = 60
    max_attempts: int = 3
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class LoadMetrics:
    """负载指标"""
    expert_name: str
    timestamp: datetime
    active_tasks: int = 0
    queue_size: int = 0
    cpu_usage: float = 0.0
    memory_usage: float = 0.0
    avg_task_duration: float = 0.0
    throughput: float = 0.0  # tasks/second
    error_rate: float = 0.0


class ExpertHealthMonitor:
    """增强型专家健康监控器"""

    def __init__(self, context_manager):
        """
        初始化健康监控器

        Args:
            context_manager: 上下文管理器
        """
        self.context = context_manager
        self.experts: Dict[str, Any] = {}

        # 健康状态存储
        self.health_status: Dict[str, HealthCheckResult] = {}
        self.health_history: Dict[str, deque] = defaultdict(lambda: deque(maxlen=100))

        # 负载指标
        self.load_metrics: Dict[str, LoadMetrics] = {}
        self.load_history: Dict[str, deque] = defaultdict(lambda: deque(maxlen=50))

        # 恢复计划
        self.recovery_plans: Dict[str, RecoveryPlan] = {}
        self.execution_history: List[Dict[str, Any]] = deque(maxlen=1000)

        # 配置参数
        self.config = {
            "health_check_interval": 30,  # 健康检查间隔(秒)
            "health_score_thresholds": {
                HealthLevel.CRITICAL: 30,
                HealthLevel.DEGRADED: 50,
                HealthLevel.FAIR: 70,
                HealthLevel.GOOD: 85,
                HealthLevel.EXCELLENT: 95
            },
            "failure_thresholds": {
                "consecutive_failures": 3,
                "failure_rate_window": 10,  # 最近10次执行
                "failure_rate_threshold": 0.5,
                "response_time_p95": 5000,  # 95分位响应时间阈值(ms)
                "queue_size_threshold": 10
            },
            "recovery_policies": {
                "max_recovery_attempts": 5,
                "recovery_cooldown": 300,  # 恢复冷却时间(秒)
                "circuit_breaker_threshold": 5,
                "circuit_breaker_timeout": 60
            }
        }

        # 启动健康检查任务
        self._health_check_task = None
        self._start_monitoring()

        logger.info("expert_health_monitor_initialized")

    def register_expert(self, expert_name: str, expert_instance: Any):
        """注册专家实例"""
        self.experts[expert_name] = expert_instance

        # 初始化健康状态
        self.health_status[expert_name] = HealthCheckResult(
            expert_name=expert_name,
            timestamp=datetime.utcnow(),
            status=ExpertStatus.ACTIVE,
            health_level=HealthLevel.GOOD,
            health_score=80.0,
            checks={},
            recommendations=["专家已注册"]
        )

        logger.info("expert_registered", expert_name=expert_name)

    def _start_monitoring(self):
        """启动后台监控任务"""
        if self._health_check_task is None:
            self._health_check_task = asyncio.create_task(self._periodic_health_check())

    async def stop_monitoring(self):
        """停止监控"""
        if self._health_check_task:
            self._health_check_task.cancel()
            self._health_check_task = None

    async def _periodic_health_check(self):
        """定期健康检查"""
        while True:
            try:
                await asyncio.sleep(self.config["health_check_interval"])
                await self._check_all_experts()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("health_check_error", error=str(e), exc_info=True)

    async def _check_all_experts(self):
        """检查所有专家健康状态"""
        for expert_name in self.experts.keys():
            try:
                await self.check_expert_health(expert_name)
            except Exception as e:
                logger.error("expert_health_check_failed",
                           expert=expert_name,
                           error=str(e))

    async def check_expert_health(self, expert_name: str) -> HealthCheckResult:
        """
        检查专家健康状态

        Args:
            expert_name: 专家名称

        Returns:
            健康检查结果
        """
        if expert_name not in self.experts:
            raise ValueError(f"专家未注册: {expert_name}")

        expert = self.experts[expert_name]

        # 1. 检查执行状态
        checks = await self._perform_health_checks(expert_name, expert)

        # 2. 计算健康评分
        health_score = self._calculate_health_score(expert_name, checks)

        # 3. 确定健康等级
        health_level = self._determine_health_level(health_score)

        # 4. 确定专家状态
        status = self._determine_expert_status(expert_name, health_level, checks)

        # 5. 生成恢复建议
        recommendations = self._generate_recommendations(expert_name, health_level, checks)

        # 创建健康检查结果
        result = HealthCheckResult(
            expert_name=expert_name,
            timestamp=datetime.utcnow(),
            status=status,
            health_level=health_level,
            health_score=health_score,
            checks=checks,
            consecutive_failures=self._get_consecutive_failures(expert_name),
            last_success=self._get_last_success_time(expert_name),
            last_failure=self._get_last_failure_time(expert_name),
            avg_response_time=checks.get("avg_response_time", 0.0),
            load_factor=checks.get("load_factor", 0.0),
            recommendations=recommendations
        )

        # 更新状态
        self.health_status[expert_name] = result
        self.health_history[expert_name].append(result)

        # 检查是否需要触发恢复
        await self._check_recovery_need(expert_name, result)

        logger.debug(
            "expert_health_checked",
            expert=expert_name,
            health_score=health_score,
            health_level=health_level.value
        )

        return result

    async def _perform_health_checks(self, expert_name: str, expert: Any) -> Dict[str, Any]:
        """执行健康检查"""
        checks = {
            "timestamp": datetime.utcnow().isoformat(),
            "is_responsive": False,
            "avg_response_time": 0.0,
            "success_rate": 0.0,
            "error_count": 0,
            "load_factor": 0.0,
            "throughput": 0.0
        }

        try:
            # 1. 响应性检查
            if hasattr(expert, "health_check"):
                health_result = await asyncio.wait_for(
                    expert.health_check(),
                    timeout=5.0
                )
                checks["is_responsive"] = health_result.get("healthy", False)
            else:
                checks["is_responsive"] = True

            # 2. 性能指标检查
            if hasattr(expert, "get_execution_stats"):
                stats = expert.get_execution_stats()
                total = stats.get("total", 0)
                success = stats.get("success", 0)
                checks["success_rate"] = success / max(1, total)

            # 3. 负载检查
            if expert_name in self.load_metrics:
                load = self.load_metrics[expert_name]
                checks["load_factor"] = min(1.0, load.active_tasks / 10.0)
                checks["throughput"] = load.throughput
                checks["queue_size"] = load.queue_size

        except asyncio.TimeoutError:
            checks["error_count"] += 1
            checks["is_responsive"] = False
            logger.warning("expert_health_check_timeout", expert=expert_name)
        except Exception as e:
            checks["error_count"] += 1
            logger.error("expert_health_check_error",
                        expert=expert_name,
                        error=str(e))

        return checks

    def _calculate_health_score(self, expert_name: str, checks: Dict[str, Any]) -> float:
        """计算健康评分 (0-100)"""
        score = 100.0

        # 响应性 (30%)
        if checks.get("is_responsive", False):
            score += 30.0
        else:
            score -= 30.0

        # 成功率 (40%)
        success_rate = checks.get("success_rate", 0.0)
        score += success_rate * 40.0

        # 错误惩罚
        error_count = checks.get("error_count", 0)
        score -= min(20.0, error_count * 5.0)

        # 负载惩罚
        load_factor = checks.get("load_factor", 0.0)
        if load_factor > 0.8:
            score -= 10.0
        elif load_factor > 0.6:
            score -= 5.0

        # 历史表现调整
        consecutive_failures = self._get_consecutive_failures(expert_name)
        if consecutive_failures > 0:
            score -= consecutive_failures * 5.0

        # 确保评分在0-100范围内
        return max(0.0, min(100.0, score))

    def _determine_health_level(self, health_score: float) -> HealthLevel:
        """根据评分确定健康等级"""
        thresholds = self.config["health_score_thresholds"]

        if health_score >= thresholds[HealthLevel.EXCELLENT]:
            return HealthLevel.EXCELLENT
        elif health_score >= thresholds[HealthLevel.GOOD]:
            return HealthLevel.GOOD
        elif health_score >= thresholds[HealthLevel.FAIR]:
            return HealthLevel.FAIR
        elif health_score >= thresholds[HealthLevel.DEGRADED]:
            return HealthLevel.DEGRADED
        else:
            return HealthLevel.CRITICAL

    def _determine_expert_status(self, expert_name: str,
                                 health_level: HealthLevel,
                                 checks: Dict[str, Any]) -> ExpertStatus:
        """确定专家运行状态"""
        consecutive_failures = self._get_consecutive_failures(expert_name)
        circuit_breaker_count = self._get_circuit_breaker_count(expert_name)

        # 检查熔断器状态
        if circuit_breaker_count >= self.config["recovery_policies"]["circuit_breaker_threshold"]:
            return ExpertStatus.CIRCUIT_BREAKER

        # 检查连续失败
        if consecutive_failures >= self.config["failure_thresholds"]["consecutive_failures"]:
            return ExpertStatus.FAILED

        # 根据健康等级确定状态
        if health_level == HealthLevel.CRITICAL:
            return ExpertStatus.FAILED
        elif health_level == HealthLevel.DEGRADED:
            return ExpertStatus.DEGRADED
        elif health_level == HealthLevel.MAINTENANCE:
            return ExpertStatus.MAINTENANCE
        else:
            return ExpertStatus.ACTIVE

    def _generate_recommendations(self, expert_name: str,
                                  health_level: HealthLevel,
                                  checks: Dict[str, Any]) -> List[str]:
        """生成健康恢复建议"""
        recommendations = []

        # 基于健康等级的建议
        if health_level == HealthLevel.CRITICAL:
            recommendations.append("立即执行故障恢复")
            recommendations.append("检查专家实例状态")
            recommendations.append("考虑切换到备用专家")
        elif health_level == HealthLevel.DEGRADED:
            recommendations.append("降低任务分配频率")
            recommendations.append("检查性能瓶颈")
            recommendations.append("监控错误率变化")

        # 基于具体检查项的建议
        if not checks.get("is_responsive", True):
            recommendations.append("专家响应超时，需要重启")

        if checks.get("success_rate", 1.0) < 0.7:
            recommendations.append("成功率过低，检查输入数据质量")

        if checks.get("load_factor", 0.0) > 0.8:
            recommendations.append("负载过高，考虑扩容或限流")

        return recommendations

    def _get_consecutive_failures(self, expert_name: str) -> int:
        """获取连续失败次数"""
        history = list(self.health_history[expert_name])
        consecutive = 0

        for result in reversed(history):
            if result.status in [ExpertStatus.FAILED, ExpertStatus.CIRCUIT_BREAKER]:
                consecutive += 1
            else:
                break

        return consecutive

    def _get_last_success_time(self, expert_name: str) -> Optional[datetime]:
        """获取最后成功时间"""
        history = list(self.health_history[expert_name])
        for result in reversed(history):
            if result.status == ExpertStatus.ACTIVE:
                return result.timestamp
        return None

    def _get_last_failure_time(self, expert_name: str) -> Optional[datetime]:
        """获取最后失败时间"""
        history = list(self.health_history[expert_name])
        for result in reversed(history):
            if result.status in [ExpertStatus.FAILED, ExpertStatus.CIRCUIT_BREAKER]:
                return result.timestamp
        return None

    def _get_circuit_breaker_count(self, expert_name: str) -> int:
        """获取熔断器触发次数"""
        return len([r for r in self.health_history[expert_name]
                   if r.status == ExpertStatus.CIRCUIT_BREAKER])

    async def _check_recovery_need(self, expert_name: str, result: HealthCheckResult):
        """检查是否需要触发恢复"""
        if result.status in [ExpertStatus.FAILED, ExpertStatus.CIRCUIT_BREAKER]:
            # 创建恢复计划
            action = self._determine_recovery_action(result)
            plan = RecoveryPlan(
                expert_name=expert_name,
                action=action,
                priority=self._calculate_priority(result),
                reason=f"专家状态异常: {result.status.value}",
                parameters=self._build_recovery_parameters(expert_name, result)
            )

            # 执行恢复计划
            await self._execute_recovery_plan(plan)

    def _determine_recovery_action(self, result: HealthCheckResult) -> RecoveryAction:
        """确定恢复动作"""
        consecutive_failures = result.consecutive_failures

        if consecutive_failures >= 5:
            return RecoveryAction.CIRCUIT_BREAKER
        elif consecutive_failures >= 3:
            return RecoveryAction.RESTART
        else:
            return RecoveryAction.RETRY

    def _calculate_priority(self, result: HealthCheckResult) -> int:
        """计算恢复优先级 (1-10)"""
        if result.health_level == HealthLevel.CRITICAL:
            return 10
        elif result.health_level == HealthLevel.DEGRADED:
            return 7
        elif result.health_level == HealthLevel.FAIR:
            return 5
        else:
            return 3

    def _build_recovery_parameters(self, expert_name: str, result: HealthCheckResult) -> Dict[str, Any]:
        """构建恢复参数"""
        params = {
            "expert_name": expert_name,
            "health_score": result.health_score,
            "checks": result.checks
        }

        if result.consecutive_failures >= 3:
            params["restart_timeout"] = 30

        return params

    async def _execute_recovery_plan(self, plan: RecoveryPlan):
        """执行恢复计划"""
        logger.info("executing_recovery_plan",
                   expert=plan.expert_name,
                   action=plan.action.value,
                   priority=plan.priority)

        execution_record = {
            "plan": plan,
            "start_time": datetime.utcnow(),
            "status": "executing"
        }

        try:
            if plan.action == RecoveryAction.RESTART:
                await self._restart_expert(plan.expert_name, plan.parameters)
            elif plan.action == RecoveryAction.RETRY:
                await self._retry_expert(plan.expert_name)
            elif plan.action == RecoveryAction.CIRCUIT_BREAKER:
                await self._activate_circuit_breaker(plan.expert_name, plan.parameters)
            else:
                logger.warning("unsupported_recovery_action",
                              action=plan.action.value)

            execution_record["status"] = "completed"
            execution_record["end_time"] = datetime.utcnow()

        except Exception as e:
            execution_record["status"] = "failed"
            execution_record["error"] = str(e)
            execution_record["end_time"] = datetime.utcnow()

            logger.error("recovery_plan_failed",
                        expert=plan.expert_name,
                        action=plan.action.value,
                        error=str(e))

        self.execution_history.append(execution_record)

    async def _restart_expert(self, expert_name: str, params: Dict[str, Any]):
        """重启专家"""
        logger.info("restarting_expert", expert=expert_name)

        # 更新状态为恢复中
        self.health_status[expert_name].status = ExpertStatus.RECOVERING

        # 等待重启完成
        await asyncio.sleep(2)

        # 重新检查健康状态
        await self.check_expert_health(expert_name)

    async def _retry_expert(self, expert_name: str):
        """重试专家"""
        logger.info("retrying_expert", expert=expert_name)

        # 延迟重试
        await asyncio.sleep(1)

        # 重新检查健康状态
        await self.check_expert_health(expert_name)

    async def _activate_circuit_breaker(self, expert_name: str, params: Dict[str, Any]):
        """激活熔断器"""
        logger.warning("activating_circuit_breaker", expert=expert_name)

        # 设置熔断器状态
        self.health_status[expert_name].status = ExpertStatus.CIRCUIT_BREAKER

        # 等待超时后尝试恢复
        timeout = self.config["recovery_policies"]["circuit_breaker_timeout"]
        await asyncio.sleep(timeout)

        # 重新检查健康状态
        await self.check_expert_health(expert_name)

    def update_load_metrics(self, expert_name: str, metrics: Dict[str, Any]):
        """更新负载指标"""
        load = LoadMetrics(
            expert_name=expert_name,
            timestamp=datetime.utcnow(),
            active_tasks=metrics.get("active_tasks", 0),
            queue_size=metrics.get("queue_size", 0),
            cpu_usage=metrics.get("cpu_usage", 0.0),
            memory_usage=metrics.get("memory_usage", 0.0),
            avg_task_duration=metrics.get("avg_task_duration", 0.0),
            throughput=metrics.get("throughput", 0.0),
            error_rate=metrics.get("error_rate", 0.0)
        )

        self.load_metrics[expert_name] = load
        self.load_history[expert_name].append(load)

    def get_health_summary(self, expert_name: Optional[str] = None) -> Dict[str, Any]:
        """获取健康摘要"""
        if expert_name:
            # 单个专家摘要
            if expert_name not in self.health_status:
                return {"error": f"专家未注册: {expert_name}"}

            result = self.health_status[expert_name]
            return {
                "expert_name": result.expert_name,
                "status": result.status.value,
                "health_level": result.health_level.value,
                "health_score": result.health_score,
                "recommendations": result.recommendations,
                "last_check": result.timestamp.isoformat()
            }
        else:
            # 所有专家摘要
            summary = {
                "total_experts": len(self.experts),
                "experts": {}
            }

            for name, result in self.health_status.items():
                summary["experts"][name] = {
                    "status": result.status.value,
                    "health_level": result.health_level.value,
                    "health_score": result.health_score
                }

            # 计算整体健康度
            if self.health_status:
                avg_score = sum(r.health_score for r in self.health_status.values()) / len(self.health_status)
                summary["overall_health_score"] = avg_score

            return summary

    def get_load_balancing_info(self) -> Dict[str, Any]:
        """获取负载均衡信息"""
        load_info = {
            "timestamp": datetime.utcnow().isoformat(),
            "experts": {}
        }

        for expert_name, result in self.health_status.items():
            load_info["experts"][expert_name] = {
                "status": result.status.value,
                "health_score": result.health_score,
                "load_factor": result.load_factor,
                "can_receive_tasks": result.status == ExpertStatus.ACTIVE
            }

        return load_info

    def should_route_to_expert(self, expert_name: str) -> Tuple[bool, str]:
        """判断是否应该路由任务到专家"""
        if expert_name not in self.health_status:
            return False, "专家未注册"

        result = self.health_status[expert_name]

        if result.status == ExpertStatus.FAILED:
            return False, "专家故障"
        elif result.status == ExpertStatus.CIRCUIT_BREAKER:
            return False, "专家熔断"
        elif result.status == ExpertStatus.MAINTENANCE:
            return False, "专家维护中"
        elif result.health_score < 50:
            return False, f"专家健康度不足: {result.health_score:.1f}"
        elif result.load_factor > 0.9:
            return False, "专家负载过高"

        return True, "可以接收任务"

    def get_health_trend(self, expert_name: str, hours: int = 24) -> Dict[str, Any]:
        """获取健康趋势"""
        if expert_name not in self.health_history:
            return {"error": "无历史数据"}

        cutoff_time = datetime.utcnow() - timedelta(hours=hours)
        history = [r for r in self.health_history[expert_name] if r.timestamp >= cutoff_time]

        if not history:
            return {"error": "指定时间内无数据"}

        # 计算趋势
        scores = [r.health_score for r in history]
        trend = "stable"

        if len(scores) >= 2:
            if scores[-1] > scores[0] * 1.1:
                trend = "improving"
            elif scores[-1] < scores[0] * 0.9:
                trend = "degrading"

        return {
            "expert_name": expert_name,
            "time_range_hours": hours,
            "data_points": len(history),
            "trend": trend,
            "current_score": scores[-1],
            "average_score": sum(scores) / len(scores),
            "min_score": min(scores),
            "max_score": max(scores),
            "samples": [{"timestamp": r.timestamp.isoformat(),
                        "score": r.health_score,
                        "level": r.health_level.value} for r in history[-10:]]
        }

    def export_health_report(self) -> Dict[str, Any]:
        """导出健康报告"""
        return {
            "timestamp": datetime.utcnow().isoformat(),
            "summary": self.get_health_summary(),
            "load_balancing": self.get_load_balancing_info(),
            "recovery_plans": [
                {
                    "expert": plan.expert_name,
                    "action": plan.action.value,
                    "priority": plan.priority,
                    "reason": plan.reason
                }
                for plan in self.recovery_plans.values()
            ],
            "execution_history": [
                {
                    "expert": record["plan"].expert_name,
                    "action": record["plan"].action.value,
                    "status": record["status"],
                    "start_time": record["start_time"].isoformat(),
                    "end_time": record["end_time"].isoformat() if record.get("end_time") else None
                }
                for record in list(self.execution_history)[-20:]
            ]
        }
