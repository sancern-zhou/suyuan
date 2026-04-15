"""
通用双层记忆系统

从 app/social/memory_store.py 迁移，支持所有7种模式（社交、助手、专家、问数、编程、报告、图表）

核心功能：
- MEMORY.md：长期事实（用户偏好、历史结论、重要数据）
- HISTORY.md：可搜索日志（完整对话历史）
- 自动整合对话内容到记忆
- 提供记忆上下文给LLM

改进版（参考 nanobot）：
- 使用JSON响应方式（更可靠）
- 失败重试机制
- 原始归档降级
"""

import asyncio
import json
import re
import weakref
from pathlib import Path
from typing import Optional, List, Dict, Any, Callable, Awaitable
from datetime import datetime
import structlog

logger = structlog.get_logger(__name__)


class MemoryStore:
    """
    通用双层记忆系统（支持所有模式）

    MEMORY.md：
    - 长期事实（用户偏好、历史结论、重要数据）
    - 持久化存储
    - 自动整合到上下文

    HISTORY.md：
    - 可搜索日志（完整对话历史）
    - 按时间倒序
    - 用于回溯和查找
    """

    def __init__(
        self,
        user_id: Optional[str] = None,
        mode: str = "expert",  # ✅ 新增：模式标识（social/assistant/expert/query/code/report/chart）
        workspace: Optional[Path] = None,
        max_memory_size: int = 10000,  # 最大记忆字符数
        max_history_size: int = 50000  # 最大历史字符数
    ):
        """
        初始化记忆存储

        Args:
            user_id: 用户ID（格式：{mode}:{user_identifier}:{shared|unique}）
            mode: 模式标识（social/assistant/expert/query/code/report/chart）
            workspace: 工作空间目录，默认 backend_data_registry/memory
            max_memory_size: MEMORY.md 最大字符数
            max_history_size: HISTORY.md 最大字符数
        """
        self.user_id = user_id or "global"  # 默认全局记忆（向后兼容）
        self.mode = mode
        self.max_memory_size = max_memory_size
        self.max_history_size = max_history_size

        # ✅ 模式专属工作空间
        self.workspace = self._init_workspace(workspace, user_id, mode)
        self.memory_file = self.workspace / "MEMORY.md"
        self.history_file = self.workspace / "HISTORY.md"

        # 初始化文件
        self._init_files()

        logger.debug(
            "memory_store_initialized",
            user_id=self.user_id,
            mode=self.mode,
            workspace=str(self.workspace)
        )

    def _init_workspace(self, workspace: Path, user_id: str, mode: str) -> Path:
        """
        初始化模式专属工作空间

        Args:
            workspace: 基础工作空间
            user_id: 用户ID（暂不使用，保留接口兼容性）
            mode: 模式标识

        Returns:
            模式专属工作空间路径
        """
        base = workspace or Path("/home/xckj/suyuan/backend_data_registry/memory")

        # 按mode分组存储（不考虑用户登录场景）
        mode_dir = base / mode
        mode_dir.mkdir(parents=True, exist_ok=True)

        # 直接返回模式目录
        # 例如：/home/xckj/suyuan/backend_data_registry/memory/query/MEMORY.md
        return mode_dir

    def _init_files(self) -> None:
        """初始化MEMORY.md和HISTORY.md文件"""
        if not self.memory_file.exists():
            initial_memory = """# 长期记忆 (MEMORY.md)

此文件存储用户的偏好、领域知识和重要结论。

## 用户偏好

## 领域知识

## 历史结论
"""
            self.memory_file.write_text(initial_memory, encoding="utf-8")
            logger.info("memory_file_created", path=str(self.memory_file))

        if not self.history_file.exists():
            initial_history = """# 对话历史 (HISTORY.md)

此文件按时间倒序记录完整的对话历史，用于回溯和查找。

---
"""
            self.history_file.write_text(initial_history, encoding="utf-8")
            logger.info("history_file_created", path=str(self.history_file))

    def get_memory_context(self) -> str:
        """
        获取记忆上下文（用于LLM）

        Returns:
            MEMORY.md的内容（如果为空则返回空字符串）
        """
        try:
            memory_content = self.memory_file.read_text(encoding="utf-8")

            # 过滤掉空内容
            if memory_content.strip() in ["", "# 长期记忆 (MEMORY.md)", "# 长期记忆 (MEMORY.md)\n"]:
                return ""

            return f"## 长期记忆\n{memory_content}"

        except Exception as e:
            logger.error(
                "failed_to_read_memory",
                error=str(e),
                exc_info=True
            )
            return ""

    async def consolidate(
        self,
        messages: List[Dict[str, Any]],
        llm_service=None,
        start_offset: int = 0
    ) -> bool:
        """
        增量整合对话内容到记忆中

        流程：
        1. 当前MEMORY.md + 新对话内容 → LLM分析
        2. 生成新的MEMORY.md（提取重要信息）
        3. 追加到HISTORY.md（完整对话）

        Args:
            messages: 对话消息列表
            llm_service: LLM服务（用于提取重要信息）
            start_offset: 起始消息偏移量（避免重复整合）

        Returns:
            是否成功整合
        """
        if not messages:
            return True

        # 只整合从 start_offset 之后的新消息
        new_messages = messages[start_offset:] if start_offset > 0 else messages

        if not new_messages:
            return True

        try:
            # 1. 追加到HISTORY.md
            await self._append_to_history(new_messages)

            # 2. 整合到MEMORY.md（如果有LLM服务）
            if llm_service:
                await self._update_memory(new_messages, llm_service)

            logger.info(
                "memory_consolidated",
                user_id=self.user_id,
                mode=self.mode,
                message_count=len(new_messages),
                start_offset=start_offset
            )
            return True

        except Exception as e:
            logger.error(
                "memory_consolidation_failed",
                user_id=self.user_id,
                mode=self.mode,
                error=str(e),
                exc_info=True
            )
            return False

    async def _append_to_history(self, messages: List[Dict[str, Any]]) -> None:
        """
        追加对话到HISTORY.md

        Args:
            messages: 对话消息列表
        """
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # 构建历史条目
        history_entry = f"\n## {timestamp}\n\n"

        for msg in messages:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")

            if role == "user":
                history_entry += f"**用户**: {content}\n\n"
            elif role == "assistant":
                # 只保留前500个字符，避免历史过长
                preview = content[:500] + "..." if len(content) > 500 else content
                history_entry += f"**助手**: {preview}\n\n"

        history_entry += "---\n"

        # 追加到文件
        current_content = self.history_file.read_text(encoding="utf-8")

        # 检查文件大小，超过限制则清理旧内容
        if len(current_content) + len(history_entry) > self.max_history_size:
            # 保留最新的80%
            keep_size = int(self.max_history_size * 0.8)
            current_content = current_content[-keep_size:]

        new_content = current_content + history_entry
        self.history_file.write_text(new_content, encoding="utf-8")

        logger.debug("history_updated", entry_length=len(history_entry))

    async def _update_memory(
        self,
        messages: List[Dict[str, Any]],
        llm_service
    ) -> None:
        """
        使用LLM更新MEMORY.md

        Args:
            messages: 对话消息列表
            llm_service: LLM服务
        """
        # 提取对话内容
        conversation_text = "\n".join([
            f"{msg.get('role', 'unknown')}: {msg.get('content', '')}"
            for msg in messages[-5:]  # 只使用最近5条消息
        ])

        current_memory = self.memory_file.read_text(encoding="utf-8")

        # 构建提示词
        prompt = f"""你是一个记忆管理助手。请根据以下对话内容，更新长期记忆。

当前记忆：
{current_memory}

新的对话内容：
{conversation_text}

**⚠️ 长期记忆内容限制（CRITICAL - 必须严格遵守）**：

长期记忆只能包含以下三个章节，严禁新增其他章节：

### ✅ 允许的三个章节：

1. **## 用户偏好**：用户明确表达的习惯、要求、禁忌、工作方式
2. **## 领域知识**：可复用的业务规则、概念定义、数据含义、系统特性
3. **## 历史结论**：经过验证的、具有普适性的分析结论和规律

### 🚫 严禁保留到长期记忆的内容：

1. **具体任务内容**：某次具体查询、分析、操作的详细过程或结果
2. **技术架构细节**：系统架构、工具调用流程、数据流转路径
3. **一次性数据**：具体的data_id、临时查询结果、单次统计数值
4. **时间敏感信息**：具体某天/某月的排名、临时统计数据、时效性结论
5. **操作细节**：具体的工具调用步骤、中间过程、调试信息
6. **可查询数据**：可以通过数据库查询获得的任何数值数据

### 📝 格式要求：

- **章节固定**：只能使用"## 用户偏好"、"## 领域知识"、"## 历史结论"三个章节
- **禁止新增章节**：不能添加"## 重要数据"、"## 操作记录"等新章节
- **总长度限制**：长期记忆总字数不超过1500字
- **内容泛化**：将具体结论泛化为可复用知识

请执行以下任务：
1. 提取对话中的重要信息（只保留用户偏好、领域知识、重要结论）
2. 整合到当前记忆中（只能使用三个固定章节）
3. 去除重复、过时、以及所有具体任务细节和技术架构信息
4. 返回更新后的完整记忆内容（Markdown格式）

**重要**：
- 只返回更新后的记忆内容，不要有其他解释
- 保持简洁，记忆内容不超过1500字
- 严格遵守三个章节限制，不能新增章节
"""

        try:
            # 调用LLM
            response = await llm_service.chat(
                messages=[{"role": "user", "content": prompt}],
                max_tokens=2000
            )

            # 提取LLM返回的内容
            if isinstance(response, dict):
                new_memory = response.get("content", "")
            else:
                new_memory = str(response)

            # 限制大小
            if len(new_memory) > self.max_memory_size:
                new_memory = new_memory[:self.max_memory_size]

            # 更新MEMORY.md
            if new_memory.strip():
                self.memory_file.write_text(new_memory, encoding="utf-8")
                logger.debug("memory_updated_by_llm", new_size=len(new_memory))

        except Exception as e:
            logger.error(
                "failed_to_update_memory_with_llm",
                error=str(e),
                exc_info=True
            )

    def search_history(
        self,
        query: str,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        搜索HISTORY.md历史对话

        Args:
            query: 搜索关键词
            limit: 返回结果数量限制

        Returns:
            匹配的历史条目列表
        """
        try:
            history_content = self.history_file.read_text(encoding="utf-8")

            # 简单的文本搜索（按行匹配）
            results = []
            lines = history_content.split("\n")

            for i, line in enumerate(lines):
                if query.lower() in line.lower():
                    # 获取上下文（前后各2行）
                    context_start = max(0, i - 2)
                    context_end = min(len(lines), i + 3)
                    context = "\n".join(lines[context_start:context_end])

                    results.append({
                        "match": line.strip(),
                        "context": context,
                        "line_number": i + 1
                    })

                    if len(results) >= limit:
                        break

            logger.info(
                "history_searched",
                mode=self.mode,
                query=query,
                results_found=len(results)
            )
            return results

        except Exception as e:
            logger.error(
                "failed_to_search_history",
                error=str(e),
                exc_info=True
            )
            return []

    def get_user_preferences(self) -> Dict[str, Any]:
        """
        获取用户偏好（从MEMORY.md解析）

        Returns:
            用户偏好字典
        """
        try:
            memory_content = self.memory_file.read_text(encoding="utf-8")

            preferences = {}

            # 简单解析：提取 "用户偏好" 部分的内容
            if "## 用户偏好" in memory_content:
                section_start = memory_content.index("## 用户偏好")
                section_end = memory_content.find("\n##", section_start + 1)
                if section_end == -1:
                    section_end = len(memory_content)

                section_content = memory_content[section_start:section_end]

                # 提取条目（简化实现）
                pattern = r"-\s*(.+?):\s*(.+)"
                matches = re.findall(pattern, section_content)
                for key, value in matches:
                    preferences[key.strip()] = value.strip()

            return preferences

        except Exception as e:
            logger.error(
                "failed_to_get_user_preferences",
                error=str(e)
            )
            return {}


# ============================================================================
# 改进版记忆合并器（使用 JSON 响应，无需工具调用）
# ============================================================================

class ImprovedMemoryStore(MemoryStore):
    """
    改进版记忆存储（参考 nanobot）

    改进点：
    1. 使用JSON响应方式（更可靠）
    2. 失败重试机制（最多3次）
    3. 原始归档降级
    4. 更好的错误处理
    """

    _MAX_FAILURES_BEFORE_RAW_ARCHIVE = 3

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._consecutive_failures = 0

    @staticmethod
    def _format_messages(messages: List[Dict[str, Any]]) -> str:
        """格式化消息列表为文本（用于提示词）"""
        lines = []
        for message in messages:
            if not message.get("content"):
                continue

            role = message.get("role", "unknown").upper()
            content = message.get("content", "")

            # 添加工具使用信息
            tools = message.get("tools_used", [])
            tool_info = f" [工具: {', '.join(tools)}]" if tools else ""

            # 添加时间戳
            timestamp = message.get("timestamp", datetime.now().strftime("%Y-%m-%d %H:%M"))

            lines.append(f"[{timestamp}] {role}{tool_info}: {content}")

        return "\n".join(lines)

    async def consolidate_improved(
        self,
        messages: List[Dict[str, Any]],
        model: str = "mimo-v2-flash",
    ) -> bool:
        """
        改进版记忆合并（使用 JSON 响应）

        Args:
            messages: 要合并的消息列表
            model: 使用的模型

        Returns:
            是否成功合并
        """
        if not messages:
            return True

        from app.services.llm_service import LLMService

        current_memory = self.read_long_term()

        # 构造提示词（要求返回 JSON）
        prompt = f"""请分析以下对话并返回 JSON 格式的记忆合并结果。

## 当前长期记忆
{current_memory or "(空)"}

## 待处理的对话
{self._format_messages(messages)}

**任务**：
1. 分析对话内容，提取重要信息
2. 生成 history_entry：一段简洁的对话摘要（格式：[YYYY-MM-DD HH:MM] 摘要内容，包含关键事件、决策、主题，便于 grep 搜索）
3. 生成 memory_update：更新后的长期记忆（Markdown格式，包含所有原有记忆+新信息）

**⚠️ 长期记忆内容限制（CRITICAL - 必须严格遵守）**：

长期记忆只能包含以下三个章节，严禁新增其他章节：

### ✅ 允许的三个章节：

1. **## 用户偏好**：用户明确表达的习惯、要求、禁忌、工作方式
   - 例如：时间基准、工具使用偏好、输出格式要求
   - 每条偏好简明扼要，不超过30字

2. **## 领域知识**：可复用的业务规则、概念定义、数据含义、系统特性
   - 例如：数据表含义、字段说明、业务规则、系统限制
   - 只保留抽象知识，不包含具体数值

3. **## 历史结论**：经过验证的、具有普适性的分析结论和规律
   - 例如：数据质量规律、系统行为模式、可复用结论
   - 必须是泛化结论，不能是单次任务的发现

### 🚫 严禁保留到长期记忆的内容：

1. **具体任务内容**：某次具体查询、分析、操作的详细过程或结果
2. **技术架构细节**：系统架构、工具调用流程、数据流转路径
3. **一次性数据**：具体的data_id、临时查询结果、单次统计数值
4. **时间敏感信息**：具体某天/某月的排名、临时统计数据、时效性结论
5. **操作细节**：具体的工具调用步骤、中间过程、调试信息
6. **可查询数据**：可以通过数据库查询获得的任何数值数据

### 📝 格式要求：

- **章节固定**：只能使用"## 用户偏好"、"## 领域知识"、"## 历史结论"三个章节
- **禁止新增章节**：不能添加"## 重要数据"、"## 操作记录"等新章节
- **总长度限制**：长期记忆总字数不超过1500字
- **内容泛化**：将具体结论泛化为可复用知识

### 🔄 更新策略：

- 新信息与旧记忆冲突时，保留最新信息
- 删除重复或过时的信息
- 合并相似的信息条目
- 具体任务中发现的知识，要泛化后才能进入长期记忆

**返回格式（必须严格遵守）**：
```json
{{
    "history_entry": "对话摘要（可包含具体任务细节）",
    "memory_update": "更新后的长期记忆（只包含三个固定章节，删除所有任务细节和技术架构信息）"
}}
```

请只返回 JSON，不要有其他内容。"""

        try:
            # 使用现有的 JSON 响应方法
            llm_service = LLMService()
            response = await llm_service.call_llm_with_json_response(
                prompt=prompt,
                max_retries=2
            )

            # 直接验证返回的 JSON 对象（call_llm_with_json_response 返回的是原始 JSON）
            if not response:
                logger.warning(
                    "memory_consolidation_no_response",
                    user_id=self.user_id,
                    mode=self.mode
                )
                return self._fail_or_raw_archive(messages)

            # 调试日志：记录 LLM 返回的内容
            logger.info(
                "memory_consolidation_llm_response",
                user_id=self.user_id,
                mode=self.mode,
                response_keys=list(response.keys()),
                has_history_entry="history_entry" in response,
                has_memory_update="memory_update" in response
            )

            # 验证字段
            if "history_entry" not in response or "memory_update" not in response:
                logger.warning(
                    "memory_consolidation_missing_fields",
                    user_id=self.user_id,
                    mode=self.mode,
                    response_keys=list(response.keys()),
                    response_preview=str(response)[:500]
                )
                return self._fail_or_raw_archive(messages)

            entry = response["history_entry"]
            update = response["memory_update"]

            if not entry or not update:
                logger.warning(
                    "memory_consolidation_empty_fields",
                    user_id=self.user_id,
                    mode=self.mode
                )
                return self._fail_or_raw_archive(messages)

            # 保存到文件
            entry = str(entry).strip()
            update = str(update).strip()

            if not entry:
                logger.warning(
                    "memory_consolidation_empty_entry",
                    user_id=self.user_id,
                    mode=self.mode
                )
                return self._fail_or_raw_archive(messages)

            # 追加到历史
            self.append_history(entry)

            # 更新长期记忆
            if update != current_memory:
                self.write_long_term(update)

            # 重置失败计数
            self._consecutive_failures = 0
            logger.info(
                "memory_consolidation_success",
                user_id=self.user_id,
                mode=self.mode,
                messages_count=len(messages),
                entry_length=len(entry),
                memory_length=len(update)
            )
            return True

        except Exception as e:
            logger.exception(
                "memory_consolidation_failed",
                user_id=self.user_id,
                mode=self.mode,
                error=str(e)
            )
            return self._fail_or_raw_archive(messages)

    def append_history(self, entry: str) -> None:
        """追加到历史记录"""
        try:
            with open(self.history_file, "a", encoding="utf-8") as f:
                f.write(entry.rstrip() + "\n\n")
            logger.debug(
                "history_appended",
                user_id=self.user_id,
                mode=self.mode,
                entry_length=len(entry)
            )
        except Exception as e:
            logger.error(
                "failed_to_append_history",
                user_id=self.user_id,
                mode=self.mode,
                error=str(e)
            )
            raise

    def read_long_term(self) -> str:
        """读取长期记忆内容"""
        try:
            if not self.memory_file.exists():
                return ""

            content = self.memory_file.read_text(encoding="utf-8")

            # 过滤掉空内容或只有标题的情况
            if content.strip() in ["", "# 长期记忆 (MEMORY.md)", "# 长期记忆 (MEMORY.md)\n"]:
                return ""

            return content

        except Exception as e:
            logger.error(
                "failed_to_read_long_term_memory",
                user_id=self.user_id,
                mode=self.mode,
                error=str(e)
            )
            return ""

    def write_long_term(self, content: str) -> None:
        """写入长期记忆"""
        try:
            # 验证记忆内容
            validated_content = self._validate_and_clean_memory(content)

            self.memory_file.write_text(validated_content, encoding="utf-8")
            logger.info(
                "long_term_memory_updated",
                user_id=self.user_id,
                mode=self.mode,
                original_length=len(content),
                validated_length=len(validated_content)
            )
        except Exception as e:
            logger.error(
                "failed_to_write_long_term_memory",
                user_id=self.user_id,
                mode=self.mode,
                error=str(e)
            )
            raise

    def _validate_and_clean_memory(self, content: str) -> str:
        """
        验证和清理记忆内容，确保符合长期记忆要求

        Args:
            content: 原始记忆内容

        Returns:
            清理后的记忆内容
        """
        lines = content.split('\n')
        valid_lines = []
        allowed_sections = {"## 用户偏好", "## 领域知识", "## 历史结论"}
        current_section = None

        for line in lines:
            # 检查是否是章节标题
            if line.startswith("## "):
                section_name = line.strip()

                # 检查是否是允许的章节
                if section_name in allowed_sections:
                    current_section = section_name
                    valid_lines.append(line)
                else:
                    # 不允许的章节，跳过并记录警告
                    logger.warning(
                        "memory_section_not_allowed",
                        section=section_name,
                        user_id=self.user_id,
                        mode=self.mode
                    )
                    current_section = None
                continue

            # 如果当前在有效的章节中，保留内容
            if current_section is not None:
                # 过滤掉包含data_id的行
                if 'data_id:' in line or 'data_id：' in line:
                    logger.debug(
                        "memory_filtered_data_id",
                        line=line[:50],
                        user_id=self.user_id,
                        mode=self.mode
                    )
                    continue

                # 过滤掉包含技术架构细节的行
                forbidden_keywords = ['工具调用流程', '数据流转', '系统架构', '调用步骤']
                if any(keyword in line for keyword in forbidden_keywords):
                    logger.debug(
                        "memory_filtered_architecture_detail",
                        line=line[:50],
                        user_id=self.user_id,
                        mode=self.mode
                    )
                    continue

                valid_lines.append(line)

        # 重新构建内容
        cleaned_content = '\n'.join(valid_lines)

        # 硬性长度限制
        max_length = 5000
        if len(cleaned_content) > max_length:
            logger.warning(
                "memory_too_long_truncated",
                user_id=self.user_id,
                mode=self.mode,
                original_length=len(cleaned_content),
                max_length=max_length
            )
            cleaned_content = cleaned_content[:max_length] + "\n\n... (记忆已截断)"

        return cleaned_content

    def _fail_or_raw_archive(self, messages: List[Dict[str, Any]]) -> bool:
        """
        失败处理：增加失败计数，达到阈值后原始归档

        Returns:
            False - 仍需重试
            True - 已原始归档，不需要重试
        """
        self._consecutive_failures += 1

        if self._consecutive_failures < self._MAX_FAILURES_BEFORE_RAW_ARCHIVE:
            return False

        # 原始归档（直接保存消息，不通过 LLM）
        self._raw_archive(messages)
        self._consecutive_failures = 0
        return True

    def _raw_archive(self, messages: List[Dict[str, Any]]) -> None:
        """原始归档：直接将消息转存到 HISTORY.md"""
        ts = datetime.now().strftime("%Y-%m-%d %H:%M")
        formatted_messages = self._format_messages(messages)

        entry = f"[{ts}] [原始归档] {len(messages)} 条消息\n{formatted_messages}\n\n"

        self.append_history(entry)
        logger.warning(
            "memory_consolidation_raw_archive",
            user_id=self.user_id,
            mode=self.mode,
            messages_count=len(messages)
        )

    def append_fact(self, category: str, fact: str) -> None:
        """
        快速追加事实到对应章节

        Args:
            category: 事实类别（用户偏好/领域知识/历史结论/环境信息）
            fact: 事实内容
        """
        content = self.memory_file.read_text(encoding="utf-8")

        # 查找章节位置
        section_header = f"## {category}"

        if section_header in content:
            # 在章节末尾追加
            section_start = content.index(section_header)
            section_end = content.find("\n##", section_start + 1)
            if section_end == -1:
                section_end = len(content)

            before = content[:section_end]
            after = content[section_end:]
            new_content = f"{before}\n- {fact}{after}"
        else:
            # 章节不存在，创建新章节
            new_content = f"{content}\n## {category}\n\n- {fact}\n"

        self.memory_file.write_text(new_content, encoding="utf-8")
        logger.debug(
            "memory_fact_appended",
            category=category,
            fact_length=len(fact)
        )

    def replace_fact(self, old_text: str, new_text: str, category: str = None) -> bool:
        """
        替换记忆条目

        Args:
            old_text: 要替换的旧内容
            new_text: 新的内容
            category: 事实类别（可选，用于过滤）

        Returns:
            是否成功替换
        """
        content = self.memory_file.read_text(encoding="utf-8")

        # 如果指定category，只在该章节内搜索
        if category:
            section_header = f"## {category}"
            if section_header not in content:
                return False
            section_start = content.index(section_header)
            section_end = content.find("\n##", section_start + 1)
            if section_end == -1:
                section_end = len(content)
            section_content = content[section_start:section_end]

            if old_text in section_content:
                new_section_content = section_content.replace(old_text, new_text)
                new_content = content[:section_start] + new_section_content + content[section_end:]
                self.memory_file.write_text(new_content, encoding="utf-8")
                logger.debug(
                    "memory_fact_replaced",
                    category=category,
                    old_text_length=len(old_text),
                    new_text_length=len(new_text)
                )
                return True
            return False
        else:
            # 全文搜索
            if old_text in content:
                new_content = content.replace(old_text, new_text)
                self.memory_file.write_text(new_content, encoding="utf-8")
                logger.debug(
                    "memory_fact_replaced_global",
                    old_text_length=len(old_text),
                    new_text_length=len(new_text)
                )
                return True
            return False

    def remove_fact(self, text: str, category: str = None) -> bool:
        """
        删除记忆条目

        Args:
            text: 要删除的内容
            category: 事实类别（可选，用于过滤）

        Returns:
            是否成功删除
        """
        content = self.memory_file.read_text(encoding="utf-8")
        lines = content.split('\n')

        if category:
            # 只在指定章节内删除
            section_header = f"## {category}"
            in_section = False
            filtered_lines = []
            for line in lines:
                if line.startswith(section_header):
                    in_section = True
                    filtered_lines.append(line)
                elif line.startswith("## ") and in_section:
                    in_section = False
                    filtered_lines.append(line)
                elif in_section and text in line:
                    continue  # 跳过包含text的行
                else:
                    filtered_lines.append(line)
        else:
            # 全文删除
            filtered_lines = [line for line in lines if text not in line]

        new_content = '\n'.join(filtered_lines)
        self.memory_file.write_text(new_content, encoding="utf-8")

        removed = len(filtered_lines) < len(lines)
        if removed:
            logger.debug(
                "memory_fact_removed",
                category=category,
                text_length=len(text),
                lines_removed=len(lines) - len(filtered_lines)
            )
        return removed


class MemoryConsolidator:
    """
    记忆合并器（参考 nanobot）

    职责：
    1. 合并策略管理
    2. 会话锁定（避免并发冲突）
    3. Token预算控制
    4. 自动触发合并
    """

    _MAX_CONSOLIDATION_ROUNDS = 5
    _SAFETY_BUFFER = 1024  # Token估算的额外缓冲

    def __init__(
        self,
        context_window_tokens: int = 200000,
        max_completion_tokens: int = 4096,
    ):
        """
        初始化记忆合并器

        Args:
            context_window_tokens: 上下文窗口大小（tokens）
            max_completion_tokens: 最大完成tokens
        """
        self.context_window_tokens = context_window_tokens
        self.max_completion_tokens = max_completion_tokens
        self._locks: weakref.WeakValueDictionary[str, asyncio.Lock] = (
            weakref.WeakValueDictionary()
        )

    def get_lock(self, session_key: str) -> asyncio.Lock:
        """获取会话的合并锁（避免并发冲突）"""
        return self._locks.setdefault(session_key, asyncio.Lock())

    async def consolidate_messages(
        self,
        user_id: str,
        mode: str,
        messages: List[Dict[str, Any]],
        model: str = "mimo-v2-flash",
    ) -> bool:
        """
        合并消息到持久化存储

        Args:
            user_id: 用户ID
            mode: 模式标识
            messages: 要合并的消息列表
            model: 使用的模型

        Returns:
            是否成功
        """
        store = ImprovedMemoryStore(user_id=user_id, mode=mode)
        return await store.consolidate_improved(messages, model)

    async def maybe_consolidate_by_tokens(
        self,
        session_key: str,
        current_tokens: int,
        user_id: str,
        mode: str,
        messages: List[Dict[str, Any]],
        model: str = "mimo-v2-flash",
    ) -> bool:
        """
        根据 Token预算自动触发合并

        Args:
            session_key: 会话键
            current_tokens: 当前使用的tokens
            user_id: 用户ID
            mode: 模式标识
            messages: 当前消息列表
            model: 使用的模型

        Returns:
            是否执行了合并
        """
        if not messages:
            return False

        # 计算预算
        budget = self.context_window_tokens - self.max_completion_tokens - self._SAFETY_BUFFER
        target = budget // 2  # 目标：保持一半预算

        if current_tokens <= 0:
            return False

        # 如果在预算内，不需要合并
        if current_tokens < budget:
            logger.debug(
                "token_consolidation_idle",
                session_key=session_key,
                current_tokens=current_tokens,
                budget=budget
            )
            return False

        # 获取锁
        lock = self.get_lock(session_key)
        async with lock:
            # 需要移除的tokens
            tokens_to_remove = current_tokens - target

            # 计算要合并的消息数量（估算：每条消息平均500 tokens）
            avg_tokens_per_message = 500
            messages_to_consolidate = max(1, tokens_to_remove // avg_tokens_per_message)

            # 取最近的消息
            messages_chunk = messages[:messages_to_consolidate]

            if not messages_chunk:
                return False

            logger.info(
                "token_consolidation_triggered",
                session_key=session_key,
                current_tokens=current_tokens,
                budget=budget,
                messages_to_consolidate=len(messages_chunk)
            )

            # 执行合并
            success = await self.consolidate_messages(
                user_id=user_id,
                mode=mode,
                messages=messages_chunk,
                model=model,
            )

            return success
