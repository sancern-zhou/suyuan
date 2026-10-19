"""Bounded personal memory operations on server-injected documents only."""

import asyncio
import os
import re
import tempfile
from contextlib import contextmanager
from datetime import date
from hashlib import sha256
from pathlib import Path

import yaml

from app.agent.memory.memory_limits import MEMORY_MD_MAX_CHARS, memory_capacity_error
from app.social.assistant_request import require_assistant_request
from app.tools.base import LLMTool, ToolCategory
from app.utils.path_config import resolve_agent_path


@contextmanager
def _locked(path):
    with path.open("a+b") as stream:
        if os.name == "nt":
            import msvcrt

            stream.seek(0, 2)
            if not stream.tell():
                stream.write(b"0")
                stream.flush()
            stream.seek(0)
            msvcrt.locking(stream.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl

            fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            if os.name == "nt":
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


class ManageAssistantMemoryTool(LLMTool):
    def __init__(self):
        description = (
            "读取、更新或删除本人的长期记忆和用户档案条目，不接受路径或用户身份。"
            "document=fact 时仅可 read，fact_id 来自当前个人事实索引，不能编辑事实层。"
            "先 read 获取 revision；update 未给 old_text 时追加，给出时精确替换唯一条目；"
            "delete 必须指定唯一 old_text，只删除该条目。修改必须携带 expected_revision。"
            "仅保存用户明确希望记住的稳定事实和偏好，临时进度使用事项工具。"
        )
        super().__init__(
            name="manage_assistant_memory",
            description=description,
            category=ToolCategory.TASK_MANAGEMENT,
            requires_context=True,
            function_schema={
                "name": "manage_assistant_memory",
                "description": description,
                "parameters": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "action": {"type": "string", "enum": ["read", "update", "delete"]},
                        "document": {"type": "string", "enum": ["long_term", "profile", "fact"]},
                        "fact_id": {"type": "string", "pattern": "^fact-[0-9a-f]{16}$"},
                        "expected_revision": {"type": "string"},
                        "old_text": {"type": "string", "minLength": 1, "maxLength": 12000},
                        "new_text": {"type": "string", "minLength": 1, "maxLength": 12000},
                    },
                    "required": ["action", "document"],
                },
            },
        )

    async def execute(
        self,
        context=None,
        action=None,
        document=None,
        fact_id=None,
        expected_revision=None,
        old_text=None,
        new_text=None,
        data_context_manager=None,
        **kwargs,
    ):
        try:
            if kwargs or action not in {"read", "update", "delete"}:
                raise ValueError("不支持的参数或操作")
            store = getattr(context, "assistant_memory_store", None)
            if getattr(context, "runtime_mode", None) != "assistant" or store is None:
                raise PermissionError("当前会话未绑定个人记忆")
            if store.mode != "assistant" or not store.user_id or store.user_id == "global":
                raise PermissionError("不能访问共享记忆")
            if document == "fact":
                if (
                    action != "read"
                    or not isinstance(fact_id, str)
                    or not re.fullmatch(r"fact-[0-9a-f]{16}", fact_id)
                ):
                    raise ValueError("事实层只允许用索引中的 fact_id 读取")
                path = resolve_agent_path(store.workspace) / "facts" / f"{fact_id}.md"
                if path.resolve().parent != resolve_agent_path(store.workspace) / "facts":
                    raise PermissionError("事实文档不在当前用户的记忆空间")
                content = await asyncio.to_thread(path.read_text, encoding="utf-8")
                if not content.startswith("---\n"):
                    raise ValueError("事实文档格式无效")
                metadata = yaml.safe_load(content[4:].split("\n---\n", 1)[0])
                if not isinstance(metadata, dict) or not isinstance(
                    metadata.get("metadata") or {}, dict
                ):
                    raise ValueError("事实文档格式无效")
                expiry = (metadata.get("metadata") or {}).get("valid_until")
                if expiry and str(expiry) < date.today().isoformat():
                    raise ValueError("该事实已过期")
                return {
                    "success": True,
                    "status": "success",
                    "data": {"document": "fact", "fact_id": fact_id, "content": content},
                }
            if fact_id is not None:
                raise ValueError("fact_id 仅用于读取事实层")
            if action != "read":
                require_assistant_request(context.session_id)
                if getattr(context, "scheduled_task_context", None):
                    raise PermissionError("后台任务不能修改个人档案")
            if document == "long_term":
                path = resolve_agent_path(store.memory_file)
            elif document == "profile" and getattr(context, "assistant_profile_path", None):
                path = resolve_agent_path(context.assistant_profile_path)
            else:
                raise ValueError("个人文档不可用")
            # The two documents must belong to the same server-bound workspace.
            root = Path(store.workspace).resolve()
            if path.resolve().parent != root or path.name not in {"MEMORY.md", "USER.md"}:
                raise PermissionError("个人文档不在当前用户的记忆空间")
            data = await asyncio.to_thread(
                self._operate, path, action, expected_revision, old_text, new_text
            )
            return {"success": True, "status": "success", "data": {"document": document, **data}}
        except (ValueError, PermissionError) as exc:
            return {"success": False, "status": "failed", "error": str(exc)}
        except (OSError, yaml.YAMLError):
            return {
                "success": False,
                "status": "failed",
                "error": "个人记忆存储暂不可用，请查询后重试",
            }

    @staticmethod
    def _operate(path, action, expected_revision, old_text, new_text):
        with _locked(path.parent / ".assistant-memory.lock"):
            content = path.read_text(encoding="utf-8") if path.exists() else ""
            revision = sha256(content.encode()).hexdigest()
            if action == "read":
                return {"content": content, "revision": revision}
            if not expected_revision or expected_revision != revision:
                raise ValueError("记忆版本冲突，请重新 read 后修改")
            if old_text is not None:
                if (
                    not isinstance(old_text, str)
                    or not old_text.strip()
                    or content.count(old_text) != 1
                ):
                    raise ValueError("old_text 必须精确匹配唯一非空条目")
            if action == "delete":
                if old_text is None or new_text is not None:
                    raise ValueError("delete 需要 old_text 且不能提供 new_text")
                updated = content.replace(old_text, "", 1)
            else:
                if not isinstance(new_text, str) or not new_text.strip():
                    raise ValueError("update 需要非空 new_text")
                updated = (
                    content.replace(old_text, new_text, 1)
                    if old_text is not None
                    else content.rstrip() + "\n\n" + new_text.strip() + "\n"
                )
            if len(updated) > MEMORY_MD_MAX_CHARS:
                raise ValueError(memory_capacity_error(len(updated)))
            temporary = None
            try:
                with tempfile.NamedTemporaryFile(
                    mode="w",
                    encoding="utf-8",
                    dir=path.parent,
                    prefix=".assistant-memory-",
                    delete=False,
                ) as stream:
                    temporary = Path(stream.name)
                    stream.write(updated)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary, path)
            finally:
                if temporary is not None:
                    temporary.unlink(missing_ok=True)
            return {"revision": sha256(updated.encode()).hexdigest(), "chars": len(updated)}
