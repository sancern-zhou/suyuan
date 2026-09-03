"""
任务级历史执行记忆

- 执行前注入：把任务专属长期记忆与最近案例渲染进任务 prompt（仅绑定当前任务，不跨任务共享）
- 执行后收尾：案例入库（确定性提取 + LLM 蒸馏）并维护长期记忆，完成前执行不结束

案例与记忆的职责边界：
- 案例 = 单次执行的回顾性总结（做了什么 / 结论如何 / 关键事实发现），不包含面向下次执行的建议
- 长期记忆 = 跨次积累的前瞻性知识（模式规律 / 经验教训 / 输出偏好 / 当前关注）
"""
import asyncio
import json
from datetime import datetime

import structlog

from .models.event import TaskEvent
from .models.execution import ExecutionStatus, TaskExecution
from .models.task import ScheduledTask
from .storage.task_case_storage import MemoryVersionConflictError, TaskCaseStorage

logger = structlog.get_logger()

# 确定性提取的截断/数量上限
CASE_SUMMARY_MAX_CHARS = 600
FALLBACK_BRIEF_MAX_CHARS = 120
ERROR_MAX_CHARS = 300
TRIGGER_DIGEST_MAX_CHARS = 200
MAX_OUTPUTS = 10
MAX_ERRORS = 5
MAX_FINDINGS = 5

# 巩固调用输入材料的截断上限
LLM_SUMMARY_MAX_CHARS = 3000
LLM_TASK_PROMPT_MAX_CHARS = 800
LLM_TOOL_SEQUENCE_LIMIT = 60

REPORT_TOOL_NAMES = {"create_report_package"}

_STATUS_MAP = {
    ExecutionStatus.SUCCESS: "succeeded",
    ExecutionStatus.TIMEOUT: "timeout",
    ExecutionStatus.FAILED: "failed",
    ExecutionStatus.CANCELLED: "failed",
    ExecutionStatus.RUNNING: "failed",
    ExecutionStatus.PENDING: "failed",
}
_CASE_STATUS_LABELS = {"succeeded": "成功", "failed": "失败", "timeout": "超时"}

_HISTORY_USAGE_NOTE = """历史记忆使用要求：
1. 持续性问题：若本次情况与「当前关注」或历史案例吻合，在输出中标注「本次为第 N 次发生」，并引用历史结论对比。
2. 结论连续性：本次结论与历史矛盾时，必须显式对比并说明变化原因。
3. 吸收「经验教训」，避免重复历史错误；历史产出引用（报告 ID 等）可用于检索上次的成品做对比。
4. 历史记忆仅供参考，不得代替本次执行的事实核查。"""

_CONSOLIDATION_PROMPT_TEMPLATE = """你是定时任务的执行记忆巩固器。任务「{task_name}」刚完成一次执行，请基于以下材料完成两件事：
一、蒸馏本次案例：只回顾本次执行（做了什么、结论如何、关键事实发现），禁止写入任何面向下次执行的建议、待办或期望——那属于长期记忆的职责。
二、改写任务长期记忆：跨次积累模式规律、经验教训、输出偏好与当前关注。

任务描述：{task_description}
任务提示词（截断）：{task_prompt}

【当前长期记忆】
{old_memory}

【本次执行材料】
- 执行状态：{status}
- 触发上下文：{trigger}
- Agent 最终回复（截断）：
{summary}
- 产出：{outputs}
- 错误：{errors}
- 工具调用序列：{tool_sequence}

输出要求：直接返回 JSON 字符串（不要用代码块包裹），结构如下：
{{
  "case": {{
    "case_brief": "不超过80字：本次做了什么、结论如何",
    "findings": ["不超过5条，每条不超过60字，仅陈述本次确认的事实发现；无则空数组"]
  }},
  "memory": "长期记忆 Markdown 全文（JSON 字符串，保留换行）"
}}

memory 必须沿用固定骨架：
# 任务记忆：{task_name}
## 使命与背景
## 已确认的模式与规律
## 经验教训
## 输出偏好
## 当前关注

memory 改写规则：
- 基于当前长期记忆增量改写：仍然有效的保留、本次新发现的合并、已过时的删除；首次执行则初始化「使命与背景」。
- 「当前关注」只保留仍值得下次跟进的事项（滚动更新，不超过5条）。
- 只依据给定材料，不编造；总长不超过 {memory_budget} 字符。"""


