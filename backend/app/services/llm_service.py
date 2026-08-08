"""
LLM Service

提供LLM调用服务，支持JSON格式响应解析。
支持多种LLM provider: deepseek, minimax, openai, agnes, glm, bailian
"""
import asyncio
import json
import html
import os
import time
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Dict, Any, Optional, Tuple, AsyncGenerator, List
import structlog
from config.settings import settings
import httpx
from app.utils.llm_context_logger import get_llm_context_logger
from app.services.llm_failover import (
    LLMFailoverError,
    classify_llm_failure,
    get_cooldown_failure,
    get_llm_pool_semaphore,
    mark_provider_cooldown,
    parse_fallback_candidates,
    should_fallback,
    summarize_attempts,
)
from app.services.chat_completions_adapter import (
    ChatCompletionsStreamAdapter,
    ToolCallArgumentsError,
    convert_anthropic_messages_to_chat,
    convert_anthropic_tools_to_chat,
    convert_chat_response_to_anthropic,
)

logger = structlog.get_logger()

_llm_request_state: ContextVar[Optional[Dict[str, Any]]] = ContextVar(
    "llm_request_state",
    default=None,
)


class LLMService:
    """LLM服务类 - 支持多provider配置"""

    @property
    def provider(self) -> str:
        state = _llm_request_state.get()
        if state is not None and "provider" in state:
            return state["provider"]
        return getattr(self, "_provider", "")

    @provider.setter
    def provider(self, value: str) -> None:
        state = _llm_request_state.get()
        if state is not None:
            state["provider"] = value
        else:
            self._provider = value

    @property
    def base_url(self) -> str:
        state = _llm_request_state.get()
        if state is not None and "base_url" in state:
            return state["base_url"]
        return getattr(self, "_base_url", "")

    @base_url.setter
    def base_url(self, value: str) -> None:
        state = _llm_request_state.get()
        if state is not None:
            state["base_url"] = value
        else:
            self._base_url = value

    @property
    def api_key(self) -> str:
        state = _llm_request_state.get()
        if state is not None and "api_key" in state:
            return state["api_key"]
        return getattr(self, "_api_key", "")

    @api_key.setter
    def api_key(self, value: str) -> None:
        state = _llm_request_state.get()
        if state is not None:
            state["api_key"] = value
        else:
            self._api_key = value

    @property
    def model(self) -> str:
        state = _llm_request_state.get()
        if state is not None and "model" in state:
            return state["model"]
        return getattr(self, "_model", "")

    @model.setter
    def model(self, value: str) -> None:
        state = _llm_request_state.get()
        if state is not None:
            state["model"] = value
        else:
            self._model = value

    @property
    def api_mode(self) -> str:
        state = _llm_request_state.get()
        if state is not None and "api_mode" in state:
            return state["api_mode"]
        return getattr(self, "_api_mode", "anthropic_messages")

    @api_mode.setter
    def api_mode(self, value: str) -> None:
        normalized = (value or "anthropic_messages").strip().lower()
        if normalized not in {"anthropic_messages", "chat_completions"}:
            raise ValueError(f"Unsupported LLM api_mode: {value}")
        state = _llm_request_state.get()
        if state is not None:
            state["api_mode"] = normalized
        else:
            self._api_mode = normalized

    @property
    def anthropic_client(self):
        state = _llm_request_state.get()
        if state is not None and "anthropic_client" in state:
            return state["anthropic_client"]
        return getattr(self, "_anthropic_client", None)

    @anthropic_client.setter
    def anthropic_client(self, value) -> None:
        state = _llm_request_state.get()
        if state is not None:
            state["anthropic_client"] = value
        else:
            self._anthropic_client = value

    @property
    def request_fallbacks(self) -> Optional[str]:
        state = _llm_request_state.get()
        if state is not None:
            return state.get("fallbacks")
        return getattr(self, "_request_fallbacks", None)

    @request_fallbacks.setter
    def request_fallbacks(self, value: Optional[str]) -> None:
        state = _llm_request_state.get()
        if state is not None:
            state["fallbacks"] = value
        else:
            self._request_fallbacks = value

    @contextmanager
    def use_provider_model(self, provider: str, model: Optional[str] = None):
        """Temporarily select a concrete provider/model for the current async request."""
        selected_provider = (provider or "").strip().lower()
        if not selected_provider:
            yield
            return

        token = _llm_request_state.set({})
        try:
            self.provider = selected_provider
            self._load_provider_config()
            if model:
                self.model = model
            self.request_fallbacks = None
            logger.info(
                "llm_request_provider_model_selected",
                provider=self.provider,
                model=self.model,
                base_url=self.base_url,
            )
            yield
        finally:
            temporary_client = self.anthropic_client
            _llm_request_state.reset(token)
            if temporary_client is not None:
                self._schedule_anthropic_client_close(temporary_client)

    @contextmanager
    def use_provider_chain(
        self,
        provider: str,
        model: Optional[str] = None,
        fallbacks: Optional[str] = None,
    ):
        """Temporarily inherit an explicit provider/model fallback chain."""
        selected_provider = (provider or "").strip().lower()
        if not selected_provider:
            yield
            return

        token = _llm_request_state.set({})
        try:
            state = _llm_request_state.get()
            if state is not None:
                state["selection_source"] = "inherited_chain"
            self.provider = selected_provider
            self._load_provider_config()
            if model:
                self.model = model
            self.request_fallbacks = fallbacks
            logger.info(
                "llm_request_provider_chain_inherited",
                provider=self.provider,
                model=self.model,
                fallbacks=self.request_fallbacks,
            )
            yield
        finally:
            temporary_client = self.anthropic_client
            _llm_request_state.reset(token)
            if temporary_client is not None:
                self._schedule_anthropic_client_close(temporary_client)

    def resolve_model_chain(
        self,
        auto_profile: Optional[str] = None,
    ) -> Tuple[str, str, Optional[str]]:
        """Resolve the configured priority chain without opening a request context."""
        active_state = _llm_request_state.get()
        if (
            active_state is not None
            and active_state.get("selection_source") != "tier"
            and (active_state.get("provider") or active_state.get("model"))
        ):
            return self.provider, self.model, self.request_fallbacks

        profile = (auto_profile or "").strip().lower()
        profile_config = {
            "multimodal": getattr(settings, "llm_multimodal_models", "") or "",
        }.get(profile)
        if profile_config and profile_config.strip():
            candidates = [
                candidate
                for candidate in parse_fallback_candidates("", "", profile_config)
                if candidate.provider
            ]
            if candidates:
                primary = candidates[0]
                fallback_items = [
                    f"{candidate.provider}/{candidate.model}"
                    if candidate.model
                    else candidate.provider
                    for candidate in candidates[1:]
                ]
                return (
                    primary.provider,
                    primary.model or "",
                    ",".join(fallback_items),
                )
        return self.provider, self.model, self.request_fallbacks

    @contextmanager
    def use_model_tier(self, model_tier: Optional[str]):
        """Temporarily select the primary model for the current async request."""
        tier = (model_tier or "").strip().lower()
        if not tier or tier == "auto":
            yield
            return

        tier_config = {
            "flash": getattr(settings, "llm_flash_models", "") or "",
            "pro": getattr(settings, "llm_pro_models", "") or "",
        }.get(tier)
        if tier_config is None:
            raise ValueError(f"Unsupported model tier: {model_tier}")

        from app.services.llm_failover import parse_fallback_candidates

        token = _llm_request_state.set({})
        try:
            state = _llm_request_state.get()
            if state is not None:
                state["selection_source"] = "tier"
                state["model_tier"] = tier
            if tier_config.strip():
                candidates = parse_fallback_candidates("", "", tier_config)
                candidates = [
                    candidate
                    for candidate in candidates
                    if candidate.provider and candidate.provider.lower() != "glm"
                ]
                if not candidates:
                    raise ValueError(
                        f"No non-GLM candidates configured for model tier: {tier}. "
                        "Flash/Pro tiers must use providers such as mimo or deepseek."
                    )
                primary = candidates[0]
                self.provider = primary.provider
                self._load_provider_config()
                if primary.model:
                    self.model = primary.model
                fallback_items = [
                    f"{candidate.provider}/{candidate.model}" if candidate.model else candidate.provider
                    for candidate in candidates[1:]
                ]
                self.request_fallbacks = ",".join(fallback_items)
            else:
                self.provider = settings.llm_provider.lower()
                self._load_provider_config()
                self.request_fallbacks = None
            logger.info(
                "llm_request_model_tier_selected",
                tier=tier,
                provider=self.provider,
                model=self.model,
                base_url=self.base_url,
                fallbacks=self.request_fallbacks,
            )
            yield
        finally:
            temporary_client = self.anthropic_client
            _llm_request_state.reset(token)
            if temporary_client is not None:
                self._schedule_anthropic_client_close(temporary_client)

    @contextmanager
    def use_auto_profile(self, auto_profile: Optional[str]):
        """Temporarily select a model chain for Auto based on capability profile.

        Capability profiles override Flash/Pro tier selections. Explicit
        provider/model calls remain authoritative for non-Agent callers.
        """
        profile = (auto_profile or "").strip().lower()
        if not profile or profile == "default":
            yield
            return

        active_state = _llm_request_state.get()
        if (
            active_state is not None
            and active_state.get("selection_source") != "tier"
            and (active_state.get("provider") or active_state.get("model"))
        ):
            yield
            return

        profile_configs = {
            "multimodal": getattr(settings, "llm_multimodal_models", "") or "",
        }
        profile_config = profile_configs.get(profile)
        if profile_config is None:
            logger.warning("llm_auto_profile_unsupported", auto_profile=profile)
            yield
            return
        if not profile_config.strip():
            logger.warning("llm_auto_profile_unconfigured", auto_profile=profile)
            yield
            return

        candidates = [
            candidate
            for candidate in parse_fallback_candidates("", "", profile_config)
            if candidate.provider
        ]
        if not candidates:
            raise ValueError(f"No candidates configured for Auto profile: {profile}")

        token = _llm_request_state.set({})
        try:
            state = _llm_request_state.get()
            if state is not None:
                state["selection_source"] = "auto_profile"
                state["auto_profile"] = profile
            primary = candidates[0]
            self.provider = primary.provider
            self._load_provider_config()
            if primary.model:
                self.model = primary.model
            fallback_items = [
                f"{candidate.provider}/{candidate.model}" if candidate.model else candidate.provider
                for candidate in candidates[1:]
            ]
            self.request_fallbacks = ",".join(fallback_items)
            logger.info(
                "llm_request_auto_profile_selected",
                auto_profile=profile,
                provider=self.provider,
                model=self.model,
                base_url=self.base_url,
                fallbacks=self.request_fallbacks,
            )
            yield
        finally:
            temporary_client = self.anthropic_client
            _llm_request_state.reset(token)
            if temporary_client is not None:
                self._schedule_anthropic_client_close(temporary_client)

    @staticmethod
    def _strip_thinking_blocks(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """剥离消息中的 thinking blocks（包括 thinking 和 redacted_thinking）

        用于新用户轮次开始时清理历史中的 thinking blocks。
        DeepSeek 要求：同一次工具调用链路必须保留 thinking blocks，
        但新一轮用户问题开始时需要清理。

        参考 Claude Code 的 stripSignatureBlocks 策略。

        Args:
            messages: Anthropic 格式消息列表

        Returns:
            剥离 thinking blocks 后的消息列表（深拷贝，不修改原列表）
        """
        import copy
        stripped = []
        thinking_count = 0

        for msg in messages:
            content = msg.get("content", [])

            if isinstance(content, list):
                # 过滤掉 thinking 和 redacted_thinking blocks
                new_blocks = [
                    block for block in content
                    if not (isinstance(block, dict) and block.get("type") in ("thinking", "redacted_thinking"))
                ]
                thinking_count += len(content) - len(new_blocks)

                if new_blocks:
                    # 还有剩余 blocks，保留消息
                    new_msg = copy.copy(msg)
                    new_msg["content"] = new_blocks
                    stripped.append(new_msg)
                else:
                    # 所有 blocks 都是 thinking，替换为空 text block
                    # Anthropic API 不允许 assistant 消息 content 为空列表
                    new_msg = copy.copy(msg)
                    new_msg["content"] = [{"type": "text", "text": ""}]
                    stripped.append(new_msg)
            else:
                stripped.append(msg)

        if thinking_count > 0:
            logger.info(
                "thinking_blocks_stripped",
                stripped_count=thinking_count,
                messages_count=len(messages)
            )

        return stripped

    @staticmethod
    def _filter_redacted_thinking_for_deepseek(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """过滤 DeepSeek 不支持的 redacted_thinking blocks

        DeepSeek API 不支持 redacted_thinking 类型，只支持 thinking。
        在保留 thinking blocks 时（同一次工具调用链路），需要过滤掉 redacted_thinking。

        Args:
            messages: Anthropic 格式消息列表

        Returns:
            过滤后的消息列表（深拷贝，不修改原列表）
        """
        import copy
        filtered = []
        redacted_count = 0

        for msg in messages:
            content = msg.get("content", [])

            if isinstance(content, list):
                # 过滤掉 redacted_thinking blocks，保留 thinking blocks
                new_blocks = [
                    block for block in content
                    if not (isinstance(block, dict) and block.get("type") == "redacted_thinking")
                ]
                redacted_count += len(content) - len(new_blocks)

                if new_blocks:
                    new_msg = copy.copy(msg)
                    new_msg["content"] = new_blocks
                    filtered.append(new_msg)
                else:
                    # 所有 blocks 都被过滤了，保留空消息（不应该发生）
                    filtered.append(msg)
            else:
                filtered.append(msg)

        if redacted_count > 0:
            logger.info(
                "redacted_thinking_filtered",
                filtered_count=redacted_count,
                messages_count=len(messages)
            )

        return filtered

    @staticmethod
    def _sanitize_anthropic_messages(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Return messages valid for Anthropic Messages API.

        The Messages API only accepts user/assistant roles. Internal compact
        boundary markers are useful for local memory, but must not be sent as
        provider messages.
        """
        import copy

        sanitized: List[Dict[str, Any]] = []
        dropped_roles: Dict[str, int] = {}

        for msg in messages:
            role = msg.get("role")
            if role in ("user", "assistant"):
                sanitized.append(copy.deepcopy(msg))
                continue

            dropped_roles[str(role)] = dropped_roles.get(str(role), 0) + 1

        if dropped_roles:
            logger.warning(
                "anthropic_invalid_message_roles_dropped",
                dropped_roles=dropped_roles,
                original_count=len(messages),
                sanitized_count=len(sanitized),
            )

        return sanitized

    @staticmethod
    def _detect_thinking_blocks(messages: List[Dict[str, Any]]) -> Tuple[bool, List[str], List[Dict[str, Any]]]:
        """Detect thinking/redacted_thinking blocks for provider-specific handling."""
        has_thinking_blocks = False
        thinking_blocks_found: List[str] = []
        messages_structure: List[Dict[str, Any]] = []

        for msg in messages:
            content = msg.get("content", [])
            msg_info = {
                "role": msg.get("role"),
                "content_type": type(content).__name__,
                "content_length": len(content) if isinstance(content, list) else 0,
                "content_types": [],
            }

            if isinstance(content, list):
                for block in content:
                    block_type = block.get("type") if isinstance(block, dict) else "unknown"
                    msg_info["content_types"].append(block_type)
                    if isinstance(block, dict) and block.get("type") in ("thinking", "redacted_thinking"):
                        has_thinking_blocks = True
                        thinking_blocks_found.append(f"role={msg.get('role')}, type={block_type}")
                        break
            messages_structure.append(msg_info)

            if has_thinking_blocks:
                break

        return has_thinking_blocks, thinking_blocks_found, messages_structure

    @staticmethod
    def _is_tool_continuation(messages: List[Dict[str, Any]]) -> bool:
        """Whether the request continues the same tool-use chain.

        用于判断是否是同一次工具调用链路的延续（vs 新用户轮次）。
        适用于 DeepSeek、Mimo 等需要在工具调用链路中保留 thinking blocks 的 provider。
        """
        if len(messages) < 2:
            return False

        last_msg = messages[-1]
        second_last_msg = messages[-2]
        if last_msg.get("role") != "user" or second_last_msg.get("role") != "assistant":
            return False

        last_content = last_msg.get("content", [])
        second_last_content = second_last_msg.get("content", [])
        has_tool_result = any(
            isinstance(block, dict) and block.get("type") == "tool_result"
            for block in (last_content if isinstance(last_content, list) else [])
        )
        has_tool_use = any(
            isinstance(block, dict) and block.get("type") == "tool_use"
            for block in (second_last_content if isinstance(second_last_content, list) else [])
        )
        return has_tool_result and has_tool_use

    # 向后兼容的别名
    _is_deepseek_tool_continuation = _is_tool_continuation

    def _build_anthropic_api_params(
        self,
        *,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict]],
        max_tokens: Optional[int],
        temperature: float,
        system: Optional[str],
        streaming: bool = False,
    ) -> Dict[str, Any]:
        """Build provider-specific Anthropic-compatible request parameters.

        This must run after selecting a fallback candidate because message
        normalization, thinking mode, and prompt-cache support differ by
        provider.
        """
        sanitized_messages = self._sanitize_anthropic_messages(messages)

        is_real_anthropic = (
            self.provider in ["anthropic", "claude"] or
            "claude" in self.model.lower() or
            "anthropic" in self.model.lower()
        )
        is_deepseek = (
            self.provider == "deepseek" or
            "deepseek" in self.model.lower()
        )
        is_mimo = (
            self.provider == "mimo" or
            "mimo" in self.model.lower()
        )

        has_thinking_blocks, thinking_blocks_found, messages_structure = self._detect_thinking_blocks(
            sanitized_messages
        )

        logger.info(
            "thinking_blocks_detection_streaming" if streaming else "thinking_blocks_detection",
            provider=self.provider,
            model=self.model,
            has_thinking_blocks=has_thinking_blocks,
            is_deepseek=is_deepseek,
            is_mimo=is_mimo,
            found_blocks=thinking_blocks_found,
            messages_count=len(sanitized_messages),
            messages_structure=messages_structure,
        )

        api_params: Dict[str, Any] = {
            "model": self.model,
            "messages": sanitized_messages,
            "max_tokens": max_tokens or 16384,
            "temperature": temperature,
        }

        if tools:
            api_params["tools"] = tools

        logger.debug(
            "thinking_mode_decision_streaming" if streaming else "thinking_mode_decision",
            provider=self.provider,
            model=self.model,
            is_real_anthropic=is_real_anthropic,
            is_deepseek=is_deepseek,
            is_mimo=is_mimo,
            has_thinking_blocks_in_history=has_thinking_blocks,
        )

        if is_real_anthropic:
            api_params["thinking"] = {
                "type": "extended",
                "budget_tokens": 20000,
            }
            logger.info("extended_thinking_enabled", provider=self.provider, model=self.model)
        elif is_mimo:
            # Mimo: 与 DeepSeek 相同的逻辑
            # 在工具调用链路中保留 thinking blocks，新用户轮次禁用 thinking 模式
            if self._is_tool_continuation(sanitized_messages) and has_thinking_blocks:
                api_params["messages"] = self._filter_redacted_thinking_for_deepseek(sanitized_messages)
                logger.info(
                    "mimo_thinking_blocks_preserved",
                    provider=self.provider,
                    model=self.model,
                    reason="Same tool call continuation, preserving thinking blocks (filtered redacted_thinking)",
                )
            else:
                api_params["thinking"] = {"type": "disabled"}
                api_params["messages"] = self._strip_thinking_blocks(sanitized_messages)
                logger.info(
                    "mimo_thinking_mode_disabled",
                    provider=self.provider,
                    model=self.model,
                    reason="New user turn, disabling thinking mode and stripping thinking blocks",
                )
        elif is_deepseek:
            if self._is_tool_continuation(sanitized_messages) and has_thinking_blocks:
                api_params["messages"] = self._filter_redacted_thinking_for_deepseek(sanitized_messages)
                logger.info(
                    "deepseek_thinking_blocks_preserved",
                    provider=self.provider,
                    model=self.model,
                    reason="Same tool call continuation, preserving thinking blocks (filtered redacted_thinking)",
                )
            else:
                api_params["thinking"] = {"type": "disabled"}
                api_params["messages"] = self._strip_thinking_blocks(sanitized_messages)
                logger.info(
                    "deepseek_thinking_mode_disabled",
                    provider=self.provider,
                    model=self.model,
                    reason="New user turn, disabling thinking mode and stripping thinking blocks",
                )
        else:
            api_params["messages"] = self._strip_thinking_blocks(sanitized_messages)
            logger.info(
                "extended_thinking_skipped",
                provider=self.provider,
                model=self.model,
                reason="Not a real Anthropic API",
            )

        if system:
            api_params["system"] = system

        if self.provider in ["mimo", "minimax", "anthropic"] or "claude" in self.model.lower():
            api_params = self._add_cache_control(api_params)
            logger.info(
                "prompt_cache_enabled",
                provider=self.provider,
                model=self.model,
                reason="Provider supports cache_control",
            )
        else:
            logger.debug(
                "prompt_cache_skipped",
                provider=self.provider,
                model=self.model,
                reason="Provider does not support cache_control (auto KV cache or not supported)",
            )

        if "thinking" in api_params:
            extra_body = api_params.get("extra_body") or {}
            if not isinstance(extra_body, dict):
                extra_body = {}
            extra_body["thinking"] = api_params.pop("thinking")
            api_params["extra_body"] = extra_body
            logger.debug(
                "thinking_param_via_extra_body",
                provider=self.provider,
                model=self.model,
                reason="anthropic SDK version does not support 'thinking' kwarg natively",
            )

        return api_params

    async def _parse_sse_stream(
        self,
        response: httpx.Response
    ) -> AsyncGenerator[str, None]:
        """解析 SSE 流，逐块 yield 内容片段

        Args:
            response: httpx 流式响应对象

        Yields:
            str: 每次返回一个文本块（chunk）
        """
        # 调试统计
        total_lines = 0
        data_lines = 0
        done_count = 0
        skipped_parse_error = 0
        skipped_no_choices = 0
        skipped_invalid_choice = 0
        skipped_empty_content = 0
        yielded_chunks = 0
        total_content_length = 0

        logger.debug(
            f"[SSE] 开始解析流式响应, "
            f"provider={self.provider}, model={self.model}"
        )

        async for line in response.aiter_lines():
            total_lines += 1
            if not line:
                continue

            # OpenAI / Qwen 兼容接口使用 "data: {...}" 和 "data: [DONE]" 形式
            if line.startswith("data: "):
                data_lines += 1
                data_str = line[len("data: "):].strip()
                if data_str == "[DONE]":
                    done_count += 1
                    logger.debug(f"[SSE] 收到 [DONE] 信号")
                    break

                try:
                    chunk = json.loads(data_str)
                except Exception as e:
                    skipped_parse_error += 1
                    if skipped_parse_error <= 5:
                        logger.warning(
                            f"[SSE] JSON 解析失败 (#{skipped_parse_error}): {e}, "
                            f"数据预览: {data_str[:200]}"
                        )
                    continue

                # 兼容不同provider的流式返回格式
                choices = chunk.get("choices")
                if not isinstance(choices, list) or not choices:
                    skipped_no_choices += 1
                    if skipped_no_choices <= 5:
                        logger.warning(
                            f"[SSE] choices 不合法 (#{skipped_no_choices}): "
                            f"type={type(choices)}, value={choices}"
                        )
                    continue

                first_choice = choices[0]
                if not isinstance(first_choice, dict):
                    skipped_invalid_choice += 1
                    if skipped_invalid_choice <= 5:
                        logger.warning(
                            f"[SSE] first_choice 不是字典 (#{skipped_invalid_choice}): "
                            f"type={type(first_choice)}, value={first_choice}"
                        )
                    continue

                # 提取内容片段
                delta = first_choice.get("delta") or first_choice.get("message") or {}

                # 优先使用 content，如果为空则尝试 reasoning_content（DeepSeek V4）
                piece = delta.get("content") or ""

                # DeepSeek V4 使用 reasoning_content 字段
                if not piece:
                    piece = delta.get("reasoning_content") or ""

                if piece:
                    yielded_chunks += 1
                    total_content_length += len(piece)
                    yield piece
                else:
                    skipped_empty_content += 1
                    # 记录前几个空数据块的完整结构，用于调试
                    if skipped_empty_content <= 3:
                        logger.debug(
                            f"[SSE] 空内容块 (#{skipped_empty_content}): "
                            f"delta keys={list(delta.keys()) if isinstance(delta, dict) else 'not dict'}"
                        )

        # 记录最终统计
        logger.info(
            f"[SSE] 流解析完成: "
            f"total_lines={total_lines}, data_lines={data_lines}, done={done_count}, "
            f"yielded_chunks={yielded_chunks}, total_content_length={total_content_length}, "
            f"skipped_parse={skipped_parse_error}, skipped_no_choices={skipped_no_choices}, "
            f"skipped_invalid_choice={skipped_invalid_choice}, skipped_empty={skipped_empty_content}"
        )

        # 如果没有任何 yield，记录警告
        if yielded_chunks == 0 and data_lines > 0:
            logger.error(
                f"[SSE] 警告: 处理了 {data_lines} 条 data 行但没有 yield 任何内容! "
                f"这表明 API 响应格式可能与预期不符"
            )

    async def _parse_sse_stream_with_status(
        self,
        response: httpx.Response
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """解析 SSE 流，逐块 yield 内容片段和状态

        Args:
            response: httpx 流式响应对象

        Yields:
            dict: {"chunk": str, "is_complete": bool}
                  - chunk: 文本块内容
                  - is_complete: 流是否结束
        """
        # 调试统计
        total_lines = 0
        data_lines = 0
        done_count = 0
        skipped_parse_error = 0
        skipped_no_choices = 0
        skipped_invalid_choice = 0
        skipped_empty_content = 0
        yielded_chunks = 0
        total_content_length = 0

        logger.debug(
            f"[SSE-with-status] 开始解析流式响应, "
            f"provider={self.provider}, model={self.model}"
        )

        async for line in response.aiter_lines():
            total_lines += 1
            if not line:
                continue

            # OpenAI / Qwen 兼容接口使用 "data: {...}" 和 "data: [DONE]" 形式
            if line.startswith("data: "):
                data_lines += 1
                data_str = line[len("data: "):].strip()
                if data_str == "[DONE]":
                    done_count += 1
                    logger.debug(f"[SSE-with-status] 收到 [DONE] 信号")
                    # 流结束，yield结束标记
                    yield {"chunk": "", "is_complete": True}
                    return

                try:
                    chunk = json.loads(data_str)
                except Exception as e:
                    skipped_parse_error += 1
                    if skipped_parse_error <= 5:
                        logger.warning(
                            f"[SSE-with-status] JSON 解析失败 (#{skipped_parse_error}): {e}, "
                            f"数据预览: {data_str[:200]}"
                        )
                    continue

                # 兼容不同provider的流式返回格式
                choices = chunk.get("choices")
                if not isinstance(choices, list) or not choices:
                    skipped_no_choices += 1
                    if skipped_no_choices <= 5:
                        logger.warning(
                            f"[SSE-with-status] choices 不合法 (#{skipped_no_choices}): "
                            f"type={type(choices)}, value={choices}"
                        )
                    continue

                first_choice = choices[0]
                if not isinstance(first_choice, dict):
                    skipped_invalid_choice += 1
                    if skipped_invalid_choice <= 5:
                        logger.warning(
                            f"[SSE-with-status] first_choice 不是字典 (#{skipped_invalid_choice}): "
                            f"type={type(first_choice)}, value={first_choice}"
                        )
                    continue

                # 提取内容片段
                delta = first_choice.get("delta") or first_choice.get("message") or {}

                # 优先使用 content，如果为空则尝试 reasoning_content（DeepSeek V4）
                piece = delta.get("content") or ""

                # DeepSeek V4 使用 reasoning_content 字段
                if not piece:
                    piece = delta.get("reasoning_content") or ""

                if piece:
                    yielded_chunks += 1
                    total_content_length += len(piece)
                    yield {"chunk": piece, "is_complete": False}
                else:
                    skipped_empty_content += 1
                    # 空内容不记录（可能很频繁）

        # 记录最终统计
        logger.info(
            f"[SSE-with-status] 流解析完成: "
            f"total_lines={total_lines}, data_lines={data_lines}, done={done_count}, "
            f"yielded_chunks={yielded_chunks}, total_content_length={total_content_length}, "
            f"skipped_parse={skipped_parse_error}, skipped_no_choices={skipped_no_choices}, "
            f"skipped_invalid_choice={skipped_invalid_choice}, skipped_empty={skipped_empty_content}"
        )

        # 如果没有任何 yield，记录警告
        if yielded_chunks == 0 and data_lines > 0:
            logger.error(
                f"[SSE-with-status] 警告: 处理了 {data_lines} 条 data 行但没有 yield 任何内容! "
                f"这表明 API 响应格式可能与预期不符"
            )

    async def _extract_response_text(self, response: httpx.Response) -> str:
        """安全地从httpx响应中提取文本内容

        处理流式和非流式响应，避免 ResponseNotRead 错误

        Args:
            response: httpx响应对象

        Returns:
            str: 响应文本（最多500字符）
        """
        try:
            # 尝试直接访问text属性（非流式响应）
            if hasattr(response, '_content') and response._content is not None:
                return response.text[:500]
            # 流式响应需要先读取
            content = await response.aread()
            return content.decode('utf-8', errors='ignore')[:500]
        except Exception as e:
            return f"Status {response.status_code} (unable to read: {str(e)[:50]})"

    async def _call_llm_with_retry(
        self,
        request_func: callable,
        *args,
        **kwargs
    ) -> Any:
        """带 429 速率限制重试的 LLM 调用

        Args:
            request_func: 异步请求函数
            *args: 传递给 request_func 的位置参数
            **kwargs: 传递给 request_func 的关键字参数

        Returns:
            request_func 的返回值

        Raises:
            Exception: 重试失败后抛出最后一次异常
        """
        max_retries = 3
        last_error = None

        for attempt in range(max_retries):
            try:
                return await request_func(*args, **kwargs)

            except httpx.HTTPStatusError as e:
                last_error = e
                status_code = e.response.status_code

                # 安全地提取响应文本
                response_text = await self._extract_response_text(e.response)

                # 检查是否是429速率限制错误
                is_rate_limit = status_code == 429 or (
                    status_code == 400 and
                    "rate limit" in response_text.lower()
                )

                if is_rate_limit and attempt < max_retries - 1:
                    # 指数退避：2秒、4秒、8秒
                    wait_time = min(2 ** attempt, 60)
                    logger.warning(
                        "llm_rate_limit_detected",
                        status_code=status_code,
                        attempt=attempt + 1,
                        max_retries=max_retries,
                        wait_seconds=wait_time,
                        response_text=response_text[:200]
                    )
                    await asyncio.sleep(wait_time)
                    continue
                else:
                    # 非429错误或已达最大重试次数，直接抛出
                    logger.error(
                        "llm_http_error",
                        status_code=status_code,
                        response_text=response_text[:500],
                        attempt=attempt + 1,
                        max_retries=max_retries
                    )
                    raise

            except Exception as e:
                # 其他异常直接抛出
                logger.error(
                    "llm_request_error",
                    error=str(e),
                    error_type=type(e).__name__,
                    attempt=attempt + 1,
                    max_retries=max_retries
                )
                raise

        # 理论上不会到达这里
        raise last_error

    # Provider配置映射（与 settings 中的 provider 一致）
    PROVIDER_CONFIG = {
        "deepseek": {
            "url_env": "DEEPSEEK_BASE_URL",
            "url_default": "https://api.deepseek.com/v1",
            "key_env": "DEEPSEEK_API_KEY",
            "model_env": "DEEPSEEK_MODEL",
            "model_default": "deepseek-chat",
        },
        "bailian": {
            "url_env": "BAILIAN_BASE_URL",
            "url_default": "https://token-plan.cn-beijing.maas.aliyuncs.com/apps/anthropic",
            "key_env": "BAILIAN_API_KEY",
            "model_env": "BAILIAN_MODEL",
            "model_default": "qwen3.8-max-preview",
        },
        "minimax": {
            "url_env": "MINIMAX_BASE_URL",
            "url_default": "https://api.minimaxi.com/v1",
            "key_env": "MINIMAX_API_KEY",
            "model_env": "MINIMAX_MODEL",
            "model_default": "MiniMax-M3",
        },
        "openai": {
            "url_env": "OPENAI_BASE_URL",
            "url_default": "https://api.openai.com/v1",
            "key_env": "OPENAI_API_KEY",
            "model_env": "OPENAI_MODEL",
            "model_default": "gpt-4-turbo-preview",
        },
        # Xiaomi Mimo，与 Agent 保持一致（Anthropic 兼容协议）
        "mimo": {
            "url_env": "MIMO_BASE_URL",
            "url_default": "https://api.xiaomimimo.com/anthropic",
            "key_env": "MIMO_API_KEY",
            "model_env": "MIMO_MODEL",
            "model_default": "mimo-v2.5",
        },
        "agnes": {
            "url_env": "AGNES_BASE_URL",
            "url_default": "https://apihub.agnes-ai.com/v1",
            "key_env": "AGNES_API_KEY",
            "model_env": "AGNES_MODEL",
            "model_default": "agnes-2.0-flash",
        },
        # 智谱 GLM Coding Plan（OpenAI + Anthropic 兼容协议）
        "glm": {
            "url_env": "GLM_BASE_URL",
            "url_default": "https://open.bigmodel.cn/api/coding/paas/v4",
            "key_env": "GLM_API_KEY",
            "model_env": "GLM_MODEL",
            "model_default": "glm-4.7",
        },
    }

    def __init__(self):
        # 优先使用 settings 中的配置，确保与 .env 文件一致
        self.provider = settings.llm_provider.lower()
        self.temperature = settings.llm_temperature

        # 调试信息：检查配置是否正确
        logger.debug(
            "llm_provider_config_check",
            provider_from_settings=self.provider,
            temperature=self.temperature
        )

        self._load_provider_config()

        logger.info(
            "llm_service_initialized",
            provider=self.provider,
            model=self.model,
            base_url=self.base_url,
            temperature=self.temperature
        )

    def _snapshot_provider_state(self) -> Dict[str, Any]:
        return {
            "provider": self.provider,
            "base_url": getattr(self, "base_url", None),
            "api_key": getattr(self, "api_key", None),
            "model": getattr(self, "model", None),
            "api_mode": getattr(self, "api_mode", "anthropic_messages"),
            "anthropic_client": getattr(self, "anthropic_client", None),
        }

    def _restore_provider_state(self, state: Dict[str, Any]) -> None:
        current_client = getattr(self, "anthropic_client", None)
        target_client = state["anthropic_client"]
        if current_client is not None and current_client is not target_client:
            self._schedule_anthropic_client_close(current_client)
        self.provider = state["provider"]
        self.base_url = state["base_url"]
        self.api_key = state["api_key"]
        self.model = state["model"]
        self.api_mode = state["api_mode"]
        self.anthropic_client = state["anthropic_client"]

    def _schedule_anthropic_client_close(self, client: Any) -> None:
        """Close a temporary Anthropic SDK client without leaking task errors."""
        close = getattr(client, "close", None)
        if not callable(close):
            return

        async def close_client() -> None:
            try:
                await close()
            except asyncio.CancelledError:
                logger.debug("llm_anthropic_client_close_cancelled")
                return
            except RuntimeError as exc:
                if "handler is closed" in str(exc):
                    logger.debug("llm_anthropic_client_close_ignored", error=str(exc))
                    return
                raise

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return

        task = loop.create_task(close_client())

        def consume_close_result(done_task: asyncio.Task) -> None:
            try:
                done_task.result()
            except asyncio.CancelledError:
                logger.debug("llm_anthropic_client_close_task_cancelled")
            except Exception as exc:
                logger.warning(
                    "llm_anthropic_client_close_failed",
                    error=str(exc),
                    error_type=type(exc).__name__,
                )

        task.add_done_callback(consume_close_result)

    def _switch_provider_for_attempt(self, provider: str, model: Optional[str] = None) -> None:
        """Switch this service instance to a fallback candidate for one attempt."""
        original_provider = self.provider
        self.provider = provider.lower()
        self._load_provider_config()
        if model:
            self.model = model
        logger.info(
            "llm_fallback_candidate_selected",
            original_provider=original_provider,
            provider=self.provider,
            model=self.model,
        )

    def _create_provider_override_service(self, provider: Optional[str], model: Optional[str]) -> Optional["LLMService"]:
        """Create an isolated service instance for an explicit provider/model call."""
        selected_provider = (provider or "").strip().lower()
        selected_model = (model or "").strip()
        if not selected_provider and not selected_model:
            return None

        service = self.__class__()
        if selected_provider:
            service.provider = selected_provider
            service._load_provider_config()
        if selected_model:
            service.model = selected_model
        service.request_fallbacks = ""
        logger.info(
            "llm_call_provider_model_selected",
            provider=service.provider,
            model=service.model,
            base_url=service.base_url,
        )
        return service

    def _schedule_provider_override_service_close(self, service: Optional["LLMService"]) -> None:
        if service is None:
            return
        temporary_client = getattr(service, "anthropic_client", None)
        if temporary_client is not None:
            self._schedule_anthropic_client_close(temporary_client)

    async def _run_llm_request_with_global_limit(self, operation: str, call):
        semaphore = get_llm_pool_semaphore(self.provider, self.model)
        wait_started = time.monotonic()
        logger.debug(
            "llm_pool_concurrency_waiting",
            provider=self.provider,
            model=self.model,
            operation=operation,
        )
        async with semaphore:
            logger.debug(
                "llm_pool_concurrency_acquired",
                provider=self.provider,
                model=self.model,
                operation=operation,
                wait_ms=round((time.monotonic() - wait_started) * 1000, 2),
            )
            return await call()

    async def _run_anthropic_with_fallback(self, operation: str, call):
        """Run an Anthropic-compatible request with configured model fallback."""
        original_state = self._snapshot_provider_state()
        candidates = parse_fallback_candidates(
            original_state["provider"],
            original_state["model"],
            self.request_fallbacks,
        )
        attempts = []

        try:
            for index, candidate in enumerate(candidates, start=1):
                if not (
                    candidate.provider == original_state["provider"].lower()
                    and (candidate.model or original_state["model"]) == original_state["model"]
                ):
                    self._switch_provider_for_attempt(candidate.provider, candidate.model)
                cooldown_failure = get_cooldown_failure(self.provider)
                if cooldown_failure and index < len(candidates):
                    attempts.append({
                        "provider": self.provider,
                        "model": self.model,
                        "reason": cooldown_failure.reason,
                        "status": cooldown_failure.status,
                        "code": cooldown_failure.code,
                        "error": "provider is in cooldown",
                    })
                    logger.warning(
                        "llm_fallback_candidate_skipped_cooldown",
                        provider=self.provider,
                        model=self.model,
                        reason=cooldown_failure.reason,
                    )
                    continue

                try:
                    result = await self._run_llm_request_with_global_limit(operation, call)
                    if attempts:
                        logger.warning(
                            "llm_fallback_candidate_succeeded",
                            provider=self.provider,
                            model=self.model,
                            attempts=summarize_attempts(attempts),
                        )
                    return result
                except Exception as exc:
                    failure = classify_llm_failure(exc)
                    attempts.append({
                        "provider": self.provider,
                        "model": self.model,
                        "reason": failure.reason,
                        "status": failure.status,
                        "code": failure.code,
                        "error": failure.message,
                    })
                    if failure.reason == "context_overflow":
                        raise
                    if should_fallback(failure):
                        mark_provider_cooldown(self.provider, failure)
                    has_next = index < len(candidates)
                    logger.warning(
                        "llm_fallback_candidate_failed",
                        provider=self.provider,
                        model=self.model,
                        reason=failure.reason,
                        status=failure.status,
                        code=failure.code,
                        has_next=has_next,
                        error=failure.message[:300],
                    )
                    if not has_next or not should_fallback(failure):
                        raise
            raise LLMFailoverError(summarize_attempts(attempts))
        except Exception:
            if attempts:
                logger.error("llm_fallback_failed", attempts=summarize_attempts(attempts))
            raise
        finally:
            self._restore_provider_state(original_state)

    def _load_provider_config(self):
        """根据provider加载对应配置"""
        if self.provider in {"qwen", "qwen_vl"}:
            raise ValueError(f"Unsupported LLM provider: {self.provider}")

        config = self.PROVIDER_CONFIG.get(self.provider)

        if not config:
            logger.warning(
                "llm_unknown_provider_fallback",
                provider=self.provider,
                fallback_provider="deepseek"
            )
            config = self.PROVIDER_CONFIG["deepseek"]
            self.provider = "deepseek"

        # 🔍 调试日志：记录配置加载过程
        logger.debug(
            "llm_loading_provider_config",
            provider=self.provider,
            config_exists=config is not None,
            url_env=config.get("url_env") if config else None,
            url_default=config.get("url_default") if config else None
        )

        # 优先从 settings 读取，如果没有则从环境变量读取
        if self.provider == "deepseek":
            self.api_mode = getattr(settings, "deepseek_api_mode", "anthropic_messages")
            self.base_url = settings.deepseek_base_url
            self.api_key = settings.deepseek_api_key or ""
            self.model = settings.deepseek_model
            # 回退到环境变量
            if not self.base_url:
                self.base_url = os.getenv(config["url_env"], config["url_default"])
                logger.debug("llm_deepseek_base_url_fallback_to_env", base_url=self.base_url)
            if not self.model:
                self.model = os.getenv(config["model_env"], config["model_default"])
                logger.debug("llm_deepseek_model_fallback_to_env", model=self.model)

        elif self.provider == "bailian":
            self.api_mode = settings.bailian_api_mode
            self.base_url = settings.bailian_base_url
            self.api_key = settings.bailian_api_key or ""
            self.model = settings.bailian_model

        elif self.provider == "minimax":
            self.api_mode = getattr(settings, "minimax_api_mode", "anthropic_messages")
            self.base_url = settings.minimax_base_url
            self.api_key = settings.minimax_api_key or ""
            self.model = settings.minimax_model
            # 回退到环境变量
            if not self.base_url:
                self.base_url = os.getenv(config["url_env"], config["url_default"])
                logger.debug("llm_minimax_base_url_fallback_to_env", base_url=self.base_url)
            if not self.model:
                self.model = os.getenv(config["model_env"], config["model_default"])
                logger.debug("llm_minimax_model_fallback_to_env", model=self.model)

        elif self.provider == "openai":
            self.api_mode = getattr(settings, "openai_api_mode", "chat_completions")
            self.base_url = settings.openai_base_url
            self.api_key = settings.openai_api_key or ""
            self.model = settings.openai_model
            # 回退到环境变量
            if not self.base_url:
                self.base_url = os.getenv(config["url_env"], config["url_default"])
                logger.debug("llm_openai_base_url_fallback_to_env", base_url=self.base_url)
            if not self.model:
                self.model = os.getenv(config["model_env"], config["model_default"])
                logger.debug("llm_openai_model_fallback_to_env", model=self.model)

        elif self.provider == "mimo":
            self.api_mode = getattr(settings, "mimo_api_mode", "anthropic_messages")
            self.base_url = settings.mimo_base_url
            self.api_key = settings.mimo_api_key or ""
            self.model = settings.mimo_model
            # 回退到环境变量
            if not self.base_url:
                self.base_url = os.getenv(config["url_env"], config["url_default"])
                logger.debug("llm_mimo_base_url_fallback_to_env", base_url=self.base_url)
            if not self.model:
                self.model = os.getenv(config["model_env"], config["model_default"])
                logger.debug("llm_mimo_model_fallback_to_env", model=self.model)

        elif self.provider == "agnes":
            self.api_mode = getattr(settings, "agnes_api_mode", "chat_completions")
            self.base_url = (
                settings.agnes_base_url
                or os.getenv(config["url_env"])
                or config["url_default"]
            )
            self.api_key = (
                settings.agnes_api_key
                or os.getenv(config["key_env"])
                or getattr(settings, "tender_secondary_llm_api_key", None)
                or ""
            )
            self.model = settings.agnes_model
            if not self.model:
                self.model = os.getenv(config["model_env"], config["model_default"])
                logger.debug("llm_agnes_model_fallback_to_env", model=self.model)

        elif self.provider == "glm":
            self.api_mode = getattr(settings, "glm_api_mode", "anthropic_messages")
            self.base_url = (
                settings.glm_base_url
                or os.getenv(config["url_env"])
                or os.getenv("OPENAI_BASE_URL")
                or config["url_default"]
            )
            self.api_key = (
                settings.glm_api_key
                or os.getenv(config["key_env"])
                or settings.anthropic_auth_token
                or os.getenv("ANTHROPIC_AUTH_TOKEN")
                or settings.anthropic_api_key
                or os.getenv("ANTHROPIC_API_KEY")
                or ""
            )
            self.model = settings.glm_model
            if not self.model:
                self.model = os.getenv(config["model_env"], config["model_default"])
                logger.debug("llm_glm_model_fallback_to_env", model=self.model)

        else:
            # 回退到环境变量
            self.api_mode = "chat_completions"
            self.base_url = os.getenv(config["url_env"], config["url_default"])
            self.api_key = os.getenv(config["key_env"], "")
            self.model = os.getenv(config["model_env"], config["model_default"])
            logger.debug(
                "llm_unknown_provider_fallback_to_env",
                provider=self.provider,
                base_url=self.base_url,
                model=self.model
            )

        # 🔍 关键验证：确保 base_url 和 model 不为 None
        if not self.base_url:
            logger.error(
                "llm_base_url_not_configured",
                provider=self.provider,
                error="base_url is None after loading config"
            )
            # 使用默认值作为最后的回退
            self.base_url = config.get("url_default", "http://localhost:8000/v1")
            logger.warning(
                "llm_using_default_base_url",
                provider=self.provider,
                default_url=self.base_url
            )

        if not self.model:
            logger.error(
                "llm_model_not_configured",
                provider=self.provider,
                error="model is None after loading config"
            )
            # 使用默认值作为最后的回退
            self.model = config.get("model_default", "gpt-3.5-turbo")
            logger.warning(
                "llm_using_default_model",
                provider=self.provider,
                default_model=self.model
            )

        # 最终配置日志
        logger.info(
            "llm_config_loaded",
            provider=self.provider,
            base_url=self.base_url,
            model=self.model,
            api_mode=self.api_mode,
            has_api_key=bool(self.api_key)
        )

        if not self.api_key:
            logger.warning("llm_api_key_not_configured", provider=self.provider)

        # Anthropic Native Client (always initialized for V3 architecture)
        self.anthropic_client = None
        if self.api_mode == "chat_completions":
            logger.info(
                "llm_anthropic_client_skipped_for_chat_completions",
                provider=self.provider,
                model=self.model,
                base_url=self.base_url,
            )
            return

        if self.provider in ["deepseek", "mimo", "glm", "minimax", "bailian"]:  # 支持 Anthropic 格式的提供商
            try:
                from anthropic import AsyncAnthropic

                # 完全从环境变量读取 base_url
                if self.provider == "mimo":
                    anthropic_base_url = settings.mimo_base_url
                elif self.provider == "minimax":
                    anthropic_base_url = (
                        getattr(settings, "minimax_anthropic_base_url", None)
                        or os.getenv("MINIMAX_ANTHROPIC_BASE_URL")
                        or "https://api.minimaxi.com/anthropic"
                    )
                elif self.provider == "deepseek":
                    # DeepSeek 的 Anthropic 格式端点
                    anthropic_base_url = settings.deepseek_base_url.replace("/v1", "/anthropic")
                elif self.provider == "glm":
                    anthropic_base_url = (
                        settings.glm_anthropic_base_url
                        or settings.anthropic_base_url
                        or os.getenv("ANTHROPIC_BASE_URL")
                        or "https://open.bigmodel.cn/api/anthropic"
                    )
                elif self.provider == "bailian":
                    anthropic_base_url = settings.bailian_base_url
                else:
                    logger.error(
                        "llm_anthropic_unsupported_provider",
                        provider=self.provider
                    )
                    return

                # 🔍 关键：确保base_url不带末尾斜杠，避免双斜杠问题
                # Anthropic SDK会自动添加斜杠，所以我们不需要
                anthropic_base_url = anthropic_base_url.rstrip('/')
                logger.info("llm_anthropic_base_url_cleaned",
                    provider=self.provider,
                    cleaned_url=anthropic_base_url
                )

                if not anthropic_base_url:
                    logger.error(
                        "llm_anthropic_base_url_missing",
                        provider=self.provider,
                        message=f"{self.provider.upper()}_BASE_URL 环境变量未配置"
                    )
                    return

                request_timeout = float(getattr(settings, "llm_request_timeout_seconds", 180.0) or 180.0)
                if self.provider == "mimo":
                    # MiMo's Anthropic-compatible endpoint accepts the SDK's
                    # standard API-key authentication. Passing api_key=None and
                    # injecting only a default header fails the SDK's local
                    # authentication validation before any request is sent.
                    self.anthropic_client = AsyncAnthropic(
                        api_key=self.api_key,
                        auth_token=None,
                        base_url=anthropic_base_url,
                        timeout=request_timeout,
                        max_retries=2
                    )
                elif self.provider == "glm":
                    # GLM Anthropic 兼容端点使用 ANTHROPIC_AUTH_TOKEN/Bearer 认证。
                    self.anthropic_client = AsyncAnthropic(
                        api_key=None,
                        auth_token=self.api_key,
                        base_url=anthropic_base_url,
                        timeout=request_timeout,
                        max_retries=2
                    )
                else:
                    self.anthropic_client = AsyncAnthropic(
                        api_key=self.api_key,
                        base_url=anthropic_base_url,
                        timeout=request_timeout,
                        max_retries=2
                    )
                logger.info(
                    "llm_anthropic_client_initialized",
                    provider=self.provider,
                    base_url=anthropic_base_url,
                    has_api_key=bool(self.api_key),
                )
            except ImportError:
                logger.error(
                    "llm_anthropic_import_failed",
                    message="anthropic package not installed, install with: pip install anthropic>=0.18.0"
                )
            except Exception as e:
                logger.error(
                    "llm_anthropic_client_init_failed",
                    error=str(e)
                )

    def _get_request_config(self) -> Tuple[str, Dict[str, str]]:
        """获取请求配置（URL, headers）"""
        # 🔍 调试日志：验证 base_url
        if not self.base_url:
            logger.error(
                "llm_get_request_config_base_url_is_none",
                provider=self.provider,
                model=self.model
            )
            raise ValueError(f"base_url is None for provider: {self.provider}")

        url = f"{self.base_url.rstrip('/')}/chat/completions"

        # 🔍 调试日志：记录请求配置
        logger.debug(
            "llm_get_request_config",
            url=url,
            has_api_key=bool(self.api_key)
        )

        headers = {
            "Content-Type": "application/json"
        }
        # 如果配置了API key，则添加Authorization header
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        return url, headers

    async def chat(
        self,
        messages: list,
        temperature: float = None,
        timeout: float = 120.0,
        max_tokens: int = None
    ) -> str:
        """
        简单的聊天接口（内部使用流式API避免超时）

        Args:
            messages: 消息列表，[{"role": "user", "content": "..."}]
            temperature: 温度参数
            timeout: 超时时间（秒），默认120秒（流式模式下使用600秒）
            max_tokens: 最大输出token数，默认None（使用API默认）

        Returns:
            LLM响应的文本内容
        """
        # 如果未指定temperature，使用settings中的默认值
        if temperature is None:
            temperature = self.temperature

        import httpx

        # 🔍 调试日志：记录 chat 方法调用
        logger.debug(
            "llm_chat_method_called",
            provider=self.provider,
            model=self.model,
            base_url=self.base_url,
            messages_count=len(messages),
            using_stream=True  # 标记使用流式模式
        )

        url, headers = self._get_request_config()

        # ✅ 使用LLMContextLogger记录完整的请求上下文到文件
        try:
            import uuid
            session_id = f"chat_{uuid.uuid4().hex[:8]}"

            llm_context_logger = get_llm_context_logger()
            log_file_path = llm_context_logger.log_request_context(
                session_id=session_id,
                iteration=0,  # chat方法没有iteration概念，使用0
                mode="chat",
                messages=messages,
                metadata={
                    "provider": self.provider,
                    "model": self.model,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                }
            )

            # 在控制台只显示预览和文件路径
            total_chars = sum(len(str(m.get("content", ""))) for m in messages)

            # 构建预览消息
            messages_preview = []
            for msg in messages:
                msg_copy = msg.copy()
                content = msg_copy.get("content", "")
                if len(content) > 300:
                    msg_copy["content"] = content[:300] + "...(truncated)"
                messages_preview.append(msg_copy)

            logger.info(
                "llm_chat_request",
                provider=self.provider,
                model=self.model,
                url=url,
                total_messages=len(messages),
                total_chars=total_chars,
                messages_preview=messages_preview,
                log_file=log_file_path,
            )
        except Exception as e:
            # 调试日志失败不影响正常请求
            logger.warning("llm_chat_request_logging_failed", error=str(e))

        # 🔥 使用流式API避免超时（超时时间增加到600秒）
        stream_timeout = 600.0  # 流式模式使用更长的超时时间

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "stream": True,  # 🔥 启用流式模式
        }

        if max_tokens is not None:
            payload["max_tokens"] = max_tokens

        # 🔍 调试日志：记录 payload
        logger.debug(
            "llm_chat_payload",
            model=payload.get("model"),
            has_messages=bool(messages),
            temperature=payload.get("temperature"),
            max_tokens=payload.get("max_tokens"),
            stream=True  # 标记为流式
        )

        # 429速率限制重试机制
        max_retries = 3
        last_error = None

        for attempt in range(max_retries):
            try:
                full_content = ""

                # 🔥 使用流式API（600秒超时）
                async with httpx.AsyncClient(timeout=stream_timeout) as client:
                    async with client.stream("POST", url, headers=headers, json=payload) as response:
                        response.raise_for_status()

                        # 使用辅助方法解析 SSE 流
                        async for chunk in self._parse_sse_stream(response):
                            full_content += chunk

                # MiniMax可能返回thinking标签，需要处理
                if self.provider == "minimax":
                    full_content = self._extract_json_from_thinking_response(full_content)

                logger.info(
                    "llm_chat_stream_completed",
                    provider=self.provider,
                    model=self.model,
                    response_length=len(full_content),
                    attempt=attempt + 1
                )

                return full_content

            except httpx.HTTPStatusError as e:
                last_error = e
                status_code = e.response.status_code

                # 读取响应内容（流式响应需要先读取）
                response_text = "N/A"
                try:
                    response_text = (await e.response.aread()).decode('utf-8', errors='ignore')[:500]
                except Exception:
                    response_text = f"Status {status_code} (unable to read response)"

                # 检查是否是429速率限制错误
                is_rate_limit = status_code == 429 or (
                    status_code == 400 and
                    "rate limit" in response_text.lower()
                )

                if is_rate_limit and attempt < max_retries - 1:
                    # 指数退避：2秒、4秒、8秒
                    wait_time = min(2 ** attempt, 60)
                    logger.warning(
                        "llm_rate_limit_detected",
                        status_code=status_code,
                        attempt=attempt + 1,
                        max_retries=max_retries,
                        wait_seconds=wait_time,
                        response_text=response_text[:200]
                    )
                    await asyncio.sleep(wait_time)
                    continue
                else:
                    # 非429错误或已达最大重试次数，直接抛出
                    logger.error(
                        "llm_http_error",
                        status_code=status_code,
                        response_text=response_text[:500],
                        url=url,
                        provider=self.provider,
                        model=self.model,
                        attempt=attempt + 1,
                        max_retries=max_retries
                    )
                    raise

        # 理论上不会到达这里，但为了类型检查完整性
        raise last_error

    async def chat_streaming(
        self,
        messages: list,
        temperature: float = None,
        timeout: float = 600.0,
        max_tokens: int = None,
    ):
        """
        真正的流式 LLM 调用，逐块 yield 文本内容

        Args:
            messages: 消息列表
            temperature: 温度参数
            timeout: 超时时间
            max_tokens: 最大token数

        Yields:
            str: 每次返回一个文本块（chunk）
        """
        # 如果未指定temperature，使用settings中的默认值
        if temperature is None:
            temperature = self.temperature

        url, headers = self._get_request_config()

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "stream": True,
        }

        if max_tokens is not None:
            payload["max_tokens"] = max_tokens

        logger.info(
            "llm_chat_streaming_start",
            provider=self.provider,
            model=self.model,
            messages_count=len(messages)
        )

        # 429速率限制重试机制
        max_retries = 3
        last_error = None

        for attempt in range(max_retries):
            try:
                async with httpx.AsyncClient(timeout=timeout) as client:
                    async with client.stream("POST", url, headers=headers, json=payload) as response:
                        response.raise_for_status()

                        # 使用辅助方法解析 SSE 流
                        async for chunk in self._parse_sse_stream(response):
                            yield chunk

                logger.info("llm_chat_streaming_complete")
                return  # 成功完成

            except httpx.HTTPStatusError as e:
                last_error = e
                status_code = e.response.status_code

                # 安全地提取响应文本
                response_text = await self._extract_response_text(e.response)

                # 检查是否是429速率限制错误
                is_rate_limit = status_code == 429 or (
                    status_code == 400 and
                    "rate limit" in response_text.lower()
                )

                if is_rate_limit and attempt < max_retries - 1:
                    # 指数退避
                    wait_time = min(2 ** attempt, 60)
                    logger.warning(
                        "llm_streaming_rate_limit_detected",
                        status_code=status_code,
                        attempt=attempt + 1,
                        max_retries=max_retries,
                        wait_seconds=wait_time,
                        response_text=response_text[:200]
                    )
                    await asyncio.sleep(wait_time)
                    continue
                else:
                    logger.error(
                        "llm_streaming_http_error",
                        status_code=status_code,
                        response_text=response_text[:500],
                        attempt=attempt + 1,
                        max_retries=max_retries
                    )
                    raise

        # 理论上不会到达这里
        raise last_error

    async def chat_streaming_with_status(
        self,
        messages: list,
        temperature: float = None,
        timeout: float = 600.0,
        max_tokens: int = None,
    ):
        """
        流式 LLM 调用，返回文本块和状态信息

        与 chat_streaming 的区别：
        - 返回字典格式：{"chunk": str, "is_complete": bool}
        - is_complete 为 True 时表示流已结束（SSE [DONE] 信号）

        Args:
            messages: 消息列表
            temperature: 温度参数
            timeout: 超时时间
            max_tokens: 最大token数

        Yields:
            dict: {"chunk": str, "is_complete": bool}
        """
        # 如果未指定temperature，使用settings中的默认值
        if temperature is None:
            temperature = self.temperature

        url, headers = self._get_request_config()

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "stream": True,
        }

        if max_tokens is not None:
            payload["max_tokens"] = max_tokens

        # ✅ 使用LLMContextLogger记录完整的请求上下文到文件
        try:
            import uuid
            session_id = f"llm_service_{uuid.uuid4().hex[:8]}"

            llm_context_logger = get_llm_context_logger()
            log_file_path = llm_context_logger.log_request_context(
                session_id=session_id,
                iteration=0,  # llm_service没有iteration概念，使用0
                mode="llm_service",
                messages=messages,
                metadata={
                    "provider": self.provider,
                    "model": self.model,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                }
            )

            # 在控制台只显示预览和文件路径
            messages_preview = []
            for msg in messages:
                msg_copy = msg.copy()
                content = msg_copy.get("content", "")
                if len(content) > 300:
                    msg_copy["content"] = content[:300] + "...(truncated)"
                messages_preview.append(msg_copy)

            logger.info(
                "llm_streaming_request",
                provider=self.provider,
                model=self.model,
                url=url,
                temperature=temperature,
                max_tokens=max_tokens,
                messages_count=len(messages),
                messages_preview=messages_preview,
                log_file=log_file_path,
            )
        except Exception as e:
            logger.error("llm_context_logging_failed", error=str(e))

        # 429速率限制重试机制
        max_retries = 3
        last_error = None

        for attempt in range(max_retries):
            try:
                async with httpx.AsyncClient(timeout=timeout) as client:
                    async with client.stream("POST", url, headers=headers, json=payload) as response:
                        response.raise_for_status()

                        # 使用辅助方法解析 SSE 流，并传递流结束信号
                        async for result in self._parse_sse_stream_with_status(response):
                            yield result

                logger.info("llm_chat_streaming_with_status_complete")

                return  # 成功完成

            except httpx.HTTPStatusError as e:
                last_error = e
                status_code = e.response.status_code

                # 安全地提取响应文本
                response_text = await self._extract_response_text(e.response)

                # 检查是否是429速率限制错误
                is_rate_limit = status_code == 429 or (
                    status_code == 400 and
                    "rate limit" in response_text.lower()
                )

                if is_rate_limit and attempt < max_retries - 1:
                    # 指数退避
                    wait_time = min(2 ** attempt, 60)
                    logger.warning(
                        "llm_streaming_with_status_rate_limit_detected",
                        status_code=status_code,
                        attempt=attempt + 1,
                        max_retries=max_retries,
                        wait_seconds=wait_time,
                        response_text=response_text[:200]
                    )
                    await asyncio.sleep(wait_time)
                    continue
                else:
                    logger.error(
                        "llm_streaming_with_status_http_error",
                        status_code=status_code,
                        response_text=response_text[:500],
                        attempt=attempt + 1,
                        max_retries=max_retries
                    )
                    raise

        # 理论上不会到达这里
        raise last_error

    async def call_llm_with_json_response(
        self,
        prompt: str,
        max_retries: int = 2
    ) -> Dict[str, Any]:
        """
        调用LLM并解析JSON响应

        Args:
            prompt: 输入提示词
            max_retries: 最大重试次数

        Returns:
            解析后的JSON响应
        """
        original_state = self._snapshot_provider_state()
        candidates = parse_fallback_candidates(
            original_state["provider"],
            original_state["model"],
            self.request_fallbacks,
        )
        attempts = []

        try:
            for index, candidate in enumerate(candidates, start=1):
                if not (
                    candidate.provider == original_state["provider"].lower()
                    and (candidate.model or original_state["model"]) == original_state["model"]
                ):
                    self._switch_provider_for_attempt(candidate.provider, candidate.model)

                cooldown_failure = get_cooldown_failure(self.provider)
                if cooldown_failure and index < len(candidates):
                    attempts.append({
                        "provider": self.provider,
                        "model": self.model,
                        "reason": cooldown_failure.reason,
                        "status": cooldown_failure.status,
                        "code": cooldown_failure.code,
                        "error": "provider is in cooldown",
                    })
                    logger.warning(
                        "llm_json_fallback_candidate_skipped_cooldown",
                        provider=self.provider,
                        model=self.model,
                        reason=cooldown_failure.reason,
                    )
                    continue

                try:
                    result = await self._run_llm_request_with_global_limit(
                        "json_response",
                        lambda: self._call_llm_with_json_response_once(prompt, max_retries=max_retries),
                    )
                    if attempts:
                        logger.warning(
                            "llm_json_fallback_candidate_succeeded",
                            provider=self.provider,
                            model=self.model,
                            attempts=summarize_attempts(attempts),
                        )
                    return result
                except Exception as exc:
                    failure = classify_llm_failure(exc)
                    attempts.append({
                        "provider": self.provider,
                        "model": self.model,
                        "reason": failure.reason,
                        "status": failure.status,
                        "code": failure.code,
                        "error": failure.message,
                    })
                    if failure.reason == "context_overflow":
                        raise
                    if should_fallback(failure):
                        mark_provider_cooldown(self.provider, failure)
                    has_next = index < len(candidates)
                    logger.warning(
                        "llm_json_fallback_candidate_failed",
                        provider=self.provider,
                        model=self.model,
                        reason=failure.reason,
                        status=failure.status,
                        code=failure.code,
                        has_next=has_next,
                        error=failure.message[:300],
                    )
                    if not has_next or not should_fallback(failure):
                        raise
            raise LLMFailoverError(summarize_attempts(attempts))
        except Exception:
            if attempts:
                logger.error("llm_json_fallback_failed", attempts=summarize_attempts(attempts))
            raise
        finally:
            self._restore_provider_state(original_state)

    async def _call_llm_with_json_response_once(
        self,
        prompt: str,
        max_retries: int = 2,
    ) -> Dict[str, Any]:
        """Call the currently selected provider and parse a JSON object response."""
        import httpx

        try:
            logger.info(
                "llm_json_request_debug",
                provider=self.provider,
                model=self.model,
                prompt_length=len(prompt),
            )
        except Exception as e:
            logger.warning("llm_json_request_debug_failed", error=str(e))

        if self.anthropic_client and "/anthropic" in (self.base_url or ""):
            return await self._call_anthropic_with_json_response(prompt, max_retries=max_retries)

        url, headers = self._get_request_config()

        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "temperature": self.temperature
        }

        if self.provider in {"deepseek", "openai"}:
            payload["response_format"] = {"type": "json_object"}

        # Mimo特殊处理：禁用思考模式
        if self.provider == "mimo":
            payload["thinking"] = {"type": "disabled"}

        for attempt in range(max_retries):
            try:
                timeout = float(getattr(settings, "llm_request_timeout_seconds", 180.0) or 180.0)
                async with httpx.AsyncClient(timeout=timeout) as client:
                    response = await client.post(url, headers=headers, json=payload)
                    response.raise_for_status()
                    data = response.json()

                    # 提取响应内容
                    content = data.get("choices", [{}])[0].get("message", {}).get("content", "")

                    if self.provider == "minimax":
                        content = self._extract_json_from_thinking_response(content)

                    # 尝试解析JSON
                    # 先检查是否包含代码块标记，如果有则直接尝试提取（避免不必要的警告）
                    if "```json" in content or "```" in content:
                        extracted = self._extract_json_from_text(content)
                        if extracted is not None:
                            logger.info(
                                "llm_response_parsed_from_mixed_text",
                                provider=self.provider,
                                attempt=attempt + 1
                            )
                            return extracted

                    # 尝试直接解析JSON
                    try:
                        result = json.loads(content)
                        logger.info(
                            "llm_response_parsed",
                            provider=self.provider,
                            attempt=attempt + 1
                        )
                        return result
                    except json.JSONDecodeError as e:
                        # 如果直接解析失败，尝试从文本中提取（兼容各种格式）
                        extracted = self._extract_json_from_text(content)
                        if extracted is not None:
                            logger.info(
                                "llm_response_parsed_from_mixed_text",
                                provider=self.provider,
                                attempt=attempt + 1
                            )
                            return extracted

                        # 如果提取也失败，记录警告
                        logger.warning(
                            "llm_json_parse_failed",
                            attempt=attempt + 1,
                            error=str(e),
                            provider=self.provider,
                            raw_preview=content[:400],
                            raw_length=len(content) if isinstance(content, str) else None,
                        )

                        # 抽取失败则继续走重试/抛错逻辑
                        raise

            except httpx.HTTPStatusError as e:
                status_code = e.response.status_code

                # 安全地提取响应文本
                response_text = await self._extract_response_text(e.response)

                # 检查是否是429速率限制错误
                is_rate_limit = status_code == 429 or (
                    status_code == 400 and
                    "rate limit" in response_text.lower()
                )

                if is_rate_limit and attempt < max_retries - 1:
                    # 指数退避：2秒、4秒、8秒
                    wait_time = min(2 ** attempt, 60)
                    logger.warning(
                        "llm_json_rate_limit_detected",
                        status_code=status_code,
                        attempt=attempt + 1,
                        max_retries=max_retries,
                        wait_seconds=wait_time,
                        response_text=response_text[:200]
                    )
                    await asyncio.sleep(wait_time)
                    continue
                else:
                    # 非429错误或已达最大重试次数
                    logger.error(
                        "llm_json_http_error",
                        status_code=status_code,
                        response_text=response_text[:500],
                        attempt=attempt + 1,
                        error=str(e)
                    )
                    if attempt == max_retries - 1:
                        raise
            except Exception as e:
                logger.error(
                    "llm_request_failed",
                    attempt=attempt + 1,
                    error=str(e)
                )
                if attempt == max_retries - 1:
                    raise

        raise Exception(f"LLM调用失败，已重试{max_retries}次")

    async def _call_anthropic_with_json_response(
        self,
        prompt: str,
        max_retries: int = 2,
    ) -> Dict[str, Any]:
        """Call an Anthropic-compatible endpoint and parse a JSON object response."""
        last_error: Optional[Exception] = None

        for attempt in range(max_retries):
            try:
                response = await self.chat_anthropic(
                    messages=[{"role": "user", "content": prompt}],
                    temperature=self.temperature,
                )
                content = self._extract_text_from_anthropic_content(response.get("content", []))
                result = self._parse_json_response_content(content)
                logger.info(
                    "llm_response_parsed",
                    provider=self.provider,
                    model=self.model,
                    attempt=attempt + 1,
                    api_format="anthropic",
                )
                return result
            except json.JSONDecodeError as e:
                last_error = e
                logger.warning(
                    "llm_json_parse_failed",
                    attempt=attempt + 1,
                    error=str(e),
                    provider=self.provider,
                    api_format="anthropic",
                )
                if attempt == max_retries - 1:
                    raise
            except Exception as e:
                last_error = e
                logger.error(
                    "llm_request_failed",
                    attempt=attempt + 1,
                    error=str(e),
                    provider=self.provider,
                    api_format="anthropic",
                )
                if attempt == max_retries - 1:
                    raise

        raise Exception(f"LLM调用失败，已重试{max_retries}次") from last_error

    def _extract_text_from_anthropic_content(self, content_blocks: Any) -> str:
        """Extract text from Anthropic SDK content blocks."""
        texts: List[str] = []
        for block in content_blocks or []:
            block_type = getattr(block, "type", None)
            if block_type == "text" and hasattr(block, "text"):
                texts.append(block.text)
            elif isinstance(block, dict) and block.get("type") == "text":
                texts.append(str(block.get("text", "")))
        return "\n".join(text for text in texts if text)

    def _parse_json_response_content(self, content: str) -> Dict[str, Any]:
        if not content or not isinstance(content, str):
            raise json.JSONDecodeError("empty LLM response", content or "", 0)

        if "```json" in content or "```" in content:
            extracted = self._extract_json_from_text(content)
            if extracted is not None:
                return extracted

        try:
            return json.loads(content)
        except json.JSONDecodeError:
            extracted = self._extract_json_from_text(content)
            if extracted is not None:
                return extracted
            raise

    def _extract_json_from_text(self, content: str) -> Optional[Dict[str, Any]]:
        """
        从可能包含 ```json 代码块或前后说明文字的文本中提取 JSON。
        主要用于兼容 mimo/minimax 等返回格式。
        """
        if not content or not isinstance(content, str):
            return None

        text = content.strip()

        # 1) 去掉 ``` 开头/结尾的代码块包装
        if text.startswith("```"):
            lines = text.splitlines()
            # 去掉第一行 ```json / ``` 等
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            # 去掉结尾的 ``` 行
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            text = "\n".join(lines).strip()

        # 2) 在文本中查找第一个 '{' 和最后一个 '}'，尝试截取为 JSON
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return None

        candidate = text[start : end + 1]
        try:
            return json.loads(candidate)
        except Exception:
            return None

    def _extract_json_from_thinking_response(self, content: str) -> str:
        """
        MiniMax常返回"<think>…</think>{...}"结构，这里统一剥离前置思维链。
        """
        if not content:
            return content

        unescaped = html.unescape(content.strip())
        lowered = unescaped.lower()

        for tag in ("think", "thinking"):
            open_tag = f"<{tag}"
            close_tag = f"</{tag}>"

            if lowered.startswith(open_tag):
                end_idx = lowered.find(close_tag)
                if end_idx != -1:
                    after = unescaped[end_idx + len(close_tag):].lstrip()
                    return after if after else unescaped

        return content

    def clean_thinking_tags(self, content: str) -> str:
        """
        清理带思维链/思考标签的响应，保持与历史代码兼容。

        - 对 MiniMax / Mimo：剥离 <think>...</think> 或类似结构
        - 其他 provider：原样返回
        """
        if not content:
            return content

        if self.provider in {"minimax", "mimo"}:
            return self._extract_json_from_thinking_response(content)

        return content

    async def call_llm_with_messages(
        self,
        messages: list,
        temperature: float = None,
        max_retries: int = 2
    ) -> Dict[str, Any]:
        """
        调用LLM并解析JSON响应（支持完整的messages列表，包括system message）

        Args:
            messages: 完整的消息列表 [{"role": "system"|"user"|"assistant", "content": "..."}]
            temperature: 温度参数
            max_retries: 最大重试次数

        Returns:
            解析后的JSON响应（Dict格式）
        """
        # 如果未指定temperature，使用settings中的默认值
        if temperature is None:
            temperature = self.temperature

        import httpx

        url, headers = self._get_request_config()

        # 调试日志
        try:
            total_chars = sum(len(str(m.get("content", ""))) for m in messages)
            logger.info(
                "llm_messages_request_debug",
                provider=self.provider,
                model=self.model,
                message_count=len(messages),
                total_chars=total_chars
            )
        except Exception as e:
            logger.warning("llm_messages_request_debug_failed", error=str(e))

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature
        }

        # Mimo特殊处理：禁用思考模式
        if self.provider == "mimo":
            payload["thinking"] = {"type": "disabled"}

        for attempt in range(max_retries):
            try:
                async with httpx.AsyncClient(timeout=60.0) as client:
                    response = await client.post(url, headers=headers, json=payload)
                    response.raise_for_status()
                    data = response.json()

                    # 提取响应内容
                    content = data.get("choices", [{}])[0].get("message", {}).get("content", "")

                    if self.provider == "minimax":
                        content = self._extract_json_from_thinking_response(content)

                    # 调试日志：显示原始输出
                    logger.info(
                        "llm_messages_raw_response",
                        provider=self.provider,
                        content_length=len(content) if content else 0,
                        content_preview=repr(content)[:200] if content else ""
                    )

                    # 尝试解析JSON
                    if "```json" in content or "```" in content:
                        extracted = self._extract_json_from_text(content)
                        if extracted is not None:
                            logger.info(
                                "llm_messages_response_parsed_from_mixed",
                                provider=self.provider,
                                attempt=attempt + 1
                            )
                            return {
                                "success": True,
                                "data": extracted,
                                "raw_content": content
                            }

                    try:
                        result = json.loads(content)
                        logger.info(
                            "llm_messages_response_parsed",
                            provider=self.provider,
                            attempt=attempt + 1
                        )
                        # 返回包含原始内容的 dict
                        return {
                            "success": True,
                            "data": result,
                            "raw_content": content
                        }
                    except json.JSONDecodeError as e:
                        extracted = self._extract_json_from_text(content)
                        if extracted is not None:
                            logger.info(
                                "llm_messages_response_parsed_from_mixed",
                                provider=self.provider,
                                attempt=attempt + 1
                            )
                            return {
                                "success": True,
                                "data": extracted,
                                "raw_content": content
                            }

                        logger.warning(
                            "llm_messages_response_parse_failed",
                            provider=self.provider,
                            attempt=attempt + 1,
                            error=str(e),
                            content_preview=repr(content)[:200]
                        )

                        # 如果还有重试机会，等待后重试
                        if attempt < max_retries - 1:
                            await asyncio.sleep(1 * (attempt + 1))
                            continue

                        # 所有重试都失败，返回包含错误的结构化响应
                        return {
                            "success": False,
                            "error": f"Failed to parse JSON after {max_retries} attempts: {e}",
                            "raw_content": content
                        }

            except httpx.HTTPStatusError as e:
                status_code = e.response.status_code

                # 安全地提取响应文本
                response_text = await self._extract_response_text(e.response)

                # 检查是否是429速率限制错误
                is_rate_limit = status_code == 429 or (
                    status_code == 400 and
                    "rate limit" in response_text.lower()
                )

                logger.error(
                    "llm_messages_http_error",
                    provider=self.provider,
                    status_code=status_code,
                    response_text=response_text[:500],
                    error=str(e),
                    is_rate_limit=is_rate_limit
                )

                if attempt < max_retries - 1:
                    # 指数退避：2秒、4秒、8秒（针对429），其他错误1秒、2秒、3秒
                    wait_time = min(2 ** attempt, 60) if is_rate_limit else (attempt + 1)
                    logger.warning(
                        "llm_messages_retry",
                        attempt=attempt + 1,
                        max_retries=max_retries,
                        wait_seconds=wait_time,
                        is_rate_limit=is_rate_limit
                    )
                    await asyncio.sleep(wait_time)
                    continue

                return {
                    "success": False,
                    "error": f"HTTP error: {status_code}",
                    "raw_content": ""
                }
            except Exception as e:
                logger.error(
                    "llm_messages_request_failed",
                    provider=self.provider,
                    error=str(e)
                )
                if attempt < max_retries - 1:
                    await asyncio.sleep(1 * (attempt + 1))
                    continue
                return {
                    "success": False,
                    "error": str(e),
                    "raw_content": ""
                }


    @staticmethod
    def _is_context_overflow_error(error: Exception) -> bool:
        """判断是否是上下文过长错误（各 Provider 错误格式不统一）

        各 Provider 的上下文溢出错误特征：
        - OpenAI/DeepSeek: "maximum context length" / "token limit exceeded"
        - Anthropic: "prompt is too long"
        - MIMO/火山: "context length exceeded" / "token limit"
        - 智谱 GLM: "maximum context length"

        Args:
            error: 异常对象

        Returns:
            True 如果是上下文过长错误
        """
        error_msg = str(error).lower()
        keywords = [
            "prompt is too long",
            "maximum context length",
            "token limit",
            "context length exceeded",
            "tokens exceeds",
            "too many tokens",
            "request too large",
            "max_tokens",
            "context_window",
        ]
        return any(kw in error_msg for kw in keywords)

    def _add_cache_control(self, api_params: Dict[str, Any]) -> Dict[str, Any]:
        """为支持 Prompt Cache 的 Provider 添加 cache_control 标记

        根据 Anthropic Prompt Cache 规范：
        - system 消息：标记为可缓存
        - tools 定义：标记为可缓存
        - 历史消息中的早期部分：标记为可缓存（保留最近 2 轮不标记）

        Args:
            api_params: Anthropic API 调用参数

        Returns:
            添加 cache_control 后的参数副本
        """
        import copy
        params = copy.deepcopy(api_params)

        # 1. 标记 system 消息为可缓存
        # 注意：只在 system 已经是列表格式时添加 cache_control
        # 字符串格式保持不变，避免 API 兼容性问题
        if "system" in params and params["system"]:
            system = params["system"]
            if isinstance(system, list) and len(system) > 0:
                # 列表格式：标记最后一个 block
                if isinstance(system[-1], dict):
                    system[-1]["cache_control"] = {"type": "ephemeral"}
                    logger.debug("cache_control_added_to_system_list")
            # 字符串格式不转换，保持原样

        # 2. 标记 tools 定义为可缓存
        if "tools" in params and params["tools"]:
            tools = params["tools"]
            if isinstance(tools, list) and len(tools) > 0:
                # 标记最后一个工具定义
                if isinstance(tools[-1], dict):
                    tools[-1]["cache_control"] = {"type": "ephemeral"}
                    logger.debug("cache_control_added_to_tools")

        # 3. 标记历史消息中的早期部分（保留最近 2 轮不标记）
        if "messages" in params and params["messages"]:
            messages = params["messages"]
            protected_turns = 2  # 保留最近 2 轮不标记

            # 计算需要标记的消息索引（排除最近 2 轮）
            # 一轮 = 1 条 user + 1 条 assistant
            messages_to_mark = len(messages) - (protected_turns * 2)

            # 确保 messages_to_mark 为正数且索引有效
            if messages_to_mark > 0 and (messages_to_mark - 1) < len(messages):
                # 标记可压缩部分的最后一条消息
                if isinstance(messages[messages_to_mark - 1], dict):
                    messages[messages_to_mark - 1]["cache_control"] = {"type": "ephemeral"}
                    logger.debug("cache_control_added_to_message", index=messages_to_mark - 1)

        logger.debug(
            "cache_control_added",
            has_system="system" in params,
            has_tools=bool(params.get("tools")),
            messages_count=len(params.get("messages", []))
        )

        return params

    def _build_chat_completions_payload(
        self,
        *,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]],
        max_tokens: Optional[int],
        temperature: float,
        system: Optional[str],
        stream: bool,
        tool_choice: Optional[Any] = None,
    ) -> Dict[str, Any]:
        converted_tools = convert_anthropic_tools_to_chat(tools)
        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": convert_anthropic_messages_to_chat(
                messages,
                system=system,
            ),
            "temperature": temperature,
        }
        payload["stream"] = stream
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        if converted_tools:
            payload["tools"] = converted_tools
            payload["tool_choice"] = tool_choice or "auto"
        if self.provider == "deepseek":
            payload["enable_thinking"] = False
            if stream:
                payload["stream_options"] = {"include_usage": True}
        return payload

    @staticmethod
    def _named_tool_choice(tool_name: str) -> Dict[str, Any]:
        return {"type": "function", "function": {"name": tool_name}}

    async def _chat_completions_create(
        self,
        *,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]],
        max_tokens: Optional[int],
        temperature: float,
        system: Optional[str],
    ) -> Dict[str, Any]:
        url, headers = self._get_request_config()
        payload = self._build_chat_completions_payload(
            messages=messages,
            tools=tools,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system,
            stream=False,
        )
        logger.info(
            "llm_chat_completions_request",
            provider=self.provider,
            model=self.model,
            api_mode=self.api_mode,
            messages_count=len(payload["messages"]),
            has_tools=bool(payload.get("tools")),
        )
        timeout = float(getattr(settings, "llm_request_timeout_seconds", 180.0) or 180.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            raw_response = response.json()
            try:
                return convert_chat_response_to_anthropic(raw_response)
            except ToolCallArgumentsError as exc:
                if not tools or not exc.tool_name:
                    raise
                retry_payload = self._build_chat_completions_payload(
                    messages=messages,
                    tools=tools,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    system=system,
                    stream=False,
                    tool_choice=self._named_tool_choice(exc.tool_name),
                )
                logger.warning(
                    "llm_chat_completions_tool_arguments_retry",
                    provider=self.provider,
                    model=self.model,
                    tool_name=exc.tool_name,
                    tool_call_id=exc.tool_call_id,
                )
                retry_response = await client.post(url, headers=headers, json=retry_payload)
                retry_response.raise_for_status()
        return convert_chat_response_to_anthropic(retry_response.json())

    async def _chat_completions_stream(
        self,
        *,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]],
        max_tokens: Optional[int],
        temperature: float,
        system: Optional[str],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        url, headers = self._get_request_config()
        payload = self._build_chat_completions_payload(
            messages=messages,
            tools=tools,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system,
            stream=True,
        )
        logger.info(
            "llm_chat_completions_streaming_request",
            provider=self.provider,
            model=self.model,
            api_mode=self.api_mode,
            messages_count=len(payload["messages"]),
            has_tools=bool(payload.get("tools")),
        )
        adapter = ChatCompletionsStreamAdapter(model=self.model)
        timeout = float(getattr(settings, "llm_request_timeout_seconds", 180.0) or 180.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream("POST", url, headers=headers, json=payload) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line or not line.startswith("data: "):
                        continue
                    data = line[len("data: "):].strip()
                    if data == "[DONE]":
                        break
                    chunk = json.loads(data)
                    for event in adapter.feed_chunk(chunk):
                        yield event
        for event in adapter.finish():
            yield event

    async def chat_anthropic(
        self,
        messages: List[Dict[str, str]],
        tools: Optional[List[Dict]] = None,
        max_tokens: Optional[int] = None,
        temperature: float = 0.3,
        system: Optional[str] = None,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        auto_profile: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Anthropic 格式聊天，支持原生工具调用

        使用 Anthropic 的 Messages API，支持原生工具调用（tool_use blocks）。

        Args:
            messages: 消息列表 [{"role": "user", "content": "..."}]
            tools: 工具列表（Anthropic 格式）
            max_tokens: 最大输出 token 数
            temperature: 温度参数
            system: 系统提示词（Anthropic API 使用单独的 system 参数）

        Returns:
            {
                "content": List[ContentBlock],  # text 和 tool_use 块
                "model": str,
                "usage": {...}
            }
        """
        override_service = self._create_provider_override_service(provider, model)
        if override_service is not None:
            try:
                return await override_service.chat_anthropic(
                    messages=messages,
                    tools=tools,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    system=system,
                )
            finally:
                self._schedule_provider_override_service_close(override_service)

        if auto_profile:
            with self.use_auto_profile(auto_profile):
                return await self.chat_anthropic(
                    messages=messages,
                    tools=tools,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    system=system,
                )

        try:
            if self.api_mode == "chat_completions":
                return await self._run_anthropic_with_fallback(
                    "chat_completions_chat",
                    lambda: self._chat_completions_create(
                        messages=messages,
                        tools=tools,
                        max_tokens=max_tokens,
                        temperature=temperature,
                        system=system,
                    ),
                )

            if not self.anthropic_client:
                raise RuntimeError(
                    "Anthropic client not initialized. "
                    f"Provider '{self.provider}' requires {self.provider.upper()}_BASE_URL environment variable."
                )

            async def create_message():
                if not self.anthropic_client:
                    raise RuntimeError(
                        f"Anthropic-compatible client not initialized for provider '{self.provider}'."
                    )
                api_params = self._build_anthropic_api_params(
                    messages=messages,
                    tools=tools,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    system=system,
                    streaming=False,
                )
                logger.info(
                    "llm_anthropic_chat_request",
                    provider=self.provider,
                    model=self.model,
                    messages_count=len(api_params.get("messages", [])),
                    has_tools=bool(api_params.get("tools")),
                )
                return await self.anthropic_client.messages.create(**api_params)

            response = await self._run_anthropic_with_fallback(
                "anthropic_chat",
                create_message,
            )

            # 提取响应数据
            result = {
                "content": response.content,
                "model": response.model,
                "usage": {
                    "input_tokens": response.usage.input_tokens,
                    "output_tokens": response.usage.output_tokens
                },
                "stop_reason": response.stop_reason
            }

            # 打印响应内容
            logger.info("========== LLM响应开始 ==========")
            logger.info(
                "【响应元数据】",
                model=result["model"],
                input_tokens=result["usage"]["input_tokens"],
                output_tokens=result["usage"]["output_tokens"],
                stop_reason=result["stop_reason"]
            )

            # 打印content blocks
            logger.info(f"【响应内容】共 {len(result['content'])} 个blocks")
            for i, block in enumerate(result["content"]):
                if hasattr(block, 'type'):
                    block_type = block.type

                    if block_type == "text":
                        text_preview = block.text[:500] + "..." if len(block.text) > 500 else block.text
                        logger.info(f"  Block {i+1}: type=text", preview=text_preview)
                    elif block_type == "tool_use":
                        logger.info(
                            f"  Block {i+1}: type=tool_use",
                            name=block.name,
                            input=str(block.input)[:300] + "..." if len(str(block.input)) > 300 else str(block.input)
                        )
                    elif block_type == "thinking":
                        thinking_preview = block.thinking[:500] + "..." if len(block.thinking) > 500 else block.thinking
                        logger.info(f"  Block {i+1}: type=thinking", preview=thinking_preview)
                    else:
                        logger.info(f"  Block {i+1}: type={block_type}")

            logger.info("========== LLM响应结束 ==========")

            logger.info(
                "llm_anthropic_chat_success",
                model=result["model"],
                input_tokens=result["usage"]["input_tokens"],
                output_tokens=result["usage"]["output_tokens"],
                stop_reason=result["stop_reason"],
                content_blocks=len(result["content"])
            )

            return result

        except Exception as e:
            # ✅ Reactive Compact：上下文溢出自动恢复
            # 捕获各 Provider 的上下文过长错误，触发压缩后重试
            if self._is_context_overflow_error(e):
                logger.warning(
                    "context_overflow_detected",
                    provider=self.provider,
                    model=self.model,
                    error=str(e)[:200],
                    action="triggering_reactive_compact"
                )
                # 防止无限重试循环
                if not getattr(self, '_reactive_compact_attempted', False):
                    self._reactive_compact_attempted = True
                    try:
                        # 触发上下文压缩
                        from app.agent.memory.context_compressor import ContextCompressor
                        compressor = ContextCompressor(self)
                        compressed_messages = await compressor.compress_messages(messages)

                        logger.info(
                            "reactive_compact_completed",
                            original_count=len(messages),
                            compressed_count=len(compressed_messages)
                        )

                        # 重试请求
                        result = await self.chat_anthropic(
                            messages=compressed_messages,
                            tools=tools,
                            max_tokens=max_tokens,
                            temperature=temperature,
                            system=system,
                        )
                        return result
                    finally:
                        self._reactive_compact_attempted = False

            logger.error(
                "llm_anthropic_chat_failed",
                provider=self.provider,
                error=str(e),
                error_type=type(e).__name__
            )
            raise

    async def chat_anthropic_streaming(
        self,
        messages: List[Dict[str, str]],
        tools: Optional[List[Dict]] = None,
        max_tokens: Optional[int] = None,
        temperature: float = 0.3,
        system: Optional[str] = None,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        auto_profile: Optional[str] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Anthropic 格式流式聊天，支持原生工具调用

        使用 Anthropic 的 Messages API 流式模式，按事件类型逐步 yield。
        参考 Claude Code 的 QueryEngine 事件序列：
        message_start -> content_block_start -> content_block_delta -> content_block_stop
        -> message_delta -> message_stop

        Yields:
            流式事件字典，类型包括：
            - {"type": "message_start", "data": {"usage": {...}}}
            - {"type": "content_block_start", "data": {"index": int, "block": ContentBlock}}
            - {"type": "content_block_delta", "data": {"index": int, "delta": ...}}
            - {"type": "content_block_stop", "data": {"index": int}}
            - {"type": "message_delta", "data": {"stop_reason": str, "usage": {...}}}
            - {"type": "message_stop", "data": {}}
        """
        override_service = self._create_provider_override_service(provider, model)
        if override_service is not None:
            try:
                async for event in override_service.chat_anthropic_streaming(
                    messages=messages,
                    tools=tools,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    system=system,
                ):
                    yield event
            finally:
                self._schedule_provider_override_service_close(override_service)
            return

        if auto_profile:
            with self.use_auto_profile(auto_profile):
                async for event in self.chat_anthropic_streaming(
                    messages=messages,
                    tools=tools,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    system=system,
                ):
                    yield event
            return

        if self.api_mode != "chat_completions" and not self.anthropic_client:
            raise RuntimeError(
                "Anthropic client not initialized. "
                f"Provider '{self.provider}' requires {self.provider.upper()}_BASE_URL environment variable."
            )

        # 追踪首token时间（TTFT - Time to First Token）
        first_token_received = False
        import time
        start_time = time.time()

        original_state = self._snapshot_provider_state()
        candidates = parse_fallback_candidates(
            original_state["provider"],
            original_state["model"],
            self.request_fallbacks,
        )
        attempts = []

        try:
            for index, candidate in enumerate(candidates, start=1):
                if not (
                    candidate.provider == original_state["provider"].lower()
                    and (candidate.model or original_state["model"]) == original_state["model"]
                ):
                    self._switch_provider_for_attempt(candidate.provider, candidate.model)

                cooldown_failure = get_cooldown_failure(self.provider)
                if cooldown_failure and index < len(candidates):
                    attempts.append({
                        "provider": self.provider,
                        "model": self.model,
                        "reason": cooldown_failure.reason,
                        "status": cooldown_failure.status,
                        "code": cooldown_failure.code,
                        "error": "provider is in cooldown",
                    })
                    logger.warning(
                        "llm_streaming_fallback_candidate_skipped_cooldown",
                        provider=self.provider,
                        model=self.model,
                        reason=cooldown_failure.reason,
                    )
                    continue

                try:
                    candidate_emitted = False
                    if self.api_mode == "chat_completions":
                        semaphore = get_llm_pool_semaphore(self.provider, self.model)
                        async with semaphore:
                            async for event in self._chat_completions_stream(
                                messages=messages,
                                tools=tools,
                                max_tokens=max_tokens,
                                temperature=temperature,
                                system=system,
                            ):
                                candidate_emitted = True
                                yield event
                        if attempts:
                            logger.warning(
                                "llm_streaming_fallback_candidate_succeeded",
                                provider=self.provider,
                                model=self.model,
                                attempts=summarize_attempts(attempts),
                            )
                        return

                    if not self.anthropic_client:
                        raise RuntimeError(
                            f"Anthropic-compatible client not initialized for provider '{self.provider}'."
                        )
                    api_params = self._build_anthropic_api_params(
                        messages=messages,
                        tools=tools,
                        max_tokens=max_tokens,
                        temperature=temperature,
                        system=system,
                        streaming=True,
                    )
                    logger.info(
                        "llm_anthropic_streaming_request",
                        provider=self.provider,
                        model=self.model,
                        messages_count=len(api_params.get("messages", [])),
                        has_tools=bool(api_params.get("tools")),
                    )
                    semaphore = get_llm_pool_semaphore(self.provider, self.model)
                    pool_wait_started = time.monotonic()
                    logger.info(
                        "llm_pool_concurrency_waiting",
                        provider=self.provider,
                        model=self.model,
                        operation="anthropic_stream",
                    )
                    async with semaphore:
                        logger.info(
                            "llm_pool_concurrency_acquired",
                            provider=self.provider,
                            model=self.model,
                            operation="anthropic_stream",
                            wait_ms=round((time.monotonic() - pool_wait_started) * 1000, 2),
                        )
                        async with self.anthropic_client.messages.stream(**api_params) as stream:
                            async for event in stream:
                                event_type = event.type

                                if event_type == "message_start":
                                    yield {
                                        "type": "message_start",
                                        "data": {
                                            "usage": {
                                                "input_tokens": event.message.usage.input_tokens,
                                                "output_tokens": event.message.usage.output_tokens,
                                            }
                                        }
                                    }

                                elif event_type == "content_block_start":
                                    yield {
                                        "type": "content_block_start",
                                        "data": {
                                            "index": event.index,
                                            "block": event.content_block,
                                        }
                                    }

                                elif event_type == "content_block_delta":
                                    # 记录首token时间
                                    if not first_token_received:
                                        first_token_received = True
                                        ttft = time.time() - start_time
                                        logger.info(
                                            "llm_first_token_received",
                                            provider=self.provider,
                                            model=self.model,
                                            ttft_seconds=round(ttft, 3),
                                        )

                                    yield {
                                        "type": "content_block_delta",
                                        "data": {
                                            "index": event.index,
                                            "delta": event.delta,
                                        }
                                    }

                                elif event_type == "content_block_stop":
                                    yield {
                                        "type": "content_block_stop",
                                        "data": {"index": event.index}
                                    }

                                elif event_type == "message_delta":
                                    yield {
                                        "type": "message_delta",
                                        "data": {
                                            "stop_reason": event.delta.stop_reason,
                                            "usage": {
                                                "output_tokens": event.usage.output_tokens,
                                            }
                                        }
                                    }

                                elif event_type == "message_stop":
                                    # 记录总时间
                                    total_time = time.time() - start_time

                                    # 打印流式响应总结
                                    logger.info("========== LLM流式响应完成 ==========")
                                    logger.info(
                                        "【流式响应总结】",
                                        provider=self.provider,
                                        model=self.model,
                                        total_seconds=round(total_time, 3),
                                        first_token_received=first_token_received,
                                        blocks_yielded=blocks_yielded if 'blocks_yielded' in locals() else 'N/A'
                                    )
                                    logger.info("========== LLM流式响应结束 ==========")

                                    logger.info(
                                        "llm_streaming_completed",
                                        provider=self.provider,
                                        model=self.model,
                                        total_seconds=round(total_time, 3),
                                        first_token_received=first_token_received,
                                    )
                                    yield {
                                        "type": "message_stop",
                                        "data": {}
                                    }
                    if attempts:
                        logger.warning(
                            "llm_streaming_fallback_candidate_succeeded",
                            provider=self.provider,
                            model=self.model,
                            attempts=summarize_attempts(attempts),
                        )
                    return
                except Exception as e:
                    # ✅ Reactive Compact：流式模式上下文溢出处理
                    # 注意：流式模式下无法直接重试（generator 已经开始产出）
                    # 只记录日志，调用方需要处理重试逻辑
                    if self._is_context_overflow_error(e):
                        logger.warning(
                            "context_overflow_detected_streaming",
                            provider=self.provider,
                            model=self.model,
                            error=str(e)[:200],
                            action="streaming_cannot_retry_in_generator"
                        )

                    failure = classify_llm_failure(e)
                    attempts.append({
                        "provider": self.provider,
                        "model": self.model,
                        "reason": failure.reason,
                        "status": failure.status,
                        "code": failure.code,
                        "error": failure.message,
                    })
                    if failure.reason == "context_overflow" or first_token_received or candidate_emitted:
                        logger.error(
                            "llm_anthropic_streaming_failed",
                            provider=self.provider,
                            error=str(e),
                            error_type=type(e).__name__,
                        )
                        raise
                    if should_fallback(failure):
                        mark_provider_cooldown(self.provider, failure)
                    has_next = index < len(candidates)
                    logger.warning(
                        "llm_streaming_fallback_candidate_failed",
                        provider=self.provider,
                        model=self.model,
                        reason=failure.reason,
                        status=failure.status,
                        code=failure.code,
                        has_next=has_next,
                        error=failure.message[:300],
                    )
                    if not has_next or not should_fallback(failure):
                        logger.error(
                            "llm_anthropic_streaming_failed",
                            provider=self.provider,
                            error=str(e),
                            error_type=type(e).__name__,
                        )
                        raise
            raise LLMFailoverError(summarize_attempts(attempts))
        finally:
            self._restore_provider_state(original_state)


# 全局LLM服务实例
llm_service = LLMService()
