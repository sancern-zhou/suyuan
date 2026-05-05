"""Fact-driven expert deliberation API."""

import asyncio
from datetime import date, datetime
from html.parser import HTMLParser
from io import BytesIO
import json
import os
from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
import structlog

from app.routers.utils_docx import convert_docx_to_markdown
from app.services.expert_deliberation import ExpertDeliberationEngine
from app.services.expert_deliberation.schemas import (
    DeliberationRequest,
    DeliberationResult,
    ParsedInputFilesResult,
    TableInput,
)

logger = structlog.get_logger()

router = APIRouter(prefix="/expert-deliberation", tags=["expert-deliberation"])

SPREADSHEET_EXTENSIONS = {".xlsx", ".xls", ".csv"}
REPORT_EXTENSIONS = {".md", ".markdown", ".qmd", ".txt", ".docx", ".html", ".htm"}
DEFAULT_INPUT_DIR = Path(os.getenv("EXPERT_DELIBERATION_INPUT_DIR", "/tmp/A会商文件"))
STAGE5_REPORT_KEYWORDS = ("阶段5", "阶段五", "stage5", "stage_5", "深度分析", "成果")
RUN_ID_PATTERN = re.compile(r"^delib_[A-Za-z0-9_-]+$")


@router.post("/run", response_model=DeliberationResult)
async def run_deliberation(request: DeliberationRequest) -> DeliberationResult:
    """Run a fact-driven expert deliberation."""
    try:
        logger.info(
            "expert_deliberation_started",
            topic=request.topic,
            region=request.region,
            tables=len(request.consultation_tables),
            data_ids=len(request.data_ids),
        )
        result = await ExpertDeliberationEngine().run_async(request)
        logger.info(
            "expert_deliberation_completed",
            facts=len(result.facts),
            analyses=len(result.analyses),
            conclusions=len(result.conclusions),
        )
        return result
    except Exception as exc:
        logger.error("expert_deliberation_failed", error=str(exc), exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/run-stream")
async def run_deliberation_stream(request: DeliberationRequest) -> StreamingResponse:
    """Run expert deliberation and stream progress events with SSE."""

    async def event_stream():
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()

        async def publish(event: dict[str, Any]) -> None:
            await queue.put({"event": "progress", **event})

        async def run_engine() -> DeliberationResult:
            logger.info(
                "expert_deliberation_started",
                topic=request.topic,
                region=request.region,
                tables=len(request.consultation_tables),
                data_ids=len(request.data_ids),
                streamed=True,
            )
            return await ExpertDeliberationEngine().run_async(request, progress_callback=publish)

        task = asyncio.create_task(run_engine())
        yield _sse_data({"event": "connected", "message": "会商进度流已连接"})

        while not task.done() or not queue.empty():
            try:
                item = await asyncio.wait_for(queue.get(), timeout=0.5)
                yield _sse_data(item)
            except asyncio.TimeoutError:
                continue

        try:
            result = await task
            logger.info(
                "expert_deliberation_completed",
                facts=len(result.facts),
                analyses=len(result.analyses),
                conclusions=len(result.conclusions),
                streamed=True,
            )
            yield _sse_data({"event": "result", "result": result.model_dump(mode="json")})
        except Exception as exc:
            logger.error("expert_deliberation_failed", error=str(exc), streamed=True, exc_info=True)
            yield _sse_data({"event": "error", "message": str(exc)})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


def _sse_data(payload: dict[str, Any]) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False, default=str)}\n\n"


@router.get("/runs")
async def list_deliberation_runs(limit: int = 30) -> dict[str, Any]:
    """List persisted expert deliberation runs for historical conclusion review."""
    output_root = ExpertDeliberationEngine().output_root
    if not output_root.exists():
        return {"runs": []}

    run_dirs = [
        path for path in output_root.iterdir()
        if path.is_dir() and RUN_ID_PATTERN.match(path.name)
    ]
    run_dirs.sort(key=lambda path: path.stat().st_mtime, reverse=True)
    capped_limit = max(1, min(limit, 200))
    return {"runs": [_build_run_summary(path) for path in run_dirs[:capped_limit]]}


@router.get("/runs/{run_id}")
async def get_deliberation_run(run_id: str) -> dict[str, Any]:
    """Load a persisted expert deliberation run without re-running LLM or tools."""
    run_dir = _resolve_run_dir(run_id)
    if not run_dir.exists() or not run_dir.is_dir():
        raise HTTPException(status_code=404, detail="历史会商记录不存在")
    return _build_run_detail(run_dir)


