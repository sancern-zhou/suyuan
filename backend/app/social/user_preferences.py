"""
用户偏好配置管理

管理社交模式用户的风格偏好配置，支持：
- 回答风格（正式/随意/专业/通俗）
- 输出格式（纯文本/Markdown/结构化）
- 详细程度（简洁/适中/详细）
- Emoji使用（是/否）
"""

import json
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime
import structlog

logger = structlog.get_logger(__name__)


class UserPreferences:
    """用户偏好配置"""

    # 预设的回复风格选项
    STYLE_OPTIONS = {
        "casual": {
            "name": "轻松随意",
            "description": "像朋友聊天一样，口语化表达，可以使用表情符号",
            "tone": "轻松、友好、亲切",
            "example": "好的，没问题！今天天气真不错~"
        },
        "formal": {
            "name": "正式专业",
            "description": "专业、严谨的表达方式，适合工作场景",
            "tone": "正式、专业、礼貌",
            "example": "您好，根据数据分析结果，建议采取以下措施..."
        },
        "professional": {
            "name": "技术专业",
            "description": "使用专业术语，适合技术人员交流",
            "tone": "专业、技术性强",
            "example": "根据PMF源解析结果，O3主要来源于..."
        },
        "simple": {
            "name": "通俗易懂",
            "description": "用简单的语言解释复杂概念，适合非专业人士",
            "tone": "简单、易懂、耐心",
            "example": "简单来说，就像做饭时火太大容易糊一样..."
        }
    }

    # 输出格式选项
    FORMAT_OPTIONS = {
        "plain": {
            "name": "纯文本",
            "description": "简单文本，不使用任何格式化"
        },
        "markdown": {
            "name": "Markdown格式",
            "description": "使用Markdown格式，支持标题、列表、加粗等"
        },
        "structured": {
            "name": "结构化",
            "description": "使用分段和列表，结构清晰"
        }
    }

    # 详细程度选项
    DETAIL_OPTIONS = {
        "concise": {
            "name": "简洁",
            "description": "只说重点，一句话概括",
            "max_length": 200
        },
        "moderate": {
            "name": "适中",
            "description": "适量信息，适中篇幅",
            "max_length": 1000
        },
        "detailed": {
            "name": "详细",
            "description": "提供完整信息和背景",
            "max_length": 2000
        }
    }

    def __init__(
        self,
        user_id: str,
        data_dir: Optional[Path] = None
    ):
        """
        初始化用户偏好配置

        Args:
            user_id: 用户ID（格式：{channel}:{bot_account}:{sender_id}）
            data_dir: 数据目录
        """
        self.user_id = user_id
        self.data_dir = data_dir or Path("backend_data_registry/social/preferences")
        self.data_dir.mkdir(parents=True, exist_ok=True)

        # 用户ID转换（避免特殊字符）
        safe_user_id = user_id.replace(":", "_")
        self.preferences_file = self.data_dir / f"{safe_user_id}.json"
        self.waiting_preferences_file = self.data_dir / f"{safe_user_id}_waiting.flag"  # 状态标记文件

        # 默认偏好
        self._preferences = {
            "style": "casual",  # 默认轻松随意
            "format": "plain",  # 默认纯文本
            "detail": "moderate",  # 默认适中
            "use_emoji": False,  # 默认不使用emoji
            "created_at": None,
            "updated_at": None
        }

        # 加载已有偏好
        self._load()

    def _load(self) -> None:
        """从文件加载用户偏好"""
        if self.preferences_file.exists():
            try:
                with open(self.preferences_file, 'r', encoding='utf-8') as f:
                    saved = json.load(f)
                    self._preferences.update(saved)
                logger.debug("preferences_loaded", user_id=self.user_id)
            except Exception as e:
                logger.error("failed_to_load_preferences",
                           user_id=self.user_id,
                           error=str(e))

    def _save(self) -> None:
        """保存用户偏好到文件"""
        try:
            self._preferences["updated_at"] = datetime.now().isoformat()
            if not self._preferences["created_at"]:
                self._preferences["created_at"] = self._preferences["updated_at"]

            with open(self.preferences_file, 'w', encoding='utf-8') as f:
                json.dump(self._preferences, f, ensure_ascii=False, indent=2)

            logger.info("preferences_saved", user_id=self.user_id)
        except Exception as e:
            logger.error("failed_to_save_preferences",
                        user_id=self.user_id,
                        error=str(e))

    def is_new_user(self) -> bool:
        """
        检查是否为新用户（未设置过偏好）

        Returns:
            是否为新用户
        """
        return not self.preferences_file.exists()

    def get_preferences(self) -> Dict[str, Any]:
        """
        获取用户偏好配置

        Returns:
            偏好配置字典
        """
        return self._preferences.copy()

    def set_preferences(self, **kwargs) -> None:
        """
        设置用户偏好

        Args:
            **kwargs: 偏好键值对（style/format/detail/use_emoji）
        """
        valid_keys = {"style", "format", "detail", "use_emoji"}
        for key, value in kwargs.items():
            if key in valid_keys:
                self._preferences[key] = value
            else:
                logger.warning("invalid_preference_key",
                             user_id=self.user_id,
                             key=key)

        self._save()

        # ✅ 保存偏好后清除等待状态
        self.clear_waiting_preferences()

    def get_style_description(self) -> str:
        """
        获取当前风格的描述

        Returns:
            风格描述字符串
        """
        style = self._preferences["style"]
        style_info = self.STYLE_OPTIONS.get(style, self.STYLE_OPTIONS["casual"])

        return (
            f"{style_info['tone']}，{style_info['description']}\n"
            f"示例：{style_info['example']}"
        )

    def get_format_description(self) -> str:
        """
        获取当前输出格式的描述

        Returns:
            格式描述字符串
        """
        format_type = self._preferences["format"]
        format_info = self.FORMAT_OPTIONS.get(format_type, self.FORMAT_OPTIONS["plain"])

        return format_info['description']

    def get_max_length(self) -> int:
        """
        获取最大回答长度

        Returns:
            最大字数
        """
        detail = self._preferences["detail"]
        detail_info = self.DETAIL_OPTIONS.get(detail, self.DETAIL_OPTIONS["moderate"])

        return detail_info['max_length']

    def generate_welcome_message(self) -> str:
        """
        生成欢迎消息（首次对话引导）

        Returns:
            欢迎消息字符串
        """
        return """欢迎使用智能分析助手！

为了更好地为你服务，请选择你的偏好配置：

**1. 回答风格**
A. 轻松随意 - 像朋友聊天一样
B. 正式专业 - 适合工作场景
C. 技术专业 - 使用专业术语
D. 通俗易懂 - 简单解释复杂概念

**2. 输出格式**
A. 纯文本 - 简单直接
B. Markdown格式 - 支持格式化
C. 结构化 - 清晰分段

**3. 详细程度**
A. 简洁 - 一句话概括
B. 适中 - 适量信息
C. 详细 - 完整信息

**4. 是否使用表情符号**
A. 是
B. 否

请直接回复你的选择，例如：1A 2B 3C 4B
或者回复"默认"使用默认配置（轻松随意+纯文本+适中+无表情）"""

    def parse_preferences_response(self, response: str) -> Optional[Dict[str, Any]]:
        """
        解析用户的偏好选择响应

        Args:
            response: 用户响应字符串

        Returns:
            解析后的偏好配置，失败返回None
        """
        try:
            # 标准化输入
            response = response.strip().upper()

            # 默认配置
            if response == "默认" or response == "DEFAULT":
                return {
                    "style": "casual",
                    "format": "plain",
                    "detail": "moderate",
                    "use_emoji": False
                }

            # 解析选择（格式：1A 2B 3C 4B）
            choices = {}

            # 构建字母到选项的映射
            style_keys = list(self.STYLE_OPTIONS.keys())
            format_keys = list(self.FORMAT_OPTIONS.keys())
            detail_keys = list(self.DETAIL_OPTIONS.keys())

            for part in response.split():
                if len(part) >= 2:
                    question = part[0]
                    answer = part[1].upper()  # 确保大写

                    if question == "1" and answer in ["A", "B", "C", "D"]:
                        # 将字母映射到实际的风格值
                        index = ord(answer) - ord('A')
                        if 0 <= index < len(style_keys):
                            choices["style"] = style_keys[index]
                    elif question == "2" and answer in ["A", "B", "C"]:
                        # 将字母映射到实际的格式值
                        index = ord(answer) - ord('A')
                        if 0 <= index < len(format_keys):
                            choices["format"] = format_keys[index]
                    elif question == "3" and answer in ["A", "B", "C"]:
                        # 将字母映射到实际的详细程度值
                        index = ord(answer) - ord('A')
                        if 0 <= index < len(detail_keys):
                            choices["detail"] = detail_keys[index]
                    elif question == "4" and answer in ["A", "B"]:
                        choices["use_emoji"] = (answer == "A")

            # 验证是否完整
            required_keys = {"style", "format", "detail", "use_emoji"}
            if not required_keys.issubset(choices.keys()):
                return None

            return choices

        except Exception as e:
            logger.error("failed_to_parse_preferences",
                        user_id=self.user_id,
                        response=response,
                        error=str(e))
            return None

    def generate_confirmation_message(self, preferences: Dict[str, Any]) -> str:
        """
        生成偏好确认消息

        Args:
            preferences: 偏好配置

        Returns:
            确认消息字符串
        """
        style_info = self.STYLE_OPTIONS.get(preferences["style"])
        format_info = self.FORMAT_OPTIONS.get(preferences["format"])
        detail_info = self.DETAIL_OPTIONS.get(preferences["detail"])
        emoji_text = "使用" if preferences["use_emoji"] else "不使用"

        return f"""配置已保存！

你的偏好设置：
- 回答风格：{style_info['name']} - {style_info['description']}
- 输出格式：{format_info['name']} - {format_info['description']}
- 详细程度：{detail_info['name']} - {detail_info['description']}
- 表情符号：{emoji_text}

现在你可以开始提问了！有什么可以帮助你的吗？"""

    def set_waiting_preferences(self) -> None:
        """
        设置等待偏好配置响应状态

        新用户收到欢迎消息后调用，标记为等待用户回复偏好配置
        """
        try:
            self.waiting_preferences_file.write_text(
                datetime.now().isoformat(),
                encoding='utf-8'
            )
            logger.info("waiting_preferences_state_set",
                       user_id=self.user_id)
        except Exception as e:
            logger.error("failed_to_set_waiting_preferences",
                        user_id=self.user_id,
                        error=str(e))

    def is_waiting_preferences(self) -> bool:
        """
        检查是否在等待偏好配置响应

        Returns:
            是否在等待偏好配置响应
        """
        return self.waiting_preferences_file.exists()

    def clear_waiting_preferences(self) -> None:
        """
        清除等待偏好配置响应状态

        用户成功配置偏好后调用
        """
        try:
            if self.waiting_preferences_file.exists():
                self.waiting_preferences_file.unlink()
                logger.info("waiting_preferences_state_cleared",
                           user_id=self.user_id)
        except Exception as e:
            logger.error("failed_to_clear_waiting_preferences",
                        user_id=self.user_id,
                        error=str(e))
