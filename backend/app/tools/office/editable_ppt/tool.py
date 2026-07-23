from __future__ import annotations

import json
import hashlib
from pathlib import Path
from typing import Any

from app.tools.base.tool_interface import LLMTool, ToolCategory
from app.tools.office.editable_ppt.compiler_client import CompilerClientError, EditablePptCompilerClient
from app.tools.office.editable_ppt.project_service import (
    EditablePptProjectService,
    RevisionConflictError,
)
from app.tools.office.editable_ppt.quality import build_editable_ppt_gate


def _branch(operation: str, required: list[str], properties: dict[str, Any] | None = None):
    base = {
        "operation": {"const": operation, "description": f"执行 {operation} 操作"},
        **(properties or {}),
    }
    return {"type": "object", "properties": base, "required": ["operation", *required], "additionalProperties": False}


PROJECT = {"project_dir": {"type": "string", "description": "可编辑 PPT 源码项目绝对路径"}}


class ManageEditablePptTool(LLMTool):
    def __init__(self, project_service=None, compiler_client=None, validator=None):
        schema = {
            "name": "manage_editable_ppt",
            "description": (
                "创建、直接读取/编辑、预览、编译和交付源码优先的高质量 PPT。"
                "源码是普通 JSON/JS/资源文档，可被 read_file/edit_file 多次修改；随后 inspect 会自动协调版本。"
            ),
            "parameters": {
                "type": "object",
                "oneOf": [
                    _branch("create", ["title"], {"title": {"type": "string"}, "theme": {"type": "string", "enum": ["government", "business", "data-analysis"], "default": "business"}}),
                    _branch("inspect", ["project_dir"], PROJECT),
                    _branch("read_source", ["project_dir", "relative_path"], {**PROJECT, "relative_path": {"type": "string"}}),
                    _branch("edit_source", ["project_dir", "relative_path", "content", "base_revision"], {**PROJECT, "relative_path": {"type": "string"}, "content": {"type": "string"}, "base_revision": {"type": "integer", "minimum": 1}}),
                    _branch("edit_sources", ["project_dir", "edits", "base_revision"], {
                        **PROJECT,
                        "edits": {
                            "type": "array",
                            "minItems": 1,
                            "items": {
                                "type": "object",
                                "properties": {
                                    "relative_path": {"type": "string"},
                                    "content": {"type": "string"},
                                },
                                "required": ["relative_path", "content"],
                                "additionalProperties": False,
                            },
                        },
                        "base_revision": {"type": "integer", "minimum": 1},
                    }),
                    _branch("render", ["project_dir"], {**PROJECT, "pages": {"type": "array", "items": {"type": "integer", "minimum": 1}}}),
                    _branch("compile", ["project_dir"], {**PROJECT, "editable": {"type": "string", "enum": ["strict", "compatible"], "default": "strict"}, "file_name": {"type": "string", "pattern": "^[^/\\\\]+\\.pptx$", "default": "presentation.pptx"}}),
                    _branch("validate", ["project_dir"], {**PROJECT, "pptx_path": {"type": "string"}}),
                    _branch("restore", ["project_dir", "revision", "base_revision"], {**PROJECT, "revision": {"type": "integer", "minimum": 1}, "base_revision": {"type": "integer", "minimum": 1}}),
                    _branch("finalize", ["project_dir"], {**PROJECT, "pptx_path": {"type": "string"}}),
                ]
            },
        }
        super().__init__(
            name="manage_editable_ppt",
            description=schema["description"],
            category=ToolCategory.REPORTING,
            function_schema=schema,
            version="1.0.0",
            requires_context=False,
        )
        self.projects = project_service or EditablePptProjectService()
        self.compiler = compiler_client or EditablePptCompilerClient()
        self.validator = validator

    async def execute(self, operation: str, **kwargs) -> dict[str, Any]:
        try:
            if operation == "create":
                state = self.projects.create_project(kwargs["title"], kwargs.get("theme", "business"))
                return self._state_result(state, "已创建可直接编辑的 PPT 源码项目")
            if operation == "inspect":
                state = self.projects.inspect(kwargs["project_dir"])
                compiler = await self.compiler.inspect(state.project_dir)
                return self._state_result(state, "项目检查完成", compiler=compiler)
            if operation == "read_source":
                state = self.projects.inspect(kwargs["project_dir"])
                content = self.projects.read_source(state.project_dir, kwargs["relative_path"])
                return self._state_result(state, "源码读取完成", relative_path=kwargs["relative_path"], content=content)
            if operation == "edit_source":
                base_revision = self._positive_int(kwargs["base_revision"], "base_revision")
                state = self.projects.edit_source(
                    kwargs["project_dir"], kwargs["relative_path"], kwargs["content"], base_revision
                )
                return self._state_result(state, "源码已更新；仅相关页面被标记为待重编译")
            if operation == "edit_sources":
                base_revision = self._positive_int(kwargs["base_revision"], "base_revision")
                edits = kwargs["edits"]
                if isinstance(edits, str):
                    edits = json.loads(edits)
                if not isinstance(edits, list) or not edits or any(
                    not isinstance(edit, dict)
                    or not isinstance(edit.get("relative_path"), str)
                    or not isinstance(edit.get("content"), str)
                    for edit in edits
                ):
                    raise ValueError("edits 必须是包含 relative_path 与 content 的非空数组")
                state = self.projects.edit_sources(
                    kwargs["project_dir"], edits, base_revision
                )
                return self._state_result(
                    state,
                    f"已在单一 revision 中原子更新 {len(edits)} 个源码文档",
                )
            if operation == "render":
                state = self.projects.inspect(kwargs["project_dir"])
                pages = kwargs.get("pages")
                if isinstance(pages, str):
                    pages = json.loads(pages)
                if pages is not None and (
                    not isinstance(pages, list)
                    or any(not isinstance(page, int) or isinstance(page, bool) or page < 1 for page in pages)
                ):
                    raise ValueError("pages 必须是正整数数组")
                result = await self.compiler.preview(
                    state.project_dir, dirty_slides=state.dirty_slides, pages=pages,
                    cache_dir=Path(state.project_dir) / ".editable-ppt" / "cache",
                )
                return self._state_result(state, "Web 预览已渲染", **result)
            if operation == "compile":
                state = self.projects.inspect(kwargs["project_dir"])
                compile_revision = state.revision
                compile_hashes = state.hashes
                result = await self.compiler.compile(
                    state.project_dir, dirty_slides=state.dirty_slides,
                    cache_dir=Path(state.project_dir) / ".editable-ppt" / "cache",
                    editable=kwargs.get("editable", "strict"), file_name=kwargs.get("file_name", "presentation.pptx"),
                )
                if result.get("success"):
                    pptx_path = Path(result["pptxPath"]).resolve()
                    result.update({
                        "sourceRevision": compile_revision,
                        "sourceHashes": compile_hashes,
                        "pptxSha256": self._sha256(pptx_path),
                    })
                if result.get("success"):
                    state = self.projects.mark_clean(state.project_dir, state.dirty_slides)
                self._record_json(state.project_dir, "last_compile.json", result)
                return self._state_result(state, "PPTX 编译完成" if result.get("success") else "PPTX 编译需要修订", **result)
            if operation == "validate":
                return await self._validate(kwargs["project_dir"], kwargs.get("pptx_path"))
            if operation == "restore":
                revision = self._positive_int(kwargs["revision"], "revision")
                base_revision = self._positive_int(kwargs["base_revision"], "base_revision")
                state = self.projects.restore_revision(kwargs["project_dir"], revision, base_revision)
                return self._state_result(state, f"已恢复 revision {kwargs['revision']}")
            if operation == "finalize":
                state = self.projects.inspect(kwargs["project_dir"])
                compile_result = self._read_json(kwargs["project_dir"], "last_compile.json")
                target = Path(kwargs.get("pptx_path") or compile_result.get("pptxPath", "")).resolve()
                stale = (
                    bool(state.dirty_slides)
                    or compile_result.get("sourceRevision") != state.revision
                    or compile_result.get("sourceHashes") != state.hashes
                    or not target.is_file()
                    or target != Path(compile_result.get("pptxPath", "")).resolve()
                    or compile_result.get("pptxSha256") != (self._sha256(target) if target.is_file() else None)
                )
                if stale:
                    return self._failure("STALE_COMPILE_ARTIFACT", "源码、revision 或 PPTX 已变化，必须重新 strict 编译", state.project_dir)
                validation = await self._validate(state.project_dir, str(target))
                gate = build_editable_ppt_gate(
                    compile_result.get("report", {}), validation["data"].get("validation", {})
                )
                validation["success"] = gate.status == "passed"
                validation["summary"] = "严格编译与 PPTX 验证通过，可以交付" if validation["success"] else "质量门未通过，拒绝交付"
                validation["data"]["finalized"] = validation["success"]
                validation["data"]["quality_gate"] = gate.to_dict()
                if validation["success"]:
                    self._record_json(state.project_dir, "finalized.json", {
                        "sourceRevision": compile_result["sourceRevision"],
                        "sourceHashes": compile_result["sourceHashes"],
                        "pptxPath": str(target),
                        "pptxSha256": compile_result["pptxSha256"],
                        "qualityGate": gate.to_dict(),
                    })
                return validation
            return self._failure("UNSUPPORTED_OPERATION", f"不支持的操作：{operation}")
        except RevisionConflictError as error:
            return self._failure("REVISION_CONFLICT", str(error), kwargs.get("project_dir"))
        except CompilerClientError as error:
            diagnostic = error.stderr.strip()[:8000]
            return self._failure(
                error.code,
                str(error),
                kwargs.get("project_dir"),
                evidence={"stderr": diagnostic} if diagnostic else None,
                next_action=(
                    f"按编译器诊断修正源码后重试：{diagnostic}"
                    if diagnostic else "修正请求后重试"
                ),
            )
        except (KeyError, ValueError, OSError) as error:
            return self._failure("INVALID_REQUEST", str(error), kwargs.get("project_dir"))

    async def _validate(self, project_dir: str, pptx_path: str | None):
        state = self.projects.inspect(project_dir)
        path = pptx_path or str(Path(project_dir) / "build" / "pptx" / "presentation.pptx")
        theme_path = Path(project_dir) / "theme.json"
        theme = json.loads(theme_path.read_text(encoding="utf-8")) if theme_path.is_file() else {}
        expected_fonts = list(dict.fromkeys(
            font for font in (theme.get("fontTitle"), theme.get("fontBody")) if font
        ))
        if self.validator is None:
            from app.tools.office.validate_pptx_tool import ValidatePptxTool
            self.validator = ValidatePptxTool()
        result = await self.validator.execute(path=path, expected_fonts=expected_fonts)
        self._record_json(project_dir, "last_validation.json", result)
        payload = result.get("data", result)
        passed = bool(result.get("success")) and payload.get("gate", {}).get("passed", payload.get("success", False))
        return self._state_result(state, result.get("summary", "PPTX 验证完成"), validation=payload, pptx_path=path, success=passed)

    @staticmethod
    def _sha256(path: Path):
        return hashlib.sha256(path.read_bytes()).hexdigest()

    @staticmethod
    def _positive_int(value: Any, field: str) -> int:
        if isinstance(value, str) and value.isdecimal():
            value = int(value)
        if not isinstance(value, int) or isinstance(value, bool) or value < 1:
            raise ValueError(f"{field} 必须是正整数")
        return value

    @staticmethod
    def _record_json(project_dir: str, name: str, value: dict[str, Any]):
        target = Path(project_dir) / ".editable-ppt" / name
        target.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    @staticmethod
    def _read_json(project_dir: str, name: str):
        target = (Path(project_dir) / ".editable-ppt" / name).resolve()
        return json.loads(target.read_text(encoding="utf-8")) if target.is_file() else {}

    @staticmethod
    def _state_result(state, summary: str, success: bool = True, **extra):
        return {
            "success": success,
            "summary": summary,
            "data": {
                "project_dir": state.project_dir, "revision": state.revision,
                "dirty_slides": state.dirty_slides, **extra,
                "next_actions": [] if success else ["根据 issues 修改对应源码后重新编译"],
            },
        }

    @staticmethod
    def _failure(
        code: str,
        message: str,
        project_dir: str | None = None,
        *,
        evidence: dict[str, Any] | None = None,
        next_action: str = "修正请求后重试",
    ):
        issue = {"code": code, "message": message}
        if evidence:
            issue["evidence"] = evidence
        return {
            "success": False, "summary": message,
            "data": {"project_dir": project_dir, "revision": None, "dirty_slides": [],
                     "issues": [issue], "next_actions": [next_action]},
        }


tool = ManageEditablePptTool()
