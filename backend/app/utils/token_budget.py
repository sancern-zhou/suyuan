"""
Token budget management for LLM context windows.

简化版：只保留token计数和简单截断功能
"""
import structlog

logger = structlog.get_logger()

# Try to import tiktoken for accurate token counting
try:
    import tiktoken
    TIKTOKEN_AVAILABLE = True
except ImportError:
    TIKTOKEN_AVAILABLE = False
    logger.warning("tiktoken_not_available",
                   message="Using character-based estimation. Install tiktoken for accurate token counting: pip install tiktoken")


class TokenBudgetManager:
    """
    简化的Token预算管理器

    功能：
    1. 精确的token计数（使用tiktoken）
    2. 简单的文本截断（按token数截断）
    """

    def __init__(
        self,
        model: str = "gpt-4",
        max_context_tokens: int = 120000,
        safety_buffer: int = 5000,
        use_tiktoken: bool = True
    ):
        """
        Initialize token budget manager.

        Args:
            model: Model name (gpt-4, deepseek-chat, etc.)
            max_context_tokens: Maximum context window size (default: 120K for GPT-4 Turbo)
            safety_buffer: Reserved tokens for response generation (default: 5K)
            use_tiktoken: Whether to use tiktoken for accurate counting
        """
        self.model = model
        self.max_context_tokens = max_context_tokens
        self.safety_buffer = safety_buffer
        self.use_tiktoken = use_tiktoken and TIKTOKEN_AVAILABLE

        # Initialize tokenizer
        self.tokenizer = None
        if self.use_tiktoken:
            try:
                # Map model names to tiktoken encodings
                if "gpt-4" in model.lower() or "gpt-3.5" in model.lower():
                    self.tokenizer = tiktoken.encoding_for_model("gpt-4")
                elif "deepseek" in model.lower():
                    # DeepSeek uses GPT-4 compatible tokenizer
                    self.tokenizer = tiktoken.encoding_for_model("gpt-4")
                else:
                    # Fallback to cl100k_base (GPT-4 encoding)
                    self.tokenizer = tiktoken.get_encoding("cl100k_base")
                logger.info("tiktoken_initialized", model=model, encoding=self.tokenizer.name)
            except Exception as e:
                logger.warning("tiktoken_init_failed", error=str(e))
                self.use_tiktoken = False

    def count_tokens(self, text: str) -> int:
        """
        Count tokens in a text string.

        Args:
            text: Input text

        Returns:
            Number of tokens
        """
        if not text:
            return 0

        if self.use_tiktoken and self.tokenizer:
            try:
                return len(self.tokenizer.encode(text))
            except Exception as e:
                logger.warning("tiktoken_count_failed", error=str(e))
                # Fallback to estimation
                return self._estimate_tokens(text)
        else:
            return self._estimate_tokens(text)

    def _estimate_tokens(self, text: str) -> int:
        """
        Estimate tokens using character count (fallback method).

        Rough estimate: 1 token ≈ 4 characters for English, 1.5 characters for Chinese
        """
        # Count Chinese characters
        chinese_chars = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
        # Count other characters
        other_chars = len(text) - chinese_chars

        # Estimated tokens: Chinese chars / 1.5 + Other chars / 4
        estimated = (chinese_chars / 1.5) + (other_chars / 4)
        return int(estimated)

    def _truncate_to_tokens(self, text: str, target_tokens: int) -> str:
        """
        Truncate text to approximately target_tokens.

        Strategy: Binary search to find character count that fits token budget

        Args:
            text: Input text
            target_tokens: Target token count

        Returns:
            Truncated text
        """
        if not text:
            return text

        current_tokens = self.count_tokens(text)

        if current_tokens <= target_tokens:
            return text

        # Estimate character ratio
        char_ratio = len(text) / current_tokens
        estimated_chars = int(target_tokens * char_ratio)

        # Binary search for optimal truncation point
        low, high = 0, len(text)
        best_truncation = estimated_chars

        for _ in range(10):  # Max 10 iterations
            mid = (low + high) // 2
            truncated = text[:mid]
            tokens = self.count_tokens(truncated)

            if tokens <= target_tokens:
                best_truncation = mid
                low = mid + 1
            else:
                high = mid - 1

        truncated_text = text[:best_truncation]

        # Add ellipsis if truncated
        if best_truncation < len(text):
            truncated_text += "\n\n...(内容已截断)"

        return truncated_text


# Global token budget manager instance
# Default: 100K context window (支持更长上下文)
# 实际分配：system(~2K) + tools(~2K) + conversation(~10K) + context(~81K) + safety(5K) = 100K
token_budget_manager = TokenBudgetManager(
    model="gpt-4",
    max_context_tokens=100000,
    safety_buffer=5000
)
