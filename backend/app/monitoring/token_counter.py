"""
Token 计数器

使用 tiktoken 计算 token 数量
"""

import tiktoken
from typing import List, Dict, Any, Optional
import structlog

logger = structlog.get_logger()


class TokenCounter:
    """Token 计数器 - 支持多种编码"""

    # 模型到编码的映射
    MODEL_ENCODINGS = {
        # GPT-4, GPT-3.5
        "gpt-4": "cl100k_base",
        "gpt-4-turbo": "cl100k_base",
        "gpt-4-turbo-preview": "cl100k_base",
        "gpt-3.5-turbo": "cl100k_base",
        # DeepSeek
        "deepseek-chat": "cl100k_base",
        "deepseek-reasoner": "cl100k_base",
        # MiniMax
        "minimax-m2": "cl100k_base",
        # Mimo
        "mimo-v2-flash": "cl100k_base",
        # Qwen (使用 cl100k_base 作为近似)
        "qwen3:30b": "cl100k_base",
        "/qwen/Qwen3-30B-A3B-Instruct-2507-AWQ/": "cl100k_base",
    }

    def __init__(self, model: str = "gpt-4"):
        """
        初始化 Token 计数器

        Args:
            model: 模型名称
        """
        self.model = model
        self.encoding_name = self._get_encoding_name(model)
        try:
            self.encoding = tiktoken.get_encoding(self.encoding_name)
        except Exception as e:
            logger.warning(
                "token_counter_encoding_failed",
                model=model,
                encoding=self.encoding_name,
                error=str(e)
            )
            # 回退到默认编码
            self.encoding = tiktoken.get_encoding("cl100k_base")
            self.encoding_name = "cl100k_base"

    def _get_encoding_name(self, model: str) -> str:
        """获取模型的编码名称"""
        # 检查完整匹配
        if model in self.MODEL_ENCODINGS:
            return self.MODEL_ENCODINGS[model]

        # 检查部分匹配
        for key, encoding in self.MODEL_ENCODINGS.items():
            if key in model or model in key:
                return encoding

        # 默认使用 cl100k_base
        return "cl100k_base"

    def count_tokens(self, text: str) -> int:
        """
        计算文本的 token 数量

        Args:
            text: 输入文本

        Returns:
            Token 数量
        """
        if not text:
            return 0
        try:
            return len(self.encoding.encode(str(text)))
        except Exception as e:
            logger.warning(
                "token_count_failed",
                error=str(e),
                text_preview=text[:100] if text else None
            )
            # 简单估算：平均每个字符 0.25 个 token
            return int(len(text) * 0.25)

    def count_messages(self, messages: List[Dict[str, Any]]) -> int:
        """
        计算消息列表的 token 数量

        Args:
            messages: 消息列表，格式：[{"role": "user", "content": "..."}]

        Returns:
            Token 数量
        """
        if not messages:
            return 0

        total = 0
        for message in messages:
            # 每个消息的格式开销（role + content 标记）
            total += 4
            # 计算 role 的 token
            if "role" in message:
                total += self.count_tokens(message["role"])
            # 计算 content 的 token
            if "content" in message:
                content = message["content"]
                if isinstance(content, str):
                    total += self.count_tokens(content)
                elif isinstance(content, list):
                    # 处理多模态内容
                    for item in content:
                        if isinstance(item, dict) and "text" in item:
                            total += self.count_tokens(item["text"])

        return total

    def count_prompt(self, prompt: str) -> int:
        """
        计算 prompt 的 token 数量（用于 completions API）

        Args:
            prompt: 输入 prompt

        Returns:
            Token 数量
        """
        return self.count_tokens(prompt)

    def estimate_output_tokens(self, text: str) -> int:
        """
        估算输出文本的 token 数量

        Args:
            text: 输出文本

        Returns:
            估算的 Token 数量
        """
        return self.count_tokens(text)

