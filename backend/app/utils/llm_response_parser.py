"""
LLM响应解析器 - 统一处理不同提供商的响应格式

核心功能：
1. 多策略解析：代码块、直接JSON、思维链、正则提取
2. 强验证：检查数据完整性和结构
3. 结构化错误报告：详细记录解析失败原因
4. 渐进式降级：确保在任何情况下都能提供有效输出
5. JSON修复：使用json-repair库自动修复常见的LLM JSON格式错误
"""

import re
import json
import html
from typing import Optional, Dict, Any, Tuple, List
from enum import Enum
from dataclasses import dataclass
import structlog

logger = structlog.get_logger()

# 导入json-repair库用于修复LLM生成的格式错误的JSON
try:
    from json_repair import repair_json
    JSON_REPAIR_AVAILABLE = True
except ImportError:
    JSON_REPAIR_AVAILABLE = False
    logger.warning("json_repair_not_available", message="json-repair库未安装，将跳过JSON修复步骤")


class ResponseFormat(Enum):
    """响应格式类型"""
    CODE_BLOCK_JSON = "code_block_json"  # ```json``` 代码块中的JSON (最高优先级)
    DIRECT_JSON = "direct_json"  # 直接JSON
    THINKING_JSON = "thinking_json"  # 思维链中的JSON
    REGEX_JSON = "regex_json"  # 正则提取的JSON
    RAW_TEXT = "raw_text"  # 原始文本（降级）


@dataclass
class ParseError:
    """结构化解析错误"""
    strategy: str
    error_type: str
    error_msg: str
    content_preview: str
    can_retry: bool


@dataclass
class ParseResult:
    """解析结果"""
    success: bool
    data: Optional[Dict[str, Any]]
    format: Optional[ResponseFormat]
    raw_content: str
    error: Optional[ParseError]
    strategies_tried: List[str]
    metadata: Dict[str, Any]


