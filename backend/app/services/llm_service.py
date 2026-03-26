"""
LLM Service

提供LLM调用服务，支持JSON格式响应解析。
支持多种LLM provider: deepseek, minimax, openai, qwen
"""
import asyncio
import json
import html
import os
from typing import Dict, Any, Optional, Tuple, AsyncGenerator
import structlog
from config.settings import settings
import httpx
from app.utils.llm_context_logger import get_llm_context_logger

logger = structlog.get_logger()


class LLMService:
    """LLM服务类 - 支持多provider配置"""

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
                piece = delta.get("content") or ""

                if piece:
                    yielded_chunks += 1
                    total_content_length += len(piece)
                    yield piece
                else:
                    skipped_empty_content += 1
                    # 空内容不记录（可能很频繁）

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
                piece = delta.get("content") or ""

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

                # 检查是否是429速率限制错误
                is_rate_limit = status_code == 429 or (
                    status_code == 400 and
                    "rate limit" in e.response.text.lower()
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
                        response_text=e.response.text[:200] if hasattr(e.response, 'text') else "N/A"
                    )
                    await asyncio.sleep(wait_time)
                    continue
                else:
                    # 非429错误或已达最大重试次数，直接抛出
                    logger.error(
                        "llm_http_error",
                        status_code=status_code,
                        response_text=e.response.text[:500] if hasattr(e.response, 'text') else "N/A",
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
        "minimax": {
            "url_env": "MINIMAX_BASE_URL",
            "url_default": "https://api.minimax.chat/v1",
            "key_env": "MINIMAX_API_KEY",
            "model_env": "MINIMAX_MODEL",
            "model_default": "minimax-m2",
        },
        "openai": {
            "url_env": "OPENAI_BASE_URL",
            "url_default": "https://api.openai.com/v1",
            "key_env": "OPENAI_API_KEY",
            "model_env": "OPENAI_MODEL",
            "model_default": "gpt-4-turbo-preview",
        },
        # Xiaomi Mimo，与 Agent 保持一致（OpenAI 兼容协议）
        "mimo": {
            "url_env": "MIMO_BASE_URL",
            "url_default": "https://api.xiaomimimo.com/v1",
            "key_env": "MIMO_API_KEY",
            "model_env": "MIMO_MODEL",
            "model_default": "mimo-v2-flash",
        },
        # 千问3本地部署（OpenAI 兼容协议）
        "qwen": {
            "url_env": "QWEN_BASE_URL",
            "url_default": "http://172.16.9.87:8000/v1",
            "key_env": "QWEN_API_KEY",
            "model_env": "QWEN_MODEL",
            "model_default": "/qwen/Qwen3-30B-A3B-Instruct-2507-AWQ/",
        },
    }

    def __init__(self):
        # 优先使用 settings 中的配置，确保与 .env 文件一致
        self.provider = settings.llm_provider.lower()
        
        # 调试信息：检查配置是否正确
        logger.debug(
            "llm_provider_config_check",
            provider_from_settings=self.provider,
            qwen_base_url=settings.qwen_base_url,
            qwen_model=settings.qwen_model
        )
        
        self._load_provider_config()
        
        logger.info(
            "llm_service_initialized",
            provider=self.provider,
            model=self.model,
            base_url=self.base_url
        )

    def _load_provider_config(self):
        """根据provider加载对应配置"""
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
        if self.provider == "qwen":
            self.base_url = settings.qwen_base_url
            self.api_key = settings.qwen_api_key or ""
            self.model = settings.qwen_model
            # 🔍 调试日志：检查 settings 值
            logger.debug(
                "llm_qwen_config_from_settings",
                base_url=self.base_url,
                model=self.model,
                has_api_key=bool(self.api_key)
            )
            # 回退到环境变量
            if not self.base_url:
                self.base_url = os.getenv(config["url_env"], config["url_default"])
                logger.debug("llm_qwen_base_url_fallback_to_env", base_url=self.base_url)
            if not self.model:
                self.model = os.getenv(config["model_env"], config["model_default"])
                logger.debug("llm_qwen_model_fallback_to_env", model=self.model)

        elif self.provider == "deepseek":
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

        elif self.provider == "minimax":
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

        else:
            # 回退到环境变量
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
            has_api_key=bool(self.api_key)
        )

        if not self.api_key and self.provider not in ["qwen"]:  # qwen 本地部署通常不需要 API key
            logger.warning("llm_api_key_not_configured", provider=self.provider)

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

        url = f"{self.base_url}/chat/completions"

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
        temperature: float = 0.7,
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

        # 千问3特殊处理：禁用思考模式
        if self.provider == "qwen":
            payload["enable_thinking"] = False

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

                # 检查是否是429速率限制错误
                is_rate_limit = status_code == 429 or (
                    status_code == 400 and
                    "rate limit" in e.response.text.lower()
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
                        response_text=e.response.text[:200] if hasattr(e.response, 'text') else "N/A"
                    )
                    await asyncio.sleep(wait_time)
                    continue
                else:
                    # 非429错误或已达最大重试次数，直接抛出
                    logger.error(
                        "llm_http_error",
                        status_code=status_code,
                        response_text=e.response.text[:500] if hasattr(e.response, 'text') else "N/A",
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
        temperature: float = 0.7,
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
        url, headers = self._get_request_config()

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "stream": True,
        }

        # 千问3特殊处理：禁用思考模式
        if self.provider == "qwen":
            payload["enable_thinking"] = False

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

                # 检查是否是429速率限制错误
                is_rate_limit = status_code == 429 or (
                    status_code == 400 and
                    "rate limit" in e.response.text.lower()
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
                    )
                    await asyncio.sleep(wait_time)
                    continue
                else:
                    logger.error(
                        "llm_streaming_http_error",
                        status_code=status_code,
                        attempt=attempt + 1,
                        max_retries=max_retries
                    )
                    raise

        # 理论上不会到达这里
        raise last_error

    async def chat_streaming_with_status(
        self,
        messages: list,
        temperature: float = 0.7,
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
        url, headers = self._get_request_config()

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "stream": True,
        }

        # 千问3特殊处理：禁用思考模式
        if self.provider == "qwen":
            payload["enable_thinking"] = False

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

                # 检查是否是429速率限制错误
                is_rate_limit = status_code == 429 or (
                    status_code == 400 and
                    "rate limit" in e.response.text.lower()
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
                    )
                    await asyncio.sleep(wait_time)
                    continue
                else:
                    logger.error(
                        "llm_streaming_with_status_http_error",
                        status_code=status_code,
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
        import httpx

        url, headers = self._get_request_config()

        # 调试日志：打印 JSON 调用的 prompt 长度与部分内容
        try:
            logger.info(
                "llm_json_request_debug",
                provider=self.provider,
                model=self.model,
                prompt_length=len(prompt),
                prompt_full=str(prompt),  # 不再截断，输出完整上下文
            )
        except Exception as e:
            logger.warning("llm_json_request_debug_failed", error=str(e))

        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "temperature": 0.1
        }

        # 千问3特殊处理：禁用思考模式
        if self.provider == "qwen":
            payload["enable_thinking"] = False

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

                # 检查是否是429速率限制错误
                is_rate_limit = status_code == 429 or (
                    status_code == 400 and
                    "rate limit" in e.response.text.lower()
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
                        response_text=e.response.text[:200] if hasattr(e.response, 'text') else "N/A"
                    )
                    await asyncio.sleep(wait_time)
                    continue
                else:
                    # 非429错误或已达最大重试次数
                    logger.error(
                        "llm_json_http_error",
                        status_code=status_code,
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
        temperature: float = 0.7,
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

        # 千问3特殊处理：禁用思考模式
        if self.provider == "qwen":
            payload["enable_thinking"] = False

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

                # 检查是否是429速率限制错误
                is_rate_limit = status_code == 429 or (
                    status_code == 400 and
                    "rate limit" in e.response.text.lower()
                )

                logger.error(
                    "llm_messages_http_error",
                    provider=self.provider,
                    status_code=status_code,
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


# 全局LLM服务实例
llm_service = LLMService()
