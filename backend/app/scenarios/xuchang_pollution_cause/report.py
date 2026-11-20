"""④污染原因分析通报报告包生成：确定性 QMD → create_report_package。

通报正文（LLM 或确定性兜底文案）原样嵌入，另附区域对比、气象区间与
站点告警明细表；报告渲染复用通用 create_report_package / publish_report
工具链，不引入第二次 LLM 调用。
"""

from __future__ import annotations

import asyncio
import re
from pathlib import Path
from typing import Any

import structlog

from app.utils.path_config import format_agent_path, get_data_registry

logger = structlog.get_logger()

REPORT_TITLE = "许昌市污染原因分析通报"
REPORT_TYPE = "pollution_cause"
DOCX_MIME_TYPE = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
)
_WEATHER_METRICS = (
    ("temperature_2m", "气温(℃)"),
    ("relative_humidity_2m", "相对湿度(%)"),
    ("wind_speed_10m", "风速(m/s)"),
    ("precipitation", "降水(mm)"),
)
_ERA5_METRICS = (
    ("boundary_layer_height", "边界层高度(m)"),
    ("cloud_cover", "云量(%)"),
)
_SAFE_ID_CHARS = re.compile(r"[^A-Za-z0-9_-]")


def _fmt(value: Any, digits: int = 1, missing: str = "缺测") -> str:
    if value is None:
        return missing
    try:
        return f"{float(value):.{digits}f}"
    except (TypeError, ValueError):
        return str(value)


def _cell(value: Any, missing: str = "—") -> str:
    if value is None or str(value).strip() == "":
        return missing
    return str(value).replace("|", "\\|").replace("\n", "；")


def _markdown_table(headers: tuple[str, ...], rows: list[tuple[Any, ...]]) -> str:
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    lines.extend("| " + " | ".join(_cell(item) for item in row) + " |" for row in rows)
    return "\n".join(lines)


def _city_type(row: dict[str, Any]) -> str:
    if row.get("is_xuchang"):
        return "许昌"
    if row.get("is_neighbor"):
        return "相邻五市"
    return "其他城市"


def _weather_rows(intervals: dict[str, Any] | None) -> list[tuple[Any, ...]]:
    rows: list[tuple[Any, ...]] = []
    for source, source_name in (("nmc", "气象站观测"), ("era5", "ERA5")):
        section = (intervals or {}).get(source) or {}
        metric_fields = _WEATHER_METRICS if source == "nmc" else _ERA5_METRICS
        if not section or not any(section.get(key) for key, _ in metric_fields):
            continue
        for field, label in metric_fields:
            stats = section.get(field) or {}
            if not stats or not stats.get("valid_hours"):
                continue
            rows.append((
                source_name,
                label,
                stats.get("valid_hours"),
                _fmt(stats.get("min")),
                _fmt(stats.get("max")),
                _fmt(stats.get("mean")),
                _fmt(stats.get("sum"), missing="—") if field == "precipitation" else "—",
            ))
    return rows


def _strip_message_prefix(message: str) -> str:
    text = str(message or "").strip()
    lines = text.splitlines()
    if lines and lines[0].strip().startswith("【"):
        return "\n".join(lines[1:]).strip() or text
    return text


def build_pollution_cause_qmd(
    evidence: dict[str, Any],
    review_brief: dict[str, Any] | None,
    message: str,
) -> str:
    """把触发证据、回顾 brief 与通报正文组装成固定结构 QMD。"""
    target_date = str(evidence.get("target_date") or "")
    city_rows = [row for row in evidence.get("city_rows") or [] if isinstance(row, dict)]
    intervals = ((review_brief or {}).get("meteorology_intervals") or {})
    alert_list = [row for row in (review_brief or {}).get("alert_list") or [] if isinstance(row, dict)]

    lines = [
        "---",
        f'title: "{REPORT_TITLE}"',
        f'date: "{target_date}"',
        "preserve-template-structure: true",
        "lang: zh-CN",
        "format:",
        "  html:",
        "    toc: false",
        "    number-sections: false",
        "  docx:",
        "    toc: false",
        "    number-sections: false",
        "---", "",
        f"# {REPORT_TITLE}（{target_date}）", "",
        "## 一、通报正文", "",
        _strip_message_prefix(message), "",
        "## 附1、区域PM2.5日均值对比", "",
    ]
    if city_rows:
        lines.extend([
            _markdown_table(
                ("城市", "PM2.5(μg/m³)", "口径"),
                [(row.get("city"), _fmt(row.get("pm25")), _city_type(row)) for row in city_rows],
            ),
            "",
        ])
    else:
        lines.extend(["当日城市日值数据暂缺。", ""])
    rank = evidence.get("city_rank")
    if rank:
        lines.append(
            f"许昌当日PM2.5在全省{evidence.get('city_count') or '—'}市中列第{rank}位（1为浓度最高）。"
        )
        lines.append("")

    lines.extend(["## 附2、气象要素区间统计", ""])
    weather_rows = _weather_rows(intervals)
    if weather_rows:
        lines.extend([
            _markdown_table(
                ("来源", "要素", "有效小时", "最小", "最大", "均值", "累计"),
                weather_rows,
            ),
            "",
            "气象区间为描述性统计，不自动形成污染成因判断。", "",
        ])
    else:
        lines.extend(["昨日气象观测统计暂缺。", ""])

    lines.extend(["## 附3、站点快速告警过程", ""])
    if alert_list:
        lines.extend([
            _markdown_table(
                ("站点", "污染物", "开始", "结束", "峰值时间", "区域分类", "传输结论"),
                [(
                    row.get("station_name") or row.get("station_id"),
                    row.get("target_pollutant"),
                    str(row.get("episode_start") or "")[:16],
                    str(row.get("episode_end") or "")[:16],
                    str(row.get("peak_time") or "")[:16],
                    row.get("regional_classification"),
                    row.get("transport_conclusion"),
                ) for row in alert_list],
            ),
            "",
        ])
    else:
        lines.extend(["昨日无站点快速告警过程记录。", ""])

    lines.extend([
        "## 数据说明", "",
        f"- 触发口径：{evidence.get('rule_description') or '许昌PM2.5日均高于相邻五市均值分级阈值'}。",
        f"- 数据来源：{evidence.get('data_source') or '省平台城市日值'}；站点与气象明细来自场景2昨日回顾证据。",
        "- 本报告为数据分析结果，不认定具体污染责任。",
        "",
    ])
    return "\n".join(lines)


