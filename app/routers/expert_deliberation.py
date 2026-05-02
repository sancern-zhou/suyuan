"""Fact-driven expert deliberation API."""

from datetime import date, datetime
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
from fastapi import APIRouter, File, HTTPException, UploadFile
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
REPORT_EXTENSIONS = {".md", ".markdown", ".txt", ".docx"}


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
        result = ExpertDeliberationEngine().run(request)
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


@router.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "service": "expert-deliberation",
        "version": "0.1.0",
    }


async def _parse_consultation_file(file: UploadFile) -> Tuple[List[TableInput], List[str]]:
    filename = file.filename or "会商表格"
    extension = Path(filename).suffix.lower()
    if extension not in SPREADSHEET_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"会商表格不支持 {extension or '无扩展名'} 文件")

    raw_bytes = await file.read()
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
    extension = Path(filename).suffix.lower()
    if extension not in REPORT_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"{label} 不支持 {extension or '无扩展名'} 文件")

    raw_bytes = await file.read()
    if not raw_bytes:
        return "", [f"{filename} 文件为空"]

    if extension == ".docx":
        return convert_docx_to_markdown(raw_bytes).strip(), []
    return _decode_text(raw_bytes).strip(), []


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