def _trigger_digest(event: TaskEvent | None) -> str | None:
    """事件触发上下文摘要（调度触发返回 None，时间由 started_at 表达）。"""
    if event is None:
        return None
    parts = [event.event_type]
    for key, value in event.attributes.items():
        if isinstance(value, (bool, int, float, str)):
            parts.append(f"{key}={value}")
    digest = "; ".join(parts)
    if len(digest) > TRIGGER_DIGEST_MAX_CHARS:
        digest = digest[:TRIGGER_DIGEST_MAX_CHARS] + "…"
    return digest


def _extract_outputs(agent_result: dict) -> list[dict]:
    """从执行器收集的实际结果中提取产出引用（report/dataset/visual）。"""
    outputs: list[dict] = []
    seen: set[tuple[str, str]] = set()

    def _add(kind: str, ref, title=None) -> None:
        if not ref or len(outputs) >= MAX_OUTPUTS:
            return
        key = (kind, str(ref))
        if key in seen:
            return
        seen.add(key)
        item = {"kind": kind, "ref": str(ref)}
        if title:
            item["title"] = str(title)[:80]
        outputs.append(item)

    for call in agent_result.get("tool_calls") or []:
        if call.get("tool") not in REPORT_TOOL_NAMES:
            continue
        result = call.get("result")
        data = result.get("data") if isinstance(result, dict) else None
        if isinstance(data, dict):
            _add("report", data.get("report_id"), data.get("title") or data.get("report_title"))
    for data_id in agent_result.get("data_ids") or []:
        _add("dataset", data_id)
    for visual in agent_result.get("visuals") or []:
        if not isinstance(visual, dict):
            continue
        _add(
            "visual",
            visual.get("visual_id") or visual.get("id") or visual.get("chart_id"),
            visual.get("title") or visual.get("name"),
        )
    return outputs


def _extract_errors(execution: TaskExecution, agent_result: dict) -> list[str]:
    errors: list[str] = []
    message = (execution.error_message or "").strip()
    if message:
        errors.append(message[:ERROR_MAX_CHARS])
    for call in agent_result.get("tool_calls") or []:
        if len(errors) >= MAX_ERRORS:
            break
        if call.get("success") is not False:
            continue
        tool = call.get("tool") or "unknown"
        detail = str(call.get("result") or "").strip()
        if detail:
            errors.append(f"工具 {tool} 失败: {detail[:150]}")
        else:
            errors.append(f"工具 {tool} 失败")
    return errors[:MAX_ERRORS]


def build_case(
    execution: TaskExecution,
    event: TaskEvent | None,
    agent_result: dict | None,
) -> dict:
    """确定性提取基础案例（蒸馏字段由收尾流程补充，失败时降级写 summary）。"""
    agent_result = agent_result or {}
    trigger: dict = {"type": "event" if event is not None else "schedule"}
    digest = _trigger_digest(event)
    if digest:
        trigger["context_digest"] = digest
    case: dict = {
        "execution_id": execution.execution_id,
        "status": _STATUS_MAP.get(execution.status, "failed"),
        "trigger": trigger,
        "started_at": execution.started_at.isoformat() if execution.started_at else None,
        "duration_seconds": execution.duration_seconds,
    }
    outputs = _extract_outputs(agent_result)
    if outputs:
        case["outputs"] = outputs
    errors = _extract_errors(execution, agent_result)
    if errors:
        case["errors"] = errors
    return case