class LLMResponseParser:
    """
    通用LLM响应解析器 - 强化版

    特点：
    - 支持```json```代码块提取（最高优先级）
    - 多策略渐进式解析
    - 结构化错误报告
    - 强验证机制
    - 完整透明度
    """

    def __init__(self):
        self.reset_stats()
        self.required_action_fields = {"type", "tool", "args", "reasoning"}
        self.required_finish_fields = {"type", "answer", "reasoning"}

    def reset_stats(self):
        """重置解析统计"""
        self.stats = {
            "total_attempts": 0,
            "preprocess_chinese_punctuation": 0,  # 中文标点修复次数
            "json_repair": 0,  # JSON修复次数
            "code_block_json": 0,
            "direct_json": 0,
            "thinking_tag": 0,
            "regex_json": 0,
            "raw_text": 0,
            "validation_failed": 0,
            "retry_required": 0
        }

    def parse(self, content: str) -> Dict[str, Any]:
        """
        统一的响应解析入口 - 多策略解析

        **解析策略（按优先级）**:
        1. JSON修复（使用json-repair库，如果可用）
        2. ```json``` 代码块提取 (最高优先级)
        3. 直接JSON解析
        4. 思维链中的JSON
        5. 智能正则提取

        Args:
            content: LLM原始响应

        Returns:
            ParseResult对象（包含所有解析信息）
        """
        self.stats["total_attempts"] += 1

        if not content or not content.strip():
            error = ParseError(
                strategy="initial_check",
                error_type="EMPTY_CONTENT",
                error_msg="Empty response from LLM",
                content_preview="",
                can_retry=True
            )
            return self._error_result(error, [str(content)])

        original_content = content
        content = content.strip()

        # 步骤0: 预处理 - 修复常见的LLM输出问题
        content = self._preprocess_llm_output(content)

        # 步骤1: 使用json-repair库修复JSON格式问题（如果可用）
        if JSON_REPAIR_AVAILABLE:
            content = self._repair_json_with_library(content, original_content)

        content, had_thinking_tag = self._unwrap_thinking_tag(content)
        if had_thinking_tag:
            self.stats["thinking_tag"] += 1
            strategies_tried.append("unwrap_thinking_tag")

        strategies_tried = []
        # 记录原始内容
        logger.info(
            "parse_llm_response_start",
            content_preview=content[:200] if content else "",
            content_length=len(content) if content else 0,
            starts_with_brace=content.startswith('{') if content else False
        )

        # 策略1: 提取 ```json``` 代码块（最高优先级）
        strategies_tried.append("code_block_json")
        result = self._extract_code_block_json(content)
        if result:
            return result

        # 策略2: 直接JSON解析
        strategies_tried.append("direct_json")
        if content.startswith('{') and content.endswith('}'):
            result = self._parse_direct_json(content, original_content)
            if result:
                return result

        # 策略3: 思维链中的JSON
        strategies_tried.append("thinking_tag")
        result = self._extract_thinking_json(content, original_content)
        if result:
            return result

        # 策略4: 智能正则提取（最后手段）
        strategies_tried.append("regex_extract")
        result = self._smart_regex_extract(content, original_content)
        if result:
            return result

        # 所有策略都失败 - 返回结构化错误
        error = ParseError(
            strategy="all_strategies",
            error_type="PARSING_FAILED",
            error_msg=self._build_failure_message(strategies_tried, had_thinking_tag),
            content_preview=original_content[:500],
            can_retry=True  # 建议让LLM重试
        )
        return self._error_result(error, strategies_tried)

    def _extract_code_block_json(self, content: str) -> Optional[Dict[str, Any]]:
        """提取```json```代码块中的JSON"""
        # 匹配```json ... ```格式
        # 改进：使用更精确的模式，从```json后开始，到```前结束
        pattern = r'```json\s*(.*?)\s*```'
        matches = re.findall(pattern, content, re.DOTALL)

        for match in matches:
            try:
                # 尝试直接解析
                data = json.loads(match.strip())
                self.stats["code_block_json"] += 1
                logger.info(
                    "response_parsed_from_code_block",
                    original_length=len(content),
                    json_length=len(match)
                )
                return self._success_result(data, ResponseFormat.CODE_BLOCK_JSON, content)
            except json.JSONDecodeError as e:
                logger.warning(
                    "code_block_json_parse_failed",
                    error=str(e),
                    content_preview=match[:200]
                )

        return None

    def _parse_direct_json(self, content: str, original_content: str) -> Optional[Dict[str, Any]]:
        """解析直接JSON"""
        try:
            data = json.loads(content)
            self.stats["direct_json"] += 1
            logger.info(
                "response_parsed_directly",
                length=len(content),
                keys=list(data.keys()) if isinstance(data, dict) else None
            )
            return self._success_result(data, ResponseFormat.DIRECT_JSON, original_content)
        except json.JSONDecodeError as e:
            logger.warning(
                "direct_json_parse_failed",
                error=str(e),
                preview=content[:100]
            )

        return None

    def _extract_thinking_json(self, content: str, original_content: str) -> Optional[Dict[str, Any]]:
        """从思维链中提取JSON"""
        # 查找```json标记的思维链
        pattern = r'```json\s*(\{.*?\})\s*```'
        matches = re.findall(pattern, content, re.DOTALL)

        for match in matches:
            try:
                data = json.loads(match.strip())
                self.stats["thinking_tag"] += 1
                logger.info("response_parsed_from_thinking_code_block")
                return self._success_result(data, ResponseFormat.THINKING_JSON, original_content)
            except json.JSONDecodeError:
                continue

        return None

    def _smart_regex_extract(self, content: str, original_content: str) -> Optional[Dict[str, Any]]:
        """智能正则提取JSON - 支持任意深度嵌套"""
        logger.info(
            "smart_regex_extract_called",
            content_preview=content[:100] if content else "",
            content_length=len(content) if content else 0
        )

        # 方法1: 查找第一个{开始，使用平衡括号提取完整JSON
        first_brace = content.find('{')
        logger.info(
            "_smart_regex_extract",
            first_brace=first_brace,
            content_preview=content[:100] if content else ""
        )
        if first_brace != -1:
            json_str = self._extract_balanced_json(content[first_brace:])
            logger.debug("balanced_json_extracted", json_str_preview=json_str[:100] if json_str else None)
            if json_str:
                try:
                    data = json.loads(json_str)
                    logger.debug("json_parsed_success", data_type=type(data).__name__)
                    # 验证必须是字典
                    if not isinstance(data, dict):
                        logger.warning("regex_extracted_non_dict", data_type=type(data).__name__)
                        return None
                    self.stats["regex_json"] += 1
                    logger.info(
                        "response_parsed_via_balanced_braces",
                        json_length=len(json_str)
                    )
                    return self._success_result(data, ResponseFormat.REGEX_JSON, original_content)
                except json.JSONDecodeError as e:
                    logger.debug("json_decode_failed", error=str(e))

        # 方法2: 查找最后一个}之前的完整JSON
        last_brace = content.rfind('}')
        if last_brace != -1 and first_brace != -1:
            potential_json = content[first_brace:last_brace + 1]
            balanced_json = self._extract_balanced_json(potential_json)
            if balanced_json:
                try:
                    data = json.loads(balanced_json)
                    logger.debug("json_parsed_success_v2", data_type=type(data).__name__)
                    # 验证必须是字典
                    if not isinstance(data, dict):
                        logger.warning("regex_extracted_non_dict_v2", data_type=type(data).__name__)
                        return None
                    self.stats["regex_json"] += 1
                    logger.info(
                        "response_parsed_via_full_range",
                        json_length=len(balanced_json)
                    )
                    return self._success_result(data, ResponseFormat.REGEX_JSON, original_content)
                except json.JSONDecodeError as e:
                    logger.debug("json_decode_failed_v2", error=str(e))

        return None

    def _unwrap_thinking_tag(self, content: str) -> Tuple[str, bool]:
        """
        处理 MiniMax 等模型返回的 <think>...</think> 或 <thinking>...</thinking> 包裹的思维链。

        返回: (去除思维链后的正文, 是否发现thinking标签)
        """
        # 先反转义，兼容 &lt;think&gt; 这种HTML转义形式
        unescaped = html.unescape(content.strip())
        lowered = unescaped.lower()

        logger.info(
            "_unwrap_thinking_tag",
            original_preview=content[:100] if content else "",
            unescaped_preview=unescaped[:100] if unescaped else ""
        )

        for tag in ("think", "thinking"):
            open_tag = f"<{tag}"
            close_tag = f"</{tag}>"

            if lowered.startswith(open_tag):
                end_idx = lowered.find(close_tag)
                if end_idx != -1:
                    after = unescaped[end_idx + len(close_tag):].lstrip()
                    # 如果标签后还有内容，优先使用后续内容；否则回退到原文以便后续策略继续尝试
                    return (after if after else unescaped, True)

        return content, False

    def _extract_balanced_json(self, text: str) -> Optional[str]:
        """
        提取平衡括号内的JSON - 支持任意深度嵌套
        增强版：处理被截断的JSON

        Args:
            text: 从第一个{开始的文本

        Returns:
            完整的JSON字符串，失败返回None
        """
        first_brace = text.find('{')
        logger.info(
            "_extract_balanced_json",
            first_brace=first_brace,
            text_preview=text[:50] if text else ""
        )

        if first_brace == -1:
            return None

        brace_count = 0
        in_string = False
        escape_next = False
        json_chars = []
        max_len = len(text)

        for i, char in enumerate(text):
            # 检查是否在字符串内部
            if escape_next:
                json_chars.append(char)
                escape_next = False
                continue

            if char == '\\':
                escape_next = True
                json_chars.append(char)
                continue

            if char == '"' and not escape_next:
                in_string = not in_string

            # 只在非字符串区域计数括号
            if not in_string:
                if char == '{':
                    brace_count += 1
                elif char == '}':
                    brace_count -= 1

            json_chars.append(char)

            # 如果括号匹配完成，说明JSON结束
            if brace_count == 0 and char == '}':
                return ''.join(json_chars)

        # 如果没有找到完整的匹配，检查是否被截断
        # 如果已有部分JSON内容（至少包含基本结构），尝试返回
        if len(json_chars) > 0:
            # 检查是否至少有一个完整的记录
            partial_json = ''.join(json_chars)
            if self._is_minimal_valid_structure(partial_json):
                logger.warning(
                    "returning_truncated_json",
                    original_length=len(text),
                    extracted_length=len(partial_json),
                    note="JSON可能被截断，但返回部分结构"
                )
                return partial_json

        return None

    def _is_minimal_valid_structure(self, text: str) -> bool:
        """
        检查文本是否包含最小的有效JSON结构

        Args:
            text: 文本内容

        Returns:
            是否包含基本JSON结构
        """
        # 至少要有完整的开始括号
        if not text.strip().startswith('{'):
            return False

        # 必须包含必需字段（thought 或 type）
        has_required_fields = '"thought"' in text or '"type"' in text
        if not has_required_fields:
            return False

        # 必须有完整的键值对结构（键: 值,）
        # 检查是否至少有一个值（不是只有键）
        # 策略：检查是否有冒号后的值（至少一个完整的键值对）
        colon_pos = text.find(':')
        if colon_pos == -1:
            return False

        # 检查冒号后面是否有有效的值（不是只有 } 或者是空值如 null/none）
        after_colon = text[colon_pos + 1:].lstrip()
        # 检查 after_colon 是否为空、只有空白、或者只包含 }
        if not after_colon or after_colon == '}' or after_colon.startswith('}'):
            return False
        # 检查是否是 null/none 等空值
        stripped = after_colon.lstrip()
        if stripped.startswith('null') or stripped.startswith('None') or stripped == '':
            return False

        # 尝试解析看是否能成功
        try:
            data = json.loads(text)
            # 必须返回字典
            if not isinstance(data, dict):
                return False
            # 必须有必需字段
            if "thought" not in data and "type" not in data:
                return False
            # 验证必需字段有实际内容（不是 None）
            if "thought" in data and data["thought"] is None:
                return False
            if "type" in data and data["type"] is None:
                return False
            return True
        except (json.JSONDecodeError, ValueError):
            return False

    def _preprocess_llm_output(self, content: str) -> str:
        """
        预处理LLM输出，强制修复常见问题

        修复的问题：
        1. 中文引号 "" → 英文引号 ""
        2. 中文单引号 '' → 英文单引号 ''
        3. 中文书名号《》 → 英文尖括号<>
        4. 中文方括号【】 → 英文方括号[]

        这是第一道防线，在json-repair之前执行。
        强制替换所有中文标点，避免LLM模仿用户输入风格。

        Args:
            content: LLM原始输出

        Returns:
            修复后的内容
        """
        if not content:
            return content

        original_length = len(content)
        modified = False

        # 强制替换所有中文标点符号为英文标点
        replacements = {
            '"': '"',  # 中文左双引号
            '"': '"',  # 中文右双引号
            ''': "'",  # 中文左单引号
            ''': "'",  # 中文右单引号
            '《': '<',  # 中文左书名号
            '》': '>',  # 中文右书名号
            '【': '[',  # 中文左方括号
            '】': ']',  # 中文右方括号
        }

        for old, new in replacements.items():
            if old in content:
                content = content.replace(old, new)
                modified = True

        if modified:
            self.stats["preprocess_chinese_punctuation"] += 1
            logger.info(
                "preprocess_fixed_chinese_punctuation",
                original_length=original_length,
                new_length=len(content),
                message="强制替换了中文标点符号"
            )

        return content

    def _repair_json_with_library(self, content: str, original_content: str) -> str:
        """
        使用json-repair库修复LLM生成的JSON

        修复的常见问题：
        - 未转义的反斜杠（Windows路径等）
        - 未转义的双引号
        - 缺失的括号
        - 尾部的额外内容

        Args:
            content: 待修复的内容
            original_content: 原始内容（用于日志）

        Returns:
            修复后的内容（如果修复失败则返回原内容）
        """
        if not JSON_REPAIR_AVAILABLE:
            return content

        try:
            # 尝试使用json-repair修复
            repaired_content = repair_json(content)

            # 检查是否发生了修复
            if repaired_content != content:
                self.stats["json_repair"] = self.stats.get("json_repair", 0) + 1
                logger.info(
                    "json_repair_successful",
                    original_length=len(content),
                    repaired_length=len(repaired_content),
                    original_preview=content[:200],
                    repaired_preview=repaired_content[:200]
                )

                # 验证修复后的JSON是否可以解析
                try:
                    json.loads(repaired_content)
                    logger.info("json_repair_valid", message="修复后的JSON可以成功解析")
                except json.JSONDecodeError as e:
                    logger.warning(
                        "json_repair_invalid",
                        error=str(e),
                        message="修复后的JSON仍然无效，将尝试其他策略"
                    )
                    # 修复失败，返回原内容
                    return content

            return repaired_content

        except Exception as e:
            # json-repair库执行失败，记录警告但继续使用原内容
            logger.warning(
                "json_repair_failed",
                error=str(e),
                error_type=type(e).__name__,
                message="json-repair库执行失败，将使用原内容"
            )
            return content

    def _build_failure_message(self, strategies: List[str], had_thinking_tag: bool) -> str:
        """
        统一构建解析失败提示，若检测到思维链标签则给出指示。
        """
        base = f"所有解析策略都失败，已尝试: {', '.join(strategies)}"
        if had_thinking_tag:
            return base + "；检测到 <think>/<thinking> 思维链包裹，请在思维链后输出严格的JSON。"
        return base

    def _success_result(
        self,
        data: Dict[str, Any],
        format: ResponseFormat,
        raw_content: str,
        strategies_tried: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """成功响应 - 包含详细元数据"""
        # 严格类型检查：必须是字典
        if not isinstance(data, dict):
            logger.error(
                "success_result_rejected_non_dict",
                data_type=type(data).__name__,
                data_value=str(data)[:100]
            )
            error = ParseError(
                strategy="type_validation",
                error_type="NON_DICT_DATA",
                error_msg=f"解析结果必须是dict，实际是{type(data).__name__}",
                content_preview=str(data)[:500],
                can_retry=True
            )
            return self._error_result(error, strategies_tried or [])

        validation_result = self._validate_data(data)

        metadata = {
            "keys": list(data.keys()) if isinstance(data, dict) else None,
            "data_size": len(str(data)),
            "validation_passed": validation_result["valid"],
            "validation_errors": validation_result["errors"]
        }

        result = {
            "success": True,
            "data": data,
            "format": format,
            "raw_content": raw_content,
            "error": None,
            "strategies_tried": strategies_tried or [],
            "metadata": metadata
        }

        if not validation_result["valid"]:
            self.stats["validation_failed"] += 1
            logger.warning(
                "validation_failed_after_parsing",
                errors=validation_result["errors"],
                format=format.value
            )

        return result

    def _error_result(self, error: ParseError, strategies_tried: List[str]) -> Dict[str, Any]:
        """错误响应 - 包含结构化错误信息"""
        self.stats["retry_required" if error.can_retry else "fallback"] += 1
        logger.error(
            "parsing_failed",
            strategy=error.strategy,
            error_type=error.error_type,
            can_retry=error.can_retry,
            strategies_tried=strategies_tried,
            content_preview=error.content_preview
        )

        return {
            "success": False,
            "data": None,
            "format": None,
            "raw_content": error.content_preview,
            "error": {
                "strategy": error.strategy,
                "error_type": error.error_type,
                "error_msg": error.error_msg,
                "can_retry": error.can_retry,
                "content_preview": error.content_preview,
                "strategies_tried": strategies_tried
            },
            "strategies_tried": strategies_tried,
            "metadata": {
                "attempted_strategies": strategies_tried,
                "should_retry": error.can_retry
            }
        }

    def _validate_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """验证解析后的数据结构"""
        if not isinstance(data, dict):
            return {
                "valid": False,
                "errors": [f"数据必须是dict，实际是{type(data).__name__}"]
            }

        errors = []
        data_type = data.get("type")
        next_action = data.get("next_action")

        # 支持两种数据结构：
        # 1. 行动决策格式：{"type": "TOOL_CALL" | "FINISH", ...}
        # 2. 思考结果格式：{"thought": "...", "reasoning": "...", "next_action": "FINISH" | "TOOL_CALL"}
        if data_type:
            # 行动决策格式
            if data_type == "TOOL_CALL":
                missing = self.required_action_fields - set(data.keys())
                if missing:
                    errors.append(f"TOOL_CALL缺少必需字段: {missing}")
            elif data_type == "FINISH":
                missing = self.required_finish_fields - set(data.keys())
                if missing:
                    errors.append(f"FINISH缺少必需字段: {missing}")
            else:
                errors.append(f"未知的action type: {data_type}")
        elif "thought" in data or "next_action" in data:
            # 思考结果格式（generate_thought 返回的格式）
            # 这种格式不需要严格验证，只需要确保有基本字段即可
            if "thought" not in data and "reasoning" not in data:
                errors.append("思考结果格式缺少必需字段: thought 或 reasoning")
        # 如果既没有 type 也没有 thought/next_action，可能是其他格式，不报错让调用方处理

        return {
            "valid": len(errors) == 0,
            "errors": errors
        }

    def get_stats(self) -> Dict[str, int]:
        """获取解析统计"""
        return self.stats.copy()


# 全局解析器实例
parser = LLMResponseParser()


# 便捷函数
def parse_llm_response(content: str) -> Dict[str, Any]:
    """
    解析LLM响应的便捷函数

    Args:
        content: LLM原始响应

    Returns:
        解析结果（Dict格式，向后兼容）
    """
    result = parser.parse(content)
    # 转换为简单的dict格式，保持向后兼容
    if result["success"]:
        return {
            "success": True,
            "data": result["data"],
            "format": result["format"],
            "raw_content": result["raw_content"],
            "error": None
        }
    else:
        return {
            "success": False,
            "data": None,
            "format": None,
            "raw_content": result.get("raw_content", ""),
            "error": result["error"]["error_msg"] if result.get("error") else "Unknown error"
        }


def extract_json_from_response(content: str) -> Optional[Dict[str, Any]]:
    """
    从响应中提取JSON的便捷函数

    Args:
        content: LLM原始响应

    Returns:
        JSON对象，失败返回None
    """
    result = parse_llm_response(content)
    if result["success"]:
        return result["data"]
    return None


# 使用示例和测试
if __name__ == "__main__":
    # 测试不同格式的响应
    test_cases = [
        # 1. ```json```代码块（期望最高优先级）
        '以下是分析结果：\n```json\n{"type": "TOOL_CALL", "tool": "get_air_quality", "args": {"question": "查询广州天气"}}\n```',
        # 2. 直接JSON
        '{"type": "FINISH", "answer": "分析完成"}',
        # 3. 复杂JSON（多层嵌套）
        '''```json
{
    "type": "TOOL_CALL",
    "tool": "generate_chart",
    "args": {
        "data": {
            "records": [
                {"time": "2025-11-07T00:00:00", "AQI": 45, "PM2.5": 25.0},
                {"time": "2025-11-07T01:00:00", "AQI": 48, "PM2.5": 27.0}
            ]
        }
    },
    "reasoning": "需要生成图表"
}
```''',
        # 4. 缺字段的JSON（验证失败）
        '{"type": "TOOL_CALL", "tool": "get_air_quality"}',
        # 5. 无效响应
        '这个响应没有JSON',
    ]

    for i, test_case in enumerate(test_cases, 1):
        print(f"\n{'='*60}")
        print(f"Test Case {i}")
        print('='*60)
        result = parse_llm_response(test_case)
        print(f"Success: {result['success']}")
        print(f"Format: {result['format'] if result['format'] else 'N/A'}")
        print(f"Data Keys: {list(result['data'].keys()) if result['success'] and result['data'] else 'N/A'}")
        if result['error']:
            print(f"Error: {result['error']}")

    print(f"\n{'='*60}")
    print("Statistics")
    print('='*60)
    print(parser.get_stats())
