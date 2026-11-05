"""子 Agent 升级提问工具（escalate，对齐 ZCode dynamic-workflow 的 escalation）。

子 Agent 在执行中遇到无法自行裁决的阻塞性问题（问数口径、统计范围、时间
边界等）时调用本工具：**只挂起当前这一次执行**，问题经 Redis 推给用户，
其余工作流节点照常运行；用户作答后答案作为工具结果返回，子 Agent 原地
继续；用户超时未答则返回"自行以最佳判断推进"的普通工具结果（不是异常——
对齐 ZCode：抛错会让模型当可重试故障反复撞墙）。

- 预算：每节点每次尝试最多 `agent_escalation_max_per_node`（默认 3）次，
  超限直接返回自行判断指引；
- 跨进程投递：3 个 uvicorn worker 下 resolve 请求可能落在其他进程，等待方
  轮询 Redis（0.5s），无订阅者生命周期问题（cancellation monitor 同款先例）；
- 挂起节点占住一个 governor 并发槽位（已知限制，max_concurrency 通常 3-4）。
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from typing import Any, Callable, Dict, Optional

import structlog

from app.tools.base.tool_interface import ToolCategory

logger = structlog.get_logger()

POLL_INTERVAL_SECONDS = 0.5

# Redis 里 pending 状态的超时兜底 TTL：即使进程崩溃也不留悬挂问题
ESCALATION_KEY_TTL_SECONDS = 24 * 3600

TIMEOUT_GUIDANCE = (
    "用户未及时响应本次提问。请基于已有信息、上游数据契约与领域常识，"
    "以最合理的口径继续完成任务，并在最终结果中明确标注你所采用的假设。"
)

BUDGET_EXHAUSTED_GUIDANCE = (
    "本次任务的提问次数已达上限。请停止提问，基于已有信息以最合理的口径"
    "完成任务，并在最终结果中明确标注你所采用的假设。"
)


def escalation_redis_key(prefix: str, escalation_id: str) -> str:
    return f"{prefix}:workflow:escalation:{escalation_id}"


class EscalateTool:
    """每个子 Agent 节点动态构造一次：持有工作流上下文并管理提问预算。"""

    def __init__(
        self,
        *,
        session_id: Optional[str],
        workflow_id: str,
        task_id: str,
        redis_client: Any = None,
        redis_prefix: Optional[str] = None,
        on_escalation: Optional[Callable[[Dict[str, Any]], None]] = None,
        max_escalations: int = 3,
        timeout_seconds: float = 600.0,
        escalation_id: Optional[str] = None,
    ) -> None:
        self.name = "escalate"
        self.description = (
            "向用户提出阻塞性澄清问题。仅当问题无法从任务描述、上游"
            "数据或领域常识推断、且猜错会导致整份结论失效时才调用；每次调用会"
            "挂起当前任务等待用户回答（有超时）。"
        )
        self.category = ToolCategory.PLANNING
        self.requires_context = False
        self.version = "1.0.0"
        self.function_schema = {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {
                    "question": {
                        "type": "string",
                        "description": "要向用户澄清的问题，必须具体、可直接回答（不要开放式征询）",
                    },
                    "context": {
                        "type": "string",
                        "description": "问题的背景：当前任务、已有发现、各候选口径的后果差异（可选）",
                    },
                },
                "required": ["question"],
            },
        }
        self.session_id = session_id
        self.workflow_id = workflow_id
        self.task_id = task_id
        self._redis = redis_client
        self._redis_prefix = redis_prefix
        self.on_escalation = on_escalation
        self.max_escalations = max(1, int(max_escalations))
        self.timeout_seconds = max(1.0, float(timeout_seconds))
        self.escalation_id = escalation_id or uuid.uuid4().hex
        self._used = 0

    def __call__(self, *args: Any, **kwargs: Any):
        # executor 直接 await registry 里的值；裸实例必须可调用（同 SubmitResultTool）
        return self.execute(*args, **kwargs)

    def get_function_schema(self) -> Dict[str, Any]:
        return self.function_schema

    # ---- Redis 投递 ----

    def _get_redis(self):
        if self._redis is not None:
            return self._redis
        try:
            from app.agent.workflow.jobs import get_workflow_job_store

            return get_workflow_job_store().redis
        except Exception:  # noqa: BLE001
            return None

    def _get_prefix(self) -> str:
        if self._redis_prefix:
            return self._redis_prefix
        try:
            from config.settings import settings

            return settings.agent_steering_redis_prefix
        except Exception:  # noqa: BLE001
            return "suyuan:agent:steering"

    async def _write_escalation(self, record: Dict[str, Any]) -> None:
        redis = self._get_redis()
        if redis is None:
            return
        try:
            await redis.set(
                escalation_redis_key(self._get_prefix(), self.escalation_id),
                json.dumps(record, ensure_ascii=False, default=str),
                ex=ESCALATION_KEY_TTL_SECONDS,
            )
        except Exception as exc:  # noqa: BLE001 - 投递失败不炸执行
            logger.warning("escalation_write_failed", escalation_id=self.escalation_id, error=str(exc))

    async def _read_answer(self) -> Optional[Dict[str, Any]]:
        redis = self._get_redis()
        if redis is None:
            return None
        try:
            raw = await redis.get(escalation_redis_key(self._get_prefix(), self.escalation_id))
        except Exception as exc:  # noqa: BLE001
            logger.warning("escalation_read_failed", escalation_id=self.escalation_id, error=str(exc))
            return None
        if not raw:
            return None
        try:
            record = json.loads(raw)
        except (TypeError, ValueError):
            return None
        if isinstance(record, dict) and record.get("status") == "answered":
            return record
        return None

    # ---- 执行 ----

    async def execute(
        self, question: Optional[str] = None, context: Optional[str] = None, **kwargs: Any
    ) -> Dict[str, Any]:
        question = str(question or "").strip()
        if self._used >= self.max_escalations:
            return self._guidance_result(BUDGET_EXHAUSTED_GUIDANCE)
        if not question:
            return {
                "status": "failed",
                "success": False,
                "result": "escalate 需要 question 参数",
                "data": {},
                "summary": "提问缺少问题内容",
            }
        self._used += 1
        record = {
            "escalation_id": self.escalation_id,
            "session_id": self.session_id,
            "workflow_id": self.workflow_id,
            "task_id": self.task_id,
            "question": question[:2000],
            "context": str(context or "")[:2000],
            "status": "pending",
            "asked_at": time.time(),
        }
        await self._write_escalation(record)
        if self.on_escalation is not None:
            try:
                self.on_escalation({**record, "event": "raised"})
            except Exception:  # noqa: BLE001 - 观察者异常不影响执行
                pass
        logger.info(
            "escalation_raised",
            escalation_id=self.escalation_id,
            workflow_id=self.workflow_id,
            task_id=self.task_id,
            question=question[:100],
        )
        deadline = time.monotonic() + self.timeout_seconds
        while time.monotonic() < deadline:
            answer_record = await self._read_answer()
            if answer_record is not None:
                answer = str(answer_record.get("answer") or "").strip()
                if self.on_escalation is not None:
                    try:
                        self.on_escalation({
                            **record,
                            "event": "resolved",
                            "answer": answer[:2000],
                            "resolved_at": time.time(),
                        })
                    except Exception:  # noqa: BLE001
                        pass
                logger.info(
                    "escalation_resolved",
                    escalation_id=self.escalation_id,
                    workflow_id=self.workflow_id,
                    task_id=self.task_id,
                )
                return {
                    "status": "success",
                    "success": True,
                    "result": f"用户已回答：{answer}",
                    "data": {"escalation_answer": answer, "escalation_id": self.escalation_id},
                    "summary": "澄清问题已获用户回答，请基于答案继续",
                }
            await asyncio.sleep(POLL_INTERVAL_SECONDS)
        # 超时：普通结果推进，不抛异常
        if self.on_escalation is not None:
            try:
                self.on_escalation({**record, "event": "timeout"})
            except Exception:  # noqa: BLE001
                pass
        logger.info(
            "escalation_timeout",
            escalation_id=self.escalation_id,
            workflow_id=self.workflow_id,
            task_id=self.task_id,
        )
        return self._guidance_result(TIMEOUT_GUIDANCE)

    @staticmethod
    def _guidance_result(guidance: str) -> Dict[str, Any]:
        return {
            "status": "success",
            "success": True,
            "result": guidance,
            "data": {"escalation_guidance": guidance},
            "summary": "无法继续提问，按指引自行推进",
        }