@router.post("/parse-input-files", response_model=ParsedInputFilesResult)
async def parse_input_files(
    consultation_file: Optional[UploadFile] = File(None),
    monthly_report_file: Optional[UploadFile] = File(None),
    stage5_report_file: Optional[UploadFile] = File(None),
) -> ParsedInputFilesResult:
    """Parse uploaded fact source files into the deliberation input shape."""
    if not any([consultation_file, monthly_report_file, stage5_report_file]):
        raise HTTPException(status_code=400, detail="至少需要上传一个事实来源文件")

    warnings: List[str] = []
    consultation_tables: List[TableInput] = []
    monthly_report_text = ""
    stage5_report_text = ""

    try:
        if consultation_file:
            consultation_tables, table_warnings = await _parse_consultation_file(consultation_file)
            warnings.extend(table_warnings)
        if monthly_report_file:
            monthly_report_text, report_warnings = await _parse_report_file(
                monthly_report_file,
                "上月污染特征与溯源分析报告",
            )
            warnings.extend(report_warnings)
        if stage5_report_file:
            stage5_report_text, report_warnings = await _parse_report_file(
                stage5_report_file,
                "阶段5深度分析成果",
            )
            warnings.extend(report_warnings)

        logger.info(
            "expert_deliberation_input_files_parsed",
            tables=len(consultation_tables),
            monthly_report_chars=len(monthly_report_text),
            stage5_report_chars=len(stage5_report_text),
            warnings=len(warnings),
        )
        return ParsedInputFilesResult(
            consultation_tables=consultation_tables,
            monthly_report_text=monthly_report_text,
            stage5_report_text=stage5_report_text,
            warnings=warnings,
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("expert_deliberation_input_file_parse_failed", error=str(exc), exc_info=True)
        raise HTTPException(status_code=500, detail=f"解析事实文件失败：{exc}") from exc


@router.get("/default-input-files", response_model=ParsedInputFilesResult)
async def parse_default_input_files() -> ParsedInputFilesResult:
    """Parse default fact source files from /tmp/A会商文件."""
    warnings: List[str] = []
    consultation_tables: List[TableInput] = []
    monthly_report_parts: List[str] = []
    stage5_report_parts: List[str] = []

    input_dir = DEFAULT_INPUT_DIR
    if not input_dir.exists():
        return ParsedInputFilesResult(warnings=[f"默认会商文件目录不存在：{input_dir}"])
    if not input_dir.is_dir():
        return ParsedInputFilesResult(warnings=[f"默认会商文件路径不是目录：{input_dir}"])

    files = sorted(
        [path for path in input_dir.iterdir() if path.is_file()],
        key=lambda path: path.name,
    )
    supported_files = [
        path for path in files
        if path.suffix.lower() in SPREADSHEET_EXTENSIONS | REPORT_EXTENSIONS
    ]
    if not supported_files:
        return ParsedInputFilesResult(warnings=[f"默认会商文件目录中没有可解析文件：{input_dir}"])

    for path in supported_files:
        try:
            raw_bytes = path.read_bytes()
            extension = path.suffix.lower()
            if extension in SPREADSHEET_EXTENSIONS:
                tables, table_warnings = _parse_consultation_bytes(raw_bytes, path.name)
                consultation_tables.extend(tables)
                warnings.extend(table_warnings)
                continue

            report_text, report_warnings = _parse_report_bytes(raw_bytes, path.name, path.stem)
            warnings.extend(report_warnings)
            if not report_text:
                continue

            report_entry = f"# {path.name}\n\n{report_text}"
            if _is_stage5_report(path.name):
                stage5_report_parts.append(report_entry)
            else:
                monthly_report_parts.append(report_entry)
        except Exception as exc:
            warnings.append(f"{path.name} 解析失败：{exc}")

    if not consultation_tables and not monthly_report_parts and not stage5_report_parts:
        warnings.append(f"默认会商文件目录未解析到有效内容：{input_dir}")

    logger.info(
        "expert_deliberation_default_input_files_parsed",
        input_dir=str(input_dir),
        files=len(supported_files),
        tables=len(consultation_tables),
        monthly_report_chars=sum(len(text) for text in monthly_report_parts),
        stage5_report_chars=sum(len(text) for text in stage5_report_parts),
        warnings=len(warnings),
    )
    return ParsedInputFilesResult(
        consultation_tables=consultation_tables,
        monthly_report_text="\n\n".join(monthly_report_parts).strip(),
        stage5_report_text="\n\n".join(stage5_report_parts).strip(),
        warnings=warnings,
    )


@router.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "service": "expert-deliberation",
        "version": "0.1.0",
    }


def _resolve_run_dir(run_id: str) -> Path:
    if not RUN_ID_PATTERN.match(run_id):
        raise HTTPException(status_code=400, detail="非法会商记录编号")
    output_root = ExpertDeliberationEngine().output_root.resolve()
    run_dir = (output_root / run_id).resolve()
    try:
        run_dir.relative_to(output_root)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="非法会商记录路径") from exc
    return run_dir


