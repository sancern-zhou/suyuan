from __future__ import annotations

from collections.abc import Generator
from typing import Any

from llama_index.core.llms import (
    ChatMessage,
    ChatResponse,
    CompletionResponse,
    CompletionResponseGen,
    LLMMetadata,
)
from llama_index.core.llms.custom import CustomLLM
from pydantic import Field


class ProjectLLMAdapter(CustomLLM):
    """LlamaIndex LLM adapter backed by the project's configured LLM service."""

    llm_service: Any = Field(exclude=True)
    model_name: str = "project-configured-model"
    temperature: float = 0.3
    max_tokens: int | None = None
    context_window: int = 8000
    cognitive_schema: Any | None = Field(default=None, exclude=True)
    last_structured_payload: dict[str, Any] | None = Field(default=None, exclude=True)

    @property
    def metadata(self) -> LLMMetadata:
        return LLMMetadata(
            context_window=self.context_window,
            num_output=self.max_tokens or 1024,
            is_chat_model=True,
            model_name=self.model_name,
        )

    def complete(self, prompt: str, formatted: bool = False, **kwargs: Any) -> CompletionResponse:
        raise RuntimeError(
            "ProjectLLMAdapter only supports async completion. Use acomplete() "
            "through LlamaIndex async extraction."
        )

    async def acomplete(
        self,
        prompt: str,
        formatted: bool = False,
        **kwargs: Any,
    ) -> CompletionResponse:
        text = await self.llm_service.chat(
            [{"role": "user", "content": prompt}],
            temperature=kwargs.get("temperature", self.temperature),
            max_tokens=kwargs.get("max_tokens", self.max_tokens),
        )
        return CompletionResponse(text=text)

    async def achat(
        self,
        messages: list[ChatMessage],
        **kwargs: Any,
    ) -> ChatResponse:
        project_messages = [
            {"role": str(message.role.value), "content": message.content or ""}
            for message in messages
        ]
        text = await self.llm_service.chat(
            project_messages,
            temperature=kwargs.get("temperature", self.temperature),
            max_tokens=kwargs.get("max_tokens", self.max_tokens),
        )
        return ChatResponse(message=ChatMessage(role="assistant", content=text))

    async def astructured_predict(
        self,
        output_cls: type[Any],
        prompt: Any,
        llm_kwargs: dict[str, Any] | None = None,
        **prompt_args: Any,
    ) -> Any:
        text = str(prompt_args.get("text") or "")
        max_triplets = int(prompt_args.get("max_triplets_per_chunk") or 10)
        extraction_prompt = self._build_structured_kg_prompt(
            text=text,
            max_triplets=max_triplets,
        )
        if hasattr(self.llm_service, "call_llm_with_json_response"):
            payload = await self.llm_service.call_llm_with_json_response(
                extraction_prompt,
                max_retries=2,
            )
        else:
            raw = await self.llm_service.chat(
                [{"role": "user", "content": extraction_prompt}],
                temperature=self.temperature,
                max_tokens=self.max_tokens,
            )
            import json

            payload = json.loads(raw)
        payload = self._normalize_structured_payload(payload)
        self.last_structured_payload = payload
        return output_cls.model_validate(payload)

    def set_cognitive_schema(self, schema: Any) -> None:
        self.cognitive_schema = schema

    def _build_structured_kg_prompt(self, text: str, max_triplets: int) -> str:
        return (
            "请从以下文本中抽取轻量知识图谱三元组，只返回 JSON，不要返回 Markdown。\n"
            "JSON schema:\n"
            "{\n"
            "  \"triplets\": [\n"
            "    {\n"
            "      \"subject\": {\n"
            "        \"type\": \"实体类型\",\n"
            "        \"name\": \"规范实体名\",\n"
            "        \"description\": \"一句话解释实体含义，可为空，最多80个中文字符\",\n"
            "        \"properties\": {}\n"
            "      },\n"
            "      \"relation\": {\n"
            "        \"type\": \"关系类型\",\n"
            "        \"description\": \"一句话解释这条关系，可为空，最多80个中文字符\",\n"
            "        \"properties\": {}\n"
            "      },\n"
            "      \"object\": {\n"
            "        \"type\": \"实体类型\",\n"
            "        \"name\": \"规范实体名\",\n"
            "        \"description\": \"一句话解释实体含义，可为空，最多80个中文字符\",\n"
            "        \"properties\": {}\n"
            "      }\n"
            "    }\n"
            "  ]\n"
            "}\n"
            "不要输出 evidence、quote、source、chunk、page、location、原文片段或来源文件信息。\n"
            "实体 description 只解释实体含义，不复述原文；常识型实体可留空。\n"
            "关系 description 只说明 subject 与 object 为什么存在该关系，不要放原文引用。\n"
            "实体名称必须是短规范名，不要把整句、长短语或文档标题当实体。\n"
            "实体规范化要求：同义词、缩写、英文名、中文名、大小写差异、别名和上下位泛称如果实际指向同一概念，只选择一个最常用规范名；例如 PM2.5、细颗粒物、细颗粒物浓度不要生成两个实体。\n"
            "如果原文同时出现规范名和别名，可用 has_alias 连接规范实体与别名实体；不要为了表达同一含义重复生成多个业务实体。\n"
            "连通性要求：优先把实体连接到已有核心实体，例如站点、污染物、指标、区域、时段、机制、措施、规则、数据源或分析方法。\n"
            "不要形成多个互不相连的小图；只有文本确实描述完全无关主题时，才允许产生独立子图。\n"
            "关系选择要服务查询和多跳遍历，优先抽取能把现象、原因、指标、对象、方法、规则串起来的关系，避免只生成孤立二元关系。\n"
            "只抽取对后续 Agent 推理、图谱编辑、污染分析或设备诊断有用的实体和关系；忽略泛泛背景信息。\n"
            f"最多抽取 {max_triplets} 个三元组。\n"
            "实体类型必须优先使用：Station, Pollutant, Metric, TimeWindow, Region, "
            "DataSource, AnalysisMethod, EmissionSource, ProcessMechanism, ControlMeasure, "
            "StandardRule, Finding, Hypothesis, Dataset, Tool, AgentRole。\n"
            "关系类型必须优先使用：located_in, measures, has_alias, belongs_to_category, "
            "affects, indicates, supports, contradicts, requires_data, derived_from, "
            "regulated_by, applies_to, produces, consumes, uses_method, has_limitation, "
            "handled_by_agent。\n"
            "如果没有可抽取内容，返回 {\"triplets\": []}。\n\n"
            f"{self._schema_prompt_hint()}\n\n"
            f"文本：\n{text}"
        )

    def _schema_prompt_hint(self) -> str:
        schema = self.cognitive_schema
        if schema is None:
            return ""
        lines = []
        build_requirement = str(getattr(schema, "build_requirement", "") or "").strip()
        if build_requirement:
            lines.extend([
                "本次认知地图构建需求：",
                build_requirement,
                "抽取实体和关系时优先保留与该需求相关、可服务后续 Agent 推理和数据分析的内容；与需求无关的背景信息不要抽取。",
            ])
        triplets = getattr(schema, "allowed_relation_triplets", []) or []
        if triplets:
            lines.append("允许的三元组方向只能使用以下组合：")
            lines.extend(f"- {source} --{relation}--> {target}" for source, relation, target in triplets)
        return "\n".join(lines)

    def _normalize_structured_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        if "triplets" in payload and isinstance(payload["triplets"], list):
            return payload
        for key in ("triples", "paths", "relationships", "relations"):
            value = payload.get(key)
            if isinstance(value, list):
                payload["triplets"] = value
                return payload
        payload["triplets"] = []
        return payload

    def stream_complete(
        self,
        prompt: str,
        formatted: bool = False,
        **kwargs: Any,
    ) -> CompletionResponseGen:
        def _gen() -> Generator[CompletionResponse, None, None]:
            raise RuntimeError("ProjectLLMAdapter does not support sync streaming")
            yield CompletionResponse(text="")

        return _gen()


def create_llamaindex_llm(provider: str | None = None):
    provider_name = (provider or "none").strip().lower()
    if provider_name in {"", "none"}:
        return None
    if provider_name == "project":
        from app.services.llm_service import llm_service

        return ProjectLLMAdapter(
            llm_service=llm_service,
            model_name=getattr(llm_service, "model", "project-configured-model"),
            temperature=getattr(llm_service, "temperature", 0.3),
        )
    raise ValueError(f"Unsupported knowledge graph LLM provider: {provider}")