def write_pollution_cause_qmd(
    evidence: dict[str, Any],
    review_brief: dict[str, Any] | None,
    message: str,
    *,
    execution_id: str,
) -> dict[str, Any]:
    """落盘 QMD 源文件并返回 create_report_package 直接可用的入参。"""
    safe_execution = _SAFE_ID_CHARS.sub("_", str(execution_id or "").strip())
    if not safe_execution:
        raise ValueError("execution_id 不能为空")
    target_date = str(evidence.get("target_date") or "")
    date_dir = get_data_registry() / "xuchang_pollution_cause" / (
        target_date.replace("-", "") or "unknown"
    )
    output_path = date_dir / f"report_source_{safe_execution}.qmd"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        build_pollution_cause_qmd(evidence, review_brief, message),
        encoding="utf-8",
    )
    return {
        "report_id": f"xuchang_pollution_cause_{target_date.replace('-', '')}_{safe_execution}",
        "source_qmd_path": str(output_path),
        "assets": [],
    }


def _run_create_package(kwargs: dict[str, Any]) -> dict[str, Any]:
    """在线程私有事件循环里跑 create_report_package，隔离 Quarto 子进程阻塞。"""
    from app.tools.report.report_package.tool import CreateReportPackageTool

    async def _execute() -> dict[str, Any]:
        return await CreateReportPackageTool().execute(**kwargs)

    return asyncio.run(_execute())


async def generate_pollution_cause_report(
    evidence: dict[str, Any],
    review_brief: dict[str, Any] | None,
    message: str,
    *,
    task: Any,
    execution: Any,
) -> dict[str, Any]:
    """生成并发布污染原因分析报告包；调用方负责 fail-open。"""
    built = await asyncio.to_thread(
        write_pollution_cause_qmd,
        evidence,
        review_brief,
        message,
        execution_id=str(getattr(execution, "execution_id", "") or ""),
    )
    result = await asyncio.to_thread(
        _run_create_package,
        {
            "report_id": built["report_id"],
            "source_qmd_path": built["source_qmd_path"],
            "assets": built["assets"],
            "output_formats": ["html", "docx"],
            "title": REPORT_TITLE,
            "report_type": "analysis",
        },
    )
    if not result.get("success"):
        raise RuntimeError(str(result.get("summary") or "create_report_package 失败"))
    data = result.get("data") or {}
    render_results = data.get("render_results") or {}
    docx_result = render_results.get("docx") or {}
    docx_path = (docx_result.get("data") or {}).get("path")
    if not docx_path or not Path(str(docx_path)).is_file():
        raise RuntimeError("报告包未产出可用的 report.docx")
    report_dir = Path(str(data.get("report_dir") or Path(str(docx_path)).parent))
    html_path = report_dir / "report.html"
    target_date = str(evidence.get("target_date") or "")
    attachment_filename = f"污染原因分析通报_{target_date.replace('-', '')}.docx"

    try:
        from app.tools.report.report_package.tool import PublishReportTool

        publish_result = await PublishReportTool().execute(
            report_id=built["report_id"],
            title=f"{REPORT_TITLE}（{target_date}）",
            report_type=REPORT_TYPE,
            task_id=str(getattr(task, "task_id", "") or ""),
            execution_id=str(getattr(execution, "execution_id", "") or ""),
            period_start=target_date,
            period_end=target_date,
        )
        if not publish_result.get("success"):
            logger.warning(
                "xuchang_pollution_cause_report_publish_failed",
                report_id=built["report_id"],
                summary=publish_result.get("summary"),
            )
    except Exception:
        logger.warning("xuchang_pollution_cause_report_publish_error", exc_info=True)

    return {
        "report_id": built["report_id"],
        "docx_path": str(docx_path),
        "html_path": str(html_path),
        "agent_path": format_agent_path(Path(str(docx_path))),
        "attachment": {
            "path": format_agent_path(Path(str(docx_path))),
            "filename": attachment_filename,
            "mime": DOCX_MIME_TYPE,
        },
    }
