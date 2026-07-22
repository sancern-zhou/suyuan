from __future__ import annotations

import json
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
                state = self.projects.edit_source(
                    kwargs["project_dir"], kwargs["relative_path"], kwargs["content"], kwargs["base_revision"]
                )
                return self._state_result(state, "源码已更新；仅相关页面被标记为待重编译")
            if operation == "render":
                state = self.projects.inspect(kwargs["project_dir"])
                result = await self.compiler.preview(
                    state.project_dir, dirty_slides=state.dirty_slides, pages=kwargs.get("pages"),
                    cache_dir=Path(state.project_dir) / ".editable-ppt" / "cache",
                )
                return self._state_result(state, "Web 预览已渲染", **result)
            if operation == "compile":
                state = self.projects.inspect(kwargs["project_dir"])
                result = await self.compiler.compile(
                    state.project_dir, dirty_slides=state.dirty_slides,
                    cache_dir=Path(state.project_dir) / ".editable-ppt" / "cache",
                    editable=kwargs.get("editable", "strict"), file_name=kwargs.get("file_name", "presentation.pptx"),
                )
                if result.get("success"):
                    state = self.projects.mark_clean(state.project_dir, state.dirty_slides)
                self._record_json(state.project_dir, "last_compile.json", result)
                return self._state_result(state, "PPTX 编译完成" if result.get("success") else "PPTX 编译需要修订", **result)
            if operation == "validate":
                return await self._validate(kwargs["project_dir"], kwargs.get("pptx_path"))
            if operation == "restore":
                state = self.projects.restore_revision(kwargs["project_dir"], kwargs["revision"], kwargs["base_revision"])
                return self._state_result(state, f"已恢复 revision {kwargs['revision']}")
            if operation == "finalize":
                validation = await self._validate(kwargs["project_dir"], kwargs.get("pptx_path"))
                compile_result = self._read_json(kwargs["project_dir"], "last_compile.json")
                gate = build_editable_ppt_gate(
                    compile_result.get("report", {}), validation["data"].get("validation", {})
                )
                validation["success"] = gate.status == "passed"
                validation["summary"] = "严格编译与 PPTX 验证通过，可以交付" if validation["success"] else "质量门未通过，拒绝交付"
                validation["data"]["finalized"] = validation["success"]
                validation["data"]["quality_gate"] = gate.to_dict()
                return validation
            return self._failure("UNSUPPORTED_OPERATION", f"不支持的操作：{operation}")
        except RevisionConflictError as error:
            return self._failure("REVISION_CONFLICT", str(error), kwargs.get("project_dir"))
        except CompilerClientError as error:
            return self._failure(error.code, str(error), kwargs.get("project_dir"))
        except (KeyError, ValueError, OSError) as error:
            return self._failure("INVALID_REQUEST", str(error), kwargs.get("project_dir"))

    async def _validate(self, project_dir: str, pptx_path: str | None):
        state = self.projects.inspect(project_dir)
        path = pptx_path or str(Path(project_dir) / "build" / "pptx" / "presentation.pptx")
        if self.validator is None:
            from app.tools.office.validate_pptx_tool import ValidatePptxTool
            self.validator = ValidatePptxTool()
        result = await self.validator.execute(path=path)
        self._record_json(project_dir, "last_validation.json", result)
        return self._state_result(state, result.get("summary", "PPTX 验证完成"), validation=result, pptx_path=path, success=result.get("success", False))

    @staticmethod
    def _record_json(project_dir: str, name: str, value: dict[str, Any]):
        target = Path(project_dir) / ".editable-ppt" / name
        target.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    @staticmethod
    def _read_json(project_dir: str, name: str):
        target = Path(project_dir) / ".editable-ppt" / name
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
    def _failure(code: str, message: str, project_dir: str | None = None):
        return {
            "success": False, "summary": message,
            "data": {"project_dir": project_dir, "revision": None, "dirty_slides": [],
                     "issues": [{"code": code, "message": message}], "next_actions": ["修正请求后重试"]},
        }


tool = ManageEditablePptTool()
