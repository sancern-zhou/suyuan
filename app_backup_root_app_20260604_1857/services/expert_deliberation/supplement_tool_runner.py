"""Execute deliberation supplement tools and convert outputs to facts."""

from __future__ import annotations

import json
from typing import Any

import structlog

from .fact_ledger import FactLedger
from .schemas import DeliberationRequest, ExpertAnalysis, FactQuality, FactRecord

logger = structlog.get_logger()


class SupplementToolRunner:
    """Run safe supplement tool calls produced by expert agents."""

    async def run(
        self,
        request: DeliberationRequest,
        ledger: FactLedger,
        analyses: list[ExpertAnalysis],
    ) -> list[FactRecord]:
        if not request.options.enable_tool_supplement:
            return []

        try:
            from app.agent.tool_adapter import get_react_agent_tool_registry

            registry = get_react_agent_tool_registry()
        except Exception as exc:
            logger.warning("expert_supplement_registry_unavailable", error=str(exc))
            return []
        new_facts: list[FactRecord] = []
        executed_keys: set[str] = set()
        for analysis in analyses:
            for plan in analysis.tool_call_plan:
                params = dict(plan.params)
                if request.data_ids and (plan.tool_name == "load_data_from_memory" or not params):
                    for data_id in request.data_ids:
                        params = {"data_id": data_id, "max_records": 100}
                        fact = await self._execute_one(registry, request, analysis.expert_id, "load_data_from_memory", plan.purpose, params, len(ledger.all()) + len(new_facts) + 1)
                        if fact and fact.fact_id not in executed_keys:
                            new_facts.append(fact)
                            executed_keys.add(fact.fact_id)
                    continue

                fact = await self._execute_one(registry, request, analysis.expert_id, plan.tool_name, plan.purpose, params, len(ledger.all()) + len(new_facts) + 1)
                if fact and fact.fact_id not in executed_keys:
                    new_facts.append(fact)
                    executed_keys.add(fact.fact_id)

        ledger.extend(new_facts)
        return new_facts

    async def _execute_one(
        self,
        registry: dict[str, Any],
        request: DeliberationRequest,
        expert_id: str,
        tool_name: str,
        purpose: str,
        params: dict[str, Any],
        index: int,
    ) -> FactRecord | None:
        tool = registry.get(tool_name)
        if not tool:
            return None
        try:
            result = await tool(context=None, **params)
        except Exception as exc:
            logger.warning("expert_supplement_tool_failed", tool_name=tool_name, expert_id=expert_id, error=str(exc))
            return None

        statement = self._summarize_result(tool_name, purpose, params, result)
        return FactRecord(
            fact_id=f"fact_supplement_{index:04d}",
            source_type="tool_supplement",
            source_ref={
                "expert_id": expert_id,
                "tool_name": tool_name,
                "params": params,
            },
            time_range=request.time_range,
            region=request.region,
            fact_type="supplement",
            statement=statement,
            method=f"补证工具执行：{tool_name}",
            quality=FactQuality(completeness="medium", temporal_coverage=request.time_range.display or "unknown", confidence=0.78),
            tags=["补证", "数据资产" if tool_name == "load_data_from_memory" else "工具结果"],
        )

    def _summarize_result(self, tool_name: str, purpose: str, params: dict[str, Any], result: Any) -> str:
        try:
            text = json.dumps(result, ensure_ascii=False, default=str)
        except TypeError:
            text = str(result)
        text = " ".join(text.split())
        if len(text) > 600:
            text = text[:600] + "..."
        return f"{purpose}；工具 {tool_name} 参数 {params} 返回：{text}"
