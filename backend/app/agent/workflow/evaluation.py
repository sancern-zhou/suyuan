"""Controlled, fixture-backed model comparison using the production DAG tool.

The bounded evaluation loop deliberately excludes production ReAct memory/SSE,
business backends and child session persistence. Its results are not a production
latency benchmark. Numeric gold values are never included in model prompts.
"""
from __future__ import annotations

import asyncio
from collections import Counter
from dataclasses import dataclass, field
import json
import math
from pathlib import Path
import time
from types import SimpleNamespace
from typing import Any

from app.agent.prompts.prompt_builder import build_react_system_prompt
from app.agent.prompts.tool_registry import get_tools_by_mode
from app.agent.workflow.delegation import delegation_error
from app.tools.agent_tools.run_agent_workflow import RunAgentWorkflowTool
from app.utils.path_config import format_agent_path, resolve_agent_path


@dataclass(frozen=True)
class EvaluationCase:
    name: str
    mode: str
    question: str
    datasets: dict[str, dict]
    expected: dict[str, float]
    required_sources: tuple[str, ...]
    no_causality: bool = False


def default_cases() -> list[EvaluationCase]:
    air = {city: {"source": f"fixture:air:{city}", "city": city, "unit": "µg/m³",
                  "rows": [{"date": f"2026-09-{day:02d}", "pm25": value}
                           for day, value in zip((1, 2, 3), values)]}
           for city, values in {"甲市": [12, 20, 28], "乙市": [32, 40, 48], "丙市": [22, 30, 38]}.items()}
    weather = {"source": "fixture:weather:甲市", "city": "甲市", "unit": "m/s",
               "rows": [{"date": f"2026-09-{day:02d}", "wind_speed": value}
                        for day, value in zip((1, 2, 3), (3, 2, 1))]}
    return [
        EvaluationCase("single_city", "query", "查询甲市2026年9月1日至3日PM2.5日均值并计算三日平均（键 mean_pm25），标注单位和数据来源。",
                       {"air_甲市": air["甲市"]}, {"mean_pm25": 20}, ("air_甲市",)),
        EvaluationCase("multi_city", "query", "对比甲市、乙市、丙市2026年9月1日至3日PM2.5三日均值（键 mean_甲市、mean_乙市、mean_丙市），计算最高与最低均值之差（键 spread）。",
                       {f"air_{city}": value for city, value in air.items()},
                       {"mean_甲市": 20, "mean_乙市": 40, "mean_丙市": 30, "spread": 20}, tuple(f"air_{city}" for city in air)),
        EvaluationCase("air_weather", "expert", "研判甲市2026年9月1日至3日PM2.5与风速的关系：计算PM2.5均值（mean_pm25）、风速均值（mean_wind）、Pearson相关系数（correlation），对齐日期并说明能否据此认定因果。",
                       {"air_甲市": air["甲市"], "weather_甲市": weather},
                       {"mean_pm25": 20, "mean_wind": 2, "correlation": -1}, ("air_甲市", "weather_甲市"), True),
    ]


FINAL_SCHEMA = {
    "type": "object", "required": ["facts", "evidence", "summary"],
    "properties": {
        "facts": {"type": "object", "additionalProperties": {"type": "number"}},
        "evidence": {"type": "array", "items": {"type": "string"}},
        "summary": {"type": "string"},
        "causal_claim": {"type": "string", "enum": ["not_established", "established", "not_applicable"]},
    },
}


def tool_schema(name: str, description: str, parameters: dict) -> dict:
    return {"name": name, "description": description, "input_schema": parameters}


@dataclass
class RunMetrics:
    calls: list[dict] = field(default_factory=list)
    tool_calls: list[dict] = field(default_factory=list)
    acquired: Counter = field(default_factory=Counter)
    accessed: set[str] = field(default_factory=set)
    node_count: int = 0
    active_children: int = 0
    peak_children: int = 0

    def usage(self) -> dict:
        known = bool(self.calls) and all(call["input_tokens"] is not None and call["output_tokens"] is not None for call in self.calls)
        return {"complete": known, "input_tokens": sum(call["input_tokens"] for call in self.calls) if known else None,
                "output_tokens": sum(call["output_tokens"] for call in self.calls) if known else None,
                "cache_read_tokens": sum(call["cache_read_tokens"] for call in self.calls),
                "cache_creation_tokens": sum(call["cache_creation_tokens"] for call in self.calls)}


