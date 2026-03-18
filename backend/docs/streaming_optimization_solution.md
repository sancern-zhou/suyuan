"""
流式检测优化方案 - 保留流式展示能力

核心思想：
- 用简单的字符串匹配代替完整JSON解析
- 只在检测到FINAL_ANSWER时才解析
- 减少重复解析和日志
"""

import re
from typing import Optional, Dict, Any

class StreamDetector:
    """
    轻量级流式检测器

    功能：
    - 检测JSON结构完整性（不解析）
    - 检测FINAL_ANSWER标记
    - 提取answer字段（简化版）
    """

    def __init__(self):
        self.buffer = ""
        self.in_answer_field = False
        self.answer_start = -1
        self.brace_count = 0
        self.in_string = False
        self.escape_next = False

    def is_json_complete(self, text: str) -> bool:
        """
        检测JSON是否完整（不解析）

        使用简单的括号平衡检测
        """
        brace_count = 0
        in_string = False
        escape_next = False

        for char in text:
            if escape_next:
                escape_next = False
                continue

            if char == '\\':
                escape_next = True
                continue

            if char == '"' and not escape_next:
                in_string = not in_string
                continue

            if not in_string:
                if char == '{':
                    brace_count += 1
                elif char == '}':
                    brace_count -= 1

        return brace_count == 0 and text.rstrip().endswith('}')

    def detect_final_answer(self, text: str) -> bool:
        """
        检测是否包含FINAL_ANSWER标记

        策略：
        1. 检查是否有 "type": "FINAL_ANSWER"
        2. 检查是否有 "answer": 字段
        """
        # 快速检测：避免正则表达式
        return '"type": "FINAL_ANSWER"' in text or '"type":"FINAL_ANSWER"' in text

    def extract_answer_field(self, text: str) -> Optional[str]:
        """
        提取answer字段（简化版，不解析完整JSON）

        策略：
        1. 查找 "answer": " 的位置
        2. 提取直到结尾的字符串值
        """
        # 查找answer字段开始
        patterns = [
            r'"answer":\s*"([^"]*(?:"[^"]*)*)"',  # "answer": "value"
            r'"answer":\s*\'([^\']*(?:\'[^\']*)*)\'',  # 'answer': 'value'
        ]

        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return match.group(1)

        return None


# ========================================
# 优化后的流式处理逻辑
# ========================================

async def think_and_action_v2_streaming_optimized(
    self,
    query: str,
    system_prompt: str,
    user_conversation: str,
    iteration: int = 0,
    latest_observation: Optional[Dict[str, Any]] = None
):
    """
    优化版流式处理

    改进：
    - 使用StreamDetector代替完整解析
    - 减少重复日志
    - 保留流式展示能力
    """
    from app.utils.llm_response_parser import parser
    from app.utils.stream_detector import StreamDetector

    detector = StreamDetector()
    buffer = ""
    is_final_answer = False
    final_answer_buffer = ""

    async for chunk in self.llm_service.chat_streaming(messages):
        buffer += chunk

        # 快速检测：避免完整解析
        if detector.is_json_complete(buffer):
            # JSON可能完整，尝试解析
            parsed = parser.parse(buffer, use_cache=True)  # 使用缓存

            if parsed.get("success") and parsed.get("data"):
                data = parsed["data"]

                # 检查是否是FINAL_ANSWER
                if detector.detect_final_answer(buffer):
                    is_final_answer = True
                    answer = data.get("action", {}).get("answer", "")

                    # 计算新增内容
                    new_content = answer[len(final_answer_buffer):]
                    if new_content:
                        final_answer_buffer = answer
                        yield {
                            "type": "streaming_text",
                            "data": {"chunk": new_content, "is_complete": False}
                        }
                    break

        # 轻量级检测：检查FINAL_ANSWER标记
        if not is_final_answer and detector.detect_final_answer(buffer):
            # 尝试提取answer字段（不解析完整JSON）
            answer = detector.extract_answer_field(buffer)
            if answer:
                is_final_answer = True
                new_content = answer[len(final_answer_buffer):]
                if new_content:
                    final_answer_buffer = answer
                    yield {
                        "type": "streaming_text",
                        "data": {"chunk": new_content, "is_complete": False}
                    }

    # 流式结束，处理最终结果
    if is_final_answer:
        yield {
            "type": "streaming_text",
            "data": {"chunk": "", "is_complete": True}
        }

        # 最终解析（只解析一次）
        parsed_result = parser.parse(buffer)
        # ... 处理结果 ...
    else:
        # 非FINAL_ANSWER，解析完整JSON
        parsed_result = parser.parse(buffer)
        # ... 处理结果 ...


# ========================================
# 方案对比
# ========================================

"""
当前方案 vs 优化方案对比

| 特性 | 当前方案 | 优化方案 |
|------|----------|----------|
| 流式解析频率 | 每个chunk都解析 | JSON完整时才解析 |
| 重复日志 | 2次 | 1次 |
| 流式展示 | ✅ 支持 | ✅ 支持 |
| 容错能力 | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ |
| 性能 | 一般 | 更好 |
| 代码复杂度 | 高 | 中 |

优化方案的优点：
1. ✅ 保留流式展示能力
2. ✅ 减少JSON解析次数
3. ✅ 消除重复日志
4. ✅ 性能更好
5. ✅ 代码更清晰
"""

# ========================================
# 实施建议
# ========================================

"""
步骤1：创建StreamDetector（轻量级检测器）
文件：app/utils/stream_detector.py

步骤2：修改planner.py流式处理
- 使用StreamDetector代替直接解析
- 只在必要时才调用parser.parse()

步骤3：添加解析缓存
- 在LLMResponseParser中添加缓存
- 避免重复解析相同内容

步骤4：测试验证
- 测试FINAL_ANSWER流式展示
- 测试工具调用的JSON解析
- 测试错误处理
"""
