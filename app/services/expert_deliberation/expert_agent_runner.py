"""ReAct expert runners for deliberation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import structlog

from .schemas import ClaimRecord, DeliberationRequest, ExpertAnalysis, ExpertCard, FactQuality, FactRecord, ToolCallPlan

logger = structlog.get_logger()


class LLMExpertAgentRunner:
    """Run each expert through the existing ReAct loop and tool system."""

    def __init__(self, workspace_root: str | Path = ".") -> None:
        self.workspace_root = Path(workspace_root)

    async def analyze(
        self,
        expert: ExpertCard,
        request: DeliberationRequest,
        facts: list[FactRecord],
        relevant: list[FactRecord],
        round_index: int,
        start_fact_index: int,
    ) -> tuple[ExpertAnalysis, list[FactRecord]]:
        deliberation_mode = expert.deliberation_mode
        prompt = self._build_prompt(expert, request, facts, relevant, round_index)
        events: list[dict[str, Any]] = []
        final_answer = ""

        try:
            from app.agent.react_agent import ReActAgent
            from app.agent.tool_adapter import get_react_agent_tool_registry

            registry = self._filter_tool_registry(get_react_agent_tool_registry(), expert)
            agent = ReActAgent(max_iterations=8, tool_registry=registry, enable_memory=False)
        except Exception as exc:
            raise RuntimeError(f"ReAct expert runner unavailable for {expert.expert_id}: {exc}") from exc

        async for event in agent.analyze(
            user_query=prompt,
            session_id=f"expert_deliberation_{expert.expert_id}_{round_index}",
            enhance_with_history=False,
            reset_session=True,
            manual_mode=deliberation_mode,
        ):
            events.append(event)
            if event.get("type") == "complete":
                data = event.get("data") if isinstance(event.get("data"), dict) else {}
                final_answer = str(data.get("answer") or data.get("response") or "")
            elif event.get("type") in {"error", "fatal_error"}:
                data = event.get("data") if isinstance(event.get("data"), dict) else {}
                raise RuntimeError(f"ReAct expert {expert.expert_id} failed: {data.get('error') or event}")

        if not final_answer.strip():
            raise RuntimeError(f"ReAct expert {expert.expert_id} did not produce a final answer")

        payload = await self._parse_or_normalize_json(expert, final_answer, events)
        analysis = self._to_analysis(expert, payload, relevant)
        new_facts = self._tool_events_to_facts(request, expert, events, start_fact_index)
        analysis.new_fact_ids = [fact.fact_id for fact in new_facts]
        return analysis, new_facts

    def _filter_tool_registry(self, registry: dict[str, Any], expert: ExpertCard) -> dict[str, Any]:
        try:
            from app.agent.prompts.tool_registry import get_tools_by_mode

            mode_tools = set(get_tools_by_mode(expert.deliberation_mode).keys())
        except Exception:
            mode_tools = set()
        allowed = (set(expert.tool_whitelist) & mode_tools) | {"TodoWrite"}
        return {name: tool for name, tool in registry.items() if name in allowed}

    def _build_prompt(
        self,
        expert: ExpertCard,
        request: DeliberationRequest,
        facts: list[FactRecord],
        relevant: list[FactRecord],
        round_index: int,
    ) -> str:
        prompt_text = self._read_prompt_file(expert.prompt_file)
        fact_lines = [
            f"- {fact.fact_id} [{fact.source_type}/{','.join(fact.tags)}] {fact.statement}"
            for fact in relevant[: request.options.max_facts_per_expert]
        ]
        global_context = "\n".join(f"- {fact.fact_id}: {fact.statement}" for fact in facts[:60])
        user_discussion = request.discussion_prompt.strip() or "无"
        data_ids = ", ".join(request.data_ids) or "无"
        return f"""
你是“{expert.display_name}”，必须使用会商专用 ReAct 模式 `{expert.deliberation_mode}` 完成第 {round_index} 轮专家会商。

## 专家提示词
{prompt_text}

## 会商任务
主题：{request.topic}
区域：{request.region}
时段：{request.time_range.display or request.time_range.start or ""}
污染物：{"、".join(request.pollutants) or "未指定"}
已有 data_id：{data_ids}
用户追加讨论/追问：{user_discussion}