def _render_case_line(case: dict, index: int) -> str:
    started = str(case.get("started_at") or "")[:16].replace("T", " ")
    status = _CASE_STATUS_LABELS.get(case.get("status"), str(case.get("status")))
    distilled = case.get("distilled") or {}
    brief = (
        distilled.get("case_brief")
        or str(case.get("summary") or "")[:FALLBACK_BRIEF_MAX_CHARS]
        or "无摘要"
    ).strip()
    line = f"- [{index}] {started} {status}｜{brief}"
    outputs = case.get("outputs") or []
    if outputs:
        refs = ", ".join(f"{item.get('kind')}:{item.get('ref')}" for item in outputs[:5])
        line += f"\n  产出: {refs}"
    errors = case.get("errors") or []
    if errors:
        line += f"\n  错误: {'；'.join(errors[:2])}"
    return line


def build_history_section(task: ScheduledTask, storage: TaskCaseStorage) -> str | None:
    """执行前注入：渲染「## 历史执行记忆」段；任务关闭或无任何历史时返回 None。"""
    config = task.history_learning
    if not config.enabled:
        return None
    memory = storage.read_memory()
    recent = storage.recent_cases(config.max_recent_cases)
    if not memory and not recent:
        return None
    total = storage.case_count()
    parts = [f"## 历史执行记忆（本任务专属，案例库累计 {total} 次执行）"]
    if memory:
        if len(memory) > config.memory_char_budget:
            memory = memory[: config.memory_char_budget].rstrip() + "\n…<记忆超出预算已截断>"
        parts.append(memory)
    if recent:
        lines = ["### 最近执行案例（旧→新，最后一条为最近一次）"]
        for index, case in enumerate(recent, start=1):
            lines.append(_render_case_line(case, index))
        parts.append("\n".join(lines))
    parts.append(_HISTORY_USAGE_NOTE)
    return "\n\n".join(parts)


def _parse_consolidation_response(content: str | dict) -> tuple[dict, str] | None:
    """解析巩固调用输出：{"case": {...}, "memory": "<markdown>"}。"""
    if isinstance(content, dict):
        data = content
    else:
        text = (content or "").strip()
        if "```" in text:
            for part in text.split("```"):
                candidate = part.strip()
                if candidate.startswith("json"):
                    candidate = candidate[4:].strip()
                if candidate.startswith("{"):
                    text = candidate
                    break
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return None
    if not isinstance(data, dict):
        return None
    case_part = data.get("case")
    memory = data.get("memory")
    if not isinstance(case_part, dict) or not isinstance(memory, str):
        return None
    brief = str(case_part.get("case_brief") or "").strip()
    if not brief:
        return None
    findings_raw = case_part.get("findings")
    findings = []
    if isinstance(findings_raw, list):
        findings = [str(item).strip()[:80] for item in findings_raw if str(item).strip()][:MAX_FINDINGS]
    memory = memory.strip()
    if len(memory) < 10:
        return None
    return {"case_brief": brief[:160], "findings": findings}, memory


