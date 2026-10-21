from __future__ import annotations

import structlog

from .aggregator import MultiSourceTenderClient
from .base import TenderSource

logger = structlog.get_logger()

_ALIASES = {
    "qianlima": "qianlima",
    "qianlima360": "qianlima",
    "zhiliaobiaoxun": "zhiliaobiaoxun",
    "zhiliao": "zhiliaobiaoxun",
    "jianyu360": "jianyu360",
    "jianyu": "jianyu360",
    "cebpubservice": "cebpubservice",
    "zhaobiao": "zhaobiao",
    "zhaobiao.cn": "zhaobiao",
    "ggzy": "ggzy",
    "zhiliao_ai": "zhiliao_ai",
    "zhiliao-ai": "zhiliao_ai",
    "zlbx_ai": "zhiliao_ai",
    "public_resource": "ggzy",
}


def _build(name: str, config):
    if name == "qianlima":
        from .qianlima import build_qianlima_source

        return build_qianlima_source(config)
    if name == "zhiliaobiaoxun":
        from .zhiliao import build_zhiliao_source

        return build_zhiliao_source(config)
    if name == "jianyu360":
        from .jianyu import build_jianyu_source

        return build_jianyu_source(config)
    if name == "cebpubservice":
        from .cebpubservice import build_cebpubservice_source

        return build_cebpubservice_source(config)
    if name == "zhaobiao":
        from .zhaobiao import build_zhaobiao_source

        return build_zhaobiao_source(config)
    if name == "ggzy":
        from .ggzy import build_ggzy_source

        return build_ggzy_source(config)
    if name == "zhiliao_ai":
        from .zhiliao_ai import build_zhiliao_ai_source

        return build_zhiliao_ai_source(config)
    return None


def build_tender_sources(config, configured: str | None = None):
    """Build enabled tender sources from TENDER_SOURCES (comma separated)."""
    from config.settings import settings

    raw = configured if configured is not None else getattr(
        settings, "tender_sources", "qianlima"
    )
    names = [item.strip().lower() for item in (raw or "qianlima").split(",")]
    sources: list[TenderSource] = []
    for raw_name in names:
        if not raw_name:
            continue
        name = _ALIASES.get(raw_name, raw_name)
        try:
            source = _build(name, config)
        except Exception:  # noqa: BLE001
            logger.exception("tender_source_build_failed", source=name)
            continue
        if source is not None:
            sources.append(source)
    return sources


__all__ = ["MultiSourceTenderClient", "TenderSource", "build_tender_sources"]