## 与你最相关的事实
{chr(10).join(fact_lines) or "暂无直接相关事实"}

## 全局事实账本
{global_context}

## 工具要求
- 你可以调用的工具：{", ".join(expert.tool_whitelist) or "无"}；读取已有数据资产时使用 read_data_registry、load_data_from_memory 或当前模式提供的数据读取工具。
- 如果事实不足以支持你的判断，必须先调用工具补证；工具 Observation 会被转成新 FactRecord。
- 不得编造事实编号，不得把未经工具读取的数据内容写成已知事实。

## 最终输出
完成必要工具调用后，最终回答只能输出严格 JSON，不要 Markdown，不要解释：
{{
  "position": "核心判断，必须引用事实编号或说明补证事实",
  "used_fact_ids": ["fact_xxx"],
  "claims": [
    {{
      "claim": "候选结论",
      "supporting_facts": ["fact_xxx"],
      "contradicting_facts": [],
      "missing_facts": ["仍需补充的证据"],
      "confidence": 0.0
    }}
  ],
  "tool_call_plan": [
    {{
      "tool_name": "后续仍需调用的工具名",
      "purpose": "补证目的",
      "expected_fact_type": "supplement",
      "params": {{}}
    }}
  ],
  "questions_to_others": [
    {{"target_expert": "专家ID", "question": "问题", "reason": "原因"}}
  ],
  "uncertainties": ["不确定性"]
}}
""".strip()

    def _read_prompt_file(self, prompt_file: str) -> str:
        candidates = [
            self.workspace_root / prompt_file,
            self.workspace_root / prompt_file.replace("backend/", "", 1),
            Path(prompt_file),
        ]
        for path in candidates:
            if path.exists():
                return path.read_text(encoding="utf-8", errors="ignore")[:6000]
        return ""

    async def _parse_or_normalize_json(
        self,
        expert: ExpertCard,
        final_answer: str,
        events: list[dict[str, Any]],
    ) -> dict[str, Any]:
        parsed = self._loads_json_object(final_answer)
        if parsed is not None:
            return parsed

        try:
            from app.services.llm_service import LLMService

            llm_service = LLMService()
            prompt = f"""
下面是 ReAct 专家“{expert.display_name}”的最终回答和工具事件摘要。请只做格式归一化，把其中观点转成指定 JSON，不要新增事实或结论。

最终回答：
{final_answer}

工具事件摘要：
{json.dumps(self._compact_events(events), ensure_ascii=False, default=str)[:8000]}

