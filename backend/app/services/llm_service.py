"""
LLM Service

提供LLM调用服务，支持JSON格式响应解析。
支持多种LLM provider: deepseek, minimax, openai, qwen
"""
import asyncio
import json
import html
import os
from typing import Dict, Any, Optional, Tuple
import structlog
from config.settings import settings

logger = structlog.get_logger()


class LLMService:
    """LLM服务类 - 支持多provider配置"""

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
        简单的聊天接口

        Args:
            messages: 消息列表，[{"role": "user", "content": "..."}]
            temperature: 温度参数
            timeout: 超时时间（秒），默认120秒
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
            messages_count=len(messages)
        )

        url, headers = self._get_request_config()

        # 调试日志：打印发送给 LLM 的消息长度与部分预览，避免整段内容过长刷屏
        try:
            total_chars = sum(len(str(m.get("content", ""))) for m in messages)
            logger.info(
                "llm_chat_request_debug",
                provider=self.provider,
                model=self.model,
                url=url,
                total_messages=len(messages),
                total_chars=total_chars,
                messages=messages,  # 不再截断，完整输出上下文
            )
        except Exception as e:
            # 调试日志失败不影响正常请求
            logger.warning("llm_chat_request_debug_failed", error=str(e))

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature
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
            max_tokens=payload.get("max_tokens")
        )

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(url, headers=headers, json=payload)
                response.raise_for_status()
                data = response.json()

                # 提取响应内容
                content = data.get("choices", [{}])[0].get("message", {}).get("content", "")

            # MiniMax可能返回thinking标签，需要处理
            if self.provider == "minimax":
                content = self._extract_json_from_thinking_response(content)

            return content

        except httpx.HTTPStatusError as e:
            logger.error(
                "llm_http_error",
                status_code=e.response.status_code,
                response_text=e.response.text[:500] if hasattr(e.response, 'text') else "N/A",
                url=url,
                provider=self.provider,
                model=self.model
            )
            raise
        except httpx.ConnectError as e:
            logger.error(
                "llm_connect_error",
                url=url,
                provider=self.provider,
                error=str(e)
            )
            raise
        except Exception as e:
            logger.error(
                "llm_chat_error",
                url=url,
                provider=self.provider,
                model=self.model,
                error_type=type(e).__name__,
                error=str(e)
            )
            raise

    async def chat_stream(
        self,
        messages: list,
        temperature: float = 0.7,
        timeout: float = 600.0,
        max_tokens: int = None,
    ) -> str:
        """
        使用 OpenAI 兼容的 stream 模式进行流式对话。
        当前主要用于长文本报告生成，避免长时间无响应导致 ReadTimeout，
        同时为后续前端流式展示预留接口。

        返回值：
            聚合后的完整文本内容（内部已把所有增量片段拼接起来）
        """
        import httpx

        url, headers = self._get_request_config()

        # 调试日志：不再打印完整 messages 内容，但会记录长度等信息
        try:
            total_chars = sum(len(str(m.get("content", ""))) for m in messages)
            logger.info(
                "llm_chat_stream_request_debug",
                provider=self.provider,
                model=self.model,
                total_messages=len(messages),
                total_chars=total_chars,
            )
        except Exception as e:
            logger.warning("llm_chat_stream_request_debug_failed", error=str(e))

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

        full_content = ""

        async with httpx.AsyncClient(timeout=timeout) as client:
            # 使用 HTTP 流式响应
            async with client.stream("POST", url, headers=headers, json=payload) as response:
                response.raise_for_status()

                async for line in response.aiter_lines():
                    if not line:
                        continue

                    # OpenAI / Qwen 兼容接口使用 "data: {...}" 和 "data: [DONE]" 形式
                    if line.startswith("data: "):
                        data_str = line[len("data: ") :].strip()
                        if data_str == "[DONE]":
                            break

                        try:
                            chunk = json.loads(data_str)
                        except Exception:
                            # 非法 JSON 片段直接跳过，避免中断整体生成
                            continue

                        # 兼容不同provider的流式返回格式，防御性解析 choices
                        choices = chunk.get("choices")
                        if not isinstance(choices, list) or not choices:
                            # 有些provider可能在部分片段不返回内容，仅返回控制信息，直接跳过即可
                            continue

                        first_choice = choices[0]
                        if not isinstance(first_choice, dict):
                            continue

                        # OpenAI / Qwen / Mimo 流式增量通常在 delta 中；
                        # 部分实现可能直接在 message 中返回完整内容，这里一并兼容。
                        delta = first_choice.get("delta") or first_choice.get("message") or {}

                        piece = delta.get("content") or ""
                        if piece:
                            full_content += piece

        # MiniMax 特殊格式兼容（理论上流式模式下不会用到）
        if self.provider == "minimax":
            full_content = self._extract_json_from_thinking_response(full_content)

        return full_content

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
                logger.error(
                    "llm_messages_http_error",
                    provider=self.provider,
                    status_code=e.response.status_code,
                    error=str(e)
                )
                if attempt < max_retries - 1:
                    await asyncio.sleep(1 * (attempt + 1))
                    continue
                return {
                    "success": False,
                    "error": f"HTTP error: {e.response.status_code}",
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
