# 多专家Agent协同架构实现方案

## 架构概览

### 混合编排模式（Hybrid Orchestration）
```
                    用户查询
                        │
                ┌───────┴───────┐
                │               │
            Query Router    Context Manager
                │               │
        ┌───────┴───────┐       │
        │               │       │
    任务分解器      知识路由器    共享上下文
        │               │       │
        └───────┬───────┴───────┘
                │
        ┌───────┴───────┐
        │               │
    Master Coordinator  Expert Registry
        │               │
    ┌───┴───┐  ┌───┴───┐  ┌───┴───┐  ┌───┴───┐
    ▼       ▼  ▼       ▼  ▼       ▼  ▼       ▼
 气象专家  组分专家  可视化专家  报告专家
(Meteoro)  (Comp)    (Vis)      (Report)
    │       │       │       │
    └───────┴───────┴───────┘
                │
        Result Aggregator
                │
                ▼
        Final Report Generator
```

## 核心组件设计

### 1. 主协调器 (Master Coordinator)
```python
from typing import Dict, Any, List, Optional
from datetime import datetime
import asyncio
import structlog
from enum import Enum

class TaskType(Enum):
    """任务类型枚举"""
    METEOROLOGICAL_ANALYSIS = "meteorological_analysis"
    COMPONENT_ANALYSIS = "component_analysis"
    VISUALIZATION = "visualization"
    REPORT_GENERATION = "report_generation"
    JOINT_ANALYSIS = "joint_analysis"

class MasterCoordinator:
    """主协调器 - 负责整体任务编排和协调"""

    def __init__(self, shared_context: SharedContextManager):
        self.shared_context = shared_context
        self.experts = {
            "meteorology": MeteorologicalExpert(),
            "components": ComponentsExpert(),
            "visualization": VisualizationExpert(),
            "reporting": ReportingExpert()
        }
        self.task_scheduler = TaskDependencyScheduler()
        self.result_aggregator = ResultAggregator()
        self.knowledge_router = KnowledgeRouter()
        self.collaboration_manager = CollaborationManager()

    async def process_query(self, user_query: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """处理用户查询的主入口"""

        logger.info("processing_user_query", query=user_query[:100])

        # 步骤1: 查询分类和任务分解
        query_plan = await self._decompose_query(user_query, context)

        # 步骤2: 建立协作任务图
        task_graph = await self._build_task_graph(query_plan)

        # 步骤3: 并行执行专家任务
        expert_results = await self._orchestrate_experts(task_graph)

        # 步骤4: 结果聚合和冲突解决
        final_result = await self._aggregate_results(expert_results, query_plan)

        # 步骤5: 生成综合报告
        report = await self._generate_final_report(final_result, user_query)

        return {
            "status": "success",
            "query": user_query,
            "result": final_result,
            "report": report,
            "metadata": {
                "processing_time": datetime.utcnow().isoformat(),
                "experts_involved": list(expert_results.keys()),
                "confidence_score": final_result.get("confidence", 0.0)
            }
        }

    async def _decompose_query(self, query: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """智能查询分解"""

        # 意图识别
        intent = await self._classify_intent(query)

        # 任务提取
        tasks = await self._extract_tasks(query, intent)

        # 专家匹配
        required_experts = self._match_experts(tasks)

        # 优先级排序
        task_priorities = self._calculate_priorities(tasks, context)

        return {
            "original_query": query,
            "intent": intent,
            "tasks": tasks,
            "required_experts": required_experts,
            "task_priorities": task_priorities,
            "complexity_score": self._estimate_complexity(query)
        }

    async def _build_task_graph(self, query_plan: Dict[str, Any]) -> Dict[str, Any]:
        """构建任务依赖图"""

        task_graph = {
            "nodes": {},
            "edges": {},
            "parallel_groups": [],
            "sequential_groups": []
        }

        # 创建任务节点
        for task_id, task in enumerate(query_plan["tasks"]):
            task_graph["nodes"][task_id] = {
                "id": task_id,
                "type": task["type"],
                "expert": task["assigned_expert"],
                "priority": task["priority"],
                "dependencies": []
            }

        # 分析任务依赖关系
        dependencies = self._analyze_task_dependencies(query_plan["tasks"])
        task_graph["edges"] = dependencies

        # 识别并行和串行组
        task_graph["parallel_groups"] = self._identify_parallel_groups(task_graph)
        task_graph["sequential_groups"] = self._identify_sequential_groups(task_graph)

        return task_graph
```

