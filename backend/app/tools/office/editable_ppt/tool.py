from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

import structlog

from app.tools.base.tool_interface import LLMTool, ToolCategory
from app.tools.office.editable_ppt.compiler_client import (
    CompilerClientError,
    EditablePptCompilerClient,
)
from app.tools.office.editable_ppt.diagnostics import PptDiagnosticBuilder
from app.tools.office.editable_ppt.project_service import (
    EditablePptProjectService,
    RevisionConflictError,
)
from app.tools.office.editable_ppt.quality import build_editable_ppt_gate
from app.tools.office.editable_ppt.report_store import PptReportStore, ReportRefError

logger = structlog.get_logger()


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
                    _branch("read_report", ["project_dir", "report_ref"], {
                        **PROJECT,
                        "report_ref": {"type": "string"},
                        "pages": {"type": "array", "items": {"type": "integer", "minimum": 1}},
                        "codes": {"type": "array", "items": {"type": "string", "minLength": 1}},
                        "element_ids": {"type": "array", "items": {"type": "string", "minLength": 1}},
                    }),
                    _branch("render", ["project_dir"], {
                        **PROJECT,
                        "pages": {"type": "array", "items": {"type": "integer", "minimum": 1}},
                        "expected_slide_count": {"type": "integer", "minimum": 1},
                    }),
                    _branch("compile", ["project_dir"], {
                        **PROJECT,
                        "editable": {"type": "string", "enum": ["strict", "compatible"], "default": "strict"},
                        "file_name": {"type": "string", "pattern": "^[^/\\\\]+\\.pptx$", "default": "presentation.pptx"},
                        "expected_slide_count": {"type": "integer", "minimum": 1},
                    }),
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
            if operation == "read_report":
                state = self.projects.inspect(kwargs["project_dir"])
                pages = self._optional_list(kwargs.get("pages"), "pages", item_type=int)
                codes = self._optional_list(kwargs.get("codes"), "codes", item_type=str)
                element_ids = self._optional_list(
                    kwargs.get("element_ids"), "element_ids", item_type=str
                )
                report = self._report_store(state.project_dir).read(
                    kwargs["report_ref"],
                    pages=pages,
                    codes=codes,
                    element_ids=element_ids,
                )
                return self._state_result(state, "PPT 原始报告读取完成", report=report)
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
                result = self._with_expected_slide_count(
                    state.project_dir, result, kwargs.get("expected_slide_count")
                )
                return self._diagnostic_result(
                    state,
                    "render",
                    result,
                    "Web 预览已渲染" if result.get("success") else "Web 预览需要修订",
                )
            if operation == "compile":
                state = self.projects.inspect(kwargs["project_dir"])
                compile_revision = state.revision
                compile_hashes = state.hashes
                result = await self.compiler.compile(
                    state.project_dir, dirty_slides=state.dirty_slides,
                    cache_dir=Path(state.project_dir) / ".editable-ppt" / "cache",
                    editable=kwargs.get("editable", "strict"), file_name=kwargs.get("file_name", "presentation.pptx"),
                )
                result = self._with_expected_slide_count(
                    state.project_dir, result, kwargs.get("expected_slide_count")
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
                return self._diagnostic_result(
                    state,
                    "compile",
                    result,
                    "PPTX 编译完成" if result.get("success") else "PPTX 编译需要修订",
                )
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
                validation_state, validation_path, raw_validation, validation_passed = (
                    await self._run_validation_raw(state.project_dir, str(target))
                )
                self._record_json(state.project_dir, "last_validation.json", raw_validation)
                gate = build_editable_ppt_gate(
                    compile_result.get("report", {}),
                    raw_validation.get("data", raw_validation),
                )
                validation = self._diagnostic_result(
                    validation_state,
                    "validate",
                    raw_validation,
                    "严格编译与 PPTX 验证通过，可以交付"
                    if gate.status == "passed" and validation_passed
                    else "质量门未通过，拒绝交付",
                    success=gate.status == "passed" and validation_passed,
                    facts={"pptx_path": validation_path, "validation_passed": validation_passed},
                )
                validation["success"] = gate.status == "passed" and validation_passed
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
        except ReportRefError as error:
            return self._failure("INVALID_REPORT_REF", str(error), kwargs.get("project_dir"))
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

    async def _run_validation_raw(self, project_dir: str, pptx_path: str | None):
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
        payload = result.get("data", result)
        passed = bool(result.get("success")) and payload.get("gate", {}).get("passed", payload.get("success", False))
        return state, path, result, passed

    async def _validate(self, project_dir: str, pptx_path: str | None):
        state, path, result, passed = await self._run_validation_raw(project_dir, pptx_path)
        self._record_json(project_dir, "last_validation.json", result)
        return self._diagnostic_result(
            state,
            "validate",
            result,
            result.get("summary", "PPTX 验证完成"),
            success=passed,
            facts={"pptx_path": path, "validation_passed": passed},
        )

    @staticmethod
    def _optional_list(value: Any, field: str, *, item_type: type):
        if isinstance(value, str):
            value = json.loads(value)
        if value is None:
            return None
        if not isinstance(value, list) or any(
            not isinstance(item, item_type)
            or (item_type is int and isinstance(item, bool))
            or (item_type is int and item < 1)
            or (item_type is str and not item)
            for item in value
        ):
            raise ValueError(f"{field} 格式不正确")
        return value

    @staticmethod
    def _deck_slide_count(project_dir: str) -> int | None:
        try:
            deck = json.loads(Path(project_dir, "deck.json").read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, TypeError):
            return None
        slides = deck.get("slides")
        return len(slides) if isinstance(slides, list) else None

    def _with_expected_slide_count(
        self,
        project_dir: str,
        raw: dict[str, Any],
        expected_slide_count: Any,
    ) -> dict[str, Any]:
        if expected_slide_count is None:
            return raw
        expected = self._positive_int(expected_slide_count, "expected_slide_count")
        report = raw.get("report") if isinstance(raw.get("report"), dict) else {}
        actual = raw.get("slideCount") or report.get("slideCount") or self._deck_slide_count(project_dir)
        if actual == expected:
            if raw.get("slideCount") is not None or report.get("slideCount") is not None:
                return raw
            augmented = copy.deepcopy(raw)
            augmented["slideCount"] = actual
            return augmented
        augmented = copy.deepcopy(raw)
        augmented["success"] = False
        augmented.setdefault("issues", []).append({
            "code": "REQUESTED_PAGE_COUNT_MISMATCH",
            "message": f"要求 {expected} 页，当前项目为 {actual} 页",
            "sourcePath": "deck.json",
            "expected": expected,
            "actual": actual,
            "severity": "error",
        })
        return augmented

    @staticmethod
    def _report_store(project_dir: str) -> PptReportStore:
        return PptReportStore(project_dir)

    def _diagnostic_result(
        self,
        state,
        operation: str,
        raw: dict[str, Any],
        summary: str,
        *,
        success: bool | None = None,
        facts: dict[str, Any] | None = None,
    ):
        raw_chars = len(json.dumps(raw, ensure_ascii=False, default=str))
        try:
            report_ref = self._report_store(state.project_dir).persist(
                operation, state.revision, raw
            )
        except OSError as error:
            return self._failure(
                "REPORT_PERSIST_FAILED",
                f"完整 PPT 报告保存失败：{error}",
                state.project_dir,
            )
        previous = self._read_json(state.project_dir, "last_diagnostic.json") or None
        builder = PptDiagnosticBuilder(state.project_dir)
        diagnostic = builder.build(operation, raw, report_ref, previous)
        self._record_json(state.project_dir, "last_diagnostic.json", diagnostic)
        compact_facts = facts or self._compact_facts(operation, raw)
        public_success = bool(raw.get("success")) if success is None else success
        result = self._state_result(
            state,
            summary,
            success=public_success,
            diagnostic=diagnostic,
            report_ref=report_ref,
            recommended_action=builder.recommended_action(diagnostic),
            suggested_stage=self._suggested_stage(operation, diagnostic, public_success),
            **compact_facts,
        )
        if not public_success:
            source_paths = result["data"]["recommended_action"]["source_paths"]
            joined_paths = "、".join(source_paths) or "diagnostic.issues 对应源码"
            if diagnostic["status"] == "unchanged":
                result["data"]["next_actions"] = [
                    f"诊断未变化；重新读取 {joined_paths} 和必要原始证据，重新判断根因后再修改"
                ]
            else:
                result["data"]["next_actions"] = [
                    f"读取 {joined_paths}，按 diagnostic.issues 的共同根因批量修复后重新检查"
                ]
        envelope_chars = len(json.dumps(result, ensure_ascii=False, default=str))
        logger.info(
            "ppt_diagnostic_envelope_built",
            operation=operation,
            revision=state.revision,
            raw_chars=raw_chars,
            envelope_chars=envelope_chars,
            issue_count=diagnostic["issue_count"],
            fingerprint=diagnostic["fingerprint"],
            diagnostic_status=diagnostic["status"],
        )
        return result

    @staticmethod
    def _compact_facts(operation: str, raw: dict[str, Any]) -> dict[str, Any]:
        report = raw.get("report") if isinstance(raw.get("report"), dict) else {}
        measurement = report.get("measurement") if isinstance(report.get("measurement"), dict) else {}
        facts: dict[str, Any] = {
            "slide_count": raw.get("slideCount") or report.get("slideCount"),
        }
        if operation == "render":
            facts["preview_dir"] = raw.get("previewDir") or measurement.get("previewDir")
        elif operation == "compile":
            facts.update({
                "pptxPath": raw.get("pptxPath"),
                "editable": report.get("editable"),
                "forbidden_raster_fallbacks": report.get("forbiddenRasterFallbacks"),
                "measurement_cache": measurement.get("cache"),
                "sourceRevision": raw.get("sourceRevision"),
                "sourceHashes": raw.get("sourceHashes"),
                "pptxSha256": raw.get("pptxSha256"),
            })
        return {key: value for key, value in facts.items() if value is not None}

    @staticmethod
    def _suggested_stage(operation: str, diagnostic: dict[str, Any], success: bool) -> str:
        if operation == "render" and diagnostic.get("issue_count"):
            return "preview_fixing"
        if operation == "compile" and diagnostic.get("issue_count"):
            return "compile_fixing"
        if operation == "compile" and success:
            return "validating"
        if operation == "validate" and success:
            return "ready_to_finalize"
        return "source_draft"

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