def _build_run_summary(run_dir: Path) -> dict[str, Any]:
    request = _read_json(run_dir / "request.json", {})
    consensus = _read_json(run_dir / "consensus.json", {})
    analyses = _read_json(run_dir / "expert_analyses.json", [])
    facts = _read_jsonl(run_dir / "fact_ledger.jsonl")
    report_markdown = _read_text(run_dir / "expert_deliberation.md")
    created_at = _run_created_at(run_dir)
    conclusions = consensus.get("conclusions") if isinstance(consensus, dict) else []

    return {
        "run_id": run_dir.name,
        "created_at": created_at,
        "topic": request.get("topic") or _infer_topic(report_markdown),
        "region": request.get("region") or "未知",
        "time_range": request.get("time_range") or {},
        "pollutants": request.get("pollutants") or [],
        "facts_count": len(facts),
        "analyses_count": len(analyses) if isinstance(analyses, list) else 0,
        "conclusions_count": len(conclusions) if isinstance(conclusions, list) else 0,
        "report_preview": _report_preview(report_markdown),
        "output_files": _run_output_files(run_dir),
    }


def _build_run_detail(run_dir: Path) -> dict[str, Any]:
    request = _read_json(run_dir / "request.json", {})
    consensus = _read_json(run_dir / "consensus.json", {})
    report_markdown = _read_text(run_dir / "expert_deliberation.md")
    facts = _read_jsonl(run_dir / "fact_ledger.jsonl")
    analyses = _read_json(run_dir / "expert_analyses.json", [])
    discussion_turns = _read_json(run_dir / "discussion_ledger.json", [])
    timeline_events = _read_json(run_dir / "timeline_events.json", [])
    forbidden_claims = _read_json(run_dir / "forbidden_claims.json", [])

    if not isinstance(consensus, dict):
        consensus = {}

    return {
        "run_id": run_dir.name,
        "created_at": _run_created_at(run_dir),
        "topic": request.get("topic") or _infer_topic(report_markdown),
        "region": request.get("region") or "未知",
        "time_range": request.get("time_range") or {},
        "pollutants": request.get("pollutants") or [],
        "facts": facts,
        "experts": consensus.get("experts") or [],
        "analyses": analyses if isinstance(analyses, list) else [],
        "discussion_turns": discussion_turns if isinstance(discussion_turns, list) else [],
        "evidence_matrix": consensus.get("evidence_matrix") or _read_json(run_dir / "evidence_matrix.json", []),
        "timeline_events": timeline_events if isinstance(timeline_events, list) else [],
        "conclusions": consensus.get("conclusions") or [],
        "dissents": consensus.get("dissents") or [],
        "forbidden_claims": forbidden_claims if isinstance(forbidden_claims, list) else [],
        "report_markdown": report_markdown,
        "output_files": _run_output_files(run_dir),
        "request": request,
    }


def _read_json(path: Path, default: Any) -> Any:
    try:
        if not path.exists():
            return default
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("expert_deliberation_history_json_read_failed", path=str(path), error=str(exc))
        return default


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    try:
        with path.open("r", encoding="utf-8") as file:
            for line in file:
                text = line.strip()
                if text:
                    rows.append(json.loads(text))
    except Exception as exc:
        logger.warning("expert_deliberation_history_jsonl_read_failed", path=str(path), error=str(exc))
    return rows


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8") if path.exists() else ""
    except Exception as exc:
        logger.warning("expert_deliberation_history_text_read_failed", path=str(path), error=str(exc))
        return ""


def _run_output_files(run_dir: Path) -> dict[str, str]:
    names = {
        "request": "request.json",
        "fact_ledger": "fact_ledger.jsonl",
        "expert_analyses": "expert_analyses.json",
        "discussion_ledger": "discussion_ledger.json",
        "evidence_matrix": "evidence_matrix.json",
        "timeline_events": "timeline_events.json",
        "consensus": "consensus.json",
        "forbidden_claims": "forbidden_claims.json",
        "report_markdown": "expert_deliberation.md",
    }
    return {
        key: str(run_dir / filename)
        for key, filename in names.items()
        if (run_dir / filename).exists()
    }


def _run_created_at(run_dir: Path) -> str:
    parts = run_dir.name.split("_")
    if len(parts) >= 3:
        try:
            return datetime.strptime(f"{parts[1]}_{parts[2]}", "%Y%m%d_%H%M%S").isoformat(timespec="seconds")
        except ValueError:
            pass
    return datetime.fromtimestamp(run_dir.stat().st_mtime).isoformat(timespec="seconds")


def _infer_topic(report_markdown: str) -> str:
    for line in report_markdown.splitlines():
        if line.startswith("**会商主题**"):
            return line.split("：", 1)[-1].strip() or "历史专家会商"
    return "历史专家会商"