### 2. 共享上下文管理器 (Shared Context Manager)
```python
class SharedContextManager:
    """共享上下文管理器 - 基于Context-Aware V2"""

    def __init__(self):
        self.data_registry = ExpertDataRegistry()
        self.knowledge_base = SharedKnowledgeBase()
        self.collaboration_space = CollaborationSpace()
        self.message_bus = ExpertMessageBus()
        self.state_manager = CollaborationStateManager()

    async def register_expert_data(
        self,
        expert_id: str,
        data: Dict[str, Any],
        metadata: Dict[str, Any]
    ) -> str:
        """注册专家数据到共享空间"""

        # 数据标准化
        standardized_data = await self._standardize_data(data, metadata)

        # 生成唯一ID
        data_id = f"{expert_id}:{uuid.uuid4().hex[:12]}"

        # 注册到数据注册表
        entry = {
            "data_id": data_id,
            "expert_id": expert_id,
            "data": standardized_data,
            "metadata": metadata,
            "timestamp": datetime.utcnow(),
            "visibility": metadata.get("visibility", "shared"),
            "schema_version": "v2.0"
        }

        await self.data_registry.register(entry)

        # 通知其他专家
        await self._notify_data_availability(expert_id, data_id, metadata)

        return data_id

    async def get_shared_data(
        self,
        requester_id: str,
        data_type: str,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """获取共享数据"""

        available_data = await self.data_registry.query(
            data_type=data_type,
            visibility=["shared", "public"],
            filters=filters
        )

        # 按相关性和质量排序
        ranked_data = await self._rank_by_relevance(
            available_data, requester_id, data_type
        )

        return ranked_data

    async def establish_collaboration(
        self,
        expert1_id: str,
        expert2_id: str,
        collaboration_type: str,
        shared_task: Dict[str, Any]
    ) -> str:
        """建立专家间协作"""

        collaboration_id = f"collab:{uuid.uuid4().hex[:12]}"

        collaboration_session = {
            "id": collaboration_id,
            "participants": [expert1_id, expert2_id],
            "type": collaboration_type,
            "task": shared_task,
            "status": "active",
            "start_time": datetime.utcnow(),
            "shared_data": [],
            "communication_log": []
        }

        await self.collaboration_space.create_session(collaboration_session)

        # 通知参与专家
        await self.message_bus.send_to_experts(
            [expert1_id, expert2_id],
            "COLLABORATION_ESTABLISHED",
            {"collaboration_id": collaboration_id, "task": shared_task}
        )

        return collaboration_id
```

### 3. 专家消息总线 (Expert Message Bus)
```python
class ExpertMessageBus:
    """专家消息总线 - 实现异步消息传递"""

    def __init__(self):
        self.message_queue = asyncio.Queue()
        self.subscribers = defaultdict(list)
        self.message_history = []

    async def send_message(
        self,
        from_expert: str,
        to_expert: str,
        message_type: str,
        payload: Dict[str, Any],
        priority: str = "normal"
    ) -> Dict[str, Any]:
        """发送消息"""

        message = {
            "id": str(uuid.uuid4()),
            "timestamp": datetime.utcnow().isoformat(),
            "from": from_expert,
            "to": to_expert,
            "type": message_type,
            "payload": payload,
            "priority": priority,
            "status": "pending"
        }

        # 添加到消息队列
        await self.message_queue.put(message)

        # 记录历史
        self.message_history.append(message)

        # 异步处理
        asyncio.create_task(self._process_message(message))

        return {"status": "sent", "message_id": message["id"]}

    async def broadcast_to_experts(
        self,
        from_expert: str,
        expert_list: List[str],
        message_type: str,
        payload: Dict[str, Any]
    ):
        """广播消息给多个专家"""

        for expert_id in expert_list:
            if expert_id != from_expert:
                await self.send_message(
                    from_expert,
                    expert_id,
                    message_type,
                    payload
                )

    async def _process_message(self, message: Dict[str, Any]):
        """异步处理消息"""

        try:
            # 路由消息
            await self._route_message(message)

            # 更新状态
            message["status"] = "delivered"
            message["delivered_at"] = datetime.utcnow().isoformat()

        except Exception as e:
            logger.error("message_processing_failed", error=str(e))
            message["status"] = "failed"
            message["error"] = str(e)
```