def score_result(case: EvaluationCase, result: dict | None, paths: dict[str, str], accessed: set[str]) -> dict:
    facts = (result or {}).get("facts", {})
    if not isinstance(facts, dict):
        facts = {}
    matches = {key: isinstance(facts.get(key), (int, float)) and not isinstance(facts.get(key), bool)
               and math.isfinite(facts[key]) and math.isclose(facts[key], expected, rel_tol=1e-6, abs_tol=1e-6)
               for key, expected in case.expected.items()}
    evidence = (result or {}).get("evidence", [])
    if not isinstance(evidence, list):
        evidence = []
    valid = {path for path in evidence if isinstance(path, str) and path in accessed and path in paths.values()}
    coverage = sum(paths[name] in valid for name in case.required_sources) / len(case.required_sources)
    causality = not case.no_causality or (result or {}).get("causal_claim") == "not_established"
    return {"facts": matches, "numeric_accuracy": sum(matches.values()) / len(matches),
            "evidence_coverage": coverage, "invalid_evidence": len(evidence) - len(valid),
            "causality_boundary": causality,
            "passed": all(matches.values()) and coverage == 1 and len(valid) == len(evidence) and causality}


class EvaluationRunner:
    def __init__(self, case: EvaluationCase, variant: str, root: Path, model: Any = None, *, tool_delay: float = 0):
        if variant not in {"direct", "dag"}:
            raise ValueError("variant must be direct or dag")
        self.case, self.variant, self.model, self.tool_delay = case, variant, model, tool_delay
        self.root = resolve_agent_path(root)
        self.root.mkdir(parents=True, exist_ok=False)
        self.paths = {}
        for name, data in case.datasets.items():
            path = self.root / f"{name}.json"
            path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            self.paths[name] = format_agent_path(path)
        self.metrics = RunMetrics()
        self.workflow_calls = 0

    def schemas(self, mode: str, *, parent: bool) -> list[dict]:
        names = set(get_tools_by_mode(mode))
        schemas = [tool_schema("submit_evaluation", "提交本任务已计算的数值、来源文件路径、结论和因果边界；不可填猜测值。子任务允许只提交自己负责的部分。", FINAL_SCHEMA)]
        if not parent or self.variant == "direct":
            for name, description in (("query_xcai_city_history", "读取固定评测数据中的城市PM2.5日均值。"),
                                      ("get_weather_data", "读取固定评测数据中的城市逐日风速。"),
                                      ("get_observed_meteorology", "读取固定评测数据中的城市逐日风速。")):
                if name in names:
                    schemas.append(tool_schema(name, description, {"type": "object", "properties": {
                        "cities": {"type": "array", "items": {"type": "string"}}}, "required": ["cities"]}))
            if "read_file" in names:
                schemas.append(tool_schema("read_file", "读取已交付的评测数据文件，优先复用上游 file_path，避免重复取数。", {
                    "type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}))
        if parent and self.variant == "dag":
            if "run_agent_workflow" not in names:
                raise ValueError("DAG delegation is disabled by this project's parent whitelist")
            schema = RunAgentWorkflowTool().get_function_schema()
            schemas.append(tool_schema(schema["name"], schema["description"], schema["parameters"]))
        return schemas

    async def business_tool(self, name: str, args: dict) -> dict:
        await asyncio.sleep(self.tool_delay)
        if name == "read_file":
            requested = format_agent_path(resolve_agent_path(args["path"]))
            if requested not in self.paths.values():
                raise ValueError("only this case's fixture files may be read")
            self.metrics.accessed.add(requested)
            return {"file_path": requested, "data": json.loads(resolve_agent_path(requested).read_text(encoding="utf-8"))}
        prefix = {"query_xcai_city_history": "air", "get_weather_data": "weather", "get_observed_meteorology": "weather"}[name]
        cities = args.get("cities")
        if not isinstance(cities, list) or not cities or not all(isinstance(city, str) for city in cities):
            raise ValueError("cities must be a nonempty array")
        requested = [f"{prefix}_{city}" for city in cities]
        if any(key not in self.case.datasets for key in requested):
            raise ValueError("city/source not in this fixture case")
        records = []
        for key in requested:
            self.metrics.acquired[key] += 1
            self.metrics.accessed.add(self.paths[key])
            records.append({"file_path": self.paths[key], **self.case.datasets[key]})
        return {"success": True, "records": records}

    async def dispatch(self, name: str, args: dict, *, mode: str, parent: bool) -> dict:
        started = time.perf_counter()
        success = False
        try:
            if name not in {schema["name"] for schema in self.schemas(mode, parent=parent)}:
                raise ValueError("tool is outside this evaluation actor's capabilities")
            if name == "run_agent_workflow":
                self.workflow_calls += 1
                if self.workflow_calls > 2:
                    raise ValueError("evaluation allows at most two workflow submissions")
                workflow = args["workflow"]
                if not isinstance(workflow, dict) or not 1 <= len(workflow.get("nodes", [])) <= 6:
                    raise ValueError("evaluation DAG must contain 1-6 nodes")
                error = delegation_error(mode, [node.get("target_mode", "") for node in workflow["nodes"]])
                if error:
                    raise ValueError(error)
                # Stable prompts choose the graph; evaluation bounds retries and cost.
                for node in workflow["nodes"]:
                    node["max_attempts"] = 1
                runner = self
                class FixtureWorkflowTool(RunAgentWorkflowTool):
                    @staticmethod
                    def _build_sub_agent_tool():
                        return runner
                    @staticmethod
                    def _persist_parent_snapshot(context, snapshot):
                        pass
                value = await FixtureWorkflowTool().execute(context=SimpleNamespace(runtime_mode=mode),
                    workflow=workflow, max_concurrency=min(int(args.get("max_concurrency", 4)), 4))
                success = bool(value.get("success"))
                return value
            value = await self.business_tool(name, args)
            success = True
            return value
        finally:
            self.metrics.tool_calls.append({"actor_mode": mode, "parent": parent, "tool": name,
                "arguments": args, "success": success, "duration_seconds": time.perf_counter() - started})

    async def execute(self, **kwargs) -> dict:
        """DAG child adapter: real scheduling/handoff, isolated evaluation model loop."""
        mode = kwargs["target_mode"]
        self.metrics.node_count += 1
        self.metrics.active_children += 1
        self.metrics.peak_children = max(self.metrics.peak_children, self.metrics.active_children)
        try:
            result = await self.model_loop(mode, kwargs["goal"] + "\n" + kwargs.get("context_str", ""), parent=False)
            paths = [path for path in result.get("evidence", []) if path in self.paths.values()]
            structured = {"findings": [{"statement": f"{key}={value}"} for key, value in result.get("facts", {}).items()],
                          "evidence": [{"id": path, "kind": "file"} for path in paths],
                          "data_gaps": [], "uncertainties": []}
            return {"success": True, "status": "success", "data": {"file_paths": paths},
                    "result_envelope": {"status": "succeeded", "summary": result.get("summary", ""),
                    "outputs": structured, "evidence": structured["evidence"], "artifacts": [], "uncertainties": []}}
        finally:
            self.metrics.active_children -= 1

    async def model_loop(self, mode: str, question: str, *, parent: bool) -> dict:
        schemas = self.schemas(mode, parent=parent)
        available = [schema["name"] for schema in schemas]
        system = build_react_system_prompt(mode, available_tools=available) + (
            "\n受控评测：城市名称和日期以本题为准。业务工具只返回固定评测数据，不连接真实业务库。"
            "仅可使用实际提供的工具，不调用提示词中其他工具或技能；无需绘图或正式报告。"
            "使用 submit_evaluation 提交结果；facts 为题目所需数值，evidence 列出实际取得的来源文件路径。"
            "不要猜测未知数值。不要输出JSON文本代替工具提交。分析需要的数据优先读上游 file_path。"
        )
        if parent:
            system += "本题数值键：" + ", ".join(self.case.expected)
            if self.variant == "dag":
                system += "本次对比强制使用run_agent_workflow取数；独立数据并行，有输入依赖的分析节点填写dependencies。然后由父Agent核算并提交最终结果。"
        messages = [{"role": "user", "content": question}]
        for _ in range(8 if parent else 5):
            started = time.perf_counter()
            response = {}
            try:
                response = await self.model.chat_anthropic(messages=messages, tools=schemas, system=system,
                                                            max_tokens=2500, temperature=0)
            finally:
                usage = response.get("usage") or {}
                self.metrics.calls.append({"actor_mode": mode, "parent": parent,
                    "model": response.get("model"), "duration_seconds": time.perf_counter() - started,
                    "input_tokens": usage.get("input_tokens", usage.get("prompt_tokens")),
                    "output_tokens": usage.get("output_tokens", usage.get("completion_tokens")),
                    "cache_read_tokens": usage.get("cache_read_input_tokens", 0) or 0,
                    "cache_creation_tokens": usage.get("cache_creation_input_tokens", 0) or 0})
            content = response.get("content") or []
            messages.append({"role": "assistant", "content": content})
            results, final = [], None
            for block in content:
                if block.get("type") != "tool_use":
                    continue
                name, args = block["name"], block.get("input") or {}
                try:
                    if name == "submit_evaluation":
                        from app.agent.workflow.protocol import validate_result_schema
                        errors = validate_result_schema(args, FINAL_SCHEMA)
                        if errors:
                            raise ValueError(str(errors))
                        final = args
                        value = {"success": True}
                    else:
                        value = await self.dispatch(name, args, mode=mode, parent=parent)
                    results.append({"type": "tool_result", "tool_use_id": block["id"], "content": json.dumps(value, ensure_ascii=False)})
                except (KeyError, TypeError, ValueError) as exc:
                    results.append({"type": "tool_result", "tool_use_id": block["id"], "is_error": True,
                                    "content": str(exc)})
            if final is not None:
                return final
            if not results:
                messages.append({"role": "user", "content": "请使用工具获取证据并调用submit_evaluation，不要只回复文字。"})
            else:
                messages.append({"role": "user", "content": results})
        raise RuntimeError("evaluation iteration limit reached")

    async def replay(self) -> dict:
        """Deterministic plumbing smoke check; not a model/latency improvement claim."""
        if self.variant == "direct":
            available = {schema["name"] for schema in self.schemas(self.case.mode, parent=True)}
            weather_tool = "get_weather_data" if "get_weather_data" in available else "get_observed_meteorology"
            for prefix, tool in (("air", "query_xcai_city_history"), ("weather", weather_tool)):
                cities = [data["city"] for key, data in self.case.datasets.items() if key.startswith(prefix + "_")]
                if cities:
                    await self.dispatch(tool, {"cities": cities}, mode=self.case.mode, parent=True)
        else:
            nodes = [{"task_id": name, "target_mode": "query_forecast" if name.startswith("weather") else "query_monitoring_city",
                      "goal": name, "task_contract": {"deliverables": ["data"]}} for name in self.case.datasets]
            await self.dispatch("run_agent_workflow", {"workflow": {"nodes": nodes}}, mode=self.case.mode, parent=True)
        return {"facts": self.case.expected, "evidence": list(self.paths.values()), "summary": "deterministic replay",
                "causal_claim": "not_established" if self.case.no_causality else "not_applicable"}

    async def run(self, *, backend: str, timeout: float) -> dict:
        started = time.perf_counter()
        result, error = None, None
        try:
            result = await asyncio.wait_for(self.replay() if backend == "replay" else self.model_loop(
                self.case.mode, self.case.question, parent=True), timeout)
        except Exception as exc:
            error = type(exc).__name__  # Provider exception strings can contain credentials/URLs.
        return {"case": self.case.name, "mode": self.case.mode, "variant": self.variant, "backend": backend,
                "duration_seconds": time.perf_counter() - started, "error": error, "result": result,
                "quality": score_result(self.case, result, self.paths, self.metrics.accessed),
                "llm_calls": len(self.metrics.calls) if backend == "live" else 0,
                "scripted_calls": len(self.metrics.calls) if backend == "replay" else 0,
                "usage": self.metrics.usage(),
                "business_calls": sum(call["tool"] != "run_agent_workflow" for call in self.metrics.tool_calls),
                "duplicate_acquisitions": sum(max(0, count - 1) for count in self.metrics.acquired.values()),
                "node_count": self.metrics.node_count, "peak_children": self.metrics.peak_children,
                "model_calls": self.metrics.calls, "tool_calls": self.metrics.tool_calls}


class ReplayChildModel:
    """Only supports deterministic child plumbing; never counts synthetic tokens."""
    async def chat_anthropic(self, *, messages, **kwargs):
        question = messages[0]["content"]
        if len(messages) == 1:
            prefix, city = question.split("\n", 1)[0].split("_", 1)
            name = "get_weather_data" if prefix == "weather" else "query_xcai_city_history"
            return {"content": [{"type": "tool_use", "id": "fetch", "name": name, "input": {"cities": [city]}}]}
        data = json.loads(messages[-1]["content"][0]["content"])
        return {"content": [{"type": "tool_use", "id": "submit", "name": "submit_evaluation", "input": {
            "facts": {}, "evidence": [record["file_path"] for record in data["records"]], "summary": "fixture acquired"}}]}
