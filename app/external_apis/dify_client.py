"""
Dify API Client

封装 Dify 工作流 API 调用
用于空气质量数据查询
"""
from typing import Dict, Any, Optional, AsyncGenerator
import httpx
import json
import structlog

logger = structlog.get_logger()


class DifyClient:
    """
    Dify API 客户端

    提供对 Dify 工作流 API 的封装，用于：
    - 空气质量数据查询（支持全国各城市）
    - 支持小时、日、月、年粒度
    """

    def __init__(self):
        self.base_url = "http://219.135.180.51:56037"
        self.api_key = "app-nlRAQE2NBII83XnPaK0ysKNw"
        self.timeout = 300  # Dify 工作流超时时间（5分钟）

    async def chat_messages(
        self,
        query: str,
        user: str = "air_quality_system",
        conversation_id: Optional[str] = None,
        response_mode: str = "blocking"
    ) -> Dict[str, Any]:
        """
        调用 Dify chat-messages API

        Args:
            query: 查询文本（自然语言，如"惠州昨日小时空气质量"）
            user: 用户标识
            conversation_id: 对话ID（可选，留空则创建新对话）
            response_mode: 响应模式（blocking 或 streaming）

        Returns:
            Dict: API 响应数据

        Raises:
            Exception: API 调用失败
        """
        url = f"{self.base_url}/v1/chat-messages"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }

        data = {
            "inputs": {},
            "query": query,
            "response_mode": response_mode,
            "conversation_id": conversation_id or "",
            "user": user
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(url, headers=headers, json=data)

                if response.status_code == 200:
                    result = response.json()
                    logger.debug(
                        "dify_api_success",
                        query=query,
                        conversation_id=result.get("conversation_id")
                    )
                    return result
                else:
                    raise Exception(
                        f"Dify API error: {response.status_code} - {response.text}"
                    )

        except httpx.TimeoutException:
            logger.error("dify_api_timeout", query=query)
            raise Exception("Dify API timeout")
        except Exception as e:
            logger.error("dify_api_failed", query=query, error=str(e))
            raise

    async def chat_messages_streaming(
        self,
        query: str,
        user: str = "air_quality_system",
        conversation_id: Optional[str] = None
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        调用 Dify chat-messages API (流式响应)

        Args:
            query: 查询文本
            user: 用户标识
            conversation_id: 对话ID

        Yields:
            Dict: 流式响应的每个数据块

        Raises:
            Exception: API 调用失败
        """
        url = f"{self.base_url}/v1/chat-messages"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }

        data = {
            "inputs": {},
            "query": query,
            "response_mode": "streaming",
            "conversation_id": conversation_id or "",
            "user": user
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                async with client.stream("POST", url, headers=headers, json=data) as response:
                    if response.status_code != 200:
                        error_text = await response.aread()
                        raise Exception(
                            f"Dify API error: {response.status_code} - {error_text.decode()}"
                        )

                    async for line in response.aiter_lines():
                        if line.startswith("data: "):
                            data_str = line[6:]  # 移除 "data: " 前缀
                            if data_str.strip():
                                try:
                                    yield json.loads(data_str)
                                except json.JSONDecodeError:
                                    logger.warning("dify_stream_parse_error", line=line)

        except httpx.TimeoutException:
            logger.error("dify_streaming_timeout", query=query)
            raise Exception("Dify streaming API timeout")
        except Exception as e:
            logger.error("dify_streaming_failed", query=query, error=str(e))
            raise

    def build_air_quality_query(
        self,
        city: str,
        time_range: str = "昨日",
        granularity: str = "小时"
    ) -> str:
        """
        构建空气质量查询语句

        Args:
            city: 城市名称（如"惠州"、"广州"）
            time_range: 时间范围（如"昨日"、"今日"、"本月"、"去年"）
            granularity: 数据粒度（"小时"、"日"、"月"、"年"）

        Returns:
            str: 自然语言查询文本
        """
        return f"{city}{time_range}{granularity}空气质量"