### 4. 任务依赖调度器 (Task Dependency Scheduler)
```python
class TaskDependencyScheduler:
    """任务依赖调度器"""

    def __init__(self):
        self.scheduler = asyncio.Scheduler()

    async def schedule_tasks(
        self,
        task_graph: Dict[str, Any],
        available_experts: Dict[str, Any]
    ) -> Dict[str, Any]:
        """调度任务执行"""

        # 计算任务执行顺序
        execution_plan = self._calculate_execution_order(task_graph)

        # 分配专家
        expert_assignments = self._assign_experts(execution_plan, available_experts)

        # 生成执行计划
        execution_schedule = {
            "phases": [],
            "expert_assignments": expert_assignments,
            "estimated_duration": self._estimate_duration(execution_plan),
            "critical_path": self._identify_critical_path(execution_plan)
        }

        # 创建执行阶段
        for phase_idx, phase_tasks in enumerate(execution_plan["phases"]):
            phase = {
                "phase_id": phase_idx,
                "tasks": phase_tasks,
                "parallel_execution": len(phase_tasks) > 1,
                "dependencies_resolved": await self._check_dependencies(
                    phase_tasks, execution_plan["completed_tasks"]
                )
            }
            execution_schedule["phases"].append(phase)

        return execution_schedule

    def _calculate_execution_order(self, task_graph: Dict[str, Any]) -> Dict[str, Any]:
        """计算任务执行顺序"""

        # 使用拓扑排序
        execution_plan = {
            "phases": [],
            "completed_tasks": set(),
            "remaining_tasks": set(task_graph["nodes"].keys())
        }

        while execution_plan["remaining_tasks"]:
            # 找到没有依赖的任务
            ready_tasks = []
            for task_id in execution_plan["remaining_tasks"]:
                task = task_graph["nodes"][task_id]
                if all(dep in execution_plan["completed_tasks"]
                       for dep in task["dependencies"]):
                    ready_tasks.append(task_id)

            if not ready_tasks:
                raise Exception("任务依赖循环引用")

            # 并行执行准备好的任务
            execution_plan["phases"].append(ready_tasks)
            execution_plan["completed_tasks"].update(ready_tasks)
            execution_plan["remaining_tasks"].difference_update(ready_tasks)

        return execution_plan
```

### 5. 结果聚合器 (Result Aggregator)
```python
class ResultAggregator:
    """结果聚合器"""

    async def aggregate_results(
        self,
        expert_results: Dict[str, Dict[str, Any]],
        aggregation_strategy: str = "weighted_consensus"
    ) -> Dict[str, Any]:
        """聚合多专家结果"""

        if aggregation_strategy == "weighted_consensus":
            return await self._weighted_consensus_aggregation(expert_results)
        elif aggregation_strategy == "hierarchical":
            return await self._hierarchical_aggregation(expert_results)
        elif aggregation_strategy == "confidence_based":
            return await self._confidence_based_aggregation(expert_results)
        else:
            raise ValueError(f"Unknown aggregation strategy: {aggregation_strategy}")

    async def _weighted_consensus_aggregation(
        self,
        results: Dict[str, Dict[str, Any]]
    ) -> Dict[str, Any]:
        """加权共识聚合"""

        # 计算专家权重
        expert_weights = {}
        for expert_id, result in results.items():
            confidence = result.get("confidence", 0.5)
            accuracy = result.get("accuracy", 0.5)
            # 权重 = 置信度 * 准确率 * 专家专业度
            expert_weights[expert_id] = confidence * accuracy * result.get("expertise_score", 1.0)

        # 归一化权重
        total_weight = sum(expert_weights.values())
        if total_weight > 0:
            expert_weights = {k: v/total_weight for k, v in expert_weights.items()}

        # 提取所有结果的维度
        all_dimensions = set()
        for result in results.values():
            if "data" in result and isinstance(result["data"], dict):
                all_dimensions.update(result["data"].keys())

        # 计算加权共识
        consensus_data = {}
        confidence_scores = {}

        for dimension in all_dimensions:
            dimension_values = []
            weights = []

            for expert_id, result in results.items():
                if "data" in result and dimension in result["data"]:
                    value = result["data"][dimension]
                    if isinstance(value, (int, float)):
                        dimension_values.append(value)
                        weights.append(expert_weights[expert_id])

            if dimension_values:
                # 加权平均
                weighted_sum = sum(v * w for v, w in zip(dimension_values, weights))
                consensus_value = weighted_sum / sum(weights)
                consensus_data[dimension] = consensus_value

                # 计算置信度
                variance = sum((v - consensus_value)**2 for v in dimension_values) / len(dimension_values)
                confidence_scores[dimension] = 1.0 / (1.0 + variance)

        # 生成共识解释
        consensus_explanation = await self._generate_consensus_explanation(
            consensus_data, expert_results
        )

        return {
            "aggregated_data": consensus_data,
            "confidence_scores": confidence_scores,
            "consensus_explanation": consensus_explanation,
            "expert_weights": expert_weights,
            "aggregation_method": "weighted_consensus",
            "quality_metrics": await self._calculate_quality_metrics(consensus_data, results)
        }
```

