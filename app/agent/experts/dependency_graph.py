"""
依赖图调度系统

实现基于依赖关系的智能调度：
- 支持并行执行
- 自动重试/跳过/替代
- 失败恢复机制
"""

from typing import Dict, Any, List, Set, Optional, Callable
from dataclasses import dataclass, field
from enum import Enum
import asyncio
import structlog
from datetime import datetime

logger = structlog.get_logger()


class TaskStatus(Enum):
    """任务状态枚举"""
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"
    RETRYING = "retrying"


class RetryStrategy(Enum):
    """重试策略枚举"""
    NONE = "none"           # 不重试
    EXPONENTIAL = "exponential"  # 指数退避
    FIXED = "fixed"         # 固定间隔
    SKIP_ON_FAIL = "skip_on_fail"  # 失败时跳过


@dataclass
class ExpertNode:
    """专家节点定义"""
    name: str
    expert_type: str
    dependencies: List[str] = field(default_factory=list)
    retry_strategy: RetryStrategy = RetryStrategy.EXPONENTIAL
    max_retries: int = 3
    retry_delay: float = 1.0
    timeout: float = 120.0
    optional: bool = False  # 是否为可选任务
    fallback_expert: Optional[str] = None  # 失败时的替代专家


@dataclass
class TaskResult:
    """任务执行结果"""
    task_name: str
    status: TaskStatus
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    diagnostics: Optional[Dict[str, Any]] = None
    execution_time: float = 0.0
    retry_count: int = 0
    timestamp: datetime = field(default_factory=datetime.utcnow)