async def _consolidation_call(
    task: ScheduledTask,
    old_memory: str,
    case: dict,
    agent_result: dict,
    memory_budget: int,
) -> tuple[dict, str]:
    """一次 LLM 巩固调用：同时产出蒸馏案例与新版长期记忆；失败重试一次。"""
    from app.services.llm_service import LLMService

    agent_result = agent_result or {}
    tool_names = [str(call.get("tool") or "") for call in agent_result.get("tool_calls") or []]
    tool_sequence = " → ".join([name for name in tool_names if name][:LLM_TOOL_SEQUENCE_LIMIT]) or "（无）"
    prompt = _CONSOLIDATION_PROMPT_TEMPLATE.format(
        task_name=task.name,
        task_description=task.description,
        task_prompt=task.prompt[:LLM_TASK_PROMPT_MAX_CHARS],
        old_memory=old_memory.strip() or "（暂无，首次执行）",
        status=case.get("status"),
        trigger=json.dumps(case.get("trigger") or {}, ensure_ascii=False),
        summary=str(agent_result.get("summary") or "（无最终回复）")[:LLM_SUMMARY_MAX_CHARS],
        outputs=json.dumps(case.get("outputs") or [], ensure_ascii=False),
        errors=json.dumps(case.get("errors") or [], ensure_ascii=False),
        tool_sequence=tool_sequence,
        memory_budget=memory_budget,
    )
    llm_service = LLMService()
    llm_service.temperature = 0.2
    last_error: Exception = RuntimeError("consolidation failed")
    for _attempt in range(2):
        try:
            response = await llm_service.call_llm_with_json_response(prompt, max_retries=1)
            parsed = _parse_consolidation_response(response)
            if parsed is not None:
                return parsed
            last_error = ValueError("consolidation response schema invalid")
        except Exception as error:  # noqa: BLE001 - 巩固失败必须降级而不是中断收尾
            last_error = error
        logger.warning(
            "scheduled_task_consolidation_attempt_failed",
            task_id=task.task_id,
            error=str(last_error),
        )
    raise last_error


async def finalize_execution(
    task: ScheduledTask,
    execution: TaskExecution,
    event: TaskEvent | None,
    agent_result: dict | None,
    storage: TaskCaseStorage,
) -> dict:
    """执行后收尾：案例入库 + 长期记忆维护。

    - 案例事实必然入库；巩固调用失败/超时降级为写 summary 兜底、保留旧记忆
    - 先写案例、成功后才覆盖记忆，保证记忆与案例库一致
    """
    config = task.history_learning
    case = build_case(execution=execution, event=event, agent_result=agent_result)
    base_meta = storage.read_meta()
    base_version = int(base_meta.get("version", 0))
    old_memory = storage.read_memory()
    consolidate_error: str | None = None
    outcome: tuple[dict, str] | None = None
    try:
        outcome = await asyncio.wait_for(
            _consolidation_call(
                task=task,
                old_memory=old_memory,
                case=case,
                agent_result=agent_result,
                memory_budget=config.memory_char_budget,
            ),
            timeout=config.consolidation_timeout_seconds,
        )
    except TimeoutError:
        consolidate_error = f"consolidation timeout after {config.consolidation_timeout_seconds}s"
    except Exception as error:  # noqa: BLE001 - 收尾只降级不抛出
        consolidate_error = str(error)

    meta = storage.read_meta()
    if outcome is not None:
        distilled, memory_md = outcome
        case["distilled"] = distilled
        storage.append_case(case)
        try:
            storage.write_memory(
                memory_md,
                {
                    "version": base_version + 1,
                    "last_execution_id": execution.execution_id,
                    "last_consolidation_status": "success",
                    "consolidation_failures": 0,
                    "updated_at": datetime.now().isoformat(),
                },
                expected_version=base_version,
            )
        except MemoryVersionConflictError:
            logger.info(
                "scheduled_task_consolidation_stale_memory",
                task_id=task.task_id,
                execution_id=execution.execution_id,
                expected_version=base_version,
                current_version=int(storage.read_meta().get("version", 0)),
            )
    else:
        fallback = str((agent_result or {}).get("summary") or "").strip()
        if fallback:
            case["summary"] = fallback[:CASE_SUMMARY_MAX_CHARS]
        storage.append_case(case)
        storage.write_meta(
            {
                **meta,
                "last_execution_id": execution.execution_id,
                "last_consolidation_status": "failed",
                "last_consolidation_error": (consolidate_error or "unparseable response")[:200],
                "consolidation_failures": int(meta.get("consolidation_failures", 0)) + 1,
                "updated_at": datetime.now().isoformat(),
            }
        )

    logger.info(
        "scheduled_task_history_finalized",
        task_id=task.task_id,
        execution_id=execution.execution_id,
        distilled=outcome is not None,
    )
    return case