### 6. 协作管理器 (Collaboration Manager)
```python
class CollaborationManager:
    """协作管理器"""

    async def facilitate_collaboration(
        self,
        task_requirements: Dict[str, Any],
        available_experts: List[str]
    ) -> Dict[str, Any]:
        """促进专家协作"""

        # 识别需要协作的任务
        collaboration_opportunities = await self._identify_collaboration_opportunities(
            task_requirements, available_experts
        )

        # 建立协作会话
        collaboration_sessions = []
        for opportunity in collaboration_opportunities:
            session = await self._establish_collaboration_session(opportunity)
            collaboration_sessions.append(session)

        # 协调协作过程
        coordination_results = await self._coordinate_collaboration_sessions(
            collaboration_sessions
        )

        return {
            "collaboration_sessions": collaboration_sessions,
            "coordination_results": coordination_results,
            "collaboration_metrics": await self._calculate_collaboration_metrics(
                collaboration_sessions
            )
        }

    async def _identify_collaboration_opportunities(
        self,
        task_requirements: Dict[str, Any],
        available_experts: List[str]
    ) -> List[Dict[str, Any]]:
        """识别协作机会"""

        opportunities = []

        # 检查跨领域分析需求
        if "meteorology" in task_requirements and "components" in task_requirements:
            opportunities.append({
                "type": "joint_analysis",
                "participants": ["meteorology", "components"],
                "shared_objective": "分析气象条件对污染物浓度的影响",
                "required_interactions": [
                    "data_sharing",
                    "result_validation",
                    "joint_interpretation"
                ]
            })

        # 检查可视化需求
        if "visualization" in available_experts:
            for requirement in task_requirements:
                if requirement != "visualization":
                    opportunities.append({
                        "type": "visualization_collaboration",
                        "participants": [requirement, "visualization"],
                        "shared_objective": f"为{requirement}结果创建专业可视化",
                        "required_interactions": [
                            "requirement_clarification",
                            "data_transmission",
                            "design_collaboration"
                        ]
                    })

        # 检查报告需求
        if "reporting" in available_experts:
            if len(available_experts) > 1:
                opportunities.append({
                    "type": "report_collaboration",
                    "participants": available_experts,
                    "shared_objective": "生成综合分析报告",
                    "required_interactions": [
                        "result_integration",
                        "content_review",
                        "quality_assurance"
                    ]
                })

        return opportunities
```

## 部署架构

### 1. 微服务架构
```yaml
# docker-compose.yml
version: '3.8'

services:
  # 主协调器
  master-coordinator:
    image: air-quality/master-coordinator:latest
    ports:
      - "8000:8000"
    environment:
      - REDIS_URL=redis://redis:6379
      - EXPERT_REGISTRY_URL=http://expert-registry:8001
    depends_on:
      - redis
      - postgres
      - expert-registry

  # 气象专家
  meteorology-expert:
    image: air-quality/meteorology-expert:latest
    ports:
      - "8002:8002"
    environment:
      - EXPERT_ID=meteorology
      - SHARED_CONTEXT_URL=http://shared-context:8003
    depends_on:
      - shared-context

  # 环境组分专家
  components-expert:
    image: air-quality/components-expert:latest
    ports:
      - "8004:8004"
    environment:
      - EXPERT_ID=components
      - SHARED_CONTEXT_URL=http://shared-context:8003
    depends_on:
      - shared-context

  # 可视化专家
  visualization-expert:
    image: air-quality/visualization-expert:latest
    ports:
      - "8005:8005"
    environment:
      - EXPERT_ID=visualization
      - SHARED_CONTEXT_URL=http://shared-context:8003
    depends_on:
      - shared-context

  # 报告专家
  reporting-expert:
    image: air-quality/reporting-expert:latest
    ports:
      - "8006:8006"
    environment:
      - EXPERT_ID=reporting
      - SHARED_CONTEXT_URL=http://shared-context:8003
    depends_on:
      - shared-context

  # 共享上下文服务
  shared-context:
    image: air-quality/shared-context:latest
    ports:
      - "8003:8003"
    environment:
      - DATABASE_URL=postgresql://postgres:password@postgres:5432/airquality
      - REDIS_URL=redis://redis:6379
    depends_on:
      - postgres
      - redis

  # 专家注册表
  expert-registry:
    image: air-quality/expert-registry:latest
    ports:
      - "8001:8001"
    environment:
      - DATABASE_URL=postgresql://postgres:password@postgres:5432/airquality
    depends_on:
      - postgres

  # Redis缓存
  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"

  # PostgreSQL数据库
  postgres:
    image: postgres:15
    environment:
      - POSTGRES_DB=airquality
      - POSTGRES_USER=postgres
      - POSTGRES_PASSWORD=password
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data

volumes:
  postgres_data:
```

