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
            "请从以下文本中抽取知识图谱三元组，只返回 JSON，不要返回 Markdown。\n"
            "JSON schema:\n"
            "{\n"
            "  \"triplets\": [\n"
            "    {\n"
            "      \"subject\": {\"type\": \"实体类型\", \"name\": \"实体名称\"},\n"
            "      \"relation\": {\"type\": \"关系类型\"},\n"
            "      \"object\": {\"type\": \"实体类型\", \"name\": \"实体名称\"}\n"
            "    }\n"
            "  ]\n"
            "}\n"
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
        triplets = getattr(schema, "allowed_relation_triplets", []) or []
        if not triplets:
            return ""
        lines = ["允许的三元组方向只能使用以下组合："]
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
    raise ValueError(f"Unsupported cognitive map LLM provider: {provider}")