def _report_preview(report_markdown: str) -> str:
    for line in report_markdown.splitlines():
        text = line.strip()
        if text and not text.startswith("#") and not text.startswith("|") and not text.startswith("**"):
            return text[:180]
    return ""


async def _parse_consultation_file(file: UploadFile) -> Tuple[List[TableInput], List[str]]:
    filename = file.filename or "会商表格"
    raw_bytes = await file.read()
    return _parse_consultation_bytes(raw_bytes, filename)


def _parse_consultation_bytes(raw_bytes: bytes, filename: str) -> Tuple[List[TableInput], List[str]]:
    extension = Path(filename).suffix.lower()
    if extension not in SPREADSHEET_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"会商表格不支持 {extension or '无扩展名'} 文件")

    if not raw_bytes:
        raise HTTPException(status_code=400, detail=f"{filename} 文件为空")

    warnings: List[str] = []
    try:
        if extension == ".csv":
            dataframe = _read_csv(raw_bytes)
            tables = [_dataframe_to_table(dataframe, Path(filename).stem or filename)]
        else:
            sheets = pd.read_excel(BytesIO(raw_bytes), sheet_name=None)
            tables = [
                _dataframe_to_table(dataframe, str(sheet_name))
                for sheet_name, dataframe in sheets.items()
            ]
    except ImportError as exc:
        raise HTTPException(status_code=400, detail=f"{filename} 解析依赖缺失：{exc}") from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"{filename} 解析失败：{exc}") from exc

    tables = [table for table in tables if table.rows]
    if not tables:
        warnings.append(f"{filename} 未解析到有效数据行")
    return tables, warnings


async def _parse_report_file(file: UploadFile, label: str) -> Tuple[str, List[str]]:
    filename = file.filename or label
    raw_bytes = await file.read()
    return _parse_report_bytes(raw_bytes, filename, label)


def _parse_report_bytes(raw_bytes: bytes, filename: str, label: str) -> Tuple[str, List[str]]:
    extension = Path(filename).suffix.lower()
    if extension not in REPORT_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"{label} 不支持 {extension or '无扩展名'} 文件")

    if not raw_bytes:
        return "", [f"{filename} 文件为空"]

    if extension == ".docx":
        return convert_docx_to_markdown(raw_bytes).strip(), []
    if extension in {".html", ".htm"}:
        return _html_to_text(_decode_text(raw_bytes)).strip(), []
    return _decode_text(raw_bytes).strip(), []


def _is_stage5_report(filename: str) -> bool:
    normalized = filename.lower()
    return any(keyword.lower() in normalized for keyword in STAGE5_REPORT_KEYWORDS)


def _read_csv(raw_bytes: bytes) -> pd.DataFrame:
    last_error: Optional[Exception] = None
    for encoding in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            return pd.read_csv(BytesIO(raw_bytes), encoding=encoding)
        except UnicodeDecodeError as exc:
            last_error = exc
    if last_error:
        raise last_error
    return pd.read_csv(BytesIO(raw_bytes))


def _decode_text(raw_bytes: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            return raw_bytes.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw_bytes.decode("utf-8", errors="ignore")


class _HTMLTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._parts: List[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        if tag in {"script", "style", "noscript"}:
            self._skip_depth += 1
            return
        if tag in {"p", "div", "section", "article", "header", "footer", "br", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6"}:
            self._parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript"} and self._skip_depth:
            self._skip_depth -= 1
            return
        if tag in {"p", "div", "section", "article", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6"}:
            self._parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        text = data.strip()
        if text:
            self._parts.append(text)

    def text(self) -> str:
        raw_text = " ".join(self._parts)
        lines = [" ".join(line.split()) for line in raw_text.splitlines()]
        return "\n".join(line for line in lines if line)


def _html_to_text(html_text: str) -> str:
    parser = _HTMLTextExtractor()
    parser.feed(html_text)
    parser.close()
    return parser.text()


def _dataframe_to_table(dataframe: pd.DataFrame, name: str) -> TableInput:
    normalized = dataframe.copy()
    normalized.columns = [
        str(column).strip() if str(column).strip() else f"字段{index + 1}"
        for index, column in enumerate(normalized.columns)
    ]
    normalized = normalized.where(pd.notna(normalized), None)
    rows: List[Dict[str, Any]] = []
    for record in normalized.to_dict(orient="records"):
        cleaned = {}
        for key, value in record.items():
            jsonable_value = _to_jsonable_value(value)
            if jsonable_value is not None:
                cleaned[str(key)] = jsonable_value
        if cleaned:
            rows.append(cleaned)
    return TableInput(name=name, source_type="consultation_table", rows=rows)


def _to_jsonable_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, float) and pd.isna(value):
        return None
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if hasattr(value, "item"):
        try:
            return value.item()
        except ValueError:
            return str(value)
    return value