### 2. Kubernetes部署
```yaml
# k8s-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: master-coordinator
spec:
  replicas: 2
  selector:
    matchLabels:
      app: master-coordinator
  template:
    metadata:
      labels:
        app: master-coordinator
    spec:
      containers:
      - name: master-coordinator
        image: air-quality/master-coordinator:latest
        ports:
        - containerPort: 8000
        env:
        - name: REDIS_URL
          value: "redis://redis-service:6379"
        resources:
          requests:
            memory: "512Mi"
            cpu: "250m"
          limits:
            memory: "1Gi"
            cpu: "500m"

---
apiVersion: v1
kind: Service
metadata:
  name: master-coordinator-service
spec:
  selector:
    app: master-coordinator
  ports:
  - protocol: TCP
    port: 80
    targetPort: 8000
  type: LoadBalancer
```

## API接口设计

### 1. 主协调器API
```python
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI(title="Multi-Agent Air Quality Analysis System")

class QueryRequest(BaseModel):
    query: str
    location: Optional[Dict[str, float]] = None
    time_range: Optional[Dict[str, str]] = None
    analysis_type: Optional[str] = None
    context: Optional[Dict[str, Any]] = None

class QueryResponse(BaseModel):
    status: str
    query: str
    result: Dict[str, Any]
    report: Dict[str, Any]
    metadata: Dict[str, Any]

@app.post("/analyze", response_model=QueryResponse)
async def analyze_query(request: QueryRequest):
    """分析用户查询"""
    try:
        coordinator = MasterCoordinator(shared_context)
        result = await coordinator.process_query(request.query, request.context or {})
        return QueryResponse(**result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/experts/status")
async def get_expert_status():
    """获取专家状态"""
    return {
        "meteorology": "active",
        "components": "active",
        "visualization": "active",
        "reporting": "active"
    }

@app.get("/experts/{expert_id}/info")
async def get_expert_info(expert_id: str):
    """获取专家信息"""
    expert_info = {
        "meteorology": {
            "name": "气象分析专家",
            "capabilities": ["天气系统分析", "边界层分析", "轨迹分析"],
            "status": "active",
            "expertise_score": 0.95
        },
        "components": {
            "name": "环境组分分析专家",
            "capabilities": ["PMF分析", "VOCs分析", "源解析"],
            "status": "active",
            "expertise_score": 0.93
        },
        "visualization": {
            "name": "数据可视化专家",
            "capabilities": ["专业图表设计", "交互式分析", "多格式输出"],
            "status": "active",
            "expertise_score": 0.92
        },
        "reporting": {
            "name": "报告专家",
            "capabilities": ["专业报告撰写", "多格式报告生成", "数据解读"],
            "status": "active",
            "expertise_score": 0.94
        }
    }
    return expert_info.get(expert_id, {"error": "Expert not found"})
```

### 2. 专家间通信API
```python
@app.post("/experts/{expert_id}/collaborate")
async def initiate_collaboration(
    expert_id: str,
    collaboration_request: Dict[str, Any]
):
    """启动专家协作"""
    collaboration_manager = CollaborationManager()
    result = await collaboration_manager.facilitate_collaboration(
        collaboration_request,
        [expert_id]
    )
    return result

@app.post("/experts/{expert_id}/data/share")
async def share_data(
    expert_id: str,
    data_request: Dict[str, Any]
):
    """共享数据"""
    shared_context = SharedContextManager()
    data_id = await shared_context.register_expert_data(
        expert_id,
        data_request["data"],
        data_request["metadata"]
    )
    return {"data_id": data_id, "status": "shared"}

@app.get("/experts/{expert_id}/data/available")
async def get_available_data(expert_id: str, data_type: str):
    """获取可用数据"""
    shared_context = SharedContextManager()
    data = await shared_context.get_shared_data(expert_id, data_type)
    return {"data": data, "count": len(data)}
```