class DependencyGraph:
    """依赖图调度器"""

    def __init__(self):
        """初始化依赖图"""
        self.nodes: Dict[str, ExpertNode] = {}
        self.task_status: Dict[str, TaskStatus] = {}
        self.execution_history: List[TaskResult] = []
        self.task_callbacks: Dict[str, Callable] = {}
        self.completed_tasks: Set[str] = set()
        self.failed_tasks: Set[str] = set()

    def add_node(self, node: ExpertNode):
        """添加专家节点"""
        self.nodes[node.name] = node
        self.task_status[node.name] = TaskStatus.PENDING
        logger.info("dependency_node_added", node=node.name, dependencies=node.dependencies)

    def add_callback(self, task_name: str, callback: Callable):
        """添加任务完成回调"""
        self.task_callbacks[task_name] = callback

    def get_ready_tasks(self) -> List[str]:
        """获取所有就绪任务（依赖已满足）"""
        ready_tasks = []
        for task_name, node in self.nodes.items():
            if self.task_status[task_name] != TaskStatus.PENDING:
                continue

            # 检查所有依赖是否已完成
            dependencies_met = all(
                self.task_status.get(dep) == TaskStatus.SUCCESS
                for dep in node.dependencies
            )

            if dependencies_met:
                ready_tasks.append(task_name)

        logger.info("ready_tasks_identified", ready_tasks=ready_tasks)
        return ready_tasks

    def can_skip_task(self, task_name: str) -> bool:
        """判断任务是否可以跳过"""
        node = self.nodes[task_name]
        if not node.optional:
            return False

        # 检查是否有替代专家
        if node.fallback_expert and self.task_status.get(node.fallback_expert) == TaskStatus.SUCCESS:
            logger.info("task_skipped_with_fallback", task=task_name, fallback=node.fallback_expert)
            return True

        # 简单启发式：如果所有后续任务都依赖此任务，则不能跳过
        downstream_tasks = self.get_downstream_tasks(task_name)
        for downstream in downstream_tasks:
            downstream_node = self.nodes[downstream]
            if not downstream_node.optional:
                return False

        logger.info("task_can_be_skipped", task=task_name)
        return True

    def get_downstream_tasks(self, task_name: str) -> List[str]:
        """获取依赖指定任务的所有下游任务"""
        downstream = []
        for name, node in self.nodes.items():
            if task_name in node.dependencies:
                downstream.append(name)
        return downstream

    async def execute_task(
        self,
        task_name: str,
        task_func: Callable,
        initial_context: Dict[str, Any]
    ) -> TaskResult:
        """执行单个任务（带重试逻辑）"""
        node = self.nodes[task_name]
        start_time = datetime.utcnow()

        # 更新状态
        self.task_status[task_name] = TaskStatus.RUNNING
        logger.info("task_started", task=task_name, retry_count=0)

        retry_count = 0
        last_error = None

        while retry_count <= node.max_retries:
            try:
                # 执行任务
                context = initial_context.copy()
                context["task_name"] = task_name
                context["attempt"] = retry_count + 1

                result = await asyncio.wait_for(
                    task_func(context),
                    timeout=node.timeout
                )

                # 任务成功
                execution_time = (datetime.utcnow() - start_time).total_seconds()
                task_result = TaskResult(
                    task_name=task_name,
                    status=TaskStatus.SUCCESS,
                    data=result,
                    execution_time=execution_time,
                    retry_count=retry_count
                )

                self.task_status[task_name] = TaskStatus.SUCCESS
                self.completed_tasks.add(task_name)
                self.execution_history.append(task_result)

                logger.info(
                    "task_completed",
                    task=task_name,
                    execution_time=execution_time,
                    retry_count=retry_count
                )

                # 触发回调
                if task_name in self.task_callbacks:
                    await self.task_callbacks[task_name](task_result)

                return task_result

            except Exception as e:
                last_error = str(e)
                retry_count += 1

                logger.warning(
                    "task_failed",
                    task=task_name,
                    attempt=retry_count,
                    error=last_error
                )

                # 检查是否应该重试
                if retry_count > node.max_retries:
                    break

                # 等待后重试
                if node.retry_strategy == RetryStrategy.EXPONENTIAL:
                    delay = node.retry_delay * (2 ** (retry_count - 1))
                elif node.retry_strategy == RetryStrategy.FIXED:
                    delay = node.retry_delay
                else:
                    delay = 0

                if delay > 0:
                    logger.info("task_retrying", task=task_name, delay=delay, attempt=retry_count)
                    await asyncio.sleep(delay)

        # 所有重试均失败
        execution_time = (datetime.utcnow() - start_time).total_seconds()
        task_result = TaskResult(
            task_name=task_name,
            status=TaskStatus.FAILED,
            error=last_error,
            execution_time=execution_time,
            retry_count=retry_count
        )

        self.task_status[task_name] = TaskStatus.FAILED
        self.failed_tasks.add(task_name)
        self.execution_history.append(task_result)

        logger.error(
            "task_failed_permanently",
            task=task_name,
            attempts=retry_count,
            error=last_error
        )

        return task_result

    async def execute_graph(
        self,
        task_functions: Dict[str, Callable],
        initial_context: Dict[str, Any]
    ) -> Dict[str, TaskResult]:
        """执行整个依赖图"""
        logger.info("graph_execution_started", total_tasks=len(self.nodes))

        results = {}
        max_iterations = len(self.nodes) * 2  # 防止无限循环
        iteration = 0

        while iteration < max_iterations:
            iteration += 1
            ready_tasks = self.get_ready_tasks()

            if not ready_tasks:
                logger.info("no_ready_tasks", iteration=iteration)
                break

            # 并行执行就绪任务
            tasks_to_run = []
            for task_name in ready_tasks:
                if task_name in task_functions:
                    tasks_to_run.append((task_name, task_functions[task_name]))

            if not tasks_to_run:
                break

            logger.info(
                "executing_ready_tasks_batch",
                tasks=[name for name, _ in tasks_to_run],
                iteration=iteration
            )

            # 并发执行
            batch_results = await asyncio.gather(
                *[self.execute_task(name, func, initial_context) for name, func in tasks_to_run],
                return_exceptions=True
            )

            # 处理结果
            for i, (task_name, _) in enumerate(tasks_to_run):
                result = batch_results[i]

                if isinstance(result, Exception):
                    logger.error("task_exception", task=task_name, error=str(result))
                    results[task_name] = TaskResult(
                        task_name=task_name,
                        status=TaskStatus.FAILED,
                        error=str(result)
                    )
                else:
                    results[task_name] = result

        # 检查是否所有任务完成
        if len(self.completed_tasks) == len(self.nodes):
            logger.info("graph_execution_completed", total_tasks=len(self.nodes))
        else:
            logger.warning(
                "graph_execution_incomplete",
                completed=len(self.completed_tasks),
                total=len(self.nodes),
                failed=list(self.failed_tasks)
            )

        return results

    def get_execution_summary(self) -> Dict[str, Any]:
        """获取执行摘要"""
        return {
            "total_tasks": len(self.nodes),
            "completed_tasks": len(self.completed_tasks),
            "failed_tasks": len(self.failed_tasks),
            "success_rate": len(self.completed_tasks) / len(self.nodes) if self.nodes else 0,
            "execution_history": [
                {
                    "task": r.task_name,
                    "status": r.status.value,
                    "execution_time": r.execution_time,
                    "retry_count": r.retry_count,
                    "timestamp": r.timestamp.isoformat()
                }
                for r in self.execution_history
            ]
        }


