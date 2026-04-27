"""
用户偏好配置管理（助理定义模式）

管理社交模式用户的助理定义配置，支持：
- 助理名称（assistant_name）
- 助理性格（assistant_personality）
"""

import json
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime
import structlog

logger = structlog.get_logger(__name__)


class UserPreferences:
    """用户偏好配置（助理定义模式）"""

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

        # 默认偏好（助理定义模式）
        self._preferences = {
            "assistant_name": "智能助手",
            "assistant_personality": "友善、专业、简洁",
            "created_at": None,
            "updated_at": None
        }

        # 加载已有偏好
        self._load()

        # ✅ 新增：记忆文件路径（用于soul.md和USER.md）
        self.memory_dir = Path("backend_data_registry/social/memory")
        self.memory_dir.mkdir(parents=True, exist_ok=True)
        safe_user_id_for_memory = user_id.replace(":", "_")
        self.user_memory_path = self.memory_dir / safe_user_id_for_memory
        self.user_memory_path.mkdir(parents=True, exist_ok=True)

        self.soul_file = self.user_memory_path / "soul.md"
        self.user_file = self.user_memory_path / "USER.md"

        # ✅ 新增：定时任务文件路径（HEARTBEAT.md）
        self.heartbeat_dir = Path("backend_data_registry/social/heartbeat")
        self.heartbeat_dir.mkdir(parents=True, exist_ok=True)
        safe_user_id_for_heartbeat = user_id.replace(":", "_")
        self.heartbeat_path = self.heartbeat_dir / safe_user_id_for_heartbeat
        self.heartbeat_path.mkdir(parents=True, exist_ok=True)

        self.heartbeat_file = self.heartbeat_path / "HEARTBEAT.md"

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
        设置用户偏好（助理定义模式）

        Args:
            **kwargs: 偏好键值对（assistant_name/assistant_personality）
        """
        valid_keys = {"assistant_name", "assistant_personality"}
        for key, value in kwargs.items():
            if key in valid_keys:
                self._preferences[key] = value
            else:
                logger.warning("invalid_preference_key",
                             user_id=self.user_id,
                             key=key)

        self._save()

        # ✅ 保存偏好后生成soul.md
        self._generate_soul_md()

        # ✅ 确保USER.md存在（空白模板）
        self._ensure_user_md_exists()

        # ✅ 清除等待状态
        self.clear_waiting_preferences()

    def _generate_soul_md(self) -> None:
        """
        从 user_preferences 生成 soul.md

        助理灵魂档案，从用户偏好配置生成（已弃用，保留向后兼容）
        """
        try:
            name = self._preferences.get("assistant_name", "智能助手")
            personality = self._preferences.get("assistant_personality", "友善、专业")

            content = f"""# 助理灵魂档案

## 基本信息
- 名称：{name}
- 性格：{personality}

## 能力范围
- 空气质量查询和分析（广东省城市日数据、统计报表、对比分析）
- 数据可视化（图表生成、AQI日历图等）
- 文件操作（读取、编辑、搜索）
- 系统管理（执行命令、定时任务）
- 记忆管理（记住你的偏好和重要信息）

## 沟通风格
- 保持对话性但专业
- 根据你的专业水平调整技术深度
- 需求不明确时主动提出澄清性问题
- 不知道时诚实承认，不编造答案
"""

            self.soul_file.write_text(content, encoding='utf-8')
            logger.info("soul_md_generated",
                       user_id=self.user_id,
                       path=str(self.soul_file))
        except Exception as e:
            logger.error("failed_to_generate_soul_md",
                        user_id=self.user_id,
                        error=str(e))

    def _ensure_user_md_exists(self) -> None:
        """
        确保 USER.md 存在（空白模板）

        用户档案文件，助理通过文件工具主动学习和管理
        """
        try:
            if not self.user_file.exists():
                content = """# 用户档案

## 基本信息
- 姓名：（暂未了解）
- 称呼：您
- 代词：你
- 时区：UTC+8

## 专业背景
- 职业：（待学习）
- 技术水平：（待学习）
- 专业领域：（待学习）

## 沟通偏好
- 详细程度：（待学习）
- 格式偏好：（待学习）
- 对话风格：（待学习）

## 学习历史
*助理通过对话逐步了解你的偏好*

---
最后更新：（自动记录）
"""
                self.user_file.write_text(content, encoding='utf-8')
                logger.info("user_md_template_created",
                           user_id=self.user_id,
                           path=str(self.user_file))
        except Exception as e:
            logger.error("failed_to_create_user_md_template",
                        user_id=self.user_id,
                        error=str(e))

    def load_soul_md(self) -> str:
        """
        加载 soul.md 内容

        Returns:
            soul.md 文件内容，如果文件不存在返回空字符串
        """
        try:
            if self.soul_file.exists():
                return self.soul_file.read_text(encoding='utf-8')
            return ""
        except Exception as e:
            logger.error("failed_to_load_soul_md",
                        user_id=self.user_id,
                        error=str(e))
            return ""

    def load_user_md(self) -> str:
        """
        加载 USER.md 内容

        Returns:
            USER.md 文件内容，如果文件不存在返回空字符串
        """
        try:
            if self.user_file.exists():
                return self.user_file.read_text(encoding='utf-8')
            return ""
        except Exception as e:
            logger.error("failed_to_load_user_md",
                        user_id=self.user_id,
                        error=str(e))
            return ""