输出 JSON 字段：position, used_fact_ids, claims, tool_call_plan, questions_to_others, uncertainties。
""".strip()
            payload = await llm_service.call_llm_with_json_response(prompt, max_retries=1)
        except Exception as exc:
            raise RuntimeError(f"ReAct expert {expert.expert_id} returned non-JSON final answer: {exc}") from exc
        if not isinstance(payload, dict):
            raise RuntimeError(f"ReAct expert {expert.expert_id} JSON normalization returned invalid payload")
        return payload

    def _loads_json_object(self, text: str) -> dict[str, Any] | None:
        try:
            value = json.loads(text)
            return value if isinstance(value, dict) else None
        except json.JSONDecodeError:
            pass
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            try:
                value = json.loads(text[start : end + 1])
                return value if isinstance(value, dict) else None
            except json.JSONDecodeError:
                return None
        return None

    def _compact_events(self, events: list[dict[str, Any]]) -> list[dict[str, Any]]:
        compact = []
        for event in events:
            if event.get("type") in {"tool_use", "tool_result", "thought"}:
                compact.append(event)
        return compact[-20:]

    def _to_analysis(self, expert: ExpertCard, payload: dict[str, Any], relevant: list[FactRecord]) -> ExpertAnalysis:
        known_ids = {fact.fact_id for fact in relevant}
        raw_used = payload.get("used_fact_ids") if isinstance(payload.get("used_fact_ids"), list) else []
        used_ids = [str(fact_id) for fact_id in raw_used if str(fact_id) in known_ids or str(fact_id).startswith("fact_supplement_")]

        claims: list[ClaimRecord] = []
        raw_claims = payload.get("claims", []) if isinstance(payload.get("claims"), list) else []
        for index, item in enumerate(raw_claims, start=1):
            if not isinstance(item, dict):
                continue
            claim_text = str(item.get("claim") or "").strip()
            if not claim_text:
                continue
            confidence = item.get("confidence", 0.6)
            try:
                confidence = max(0.0, min(float(confidence), 1.0))
            except (TypeError, ValueError):
                confidence = 0.6
            claims.append(
                ClaimRecord(
                    claim_id=f"claim_{expert.expert_id}_{index:03d}",
                    expert_id=expert.expert_id,
                    claim=claim_text,
                    supporting_facts=[str(x) for x in item.get("supporting_facts", [])],
                    contradicting_facts=[str(x) for x in item.get("contradicting_facts", [])],
                    missing_facts=[str(x) for x in item.get("missing_facts", [])],
                    confidence=round(confidence, 2),
                )
            )

        plans: list[ToolCallPlan] = []
        allowed_tools = set(expert.tool_whitelist) | {"read_data_registry", "load_data_from_memory"}
        raw_plans = payload.get("tool_call_plan", []) if isinstance(payload.get("tool_call_plan"), list) else []
        for item in raw_plans:
            if not isinstance(item, dict):
                continue
            tool_name = str(item.get("tool_name") or "").strip()
            if tool_name and tool_name not in allowed_tools:
                continue
            plans.append(
                ToolCallPlan(
                    tool_name=tool_name or ("read_data_registry" if "read_data_registry" in allowed_tools else "load_data_from_memory"),
                    purpose=str(item.get("purpose") or "补充验证"),
                    expected_fact_type=str(item.get("expected_fact_type") or "supplement"),
                    params=item.get("params") if isinstance(item.get("params"), dict) else {},
                )
            )

        position = str(payload.get("position") or "").strip()
        if not position and claims:
            position = claims[0].claim
        if not position:
            raise RuntimeError(f"ReAct expert {expert.expert_id} returned no position")

        return ExpertAnalysis(
            expert_id=expert.expert_id,
            display_name=expert.display_name,
            used_fact_ids=used_ids,
            tool_call_plan=plans,
            position=position,
            key_findings=claims,
            questions_to_others=payload.get("questions_to_others", []) if isinstance(payload.get("questions_to_others"), list) else [],
            uncertainties=[str(x) for x in payload.get("uncertainties", [])] if isinstance(payload.get("uncertainties"), list) else [],
        )

    def _tool_events_to_facts(
        self,
        request: DeliberationRequest,
        expert: ExpertCard,
        events: list[dict[str, Any]],
        start_index: int,
    ) -> list[FactRecord]:
        facts: list[FactRecord] = []
        for event in events:
            if event.get("type") != "tool_result":
                continue
            data = event.get("data") if isinstance(event.get("data"), dict) else {}
            if data.get("is_error"):
                continue
            tool_name = str(data.get("tool_name") or data.get("tool_use_id") or "tool")
            result = data.get("result")
            statement = self._summarize_tool_result(tool_name, result)
            facts.append(
                FactRecord(
                    fact_id=f"fact_supplement_{start_index + len(facts):04d}",
                    source_type="tool_supplement",
                    source_ref={
                        "expert_id": expert.expert_id,
                        "tool_name": tool_name,
                        "tool_use_id": data.get("tool_use_id"),
                        "result": result,
                    },
                    time_range=request.time_range,
                    region=request.region,
                    fact_type="supplement",
                    statement=statement,
                    method=f"ReAct补证工具执行：{tool_name}",
                    quality=FactQuality(completeness="medium", temporal_coverage=request.time_range.display or "unknown", confidence=0.78),
                    tags=["补证", "工具结果", "数据资产" if tool_name in {"read_data_registry", "load_data_from_memory"} else "ReAct"],
                )
            )
        return facts

    def _summarize_tool_result(self, tool_name: str, result: Any) -> str:
        try:
            text = json.dumps(result, ensure_ascii=False, default=str)
        except TypeError:
            text = str(result)
        text = " ".join(text.split())
        if len(text) > 800:
            text = text[:800] + "..."
        return f"专家补证工具 {tool_name} 返回结果：{text}"