# 预定义的专家依赖图模板
def create_weather_component_dependency_graph() -> DependencyGraph:
    """创建气象-组分分析依赖图"""
    graph = DependencyGraph()

    # 气象分析节点
    graph.add_node(ExpertNode(
        name="weather_analysis",
        expert_type="weather",
        dependencies=[],
        retry_strategy=RetryStrategy.EXPONENTIAL,
        max_retries=2,
        optional=False
    ))

    # 组分分析节点
    graph.add_node(ExpertNode(
        name="component_analysis",
        expert_type="component",
        dependencies=["weather_analysis"],  # 可选：需要气象背景
        retry_strategy=RetryStrategy.EXPONENTIAL,
        max_retries=2,
        optional=True  # 组分分析是可选的
    ))

    # 可视化节点
    graph.add_node(ExpertNode(
        name="visualization",
        expert_type="viz",
        dependencies=["weather_analysis", "component_analysis"],
        retry_strategy=RetryStrategy.SKIP_ON_FAIL,
        max_retries=1,
        optional=True,
        fallback_expert="weather_analysis"  # 失败时只用气象数据
    ))

    # 报告节点
    graph.add_node(ExpertNode(
        name="report_generation",
        expert_type="report",
        dependencies=["weather_analysis", "component_analysis", "visualization"],
        retry_strategy=RetryStrategy.FIXED,
        max_retries=1,
        optional=False
    ))

    return graph


def create_parallel_analysis_dependency_graph() -> DependencyGraph:
    """创建并行分析依赖图（Weather和Component并行）"""
    graph = DependencyGraph()

    # 气象分析
    graph.add_node(ExpertNode(
        name="weather_analysis",
        expert_type="weather",
        dependencies=[],
        retry_strategy=RetryStrategy.EXPONENTIAL,
        max_retries=2,
        optional=False
    ))

    # 组分分析（不依赖气象，可并行）
    graph.add_node(ExpertNode(
        name="component_analysis",
        expert_type="component",
        dependencies=[],
        retry_strategy=RetryStrategy.EXPONENTIAL,
        max_retries=2,
        optional=True
    ))

    # 数据融合（需要前面的结果）
    graph.add_node(ExpertNode(
        name="data_fusion",
        expert_type="fusion",
        dependencies=["weather_analysis", "component_analysis"],
        retry_strategy=RetryStrategy.FIXED,
        max_retries=2,
        optional=True
    ))

    # 可视化（依赖融合结果）
    graph.add_node(ExpertNode(
        name="visualization",
        expert_type="viz",
        dependencies=["data_fusion"],
        retry_strategy=RetryStrategy.SKIP_ON_FAIL,
        max_retries=1,
        optional=True
    ))

    # 报告生成
    graph.add_node(ExpertNode(
        name="report_generation",
        expert_type="report",
        dependencies=["weather_analysis", "component_analysis", "visualization"],
        retry_strategy=RetryStrategy.FIXED,
        max_retries=1,
        optional=False
    ))

    return graph