## 性能优化

### 1. 缓存策略
```python
class CacheManager:
    """缓存管理器"""

    def __init__(self):
        self.redis_client = redis.Redis(host='redis', port=6379, decode_responses=True)

    async def cache_query_result(self, query_hash: str, result: Dict[str, Any]):
        """缓存查询结果"""
        await self.redis_client.setex(
            f"query_result:{query_hash}",
            3600,  # 1小时过期
            json.dumps(result)
        )

    async def get_cached_result(self, query_hash: str) -> Optional[Dict[str, Any]]:
        """获取缓存结果"""
        cached = await self.redis_client.get(f"query_result:{query_hash}")
        return json.loads(cached) if cached else None

    async def cache_expert_data(self, expert_id: str, data_id: str, data: Dict[str, Any]):
        """缓存专家数据"""
        await self.redis_client.setex(
            f"expert_data:{expert_id}:{data_id}",
            7200,  # 2小时过期
            json.dumps(data)
        )
```

### 2. 并发优化
```python
class AsyncTaskPool:
    """异步任务池"""

    def __init__(self, max_workers: int = 10):
        self.semaphore = asyncio.Semaphore(max_workers)
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=max_workers)

    async def execute_expert_task(self, expert_id: str, task: Dict[str, Any]) -> Dict[str, Any]:
        """执行专家任务"""
        async with self.semaphore:
            # 使用线程池执行CPU密集型任务
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                self.executor,
                self._run_task_sync,
                expert_id,
                task
            )
            return result

    def _run_task_sync(self, expert_id: str, task: Dict[str, Any]) -> Dict[str, Any]:
        """同步执行任务"""
        expert = self.experts[expert_id]
        return expert.execute_task(task)
```

## 监控和日志

### 1. 性能监控
```python
class MetricsCollector:
    """指标收集器"""

    def __init__(self):
        self.metrics = {
            "query_count": 0,
            "expert_invocation_count": defaultdict(int),
            "collaboration_count": 0,
            "average_response_time": 0.0,
            "error_count": 0
        }

    async def record_query(self, query: str, response_time: float):
        """记录查询指标"""
        self.metrics["query_count"] += 1
        # 更新平均响应时间
        self.metrics["average_response_time"] = (
            (self.metrics["average_response_time"] * (self.metrics["query_count"] - 1) +
             response_time) / self.metrics["query_count"]
        )

    async def record_expert_invocation(self, expert_id: str, response_time: float):
        """记录专家调用指标"""
        self.metrics["expert_invocation_count"][expert_id] += 1

    async def get_metrics(self) -> Dict[str, Any]:
        """获取指标"""
        return dict(self.metrics)
```

### 2. 结构化日志
```python
import structlog

logger = structlog.get_logger()

async def log_collaboration(
    collaboration_id: str,
    experts: List[str],
    task_type: str,
    duration: float
):
    """记录协作日志"""
    logger.info(
        "expert_collaboration",
        collaboration_id=collaboration_id,
        experts=experts,
        task_type=task_type,
        duration=duration,
        timestamp=datetime.utcnow().isoformat()
    )

async def log_expert_performance(
    expert_id: str,
    task_type: str,
    response_time: float,
    accuracy: float
):
    """记录专家性能"""
    logger.info(
        "expert_performance",
        expert_id=expert_id,
        task_type=task_type,
        response_time=response_time,
        accuracy=accuracy,
        timestamp=datetime.utcnow().isoformat()
    )
```

## 总结

该多专家Agent协同架构具备以下优势：

1. **专业化程度高** - 每个专家都有深度的领域知识
2. **协作效率高** - 智能的任务分配和结果聚合
3. **可扩展性强** - 模块化设计，易于添加新专家
4. **鲁棒性好** - 多层次的错误处理和恢复机制
5. **性能优化** - 缓存、并发、负载均衡等优化策略

通过这个架构，系统可以提供专业、准确、高效的环境分析服务。
